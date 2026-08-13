from __future__ import annotations

"""Metadata / formula inspection only for local strategy workbooks.

This is an inspection helper, not an Office artifact-generation path. It masks
long identifiers and limits output to headers and the first populated rows.
"""

from pathlib import Path
from typing import Any

from openpyxl import load_workbook

DESKTOP = Path("C:/Users/PP-2026070302/Desktop")
FILES = [
    "\u63d0\u989d\u7cfb\u657020260812.xlsx",
    "\u5927\u6a21\u578b\u4f18\u5316\u63d0\u989d\u5e45\u5ea620260812.xlsx",
    "\u5927\u6a21\u578b\u6837\u672c2-\u63d0\u989d\u65b9\u6848-ABC\u5ba2\u7fa4-20260812.xlsx",
    "\u5927\u6a21\u578b\u6837\u672c2.xlsx",
    "\u65b0\u6a21\u578b\u7ebf\u4e0a\u9700\u8981\u56de\u6d41\u7684\u53d8\u91cf.xlsx",
]
OUT = Path("E:/agent/monitor/_source_inspection/credit_strategy_workbooks.md")


def display(value: Any) -> str:
    if value is None:
        return ""
    value = str(value).replace("\n", " / ").replace("\r", " ")
    # Avoid carrying arbitrary raw identifiers into the analysis artifact.
    if len(value) > 80:
        return value[:77] + "..."
    return value


def main() -> None:
    lines: list[str] = ["# 提额策略相关工作簿检查", ""]
    for name in FILES:
        path = DESKTOP / name
        lines.extend([f"## {name}", ""])
        if not path.exists():
            lines.extend(["文件不存在", ""])
            continue
        try:
            wb = load_workbook(path, data_only=False, read_only=True)
        except Exception as exc:  # noqa: BLE001
            lines.extend([f"无法读取：{type(exc).__name__}: {exc}", ""])
            continue
        lines.append("工作表：" + "、".join(wb.sheetnames))
        for ws in wb.worksheets:
            lines.extend(["", f"### {ws.title}", f"维度：{ws.max_row} 行 × {ws.max_column} 列", ""])
            # Output the first 35 rows with cells populated. Strategy lookup
            # sheets normally put headers / mapping rules near the top.
            nonempty_rows = 0
            for row in ws.iter_rows():
                cells = []
                for cell in row:
                    if cell.value is not None:
                        cells.append(f"{cell.coordinate}={display(cell.value)}")
                if cells:
                    lines.append(" | ".join(cells))
                    nonempty_rows += 1
                if nonempty_rows >= 35:
                    break
        lines.append("")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
