# Risk BI Monitor

风控 BI 监控项目，包含：

- **提额策略执行分析**：按《提额系数》逐行统计提额/未提额客户、额度变化、T0/下一笔发起及 FPD 指标，并测算整体户均额度目标达成。
- **授信归因监控**：MaxCompute 聚合数据上的 Top-K 自动归因与专家规则归因；点击预警路径可加载该路径近 15 天趋势。
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
