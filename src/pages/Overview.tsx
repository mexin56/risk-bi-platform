import ReactECharts from 'echarts-for-react';
import KpiCard from '@/components/KpiCard';
import ChartCard from '@/components/ChartCard';
import FeishuTable, { heatStyle, type FeishuColumn } from '@/components/FeishuTable';
import { baseOption } from '@/lib/chartTheme';
import {
  channelPie,
  getLoanTrend,
  getOverdueTrend,
  overviewKpis,
  productTable,
  type ProductRow,
} from '@/data/mockData';

export default function Overview() {
  const loanTrend = getLoanTrend();
  const overdueTrend = getOverdueTrend();

  const loanOption = {
    ...baseOption(),
    tooltip: { ...baseOption().tooltip, trigger: 'axis' },
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
        lineStyle: { width: 2 },
        areaStyle: { opacity: 0.08 },
        data: loanTrend.map((d) => d.申请量),
      },
      {
        name: '放款金额',
        type: 'bar',
        barMaxWidth: 14,
        itemStyle: { borderRadius: [3, 3, 0, 0], color: '#4e83fd' },
        data: loanTrend.map((d) => d.放款金额),
      },
    ],
  };

  const overdueOption = {
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: overdueTrend.map((d) => d.date) },
    yAxis: { ...baseOption().yAxis, axisLabel: { color: '#8f959e', fontSize: 11, formatter: '{value}%' } },
    series: (['DPD1+', 'M1+', 'M3+'] as const).map((k) => ({
      name: k,
      type: 'line',
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2 },
      data: overdueTrend.map((d) => d[k] as number),
    })),
  };

  const pieOption = {
    color: ['#4e83fd', '#36cfc9', '#ffb020', '#f76965', '#7f6bf2', '#bcc0c7'],
    tooltip: { trigger: 'item', formatter: '{b}: {c}% ({d}%)' },
    legend: { orient: 'vertical', right: 4, top: 'middle', icon: 'circle', itemWidth: 8, textStyle: { fontSize: 11, color: '#646a73' } },
    series: [
      {
        type: 'pie',
        radius: ['52%', '76%'],
        center: ['34%', '52%'],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 5, borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        data: channelPie,
      },
    ],
    graphic: [
      {
        type: 'text',
        left: '27.5%',
        top: '46%',
        style: { text: '渠道放款', fontSize: 12, fill: '#8f959e', textAlign: 'center' },
      },
      {
        type: 'text',
        left: '29%',
        top: '54%',
        style: { text: '占比', fontSize: 12, fill: '#8f959e', textAlign: 'center' },
      },
    ],
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
      {/* KPI 卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3">
        {overviewKpis.map((k) => (
          <KpiCard key={k.label} kpi={k} />
        ))}
      </div>

      {/* 趋势区 */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <ChartCard title="放款与申请趋势" subtitle="近30天 · 万元 / 件" className="xl:col-span-2">
          <ReactECharts option={loanOption} style={{ height: 280 }} notMerge />
        </ChartCard>
        <ChartCard title="渠道放款结构" subtitle="当日放款金额占比">
          <ReactECharts option={pieOption} style={{ height: 280 }} notMerge />
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <ChartCard title="资产质量趋势" subtitle="近30天逾期率走势 (%)" className="xl:col-span-2">
          <ReactECharts option={overdueOption} style={{ height: 260 }} notMerge />
        </ChartCard>

        {/* 风险提示卡片 */}
        <div className="bg-white rounded-xl border border-slate-200/80 shadow-[0_1px_2px_rgba(15,23,42,0.04)] p-5">
          <div className="text-[14px] font-semibold text-slate-800 mb-3">风险信号</div>
          <div className="space-y-3">
            {[
              { level: '预警', color: 'rose', text: '小微经营贷 M1+ 逾期率 4.88%，连续 5 日高于阈值 4.5%', time: '今日 08:30' },
              { level: '关注', color: 'orange', text: '信息流投放渠道 FPD7 升至 1.42%，环比 +0.18pct', time: '今日 08:30' },
              { level: '关注', color: 'orange', text: '反欺诈分 v4.0 灰度期 PSI 0.121，触及关注线', time: '昨日 20:00' },
              { level: '恢复', color: 'emerald', text: '信用贷-标准 M3+ 不良率回落至 1.38%，低于阈值', time: '昨日 08:30' },
            ].map((a, i) => (
              <div key={i} className="flex gap-2.5 items-start">
                <span
                  className={`shrink-0 mt-0.5 px-1.5 py-0.5 rounded text-[10.5px] border bg-${a.color}-50 text-${a.color}-600 border-${a.color}-200`}
                  style={{
                    backgroundColor: a.color === 'rose' ? '#fff1f0' : a.color === 'orange' ? '#fff7e6' : '#f0fdf4',
                    color: a.color === 'rose' ? '#e11d48' : a.color === 'orange' ? '#d97706' : '#059669',
                    borderColor: a.color === 'rose' ? '#fecdd3' : a.color === 'orange' ? '#fed7aa' : '#a7f3d0',
                  }}
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

      {/* 产品资产质量表 */}
      <ChartCard title="产品线资产质量明细" subtitle="单元格颜色越深风险越高 · 口径 T-1">
        <FeishuTable columns={productCols} data={productTable} rowKey={(r) => r.product} />
      </ChartCard>
    </div>
  );
}
