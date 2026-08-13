# 配置文档.xlsx

工作表：Sheet1

## Sheet1
维度：14 行 × 7 列；冻结窗格：无

### 非空单元格（坐标 / 值 / 填充色）
A1=字段名 [fill=solid:rgb:FF2F75B5] | B1=字段含义 [fill=solid:rgb:FF2F75B5] | C1=备注 [fill=solid:rgb:FF2F75B5] | D1=免归因取值/条件 [fill=solid:rgb:FF2F75B5] | E1=强制单维下钻 [fill=solid:rgb:FF2F75B5] | F1=强制双维下钻 [fill=solid:rgb:FF2F75B5] | G1=强制三维下钻 [fill=solid:rgb:FF2F75B5]
A2=create_date | B2=申请授信日期/统计日期 | C2=用于窗口切分，不参与归因 | D2=不适用 | E2=否 | F2=否 | G2=否
A3=traffic_channel | B3=流量或业务入口渠道 | C3=待业务补充 | D3=traffic_channel = FLEXI_REPAYMENT_OPEN_PDL不归因
A4=systemtype | B4=设备操作系统类型 | C4=待业务补充
A5=device_brand | B5=设备品牌 | C5=待业务补充
A6=authen_type | B6=身份认证方式 | C6=待业务补充
A7=ios_install_sysup_gap_mins_flag | B7=iOS安装/系统更新时间差分层 | C7=iOS专属字段，需关注 none 口径 | D7=ios_install_sysup_gap_mins_flag=none 不归因
A8=reg_sx_days | B8=注册至授信申请间隔天数分层 | C8=0代表当天注册当天授信 | D8=reg_sx_days=10+ 不归因
A9=high_risk_birth | B9=高风险生日标识 | C9=具体业务定义待补充 | D9=high_risk_birth=0 不归因
A10=if_recommend_flag | B10=推荐/转介绍标识 | C10=具体业务定义待补充 | D10=if_recommend_flag=0 不归因
A11=state_name_clean | B11=州/地区 | C11=建议统一州名拼写 | E11=否 | F11=否 | G11=是：全量
A12=register_software | B12=注册软件/客户端来源 | C12=如PalmPay_IOS、PalmPay_Android | E12=是：PalmPay_IOS | F12=否 | G12=否
A13=first_channel | B13=首次来源渠道 | C13=待业务补充
A14=cnt | B14=该维度组合下申请授信量 | C14=统计权重，不参与归因 | D14=不适用 | E14=否 | F14=否 | G14=否

非空单元格数量：65