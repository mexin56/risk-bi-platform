# -*- coding: utf-8 -*-
src = open(r'E:\agent\monitor\risk_analysis\opt_plan_v11.py', encoding='utf-8').read()
src = src.replace('df = pd.read_excel(SRC, sheet_name="Sheet5")', 'df = pd.read_excel(SRC, sheet_name=0)')
src = src.replace('for row in wb_src["Sheet5"].iter_rows():', 'for row in wb_src.worksheets[0].iter_rows():')
open(r'E:\agent\monitor\risk_analysis\opt_plan_v11.py', 'w', encoding='utf-8').write(src)
print('fixed')
