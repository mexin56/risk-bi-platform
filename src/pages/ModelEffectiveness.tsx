import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, ArrowDown, ArrowUp, ArrowUpDown, Database, Filter, RefreshCw } from 'lucide-react';
import ModelScoreDashboard from '@/components/model-monitoring/ModelScoreDashboard';
import {
  fetchModelMonitoring,
  fetchModelMonitoringFilters,
  fetchModelScoreMonitoring,
  type ModelEffectWeekly,
  type ModelMonitoringPayload,
  type ModelScoreMonitoringPayload,
  type TargetMetric,
} from '@/lib/modelMonitoringApi';
import { commonWeeklySampleStats, metricBarWidth, modelFieldsWithAuc, weeksWithAuc } from '@/lib/modelEffectTable';

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
const filterLabelClassName = 'flex max-w-full shrink-0 flex-col gap-1.5 text-[12px] font-medium text-slate-600';

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

const MODEL_MONITOR_TABS: Array<{ key: ModelMonitorTab; label: string }> = [
  { key: 'effect', label: '模型效果监控' },
  { key: 'stability', label: '模型分稳定性变化' },
  { key: 'cohort', label: '客群变化' },
];

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
  const [activeTab, setActiveTab] = useState<ModelMonitorTab>(() =>
    new URLSearchParams(window.location.search).get('page') === 'stability' ? 'stability' : 'effect');
  const [primaryModelsByScene, setPrimaryModelsByScene] = useState<Record<string, string>>({});
  const [scorePayload, setScorePayload] = useState<ModelScoreMonitoringPayload | null>(null);
  const [scoreLoading, setScoreLoading] = useState(false);
  const [scoreError, setScoreError] = useState<string | null>(null);
  const [scoreRefreshKey, setScoreRefreshKey] = useState(0);
  const scoreRefreshPending = useRef(false);
  const loadRequest = useRef(0);
  const scoreCache = useRef(new Map<string, Promise<ModelScoreMonitoringPayload>>());
  const scoreActive = activeTab !== 'effect';

  // Choose the best-covered model within the applied business stage.
  const fallbackModelField = useMemo(() => {
    const stageFields = new Set((payload?.model_effect_weekly ?? []).filter(row => row.alias === appliedAlias && row.score_valid_count > 0).map(row => row.model));
    const stageSamples = new Map<string, number>();
    for (const row of payload?.model_effect_weekly ?? []) {
      if (row.alias === appliedAlias && row.target === 'fpd7') stageSamples.set(row.model, (stageSamples.get(row.model) ?? 0) + row.score_valid_count);
    }
    const candidates = (payload?.model_coverage ?? []).filter((row) => (row.valid ?? 0) > 0 && stageFields.has(row.field));
    const sorted = [...candidates].sort(
      (left, right) => (stageSamples.get(right.field) ?? 0) - (stageSamples.get(left.field) ?? 0) || left.field.localeCompare(right.field),
    );
    return sorted[0]?.field ?? '';
  }, [payload, appliedAlias]);
  const primarySceneKey = JSON.stringify([appliedAlias, appliedFlagMobType, appliedFlagProduct, appliedCashSerCallNode]);
  const preferredPrimaryField = primaryModelsByScene[primarySceneKey] ?? appliedModelField;
  const primaryFieldAvailable = Boolean(preferredPrimaryField && payload?.model_coverage.some(row =>
    row.field === preferredPrimaryField && row.valid > 0) && payload.model_effect_weekly.some(row =>
    row.alias === appliedAlias && row.model === preferredPrimaryField && row.score_valid_count > 0));
  const effectiveModelField = primaryFieldAvailable ? preferredPrimaryField : fallbackModelField;

  const load = async (
    force = false,
    nextLabels: LabelFilters = { flagMobType: appliedFlagMobType, flagProduct: appliedFlagProduct, cashSerCallNode: appliedCashSerCallNode },
    selectionOverrides: { alias?: string; modelField?: string } = {},
  ) => {
    const requestId = ++loadRequest.current;
    setError(null);
    setRefreshing(force);
    setLoading(!force);
    try {
      const result = await fetchModelMonitoring(undefined, force, {
        flagMobType: nextLabels.flagMobType || undefined,
        flagProduct: nextLabels.flagProduct || undefined,
        cashSerCallNode: nextLabels.cashSerCallNode || undefined,
      });
      if (requestId !== loadRequest.current) return;
      const availableAliases = aliasesFor(result);
      const requestedAlias = selectionOverrides.alias ?? alias;
      const nextAlias = requestedAlias && availableAliases.includes(requestedAlias) ? requestedAlias : availableAliases[0] ?? '';
      const availableModelFields = new Set(result.model_effect_weekly.filter(row => row.alias === nextAlias && row.score_valid_count > 0).map(row => row.model));
      const requestedModelField = selectionOverrides.modelField ?? modelField;
      const nextModelField = requestedModelField && availableModelFields.has(requestedModelField) ? requestedModelField : '';
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
      if (requestId === loadRequest.current) setError(cause instanceof Error ? cause.message : '模型效果数据加载失败');
    } finally {
      if (requestId === loadRequest.current) {
        setLoading(false);
        setRefreshing(false);
      }
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
    if (!scoreActive || !appliedAlias || !effectiveModelField) {
      setScoreLoading(false);
      setScoreError(null);
      return undefined;
    }
    let alive = true;
    const forceScoreRefresh = scoreRefreshPending.current;
    scoreRefreshPending.current = false;
    setScoreLoading(true);
    setScoreError(null);
    setScorePayload(null);
    const filters = {
      flagMobType: appliedFlagMobType || undefined,
      flagProduct: appliedFlagProduct || undefined,
      cashSerCallNode: appliedCashSerCallNode || undefined,
    };
    const cacheKey = JSON.stringify([payload?.meta.partition, payload?.meta.generated_at, effectiveModelField,
      appliedAlias, appliedTarget, appliedFlagMobType, appliedFlagProduct, appliedCashSerCallNode, scoreRefreshKey]);
    if (forceScoreRefresh) scoreCache.current.clear();
    let request = scoreCache.current.get(cacheKey);
    if (!request) {
      if (scoreCache.current.size >= 24) scoreCache.current.clear();
      request = fetchModelScoreMonitoring(effectiveModelField, appliedAlias, appliedTarget,
        payload?.meta.partition, forceScoreRefresh, filters);
      scoreCache.current.set(cacheKey, request);
      void request.catch(() => scoreCache.current.delete(cacheKey));
    }
    void request.then((result) => {
      if (alive) setScorePayload(result);
    }).catch((cause) => {
      if (alive) setScoreError(cause instanceof Error ? cause.message : '分箱数据加载失败');
    }).finally(() => {
      if (alive) setScoreLoading(false);
    });
    return () => {
      alive = false;
    };
  }, [scoreActive, appliedAlias, appliedCashSerCallNode, appliedFlagMobType, appliedFlagProduct, effectiveModelField, appliedTarget, payload?.meta.partition, payload?.meta.generated_at, scoreRefreshKey]);

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
  const stageModelFields = new Set(payload.model_effect_weekly.filter(row => row.alias === appliedAlias && row.score_valid_count > 0).map(row => row.model));
  const draftStageFields = new Set(payload.model_effect_weekly.filter(row => row.alias === alias && row.score_valid_count > 0).map(row => row.model));
  const selectableModelOptions = modelOptions.filter(row => draftStageFields.has(row.field));
  const comparisonModelOptions = modelOptions.filter(row => stageModelFields.has(row.field));
  const selectedModelName = modelOptions.find((row) => row.field === effectiveModelField)?.model ?? effectiveModelField;
  const usingFallbackModel = activeTab !== 'effect' && !primaryFieldAvailable && Boolean(effectiveModelField);
  const displayedModelFields = modelFieldsWithAuc(selectedRows, modelOptions.map((row) => row.field), appliedModelField);
  const modelCount = activeTab === 'effect' ? displayedModelFields.length : comparisonModelOptions.length;

  const applyFilters = () => {
    setAppliedAlias(alias);
    setAppliedTarget(target);
    setAppliedModelField(modelField);
    setAppliedFlagMobType(flagMobType);
    setAppliedFlagProduct(flagProduct);
    setAppliedCashSerCallNode(cashSerCallNode);
    void load(false, { flagMobType, flagProduct, cashSerCallNode }, { alias, modelField });
  };

  const refreshAll = () => {
    scoreRefreshPending.current = true;
    setScorePayload(null);
    setScoreRefreshKey((value) => value + 1);
    void Promise.all([
      load(true, { flagMobType: appliedFlagMobType, flagProduct: appliedFlagProduct, cashSerCallNode: appliedCashSerCallNode }, { alias: appliedAlias, modelField: appliedModelField }),
      loadFilterOptions(true),
    ]);
  };

  return (
    <div className="min-h-full min-w-0 w-full bg-[#f5f7fa] text-slate-900">
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-[0_8px_24px_-20px_rgba(15,23,42,0.45)]">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-200 bg-white px-5 py-4">
          <div>
            <div className="flex items-center gap-2 text-[17px] font-semibold text-slate-900">
              <span className="h-5 w-1 rounded-full" style={{ background: 'var(--brand)' }} />
              模型分监控
            </div>
            <div className="mt-1 text-[12px] text-slate-500">按业务环节、客户类型和产品标签查看已计算的模型效果、稳定性与客群趋势</div>
          </div>
          <div className="flex items-center gap-2 text-[12px] text-slate-500">
            <span className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1.5"><Database size={13} /> pt={payload.meta.partition}</span>
            <span className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1.5">模型 {modelCount}</span>
            <span className="rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 text-emerald-700" title="时间为业务结果生成时间；页面读取 MyWorkflow 发布的 DuckDB 结果">结果生成 · {new Date(payload.meta.generated_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })}</span>
            <button type="button" onClick={refreshAll} title="读取最新发布结果，计算任务在 MyWorkflow 调度" disabled={refreshing} className="inline-flex h-8 items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 text-[12px] font-medium text-slate-600 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50">
              <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />刷新结果
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
          <div className="flex flex-wrap items-end gap-x-2 gap-y-3">
            <label className={`${filterLabelClassName} w-[120px]`}>
              业务环节（alias）
              <select value={alias} onChange={(event) => setAlias(event.target.value)} className={selectClassName} aria-label="选择业务环节">
                {availableAliases.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
            <label className={`${filterLabelClassName} w-[132px]`}>
              客户类型
              <select value={flagMobType} onChange={(event) => setFlagMobType(event.target.value)} className={selectClassName} aria-label="选择客户类型">
                <option value="">全部客户类型</option>
                {mobTypeSelectOptions.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
            <label className={`${filterLabelClassName} w-[132px]`}>
              产品标签
              <select value={flagProduct} onChange={(event) => setFlagProduct(event.target.value)} className={selectClassName} aria-label="选择产品标签">
                <option value="">全部产品标签</option>
                {productSelectOptions.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
            <label className={`${filterLabelClassName} w-[144px]`}>
              服务节点
              <select value={cashSerCallNode} onChange={(event) => setCashSerCallNode(event.target.value)} className={selectClassName} aria-label="选择服务节点">
                <option value="">全部服务节点</option>
                {cashSerCallNodeSelectOptions.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
            <label className={`${filterLabelClassName} w-[96px]`}>
              目标变量
              <select value={target} onChange={(event) => setTarget(event.target.value as TargetMetric)} className={selectClassName} aria-label="选择目标变量">
                {(Object.keys(targetLabels) as TargetMetric[]).map((item) => <option key={item} value={item}>{targetLabels[item]}</option>)}
              </select>
            </label>
            <div className="flex max-w-full flex-wrap items-end gap-2">
            {!scoreActive && <label className={`${filterLabelClassName} w-[168px]`}>
              模型分
              <select value={modelField} onChange={(event) => setModelField(event.target.value)} className={selectClassName} aria-label="选择模型分">
                <option value="">全部模型分（默认）</option>
                {selectableModelOptions.map((item) => <option key={item.field} value={item.field}>{item.model}</option>)}
              </select>
            </label>}
            <button type="button" onClick={applyFilters} disabled={loading} className="inline-flex h-9 w-[88px] shrink-0 items-center justify-center gap-1.5 rounded-md px-3 text-[13px] font-semibold text-white shadow-sm transition hover:brightness-95 focus:outline-none disabled:cursor-wait disabled:opacity-60" style={{ background: 'var(--brand)', boxShadow: '0 4px 10px rgba(var(--brand-rgb), 0.22)' }}>
              {loading && <RefreshCw size={13} className="animate-spin" />} {loading ? '查询中' : '查询'}
            </button>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-[11px] text-slate-400">{scoreActive
              ? '主模型可在下方切换，图表即时更新；本次页面使用期间按场景记住选择，可添加三个对比模型'
              : '全部模型分：展示当前场景下全部可用模型的效果；选择单个模型后点击查询'}</span>
            <span className="ml-auto text-[11px] text-slate-400">标签筛选变更后会重新读取当前 pt 的模型效果数据{loading ? '，请等待查询完成' : ''}</span>
          </div>
        </div>

        <div className="p-4">
          {usingFallbackModel && (
            <div className="mb-3 rounded-lg border border-sky-200 bg-sky-50 px-3.5 py-2 text-[12px] text-sky-700">
              默认主模型为当前业务环节内覆盖量最高的模型分 <span className="font-medium">{selectedModelName}</span>，可在下方切换。
            </div>
          )}
          {activeTab === 'effect' && <WeeklyEffectTable payload={payload} alias={appliedAlias} target={appliedTarget} modelField={appliedModelField} />}
          {activeTab !== 'effect' && <ModelScoreDashboard
            mode={activeTab} payload={scorePayload} loading={scoreLoading} error={scoreError}
            model={{ field: effectiveModelField, model: selectedModelName }} models={comparisonModelOptions}
            onModelChange={field => setPrimaryModelsByScene(current => ({ ...current, [primarySceneKey]: field }))}
            modelSelectionDisabled={loading}
            alias={appliedAlias} target={appliedTarget} partition={payload.meta.partition}
            generatedAt={payload.meta.generated_at} refreshKey={scoreRefreshKey}
            filters={{ flagMobType: appliedFlagMobType || undefined, flagProduct: appliedFlagProduct || undefined, cashSerCallNode: appliedCashSerCallNode || undefined }}
          />}
        </div>

        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-slate-200 px-5 py-3 text-[11px] text-slate-500">
          {activeTab === 'effect' && <><span>count 为成熟样本数</span><span>成熟样本数&lt;100 时该周留空</span><span>count/badrate 已合并到周标题括号内</span></>}
          {activeTab !== 'effect' && <span>图表读取已发布结果 · 不触发重新计算</span>}
          <span>周起始日按周一统计</span>
          {error && <span className="font-medium text-rose-600">刷新失败：{error}</span>}
        </div>
      </div>
    </div>
  );
}
