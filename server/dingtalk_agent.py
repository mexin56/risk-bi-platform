"""Small, dependency-light DingTalk boundary for the read-only agent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Callable, Mapping


def _redact(value: Any) -> str:
    text = str(value or "")
    patterns = (
        (r"(?<!\d)1[3-9]\d{9}(?!\d)", "[REDACTED]"),
        (r"(?<!\d)\d{17}[0-9Xx](?!\d)", "[REDACTED]"),
        (r"(?i)(password|secret|token|api[_-]?key|device[_-]?id)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]"),
    )
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    return text


@dataclass(frozen=True)
class DingTalkEvent:
    message_id: str
    group_id: str
    user_id: str
    text: str
    mentioned_agent: bool
    reply_target: dict[str, str]

    @classmethod
    def from_payload(cls, payload: dict) -> "DingTalkEvent | None":
        if not isinstance(payload, dict):
            return None
        message_id = payload.get("messageId") or payload.get("msgId")
        group_id = payload.get("conversationId") or payload.get("openConversationId")
        user_id = payload.get("senderId") or payload.get("senderStaffId")
        if not all((message_id, group_id, user_id)):
            return None
        raw_text = payload.get("text", "")
        text = raw_text.get("content", "") if isinstance(raw_text, dict) else raw_text
        text = str(text or "")
        mentioned = bool(payload.get("mentioned_agent") or payload.get("isInAtList"))
        mentioned = mentioned or bool(re.search(r"@(授信归因助手|授权归因助手|助手)", text))
        cleaned = re.sub(r"@(?:授信归因助手|授权归因助手|助手)", " ", text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        webhook = payload.get("sessionWebhook") or payload.get("webhook_url")
        target = {"conversation_id": str(group_id)}
        if webhook:
            target["webhook_url"] = str(webhook)
        return cls(str(message_id), str(group_id), str(user_id), cleaned, mentioned, target)


class AgentAuditStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS agent_audit (
                message_id TEXT PRIMARY KEY, group_id TEXT, user_id TEXT,
                question TEXT, pt TEXT, paths_json TEXT, tools_json TEXT,
                status TEXT, elapsed_ms REAL, error_summary TEXT,
                created_at TEXT, finished_at TEXT
            )""")

    def seen(self, message_id: str) -> bool:
        with sqlite3.connect(self.path) as db:
            return db.execute("SELECT 1 FROM agent_audit WHERE message_id=?", (message_id,)).fetchone() is not None

    def record_start(self, message_id: str, group_id: str = "", user_id: str = "", question: str = "") -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.path) as db:
            cur = db.execute(
                "INSERT OR IGNORE INTO agent_audit(message_id,group_id,user_id,question,status,created_at) VALUES(?,?,?,?,?,?)",
                (str(message_id), str(group_id), str(user_id), _redact(question)[:500], "started", now),
            )
            return cur.rowcount == 1

    def record_finish(self, message_id: str, *, status: str, answer: Mapping[str, Any] | None = None,
                      elapsed_ms: float | None = None, error_summary: str = "") -> None:
        answer = answer or {}
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.path) as db:
            db.execute("""UPDATE agent_audit SET status=?, pt=?, paths_json=?, tools_json=?,
                elapsed_ms=?, error_summary=?, finished_at=? WHERE message_id=?""",
                (status, str(answer.get("pt", "")), json.dumps(
                    [item.get("path", item) if isinstance(item, Mapping) else item
                     for item in answer.get("evidence", [])], ensure_ascii=False),
                 json.dumps(answer.get("used_tools", []), ensure_ascii=False), elapsed_ms,
                 _redact(error_summary)[:500], now, str(message_id)))

    def fetch(self, message_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM agent_audit WHERE message_id=?", (message_id,)).fetchone()
            return dict(row) if row else None


class DingTalkSender:
    def __init__(self, post: Callable[..., Any] | None = None, timeout_seconds: int = 10):
        if post is None:
            import requests
            post = requests.post
        self.post = post
        self.timeout_seconds = timeout_seconds

    def send(self, reply_target: dict, markdown: str) -> dict:
        if not isinstance(reply_target, dict) or not reply_target.get("webhook_url") or not isinstance(markdown, str):
            return {"status": "failed", "error": "send_failed"}
        try:
            response = self.post(reply_target["webhook_url"], json={
                "msgtype": "markdown", "markdown": {"title": "授信归因助手", "text": markdown}
            }, timeout=self.timeout_seconds)
            response.raise_for_status()
            return {"status": "sent"}
        except Exception:
            return {"status": "failed", "error": "send_failed"}


def _answer_dict(answer: Any) -> dict[str, Any]:
    value = answer.to_dict() if hasattr(answer, "to_dict") else answer
    return dict(value) if isinstance(value, Mapping) else {"conclusion": str(value)}


def _markdown(answer: Mapping[str, Any]) -> str:
    labels = (("结论", "conclusion"), ("证据", "evidence"), ("事实", "facts"),
              ("推断", "inference"), ("下一步", "next_steps"), ("链接", "links"),
              ("PT", "pt"), ("窗口", "window"))
    return "\n\n".join(f"## {label}\n{answer.get(key, '')}" for label, key in labels)


class DingTalkAdapter:
    def __init__(self, config: Any, agent: Any, sender: Any, audit_store: AgentAuditStore):
        self.config, self.agent, self.sender, self.audit = config, agent, sender, audit_store

    def handle(self, payload: dict) -> dict:
        event = DingTalkEvent.from_payload(payload)
        if event is None:
            return {"status": "failed", "error": "invalid_event"}
        if self.audit.seen(event.message_id):
            return {"status": "duplicate"}
        groups = getattr(self.config, "allowed_group_ids", frozenset())
        users = getattr(self.config, "allowed_user_ids", frozenset())
        authorized = (getattr(self.config, "enabled", False) and event.mentioned_agent
                      and event.group_id in groups and event.user_id in users)
        if not self.audit.record_start(
            event.message_id, event.group_id, event.user_id, event.text if authorized else ""
        ):
            return {"status": "duplicate"}
        started = time.perf_counter()
        def finish(status: str, answer: Mapping[str, Any] | None = None, error: str = ""):
            self.audit.record_finish(event.message_id, status=status, answer=answer,
                                     elapsed_ms=(time.perf_counter() - started) * 1000, error_summary=error)
        if not getattr(self.config, "enabled", False):
            finish("ignored")
            return {"status": "ignored"}
        if not event.mentioned_agent:
            finish("ignored")
            return {"status": "ignored"}
        if event.group_id not in groups or event.user_id not in users:
            try:
                result = self.sender.send(event.reply_target, "## 授权提示\n当前会话未授权。")
                if isinstance(result, dict) and result.get("status") == "failed":
                    finish("failed", error=result.get("error", "send_failed"))
                    return {"status": "failed", "error": result.get("error", "send_failed")}
            except Exception as exc:
                finish("failed", error=str(exc))
                return {"status": "failed", "error": "send_failed"}
            finish("forbidden")
            return {"status": "forbidden"}
        try:
            answer = _answer_dict(self.agent.answer(event.text, {"group_id": event.group_id, "user_id": event.user_id}))
        except Exception as exc:
            finish("failed", error=str(exc))
            return {"status": "failed", "error": "processing_failed"}
        try:
            result = self.sender.send(event.reply_target, _markdown(answer))
            if isinstance(result, dict) and result.get("status") == "failed":
                finish("failed", answer, result.get("error", "send_failed"))
                return {"status": "failed", "error": result.get("error", "send_failed")}
        except Exception as exc:
            finish("failed", answer, str(exc))
            return {"status": "failed", "error": "send_failed"}
        finish("replied", answer)
        return {"status": "replied"}
