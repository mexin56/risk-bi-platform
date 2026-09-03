from attribution_agent import AgentAnswer, AgentConfig


def test_config_is_disabled_without_credentials(monkeypatch):
    monkeypatch.delenv("DINGTALK_AGENT_ENABLED", raising=False)
    config = AgentConfig.from_env()
    assert config.enabled is False


def test_answer_serializes_required_sections():
    answer = AgentAnswer(
        conclusion="当前风险以高等级规则为主",
        evidence=["pt=20260902, Level3=2"],
        facts=["Level3=2"],
        inference=["需要结合趋势复核"],
        next_steps=["继续观察下一个 pt"],
        links=[],
        used_tools=["dashboard_summary"],
        pt="20260902",
        window="当天",
    )
    payload = answer.to_dict()
    assert {
        "conclusion",
        "evidence",
        "facts",
        "inference",
        "next_steps",
        "pt",
        "window",
    } <= payload.keys()
