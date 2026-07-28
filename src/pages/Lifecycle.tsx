import { AnimatePresence, motion } from 'framer-motion';
import ReactECharts from 'echarts-for-react';
import {
  ArrowDownRight,
  ArrowUpRight,
  BadgeCheck,
  Coins,
  PhoneCall,
  Repeat2,
  UserPlus,
  type LucideIcon,
} from 'lucide-react';
import ChartCard from '@/components/ChartCard';
import FeishuTable, { heatStyle, type FeishuColumn } from '@/components/FeishuTable';
import { areaGradient, baseOption } from '@/lib/chartTheme';
import { getBrand, getPalette } from '@/lib/theme';
import {
  collectChannels,
  collectKpis,
  creditKpis,
  getCollectTrend,
  getCreditPassTrend,
  getLifecycleTrend,
  getLoanTrend,
  getRegTrend,
  getRetentionCurve,
  limitDist,
  loanFunnel,
  loanKpis,
  regFunnel,
  regKpis,
  rejectPie,
  relendKpis,
  rollTable,
  termDist,
  lifecycleStageTable,
  type FunnelStage,
  type LifecycleStageRow,
  type RollRow,
  type StageKpi,
} from '@/data/mockData';

// ==================== 环节配置（侧边栏二级菜单共用） ====================
export type StageKey = 'pre' | 'credit' | 'loan' | 'reloan' | 'collect';

export const STAGES: { key: StageKey; label: string; icon: LucideIcon; hint: string }[] = [
  { key: 'pre', label: '贷前注册', icon: UserPlus, hint: '注册→实名→资料→授信申请' },
  { key: 'credit', label: '授信环节', icon: BadgeCheck, hint: '机审/终审/额度/时效' },
  { key: 'loan', label: '交易环节', icon: Coins, hint: '支用→放款→期限结构' },
  { key: 'reloan', label: '复贷环节', icon: Repeat2, hint: '留存/复借/客户分层' },
  { key: 'collect', label: '催收环节', icon: PhoneCall, hint: '入催/滚动率/催回' },
];

// ==================== 环节 KPI 小卡 ====================
function StageKpiCard({ kpi, index }: { kpi: StageKpi; index: number }) {
  const up = kpi.mom >= 0;
  const bad = kpi.goodDown ? up : !up;
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: index * 0.05 }}
      className="bg-white rounded-xl border border-slate-200/80 px-4 py-3.5 shadow-[0_1px_2px_rgba(15,23,42,0.04)] hover:shadow-md hover:-translate-y-0.5 transition-all duration-300"
    >
      <div className="text-[12px] text-slate-500 mb-1.5">{kpi.label}</div>
      <div className="flex items-baseline gap-1">
        <span className="text-[22px] font-semibold text-slate-800 tracking-tight tabular-nums">{kpi.value}</span>
        {kpi.unit && <span className="text-[12px] text-slate-400">{kpi.unit}</span>}
      </div>
      <div
        className={`mt-1.5 inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md text-[11px] font-medium tabular-nums ${
          kpi.mom === 0 ? 'bg-slate-100 text-slate-500' : bad ? 'bg-rose-50 text-rose-500' : 'bg-emerald-50 text-emerald-600'
        }`}
      >
        {kpi.mom !== 0 && (up ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />)}
        {kpi.mom === 0 ? '持平' : `${Math.abs(kpi.mom)}%`}
        <span className="text-slate-400 font-normal ml-0.5">环比</span>
      </div>
    </motion.div>
  );
}

function KpiRow({ items, cols }: { items: StageKpi[]; cols: string }) {
  return (
    <div className={`grid gap-3 ${cols}`}>
      {items.map((k, i) => (
        <StageKpiCard key={k.label} kpi={k} index={i} />
      ))}
    </div>
  );
}

// ==================== 漏斗图生成器 ====================
function funnelOption(data: FunnelStage[], widthPct = '58%') {
  const pal = getPalette();
  return {
    color: [pal[0], '#5f94fe', '#36cfc9', '#4fd0a5', '#37c26b', '#ffb020', '#ff8f4d', '#f76965'],
    tooltip: { trigger: 'item', formatter: (p: { name: string; value: number }) => `${p.name}: ${p.value.toLocaleString()} 人` },
    series: [
      {
        type: 'funnel',
        left: '4%',
        width: widthPct,
        top: 12,
        bottom: 12,
        minSize: '22%',
        maxSize: '100%',
        sort: 'descending',
        gap: 3,
        label: {
          show: true,
          position: 'inside',
          formatter: (p: { name: string; value: number }) => `${p.name}\n${p.value.toLocaleString()}`,
          fontSize: 11.5,
          color: '#fff',
          lineHeight: 16,
        },
        itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
        data: data.map((s) => ({ name: s.stage, value: s.value })),
      },
    ],
  };
}

// ==================== 贷前注册环节 ====================
function StagePre() {
  const trend = getRegTrend();
  const trendOption = {
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: trend.map((d) => d.date), boundaryGap: false },
    yAxis: { ...baseOption().yAxis },
    series: (['新增注册', '实名通过'] as const).map((k, i) => ({
      name: k,
      type: 'line',
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2 },
      areaStyle: { color: areaGradient(i === 0 ? getBrand() : '#36cfc9', 0.12) },
      data: trend.map((d) => d[k] as number),
    })),
  };

  return (
    <div className="space-y-4">
      <KpiRow items={regKpis} cols="grid-cols-2 xl:grid-cols-4" />
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ChartCard title="注册→授信申请 转化漏斗" subtitle="当日口径 · 人">
          <ReactECharts option={funnelOption(regFunnel)} style={{ height: 300 }} notMerge />
        </ChartCard>
        <ChartCard title="注册与实名趋势" subtitle="近30天 · 人" accent="#36cfc9">
          <ReactECharts option={trendOption} style={{ height: 300 }} notMerge />
        </ChartCard>
      </div>
    </div>
  );
}

// ==================== 授信环节 ====================
function StageCredit() {
  const passTrend = getCreditPassTrend();

  const rejectOption = {
    color: [getBrand(), '#ffb020', '#36cfc9', '#f76965', '#bcc0c7'],
    tooltip: { trigger: 'item', formatter: '{b}: {c}% ({d}%)' },
    legend: { orient: 'vertical', right: 4, top: 'middle', icon: 'circle', itemWidth: 8, textStyle: { fontSize: 11, color: '#646a73' } },
    series: [
      {
        type: 'pie',
        radius: ['50%', '74%'],
        center: ['36%', '52%'],
        itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        emphasis: { scale: true, scaleSize: 6 },
        data: rejectPie,
      },
    ],
  };

  const limitOption = {
    ...baseOption(),
    grid: { left: 12, right: 16, top: 24, bottom: 8, containLabel: true },
    xAxis: { ...baseOption().xAxis, data: limitDist.map((d) => d.range) },
    yAxis: { ...baseOption().yAxis, axisLabel: { formatter: '{value}%', color: '#8f959e', fontSize: 11 } },
    series: [
      {
        type: 'bar',
        barMaxWidth: 26,
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: getBrand() },
              { offset: 1, color: `${getBrand()}88` },
            ],
          },
        },
        label: { show: true, position: 'top', fontSize: 10.5, color: '#8f959e', formatter: '{c}%' },
        data: limitDist.map((d) => d.pct),
      },
    ],
  };

  const passOption = {
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: passTrend.map((d) => d.date), boundaryGap: false },
    yAxis: { ...baseOption().yAxis, axisLabel: { formatter: '{value}%', color: '#8f959e', fontSize: 11 } },
    series: (['机审通过率', '终审通过率'] as const).map((k, i) => ({
      name: k,
      type: 'line',
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2 },
      areaStyle: { color: areaGradient(i === 0 ? getBrand() : '#36cfc9', 0.1) },
      data: passTrend.map((d) => d[k] as number),
    })),
  };

  return (
    <div className="space-y-4">
      <KpiRow items={creditKpis} cols="grid-cols-2 md:grid-cols-3 xl:grid-cols-5" />
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ChartCard title="审批通过率趋势" subtitle="近30天 · 机审 / 终审 (%)">
          <ReactECharts option={passOption} style={{ height: 270 }} notMerge />
        </ChartCard>
        <ChartCard title="拒绝原因分布" subtitle="当日拒绝件归因 (%)" accent="#f76965">
          <ReactECharts option={rejectOption} style={{ height: 270 }} notMerge />
        </ChartCard>
      </div>
      <ChartCard title="授信额度分布" subtitle="终审通过客户 · 额度区间占比" accent="#7f6bf2">
        <ReactECharts option={limitOption} style={{ height: 240 }} notMerge />
      </ChartCard>
    </div>
  );
}

// ==================== 交易环节 ====================
function StageLoan() {
  const loanTrend = getLoanTrend();

  const termOption = {
    ...baseOption(),
    grid: { left: 12, right: 16, top: 24, bottom: 8, containLabel: true },
    xAxis: { ...baseOption().xAxis, data: termDist.map((d) => d.range) },
    yAxis: { ...baseOption().yAxis, axisLabel: { formatter: '{value}%', color: '#8f959e', fontSize: 11 } },
    series: [
      {
        type: 'bar',
        barMaxWidth: 26,
        itemStyle: { borderRadius: [4, 4, 0, 0], color: '#36cfc9' },
        label: { show: true, position: 'top', fontSize: 10.5, color: '#8f959e', formatter: '{c}%' },
        data: termDist.map((d) => d.pct),
      },
    ],
  };

  const loanOption = {
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: loanTrend.map((d) => d.date) },
    yAxis: [{ ...baseOption().yAxis }],
    series: [
      {
        name: '放款金额',
        type: 'bar',
        barMaxWidth: 14,
        itemStyle: { borderRadius: [3, 3, 0, 0], color: getBrand(), opacity: 0.9 },
        data: loanTrend.map((d) => d.放款金额),
      },
      {
        name: '通过量',
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2, color: '#ffb020' },
        data: loanTrend.map((d) => d.通过量),
      },
    ],
  };

  return (
    <div className="space-y-4">
      <KpiRow items={loanKpis} cols="grid-cols-2 xl:grid-cols-4" />
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ChartCard title="支用→放款 转化漏斗" subtitle="当日口径 · 人">
          <ReactECharts option={funnelOption(loanFunnel)} style={{ height: 290 }} notMerge />
        </ChartCard>
        <ChartCard title="借款期限结构" subtitle="当日放款 · 期限占比 (%)" accent="#36cfc9">
          <ReactECharts option={termOption} style={{ height: 290 }} notMerge />
        </ChartCard>
      </div>
      <ChartCard title="放款与通过趋势" subtitle="近30天 · 万元 / 件" accent="#ffb020">
        <ReactECharts option={loanOption} style={{ height: 250 }} notMerge />
      </ChartCard>
    </div>
  );
}

// ==================== 复贷环节 ====================
function StageReloan() {
  const trend = getLifecycleTrend();
  const retention = getRetentionCurve();

  const trendOption = {
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: trend.map((d) => d.date), boundaryGap: false },
    yAxis: { ...baseOption().yAxis, axisLabel: { formatter: '{value}%', color: '#8f959e', fontSize: 11 } },
    series: [
      { name: '新户放款占比', type: 'line', smooth: true, symbol: 'none', areaStyle: { color: areaGradient(getBrand(), 0.12) }, data: trend.map((d) => d.新户放款占比) },
      { name: '复借占比', type: 'line', smooth: true, symbol: 'none', areaStyle: { color: areaGradient('#36cfc9', 0.12) }, data: trend.map((d) => d.复借占比) },
      { name: '结清流失率', type: 'line', smooth: true, symbol: 'none', lineStyle: { type: 'dashed', width: 2, color: '#f76965' }, data: trend.map((d) => d.结清流失率) },
    ],
  };

  const retentionOption = {
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: retention.map((d) => d.date) },
    yAxis: { ...baseOption().yAxis, max: 100, axisLabel: { formatter: '{value}%', color: '#8f959e', fontSize: 11 } },
    series: ['2025-11', '2025-12', '2026-01'].map((c) => ({
      name: `${c} 放款cohort`,
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { width: 2 },
      data: retention.map((d) => d[c] as number),
    })),
  };

  const stageCols: FeishuColumn<LifecycleStageRow>[] = [
    { key: 'stage', title: '生命周期阶段', sticky: true, width: 170, render: (r) => <span className="font-medium text-slate-800">{r.stage}</span> },
    { key: 'customers', title: '客户数', align: 'right' },
    {
      key: 'ratio', title: '占比', align: 'right',
      render: (r) => (
        <div className="flex items-center justify-end gap-2">
          <div className="w-16 h-1.5 rounded-full bg-slate-100 overflow-hidden">
            <div className="h-full rounded-full" style={{ width: `${r.ratio}%`, background: 'var(--brand)' }} />
          </div>
          <span className="w-11 text-right">{r.ratio}%</span>
        </div>
      ),
    },
    { key: 'avgBalance', title: '人均在贷', align: 'right' },
    { key: 'm1Rate', title: 'M1+ 逾期率', align: 'right', render: (r) => (r.m1Rate === 0 ? '—' : `${r.m1Rate}%`), cellStyle: (r) => (r.m1Rate === 0 ? undefined : heatStyle(r.m1Rate, 1.5, 4.8, 'red')) },
    { key: 'relendRate', title: '复借率', align: 'right', render: (r) => (r.relendRate === 0 ? '—' : `${r.relendRate}%`), cellStyle: (r) => (r.relendRate === 0 ? undefined : heatStyle(r.relendRate, 0, 80, 'green')) },
  ];

  return (
    <div className="space-y-4">
      <KpiRow items={relendKpis} cols="grid-cols-2 xl:grid-cols-4" />
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ChartCard title="新旧户结构与流失趋势" subtitle="近12个月放款结构 (%)">
          <ReactECharts option={trendOption} style={{ height: 270 }} notMerge />
        </ChartCard>
        <ChartCard title="放款后留存曲线" subtitle="放款后第N月仍有在贷/复借行为的客户占比" accent="#37c26b">
          <ReactECharts option={retentionOption} style={{ height: 270 }} notMerge />
        </ChartCard>
      </div>
      <ChartCard title="客户分层明细" subtitle="生命周期阶段 × 风险与价值指标" accent="#37c26b">
        <FeishuTable columns={stageCols} data={lifecycleStageTable} rowKey={(r) => r.stage} />
      </ChartCard>
    </div>
  );
}

// ==================== 催收环节 ====================
function StageCollect() {
  const trend = getCollectTrend();

  const trendOption = {
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: trend.map((d) => d.date), boundaryGap: false },
    yAxis: { ...baseOption().yAxis, axisLabel: { formatter: '{value}%', color: '#8f959e', fontSize: 11 } },
    series: [
      { name: '入催率', type: 'line', smooth: true, symbol: 'none', lineStyle: { width: 2, color: '#f76965' }, areaStyle: { color: areaGradient('#f76965', 0.1) }, data: trend.map((d) => d.入催率) },
      { name: 'M1催回率', type: 'line', smooth: true, symbol: 'none', lineStyle: { width: 2, color: getBrand() }, areaStyle: { color: areaGradient(getBrand(), 0.1) }, data: trend.map((d) => d.M1催回率) },
    ],
  };

  const channelOption = {
    ...baseOption(),
    grid: { left: 12, right: 44, top: 20, bottom: 8, containLabel: true },
    xAxis: { ...baseOption().xAxis, type: 'value', axisLabel: { formatter: '{value}%', color: '#8f959e', fontSize: 11 } },
    yAxis: {
      type: 'category',
      inverse: true,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#1f2329', fontSize: 11.5 },
      data: collectChannels.map((c) => c.name),
    },
    series: [
      {
        type: 'bar',
        barWidth: 16,
        itemStyle: {
          borderRadius: [0, 8, 8, 0],
          color: (p: { dataIndex: number }) => ['#37c26b', getBrand(), '#ffb020', '#f76965'][p.dataIndex],
        },
        label: { show: true, position: 'right', fontSize: 11, color: '#646a73', formatter: '{c}%' },
        data: collectChannels.map((c) => c.rate),
      },
    ],
  };

  const rollCols: FeishuColumn<RollRow>[] = [
    { key: 'from', title: '逾期阶段', sticky: true, width: 140, render: (r) => <span className="font-medium text-slate-800">{r.from}</span> },
    { key: 'bal', title: '入催余额', align: 'right' },
    { key: 'cure', title: '当月结清', align: 'right', render: (r) => `${r.cure}%`, cellStyle: (r) => heatStyle(r.cure, 0, 85, 'green') },
    { key: 'stay', title: '维持同阶段', align: 'right', render: (r) => `${r.stay}%`, cellStyle: (r) => heatStyle(r.stay, 0, 35, 'blue') },
    { key: 'worse', title: '恶化至下阶段', align: 'right', render: (r) => `${r.worse}%`, cellStyle: (r) => heatStyle(r.worse, 0, 70, 'red') },
  ];

  return (
    <div className="space-y-4">
      <KpiRow items={collectKpis} cols="grid-cols-2 xl:grid-cols-4" />
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ChartCard title="入催率与催回率趋势" subtitle="近12个月 (%)" accent="#f76965">
          <ReactECharts option={trendOption} style={{ height: 260 }} notMerge />
        </ChartCard>
        <ChartCard title="催收方式回收率对比" subtitle="近30天 · 各触达方式回收率 (%)" accent="#37c26b">
          <ReactECharts option={channelOption} style={{ height: 260 }} notMerge />
        </ChartCard>
      </div>
      <ChartCard title="滚动率矩阵 (Roll Rate)" subtitle="各逾期阶段当月迁移去向 · 绿色=结清 / 蓝色=维持 / 红色=恶化" accent="#f76965">
        <FeishuTable columns={rollCols} data={rollTable} rowKey={(r) => r.from} />
      </ChartCard>
    </div>
  );
}

// ==================== 页面主体（环节由侧边栏二级菜单控制） ====================
export default function Lifecycle({ stage }: { stage: StageKey }) {
  const active = STAGES.find((s) => s.key === stage)!;

  return (
    <div className="space-y-4 max-w-[1440px] mx-auto">
      {/* 面包屑 + 当前环节提示 */}
      <AnimatePresence mode="wait">
        <motion.div
          key={stage}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="flex items-center gap-2 text-[12px] px-1"
        >
          <span className="text-slate-400">客户生命周期</span>
          <span className="text-slate-300">/</span>
          <active.icon size={13} style={{ color: 'var(--brand)' }} />
          <span className="font-medium text-slate-700">{active.label}</span>
          <span className="text-slate-300">·</span>
          <span className="text-slate-400">{active.hint}</span>
        </motion.div>
      </AnimatePresence>

      {/* 环节内容 */}
      <AnimatePresence mode="wait">
        <motion.div
          key={stage}
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
        >
          {stage === 'pre' && <StagePre />}
          {stage === 'credit' && <StageCredit />}
          {stage === 'loan' && <StageLoan />}
          {stage === 'reloan' && <StageReloan />}
          {stage === 'collect' && <StageCollect />}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
