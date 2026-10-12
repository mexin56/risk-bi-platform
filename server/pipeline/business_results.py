"""按系统发布只包含业务结果表的 DuckDB，供 Risk BI 和 MyWorkflow 共用。"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import uuid

import duckdb

RESULT_TABLES = ("alerts", "alert_windows", "daily_trend", "path_daily", "summary", "structures", "suppressed")


def system_database_path(serving_dir: Path) -> Path:
    configured = os.getenv("RISK_BI_RESULTS_DB")
    return Path(configured) if configured else Path(serving_dir).parent / "duckdb/risk_bi_platform.duckdb"


def result_prefix(serving_dir: Path) -> str:
    return "fund" if Path(serving_dir).name == "fund_serving" else "credit"


def file_version(path: Path) -> str:
    try:
        stat = Path(path).stat()
        return f"{stat.st_dev}:{stat.st_ino}:{stat.st_mtime_ns}:{stat.st_size}"
    except FileNotFoundError:
        return ""


def snapshot_version(serving_dir: Path) -> str:
    return file_version(system_database_path(serving_dir))


def connect_results(serving_dir: Path):
    path = system_database_path(serving_dir)
    if not path.is_file():
        raise FileNotFoundError("Risk BI 业务结果尚未发布")
    return duckdb.connect(str(path), read_only=True)


def _literal(path: Path) -> str:
    return "'" + str(path.resolve()).replace("'", "''") + "'"


def _copy_domain(conn, alias: str, prefix: str, previous_tables: set[str]) -> None:
    for suffix in RESULT_TABLES:
        table = f"{prefix}_{suffix}"
        conn.execute(f"CREATE TABLE {table} AS SELECT * FROM {alias}.{suffix}")
    table = f"{prefix}_dashboard"
    conn.execute(f"""CREATE TABLE {table} AS
        SELECT r.pt, r.offset_days, r.run_id, r.generated_at,
               COALESCE(d.min_day, r.table_date_min) AS table_date_min,
               COALESCE(d.max_day, r.table_date_max) AS table_date_max,
               r.source AS compute_source, p.payload
        FROM {alias}.attr_runs r JOIN {alias}.attr_payloads p USING (run_id)
        LEFT JOIN {alias}.dim_partitions d ON d.pt = r.pt""")
    if prefix == "credit":
        # 已装配的历史结果直接复用；只处理新增或重算批次，降低日常发布开销。
        if table in previous_tables:
            conn.execute(f"""UPDATE {table} AS target SET payload = previous.payload
                FROM previous_db.{table} AS previous
                WHERE target.run_id = previous.run_id AND target.generated_at = previous.generated_at""")
            pending = conn.execute(f"""SELECT target.run_id, target.payload FROM {table} AS target
                LEFT JOIN previous_db.{table} AS previous
                ON target.run_id = previous.run_id AND target.generated_at = previous.generated_at
                WHERE previous.run_id IS NULL""").fetchall()
        else:
            pending = conn.execute(f"SELECT run_id, payload FROM {table}").fetchall()
        from pipeline.assemble import enrich_approval_rates
        for run_id, payload in pending:
            frame = conn.execute(f"""SELECT alert_id, date, application_count,
                total_application_count, approval_count, cid_cnt, approval_cid_cnt
                FROM {prefix}_path_daily WHERE run_id = ?""", [run_id]).df()
            prepared = enrich_approval_rates(json.loads(payload), frame)
            prepared.setdefault("meta", {})["approval_enriched"] = True
            conn.execute(f"UPDATE {table} SET payload = ? WHERE run_id = ?",
                         [json.dumps(prepared, ensure_ascii=False, allow_nan=False), run_id])
    conn.execute(f"CREATE INDEX {prefix}_dashboard_lookup ON {table}(pt, offset_days, generated_at)")
    conn.execute(f"CREATE INDEX {prefix}_path_lookup ON {prefix}_path_daily(run_id, alert_id, date)")


def publish_system_database(serving_dir: Path) -> Path:
    """各业务计算完成后串行发布系统结果库，保留其他业务的结果。"""
    serving_dir = Path(serving_dir)
    target = system_database_path(serving_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f".risk_bi_platform-{uuid.uuid4().hex}.duckdb"
    with target.with_suffix(".publish.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        conn = duckdb.connect(str(temporary), config={"threads": "2"})
        try:
            previous_tables: set[str] = set()
            if target.is_file():
                conn.execute(f"ATTACH {_literal(target)} AS previous_db (READ_ONLY)")
                previous_tables = {row[0] for row in conn.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_catalog = 'previous_db'"
                ).fetchall()}
            domains = (("credit", "serving"), ("fund", "fund_serving"), ("model", "model_serving"))
            copied = False
            for prefix, folder in domains:
                source = serving_dir.parent / folder / "results.duckdb"
                if source.is_file():
                    alias = prefix + "_source"
                    conn.execute(f"ATTACH {_literal(source)} AS {alias} (READ_ONLY)")
                    if prefix == 'model':
                        from model_result_store import MODEL_RESULT_TABLES
                        for table in MODEL_RESULT_TABLES:
                            conn.execute(f'CREATE TABLE {table} AS SELECT * FROM {alias}.{table}')
                            if table != 'model_filters':
                                conn.execute(f'CREATE INDEX {table}_scope ON {table}(pt,flag_mob_type,flag_product,cash_ser_call_node)')
                        for table in ('model_stability_weekly','model_cohort_trend'):
                            conn.execute(f'CREATE INDEX {table}_model ON {table}(pt,model,alias)')
                    else:
                        _copy_domain(conn, alias, prefix, previous_tables)
                    copied = True
                elif previous_tables:
                    # 另一业务暂时没有新快照时，保留该业务的已发布历史结果。
                    for table in sorted(previous_tables):
                        if table.startswith(prefix + "_"):
                            conn.execute(f"CREATE TABLE {table} AS SELECT * FROM previous_db.{table}")
                            copied = True
            if not copied:
                raise RuntimeError("尚无可发布的业务结果")
            conn.execute("CHECKPOINT")
            conn.close()
            conn = None
            os.replace(temporary, target)
        finally:
            if conn is not None:
                conn.close()
            temporary.unlink(missing_ok=True)
            temporary.with_suffix(".duckdb.wal").unlink(missing_ok=True)
    return target
