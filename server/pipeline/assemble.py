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
        frame = _query_parquet(
            f"SELECT alert_id, date, application_count, total_application_count FROM read_parquet('{escaped}')"
        )
    except Exception:
        return None
    if frame.empty:
        return frame  # 空 frame 也是合法结果(该快照无路径数据)
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    return frame


def path_series_for_alert(frame: pd.DataFrame | None, alert_id: str) -> "pd.Series[Any]" | None:
    """从路径日序列 frame 中取单个 alert 的 Series(date 索引);无记录返回 None。"""
    if frame is None or frame.empty:
        return None
    rows = frame[frame["alert_id"] == alert_id]
    if rows.empty:
        return None
    return pd.Series(
        rows.set_index("date")["application_count"].astype(float).to_dict(),
        dtype=float,
    )


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
