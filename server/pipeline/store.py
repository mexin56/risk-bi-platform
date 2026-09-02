"""DuckDB 持久化层:预计算归因结果的唯一写入入口。

单写者纪律:只有 pipeline 进程以读写方式打开 attribution.duckdb;
FastAPI 服务永远不碰这个文件,只读 exporter 导出的 serving parquet 快照。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

SCHEMA_SQL = [
    # 运行批次(幂等键:pt + offset + config_hash;重跑覆盖同 run_id)
    """
    CREATE TABLE IF NOT EXISTS attr_runs (
        run_id         VARCHAR PRIMARY KEY,
        pt             VARCHAR NOT NULL,
        offset_days    INTEGER NOT NULL DEFAULT 0,
        config_version VARCHAR NOT NULL,
        config_hash    VARCHAR NOT NULL,
        window_start   DATE,
        window_end     DATE,
        table_date_min VARCHAR,
        table_date_max VARCHAR,
        generated_at   TIMESTAMP NOT NULL,
        duration_ms    INTEGER,
        source         VARCHAR NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS attr_summary (
        run_id  VARCHAR PRIMARY KEY,
        payload VARCHAR
    )
    """,
    # 合并预警主表(suppressed 路径用 attr_suppressed 单独存放)
    """
    CREATE TABLE IF NOT EXISTS attr_alerts (
        run_id         VARCHAR NOT NULL,
        id             VARCHAR NOT NULL,
        canonical_path VARCHAR NOT NULL,
        path           VARCHAR NOT NULL,
        source         VARCHAR,
        layer          VARCHAR,
        level          INTEGER,
        level_label    VARCHAR,
        severity       VARCHAR,
        anomaly_type   VARCHAR,
        primary_window VARCHAR,
        hit_windows    VARCHAR,
        observation_count DOUBLE,
        growth_factor  DOUBLE,
        structure_lift_factor DOUBLE,
        z_score        DOUBLE,
        excess_count   DOUBLE,
        relative_strength DOUBLE,
        conditions     VARCHAR,
        is_expert_forced BOOLEAN,
        rule_note      VARCHAR,
        is_suppressed  BOOLEAN,
        enters_next_level BOOLEAN,
        drilldown_rule VARCHAR,
        sort_rank      INTEGER,
        PRIMARY KEY (run_id, id)
    )
    """,
    # 每路径 × 每窗口的完整窗口指标(windows 字典拆平)
    """
    CREATE TABLE IF NOT EXISTS attr_alert_windows (
        run_id VARCHAR NOT NULL,
        alert_id VARCHAR NOT NULL,
        window_key VARCHAR NOT NULL,
        label VARCHAR, color VARCHAR, purpose VARCHAR,
        baseline_start DATE, baseline_end DATE,
        observation_start DATE, observation_end DATE,
        baseline_days INTEGER, observation_days INTEGER,
        baseline_count DOUBLE, observation_count DOUBLE,
        baseline_daily DOUBLE, observation_daily DOUBLE,
        baseline_share DOUBLE, observation_share DOUBLE,
        growth_factor DOUBLE, structure_lift_factor DOUBLE,
        structure_change DOUBLE,
        expected_count DOUBLE, excess_count DOUBLE, z_score DOUBLE,
        level INTEGER, level_label VARCHAR, severity VARCHAR,
        cid_cnt DOUBLE, approval_cid_cnt DOUBLE, cid_approval_rate_pct DOUBLE,
        PRIMARY KEY (run_id, alert_id, window_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS attr_daily_trend (
        run_id VARCHAR NOT NULL,
        date DATE NOT NULL,
        application_count DOUBLE, approval_count DOUBLE,
        cid_cnt DOUBLE, approval_cid_cnt DOUBLE,
        expert_seed_count DOUBLE, focus_path_count DOUBLE,
        PRIMARY KEY (run_id, date)
    )
    """,
    # ★ 路径 × 日 预计算(path-trend 接口直接读,消灭点击时在线查询)
    """
    CREATE TABLE IF NOT EXISTS attr_path_daily (
        run_id VARCHAR NOT NULL,
        alert_id VARCHAR NOT NULL,
        date DATE NOT NULL,
        application_count DOUBLE,
        total_application_count DOUBLE,
        approval_count DOUBLE,
        cid_cnt DOUBLE,
        approval_cid_cnt DOUBLE,
        PRIMARY KEY (run_id, alert_id, date)
    )
    """,
    # 免归因(suppressed)路径
    """
    CREATE TABLE IF NOT EXISTS attr_suppressed (
        run_id VARCHAR PRIMARY KEY,
        payload VARCHAR
    )
    """,
    # top_k 下钻结构 + expert 强制链 + rules(结构化收益低,整块 JSON 存)
    """
    CREATE TABLE IF NOT EXISTS attr_structures (
        run_id VARCHAR PRIMARY KEY,
        top_k VARCHAR, expert VARCHAR, rules VARCHAR
    )
    """,
    # 完整响应载荷(与 API 契约同构;装配时优先使用)
    """
    CREATE TABLE IF NOT EXISTS attr_payloads (
        run_id VARCHAR PRIMARY KEY,
        payload VARCHAR
    )
    """,
    # 分区范围(partitions 接口直接读,消灭冷启动串行 MIN/MAX)
    """
    CREATE TABLE IF NOT EXISTS dim_partitions (
        pt VARCHAR PRIMARY KEY,
        min_day VARCHAR,
        max_day VARCHAR,
        refreshed_at TIMESTAMP
    )
    """,
]


def connect(db_path: Path) -> duckdb.DuckDBPyConnection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    for statement in SCHEMA_SQL:
        conn.execute(statement)
    # 轻量迁移:老库补列(已存在时报错被吞掉即可)
    try:
        conn.execute("ALTER TABLE attr_path_daily ADD COLUMN IF NOT EXISTS approval_count DOUBLE")
        conn.execute("ALTER TABLE attr_daily_trend ADD COLUMN IF NOT EXISTS cid_cnt DOUBLE")
        conn.execute("ALTER TABLE attr_daily_trend ADD COLUMN IF NOT EXISTS approval_cid_cnt DOUBLE")
        conn.execute("ALTER TABLE attr_path_daily ADD COLUMN IF NOT EXISTS cid_cnt DOUBLE")
        conn.execute("ALTER TABLE attr_path_daily ADD COLUMN IF NOT EXISTS approval_cid_cnt DOUBLE")
        conn.execute("ALTER TABLE attr_alert_windows ADD COLUMN IF NOT EXISTS cid_cnt DOUBLE")
        conn.execute("ALTER TABLE attr_alert_windows ADD COLUMN IF NOT EXISTS approval_cid_cnt DOUBLE")
        conn.execute("ALTER TABLE attr_alert_windows ADD COLUMN IF NOT EXISTS cid_approval_rate_pct DOUBLE")
    except Exception:
        pass
    return conn


def config_fingerprint(config: dict[str, Any]) -> tuple[str, str]:
    """配置版本号 + 内容哈希:口径变更检测的依据。"""
    raw = json.dumps(config, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return str(config.get("version", "unknown")), digest[:12]


def make_run_id(pt: str, offset: int, config_hash: str) -> str:
    return f"{pt}_{int(offset)}_{config_hash}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _date_only(value: Any):
    if value is None:
        return None
    text = str(value)
    return text[:10]


def persist_result(
    conn: duckdb.DuckDBPyConnection,
    *,
    result: dict[str, Any],
    path_rows: list[dict[str, Any]],
    pt: str,
    offset: int,
    config: dict[str, Any],
    duration_ms: int,
    source: str,
) -> str:
    """一个事务内写完整批次;同 run_id 重跑即覆盖(幂等)。返回 run_id。"""
    meta = result["meta"]
    version, config_hash = config_fingerprint(config)
    run_id = make_run_id(pt, offset, config_hash)
    generated_at = utc_now()

    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute(
            "INSERT OR REPLACE INTO attr_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                run_id, pt, int(offset), version, config_hash,
                _date_only(meta.get("date_start")), _date_only(meta.get("date_end")),
                meta.get("table_date_min"), meta.get("table_date_max"),
                generated_at, int(duration_ms), source,
            ],
        )
        conn.execute(
            "INSERT OR REPLACE INTO attr_summary VALUES (?, ?)",
            [run_id, _dump(result.get("summary", {}))],
        )

        alerts = result.get("merged_alerts", [])
        conn.execute("DELETE FROM attr_alerts WHERE run_id = ?", [run_id])
        conn.execute("DELETE FROM attr_alert_windows WHERE run_id = ?", [run_id])
        alert_rows = []
        window_rows = []
        for rank, alert in enumerate(alerts):
            alert_rows.append(
                [
                    run_id, alert["id"], alert["canonical_path"], alert["path"],
                    alert.get("source"), alert.get("layer"), int(alert.get("level", 0) or 0),
                    alert.get("level_label"), alert.get("severity"), alert.get("anomaly_type"),
                    alert.get("primary_window"), _dump(alert.get("hit_windows", [])),
                    float(alert.get("observation_count", 0) or 0),
                    float(alert.get("growth_factor", 0) or 0),
                    float(alert.get("structure_lift_factor", 0) or 0),
                    float(alert.get("z_score", 0) or 0),
                    float(alert.get("excess_count", 0) or 0),
                    float(alert.get("relative_strength", 0) or 0),
                    _dump(alert.get("conditions", [])),
                    bool(alert.get("is_expert_forced")), alert.get("rule_note"),
                    bool(alert.get("is_suppressed")), bool(alert.get("enters_next_level")),
                    alert.get("drilldown_rule"), rank,
                ]
            )
            for window_key, window in (alert.get("windows") or {}).items():
                window_rows.append(
                    [
                        run_id, alert["id"], window_key,
                        window.get("label"), window.get("color"), window.get("purpose"),
                        _date_only(window.get("baseline_start")), _date_only(window.get("baseline_end")),
                        _date_only(window.get("observation_start")), _date_only(window.get("observation_end")),
                        int(window.get("baseline_days", 0) or 0), int(window.get("observation_days", 0) or 0),
                        float(window.get("baseline_count", 0) or 0), float(window.get("observation_count", 0) or 0),
                        float(window.get("baseline_daily", 0) or 0), float(window.get("observation_daily", 0) or 0),
                        float(window.get("baseline_share", 0) or 0), float(window.get("observation_share", 0) or 0),
                        float(window.get("growth_factor", 0) or 0), float(window.get("structure_lift_factor", 0) or 0),
                        float(window.get("structure_change", 0) or 0),
                        float(window.get("expected_count", 0) or 0), float(window.get("excess_count", 0) or 0),
                        float(window.get("z_score", 0) or 0),
                        int(window.get("level", 0) or 0), window.get("level_label"), window.get("severity"),
                        float(window["cid_cnt"]) if window.get("cid_cnt") is not None else None,
                        float(window["approval_cid_cnt"]) if window.get("approval_cid_cnt") is not None else None,
                        float(window["cid_approval_rate_pct"]) if window.get("cid_approval_rate_pct") is not None else None,
                    ]
                )
        if alert_rows:
            conn.executemany(
                "INSERT INTO attr_alerts VALUES (" + ",".join(["?"] * 25) + ")",
                alert_rows,
            )
        if window_rows:
            conn.executemany(
                "INSERT INTO attr_alert_windows VALUES (" + ",".join(["?"] * 30) + ")",
                window_rows,
            )

        conn.execute("DELETE FROM attr_daily_trend WHERE run_id = ?", [run_id])
        trend_rows = [
            [
                run_id, _date_only(row.get("date")),
                float(row.get("application_count", 0) or 0),
                float(row.get("approval_count", 0) or 0),
                float(row.get("cid_cnt", 0) or 0),
                float(row.get("approval_cid_cnt", 0) or 0),
                float(row.get("expert_seed_count", 0) or 0),
                float(row.get("focus_path_count", 0) or 0),
            ]
            for row in result.get("daily_trend", [])
        ]
        if trend_rows:
            conn.executemany(
                "INSERT INTO attr_daily_trend "
                "(run_id, date, application_count, approval_count, cid_cnt, approval_cid_cnt, expert_seed_count, focus_path_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", trend_rows
            )

        conn.execute("DELETE FROM attr_path_daily WHERE run_id = ?", [run_id])
        if path_rows:
            conn.executemany(
                "INSERT INTO attr_path_daily "
                "(run_id, alert_id, date, application_count, total_application_count, approval_count, cid_cnt, approval_cid_cnt) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    [
                        run_id, row["alert_id"], _date_only(row["date"]),
                        float(row.get("application_count", 0) or 0),
                        float(row.get("total_application_count", 0) or 0),
                        float(row["approval_count"]) if row.get("approval_count") is not None else None,
                        float(row["cid_cnt"]) if row.get("cid_cnt") is not None else None,
                        float(row["approval_cid_cnt"]) if row.get("approval_cid_cnt") is not None else None,
                    ]
                    for row in path_rows
                ],
            )

        suppressed = result.get("suppressed_alerts", [])
        conn.execute(
            "INSERT OR REPLACE INTO attr_suppressed VALUES (?, ?)",
            [run_id, _dump({"alerts": suppressed, "total": result.get("suppressed_alert_total", len(suppressed))})],
        )
        structures = result.get("structures")
        if structures is None:
            structures = {
                "top_k": result.get("top_k"),
                "expert": result.get("expert"),
                "rules": result.get("rules"),
            }
        conn.execute(
            "INSERT OR REPLACE INTO attr_structures VALUES (?, ?, ?, ?)",
            [run_id, _dump(structures.get("top_k")), _dump(structures.get("expert")), _dump(structures.get("rules"))],
        )
        conn.execute(
            "INSERT OR REPLACE INTO attr_payloads VALUES (?, ?)",
            [run_id, _dump(result)],
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return run_id


def upsert_partition_range(conn: duckdb.DuckDBPyConnection, pt: str, min_day: Any, max_day: Any) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO dim_partitions VALUES (?, ?, ?, ?)",
        [pt, min_day, max_day, utc_now()],
    )
