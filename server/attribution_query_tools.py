"""Fixed, read-only query tools for the credit-attribution assistant.

The adapter deliberately exposes only precomputed dashboard and path-trend data.
It does not accept query text and does not know how to mutate attribution state.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import math
import re
from numbers import Number
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SOURCE = "duckdb/serving"
ALLOWED_DAYS = frozenset({7, 15, 30, 60})
PT_PATTERN = re.compile(r"^\d{8}$")
RECORD_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")
STATUS_LABELS = {
    "0": 0,
    "不需要处理": 0,
    "1": 1,
    "已上策略": 1,
    "2": 2,
    "持续观察": 2,
}


def _json_safe(value: Any) -> Any:
    """Convert common analytical scalar/container values to JSON primitives."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        converted = float(value)
        return converted if math.isfinite(converted) else None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return _json_safe(item_method())
        except (TypeError, ValueError):
            pass
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        try:
            return str(isoformat())
        except (TypeError, ValueError):
            pass
    return str(value)


def _numeric(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def add_approval_rates(metrics: Mapping[str, Any]) -> dict[str, Any]:
    """Add consistently named person/item approval ratios to aggregated metrics."""
    result = dict(metrics)
    warnings = list(result.get("warnings") or [])

    def add_rate(
        output_name: str,
        numerator_names: tuple[str, ...],
        denominator_names: tuple[str, ...],
        denominator_label: str,
    ) -> None:
        numerator_key = next((name for name in numerator_names if name in result), None)
        denominator_key = next((name for name in denominator_names if name in result), None)

        def metric_value(key: str | None, names: tuple[str, ...]) -> float | None:
            if key is None or result.get(key) is None:
                warnings.append(f"{output_name}缺少指标 {key or names[0]}")
                return None
            value = _numeric(result[key])
            if value is None:
                warnings.append(f"{output_name}指标 {key} 非数字")
            return value

        numerator = metric_value(numerator_key, numerator_names)
        denominator = metric_value(denominator_key, denominator_names)
        if denominator == 0:
            result[output_name] = None
            warnings.append(f"{output_name}分母 {denominator_label} 为 0")
        elif numerator is not None and denominator is not None:
            result[output_name] = numerator / denominator
        else:
            result[output_name] = None

    add_rate(
        "通过率（人数）",
        ("approval_cid_cnt",),
        ("cid_cnt",),
        "cid_cnt",
    )
    add_rate(
        "通过率（件数）",
        ("approval_cnt", "approval_count"),
        ("cnt", "application_count"),
        "cnt",
    )
    result["warnings"] = list(dict.fromkeys(str(item) for item in warnings))
    return result


class AttributionQueryTools:
    """Seven fixed adapters over an injected read-only attribution service."""

    _TOOLS = (
        "compare_partitions",
        "dashboard_summary",
        "find_rules",
        "latest_partition",
        "path_trend",
        "rule_detail",
        "tracked_rule_followup",
    )

    def __init__(self, service: Any, page_base_url: str = "") -> None:
        self._service = service
        self._page_base_url = page_base_url.strip()

    def available_tools(self) -> list[str]:
        return list(self._TOOLS)

    @staticmethod
    def _envelope(
        *,
        pt: str | None = None,
        pt_range: dict[str, str] | None = None,
        data: Any = None,
        warnings: list[str] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        result = {
            "source": SOURCE,
            "pt": pt,
            "pt_range": pt_range,
            "data": _json_safe(data),
            "warnings": list(dict.fromkeys(warnings or [])),
        }
        if error:
            result["error"] = str(error)
        return result

    @staticmethod
    def _validated_pt(pt: str | None) -> tuple[str | None, str | None]:
        if pt is None:
            return None, None
        candidate = str(pt).strip()
        if not PT_PATTERN.fullmatch(candidate):
            return None, "pt 格式不合法，应为 8 位日期 YYYYMMDD"
        try:
            datetime.strptime(candidate, "%Y%m%d")
        except ValueError:
            return None, "pt 格式不合法，应为 8 位日期 YYYYMMDD"
        return candidate, None

    @staticmethod
    def _actual_pt(payload: Mapping[str, Any], fallback: str | None) -> str | None:
        meta = payload.get("meta")
        if isinstance(meta, Mapping):
            value = meta.get("partition") or meta.get("pt")
            if value:
                return str(value)
        value = payload.get("partition") or payload.get("pt")
        return str(value) if value else fallback

    def _read_dashboard(self, pt: str | None) -> tuple[dict[str, Any] | None, str | None, str | None]:
        validated, validation_error = self._validated_pt(pt)
        if validation_error:
            return None, None, validation_error
        try:
            payload = self._service.dashboard(
                partition=validated,
                force=False,
                offset=0,
            )
        except Exception as exc:
            return None, validated, str(exc)
        if not isinstance(payload, Mapping):
            return None, validated, "预计算归因快照格式不合法"
        copied = dict(payload)
        return copied, self._actual_pt(copied, validated), None

    def _resolve_latest_pt(self) -> tuple[str | None, str | None]:
        latest_method = getattr(self._service, "latest_partition", None)
        try:
            if callable(latest_method):
                value = latest_method()
                if isinstance(value, Mapping):
                    value = value.get("partition") or value.get("pt")
                candidate = str(value).strip() if value else ""
            else:
                payload = self._service.dashboard(partition=None, force=False, offset=0)
                candidate = self._actual_pt(payload, None) or ""
        except Exception as exc:
            return None, str(exc)
        validated, validation_error = self._validated_pt(candidate or None)
        if candidate == "":
            return None, "未找到可用的预计算 pt"
        return validated, validation_error

    def _resolve_pt(self, pt: str | None) -> tuple[str | None, str | None]:
        if pt is not None:
            return self._validated_pt(pt)
        return self._resolve_latest_pt()

    def _page_url(self, pt: str) -> str:
        if not self._page_base_url:
            return ""
        parts = urlsplit(self._page_base_url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["pt"] = pt
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    def latest_partition(self) -> dict[str, Any]:
        pt, error = self._resolve_latest_pt()
        if error:
            return self._envelope(data=None, warnings=[error], error=error)
        return self._envelope(pt=pt, data={"latest_partition": pt})

    def dashboard_summary(self, pt: str | None = None) -> dict[str, Any]:
        resolved, error = self._resolve_pt(pt)
        if error:
            return self._envelope(data=None, warnings=[error], error=error)
        dashboard, actual_pt, error = self._read_dashboard(resolved)
        if error:
            return self._envelope(pt=actual_pt, data=None, warnings=[error], error=error)
        summary = dashboard.get("summary", {})
        if not isinstance(summary, Mapping):
            message = "预计算归因快照缺少 summary"
            return self._envelope(pt=actual_pt, data=None, warnings=[message], error=message)
        data = add_approval_rates(summary)
        warnings = list(data.pop("warnings", []))
        page_url = self._page_url(actual_pt or resolved or "")
        if page_url:
            data["page_url"] = page_url
        return self._envelope(pt=actual_pt, data=data, warnings=warnings)

    @staticmethod
    def _rule_matches(rule: Mapping[str, Any], value: str) -> bool:
        needle = value.strip().casefold()
        if not needle:
            return False
        candidates = (
            rule.get("id"),
            rule.get("record_id"),
            rule.get("canonical_path"),
            rule.get("path"),
        )
        return any(str(candidate).casefold() == needle for candidate in candidates if candidate is not None)

    @staticmethod
    def _status_matches(value: Any, requested: str) -> bool:
        needle = requested.strip()
        if not needle:
            return True
        expected = STATUS_LABELS.get(needle)
        if expected is None:
            try:
                expected = int(needle)
            except ValueError:
                return str(value).casefold() == needle.casefold()
        try:
            return int(value) == expected
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _level_matches(rule: Mapping[str, Any], requested: str) -> bool:
        needle = requested.strip().casefold()
        if not needle:
            return True
        level = rule.get("level")
        candidates = {str(rule.get("level_label", "")).casefold()}
        if level is not None:
            candidates.update({str(level).casefold(), f"level{level}".casefold()})
        return needle in candidates

    def find_rules(
        self,
        pt: str | None = None,
        keyword: str = "",
        level: str = "",
        status: str = "",
    ) -> dict[str, Any]:
        resolved, error = self._resolve_pt(pt)
        if error:
            return self._envelope(data=None, warnings=[error], error=error)
        dashboard, actual_pt, error = self._read_dashboard(resolved)
        if error:
            return self._envelope(pt=actual_pt, data=None, warnings=[error], error=error)
        alerts = dashboard.get("merged_alerts", [])
        if not isinstance(alerts, list):
            message = "预计算归因快照缺少 merged_alerts"
            return self._envelope(pt=actual_pt, data=None, warnings=[message], error=message)

        needle = keyword.strip().casefold()
        matches = []
        for rule in alerts:
            if not isinstance(rule, Mapping):
                continue
            searchable = " ".join(
                str(rule.get(name, ""))
                for name in ("id", "record_id", "canonical_path", "path", "level_label")
            ).casefold()
            if needle and needle not in searchable:
                continue
            if not self._level_matches(rule, str(level)):
                continue
            if not self._status_matches(rule.get("status", 0), str(status)):
                continue
            matches.append(dict(rule))
        return self._envelope(pt=actual_pt, data=matches)

    def rule_detail(self, pt: str | None, record_id_or_path: str) -> dict[str, Any]:
        requested = str(record_id_or_path or "").strip()
        resolved, error = self._resolve_pt(pt)
        if error:
            return self._envelope(data=None, warnings=[error], error=error)
        if not requested:
            message = "规则标识不能为空"
            return self._envelope(pt=resolved, data=None, warnings=[message], error=message)
        dashboard, actual_pt, error = self._read_dashboard(resolved)
        if error:
            return self._envelope(pt=actual_pt, data=None, warnings=[error], error=error)
        alerts = dashboard.get("merged_alerts", [])
        match = next(
            (
                dict(rule)
                for rule in alerts
                if isinstance(rule, Mapping) and self._rule_matches(rule, requested)
            ),
            None,
        )
        if match is None:
            message = "未找到匹配规则"
            warning = f"pt={actual_pt} 未找到匹配规则：{requested}"
            return self._envelope(
                pt=actual_pt,
                data=None,
                warnings=[warning],
                error=message,
            )
        return self._envelope(pt=actual_pt, data=match)

    @staticmethod
    def _normalized_days(days: int) -> tuple[int | None, str | None]:
        try:
            normalized = int(days)
        except (TypeError, ValueError, OverflowError):
            return None, "days 只允许 7、15、30、60"
        if normalized not in ALLOWED_DAYS:
            return None, "days 只允许 7、15、30、60"
        return normalized, None

    def path_trend(
        self,
        pt: str | None,
        record_id: str,
        days: int = 60,
    ) -> dict[str, Any]:
        normalized_days, days_error = self._normalized_days(days)
        if days_error:
            validated_pt, _ = self._validated_pt(pt)
            return self._envelope(
                pt=validated_pt,
                data=None,
                warnings=[days_error],
                error=days_error,
            )
        resolved, error = self._resolve_pt(pt)
        if error:
            return self._envelope(data=None, warnings=[error], error=error)
        record_id = str(record_id or "").strip()
        if not RECORD_ID_PATTERN.fullmatch(record_id):
            message = "record_id 格式不合法，应为 12 位十六进制"
            return self._envelope(pt=resolved, data=None, warnings=[message], error=message)
        warnings: list[str] = []
        try:
            payload = self._service.path_trend(
                record_id=record_id,
                partition=resolved,
                offset=0,
            )
        except Exception as exc:
            message = str(exc)
            return self._envelope(
                pt=resolved,
                data=None,
                warnings=[*warnings, message],
                error=message,
            )
        if not isinstance(payload, Mapping):
            message = "预计算趋势数据格式不合法"
            return self._envelope(pt=resolved, data=None, warnings=[*warnings, message], error=message)

        data = dict(payload)
        actual_pt = self._actual_pt(data, resolved)
        if isinstance(data.get("days"), list):
            data["days"] = data["days"][-normalized_days:]
        daily = data.get("daily")
        if isinstance(daily, list):
            enriched_daily = []
            for row in daily[-normalized_days:]:
                if isinstance(row, Mapping):
                    enriched = add_approval_rates(row)
                    for warning in enriched.get("warnings", []):
                        if warning not in warnings:
                            warnings.append(warning)
                    enriched_daily.append(enriched)
                else:
                    enriched_daily.append(row)
            data["daily"] = enriched_daily
        return self._envelope(pt=actual_pt, data=data, warnings=warnings)

    def tracked_rule_followup(
        self,
        path: str,
        start_pt: str,
        end_pt: str | None = None,
    ) -> dict[str, Any]:
        requested_path = str(path or "").strip()
        start, error = self._validated_pt(start_pt)
        if error:
            return self._envelope(data=None, warnings=[error], error=error)
        if not requested_path:
            message = "规则路径不能为空"
            return self._envelope(data=None, warnings=[message], error=message)
        if end_pt is None:
            end, error = self._resolve_latest_pt()
        else:
            end, error = self._validated_pt(end_pt)
        if error:
            return self._envelope(data=None, warnings=[error], error=error)
        pt_range = {"start": start, "end": end}
        start_date = datetime.strptime(start, "%Y%m%d").date()
        end_date = datetime.strptime(end, "%Y%m%d").date()
        if start_date > end_date:
            message = "start_pt 不能晚于 end_pt"
            return self._envelope(pt_range=pt_range, data=None, warnings=[message], error=message)

        rows: list[dict[str, Any]] = []
        warnings: list[str] = []
        current = start_date
        while current <= end_date:
            current_pt = current.strftime("%Y%m%d")
            dashboard, actual_pt, dashboard_error = self._read_dashboard(current_pt)
            if dashboard_error:
                rows.append(
                    {"pt": current_pt, "matched": False, "available": False}
                )
                warnings.append(f"pt={current_pt}: {dashboard_error}")
            else:
                alerts = dashboard.get("merged_alerts", [])
                match = next(
                    (
                        dict(rule)
                        for rule in alerts
                        if isinstance(rule, Mapping)
                        and self._rule_matches(rule, requested_path)
                    ),
                    None,
                )
                if match is None:
                    rows.append({"pt": actual_pt or current_pt, "matched": False})
                    warnings.append(f"pt={actual_pt or current_pt} 未找到规则：{requested_path}")
                else:
                    match["pt"] = actual_pt or current_pt
                    match["matched"] = True
                    rows.append(match)
            current += timedelta(days=1)
        return self._envelope(pt_range=pt_range, data=rows, warnings=warnings)

    def compare_partitions(self, pt_a: str, pt_b: str) -> dict[str, Any]:
        first, first_error = self._validated_pt(pt_a)
        second, second_error = self._validated_pt(pt_b)
        validation_error = first_error or second_error
        if validation_error:
            return self._envelope(data=None, warnings=[validation_error], error=validation_error)
        pt_range = {"start": first, "end": second}
        first_result = self.dashboard_summary(first)
        second_result = self.dashboard_summary(second)
        warnings = [*first_result["warnings"], *second_result["warnings"]]
        if first_result.get("error") or second_result.get("error"):
            message = first_result.get("error") or second_result.get("error")
            return self._envelope(
                pt_range=pt_range,
                data=None,
                warnings=warnings,
                error=message,
            )

        first_data = dict(first_result["data"])
        second_data = dict(second_result["data"])
        delta: dict[str, float] = {}
        for key in first_data.keys() & second_data.keys():
            first_value = first_data[key]
            second_value = second_data[key]
            if (
                isinstance(first_value, Number)
                and not isinstance(first_value, bool)
                and isinstance(second_value, Number)
                and not isinstance(second_value, bool)
            ):
                delta[key] = round(float(second_value) - float(first_value), 12)
        data = {"pt_a": first_data, "pt_b": second_data, "delta": delta}
        return self._envelope(pt_range=pt_range, data=data, warnings=warnings)
