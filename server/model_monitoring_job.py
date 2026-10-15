"""Offline model monitoring: batch all label slices and publish business results.

Only the scheduler invokes this module. Page APIs read model_result_store.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import itertools
import json
import os
from pathlib import Path
import re
import signal
import sys
import threading
import time

# A migration can compute against the live service configuration into a staged file.
if os.environ.get('MODEL_COMPUTE_SERVER_ROOT'):
    sys.path.insert(0, os.environ['MODEL_COMPUTE_SERVER_ROOT'])
from app import AttributionService, MODEL_MONITOR_DISK_CACHE_DIR, SAFE_PARTITION, json_safe
from model_monitoring import MODEL_SCORES, TARGET_FIELDS, CASH_SER_CALL_NODE_OPTIONS, build_monitoring_payload, build_model_score_stability_weekly, build_model_score_cohort_trend

DIMENSIONS = ('flag_mob_type', 'flag_product', 'cash_ser_call_node')
SCOPE_COLUMNS = ('__mob_filter', '__product_filter', '__node_filter')
ACTIVE_SERVICE = None


def scope_of(row):
    return tuple(str(row.pop(key) or '') for key in SCOPE_COLUMNS)


class BatchModelService(AttributionService):
    """Use the existing business SQL and add CUBE to compute every filter slice."""
    def __init__(self):
        super().__init__()
        self.grouped = defaultdict(dict)
        self.group_lock = threading.Lock()
        self.label_rows = []
        self.active_instances = set()
        self.extra_query_rows: dict[str, list] = {}

    def _run_extra_query(self, sink, name, sql):
        """Run a heavy extra SQL through the same pool and keep its raw rows."""
        rows = self._remote_rows(sql, name)
        sink[name] = rows
        return rows

    def _remote_rows(self, sql, label):
        started=time.monotonic()
        # Submit without blocking so the task exposes its instance and can cancel it.
        instance = self._odps().run_sql(sql)
        with self.group_lock:self.active_instances.add(instance)
        print(f'[model] upstream query submitted: {label}, instance={instance.id}',flush=True)
        submitted=time.monotonic();last_report=submitted
        try:
            while not instance.is_terminated(retry=True):
                time.sleep(5)
                now=time.monotonic()
                if now-last_report >= 60:
                    print(f'[model] upstream query running: {label}, elapsed={now-started:.0f}s',flush=True)
                    last_report=now
            instance.wait_for_success()
            completed=time.monotonic()
            with instance.open_reader(tunnel=True,limit=False) as reader:
                columns=[column.name for column in reader.schema.columns]
                rows=[{name:record[index] for index,name in enumerate(columns)} for record in reader]
            print('[model] query performance: '+json.dumps({'query':label,'instance':instance.id,
                'submit_seconds':round(submitted-started,3),'execute_seconds':round(completed-submitted,3),
                'download_seconds':round(time.monotonic()-completed,3),'rows':len(rows)},ensure_ascii=False),flush=True)
            return rows
        finally:
            with self.group_lock:self.active_instances.discard(instance)

    def cancel(self):
        with self.group_lock:instances=list(self.active_instances)
        for instance in instances:
            try:instance.stop()
            except Exception:pass

    def _save_model_monitor_disk_cache(self, *args, **kwargs):
        # A scheduler publishes one complete business snapshot instead of page caches.
        pass

    def _run_sql_rows(self, sql):
        if 'AS row_count' in sql:
            kind = 'overview'
        elif 'AS business_type' in sql:
            kind = 'business'
        elif 'AS band_order' in sql:
            kind = 'score'
        elif 'AS score_valid_cnt' in sql:
            kind = 'model_effect'
        elif 'AS alias' in sql:
            kind = 'alias_daily'
        elif 'AS applications' in sql:
            kind = 'daily'
        else:
            rows = self._remote_rows(sql,'labels')
            self.label_rows = rows
            return rows
        # Normalize dimensions once so GROUPING has simple column arguments.
        table = self.model_monitoring_table_name
        dimension_select = ', '.join(f"COALESCE(CAST({name} AS STRING), '未知') AS __dim_{index}" for index,name in enumerate(DIMENSIONS))
        partition = re.search(r"pt\s*=\s*'([0-9]{8})'", sql).group(1)
        sql = sql.replace('FROM '+table, f"FROM (SELECT *, {dimension_select} FROM {table} WHERE pt = '{partition}') model_source", 1)
        selections = ', '.join(f"CASE WHEN GROUPING(__dim_{index}) = 1 THEN '' ELSE __dim_{index} END AS {key}, GROUPING(__dim_{index}) AS __group_{index}" for index,key in enumerate(SCOPE_COLUMNS))
        sql = re.sub(r'\bSELECT\b', 'SELECT '+selections+', ', sql, count=1, flags=re.I)
        cube = 'CUBE(__dim_0, __dim_1, __dim_2)'
        order = re.search(r'\bORDER\s+BY\b', sql, flags=re.I)
        head, tail = (sql[:order.start()], sql[order.start():]) if order else (sql, '')
        if re.search(r'\bGROUP\s+BY\b', head, flags=re.I):
            sql = head.rstrip()+', '+cube+'\n'+tail
        else:
            sql = head.rstrip()+'\nGROUP BY '+cube+'\n'+tail
        started=time.monotonic()
        print(f'[model] aggregation started: {kind}', flush=True)
        rows = self._remote_rows(sql,kind)
        by_scope=defaultdict(list)
        for row in rows:
            scope=scope_of(row)
            grouping=tuple(row.pop(f'__group_{index}') for index in range(3))
            # Empty-string labels have no distinct UI filter. Keep their rows in
            # rollups, but never let a literal empty group overwrite an all slice.
            if any(not grouping[index] and not scope[index] for index in range(3)):continue
            by_scope[scope].append(row)
        with self.group_lock:
            for scope, values in by_scope.items():self.grouped[scope][kind]=values
        print(f'[model] aggregation completed: {kind}, scopes={len(by_scope)}, elapsed={time.monotonic()-started:.1f}s',flush=True)
        return by_scope.get(('', '', ''), [])


def qcut_sql(table, partition):
    """Deduplicate within each slice, then fix qcut10 per slice/model/alias."""
    lookback=(datetime.strptime(partition,'%Y%m%d').date()-timedelta(days=30)).isoformat()
    scores=', '.join(f"'{field}', CAST({field} AS STRING)" for field,_ in MODEL_SCORES)
    scope_expressions=[]
    for index,name in enumerate(DIMENSIONS):
        masks=', '.join(str(mask) for mask in range(8) if mask & (1<<index))
        scope_expressions.append(f"CASE WHEN scope_mask IN ({masks}) THEN COALESCE(CAST({name} AS STRING), '未知') ELSE '' END AS {SCOPE_COLUMNS[index]}")
    scope_names=', '.join(SCOPE_COLUMNS)
    scope_expanded=', '.join(scope_expressions)
    sums=', '.join(f'SUM(CASE WHEN {target}_fm_dd = 1 THEN 1 ELSE 0 END) AS {target}_base, SUM(CASE WHEN {target}_fz_dd = 1 THEN 1 ELSE 0 END) AS {target}_bad' for target in TARGET_FIELDS)
    raw_targets=', '.join(f'{target}_fm_dd, {target}_fz_dd' for target in TARGET_FIELDS)
    return f"""
SELECT {scope_names}, day, alias, model, qcut_bin AS bin,
       COUNT(*) AS customer_count, COUNT(*) AS samples,
       SUM(CASE WHEN approval_result IS NOT NULL AND approval_result <> '' THEN 1 ELSE 0 END) AS approval_labeled,
       SUM(CASE WHEN approval_result = '1.0' THEN 1 ELSE 0 END) AS approved,
       SUM(CASE WHEN if_loan_success IS NOT NULL THEN 1 ELSE 0 END) AS loan_labeled,
       SUM(CASE WHEN if_loan_success = 1 THEN 1 ELSE 0 END) AS loan_success,
       {sums}
FROM (
    SELECT customer_candidates.*,
           NTILE(10) OVER (PARTITION BY {scope_names}, alias, model ORDER BY score_value, CAST(cid AS STRING), CAST(businessid AS STRING)) AS qcut_bin
    FROM (
        SELECT sliced.*,
               ROW_NUMBER() OVER (PARTITION BY day, alias, cid, model, {scope_names} ORDER BY create_time DESC, CAST(businessid AS STRING) DESC) AS customer_row_number
        FROM (
            SELECT {', '.join(scope_expressions)}, event_date AS day,
                   COALESCE(CAST(alias AS STRING), '未知') AS alias, cid, businessid, create_time,
                   model, CAST(score_value AS DOUBLE) AS score_value,
                   approval_result, if_loan_success, {raw_targets}
            FROM {table}
            LATERAL VIEW EXPLODE(MAP({scores})) model_expanded AS model, score_value
            LATERAL VIEW EXPLODE(ARRAY(0,1,2,3,4,5,6,7)) scopes_expanded AS scope_mask
            WHERE pt = '{partition}' AND event_date IS NOT NULL AND event_date >= '{lookback}'
              AND cid IS NOT NULL AND score_value IS NOT NULL AND score_value <> '' AND CAST(score_value AS DOUBLE) >= 0
        ) sliced
    ) customer_candidates
    WHERE customer_row_number = 1
) scored
GROUP BY {scope_names}, day, alias, model, qcut_bin
"""


def overview_distinct_sql(table, partition, subset):
    """只对 subset 指定的维度做 COUNT(DISTINCT)，其余维度输出空串。

    CUBE 会把 DISTINCT 放大到 116 个切片（全分区 329s~1455s），而按维度子集
    分组时单条只需 10~50s；8 个子集并行提交后总墙钟 = 最慢的一条。
    """
    dims=', '.join(f"COALESCE(CAST({name} AS STRING), '未知') AS __dim_{index}" for index,name in enumerate(DIMENSIONS))
    selected=[index for index in range(len(DIMENSIONS)) if subset >> index & 1]
    labels=[]
    for index,key in enumerate(SCOPE_COLUMNS):
        if index in selected:
            labels.append(f"__dim_{index} AS {key}")
        else:
            labels.append(f"CAST('' AS STRING) AS {key}")
    group=', '.join(f"__dim_{index}" for index in selected)
    # subset=0 即全量切片：不带 GROUP BY，直接返回一行。
    group_clause=f'\nGROUP BY {group}' if selected else ''
    return f"""
SELECT {', '.join(labels)},
       COUNT(DISTINCT businessid) AS business_cnt,
       COUNT(DISTINCT cid) AS cid_cnt
FROM (SELECT *, {dims} FROM {table} WHERE pt = '{partition}') model_source{group_clause}
"""


def smoke_test_sqls(queries):
    """用不存在的分区重发每条 SQL，只验语法/语义，秒级返回。

    上游 SQL 一旦写错，线程池会等最慢那条（50 分钟）才报错；这里先把错误挡在提交前。
    """
    from concurrent.futures import ThreadPoolExecutor
    service=BatchModelService()
    def check(item):
        name,sql=item
        probe=re.sub(r"pt\s*=\s*'\d{8}'","pt = '19000101'",sql)
        probe=re.sub(r"pt\s*=\s*\d{8}","pt = 19000101",probe)
        instance=service._odps().run_sql(probe)
        instance.wait_for_success()
        return name
    with ThreadPoolExecutor(max_workers=len(queries)) as executor:
        return list(executor.map(check,queries.items()))


def compute_partition(partition):
    global ACTIVE_SERVICE
    if not re.fullmatch(r'\d{8}',partition):raise ValueError('pt must be YYYYMMDD')
    service=BatchModelService()
    ACTIVE_SERVICE=service
    partitions=service.model_monitoring_partitions()
    if partition not in partitions:
        print(f'[model] upstream partition not ready: requested={partition}, latest={partitions[0] if partitions else "none"}',flush=True)
        raise ValueError('Requested upstream partition is not ready')
    # qcut10 与其余聚合同批并行提交：它本身就是最长的一杆，串行等会把总时长翻倍。
    qcut_sql_text=qcut_sql(service.model_monitoring_table_name,partition)
    distinct_queries={f'overview_distinct_{mask}':overview_distinct_sql(service.model_monitoring_table_name,partition,mask) for mask in range(8)}
    if os.environ.get('RISK_BI_SQL_SMOKE')=='1':
        checked=smoke_test_sqls({'qcut10':qcut_sql_text,**distinct_queries})
        print(f'[model] sql smoke test passed: {len(checked)} queries',flush=True)
    service.model_monitoring(partition=partition,force=True,overview_distinct=False,
        extra_queries={'qcut10':qcut_sql_text,**distinct_queries})
    # 回填精确去重数：CUBE 查询里已置零，按维度子集的结果按标签三元组写回。
    filled=0
    for name,rows in service.extra_query_rows.items():
        if not name.startswith('overview_distinct_'):continue
        for row in rows:
            scope=tuple(str(row.pop(key) or '') for key in SCOPE_COLUMNS)
            buckets=service.grouped.get(scope,{}).get('overview')
            if not buckets:continue
            for bucket in buckets:
                if row.get('business_cnt') is not None:bucket['business_cnt']=row['business_cnt']
                if row.get('cid_cnt') is not None:bucket['cid_cnt']=row['cid_cnt']
            filled+=1
    print(f'[model] overview distinct backfilled: scopes={filled}',flush=True)
    filters={'partition':partition,
             'flag_mob_type_options':sorted({str(row.get('flag_mob_type') or '未知') for row in service.label_rows}),
             'flag_product_options':sorted({str(row.get('flag_product') or '未知') for row in service.label_rows}),
             'cash_ser_call_node_options':list(CASH_SER_CALL_NODE_OPTIONS)}
    print('[model] qcut10 all-model/all-slice aggregation started',flush=True)
    started=time.monotonic()
    qcuts=defaultdict(list)
    for row in service.extra_query_rows.get('qcut10', []):
        qcuts[scope_of(row)].append(row)
    print(f'[model] qcut10 aggregation completed, scopes={len(qcuts)}, elapsed={time.monotonic()-started:.1f}s',flush=True)
    # ROW_NUMBER above keeps one non-null cid per day/model/alias/scope. COUNT(*)
    # therefore equals COUNT(DISTINCT cid) in each final bin without another hash set.
    slices={}
    materialize_started=time.monotonic()
    # Keep observed business combinations as well as every selectable UI slice.
    scopes=sorted(set(itertools.product(*[('',*filters[name+'_options']) for name in DIMENSIONS])) | set(service.grouped))
    for scope_index,scope in enumerate(scopes,1):
        rows=service.grouped.get(scope,{})
        overview=rows.get('overview') or []
        payload=build_monitoring_payload(overview=overview[0] if overview else {}, business_rows=rows.get('business',[]),
            daily_rows=rows.get('daily',[]),score_band_rows=rows.get('score',[]),
            model_effect_rows=rows.get('model_effect',[]),alias_daily_rows=rows.get('alias_daily',[]),
            flag_mob_type_options=filters['flag_mob_type_options'],flag_product_options=filters['flag_product_options'],
            cash_ser_call_node_options=filters['cash_ser_call_node_options'],
            selected_flag_mob_type=scope[0],selected_flag_product=scope[1],selected_cash_ser_call_node=scope[2],
            partition=partition,table_name=service.model_monitoring_table_name)
        score_rows=qcuts.get(scope,[])
        stability=[row for target in TARGET_FIELDS for row in build_model_score_stability_weekly(score_rows,target=target)]
        cohort=build_model_score_cohort_trend(score_rows)
        slices[scope]=(json_safe(payload),json_safe(stability),json_safe(cohort))
        if scope_index % 25 == 0:
            print(f'[model] materializing slices={scope_index}/{len(scopes)}, elapsed={time.monotonic()-materialize_started:.1f}s',flush=True)
    if ('','','') not in slices:raise RuntimeError('No default model result was computed')
    print(f'[model] materialized slices={len(slices)}, elapsed={time.monotonic()-materialize_started:.1f}s',flush=True)
    return filters,slices


def cached_partitions():
    """Import existing business caches without recomputation or upstream requests."""
    dashboards=[];filters=[]
    for path in sorted(MODEL_MONITOR_DISK_CACHE_DIR.glob('*.json')):
        try:
            raw=json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            print('[model] skipped unreadable historical cache',flush=True)
            continue
        payload=raw.get('payload')
        if not isinstance(payload,dict):continue
        if 'flag_mob_type_options' in payload and payload.get('partition'):
            filters.append(payload)
        elif payload.get('meta',{}).get('partition') and 'model_coverage' in payload:
            dashboards.append(payload)
    return filters,dashboards


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['run','import-cache','publish'])
    parser.add_argument('--pt',default='')
    parser.add_argument('--source',default='myworkflow')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--no-publish',action='store_true')
    args=parser.parse_args()
    # Import local modules explicitly when a migration uses the live app module.
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from model_result_store import source_database,write_results,publish_results
    database=args.output or source_database()
    if args.action=='publish':
        if args.output or args.no_publish:parser.error('publish does not accept --output or --no-publish')
        if not database.is_file():
            print('[model] no completed model snapshot is available',flush=True)
            raise RuntimeError('Model snapshot is missing')
        import duckdb
        with duckdb.connect(str(database),read_only=True) as conn:
            ready=conn.execute("SELECT count(*) FROM model_dashboard WHERE score_ready AND flag_mob_type='' AND flag_product='' AND cash_ser_call_node=''").fetchone()[0]
        if not ready:
            print('[model] full model computation must finish before publishing',flush=True)
            raise RuntimeError('Model score results are missing')
        print('[model] publishing completed business snapshot',flush=True)
        publish_results()
        print('[model] business results published',flush=True)
        return
    history_filters,history_dashboards=cached_partitions()
    if args.action=='import-cache':
        write_results(database,history_filters,history_dashboards,source='cache-migration')
    else:
        filters,slices=compute_partition(args.pt)
        write_results(database,history_filters,history_dashboards,new_filters=filters,slices=slices,source=args.source)
    print('[model] business snapshot ready',flush=True)
    if not args.no_publish and not args.output:publish_results()


if __name__=='__main__':
    def cancelled(signum,frame):
        if ACTIVE_SERVICE is not None:ACTIVE_SERVICE.cancel()
        print('[model] cancelled; active upstream queries stopped',flush=True)
        raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM,cancelled)
    signal.signal(signal.SIGINT,cancelled)
    try:main()
    except Exception as exc:
        # Upstream connection failures must not print credentials or connection reprs.
        print('[model] failed: '+type(exc).__name__,file=sys.stderr,flush=True)
        raise SystemExit(1) from None
