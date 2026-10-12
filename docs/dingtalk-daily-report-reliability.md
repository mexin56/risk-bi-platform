# 钉钉日报可靠性保障（授信归因 / 资金归集）

## 背景：10/02~10/07 连续 6 天日报没发

| 时间 | 发生了什么 |
|---|---|
| 10-01 16:06 | 手工起的 `dagster-daemon` 进程消失，**没有 systemd 托管，也不在巡检脚本里**，无人拉起 |
| 10-02 ~ 10-07 | 14:00 计算与 14:20 日报全部没有触发；失败传感器只写 ERROR 日志，没人收到任何提醒 |
| 10-08 11:48~14:38 | 人工回补了 20261001~20261006 的计算快照，**但没有回补通知** |
| 10-08 18:52 | 才安装 `risk-bi-dagster.service`（`Restart=always`） |

根因三条，与编排器无关：**① 进程无托管 ② 失败无告警 ③ 无补发**。

## 现在有三层防护

### 1. 进程托管 + 探针（`service-healthcheck.sh` 每 2 分钟）

```
risk-bi-dagster|active://risk-bi-dagster                     # 进程死了自动 restart
risk-bi-dagster-webserver|http://127.0.0.1:3001/server_info # 假死时自动 restart
```

`risk-bi-dagster-webserver.service`（127.0.0.1:3001）同时提供 Dagster UI，用来查历史 run、手动补跑失败的日报 job。

### 2. 发送自愈（`server/pipeline/dagster_defs.py::plan_notification`）

日报不再硬性要求"pt == 昨天"：

1. 有昨天分区 → 发昨天（正常路径）；
2. 没有昨天分区 → 先查上游分区是否存在：
   - 上游**有**（只是 14:00 还在算/晚到）→ `RetryRequested` 等 3×20min；
   - 上游**没有**（真缺分区）→ 发"最新且未发送"的昨天及更早快照，正文顶部加
     `> ⚠️ 补发：最新可用数据分区为 xxx，日报应覆盖 yyy`；
3. 落后期望分区超过 `ATTRIBUTION_NOTIFY_MAX_STALE_DAYS`（默认 3 天）→ 不发，交给巡检告警；
4. 停机多天留下的 backlog，一次最多补 `ATTRIBUTION_NOTIFY_CATCHUP_MAX`（**默认 1，即默认不回放历史**，
   调大到 3 才会一次性补发）条，带
   `> ⚠️ 补发历史分区：xxx 此前未发送` 标注；
5. pt 晚于昨天的快照（当天半天数据）**永不参与**，避免把不完整数据当日报。

发送台账新增 `expected_pt` 列（老库自动 `ALTER TABLE` 升级），记录"这条消息是为哪一天发的"，
所以巡检能区分"真没发"和"已发过补发消息"。

### 3. 缺口巡检告警（每天 15:00）

`risk-bi-notify-watchdog.service/.timer` → `server/scripts/notify_watchdog.py`：
查两张台账，期望分区（昨天）没被任何消息覆盖就直接往群里发"归因日报缺失告警"。
`Persistent=true`，机器 15:00 停机也会开机补跑。

```bash
python server/scripts/notify_watchdog.py --check-only   # 只检查：0 正常 / 2 有缺口
journalctl -u risk-bi-notify-watchdog.service -n 50     # 看上次巡检结果
```

## 补发与运维命令

```bash
# 上游补出某个分区后，计算 + 补发一条龙（台账按 pt 去重，重复执行不会重发）
python server/scripts/backfill_notify.py --pt 20261007
python server/scripts/backfill_notify.py --pt 20261007 --skip-compute   # 只补发不重算
python server/scripts/backfill_notify.py --pt 20261007 --fund-only      # 只补资金归集

# 手动触发一次日报（会用真实钉钉通道发送）
cd server && ../.venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from pipeline.dagster_defs import _send_credit_daily, _send_fund_daily
class L:
    def info(self, m, *a): print(m % a if a else m)
    warning = info
    def exception(self, m, *a, **k): print('ERR', m % a if a else m)
print(_send_credit_daily(log=L()))
print(_send_fund_daily(log=L()))
"

# 排查
systemctl status risk-bi-dagster risk-bi-dagster-webserver risk-bi-notify-watchdog.timer
journalctl -u risk-bi-dagster -n 200 | grep -E "日报发送成功|RetryRequested|重试"
python -c "import sqlite3;print(sqlite3.connect('server/data/attribution_dingtalk_notifications.sqlite3').execute('select pt,status,sent_at,expected_pt from attribution_dingtalk_notification order by pt desc limit 5').fetchall())"
```

## 相关配置（server/.env.local，可加到 .env.example 对照）

| 变量 | 默认 | 说明 |
|---|---|---|
| `ATTRIBUTION_NOTIFY_CATCHUP_MAX` | 1 | 一次最多补发几条历史日报（默认只发当天，不回放 backlog） |
| `ATTRIBUTION_NOTIFY_MAX_STALE_DAYS` | 3 | 落后期望分区超过多少天就不再补发 |
| `NOTIFY_WATCHDOG_LAG_DAYS` | 0 | 巡检期望分区相对昨天的偏移（上游 T+2 产数时设 1） |

## 已知遗留

- 上游 `pt='20261007'` 分区缺失（`lj_sx_cnt_analysis_summary` / `lj_cap_flow_analysis_base` 都没有），
  要等数仓补数后跑上面的 `backfill_notify.py --pt 20261007`。
- `nightly_attribution_failure_sensor` 目前仍只记 ERROR 日志；巡检层已经能兜住"日报没发"，
  但计算任务本身失败仍需看 Dagster UI。
- daemon 的 grpc code location 每分钟心跳超时重启（`No heartbeat received in 20 seconds`），
  目前不影响调度（每次 run 自行加载代码），但值得后续调大 `heartbeat-timeout`。