import json
import sqlite3
from types import SimpleNamespace

import pytest

from attribution_agent import AgentAnswer
from dingtalk_agent import AgentAuditStore, DingTalkAdapter, DingTalkEvent, DingTalkSender


class FakeAgent:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def answer(self, question, context):
        self.calls.append((question, context))
        if self.error:
            raise self.error
        return AgentAnswer(
            conclusion="当前结论",
            evidence=[{"path": "channel=organic", "count": 2}],
            facts=["Level3=2"],
            inference=["可能需要复核"],
            next_steps=["观察下一分区"],
            links=["https://monitor.example/report"],
            used_tools=["dashboard_summary"],
            pt="20260902",
            window="当天",
        )


class FakeSender:
    def __init__(self, result=None, error=None):
        self.messages = []
        self.result = result or {"status": "sent"}
        self.error = error

    def send(self, reply_target, markdown):
        self.messages.append((reply_target, markdown))
        if self.error:
            raise self.error
        return self.result


def config(**overrides):
    values = {
        "enabled": True,
        "allowed_group_ids": frozenset({"g1"}),
        "allowed_user_ids": frozenset({"u1"}),
        "app_secret": "DING-SECRET-VALUE",
        "api_key": "AI-SECRET-VALUE",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_adapter(tmp_path, **kwargs):
    store = AgentAuditStore(tmp_path / "audit.sqlite3")
    agent = kwargs.get("agent", FakeAgent())
    sender = kwargs.get("sender", FakeSender())
    adapter = DingTalkAdapter(kwargs.get("config", config()), agent, sender, store)
    return adapter, agent, sender, store


@pytest.mark.parametrize(
    "payload",
    [
        {
            "messageId": "m1",
            "conversationId": "g1",
            "senderId": "u1",
            "text": "@授信归因助手  最新风险",
            "sessionWebhook": "https://oapi.example/reply",
        },
        {
            "msgId": "m1",
            "openConversationId": "g1",
            "senderStaffId": "u1",
            "text": {"content": "最新风险"},
            "isInAtList": True,
            "sessionWebhook": "https://oapi.example/reply",
            "database_password": "must-not-cross-boundary",
        },
    ],
)
def test_event_normalizes_compatible_fields_and_safe_reply_target(payload):
    event = DingTalkEvent.from_payload(payload)
    assert event is not None
    assert (event.message_id, event.group_id, event.user_id) == ("m1", "g1", "u1")
    assert event.text == "最新风险"
    assert event.mentioned_agent is True
    assert event.reply_target == {
        "conversation_id": "g1",
        "webhook_url": "https://oapi.example/reply",
    }


@pytest.mark.parametrize("missing", ["messageId", "conversationId", "senderId"])
def test_event_rejects_missing_required_identity(missing):
    payload = {
        "messageId": "m1",
        "conversationId": "g1",
        "senderId": "u1",
        "text": "@助手 风险",
    }
    payload.pop(missing)
    assert DingTalkEvent.from_payload(payload) is None


def test_non_mention_is_ignored_before_agent(tmp_path):
    adapter, agent, sender, store = make_adapter(tmp_path)
    result = adapter.handle(
        {"messageId": "m2", "conversationId": "g1", "senderId": "u1", "text": "普通消息"}
    )
    assert result == {"status": "ignored"}
    assert agent.calls == []
    assert sender.messages == []
    assert store.fetch("m2")["status"] == "ignored"


@pytest.mark.parametrize(
    ("overrides", "payload"),
    [
        ({"allowed_group_ids": frozenset()}, {"conversationId": "g1", "senderId": "u1"}),
        ({"allowed_user_ids": frozenset()}, {"conversationId": "g1", "senderId": "u1"}),
        ({}, {"conversationId": "g1-extra", "senderId": "u1"}),
        ({}, {"conversationId": "g1", "senderId": "u1-extra"}),
    ],
)
def test_empty_or_non_exact_allowlists_are_forbidden_without_business_data(
    tmp_path, overrides, payload
):
    adapter, agent, sender, store = make_adapter(tmp_path, config=config(**overrides))
    payload.update({"messageId": "m3", "text": "@助手 最新 Level3 风险"})
    result = adapter.handle(payload)
    assert result == {"status": "forbidden"}
    assert agent.calls == []
    assert len(sender.messages) == 1
    assert "Level3" not in sender.messages[0][1]
    assert store.fetch("m3")["question"] == ""


def test_disabled_adapter_is_quiet_and_does_not_call_dependencies(tmp_path):
    adapter, agent, sender, store = make_adapter(tmp_path, config=config(enabled=False))
    result = adapter.handle(
        {"messageId": "m4", "conversationId": "g1", "senderId": "u1", "text": "@助手 风险"}
    )
    assert result == {"status": "ignored"}
    assert agent.calls == []
    assert sender.messages == []
    assert store.fetch("m4")["status"] == "ignored"


def test_success_cleans_mention_injects_safe_context_and_sends_public_markdown(tmp_path):
    adapter, agent, sender, store = make_adapter(tmp_path)
    result = adapter.handle(
        {"messageId": "m5", "conversationId": "g1", "senderId": "u1", "text": " @助手   最新风险 "}
    )
    assert result == {"status": "replied"}
    assert agent.calls == [("最新风险", {"group_id": "g1", "user_id": "u1"})]
    markdown = sender.messages[0][1]
    for heading in ("结论", "证据", "事实", "推断", "下一步", "链接", "PT", "窗口"):
        assert heading in markdown
    assert "raw_model_response" not in markdown
    row = store.fetch("m5")
    assert row["status"] == "replied"
    assert row["pt"] == "20260902"
    assert json.loads(row["paths_json"]) == ["channel=organic"]
    assert json.loads(row["tools_json"]) == ["dashboard_summary"]


def test_sqlite_primary_key_deduplicates_before_agent_and_reply(tmp_path):
    adapter, agent, sender, store = make_adapter(tmp_path)
    payload = {"messageId": "m6", "conversationId": "g1", "senderId": "u1", "text": "@助手 最新pt"}
    assert adapter.handle(payload) == {"status": "replied"}
    assert adapter.handle(payload) == {"status": "duplicate"}
    assert len(agent.calls) == 1
    assert len(sender.messages) == 1
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT count(*) FROM agent_audit WHERE message_id='m6'").fetchone()[0] == 1


@pytest.mark.parametrize(
    ("agent_error", "sender"),
    [
        (RuntimeError("password=DB-SECRET 13812345678"), FakeSender()),
        (None, FakeSender(error=RuntimeError("token=SEND-SECRET 11010519491231002X"))),
        (None, FakeSender(result={"status": "failed", "error": "remote_rejected"})),
    ],
)
def test_processing_and_sender_failures_are_structured_and_sanitized(
    tmp_path, agent_error, sender
):
    agent = FakeAgent(error=agent_error)
    adapter, _, _, store = make_adapter(tmp_path, agent=agent, sender=sender)
    result = adapter.handle(
        {"messageId": "m7", "conversationId": "g1", "senderId": "u1", "text": "@助手 风险"}
    )
    assert result["status"] == "failed"
    assert result["error"] in {"processing_failed", "send_failed", "remote_rejected"}
    row = store.fetch("m7")
    assert row["status"] == "failed"
    assert "SECRET" not in (row["error_summary"] or "")
    assert "13812345678" not in (row["error_summary"] or "")
    assert "11010519491231002X" not in (row["error_summary"] or "")


def test_audit_schema_and_question_redaction_are_bounded(tmp_path):
    store = AgentAuditStore(tmp_path / "audit.sqlite3")
    question = (
        "手机号 13812345678 身份证 11010519491231002X "
        "device_id=DEVICE-ABC-123 secret=TOP-SECRET password=DB-PASS "
        + "问" * 600
    )
    assert store.record_start("m8", "g1", "u1", question) is True
    store.record_finish("m8", status="failed", error_summary="token=RAW-TOKEN")
    row = store.fetch("m8")
    assert len(row["question"]) <= 500
    serialized = json.dumps(row, ensure_ascii=False)
    for sensitive in (
        "13812345678",
        "11010519491231002X",
        "DEVICE-ABC-123",
        "TOP-SECRET",
        "DB-PASS",
        "RAW-TOKEN",
    ):
        assert sensitive not in serialized
    with sqlite3.connect(store.path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(agent_audit)")}
    assert columns == {
        "message_id", "group_id", "user_id", "question", "pt", "paths_json",
        "tools_json", "status", "elapsed_ms", "error_summary", "created_at", "finished_at",
    }


def test_sender_posts_only_normalized_markdown_and_returns_structured_failures():
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"errcode": 0, "errmsg": "ok", "secret": "never-return"}

    def post(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return Response()

    sender = DingTalkSender(post=post, timeout_seconds=3)
    result = sender.send(
        {"conversation_id": "g1", "webhook_url": "https://oapi.example/reply"},
        "## 安全响应",
    )
    assert result == {"status": "sent"}
    assert captured == {
        "url": "https://oapi.example/reply",
        "json": {"msgtype": "markdown", "markdown": {"title": "授信归因助手", "text": "## 安全响应"}},
        "timeout": 3,
    }
    assert DingTalkSender(post=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret=x"))).send(
        {"conversation_id": "g1", "webhook_url": "https://oapi.example/reply"}, "ok"
    ) == {"status": "failed", "error": "send_failed"}

