# -*- coding: utf-8 -*-
src = open(r'E:\agent\monitor\risk_analysis\opt_plan_v11.py', encoding='utf-8').read()
src = src.replace("avg_b = (cur_amt + inc_b.sum()) / N\nprint(f\"方案B[原始盖帽]: 新增 {inc_b.sum()/1e8:.2f} 亿 | 可达 {avg_b:,.0f} 元\")",
                  "avg_b = (cur_amt + df_b_inc.sum()) / N\nprint(f\"方案B[原始盖帽]: 新增 {df_b_inc.sum()/1e8:.2f} 亿 | 可达 {avg_b:,.0f} 元\")")
src = src.replace("新增 {inc_b.sum()/1e8:.2f}", "新增 {df_b_inc.sum()/1e8:.2f}")
src = src.replace("v4 = inc_b.sum()", "v4 = df_b_inc.sum()")
open(r'E:\agent\monitor\risk_analysis\opt_plan_v11.py', 'w', encoding='utf-8').write(src)
print('fixed2')
