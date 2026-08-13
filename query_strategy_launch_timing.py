from __future__ import annotations

import json
from pathlib import Path

from probe_flexi_cash_strategy import get_odps, query

TABLE = "pb_biz_credit.flexi_cash_jq_result_v1"
OUTPUT = Path("risk_analysis/strategy_launch_timing.json")


def main() -> None:
    odps = get_odps()
    queries = {
        "new_by_jq_date": f"""
            SELECT jq_date, COUNT(1) AS cnt, MIN(jq_time) AS min_jq_time, MAX(jq_time) AS max_jq_time
            FROM {TABLE} WHERE str_type = 'new'
            GROUP BY jq_date ORDER BY jq_date
        """,
        "by_run_day_hour": f"""
            SELECT TO_CHAR(jq_time, 'yyyy-MM-dd HH') AS run_hour, str_type,
                   COUNT(1) AS cnt
            FROM {TABLE}
            WHERE jq_time >= CAST('2026-08-11 00:00:00' AS DATETIME)
            GROUP BY TO_CHAR(jq_time, 'yyyy-MM-dd HH'), str_type
            ORDER BY run_hour, str_type
        """,
        "new_overall": f"""
            SELECT COUNT(1) AS cnt, MIN(jq_time) AS min_jq_time, MAX(jq_time) AS max_jq_time,
                   MIN(jq_date) AS min_jq_date, MAX(jq_date) AS max_jq_date
            FROM {TABLE} WHERE str_type='new'
        """,
    }
    output = {name: query(odps, sql) for name, sql in queries.items()}
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
