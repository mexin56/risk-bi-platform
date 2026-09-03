import pytest

from attribution_agent import AgentAnswer, AgentConfig, AttributionAgent


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


def test_agent_answer_public_contract_is_explicitly_unimplemented():
    agent = AttributionAgent(AgentConfig())

    with pytest.raises(NotImplementedError, match="later task"):
        agent.answer("查询最新风险", {"pt": "20260902"})
