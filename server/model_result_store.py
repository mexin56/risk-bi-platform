"""Published model monitoring business results; page readers never query upstream."""
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import time
import uuid

import duckdb
import pandas as pd
from fastapi import HTTPException
from model_monitoring import MODEL_SCORES, TARGET_FIELDS
from pipeline.business_results import system_database_path

ROOT = Path(__file__).resolve().parent
DIMENSIONS = ('flag_mob_type', 'flag_product', 'cash_ser_call_node')
BASE = {'pt': 'VARCHAR', **{key:'VARCHAR' for key in DIMENSIONS}, 'generated_at':'VARCHAR'}
SCHEMAS = {
    'model_summary': {'row_count':'BIGINT','business_cnt':'BIGINT','cid_cnt':'BIGINT', **{key:'VARCHAR' for key in ('min_create_time','max_create_time','min_event_date','max_event_date','min_loan_date','max_loan_date')}},
    'model_coverage': {'field':'VARCHAR','model':'VARCHAR','nonempty':'BIGINT','sentinel':'BIGINT','valid':'BIGINT','coverage':'DOUBLE'},
    'model_effect_weekly': {**{key:'VARCHAR' for key in ('week_start','week_end','alias','model','target')}, **{key:'BIGINT' for key in ('count','mature_count','bad_count','good_count','score_valid_count')}, **{key:'DOUBLE' for key in ('badrate','auc','ks','score_coverage','maturity_ratio')},'maturity_warning':'BOOLEAN'},
    'model_stability_weekly': {**{key:'VARCHAR' for key in ('week_start','week_end','alias','model','target','bin_label')}, **{key:'BIGINT' for key in ('bin','customer_count','samples','target_base','target_bad')}, **{key:'DOUBLE' for key in ('customer_share','approval_rate','loan_success_rate','badrate')}, 'maturity_warning':'BOOLEAN'},
    'model_cohort_trend': {**{key:'VARCHAR' for key in ('day','alias','model','bin_label')}, 'bin':'BIGINT','customer_count':'BIGINT','customer_share':'DOUBLE'},
}
MODEL_RESULT_TABLES = ('model_dashboard','model_filters',*SCHEMAS)


def source_database():
    return ROOT / 'data/model_serving/results.duckdb'


def published_database():
    return system_database_path(ROOT / 'data/serving')


def compact_payload(payload):
    return {key: ([] if key in {'daily_trend','model_effect_trend','latest_model_effect','model_score_stability_weekly','model_score_cohort_trend'} else value) for key,value in payload.items()}


def _dump(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))


def _insert_rows(conn, table, rows):
    if not rows:return
    columns=list(BASE)+list(SCHEMAS[table])
    frame=pd.DataFrame(rows).reindex(columns=columns)
    conn.register('incoming_business',frame)
    try:conn.execute(f'INSERT INTO {table} BY NAME SELECT * FROM incoming_business')
    finally:conn.unregister('incoming_business')


def write_results(database, history_filters=(), history_dashboards=(), *, new_filters=None, slices=None, source='myworkflow'):
    """Replace each completed slice atomically and keep all published history."""
    database=Path(database);database.parent.mkdir(parents=True,exist_ok=True)
    temporary=database.parent / f'.model-{uuid.uuid4().hex}.duckdb'
    with database.with_suffix('.write.lock').open('a') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        started=time.monotonic()
        if database.exists():shutil.copy2(database,temporary)
        print(f'[model] snapshot copy completed, elapsed={time.monotonic()-started:.1f}s',flush=True)
        conn=duckdb.connect(str(temporary),config={'threads':'2'})
        try:
            base_sql=', '.join(f'{key} {kind}' for key,kind in BASE.items())
            conn.execute(f'CREATE TABLE IF NOT EXISTS model_dashboard ({base_sql}, compute_source VARCHAR, score_ready BOOLEAN, payload VARCHAR, page_payload VARCHAR, meta_payload VARCHAR)')
            conn.execute('CREATE TABLE IF NOT EXISTS model_filters (pt VARCHAR PRIMARY KEY, generated_at VARCHAR, payload VARCHAR)')
            for table,schema in SCHEMAS.items():
                conn.execute(f'CREATE TABLE IF NOT EXISTS {table} ({base_sql}, '+', '.join(f'"{key}" {kind}' for key,kind in schema.items())+')')
            # All rows form one snapshot. Avoid thousands of autocommit/WAL flushes.
            conn.execute('BEGIN TRANSACTION')
            write_started=time.monotonic()
            existing={tuple(row) for row in conn.execute('SELECT pt, flag_mob_type, flag_product, cash_ser_call_node FROM model_dashboard').fetchall()}
            historical={}
            for payload in history_dashboards:
                meta=payload['meta'];filters=meta.get('filters') or {}
                key=(meta['partition'],*(filters.get(name,'') for name in DIMENSIONS))
                # Prefer the complete all-model cache over a selected-model cache.
                previous=historical.get(key)
                if previous is None or len(payload.get('model_effect_weekly',[]))>len(previous.get('model_effect_weekly',[])):historical[key]=payload
            updates=[]
            for key,payload in historical.items():
                if key not in existing:updates.append((key,payload,[],[],False,'cache-migration'))
            for scope,values in (slices or {}).items():
                payload,stability,cohort=values
                updates.append(((payload['meta']['partition'],*scope),payload,stability,cohort,True,source))
            now=datetime.now(timezone.utc).isoformat()
            for filters in [*history_filters,*([new_filters] if new_filters else [])]:
                conn.execute('INSERT OR REPLACE INTO model_filters VALUES (?,?,?)',[filters['partition'],now,_dump(filters)])
            predicate='pt=? AND flag_mob_type=? AND flag_product=? AND cash_ser_call_node=?'
            for update_index,(key,payload,stability,cohort,ready,origin) in enumerate(updates,1):
                for table in ('model_dashboard',*SCHEMAS):conn.execute(f'DELETE FROM {table} WHERE {predicate}',list(key))
                meta=payload['meta'];meta.update(result_store='duckdb',compute_source=origin,score_ready=ready)
                generated=meta.get('generated_at') or now
                conn.execute('INSERT INTO model_dashboard VALUES (?,?,?,?,?,?,?,?,?,?)',[*key,generated,origin,ready,_dump(payload),_dump(compact_payload(payload)),_dump(meta)])
                base=dict(zip(BASE,(*key,generated)))
                collections={'model_summary':[payload['summary']], 'model_coverage':payload['model_coverage'], 'model_effect_weekly':payload.get('model_effect_weekly',[]), 'model_stability_weekly':stability,'model_cohort_trend':cohort}
                for table,rows in collections.items():_insert_rows(conn,table,[{**base,**row} for row in rows])
                if update_index % 25 == 0:
                    print(f'[model] snapshot writing slices={update_index}/{len(updates)}, elapsed={time.monotonic()-write_started:.1f}s',flush=True)
            for table in ('model_dashboard',*SCHEMAS):
                conn.execute(f'CREATE INDEX IF NOT EXISTS {table}_scope ON {table}(pt,flag_mob_type,flag_product,cash_ser_call_node)')
            for table in ('model_stability_weekly','model_cohort_trend'):
                conn.execute(f'CREATE INDEX IF NOT EXISTS {table}_model ON {table}(pt,model,alias)')
            conn.execute('COMMIT')
            print(f'[model] snapshot transaction committed, slices={len(updates)}, elapsed={time.monotonic()-write_started:.1f}s',flush=True)
            checkpoint_started=time.monotonic()
            conn.execute('CHECKPOINT');conn.close();conn=None
            print(f'[model] snapshot checkpoint completed, elapsed={time.monotonic()-checkpoint_started:.1f}s',flush=True)
            os.replace(temporary,database)
        finally:
            if conn is not None:conn.close()
            temporary.unlink(missing_ok=True)
            temporary.with_suffix('.duckdb.wal').unlink(missing_ok=True)


def publish_results():
    from pipeline.business_results import publish_system_database
    return publish_system_database(ROOT / 'data/serving')


def _connect():
    path=published_database()
    if not path.exists():raise HTTPException(503,'模型监控结果尚未发布，请在 MyWorkflow 运行模型监控工作流。')
    conn=duckdb.connect(str(path),read_only=True)
    if not conn.execute("SELECT count(*) FROM information_schema.tables WHERE table_name='model_dashboard'").fetchone()[0]:
        conn.close();raise HTTPException(503,'模型监控结果尚未发布，请在 MyWorkflow 运行模型监控工作流。')
    return conn


def _partition(conn,pt):
    if pt:
        import re
        if not re.fullmatch(r'\d{8}',pt):raise HTTPException(422,'分区格式必须为 YYYYMMDD。')
        return pt
    row=conn.execute("SELECT max(pt) FROM model_dashboard WHERE flag_mob_type='' AND flag_product='' AND cash_ser_call_node='' AND score_ready").fetchone()
    value=row[0] or conn.execute('SELECT max(pt) FROM model_dashboard').fetchone()[0]
    if not value:raise HTTPException(503,'模型监控尚无已发布结果。')
    return value


def _scope(conn,pt,scope):
    row=conn.execute('SELECT generated_at,score_ready,meta_payload FROM model_dashboard WHERE pt=? AND flag_mob_type=? AND flag_product=? AND cash_ser_call_node=?',[pt,*scope]).fetchone()
    if row is None:raise HTTPException(503,'该筛选组合尚无已发布结果，请在 MyWorkflow 运行模型监控工作流。')
    return row


def read_filters(pt=None):
    conn=_connect()
    try:
        pt=_partition(conn,pt)
        row=conn.execute('SELECT payload FROM model_filters WHERE pt=?',[pt]).fetchone()
        if not row:raise HTTPException(503,'该分区筛选目录尚未发布。')
        payload=json.loads(row[0]);payload['meta']={'result_store':'duckdb','partition':pt}
        return payload
    finally:conn.close()


def read_dashboard(pt=None,scope=('','',''),model='',compact=False):
    conn=_connect()
    try:
        pt=_partition(conn,pt)
        column='page_payload' if compact else 'payload'
        row=conn.execute(f'SELECT {column} FROM model_dashboard WHERE pt=? AND flag_mob_type=? AND flag_product=? AND cash_ser_call_node=?',[pt,*scope]).fetchone()
        if row is None:raise HTTPException(503,'该筛选组合尚无已发布结果，请在 MyWorkflow 运行模型监控工作流。')
        payload=json.loads(row[0])
        if model:
            for field in ('model_effect_weekly','model_effect_trend','latest_model_effect'):
                payload[field]=[item for item in payload.get(field,[]) if item.get('model')==model]
        return payload
    finally:conn.close()


def read_score(model,alias='',target='fpd7',pt=None,scope=('','','')):
    conn=_connect()
    try:
        pt=_partition(conn,pt)
        generated,ready,raw=_scope(conn,pt,scope)
        if not ready:raise HTTPException(503,'该历史分区未发布稳定性和客群结果，请在 MyWorkflow 补算对应分区。')
        conditions='pt=? AND flag_mob_type=? AND flag_product=? AND cash_ser_call_node=? AND model=?'
        params=[pt,*scope,model]
        if alias:conditions+=' AND alias=?';params.append(alias)
        def rows(table,extra='',values=()):
            cursor=conn.execute(f'SELECT * FROM {table} WHERE {conditions}{extra}',[*params,*values])
            names=[col[0] for col in cursor.description]
            return [{key:value for key,value in zip(names,row) if key not in BASE} for row in cursor.fetchall()]
        meta=json.loads(raw)
        return {'meta':{**meta,'generated_at':generated,'model':model,'alias':alias,'target':target,'lookback_days':30,'qcut_rule':'当前 pt 最近 30 天内按业务环节和模型分固定 qcut10，Q1 为低分段，Q10 为高分段'},'model_score_stability_weekly':rows('model_stability_weekly',' AND target=?',[target]),'model_score_cohort_trend':rows('model_cohort_trend')}
    finally:conn.close()
