# -*- coding: utf-8 -*-
src = open(r'E:\agent\monitor\risk_analysis\opt_plan_pdl_v3.py', encoding='utf-8').read()
src = src.replace('"风险档", "档位提幅", "等级可提", "风险可提", "是否可提额",',
                  '"风险档", "档位提幅", "等级可提", "是否可提额",')
src = src.replace('"提幅", "额度", "风险档", "档位提幅", "等级可提", "风险可提", "是否可提额",',
                  '"提幅", "额度", "风险档", "档位提幅", "等级可提", "是否可提额",')
open(r'E:\agent\monitor\risk_analysis\opt_plan_pdl_v3.py', 'w', encoding='utf-8').write(src)
print('ok')
