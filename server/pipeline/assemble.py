"""serving 快照读取与响应装配(API 进程唯一使用的模块)。

只读 parquet(duckdb 内存模式),不触碰 attribution.duckdb,
与 pipeline 写进程零锁冲突。所有函数均为纯读取 + 纯计算。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


def _query_parquet(sql: str) -> pd.DataFrame:
    """duckdb 内存模式直查;连接用完即弃。"""
    conn = duckdb.connect(":memory:")
    try:
        return conn.execute(sql).df()
    finally:
        conn.close()


def read_dashboard_snapshot(serving_dir: Path, pt: str, offset: int) -> dict[str, Any] | None:
    """返回该 (pt, offset) 的完整 dashboard 载荷;不存在返回 None。"""
    path = Path(serving_dir) / f"dashboard_{pt}_{int(offset)}.parquet"
    if not path.exists():
        return None
    escaped = str(path).replace("'", "''")
    try:
        frame = _query_parquet(f"SELECT payload FROM read_parquet('{escaped}')")
    except Exception:
        return None
    if frame.empty:
        return None
    try:
        payload = json.loads(frame.iloc[0]["payload"])
        meta = payload.setdefault("meta", {})
        meta["cache_hit"] = True
        meta["async_refresh"] = False
        meta["serving"] = True
        return payload
    except Exception:
        return None


def read_path_daily_frame(serving_dir: Path, pt: str, offset: int) -> pd.DataFrame | None:
    path = Path(serving_dir) / f"path_daily_{pt}_{int(offset)}.parquet"
    if not path.exists():
        return None
    escaped = str(path).replace("'", "''")
    try:
        frame = _query_parquet(f"SELECT * FROM read_parquet('{escaped}')")
    except Exception:
        return None
    if frame.empty:
        return frame  # 空 frame 也是合法结果(该快照无路径数据)
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    if "approval_count" not in frame.columns:
        # 旧快照无通过量列, 降级为缺失
        frame["approval_count"] = pd.NA
    if "cid_cnt" not in frame.columns:
        frame["cid_cnt"] = pd.NA
    if "approval_cid_cnt" not in frame.columns:
        frame["approval_cid_cnt"] = pd.NA
    return frame


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


def read_partition_ranges(serving_dir: Path) -> dict[str, dict[str, str]] | None:
    """dim_partitions 快照:{pt: {min, max}};文件缺失或损坏返回 None。"""
    path = Path(serving_dir) / "partitions.parquet"
    if not path.exists():
        return None
    escaped = str(path).replace("'", "''")
    try:
        frame = _query_parquet(f"SELECT pt, min_day, max_day FROM read_parquet('{escaped}')")
    except Exception:
        return None
    ranges: dict[str, dict[str, str]] = {}
    for row in frame.itertuples(index=False):
        if row.min_day and row.max_day:
            ranges[str(row.pt)] = {"min": str(row.min_day), "max": str(row.max_day)}
    return ranges or None


def snapshot_exists(serving_dir: Path, pt: str, offset: int) -> bool:
    return (Path(serving_dir) / f"dashboard_{pt}_{int(offset)}.parquet").exists()
