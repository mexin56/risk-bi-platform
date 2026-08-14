import { useMemo, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import {
  BadgeCheck,
  ChevronRight,
  CircleAlert,
  ClipboardCheck,
  Database,
  FileWarning,
  Gauge,
  Layers3,
  ShieldAlert,
  Target,
  TrendingUp,
  UsersRound,
  ExternalLink,
} from 'lucide-react';
import ChartCard from '@/components/ChartCard';
import FeishuTable, { StatusTag, type FeishuColumn } from '@/components/FeishuTable';
import { baseOption } from '@/lib/chartTheme';
import { getBrand } from '@/lib/theme';
import {
  coefficientDistribution,
  rolloutMix,
  rootCauses,
  strategyChecks,
  strategyScenarios,
  strategyScoreRows,
  strategySnapshot,
  type StrategyCheck,
  type StrategyScoreRow,
} from '@/data/creditStrategyMonitor';

type View = 'overview' | 'validation';

type Tone = 'green' | 'orange' | 'red' | 'blue';

const toneStyle: Record<Tone, { chip: string; line: string; icon: string }> = {
  green: { chip: 'bg-emerald-50 text-emerald-700 border-emerald-200', line: '#22a06b', icon: 'bg-emerald-50 text-emerald-600' },
  orange: { chip: 'bg-orange-50 text-orange-700 border-orange-200', line: '#f59e0b', icon: 'bg-orange-50 text-orange-600' },
  red: { chip: 'bg-rose-50 text-rose-700 border-rose-200', line: '#f76965', icon: 'bg-rose-50 text-rose-600' },
  blue: { chip: 'bg-blue-50 text-blue-700 border-blue-200', line: '#4e83fd', icon: 'bg-blue-50 text-blue-600' },
};

function integer(value: number) {
  return Math.round(value).toLocaleString('zh-CN');
}

function percent(value: number, digits = 1) {
  return `${value.toFixed(digits)}%`;
}

function SnapshotKpi({
  label,
  value,
  unit,
  hint,
  tone = 'blue',
  icon: Icon,
}: {
  label: string;
  value: string;
  unit?: string;
  hint: string;
  tone?: Tone;
  icon: typeof Target;
}) {
  const style = toneStyle[tone];
  return (
    <div className="relative overflow-hidden bg-white/60 backdrop-blur-xl rounded-2xl border border-white/60 px-4 pt-3.5 pb-3 shadow-[0_1px_2px_rgba(15,23,42,0.04)] hover:-translate-y-0.5 hover:shadow-[0_8px_22px_-10px_rgba(15,23,42,0.18)] transition-all duration-300">
      <div className="absolute top-0 left-0 h-[2px] w-full" style={{ background: style.line }} />
      <div className="flex items-center justify-between gap-3">
        <span className="text-[11px] font-semibold tracking-[0.07em] text-slate-500">{label}</span>
        <span className={`w-7 h-7 rounded-lg flex items-center justify-center ${style.icon}`}>
          <Icon size={14} strokeWidth={2.2} />
        </span>
      </div>
      <div className="flex items-baseline gap-1 mt-2.5">
        <span className="text-[25px] leading-6 font-semibold tracking-tight tabular-nums text-slate-800">{value}</span>
        {unit && <span className="text-[11px] text-slate-400">{unit}</span>}
      </div>
      <div className="mt-2 text-[10.5px] leading-4 text-slate-400">{hint}</div>
    </div>
  );
}

function CheckRow({ check }: { check: StrategyCheck }) {
  const style = toneStyle[check.tone];
  return (
    <div className="flex items-start gap-3 py-3 border-b border-slate-100 last:border-none">
      <span className={`mt-0.5 w-7 h-7 shrink-0 rounded-lg flex items-center justify-center ${style.icon}`}>
        {check.tone === 'green' ? <BadgeCheck size={14} /> : <CircleAlert size={14} />}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-[12.5px] font-semibold text-slate-800">{check.name}</span>
          <span className={`inline-flex rounded-md border px-1.5 py-0.5 text-[10.5px] font-semibold tabular-nums ${style.chip}`}>{check.value}</span>
        </div>
        <p className="mt-1 text-[11px] leading-4 text-slate-500">{check.detail}</p>
      </div>
      <ChevronRight size={15} className="mt-2 shrink-0 text-slate-300" />
    </div>
  );
}

export default function CreditStrategy() {
  const [view, setView] = useState<View>('overview');
  const brand = getBrand();
  const s = strategySnapshot;

  const scenarioOption = useMemo(
    () => ({
      ...baseOption(),
      grid: { left: 16, right: 20, top: 26, bottom: 20, containLabel: true },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        valueFormatter: (value: number) => `${integer(value)} 元`,
      },
      xAxis: {
        ...baseOption().xAxis,
        type: 'category',
        data: strategyScenarios.map((item) => item.label),
        axisLabel: { color: '#64748b', fontSize: 11, interval: 0 },
      },
      yAxis: {
        ...baseOption().yAxis,
        min: 40000,
        max: 52000,
        axisLabel: { color: '#94a3b8', fontSize: 10, formatter: (value: number) => `${Math.round(value / 1000)}k` },
      },
      series: [
        {
          name: '户均额度',
          type: 'bar',
          barMaxWidth: 42,
          data: strategyScenarios.map((item) => ({
            value: item.averageLimit,
            itemStyle: {
              color:
                item.tone === 'target'
                  ? '#f59e0b'
                  : item.tone === 'current'
                    ? brand
                    : item.tone === 'whatIf'
                      ? '#70a1fb'
                      : '#cbd5e1',
              borderRadius: [5, 5, 0, 0],
            },
          })),
          label: { show: true, position: 'top', color: '#475569', fontSize: 10, formatter: (params: { value: number }) => `${(params.value / 10000).toFixed(2)}万` },
          markLine: {
            symbol: 'none',
            lineStyle: { color: '#f59e0b', type: 'dashed', width: 1.5 },
            label: { formatter: '目标 5.00 万', position: 'insideEndTop', color: '#b45309', fontSize: 10 },
            data: [{ yAxis: s.targetAverage }],
          },
        },
      ],
    }),
    [brand, s.targetAverage]
  );

  const coefficientOption = useMemo(
    () => ({
      ...baseOption(),
      tooltip: { trigger: 'item', formatter: '{b}<br/>{c} 人 · {d}%' },
      legend: { bottom: 2, left: 'center', itemWidth: 8, itemHeight: 8, textStyle: { color: '#64748b', fontSize: 10.5 } },
      series: [
        {
          name: '系数核验',
          type: 'pie',
          radius: ['47%', '70%'],
          center: ['50%', '45%'],
          avoidLabelOverlap: true,
          label: { show: false },
          labelLine: { show: false },
          itemStyle: { borderColor: '#fff', borderWidth: 3, borderRadius: 5 },
          data: coefficientDistribution.map((item) => ({ value: item.value, name: item.name, itemStyle: { color: item.color } })),
        },
      ],
      graphic: [
        { type: 'text', left: 'center', top: '34%', style: { text: '42.1%', fill: '#1e293b', fontSize: 24, fontWeight: 700, textAlign: 'center' } },
        { type: 'text', left: 'center', top: '48%', style: { text: '系数一致率', fill: '#94a3b8', fontSize: 10.5, textAlign: 'center' } },
      ],
    }),
    []
  );

  const rolloutOption = useMemo(
    () => ({
      ...baseOption(),
      grid: { left: 0, right: 0, top: 24, bottom: 34, containLabel: false },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (items: Array<{ seriesName: string; value: number }>) => items.map((item) => `${item.seriesName}：${item.value.toFixed(2)}%`).join('<br/>') },
      xAxis: { type: 'value', max: 100, show: false },
      yAxis: { type: 'category', data: ['8/12 业务日'], show: false },
      series: rolloutMix.map((item, index) => ({
        name: item.name,
        type: 'bar',
        stack: 'total',
        barWidth: 30,
        data: [item.pct],
        itemStyle: { color: item.name === '新策略' ? brand : item.color, borderRadius: index === 0 ? [5, 0, 0, 5] : index === rolloutMix.length - 1 ? [0, 5, 5, 0] : 0 },
        label: { show: item.pct > 5, position: 'inside', formatter: `${item.name} ${item.pct.toFixed(1)}%`, color: '#fff', fontSize: 11, fontWeight: 600 },
      })),
    }),
    [brand]
  );

  const scoreColumns: FeishuColumn<StrategyScoreRow>[] = [
    {
      key: 'score',
      title: '风险等级',
      sticky: true,
      width: 94,
      render: (row) => <span className="font-semibold text-slate-800">{row.score}</span>,
    },
    {
      key: 'planScope',
      title: '5万方案范围',
      width: 108,
      render: (row) => <StatusTag text={row.planScope} tone={row.planScope === '计划内' ? 'green' : 'red'} />,
    },
    { key: 'customers', title: '有效客户', align: 'right', render: (row) => integer(row.customers) },
    { key: 'raisedCustomers', title: '实际提额', align: 'right', render: (row) => integer(row.raisedCustomers) },
    {
      key: 'raiseRate',
      title: '提额覆盖率',
      align: 'right',
      render: (row) => <span className={row.raiseRate < 40 ? 'font-medium text-orange-600' : 'font-medium text-emerald-600'}>{percent(row.raiseRate)}</span>,
    },
    { key: 'beforeAverage', title: '提额前均额', align: 'right', render: (row) => `${integer(row.beforeAverage)} 元` },
    { key: 'afterAverage', title: '提额后均额', align: 'right', render: (row) => `${integer(row.afterAverage)} 元` },
    {
      key: 'delta',
      title: '均额变化',
      align: 'right',
      render: (row) => <span className="font-semibold text-blue-600">+{integer(row.delta)} 元</span>,
    },
  ];

  return (
    <div className="space-y-4 max-w-[1440px] mx-auto pb-2">
      <section className="relative overflow-hidden rounded-2xl border border-slate-200/90 bg-white/60 backdrop-blur-xl px-5 py-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
        <div className="absolute inset-y-0 left-0 w-1" style={{ background: `linear-gradient(180deg, ${brand}, #76a5ff)` }} />
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="pl-1">
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 px-2 py-1 text-[10.5px] font-semibold text-blue-600">
                <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
                上线后首日监控
              </span>
              <span className="text-[11px] text-slate-400">业务日 {s.businessDate} · 有效样本 {integer(s.validCustomers)} 人</span>
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <h2 className="text-[17px] font-semibold tracking-tight text-slate-800">提额策略 · 5 万目标达成诊断</h2>
              <span className="text-[11.5px] text-slate-400">新策略 defq-重构</span>
            </div>
            <p className="mt-1 text-[11.5px] text-slate-500">跑批窗口：{s.runWindow} · 快照表：{s.table} · 首日客群口径，非原方案全量测算底表</p>
          </div>
          <div className="flex items-center gap-2">
            <a
              href="/reports/credit-strategy-monitor-20260812.html"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[11.5px] font-medium text-slate-600 shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600"
              title="打开 HTML 分析报告"
            >
              <ExternalLink size={13} />
              HTML 报告
            </a>
            <div className="flex items-center rounded-lg bg-slate-100/80 p-1">
              {([
                ['overview', '效果总览'],
                ['validation', '策略核验'],
              ] as const).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setView(key)}
                  className={`rounded-md px-3 py-1.5 text-[11.5px] font-medium transition-all ${view === key ? 'bg-white text-slate-800 shadow-[0_1px_2px_rgba(15,23,42,0.12)]' : 'text-slate-500 hover:text-slate-700'}`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <SnapshotKpi label="新策略整体均额" value={integer(s.currentAverage)} unit="元" hint={`距 5 万目标差 ${integer(s.targetGap)} 元`} tone="blue" icon={Target} />
        <SnapshotKpi label="均额实际提升" value={`+${integer(s.averageIncrease)}`} unit="元" hint={`较提额前 +${percent(s.averageIncreaseRate)}`} tone="green" icon={TrendingUp} />
        <SnapshotKpi label="目标增量达成" value={percent(s.upliftTargetAttainment)} hint="实际增量 / 达标所需增量" tone="orange" icon={Gauge} />
        <SnapshotKpi label="实际提额覆盖" value={percent(s.raiseCoverage)} hint={`${integer(s.raisedCustomers)} / ${integer(s.validCustomers)} 人`} tone="blue" icon={UsersRound} />
        <SnapshotKpi label="系数表一致率" value={percent(s.coefficientMatchRate)} hint="仅统计 te_flag=1 提额客户" tone="red" icon={ClipboardCheck} />
        <SnapshotKpi label="公式回算一致率" value={percent(s.formulaMatchRate)} hint={`带帽回算 ${integer(s.formulaMatchCustomers)} 人一致`} tone="orange" icon={ShieldAlert} />
      </div>

      {view === 'overview' ? (
        <>
          <div className="grid grid-cols-1 xl:grid-cols-[1.18fr_0.82fr] gap-4">
            <ChartCard
              title="户均额度 · 目标差距路径"
              subtitle="同一批新策略有效样本；蓝色为实际跑批，浅蓝为系数/幅度敏感性，橙线为 5 万目标"
              extra={<StatusTag text={`目标尚差 ${integer(s.targetGap)} 元 / 户`} tone="orange" />}
            >
              <ReactECharts option={scenarioOption} style={{ height: 286 }} notMerge />
              <div className="mx-4 mb-3 grid grid-cols-1 sm:grid-cols-3 gap-2 rounded-lg bg-slate-50 px-3 py-2.5 text-[10.5px] text-slate-500">
                <div><span className="font-semibold text-slate-700">实际：</span>增量完成 {percent(s.upliftTargetAttainment)}，总缺口约 {s.targetGapTotal.toLocaleString('zh-CN', { maximumFractionDigits: 0 })} 万元。</div>
                <div><span className="font-semibold text-slate-700">系数表一致：</span>可缩小缺口至 {integer(1675)} 元 / 户。</div>
                <div><span className="font-semibold text-slate-700">方案 A 幅度：</span>按 A/B/C 同批次敏感性，仍差约 761 元 / 户。</div>
              </div>
            </ChartCard>

            <ChartCard title="系数落地核验" subtitle="实际提额客户 cash_remark1 与 315 格策略系数表逐格对照" extra={<StatusTag text="高优先级" tone="red" />}>
              <div className="relative">
                <ReactECharts option={coefficientOption} style={{ height: 230 }} notMerge />
                <div className="mx-4 mb-3 rounded-lg border border-rose-100 bg-rose-50/70 px-3 py-2.5 text-[11px] leading-5 text-rose-700">
                  <span className="font-semibold">净影响：</span>实际系数偏低客户集中于较高额度段；按同一提额客群无约束测算，较系数表少增约 {s.coefficientNetGap.toLocaleString('zh-CN', { maximumFractionDigits: 0 })} 万元。
                </div>
              </div>
            </ChartCard>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-[0.94fr_1.06fr] gap-4">
            <ChartCard title="上线分流覆盖" subtitle="业务日全量跑批 41,900 笔；新旧策略并存会稀释混合口径" extra={<StatusTag text="未全量切换" tone="orange" />}>
              <ReactECharts option={rolloutOption} style={{ height: 128 }} notMerge />
              <div className="mx-4 mb-3 flex items-start gap-2 rounded-lg bg-orange-50 px-3 py-2.5 text-[11px] leading-5 text-orange-700">
                <FileWarning size={14} className="mt-0.5 shrink-0" />
                <span>旧策略仍承接 {s.legacyShare.toFixed(1)}% 流量；其中 {integer(s.legacyDownCustomers)} 人发生降额，合计减少约 {integer(s.legacyDownAmount)} 万元。全量混跑有效样本均额为 {integer(s.overallAverage)} 元。</span>
              </div>
            </ChartCard>

            <ChartCard title="平均额度未达标 · 直接原因" subtitle="以当前新策略有效样本为口径，按可行动性排序">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 px-3 pb-3 pt-2">
                {rootCauses.map((cause) => {
                  const style = toneStyle[cause.tone];
                  return (
                    <div key={cause.order} className="rounded-lg border border-slate-100 bg-slate-50/70 p-3">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-[10.5px] font-semibold" style={{ color: style.line }}>{cause.order}</span>
                        <span className="text-[12px] font-semibold text-slate-800">{cause.title}</span>
                      </div>
                      <div className="mt-2 text-[15px] font-semibold tracking-tight" style={{ color: style.line }}>{cause.metric}</div>
                      <p className="mt-1 text-[10.5px] leading-4 text-slate-500">{cause.detail}</p>
                    </div>
                  );
                })}
              </div>
            </ChartCard>
          </div>

          <ChartCard
            title="风险等级 × 提额覆盖明细"
            subtitle="5 万方案要求仅 A/B/C 客群提额；D/E 实际提额需与审批策略确认是否为例外规则"
            extra={<StatusTag text="D/E 实提 3,155 人" tone="red" />}
          >
            <FeishuTable columns={scoreColumns} data={strategyScoreRows} rowKey={(row) => row.score} maxHeight={330} />
          </ChartCard>
        </>
      ) : (
        <>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <ChartCard title="策略公式核验" subtitle="以字段字典口径回算：min(向上取整后的前额度×(1+提幅)，客户额度盖帽，前额度+单次提幅盖帽)">
              <div className="px-4 pb-4 pt-3">
                <div className="flex items-end justify-between gap-4">
                  <div>
                    <div className="text-[28px] leading-7 font-semibold tracking-tight text-slate-800">{percent(s.formulaMatchRate, 2)}</div>
                    <div className="mt-1 text-[11px] text-slate-500">{integer(s.formulaMatchCustomers)} / {integer(s.formulaEligibleCustomers)} 名有完整字段的提额客户回算一致</div>
                  </div>
                  <StatusTag text="需复核例外规则" tone="orange" />
                </div>
                <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full" style={{ width: `${s.formulaMatchRate}%`, background: `linear-gradient(90deg, ${brand}, #7db1ff)` }} />
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2">
                  <div className="rounded-lg bg-orange-50 px-3 py-2.5"><div className="text-[10.5px] text-orange-600">高于客户额度盖帽</div><div className="mt-1 text-[18px] font-semibold text-orange-700">{integer(s.aboveTotalCapCustomers)} 人</div></div>
                  <div className="rounded-lg bg-rose-50 px-3 py-2.5"><div className="text-[10.5px] text-rose-600">高于单次提幅盖帽</div><div className="mt-1 text-[18px] font-semibold text-rose-700">{integer(s.aboveIncreaseCapCustomers)} 人</div></div>
                </div>
              </div>
            </ChartCard>

            <ChartCard title="提额闸门覆盖" subtitle="te_flag=0 且配置为正并不等于实际提额；需下钻资格、封顶与数据校验原因">
              <div className="px-4 pb-4 pt-3">
                <div className="flex items-center gap-4">
                  <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-blue-50 text-blue-600"><Layers3 size={26} /></div>
                  <div>
                    <div className="text-[25px] leading-7 font-semibold tracking-tight text-slate-800">{integer(s.positiveConfigNonRaise)} 人</div>
                    <div className="mt-1 text-[11px] text-slate-500">有正向配置系数但未实际提额，占 te_flag=0 客户 {percent((s.positiveConfigNonRaise / s.nonRaisedCustomers) * 100)}</div>
                  </div>
                </div>
                <div className="mt-4 rounded-lg border border-blue-100 bg-blue-50/60 px-3 py-2.5 text-[11px] leading-5 text-blue-700">
                  建议按 <span className="font-semibold">资格未满足 / 已触额度盖帽 / 单次提幅盖帽 / 输入字段异常 / 白名单例外</span> 五类补充落表原因码，再监控各类的金额贡献。
                </div>
              </div>
            </ChartCard>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-[0.9fr_1.1fr] gap-4">
            <ChartCard title="上线与数据质量提醒" subtitle="从策略标签与跑批时间交叉核验得到的实施风险">
              <div className="px-4 pb-4 pt-2">
                <div className="flex items-start gap-3 py-3 border-b border-slate-100">
                  <span className="mt-0.5 w-7 h-7 rounded-lg bg-orange-50 text-orange-600 flex items-center justify-center"><Database size={14} /></span>
                  <div><div className="text-[12.5px] font-semibold text-slate-800">新策略标签早于口径日期出现</div><p className="mt-1 text-[11px] leading-4 text-slate-500">str_type=new 最早跑批时间为 2026-08-11 11:30:32；与“8/12 上线”需确认时区、灰度或业务日期口径。</p></div>
                </div>
                <div className="flex items-start gap-3 py-3 border-b border-slate-100">
                  <span className="mt-0.5 w-7 h-7 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center"><ShieldAlert size={14} /></span>
                  <div><div className="text-[12.5px] font-semibold text-slate-800">5 万方案范围存在 D/E 提额</div><p className="mt-1 text-[11px] leading-4 text-slate-500">若采用方案文件“仅 A/B/C”限制，D/E 实际提额 3,155 人属于需确认的策略例外。</p></div>
                </div>
                <div className="flex items-start gap-3 py-3">
                  <span className="mt-0.5 w-7 h-7 rounded-lg bg-slate-100 text-slate-600 flex items-center justify-center"><FileWarning size={14} /></span>
                  <div><div className="text-[12.5px] font-semibold text-slate-800">5 笔新策略记录未进入金额口径</div><p className="mt-1 text-[11px] leading-4 text-slate-500">因额度字段无效被排除；需作为数据质量监控项持续观察。</p></div>
                </div>
              </div>
            </ChartCard>

            <ChartCard title="策略核验清单" subtitle="先修正高影响配置偏差，再补足资格/例外原因码，最后完成流量切换">
              <div className="px-4 pb-3 pt-1">{strategyChecks.map((check) => <CheckRow key={check.name} check={check} />)}</div>
            </ChartCard>
          </div>
        </>
      )}
    </div>
  );
}
