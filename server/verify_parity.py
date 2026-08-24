# -*- coding: utf-8 -*-
"""P1 验收:对比在线基线与预计算快照的 summary 是否逐字段一致。"""
import json
import sys

import duckdb

baseline = json.load(open("data/baseline_summary.json", encoding="utf-8-sig"))
conn = duckdb.connect("data/attribution.duckdb", read_only=True)
row = conn.execute(
    "SELECT payload FROM attr_payloads WHERE run_id LIKE '20260823%'"
).fetchone()
conn.close()
payload = json.loads(row[0])

keys = sorted(set(baseline) | set(payload["summary"]))
diff = [
    (k, baseline.get(k), payload["summary"].get(k))
    for k in keys
    if baseline.get(k) != payload["summary"].get(k)
]
print("summary 字段数:", len(keys))
print("差异字段:", diff if diff else "无 - 完全一致 [OK]")
print(
    "alerts:", len(payload["merged_alerts"]),
    "| suppressed:", len(payload["suppressed_alerts"]),
    "| daily_trend days:", len(payload["daily_trend"]),
)
sys.exit(1 if diff else 0)
