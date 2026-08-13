# -*- coding: utf-8 -*-
src = open(r'E:\agent\monitor\risk_analysis\opt_plan_v11.py', encoding='utf-8').read()
src = src.replace("""wb_src.close()

# 提额结果""", """wb_src.close()

if "Sheet5_原始" in wb.sheetnames:
    del wb["Sheet5_原始"]

# 提额结果""")
open(r'E:\agent\monitor\risk_analysis\opt_plan_v11.py', 'w', encoding='utf-8').write(src)
print('fixed3')
