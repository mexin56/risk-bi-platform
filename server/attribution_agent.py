"""Safe, read-only orchestration for the DingTalk attribution assistant."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import re
from typing import Any

import requests


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


class IntentParser:
    """Deterministically map a question to one of seven read-only tools."""

    _PT_RE = re.compile(r"(?<!\d)(20\d{6})(?!\d)")
    _DAYS_RE = re.compile(r"近\s*(\d+)\s*天")
    _RULE_RE = re.compile(r"规则\s*([A-Za-z0-9_-]{2,})", re.IGNORECASE)

    def parse(self, question: str) -> dict[str, Any]:
        text = (question or "").strip()
        pts = self._PT_RE.findall(text)
        days_match = self._DAYS_RE.search(text)
        rule_match = self._RULE_RE.search(text)
        level_match = re.search(r"level\s*([123])", text, re.IGNORECASE)
        status = next(
            (value for value in ("不需要处理", "已上策略", "持续观察") if value in text),
            "",
        )

        if any(word in text for word in ("对比", "比较")) and len(pts) >= 2:
            intent = "compare_partitions"
        elif "持续跟踪" in text or "后续跟踪" in text:
            intent = "tracked_rule_followup"
        elif "趋势" in text:
            intent = "path_trend"
        elif "为什么" in text or "详情" in text:
            intent = "rule_detail"
        elif any(word in text for word in ("查找", "搜索", "哪些规则")):
            intent = "find_rules"
        elif "最新分区" in text:
            intent = "latest_partition"
        else:
            intent = "dashboard_summary"

        keyword = ""
        if intent == "find_rules":
            cleaned = self._PT_RE.sub(" ", text)
            cleaned = re.sub(r"level\s*[123]", " ", cleaned, flags=re.IGNORECASE)
            for token in ("查找", "搜索", "规则", "哪些", status):
                cleaned = cleaned.replace(token, " ")
            keyword = " ".join(cleaned.split())

        return {
            "intent": intent,
            "pt": pts[0] if pts else None,
            "level": f"Level{level_match.group(1)}" if level_match else "",
            "keyword": keyword,
            "record_id": rule_match.group(1) if rule_match else "",
            "days": int(days_match.group(1)) if days_match else 60,
            "pt_a": pts[0] if len(pts) >= 2 else None,
            "pt_b": pts[1] if len(pts) >= 2 else None,
            "status": status,
        }


class OpenAICompatibleClient:
    """Small OpenAI-compatible chat-completions client."""

    def __init__(self, config: AgentConfig):
        self.config = config

    def complete(self, messages: list[dict[str, str]]) -> str:
        if not all((self.config.base_url, self.config.api_key, self.config.model)):
            raise RuntimeError("AI client is not configured")
        endpoint = self.config.base_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        response = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.config.model,
                "messages": messages,
                "temperature": 0,
            },
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("AI response has an invalid format") from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("AI response content is empty")
        return content.strip()


class AttributionAgent:
    """Parse questions and orchestrate only the seven fixed read-only tools."""

    _SQL_RE = re.compile(
        r"(?is)\b(?:select|insert|update|delete|drop|alter|create|truncate|merge|grant|revoke)\b"
        r".*?(?=[；;\r\n]|$)"
    )

    def __init__(
        self,
        query_tools: Any,
        config: AgentConfig | None = None,
        client: Any | None = None,
    ):
        self.query_tools = query_tools
        self.config = config or AgentConfig.from_env()
        self.client = client
        self.parser = IntentParser()

    @staticmethod
    def _latest_pt(result: dict[str, Any]) -> str:
        data = result.get("data") or {}
        if isinstance(data, dict):
            return str(data.get("latest_partition") or result.get("pt") or "")
        return str(result.get("pt") or "")

    @staticmethod
    def _first_rule(result: dict[str, Any]) -> dict[str, Any]:
        data = result.get("data") or []
        return data[0] if isinstance(data, list) and data else {}

    @staticmethod
    def _links(results: list[dict[str, Any]]) -> list[Any]:
        links: list[Any] = []

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in {"url", "page_url", "report_url"} and isinstance(child, str):
                        links.append(child)
                    else:
                        visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(results)
        return list(dict.fromkeys(links))

    @staticmethod
    def _safe_model_conclusion(content: str, results: list[dict[str, Any]]) -> str | None:
        allowed_text = json.dumps(results, ensure_ascii=False, default=str)
        allowed_numbers = set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", allowed_text))
        output_numbers = set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", content))
        return content if output_numbers <= allowed_numbers else None

    def _resolve_pt(
        self,
        parsed: dict[str, Any],
        results: list[dict[str, Any]],
        used_tools: list[str],
    ) -> str:
        if parsed["pt"]:
            return parsed["pt"]
        latest = self.query_tools.latest_partition()
        results.append({"tool": "latest_partition", "result": latest})
        used_tools.append("latest_partition")
        return self._latest_pt(latest)

    def _call_tools(self, parsed: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], str]:
        intent = parsed["intent"]
        results: list[dict[str, Any]] = []
        used: list[str] = []

        def add(name: str, result: dict[str, Any]) -> dict[str, Any]:
            results.append({"tool": name, "result": result})
            used.append(name)
            return result

        if intent == "latest_partition":
            result = add("latest_partition", self.query_tools.latest_partition())
            return results, used, self._latest_pt(result)

        if intent == "compare_partitions":
            pt_a, pt_b = parsed["pt_a"], parsed["pt_b"]
            if not pt_a or not pt_b:
                pt_b = self._resolve_pt(parsed, results, used)
                pt_a = pt_a or pt_b
            add("compare_partitions", self.query_tools.compare_partitions(pt_a, pt_b))
            return results, used, pt_b or ""

        pt = self._resolve_pt(parsed, results, used)
        if intent == "dashboard_summary":
            add("dashboard_summary", self.query_tools.dashboard_summary(pt=pt))
        elif intent == "find_rules":
            add(
                "find_rules",
                self.query_tools.find_rules(
                    pt=pt,
                    keyword=parsed["keyword"],
                    level=parsed["level"],
                    status=parsed["status"],
                ),
            )
        elif intent in {"rule_detail", "path_trend"}:
            record_id = parsed["record_id"]
            if not record_id:
                found = add(
                    "find_rules",
                    self.query_tools.find_rules(pt=pt, keyword="", level="", status=""),
                )
                record_id = str(self._first_rule(found).get("id") or "")
            if intent == "rule_detail":
                add("rule_detail", self.query_tools.rule_detail(pt, record_id))
            else:
                add("path_trend", self.query_tools.path_trend(pt, record_id, parsed["days"]))
        elif intent == "tracked_rule_followup":
            path = parsed["record_id"]
            if not path:
                found = add(
                    "find_rules",
                    self.query_tools.find_rules(pt=pt, keyword="", level="", status=parsed["status"]),
                )
                rule = self._first_rule(found)
                path = str(rule.get("canonical_path") or rule.get("id") or "")
            add(
                "tracked_rule_followup",
                self.query_tools.tracked_rule_followup(path=path, start_pt=pt, end_pt=None),
            )
        return results, used, pt

    def _messages(
        self,
        question: str,
        current_time: str,
        results: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        safe_question = re.sub(r"(?s)/\*.*?\*/", "[已移除不安全内容]", question)
        safe_question = re.sub(r"(?m)--.*$", "[已移除不安全内容]", safe_question)
        safe_question = self._SQL_RE.sub("[已移除不安全内容]", safe_question)
        for secret in (self.config.app_secret, self.config.api_key):
            if secret:
                safe_question = safe_question.replace(secret, "[已移除敏感信息]")
        safe_payload = {
            "question": safe_question,
            "current_time": current_time,
            "rules": [
                "只根据白名单工具结果回答",
                "不得补充工具结果中不存在的数字",
                "推断必须明确标记，不能写成事实",
            ],
            "tool_results": results,
        }
        return [
            {"role": "system", "content": "你是授信归因只读分析助手。"},
            {"role": "user", "content": json.dumps(safe_payload, ensure_ascii=False, default=str)},
        ]

    def answer(self, question: str, context: dict[str, str]) -> AgentAnswer:
        parsed = self.parser.parse(question)
        results, used_tools, pt = self._call_tools(parsed)
        data_items = [item["result"].get("data") for item in results if item["result"].get("data") is not None]
        facts: list[Any] = [{"observed": item} for item in data_items]
        inference: list[Any] = []
        next_steps: list[Any] = ["结合下一分区数据继续复核。"]
        if "为什么" in (question or ""):
            inference = [
                "可能原因及证据：当前只能依据已查询的规则指标判断。",
                "当前无法确认：工具结果未覆盖上游业务事件和策略变更。",
            ]
            next_steps = ["检查对应路径的近 60 天趋势及上游业务变更。"]

        conclusion = "AI 总结暂不可用；已返回结构化查询结果。"
        if self.client is not None:
            current_time = context.get("current_time") or datetime.now(timezone.utc).isoformat()
            try:
                candidate = self.client.complete(self._messages(question, current_time, results))
                safe_candidate = self._safe_model_conclusion(candidate, results)
                if safe_candidate:
                    conclusion = safe_candidate
            except Exception:
                pass

        window = f"近{parsed['days']}天" if parsed["intent"] == "path_trend" else "当天"
        if parsed["intent"] in {"compare_partitions", "tracked_rule_followup"}:
            window = "分区范围"
        return AgentAnswer(
            conclusion=conclusion,
            evidence=results,
            facts=facts,
            inference=inference,
            next_steps=next_steps,
            links=self._links(results),
            used_tools=used_tools,
            pt=pt,
            window=window,
        )
