from __future__ import annotations

import sys
sys.path.insert(0, r"E:\agent\monitor")
from probe_maxcompute_table import load_connection, TABLE  # noqa: E402
from odps import ODPS  # noqa: E402

ak, sk, project, endpoint = load_connection()
odps = ODPS(ak, sk, project=project, endpoint=endpoint)
table = odps.get_table(TABLE)
parts = sorted(str(part) for part in table.partitions)
print(f"PARTITION_COUNT={len(parts)}")
for part in parts[-20:]:
    print(part)
