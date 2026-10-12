import { useEffect, useMemo, useRef, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { ArrowLeftRight, CalendarDays, ChevronDown, Layers3, RefreshCw, X } from 'lucide-react';
import type { EChartsOption } from 'echarts';
import {
  fetchModelScoreMonitoring, type ModelMonitoringFilters, type ModelScoreMonitoringPayload,
  type ModelScoreStabilityWeekly, type TargetMetric,
} from '@/lib/modelMonitoringApi';
import {
  COUNTS, TARGET_LABELS, dateLabel, distributions, groupedDistribution, groupLabels,
  largestShift, percent, points, ratio, shiftDay, sumCustomers,
  type Distribution, type Grain, type ScoreModel, type WindowDays,
} from './scorePresentation';
import { asPercent, bars, CHART_COLORS, composition, cumulative, lineChart, shareDelta, shareHeatmap } from './scoreCharts';

const controlClass = 'h-8 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-700 outline-none focus:border-blue-500';
type Props = {
  mode: 'stability' | 'cohort'; payload: ModelScoreMonitoringPayload | null;
  loading: boolean; error: string | null; model: ScoreModel; models: ScoreModel[];
  alias: string; target: TargetMetric; partition: string; generatedAt: string;
  filters: ModelMonitoringFilters; refreshKey: number;
  onModelChange: (field: string) => void; modelSelectionDisabled: boolean;
};
type Comparison = { model: ScoreModel; payload?: ModelScoreMonitoringPayload; error?: string };

function Panel({ title, subtitle, option, height = 310, children, wide = false }: {
  title: string; subtitle: string; option?: EChartsOption; height?: number; children?: React.ReactNode; wide?: boolean;
}) {
  return <section className={`min-w-0 rounded-xl border border-slate-200 bg-white ${wide ? 'xl:col-span-2' : ''}`}>
    <div className="px-4 pb-2 pt-4"><h3 className="text-sm font-semibold text-slate-800">{title}</h3><p className="mt-1 text-xs leading-5 text-slate-500">{subtitle}</p></div>
    {option && <ReactECharts option={option} style={{ height }} opts={{ renderer: 'canvas' }} notMerge />}
    {children}
  </section>;
}

function Stat({ label, value, note }: { label: string; value: string; note: string }) {
  return <div className="min-w-0 rounded-xl border border-slate-200 bg-white px-4 py-3">
    <div className="text-xs text-slate-500">{label}</div><div className="my-1.5 break-words text-xl font-semibold tabular-nums text-slate-800">{value}</div>
    <div className="text-[11px] leading-4 text-slate-500">{note}</div>
  </div>;
}

function Note({ children }: { children: React.ReactNode }) {
  return <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-600">{children}</div>;
}

function useComparisons(props: Props, selected: ScoreModel[]) {
  const cache = useRef(new Map<string, Promise<ModelScoreMonitoringPayload>>());
  const [state, setState] = useState<{ key: string; rows: Comparison[]; loading: boolean }>({ key: '', rows: [], loading: false });
  const fields = selected.map(item => item.field).join('|');
  const key = JSON.stringify([props.partition, props.generatedAt, props.alias, props.target, props.filters.flagMobType,
    props.filters.flagProduct, props.filters.cashSerCallNode, props.refreshKey, fields]);
  useEffect(() => {
    let alive = true;
    const models = fields ? fields.split('|') : [];
    setState({ key, rows: [], loading: models.length > 0 });
    void Promise.all(models.map(async field => {
      const model = selected.find(item => item.field === field)!;
      const queryKey = JSON.stringify([props.partition, props.generatedAt, props.alias, props.target, props.filters.flagMobType,
        props.filters.flagProduct, props.filters.cashSerCallNode, props.refreshKey, field]);
      let request = cache.current.get(queryKey);
      if (!request) {
        if (cache.current.size >= 24) cache.current.clear();
        request = fetchModelScoreMonitoring(field, props.alias, props.target, props.partition, false, props.filters);
        cache.current.set(queryKey, request);
        void request.catch(() => cache.current.delete(queryKey));
      }
      try { return { model, payload: await request }; }
      catch (cause) { return { model, error: cause instanceof Error ? cause.message : '读取失败' }; }
    })).then(rows => { if (alive) setState({ key, rows, loading: false }); });
    return () => { alive = false; };
    // The primitive key includes every request parameter; option object identity is immaterial.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return state.key === key ? state : { key, rows: [], loading: selected.length > 0 };
}

function distributionForWeek(rows: ModelScoreStabilityWeekly[], week: string): Distribution | undefined {
  const selected = rows.filter(row => row.week_start === week);
  if (!selected.length) return undefined;
  const counts = Array.from({ length: 10 }, (_, i) => selected.find(row => row.bin === i + 1)?.customer_count ?? 0);
  const total = counts.reduce((sum, value) => sum + value, 0);
  return { period: week, counts, shares: counts.map(count => ratio(count, total)), total, firstDay: week,
    lastDay: selected[0].week_end, days: 7 };
}

export default function ModelScoreDashboard(props: Props) {
  const { mode, model, alias, target, payload } = props;
  const [windowDays, setWindowDays] = useState<WindowDays>(30);
  const [grain, setGrain] = useState<Grain>('day');
  const [groups, setGroups] = useState<5 | 10>(10);
  const [analysisWeek, setAnalysisWeek] = useState('');
  const [baselineSelection, setBaselineSelection] = useState('');
  const [comparisonFields, setComparisonFields] = useState<string[] | null>(null);
  const availableComparisons = props.models.filter(item => item.field !== model.field);
  const selectedComparisons = (comparisonFields ?? availableComparisons.slice(0, 2).map(item => item.field))
    .map(field => availableComparisons.find(item => item.field === field)).filter((item): item is ScoreModel => Boolean(item)).slice(0, 3);
  const comparisons = useComparisons(props, selectedComparisons);
  const sourceRows = payload?.model_score_cohort_trend ?? [];
  const allRows = sourceRows.filter(row => row.alias === alias && row.model === model.field);
  const endDay = allRows.reduce((latest, row) => row.day > latest ? row.day : latest, '');
  const startDay = endDay ? shiftDay(endDay, 1 - windowDays) : '';
  const availableStartDay = allRows.reduce((earliest, row) => !earliest || row.day < earliest ? row.day : earliest, '');
  const visibleRows = allRows.filter(row => row.day >= startDay && row.day <= endDay);
  const periods = useMemo(() => distributions(visibleRows, grain), [visibleRows, grain]);
  const stabilityRows = (payload?.model_score_stability_weekly ?? []).filter(row => row.alias === alias && row.model === model.field && row.target === target);
  const weeks = [...new Set(stabilityRows.map(row => row.week_start))].sort();
  const matureWeeks = [...new Set(stabilityRows.filter(row => row.badrate != null).map(row => row.week_start))].sort();
  const defaultWeek = matureWeeks[matureWeeks.length - 1] ?? weeks[weeks.length - 1] ?? '';
  const currentPeriod = mode === 'cohort' ? periods[periods.length - 1]?.period ?? '' : weeks.includes(analysisWeek) ? analysisWeek : defaultWeek;
  const periodOptions = mode === 'cohort' ? periods.map(item => item.period) : weeks;
  const previousPeriod = periodOptions[periodOptions.indexOf(currentPeriod) - 1] ?? currentPeriod;
  const baselinePeriod = periodOptions.includes(baselineSelection) ? baselineSelection : previousPeriod;
  const current = mode === 'cohort' ? periods.find(item => item.period === currentPeriod) : distributionForWeek(stabilityRows, currentPeriod);
  const baseline = mode === 'cohort' ? periods.find(item => item.period === baselinePeriod) : distributionForWeek(stabilityRows, baselinePeriod);
  const countUnit = mode === 'stability' || grain === 'week' ? '人次' : '人';
  const context = `${alias} · ${model.model} · ${mode === 'stability' ? TARGET_LABELS[target] : grain === 'day' ? '日粒度' : '周粒度'}`;
  const shift = largestShift(current, baseline);
  const modelSets: Comparison[] = [{ model, payload: payload ?? undefined }, ...comparisons.rows];

  const comparisonControls = <div className="flex flex-wrap items-center gap-2">
    <span className="inline-flex items-center gap-1 text-xs font-medium text-slate-600"><ArrowLeftRight size={14} />对比模型</span>
    <label className="flex min-w-0 items-center gap-1.5 text-xs font-medium text-blue-700">主模型
      <select aria-label="选择主模型" className={`${controlClass} max-w-[320px] border-blue-200 bg-blue-50 text-blue-700`}
        title={model.field} value={model.field} disabled={props.modelSelectionDisabled || props.models.length === 0}
        onChange={event => props.onModelChange(event.target.value)}>
        {!props.models.length && <option value="">暂无可用模型</option>}
        {props.models.map(item => <option key={item.field} value={item.field}>{item.model} · {item.field}</option>)}
      </select>
    </label>
    {selectedComparisons.map((item, index) => <span key={item.field} className="inline-flex max-w-[260px] items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-600" title={item.field}>
      <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: CHART_COLORS[index + 1] }} /><span className="truncate">{item.model}</span>
      <button type="button" aria-label={`移除对比模型${item.model}`} onClick={() => setComparisonFields(selectedComparisons.filter(other => other.field !== item.field).map(other => other.field))} className="rounded p-0.5 hover:bg-slate-100"><X size={12} /></button>
    </span>)}
    <select aria-label="添加对比模型" className={controlClass} value="" disabled={selectedComparisons.length >= 3} onChange={event => {
      if (event.target.value) setComparisonFields([...selectedComparisons.map(item => item.field), event.target.value]);
    }}><option value="">{selectedComparisons.length >= 3 ? '最多对比四个模型' : '＋ 添加模型'}</option>
      {availableComparisons.filter(item => !selectedComparisons.some(selected => selected.field === item.field)).map(item => <option key={item.field} value={item.field}>{item.model}</option>)}
    </select>
    {comparisons.loading && <span className="inline-flex items-center gap-1 text-xs text-slate-400"><RefreshCw size={12} className="animate-spin" />读取对比结果</span>}
  </div>;

  return <div className="space-y-4">
    <section className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h2 className="flex items-center gap-2 text-base font-semibold text-slate-800"><Layers3 size={17} className="text-blue-600" />{mode === 'stability' ? '模型分稳定性分析' : '模型分客群结构分析'}</h2>
          <p className="mt-1 text-xs leading-5 text-slate-500">{context} · {endDay ? `${mode === 'stability' ? availableStartDay : startDay} ～ ${endDay}` : '读取已发布结果'} · 基准与当前使用同一分区内的固定分箱</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {mode === 'stability' && <label className="flex items-center gap-1.5 text-xs text-slate-500">分析周<select aria-label="选择稳定性分析周" className={controlClass} value={currentPeriod} onChange={event => setAnalysisWeek(event.target.value)}>
            {weeks.map(week => <option key={week} value={week}>{week}{!matureWeeks.includes(week) ? ' · 坏账率未成熟' : ''}{week === weeks[weeks.length - 1] ? '（最近观察）' : ''}</option>)}
          </select></label>}
          {mode === 'cohort' && <>
            <label className="flex items-center gap-1.5 text-xs text-slate-500">范围<select aria-label="客群时间范围" className={controlClass} value={windowDays} onChange={event => setWindowDays(Number(event.target.value) as WindowDays)}>
              {[7, 14, 30].map(days => <option key={days} value={days}>近 {days} 天</option>)}</select></label>
            <label className="flex items-center gap-1.5 text-xs text-slate-500">粒度<select aria-label="客群时间粒度" className={controlClass} value={grain} onChange={event => setGrain(event.target.value as Grain)}><option value="day">按日</option><option value="week">按周</option></select></label>
            <label className="flex items-center gap-1.5 text-xs text-slate-500">分箱<select aria-label="客群分箱尺度" className={controlClass} value={groups} onChange={event => setGroups(Number(event.target.value) as 5 | 10)}><option value={10}>10 组 · Q1–Q10</option><option value={5}>5 组 · 相邻合并</option></select></label>
          </>}
          <label className="flex items-center gap-1.5 text-xs text-slate-500"><CalendarDays size={13} />基准{mode === 'stability' ? '周' : '期'}<select aria-label="选择对比基准" className={controlClass} value={baselinePeriod} onChange={event => setBaselineSelection(event.target.value)}>
            {periodOptions.map(period => <option key={period} value={period}>{period}{period === currentPeriod ? '（当前）' : ''}</option>)}</select></label>
        </div>
      </div>
      <div className="mt-3 border-t border-slate-100 pt-3">{comparisonControls}</div>
      {mode === 'stability' && <p className="mt-2 text-[11px] leading-5 text-slate-500">{!props.loading && payload && matureWeeks.length === 0 ? '该目标在观察窗口内暂无到期样本达到 100 的分箱；坏账率留空，仍可查看客群结构与通过率。' : '默认分析最近有成熟分箱的周；可切换到最近观察周查看最新客群与通过率，未成熟的坏账率保持空白。'}</p>}
    </section>

    {!model.field ? <Note>当前业务环节暂无可选择的模型分。</Note>
      : props.loading ? <div className="flex min-h-[260px] items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white text-sm text-slate-500"><RefreshCw size={16} className="animate-spin" />正在读取模型分布与稳定性结果…</div>
      : props.error ? <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">{props.error}</div>
      : !current ? <Note>当前模型和筛选条件暂无已发布的{mode === 'stability' ? '稳定性' : '客群'}结果。可以切换业务环节或模型查看。</Note>
      : <>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Stat label={mode === 'cohort' ? `当前${grain === 'day' ? '日' : '周'}客户量` : '分析周客户量'} value={`${COUNTS.format(current.total)} ${countUnit}`} note={`${currentPeriod}${mode === 'stability' || grain === 'week' ? ' · 日去重客户量累计' : ' · 当日去重客户量'}`} />
          <Stat label="相对基准规模变化" value={baseline && baseline.total > 0 ? `${current.total - baseline.total >= 0 ? '+' : ''}${COUNTS.format(current.total - baseline.total)} ${countUnit}` : '—'} note={baseline ? `基准 ${baselinePeriod} · ${COUNTS.format(baseline.total)} ${countUnit}` : '暂无可比基准'} />
          <Stat label="最大分箱占比变化" value={shift ? `${points(shift.value)}` : '—'} note={shift ? `Q${shift.bin} · 当前期减基准期；pp 为百分点` : '没有可比样本'} />
          {mode === 'stability' ? <Stat label="可观察坏账率的分箱" value={`${stabilityRows.filter(row => row.week_start === currentPeriod && row.badrate != null).length} / 10`} note={`${TARGET_LABELS[target]} · 各箱到期样本 ≥ 100 才显示`} />
            : <Stat label="观察期数" value={`${periods.length} ${grain === 'day' ? '天' : '周'}`} note={`${startDay} ～ ${endDay} · 最多四个模型比较`} />}
        </div>
        {mode === 'stability' ? <StabilityCharts rows={stabilityRows} weeks={weeks} current={current} baseline={baseline} models={modelSets} target={target} alias={alias} />
          : <CohortCharts periods={periods} current={current} baseline={baseline} groups={groups} grain={grain} models={modelSets} alias={alias} startDay={startDay} endDay={endDay} />}
        {comparisons.rows.filter(item => item.error).map(item => <Note key={item.model.field}>{item.model.model} 对比结果读取失败：{item.error}。主模型图表仍可查看。</Note>)}
        <ModelSamples models={modelSets} alias={alias} target={target} currentPeriod={currentPeriod} mode={mode} grain={grain} startDay={startDay} endDay={endDay} />
        <Note>口径：Q1 为低分段、Q10 为高分段，不代表统一的风险方向。不同模型／筛选组合独立分箱，横向对比的是相对分数段，不是相同原始分值或相同客户。日量按客户去重；周量为日去重量累计。同一客户可能在多天出现。占比变化单位为百分点（pp）。{mode === 'stability' ? ' 首尾周可能不足 7 天，样本不足的坏账率保持空白。通过率与交易通过率沿用各自有标签样本作为分母。' : ' 周图按所选窗口内实际观察日累计，首尾周可能不完整。'}</Note>
      </>}
  </div>;
}

function StabilityCharts({ rows, weeks, current, baseline, models, target, alias }: {
  rows: ModelScoreStabilityWeekly[]; weeks: string[]; current: Distribution; baseline?: Distribution;
  models: Comparison[]; target: TargetMetric; alias: string;
}) {
  const labels = groupLabels(10);
  const byKey = new Map(rows.map(row => [`${row.week_start}|${row.bin}`, row]));
  const valueFor = (week: string, key: 'badrate' | 'approval_rate' | 'loan_success_rate') => labels.map((_, i) => asPercent(byKey.get(`${week}|${i + 1}`)?.[key]));
  const currentRows = rows.filter(row => row.week_start === current.period);
  const mature = currentRows.reduce((sum, row) => sum + row.target_base, 0);
  const selectedBins = [1, 3, 5, 8, 10];
  const subtitle = `${alias} · ${TARGET_LABELS[target]} · Q1–Q10 按分数升序 · 缺失值不连线`;
  return <div className="grid gap-4 xl:grid-cols-2">
    <Panel title="分箱坏账率周热力图" subtitle={`${subtitle} · 颜色为坏账率，悬停查看到期样本量`} option={shareHeatmap(weeks, labels, weeks.map(week => valueFor(week, 'badrate')), '坏账率', weeks.map(week => labels.map((_, i) => byKey.get(`${week}|${i + 1}`)?.target_base ?? 0)))} />
    <Panel title="代表分箱坏账率周对比" subtitle={`${subtitle} · 展示 Q1 / Q3 / Q5 / Q8 / Q10`} option={bars(weeks.map(dateLabel), selectedBins.map((bin, i) => ({ name: `Q${bin}`, color: CHART_COLORS[i], dashed: i % 2 === 1, values: weeks.map(week => asPercent(byKey.get(`${week}|${bin}`)?.badrate)) })))} />
    <Panel title="分析周与基准周坏账率" subtitle={`${TARGET_LABELS[target]} · 分析周 ${current.period} / 基准 ${baseline?.period ?? '—'} · 分母为各箱到期样本`} option={bars(labels, [
      { name: `当前 ${current.period}`, values: valueFor(current.period, 'badrate') },
      { name: `基准 ${baseline?.period ?? '—'}`, color: '#94a3b8', values: baseline ? valueFor(baseline.period, 'badrate') : labels.map(() => null) },
    ])} />
    <Panel title="通过率与交易通过率分箱对比" subtitle={`分析周 ${current.period} · 分母分别为审批标签样本 / 交易标签样本 · 缺失值留空`} option={bars(labels, [
      { name: '通过率', values: valueFor(current.period, 'approval_rate') },
      { name: '交易通过率', values: valueFor(current.period, 'loan_success_rate') },
    ])} />
    <Panel title="分箱客群占比变化" subtitle={`当前 ${current.period} 减基准 ${baseline?.period ?? '—'} · 单位：百分点（pp）`} option={shareDelta(labels, current.shares.map((share, i) => share == null || baseline?.shares[i] == null ? null : (share - baseline.shares[i]!) * 100))} />
    <Panel title="多模型分箱坏账率对比" subtitle={`${alias} · ${TARGET_LABELS[target]} · 统一比较周 ${current.period} · 各模型独立分箱`} option={lineChart(labels, models.map((item, index) => ({ name: item.model.model, color: CHART_COLORS[index], dashed: index > 0,
      values: labels.map((_, i) => asPercent(item.payload?.model_score_stability_weekly.find(row => row.alias === alias && row.target === target && row.week_start === current.period && row.bin === i + 1)?.badrate)),
    })))} />
    <Panel title="分析周分箱样本量" subtitle={`分析周 ${current.period} · 日去重客户累计与到期样本 · 到期样本合计 ${COUNTS.format(mature)}`} option={bars(labels, [
      { name: '日去重客户累计', values: current.counts },
      { name: `${TARGET_LABELS[target]} 到期样本`, color: '#94a3b8', values: labels.map((_, i) => byKey.get(`${current.period}|${i + 1}`)?.target_base ?? null) },
    ], 'count')} />
    <Panel title="周客群分箱结构" subtitle={`${alias} · 客户占比分母为该模型当周日去重客户累计 · 每周合计 100%`} option={composition(weeks, labels, weeks.map(week => labels.map((_, i) => asPercent(byKey.get(`${week}|${i + 1}`)?.customer_share))))} />
    <section className="min-w-0 rounded-xl border border-slate-200 bg-white xl:col-span-2">
      <details><summary className="flex cursor-pointer list-none items-center justify-between p-4 text-sm font-semibold text-slate-700">模型分稳定性明细 <ChevronDown size={15} /></summary>
        <div className="max-h-[380px] overflow-auto px-4 pb-4"><table className="w-full min-w-[880px] text-xs text-slate-600">
          <thead className="sticky top-0 bg-slate-50 text-left"><tr>{['统计周', '分箱', '日去重客户累计', '客户占比', '通过率', '交易通过率', `${TARGET_LABELS[target]} 坏账率`, '到期样本'].map(label => <th key={label} className="border-b border-slate-200 px-3 py-2 font-medium">{label}</th>)}</tr></thead>
          <tbody>{[...rows].sort((a, b) => b.week_start.localeCompare(a.week_start) || a.bin - b.bin).map(row => <tr key={`${row.week_start}|${row.bin}`} className="border-b border-slate-100 hover:bg-slate-50">
            <td className="px-3 py-2">{row.week_start}</td><td className="px-3 py-2">{row.bin_label}</td><td className="px-3 py-2 tabular-nums">{COUNTS.format(row.customer_count)}</td><td className="px-3 py-2">{percent(row.customer_share)}</td><td className="px-3 py-2">{percent(row.approval_rate)}</td><td className="px-3 py-2">{percent(row.loan_success_rate)}</td><td className="px-3 py-2">{percent(row.badrate)}</td><td className="px-3 py-2 tabular-nums">{COUNTS.format(row.target_base)}</td>
          </tr>)}</tbody></table></div>
      </details>
    </section>
  </div>;
}

function CohortCharts({ periods, current, baseline, groups, grain, models, alias, startDay, endDay }: {
  periods: Distribution[]; current: Distribution; baseline?: Distribution; groups: 5 | 10; grain: Grain;
  models: Comparison[]; alias: string; startDay: string; endDay: string;
}) {
  const labels = groupLabels(groups);
  const grouped = periods.map(item => groupedDistribution(item, groups));
  const now = groupedDistribution(current, groups);
  const before = baseline ? groupedDistribution(baseline, groups) : undefined;
  const compared = models.map(item => ({ ...item, periods: distributions((item.payload?.model_score_cohort_trend ?? []).filter(row => row.alias === alias && row.day >= startDay && row.day <= endDay), grain) }));
  const shares = (item: Distribution | undefined) => labels.map((_, i) => asPercent(item?.shares[i]));
  const context = `${alias} · ${startDay} ～ ${endDay} · ${grain === 'day' ? '当日去重客户' : '周内日去重量累计'}`;
  return <div className="grid gap-4 xl:grid-cols-2">
    <Panel title="客群规模与多模型覆盖趋势" subtitle={`${context} · 各模型有效分数客户量，人数差异可能来自覆盖差异`} option={lineChart(periods.map(item => dateLabel(item.period)), compared.map((item, i) => ({ name: item.model.model, color: CHART_COLORS[i], dashed: i > 0, values: periods.map(period => item.periods.find(other => other.period === period.period)?.total ?? null) })), 'count', true)} />
    <Panel title="客群分箱结构变化" subtitle={`${context} · ${groups} 组分箱 · 占比分母为该模型当期有效分数客户量`} option={composition(grouped.map(item => item.period), labels, grouped.map(item => shares(item)))} />
    <Panel title="分箱占比时间热力图" subtitle={`${context} · 浅色占比低、深色占比高 · 色阶按当前窗口范围调整，范围见图例 · 悬停查看占比与客户量`} option={shareHeatmap(grouped.map(item => item.period), labels, grouped.map(item => shares(item)), '客户占比', grouped.map(item => item.counts), 'observed')} height={350} wide />
    <Panel title="当前期与基准期客群分布" subtitle={`当前 ${current.period} / 基准 ${baseline?.period ?? '—'} · ${groups} 组分箱 · 单位：%`} option={bars(labels, [
      { name: `当前 ${current.period}`, values: shares(now) },
      { name: `基准 ${baseline?.period ?? '—'}`, color: '#94a3b8', values: shares(before) },
    ])} />
    <Panel title="各分箱客群占比变化" subtitle={`当前 ${current.period} 减基准 ${baseline?.period ?? '—'} · 正值表示占比增加 · 单位：百分点（pp）`} option={shareDelta(labels, now.shares.map((share, i) => share == null || before?.shares[i] == null ? null : (share - before.shares[i]!) * 100))} />
    <Panel title="多模型当前期分箱分布" subtitle={`${alias} · 统一比较期 ${current.period} · 模型分数尺度不一致，比较各自相对分箱`} option={bars(labels, compared.map((item, i) => ({ name: item.model.model, color: CHART_COLORS[i], values: shares(item.periods.find(period => period.period === current.period) ? groupedDistribution(item.periods.find(period => period.period === current.period)!, groups) : undefined) })))} />
    <Panel title="多模型累计客群分布" subtitle={`${alias} · ${current.period} · 从 Q1 累加到高分段，纵轴为累计客户占比（%）`} option={cumulative(labels, compared.map((item, i) => ({ name: item.model.model, color: CHART_COLORS[i], dashed: i > 0, values: shares(item.periods.find(period => period.period === current.period) ? groupedDistribution(item.periods.find(period => period.period === current.period)!, groups) : undefined) })))} />
    <section className="min-w-0 rounded-xl border border-slate-200 bg-white p-4 xl:col-span-2">
      <h3 className="text-sm font-semibold text-slate-700">当前期分箱客户量与占比</h3><p className="mt-1 text-xs text-slate-500">{current.period} · 分母 {COUNTS.format(current.total)} {grain === 'day' ? '人' : '人次'} · 当前与基准占比对照</p>
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">{labels.map((label, i) => <div key={label} className="rounded-lg border border-slate-100 bg-slate-50 p-3">
        <div className="text-xs font-medium text-slate-600">{label}</div><div className="mt-1 text-lg font-semibold tabular-nums text-slate-800">{percent(now.shares[i])}</div>
        <div className="mt-1 text-[11px] text-slate-500">{COUNTS.format(now.counts[i])} {grain === 'day' ? '人' : '人次'}</div><div className="mt-1 text-[11px] text-slate-500">变化 {now.shares[i] == null || before?.shares[i] == null ? '—' : points(now.shares[i]! - before.shares[i]!)}</div>
      </div>)}</div>
    </section>
  </div>;
}

function ModelSamples({ models, alias, target, currentPeriod, mode, grain, startDay, endDay }: {
  models: Comparison[]; alias: string; target: TargetMetric; currentPeriod: string; mode: 'stability' | 'cohort'; grain: Grain; startDay: string; endDay: string;
}) {
  return <section className="rounded-xl border border-slate-200 bg-white p-4">
    <h3 className="text-sm font-semibold text-slate-700">模型对比样本范围</h3><p className="mt-1 text-xs text-slate-500">{alias} · {currentPeriod} · 模型缺失当前期结果时不补零、不使用其他日期代替</p>
    <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{models.map((item, i) => {
      const weekly = (item.payload?.model_score_stability_weekly ?? []).filter(row => row.alias === alias && row.target === target && row.week_start === currentPeriod);
      const daily = distributions((item.payload?.model_score_cohort_trend ?? []).filter(row => row.alias === alias && row.day >= startDay && row.day <= endDay), grain).find(period => period.period === currentPeriod);
      const available = mode === 'stability' ? weekly.length > 0 : Boolean(daily);
      return <div key={item.model.field} className="min-w-0 border-l-2 pl-3" style={{ borderColor: CHART_COLORS[i] }}>
        <div className="truncate text-xs font-medium text-slate-700" title={item.model.field}>{item.model.model}</div>
        <div className="mt-1 text-sm font-semibold tabular-nums text-slate-800">{available ? `${COUNTS.format(mode === 'stability' ? sumCustomers(weekly) : daily!.total)} ${mode === 'stability' || grain === 'week' ? '人次' : '人'}` : '当前期暂无结果'}</div>
        <div className="mt-1 text-[11px] text-slate-500">{mode === 'stability' ? `到期样本 ${COUNTS.format(weekly.reduce((sum, row) => sum + row.target_base, 0))}` : daily ? `观察 ${daily.days} 天 · ${daily.firstDay} ～ ${daily.lastDay}` : '可切换模型或比较日期'}</div>
      </div>;
    })}</div>
  </section>;
}
