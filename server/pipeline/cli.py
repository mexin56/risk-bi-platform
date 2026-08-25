"""预计算管线 CLI(P1 手动/兜底入口,P2 由 Dagster 以同一入口调度)。

用法(server/ 目录下执行):

    python -m pipeline.cli run --pt 20260822           # 计算+发布单个分区
    python -m pipeline.cli run                         # 自动取最新分区
    python -m pipeline.cli run --backfill 5            # 回填最近 5 个分区
    python -m pipeline.cli ingest --input result.json  # 在线兜底结果写回发布

流程:MaxCompute 聚合(复用 WarehouseAttributionRunner,算法零改动)
      → 全部预警路径日序列批量预计算(一次扫描)
      → 分区范围一次扫描刷新
      → DuckDB 事务写入 → serving parquet 快照发布(meta.json 指针收尾)。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

SERVER_DIR = Path(__file__).resolve().parent.parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app import AttributionService, json_safe, load_config, load_local_env  # noqa: E402
from pipeline import DB_PATH, SERVING_DIR  # noqa: E402
from pipeline import exporter, store  # noqa: E402
from warehouse import WarehouseAttributionRunner  # noqa: E402


def _day_text(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def build_path_rows(
    runner: WarehouseAttributionRunner,
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    """全部预警路径(+免归因路径)的日序列与通过量,批量条件聚合扫完。

    覆盖范围 = 趋势扩展窗口(trend_days, 默认60天), 与预警观察窗口解耦;
    总量列为同期整体每日申请量(供前端占比线)。
    """
    alerts = [*result.get("merged_alerts", []), *result.get("suppressed_alerts", [])]
    condition_sets = [
        {"key": alert["id"], "conditions": alert["conditions"]} for alert in alerts
    ]
    series_map = runner.paths_exact_daily_batch(condition_sets)
    totals_series = runner.trend_daily_totals()
    totals = {
        _day_text(day): float(count or 0)
        for day, count in totals_series.items()
    }
    rows: list[dict[str, Any]] = []
    for alert_id, (series, approval_series) in series_map.items():
        for day, count in series.items():
            day_text = _day_text(day)
            approval = float(approval_series.get(day, 0.0)) if len(approval_series) else None
            rows.append(
                {
                    "alert_id": alert_id,
                    "date": day_text,
                    "application_count": float(count or 0),
                    "total_application_count": float(totals.get(day_text, 0.0) or 0),
                    "approval_count": approval,
                }
            )
    return rows


def refresh_partition_ranges(service: AttributionService, config: dict[str, Any]) -> dict[str, dict[str, str]]:
    """各分区 create_date MIN/MAX。

    注意:该表禁止全分区扫描(GROUP BY pt 会报 ODPS-0130071),只能逐分区
    带谓词查询;离线管线里串行可接受(每日一次,不占用在线链路)。
    """
    date_field = config["date_field"]
    ranges: dict[str, dict[str, str]] = {}
    for pt in service.available_partitions():
        try:
            sql = f"""
                SELECT MIN(TO_CHAR({date_field}, 'yyyy-MM-dd')) AS min_day,
                       MAX(TO_CHAR({date_field}, 'yyyy-MM-dd')) AS max_day
                FROM {service.table_name}
                WHERE pt = '{pt}'
            """
            rows = service._run_sql_rows(sql)
            if rows and rows[0].get("min_day"):
                ranges[str(pt)] = {"min": str(rows[0]["min_day"]), "max": str(rows[0]["max_day"])}
        except Exception as exc:
            print(f"[warn] partition range failed pt={pt}: {exc}", file=sys.stderr)
    return ranges


def publish_result(
    *,
    result: dict[str, Any],
    path_rows: list[dict[str, Any]],
    partition_ranges: dict[str, dict[str, str]],
    config: dict[str, Any],
    pt: str,
    offset: int,
    duration_ms: int,
    source: str,
) -> str:
    conn = store.connect(DB_PATH)
    try:
        run_id = store.persist_result(
            conn,
            result=result,
            path_rows=path_rows,
            pt=pt,
            offset=offset,
            config=config,
            duration_ms=duration_ms,
            source=source,
        )
        for range_pt, values in partition_ranges.items():
            store.upsert_partition_range(conn, range_pt, values.get("min"), values.get("max"))
    finally:
        conn.close()
    exporter.export_snapshot(DB_PATH, SERVING_DIR, run_id=run_id, pt=pt, offset=offset)
    return run_id


def compute_and_publish(
    service: AttributionService,
    config: dict[str, Any],
    pt: str,
    offset: int,
    source: str,
) -> dict[str, Any]:
    started = time.time()
    runner = WarehouseAttributionRunner(
        config=config,
        table=service.table_name,
        partition=pt,
        offset=offset,
        query_rows=service._run_sql_rows,
    )
    result = json_safe(runner.run())
    compute_seconds = time.time() - started

    path_rows_started = time.time()
    path_rows = build_path_rows(runner, result)
    path_seconds = time.time() - path_rows_started

    try:
        ranges = refresh_partition_ranges(service, config)
    except Exception as exc:  # 分区范围失败不阻塞主结果发布
        print(f"[warn] partition ranges refresh failed: {exc}", file=sys.stderr)
        ranges = {}

    publish_started = time.time()
    run_id = publish_result(
        result=result,
        path_rows=path_rows,
        partition_ranges=ranges,
        config=config,
        pt=pt,
        offset=offset,
        duration_ms=int(compute_seconds * 1000),
        source=source,
    )

    return {
        "run_id": run_id,
        "pt": pt,
        "offset": offset,
        "compute_s": round(compute_seconds, 1),
        "path_trend_s": round(path_seconds, 1),
        "publish_s": round(time.time() - publish_started, 1),
        "alerts": len(result.get("merged_alerts", [])),
        "suppressed": len(result.get("suppressed_alerts", [])),
        "path_days": len(path_rows),
        "source": source,
    }


def cmd_run(args: argparse.Namespace) -> int:
    load_local_env()
    service = AttributionService()
    config = load_config()

    partitions = service.available_partitions()
    if not partitions:
        print("[error] no available pt partition", file=sys.stderr)
        return 2

    targets: list[tuple[str, int]]
    if args.backfill:
        count = max(1, args.backfill)
        targets = [(pt, 0) for pt in partitions[:count]]
    else:
        pt = args.pt or partitions[0]
        if pt not in partitions:
            print(f"[error] pt={pt} not in available partitions", file=sys.stderr)
            return 2
        targets = [(pt, int(args.offset))]

    failed = 0
    for index, (pt, offset) in enumerate(targets, start=1):
        tag = f"[{index}/{len(targets)}]"
        try:
            stats = compute_and_publish(service, config, pt, offset, source=args.source or ("backfill" if args.backfill else "dagster"))
            print(
                f"{tag} OK pt={stats['pt']} offset={stats['offset']} "
                f"compute={stats['compute_s']}s path_trend={stats['path_trend_s']}s "
                f"publish={stats['publish_s']}s alerts={stats['alerts']} "
                f"suppressed={stats['suppressed']} path_days={stats['path_days']}"
            )
        except Exception as exc:
            failed += 1
            print(f"{tag} FAIL pt={pt} offset={offset}: {exc}", file=sys.stderr)
    return 1 if failed else 0


def cmd_ingest(args: argparse.Namespace) -> int:
    """把在线兜底算出的完整结果写回 DuckDB + 快照(懒物化 / 兜底写回)。"""
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = payload["result"]
    pt = str(payload["pt"])
    offset = int(payload.get("offset", 0))
    config = load_config()
    conn = store.connect(DB_PATH)
    try:
        run_id = store.persist_result(
            conn,
            result=result,
            path_rows=payload.get("path_rows", []),
            pt=pt,
            offset=offset,
            config=config,
            duration_ms=int(payload.get("duration_ms") or 0),
            source=str(payload.get("source") or "fallback_online"),
        )
        for range_pt, values in (payload.get("partition_ranges") or {}).items():
            store.upsert_partition_range(conn, range_pt, values.get("min"), values.get("max"))
    finally:
        conn.close()
    exporter.export_snapshot(DB_PATH, SERVING_DIR, run_id=run_id, pt=pt, offset=offset)
    print(f"OK run_id={run_id}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    if not DB_PATH.exists():
        print("db: missing")
        return 1
    conn = store.connect(DB_PATH)
    try:
        runs = conn.execute(
            "SELECT run_id, pt, offset_days, generated_at, source, duration_ms FROM attr_runs ORDER BY generated_at DESC LIMIT ?",
            [args.limit],
        ).fetchall()
    finally:
        conn.close()
    print(f"db: {DB_PATH}")
    snapshots = sorted(SERVING_DIR.glob("dashboard_*.parquet")) if SERVING_DIR.exists() else []
    print(f"serving snapshots: {len(snapshots)}")
    for row in runs:
        print(f"  {row[0]}  src={row[4]}  dur={row[5]}ms  at={row[3]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline.cli", description="attribution precompute pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="compute + publish attribution for partition(s)")
    run_parser.add_argument("--pt", default=None, help="target partition; default = latest")
    run_parser.add_argument("--offset", type=int, default=0)
    run_parser.add_argument("--backfill", type=int, default=0, metavar="N", help="backfill latest N partitions")
    run_parser.add_argument("--source", default=None, help="run source tag (default dagster/backfill)")
    run_parser.set_defaults(func=cmd_run)

    ingest_parser = sub.add_parser("ingest", help="persist an externally computed result payload")
    ingest_parser.add_argument("--input", required=True)
    ingest_parser.set_defaults(func=cmd_ingest)

    status_parser = sub.add_parser("status", help="show recent runs and snapshots")
    status_parser.add_argument("--limit", type=int, default=10)
    status_parser.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
