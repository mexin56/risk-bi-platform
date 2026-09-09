# Risk BI Monitor

风控 BI 监控项目，包含：

- **提额策略执行分析**：按《提额系数》逐行统计提额/未提额客户、额度变化、T0/下一笔发起及 FPD 指标，并测算整体户均额度目标达成。
- **归因监控**：授信归因与资金归结统一在同一页面，通过 tab 切换；点击预警路径可加载对应路径趋势。
- 其他风控监控页面：生命周期、渠道质量、反欺诈、Vintage、模型分与模型稳定性。

## 开发启动

```powershell
# 前端（默认对局域网开放 3000 端口）
npm install
npm run dev -- --host 0.0.0.0 --port 3000

# 授信归因 API（另开一个终端）
cd server
python -m pip install -r requirements.txt
python app.py
```

前端通过 Vite 的 `/api` 代理访问本机 `127.0.0.1:8010` 的归因 API；API 和 MaxCompute 凭证不直接暴露给浏览器。

## 授信归因预计算管线（P1 已上线）

归因结果每日预计算后存入 DuckDB（`server/data/attribution.duckdb`，仅管线进程写），
并导出 serving 快照（`server/data/serving/*.parquet`，API 只读层）。接口读取优先级：
内存缓存 → 磁盘缓存 → serving 快照 → MaxCompute 在线兑底（兑底结果自动异步发布）。

```powershell
# 在 server/ 目录下：
python -m pipeline.cli run                        # 计算并发布最新分区
python -m pipeline.cli run --pt 20260823          # 指定分区
python -m pipeline.cli run --backfill 5           # 回填最近 5 个分区
python -m pipeline.cli status                     # 查看运行批次与快照
```

- dashboard 冷响应 ~114s → <0.5s；path-trend 点击 ~7s → <100ms。
- `force=true` 语义：立即返回旧数据 + 后台子进程重算并重新发布（`meta.async_refresh=true`）。
- 设计与验收详见 `design/attribution-precompute-duckdb-dagster-plan.md`（P2 将接入 Dagster 调度）。

## 资金归结监控（贷前 · 中介团伙异常订单归因 v1.2）

资金归结已与授信归因统一到「归因监控」页面，通过顶层 tab 切换；资金计算、结果存储与授信独立，页面骨架沿用授信归因模块：观察区间/分区工具条、规则状态 tab、飞书表格、选中路径趋势和运行口径卡片。

- **数据源**：MaxCompute 明细表 `pb_biz_credit.lj_cap_flow_analysis_base`（pt 分区，businessid 每行唯一，
  `payee_last1_cnt_cate` 0/1 异常标记），按 `create_date` + 9 个归因维度在 MaxCompute 侧聚合，
  只把结果切片传回进程内（与 `warehouse.py` 同款 per-field GROUP BY + Top-K 候选条件聚合批量精确序列）。
- **方案 v1.2 口径**：近 1/3/7 天为观察期，观察期以外**全部历史日期**为该窗口基准期（不截断）；
  双序列（异常订单数 + 总订单数）；核心指标 = 异常订单量增长倍数 / 异常率提升倍数 / 两样本比例 z-score；
  Level1 黄（≥5/×1.5/×1.5/z≥2）、Level2 橙（≥10/×2/×2/z≥3）、Level3 红（≥20/×3/×3/z≥5）；
  基准异常=0 走「新增异常」口径，基准总订单=0 标记「无基准，人工复核」。
- **Top-K**：单维全量 → 内部 Top10 → 二级 → 内部 Top5 → 三级终止；候选门槛：任一窗口观察异常订单 ≥5。
- **专家规则**：强制单维（当前：loan_cust_lifecycle_stage in (-1, 新客当月, 新客次月)）/ 双维 / 三维，
  绕过剪枝但不改变指标与阈值；合并去重后双链标记「Top-K + 专家规则」。
- **服务语义与授信归因一致**（`fund_service.py` 镜像 `app.AttributionService`）：
  分区发现 / 观察区间回看（offset）/ 内存+磁盘缓存（`server/data/fund_attribution_cache/`）/
  force=true 立即返回旧数据 + 后台异步重算（前端 15s 轮询）/ 路径趋势（记录内嵌每日序列）/ 规则状态标记
  （`server/data/fund_attribution_status.sqlite3`，与授信归因同一套 AttributionStatusStore）。
- **预计算存储**：`server/fund_pipeline/cli.py` 将结果写入独立 `server/data/fund_attribution.duckdb`，并发布到只读
  `server/data/fund_serving/*.parquet`；API 优先读取资金 serving 快照，缺失时再走缓存/在线计算。
  ```powershell
  cd server
  python -m fund_pipeline.cli run --pt 20260903
  python -m fund_pipeline.cli status
  ```
- **API**：`/api/fund-attribution/{health,partitions,dashboard,path-trend,rule-status,rule-status-history}`，
  权限 key：`fundMonitor`。
- **前端**：`src/pages/AttributionMonitor.tsx` 统一承载 tab；资金实现为 `src/pages/FundAttribution.tsx`，
  `src/pages/FundMonitor.tsx` 仅保留旧入口兼容导出。
- **配置**：`server/config/fund_monitor_config.json`（表名、维度、阈值、Top-K、专家规则可配，
  可用 `FUND_MONITOR_TABLE` 环境变量覆盖表名）。
- **测试与核验**：`server/test_fund_attribution.py`（离线验证完整编排与 v1.2 口径）+
  `server/test_fund_service_api.py`（API 缓存/路径趋势/规则状态/鉴权）+
  `server/test_fund_pipeline.py`（独立 DuckDB/serving 发布）+
  `server/verify_fund_sample.py`（对比 Excel 的窗口总览、日趋势、专家强制路径和正式预警状态）。
  ```powershell
  python server/verify_fund_sample.py --result result.json --expected "中介团伙异常订单归因_20260905样本_v1.2_全历史基准期运行结果.xlsx"
  ```
- **实测**：pt=20260903（450 万订单 / 60 天 / 4,629 异常）首次全量计算约 228s，之后缓存秒开。

## 登录与权限管理

- 首次启动自动创建 SQLite 库（`server/data/rcbi.db`，已 Git 忽略）并初始化角色与演示账号：
  - 管理员 `admin / admin123`（全部页面权限）
  - 分析师 `analyst / analyst123`（除权限管理外全部）
  - 访客 `viewer / viewer123`（只读子集）
- 管理员登录后在「权限管理」页维护用户、角色与页面权限；角色权限修改即时生效（后端接口层同样强制校验）。
- 初始密码可用环境变量覆盖：`AUTH_ADMIN_PASSWORD` / `AUTH_ANALYST_PASSWORD` / `AUTH_VIEWER_PASSWORD`；会话有效期 `AUTH_TOKEN_TTL_SECONDS`（默认 12 小时）。
- 登录接口 `POST /api/auth/login`；除登录外所有 `/api` 接口均需 `Authorization: Bearer <token>`。

## 授信归因配置

复制 `server/.env.example` 为 `server/.env.local`，再在本机填写配置。`server/.env.local` 已被 Git 忽略，**不得提交 AK/SK、Token 或连接 notebook**。

## 提额策略分析重跑

```powershell
python build_strategy_execution_excel.py
python build_strategy_execution_html_report.py
```

最终交付物：

- `risk_analysis/提额策略执行分析_20260812_v2.xlsx`
- `public/reports/credit-strategy-execution-20260812.html`
- `risk_analysis/提额策略分析方法与代码归档_20260812.md`

提额策略的完整口径、字段映射、SQL、代码入口及结果解释见上述归档文档。

## 安全约束

- ODPS/MaxCompute 凭证仅允许服务端本机读取。
- 不导出客户标识、密钥或原始凭证到前端、HTML 报告或 Git 仓库。
- Git 提交前请确认 `.env.local`、日志、Python 缓存和 Office 临时锁文件未被暂存。
