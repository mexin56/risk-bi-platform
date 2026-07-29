import ReactECharts from 'echarts-for-react';
import { Megaphone } from 'lucide-react';
import KpiCard from '@/components/KpiCard';
import ChartCard from '@/components/ChartCard';
import FeishuTable, { heatStyle, type FeishuColumn } from '@/components/FeishuTable';
import { areaGradient, baseOption } from '@/lib/chartTheme';
import { getBrand } from '@/lib/theme';
import {
  alertTicker,
  aprDist,
  assetFiveClass,
  channelPie,
  getFundingTrend,
  getLoanTrend,
  getOverdueTrend,
  overviewKpis,
  productTable,
  riskHealth,
  type ProductRow,
} from '@/data/mockData';

const TICKER_TONE: Record<string, string> = {
  预警: 'bg-rose-100 text-rose-600',
  关注: 'bg-orange-100 text-orange-600',
  恢复: 'bg-emerald-100 text-emerald-600',
  提示: 'bg-blue-100 text-blue-600',
};

function AlertTickerBar() {
  const items = [...alertTicker, ...alertTicker]; // 复制一遍实现无缝滚动
  return (
    <div className="flex items-center gap-3 bg-white rounded-xl border border-slate-200/80 px-4 py-2.5 shadow-[0_1px_2px_rgba(15,23,42,0.04)] overflow-hidden">
      <div className="shrink-0 flex items-center gap-1.5 text-[12px] font-semibold text-slate-700 pr-3 border-r border-slate-100">
        <span className="relative flex w-2 h-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-60" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-rose-500" />
        </span>
        <Megaphone size={14} className="text-rose-500" />
        风险信号
      </div>
      <div className="flex-1 overflow-hidden [mask-image:linear-gradient(90deg,transparent,#000_3%,#000_97%,transparent)]">
        <div className="ticker-track flex gap-10 whitespace-nowrap w-max">
          {items.map((a, i) => (
            <span key={i} className="inline-flex items-center gap-2 text-[12px] text-slate-600">
              <span className={`px-1.5 py-0.5 rounded text-[10.5px] font-medium ${TICKER_TONE[a.level]}`}>
                {a.level}
              </span>
              {a.text}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function RiskHealthGauge() {
  const gaugeOption = {
    series: [
      {
        type: 'gauge',
        startAngle: 210,
        endAngle: -30,
        min: 0,
        max: 100,
        radius: '100%',
        center: ['50%', '58%'],
        progress: {
          show: true,
          width: 12,
          roundCap: true,
          itemStyle: {
            color: {
              type: 'linear',
              x: 0, y: 0, x2: 1, y2: 0,
              colorStops: [
                { offset: 0, color: '#36cfc9' },
                { offset: 1, color: getBrand() },
              ],
            },
          },
        },
        axisLine: { lineStyle: { width: 12, color: [[1, '#eef1f6']] } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        pointer: { show: false },
        anchor: { show: false },
        title: { show: true, offsetCenter: [0, '32%'], fontSize: 11, color: '#8f959e' },
        detail: {
          valueAnimation: true,
          offsetCenter: [0, '-2%'],
          fontSize: 34,
          fontWeight: 600,
          color: '#1f2329',
          formatter: '{value}',
        },
        data: [{ value: riskHealth.score, name: '综合风险健康度' }],
      },
    ],
  };

  return (
    <ChartCard title="风险健康度" subtitle="四维加权评估 · 日终更新" accent="#36cfc9">
      <div className="relative">
        <div className="absolute left-1/2 top-[42%] -translate-x-1/2 -translate-y-1/2 w-24 h-24 rounded-full bg-blue-100/50 pulse-ring pointer-events-none" />
        <ReactECharts option={gaugeOption} style={{ height: 150 }} notMerge />
      </div>
      <div className="px-5 pb-3 grid grid-cols-2 gap-x-4 gap-y-2.5">
        {riskHealth.dims.map((d) => (
          <div key={d.name}>
            <div className="flex justify-between text-[11px] mb-1">
              <span className="text-slate-500">{d.name}</span>
              <span className="font-semibold text-slate-700 tabular-nums">{d.score}</span>
            </div>
            <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{
                  width: `${d.score}%`,
                  background: d.score >= 85 ? 'linear-gradient(90deg,#36cfc9,#37c26b)' : 'linear-gradient(90deg,#4e83fd,#7f6bf2)',
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </ChartCard>
  );
}

// 资产五级分类堆叠条
function FiveClassBar() {
  return (
    <ChartCard title="资产五级分类结构" subtitle="在贷余额口径 · 监管五级分类" accent="#37c26b">
      <div className="px-5 py-6">
        <div className="flex h-9 rounded-lg overflow-hidden border border-white shadow-sm">
          {assetFiveClass.map((c) => (
            <div
              key={c.name}
              className="relative flex items-center justify-center transition-all hover:opacity-85"
              style={{ width: `${c.pct}%`, backgroundColor: c.color, minWidth: c.pct < 1 ? 6 : undefined }}
              title={`${c.name}: ${c.pct}%`}
            >
              {c.pct >= 2 && (
                <span className="text-[11px] font-semibold text-white tabular-nums">{c.pct}%</span>
              )}
            </div>
          ))}
        </div>
        <div className="mt-3.5 flex flex-wrap gap-x-5 gap-y-1.5">
          {assetFiveClass.map((c) => (
            <span key={c.name} className="inline-flex items-center gap-1.5 text-[11.5px] text-slate-600">
              <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: c.color }} />
              {c.name}
              <span className="text-slate-400 tabular-nums">{c.pct}%</span>
            </span>
          ))}
        </div>
        <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-[11.5px]">
          <span className="text-slate-400">不良率（次级+可疑+损失）</span>
          <span className="font-semibold text-rose-500 tabular-nums">3.2%</span>
        </div>
        <div className="mt-1.5 flex items-center justify-between text-[11.5px]">
          <span className="text-slate-400">拨备覆盖率</span>
          <span className="font-semibold text-slate-700 tabular-nums">218%</span>
        </div>
      </div>
    </ChartCard>
  );
}

export default function Overview() {
  const loanTrend = getLoanTrend();
  const overdueTrend = getOverdueTrend();

  const loanOption = {
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: loanTrend.map((d) => d.date) },
    yAxis: [
      { ...baseOption().yAxis, name: '放款(万元)', nameTextStyle: { color: '#8f959e', fontSize: 10 } },
      { ...baseOption().yAxis, name: '申请(件)', splitLine: { show: false }, nameTextStyle: { color: '#8f959e', fontSize: 10 } },
    ],
    series: [
      {
        name: '申请量',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2, color: '#36cfc9' },
        areaStyle: { color: areaGradient('#36cfc9', 0.14) },
        data: loanTrend.map((d) => d.申请量),
      },
      {
        name: '放款金额',
        type: 'bar',
        barMaxWidth: 14,
        itemStyle: {
          borderRadius: [3, 3, 0, 0],
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: getBrand() },
              { offset: 1, color: getBrand() },
            ],
          },
          opacity: 0.9,
        },
        emphasis: { itemStyle: { opacity: 1 } },
        data: loanTrend.map((d) => d.放款金额),
      },
    ],
  };

  const overdueColors = ['#4e83fd', '#36cfc9', '#ffb020'];
  const overdueOption = {
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: overdueTrend.map((d) => d.date), boundaryGap: false },
    yAxis: { ...baseOption().yAxis, axisLabel: { color: '#8f959e', fontSize: 11, formatter: '{value}%' } },
    series: (['DPD1+', 'M1+', 'M3+'] as const).map((k, i) => ({
      name: k,
      type: 'line',
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2.2, color: overdueColors[i] },
      areaStyle: i === 0 ? { color: areaGradient(overdueColors[i], 0.1) } : undefined,
      data: overdueTrend.map((d) => d[k] as number),
    })),
  };

  const pieOption = {
    color: [getBrand(), '#36cfc9', '#ffb020', '#f76965', '#7f6bf2', '#bcc0c7'],
    tooltip: { trigger: 'item', formatter: '{b}: {c}% ({d}%)' },
    legend: { orient: 'vertical', right: 4, top: 'middle', icon: 'circle', itemWidth: 8, textStyle: { fontSize: 11, color: '#646a73' } },
    series: [
      {
        type: 'pie',
        radius: ['54%', '78%'],
        center: ['34%', '52%'],
        itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        emphasis: { scale: true, scaleSize: 6 },
        data: channelPie,
      },
    ],
    graphic: [
      { type: 'text', left: '28.5%', top: '44%', style: { text: '渠道放款', fontSize: 11, fill: '#8f959e', textAlign: 'center' } },
      { type: 'text', left: '30%', top: '53%', style: { text: '结构占比', fontSize: 11, fill: '#8f959e', textAlign: 'center' } },
    ],
  };

  const aprOption = {
    ...baseOption(),
    grid: { left: 12, right: 16, top: 30, bottom: 8, containLabel: true },
    xAxis: { ...baseOption().xAxis, data: aprDist.map((d) => d.range) },
    yAxis: { ...baseOption().yAxis, axisLabel: { formatter: '{value}%', color: '#8f959e', fontSize: 11 } },
    series: [
      {
        type: 'bar',
        barMaxWidth: 34,
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: (p: { dataIndex: number }) => (p.dataIndex === 3 ? '#f76965' : getBrand()),
        },
        label: { show: true, position: 'top', fontSize: 10.5, color: '#8f959e', formatter: '{c}%' },
        markLine: {
          symbol: 'none',
          lineStyle: { color: '#f76965', type: 'dashed' },
          label: { formatter: '24%红线', fontSize: 10, color: '#f76965' },
          data: [{ xAxis: 2.5 }],
        },
        data: aprDist.map((d) => d.pct),
      },
    ],
  };

  const fundingTrend = getFundingTrend();
  const fundingOption = {
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: fundingTrend.map((d) => d.date), boundaryGap: false },
    yAxis: { ...baseOption().yAxis, axisLabel: { formatter: '{value}%', color: '#8f959e', fontSize: 11 } },
    series: (['平均IRR', '资金成本', '净息差NIM'] as const).map((k, i) => ({
      name: k,
      type: 'line',
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2, type: k === '资金成本' ? 'dashed' : 'solid' },
      areaStyle: i === 2 ? { color: areaGradient('#36cfc9', 0.1) } : undefined,
      data: fundingTrend.map((d) => d[k] as number),
    })),
  };

  const productCols: FeishuColumn<ProductRow>[] = [
    { key: 'product', title: '产品线', sticky: true, width: 130, render: (r) => <span className="font-medium text-slate-800">{r.product}</span> },
    { key: 'balance', title: '在贷余额', align: 'right' },
    { key: 'dailyLoan', title: '当日放款', align: 'right' },
    { key: 'passRate', title: '审批通过率', align: 'right', render: (r) => `${r.passRate}%`, cellStyle: (r) => heatStyle(r.passRate, 20, 65, 'blue') },
    { key: 'fpd7', title: 'FPD7 首逾', align: 'right', render: (r) => `${r.fpd7}%`, cellStyle: (r) => heatStyle(r.fpd7, 0.3, 1.8, 'red') },
    { key: 'm1', title: 'M1+ 逾期率', align: 'right', render: (r) => `${r.m1}%`, cellStyle: (r) => heatStyle(r.m1, 1.5, 5.2, 'red') },
    { key: 'm3', title: 'M3+ 不良率', align: 'right', render: (r) => `${r.m3}%`, cellStyle: (r) => heatStyle(r.m3, 0.5, 2.6, 'red') },
    { key: 'vintageM6', title: 'MOB6 Vintage(M1+)', align: 'right', render: (r) => `${r.vintageM6}%`, cellStyle: (r) => heatStyle(r.vintageM6, 2, 7.5, 'red') },
  ];

  return (
    <div className="space-y-4 max-w-[1440px] mx-auto">
      <AlertTickerBar />

      {/* KPI 卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3">
        {overviewKpis.map((k, i) => (
          <KpiCard key={k.label} kpi={k} index={i} />
        ))}
      </div>

      {/* 趋势区 */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <ChartCard title="放款与申请趋势" subtitle="近30天 · 万元 / 件" className="xl:col-span-2">
          <ReactECharts option={loanOption} style={{ height: 280 }} notMerge />
        </ChartCard>
        <ChartCard title="渠道放款结构" subtitle="当日放款金额占比" accent="#7f6bf2" delay={0.08}>
          <ReactECharts option={pieOption} style={{ height: 280 }} notMerge />
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <ChartCard title="资产质量趋势" subtitle="近30天逾期率走势 (%)" accent="#ffb020" className="xl:col-span-2">
          <ReactECharts option={overdueOption} style={{ height: 265 }} notMerge />
        </ChartCard>
        <RiskHealthGauge />
      </div>

      {/* 定价与资金 */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <ChartCard title="APR 定价分布" subtitle="放款笔数口径 · 红色为超24%利率红线部分" accent="#f76965">
          <ReactECharts option={aprOption} style={{ height: 235 }} notMerge />
        </ChartCard>
        <ChartCard title="收益与资金成本" subtitle="近12个月 · IRR / 资金成本 / 净息差 (%)" accent="#36cfc9">
          <ReactECharts option={fundingOption} style={{ height: 235 }} notMerge />
        </ChartCard>
        <FiveClassBar />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {/* 产品资产质量表 */}
        <ChartCard title="产品线资产质量明细" subtitle="单元格颜色越深风险越高 · 口径 T-1" accent="#f76965" className="xl:col-span-2">
          <FeishuTable columns={productCols} data={productTable} rowKey={(r) => r.product} />
        </ChartCard>

        {/* 风险信号列表 */}
        <div className="bg-white rounded-xl border border-slate-200/80 shadow-[0_1px_2px_rgba(15,23,42,0.04)] p-5">
          <div className="flex items-center gap-2.5 mb-4">
            <div className="w-[3px] h-[15px] rounded-full bg-gradient-to-b from-rose-400 to-rose-400/30" />
            <div className="text-[14px] font-semibold text-slate-800">处置待办</div>
            <span className="ml-auto text-[10.5px] text-slate-400">按严重度排序</span>
          </div>
          <div className="space-y-3">
            {[
              { level: '预警', bg: '#fff1f0', fg: '#e11d48', bd: '#fecdd3', text: '小微经营贷 M1+ 逾期率 4.88%，连续 5 日高于阈值 4.5%', time: '今日 08:30' },
              { level: '关注', bg: '#fff7e6', fg: '#d97706', bd: '#fed7aa', text: '信息流投放渠道 FPD7 升至 1.42%，环比 +0.18pct', time: '今日 08:30' },
              { level: '关注', bg: '#fff7e6', fg: '#d97706', bd: '#fed7aa', text: '反欺诈分 v4.0 灰度期 PSI 0.121，触及关注线', time: '昨日 20:00' },
              { level: '恢复', bg: '#f0fdf4', fg: '#059669', bd: '#a7f3d0', text: '信用贷-标准 M3+ 不良率回落至 1.38%，低于阈值', time: '昨日 08:30' },
            ].map((a, i) => (
              <div key={i} className="flex gap-2.5 items-start p-2.5 rounded-lg hover:bg-slate-50 transition-colors cursor-pointer">
                <span
                  className="shrink-0 mt-0.5 px-1.5 py-0.5 rounded text-[10.5px] font-medium border"
                  style={{ backgroundColor: a.bg, color: a.fg, borderColor: a.bd }}
                >
                  {a.level}
                </span>
                <div className="min-w-0">
                  <div className="text-[12px] text-slate-700 leading-5">{a.text}</div>
                  <div className="text-[10.5px] text-slate-400 mt-0.5">{a.time}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
