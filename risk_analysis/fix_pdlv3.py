# -*- coding: utf-8 -*-
src = open(r'E:\agent\monitor\risk_analysis\opt_plan_pdl_v3.py', encoding='utf-8').read()
src = src.replace('df["风险可提"] = df["fpd7_rate$"] < cur_fpd7\n', '')
src = src.replace('df["是否可提额"] = df["等级可提"] & df["风险可提"]', 'df["是否可提额"] = df["等级可提"]')
old = '"提额客群范围", "数值": "A/B/C 且 fpd7_rate$<大盘",\n     "说明": f"D/E({df.loc[~df[\'等级可提\'],\'提额客户\'].sum():,}) + 高于大盘{cur_fpd7*100:.1f}%的ABC客群({df.loc[df[\'等级可提\']&~df[\'风险可提\'],\'提额客户\'].sum():,}) 不予提额, 共排除{df.loc[~df[\'是否可提额\'],\'提额客户\'].sum():,}"'
new = '"提额客群范围", "数值": "仅评级 A/B/C",\n     "说明": f"D/E 客群({df.loc[~df[\'等级可提\'],\'提额客户\'].sum():,}提额客户)不予提额, 未提额客户额度不变"'
assert old in src, "summary block not found"
src = src.replace(old, new)
old2 = '"数值": f"满档位可达{avg_b:,.0f}, 缩放至精确50,000"'
new2 = '"数值": f"满档位可达{avg_b:,.0f}, 缩放至精确50,000"'
src = src.replace(old2, new2)
open(r'E:\agent\monitor\risk_analysis\opt_plan_pdl_v3.py', 'w', encoding='utf-8').write(src)
print('ok')
