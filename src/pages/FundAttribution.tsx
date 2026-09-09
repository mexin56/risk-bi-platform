import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { EChartsOption } from 'echarts';
import ReactECharts from 'echarts-for-react';
import { toPng } from 'html-to-image';
import {
  AlertTriangle,
  Camera,
  Check,
  Database,
  Link2,
  LoaderCircle,
  RefreshCw,
  SearchCheck,
  ShieldAlert,
  Sparkles,
} from 'lucide-react';
import ChartCard from '@/components/ChartCard';
import FeishuTable, { StatusTag, type FeishuColumn } from '@/components/FeishuTable';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { baseOption } from '@/lib/chartTheme';
import { isAttributionRefreshReady } from '@/lib/attributionRefresh';
import { buildFundDailyTrendOption } from '@/lib/fundDailyTrend';
import { getTheme } from '@/lib/theme';
import {
  fetchFundAttribution,
  fetchFundPartitions,
  fetchFundPathTrend,
  fetchFundRuleStatusHistory,
  updateFundRuleStatus,
  type FundDashboard,
  type FundPathTrend,
  type FundRecord,
  type FundRuleStatusHistory,
  type FundWindowKey,
  type FundWindowMetric,
  type RuleStatus,
  type Severity,
} from '@/lib/fundMonitorApi';
import { LatestRequestGuard } from '@/lib/latestRequestGuard';

const numberFormatter = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 });
const WINDOW_ORDER: FundWindowKey[] = ['1d', '3d', '7d'];
const RULE_STATUS_OPTIONS: Array<{ value: RuleStatus; label: string }> = [
  { value: 0, label: '不需要处理' },
  { value: 1, label: '已上策略' },
  { value: 2, label: '持续观察' },
];
const RULE_STATUS_TABS: Array<{ value: RuleStatus | 'history'; label: string }> = [
  { value: 0, label: '发现规则' },
  { value: 1, label: '已上策略' },
  { value: 2, label: '持续观察监控' },
  { value: 'history', label: '打标记录' },
];
type ShareParams = Partial<Record<'pt' | 'offset' | 'path' | 'range' | 'lv' | 'src' | 'type' | 'win' | 'dim', string>>;

const SEVERITY: Record<Severity, { bg: string; border: string; text: string; dot: string; label: string }> = {
  slate: { bg: '#f8fafc', border: '#e2e8f0', text: '#64748b', dot: '#94a3b8', label: 'Level0' },
  yellow: { bg: '#fffbeb', border: '#fde68a', text: '#b45309', dot: '#f59e0b', label: 'Level1 黄色' },
  orange: { bg: '#fff7ed', border: '#fdba74', text: '#c2410c', dot: '#f97316', label: 'Level2 橙色' },
  red: { bg: '#fff1f2', border: '#fecdd3', text: '#e11d48', dot: '#f43f5e', label: 'Level3 红色' },
};

function formatNumber(value: number | null | undefined) {
  return value == null || Number.isNaN(value) ? '—' : numberFormatter.format(Number(value));
}

function formatFactor(value: number | null | undefined) {
  return value == null || Number.isNaN(value) ? '—' : `${Number(value).toFixed(2)}×`;
}

function formatRate(value: number | null | undefined) {
  return value == null || Number.isNaN(value) ? '—' : `${(Number(value) * 100).toFixed(4)}%`;
}

function formatSignedPercent(value: number | null | undefined) {
  const number = Number(value ?? 0);
  return `${number >= 0 ? '+' : ''}${number.toFixed(2)}%`;
}

function formatDate(value: string | null | undefined) {
  return value ? value.slice(5).replace('-', '/') : '—';
}

function readShareParams(): ShareParams {
  const query = new URLSearchParams(window.location.search);
  const result: ShareParams = {};
  for (const key of ['pt', 'offset', 'path', 'range', 'lv', 'src', 'type', 'win', 'dim'] as const) {
    const value = query.get(key);
    if (value) result[key] = value;
  }
  return result;
}

async function copyText(value: string) {
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    try {
      const area = document.createElement('textarea');
      area.value = value;
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      const ok = document.execCommand('copy');
      document.body.removeChild(area);
      return ok;
    } catch {
      return false;
    }
  }
}

function shadeHex(hex: string, amount: number) {
  const normalized = hex.replace('#', '');
  const mix = (offset: number) => {
    const value = parseInt(normalized.slice(offset, offset + 2), 16);
    const target = amount >= 0 ? 255 : 0;
    return Math.round(value + (target - value) * Math.abs(amount)).toString(16).padStart(2, '0');
  };
  return `#${mix(0)}${mix(2)}${mix(4)}`;
}

function hexWithAlpha(hex: string, alpha: number) {
  const normalized = hex.replace('#', '');
  return `rgba(${parseInt(normalized.slice(0, 2), 16)},${parseInt(normalized.slice(2, 4), 16)},${parseInt(normalized.slice(4, 6), 16)},${alpha})`;
}

function PathHoverTip({ path, children }: { path: string; children: React.ReactNode }) {
  return (
    <Tooltip delayDuration={150}>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side="top" collisionPadding={12} className="max-w-[560px] break-all border-slate-700 bg-slate-900/95 px-3 py-2 text-[12.5px] font-semibold leading-5 text-slate-50">
        {path}
      </TooltipContent>
    </Tooltip>
  );
}

function SeverityTag({ severity, text }: { severity: Severity; text?: string }) {
  const tone = SEVERITY[severity];
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap" style={{ background: tone.bg, borderColor: tone.border, color: tone.text }}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: tone.dot }} />
      {text ?? tone.label}
    </span>
  );
}

function SourceTag({ source }: { source: string }) {
  if (source.includes('专家') && source.includes('Top-K')) return <StatusTag text="Top-K + 专家" tone="blue" />;
  if (source.includes('专家')) return <StatusTag text="专家规则" tone="orange" />;
  return <StatusTag text="Top-K" tone="green" />;
}

function WindowCard({ metric, primary = false }: { metric: FundWindowMetric; primary?: boolean }) {
  const tone = SEVERITY[metric.severity];
  return (
    <div className="rounded-xl border px-3 py-2.5" style={{ background: primary ? `${metric.color}0D` : '#fff', borderColor: primary ? `${metric.color}88` : '#e2e8f0' }}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: metric.color }} /><span className="text-[12px] font-semibold text-slate-800">{metric.label}</span>{primary && <span className="rounded bg-white/80 px-1 py-0.5 text-[9px] font-medium text-slate-500">主窗口</span>}</div>
          <div className="mt-0.5 text-[10px] text-slate-400">{metric.observation_days}天观察 · {metric.baseline_days}天基准 · {metric.purpose}</div>
        </div>
        <SeverityTag severity={metric.severity} text={metric.level_label.replace('Level0 无预警', '无预警')} />
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-[10px] sm:grid-cols-6">
        <div><div className="text-slate-400">观察异常</div><div className="mt-0.5 font-semibold text-slate-700 tabular-nums">{formatNumber(metric.observation_abnormal_count)}</div></div>
        <div><div className="text-slate-400">异常率</div><div className="mt-0.5 font-semibold text-slate-700 tabular-nums">{formatRate(metric.observation_rate)}</div></div>
        <div><div className="text-slate-400">总订单</div><div className="mt-0.5 font-semibold text-slate-700 tabular-nums">{formatNumber(metric.observation_total_count)}</div></div>
        <div><div className="text-slate-400">异常量增长</div><div className="mt-0.5 font-semibold tabular-nums" style={{ color: tone.text }}>{metric.growth_display == null ? (metric.is_new_anomaly ? '新增' : '—') : formatFactor(metric.growth_display)}</div></div>
        <div><div className="text-slate-400">异常率提升</div><div className="mt-0.5 font-semibold tabular-nums" style={{ color: tone.text }}>{metric.rate_lift_display == null ? (metric.is_new_anomaly ? '新增' : '—') : formatFactor(metric.rate_lift_display)}</div></div>
        <div><div className="text-slate-400">z-score</div><div className="mt-0.5 font-semibold text-slate-700 tabular-nums">{metric.z_score.toFixed(2)}</div></div>
      </div>
      <div className="mt-2 flex items-center justify-between border-t border-slate-200/70 pt-2 text-[10px] text-slate-400">
        <span>异常日均 {metric.baseline_abnormal_daily.toFixed(1)} → {metric.observation_abnormal_daily.toFixed(1)}</span>
        <span className="tabular-nums">超额 {metric.excess_abnormal_count >= 0 ? '+' : ''}{formatNumber(metric.excess_abnormal_count)}</span>
      </div>
      {metric.special_labels.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{metric.special_labels.map((label) => <span key={label} className="rounded border border-slate-200 bg-slate-100 px-1 py-0.5 text-[10px] text-slate-500">{label}</span>)}</div>}
    </div>
  );
}

function LoadingState({ text = '正在加载资金归结归因结果…' }: { text?: string }) {
  return (
    <div className="flex min-h-[520px] flex-col items-center justify-center rounded-2xl border border-slate-200 bg-white/60 backdrop-blur-xl text-center shadow-[0_1px_3px_rgba(15,23,42,0.05)]">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50 text-blue-500"><LoaderCircle size={24} className="animate-spin" /></div>
      <div className="text-[15px] font-semibold text-slate-700">{text}</div>
      <div className="mt-2 max-w-md text-[12px] leading-5 text-slate-400">按 v1.2 全历史基准期口径运行近1/3/7天观察窗口、Top-K 下钻与专家强制路径。</div>
    </div>
  );
}

function SelectedPathAnalysis({
  record,
  pathTrend,
  pathTrendLoading,
  pathTrendError,
  trendOption,
  trendRange,
  onTrendRangeChange,
  onRetry,
}: {
  record: FundRecord;
  pathTrend: FundPathTrend | null;
  pathTrendLoading: boolean;
  pathTrendError: string | null;
  trendOption: EChartsOption;
  trendRange: number;
  onTrendRangeChange: (value: number) => void;
  onRetry: () => void;
}) {
  const currentTrend = pathTrend?.record_id === record.id ? pathTrend : null;
  const visibleDaily = currentTrend?.daily.slice(-trendRange) ?? [];
  const visibleDays = visibleDaily.length || Math.min(trendRange, currentTrend?.summary.period_days ?? trendRange);
  const totalAbnormal = visibleDaily.reduce((sum, item) => sum + item.abnormal_order_count, 0);
  const latest = visibleDaily[visibleDaily.length - 1];
  const previous = visibleDaily[visibleDaily.length - 2];
  const peak = visibleDaily.reduce((max, item) => item.abnormal_order_count > max.abnormal_order_count ? item : max, visibleDaily[0]);
  const changePct = latest && previous && previous.abnormal_order_count > 0 ? (latest.abnormal_order_count / previous.abnormal_order_count - 1) * 100 : 0;
  return (
    <ChartCard title="选中路径 · 归因解释与近60天趋势" subtitle="点击下方预警表中的路径，趋势和三个观察窗口会同步切换" accent={SEVERITY[record.severity].dot} extra={<div className="flex items-center gap-2"><SourceTag source={record.source} /><SeverityTag severity={record.severity} text={record.level_label} /></div>}>
      <div className="px-4 pb-4 pt-2">
        <div className="flex flex-col gap-3 rounded-xl border border-slate-100 bg-slate-50/70 px-4 py-3 lg:flex-row lg:items-center">
          <div className="min-w-0 flex-1"><div className="truncate text-[13px] font-semibold leading-6 text-slate-800" title={record.path}>{record.path}</div><div className="mt-1 flex flex-wrap items-center gap-1.5">{record.conditions.map((condition) => <span key={`${condition.field}:${condition.value}`} className="rounded-md border border-slate-200 bg-white px-1.5 py-0.5 text-[10.5px] text-slate-600"><span className="text-slate-400">{condition.label}</span>={condition.value}</span>)}</div></div>
          <div className="flex shrink-0 flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500"><span>异常类型 <b className="ml-1 text-slate-700">{record.anomaly_type}</b></span><span>命中窗口 <b className="ml-1 text-slate-700">{record.hit_windows.length ? record.hit_windows.map((item) => ({ '1d': '近1天', '3d': '近3天', '7d': '近7天' }[item])).join('、') : '无'}</b></span><span>来源说明 <b className="ml-1 text-slate-700">{record.rule_note || 'Top-K 自动发现'}</b></span></div>
        </div>
        <div className="mt-3 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.75fr)_minmax(370px,0.9fr)]">
          <section className="overflow-hidden rounded-2xl border border-slate-100 bg-white/60 backdrop-blur-xl">
            <div className="flex items-center justify-between border-b border-slate-100 px-3.5 py-2.5"><div><div className="text-[12px] font-semibold text-slate-800">近{visibleDays}天异常订单趋势</div><div className="mt-0.5 text-[10px] text-slate-400">柱形为路径异常订单，折线为路径异常率</div></div><span className="theme-select-wrap"><select value={trendRange} onChange={(event) => onTrendRangeChange(Number(event.target.value))} className="theme-select" aria-label="选择趋势显示范围">{[7, 15, 30, 60].map((days) => <option key={days} value={days}>近{days}天</option>)}</select></span></div>
            {pathTrendLoading && <div className="flex h-[350px] flex-col items-center justify-center gap-2 text-[12px] text-slate-400"><LoaderCircle size={20} className="animate-spin text-blue-500" />正在准备选中路径趋势…</div>}
            {!pathTrendLoading && pathTrendError && <div className="flex h-[260px] flex-col items-center justify-center gap-3 text-center"><div className="text-[12px] text-rose-500">趋势加载失败：{pathTrendError}</div><button onClick={onRetry} className="rounded-lg bg-blue-500 px-3 py-1.5 text-[11px] font-medium text-white hover:bg-blue-600">重新加载趋势</button></div>}
            {!pathTrendLoading && !pathTrendError && currentTrend && <><div className="grid grid-cols-2 gap-2 px-3.5 pt-3 sm:grid-cols-6"><div className="rounded-lg border border-blue-100 bg-blue-50/60 px-2.5 py-2"><div className="text-[10px] text-slate-400">{visibleDays}天累计异常</div><div className="mt-0.5 text-[17px] font-semibold text-slate-700 tabular-nums">{formatNumber(totalAbnormal)}</div></div><div className="rounded-lg border border-slate-100 bg-white px-2.5 py-2"><div className="text-[10px] text-slate-400">最新日</div><div className="mt-0.5 text-[17px] font-semibold text-slate-700 tabular-nums">{formatNumber(latest?.abnormal_order_count)}</div></div><div className="rounded-lg border border-slate-100 bg-white px-2.5 py-2"><div className="text-[10px] text-slate-400">较前一日</div><div className={`mt-0.5 text-[17px] font-semibold tabular-nums ${changePct >= 0 ? 'text-rose-500' : 'text-emerald-600'}`}>{formatSignedPercent(changePct)}</div></div><div className="rounded-lg border border-slate-100 bg-white px-2.5 py-2"><div className="text-[10px] text-slate-400">{visibleDays}天峰值</div><div className="mt-0.5 text-[17px] font-semibold text-slate-700 tabular-nums">{formatNumber(peak?.abnormal_order_count)}</div><div className="text-[9.5px] text-slate-400">{peak?.date}</div></div><div className="rounded-lg border border-violet-100 bg-violet-50/60 px-2.5 py-2"><div className="text-[10px] text-slate-400">最新异常率</div><div className="mt-0.5 text-[17px] font-semibold text-violet-700 tabular-nums">{formatRate(latest?.abnormal_rate)}</div></div><div className="rounded-lg border border-emerald-100 bg-emerald-50/60 px-2.5 py-2"><div className="text-[10px] text-slate-400">主窗口基准日均</div><div className="mt-0.5 text-[17px] font-semibold text-emerald-700 tabular-nums">{formatNumber(currentTrend.primary_window.baseline_daily)}</div></div></div><ReactECharts option={trendOption} style={{ height: 280 }} notMerge /><div className="-mt-1 flex flex-wrap justify-center gap-x-3 gap-y-1 px-3.5 pb-3 text-[10px] text-slate-400"><span><i className="mr-1 inline-block h-2 w-2 rounded-sm bg-blue-500" />路径异常订单</span><span><i className="mr-1 inline-block h-0.5 w-3 align-middle bg-orange-500" />异常率</span><span><i className="mr-1 inline-block h-2 w-3 bg-blue-100" />观察期</span><span><i className="mr-1 inline-block w-3 border-t border-dashed align-middle border-emerald-500" />基准日均</span></div></>}
          </section>
          <section className="rounded-xl border border-slate-100 bg-slate-50/50 p-3"><div className="mb-2.5 flex items-center justify-between"><div><div className="text-[12px] font-semibold text-slate-800">分窗口归因解释</div><div className="mt-0.5 text-[10px] text-slate-400">观察量、异常量增长、异常率提升与 z-score 同时判断</div></div><SearchCheck size={15} className="text-blue-500" /></div><div className="space-y-2.5">{WINDOW_ORDER.map((key) => <WindowCard key={key} metric={record.windows[key]} primary={key === record.primary_window} />)}</div></section>
        </div>
      </div>
    </ChartCard>
  );
}

function allFundRows(dashboard: FundDashboard) {
  const groups = [dashboard.merged_alerts, dashboard.top_k.single_downstream, dashboard.top_k.pair_downstream, dashboard.top_k.third_alerts, dashboard.expert.single, dashboard.expert.pair, dashboard.expert.third, dashboard.review_items];
  const seen = new Set<string>();
  return groups.flat().filter((record) => {
    if (seen.has(record.canonical_path)) return false;
    seen.add(record.canonical_path);
    return true;
  });
}

export default function FundAttribution() {
  const share = useRef(readShareParams()).current;
  const [dashboard, setDashboard] = useState<FundDashboard | null>(null);
  const [partitions, setPartitions] = useState<string[]>([]);
  const [partitionRanges, setPartitionRanges] = useState<Record<string, { min: string; max: string }>>({});
  const [selectedPartition, setSelectedPartition] = useState(share.pt ?? '');
  const [daysBack, setDaysBack] = useState(Math.max(0, Number(share.offset ?? 0) || 0));
  const [selected, setSelected] = useState<FundRecord | null>(null);
  const [pathTrend, setPathTrend] = useState<FundPathTrend | null>(null);
  const [pathTrendLoading, setPathTrendLoading] = useState(false);
  const [pathTrendError, setPathTrendError] = useState<string | null>(null);
  const [pathTrendRequest, setPathTrendRequest] = useState(0);
  const [levelFilter, setLevelFilter] = useState<number | 'all'>(share.lv && ['1', '2', '3'].includes(share.lv) ? Number(share.lv) : 'all');
  const [sourceFilter, setSourceFilter] = useState<'all' | 'topk' | 'expert'>(share.src === 'topk' || share.src === 'expert' ? share.src : 'all');
  const [typeFilter, setTypeFilter] = useState(share.type ?? 'all');
  const [windowFilter, setWindowFilter] = useState<'all' | FundWindowKey>(share.win && ['1d', '3d', '7d'].includes(share.win) ? share.win as FundWindowKey : 'all');
  const [dimFilter, setDimFilter] = useState(share.dim ?? 'all');
  const [resultTab, setResultTab] = useState<'alerts' | 'trend'>('alerts');
  const [ruleStatusTab, setRuleStatusTab] = useState<RuleStatus | 'history'>(0);
  const [savingRuleStatus, setSavingRuleStatus] = useState<string | null>(null);
  const [statusHistory, setStatusHistory] = useState<FundRuleStatusHistory[]>([]);
  const [statusHistoryLoading, setStatusHistoryLoading] = useState(false);
  const [statusHistoryError, setStatusHistoryError] = useState<string | null>(null);
  const [trendRange, setTrendRange] = useState([7, 15, 30, 60].includes(Number(share.range)) ? Number(share.range) : 60);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shareCopied, setShareCopied] = useState(false);
  const [shooting, setShooting] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const selectedAnalysisRef = useRef<HTMLDivElement>(null);
  const loadRequestGuard = useRef(new LatestRequestGuard()).current;

  const applyDashboard = useCallback((payload: FundDashboard) => {
    setDashboard(payload);
    setSelectedPartition(payload.meta.partition);
    const rows = allFundRows(payload);
    setSelected((current) => rows.find((record) => record.canonical_path === current?.canonical_path) ?? rows.find((record) => record.id === share.path) ?? payload.highlight ?? rows[0] ?? null);
    setPathTrend(null);
    setPathTrendError(null);
  }, [share.path]);

  const reloadPartitions = useCallback((force = false) => {
    void fetchFundPartitions(force).then(({ partitions: values, ranges }) => { setPartitions(values); setPartitionRanges(ranges ?? {}); }).catch(() => undefined);
  }, []);

  const load = useCallback(async (force = false, pt?: string, offset = 0) => {
    const requestId = loadRequestGuard.begin();
    const current = () => loadRequestGuard.isCurrent(requestId);
    if (force) setRefreshing(true); else setLoading(true);
    setError(null);
    let asyncMode = false;
    try {
      const payload = await fetchFundAttribution(pt, force, offset);
      if (!current()) return;
      applyDashboard(payload);
      if (force && payload.meta.async_refresh) {
        asyncMode = true;
        const baseline = payload.meta.generated_at;
        void (async () => {
          for (let attempt = 0; attempt < 12; attempt += 1) {
            await new Promise((resolve) => setTimeout(resolve, 15000));
            if (!current()) return;
            const fresh = await fetchFundAttribution(pt, false, offset);
            if (isAttributionRefreshReady(fresh.meta.generated_at, baseline, fresh.meta)) { applyDashboard(fresh); break; }
          }
          if (current()) setRefreshing(false);
        })().catch(() => undefined);
      }
    } catch (err) {
      if (current()) setError(err instanceof Error ? err.message : '无法获取资金归结归因数据');
    } finally {
      if (current()) { setLoading(false); if (!asyncMode) setRefreshing(false); }
    }
  }, [applyDashboard, loadRequestGuard]);

  useEffect(() => { reloadPartitions(false); void load(false, share.pt || undefined, Number(share.offset ?? 0) || 0); }, [load, reloadPartitions, share]);

  const loadStatusHistory = useCallback(async () => {
    setStatusHistoryLoading(true); setStatusHistoryError(null);
    try { setStatusHistory((await fetchFundRuleStatusHistory()).records); } catch (err) { setStatusHistoryError(err instanceof Error ? err.message : '无法加载打标记录'); } finally { setStatusHistoryLoading(false); }
  }, []);
  useEffect(() => { void loadStatusHistory(); }, [loadStatusHistory]);

  const activeRecord = selected ?? dashboard?.highlight ?? dashboard?.merged_alerts[0] ?? null;
  const allRows = useMemo(() => dashboard ? allFundRows(dashboard) : [], [dashboard]);
  const anomalyTypes = useMemo(() => Array.from(new Set(allRows.map((record) => record.anomaly_type))).sort(), [allRows]);
  const filteredAlerts = useMemo(() => {
    if (ruleStatusTab === 'history') return [];
    return allRows.filter((record) => {
      const statusMatched = ruleStatusTab === 0 ? !record.is_tracked_only : (record.status ?? 0) === ruleStatusTab;
      const sourceMatched = sourceFilter === 'all' || (sourceFilter === 'topk' && record.source.includes('Top-K')) || (sourceFilter === 'expert' && record.source.includes('专家'));
      return statusMatched && (levelFilter === 'all' || record.level === levelFilter) && sourceMatched && (typeFilter === 'all' || record.anomaly_type === typeFilter) && (windowFilter === 'all' || record.primary_window === windowFilter) && (dimFilter === 'all' || record.layer === dimFilter);
    });
  }, [allRows, dimFilter, levelFilter, ruleStatusTab, sourceFilter, typeFilter, windowFilter]);
  const ruleStatusCounts = useMemo(() => ({ 0: allRows.filter((record) => !record.is_tracked_only).length, 1: allRows.filter((record) => (record.status ?? 0) === 1).length, 2: allRows.filter((record) => (record.status ?? 0) === 2).length }), [allRows]);
  const availableOffsets = useMemo(() => {
    const range = partitionRanges[selectedPartition];
    const min = range?.min ?? dashboard?.meta.table_date_min;
    const max = range?.max ?? dashboard?.meta.table_date_max;
    if (!min || !max) return [0];
    const total = Math.max(1, Math.floor((Date.parse(max) - Date.parse(min)) / 86400000) + 1);
    return Array.from({ length: Math.ceil(total / 15) }, (_, index) => index * 15);
  }, [dashboard, partitionRanges, selectedPartition]);
  const obsRange = useMemo(() => dashboard && dashboard.meta.partition === selectedPartition ? { start: dashboard.meta.date_start, end: dashboard.meta.date_end } : partitionRanges[selectedPartition]?.max ? { start: partitionRanges[selectedPartition].min, end: partitionRanges[selectedPartition].max, pending: true } : null, [dashboard, partitionRanges, selectedPartition]);

  const selectAlertPath = useCallback((record: FundRecord) => { setSelected(record); setPathTrend(null); setPathTrendError(null); setPathTrendRequest((value) => value + 1); window.setTimeout(() => selectedAnalysisRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0); }, []);
  useEffect(() => {
    if (!activeRecord) return;
    const requestId = pathTrendRequest;
    setPathTrendLoading(true); setPathTrendError(null);
    void fetchFundPathTrend(activeRecord.id, selectedPartition || undefined, daysBack).then((result) => { if (requestId === pathTrendRequest) setPathTrend(result); }).catch((err) => { if (requestId === pathTrendRequest) setPathTrendError(err instanceof Error ? err.message : '无法加载该路径趋势'); }).finally(() => { if (requestId === pathTrendRequest) setPathTrendLoading(false); });
  }, [activeRecord, daysBack, pathTrendRequest, selectedPartition]);

  const updateRuleStatus = useCallback(async (record: FundRecord, status: RuleStatus) => {
    setSavingRuleStatus(record.canonical_path); setError(null);
    try {
      const updated = await updateFundRuleStatus(record.canonical_path, status, dashboard?.meta.partition ?? selectedPartition, record);
      const patch = (item: FundRecord) => item.canonical_path === record.canonical_path ? { ...item, status: updated.status, status_updated_at: updated.updated_at, status_updated_by: updated.updated_by, action_date: updated.action_date } : item;
      setDashboard((current) => current ? { ...current, merged_alerts: current.merged_alerts.map(patch) } : current);
      setSelected((current) => current?.canonical_path === record.canonical_path ? patch(current) : current);
      void loadStatusHistory();
    } catch (err) { setError(err instanceof Error ? err.message : '规则状态更新失败'); } finally { setSavingRuleStatus(null); }
  }, [dashboard?.meta.partition, loadStatusHistory, selectedPartition]);

  const buildShareUrl = useCallback(() => {
    const url = new URL(window.location.href); url.searchParams.set('page', 'attribution'); url.searchParams.set('tab', 'fund');
    const assign = (key: string, value: string | number | null | undefined) => { if (value == null || value === '' || value === 'all') url.searchParams.delete(key); else url.searchParams.set(key, String(value)); };
    assign('pt', selectedPartition); assign('offset', daysBack || null); assign('path', activeRecord?.id); assign('range', trendRange !== 60 ? trendRange : null); assign('lv', levelFilter !== 'all' ? levelFilter : null); assign('src', sourceFilter); assign('type', typeFilter); assign('win', windowFilter); assign('dim', dimFilter);
    return url.toString();
  }, [activeRecord?.id, daysBack, dimFilter, levelFilter, selectedPartition, sourceFilter, trendRange, typeFilter, windowFilter]);
  const handleShare = useCallback(async () => { if (await copyText(buildShareUrl())) { setShareCopied(true); window.setTimeout(() => setShareCopied(false), 2000); } else window.prompt('复制以下链接分享给同事：', buildShareUrl()); }, [buildShareUrl]);
  const handleScreenshot = useCallback(async () => { if (!contentRef.current) return; setShooting(true); try { const dataUrl = await toPng(contentRef.current, { backgroundColor: '#f4f6fa', pixelRatio: 2 }); const link = document.createElement('a'); link.download = `资金归结_${selectedPartition || '最新'}_${new Date().toISOString().slice(0, 16).replace(/[T:]/g, '-')}.png`; link.href = dataUrl; link.click(); } catch { /* 截图失败不阻断页面 */ } finally { setShooting(false); } }, [selectedPartition]);

  const activeTheme = getTheme();
  const trendBrand = activeTheme.brand;
  const trendHover = shadeHex(trendBrand, -0.14);
  const trendAccent = shadeHex(trendBrand, -0.42);
  const trendTint = hexWithAlpha(trendBrand, 0.10);
  const trendGuide = hexWithAlpha(trendAccent, 0.78);
  const trendOption = useMemo<EChartsOption>(() => {
    if (!pathTrend) return {};
    const trend = pathTrend.daily.slice(-trendRange);
    const window = pathTrend.primary_window;
    const clamp = (value: string | null) => !value || !trend.length ? null : value <= trend[0].date ? trend[0].date : value >= trend[trend.length - 1].date ? trend[trend.length - 1].date : value;
    const areaStart = clamp(window.observation_start); const areaEnd = clamp(window.observation_end);
    return { ...baseOption(), grid: { left: 16, right: 20, top: 38, bottom: 12, containLabel: true }, legend: { ...baseOption().legend, right: undefined, top: 2, left: 'center' }, tooltip: { ...baseOption().tooltip, trigger: 'axis', formatter: (params: Array<{ dataIndex?: number }>) => { const point = trend[params[0]?.dataIndex ?? 0]; return point ? [`<b>${point.date}</b>`, `路径异常订单：<b>${formatNumber(point.abnormal_order_count)}</b> 件`, `路径总订单：${formatNumber(point.order_count)} 件`, `路径异常率：<b>${formatRate(point.abnormal_rate)}</b>`].join('<br/>') : ''; } }, xAxis: { ...baseOption().xAxis, data: trend.map((item) => formatDate(item.date)) }, yAxis: [{ ...baseOption().yAxis, name: '异常订单', nameTextStyle: { color: '#8f959e', fontSize: 10 } }, { ...baseOption().yAxis, name: '异常率', position: 'right', min: 0, splitLine: { show: false }, axisLabel: { color: '#8f959e', fontSize: 10, formatter: (value: number) => `${(value * 100).toFixed(2)}%` }, nameTextStyle: { color: '#8f959e', fontSize: 10 } }], series: [{ name: '路径异常订单', type: 'bar', barMaxWidth: 26, data: trend.map((item) => item.abnormal_order_count), itemStyle: { color: trendBrand, borderRadius: [4, 4, 0, 0] }, emphasis: { itemStyle: { color: trendHover } }, markPoint: { symbolSize: 38, label: { color: '#fff', fontSize: 10, formatter: '峰值' }, itemStyle: { color: trendAccent }, data: [{ type: 'max', name: '峰值' }] }, markLine: window.baseline_daily > 0 ? { symbol: 'none', lineStyle: { color: trendGuide, type: 'dashed' }, label: { color: trendAccent, fontSize: 10, formatter: `基准日均 ${window.baseline_daily.toFixed(1)}` }, data: [{ yAxis: window.baseline_daily }] } : undefined, markArea: areaStart && areaEnd && areaStart <= areaEnd ? { silent: true, itemStyle: { color: trendTint }, label: { color: trendAccent, fontSize: 10, formatter: `${window.label}观察期` }, data: [[{ xAxis: formatDate(areaStart) }, { xAxis: formatDate(areaEnd) }]] } : undefined }, { name: '异常率', type: 'line', yAxisIndex: 1, smooth: true, symbol: 'circle', symbolSize: 5, connectNulls: true, lineStyle: { width: 2, color: trendAccent }, itemStyle: { color: trendAccent }, data: trend.map((item) => item.abnormal_rate) }] };
  }, [pathTrend, trendAccent, trendBrand, trendGuide, trendHover, trendRange, trendTint]);
  const marketTrendOption = useMemo(
    () => buildFundDailyTrendOption(dashboard?.daily_trend ?? [], { bar: trendBrand, line: '#ed7d31' }, baseOption),
    [dashboard?.daily_trend, trendBrand],
  );

  const alertColumns: FeishuColumn<FundRecord>[] = [
    { key: 'status', title: '状态', width: 142, align: 'center', render: (record) => <select value={record.status ?? 0} disabled={savingRuleStatus === record.canonical_path} onChange={(event) => void updateRuleStatus(record, Number(event.target.value) as RuleStatus)} aria-label={`设置规则状态 ${record.path}`} className="theme-select max-w-[132px]">{RULE_STATUS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select> },
    ...(ruleStatusTab === 1 || ruleStatusTab === 2 ? [{ key: 'action_date', title: '措施日期', width: 104, align: 'center' as const, render: (record: FundRecord) => record.status === 0 ? '—' : (record.action_date ?? '—') }] : []),
    { key: 'level_label', title: '等级', sticky: true, width: 104, render: (record) => record.level === 0 ? <span className="text-[11px] text-slate-400">无预警</span> : <SeverityTag severity={record.severity} text={`L${record.level}`} /> },
    { key: 'source', title: '来源', width: 118, render: (record) => <SourceTag source={record.source} /> },
    { key: 'path', title: '异常归因路径', width: 360, render: (record) => <PathHoverTip path={record.path}><button onClick={() => selectAlertPath(record)} className="max-w-[340px] cursor-pointer truncate text-left font-medium text-slate-700 underline-offset-2 hover:text-blue-600 hover:underline" title="悬停查看完整值; 点击查看该路径近60天趋势">{record.path}</button></PathHoverTip> },
    { key: 'layer', title: '层级', width: 70, align: 'center' },
    { key: 'anomaly_type', title: '异常类型', width: 90 },
    { key: 'primary_window_label', title: '主窗口', width: 78, align: 'center' },
    { key: 'observation_abnormal_count', title: '观察异常', width: 88, align: 'right', render: (record) => formatNumber(record.observation_abnormal_count) },
    { key: 'growth_factor', title: '异常量增长', width: 96, align: 'right', render: (record) => formatFactor(record.windows[record.primary_window].growth_display) },
    { key: 'rate_lift_factor', title: '异常率提升', width: 96, align: 'right', render: (record) => formatFactor(record.windows[record.primary_window].rate_lift_display) },
    { key: 'z_score', title: 'z-score', width: 76, align: 'right', render: (record) => record.z_score.toFixed(2) },
    { key: 'excess_abnormal_count', title: '超额异常', width: 100, align: 'right', render: (record) => `${record.excess_abnormal_count >= 0 ? '+' : ''}${formatNumber(record.excess_abnormal_count)}` },
  ];
  const historyColumns: FeishuColumn<FundRuleStatusHistory>[] = [
    { key: 'status', title: '标记状态', width: 104, render: (row) => row.status === 1 ? '已上策略' : '持续观察' },
    { key: 'canonical_path', title: '异常归因路径', width: 360 }, { key: 'entered_pt', title: '进入 pt', width: 104, align: 'center' }, { key: 'entered_at', title: '进入时间', width: 168 }, { key: 'entered_by', title: '进入操作人', width: 112 }, { key: 'exited_pt', title: '移出 pt', width: 104, align: 'center', render: (row) => row.exited_pt ?? '—' }, { key: 'exited_at', title: '移出时间', width: 168, render: (row) => row.exited_at ?? '—' }, { key: 'exited_by', title: '移出操作人', width: 112, render: (row) => row.exited_by ?? '—' }, { key: 'is_active', title: '当前状态', width: 96, align: 'center', render: (row) => row.is_active ? '进行中' : '已结束' },
  ];

  if (loading && !dashboard) return <LoadingState />;
  if (error && !dashboard) return <div className="flex min-h-[520px] flex-col items-center justify-center rounded-2xl border border-rose-100 bg-white/60 text-center"><div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-rose-50 text-rose-500"><ShieldAlert size={24} /></div><div className="text-[15px] font-semibold text-slate-700">资金归结服务暂不可用</div><div className="mt-2 max-w-lg text-[12px] leading-5 text-slate-400">{error}</div><button onClick={() => void load(true, selectedPartition || undefined, daysBack)} className="mt-5 inline-flex items-center gap-2 rounded-lg bg-blue-500 px-4 py-2 text-[12px] font-medium text-white hover:bg-blue-600"><RefreshCw size={14} />重试连接</button></div>;
  if (!dashboard) return <LoadingState />;
  const { meta, rules, summary } = dashboard;
  return (
    <div className="mx-auto max-w-[1440px] space-y-4 pb-2" data-testid="fund-attribution-content" ref={contentRef}>
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white/60 px-2.5 py-1.5 text-[10.5px] text-slate-500 backdrop-blur-xl"><span className="text-slate-400">观察区间</span><span className="theme-select-wrap"><select value={daysBack} onChange={(event) => { const value = Number(event.target.value); setDaysBack(value); void load(false, selectedPartition || undefined, value); }} className="theme-select" aria-label="选择观察区间">{availableOffsets.map((off) => <option key={off} value={off}>{off === 0 ? '最近窗口' : `${off}天前`}</option>)}</select></span><span className="font-medium text-slate-700 tabular-nums">{obsRange ? `${obsRange.start} ～ ${obsRange.end}` : '—'}</span>{obsRange?.pending && <span className="inline-flex items-center gap-1 rounded bg-blue-50 px-1.5 py-0.5 text-[10px] text-blue-600"><LoaderCircle size={10} className="animate-spin" />正在加载 pt={selectedPartition} 数据…</span>}</div>
        <div className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white/60 px-2.5 py-1.5 text-[10.5px] text-slate-500 backdrop-blur-xl"><span className="text-slate-400">数据分区</span><span className="theme-select-wrap"><select value={selectedPartition} onChange={(event) => { const pt = event.target.value; setSelectedPartition(pt); setDaysBack(0); void load(false, pt, 0); }} className="theme-select" aria-label="选择数据分区">{partitions.map((pt) => <option key={pt} value={pt}>pt={pt}</option>)}</select></span></div>
        <button onClick={() => { void load(true, selectedPartition || undefined, daysBack); reloadPartitions(true); }} disabled={refreshing} className="inline-flex items-center gap-1.5 rounded-lg bg-blue-500 px-3 py-1.5 text-[11px] font-medium text-white transition-colors hover:bg-blue-600 disabled:opacity-60"><RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />{refreshing ? '重新计算中' : '刷新归因'}</button>
        <span className="inline-flex items-center gap-1 text-[10.5px] text-slate-400"><Database size={12} />{meta.table}</span><span className={meta.cache_hit ? 'text-emerald-600' : 'text-blue-500'}>{meta.cache_hit ? '命中缓存' : '本次为最新计算结果'}</span>
        <div className="ml-auto flex items-center gap-1.5"><button onClick={() => void handleShare()} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-medium text-slate-600 hover:border-blue-300 hover:text-blue-600">{shareCopied ? <Check size={13} className="text-emerald-500" /> : <Link2 size={13} />}{shareCopied ? '已复制' : '分享'}</button><button onClick={() => void handleScreenshot()} disabled={shooting} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-medium text-slate-600 hover:border-blue-300 hover:text-blue-600 disabled:opacity-60">{shooting ? <LoaderCircle size={13} className="animate-spin" /> : <Camera size={13} />}{shooting ? '生成中…' : '截屏'}</button></div>
      </div>
      {error && <div className="flex items-center gap-2 rounded-xl border border-orange-200 bg-orange-50 px-4 py-2.5 text-[12px] text-orange-700"><AlertTriangle size={15} />刷新失败，当前继续展示上一次成功结果：{error}</div>}
      <ChartCard title="合并预警结果" subtitle="Top-K 单维/二级/三级下钻名单与专家强制路径全部展示；鼠标悬停路径显示完整值，点击查看近60天趋势" accent="#f97316">
        <div role="tablist" aria-label="归因结果视图" className="flex items-center gap-1 border-b border-slate-100 px-4 pt-3">
          {([{ value: 'alerts', label: '合并预警结果' }, { value: 'trend', label: '大盘日趋势' }] as const).map((tab) => <button key={tab.value} role="tab" aria-selected={resultTab === tab.value} onClick={() => setResultTab(tab.value)} className={`border-b-2 px-3 py-2 text-[12px] font-medium transition-colors ${resultTab === tab.value ? 'border-blue-500 text-blue-600' : 'border-transparent text-slate-400 hover:text-slate-600'}`}>{tab.label}</button>)}
        </div>
        {resultTab === 'alerts' && <>
          <div role="tablist" aria-label="规则处理状态" className="flex items-center gap-1 border-b border-slate-100 px-4 pt-3">{RULE_STATUS_TABS.map((tab) => { const active = ruleStatusTab === tab.value; const count = tab.value === 'history' ? statusHistory.length : ruleStatusCounts[tab.value]; return <button key={tab.value} role="tab" aria-selected={active} onClick={() => setRuleStatusTab(tab.value)} className={`border-b-2 px-3 py-2 text-[12px] font-medium transition-colors ${active ? 'border-blue-500 text-blue-600' : 'border-transparent text-slate-400 hover:text-slate-600'}`}>{tab.label}<span className={`ml-1.5 rounded-full px-1.5 py-0.5 text-[10px] tabular-nums ${active ? 'bg-blue-50 text-blue-600' : 'bg-slate-100 text-slate-400'}`}>{count}</span></button>; })}</div>
          {ruleStatusTab === 'history' ? <>{statusHistoryError && <div className="flex items-center gap-2 px-4 pb-2 pt-3 text-[12px] text-rose-600"><AlertTriangle size={15} />加载打标记录失败：{statusHistoryError}<button onClick={() => void loadStatusHistory()} className="rounded-lg bg-rose-50 px-3 py-1.5 font-medium">重试</button></div>}{statusHistoryLoading && <div className="flex min-h-[180px] items-center justify-center gap-2 text-[12px] text-slate-400"><LoaderCircle size={18} className="animate-spin text-blue-500" />正在加载打标记录…</div>}{!statusHistoryLoading && !statusHistoryError && statusHistory.length === 0 && <div className="flex min-h-[180px] items-center justify-center text-[12px] text-slate-400">暂无打标记录</div>}{!statusHistoryLoading && statusHistory.length > 0 && <FeishuTable columns={historyColumns} data={statusHistory} maxHeight={470} rowKey={(row) => String(row.id)} />}</> : <><div className="flex flex-wrap items-center gap-2 px-4 pb-2"><span className="theme-select-wrap"><select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value as typeof sourceFilter)} className="theme-select" aria-label="按来源筛选"><option value="all">全部来源</option><option value="topk">Top-K</option><option value="expert">专家</option></select></span><span className="theme-select-wrap"><select value={dimFilter} onChange={(event) => setDimFilter(event.target.value)} className="theme-select" aria-label="按层级筛选"><option value="all">全部层级</option><option value="单维">单维</option><option value="二级">二级</option><option value="三级">三级</option></select></span><span className="theme-select-wrap"><select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)} className="theme-select" aria-label="按异常类型筛选"><option value="all">全部类型</option>{anomalyTypes.map((type) => <option key={type} value={type}>{type}</option>)}</select></span><span className="theme-select-wrap"><select value={windowFilter} onChange={(event) => setWindowFilter(event.target.value as typeof windowFilter)} className="theme-select" aria-label="按主窗口筛选"><option value="all">全部窗口</option>{WINDOW_ORDER.map((key) => <option key={key} value={key}>{key === '1d' ? '近1日' : key === '3d' ? '近3日' : '近7日'}</option>)}</select></span><span className="ml-auto text-[10.5px] text-slate-400">共 {filteredAlerts.length} 条</span><div className="flex items-center gap-1.5">{(['all', 3, 2, 1] as const).map((filter) => <button key={String(filter)} onClick={() => setLevelFilter(filter)} className={`rounded-md px-2 py-1 text-[10.5px] ${levelFilter === filter ? 'bg-slate-700 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`}>{filter === 'all' ? '全部等级' : `L${filter}`}</button>)}</div></div><FeishuTable columns={alertColumns} data={filteredAlerts} maxHeight={470} rowKey={(record) => record.id} /></>}
        </>}
        {resultTab === 'trend' && <div className="px-4 pb-4 pt-2">
          <div className="mb-2 text-[10.5px] text-slate-400">全样本每日异常订单与异常率，日期范围与本次资金归因结果一致</div>
          <ReactECharts option={marketTrendOption} style={{ height: 320 }} notMerge />
        </div>}
      </ChartCard>
      {resultTab === 'alerts' && activeRecord && <div ref={selectedAnalysisRef}><SelectedPathAnalysis record={activeRecord} pathTrend={pathTrend} pathTrendLoading={pathTrendLoading} pathTrendError={pathTrendError} trendOption={trendOption} trendRange={trendRange} onTrendRangeChange={setTrendRange} onRetry={() => setPathTrendRequest((value) => value + 1)} /></div>}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <ChartCard title="内部最高候选与专家规则" subtitle="内部 Top 候选用于解释未达正式预警门槛的路径；专家强制路径按方案固定展示" accent="#f59e0b"><div className="px-4 pb-4 pt-3"><div className="space-y-2">{Object.entries(dashboard.top_k.internal_top).filter(([, item]) => item).map(([key, item]) => <div key={key} className="flex items-center justify-between gap-3 border-b border-slate-50 pb-2 text-[11px]"><div className="min-w-0"><span className="mr-2 text-slate-400">{item!.layer}</span><span className="truncate font-medium text-slate-700">{item!.path}</span></div><div className="shrink-0 text-right text-slate-500">观察异常 {formatNumber(item!.observation_abnormal_count)} · 增长 {item!.growth_factor == null ? '新增' : formatFactor(item!.growth_factor)} · z {item!.z_score.toFixed(2)}<div className="text-[10px] text-amber-700">{item!.reason}</div></div></div>)}{!Object.values(dashboard.top_k.internal_top).some(Boolean) && <div className="text-[11.5px] text-slate-400">各层级候选均无待复核的 Level0 路径。</div>}</div><div className="mt-3 rounded-lg border border-amber-100 bg-amber-50 px-3 py-2 text-[10.5px] leading-5 text-amber-800"><Sparkles size={14} className="mr-1 inline" />专家强制单维：{rules.expert_forced_single.map((rule) => rule.label || `${rule.field}=${rule.value || rule.values?.join('、')}`).join('；') || '暂无'}</div></div></ChartCard>
        <ChartCard title="预警阈值与运行口径" subtitle="Level1/2/3 均要求观察量、异常量增长、异常率提升、z-score 同时满足" accent="#4e83fd"><div className="px-4 pb-4 pt-3"><div className="grid grid-cols-1 gap-2 md:grid-cols-3">{rules.thresholds.map((threshold) => { const severity: Severity = threshold.level === 3 ? 'red' : threshold.level === 2 ? 'orange' : 'yellow'; return <div key={threshold.level} className="rounded-lg border p-2.5" style={{ background: SEVERITY[severity].bg, borderColor: SEVERITY[severity].border }}><div className="mb-1"><SeverityTag severity={severity} text={`Level${threshold.level}`} /></div><div className="space-y-0.5 text-[10.5px] text-slate-600"><div>观察异常订单 ≥ {threshold.min_observation_count}</div><div>异常量增长 ≥ {threshold.min_growth_factor}×</div><div>异常率提升 ≥ {threshold.min_rate_lift_factor}× · z ≥ {threshold.min_z_score}</div></div></div>; })}</div><div className="mt-3 flex items-start gap-2 rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-[10.5px] leading-5 text-blue-700"><Sparkles size={14} className="mt-0.5 shrink-0" /><span>近1/3/7天为观察窗口，观察期以外全部历史日期作为对应窗口基准期；异常订单口径直接使用输入字段 {rules.field_labels ? 'payee_last1_cnt_cate' : '异常标记'}。</span></div><div className="mt-3 space-y-0.5">{dashboard.config_summary.map((entry) => <div key={entry.item} className="flex gap-2 border-b border-slate-50 py-0.5 text-[10.5px]"><span className="w-20 shrink-0 text-slate-400">{entry.item}</span><span className="text-slate-600">{entry.content}</span></div>)}</div></div></ChartCard>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7"><div className="rounded-xl border border-slate-200 bg-white/60 px-3 py-2"><div className="text-[10px] text-slate-400">总订单数</div><div className="text-[18px] font-semibold text-slate-800">{formatNumber(summary.total_order_count)}</div></div><div className="rounded-xl border border-rose-100 bg-rose-50/50 px-3 py-2"><div className="text-[10px] text-slate-400">异常订单数</div><div className="text-[18px] font-semibold text-rose-600">{formatNumber(summary.abnormal_order_count)}</div></div><div className="rounded-xl border border-slate-200 bg-white/60 px-3 py-2"><div className="text-[10px] text-slate-400">全样本异常率</div><div className="text-[18px] font-semibold text-slate-800">{formatRate(summary.overall_abnormal_rate)}</div></div><div className="rounded-xl border border-slate-200 bg-white/60 px-3 py-2"><div className="text-[10px] text-slate-400">正式预警</div><div className="text-[18px] font-semibold text-slate-800">{summary.merged_alert_count}</div></div><div className="rounded-xl border border-rose-100 bg-rose-50/50 px-3 py-2"><div className="text-[10px] text-slate-400">Level3</div><div className="text-[18px] font-semibold text-rose-600">{summary.level3_count}</div></div><div className="rounded-xl border border-orange-100 bg-orange-50/50 px-3 py-2"><div className="text-[10px] text-slate-400">Level2</div><div className="text-[18px] font-semibold text-orange-600">{summary.level2_count}</div></div><div className="rounded-xl border border-amber-100 bg-amber-50/50 px-3 py-2"><div className="text-[10px] text-slate-400">Level1</div><div className="text-[18px] font-semibold text-amber-600">{summary.level1_count}</div></div></div>
    </div>
  );
}
