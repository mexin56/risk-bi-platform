from __future__ import annotations
import sys
import time
sys.path.insert(0, r"D:\vscode\归因分析\risk-bi-platform\server")
from app import service

odps = service._odps()
for cols in ["create_date, cnt", "create_date, traffic_channel, systemtype, device_brand, authen_type, ios_install_sysup_gap_mins_flag, reg_sx_days, high_risk_birth, if_recommend_flag, state_name_clean, register_software, first_channel, cnt, approval_cnt, approval_jy0_cnt"]:
    sql = f"SELECT {cols} FROM pb_biz_credit.lj_sx_cnt_analysis_summary WHERE pt = '20260803'"
    start = time.perf_counter()
    instance = odps.execute_sql(sql)
    submitted = time.perf_counter()
    n=0
    with instance.open_reader(tunnel=True, limit=False) as reader:
        for record in reader:
            n += 1
    end = time.perf_counter()
    print({'columns': cols.count(',') + 1, 'rows': n, 'submit_sec': round(submitted-start,2),'total_sec':round(end-start,2)})
