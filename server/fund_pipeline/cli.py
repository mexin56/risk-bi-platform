"""资金归结预计算与发布入口。"""

from __future__ import annotations

import copy
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

SERVER_DIR = Path(__file__).resolve().parent.parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from fund_attribution import FundAttributionRunner  # noqa: E402
from pipeline import exporter  # noqa: E402

from . import DB_PATH, SERVING_DIR  # noqa: E402
from . import storage  # noqa: E402


def _day_text(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _fund_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    groups = [
        result.get("merged_alerts", []),
        result.get("top_k", {}).get("single_downstream", []),
        result.get("top_k", {}).get("pair_downstream", []),
        result.get("top_k", {}).get("third_alerts", []),
        result.get("expert", {}).get("single", []),
        result.get("expert", {}).get("pair", []),
        result.get("expert", {}).get("third", []),
        result.get("review_items", []),
    ]
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    for group in groups:
        for record in group:
            key = str(record.get("id") or record.get("canonical_path"))
            if key in seen:
                continue
            seen.add(key)
            records.append(record)
    return records


def build_fund_path_rows(runner: FundAttributionRunner, result: dict[str, Any]) -> list[dict[str, Any]]:
    """一次批量计算所有页面可下钻路径的每日异常量与订单量。"""
    records = _fund_records(result)
    conditions = [{"key": record["id"], "conditions": record.get("conditions", [])} for record in records]
    series_map = runner.path_daily_batch(conditions)
    totals = {
        str(row["date"]): float(row.get("order_count", 0) or 0)
        for row in result.get("daily_trend", [])
    }
    days = sorted(totals)
    rows: list[dict[str, Any]] = []
    for record in records:
        abnormal, orders = series_map.get(record["id"], (pd.Series(dtype=float), pd.Series(dtype=float)))
        for day in days:
            rows.append(
                {
                    "alert_id": record["id"],
                    "date": day,
                    "abnormal_order_count": float(abnormal.get(day, 0) or 0),
                    "order_count": float(orders.get(day, 0) or 0),
                    "total_order_count": totals[day],
                }
            )
    return rows


def publish_fund_result(
    *,
    db_path: Path = DB_PATH,
    serving_dir: Path = SERVING_DIR,
    result: dict[str, Any],
    path_rows: list[dict[str, Any]],
    pt: str,
    offset: int,
    config: dict[str, Any],
    duration_ms: int,
    source: str,
) -> str:
    conn = storage.open_database(db_path)
    try:
        run_id = storage.persist_result(
            conn,
            result=result,
            path_rows=path_rows,
            pt=pt,
            offset=offset,
            config=config,
            duration_ms=duration_ms,
            source=source,
        )
        meta = result.get("meta", {})
        storage.upsert_partition_range(
            conn,
            pt,
            meta.get("table_date_min") or meta.get("date_start"),
            meta.get("table_date_max") or meta.get("date_end"),
        )
    finally:
        conn.close()
    exporter.export_snapshot(db_path, serving_dir, run_id=run_id, pt=pt, offset=offset)
    return run_id


def compute_and_publish(
    *,
    config: dict[str, Any],
    table: str,
    partition: str,
    offset: int,
    query_rows,
    source: str = "fund_pipeline",
    db_path: Path = DB_PATH,
    serving_dir: Path = SERVING_DIR,
) -> dict[str, Any]:
    started = time.time()
    runner = FundAttributionRunner(
        config=config,
        table=table,
        partition=partition,
        offset=offset,
        query_rows=query_rows,
    )
    result = copy.deepcopy(runner.run())
    path_rows = build_fund_path_rows(runner, result)
    run_id = publish_fund_result(
        db_path=db_path,
        serving_dir=serving_dir,
        result=result,
        path_rows=path_rows,
        pt=partition,
        offset=offset,
        config=config,
        duration_ms=int((time.time() - started) * 1000),
        source=source,
    )
    return {
        "run_id": run_id,
        "pt": partition,
        "offset": offset,
        "alerts": len(result.get("merged_alerts", [])),
        "path_days": len(path_rows),
        "source": source,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fund_pipeline.cli", description="fund attribution precompute pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="compute + publish fund attribution")
    run.add_argument("--pt", default=None, help="target pt; default latest")
    run.add_argument("--offset", type=int, default=0)
    run.add_argument("--backfill", type=int, default=0, metavar="N")
    run.add_argument("--source", default="fund_pipeline")
    status = sub.add_parser("status", help="show fund pipeline runs")
    status.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)

    from fund_service import FundAttributionService, _run_sql_rows

    if args.command == "run":
        service = FundAttributionService()
        partitions = service.available_partitions()
        if not partitions:
            print("[error] no available fund pt partition", file=sys.stderr)
            return 2
        if args.backfill:
            targets = [(pt, 0) for pt in partitions[: max(1, args.backfill)]]
        else:
            pt = args.pt or partitions[0]
            if pt not in partitions:
                print(f"[error] pt={pt} not in available partitions", file=sys.stderr)
                return 2
            targets = [(pt, max(0, args.offset))]
        failed = 0
        for pt, offset in targets:
            try:
                stats = compute_and_publish(
                    config=service.config,
                    table=service.table_name,
                    partition=pt,
                    offset=offset,
                    query_rows=_run_sql_rows,
                    source=args.source,
                )
                print(json.dumps(stats, ensure_ascii=False))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"[error] pt={pt} offset={offset}: {exc}", file=sys.stderr)
        return 1 if failed else 0

    if args.command == "status":
        if not DB_PATH.exists():
            print("db: missing")
            return 1
        conn = storage.open_database()
        try:
            rows = conn.execute(
                "SELECT run_id, pt, offset_days, generated_at, source, duration_ms FROM attr_runs ORDER BY generated_at DESC LIMIT ?",
                [args.limit],
            ).fetchall()
        finally:
            conn.close()
        print(f"db: {DB_PATH}")
        for row in rows:
            print(f"  {row[0]} src={row[4]} dur={row[5]}ms at={row[3]}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
