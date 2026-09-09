"""贷前资金归结监控（中介团伙异常订单归因 v1.2）API · 与授信归因同款模板。

- 数据源：MaxCompute 聚合表 `pb_biz_credit.lj_cap_flow_analysis_base`（pt 分区，
  businessid 每行唯一，`payee_last1_cnt_cate` 0/1 异常标记），按 create_date +
  9 个归因维度在 MaxCompute 侧聚合，只把结果切片传回进程内。
- 语义与授信归因 app.AttributionService 一致：分区发现 / 观察区间回看(offset) /
  内存+磁盘缓存 / force=true 异步重算（立即返回旧数据）/ 路径趋势 / 规则状态标记。
- 计算口径为方案 v1.2（全历史基准期），见 fund_attribution.py。
"""

from __future__ import annotations

import copy
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

try:
    from odps import ODPS  # type: ignore
except ImportError:  # pragma: no cover
    ODPS = None  # type: ignore

from attribution_status import AttributionStatusStore
from auth import require_perm
from fund_attribution import FundAttributionError, FundAttributionRunner
from fund_pipeline import SERVING_DIR as FUND_SERVING_DIR
from fund_pipeline import assemble as fund_assemble

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "fund_monitor_config.json"
STATUS_DB_PATH = ROOT / "data" / "fund_attribution_status.sqlite3"
DISK_CACHE_DIR = ROOT / "data" / "fund_attribution_cache"
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$")
SAFE_PARTITION = re.compile(r"^[A-Za-z0-9_-]+$")
SAFE_RECORD_ID = re.compile(r"^[0-9a-f]{12}$")


class FundAttributionServiceError(RuntimeError):
    """配置/数据源故障，可安全暴露给 UI。"""


def load_fund_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def get_connection() -> Any:
    """复用授信归因的 MaxCompute 连接配置（env 或 notebook 静态读取）。"""
    from app import get_connection as _get_connection

    return _get_connection()


def _run_sql_rows(sql: str) -> list[dict[str, Any]]:
    """与 app.AttributionService._run_sql_rows 相同的 Record 读取方式。"""
    if ODPS is None:
        raise FundAttributionServiceError("未安装 pyodps。请执行 python -m pip install -r server/requirements.txt。")
    connection = get_connection()
    odps = ODPS(
        connection.access_key_id,
        connection.access_key_secret,
        project=connection.project,
        endpoint=connection.endpoint,
    )
    instance = odps.execute_sql(sql)
    rows: list[dict[str, Any]] = []
    with instance.open_reader(tunnel=True, limit=False) as reader:
        columns = [column.name for column in reader.schema.columns]
        for record in reader:
            row: dict[str, Any] = {}
            for index, name in enumerate(columns):
                try:
                    row[name] = record[name]
                except Exception:  # noqa: BLE001
                    row[name] = record[index]
            rows.append(row)
    return rows


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if hasattr(value, "item") and callable(value.item):
        try:
            return value.item()
        except Exception:  # noqa: BLE001
            pass
    return value


class FundAttributionService:
    """与授信归因 AttributionService 同款缓存/回退语义。"""

    def __init__(self) -> None:
        self.config = load_fund_config()
        self._status_store = AttributionStatusStore(STATUS_DB_PATH)
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._path_trend_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._partition_cache: tuple[float, list[str]] | None = None
        self._partition_range_cache: tuple[float, dict[str, dict[str, str]]] | None = None
        self._lock = threading.Lock()

    # ---------- 分区 ----------
    @property
    def table_name(self) -> str:
        table = os.getenv("FUND_MONITOR_TABLE", self.config["table"]).strip()
        if not SAFE_IDENTIFIER.fullmatch(table):
            raise FundAttributionServiceError("FUND_MONITOR_TABLE 格式不合法。")
        return table

    def _odps(self) -> Any:
        if ODPS is None:
            raise FundAttributionServiceError("未安装 pyodps。请执行 python -m pip install -r server/requirements.txt。")
        connection = get_connection()
        return ODPS(
            connection.access_key_id,
            connection.access_key_secret,
            project=connection.project,
            endpoint=connection.endpoint,
        )

    def available_partitions(self, *, prefer_serving: bool = True) -> list[str]:
        cached = self._partition_cache
        if cached and time.time() - cached[0] < CACHE_SECONDS:
            return list(cached[1])
        if prefer_serving:
            published_ranges = fund_assemble.read_partition_ranges(FUND_SERVING_DIR)
            if published_ranges:
                result = sorted(published_ranges, reverse=True)
                self._partition_cache = (time.time(), result)
                return list(result)
        odps = self._odps()
        table = odps.get_table(self.table_name.split(".")[-1])
        partitions: list[str] = []
        for partition in table.partitions:
            match = re.search(r"pt='([^']+)'", str(partition))
            if match:
                partitions.append(match.group(1))
        result = sorted(set(partitions), reverse=True)
        self._partition_cache = (time.time(), result)
        return result

    def refresh_partitions(self) -> list[str]:
        self._partition_cache = None
        self._partition_range_cache = None
        return self.available_partitions(prefer_serving=False)

    def partition_ranges(self) -> dict[str, dict[str, str]]:
        """每个分区内 create_date 的 MIN/MAX，供前端观察区间档位动态计算。"""
        cached = self._partition_range_cache
        if cached and time.time() - cached[0] < CACHE_SECONDS:
            return {key: dict(value) for key, value in cached[1].items()}
        published = fund_assemble.read_partition_ranges(FUND_SERVING_DIR)
        if published:
            self._partition_range_cache = (time.time(), published)
            return {key: dict(value) for key, value in published.items()}
        ranges: dict[str, dict[str, str]] = {}
        date_field = self.config["date_field"]
        for pt in self.available_partitions():
            try:
                rows = _run_sql_rows(
                    f"""
                    SELECT MIN(TO_CHAR({date_field}, 'yyyy-MM-dd')) AS min_day,
                           MAX(TO_CHAR({date_field}, 'yyyy-MM-dd')) AS max_day
                    FROM {self.table_name}
                    WHERE pt = '{pt}'
                    """
                )
            except Exception:  # noqa: BLE001
                continue
            if rows and rows[0].get("min_day"):
                ranges[pt] = {"min": rows[0]["min_day"], "max": rows[0]["max_day"]}
        self._partition_range_cache = (time.time(), ranges)
        return {key: dict(value) for key, value in ranges.items()}

    # ---------- 磁盘缓存 ----------
    def _disk_cache_path(self, key: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", key)
        return DISK_CACHE_DIR / f"fund_{safe}.json"

    def _load_disk_cache(self, key: str) -> dict[str, Any] | None:
        path = self._disk_cache_path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - float(payload.get("_ts", 0)) < CACHE_SECONDS:
                return payload.get("result")
        except Exception:  # noqa: BLE001
            pass
        return None

    def _save_disk_cache(self, key: str, result: dict[str, Any]) -> None:
        try:
            DISK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            payload = {"_ts": time.time(), "result": result}
            self._disk_cache_path(key).write_text(
                json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8"
            )
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _generated_at(payload: dict[str, Any] | None) -> str:
        if not isinstance(payload, dict):
            return ""
        meta = payload.get("meta")
        return str(meta.get("generated_at") or "") if isinstance(meta, dict) else ""

    def _latest_published_partition(self, offset: int) -> str | None:
        """最近一个已发布 serving/缓存分区（不访问 MaxCompute，页面秒开）。"""
        if FUND_SERVING_DIR.exists():
            pattern = re.compile(r"^dashboard_([A-Za-z0-9_-]+)_([0-9]+)\.parquet$")
            candidates: list[str] = []
            for path in FUND_SERVING_DIR.glob(f"dashboard_*_{offset}.parquet"):
                match = pattern.fullmatch(path.name)
                if match and int(match.group(2)) == offset:
                    candidates.append(match.group(1))
            if candidates:
                return sorted(set(candidates), reverse=True)[0]
        if not DISK_CACHE_DIR.exists():
            return None
        pattern = re.compile(r"^fund_([A-Za-z0-9_-]+)_(\d+)\.json$")
        candidates: list[str] = []
        for path in DISK_CACHE_DIR.glob(f"fund_*_{offset}.json"):
            match = pattern.fullmatch(path.name)
            if match and int(match.group(2)) == offset:
                candidates.append(match.group(1))
        for candidate in sorted(set(candidates), reverse=True):
            if self._load_disk_cache(f"{candidate}|{offset}") is not None:
                return candidate
        return None

    # ---------- 规则状态 ----------
    def with_rule_statuses(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(payload)
        statuses = self._status_store.get_all()
        active_tracking = self._status_store.get_active_tagged_rules()
        missing_rules: list[tuple[str, dict[str, Any]]] = []

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                canonical_path = value.get("canonical_path")
                if canonical_path is not None and "level" in value:
                    status = statuses.get(str(canonical_path))
                    value["status"] = int(status["status"]) if status else 0
                    value["status_updated_at"] = status["updated_at"] if status else None
                    value["status_updated_by"] = status["updated_by"] if status else None
                    value["action_date"] = status.get("action_date") if status else None
                    active = active_tracking.get(str(canonical_path))
                    value["tracking_start_pt"] = active.get("entered_pt") if active else None
                    if status and int(status["status"]) in (1, 2) and not status.get("rule"):
                        missing_rules.append((str(canonical_path), value))
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(result)
        for canonical_path, rule in missing_rules:
            self._status_store.save_rule_if_missing(canonical_path, rule)
        return result

    # ---------- dashboard ----------
    def dashboard(self, partition: str | None = None, force: bool = False, offset: int = 0) -> dict[str, Any]:
        offset = max(0, min(int(offset), 180))
        selected = partition
        if selected is None and not force:
            # 优先展示最近已落盘缓存，避免因上游新 pt 同步扫 MaxCompute
            selected = self._latest_published_partition(offset)
        if selected is None:
            partitions = self.available_partitions()
            if not partitions:
                raise FundAttributionServiceError("目标表未找到可用 pt 分区。")
            selected = partition or partitions[0]

        if not SAFE_PARTITION.fullmatch(selected):
            raise FundAttributionServiceError(f"分区 pt={selected} 格式不合法。")

        cache_key = f"{selected}|{offset}"
        if force:
            for key in [k for k in self._path_trend_cache if k.startswith(f"{selected}|{offset}|")]:
                self._path_trend_cache.pop(key, None)

        cached = self._cache.get(cache_key)
        if cached and not force and time.time() - cached[0] < CACHE_SECONDS:
            result = copy.deepcopy(cached[1])
            result["meta"]["cache_hit"] = True
            return result

        if not force:
            serving = fund_assemble.read_dashboard_snapshot(FUND_SERVING_DIR, selected, offset)
            if serving:
                result = self._adopt_serving_snapshot(serving, selected, offset, cache_key)
                result["meta"]["cache_hit"] = True
                return result
            disk = self._load_disk_cache(cache_key)
            if disk:
                self._cache[cache_key] = (time.time(), disk)
                result = copy.deepcopy(disk)
                result["meta"]["cache_hit"] = True
                return result
            raise FundAttributionServiceError(
                f"pt={selected} 尚无缓存结果，请点击「刷新归因」后查看（首次计算约需 1-3 分钟）。"
            )

        # force 刷新且已有旧缓存: 立即返回旧数据, 后台线程异步重算(避免用户长时间等待)
        if cached:
            result = copy.deepcopy(cached[1])
            result["meta"]["cache_hit"] = True
            result["meta"]["async_refresh"] = True
            result["meta"]["generated_at"] = cached[1]["meta"]["generated_at"]
            threading.Thread(
                target=self._recompute,
                args=(selected, offset),
                daemon=True,
                name=f"fund-attribution-recompute-{cache_key}",
            ).start()
            return result

        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and not force and time.time() - cached[0] < CACHE_SECONDS:
                result = copy.deepcopy(cached[1])
                result["meta"]["cache_hit"] = True
                return result
            return self._compute_and_cache(selected, offset)

    def _adopt_serving_snapshot(
        self, snapshot: dict[str, Any], selected: str, offset: int, cache_key: str
    ) -> dict[str, Any]:
        result = copy.deepcopy(snapshot)
        result.setdefault("meta", {})["partition"] = selected
        result["meta"]["offset_days"] = offset
        result["meta"]["cache_hit"] = True
        result["meta"]["serving"] = True
        result["meta"]["async_refresh"] = False
        self._cache[cache_key] = (time.time(), result)
        self._save_disk_cache(cache_key, result)
        for key in [key for key in self._path_trend_cache if key.startswith(f"{selected}|{offset}|")]:
            self._path_trend_cache.pop(key, None)
        return result

    def _compute_and_cache(self, selected: str, offset: int) -> dict[str, Any]:
        runner = FundAttributionRunner(
            config=self.config,
            table=self.table_name,
            partition=selected,
            offset=offset,
            query_rows=_run_sql_rows,
        )
        result = runner.run()
        result["meta"]["cache_hit"] = False
        result["meta"]["async_refresh"] = False
        self._cache[f"{selected}|{offset}"] = (time.time(), result)
        self._save_disk_cache(f"{selected}|{offset}", result)
        return copy.deepcopy(result)

    def _recompute(self, selected: str, offset: int = 0) -> None:
        """后台线程强制重算并更新缓存（force 刷新不阻塞请求）。"""
        cache_key = f"{selected}|{offset}"
        try:
            with self._lock:
                self._compute_and_cache(selected, offset)
        except Exception:  # noqa: BLE001
            # 后台重算失败保留旧缓存, 前端轮询超时后自然停止
            pass

    # ---------- 路径趋势 ----------
    def path_trend(self, record_id: str, partition: str | None = None, offset: int = 0) -> dict[str, Any]:
        if not SAFE_RECORD_ID.fullmatch(record_id):
            raise FundAttributionServiceError("预警路径标识格式不合法。")
        dashboard = self.dashboard(partition=partition, offset=offset)
        selected_partition = dashboard["meta"]["partition"]
        record = next(
            (
                item
                for item in dashboard.get("merged_alerts", [])
                + dashboard.get("top_k", {}).get("single_downstream", [])
                + dashboard.get("top_k", {}).get("pair_downstream", [])
                + dashboard.get("top_k", {}).get("third_alerts", [])
                + dashboard.get("expert", {}).get("single", [])
                + dashboard.get("expert", {}).get("pair", [])
                + dashboard.get("expert", {}).get("third", [])
                + dashboard.get("review_items", [])
                if item.get("id") == record_id
            ),
            None,
        )
        if record is None:
            raise FundAttributionServiceError("未在当前归因结果中找到该路径，请刷新归因结果后重试。")

        cache_key = f"{selected_partition}|{offset}|{record_id}"
        cached = self._path_trend_cache.get(cache_key)
        if cached and time.time() - cached[0] < CACHE_SECONDS:
            return copy.deepcopy(cached[1])
        result = self._format_path_trend(record)
        self._path_trend_cache[cache_key] = (time.time(), result)
        return copy.deepcopy(result)

    @staticmethod
    def _format_path_trend(record: dict[str, Any]) -> dict[str, Any]:
        daily = record.get("daily") or []
        latest = daily[-1] if daily else None
        previous = daily[-2] if len(daily) > 1 else None
        peak = max(daily, key=lambda item: float(item["abnormal_order_count"])) if daily else None
        primary_window = (record.get("windows") or {}).get(record.get("primary_window"), {})
        return {
            "record_id": record["id"],
            "path": record["path"],
            "source": record["source"],
            "level": record["level"],
            "level_label": record["level_label"],
            "severity": record["severity"],
            "status": record.get("status", 0),
            "primary_window": {
                "key": record["primary_window"],
                "label": primary_window.get("label", record.get("primary_window_label")),
                "observation_start": primary_window.get("observation_start"),
                "observation_end": primary_window.get("observation_end"),
                "baseline_start": primary_window.get("baseline_start"),
                "baseline_end": primary_window.get("baseline_end"),
                "baseline_daily": primary_window.get("baseline_abnormal_daily", 0),
            },
            "daily": daily,
            "summary": {
                "period_days": len(daily),
                "period_abnormal_count": sum(float(item["abnormal_order_count"]) for item in daily),
                "latest_abnormal_count": latest["abnormal_order_count"] if latest else 0,
                "previous_abnormal_count": previous["abnormal_order_count"] if previous else None,
                "latest_day_change_pct": (
                    (float(latest["abnormal_order_count"]) / float(previous["abnormal_order_count"]) - 1) * 100
                    if previous and float(previous["abnormal_order_count"]) > 0
                    else 0.0
                ),
                "peak_abnormal_count": peak["abnormal_order_count"] if peak else 0,
                "peak_date": peak["date"] if peak else None,
                "latest_abnormal_rate": latest["abnormal_rate"] if latest else 0.0,
            },
        }


load_fund_config()
CACHE_SECONDS = int(os.getenv("FUND_CACHE_SECONDS", os.getenv("ATTRIBUTION_CACHE_SECONDS", "900")))
service = FundAttributionService()

router = APIRouter(prefix="/api/fund-attribution", tags=["fund-attribution"])


def handle_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (FundAttributionError, FundAttributionServiceError)):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, RuntimeError) and "无可用数据" in str(exc):
        return HTTPException(status_code=503, detail=str(exc))
    # 避免泄漏 SQL 文本、endpoint 或凭证
    return HTTPException(status_code=502, detail="MaxCompute 数据读取失败，请检查服务端连接与表权限。")


@router.get("/health")
def health(_user: dict = Depends(require_perm("fundMonitor"))) -> dict[str, Any]:
    try:
        connection = get_connection()
        return {
            "status": "configured",
            "project": connection.project,
            "table": service.table_name,
            "version": service.config.get("version"),
            "scheme_name": service.config.get("scheme_name"),
        }
    except FundAttributionServiceError as exc:
        return {"status": "not_configured", "detail": str(exc)}


@router.get("/partitions")
def partitions(force: bool = False, _user: dict = Depends(require_perm("fundMonitor"))) -> JSONResponse:
    try:
        return JSONResponse(
            content={
                "partitions": service.refresh_partitions() if force else service.available_partitions(),
                "ranges": service.partition_ranges(),
            }
        )
    except Exception as exc:  # noqa: BLE001
        raise handle_error(exc) from exc


@router.get("/dashboard")
def dashboard(
    pt: str | None = Query(default=None, max_length=64),
    force: bool = Query(default=False),
    offset: int = Query(default=0, ge=0, le=180),
    _user: dict = Depends(require_perm("fundMonitor")),
) -> JSONResponse:
    try:
        payload = service.with_rule_statuses(service.dashboard(partition=pt, force=force, offset=offset))
        return JSONResponse(content=json_safe(payload))
    except Exception as exc:  # noqa: BLE001
        raise handle_error(exc) from exc


@router.get("/path-trend")
def path_trend(
    record_id: str = Query(min_length=12, max_length=12),
    pt: str | None = Query(default=None, max_length=64),
    offset: int = Query(default=0, ge=0, le=180),
    _user: dict = Depends(require_perm("fundMonitor")),
) -> JSONResponse:
    try:
        return JSONResponse(content=json_safe(service.path_trend(record_id=record_id, partition=pt, offset=offset)))
    except Exception as exc:  # noqa: BLE001
        raise handle_error(exc) from exc


class FundRuleStatusUpdate(BaseModel):
    canonical_path: str = Field(min_length=1, max_length=2000)
    status: int = Field(ge=0, le=2)
    action_pt: str = Field(min_length=1, max_length=64)
    rule: dict[str, Any] | None = None

    @field_validator("action_pt")
    @classmethod
    def action_pt_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("action_pt cannot be blank")
        return value


@router.put("/rule-status")
def update_rule_status(
    update: FundRuleStatusUpdate,
    user: dict = Depends(require_perm("fundMonitor")),
) -> JSONResponse:
    try:
        result = service._status_store.set_status(
            update.canonical_path,
            update.status,
            str(user.get("username") or "unknown"),
            action_pt=update.action_pt,
            rule=update.rule,
        )
        history = next(
            (
                item
                for item in service._status_store.get_history()
                if item["canonical_path"] == result["canonical_path"] and item["is_active"]
            ),
            None,
        )
        result["history"] = history if result["status"] in (1, 2) else None
        return JSONResponse(content=json_safe(result))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise handle_error(exc) from exc


@router.get("/rule-status-history")
def rule_status_history(_user: dict = Depends(require_perm("fundMonitor"))) -> JSONResponse:
    return JSONResponse(content=json_safe({"records": service._status_store.get_history()}))
