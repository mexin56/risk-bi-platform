# Task 2 实施报告

状态：DONE

代码提交：`bacca39 feat: add read-only attribution query tools`

## 完成内容

- 新增 `server/attribution_query_tools.py`。
- 实现统一 `duckdb/serving` envelope，并保证返回值可 JSON 序列化。
- 仅暴露七个固定只读工具：`latest_partition`、`dashboard_summary`、`find_rules`、`rule_detail`、`path_trend`、`tracked_rule_followup`、`compare_partitions`。
- 查询复用注入服务的 `dashboard(..., force=False, offset=0)` 与 `path_trend(...)`，没有导入 MaxCompute 客户端、执行任意 SQL或调用状态写入方法。
- 实现规则过滤与详情匹配、7/15/30/60 天趋势截取、缺失快照/趋势/规则的结构化错误、跟踪规则逐分区查询和分区对比。
- 新增 `add_approval_rates`，按 `approval_cid_cnt / cid_cnt` 计算“通过率（人数）”，按 `approval_cnt / cnt`（兼容趋势字段名）计算“通过率（件数）”；分母为 0 时返回 `None` 和 warning。

## 验证命令与输出

命令：

```text
python -m pytest server/test_attribution_query_tools.py -q
```

输出：

```text
....................                                                     [100%]
20 passed in 0.09s
```

命令：

```text
$env:PYTEST_ADDOPTS='--basetemp=.pytest_tmp_task2_required'; python -m pytest server/test_path_trend_duckdb.py server/test_person_approval_rate.py -q
```

输出：

```text
....                                                                     [100%]
4 passed in 1.71s
```

说明：第二条命令首次运行时，pytest 默认临时目录 `C:\Users\PP-2026070302\AppData\Local\Temp\pytest-of-PP-2026070302` 返回 `WinError 5`。将 `basetemp` 定向到工作区后原测试命令全部通过，该问题与代码或断言无关。

附加校验：

```text
python -m py_compile server/attribution_query_tools.py server/test_attribution_query_tools.py
git diff --cached --check
```

均以退出码 0 完成；提交前暂存区仅包含上述两个 Task 2 文件。
