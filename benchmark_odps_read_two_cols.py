from __future__ import annotations
import sys,time
sys.path.insert(0, r"D:\vscode\归因分析\risk-bi-platform\server")
from app import service
odps=service._odps()
sql="SELECT create_date, cnt FROM pb_biz_credit.lj_sx_cnt_analysis_summary WHERE pt='20260803'"
start=time.perf_counter(); ins=odps.execute_sql(sql); print('submit',round(time.perf_counter()-start,2), flush=True)
n=0
with ins.open_reader(tunnel=True, limit=False) as reader:
  for x in reader:
    n+=1
    if n%100000==0: print('n',n,'sec',round(time.perf_counter()-start,2), flush=True)
print('finished',n,round(time.perf_counter()-start,2), flush=True)
