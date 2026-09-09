"""资金 serving 快照读取：复用只读 parquet 装配，但返回资金字段名。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from pipeline import assemble as _assemble


def read_dashboard_snapshot(serving_dir: Path, pt: str, offset: int):
    return _assemble.read_dashboard_snapshot(serving_dir, pt, offset)


def read_path_daily_frame(serving_dir: Path, pt: str, offset: int) -> pd.DataFrame | None:
    frame = _assemble.read_path_daily_frame(serving_dir, pt, offset)
    if frame is None:
        return None
    return frame.rename(
        columns={
            "application_count": "abnormal_order_count",
            "total_application_count": "order_count",
        }
    )


def read_partition_ranges(serving_dir: Path):
    return _assemble.read_partition_ranges(serving_dir)


def snapshot_exists(serving_dir: Path, pt: str, offset: int) -> bool:
    return _assemble.snapshot_exists(serving_dir, pt, offset)
