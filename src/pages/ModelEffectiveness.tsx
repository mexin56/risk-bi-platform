import { useEffect, useMemo, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { AlertTriangle, ArrowDown, ArrowUp, ArrowUpDown, Database, Filter, RefreshCw } from 'lucide-react';
import ChartCard from '@/components/ChartCard';
import {
  fetchModelMonitoring,
  fetchModelMonitoringFilters,
  fetchModelScoreMonitoring,
  type ModelEffectWeekly,
  type ModelMonitoringPayload,
  type ModelScoreCohortTrend,
  type ModelScoreMonitoringPayload,
  type ModelScoreStabilityWeekly,
  type TargetMetric,
} from '@/lib/modelMonitoringApi';
import { commonWeeklySampleStats, metricBarWidth, modelFieldsWithAuc, weeksWithAuc } from '@/lib/modelEffectTable';
import { baseOption } from '@/lib/chartTheme';
import { getTheme } from '@/lib/theme';

const numberFormat = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 });
const targetLabels: Record<TargetMetric, string> = {
  fpd1: 'FPD1',
  fpd7: 'FPD7',
  fpd10: 'FPD10',
  fpd15: 'FPD15',
  fpd30: 'FPD30',
  term3: 'TERM3',
};
const selectClassName = 'h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-[13px] font-medium text-slate-700 outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-100';

type LabelFilters = {
  flagMobType: string;
  flagProduct: string;
  cashSerCallNode: string;
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

function optionsFor(values: string[] | undefined): string[] {
  return values?.length ? values : ['未知'];
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

type MetricKey = 'auc' | 'ks';
type SortState = { week: string; metric: MetricKey; direction: 'asc' | 'desc' };

type ModelMonitorTab = 'effect' | 'stability' | 'cohort';
type CohortRange = 'month' | 'current_month' | 'week' | 'day';

const MODEL_MONITOR_TABS: Array<{ key: ModelMonitorTab; label: string }> = [
  { key: 'effect', label: '模型效果监控' },
  { key: 'stability', label: '模型分稳定性变化' },
  { key: 'cohort', label: '客群变化' },
];

const COHORT_RANGES: Array<{ key: CohortRange; label: string }> = [
  { key: 'month', label: '最近一月' },
  { key: 'current_month', label: '本月' },
  { key: 'week', label: '本周' },
  { key: 'day', label: '近一天' },
];

function formatRate(value: number | null | undefined): string {
  return value == null || Number.isNaN(value) ? '—' : `${(value * 100).toFixed(2)}%`;
}

function formatDay(value: string): string {
  return value ? value.slice(5).replace('-', '/') : '—';
}

function parseDay(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return null;
  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
}

function isoDay(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function addDays(value: string, amount: number): string {
  const parsed = parseDay(value);
  if (!parsed) return value;
  parsed.setUTCDate(parsed.getUTCDate() + amount);
  return isoDay(parsed);
}

function cohortStartDay(range: CohortRange, endDay: string): string {
  const parsed = parseDay(endDay);
  if (!parsed) return endDay;
  if (range === 'day') return endDay;
  if (range === 'week') {
    const dayOfWeek = parsed.getUTCDay();
    parsed.setUTCDate(parsed.getUTCDate() + (dayOfWeek === 0 ? -6 : 1 - dayOfWeek));
    return isoDay(parsed);
  }
  if (range === 'current_month') {
    parsed.setUTCDate(1);
    return isoDay(parsed);
  }
  return addDays(endDay, -29);
}

function rgbaFromHex(hex: string, alpha: number): string {
  const normalized = hex.replace('#', '');
  const red = parseInt(normalized.slice(0, 2), 16);
  const green = parseInt(normalized.slice(2, 4), 16);
  const blue = parseInt(normalized.slice(4, 6), 16);
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

function binColors(): string[] {
  const { brand } = getTheme();
  return Array.from({ length: 10 }, (_, index) => rgbaFromHex(brand, 0.42 + index * 0.05));
}

function ModelScoreStabilityView({ rows: sourceRows, alias, target, modelField, modelName, loading, error }: { rows: ModelScoreStabilityWeekly[]; alias: string; target: TargetMetric; modelField: string; modelName: string; loading: boolean; error: string | null }) {
  const rows = useMemo<ModelScoreStabilityWeekly[]>(
    () => sourceRows.filter((row) => row.alias === alias && row.target === target && row.model === modelField),
    [alias, modelField, sourceRows, target],
  );
  const weeks = useMemo(
    () => [...new Set(rows.map((row) => row.week_start))].sort((left, right) => left.localeCompare(right)),
    [rows],
  );
  const rowByKey = useMemo(
    () => new Map(rows.map((row) => [`${row.week_start}|${row.bin}`, row])),
    [rows],
  );
  const chartOption = useMemo(() => ({
    ...baseOption(),
    color: binColors(),
    grid: { left: 12, right: 18, top: 22, bottom: 58, containLabel: true },
    legend: { type: 'scroll', bottom: 0, left: 8, right: 8, icon: 'roundRect', itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 10, color: '#646a73' } },
    xAxis: { ...baseOption().xAxis, data: weeks.map(formatDateGroup), boundaryGap: false },
    yAxis: { ...baseOption().yAxis, min: 0, max: 100, axisLabel: { color: '#8f959e', fontSize: 11, formatter: (value: number) => `${value}%` } },
    series: Array.from({ length: 10 }, (_, index) => ({
      name: `Q${index + 1}`,
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 4,
      lineStyle: { width: 1.5 },
      data: weeks.map((week) => {
        const value = rowByKey.get(`${week}|${index + 1}`)?.badrate;
        return value == null ? null : Number((value * 100).toFixed(4));
      }),
    })),
  }), [rowByKey, weeks]);

  if (!modelField) {
    return <div className="rounded-lg border border-dashed border-slate-300 bg-white px-4 py-14 text-center text-[13px] text-slate-500">请在上方“模型分”筛选器中选择一个模型分后查看稳定性变化</div>;
  }
  if (loading) {
    return <div className="rounded-lg border border-slate-200 bg-white px-4 py-14 text-center text-[13px] text-slate-500">正在读取模型分稳定性数据…</div>;
  }
  if (error) {
    return <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-14 text-center text-[13px] text-rose-600">模型分稳定性数据加载失败：{error}</div>;
  }
  if (!rows.length) {
    return <div className="rounded-lg border border-dashed border-slate-300 bg-white px-4 py-14 text-center text-[13px] text-slate-500">当前筛选条件暂无模型分稳定性数据</div>;
  }

  const tableRows = [...rows].sort((left, right) => right.week_start.localeCompare(left.week_start) || left.bin - right.bin);
  return (
    <div className="space-y-4">
      <ChartCard title="模型分分箱 badrate 周趋势" subtitle={`${modelName} · ${targetLabels[target]} · Q1 为低分段，Q10 为高分段`}>
        <ReactECharts option={chartOption} style={{ height: 350 }} notMerge />
      </ChartCard>
      <ChartCard title="模型分稳定性明细" subtitle="用于观察不同分箱的客户占比、通过率、交易通过率和 badrate 排序性">
        <div className="max-h-[430px] overflow-auto">
          <table className="min-w-[920px] w-full border-separate border-spacing-0 text-[12px] text-slate-700">
            <thead className="sticky top-0 z-10 bg-white">
              <tr>
                {['统计周', '分箱', '客户量', '客户占比', '通过率', '交易通过率', `${targetLabels[target]} badrate`, '到期样本数'].map((title) => <th key={title} className="border-b border-r border-slate-200 bg-slate-50 px-3 py-2.5 text-left text-[11px] font-semibold text-slate-500 last:border-r-0">{title}</th>)}
              </tr>
            </thead>
            <tbody>
              {tableRows.map((row) => (
                <tr key={`${row.week_start}|${row.bin}`} className="hover:bg-slate-50">
                  <td className="border-b border-r border-slate-100 px-3 py-2.5">{formatDateGroup(row.week_start)}</td>
                  <td className="border-b border-r border-slate-100 px-3 py-2.5 font-medium">{row.bin_label}</td>
                  <td className="border-b border-r border-slate-100 px-3 py-2.5 text-right tabular-nums">{numberFormat.format(row.customer_count)}</td>
                  <td className="border-b border-r border-slate-100 px-3 py-2.5 text-right tabular-nums">{formatRate(row.customer_share)}</td>
                  <td className="border-b border-r border-slate-100 px-3 py-2.5 text-right tabular-nums">{formatRate(row.approval_rate)}</td>
                  <td className="border-b border-r border-slate-100 px-3 py-2.5 text-right tabular-nums">{formatRate(row.loan_success_rate)}</td>
                  <td className="border-b border-r border-slate-100 px-3 py-2.5 text-right font-medium tabular-nums">{formatRate(row.badrate)}</td>
                  <td className="border-b border-slate-100 px-3 py-2.5 text-right tabular-nums">{numberFormat.format(row.target_base)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ChartCard>
    </div>
  );
}

function ModelScoreCohortView({ rows: sourceRows, alias, modelField, modelName, loading, error }: { rows: ModelScoreCohortTrend[]; alias: string; modelField: string; modelName: string; loading: boolean; error: string | null }) {
  const [range, setRange] = useState<CohortRange>('month');
  const rows = useMemo<ModelScoreCohortTrend[]>(
    () => sourceRows.filter((row) => row.alias === alias && row.model === modelField),
    [alias, modelField, sourceRows],
  );
  const endDay = useMemo(() => rows.reduce((latest, row) => row.day > latest ? row.day : latest, ''), [rows]);
  const startDay = cohortStartDay(range, endDay);
  const visibleRows = useMemo(
    () => rows.filter((row) => row.day >= startDay && row.day <= endDay),
    [endDay, rows, startDay],
  );
  const days = useMemo(
    () => [...new Set(visibleRows.map((row) => row.day))].sort((left, right) => left.localeCompare(right)),
    [visibleRows],
  );
  const rowByKey = useMemo(
    () => new Map(visibleRows.map((row) => [`${row.day}|${row.bin}`, row])),
    [visibleRows],
  );
  const chartOption = useMemo(() => ({
    ...baseOption(),
    color: binColors(),
    grid: { left: 12, right: 18, top: 22, bottom: 58, containLabel: true },
    legend: { type: 'scroll', bottom: 0, left: 8, right: 8, icon: 'roundRect', itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 10, color: '#646a73' } },
    xAxis: { ...baseOption().xAxis, data: days.map(formatDay), boundaryGap: false },
    yAxis: { ...baseOption().yAxis, min: 0, max: 100, axisLabel: { color: '#8f959e', fontSize: 11, formatter: (value: number) => `${value}%` } },
    series: Array.from({ length: 10 }, (_, index) => ({
      name: `Q${index + 1}`,
      type: 'line',
      stack: 'share',
      smooth: true,
      symbol: 'none',
      areaStyle: { opacity: 0.22 },
      lineStyle: { width: 1 },
      data: days.map((day) => {
        const value = rowByKey.get(`${day}|${index + 1}`)?.customer_share;
        return value == null ? null : Number((value * 100).toFixed(4));
      }),
    })),
  }), [days, rowByKey]);

  if (!modelField) {
    return <div className="rounded-lg border border-dashed border-slate-300 bg-white px-4 py-14 text-center text-[13px] text-slate-500">请在上方“模型分”筛选器中选择一个模型分后查看客群变化</div>;
  }
  if (loading) {
    return <div className="rounded-lg border border-slate-200 bg-white px-4 py-14 text-center text-[13px] text-slate-500">正在读取客群变化数据…</div>;
  }
  if (error) {
    return <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-14 text-center text-[13px] text-rose-600">客群变化数据加载失败：{error}</div>;
  }
  if (!rows.length) {
    return <div className="rounded-lg border border-dashed border-slate-300 bg-white px-4 py-14 text-center text-[13px] text-slate-500">当前筛选条件暂无客群变化数据</div>;
  }

  const latestRows = visibleRows.filter((row) => row.day === endDay).sort((left, right) => left.bin - right.bin);
  return (
    <div className="space-y-4">
      <ChartCard
        title="模型分客群占比变化"
        subtitle={`${modelName} · 固定 qcut10 分箱 · ${formatDay(startDay)}～${formatDay(endDay)}`}
        extra={<div className="flex items-center gap-1 rounded-md bg-slate-100 p-1">{COHORT_RANGES.map((item) => <button key={item.key} type="button" onClick={() => setRange(item.key)} className={`rounded px-2 py-1 text-[11px] transition ${range === item.key ? 'bg-white font-medium text-[var(--brand)] shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>{item.label}</button>)}</div>}
      >
        <ReactECharts option={chartOption} style={{ height: 350 }} notMerge />
      </ChartCard>
      <ChartCard title="最新一天分箱占比" subtitle="用于核对当前客群结构，合计客户占比应接近 100%">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5 lg:grid-cols-10">
          {latestRows.map((row) => <div key={row.bin} className="rounded-lg border border-slate-100 bg-slate-50 px-2.5 py-2 text-center"><div className="text-[11px] font-medium text-slate-500">{row.bin_label}</div><div className="mt-1 text-[15px] font-semibold tabular-nums text-slate-700">{formatRate(row.customer_share)}</div><div className="mt-0.5 text-[10px] text-slate-400">{numberFormat.format(row.customer_count)} 人</div></div>)}
        </div>
      </ChartCard>
    </div>
  );
}

function MetricCell({ value, index, metric }: { value: number | null | undefined; index: number; metric: MetricKey }) {
  const width = metricBarWidth(value);
  const barBackground = metric === 'auc' ? 'rgba(var(--brand-rgb), 0.42)' : 'var(--brand-300)';
  const barOpacity = metric === 'auc' ? 1 : 0.72;

  return (
    <td className={`relative overflow-hidden border-b border-r border-slate-200 px-3 py-2.5 text-right font-medium tabular-nums text-slate-700 ${index % 2 === 0 ? 'bg-white' : 'bg-[#f8fafc]'} group-hover:bg-[#eff6ff]`}>
      {width > 0 && <span aria-hidden="true" className="pointer-events-none absolute left-1 top-1/2 h-4 -translate-y-1/2 rounded-sm" style={{ width: `${width}%`, background: barBackground, opacity: barOpacity }} />}
      <span className="relative z-[1]">{formatTableValue('metric', value)}</span>
    </td>
  );
}

function WeeklyEffectTable({ payload, alias, target, modelField }: { payload: ModelMonitoringPayload; alias: string; target: TargetMetric; modelField: string }) {
  const rows = useMemo(() => weeklyRowsFor(payload, alias, target), [payload, alias, target]);
  const candidateFields = useMemo(
    () => payload.model_coverage.filter((row) => row.valid > 0).map((row) => row.field),
    [payload.model_coverage],
  );
  const visibleModelFields = useMemo(
    () => modelFieldsWithAuc(rows, candidateFields, modelField),
    [candidateFields, modelField, rows],
  );
  const models = useMemo(
    () => payload.model_coverage
      .filter((row) => visibleModelFields.includes(row.field))
      .sort((left, right) => left.field.localeCompare(right.field)),
    [payload.model_coverage, visibleModelFields],
  );
  const visibleRows = useMemo(
    () => rows.filter((row) => visibleModelFields.includes(row.model)),
    [rows, visibleModelFields],
  );
  const weeks = useMemo(
    () => weeksWithAuc(visibleRows, visibleModelFields),
    [visibleModelFields, visibleRows],
  );
  const commonStatsByWeek = useMemo(
    () => new Map(weeks.map((week) => [week, commonWeeklySampleStats(visibleRows, week)])),
    [visibleRows, weeks],
  );
  const rowByKey = useMemo(
    () => new Map(visibleRows.map((row) => [`${row.model}|${row.week_start}`, row])),
    [visibleRows],
  );
  const [sortState, setSortState] = useState<SortState | null>(null);
  const sortedModels = useMemo(() => {
    if (!sortState) return models;
    const sorted = [...models];
    sorted.sort((left, right) => {
      const leftRow = rowByKey.get(`${left.field}|${sortState.week}`);
      const rightRow = rowByKey.get(`${right.field}|${sortState.week}`);
      const leftValue = leftRow?.[sortState.metric] ?? null;
      const rightValue = rightRow?.[sortState.metric] ?? null;
      if (leftValue == null && rightValue == null) return left.field.localeCompare(right.field);
      if (leftValue == null) return 1;
      if (rightValue == null) return -1;
      const delta = leftValue - rightValue;
      return (sortState.direction === 'asc' ? delta : -delta) || left.field.localeCompare(right.field);
    });
    return sorted;
  }, [models, rowByKey, sortState]);
  const toggleSort = (week: string, metric: MetricKey) => {
    setSortState((current) => current?.week === week && current.metric === metric
      ? { ...current, direction: current.direction === 'asc' ? 'desc' : 'asc' }
      : { week, metric, direction: 'desc' });
  };
  const sortIcon = (week: string, metric: MetricKey) => {
    if (sortState?.week !== week || sortState.metric !== metric) return <ArrowUpDown size={12} />;
    return sortState.direction === 'asc' ? <ArrowUp size={12} /> : <ArrowDown size={12} />;
  };
  if (!alias) {
    return <div className="rounded-lg border border-slate-200 bg-white px-4 py-10 text-center text-[14px] text-slate-500">暂无业务环节数据</div>;
  }

  if (!weeks.length) {
    return <div className="rounded-lg border border-slate-200 bg-white px-4 py-10 text-center text-[14px] text-slate-500">当前筛选条件暂无可展示的模型效果数据</div>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="min-w-[1840px] w-full border-separate border-spacing-0 text-[12px] text-slate-700">
        <thead>
          <tr>
            <th rowSpan={2} className="sticky left-0 top-0 z-30 w-[250px] min-w-[250px] border-b border-r border-slate-200 px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-600 shadow-[8px_0_16px_-16px_rgba(15,23,42,0.6)]" style={{ background: 'rgba(var(--brand-rgb), 0.08)' }}>模型分字段</th>
            <th rowSpan={2} className="sticky left-[250px] top-0 z-30 w-[148px] min-w-[148px] border-b border-r border-slate-200 px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-600 shadow-[8px_0_16px_-16px_rgba(15,23,42,0.6)]" style={{ background: 'rgba(var(--brand-rgb), 0.08)' }}>模型标签</th>
            {weeks.map((week) => {
              const commonStats = commonStatsByWeek.get(week);
              return (
                <th key={week} colSpan={2} className="border-b border-r border-slate-200 px-3 py-2 text-center text-[12px] font-semibold tracking-[0.04em] text-slate-700" style={{ background: 'rgba(var(--brand-rgb), 0.12)' }}>
                  <div>{formatDateGroup(week)}</div>
                  {commonStats && <div className="mt-1 text-[10px] font-medium tracking-normal text-slate-500">(count={formatTableValue('count', commonStats.count)} / badrate={formatTableValue('badrate', commonStats.badrate)})</div>}
                </th>
              );
            })}
          </tr>
          <tr>
            {weeks.flatMap((week) => {
              return [
                <th key={`${week}-auc`} aria-sort={sortState?.week === week && sortState.metric === 'auc' ? sortState.direction === 'asc' ? 'ascending' : 'descending' : 'none'} className="sticky top-[50px] z-20 w-[92px] min-w-[92px] border-b border-r border-slate-200 px-3 py-2 text-center text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-500" style={{ background: 'rgba(var(--brand-rgb), 0.04)' }}>
                  <button type="button" onClick={() => toggleSort(week, 'auc')} className={`mx-auto inline-flex items-center gap-1 rounded-md border px-2 py-1 transition ${sortState?.week === week && sortState.metric === 'auc' ? 'border-[var(--brand)] bg-[rgba(var(--brand-rgb),0.12)] text-[var(--brand)]' : 'border-slate-200 bg-white/80 text-slate-600 hover:border-[rgba(var(--brand-rgb),0.5)] hover:bg-[rgba(var(--brand-rgb),0.08)] hover:text-[var(--brand)]'}`} aria-label={`按${formatDateGroup(week)} AUC排序`}>AUC {sortIcon(week, 'auc')}</button>
                </th>,
                <th key={`${week}-ks`} aria-sort={sortState?.week === week && sortState.metric === 'ks' ? sortState.direction === 'asc' ? 'ascending' : 'descending' : 'none'} className="sticky top-[50px] z-20 w-[92px] min-w-[92px] border-b border-r border-slate-200 px-3 py-2 text-center text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-500" style={{ background: 'rgba(var(--brand-rgb), 0.04)' }}>
                  <button type="button" onClick={() => toggleSort(week, 'ks')} className={`mx-auto inline-flex items-center gap-1 rounded-md border px-2 py-1 transition ${sortState?.week === week && sortState.metric === 'ks' ? 'border-[var(--brand)] bg-[rgba(var(--brand-rgb),0.12)] text-[var(--brand)]' : 'border-slate-200 bg-white/80 text-slate-600 hover:border-[rgba(var(--brand-rgb),0.5)] hover:bg-[rgba(var(--brand-rgb),0.08)] hover:text-[var(--brand)]'}`} aria-label={`按${formatDateGroup(week)} KS排序`}>KS {sortIcon(week, 'ks')}</button>
                </th>,
              ];
            })}
          </tr>
        </thead>
        <tbody>
          {sortedModels.map((model, index) => (
            <tr key={model.field} className="group hover:bg-[#eff6ff]">
              <td className={`sticky left-0 z-10 w-[250px] min-w-[250px] border-b border-r border-slate-200 px-4 py-2.5 align-middle font-mono text-[11px] text-slate-600 shadow-[8px_0_16px_-16px_rgba(15,23,42,0.6)] ${index % 2 === 0 ? 'bg-white' : 'bg-[#f8fafc]'} group-hover:bg-[#eff6ff]`}>{model.field}</td>
              <td className={`sticky left-[250px] z-10 w-[148px] min-w-[148px] border-b border-r border-slate-200 px-4 py-2.5 align-middle font-medium text-slate-800 shadow-[8px_0_16px_-16px_rgba(15,23,42,0.6)] ${index % 2 === 0 ? 'bg-white' : 'bg-[#f8fafc]'} group-hover:bg-[#eff6ff]`}>{model.model}</td>
              {weeks.flatMap((week) => {
                const row = rowByKey.get(`${model.field}|${week}`);
                return [
                  <MetricCell key={`${model.field}-${week}-auc`} value={row?.auc} index={index} metric="auc" />,
                  <MetricCell key={`${model.field}-${week}-ks`} value={row?.ks} index={index} metric="ks" />,
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
  const [flagMobType, setFlagMobType] = useState('');
  const [appliedFlagMobType, setAppliedFlagMobType] = useState('');
  const [flagProduct, setFlagProduct] = useState('');
  const [appliedFlagProduct, setAppliedFlagProduct] = useState('');
  const [cashSerCallNode, setCashSerCallNode] = useState('');
  const [appliedCashSerCallNode, setAppliedCashSerCallNode] = useState('');
  const [mobTypeOptions, setMobTypeOptions] = useState<string[]>([]);
  const [productOptions, setProductOptions] = useState<string[]>([]);
  const [cashSerCallNodeOptions, setCashSerCallNodeOptions] = useState<string[]>([]);
  const [modelField, setModelField] = useState('');
  const [appliedModelField, setAppliedModelField] = useState('');
  const [target, setTarget] = useState<TargetMetric>('fpd7');
  const [appliedTarget, setAppliedTarget] = useState<TargetMetric>('fpd7');
  const [activeTab, setActiveTab] = useState<ModelMonitorTab>('effect');
  const [scorePayload, setScorePayload] = useState<ModelScoreMonitoringPayload | null>(null);
  const [scoreLoading, setScoreLoading] = useState(false);
  const [scoreError, setScoreError] = useState<string | null>(null);
  const [scoreRefreshKey, setScoreRefreshKey] = useState(0);

  // 「全部模型分」时的兼容策略：稳定性/客群变化 tab 自动展示覆盖率最高的模型分
  const fallbackModelField = useMemo(() => {
    const candidates = (payload?.model_coverage ?? []).filter((row) => (row.valid ?? 0) > 0);
    const sorted = [...candidates].sort(
      (left, right) => (right.valid ?? 0) - (left.valid ?? 0) || left.field.localeCompare(right.field),
    );
    return sorted[0]?.field ?? '';
  }, [payload]);
  const effectiveModelField = appliedModelField || fallbackModelField;

  const load = async (
    force = false,
    nextLabels: LabelFilters = { flagMobType: appliedFlagMobType, flagProduct: appliedFlagProduct, cashSerCallNode: appliedCashSerCallNode },
    selectionOverrides: { alias?: string; modelField?: string } = {},
  ) => {
    setError(null);
    if (force) setRefreshing(true);
    else setLoading(true);
    try {
      const selectedModelForQuery = selectionOverrides.modelField ?? modelField;
      const result = await fetchModelMonitoring(undefined, force, {
        model: activeTab === 'effect' ? selectedModelForQuery || undefined : undefined,
        flagMobType: nextLabels.flagMobType || undefined,
        flagProduct: nextLabels.flagProduct || undefined,
        cashSerCallNode: nextLabels.cashSerCallNode || undefined,
      });
      const availableAliases = aliasesFor(result);
      const requestedAlias = selectionOverrides.alias ?? alias;
      const nextAlias = requestedAlias && availableAliases.includes(requestedAlias) ? requestedAlias : availableAliases[0] ?? '';
      const availableModelFields = result.model_coverage.filter((row) => row.valid > 0).map((row) => row.field);
      const requestedModelField = selectionOverrides.modelField ?? modelField;
      const nextModelField = requestedModelField && availableModelFields.includes(requestedModelField) ? requestedModelField : '';
      setPayload(result);
      setAlias(nextAlias);
      setAppliedAlias(nextAlias);
      setModelField(nextModelField);
      setAppliedModelField(nextModelField);
      setFlagMobType(nextLabels.flagMobType);
      setAppliedFlagMobType(nextLabels.flagMobType);
      setFlagProduct(nextLabels.flagProduct);
      setAppliedFlagProduct(nextLabels.flagProduct);
      setCashSerCallNode(nextLabels.cashSerCallNode);
      setAppliedCashSerCallNode(nextLabels.cashSerCallNode);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '模型效果数据加载失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const loadFilterOptions = async (force = false) => {
    try {
      const result = await fetchModelMonitoringFilters(undefined, force);
      setMobTypeOptions(result.flag_mob_type_options ?? []);
      setProductOptions(result.flag_product_options ?? []);
      setCashSerCallNodeOptions(result.cash_ser_call_node_options ?? []);
    } catch {
      // The main payload still carries a safe fallback when the lightweight options query is unavailable.
    }
  };

  useEffect(() => {
    void load(false, { flagMobType: '', flagProduct: '', cashSerCallNode: '' }, { alias: '', modelField: '' });
    void loadFilterOptions();
    // Initial load only; filter changes are applied by 查询.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (activeTab === 'effect' || !appliedAlias || !effectiveModelField) {
      setScoreLoading(false);
      setScoreError(null);
      return undefined;
    }
    let alive = true;
    setScoreLoading(true);
    setScoreError(null);
    void fetchModelScoreMonitoring(
      effectiveModelField,
      appliedAlias,
      appliedTarget,
      payload?.meta.partition,
      scoreRefreshKey > 0,
      {
        flagMobType: appliedFlagMobType || undefined,
        flagProduct: appliedFlagProduct || undefined,
        cashSerCallNode: appliedCashSerCallNode || undefined,
      },
    ).then((result) => {
      if (alive) setScorePayload(result);
    }).catch((cause) => {
      if (alive) setScoreError(cause instanceof Error ? cause.message : '分箱数据加载失败');
    }).finally(() => {
      if (alive) setScoreLoading(false);
    });
    return () => {
      alive = false;
    };
  }, [activeTab, appliedAlias, appliedCashSerCallNode, appliedFlagMobType, appliedFlagProduct, effectiveModelField, appliedTarget, payload?.meta.partition, scoreRefreshKey]);

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
  const mobTypeSelectOptions = optionsFor(mobTypeOptions.length ? mobTypeOptions : payload.model_effect_mob_types);
  const productSelectOptions = optionsFor(productOptions.length ? productOptions : payload.model_effect_products);
  const cashSerCallNodeSelectOptions = optionsFor(cashSerCallNodeOptions.length ? cashSerCallNodeOptions : payload.model_effect_cash_ser_call_nodes);
  const selectedRows = weeklyRowsFor(payload, appliedAlias, appliedTarget).filter((row) => !appliedModelField || row.model === appliedModelField);
  const modelOptions = payload.model_coverage.filter((row) => row.valid > 0).sort((left, right) => left.field.localeCompare(right.field));
  const selectedModelName = modelOptions.find((row) => row.field === effectiveModelField)?.model ?? effectiveModelField;
  const usingFallbackModel = activeTab !== 'effect' && !appliedModelField && Boolean(effectiveModelField);
  const displayedModelFields = modelFieldsWithAuc(selectedRows, modelOptions.map((row) => row.field), appliedModelField);
  const modelCount = displayedModelFields.length;

  const applyFilters = () => {
    setScorePayload(null);
    setAppliedAlias(alias);
    setAppliedTarget(target);
    setAppliedModelField(modelField);
    setAppliedFlagMobType(flagMobType);
    setAppliedFlagProduct(flagProduct);
    setAppliedCashSerCallNode(cashSerCallNode);
    void load(false, { flagMobType, flagProduct, cashSerCallNode }, { alias, modelField });
  };

  const refreshAll = () => {
    setScorePayload(null);
    setScoreRefreshKey((value) => value + 1);
    void Promise.all([
      load(true, { flagMobType: appliedFlagMobType, flagProduct: appliedFlagProduct, cashSerCallNode: appliedCashSerCallNode }, { alias: appliedAlias, modelField: appliedModelField }),
      loadFilterOptions(true),
    ]);
  };

  return (
    <div className="min-h-full bg-[#f5f7fa] p-4 text-slate-900">
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-[0_8px_24px_-20px_rgba(15,23,42,0.45)]">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-200 bg-white px-5 py-4">
          <div>
            <div className="flex items-center gap-2 text-[17px] font-semibold text-slate-900">
              <span className="h-5 w-1 rounded-full" style={{ background: 'var(--brand)' }} />
              模型效果监控
            </div>
            <div className="mt-1 text-[12px] text-slate-500">按业务环节、客户类型和产品标签查看模型分的周度区分能力</div>
          </div>
          <div className="flex items-center gap-2 text-[12px] text-slate-500">
            <span className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1.5"><Database size={13} /> pt={payload.meta.partition}</span>
            <span className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1.5">模型 {modelCount}</span>
            <button type="button" onClick={refreshAll} disabled={refreshing} className="inline-flex h-8 items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 text-[12px] font-medium text-slate-600 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50">
              <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />刷新数据
            </button>
          </div>
        </div>

        <div className="flex items-center gap-1 overflow-x-auto border-b border-slate-200 bg-white px-5 pt-2">
          {MODEL_MONITOR_TABS.map((tab) => {
            const active = activeTab === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setActiveTab(tab.key)}
                className={`whitespace-nowrap border-b-2 px-3 py-2 text-[12px] font-medium transition ${active ? 'border-[var(--brand)] text-[var(--brand)]' : 'border-transparent text-slate-500 hover:border-[rgba(var(--brand-rgb),0.35)] hover:text-[var(--brand)]'}`}
              >
                {tab.label}
              </button>
            );
          })}
        </div>

        <div className="border-b border-slate-200 bg-[#f8fafc] px-5 py-4">
          <div className="mb-3 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.1em] text-slate-500">
            <Filter size={14} />筛选条件
          </div>
          <div className="flex flex-wrap items-end justify-start gap-3">
            <div className="grid w-full grid-cols-1 gap-3 sm:grid-cols-2 lg:w-[648px] lg:max-w-[648px] lg:grid-cols-6">
            <label className="min-w-0 text-[12px] font-medium text-slate-600">
              业务环节（alias）
              <select value={alias} onChange={(event) => setAlias(event.target.value)} className={selectClassName} aria-label="选择业务环节">
                {availableAliases.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
            <label className="min-w-0 text-[12px] font-medium text-slate-600">
              客户类型
              <select value={flagMobType} onChange={(event) => setFlagMobType(event.target.value)} className={selectClassName} aria-label="选择客户类型">
                <option value="">全部客户类型</option>
                {mobTypeSelectOptions.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
            <label className="min-w-0 text-[12px] font-medium text-slate-600">
              产品标签
              <select value={flagProduct} onChange={(event) => setFlagProduct(event.target.value)} className={selectClassName} aria-label="选择产品标签">
                <option value="">全部产品标签</option>
                {productSelectOptions.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
            <label className="min-w-0 text-[12px] font-medium text-slate-600">
              服务节点
              <select value={cashSerCallNode} onChange={(event) => setCashSerCallNode(event.target.value)} className={selectClassName} aria-label="选择服务节点">
                <option value="">全部服务节点</option>
                {cashSerCallNodeSelectOptions.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
            <label className="min-w-0 text-[12px] font-medium text-slate-600">
              目标变量
              <select value={target} onChange={(event) => setTarget(event.target.value as TargetMetric)} className={selectClassName} aria-label="选择目标变量">
                {(Object.keys(targetLabels) as TargetMetric[]).map((item) => <option key={item} value={item}>{targetLabels[item]}</option>)}
              </select>
            </label>
            <label className="min-w-0 text-[12px] font-medium text-slate-600">
              模型分
              <select value={modelField} onChange={(event) => setModelField(event.target.value)} className={selectClassName} aria-label="选择模型分">
                <option value="">全部模型分（默认）</option>
                {modelOptions.map((item) => <option key={item.field} value={item.field}>{item.model}</option>)}
              </select>
            </label>
            </div>
            <button type="button" onClick={applyFilters} disabled={loading} className="inline-flex h-9 items-center gap-1.5 rounded-md px-5 text-[13px] font-semibold text-white shadow-sm transition hover:brightness-95 focus:outline-none disabled:cursor-wait disabled:opacity-60" style={{ background: 'var(--brand)', boxShadow: '0 4px 10px rgba(var(--brand-rgb), 0.22)' }}>
              {loading && <RefreshCw size={13} className="animate-spin" />} {loading ? '查询中' : '查询'}
            </button>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-[11px] text-slate-400">全部模型分：模型效果监控展示全部模型分；稳定性/客群变化自动展示覆盖率最高的模型分</span>
            <span className="ml-auto text-[11px] text-slate-400">标签筛选变更后会重新读取当前 pt 的模型效果数据{loading ? '，请等待查询完成' : ''}</span>
          </div>
        </div>

        <div className="p-4">
          {usingFallbackModel && (
            <div className="mb-3 rounded-lg border border-sky-200 bg-sky-50 px-3.5 py-2 text-[12px] text-sky-700">
              当前为「全部模型分」：本 tab 默认展示覆盖率最高的模型分 <span className="font-medium">{selectedModelName}</span>，可在上方筛选器切换到其它模型分。
            </div>
          )}
          {activeTab === 'effect' && <WeeklyEffectTable payload={payload} alias={appliedAlias} target={appliedTarget} modelField={appliedModelField} />}
          {activeTab === 'stability' && <ModelScoreStabilityView rows={scorePayload?.model_score_stability_weekly ?? []} alias={appliedAlias} target={appliedTarget} modelField={effectiveModelField} modelName={selectedModelName} loading={scoreLoading} error={scoreError} />}
          {activeTab === 'cohort' && <ModelScoreCohortView rows={scorePayload?.model_score_cohort_trend ?? []} alias={appliedAlias} modelField={effectiveModelField} modelName={selectedModelName} loading={scoreLoading} error={scoreError} />}
        </div>

        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-slate-200 px-5 py-3 text-[11px] text-slate-500">
          <span>count 为成熟样本数</span>
          <span>成熟样本数&lt;100 时该周留空</span>
          <span>count/badrate 已合并到周标题括号内</span>
          <span>周起始日按周一统计</span>
          {error && <span className="font-medium text-rose-600">刷新失败：{error}</span>}
        </div>
      </div>
    </div>
  );
}
