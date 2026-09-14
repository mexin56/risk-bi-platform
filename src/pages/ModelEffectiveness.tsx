import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import {
  fetchModelMonitoring,
  type ModelEffectWeekly,
  type ModelMonitoringPayload,
  type TargetMetric,
} from '@/lib/modelMonitoringApi';
import { metricTone } from '@/lib/modelEffectTable';

const numberFormat = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 });
const targetLabels: Record<TargetMetric, string> = {
  fpd7: 'FPD7',
  fpd30: 'FPD30',
  term3: 'TERM3',
};

function formatTableValue(kind: 'count' | 'badrate' | 'metric', value: number | null | undefined): string {
  if (value == null) return '';
  if (kind === 'count') return numberFormat.format(value);
  if (kind === 'badrate') return `${(value * 100).toFixed(2)}%`;
  return value.toFixed(3);
}

function formatDateGroup(value: string): string {
  return value.replace(/-/g, '').slice(0, 8);
}

function aliasesFor(payload: ModelMonitoringPayload): string[] {
  return payload.model_effect_aliases?.length
    ? payload.model_effect_aliases
    : [...new Set(payload.model_effect_weekly?.map((row) => row.alias) ?? [])].sort();
}

function weeklyRowsFor(payload: ModelMonitoringPayload, alias: string, target: TargetMetric): ModelEffectWeekly[] {
  return (payload.model_effect_weekly ?? []).filter((row) => row.alias === alias && row.target === target);
}

function LoadingState() {
  return (
    <div className="flex min-h-[520px] items-center justify-center bg-[#f5f7fa] text-[14px] text-slate-500">
      <RefreshCw size={16} className="mr-2 animate-spin" />
      正在读取模型效果数据…
    </div>
  );
}

function WeeklyEffectTable({ payload, alias, target }: { payload: ModelMonitoringPayload; alias: string; target: TargetMetric }) {
  const rows = useMemo(() => weeklyRowsFor(payload, alias, target), [payload, alias, target]);
  const weeks = useMemo(
    () => [...new Set(rows.map((row) => row.week_start))].sort((left, right) => right.localeCompare(left)),
    [rows],
  );
  const models = useMemo(
    () => payload.model_coverage.filter((row) => row.valid > 0).sort((left, right) => left.field.localeCompare(right.field)),
    [payload.model_coverage],
  );
  const rowByKey = useMemo(
    () => new Map(rows.map((row) => [`${row.model}|${row.week_start}`, row])),
    [rows],
  );

  if (!alias) {
    return <div className="rounded-lg border border-slate-200 bg-white px-4 py-10 text-center text-[14px] text-slate-500">暂无业务环节数据</div>;
  }

  if (!weeks.length) {
    return <div className="rounded-lg border border-slate-200 bg-white px-4 py-10 text-center text-[14px] text-slate-500">当前业务环节暂无可展示的模型效果数据</div>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="min-w-[1840px] w-full border-separate border-spacing-0 text-[12px] text-slate-700">
        <thead>
          <tr>
            <th rowSpan={2} className="sticky left-0 top-0 z-30 w-[220px] min-w-[220px] border-b border-r border-slate-200 bg-white px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500 shadow-[8px_0_16px_-16px_rgba(15,23,42,0.6)]">模型编码</th>
            <th rowSpan={2} className="sticky left-[220px] top-0 z-30 w-[148px] min-w-[148px] border-b border-r border-slate-200 bg-white px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500 shadow-[8px_0_16px_-16px_rgba(15,23,42,0.6)]">模型名称</th>
            {weeks.map((week) => (
              <th key={week} colSpan={4} className="border-b border-r border-slate-200 bg-[#e9eff7] px-3 py-3 text-center text-[12px] font-semibold tracking-[0.04em] text-slate-700">{formatDateGroup(week)}</th>
            ))}
          </tr>
          <tr>
            {weeks.flatMap((week) => [
              <th key={`${week}-count`} className="sticky top-[42px] z-20 w-[92px] min-w-[92px] border-b border-r border-slate-200 bg-[#f6f8fb] px-3 py-2 text-center text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-500">count</th>,
              <th key={`${week}-badrate`} className="sticky top-[42px] z-20 w-[92px] min-w-[92px] border-b border-r border-slate-200 bg-[#f6f8fb] px-3 py-2 text-center text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-500">badrate</th>,
              <th key={`${week}-auc`} className="sticky top-[42px] z-20 w-[92px] min-w-[92px] border-b border-r border-slate-200 bg-[#f6f8fb] px-3 py-2 text-center text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-500">AUC</th>,
              <th key={`${week}-ks`} className="sticky top-[42px] z-20 w-[92px] min-w-[92px] border-b border-r border-slate-200 bg-[#f6f8fb] px-3 py-2 text-center text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-500">KS</th>,
            ])}
          </tr>
        </thead>
        <tbody>
          {models.map((model, index) => (
            <tr key={model.field} className="group hover:bg-[#eff6ff]">
              <td className={`sticky left-0 z-10 w-[220px] min-w-[220px] border-b border-r border-slate-200 px-4 py-2.5 align-middle font-mono text-[11px] text-slate-600 shadow-[8px_0_16px_-16px_rgba(15,23,42,0.6)] ${index % 2 === 0 ? 'bg-white' : 'bg-[#f8fafc]'} group-hover:bg-[#eff6ff]`}>{model.field}</td>
              <td className={`sticky left-[220px] z-10 w-[148px] min-w-[148px] border-b border-r border-slate-200 px-4 py-2.5 align-middle font-medium text-slate-800 shadow-[8px_0_16px_-16px_rgba(15,23,42,0.6)] ${index % 2 === 0 ? 'bg-white' : 'bg-[#f8fafc]'} group-hover:bg-[#eff6ff]`}>{model.model}</td>
              {weeks.flatMap((week) => {
                const row = rowByKey.get(`${model.field}|${week}`);
                return [
                  <td key={`${model.field}-${week}-count`} className={`border-b border-r border-slate-200 px-3 py-2.5 text-right tabular-nums ${index % 2 === 0 ? 'bg-white' : 'bg-[#f8fafc]'} group-hover:bg-[#eff6ff]`}>{formatTableValue('count', row?.count)}</td>,
                  <td key={`${model.field}-${week}-badrate`} className={`border-b border-r border-slate-200 px-3 py-2.5 text-right tabular-nums ${index % 2 === 0 ? 'bg-white' : 'bg-[#f8fafc]'} group-hover:bg-[#eff6ff]`}>{formatTableValue('badrate', row?.badrate)}</td>,
                  <td key={`${model.field}-${week}-auc`} className={`border-b border-r border-slate-200 px-3 py-2.5 text-right font-medium tabular-nums ${index % 2 === 0 ? 'bg-white' : 'bg-[#f8fafc]'} group-hover:bg-[#eff6ff] ${metricTone(row?.auc)}`}>{formatTableValue('metric', row?.auc)}</td>,
                  <td key={`${model.field}-${week}-ks`} className={`border-b border-r border-slate-200 px-3 py-2.5 text-right font-medium tabular-nums ${index % 2 === 0 ? 'bg-white' : 'bg-[#f8fafc]'} group-hover:bg-[#eff6ff] ${metricTone(row?.ks)}`}>{formatTableValue('metric', row?.ks)}</td>,
                ];
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ModelEffectiveness() {
  const [payload, setPayload] = useState<ModelMonitoringPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [alias, setAlias] = useState('');
  const [appliedAlias, setAppliedAlias] = useState('');
  const [target, setTarget] = useState<TargetMetric>('fpd7');
  const [appliedTarget, setAppliedTarget] = useState<TargetMetric>('fpd7');

  const load = async (force = false) => {
    setError(null);
    if (force) setRefreshing(true);
    else setLoading(true);
    try {
      const result = await fetchModelMonitoring(undefined, force);
      const availableAliases = aliasesFor(result);
      const nextAlias = alias && availableAliases.includes(alias) ? alias : availableAliases[0] ?? '';
      setPayload(result);
      setAlias(nextAlias);
      setAppliedAlias((current) => current && availableAliases.includes(current) ? current : nextAlias);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '模型效果数据加载失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    void load();
    // Initial load only; filter changes are intentionally local until 查询.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading && !payload) return <LoadingState />;
  if (!payload) {
    return (
      <div className="flex min-h-[520px] flex-col items-center justify-center bg-[#f5f7fa] text-center">
        <AlertTriangle size={24} className="mb-3 text-rose-500" />
        <div className="text-[16px] font-semibold text-slate-800">模型效果数据暂不可用</div>
        <div className="mt-2 max-w-lg text-[13px] text-slate-500">{error}</div>
        <button type="button" onClick={() => void load()} className="mt-5 rounded-md border border-slate-300 bg-white px-4 py-2 text-[13px] font-medium text-slate-700 shadow-sm hover:bg-slate-50">重试</button>
      </div>
    );
  }

  const availableAliases = aliasesFor(payload);
  return (
    <div className="min-h-full bg-[#f5f7fa] p-3 text-slate-900">
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-[0_8px_24px_-20px_rgba(15,23,42,0.45)]">
        <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-[#f8fafc] px-4 py-3">
          <div className="mr-1 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.12em] text-slate-500">
            <span className="h-4 w-1 rounded-full bg-[#facc15]" />
            筛选器
          </div>
          <div className="hidden h-5 w-px bg-slate-200 sm:block" />
          <label className="flex items-center gap-2 text-[12px] font-medium text-slate-500">
            业务环节
            <select value={alias} onChange={(event) => setAlias(event.target.value)} className="h-8 min-w-[120px] rounded-md border border-slate-300 bg-white px-2.5 text-[13px] font-medium text-slate-700 shadow-sm outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-100" aria-label="选择业务环节">
              {availableAliases.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-2 text-[12px] font-medium text-slate-500">
            目标变量
            <select value={target} onChange={(event) => setTarget(event.target.value as TargetMetric)} className="h-8 min-w-[108px] rounded-md border border-slate-300 bg-white px-2.5 text-[13px] font-medium text-slate-700 shadow-sm outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-100" aria-label="选择目标变量">
              {(Object.keys(targetLabels) as TargetMetric[]).map((item) => <option key={item} value={item}>{targetLabels[item]}</option>)}
            </select>
          </label>
          <button type="button" onClick={() => { setAppliedAlias(alias); setAppliedTarget(target); }} className="h-8 min-w-[72px] rounded-md bg-[#facc15] px-4 text-[13px] font-semibold text-slate-900 shadow-sm transition hover:bg-[#eab308] focus:outline-none focus:ring-2 focus:ring-yellow-200">查询</button>
          <button type="button" onClick={() => void load(true)} disabled={refreshing} className="ml-auto inline-flex h-8 items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 text-[12px] font-medium text-slate-600 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50">
            <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />刷新数据
          </button>
        </div>

        <div className="p-3">
          <WeeklyEffectTable payload={payload} alias={appliedAlias} target={appliedTarget} />
        </div>

        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-slate-200 px-4 py-2.5 text-[11px] text-slate-500">
          <span>业务环节：{appliedAlias || '—'}</span>
          <span>目标变量：{targetLabels[appliedTarget]}</span>
          <span>count 为成熟样本数</span>
          <span>数据分区：pt={payload.meta.partition}</span>
          <span>周起始日按周一统计</span>
          {error && <span className="font-medium text-rose-600">刷新失败：{error}</span>}
        </div>
      </div>
    </div>
  );
}
