"""资金归结存储适配层。

底层表结构复用授信归因的批次/快照 schema，但数据库文件完全分离；
适配器把资金字段映射到通用存储字段，原始资金 payload 仍完整保留在快照中。
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from pipeline import store as _store

from . import DB_PATH, SERVING_DIR

connect = _store.connect
config_fingerprint = _store.config_fingerprint
make_run_id = _store.make_run_id
upsert_partition_range = _store.upsert_partition_range


def _storage_result(result: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(result)
    for alert in payload.get("merged_alerts", []):
        primary = (alert.get("windows") or {}).get(alert.get("primary_window"), {})
        alert.setdefault("observation_count", primary.get("observation_abnormal_count", 0))
        alert.setdefault("excess_count", primary.get("excess_abnormal_count", 0))
        for metric in (alert.get("windows") or {}).values():
            metric.setdefault("baseline_count", metric.get("baseline_abnormal_count", 0))
            metric.setdefault("observation_count", metric.get("observation_abnormal_count", 0))
            metric.setdefault("baseline_daily", metric.get("baseline_abnormal_daily", 0))
            metric.setdefault("observation_daily", metric.get("observation_abnormal_daily", 0))
            metric.setdefault("baseline_share", 0)
            metric.setdefault("observation_share", 0)
            metric.setdefault("structure_change", 0)
            metric.setdefault("expected_count", metric.get("expected_abnormal_count", 0))
            metric.setdefault("excess_count", metric.get("excess_abnormal_count", 0))
    payload["daily_trend"] = [
        {
            **row,
            "application_count": row.get("order_count", 0),
            "approval_count": row.get("abnormal_order_count", 0),
        }
        for row in payload.get("daily_trend", [])
    ]
    return payload


def persist_result(
    conn: Any,
    *,
    result: dict[str, Any],
    path_rows: list[dict[str, Any]],
    pt: str,
    offset: int,
    config: dict[str, Any],
    duration_ms: int,
    source: str,
) -> str:
    storage_payload = _storage_result(result)
    storage_rows = [
        {
            **row,
            "application_count": row.get("abnormal_order_count", 0),
            "total_application_count": row.get("order_count", 0),
        }
        for row in path_rows
    ]
    return _store.persist_result(
        conn,
        result=storage_payload,
        path_rows=storage_rows,
        pt=pt,
        offset=offset,
        config=config,
        duration_ms=duration_ms,
        source=source,
    )


def open_database(path: Path | None = None) -> Any:
    return connect(Path(path or DB_PATH))
