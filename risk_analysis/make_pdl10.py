# -*- coding: utf-8 -*-
src = open(r'E:\agent\monitor\risk_analysis\opt_plan_pdl.py', encoding='utf-8').read()

old_tiers = '''RISK_TIERS = [
    (0.05, 2.5, "T1_超低风险(<5%)"),
    (0.10, 2.0, "T2_低风险(5-10%)"),
    (0.20, 1.5, "T3_中低风险(10-20%)"),
    (0.30, 1.2, "T4_中风险(20-30%)"),
    (np.inf, 1.0, "T5_高风险(>=30%)"),
]'''
new_tiers = '''RISK_TIERS = [
    (0.02, 5.0, "T1_<2%"), (0.04, 4.0, "T2_2-4%"), (0.06, 3.0, "T3_4-6%"),
    (0.08, 2.5, "T4_6-8%"), (0.10, 2.0, "T5_8-10%"), (0.15, 1.5, "T6_10-15%"),
    (0.20, 1.2, "T7_15-20%"), (0.25, 1.0, "T8_20-25%"), (0.30, 0.7, "T9_25-30%"),
    (np.inf, 0.5, "T10_>=30%"),
]'''
assert old_tiers in src, "tiers block not found"
src = src.replace(old_tiers, new_tiers)
src = src.replace('DST = "/data2/jupyter-wenning/strage/PDL提额系数-提额方案-20260814.xlsx"',
                  'DST = "/data2/jupyter-wenning/strage/PDL提额系数-提额方案-10档差异化-20260814.xlsx"')
old_desc = '"按fpd7_rate$风险差异化",\n     "说明": "<5%×2.5 / 5-10%×2.0 / 10-20%×1.5 / 20-30%×1.2 / >=30%×1.0"'
new_desc = '"按fpd7_rate$风险差异化(10档)",\n     "说明": "T1<2%×5.0 ~ T8 20-25%×1.0, T9 25-30%×0.7, T10>=30%×0.5(收缩, 并非都提)"'
assert old_desc in src, "desc block not found"
src = src.replace(old_desc, new_desc)
open(r'E:\agent\monitor\risk_analysis\opt_plan_pdl10.py', 'w', encoding='utf-8').write(src)
print('ok')
