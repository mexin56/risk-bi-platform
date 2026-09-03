# Task 4 实现报告

## 完成内容

- 新增 `server/dingtalk_agent.py`：事件字段兼容与 @助手 清理、启用开关、群/用户精确白名单、SQLite 主键去重、最小审计字段、注入式 Agent/Sender、Markdown HTTP 边界。
- `AgentAuditStore` 对问题、错误摘要执行长度限制与敏感信息脱敏，不保存凭证、原始模型响应或数据库信息。
- `DingTalkSender` 仅接收规范化 reply target、Markdown 和注入的 HTTP callable；网络行为在测试中使用 fake callable。
- `server/test_dingtalk_agent.py` 覆盖字段兼容、过滤、白名单、异常、去重、审计脱敏和发送边界。

## 验证

```text
python -m pytest server/test_dingtalk_agent.py -q
18 passed in 0.55s

python -m py_compile server/dingtalk_agent.py server/test_dingtalk_agent.py
exit 0
```

## 提交

提交信息：`feat: add dingtalk agent adapter and audit`

## 审查修复（C1/I1/I2/I3）

- `DingTalkSender` 仅允许 HTTPS、标准端口和精确钉钉域名，拒绝 userinfo/任意 host；校验 HTTP JSON `errcode == 0`。
- Adapter 对 Sender 的非 dict、非 `sent` 返回统一按发送失败处理。
- mention 仅接受结构化 `atUsers`/`at_user_list` 中匹配配置机器人标识，或明确 verified mention；正文 @ 和伪造布尔字段仅用于清理/不再触发。
- 审计 finish 对 pt、evidence/path、used_tools、error_summary 递归脱敏并限制长度；新增敏感 answer 回归测试。
- 测试已更新为受信钉钉 URL，并覆盖 SSRF、errcode、伪造 mention、审计 answer 脱敏。

## 修复后验证

```text
python -m pytest server/test_dingtalk_agent.py -q
29 passed in 0.39s

python -m py_compile server/dingtalk_agent.py server/test_dingtalk_agent.py
exit 0
```
