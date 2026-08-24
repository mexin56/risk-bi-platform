# 授信归因预计算优化方案(DuckDB + Dagster)

> 目标:归因结果每日定时预计算并存入 DuckDB,线上接口直接读结果,
> dashboard 冷启动从 **~114s** 降到 **<1s**;同时保留在线兜底计算能力。
>
> 结论先行:**方案可行且方向正确**,但需做 3 个关键调整(见 §1)。

---

## 0. 现状基线(实测)

| 项目 | 现状 |
|---|---|
| dashboard 冷计算 | ~114s(约 38 个 MaxCompute SQL 作业,分 6 波串行) |
| 缓存 | 内存 15min + 磁盘 JSON(`server/data/attribution_cache/*.json`) |
| path-trend 点击 | 每条路径实时查 MaxCompute(~7s) |
| partitions/ranges 冷启动 | 5 分区 × 串行 MIN/MAX ≈ 35s |
| 数据规模 | 单 pt 近 17 天窗口聚合后数据量很小(缓存 JSON 约 1MB) |

关键观察:**最终结果很小,但每次都要扫 MaxCompute 重算**。预计算的收益/成本比极高。

---

## 1. 对原提案的评估与 3 个关键调整

原提案「DuckDB 存储 + 定时调度 + 系统直接读」正确,直接采纳。以下 3 点必须调整:

### 调整 1:DuckDB 不能同时被调度进程写、API 进程读
DuckDB 的并发模型是**同一文件要么多连接只读、要么单连接读写**,跨进程"一写一读"会锁冲突
(Windows 上尤其严格)。因此分层解决:

```
Dagster 管线(写) ──► attribution.duckdb          ← 源表 / 历史档案 / 可 SQL 查询
                    │  管线末步导出快照(原子替换)
                    └──► data/serving/*.parquet   ← API 只读这一层(duckdb 内存模式直查)
```

- API 用 `duckdb.connect(":memory:")` 直查 parquet,**零文件锁问题**;
- 每个 parquet 文件整体替换,天然原子性;
- `pyarrow` 已在依赖里,无新增重量级依赖。

### 调整 2:path-trend 必须一并预计算
现在点击预警路径会实时查一次 MaxCompute。预计算后如果这条还在线查,体验割裂。
做法:管线末步把**当前全部预警路径(merged_alerts 全量,suppressed 含内)**的 15 天日序列
用现有的条件聚合模式(`_grouped_for_condition_sets` 同款,一条 SQL 扫完所有路径)算好存入
`attr_path_daily`,接口改为纯读。

### 调整 3:`force=true` 语义重新定义
预计算后"强制刷新"不再是现场重算,而是:
1. 先返回旧快照(沿用现有 `async_refresh` 机制);
2. 后台触发一次 Dagster run(或直接子进程调用管线入口);
3. 完成后新快照落盘,前端下次轮询拿到新数据。
同时保留「MaxCompute 在线兜底」:当快照缺失且 Dagster 不可用时,走现有 runner 保证页面可用。

### 其余设计决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 算法口径 | **完全复用 `WarehouseAttributionRunner`**,不改算法 | 口径已对齐 Excel 报告 v2.4,动算法=引入回归风险 |
| `offset > 0` 历史窗口 | 不预计算,首次访问时在线算并**懒物化**入 DuckDB | 组合爆炸(offset 0..180),实际低频 |
| 配置变更 | runs 表记 `config_hash`;检测到变化自动重跑近 N 天 | 阈值/维度调整后口径一致 |
| 前端 | **零改动** | API 契约不变 |

---

## 2. 总体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Dagster(调度层)                          │
│  schedule: 每日 07:30 Asia/Shanghai                              │
│  sensor:   新 pt 分区就绪检测(上游 MaxCompute 产出后触发)         │
│  job:      check_partition → compute_attribution → export_serving │
└──────────────┬──────────────────────────────────────────────────┘
               │ 写                                    │ 导出快照
               ▼                                       ▼
   server/data/attribution.duckdb        server/data/serving/
   ├ attr_runs          (运行批次)        ├ latest_dashboard.parquet
   ├ attr_summary       (run 汇总)        ├ alerts.parquet
   ├ attr_alerts        (合并预警主表)    ├ alert_windows.parquet
   ├ attr_alert_windows (窗口明细)        ├ daily_trend.parquet
   ├ attr_daily_trend   (大盘日序列)      ├ path_daily.parquet
   ├ attr_path_daily    (路径×日 预计算)  ├ summary.parquet
   ├ attr_suppressed    (免归因路径)      ├ partitions.parquet
   └ dim_partitions     (分区范围)        └ meta.json(指向最新 run_id)
               ▲                                       │
               │ 兜底(仅当快照缺失)                   │ 只读
┌──────────────┴───────────────┐        ┌──────────────┴─────────────┐
│  MaxCompute(现有 warehouse) │        │  FastAPI(app.py)           │
│  WarehouseAttributionRunner  │◄───────│  dashboard()/path-trend()  │
└──────────────────────────────┘ 兜底   └────────────────────────────┘
                                                 ▲
                                        前端(零改动)
```

读取优先级(API 内):

```
内存缓存 → serving 快照(parquet) → DuckDB(跨天历史查询用) → 在线 MaxCompute 兜底
```

---

## 3. DuckDB 表设计

```sql
-- 运行批次:每次计算的元信息(幂等键 = pt + offset + config_hash 的最新一次)
CREATE TABLE IF NOT EXISTS attr_runs (
    run_id         VARCHAR PRIMARY KEY,   -- '20260822_0_<config_hash8>'
    pt             VARCHAR NOT NULL,
    offset_days    INTEGER NOT NULL DEFAULT 0,
    config_version VARCHAR NOT NULL,      -- 'v2.4'
    config_hash    VARCHAR NOT NULL,      -- sha1(config.json)[:12]
    window_start   DATE,
    window_end     DATE,
    table_date_min VARCHAR,
    table_date_max VARCHAR,
    generated_at   TIMESTAMP NOT NULL,
    duration_ms    INTEGER,
    source         VARCHAR NOT NULL       -- 'dagster' | 'lazy_offset' | 'fallback_online'
);

CREATE TABLE IF NOT EXISTS attr_summary (
    run_id VARCHAR PRIMARY KEY REFERENCES attr_runs(run_id),
    payload JSON                                -- summary 整体(json_safe 后)
);

-- 合并预警主表(含 suppressed 标记位;排序字段冗余便于 SQL 直接出 Top-N)
CREATE TABLE IF NOT EXISTS attr_alerts (
    run_id         VARCHAR NOT NULL REFERENCES attr_runs(run_id),
    id             VARCHAR NOT NULL,            -- 原 sha1 前 12 位
    canonical_path VARCHAR NOT NULL,
    path           VARCHAR NOT NULL,
    source         VARCHAR,
    layer          VARCHAR,
    level          INTEGER,
    level_label    VARCHAR,
    severity       VARCHAR,
    anomaly_type   VARCHAR,
    primary_window VARCHAR,
    hit_windows    JSON,                        -- ["1d","3d"]
    observation_count DOUBLE,
    growth_factor  DOUBLE,
    structure_lift_factor DOUBLE,
    z_score        DOUBLE,
    excess_count   DOUBLE,
    relative_strength DOUBLE,
    conditions     JSON,                        -- [{field,value,label}]
    is_expert_forced BOOLEAN,
    rule_note      VARCHAR,
    is_suppressed  BOOLEAN,
    enters_next_level BOOLEAN,
    drilldown_rule VARCHAR,
    sort_rank      INTEGER,                     -- 服务端排序后的名次
    PRIMARY KEY (run_id, id)
);

-- 每路径 × 每窗口 的完整窗口指标(windows 字典拆平)
CREATE TABLE IF NOT EXISTS attr_alert_windows (
    run_id VARCHAR NOT NULL,
    alert_id VARCHAR NOT NULL,
    window_key VARCHAR NOT NULL,                -- '1d'/'3d'/'7d'
    label VARCHAR, color VARCHAR, purpose VARCHAR,
    baseline_start DATE, baseline_end DATE,
    observation_start DATE, observation_end DATE,
    baseline_days INTEGER, observation_days INTEGER,
    baseline_count DOUBLE, observation_count DOUBLE,
    baseline_daily DOUBLE, observation_daily DOUBLE,
    baseline_share DOUBLE, observation_share DOUBLE,
    growth_factor DOUBLE, structure_lift_factor DOUBLE,
    structure_change DOUBLE,
    expected_count DOUBLE, excess_count DOUBLE, z_score DOUBLE,
    level INTEGER, level_label VARCHAR, severity VARCHAR,
    PRIMARY KEY (run_id, alert_id, window_key),
    FOREIGN KEY (run_id, alert_id) REFERENCES attr_alerts(run_id, id)
);

-- 大盘日序列
CREATE TABLE IF NOT EXISTS attr_daily_trend (
    run_id VARCHAR NOT NULL REFERENCES attr_runs(run_id),
    date DATE NOT NULL,
    application_count DOUBLE, approval_count DOUBLE,
    expert_seed_count DOUBLE, focus_path_count DOUBLE,
    PRIMARY KEY (run_id, date)
);

-- ★ 路径 × 日 预计算(path-trend 接口直接读,消灭点击时 7s 查询)
CREATE TABLE IF NOT EXISTS attr_path_daily (
    run_id VARCHAR NOT NULL REFERENCES attr_runs(run_id),
    alert_id VARCHAR NOT NULL,
    date DATE NOT NULL,
    application_count DOUBLE,
    total_application_count DOUBLE,
    PRIMARY KEY (run_id, alert_id, date)
);

-- 免归因(suppressed)路径
CREATE TABLE IF NOT EXISTS attr_suppressed (
    run_id VARCHAR NOT NULL REFERENCES attr_runs(run_id),
    id VARCHAR NOT NULL, canonical_path VARCHAR NOT NULL, path VARCHAR,
    level INTEGER, level_label VARCHAR, severity VARCHAR,
    primary_window VARCHAR, observation_count DOUBLE,
    growth_factor DOUBLE, structure_lift_factor DOUBLE, z_score DOUBLE,
    suppression_reasons JSON, conditions JSON, windows JSON,
    PRIMARY KEY (run_id, id)
);

-- top_k 下钻结构 + expert 强制链(结构化收益低,整块 JSON 存)
CREATE TABLE IF NOT EXISTS attr_structures (
    run_id VARCHAR PRIMARY KEY REFERENCES attr_runs(run_id),
    top_k JSON, expert JSON, rules JSON
);

-- 分区范围(partitions 接口直接读,消灭冷启动 35s 串行 MIN/MAX)
CREATE TABLE IF NOT EXISTS dim_partitions (
    pt VARCHAR PRIMARY KEY,
    min_day VARCHAR, max_day VARCHAR,
    row_hint BIGINT,
    refreshed_at TIMESTAMP
);
```

要点:
- 主键幂等:**同 `(pt, offset)` 重跑 = 新 run_id 替换 serving 层指针,DuckDB 里保留历史批次**
  (天然获得"每天归因结果的历史留痕",后续可做预警路径的时间演化分析);
- `payload JSON` 列存 `json_safe` 后的整体结构,装配响应时优先用它,拆平表用于查询分析。

---

## 4. 计算管线(Dagster Assets / Jobs)

代码布局:

```
server/
├── pipeline/
│   ├── __init__.py
│   ├── definitions.py        # Dagster Definitions(job/schedule/sensor)
│   ├── assets.py             # 4 个 asset
│   ├── store.py              # DuckDB 写入层(store.py 只在管线进程使用)
│   ├── exporter.py           # duckdb → serving parquet 导出 + meta.json 指针
│   ├── assemble.py           # ★ 从存储层装配出与现有 API 完全同构的响应 JSON
│   └── cli.py                # python -m pipeline.cli run [--pt ...] (force 触发入口)
```

### Assets

```python
# assets.py(骨架)
@asset
def latest_partition(context) -> str:
    """检查 MaxCompute 最新可用 pt(行数阈值校验,防半成品分区)。"""

@asset
def attribution_result(context, latest_partition) -> dict:
    """复用 WarehouseAttributionRunner.run() 得到完整 result dict(算法零改动)。"""

@asset
def path_trends(context, attribution_result) -> dict:
    """一条 UNION ALL 条件聚合 SQL 扫出全部 merged_alerts 路径的 15 天日序列。"""

@asset
def publish(context, attribution_result, path_trends) -> None:
    """写 DuckDB(事务) → 导出 serving parquet → 原子更新 meta.json 指针。"""
```

`publish` 内部顺序(保证任何时刻 API 都读到完整一致的快照):

```
BEGIN TRANSACTION → INSERT runs/summary/alerts/windows/trend/path_daily/structures → COMMIT
→ 逐表 EXPORT 到 data/serving/*.parquet.tmp → os.replace 原子改名
→ 最后写 data/serving/meta.json {"latest_run_id": ..., "pt": ..., "generated_at": ...}
```

### Job / Schedule / Sensor

```python
nightly_job = define_asset_job("nightly_attribution", selection="*")

schedule = ScheduleDefinition(
    job=nightly_job,
    cron_schedule="30 7 * * *",            # 07:30 Asia/Shanghai,避开上游产分区时段
    execution_timezone="Asia/Shanghai",
)

@run_status_sensor(run_status=DagsterRunStatus.FAILURE, monitored_jobs=[nightly_job])
def nightly_failure_sensor(context): ...   # 记日志/可扩展 webhook

@sensor(job=nightly_job, minimum_interval_seconds=1800)
def new_partition_sensor(context):
    """每 30min 探测新 pt;发现即补跑(覆盖 schedule 因上游延迟漏掉的情况)。"""
```

补充能力:
- **Backfill**:历史 5 个 pt(20260803/0819/0820/0821/0822)一次性物化;
  Dagster UI 或 `dagster asset materialize-selection` 均可发起;
- **手动触发**:`python -m server.pipeline.cli run --pt 20260822`;
  API 的 `force=true` 也走这个入口(子进程,不阻塞请求线程)。

### 部署(Windows 本机)

| 进程 | 启动方式 |
|---|---|
| FastAPI(8010) | 现状不变 |
| `dagster daemon` | 常驻(负责 schedule/sensor) |
| `dagster dev`(或 webserver) | 常驻(UI + 触发入口),端口 3001 仅本机/内网 |
| run storage | 默认 SQLite($DAGSTER_HOME),本机规模足够 |

用 Windows 任务计划程序或 NSSM 注册为开机自启;`$DAGSTER_HOME` 设为
`server/dagster_home/`(gitignore)。

---

## 5. API 改造(app.py,改动收敛在 AttributionService)

```python
class AttributionService:
    def dashboard(self, partition=None, force=False, offset=0):
        # 1) 内存缓存命中(15min)——不变
        # 2) ★ 新增:serving 快照命中(pt+offset 匹配 meta.json)→ deepcopy 返回,cache_hit=True
        # 3) ★ 新增:offset>0 且快照未覆盖 → 查 attr_runs 是否已有该 (pt,offset) 物化结果
        # 4) force=true:返回旧数据 + 后台触发 cli 子进程重算(async_refresh 机制复用)
        # 5) 兜底:快照/DuckDB 全 miss 且非 force → 现有在线 runner 原路径(逻辑不动)
        #    并把结果顺手写入 DuckDB(source='fallback_online'),下次就是秒读

    def path_trend(self, record_id, partition=None, offset=0):
        # ★ 主路径:SELECT ... FROM attr_path_daily WHERE run_id=? AND alert_id=?  (<10ms)
        #   与 daily_context 拼装 summary 的纯计算逻辑抽到 assemble.py 共用
        # 兜底:快照缺该路径时走现有 _exact_daily 在线查询

    def available_partitions(self):   # 不变(元数据接口本来就快)
    def partition_ranges(self):       # ★ 改为 SELECT * FROM dim_partitions(冷启动 35s→<10ms)
```

兼容性承诺:**响应 JSON 结构一字节不改**,`meta.cache_hit`、`meta.async_refresh` 等
标记语义保持,前端与既有冒烟脚本(`smoke_merged_path_card.py` 等)全部照常工作。

---

## 6. 一致性保障

1. **Parity 校验(asset)**:发布前抽样对比——对最新 pt 用在线 runner 算一份,
   与装配自存储层的结果比对 `summary.total_application_count`、`merged_alert_total`、
   各 level 计数、Top10 canonical_path 集合;不一致则**不发布**新快照并告警;
2. **config_hash 守卫**:启动/调度时若 `attribution_config.json` 哈希变化,
   自动重跑最近 7 天 pt 再发布;
3. **上游晚到**:sensor 每 30min 检测;`latest_partition` asset 内做行数下限校验
   (如 < 当日同时段均值 50% 则判为半成品,跳过并告警);
4. **幂等**:同 pt 重跑安全(新 run_id + 指针切换),DuckDB 历史批次自然累积。

---

## 7. 分期实施计划

### P1 — 存储层 + 秒读（核心收益）✅ 已完成 2026-08-24
- [x] `pipeline/store.py`：建表 + 幂等写入（批量 executemany，全量持久化 <1s）
- [x] `pipeline/assemble.py`：存储层 → 现有 API 同构 JSON（逐字段对齐）
- [x] `pipeline/exporter.py`：serving parquet 导出 + meta.json 指针
- [x] `pipeline/cli.py`：`run` / `ingest` / `status` 入口
- [x] app.py 接入读取优先级 + force 子进程联动 + 兑底写回（ingest 子进程）
- [x] 5 个历史分区回填（20260819–20260823）
- **验收结果**：dashboard 快照路径 354ms（冷，含 parquet 读取+deepcopy；热命中内存更快）；
  path-trend 65ms；partitions ranges 即时；summary 14 字段与在线基线逐字段一致；
  响应结构零变更。

### P2 — Dagster 调度(~1 天)
- [ ] definitions/assets/schedule(07:30 Asia/Shanghai)/new_partition_sensor/failure sensor
- [ ] `$DAGSTER_HOME` + 任务计划程序/NSSM 常驻部署
- [ ] force=true → cli 子进程联动
- **验收**:连续 2 天无人值守自动产出新 pt 快照;杀掉 daemon 后页面仍可用(fallback 生效)

### P3 — 质量与增强(~1 天,可选)
- [ ] parity 校验 asset 接入发布门禁
- [ ] config_hash 变更自动重跑近 7 天
- [ ] 失败 webhook 通知
- [ ] (增值)基于 attr_runs 历史批次的「预警路径演变」分析页素材

---

## 8. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| DuckDB 跨进程锁 | API/调度一方失败 | 架构上已规避:API 只碰 parquet,DuckDB 仅管线进程持有 |
| 上游分区延迟/数据迟到 | 发布了不完整结果 | 行数阈值校验 + 30min sensor 重探 + 支持当天重复发布 |
| 配置口径变更 | 新旧结果混用 | config_hash 记录 + 自动重跑 + serving 指针原子切换 |
| Dagster 宕机 | 当日无预计算 | API 三级降级(快照→DuckDB→在线兜底),页面永不白屏 |
| Windows 进程守护缺失 | 调度悄悄停摆 | 任务计划程序开机自启 + failure sensor + 每日心跳日志 |
| 磁盘增长 | parquet/duckdb 膨胀 | 单快照 ~1MB,日均增量极小;保留策略:runs 明细保留 90 天定期清理 |

---

## 9. 预期收益

| 指标 | 现状 | 目标 |
|---|---|---|
| dashboard 冷响应 | ~114s | < 1s(**>100x**) |
| path-trend 点击 | ~7s | < 100ms |
| partitions 冷启动 | ~35s | < 10ms |
| MaxCompute 日均作业数 | 每次访问最多 38 个 | 每天固定 ~40 个(1 次) |
| 历史归因留痕 | 无(缓存过期即失) | DuckDB 全量批次,可 SQL 分析 |
