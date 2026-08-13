from __future__ import annotations

import ast
import json
from pathlib import Path
from odps import ODPS

NOTEBOOK = Path(r"D:\vscode\数据库连接示例.ipynb")


def literal(node: ast.AST) -> str:
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        raise RuntimeError("Notebook ODPS 参数不是静态字符串")
    return node.value


def conn() -> tuple[str, str, str, str]:
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    for cell in nb["cells"]:
        if cell.get("cell_type") != "code":
            continue
        try:
            tree = ast.parse("".join(cell.get("source", [])))
        except SyntaxError:
            continue
        for call in ast.walk(tree):
            name = call.func.id if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) else call.func.attr if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) else ""
            if name == "ODPS" and len(call.args) >= 3:
                endpoint = next((kw.value for kw in call.keywords if kw.arg == "endpoint"), None)
                if endpoint:
                    return literal(call.args[0]), literal(call.args[1]), literal(call.args[2]), literal(endpoint)
    raise RuntimeError("Notebook 未发现 ODPS 连接")


def query(odps: ODPS, sql: str):
    instance = odps.execute_sql(sql)
    with instance.open_reader(tunnel=True, limit=False) as reader:
        columns = [col.name for col in reader.schema.columns]
        return [dict((name, record[name]) for name in columns) for record in reader]


ak, sk, project, endpoint = conn()
odps = ODPS(ak, sk, project=project, endpoint=endpoint)
base = "pb_biz_credit.lj_sx_cnt_analysis_summary"
where = "WHERE pt = '20260803'"

queries = {
    "summary": f"""
        SELECT MIN(create_date) AS min_create_date,
               MAX(create_date) AS max_create_date,
               COUNT(1) AS aggregate_rows,
               SUM(cnt) AS application_cnt,
               SUM(approval_cnt) AS approval_cnt,
               SUM(approval_jy0_cnt) AS approval_jy0_cnt
        FROM {base}
        {where}
    """,
    "daily": f"""
        SELECT TO_CHAR(create_date, 'yyyy-MM-dd') AS create_date,
               SUM(cnt) AS application_cnt,
               SUM(approval_cnt) AS approval_cnt,
               SUM(approval_jy0_cnt) AS approval_jy0_cnt
        FROM {base}
        {where}
        GROUP BY TO_CHAR(create_date, 'yyyy-MM-dd')
        ORDER BY create_date DESC
        LIMIT 31
    """,
}

for name, sql in queries.items():
    print(f"## {name}")
    for row in query(odps, sql):
        print(json.dumps(row, ensure_ascii=False, default=str))
