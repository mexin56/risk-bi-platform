import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import type { EChartsOption } from 'echarts';
import ReactECharts from 'echarts-for-react';
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  CheckCircle2,
  ChevronRight,
  Database,
  Layers3,
  LoaderCircle,
  RefreshCw,
  SearchCheck,
  ShieldAlert,
  Sparkles,
  Target,
  TrendingUp,
} from 'lucide-react';
import ChartCard from '@/components/ChartCard';
import FeishuTable, { StatusTag, type FeishuColumn } from '@/components/FeishuTable';
import { areaGradient, baseOption } from '@/lib/chartTheme';
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

function MetricTile({
  label,
  value,
  detail,
  tone = 'blue',
  icon,
}: {
  label: string;
  value: ReactNode;
  detail: ReactNode;
  tone?: 'blue' | 'red' | 'orange' | 'green';
  icon: ReactNode;
}) {
  const colors = {
    blue: { bg: '#eef4ff', fg: '#4e83fd', line: '#d8e6ff' },
    red: { bg: '#fff1f2', fg: '#f43f5e', line: '#ffe0e6' },
    orange: { bg: '#fff7ed', fg: '#f97316', line: '#ffead5' },
    green: { bg: '#ecfdf5', fg: '#10b981', line: '#d1fae5' },
  }[tone];
  return (
    <div className="relative overflow-hidden rounded-xl border bg-white px-4 py-3.5 shadow-[0_1px_2px_rgba(15,23,42,0.04)]" style={{ borderColor: colors.line }}>
      <div className="absolute inset-x-0 top-0 h-0.5" style={{ background: colors.fg }} />
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[12px] text-slate-500">{label}</span>
        <span className="flex h-6 w-6 items-center justify-center rounded-md" style={{ background: colors.bg, color: colors.fg }}>
          {icon}
        </span>
      </div>
      <div className="text-[24px] font-semibold leading-7 tracking-tight text-slate-800 tabular-nums">{value}</div>
      <div className="mt-1.5 min-h-4 text-[10.5px] text-slate-400">{detail}</div>
    </div>
  );
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
      <div className="mt-2 grid grid-cols-4 gap-2 text-[10px]">
        <div><div className="text-slate-400">观察量</div><div className="mt-0.5 font-semibold text-slate-700 tabular-nums">{formatNumber(metric.observation_count)}</div></div>
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
    <div className="flex min-h-[520px] flex-col items-center justify-center rounded-2xl border border-slate-200 bg-white text-center shadow-[0_1px_3px_rgba(15,23,42,0.05)]">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50 text-blue-500">
        <LoaderCircle size={24} className="animate-spin" />
      </div>
      <div className="text-[15px] font-semibold text-slate-700">{text}</div>
      <div className="mt-2 max-w-md text-[12px] leading-5 text-slate-400">
        正在按 v2.2 口径运行单维全量扫描、Top-K 下钻与专家路径。首次计算通常需要约 1–2 分钟，结果将缓存 15 分钟。
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
          <section className="overflow-hidden rounded-xl border border-slate-100 bg-white">
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
                  <div className="rounded-lg border border-violet-100 bg-violet-50/60 px-2.5 py-2"><div className="text-[10px] text-slate-400">最新日占比</div><div className="mt-0.5 text-[17px] font-semibold text-violet-700 tabular-nums">{currentTrend.summary.latest_application_share_pct.toFixed(3)}%</div></div>
                </div>
                <ReactECharts option={trendOption} style={{ height: 280 }} notMerge />
                <div className="-mt-1 flex flex-wrap gap-x-3 gap-y-1 px-3.5 pb-3 text-[10px] text-slate-400">
                  <span><i className="mr-1 inline-block h-2 w-2 rounded-sm" style={{ background: trendBrand }} />路径申请量</span>
                  <span><i className="mr-1 inline-block h-0.5 w-3 align-middle" style={{ background: trendAccent }} />路径占比</span>
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
  const [selectedPartition, setSelectedPartition] = useState('');
  const [selected, setSelected] = useState<AttributionRecord | null>(null);
  const [selectedTrendRecord, setSelectedTrendRecord] = useState<AttributionRecord | null>(null);
  const [pathTrend, setPathTrend] = useState<AttributionPathTrend | null>(null);
  const [pathTrendLoading, setPathTrendLoading] = useState(false);
  const [pathTrendError, setPathTrendError] = useState<string | null>(null);
  const [pathTrendRequest, setPathTrendRequest] = useState(0);
  const [levelFilter, setLevelFilter] = useState<number | 'all'>('all');
  const [sourceFilter, setSourceFilter] = useState<'all' | 'topk' | 'expert'>('all');
  const [showSuppressed, setShowSuppressed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selectedAnalysisRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async (force = false, pt?: string) => {
    if (force) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const payload = await fetchCreditAttribution(pt, force);
      setDashboard(payload);
      setSelectedPartition(payload.meta.partition);
      setSelected((current) => payload.merged_alerts.find((record) => record.canonical_path === current?.canonical_path) ?? payload.highlight ?? payload.merged_alerts[0] ?? null);
      setSelectedTrendRecord(null);
      setPathTrend(null);
      setPathTrendError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法获取授信归因数据');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void fetchAttributionPartitions()
      .then(({ partitions: values }) => setPartitions(values))
      .catch(() => setPartitions([]));
    void load();
  }, [load]);

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
    void fetchAttributionPathTrend(selectedTrendRecord.id, dashboard.meta.partition)
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
  }, [dashboard?.meta.partition, pathTrendRequest, selectedTrendRecord?.id]);

  const filteredAlerts = useMemo(() => {
    if (!dashboard) return [];
    return dashboard.merged_alerts.filter((record) => {
      const levelMatched = levelFilter === 'all' || record.level === levelFilter;
      const sourceMatched = sourceFilter === 'all'
        || (sourceFilter === 'topk' && record.source.includes('Top-K'))
        || (sourceFilter === 'expert' && record.source.includes('专家'));
      return levelMatched && sourceMatched;
    });
  }, [dashboard, levelFilter, sourceFilter]);

  const activeTheme = getTheme();
  // 全部使用当前主题主色：柱形=主色，折线=主色深阶，区域/基准线使用同色透明阶。
  const selectedTrendBrand = activeTheme.brand;
  const selectedTrendHover = shadeHex(selectedTrendBrand, -0.14);
  const selectedTrendAccent = shadeHex(selectedTrendBrand, -0.42);
  const selectedTrendTint = hexWithAlpha(selectedTrendBrand, 0.10);
  const selectedTrendGuide = hexWithAlpha(selectedTrendAccent, 0.78);

  const trendOption = useMemo(() => {
    if (!dashboard) return {};
    const trend = dashboard.daily_trend;
    const focusName = dashboard.highlight ? `系统重点路径 · ${dashboard.highlight.conditions.at(-1)?.value ?? '重点路径'}` : '系统重点路径';
    return {
      ...baseOption(),
      grid: { left: 16, right: 20, top: 38, bottom: 12, containLabel: true },
      legend: { ...baseOption().legend, top: 2, right: 6 },
      xAxis: { ...baseOption().xAxis, boundaryGap: false, data: trend.map((item) => formatDate(item.date)) },
      yAxis: [
        { ...baseOption().yAxis, name: '申请量', nameTextStyle: { color: '#8f959e', fontSize: 10 } },
        { ...baseOption().yAxis, name: '重点路径', splitLine: { show: false }, nameTextStyle: { color: '#8f959e', fontSize: 10 } },
      ],
      series: [
        {
          name: '整体授信申请量', type: 'line', smooth: true, symbol: 'none', lineStyle: { width: 2.4, color: '#4e83fd' },
          areaStyle: { color: areaGradient('#4e83fd', 0.16) }, data: trend.map((item) => item.application_count),
        },
        {
          name: 'PalmPay_IOS', type: 'line', smooth: true, symbol: 'none', lineStyle: { width: 1.8, color: '#8b5cf6', type: 'dashed' },
          data: trend.map((item) => item.expert_seed_count),
        },
        {
          name: focusName, type: 'line', yAxisIndex: 1, smooth: true, symbol: 'circle', symbolSize: 5,
          lineStyle: { width: 2.4, color: '#f43f5e' }, itemStyle: { color: '#f43f5e' },
          data: trend.map((item) => item.focus_path_count),
        },
      ],
    };
  }, [dashboard]);

  const levelOption = useMemo(() => {
    if (!dashboard) return {};
    const values = [dashboard.summary.level3_count, dashboard.summary.level2_count, dashboard.summary.level1_count];
    return {
      ...baseOption(),
      grid: { left: 12, right: 14, top: 20, bottom: 6, containLabel: true },
      xAxis: { ...baseOption().xAxis, type: 'value', splitLine: { show: false }, axisLabel: { show: false } },
      yAxis: { ...baseOption().yAxis, type: 'category', data: ['Level3 红色', 'Level2 橙色', 'Level1 黄色'], axisTick: { show: false } },
      tooltip: { ...baseOption().tooltip, trigger: 'axis', axisPointer: { type: 'shadow' } },
      series: [{
        type: 'bar', data: values, barWidth: 16,
        label: { show: true, position: 'right', color: '#64748b', fontSize: 11 },
        itemStyle: { borderRadius: [0, 5, 5, 0], color: (params: { dataIndex: number }) => ['#f43f5e', '#f97316', '#f59e0b'][params.dataIndex] },
      }],
    };
  }, [dashboard]);

  const selectedPathTrendOption = useMemo<EChartsOption>(() => {
    if (!pathTrend) return {};
    const trend = pathTrend.daily;
    const primaryWindow = pathTrend.primary_window;
    const baselineDaily = Number(primaryWindow.baseline_daily ?? 0);
    return {
      ...baseOption(),
      grid: { left: 16, right: 20, top: 38, bottom: 12, containLabel: true },
      legend: { ...baseOption().legend, top: 2, right: 6 },
      tooltip: {
        ...baseOption().tooltip,
        trigger: 'axis',
        formatter: (params: Array<{ dataIndex?: number }>) => {
          const point = trend[params[0]?.dataIndex ?? 0];
          if (!point) return '';
          return [
            `<b>${point.date}</b>`,
            `路径授信申请量：<b>${formatNumber(point.application_count)}</b> 件`,
            `当日整体申请量：${formatNumber(point.total_application_count)} 件`,
            `路径占比：${point.application_share_pct.toFixed(3)}%`,
          ].join('<br/>');
        },
      },
      xAxis: { ...baseOption().xAxis, data: trend.map((item) => formatDate(item.date)) },
      yAxis: [
        { ...baseOption().yAxis, name: '路径申请量', nameTextStyle: { color: '#8f959e', fontSize: 10 } },
        {
          ...baseOption().yAxis,
          name: '路径占比',
          position: 'right',
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
          name: '路径占比',
          type: 'line',
          yAxisIndex: 1,
          smooth: true,
          symbol: 'circle',
          symbolSize: 5,
          lineStyle: { width: 2, color: selectedTrendAccent },
          itemStyle: { color: selectedTrendAccent },
          data: trend.map((item) => item.application_share_pct),
        },
      ],
    };
  }, [activeTheme.key, pathTrend, selectedTrendAccent, selectedTrendBrand, selectedTrendGuide, selectedTrendHover, selectedTrendTint]);

  const alertColumns: FeishuColumn<AttributionRecord>[] = [
    {
      key: 'level_label', title: '等级', sticky: true, width: 104,
      render: (record) => <SeverityTag severity={record.severity} text={`L${record.level}`} />,
    },
    { key: 'source', title: '来源', width: 118, render: (record) => <SourceTag source={record.source} /> },
    {
      key: 'path', title: '异常归因路径', width: 360,
      render: (record) => (
        <button
          onClick={() => selectAlertPath(record)}
          className="max-w-[340px] truncate text-left font-medium text-slate-700 underline-offset-2 hover:text-blue-600 hover:underline"
          title="点击查看该路径近15天授信申请量趋势"
        >
          {record.path}
        </button>
      ),
    },
    { key: 'layer', title: '层级', width: 70, align: 'center' },
    { key: 'anomaly_type', title: '异常类型', width: 90 },
    { key: 'primary_window_label', title: '主窗口', width: 78, align: 'center' },
    { key: 'observation_count', title: '观察量', width: 82, align: 'right', render: (record) => formatNumber(record.observation_count) },
    { key: 'growth_factor', title: '申请增长', width: 92, align: 'right', render: (record) => formatFactor(record.growth_factor) },
    { key: 'structure_lift_factor', title: '结构提升', width: 92, align: 'right', render: (record) => formatFactor(record.structure_lift_factor) },
    { key: 'z_score', title: 'z-score', width: 76, align: 'right', render: (record) => record.z_score.toFixed(2) },
    { key: 'excess_count', title: '超额量(辅助)', width: 108, align: 'right', render: (record) => `${record.excess_count >= 0 ? '+' : ''}${formatNumber(record.excess_count)}` },
  ];

  if (loading && !dashboard) return <LoadingState />;

  if (error && !dashboard) {
    return (
      <div className="flex min-h-[520px] flex-col items-center justify-center rounded-2xl border border-rose-100 bg-white text-center shadow-[0_1px_3px_rgba(15,23,42,0.05)]">
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

  const { summary, meta, rules } = dashboard;
  const topKCounts = dashboard.top_k.counts;

  return (
    <div className="mx-auto max-w-[1440px] space-y-4 pb-2">
      <section className="relative overflow-hidden rounded-2xl border border-blue-100 bg-white shadow-[0_4px_18px_-10px_rgba(59,130,246,0.35)]">
        <div className="absolute inset-y-0 left-0 w-1 bg-gradient-to-b from-blue-500 via-violet-500 to-rose-400" />
        <div className="absolute -right-16 -top-20 h-52 w-52 rounded-full bg-blue-100/60 blur-3xl" />
        <div className="relative flex flex-col gap-4 px-5 py-4 lg:flex-row lg:items-center">
          <div className="flex min-w-0 items-start gap-3">
            <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-violet-500 text-white shadow-lg shadow-blue-200">
              <Target size={19} />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-[17px] font-semibold tracking-tight text-slate-800">授信归因监控</h2>
                <span className="rounded-md border border-violet-100 bg-violet-50 px-1.5 py-0.5 text-[10.5px] font-medium text-violet-600">Top-K 自动归因 × 专家规则</span>
                <span className="inline-flex items-center gap-1 text-[10.5px] text-emerald-600"><CheckCircle2 size={12} /> MaxCompute 直连</span>
              </div>
              <p className="mt-1 text-[12px] text-slate-500">监控贷前授信申请量异常爆量，区分整体增长与局部画像结构性放量。</p>
            </div>
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-[10.5px] text-slate-500">
              <span className="text-slate-400">观察区间 </span><span className="font-medium text-slate-700">{meta.date_start} ～ {meta.date_end}</span>
            </div>
            {partitions.length > 1 && (
              <select
                value={selectedPartition}
                onChange={(event) => { const pt = event.target.value; setSelectedPartition(pt); void load(false, pt); }}
                className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] text-slate-600 outline-none focus:border-blue-400"
                aria-label="选择数据分区"
              >
                {partitions.map((pt) => <option key={pt} value={pt}>pt={pt}</option>)}
              </select>
            )}
            <button
              onClick={() => void load(true, selectedPartition || undefined)}
              disabled={refreshing}
              className="inline-flex items-center gap-1.5 rounded-lg bg-blue-500 px-3 py-1.5 text-[11px] font-medium text-white transition-colors hover:bg-blue-600 disabled:opacity-60"
            >
              <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} /> {refreshing ? '重新计算中' : '刷新归因'}
            </button>
          </div>
        </div>
        <div className="relative flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-slate-100 px-5 py-2 text-[10.5px] text-slate-400">
          <span className="inline-flex items-center gap-1"><Database size={12} /> {meta.table}</span>
          <span>pt={meta.partition}</span>
          <span>{formatNumber(meta.aggregate_row_count)} 条聚合记录 · {meta.dimension_count} 个归因维度</span>
          <span className={meta.cache_hit ? 'text-emerald-600' : 'text-blue-500'}>{meta.cache_hit ? '命中 15 分钟缓存' : '本次为最新计算结果'}</span>
        </div>
      </section>

      {error && (
        <div className="flex items-center gap-2 rounded-xl border border-orange-200 bg-orange-50 px-4 py-2.5 text-[12px] text-orange-700">
          <AlertTriangle size={15} /> 刷新失败，当前继续展示上一次成功结果：{error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
        <MetricTile label="当日授信申请量" value={formatNumber(summary.latest_application_count)} detail={`上一日 ${formatNumber(summary.previous_application_count)} 件`} icon={<TrendingUp size={14} />} />
        <MetricTile label="日环比变化" value={formatSignedPercent(summary.latest_day_change_pct)} detail="仅用于大盘波动观察" tone={summary.latest_day_change_pct > 0 ? 'orange' : 'green'} icon={<ArrowRight size={14} />} />
        <MetricTile label="合并异常路径" value={formatNumber(summary.merged_alert_count)} detail={`L2+L3 共 ${summary.level2_count + summary.level3_count} 条`} tone="orange" icon={<SearchCheck size={14} />} />
        <MetricTile label="Level3 高优先级" value={formatNumber(summary.level3_count)} detail="P0：多窗口高强度异常优先复核" tone="red" icon={<ShieldAlert size={14} />} />
        <MetricTile label="当日审批通过率" value={`${summary.latest_approval_rate.toFixed(2)}%`} detail={`累计审批 ${formatNumber(summary.approval_count)} 件`} tone="green" icon={<CheckCircle2 size={14} />} />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <ChartCard title="授信申请量与重点路径趋势" subtitle="整体申请量 · 专家一级种子 · 系统重点异常路径" accent="#4e83fd" className="xl:col-span-2">
          <ReactECharts option={trendOption} style={{ height: 288 }} notMerge />
        </ChartCard>
        <ChartCard title="预警等级分布" subtitle="等级由观察量、增长、结构提升、z-score 四项同时判定" accent="#f97316">
          <ReactECharts option={levelOption} style={{ height: 150 }} notMerge />
          <div className="mx-4 mb-3 border-t border-slate-100 pt-3 text-[10.5px] leading-5 text-slate-400">
            <span className="font-medium text-slate-600">v2.2 原则：</span>超额申请量只描述业务影响，<span className="font-medium text-slate-600">不参与等级升级或 Top-K 主排序</span>。
          </div>
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <ChartCard title="自动归因下钻链路" subtitle="全量扫描 → 严格 Top-K 下钻，避免维度组合爆炸" accent="#4e83fd" className="xl:col-span-2">
          <div className="grid grid-cols-1 gap-3 px-3 py-3 md:grid-cols-3">
            {[
              { title: '单维全量扫描', value: topKCounts.single_scanned ?? 0, sub: `保留 Top${dashboard.top_k.single_downstream.length} 进入二级`, color: '#4e83fd', icon: <SearchCheck size={15} /> },
              { title: '二级组合扫描', value: topKCounts.pair_scanned ?? 0, sub: `保留 Top${dashboard.top_k.pair_downstream.length} 进入三级`, color: '#8b5cf6', icon: <Layers3 size={15} /> },
              { title: '三级异常输出', value: topKCounts.third_alerts ?? 0, sub: `三级已计算 ${topKCounts.third_scanned ?? 0} 条`, color: '#f97316', icon: <AlertTriangle size={15} /> },
            ].map((item, index) => (
              <div key={item.title} className="relative rounded-xl border border-slate-100 bg-slate-50/70 p-3.5">
                {index < 2 && <ChevronRight size={17} className="absolute -right-[14px] top-1/2 z-10 hidden -translate-y-1/2 text-slate-300 md:block" />}
                <div className="mb-2 flex items-center gap-2" style={{ color: item.color }}>{item.icon}<span className="text-[11px] font-medium">{item.title}</span></div>
                <div className="text-[25px] font-semibold leading-7 text-slate-800 tabular-nums">{formatNumber(item.value)}</div>
                <div className="mt-1 text-[10.5px] text-slate-400">{item.sub}</div>
              </div>
            ))}
          </div>
        </ChartCard>
        <ChartCard title="专家规则兜底链路" subtitle="不受 Top-K 剪枝限制，但不改变统一预警阈值" accent="#8b5cf6">
          <div className="px-4 py-4">
            <div className="mb-4 flex items-center gap-2 text-violet-600"><Bot size={16} /><span className="text-[12px] font-semibold">业务重点路径</span></div>
            <div className="space-y-2">
              {rules.expert_path.map((step, index) => (
                <div key={step.field} className="flex items-center gap-2 text-[11px]">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-violet-100 text-[10px] font-semibold text-violet-600">{index + 1}</span>
                  <span className="min-w-0 truncate rounded-md border border-violet-100 bg-violet-50 px-2 py-1 text-violet-700">{step.field}={step.value === '*' ? '全量' : step.value}</span>
                </div>
              ))}
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2 border-t border-slate-100 pt-3">
              <div><div className="text-[10px] text-slate-400">三级全量计算</div><div className="mt-0.5 text-[17px] font-semibold text-slate-700">{dashboard.expert.counts.third_calculated ?? 0}</div></div>
              <div><div className="text-[10px] text-slate-400">专家发现预警</div><div className="mt-0.5 text-[17px] font-semibold text-violet-600">{dashboard.expert.counts.alerts ?? 0}</div></div>
            </div>
          </div>
        </ChartCard>
      </div>

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

      <ChartCard
        title="合并预警结果"
        subtitle={`Top-K 与专家规则按“字段=取值”标准化路径去重；当前 ${dashboard.merged_alert_total} 条预警结果。点击路径可同步切换上方归因解释与近15天趋势`}
        accent="#f97316"
        extra={
          <div className="flex items-center gap-1.5">
            {(['all', 3, 2, 1] as const).map((filter) => {
              const label = filter === 'all' ? '全部' : `L${filter}`;
              const active = levelFilter === filter;
              return <button key={label} onClick={() => setLevelFilter(filter)} className={`rounded-md px-2 py-1 text-[10.5px] ${active ? 'bg-slate-700 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`}>{label}</button>;
            })}
            <span className="mx-0.5 h-4 w-px bg-slate-200" />
            {(['all', 'topk', 'expert'] as const).map((filter) => {
              const active = sourceFilter === filter;
              const label = filter === 'all' ? '全部来源' : filter === 'topk' ? 'Top-K' : '专家';
              return <button key={filter} onClick={() => setSourceFilter(filter)} className={`rounded-md px-2 py-1 text-[10.5px] ${active ? 'bg-blue-500 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`}>{label}</button>;
            })}
          </div>
        }
      >
        <FeishuTable columns={alertColumns} data={filteredAlerts} maxHeight={470} rowKey={(record) => record.id} />
      </ChartCard>

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
                    <span className="min-w-0 flex-1 truncate text-slate-600">{record.path}</span>
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
