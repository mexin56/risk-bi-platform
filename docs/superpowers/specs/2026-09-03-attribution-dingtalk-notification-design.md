# 授信归因钉钉日报通知设计

## 目标

每天 10:30（Asia/Shanghai）读取最新已发布的授信归因 serving 快照，生成授信归因页面完整长截图和预警摘要，并通过钉钉自定义机器人发送到群里。上游 pt 延迟时使用当前最新已发布 pt，不重新触发 MaxCompute 计算。

## 方案

在现有 Dagster 中增加独立的 10:30 通知 job。通知 job 不依赖 09:50 计算 job 的同一进程状态，而是从 serving 快照读取最新可用 dashboard payload，保证服务重启或上游延迟时仍能发送最近一次有效结果。

通知流程分成四个小单元：

1. `DingTalkNotifier`：从环境变量读取 Webhook URL 和加签 Secret，生成 DingTalk Markdown 请求并发送；Secret 不进入源码、配置样例或日志。
2. `AttributionDigestBuilder`：从 dashboard payload 生成摘要，包括 pt、Level 1/2/3 规则数、预警总数、当天申请/通过率，以及当前仍命中的已上策略/持续观察规则。跟踪状态规则若当天未命中仍列出，并标记“本日未命中，仍在持续跟踪”。
3. `AttributionScreenshotter`：使用 Playwright 打开配置的授信归因页面，使用配置的服务账号登录，等待页面加载到目标 pt 后截取完整页面，保存到 `server/data/notification_reports/`。
4. 报告文件只读接口：API 以随机文件名校验和路径约束提供 PNG，供内网钉钉 Markdown 图片 URL 和点击链接使用；不允许目录遍历，不需要登录才能读取报告文件。

Markdown 消息同时包含摘要、截图嵌入、截图链接和授信归因页面链接。钉钉只能通过可访问 URL 获取图片，因此当钉钉服务端无法访问内网图片地址时，消息仍保留可由同事浏览器打开的截图链接，并在日志中记录 URL。

## 配置

新增本地环境变量：

```text
DINGTALK_WEBHOOK_URL=
DINGTALK_SECRET=
ATTRIBUTION_PUBLIC_BASE_URL=http://<内网地址>:<API端口>
ATTRIBUTION_WEB_URL=http://<内网地址>:<前端端口>/?page=attribution
ATTRIBUTION_NOTIFY_USERNAME=
ATTRIBUTION_NOTIFY_PASSWORD=
```

`ATTRIBUTION_PUBLIC_BASE_URL` 用于拼接报告图片和下载链接；`ATTRIBUTION_WEB_URL` 用于 Playwright 截图以及消息中的页面链接。未配置钉钉 Webhook 时，10:30 job 明确记录为 dry-run 并生成截图，不发送请求。

## 调度与幂等

新增 `daily_attribution_dingtalk_1030` job 和 `daily_attribution_dingtalk_1030` schedule，cron 为 `30 10 * * *`，时区为 `Asia/Shanghai`。报告文件名包含 pt 和日期；同一 pt 的通知在本地发送记录中只发送一次，手工 dry-run 不写入已发送状态。通知失败只影响通知 job，不影响归因计算和页面服务。

## 摘要口径

- Level 1/2/3 数量直接取 dashboard `summary.level1_count`、`level2_count`、`level3_count`。
- 当前仍命中：规则状态为 1/2，且出现在 `merged_alerts` 且 `is_tracked_only` 不为真；显示规则路径、当前等级、命中窗口和跟踪起始 pt。
- 当前未命中但持续跟踪：规则状态为 1/2，出现在 `merged_alerts` 且 `is_tracked_only` 为真；显示规则路径、状态和跟踪起始 pt。
- 不把历史已退出状态规则加入当前日报，只在已有打标记录页面复盘。

## 测试与验收

- 单元测试验证加签 URL、摘要等级计数、持续命中/未命中文案、PNG 路径安全和同 pt 幂等。
- Dagster 定义测试验证 10:30 Asia/Shanghai schedule 已注册。
- dry-run 生成一张完整长截图，使用本地图片预览确认页面内容、pt 和中文摘要后，才执行一次真实 Webhook 测试。
- 真实发送只使用环境变量中的临时/已轮换钉钉凭据，测试响应必须为 `errcode=0`；失败时保留截图和错误日志。
