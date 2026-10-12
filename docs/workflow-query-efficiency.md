# 工作流取数与计算效率优化

## 现状与依据

2026-10-11 模型计算节点日志显示总耗时约 83 分钟。分箱 SQL 约 35 分钟，Python 组装 198 个筛选切片约 6 分钟，组装后落库和发布约 13 分钟。其余时间包括其它聚合 SQL 和任务准备，不能都归因于下载。

现有计算已经将分区过滤、聚合、去重、窗口函数推到 MaxCompute，多个聚合 SQL 并行执行；不会下载整份原始客户数据。应先减少远端重复工作和本地重复转换，再根据分段日志继续调整。

## 已落实

1. 分箱 SQL 中 `ROW_NUMBER=1` 已保证每个日期、模型、客群、筛选范围内每个非空客户只保留一条记录。因此分箱客户数改用 `COUNT(*)`，避免再次执行 `COUNT(DISTINCT cid)`，保持原业务口径。
2. 日期到统计周的转换增加最多 2048 项缓存，避免按模型、目标和筛选组合重复解析相同日期。
3. 一次模型快照的切片更新和结果表插入放在一个 DuckDB 事务中，减少逐条自动提交；事务完成、检查点完成之后才原子发布。
4. `execute_sql` 改为 `run_sql` 提交后轮询，并调用 `wait_for_success` 保留失败处理。分别记录提交、远端执行、下载行数与耗时；组装、写入、提交、检查点也增加进度和耗时。

以上改动通过代码审查和语法检查。尚未用新版本执行完整的每日计算，因此没有声称实测提速比例；下一次正常调度日志可用于比较。

## SQL 与 Python 分工

| 阶段 | 执行位置 | 建议 |
| --- | --- | --- |
| 分区、日期、有效分数过滤 | MaxCompute SQL | 尽早过滤，仅选必要列 |
| 关联、去重、分组、分箱 | MaxCompute SQL | 保留精确业务口径；避免重复 DISTINCT |
| AUC/KS、成熟度、多个目标的指标组装 | Python | 只处理聚合结果，复用相同日期和维度转换 |
| 持久化业务结果 | DuckDB | Arrow/批量输入、一个事务、完整快照原子发布 |
| 页面展示 | 已发布 DuckDB | 只读结果；禁止请求触发上游计算 |

最新记录选择涉及有效分数、模型和筛选范围，不能随意提前到模型/客群展开之前，否则可能改变客户样本口径。也不采用近似分箱替换精确分箱。

## MaxFrame 选择

当前环境有 PyODPS、Pandas、PyArrow 和 DuckDB，没有安装 MaxFrame。MaxFrame 适合用 Pandas 风格表达复杂远端计算，`execute` 在远端执行、`fetch` 获取结果；它并不保证比等价 MaxCompute SQL 更快。现有计算已经由 SQL 下推，先优化执行计划和本地持久化更有依据，不为此次优化增加 MaxFrame 依赖。

参考：[MaxFrame 官方介绍](https://help.aliyun.com/en/maxcompute/maxframe-api-overview/)、[PyODPS SQL 执行与结果读取](https://pyodps.readthedocs.io/zh-cn/stable/base-sql.html)、[MaxFrame 数据读写](https://maxframe.readthedocs.io/en/latest/user_guide/dataframe/io.html)。
