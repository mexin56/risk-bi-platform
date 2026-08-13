from __future__ import annotations
import json
import sys
import time
sys.path.insert(0, r"D:\vscode\归因分析\risk-bi-platform\server")
from app import service
start=time.perf_counter()
print('starting', flush=True)
result=service.dashboard(force=True)
print('finished_seconds',round(time.perf_counter()-start,2),flush=True)
print(json.dumps({
 'meta':result['meta'],
 'summary':result['summary'],
 'highlight': {k:result['highlight'].get(k) for k in ['source','path','level_label','anomaly_type','primary_window_label','growth_factor','structure_lift_factor','z_score','excess_count']} if result['highlight'] else None,
 'top_k_counts':result['top_k']['counts'],
 'expert_counts':result['expert']['counts'],
 'alerts':[{k:r.get(k) for k in ['source','path','level_label','anomaly_type']} for r in result['merged_alerts'][:5]],
},ensure_ascii=False,indent=2,default=str),flush=True)
