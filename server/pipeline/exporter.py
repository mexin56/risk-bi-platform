"""serving 快照导出:DuckDB 结果 → API 只读的 parquet 文件层。

为什么中间要有一层 parquet:DuckDB 同一文件不允许跨进程"一写一读"。
API 用 duckdb 内存模式直查这些 parquet,零文件锁冲突;每个文件整体
写入 .tmp 后 os.replace 原子替换,任何时刻 API 读到的都是完整快照。

单文件量级 ~1MB,pandas/pyarrow 中转足够快(<100ms),不做花哨优化。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


def snapshot_paths(serving_dir: Path, pt: str, offset: int) -> dict[str, Path]:
    base = f"{pt}_{int(offset)}"
    return {
        "dashboard": serving_dir / f"dashboard_{base}.parquet",
        "path_daily": serving_dir / f"path_daily_{base}.parquet",
    }


def _write_parquet_atomic(frame: pd.DataFrame, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".parquet.tmp")
    frame.to_parquet(tmp, index=False, compression="zstd")
    os.replace(tmp, target)


def export_snapshot(
    db_path: Path,
    serving_dir: Path,
    *,
    run_id: str,
    pt: str,
    offset: int,
) -> dict[str, Any]:
    """从 DuckDB 读取刚写入的 run,导出该 (pt, offset) 的完整 serving 快照。"""
    serving_dir = Path(serving_dir)
    serving_dir.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect(str(Path(db_path)), read_only=True)
    try:
        payload_row = conn.execute(
            "SELECT payload FROM attr_payloads WHERE run_id = ?", [run_id]
        ).fetchone()
        if payload_row is None:
            raise RuntimeError(f"run_id={run_id} 在 DuckDB 中不存在,无法导出快照")

        dashboard_frame = pd.DataFrame(
            [
                {
                    "pt": pt,
                    "offset_days": int(offset),
                    "run_id": run_id,
                    "exported_at": datetime.now(timezone.utc),
                    "payload": payload_row[0],
                }
            ]
        )
        path_frame = conn.execute(
            """
            SELECT alert_id, date, application_count, total_application_count
            FROM attr_path_daily WHERE run_id = ?
            ORDER BY alert_id, date
            """,
            [run_id],
        ).df()
        partitions_frame = conn.execute(
            "SELECT pt, min_day, max_day, refreshed_at FROM dim_partitions ORDER BY pt DESC"
        ).df()
    finally:
        conn.close()

    paths = snapshot_paths(serving_dir, pt, offset)
    _write_parquet_atomic(dashboard_frame, paths["dashboard"])
    _write_parquet_atomic(path_frame, paths["path_daily"])
    _write_parquet_atomic(partitions_frame, serving_dir / "partitions.parquet")

    info = update_meta_index(
        serving_dir,
        entry={
            "pt": pt,
            "offset": int(offset),
            "run_id": run_id,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "dashboard_file": paths["dashboard"].name,
            "path_daily_file": paths["path_daily"].name,
        },
    )
    return info


def update_meta_index(serving_dir: Path, *, entry: dict[str, Any]) -> dict[str, Any]:
    """meta.json 指针:记录全部已发布快照;最后写,代表发布完成。"""
    serving_dir = Path(serving_dir)
    meta_path = serving_dir / "meta.json"
    index: dict[str, Any] = {"snapshots": []}
    if meta_path.exists():
        try:
            index = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            index = {"snapshots": []}
    snapshots = [
        item
        for item in index.get("snapshots", [])
        if not (item.get("pt") == entry["pt"] and item.get("offset") == entry["offset"])
    ]
    snapshots.insert(0, entry)
    index["snapshots"] = snapshots[:200]
    index["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = meta_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, meta_path)
    return index
