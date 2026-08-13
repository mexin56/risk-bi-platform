from __future__ import annotations
import concurrent.futures
import sys
import time
from collections import defaultdict

sys.path.insert(0, r"D:\vscode\归因分析\risk-bi-platform\server")
from app import service

FIELDS = [
    'traffic_channel','systemtype','device_brand','authen_type','ios_install_sysup_gap_mins_flag',
    'reg_sx_days','high_risk_birth','if_recommend_flag','state_name_clean','register_software','first_channel'
]
PARTITION='20260803'
TABLE='pb_biz_credit.lj_sx_cnt_analysis_summary'

def run(field):
    odps=service._odps()
    sql=f"""SELECT CAST({field} AS STRING) AS value, TO_CHAR(create_date,'yyyy-MM-dd') AS day, SUM(cnt) AS cnt
FROM {TABLE} WHERE pt='{PARTITION}'
GROUP BY CAST({field} AS STRING), TO_CHAR(create_date,'yyyy-MM-dd')"""
    start=time.perf_counter(); ins=odps.execute_sql(sql); rows=[]
    with ins.open_reader(tunnel=True,limit=False) as reader:
        for r in reader:
            rows.append((r['value'],str(r['day']),r['cnt']))
    return field,rows,round(time.perf_counter()-start,2)

start=time.perf_counter()
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
    futures=[ex.submit(run,f) for f in FIELDS]
    for future in concurrent.futures.as_completed(futures):
      f,rows,sec=future.result(); print(f, len(rows), sec, flush=True)
print('total',round(time.perf_counter()-start,2),flush=True)
