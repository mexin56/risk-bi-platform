import json

import pytest

from attribution_agent import (
    AgentAnswer,
    AgentConfig,
    AttributionAgent,
    IntentParser,
    OpenAICompatibleClient,
)


class FakeTools:
    """Only the seven read-only Task 2 methods, with call recording."""

    def __init__(self):
        self.calls = []

    @staticmethod
    def _result(pt="20260902", data=None, error=None):
        return {
            "source": "duckdb/serving",
            "pt": pt,
            "pt_range": None,
            "data": data,
            "warnings": [error] if error else [],
            "error": error,
        }

    def latest_partition(self):
        self.calls.append(("latest_partition", {}))
        return self._result(data={"latest_partition": "20260902"})

    def dashboard_summary(self, pt=None):
        self.calls.append(("dashboard_summary", {"pt": pt}))
        return self._result(
            pt=pt,
            data={
                "level1_count": 4,
                "level2_count": 2,
                "level3_count": 1,
                "通过率（人数）": 0.2,
                "page_url": f"http://monitor.example/credit?pt={pt}",
            },
        )

    def find_rules(self, pt=None, keyword="", level="", status=""):
        self.calls.append(
            (
                "find_rules",
                {"pt": pt, "keyword": keyword, "level": level, "status": status},
            )
        )
        return self._result(
            pt=pt,
            data=[
                {
                    "id": "aaaaaaaaaaaa",
                    "canonical_path": "channel=organic",
                    "level": 3,
                }
            ],
        )

    def rule_detail(self, pt, record_id_or_path):
        self.calls.append(
            ("rule_detail", {"pt": pt, "record_id_or_path": record_id_or_path})
        )
        return self._result(
            pt=pt,
            data={"id": record_id_or_path, "level": 3, "z_score": 2.1},
        )

    def path_trend(self, pt, record_id, days=60):
        self.calls.append(
            ("path_trend", {"pt": pt, "record_id": record_id, "days": days})
        )
        if days not in {7, 15, 30, 60}:
            return self._result(pt=pt, error="days 只允许 7、15、30、60")
        return self._result(
            pt=pt,
            data={"record_id": record_id, "days": days, "daily": [{"count": 3}]},
        )

    def tracked_rule_followup(self, path, start_pt, end_pt=None):
        self.calls.append(
            (
                "tracked_rule_followup",
                {"path": path, "start_pt": start_pt, "end_pt": end_pt},
            )
        )
        result = self._result(
            pt=end_pt or "20260902", data=[{"pt": start_pt, "matched": True}]
        )
        result["pt_range"] = {"start": start_pt, "end": end_pt or "20260902"}
        return result

    def compare_partitions(self, pt_a, pt_b):
        self.calls.append(
            ("compare_partitions", {"pt_a": pt_a, "pt_b": pt_b})
        )
        result = self._result(
            pt=pt_b,
            data={"pt_a": {"level3_count": 1}, "pt_b": {"level3_count": 2}},
        )
        result["pt_range"] = {"start": pt_a, "end": pt_b}
        return result


class RecordingClient:
    def __init__(self, content="基于已查询的数据，当前有 1 条 Level3 规则。"):
        self.content = content
        self.messages = None

    def complete(self, messages):
        self.messages = messages
        return self.content


def test_config_is_disabled_without_credentials(monkeypatch):
    monkeypatch.delenv("DINGTALK_AGENT_ENABLED", raising=False)
    config = AgentConfig.from_env()
    assert config.enabled is False


def test_config_from_env_normalizes_flags_allowlists_timeout_and_mappings(monkeypatch):
    monkeypatch.setenv("DINGTALK_AGENT_ENABLED", "TrUe")
    monkeypatch.setenv("DINGTALK_AGENT_APP_KEY", "ding-app")
    monkeypatch.setenv("DINGTALK_AGENT_APP_SECRET", "ding-secret")
    monkeypatch.setenv("DINGTALK_AGENT_ALLOWED_GROUP_IDS", " group-a,group-b, group-a, ")
    monkeypatch.setenv("DINGTALK_AGENT_ALLOWED_USER_IDS", " user-a, user-b,user-a ")
    monkeypatch.setenv("AI_AGENT_BASE_URL", "https://ai.example.test/v1")
    monkeypatch.setenv("AI_AGENT_API_KEY", "ai-key")
    monkeypatch.setenv("AI_AGENT_MODEL", "model-a")
    monkeypatch.setenv("AI_AGENT_TIMEOUT_SECONDS", "0")

    config = AgentConfig.from_env()

    assert config.enabled is True
    assert config.app_key == "ding-app"
    assert config.app_secret == "ding-secret"
    assert config.allowed_group_ids == frozenset({"group-a", "group-b"})
    assert config.allowed_user_ids == frozenset({"user-a", "user-b"})
    assert config.base_url == "https://ai.example.test/v1"
    assert config.api_key == "ai-key"
    assert config.model == "model-a"
    assert config.timeout_seconds == 1


def test_answer_serializes_exact_public_fields_and_values():
    answer = AgentAnswer(
        conclusion="当前风险以高等级规则为主",
        evidence=["pt=20260902, Level3=2"],
        facts=["Level3=2"],
        inference=["需要结合趋势复核"],
        next_steps=["继续观察下一个 pt"],
        links=["http://host/report"],
        used_tools=["dashboard_summary"],
        pt="20260902",
        window="当天",
    )

    payload = answer.to_dict()
    assert set(payload) == {
        "conclusion",
        "evidence",
        "facts",
        "inference",
        "next_steps",
        "links",
        "used_tools",
        "pt",
        "window",
    }
    assert payload == {
        "conclusion": "当前风险以高等级规则为主",
        "evidence": ["pt=20260902, Level3=2"],
        "facts": ["Level3=2"],
        "inference": ["需要结合趋势复核"],
        "next_steps": ["继续观察下一个 pt"],
        "links": ["http://host/report"],
        "used_tools": ["dashboard_summary"],
        "pt": "20260902",
        "window": "当天",
    }


def test_parser_extracts_latest_level_question():
    parsed = IntentParser().parse("看最新pt各等级规则有多少")
    assert parsed == {
        "intent": "dashboard_summary",
        "pt": None,
        "level": "",
        "keyword": "",
        "record_id": "",
        "days": 60,
        "pt_a": None,
        "pt_b": None,
        "status": "",
    }


def test_parser_extracts_trend_days_and_rule():
    parsed = IntentParser().parse("20260902 规则 abc 看近60天趋势")
    assert parsed["intent"] == "path_trend"
    assert parsed["pt"] == "20260902"
    assert parsed["record_id"] == "abc"
    assert parsed["days"] == 60


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("最新分区是什么", "latest_partition"),
        ("20260902 查找 Level3 持续观察规则", "find_rules"),
        ("20260902 规则 aaaaaaaaaaaa 为什么命中", "rule_detail"),
        ("规则 aaaaaaaaaaaa 从 20260901 开始持续跟踪", "tracked_rule_followup"),
        ("对比 20260901 和 20260902", "compare_partitions"),
    ],
)
def test_parser_supports_remaining_whitelisted_intents(question, intent):
    assert IntentParser().parse(question)["intent"] == intent


def test_parser_extracts_level_status_keyword_and_comparison_partitions():
    rule_query = IntentParser().parse("20260902 查找 Level2 已上策略 渠道规则")
    comparison = IntentParser().parse("比较 20260901 与 20260902")

    assert rule_query["level"] == "Level2"
    assert rule_query["status"] == "已上策略"
    assert rule_query["keyword"] == "渠道"
    assert comparison["pt_a"] == "20260901"
    assert comparison["pt_b"] == "20260902"


def test_missing_pt_resolves_latest_before_dashboard_summary():
    tools = FakeTools()
    answer = AttributionAgent(tools, AgentConfig(), client=None).answer(
        "看最新pt各等级规则有多少", {"group_id": "g", "user_id": "u"}
    )

    assert [name for name, _ in tools.calls] == [
        "latest_partition",
        "dashboard_summary",
    ]
    assert answer.used_tools == ["latest_partition", "dashboard_summary"]
    assert answer.pt == "20260902"
    assert answer.evidence


def test_missing_rule_id_finds_rule_before_loading_trend():
    tools = FakeTools()
    answer = AttributionAgent(tools, AgentConfig()).answer(
        "20260902 看近15天趋势", {}
    )

    assert [name for name, _ in tools.calls] == ["find_rules", "path_trend"]
    assert tools.calls[-1][1] == {
        "pt": "20260902",
        "record_id": "aaaaaaaaaaaa",
        "days": 15,
    }
    assert answer.window == "近15天"


def test_unsupported_days_reaches_only_fixed_path_trend_tool():
    tools = FakeTools()
    answer = AttributionAgent(tools, AgentConfig()).answer(
        "20260902 规则 aaaaaaaaaaaa 看近90天趋势", {}
    )

    assert tools.calls == [
        (
            "path_trend",
            {"pt": "20260902", "record_id": "aaaaaaaaaaaa", "days": 90},
        )
    ]
    assert answer.evidence[0]["result"]["error"] == "days 只允许 7、15、30、60"


def test_arbitrary_sql_never_enters_tool_arguments():
    tools = FakeTools()
    AttributionAgent(tools, AgentConfig()).answer(
        "select * from secret_table; drop table audit", {}
    )

    arguments = json.dumps(tools.calls, ensure_ascii=False).lower()
    assert "select" not in arguments
    assert "drop table" not in arguments
    assert {name for name, _ in tools.calls} <= {
        "latest_partition",
        "dashboard_summary",
        "find_rules",
        "rule_detail",
        "path_trend",
        "tracked_rule_followup",
        "compare_partitions",
    }


def test_model_input_excludes_secrets_database_credentials_and_sql():
    tools = FakeTools()
    client = RecordingClient()
    config = AgentConfig(
        app_secret="DING-SECRET-VALUE",
        api_key="AI-SECRET-VALUE",
        base_url="https://ai.example.test/v1",
        model="model-a",
    )
    AttributionAgent(tools, config, client=client).answer(
        "看最新等级", {
            "current_time": "2026-09-03T10:30:00+08:00",
            "database_password": "DB-SECRET-VALUE",
            "sql": "select password from credentials",
        }
    )

    prompt = json.dumps(client.messages, ensure_ascii=False)
    assert "DING-SECRET-VALUE" not in prompt
    assert "AI-SECRET-VALUE" not in prompt
    assert "DB-SECRET-VALUE" not in prompt
    assert "select password" not in prompt.lower()
    assert "2026-09-03T10:30:00+08:00" in prompt


def test_model_input_redacts_sql_embedded_in_user_question():
    tools = FakeTools()
    client = RecordingClient()
    AttributionAgent(tools, AgentConfig(), client=client).answer(
        "看最新等级；select password from credentials; drop table audit", {}
    )

    prompt = json.dumps(client.messages, ensure_ascii=False).lower()
    assert "select password" not in prompt
    assert "drop table" not in prompt
    assert "看最新等级" in prompt


def test_model_failure_returns_data_answer_without_inventing_conclusion():
    class BrokenClient:
        def complete(self, messages):
            raise TimeoutError("timeout containing secret")

    agent = AttributionAgent(FakeTools(), AgentConfig(), client=BrokenClient())
    answer = agent.answer("看最新等级", {"group_id": "g", "user_id": "u"})

    assert "AI 总结暂不可用" in answer.conclusion
    assert "secret" not in answer.conclusion
    assert answer.evidence
    assert answer.evidence[0]["result"]["source"] == "duckdb/serving"


def test_model_numbers_not_present_in_tool_results_are_rejected():
    client = RecordingClient("当前有 999 条高风险规则。")
    answer = AttributionAgent(FakeTools(), AgentConfig(), client=client).answer(
        "看最新等级", {}
    )

    assert "999" not in answer.conclusion
    assert "AI 总结暂不可用" in answer.conclusion


def test_why_answer_separates_facts_inference_unknowns_and_next_steps():
    answer = AttributionAgent(FakeTools(), AgentConfig()).answer(
        "20260902 规则 aaaaaaaaaaaa 为什么命中", {}
    )

    assert answer.facts
    assert any("可能原因" in str(item) for item in answer.inference)
    assert any("当前无法确认" in str(item) for item in answer.inference)
    assert answer.next_steps


def test_openai_compatible_client_posts_expected_request(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "安全总结"}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("attribution_agent.requests.post", fake_post)
    config = AgentConfig(
        base_url="https://ai.example.test/v1/",
        api_key="ai-key",
        model="model-a",
        timeout_seconds=12,
    )
    content = OpenAICompatibleClient(config).complete(
        [{"role": "user", "content": "问题"}]
    )

    assert content == "安全总结"
    assert captured["url"] == "https://ai.example.test/v1/chat/completions"
    assert captured["json"] == {
        "model": "model-a",
        "messages": [{"role": "user", "content": "问题"}],
        "temperature": 0,
    }
    assert captured["headers"] == {
        "Authorization": "Bearer ai-key",
        "Content-Type": "application/json",
    }
    assert captured["timeout"] == 12


@pytest.mark.parametrize(
    "config",
    [
        AgentConfig(api_key="k", model="m"),
        AgentConfig(base_url="https://ai.example", model="m"),
        AgentConfig(base_url="https://ai.example", api_key="k"),
    ],
)
def test_openai_client_rejects_incomplete_configuration_without_http(config, monkeypatch):
    called = False

    def fake_post(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("attribution_agent.requests.post", fake_post)

    with pytest.raises(RuntimeError, match="AI client is not configured"):
        OpenAICompatibleClient(config).complete([])
    assert called is False


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{"message": {"content": ""}}]},
    ],
)
def test_openai_client_raises_catchable_error_for_invalid_json_shape(payload, monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    monkeypatch.setattr(
        "attribution_agent.requests.post", lambda *args, **kwargs: FakeResponse()
    )
    config = AgentConfig(base_url="https://ai.example", api_key="k", model="m")

    with pytest.raises(RuntimeError):
        OpenAICompatibleClient(config).complete([])
