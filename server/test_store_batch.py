# -*- coding: utf-8 -*-
"""store.persist_result 批量插入路径的快速回归测试(临时库,不碰正式库)。"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import duckdb

from pipeline import store

cfg = json.load(open("config/attribution_config.json", encoding="utf-8"))
conn = duckdb.connect("data/attribution.duckdb", read_only=True)
payload = conn.execute(
    "SELECT payload FROM attr_payloads WHERE run_id LIKE '20260823%'"
).fetchone()[0]
conn.close()
result = json.loads(payload)

path_rows = [
    {"alert_id": a["id"], "date": r["date"], "application_count": 1.0, "total_application_count": 2.0}
    for a in result["merged_alerts"][:3]
    for r in result["daily_trend"][:3]
]

tmp_db = Path("data/tmp_test.duckdb")
if tmp_db.exists():
    tmp_db.unlink()

t0 = time.time()
c = store.connect(tmp_db)
rid = store.persist_result(
    c,
    result=result,
    path_rows=path_rows,
    pt="t",
    offset=0,
    config=cfg,
    duration_ms=1,
    source="test",
)
c.close()
elapsed = round(time.time() - t0, 2)
print("persist OK run_id=", rid, "elapsed=", elapsed, "s")

v = duckdb.connect(str(tmp_db), read_only=True)
counts = {
    "alerts": v.execute("SELECT COUNT(*) FROM attr_alerts").fetchone()[0],
    "windows": v.execute("SELECT COUNT(*) FROM attr_alert_windows").fetchone()[0],
    "trend": v.execute("SELECT COUNT(*) FROM attr_daily_trend").fetchone()[0],
    "paths": v.execute("SELECT COUNT(*) FROM attr_path_daily").fetchone()[0],
    "suppressed": v.execute("SELECT COUNT(*) FROM attr_suppressed").fetchone()[0],
}
v.close()
tmp_db.unlink()
print(counts)
assert counts["alerts"] == len(result["merged_alerts"]), "alert count mismatch"
assert counts["paths"] == len(path_rows), "path row count mismatch"
print("[OK] batch persist verified")
