"""Contracts and configuration for the DingTalk attribution assistant."""

from dataclasses import dataclass
import os
from typing import Any


@dataclass(frozen=True)
class AgentConfig:
    enabled: bool = False
    app_key: str = ""
    app_secret: str = ""
    allowed_group_ids: frozenset[str] = frozenset()
    allowed_user_ids: frozenset[str] = frozenset()
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout_seconds: int = 30

    @classmethod
    def from_env(cls) -> "AgentConfig":
        def split(name: str) -> frozenset[str]:
            return frozenset(
                value.strip()
                for value in os.getenv(name, "").split(",")
                if value.strip()
            )

        return cls(
            enabled=os.getenv("DINGTALK_AGENT_ENABLED", "false").lower() == "true",
            app_key=os.getenv("DINGTALK_AGENT_APP_KEY", ""),
            app_secret=os.getenv("DINGTALK_AGENT_APP_SECRET", ""),
            allowed_group_ids=split("DINGTALK_AGENT_ALLOWED_GROUP_IDS"),
            allowed_user_ids=split("DINGTALK_AGENT_ALLOWED_USER_IDS"),
            base_url=os.getenv("AI_AGENT_BASE_URL", ""),
            api_key=os.getenv("AI_AGENT_API_KEY", ""),
            model=os.getenv("AI_AGENT_MODEL", ""),
            timeout_seconds=max(1, int(os.getenv("AI_AGENT_TIMEOUT_SECONDS", "30"))),
        )


@dataclass(frozen=True)
class AgentAnswer:
    conclusion: str
    evidence: list[Any]
    facts: list[Any]
    inference: list[Any]
    next_steps: list[Any]
    links: list[Any]
    used_tools: list[str]
    pt: str
    window: str

    def to_dict(self) -> dict[str, Any]:
        """Return the public answer envelope, excluding internal model payloads."""
        return {
            "conclusion": self.conclusion,
            "evidence": self.evidence,
            "facts": self.facts,
            "inference": self.inference,
            "next_steps": self.next_steps,
            "links": self.links,
            "used_tools": self.used_tools,
            "pt": self.pt,
            "window": self.window,
        }


class AttributionAgent:
    """Public agent facade; orchestration is added in the following task."""

    def __init__(self, config: AgentConfig | None = None):
        self.config = config or AgentConfig.from_env()

    def answer(self, question: str, context: dict[str, str]) -> AgentAnswer:
        raise NotImplementedError("agent orchestration is implemented in a later task")
