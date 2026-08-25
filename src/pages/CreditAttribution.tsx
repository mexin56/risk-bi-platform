import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { EChartsOption } from 'echarts';
import ReactECharts from 'echarts-for-react';
import {
  AlertTriangle,
  ChevronRight,
  Database,
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
  type AttributionDashboard,
  type AttributionPathTrend,
  type AttributionRecord,
  type Severity,
  type WindowMetric,
} from '@/lib/creditAttributionApi';

const numberFormatter = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 });

const SEVERITY: Record<Severity, { bg: string; border: string; text: string; dot: string; label: string }> = {
  slate: { bg: '#f8fafc', border: '#e2e8f0', text: '#64748b', dot: '#94a3b8', label: 'Level0' },
  yellow: { bg: '#fffbeb', border: '#fde68a', text: '#b45309', dot: '#f59e0b', label: 'Level1 黄色' },
  orange: { bg: '#fff7ed', border: '#fdba74', text: '#c2410c', dot: '#f97316', label: 'Level2 橙色' },
  red: { bg: '#fff1f2', border: '#fecdd3', text: '#e11d48', dot: '#f43f5e', label: 'Level3 红色' },
};

const WINDOW_ORDER: Array<'1d' | '3d' | '7d'> = ['1d', '3d', '7d'];

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
      <div className="mt-2 grid grid-cols-5 gap-2 text-[10px]">
        <div><div className="text-slate-400">观察量</div><div className="mt-0.5 font-semibold text-slate-700 tabular-nums">{formatNumber(metric.observation_count)}</div></div>
        <div><div className="text-slate-400">通过率</div><div className="mt-0.5 font-semibold text-slate-700 tabular-nums">{formatApprovalRate(metric.approval_rate_pct)}</div></div>
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
  onRetry: () => void;
}) {
  const currentTrend = pathTrend?.record_id === record.id ? pathTrend : null;

  return (
    <ChartCard
      title="选中路径 · 归因解释与近15天趋势"
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
                <div className="text-[12px] font-semibold text-slate-800">近15天授信申请量趋势</div>
                <div className="mt-0.5 text-[10px] text-slate-400">柱形为路径申请量，紫线为路径占当日整体申请量比例</div>
              </div>
              {currentTrend && <span className="text-[10px] text-slate-400">重点窗口：<b className="font-medium text-slate-600">{currentTrend.primary_window.label}</b></span>}
            </div>

            {pathTrendLoading && (
              <div className="flex h-[350px] flex-col items-center justify-center gap-2 text-[12px] text-slate-400">
                <LoaderCircle size={20} className="animate-spin text-blue-500" />
                正在聚合该路径近 15 天申请量…
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
                <div className="grid grid-cols-2 gap-2 px-3.5 pt-3 sm:grid-cols-5">
                  <div className="rounded-lg border border-blue-100 bg-blue-50/60 px-2.5 py-2"><div className="text-[10px] text-slate-400">15天累计</div><div className="mt-0.5 text-[17px] font-semibold text-slate-700 tabular-nums">{formatNumber(currentTrend.summary.period_application_count)}</div></div>
                  <div className="rounded-lg border border-slate-100 bg-white px-2.5 py-2"><div className="text-[10px] text-slate-400">最新日</div><div className="mt-0.5 text-[17px] font-semibold text-slate-700 tabular-nums">{formatNumber(currentTrend.summary.latest_application_count)}</div></div>
                  <div className="rounded-lg border border-slate-100 bg-white px-2.5 py-2"><div className="text-[10px] text-slate-400">较前一日</div><div className={`mt-0.5 text-[17px] font-semibold tabular-nums ${currentTrend.summary.latest_day_change_pct >= 0 ? 'text-rose-500' : 'text-emerald-600'}`}>{formatSignedPercent(currentTrend.summary.latest_day_change_pct)}</div></div>
                  <div className="rounded-lg border border-slate-100 bg-white px-2.5 py-2"><div className="text-[10px] text-slate-400">15天峰值</div><div className="mt-0.5 text-[17px] font-semibold text-slate-700 tabular-nums">{formatNumber(currentTrend.summary.peak_application_count)}</div><div className="text-[9.5px] text-slate-400">{currentTrend.summary.peak_date}</div></div>
                  <div className="rounded-lg border border-violet-100 bg-violet-50/60 px-2.5 py-2"><div className="text-[10px] text-slate-400">最新通过率</div><div className="mt-0.5 text-[17px] font-semibold text-violet-700 tabular-nums">{currentTrend.summary.latest_approval_rate_pct == null ? '—' : `${currentTrend.summary.latest_approval_rate_pct.toFixed(2)}%`}</div></div>
                </div>
                <ReactECharts option={trendOption} style={{ height: 280 }} notMerge />
                <div className="-mt-1 flex flex-wrap justify-center gap-x-3 gap-y-1 px-3.5 pb-3 text-[10px] text-slate-400">
                  <span><i className="mr-1 inline-block h-2 w-2 rounded-sm" style={{ background: trendBrand }} />路径申请量</span>
                  <span><i className="mr-1 inline-block h-0.5 w-3 align-middle" style={{ background: trendAccent }} />通过率</span>
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
  const [dashboard, setDashboard] = useState<AttributionDashboard | null>(null);
  const [partitions, setPartitions] = useState<string[]>([]);
  const [partitionRanges, setPartitionRanges] = useState<Record<string, { min: string; max: string }>>({});
  const [selectedPartition, setSelectedPartition] = useState('');
  const [selected, setSelected] = useState<AttributionRecord | null>(null);
  const [selectedTrendRecord, setSelectedTrendRecord] = useState<AttributionRecord | null>(null);
  const [pathTrend, setPathTrend] = useState<AttributionPathTrend | null>(null);
  const [pathTrendLoading, setPathTrendLoading] = useState(false);
  const [pathTrendError, setPathTrendError] = useState<string | null>(null);
  const [pathTrendRequest, setPathTrendRequest] = useState(0);
  const [levelFilter, setLevelFilter] = useState<number | 'all'>('all');
  const [sourceFilter, setSourceFilter] = useState<'all' | 'topk' | 'expert'>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [windowFilter, setWindowFilter] = useState<'all' | '1d' | '3d' | '7d'>('all');
  const [dimFilter, setDimFilter] = useState<string>('all'); // 下钻层级: 单维/二级/三级
  const [daysBack, setDaysBack] = useState(0); // 观察区间向前偏移天数(0=最新)
  const [showSuppressed, setShowSuppressed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selectedAnalysisRef = useRef<HTMLDivElement>(null);

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
    if (force) setRefreshing(true);
    else setLoading(true);
    setError(null);
    let asyncMode = false;
    const apply = (payload: AttributionDashboard) => {
      setDashboard(payload);
      setSelectedPartition(payload.meta.partition);
      setSelected((current) => payload.merged_alerts.find((record) => record.canonical_path === current?.canonical_path) ?? payload.highlight ?? payload.merged_alerts[0] ?? null);
      setSelectedTrendRecord(null);
      setPathTrend(null);
      setPathTrendError(null);
    };
    try {
      const payload = await fetchCreditAttribution(pt, force, offset);
      apply(payload);
      // 后端已返回旧缓存并启动后台重算: 轮询等待新结果(最多 12 次 × 15s)
      if (force && payload.meta.async_refresh) {
        asyncMode = true;
        const baseline = payload.meta.generated_at;
        void (async () => {
          try {
            for (let attempt = 0; attempt < 12; attempt++) {
              await new Promise((resolve) => setTimeout(resolve, 15000));
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
            setRefreshing(false);
          }
        })();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法获取授信归因数据');
    } finally {
      setLoading(false);
      if (!asyncMode) setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    reloadPartitions(false);
    void load();
  }, [load, reloadPartitions]);

  const activeRecord = selected ?? dashboard?.highlight ?? dashboard?.merged_alerts[0] ?? null;

  const selectAlertPath = useCallback((record: AttributionRecord) => {
    setSelected(record);
    setSelectedTrendRecord(record);
    setPathTrend(null);
    setPathTrendError(null);
    setPathTrendRequest((value) => value + 1);
    window.setTimeout(() => selectedAnalysisRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0);
  }, []);

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
      const levelMatched = levelFilter === 'all' || record.level === levelFilter;
      const sourceMatched = sourceFilter === 'all'
        || (sourceFilter === 'topk' && record.source.includes('Top-K'))
        || (sourceFilter === 'expert' && record.source.includes('专家'));
      const typeMatched = typeFilter === 'all' || record.anomaly_type === typeFilter;
      const windowMatched = windowFilter === 'all' || record.primary_window === windowFilter;
      const dimMatched = dimFilter === 'all' || record.layer === dimFilter;
      return levelMatched && sourceMatched && typeMatched && windowMatched && dimMatched;
    });
  }, [allRows, levelFilter, sourceFilter, typeFilter, windowFilter, dimFilter]);

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

  const activeTheme = getTheme();
  // 全部使用当前主题主色：柱形=主色，折线=主色深阶，区域/基准线使用同色透明阶。
  const selectedTrendBrand = activeTheme.brand;
  const selectedTrendHover = shadeHex(selectedTrendBrand, -0.14);
  const selectedTrendAccent = shadeHex(selectedTrendBrand, -0.42);
  const selectedTrendTint = hexWithAlpha(selectedTrendBrand, 0.10);
  const selectedTrendGuide = hexWithAlpha(selectedTrendAccent, 0.78);

  const selectedPathTrendOption = useMemo<EChartsOption>(() => {
    if (!pathTrend) return {};
    const trend = pathTrend.daily;
    const primaryWindow = pathTrend.primary_window;
    const baselineDaily = Number(primaryWindow.baseline_daily ?? 0);
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
            `当日整体申请量：${formatNumber(point.total_application_count)} 件`,
            `通过率：<b>${point.approval_rate_pct == null ? '—' : `${point.approval_rate_pct.toFixed(2)}%`}</b>`,
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
            data: [{ type: 'max', name: '15天峰值' }],
          },
          markLine: baselineDaily > 0 ? {
            symbol: 'none',
            lineStyle: { color: selectedTrendGuide, type: 'dashed' },
            label: { color: selectedTrendAccent, fontSize: 10, formatter: `基准日均 ${baselineDaily.toFixed(1)}` },
            data: [{ yAxis: baselineDaily }],
          } : undefined,
          markArea: primaryWindow.observation_start && primaryWindow.observation_end ? {
            silent: true,
            itemStyle: { color: selectedTrendTint },
            label: { color: selectedTrendAccent, fontSize: 10, formatter: `${primaryWindow.label}观察期` },
            data: [[
              { xAxis: formatDate(primaryWindow.observation_start) },
              { xAxis: formatDate(primaryWindow.observation_end) },
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
      ],
    };
  }, [activeTheme.key, pathTrend, selectedTrendAccent, selectedTrendBrand, selectedTrendGuide, selectedTrendHover, selectedTrendTint]);

  const alertColumns: FeishuColumn<AttributionRecord>[] = [
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
    { key: 'approval_rate_pct', title: '通过率', width: 82, align: 'right', render: (record) => <span className="tabular-nums">{formatApprovalRate(record.approval_rate_pct)}</span> },
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
    <div className="mx-auto max-w-[1440px] space-y-4 pb-2">
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
