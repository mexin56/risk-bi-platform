from __future__ import annotations

import ast
import json
from pathlib import Path

from odps import ODPS

NOTEBOOK = Path(r"D:\vscode\数据库连接示例.ipynb")
TABLE = "lj_sx_cnt_analysis_summary"


def literal(node: ast.AST) -> str:
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        raise RuntimeError("Notebook 中的 ODPS 连接参数不是静态字符串，无法安全提取")
    return node.value


def load_connection() -> tuple[str, str, str, str]:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        try:
            tree = ast.parse("".join(cell.get("source", [])))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if name != "ODPS" or len(node.args) < 3:
                continue
            endpoint = next((kw.value for kw in node.keywords if kw.arg == "endpoint"), None)
            if endpoint is None:
                raise RuntimeError("Notebook 中的 ODPS 调用缺少 endpoint")
            return literal(node.args[0]), literal(node.args[1]), literal(node.args[2]), literal(endpoint)
    raise RuntimeError("Notebook 中未找到可用的 ODPS(...) 调用")


ak, sk, project, endpoint = load_connection()
odps = ODPS(ak, sk, project=project, endpoint=endpoint)
table = odps.get_table(TABLE)

print(f"CONNECTION: PASS ({project})")
print(f"TABLE: {project}.{TABLE}")
print("COLUMNS:")
for column in table.schema.columns:
    print(f"- {column.name}: {column.type}")
if table.schema.partitions:
    print("PARTITIONS:")
    for partition in table.schema.partitions:
        print(f"- {partition.name}: {partition.type}")
else:
    print("PARTITIONS: none")
