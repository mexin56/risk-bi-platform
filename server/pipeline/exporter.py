"""将管线计算结果发布为原子替换的 DuckDB 只读查询快照。"""

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
    """确认完整批次后发布 DuckDB；成功返回后下游可直接查询。"""
    from pipeline.duckdb_serving import publish_database

    target = publish_database(db_path, serving_dir, run_id=run_id)
    from pipeline.business_results import publish_system_database
    business_target = publish_system_database(Path(serving_dir))
    return update_meta_index(
        Path(serving_dir),
        entry={
            "pt": pt,
            "offset": int(offset),
            "run_id": run_id,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "duckdb_file": target.name,
            "business_database": str(business_target),
        },
    )


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
