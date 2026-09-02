import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { EChartsOption } from 'echarts';
import ReactECharts from 'echarts-for-react';
import { toPng } from 'html-to-image';
import {
  AlertTriangle,
  Camera,
  Check,
  ChevronRight,
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
import { getTheme } from '@/lib/theme';
import {
  fetchAttributionPartitions,
  fetchAttributionPathTrend,
  fetchCreditAttribution,
  updateAttributionRuleStatus,
  type AttributionDashboard,
  type AttributionPathTrend,
  type AttributionRecord,
  type RuleStatus,
  type Severity,
  type WindowMetric,
} from '@/lib/creditAttributionApi';
import { LatestRequestGuard } from '@/lib/latestRequestGuard';

const numberFormatter = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 });

const SEVERITY: Record<Severity, { bg: string; border: string; text: string; dot: string; label: string }> = {
  slate: { bg: '#f8fafc', border: '#e2e8f0', text: '#64748b', dot: '#94a3b8', label: 'Level0' },
  yellow: { bg: '#fffbeb', border: '#fde68a', text: '#b45309', dot: '#f59e0b', label: 'Level1 黄色' },
  orange: { bg: '#fff7ed', border: '#fdba74', text: '#c2410c', dot: '#f97316', label: 'Level2 橙色' },
  red: { bg: '#fff1f2', border: '#fecdd3', text: '#e11d48', dot: '#f43f5e', label: 'Level3 红色' },
};

const WINDOW_ORDER: Array<'1d' | '3d' | '7d'> = ['1d', '3d', '7d'];

const RULE_STATUS_OPTIONS: Array<{ value: RuleStatus; label: string }> = [
  { value: 0, label: '不需要处理' },
  { value: 1, label: '已上策略' },
  { value: 2, label: '持续观察' },
];

const RULE_STATUS_TABS: Array<{ value: RuleStatus; label: string }> = [
  { value: 0, label: '发现规则' },
  { value: 1, label: '已上策略' },
  { value: 2, label: '持续观察监控' },
];

function formatNumber(value: number | undefined | null) {
  return numberFormatter.format(Number(value ?? 0));
}

function formatFactor(value: number | undefined | null) {
  const number = Number(value ?? 0);
  return number >= 999 ? '∞' : `${number.toFixed(2)}×`;
}

function formatSignedPercent(value: number | undefined | null) {
  const number = Number(value ?? 0);
  return `${number >= 0 ? '+' : ''}${number.toFixed(2)}%`;
}

/** 通过率显示: 快照缺失 approval 数据时为 null, 显示 — */
function formatApprovalRate(value: number | undefined | null) {
  return value == null ? '—' : `${value.toFixed(2)}%`;
}

function formatDate(value: string | null | undefined) {
  if (!value) return '—';
  return value.slice(5).replace('-', '/');
}

/** 分享链接白名单参数键 */
const SHARE_KEYS = ['pt', 'offset', 'path', 'range', 'lv', 'src', 'type', 'win', 'dim'] as const;
type ShareParams = Partial<Record<(typeof SHARE_KEYS)[number], string>>;

/** 从 URL 读取分享参数(仅取白名单键) */
function readShareParams(): ShareParams {
  const query = new URLSearchParams(window.location.search);
  const result: ShareParams = {};
  for (const key of SHARE_KEYS) {
    const value = query.get(key);
    if (value != null && value !== '') result[key] = value;
  }
  return result;
}

/** 复制文本到剪贴板: 优先 Clipboard API, 局域网 HTTP 环境降级 execCommand */
async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const area = document.createElement('textarea');
      area.value = text;
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
  const red = parseInt(normalized.slice(0, 2), 16);
  const green = parseInt(normalized.slice(2, 4), 16);
  const blue = parseInt(normalized.slice(4, 6), 16);
  return `rgba(${red},${green},${blue},${alpha})`;
}

/** 鼠标悬停即放大显示完整归因路径(表格单元格默认 "..." 截断)。 */
function PathHoverTip({ path, children }: { path: string; children: React.ReactNode }) {
  return (
    // 注意结构: TooltipTrigger 必须直接包裹真实 DOM 元素(asChild 链式合并事件)
    <Tooltip delayDuration={150}>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent
        side="top"
        collisionPadding={12}
        className="max-w-[560px] break-all border-slate-700 bg-slate-900/95 px-3 py-2 text-[12.5px] font-semibold leading-5 text-slate-50"
      >
        {path}
      </TooltipContent>
    </Tooltip>
  );
}

function SeverityTag({ severity, text }: { severity: Severity; text?: string }) {
  const tone = SEVERITY[severity];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap"
      style={{ background: tone.bg, borderColor: tone.border, color: tone.text }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: tone.dot }} />
      {text ?? tone.label}
    </span>
  );
}

function SourceTag({ source }: { source: string }) {
  if (source === '专家规则') return <StatusTag text="专家规则" tone="orange" />;
  if (source.includes('专家')) return <StatusTag text="Top-K + 专家" tone="blue" />;
  return <StatusTag text="Top-K" tone="green" />;
}

function WindowCard({ metric, primary = false }: { metric: WindowMetric; primary?: boolean }) {
  const tone = SEVERITY[metric.severity];
  return (
    <div
      className="rounded-xl border px-3 py-2.5"
      style={{
        background: primary ? `${metric.color}0D` : '#fff',
        borderColor: primary ? `${metric.color}88` : '#e2e8f0',
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ background: metric.color }} />
            <span className="text-[12px] font-semibold text-slate-800">{metric.label}</span>
            {primary && <span className="rounded bg-white/80 px-1 py-0.5 text-[9px] font-medium text-slate-500">主窗口</span>}
          </div>
          <div className="mt-0.5 text-[10px] text-slate-400">{metric.observation_days}天观察 · {metric.baseline_days}天基准 · {metric.purpose}</div>
        </div>
        <SeverityTag severity={metric.severity} text={metric.level_label.replace('Level0 无预警', '无预警')} />
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-[10px] sm:grid-cols-6">
        <div><div className="text-slate-400">观察量</div><div className="mt-0.5 font-semibold text-slate-700 tabular-nums">{formatNumber(metric.observation_count)}</div></div>
        <div><div className="text-slate-400">通过率（件数）</div><div className="mt-0.5 font-semibold text-slate-700 tabular-nums">{formatApprovalRate(metric.approval_rate_pct)}</div></div>
        <div><div className="text-slate-400">通过率（人数）</div><div className="mt-0.5 font-semibold text-slate-700 tabular-nums">{formatApprovalRate(metric.cid_approval_rate_pct)}</div></div>
        <div><div className="text-slate-400">增长</div><div className="mt-0.5 font-semibold tabular-nums" style={{ color: tone.text }}>{formatFactor(metric.growth_factor)}</div></div>
        <div><div className="text-slate-400">结构</div><div className="mt-0.5 font-semibold tabular-nums" style={{ color: tone.text }}>{formatFactor(metric.structure_lift_factor)}</div></div>
        <div><div className="text-slate-400">z-score</div><div className="mt-0.5 font-semibold text-slate-700 tabular-nums">{metric.z_score.toFixed(2)}</div></div>
      </div>
      <div className="mt-2 flex items-center justify-between border-t border-slate-200/70 pt-2 text-[10px] text-slate-400">
        <span>日均 {metric.baseline_daily.toFixed(1)} → {metric.observation_daily.toFixed(1)}</span>
        <span className="tabular-nums">超额 {metric.excess_count >= 0 ? '+' : ''}{formatNumber(metric.excess_count)}</span>
      </div>
    </div>
  );
}

function LoadingState({ text = '正在从 MaxCompute 聚合授信数据…' }: { text?: string }) {
  return (
    <div className="flex min-h-[520px] flex-col items-center justify-center rounded-2xl border border-slate-200 bg-white/60 backdrop-blur-xl text-center shadow-[0_1px_3px_rgba(15,23,42,0.05)]">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50 text-blue-500">
        <LoaderCircle size={24} className="animate-spin" />
      </div>
      <div className="text-[15px] font-semibold text-slate-700">{text}</div>
      <div className="mt-2 max-w-md text-[12px] leading-5 text-slate-400">
        正在按 v2.4 口径运行单维全量扫描、Top-K 下钻与专家路径。首次计算通常需要约 1–2 分钟，结果将缓存 1 小时。
      </div>
    </div>
  );
}

function SelectedPathAnalysis({
  record,
  pathTrend,
  pathTrendLoading,
  pathTrendError,
  trendOption,
  trendBrand,
  trendAccent,
  trendTint,
  trendRange,
  onTrendRangeChange,
  onRetry,
}: {
  record: AttributionRecord;
  pathTrend: AttributionPathTrend | null;
  pathTrendLoading: boolean;
  pathTrendError: string | null;
  trendOption: EChartsOption;
  trendBrand: string;
  trendAccent: string;
  trendTint: string;
  trendRange: number;
  onTrendRangeChange: (value: number) => void;
  onRetry: () => void;
}) {
  const currentTrend = pathTrend?.record_id === record.id ? pathTrend : null;
  // 趋势覆盖天数由后端返回(period_days);旧快照未重算时自动降级显示实际天数
  const periodDays = currentTrend?.summary.period_days ?? 60;
  // 视窗切片: 图表与汇总卡片均只统计所选范围内数据
  const visibleDaily = currentTrend ? currentTrend.daily.slice(-trendRange) : [];
  const visibleDays = visibleDaily.length || Math.min(trendRange, periodDays);
  const totalApplications = visibleDaily.reduce((sum, item) => sum + item.application_count, 0);
  const latestPoint = visibleDaily[visibleDaily.length - 1];
  const previousPoint = visibleDaily[visibleDaily.length - 2];
  const peakPoint = visibleDaily.reduce(
    (max, item) => (item.application_count > max.application_count ? item : max),
    visibleDaily[0],
  );
  const changePct =
    latestPoint && previousPoint && previousPoint.application_count > 0
      ? (latestPoint.application_count / previousPoint.application_count - 1) * 100
      : 0;

  return (
    <ChartCard
      title="选中路径 · 归因解释与近60天趋势"
      subtitle="点击下方合并预警表中的路径，趋势和三个观察窗口会同步切换"
      accent={SEVERITY[record.severity].dot}
      extra={<div className="flex items-center gap-2"><SourceTag source={record.source} /><SeverityTag severity={record.severity} text={record.level_label} /></div>}
    >
      <div className="px-4 pb-4 pt-2">
        <div className="flex flex-col gap-3 rounded-xl border border-slate-100 bg-slate-50/70 px-4 py-3 lg:flex-row lg:items-center">
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13px] font-semibold leading-6 text-slate-800" title={record.path}>{record.path}</div>
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              {record.conditions.map((condition) => (
                <span key={`${condition.field}:${condition.value}`} className="rounded-md border border-slate-200 bg-white px-1.5 py-0.5 text-[10.5px] text-slate-600">
                  <span className="text-slate-400">{condition.label}</span>={condition.value}
                </span>
              ))}
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500">
            <span>异常类型 <b className="ml-1 text-slate-700">{record.anomaly_type}</b></span>
            <span>命中窗口 <b className="ml-1 text-slate-700">{record.hit_windows.length ? record.hit_windows.map((item) => ({ '1d': '近1天', '3d': '近3天', '7d': '近7天' }[item])).join('、') : '无'}</b></span>
            <span>来源说明 <b className="ml-1 text-slate-700">{record.rule_note || 'Top-K 自动发现'}</b></span>
          </div>
        </div>

        <div className="mt-3 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.75fr)_minmax(370px,0.9fr)]">
          <section className="overflow-hidden rounded-2xl border border-slate-100 bg-white/60 backdrop-blur-xl">
            <div className="flex items-center justify-between border-b border-slate-100 px-3.5 py-2.5">
              <div>
                <div className="text-[12px] font-semibold text-slate-800">近{visibleDays}天授信申请量趋势</div>
                <div className="mt-0.5 text-[10px] text-slate-400">柱形为路径申请量，折线为路径占当日整体申请量比例</div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {currentTrend && <span className="text-[10px] text-slate-400">重点窗口：<b className="font-medium text-slate-600">{currentTrend.primary_window.label}</b></span>}
                <span className="theme-select-wrap">
                  <select
                    value={trendRange}
                    onChange={(event) => onTrendRangeChange(Number(event.target.value))}
                    className="theme-select"
                    aria-label="选择趋势显示范围"
                    title="切换趋势视窗范围(数据仍为预计算的近60天序列)"
                  >
                    {[7, 15, 30, 60].map((days) => (
                      <option key={days} value={days}>近{days}天</option>
                    ))}
                  </select>
                </span>
              </div>
            </div>

            {pathTrendLoading && (
              <div className="flex h-[350px] flex-col items-center justify-center gap-2 text-[12px] text-slate-400">
                <LoaderCircle size={20} className="animate-spin text-blue-500" />
                正在聚合该路径近 60 天申请量…
              </div>
            )}

            {!pathTrendLoading && pathTrendError && (
              <div className="flex h-[260px] flex-col items-center justify-center gap-3 text-center">
                <div className="text-[12px] text-rose-500">趋势加载失败：{pathTrendError}</div>
                <button onClick={onRetry} className="rounded-lg bg-blue-500 px-3 py-1.5 text-[11px] font-medium text-white hover:bg-blue-600">重新加载趋势</button>
              </div>
            )}

            {!pathTrendLoading && !pathTrendError && !currentTrend && (
              <div className="flex h-[280px] flex-col items-center justify-center gap-2 text-[12px] text-slate-400">
                <LoaderCircle size={18} className="animate-spin text-blue-500" />
                正在准备选中路径趋势…
              </div>
            )}

            {!pathTrendLoading && currentTrend && (
              <>
                <div className="grid grid-cols-2 gap-2 px-3.5 pt-3 sm:grid-cols-6">
                  <div className="rounded-lg border border-blue-100 bg-blue-50/60 px-2.5 py-2"><div className="text-[10px] text-slate-400">{visibleDays}天累计</div><div className="mt-0.5 text-[17px] font-semibold text-slate-700 tabular-nums">{formatNumber(totalApplications)}</div></div>
                  <div className="rounded-lg border border-slate-100 bg-white px-2.5 py-2"><div className="text-[10px] text-slate-400">最新日</div><div className="mt-0.5 text-[17px] font-semibold text-slate-700 tabular-nums">{formatNumber(latestPoint?.application_count ?? 0)}</div></div>
                  <div className="rounded-lg border border-slate-100 bg-white px-2.5 py-2"><div className="text-[10px] text-slate-400">较前一日</div><div className={`mt-0.5 text-[17px] font-semibold tabular-nums ${changePct >= 0 ? 'text-rose-500' : 'text-emerald-600'}`}>{formatSignedPercent(changePct)}</div></div>
                  <div className="rounded-lg border border-slate-100 bg-white px-2.5 py-2"><div className="text-[10px] text-slate-400">{visibleDays}天峰值</div><div className="mt-0.5 text-[17px] font-semibold text-slate-700 tabular-nums">{formatNumber(peakPoint?.application_count ?? 0)}</div><div className="text-[9.5px] text-slate-400">{peakPoint?.date}</div></div>
                  <div className="rounded-lg border border-violet-100 bg-violet-50/60 px-2.5 py-2"><div className="text-[10px] text-slate-400">最新通过率（件数）</div><div className="mt-0.5 text-[17px] font-semibold text-violet-700 tabular-nums">{latestPoint?.approval_rate_pct == null ? '—' : `${latestPoint.approval_rate_pct.toFixed(2)}%`}</div></div>
                  <div className="rounded-lg border border-emerald-100 bg-emerald-50/60 px-2.5 py-2"><div className="text-[10px] text-slate-400">最新通过率（人数）</div><div className="mt-0.5 text-[17px] font-semibold text-emerald-700 tabular-nums">{latestPoint?.cid_approval_rate_pct == null ? '—' : `${latestPoint.cid_approval_rate_pct.toFixed(2)}%`}</div></div>
                </div>
                <ReactECharts option={trendOption} style={{ height: 280 }} notMerge />
                <div className="-mt-1 flex flex-wrap justify-center gap-x-3 gap-y-1 px-3.5 pb-3 text-[10px] text-slate-400">
                  <span><i className="mr-1 inline-block h-2 w-2 rounded-sm" style={{ background: trendBrand }} />路径申请量</span>
                  <span><i className="mr-1 inline-block h-0.5 w-3 align-middle" style={{ background: trendAccent }} />通过率（件数）</span>
                  <span><i className="mr-1 inline-block h-0.5 w-3 align-middle" style={{ background: '#10b981' }} />通过率（人数）</span>
                  <span><i className="mr-1 inline-block h-2 w-3" style={{ background: trendTint }} />{currentTrend.primary_window.label}观察期</span>
                  <span><i className="mr-1 inline-block w-3 border-t border-dashed align-middle" style={{ borderColor: trendAccent }} />基准日均</span>
                </div>
              </>
            )}
          </section>

          <section className="rounded-xl border border-slate-100 bg-slate-50/50 p-3">
            <div className="mb-2.5 flex items-center justify-between">
              <div>
                <div className="text-[12px] font-semibold text-slate-800">分窗口归因解释</div>
                <div className="mt-0.5 text-[10px] text-slate-400">观察量、增长、结构提升与 z-score 需同时达标</div>
              </div>
              <SearchCheck size={15} className="text-blue-500" />
            </div>
            <div className="space-y-2.5">
              {WINDOW_ORDER.map((key) => <WindowCard key={key} metric={record.windows[key]} primary={key === record.primary_window} />)}
            </div>
          </section>
        </div>
      </div>
    </ChartCard>
  );
}

export default function CreditAttribution() {
  // 分享参数: 仅在首次挂载时读取一次, 用于还原链接携带的页面状态
  const share = useRef(readShareParams()).current;
  const [dashboard, setDashboard] = useState<AttributionDashboard | null>(null);
  const [partitions, setPartitions] = useState<string[]>([]);
  const [partitionRanges, setPartitionRanges] = useState<Record<string, { min: string; max: string }>>({});
  const [selectedPartition, setSelectedPartition] = useState(share.pt ?? '');
  const [selected, setSelected] = useState<AttributionRecord | null>(null);
  const [selectedTrendRecord, setSelectedTrendRecord] = useState<AttributionRecord | null>(null);
  const [pathTrend, setPathTrend] = useState<AttributionPathTrend | null>(null);
  const [pathTrendLoading, setPathTrendLoading] = useState(false);
  const [pathTrendError, setPathTrendError] = useState<string | null>(null);
  const [pathTrendRequest, setPathTrendRequest] = useState(0);
  const [levelFilter, setLevelFilter] = useState<number | 'all'>(
    share.lv === '1' || share.lv === '2' || share.lv === '3' ? Number(share.lv) : 'all',
  );
  const [sourceFilter, setSourceFilter] = useState<'all' | 'topk' | 'expert'>(
    share.src === 'topk' || share.src === 'expert' ? share.src : 'all',
  );
  const [typeFilter, setTypeFilter] = useState<string>(share.type ?? 'all');
  const [windowFilter, setWindowFilter] = useState<'all' | '1d' | '3d' | '7d'>(
    share.win === '1d' || share.win === '3d' || share.win === '7d' ? share.win : 'all',
  );
  const [ruleStatusTab, setRuleStatusTab] = useState<RuleStatus>(0);
  const [savingRuleStatus, setSavingRuleStatus] = useState<string | null>(null);
  const [dimFilter, setDimFilter] = useState<string>(share.dim ?? 'all'); // 下钻层级: 单维/二级/三级
  const [daysBack, setDaysBack] = useState(() => {
    const value = Number(share.offset ?? 0);
    return Number.isFinite(value) && value > 0 ? Math.floor(value) : 0;
  }); // 观察区间向前偏移天数(0=最新)
  const [trendRange, setTrendRange] = useState(() => {
    const value = Number(share.range ?? 60);
    return [7, 15, 30, 60].includes(value) ? value : 60;
  }); // 趋势视窗范围(天), 从预计算序列中切片显示
  const [showSuppressed, setShowSuppressed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selectedAnalysisRef = useRef<HTMLDivElement>(null);
  const loadRequestGuard = useRef(new LatestRequestGuard()).current;
  const contentRef = useRef<HTMLDivElement>(null); // 截屏范围 = 页面内容区

  // 分区列表刷新: force=true 跳过服务端缓存, 用于刷新归因后立即发现上游新分区(调度延迟补数场景)
  const reloadPartitions = useCallback((force = false) => {
    void fetchAttributionPartitions(force)
      .then(({ partitions: values, ranges }) => {
        setPartitions(values);
        setPartitionRanges(ranges ?? {});
      })
      .catch(() => {
        /* 保留现有分区列表 */
      });
  }, []);

  const load = useCallback(async (force = false, pt?: string, offset = 0) => {
    const requestId = loadRequestGuard.begin();
    const isCurrentRequest = () => loadRequestGuard.isCurrent(requestId);
    if (force) setRefreshing(true);
    else setLoading(true);
    setError(null);
    let asyncMode = false;
    const apply = (payload: AttributionDashboard) => {
      if (!isCurrentRequest()) return;
      setDashboard(payload);
      setSelectedPartition(payload.meta.partition);
      setSelected((current) => payload.merged_alerts.find((record) => record.canonical_path === current?.canonical_path) ?? payload.highlight ?? payload.merged_alerts[0] ?? null);
      setSelectedTrendRecord(null);
      setPathTrend(null);
      setPathTrendError(null);
    };
    try {
      const payload = await fetchCreditAttribution(pt, force, offset);
      if (!isCurrentRequest()) return;
      apply(payload);
      // 后端已返回旧缓存并启动后台重算: 轮询等待新结果(最多 12 次 × 15s)
      if (force && payload.meta.async_refresh) {
        asyncMode = true;
        const baseline = payload.meta.generated_at;
        void (async () => {
          try {
            for (let attempt = 0; attempt < 12; attempt++) {
              if (!isCurrentRequest()) return;
              await new Promise((resolve) => setTimeout(resolve, 15000));
              if (!isCurrentRequest()) return;
              const fresh = await fetchCreditAttribution(pt, false, offset);
              if (fresh.meta.generated_at !== baseline) {
                apply(fresh);
                reloadPartitions(true); // 重算可能包含新发现分区, 同步更新下拉选项
                break;
              }
            }
          } catch {
            /* 轮询失败保留当前数据 */
          } finally {
            if (isCurrentRequest()) setRefreshing(false);
          }
        })();
      }
    } catch (err) {
      if (isCurrentRequest()) setError(err instanceof Error ? err.message : '无法获取授信归因数据');
    } finally {
      if (isCurrentRequest()) {
        setLoading(false);
        if (!asyncMode) setRefreshing(false);
      }
    }
  }, [loadRequestGuard]);

  useEffect(() => {
    reloadPartitions(false);
    // 分享链接携带 pt/offset 时直接按参数加载, 否则服务端默认最新分区
    void load(false, share.pt || undefined, Number(share.offset ?? 0) || 0);
  }, [load, reloadPartitions, share]);

  const activeRecord = selected ?? dashboard?.highlight ?? dashboard?.merged_alerts[0] ?? null;

  const selectAlertPath = useCallback((record: AttributionRecord) => {
    setSelected(record);
    setSelectedTrendRecord(record);
    setPathTrend(null);
    setPathTrendError(null);
    setPathTrendRequest((value) => value + 1);
    window.setTimeout(() => selectedAnalysisRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0);
  }, []);

  const updateRuleStatus = useCallback(async (record: AttributionRecord, status: RuleStatus) => {
    const canonicalPath = record.canonical_path;
    setSavingRuleStatus(canonicalPath);
    setError(null);
    try {
      const updated = await updateAttributionRuleStatus(
        canonicalPath,
        status,
        dashboard?.meta.partition ?? selectedPartition,
        record,
      );
      const applyStatus = (item: AttributionRecord) => item.canonical_path === canonicalPath
        ? {
            ...item,
            status: updated.status,
            status_updated_at: updated.updated_at,
            status_updated_by: updated.updated_by,
            action_date: updated.action_date,
          }
        : item;
      setDashboard((current) => current ? {
        ...current,
        merged_alerts: current.merged_alerts.map(applyStatus),
        highlight: current.highlight ? applyStatus(current.highlight) : current.highlight,
        top_k: {
          ...current.top_k,
          single_downstream: current.top_k.single_downstream.map(applyStatus),
          pair_downstream: current.top_k.pair_downstream.map(applyStatus),
          third_alerts: current.top_k.third_alerts.map(applyStatus),
        },
        expert: {
          ...current.expert,
          single: current.expert.single ? applyStatus(current.expert.single) : current.expert.single,
          pair: current.expert.pair ? applyStatus(current.expert.pair) : current.expert.pair,
          third_alerts: current.expert.third_alerts.map(applyStatus),
          third_calculated: current.expert.third_calculated.map(applyStatus),
        },
        suppressed_alerts: current.suppressed_alerts.map(applyStatus),
      } : current);
      setSelected((current) => current ? applyStatus(current) : current);
      setSelectedTrendRecord((current) => current ? applyStatus(current) : current);
    } catch (err) {
      setError(err instanceof Error ? err.message : '规则状态更新失败');
    } finally {
      setSavingRuleStatus(null);
    }
  }, []);

  // 分享链接携带 path 时: 仪表盘就绪后自动选中该路径(含趋势加载与滚动定位)
  useEffect(() => {
    const pendingPath = share.path;
    if (!pendingPath || !dashboard) return;
    const record = dashboard.merged_alerts.find((item) => item.id === pendingPath);
    if (record) selectAlertPath(record);
    share.path = undefined; // 仅还原一次, 之后用户自由切换
  }, [dashboard, selectAlertPath, share]);

  useEffect(() => {
    if (activeRecord && selectedTrendRecord?.id !== activeRecord.id) {
      setSelectedTrendRecord(activeRecord);
    }
  }, [activeRecord?.id, selectedTrendRecord?.id]);

  useEffect(() => {
    if (!selectedTrendRecord || !dashboard) {
      setPathTrendLoading(false);
      return;
    }

    let cancelled = false;
    setPathTrendLoading(true);
    setPathTrendError(null);
    void fetchAttributionPathTrend(selectedTrendRecord.id, dashboard.meta.partition, daysBack)
      .then((result) => {
        if (!cancelled) setPathTrend(result);
      })
      .catch((err) => {
        if (!cancelled) setPathTrendError(err instanceof Error ? err.message : '无法加载该路径趋势');
      })
      .finally(() => {
        if (!cancelled) setPathTrendLoading(false);
      });

    return () => { cancelled = true; };
  }, [dashboard?.meta.partition, daysBack, pathTrendRequest, selectedTrendRecord?.id]);

  // 完整下钻名单: 合并预警(已去重) + 单维/二级名单中通过门槛的无预警记录(Level0 也展示)
  const allRows = useMemo(() => {
    if (!dashboard) return [] as AttributionRecord[];
    const extras = [...dashboard.top_k.single_downstream, ...dashboard.top_k.pair_downstream].filter(
      (record) => record.level === 0,
    );
    const seen = new Set<string>();
    const rows: AttributionRecord[] = [];
    for (const record of [...dashboard.merged_alerts, ...extras]) {
      if (seen.has(record.canonical_path)) continue;
      seen.add(record.canonical_path);
      rows.push(record);
    }
    return rows;
  }, [dashboard]);

  const filteredAlerts = useMemo(() => {
    return allRows.filter((record) => {
      // Discovery always shows the current pt's abnormal rows, regardless of
      // whether the same rule is already marked as strategy/observation.
      // Rows appended only for tracked daily statistics are not current hits.
      const statusMatched = ruleStatusTab === 0
        ? !record.is_tracked_only
        : (record.status ?? 0) === ruleStatusTab;
      const levelMatched = levelFilter === 'all' || record.level === levelFilter;
      const sourceMatched = sourceFilter === 'all'
        || (sourceFilter === 'topk' && record.source.includes('Top-K'))
        || (sourceFilter === 'expert' && record.source.includes('专家'));
      const typeMatched = typeFilter === 'all' || record.anomaly_type === typeFilter;
      const windowMatched = windowFilter === 'all' || record.primary_window === windowFilter;
      const dimMatched = dimFilter === 'all' || record.layer === dimFilter;
      return statusMatched && levelMatched && sourceMatched && typeMatched && windowMatched && dimMatched;
    });
  }, [allRows, levelFilter, sourceFilter, typeFilter, windowFilter, dimFilter, ruleStatusTab]);

  const ruleStatusCounts = useMemo(() => {
    return RULE_STATUS_TABS.reduce<Record<RuleStatus, number>>((counts, tab) => {
      counts[tab.value] = tab.value === 0
        ? allRows.filter((record) => !record.is_tracked_only).length
        : allRows.filter((record) => (record.status ?? 0) === tab.value).length;
      return counts;
    }, { 0: 0, 1: 0, 2: 0 });
  }, [allRows]);

  const anomalyTypes = useMemo(() => {
    return Array.from(new Set(allRows.map((record) => record.anomaly_type))).sort();
  }, [allRows]);

  // 观察区间可选偏移: 按所选 pt 的表数据范围动态生成(每档 15 天, 窗口不能超出表范围)
  const availableOffsets = useMemo(() => {
    const range = partitionRanges[selectedPartition];
    const min = range?.min ?? dashboard?.meta.table_date_min;
    const max = range?.max ?? dashboard?.meta.table_date_max;
    if (!min || !max) return [0];
    const totalDays = Math.floor((Date.parse(max) - Date.parse(min)) / 86400000) + 1;
    const options: number[] = [];
    for (let off = 0; off < totalDays; off += 15) options.push(off);
    return options;
  }, [partitionRanges, selectedPartition, dashboard]);

  // 观察窗口显示: 已加载完用结果日期; 切换 pt 后立即按该 pt 表范围估算最近15天窗口
  const obsRange = useMemo(() => {
    if (dashboard && dashboard.meta.partition === selectedPartition) {
      return { start: dashboard.meta.date_start, end: dashboard.meta.date_end };
    }
    const range = partitionRanges[selectedPartition];
    if (range?.max) {
      const end = new Date(range.max);
      const start = new Date(end);
      start.setDate(start.getDate() - 14);
      return {
        start: start.toISOString().slice(0, 10),
        end: range.max,
        pending: true,
      };
    }
    return null;
  }, [dashboard, selectedPartition, partitionRanges]);

  // ============ 分享 / 截屏 ============
  const [shareCopied, setShareCopied] = useState(false);
  const [shooting, setShooting] = useState(false);

  const buildShareUrl = useCallback(() => {
    const url = new URL(window.location.href);
    url.searchParams.set('page', 'attribution');
    const assign = (key: string, value: string | number | null | undefined) => {
      if (value == null || value === '' || value === 'all') url.searchParams.delete(key);
      else url.searchParams.set(key, String(value));
    };
    assign('pt', selectedPartition);
    assign('offset', daysBack > 0 ? daysBack : null);
    assign('path', activeRecord?.id);
    assign('range', trendRange !== 60 ? trendRange : null);
    assign('lv', levelFilter !== 'all' ? levelFilter : null);
    assign('src', sourceFilter);
    assign('type', typeFilter);
    assign('win', windowFilter);
    assign('dim', dimFilter);
    return url.toString();
  }, [activeRecord?.id, daysBack, dimFilter, levelFilter, selectedPartition, sourceFilter, trendRange, typeFilter, windowFilter]);

  const handleShare = useCallback(async () => {
    const ok = await copyText(buildShareUrl());
    if (ok) {
      setShareCopied(true);
      window.setTimeout(() => setShareCopied(false), 2000);
    } else {
      // 剪贴板不可用(如非 HTTPS 局域网)时弹出输入框让用户手动复制
      window.prompt('复制以下链接分享给同事：', buildShareUrl());
    }
  }, [buildShareUrl]);

  const handleScreenshot = useCallback(async () => {
    const node = contentRef.current;
    if (!node) return;
    setShooting(true);
    try {
      const dataUrl = await toPng(node, {
        backgroundColor: '#f4f6fa',
        pixelRatio: 2,
      });
      const link = document.createElement('a');
      const stamp = new Date().toISOString().slice(0, 16).replace(/[T:]/g, '-');
      link.download = `授信归因_${selectedPartition || '最新'}_${stamp}.png`;
      link.href = dataUrl;
      link.click();
    } catch {
      /* 截图失败静默降级, 不阻断页面使用 */
    } finally {
      setShooting(false);
    }
  }, [selectedPartition]);

  const activeTheme = getTheme();
  // 全部使用当前主题主色：柱形=主色，折线=主色深阶，区域/基准线使用同色透明阶。
  const selectedTrendBrand = activeTheme.brand;
  const selectedTrendHover = shadeHex(selectedTrendBrand, -0.14);
  const selectedTrendAccent = shadeHex(selectedTrendBrand, -0.42);
  const selectedTrendTint = hexWithAlpha(selectedTrendBrand, 0.10);
  const selectedTrendGuide = hexWithAlpha(selectedTrendAccent, 0.78);

  const selectedPathTrendOption = useMemo<EChartsOption>(() => {
    if (!pathTrend) return {};
    // 视窗切片: 只取最近 trendRange 天构建图表(数据仍来自预计算完整序列)
    const trend = pathTrend.daily.slice(-trendRange);
    const primaryWindow = pathTrend.primary_window;
    const baselineDaily = Number(primaryWindow.baseline_daily ?? 0);
    // 观察期标注钳制到当前视窗内, 避免分类轴上出现不存在的日期
    const clampToRange = (value: string | null): string | null => {
      if (!value || !trend.length) return null;
      if (value <= trend[0].date) return trend[0].date;
      if (value >= trend[trend.length - 1].date) return trend[trend.length - 1].date;
      return value;
    };
    const areaStart = clampToRange(primaryWindow.observation_start);
    const areaEnd = clampToRange(primaryWindow.observation_end);
    return {
      ...baseOption(),
      grid: { left: 16, right: 20, top: 38, bottom: 12, containLabel: true },
      legend: { ...baseOption().legend, right: undefined, top: 2, left: 'center' },
      tooltip: {
        ...baseOption().tooltip,
        trigger: 'axis',
        formatter: (params: Array<{ dataIndex?: number }>) => {
          const point = trend[params[0]?.dataIndex ?? 0];
          if (!point) return '';
          return [
            `<b>${point.date}</b>`,
            `路径授信申请量：<b>${formatNumber(point.application_count)}</b> 件`,
            `路径通过量：<b>${formatNumber(point.approval_count)}</b> 件`,
            `路径人数：<b>${formatNumber(point.cid_cnt)}</b> 人`,
            `路径通过人数：<b>${formatNumber(point.approval_cid_cnt)}</b> 人`,
            `当日整体申请量：${formatNumber(point.total_application_count)} 件`,
            `通过率（件数）：<b>${point.approval_rate_pct == null ? '—' : `${point.approval_rate_pct.toFixed(2)}%`}</b>`,
            `通过率（人数）：<b>${point.cid_approval_rate_pct == null ? '—' : `${point.cid_approval_rate_pct.toFixed(2)}%`}</b>`,
            `整体占比：${point.application_share_pct.toFixed(3)}%`,
          ].join('<br/>');
        },
      },
      xAxis: { ...baseOption().xAxis, data: trend.map((item) => formatDate(item.date)) },
      yAxis: [
        { ...baseOption().yAxis, name: '路径申请量', nameTextStyle: { color: '#8f959e', fontSize: 10 } },
        {
          ...baseOption().yAxis,
          name: '通过率',
          position: 'right',
          min: 0,
          splitLine: { show: false },
          axisLabel: { color: '#8f959e', fontSize: 10, formatter: '{value}%' },
          nameTextStyle: { color: '#8f959e', fontSize: 10 },
        },
      ],
      series: [
        {
          name: '路径授信申请量',
          type: 'bar',
          barMaxWidth: 26,
          data: trend.map((item) => item.application_count),
          itemStyle: { color: selectedTrendBrand, borderRadius: [4, 4, 0, 0] },
          emphasis: { itemStyle: { color: selectedTrendHover } },
          markPoint: {
            symbolSize: 38,
            label: { color: '#fff', fontSize: 10, formatter: '峰值' },
            itemStyle: { color: selectedTrendAccent },
            data: [{ type: 'max', name: '60天峰值' }],
          },
          markLine: baselineDaily > 0 ? {
            symbol: 'none',
            lineStyle: { color: selectedTrendGuide, type: 'dashed' },
            label: { color: selectedTrendAccent, fontSize: 10, formatter: `基准日均 ${baselineDaily.toFixed(1)}` },
            data: [{ yAxis: baselineDaily }],
          } : undefined,
          markArea: areaStart && areaEnd && areaStart <= areaEnd ? {
            silent: true,
            itemStyle: { color: selectedTrendTint },
            label: { color: selectedTrendAccent, fontSize: 10, formatter: `${primaryWindow.label}观察期` },
            data: [[
              { xAxis: formatDate(areaStart) },
              { xAxis: formatDate(areaEnd) },
            ]],
          } : undefined,
        },
        {
          name: '通过率',
          type: 'line',
          yAxisIndex: 1,
          smooth: true,
          symbol: 'circle',
          symbolSize: 5,
          connectNulls: true,
          lineStyle: { width: 2, color: selectedTrendAccent },
          itemStyle: { color: selectedTrendAccent },
          data: trend.map((item) => item.approval_rate_pct),
        },
        {
          name: '通过率（人数）',
          type: 'line',
          yAxisIndex: 1,
          smooth: true,
          symbol: 'circle',
          symbolSize: 4,
          connectNulls: true,
          lineStyle: { width: 2, type: 'dashed', color: '#10b981' },
          itemStyle: { color: '#10b981' },
          data: trend.map((item) => item.cid_approval_rate_pct),
        },
      ],
    };
  }, [activeTheme.key, pathTrend, selectedTrendAccent, selectedTrendBrand, selectedTrendGuide, selectedTrendHover, selectedTrendTint, trendRange]);

  const actionDateColumn: FeishuColumn<AttributionRecord> = {
    key: 'action_date', title: '措施日期', width: 104, align: 'center',
    render: (record) => record.status === 0 ? '—' : (record.action_date ?? '—'),
  };

  const alertColumns: FeishuColumn<AttributionRecord>[] = [
    {
      key: 'status', title: '状态', width: 142, align: 'center',
      render: (record) => (
        <select
          value={record.status ?? 0}
          disabled={savingRuleStatus === record.canonical_path}
          onChange={(event) => void updateRuleStatus(record, Number(event.target.value) as RuleStatus)}
          aria-label={`设置规则状态 ${record.path}`}
          className="theme-select max-w-[132px]"
        >
          {RULE_STATUS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      ),
    },
    ...(ruleStatusTab === 0 ? [] : [actionDateColumn]),
    {
      key: 'level_label', title: '等级', sticky: true, width: 104,
      render: (record) => record.level === 0
        ? <span className="text-[11px] text-slate-400">无预警</span>
        : <SeverityTag severity={record.severity} text={`L${record.level}`} />,
    },
    { key: 'source', title: '来源', width: 118, render: (record) => <SourceTag source={record.source} /> },
    {
      key: 'path', title: '异常归因路径', width: 360,
      render: (record) => record.level === 0 ? (
        <PathHoverTip path={record.path}>
          <span
            className="max-w-[340px] cursor-pointer truncate text-slate-500 hover:text-slate-700"
            title="悬停查看完整值"
          >{record.path}</span>
        </PathHoverTip>
      ) : (
        <PathHoverTip path={record.path}>
          <button
            onClick={() => selectAlertPath(record)}
            className="max-w-[340px] cursor-pointer truncate text-left font-medium text-slate-700 underline-offset-2 hover:text-blue-600 hover:underline"
            title="悬停查看完整值; 点击查看该路径近15天趋势"
          >
            {record.path}
          </button>
        </PathHoverTip>
      ),
    },
    { key: 'layer', title: '层级', width: 70, align: 'center' },
    { key: 'anomaly_type', title: '异常类型', width: 90 },
    { key: 'primary_window_label', title: '主窗口', width: 78, align: 'center' },
    { key: 'observation_count', title: '观察量', width: 82, align: 'right', render: (record) => formatNumber(record.observation_count) },
    { key: 'approval_rate_pct', title: '通过率（件数）', width: 100, align: 'right', render: (record) => <span className="tabular-nums">{formatApprovalRate(record.approval_rate_pct)}</span> },
    { key: 'cid_approval_rate_pct', title: '通过率（人数）', width: 100, align: 'right', render: (record) => <span className="tabular-nums">{formatApprovalRate(record.cid_approval_rate_pct)}</span> },
    { key: 'growth_factor', title: '申请增长', width: 92, align: 'right', render: (record) => formatFactor(record.growth_factor) },
    { key: 'structure_lift_factor', title: '结构提升', width: 92, align: 'right', render: (record) => formatFactor(record.structure_lift_factor) },
    { key: 'z_score', title: 'z-score', width: 76, align: 'right', render: (record) => record.z_score.toFixed(2) },
    { key: 'excess_count', title: '超额量(辅助)', width: 108, align: 'right', render: (record) => `${record.excess_count >= 0 ? '+' : ''}${formatNumber(record.excess_count)}` },
  ];

  if (loading && !dashboard) return <LoadingState />;

  if (error && !dashboard) {
    return (
      <div className="flex min-h-[520px] flex-col items-center justify-center rounded-2xl border border-rose-100 bg-white/60 backdrop-blur-xl text-center shadow-[0_1px_3px_rgba(15,23,42,0.05)]">
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-rose-50 text-rose-500"><ShieldAlert size={24} /></div>
        <div className="text-[15px] font-semibold text-slate-700">授信归因服务暂不可用</div>
        <div className="mt-2 max-w-lg text-[12px] leading-5 text-slate-400">{error}</div>
        <button onClick={() => void load(true, selectedPartition || undefined)} className="mt-5 inline-flex items-center gap-2 rounded-lg bg-blue-500 px-4 py-2 text-[12px] font-medium text-white hover:bg-blue-600">
          <RefreshCw size={14} /> 重试连接
        </button>
      </div>
    );
  }

  if (!dashboard) return <LoadingState />;

  const { meta, rules } = dashboard;

  return (
    <div className="mx-auto max-w-[1440px] space-y-4 pb-2" ref={contentRef}>
      {/* 工具条: 观察区间 / 分区 / 刷新 */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white/60 px-2.5 py-1.5 text-[10.5px] text-slate-500 backdrop-blur-xl">
          <span className="text-slate-400">观察区间</span>
          <span className="theme-select-wrap">
          <select
            value={daysBack}
            onChange={(event) => {
              const value = Number(event.target.value);
              setDaysBack(value);
              void load(false, selectedPartition || undefined, value);
            }}
            className="theme-select"
            aria-label="选择观察区间"
            title="默认展示最近15天, 可回看历史区间"
          >
            {availableOffsets.map((off) => (
              <option key={off} value={off}>{off === 0 ? '最近15天' : `${off}天前`}</option>
            ))}
          </select>
          </span>
          <span className="font-medium text-slate-700 tabular-nums">{obsRange ? `${obsRange.start} ～ ${obsRange.end}` : '—'}</span>
          {obsRange?.pending && (
            <span className="inline-flex items-center gap-1 rounded bg-blue-50 px-1.5 py-0.5 text-[10px] text-blue-600">
              <LoaderCircle size={10} className="animate-spin" /> 正在加载 pt={selectedPartition} 数据…
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white/60 px-2.5 py-1.5 text-[10.5px] text-slate-500 backdrop-blur-xl">
          <span className="text-slate-400">数据分区</span>
          <span className="theme-select-wrap">
          <select
            value={selectedPartition}
            onChange={(event) => {
              const pt = event.target.value;
              setSelectedPartition(pt);
              setDaysBack(0); // 切换分区后观察区间回到最近15天, 档位按新分区范围动态生成
              void load(false, pt, 0); // 立即按新分区加载
            }}
            className="theme-select"
            aria-label="选择数据分区"
            title="切换分区后自动按新分区重新加载"
          >
            {partitions.map((pt) => <option key={pt} value={pt}>pt={pt}</option>)}
          </select>
          </span>
        </div>
        <button
          onClick={() => {
            void load(true, selectedPartition || undefined, daysBack);
            reloadPartitions(true); // 强制重新发现分区: 上游补数后无需重启即可选到新 pt
          }}
          disabled={refreshing}
          className="inline-flex items-center gap-1.5 rounded-lg bg-blue-500 px-3 py-1.5 text-[11px] font-medium text-white transition-colors hover:bg-blue-600 disabled:opacity-60"
        >
          <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} /> {refreshing ? '重新计算中' : '刷新归因'}
        </button>
        <span className="inline-flex items-center gap-1 text-[10.5px] text-slate-400">
          <Database size={12} /> {meta.table}
        </span>
        <span className={meta.cache_hit ? 'text-emerald-600' : 'text-blue-500'}>{meta.cache_hit ? '命中 15 分钟缓存' : '本次为最新计算结果'}</span>

        {/* 分享 / 截屏: 推到行末 */}
        <div className="ml-auto flex items-center gap-1.5">
          <button
            onClick={() => void handleShare()}
            disabled={!dashboard}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-medium text-slate-600 transition-colors hover:border-blue-300 hover:text-blue-600 disabled:opacity-60"
            title="复制当前页面状态链接(含分区/筛选/选中路径), 同事打开后还原同一视角"
          >
            {shareCopied ? <Check size={13} className="text-emerald-500" /> : <Link2 size={13} />}
            {shareCopied ? '已复制' : '分享'}
          </button>
          <button
            onClick={() => void handleScreenshot()}
            disabled={shooting || !dashboard}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-medium text-slate-600 transition-colors hover:border-blue-300 hover:text-blue-600 disabled:opacity-60"
            title="将当前页面截图为 PNG 并下载, 可直接发给同事"
          >
            {shooting ? <LoaderCircle size={13} className="animate-spin" /> : <Camera size={13} />}
            {shooting ? '生成中…' : '截屏'}
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-xl border border-orange-200 bg-orange-50 px-4 py-2.5 text-[12px] text-orange-700">
          <AlertTriangle size={15} /> 刷新失败，当前继续展示上一次成功结果：{error}
        </div>
      )}

      <ChartCard
        title="合并预警结果"
        subtitle={`Top-K 单维/二级下钻名单与专家规则全部展示(含无预警候选)；鼠标悬停路径放大显示完整值, 点击查看该路径近15天趋势`}
        accent="#f97316"
      >
        <div role="tablist" aria-label="规则处理状态" className="flex items-center gap-1 border-b border-slate-100 px-4 pt-3">
          {RULE_STATUS_TABS.map((tab) => {
            const active = ruleStatusTab === tab.value;
            return (
              <button
                key={tab.value}
                role="tab"
                aria-selected={active}
                onClick={() => setRuleStatusTab(tab.value)}
                className={`border-b-2 px-3 py-2 text-[12px] font-medium transition-colors ${active ? 'border-blue-500 text-blue-600' : 'border-transparent text-slate-400 hover:text-slate-600'}`}
              >
                {tab.label}
                <span className={`ml-1.5 rounded-full px-1.5 py-0.5 text-[10px] tabular-nums ${active ? 'bg-blue-50 text-blue-600' : 'bg-slate-100 text-slate-400'}`}>
                  {ruleStatusCounts[tab.value]}
                </span>
              </button>
            );
          })}
        </div>
        <div className="flex flex-wrap items-center gap-2 px-4 pb-2">
          <span className="theme-select-wrap">
          <select
            value={sourceFilter}
            onChange={(event) => setSourceFilter(event.target.value as 'all' | 'topk' | 'expert')}
            className="theme-select"
            aria-label="按来源筛选"
          >
            <option value="all">全部来源</option>
            <option value="topk">Top-K</option>
            <option value="expert">专家</option>
          </select>
          </span>
          <span className="theme-select-wrap">
          <select
            value={dimFilter}
            onChange={(event) => setDimFilter(event.target.value)}
            className="theme-select"
            aria-label="按层级筛选"
          >
            <option value="all">全部层级</option>
            <option value="单维">单维</option>
            <option value="二级">二级</option>
            <option value="三级">三级</option>
          </select>
          </span>
          <span className="theme-select-wrap">
          <select
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value)}
            className="theme-select"
            aria-label="按异常类型筛选"
          >
            <option value="all">全部类型</option>
            {anomalyTypes.map((type) => <option key={type} value={type}>{type}</option>)}
          </select>
          </span>
          <span className="theme-select-wrap">
          <select
            value={windowFilter}
            onChange={(event) => setWindowFilter(event.target.value as 'all' | '1d' | '3d' | '7d')}
            className="theme-select"
            aria-label="按主窗口筛选"
          >
            <option value="all">全部窗口</option>
            <option value="1d">近1日</option>
            <option value="3d">近3日</option>
            <option value="7d">近7日</option>
          </select>
          </span>
          <span className="ml-auto text-[10.5px] text-slate-400">共 {filteredAlerts.length} 条</span>
          <div className="flex items-center gap-1.5">
            {(['all', 3, 2, 1] as const).map((filter) => {
              const label = filter === 'all' ? '全部等级' : `L${filter}`;
              const active = levelFilter === filter;
              return <button key={label} onClick={() => setLevelFilter(filter)} className={`rounded-md px-2 py-1 text-[10.5px] ${active ? 'bg-slate-700 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`}>{label}</button>;
            })}
          </div>
        </div>
        <FeishuTable columns={alertColumns} data={filteredAlerts} maxHeight={470} rowKey={(record) => record.id} />
      </ChartCard>

      {activeRecord && (
        <div ref={selectedAnalysisRef}>
          <SelectedPathAnalysis
            record={activeRecord}
            pathTrend={pathTrend}
            pathTrendLoading={pathTrendLoading}
            pathTrendError={pathTrendError}
            trendOption={selectedPathTrendOption}
            trendBrand={selectedTrendBrand}
            trendAccent={selectedTrendAccent}
            trendTint={selectedTrendTint}
            trendRange={trendRange}
            onTrendRangeChange={setTrendRange}
            onRetry={() => setPathTrendRequest((value) => value + 1)}
          />
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <ChartCard title="免归因抑制与审计" subtitle="抑制客群仍参与整体申请量、结构占比分母，但不进入候选、预警与下钻" accent="#f59e0b">
          <div className="px-4 pb-4 pt-3">
            <div className="mb-3 flex items-center justify-between rounded-lg border border-amber-100 bg-amber-50 px-3 py-2.5">
              <div className="flex items-center gap-2"><AlertTriangle size={15} className="text-amber-500" /><span className="text-[12px] text-amber-800">本次命中且被抑制的预警</span></div>
              <span className="text-[18px] font-semibold text-amber-600 tabular-nums">{dashboard.suppressed_alert_total}</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {rules.suppression_rules.map((rule) => (
                <span key={`${rule.field}:${rule.value}`} className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[10.5px] text-slate-600" title={rule.reason}>
                  {rule.field}={rule.value}
                </span>
              ))}
            </div>
            <button onClick={() => setShowSuppressed((value) => !value)} className="mt-3 text-[11px] font-medium text-blue-600 hover:text-blue-700">
              {showSuppressed ? '收起' : '查看'} 抑制明细 <ChevronRight size={13} className={`inline transition-transform ${showSuppressed ? 'rotate-90' : ''}`} />
            </button>
            {showSuppressed && (
              <div className="mt-2 max-h-40 overflow-auto rounded-lg border border-slate-100">
                {dashboard.suppressed_alerts.map((record) => (
                  <div key={record.id} className="flex items-center gap-2 border-b border-slate-100 px-2.5 py-2 text-[10.5px] last:border-0">
                    <SeverityTag severity={record.severity} text={`L${record.level}`} />
                    <PathHoverTip path={record.path}>
                      <span className="min-w-0 flex-1 cursor-pointer truncate text-slate-600 hover:text-slate-800" title="悬停查看完整值">{record.path}</span>
                    </PathHoverTip>
                    <span className="shrink-0 text-slate-400">{record.suppression_reasons[0]}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </ChartCard>
        <ChartCard title="预警阈值与运行口径" subtitle="所有等级均要求四项指标同时达标" accent="#4e83fd">
          <div className="px-4 pb-4 pt-3">
            <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
              {rules.thresholds.map((threshold) => {
                const severity: Severity = threshold.level === 3 ? 'red' : threshold.level === 2 ? 'orange' : 'yellow';
                return (
                  <div key={threshold.level} className="rounded-lg border p-2.5" style={{ background: SEVERITY[severity].bg, borderColor: SEVERITY[severity].border }}>
                    <div className="mb-1"><SeverityTag severity={severity} text={`Level${threshold.level}`} /></div>
                    <div className="space-y-0.5 text-[10.5px] text-slate-600">
                      <div>观察量 ≥ {threshold.min_observation_count}</div>
                      <div>增长 ≥ {threshold.min_growth_factor}× · 结构 ≥ {threshold.min_structure_lift_factor}×</div>
                      <div>z-score ≥ {threshold.min_z_score}</div>
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="mt-3 flex items-start gap-2 rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-[10.5px] leading-5 text-blue-700">
              <Sparkles size={14} className="mt-0.5 shrink-0" />
              <span>{meta.note}</span>
            </div>
          </div>
        </ChartCard>
      </div>
    </div>
  );
}
