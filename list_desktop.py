from pathlib import Path
import json

items = []
for p in Path("C:/Users/PP-2026070302/Desktop").iterdir():
    items.append({"name": p.name, "path": str(p), "suffix": p.suffix, "size": p.stat().st_size})
Path("E:/agent/monitor/_source_inspection/desktop_files.json").write_text(
    json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
)
