from __future__ import annotations

"""Read-only exploration of pb_biz_credit.flexi_cash_jq_result_v1.

Connection credentials are read from the local notebook and are never printed.
"""

import ast
import json
from pathlib import Path
from typing import Any

from odps import ODPS

NOTEBOOK = Path("D:/vscode/" + "\u6570\u636e\u5e93\u8fde\u63a5\u793a\u4f8b.ipynb")
OUTPUT = Path("E:/agent/monitor/risk_analysis/flexi_cash_probe.json")
TABLE = "pb_biz_credit.flexi_cash_jq_result_v1"


def literal(node: ast.AST) -> str:
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        raise RuntimeError("ODPS connection parameters must be literal strings")
    return node.value


def get_odps() -> ODPS:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    for cell in notebook["cells"]:
        if cell.get("cell_type") != "code":
            continue
        try:
            tree = ast.parse("".join(cell.get("source", [])))
        except SyntaxError:
            continue
        for call in ast.walk(tree):
            name = (
                call.func.id
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                else call.func.attr
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                else ""
            )
            if name != "ODPS" or len(call.args) < 3:
                continue
            endpoint = next((kw.value for kw in call.keywords if kw.arg == "endpoint"), None)
            if endpoint is not None:
                return ODPS(
                    literal(call.args[0]),
                    literal(call.args[1]),
                    project=literal(call.args[2]),
                    endpoint=literal(endpoint),
                )
    raise RuntimeError("No usable ODPS connection was found")


def query(odps: ODPS, sql: str) -> list[dict[str, Any]]:
    instance = odps.execute_sql(sql)
    with instance.open_reader(tunnel=True, limit=False) as reader:
        fields = [field.name for field in reader.schema.columns]
        return [{field: record[field] for field in fields} for record in reader]


def main() -> None:
    odps = get_odps()
    queries = {
        "overall": f"""
            SELECT COUNT(1) AS row_cnt,
                   COUNT(DISTINCT businessid) AS businessid_cnt,
                   MIN(jq_date) AS min_jq_date,
                   MAX(jq_date) AS max_jq_date,
                   MIN(jq_time) AS min_jq_time,
                   MAX(jq_time) AS max_jq_time
            FROM {TABLE}
        """,
        "date_distribution": f"""
            SELECT jq_date, COUNT(1) AS row_cnt,
                   COUNT(DISTINCT businessid) AS businessid_cnt
            FROM {TABLE}
            GROUP BY jq_date
            ORDER BY jq_date DESC
            LIMIT 100
        """,
        "strategy_distribution": f"""
            SELECT str_type, app_flow_flag, te_flag,
                   COUNT(1) AS row_cnt,
                   COUNT(DISTINCT businessid) AS businessid_cnt,
                   AVG(CAST(jq_credit_quota AS DOUBLE)) AS avg_before_limit,
                   AVG(CAST(cash_quota_amount_now_after AS DOUBLE)) AS avg_after_limit,
                   AVG(CAST(cash_remark1 AS DOUBLE)) AS avg_raise_amount
            FROM {TABLE}
            GROUP BY str_type, app_flow_flag, te_flag
            ORDER BY row_cnt DESC
            LIMIT 200
        """,
        "cash_remark_distribution": f"""
            SELECT cash_remark1, COUNT(1) AS row_cnt,
                   COUNT(DISTINCT businessid) AS businessid_cnt,
                   MIN(CAST(jq_credit_quota AS DOUBLE)) AS min_before_limit,
                   MAX(CAST(jq_credit_quota AS DOUBLE)) AS max_before_limit,
                   MIN(CAST(cash_quota_amount_now_after AS DOUBLE)) AS min_after_limit,
                   MAX(CAST(cash_quota_amount_now_after AS DOUBLE)) AS max_after_limit
            FROM {TABLE}
            GROUP BY cash_remark1
            ORDER BY row_cnt DESC
            LIMIT 200
        """,
    }
    results = {name: query(odps, sql) for name, sql in queries.items()}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
