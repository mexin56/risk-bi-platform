from __future__ import annotations
import sys,time
field=sys.argv[1] if len(sys.argv)>1 else 'device_brand'
sys.path.insert(0, r"D:\vscode\归因分析\risk-bi-platform\server")
from app import service
odps=service._odps()
sql=f"""
SELECT CAST({field} AS STRING) AS value,
       TO_CHAR(create_date, 'yyyy-MM-dd') AS day,
       SUM(cnt) AS cnt
FROM pb_biz_credit.lj_sx_cnt_analysis_summary
WHERE pt = '20260803'
GROUP BY CAST({field} AS STRING), TO_CHAR(create_date, 'yyyy-MM-dd')
"""
start=time.perf_counter(); ins=odps.execute_sql(sql); print('submitted',round(time.perf_counter()-start,2), flush=True)
n=0
with ins.open_reader(tunnel=True,limit=False) as r:
 names=[c.name for c in r.schema.columns]
 for rec in r:
  n+=1
  if n % 100000 ==0: print('n',n,'sec',round(time.perf_counter()-start,2),flush=True)
print('field',field,'rows',n,'sec',round(time.perf_counter()-start,2),flush=True)
