"""授信归因监控 API。

AK/SK 只在服务端读取：优先使用部署环境变量；本地开发可从指定 notebook
静态读取 ODPS(AK, SK, project, endpoint) 的字面量参数。不会执行 notebook，
不会向浏览器返回或写入 AK/SK。
"""

from __future__ import annotations

import ast
import copy
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from auth import require_perm, router as auth_router
from attribution_status import AttributionStatusStore
from warehouse import WarehouseAttributionRunner

try:
    from odps import ODPS
except ImportError:  # pragma: no cover
    ODPS = None  # type: ignore[assignment,misc]

# 预计算 serving 快照层(P1):缺失/损坏时自动降级为在线计算,不阻塞启动
try:
    from pipeline import DB_PATH, SERVING_DIR, assemble as serving_assemble
except Exception:  # pragma: no cover
    SERVING_DIR = ROOT / "data" / "serving"
    DB_PATH = ROOT / "data" / "attribution.duckdb"
    serving_assemble = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "attribution_config.json"
LOCAL_ENV_PATH = ROOT / ".env.local"
STATUS_DB_PATH = ROOT / "data" / "attribution_status.sqlite3"
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$")
SAFE_PARTITION = re.compile(r"^[A-Za-z0-9_-]+$")
SAFE_RECORD_ID = re.compile(r"^[0-9a-f]{12}$")
DISK_CACHE_DIR = ROOT / "data" / "attribution_cache"


class AttributionServiceError(RuntimeError):
    """A configuration/data-source failure that is safe to expose to the UI."""


@dataclass(frozen=True)
class MaxComputeConnection:
    access_key_id: str
    access_key_secret: str
    project: str
    endpoint: str


def load_local_env() -> None:
    """Load git-ignored server/.env.local without adding a dotenv dependency."""
    if not LOCAL_ENV_PATH.exists():
        return
    for raw_line in LOCAL_ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _literal_string(node: ast.AST, label: str) -> str:
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        raise AttributionServiceError(f"Notebook 中的 {label} 不是静态字符串，无法安全读取。")
    return node.value


def read_connection_from_notebook(path: Path) -> MaxComputeConnection:
    """Read literal ODPS arguments only; untrusted notebook code is never executed."""
    if not path.exists():
        raise AttributionServiceError(f"未找到连接 notebook：{path}")
    try:
        notebook = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AttributionServiceError("无法解析 MaxCompute 连接 notebook。") from exc

    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        try:
            tree = ast.parse("".join(cell.get("source", [])))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if name != "ODPS" or len(node.args) < 3:
                continue
            endpoint = next((keyword.value for keyword in node.keywords if keyword.arg == "endpoint"), None)
            if endpoint is None:
                continue
            return MaxComputeConnection(
                access_key_id=_literal_string(node.args[0], "Access Key ID"),
                access_key_secret=_literal_string(node.args[1], "Access Key Secret"),
                project=_literal_string(node.args[2], "project"),
                endpoint=_literal_string(endpoint, "endpoint"),
            )
    raise AttributionServiceError("Notebook 中未找到可用的 ODPS(AK, SK, project, endpoint) 调用。")


def get_connection() -> MaxComputeConnection:
    values = {
        "access_key_id": os.getenv("MAXCOMPUTE_ACCESS_KEY_ID", "").strip(),
        "access_key_secret": os.getenv("MAXCOMPUTE_ACCESS_KEY_SECRET", "").strip(),
        "project": os.getenv("MAXCOMPUTE_PROJECT", "").strip(),
        "endpoint": os.getenv("MAXCOMPUTE_ENDPOINT", "").strip(),
    }
    if all(values.values()):
        return MaxComputeConnection(**values)

    notebook_path = os.getenv("MAXCOMPUTE_NOTEBOOK_PATH", "").strip()
    if not notebook_path:
        raise AttributionServiceError(
            "未配置 MaxCompute 凭据。请设置 MAXCOMPUTE_* 环境变量，或在 server/.env.local 中设置 MAXCOMPUTE_NOTEBOOK_PATH。"
        )
    return read_connection_from_notebook(Path(notebook_path).expanduser())


def json_safe(value: Any) -> Any:
    """Convert rare numpy/pandas scalar results without exposing internal objects."""
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if hasattr(value, "item") and callable(value.item):
        try:
            return value.item()
        except Exception:
            pass
    return value


class AttributionService:
    def __init__(self) -> None:
        self.config = load_config()
        self._status_store = AttributionStatusStore(STATUS_DB_PATH)
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._path_trend_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._partition_cache: tuple[float, list[str]] | None = None
        self._partition_range_cache: tuple[float, dict[str, dict[str, str]]] | None = None
        self._lock = threading.Lock()

    def with_rule_statuses(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Overlay manually managed rule states onto a fresh dashboard payload."""
        result = copy.deepcopy(payload)
        statuses = self._status_store.get_all()
        missing_rules: list[tuple[str, dict[str, Any]]] = []

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                canonical_path = value.get("canonical_path")
                if canonical_path is not None:
                    status = statuses.get(str(canonical_path))
                    value["status"] = int(status["status"]) if status else 0
                    value["status_updated_at"] = status["updated_at"] if status else None
                    value["status_updated_by"] = status["updated_by"] if status else None
                    value["action_date"] = status.get("action_date") if status else None
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

    @property
    def table_name(self) -> str:
        table = os.getenv("MAXCOMPUTE_TABLE", self.config["table"]).strip()
        if not SAFE_IDENTIFIER.fullmatch(table):
            raise AttributionServiceError("MAXCOMPUTE_TABLE 格式不合法。")
        return table

    def _odps(self) -> Any:
        if ODPS is None:
            raise AttributionServiceError("未安装 pyodps。请执行 python -m pip install -r server/requirements.txt。")
        connection = get_connection()
        return ODPS(
            connection.access_key_id,
            connection.access_key_secret,
            project=connection.project,
            endpoint=connection.endpoint,
        )

    def available_partitions(self) -> list[str]:
        cached = self._partition_cache
        if cached and time.time() - cached[0] < CACHE_SECONDS:
            return list(cached[1])

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
        """清空分区缓存后重新发现(上游补数/调度延迟时, 前端刷新即可见到新分区)."""
        self._partition_cache = None
        return self.available_partitions()

    def _latest_published_partition(self, offset: int) -> str | None:
        """Return the newest local serving partition without querying MaxCompute."""
        if serving_assemble is not None:
            pattern = re.compile(r"^dashboard_(.+)_(\d+)\.parquet$")
            candidates: list[str] = []
            serving_dir = Path(SERVING_DIR)
            if serving_dir.exists():
                for path in serving_dir.glob(f"dashboard_*_{offset}.parquet"):
                    match = pattern.fullmatch(path.name)
                    if match and int(match.group(2)) == offset:
                        candidates.append(match.group(1))
            for candidate in sorted(set(candidates), reverse=True):
                try:
                    snapshot = serving_assemble.read_dashboard_snapshot(SERVING_DIR, candidate, offset)
                except Exception:
                    snapshot = None
                if snapshot is not None:
                    return candidate

        # serving 快照不可用时，再检查已经落盘的在线缓存；同样不访问 MaxCompute。
        cache_dir = Path(DISK_CACHE_DIR)
        if cache_dir.exists():
            cache_pattern = re.compile(r"^([A-Za-z0-9_-]+)_(\d+)\.json$")
            cached_candidates: list[str] = []
            for path in cache_dir.glob(f"*_{offset}.json"):
                match = cache_pattern.fullmatch(path.name)
                if match and int(match.group(2)) == offset:
                    cached_candidates.append(match.group(1))
            for candidate in sorted(set(cached_candidates), reverse=True):
                if self._load_disk_cache(f"{candidate}|{offset}") is not None:
                    return candidate
        return None

    def partition_ranges(self) -> dict[str, dict[str, str]]:
        """每个分区内 create_date 的 MIN/MAX, 供前端观察区间档位动态计算.

        优先读预计算快照(夜间管线一条 GROUP BY 刷新);快照缺失时才回退到
        逐分区串行查询(冷启动可能耗时数十秒).
        """
        cached = self._partition_range_cache
        if cached and time.time() - cached[0] < CACHE_SECONDS:
            return {key: dict(value) for key, value in cached[1].items()}
        if serving_assemble is not None:
            ranges = serving_assemble.read_partition_ranges(SERVING_DIR)
            if ranges:
                self._partition_range_cache = (time.time(), ranges)
                return {key: dict(value) for key, value in ranges.items()}
        ranges: dict[str, dict[str, str]] = {}
        date_field = self.config["date_field"]
        for pt in self.available_partitions():
            try:
                rows = self._run_sql_rows(
                    f"""
                    SELECT MIN(TO_CHAR({date_field}, 'yyyy-MM-dd')) AS min_day,
                           MAX(TO_CHAR({date_field}, 'yyyy-MM-dd')) AS max_day
                    FROM {self.table_name}
                    WHERE pt = '{pt}'
                    """
                )
            except Exception:
                continue
            if rows and rows[0].get("min_day"):
                ranges[pt] = {"min": rows[0]["min_day"], "max": rows[0]["max_day"]}
        self._partition_range_cache = (time.time(), ranges)
        return {key: dict(value) for key, value in ranges.items()}

    def _run_sql_rows(self, sql: str) -> list[dict[str, Any]]:
        """Pair-safe PyODPS Record extraction for compact daily aggregation results."""
        odps = self._odps()
        instance = odps.execute_sql(sql)
        rows: list[dict[str, Any]] = []
        with instance.open_reader(tunnel=True, limit=False) as reader:
            columns = [column.name for column in reader.schema.columns]
            for record in reader:
                row: dict[str, Any] = {}
                for index, name in enumerate(columns):
                    try:
                        row[name] = record[name]
                    except Exception:
                        row[name] = record[index]
                rows.append(row)
        return rows

    # ---------- 磁盘持久化缓存: 服务重启后依然秒开 ----------
    def _disk_cache_path(self, key: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", key)
        return DISK_CACHE_DIR / f"{safe}.json"

    def _load_disk_cache(self, key: str) -> dict[str, Any] | None:
        path = self._disk_cache_path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - float(payload.get("_ts", 0)) < CACHE_SECONDS:
                return payload.get("result")
        except Exception:
            pass
        return None

    def _save_disk_cache(self, key: str, result: dict[str, Any]) -> None:
        try:
            DISK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            payload = {"_ts": time.time(), "result": result}
            self._disk_cache_path(key).write_text(
                json.dumps(payload, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _enrich_approval(self, payload: dict[str, Any], selected: str, offset: int) -> None:
        """读取层富化:用 path_daily 快照给 alert 补窗口通过量/通过率。

        快照缺失或旧格式时字段留空(前端显示 —);任何异常都静默,
        不影响 dashboard 主流程。
        """
        if serving_assemble is None or not isinstance(payload, dict):
            return
        try:
            frame = serving_assemble.read_path_daily_frame(SERVING_DIR, selected, offset)
            serving_assemble.enrich_approval_rates(payload, frame)
        except Exception:
            pass

    @staticmethod
    def _generated_at(payload: dict[str, Any] | None) -> str:
        """结果生成时间(ISO 字符串可直接按字典序比较);缺失时视为最旧。"""
        if not isinstance(payload, dict):
            return ""
        meta = payload.get("meta")
        return str(meta.get("generated_at") or "") if isinstance(meta, dict) else ""

    def _adopt_serving_snapshot(self, snapshot: dict[str, Any], selected: str, offset: int, cache_key: str) -> dict[str, Any]:
        """采纳管线刚发布的 serving 快照, 覆盖旧缓存并清除对应路径趋势缓存。"""
        self._enrich_approval(snapshot, selected, offset)
        self._cache[cache_key] = (time.time(), snapshot)
        self._save_disk_cache(cache_key, snapshot)
        for key in [key for key in self._path_trend_cache if key.startswith(f"{selected}|{offset}|")]:
            self._path_trend_cache.pop(key, None)
        return snapshot

    def dashboard(self, partition: str | None = None, force: bool = False, offset: int = 0) -> dict[str, Any]:
        offset = max(0, min(int(offset), 180))

        # 首次打开页面优先展示最近已发布快照，避免因为上游刚出新 pt 而同步扫 MaxCompute。
        # force=true 或显式指定 pt 时，仍走最新分区/指定分区的计算路径。
        partitions: list[str] | None = None
        selected = partition
        if selected is None and not force:
            selected = self._latest_published_partition(offset)
        if selected is None:
            partitions = self.available_partitions()
            if not partitions:
                raise AttributionServiceError("目标表未找到可用 pt 分区。")
            selected = partition or partitions[0]

        if not SAFE_PARTITION.fullmatch(selected):
            raise AttributionServiceError(f"分区 pt={selected} 格式不合法。")
        if partitions is not None and selected not in partitions:
            raise AttributionServiceError(f"分区 pt={selected} 不存在或格式不合法。")

        cache_key = f"{selected}|{offset}"

        if force:
            for key in [key for key in self._path_trend_cache if key.startswith(f"{selected}|{offset}|")]:
                self._path_trend_cache.pop(key, None)

        cached = self._cache.get(cache_key)
        if cached and not force and time.time() - cached[0] < CACHE_SECONDS:
            # 管线可能在 API 进程外发布了新快照: 不能让 15 分钟内存缓存遮住新数据
            if serving_assemble is not None:
                snapshot = serving_assemble.read_dashboard_snapshot(SERVING_DIR, selected, offset)
                if snapshot is not None and self._generated_at(snapshot) > self._generated_at(cached[1]):
                    result = copy.deepcopy(self._adopt_serving_snapshot(snapshot, selected, offset, cache_key))
                    result["meta"]["cache_hit"] = True
                    return result
            result = copy.deepcopy(cached[1])
            result["meta"]["cache_hit"] = True
            return result

        # 内存未命中: serving 快照与磁盘缓存都可能存在, 按 generated_at 取最新。
        # serving 是管线发布的权威产物, 先比对避免旧磁盘缓存遮住刚发布的数据。
        if not force:
            disk = self._load_disk_cache(cache_key)
            snapshot = (
                serving_assemble.read_dashboard_snapshot(SERVING_DIR, selected, offset)
                if serving_assemble is not None
                else None
            )
            if snapshot is not None and (
                disk is None or self._generated_at(snapshot) >= self._generated_at(disk)
            ):
                result = copy.deepcopy(self._adopt_serving_snapshot(snapshot, selected, offset, cache_key))
                result["meta"]["cache_hit"] = True
                return result
            if disk:
                self._enrich_approval(disk, selected, offset)
                self._cache[cache_key] = (time.time(), disk)
                result = copy.deepcopy(disk)
                result["meta"]["cache_hit"] = True
                return result

        if not force:
            raise AttributionServiceError(
                f"pt={selected} 尚未发布预计算快照，请点击刷新后再查看最新数据。"
            )

        # force 刷新且已有旧缓存: 立即返回旧数据, 后台线程异步重算(避免用户长时间等待)
        if force and cached:
            result = copy.deepcopy(cached[1])
            result["meta"]["cache_hit"] = True
            result["meta"]["async_refresh"] = True
            result["meta"]["generated_at"] = cached[1]["meta"]["generated_at"]
            threading.Thread(
                target=self._recompute,
                args=(selected, offset),
                daemon=True,
                name=f"attribution-recompute-{cache_key}",
            ).start()
            return result

        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and not force and time.time() - cached[0] < CACHE_SECONDS:
                result = copy.deepcopy(cached[1])
                result["meta"]["cache_hit"] = True
                return result
            runner = WarehouseAttributionRunner(
                config=self.config,
                table=self.table_name,
                partition=selected,
                offset=offset,
                query_rows=self._run_sql_rows,
            )
            result = runner.run()
            result["meta"]["cache_hit"] = False
            self._enrich_approval(result, selected, offset)
            self._cache[cache_key] = (time.time(), result)
            self._save_disk_cache(cache_key, result)
            # 兜底写回:子进程把结果发布进 DuckDB + 快照(下次就是秒读)
            self._spawn_ingest(selected, offset, result)
            return copy.deepcopy(result)

    @staticmethod
    def _format_precomputed_path_trend(
        record: dict[str, Any], rows: list[dict[str, Any]], limit: int = 60
    ) -> dict[str, Any] | None:
        """Format path trend rows already persisted by the attribution pipeline."""
        totals: dict[str, float] = {}
        path_counts: dict[str, float] = {}
        approvals: dict[str, float] = {}
        cid_counts: dict[str, float] = {}
        approval_cid_counts: dict[str, float] = {}
        record_id = str(record["id"])

        def day_text(value: Any) -> str:
            return value.isoformat() if hasattr(value, "isoformat") else str(value)[:10]

        def number(value: Any) -> float:
            try:
                parsed = float(value or 0)
                return parsed if parsed == parsed else 0.0
            except (TypeError, ValueError):
                return 0.0

        for row in rows:
            day = day_text(row.get("date"))
            total = number(row.get("total_application_count"))
            totals[day] = max(totals.get(day, 0.0), total)
            if str(row.get("alert_id")) != record_id:
                continue
            path_counts[day] = number(row.get("application_count"))
            approval = row.get("approval_count")
            if approval is not None:
                try:
                    parsed_approval = float(approval)
                    if parsed_approval == parsed_approval:
                        approvals[day] = parsed_approval
                except (TypeError, ValueError):
                    pass
            cid = row.get("cid_cnt")
            if cid is not None:
                try:
                    parsed_cid = float(cid)
                    if parsed_cid == parsed_cid:
                        cid_counts[day] = parsed_cid
                except (TypeError, ValueError):
                    pass
            approval_cid = row.get("approval_cid_cnt")
            if approval_cid is not None:
                try:
                    parsed_approval_cid = float(approval_cid)
                    if parsed_approval_cid == parsed_approval_cid:
                        approval_cid_counts[day] = parsed_approval_cid
                except (TypeError, ValueError):
                    pass

        days = sorted(totals)[-int(limit):]
        if not days:
            return None

        daily: list[dict[str, Any]] = []
        for day in days:
            application_count = path_counts.get(day, 0.0)
            total_application_count = totals[day]
            approval_count = approvals.get(day)
            cid_count = cid_counts.get(day)
            approval_cid_count = approval_cid_counts.get(day)
            daily.append(
                {
                    "date": day,
                    "application_count": application_count,
                    "total_application_count": total_application_count,
                    "application_share_pct": (
                        application_count / total_application_count * 100
                        if total_application_count
                        else 0.0
                    ),
                    "approval_count": approval_count,
                    "approval_rate_pct": (
                        approval_count / application_count * 100
                        if approval_count is not None and application_count > 0
                        else 0.0 if approval_count is not None else None
                    ),
                    "cid_cnt": cid_count,
                    "approval_cid_cnt": approval_cid_count,
                    "cid_approval_rate_pct": (
                        approval_cid_count / cid_count * 100
                        if approval_cid_count is not None and cid_count is not None and cid_count > 0
                        else 0.0 if approval_cid_count is not None and cid_count is not None else None
                    ),
                }
            )

        latest = daily[-1]
        previous = daily[-2] if len(daily) > 1 else None
        peak = max(daily, key=lambda item: float(item["application_count"]))
        primary_window = (record.get("windows") or {}).get(record.get("primary_window"), {})
        return {
            "record_id": record["id"],
            "path": record["path"],
            "source": record["source"],
            "level": record["level"],
            "level_label": record["level_label"],
            "severity": record["severity"],
            "primary_window": {
                "key": record["primary_window"],
                "label": primary_window.get("label", record["primary_window_label"]),
                "observation_start": primary_window.get("observation_start"),
                "observation_end": primary_window.get("observation_end"),
                "baseline_daily": primary_window.get("baseline_daily", 0),
            },
            "daily": daily,
            "summary": {
                "period_days": len(daily),
                "period_application_count": sum(float(item["application_count"]) for item in daily),
                "latest_application_count": latest["application_count"],
                "previous_application_count": previous["application_count"] if previous else None,
                "latest_day_change_pct": (
                    (float(latest["application_count"]) / float(previous["application_count"]) - 1) * 100
                    if previous and float(previous["application_count"]) > 0
                    else 0.0
                ),
                "peak_application_count": peak["application_count"],
                "peak_date": peak["date"],
                "latest_application_share_pct": latest["application_share_pct"],
                "latest_approval_rate_pct": latest["approval_rate_pct"],
                "latest_cid_approval_rate_pct": latest["cid_approval_rate_pct"],
            },
        }

    def _read_duckdb_path_trend(
        self, record: dict[str, Any], selected: str, offset: int
    ) -> dict[str, Any] | None:
        """Read the latest precomputed path trend for a pt from DuckDB."""
        if not Path(DB_PATH).exists():
            return None
        try:
            conn = duckdb.connect(str(DB_PATH), read_only=True)
            try:
                run = conn.execute(
                    """
                    SELECT run_id
                    FROM attr_runs
                    WHERE pt = ? AND offset_days = ?
                    ORDER BY generated_at DESC
                    LIMIT 1
                    """,
                    [selected, int(offset)],
                ).fetchone()
                if not run:
                    return None
                result = conn.execute(
                    """
                    SELECT alert_id, date, application_count,
                           total_application_count, approval_count,
                           cid_cnt, approval_cid_cnt
                    FROM attr_path_daily
                    WHERE run_id = ?
                    ORDER BY date, alert_id
                    """,
                    [run[0]],
                ).fetchall()
                columns = [
                    "alert_id", "date", "application_count",
                    "total_application_count", "approval_count",
                    "cid_cnt", "approval_cid_cnt",
                ]
                rows = [dict(zip(columns, row)) for row in result]
            finally:
                conn.close()
            return self._format_precomputed_path_trend(record, rows)
        except Exception:
            return None

    def _spawn_ingest(self, selected: str, offset: int, result: dict[str, Any]) -> None:
        """后台子进程调用管线 ingest,把在线兜底结果写入 DuckDB + 快照。

        保持单写者纪律:API 进程自身不打开 DuckDB;子进程失败静默降级
        (下次访问重试),不影响本次响应。
        """
        if serving_assemble is None:
            return

        def _work() -> None:
            try:
                tmp_dir = DISK_CACHE_DIR.parent / "tmp"
                tmp_dir.mkdir(parents=True, exist_ok=True)
                input_path = tmp_dir / f"ingest_{uuid.uuid4().hex}.json"
                input_path.write_text(
                    json.dumps({"pt": selected, "offset": offset, "result": json_safe(result)}, ensure_ascii=False, default=str),
                    encoding="utf-8",
                )
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                subprocess.Popen(
                    [sys.executable, "-m", "pipeline.cli", "ingest", "--input", str(input_path)],
                    cwd=str(ROOT),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=flags,
                )
            except Exception:
                pass

        threading.Thread(target=_work, daemon=True, name="attribution-ingest").start()

    def _recompute(self, selected: str, offset: int = 0) -> None:
        """后台线程:强制重算指定分区并更新缓存(force 刷新不阻塞请求).

        P1 起优先走管线子进程(重算 + 发布快照);子进程不可用时回退为
        进程内在线重算(仅更新内存/磁盘缓存,不落库).
        """
        cache_key = f"{selected}|{offset}"
        if serving_assemble is not None:
            try:
                # 调度延迟场景: 先重新发现分区, 若上游已产出比当前更新的分区则一并重算发布,
                # 这样点「刷新归因」即可补上缺失的每日快照, 无需等夜间调度
                try:
                    latest = self.refresh_partitions()[0]
                except Exception:
                    latest = selected
                # 当前分区先算(前端轮询的是它), 新分区追加在后;
                # 新分区已有 path_daily 快照时跳过(避免每次刷新都重复重算)
                targets = [selected]
                if latest > selected and latest not in targets:
                    has_snapshot = (
                        Path(SERVING_DIR) / f"path_daily_{latest}_0.parquet"
                    ).exists()
                    if not has_snapshot:
                        targets.append(latest)
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                ok_targets: list[str] = []
                proc = None
                for target_pt in targets:
                    t_off = offset if target_pt == selected else 0
                    proc = subprocess.run(
                        [sys.executable, "-m", "pipeline.cli", "run", "--pt", target_pt, "--offset", str(t_off)],
                        cwd=str(ROOT),
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=int(os.getenv("ATTRIBUTION_PIPELINE_TIMEOUT_SECONDS", "1200")),
                        creationflags=flags,
                    )
                    if proc.returncode == 0:
                        ok_targets.append(target_pt)
                debug_dir = DISK_CACHE_DIR.parent / "tmp"
                try:
                    debug_dir.mkdir(parents=True, exist_ok=True)
                    (debug_dir / "force_refresh_last.log").write_text(
                        f"targets={targets} ok={ok_targets}\nreturncode={proc.returncode if proc else 'n/a'}\n"
                        f"--- stdout ---\n{proc.stdout if proc else ''}\n--- stderr ---\n{proc.stderr if proc else ''}",
                        encoding="utf-8",
                    )
                except Exception:
                    pass
                # 只要请求的分区成功就入缓存返回; 追加的新分区失败不影响主流程
                if selected in ok_targets:
                    for target_pt in ok_targets:
                        t_off = offset if target_pt == selected else 0
                        t_key = f"{target_pt}|{t_off}"
                        snapshot = serving_assemble.read_dashboard_snapshot(SERVING_DIR, target_pt, t_off)
                        if snapshot is not None:
                            # 管线快照未经读取层富化: 入缓存前补齐窗口级/记录级通过率,
                            # 否则内存缓存命中分支会返回无通过率字段的载荷
                            self._enrich_approval(snapshot, target_pt, t_off)
                            with self._lock:
                                self._cache[t_key] = (time.time(), snapshot)
                                self._save_disk_cache(t_key, snapshot)
                    return
            except Exception:
                pass  # 子进程链路失败 → 回退到进程内重算
        try:
            with self._lock:
                runner = WarehouseAttributionRunner(
                    config=self.config,
                    table=self.table_name,
                    partition=selected,
                    offset=offset,
                    query_rows=self._run_sql_rows,
                )
                result = runner.run()
                result["meta"]["cache_hit"] = False
                result["meta"]["async_refresh"] = False
                # 与同步计算路径保持一致: 重算结果入缓存前先富化通过率
                self._enrich_approval(result, selected, offset)
                self._cache[cache_key] = (time.time(), result)
                self._save_disk_cache(cache_key, result)
        except Exception:
            # 后台重算失败保留旧缓存, 前端轮询超时后自然停止
            pass

    def path_trend(self, record_id: str, partition: str | None = None, offset: int = 0) -> dict[str, Any]:
        """Load only the selected server-side alert path's 15-day daily series."""
        if not SAFE_RECORD_ID.fullmatch(record_id):
            raise AttributionServiceError("预警路径标识格式不合法。")

        dashboard = self.dashboard(partition=partition, offset=offset)
        selected_partition = dashboard["meta"]["partition"]
        record = next((item for item in dashboard["merged_alerts"] if item["id"] == record_id), None)
        if record is None:
            raise AttributionServiceError("未在当前合并预警结果中找到该路径，请刷新归因结果后重试。")

        cache_key = f"{selected_partition}|{offset}|{record_id}"
        cached = self._path_trend_cache.get(cache_key)
        if cached and time.time() - cached[0] < CACHE_SECONDS:
            return copy.deepcopy(cached[1])

        result = self._read_duckdb_path_trend(record, selected_partition, offset)
        if result is not None:
            self._path_trend_cache[cache_key] = (time.time(), result)
            return copy.deepcopy(result)

        if serving_assemble is not None:
            frame = serving_assemble.read_path_daily_frame(SERVING_DIR, selected_partition, offset)
            if frame is not None:
                result = self._format_precomputed_path_trend(
                    record, frame.to_dict(orient="records")
                )
                if result is not None:
                    self._path_trend_cache[cache_key] = (time.time(), result)
                    return copy.deepcopy(result)

        raise AttributionServiceError(
            f"pt={selected_partition} 尚无该路径的预计算趋势数据，请先刷新归因结果。"
        )

        # 优先读预计算路径日序列(serving 快照), 点击响应 <100ms
        if serving_assemble is not None:
            frame = serving_assemble.read_path_daily_frame(SERVING_DIR, selected_partition, offset)
            series, approval_series, cid_series, approval_cid_series = serving_assemble.path_series_for_alert(frame, record_id)
            if series is not None:
                runner = WarehouseAttributionRunner(
                    config=self.config,
                    table=self.table_name,
                    partition=selected_partition,
                    offset=offset,
                    query_rows=self._run_sql_rows,
                )
                # 趋势上下文从快照自身日期范围构建(重算后覆盖近 trend_days 天;
                # 旧快照仅 15 天时自动降级展示实际天数)
                context = serving_assemble.build_trend_context(frame)
                result = runner.format_path_trend(
                    record, context, series, approval_series, cid_series, approval_cid_series
                )
                self._path_trend_cache[cache_key] = (time.time(), result)
                return copy.deepcopy(result)

        runner = WarehouseAttributionRunner(
            config=self.config,
            table=self.table_name,
            partition=selected_partition,
            offset=offset,
            query_rows=self._run_sql_rows,
        )
        result = runner.path_trend(record)
        self._path_trend_cache[cache_key] = (time.time(), result)
        return copy.deepcopy(result)


load_local_env()
CACHE_SECONDS = int(os.getenv("ATTRIBUTION_CACHE_SECONDS", "900"))
service = AttributionService()
app = FastAPI(title="Risk BI · Credit Attribution API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])


class RuleStatusUpdate(BaseModel):
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
# 除登录外，全部接口均需 Authorization: Bearer <token>；
# 归因数据要求当前账号具备 attribution 页面权限。


def handle_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AttributionServiceError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, RuntimeError) and "无可用数据" in str(exc):
        return HTTPException(status_code=503, detail=str(exc))
    # Avoid leaking SQL text, endpoint details, or credentials to the browser.
    return HTTPException(status_code=502, detail="MaxCompute 数据读取失败，请检查服务端连接与表权限。")


@app.get("/api/credit-attribution/health")
def health(_user: dict = Depends(require_perm("attribution"))) -> dict[str, Any]:
    try:
        connection = get_connection()
        return {
            "status": "configured",
            "project": connection.project,
            "table": service.table_name,
            "credential_source": "environment" if os.getenv("MAXCOMPUTE_ACCESS_KEY_ID") else "notebook",
        }
    except AttributionServiceError as exc:
        return {"status": "not_configured", "detail": str(exc)}


@app.get("/api/credit-attribution/partitions")
def partitions(force: bool = False, _user: dict = Depends(require_perm("attribution"))) -> JSONResponse:
    try:
        return JSONResponse(
            content={
                "partitions": service.refresh_partitions() if force else service.available_partitions(),
                "ranges": service.partition_ranges(),
            }
        )
    except Exception as exc:
        raise handle_error(exc) from exc


@app.get("/api/credit-attribution/dashboard")
def dashboard(
    pt: str | None = Query(default=None, max_length=64),
    force: bool = Query(default=False),
    offset: int = Query(default=0, ge=0, le=180),
    _user: dict = Depends(require_perm("attribution")),
) -> JSONResponse:
    try:
        payload = service.with_rule_statuses(service.dashboard(partition=pt, force=force, offset=offset))
        return JSONResponse(content=json_safe(payload))
    except Exception as exc:
        raise handle_error(exc) from exc


@app.put("/api/credit-attribution/rule-status")
def update_rule_status(
    update: RuleStatusUpdate,
    user: dict = Depends(require_perm("attribution")),
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
    except Exception as exc:
        raise handle_error(exc) from exc


@app.get("/api/credit-attribution/rule-status-history")
def rule_status_history(
    _user: dict = Depends(require_perm("attribution")),
) -> JSONResponse:
    return JSONResponse(content=json_safe({"records": service._status_store.get_history()}))


@app.get("/api/credit-attribution/path-trend")
def path_trend(
    record_id: str = Query(min_length=12, max_length=12),
    pt: str | None = Query(default=None, max_length=64),
    offset: int = Query(default=0, ge=0, le=180),
    _user: dict = Depends(require_perm("attribution")),
) -> JSONResponse:
    try:
        return JSONResponse(content=json_safe(service.path_trend(record_id=record_id, partition=pt, offset=offset)))
    except Exception as exc:
        raise handle_error(exc) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=int(os.getenv("ATTRIBUTION_API_PORT", "8010")), reload=False)
