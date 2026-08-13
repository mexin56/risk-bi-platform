from __future__ import annotations

import ast
import json
from pathlib import Path

path = Path(r"D:\vscode\数据库连接示例.ipynb")
nb = json.loads(path.read_text(encoding="utf-8"))

for cell_index, cell in enumerate(nb.get("cells", []), 1):
    if cell.get("cell_type") != "code":
        continue
    source = "".join(cell.get("source", []))
    try:
        tree = ast.parse(source)
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None
        if name != "ODPS":
            continue
        arg_desc = []
        for index, arg in enumerate(node.args, 1):
            if index in (1, 2):
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    arg_desc.append(f"arg{index}=literal-string(redacted,length={len(arg.value)})")
                else:
                    arg_desc.append(f"arg{index}={type(arg).__name__}(redacted)")
            elif isinstance(arg, ast.Constant):
                arg_desc.append(f"arg{index}={arg.value!r}")
            else:
                arg_desc.append(f"arg{index}={ast.unparse(arg)}")
        kw_desc = []
        for kw in node.keywords:
            if kw.arg is None:
                continue
            if kw.arg.lower() in {"access_id", "access_key", "access_key_id", "access_key_secret", "secret", "password", "token"}:
                kw_desc.append(f"{kw.arg}=redacted")
            elif isinstance(kw.value, ast.Constant):
                kw_desc.append(f"{kw.arg}={kw.value.value!r}")
            else:
                kw_desc.append(f"{kw.arg}={ast.unparse(kw.value)}")
        print(f"cell={cell_index}; " + "; ".join(arg_desc + kw_desc))
