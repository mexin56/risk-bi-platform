# -*- coding: utf-8 -*-
src = open(r'E:\agent\monitor\risk_analysis\opt_plan_pdl_final.py', encoding='utf-8').read()
src = src.replace('USE_BASE = {"高额度使用率": 3.0, "中额度使用率": 1.8, "低额度使用率": 0.8}',
                  'USE_BASE = {"高额度使用率": 2.4, "中额度使用率": 1.7, "低额度使用率": 1.0}')
src = src.replace('DST = "/data2/jupyter-wenning/strage/PDL提额方案-最终-20260814.xlsx"',
                  'DST = "/data2/jupyter-wenning/strage/PDL提额方案-压降版-20260814.xlsx"')
src = src.replace('"高300% / 中180% / 低80%"', '"高240% / 中170% / 低100%"')
src = src.replace('"使用意愿优先: 高使用率客群基础提幅最高, 低使用率最低(提了也不用)"',
                  '"使用意愿优先(压降版): 高240% > 中170% > 低100%, 最大提幅压降至约240%"')
open(r'E:\agent\monitor\risk_analysis\opt_plan_pdl_final.py', 'w', encoding='utf-8').write(src)
print('ok')
