"""API 从已发布的 DuckDB 读取结果，与管线写入库隔离。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


from pipeline.business_results import connect_results, result_prefix, snapshot_version, system_database_path


@lru_cache(maxsize=128)
def _partitions_cached(path: str, prefix: str, offset: int | None, version: str) -> tuple[str, ...]:
    conn = duckdb.connect(path, read_only=True)
    try:
        sql = f"SELECT DISTINCT pt FROM {prefix}_dashboard"
        params = []
        if offset is not None:
            sql += " WHERE offset_days = ?"
            params.append(int(offset))
        return tuple(str(row[0]) for row in conn.execute(sql + " ORDER BY pt DESC", params).fetchall())
    finally:
        conn.close()


def published_partitions(serving_dir: Path, offset: int | None = None) -> list[str]:
    try:
        version = snapshot_version(serving_dir)
        if not version:
            return []
        return list(_partitions_cached(str(system_database_path(serving_dir)), result_prefix(serving_dir), offset, version))
    except (FileNotFoundError, duckdb.Error):
        return []


def read_dashboard_snapshot(serving_dir: Path, pt: str, offset: int) -> dict[str, Any] | None:
    """直接读取已预先装配的业务看板结果，不在请求中重复计算指标。"""
    version = snapshot_version(serving_dir)
    prefix = result_prefix(serving_dir)
    try:
        conn = connect_results(serving_dir)
        try:
            row = conn.execute(
                f"""SELECT payload FROM {prefix}_dashboard
                WHERE pt = ? AND offset_days = ? ORDER BY generated_at DESC LIMIT 1""",
                [pt, int(offset)],
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        payload = json.loads(row[0])
        meta = payload.setdefault("meta", {})
        meta.update(cache_hit=True, async_refresh=False, serving=True,
                    result_store="duckdb", result_version=version)
        return payload
    except (FileNotFoundError, duckdb.Error, ValueError, TypeError):
        return None


def _path_rows(serving_dir: Path, pt: str, offset: int, alert_id: str | None = None):
    prefix = result_prefix(serving_dir)
    conn = connect_results(serving_dir)
    try:
        run = conn.execute(
            f"SELECT run_id FROM {prefix}_dashboard WHERE pt = ? AND offset_days = ? ORDER BY generated_at DESC LIMIT 1",
            [pt, int(offset)],
        ).fetchone()
        if run is None:
            return None
        counts = ("abnormal_order_count AS application_count, order_count AS total_application_count"
                  if prefix == "fund" else "application_count, total_application_count")
        sql = f"SELECT alert_id, date, {counts}, approval_count, cid_cnt, approval_cid_cnt FROM {prefix}_path_daily WHERE run_id = ?"
        params = [run[0]]
        if alert_id is not None:
            sql += " AND alert_id = ?"
            params.append(alert_id)
        result = conn.execute(sql + " ORDER BY alert_id, date", params)
        columns = [col[0] for col in result.description]
        return columns, result.fetchall()
    finally:
        conn.close()


def read_path_daily_rows(serving_dir: Path, pt: str, offset: int, alert_id: str) -> list[dict] | None:
    try:
        result = _path_rows(serving_dir, pt, offset, alert_id)
        if result is None:
            return None
        columns, rows = result
        return [dict(zip(columns, row)) for row in rows]
    except (FileNotFoundError, duckdb.Error):
        return None


def read_path_daily_frame(serving_dir: Path, pt: str, offset: int) -> pd.DataFrame | None:
    try:
        result = _path_rows(serving_dir, pt, offset)
        if result is None:
            return None
        columns, rows = result
        frame = pd.DataFrame(rows, columns=columns)
        if not frame.empty:
            frame["date"] = pd.to_datetime(frame["date"]).dt.date
        return frame
    except (FileNotFoundError, duckdb.Error):
        return None


def path_series_for_alert(
    frame: pd.DataFrame | None, alert_id: str
) -> tuple["pd.Series[Any] | None", "pd.Series[Any] | None", "pd.Series[Any] | None", "pd.Series[Any] | None"]:
    """取单个 alert 的 (申请量序列, 通过量序列);无记录返回 (None, None)。

    通过量为空 Series 表示快照缺该数据(旧格式), 由上层降级处理。
    """
    if frame is None or frame.empty:
        return None, None, None, None
    rows = frame[frame["alert_id"] == alert_id]
    if rows.empty:
        return None, None, None, None
    application = pd.Series(
        rows.set_index("date")["application_count"].astype(float).to_dict(),
        dtype=float,
    )
    approval_rows = rows[["date", "approval_count"]].dropna(subset=["approval_count"])
    approval = (
        pd.Series(
            approval_rows.set_index("date")["approval_count"].astype(float).to_dict(),
            dtype=float,
        )
        if not approval_rows.empty
        else pd.Series(dtype=float)
    )
    cid_rows = rows[["date", "cid_cnt"]].dropna(subset=["cid_cnt"])
    cid = (
        pd.Series(cid_rows.set_index("date")["cid_cnt"].astype(float).to_dict(), dtype=float)
        if not cid_rows.empty else pd.Series(dtype=float)
    )
    approval_cid_rows = rows[["date", "approval_cid_cnt"]].dropna(subset=["approval_cid_cnt"])
    approval_cid = (
        pd.Series(approval_cid_rows.set_index("date")["approval_cid_cnt"].astype(float).to_dict(), dtype=float)
        if not approval_cid_rows.empty else pd.Series(dtype=float)
    )
    return application, approval, cid, approval_cid


def build_trend_context(frame: pd.DataFrame | None, limit: int = 60) -> list[dict[str, Any]]:
    """从 path_daily 快照构建路径趋势日上下文 [{date, application_count}]。

    - application_count 为当日整体申请量(快照各行 total 列相同, 取首个非空值)
    - 按日期升序返回最后 limit 天; 旧快照仅覆盖 15 天时自动降级,
      前端 period_days 动态显示实际天数, 重算后自然扩展到 trend_days
    """
    if frame is None or frame.empty:
        return []
    grouped = frame.groupby("date")["total_application_count"].max().dropna().sort_index()
    if grouped.empty:
        return []
    return [
        {"date": day.isoformat(), "application_count": float(count)}
        for day, count in list(grouped.items())[-int(limit):]
    ]


def enrich_approval_rates(dashboard: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
    """用 path_daily 快照给 alert 记录补窗口级通过量/通过率(读取层富化, 幂等)。

    - 每个窗口: approval_count = 观察期逐日通过量之和;
      approval_rate_pct = approval_count / observation_count * 100
    - 记录级 approval_rate_pct = 主窗口观察期通过率
    - 快照缺失 / 旧格式(无 approval_count 列) / 记录不在快照中 → 字段为 None(前端显示 —)
    """
    if not isinstance(dashboard, dict):
        return dashboard
    series_map: dict[str, pd.Series[Any]] = {}
    cid_series_map: dict[str, pd.Series[Any]] = {}
    if frame is not None and not frame.empty and "approval_count" in frame.columns:
        approval_rows = frame[["alert_id", "date", "approval_count"]].dropna(subset=["approval_count"])
        for alert_id, group in approval_rows.groupby("alert_id"):
            series_map[str(alert_id)] = pd.Series(
                group.set_index("date")["approval_count"].astype(float).to_dict(), dtype=float
            )
    if frame is not None and not frame.empty and "cid_cnt" in frame.columns:
        cid_rows = frame[["alert_id", "date", "cid_cnt"]].dropna(subset=["cid_cnt"])
        for alert_id, group in cid_rows.groupby("alert_id"):
            cid_series_map[str(alert_id)] = pd.Series(
                group.set_index("date")["cid_cnt"].astype(float).to_dict(), dtype=float
            )
    approval_cid_series_map: dict[str, pd.Series[Any]] = {}
    if frame is not None and not frame.empty and "approval_cid_cnt" in frame.columns:
        approval_cid_rows = frame[["alert_id", "date", "approval_cid_cnt"]].dropna(subset=["approval_cid_cnt"])
        for alert_id, group in approval_cid_rows.groupby("alert_id"):
            approval_cid_series_map[str(alert_id)] = pd.Series(
                group.set_index("date")["approval_cid_cnt"].astype(float).to_dict(), dtype=float
            )

    def _window_sum(series: pd.Series[Any] | None, metric: dict[str, Any]) -> float | None:
        start, end = metric.get("observation_start"), metric.get("observation_end")
        if not start or not end:
            return None
        try:
            start_day = pd.to_datetime(start).date()
            end_day = pd.to_datetime(end).date()
        except Exception:
            return None
        if series is None:
            return None
        normalized = series.copy()
        normalized.index = pd.to_datetime(normalized.index).date
        selected = normalized[(normalized.index >= start_day) & (normalized.index <= end_day)]
        return float(selected.sum())

    for list_key in ("merged_alerts", "suppressed_alerts"):
        for record in dashboard.get(list_key) or []:
            if not isinstance(record, dict):
                continue
            series = series_map.get(str(record.get("id")))
            has_approval = series is not None and not series.empty
            cid_series = cid_series_map.get(str(record.get("id")))
            approval_cid_series = approval_cid_series_map.get(str(record.get("id")))
            has_cid = cid_series is not None and approval_cid_series is not None and not cid_series.empty
            primary_rate: float | None = None
            primary_cid_rate: float | None = None
            for window in (record.get("windows") or {}).values():
                if not isinstance(window, dict):
                    continue
                if has_approval:
                    approval = _window_sum(series, window)
                    observation = float(window.get("observation_count") or 0)
                    rate = approval / observation * 100 if approval is not None and observation > 0 else None
                    window["approval_count"] = approval
                    window["approval_rate_pct"] = rate
                else:
                    window["approval_count"] = None
                    window["approval_rate_pct"] = None
                if has_cid:
                    cid_count = _window_sum(cid_series, window)
                    approval_cid_count = _window_sum(approval_cid_series, window)
                    cid_rate = (
                        approval_cid_count / cid_count * 100
                        if cid_count is not None and approval_cid_count is not None and cid_count > 0
                        else None
                    )
                    window["cid_cnt"] = cid_count
                    window["approval_cid_cnt"] = approval_cid_count
                    window["cid_approval_rate_pct"] = cid_rate
                else:
                    window["cid_cnt"] = None
                    window["approval_cid_cnt"] = None
                    window["cid_approval_rate_pct"] = None
                if window.get("key") == record.get("primary_window"):
                    primary_rate = window.get("approval_rate_pct")
                    primary_cid_rate = window.get("cid_approval_rate_pct")
            record["approval_rate_pct"] = primary_rate
            record["cid_approval_rate_pct"] = primary_cid_rate
    return dashboard


@lru_cache(maxsize=64)
def _ranges_cached(path: str, prefix: str, version: str) -> tuple:
    conn = duckdb.connect(path, read_only=True)
    try:
        return tuple(conn.execute(f"""SELECT pt, MIN(table_date_min), MAX(table_date_max)
            FROM {prefix}_dashboard GROUP BY pt""").fetchall())
    finally:
        conn.close()


def read_partition_ranges(serving_dir: Path) -> dict[str, dict[str, str]] | None:
    try:
        version = snapshot_version(serving_dir)
        if not version:
            return None
        rows = _ranges_cached(str(system_database_path(serving_dir)), result_prefix(serving_dir), version)
        return {str(pt): {"min": str(lo), "max": str(hi)} for pt, lo, hi in rows if lo and hi} or None
    except (FileNotFoundError, duckdb.Error):
        return None


def snapshot_exists(serving_dir: Path, pt: str, offset: int) -> bool:
    return str(pt) in published_partitions(serving_dir, offset)
