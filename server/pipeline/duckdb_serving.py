"""发布完整 DuckDB 查询快照，隔离计算写入与跨进程只读查询。"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
import sys
import uuid

import duckdb


def database_path(serving_dir: Path) -> Path:
    return Path(serving_dir) / "results.duckdb"


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def publish_database(db_path: Path, serving_dir: Path, *, run_id: str | None = None) -> Path:
    """在源库只读锁内复制一致结果；完整关闭后原子发布，失败保留旧快照。"""
    serving_dir = Path(serving_dir)
    serving_dir.mkdir(parents=True, exist_ok=True)
    target = database_path(serving_dir)
    temporary = serving_dir / f".results-{uuid.uuid4().hex}.duckdb"
    with (serving_dir / ".duckdb-publish.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        conn = duckdb.connect(":memory:")
        try:
            conn.execute(f"ATTACH {_literal(str(Path(db_path).resolve()))} AS source_db (READ_ONLY)")
            if run_id is not None and conn.execute(
                "SELECT 1 FROM source_db.attr_payloads WHERE run_id = ?", [run_id]
            ).fetchone() is None:
                raise RuntimeError(f"run_id={run_id} 没有完整计算结果，不能发布")
            conn.execute(f"ATTACH {_literal(str(temporary.resolve()))} AS published_db")
            conn.execute("COPY FROM DATABASE source_db TO published_db")
            conn.execute("USE published_db")
            fund = Path(db_path).name.startswith("fund_")
            conn.execute("CREATE OR REPLACE VIEW runs AS SELECT * FROM attr_runs")
            conn.execute("CREATE OR REPLACE VIEW partitions AS SELECT * FROM dim_partitions")
            tables = {
                "alerts": "attr_alerts", "alert_windows": "attr_alert_windows",
                "summary": "attr_summary", "structures": "attr_structures",
                "suppressed": "attr_suppressed", "dashboard_payloads": "attr_payloads",
            }
            for view, table in tables.items():
                if fund and view in {"alerts", "alert_windows"}:
                    continue
                conn.execute(f"""CREATE OR REPLACE VIEW {view} AS
                    SELECT r.pt, r.offset_days, r.generated_at, r.source AS compute_source, t.*
                    FROM {table} t JOIN attr_runs r USING (run_id)""")
            if fund:
                # 从完整业务载荷展开资金字段，保留异常率等通用表未保存的指标。
                conn.execute("""CREATE TABLE fund_rule_payloads AS
                    SELECT r.pt, r.offset_days, r.generated_at, r.source AS compute_source,
                           r.run_id, json_extract_string(a.value, '$.id') AS id, a.value AS payload
                    FROM attr_runs r JOIN attr_payloads p USING (run_id),
                         LATERAL json_each(p.payload, '$.merged_alerts') a""")
                conn.execute("""CREATE OR REPLACE VIEW alerts AS
                    SELECT p.pt, p.offset_days, p.generated_at, p.compute_source,
                           t.* EXCLUDE (observation_count, excess_count, structure_lift_factor),
                           t.observation_count AS observation_abnormal_count,
                           t.excess_count AS excess_abnormal_count,
                           CAST(json_extract(p.payload, '$.rate_lift_factor') AS DOUBLE) AS rate_lift_factor
                    FROM fund_rule_payloads p JOIN attr_alerts t USING (run_id, id)""")
                fields = (
                    "baseline_abnormal_count", "observation_abnormal_count", "baseline_abnormal_daily",
                    "observation_abnormal_daily", "baseline_total_count", "observation_total_count",
                    "baseline_rate", "observation_rate", "growth_factor", "rate_lift_factor",
                    "rate_change_bp", "z_score", "expected_abnormal_count", "excess_abnormal_count",
                )
                numeric_columns = ", ".join(
                    f"CAST(json_extract(w.value, '$.{field}') AS DOUBLE) AS {field}" for field in fields
                )
                conn.execute(f"""CREATE TABLE fund_window_metrics AS
                    SELECT p.pt, p.offset_days, p.generated_at, p.compute_source, p.run_id,
                           p.id AS alert_id, w.key AS window_key,
                           json_extract_string(w.value, '$.label') AS label,
                           json_extract_string(w.value, '$.baseline_start') AS baseline_start,
                           json_extract_string(w.value, '$.baseline_end') AS baseline_end,
                           json_extract_string(w.value, '$.observation_start') AS observation_start,
                           json_extract_string(w.value, '$.observation_end') AS observation_end,
                           {numeric_columns}, w.value AS payload
                    FROM fund_rule_payloads p, LATERAL json_each(p.payload, '$.windows') w""")
                conn.execute("CREATE OR REPLACE VIEW alert_windows AS SELECT * FROM fund_window_metrics")
            daily_columns = (
                "t.* EXCLUDE (application_count, approval_count), "
                "t.application_count AS order_count, t.approval_count AS abnormal_order_count"
                if fund else "t.*"
            )
            path_columns = (
                "t.* EXCLUDE (application_count, total_application_count), "
                "t.application_count AS abnormal_order_count, t.total_application_count AS order_count"
                if fund else "t.*"
            )
            for view, table, columns in (
                ("daily_trend", "attr_daily_trend", daily_columns),
                ("path_daily", "attr_path_daily", path_columns),
            ):
                conn.execute(f"""CREATE OR REPLACE VIEW {view} AS
                    SELECT r.pt, r.offset_days, r.generated_at, r.source AS compute_source, {columns}
                    FROM {table} t JOIN attr_runs r USING (run_id)""")
            conn.execute("CHECKPOINT")
        finally:
            conn.close()
            # 计算/复制异常时保留正式数据库，清除未发布文件。
            if sys.exc_info()[0] is not None:
                temporary.unlink(missing_ok=True)
                temporary.with_suffix(".duckdb.wal").unlink(missing_ok=True)
        try:
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
            temporary.with_suffix(".duckdb.wal").unlink(missing_ok=True)
    return target


def connect_readonly(serving_dir: Path):
    path = database_path(serving_dir)
    if not path.exists():
        raise FileNotFoundError(f"DuckDB 结果尚未发布：{path.name}")
    return duckdb.connect(str(path), read_only=True)
