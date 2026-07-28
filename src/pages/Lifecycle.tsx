import ReactECharts from 'echarts-for-react';
import ChartCard from '@/components/ChartCard';
import FeishuTable, { heatStyle, type FeishuColumn } from '@/components/FeishuTable';
import { baseOption } from '@/lib/chartTheme';
import {
  getLifecycleTrend,
  getRetentionCurve,
  lifecycleFunnel,
  lifecycleStageTable,
  type LifecycleStageRow,
} from '@/data/mockData';

export default function Lifecycle() {
  const trend = getLifecycleTrend();
  const retention = getRetentionCurve();

  const funnelOption = {
    color: ['#4e83fd', '#5f94fe', '#36cfc9', '#4fd0a5', '#37c26b', '#ffb020', '#ff8f4d', '#f76965'],
    tooltip: { trigger: 'item', formatter: (p: { name: string; value: number }) => `${p.name}: ${p.value.toLocaleString()} 人` },
    series: [
      {
        type: 'funnel',
        left: '6%',
        width: '56%',
        top: 10,
        bottom: 10,
        minSize: '18%',
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
        data: lifecycleFunnel.map((s) => ({ name: s.stage, value: s.value })),
      },
    ],
  };

  const convBarOption = {
    ...baseOption(),
    grid: { left: 12, right: 40, top: 20, bottom: 8, containLabel: true },
    xAxis: { ...baseOption().xAxis, type: 'value', axisLabel: { formatter: '{value}%', color: '#8f959e', fontSize: 11 }, splitLine: { lineStyle: { color: '#f0f1f3' } } },
    yAxis: {
      type: 'category',
      inverse: true,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#1f2329', fontSize: 11.5 },
      data: lifecycleFunnel.filter((s) => s.conv !== null).map((s) => s.stage),
    },
    series: [
      {
        type: 'bar',
        barWidth: 14,
        itemStyle: {
          borderRadius: [0, 7, 7, 0],
          color: (p: { value: number }) =>
            p.value >= 75 ? '#37c26b' : p.value >= 50 ? '#4e83fd' : '#ffb020',
        },
        label: { show: true, position: 'right', fontSize: 11, color: '#646a73', formatter: '{c}%' },
        data: lifecycleFunnel.filter((s) => s.conv !== null).map((s) => s.conv),
      },
    ],
  };

  const trendOption = {
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: trend.map((d) => d.date) },
    yAxis: { ...baseOption().yAxis, axisLabel: { formatter: '{value}%', color: '#8f959e', fontSize: 11 } },
    series: [
      {
        name: '新户放款占比',
        type: 'line',
        smooth: true,
        symbol: 'none',
        areaStyle: { opacity: 0.1 },
        data: trend.map((d) => d.新户放款占比),
      },
      {
        name: '复借占比',
        type: 'line',
        smooth: true,
        symbol: 'none',
        areaStyle: { opacity: 0.1 },
        data: trend.map((d) => d.复借占比),
      },
      {
        name: '结清流失率',
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { type: 'dashed', width: 2 },
        data: trend.map((d) => d.结清流失率),
      },
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
      key: 'ratio',
      title: '占比',
      align: 'right',
      render: (r) => (
        <div className="flex items-center justify-end gap-2">
          <div className="w-16 h-1.5 rounded-full bg-slate-100 overflow-hidden">
            <div className="h-full rounded-full bg-blue-500" style={{ width: `${r.ratio}%` }} />
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
    <div className="space-y-4 max-w-[1440px] mx-auto">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ChartCard title="申请-放款-复借 转化漏斗" subtitle="当日口径 · 人">
          <ReactECharts option={funnelOption} style={{ height: 320 }} notMerge />
        </ChartCard>
        <ChartCard title="环节转化率" subtitle="相对上一环节 · 绿色≥75% / 蓝色≥50% / 橙色<50%">
          <ReactECharts option={convBarOption} style={{ height: 320 }} notMerge />
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ChartCard title="新旧户结构与流失趋势" subtitle="近12个月放款结构 (%)">
          <ReactECharts option={trendOption} style={{ height: 270 }} notMerge />
        </ChartCard>
        <ChartCard title="放款后留存曲线" subtitle="放款后第N月仍有在贷/复借行为的客户占比">
          <ReactECharts option={retentionOption} style={{ height: 270 }} notMerge />
        </ChartCard>
      </div>

      <ChartCard title="生命周期阶段明细" subtitle="客户分层 × 风险与价值指标">
        <FeishuTable columns={stageCols} data={lifecycleStageTable} rowKey={(r) => r.stage} />
      </ChartCard>
    </div>
  );
}
