from __future__ import annotations
import sys
import time
sys.path.insert(0, r"D:\vscode\归因分析\risk-bi-platform\server")
from app import service
odps = service._odps()
sql = """
SELECT CAST(traffic_channel AS STRING) AS value,
       TO_CHAR(create_date, 'yyyy-MM-dd') AS day,
       SUM(cnt) AS cnt
FROM pb_biz_credit.lj_sx_cnt_analysis_summary
WHERE pt = '20260803'
GROUP BY CAST(traffic_channel AS STRING), TO_CHAR(create_date, 'yyyy-MM-dd')
"""
start=time.perf_counter()
instance=odps.execute_sql(sql)
print('submitted', round(time.perf_counter()-start,2))
rows=0
with instance.open_reader(tunnel=True, limit=False) as reader:
    names=[c.name for c in reader.schema.columns]
    for r in reader:
        rows+=1
        if rows <= 3:
            print({n:r[n] for n in names})
print('rows', rows, 'seconds', round(time.perf_counter()-start,2))
