import ReactECharts from 'echarts-for-react';
import ChartCard from '@/components/ChartCard';
import FeishuTable, { heatStyle, StatusTag, type FeishuColumn } from '@/components/FeishuTable';
import { areaGradient, baseOption } from '@/lib/chartTheme';
import { getBrand } from '@/lib/theme';
import { channelQuality, getChannelTrend, type ChannelRow } from '@/data/mockData';

const TYPE_TONE: Record<string, 'green' | 'blue' | 'orange' | 'gray' | 'red'> = {
  自营: 'green',
  信息流: 'blue',
  API导流: 'orange',
  应用市场: 'gray',
  地推: 'red',
};

export default function Channel() {
  const trend = getChannelTrend();

  // 通过率-首逾 四象限散点（优质渠道=高通过+低首逾 → 右下象限）
  const avgPass = channelQuality.reduce((s, c) => s + c.passRate, 0) / channelQuality.length;
  const avgFpd = channelQuality.reduce((s, c) => s + c.fpd7, 0) / channelQuality.length;
  const scatterOption = {
    ...baseOption(),
    grid: { left: 12, right: 24, top: 30, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'item',
      formatter: (p: { data: { value: number[]; name: string } }) =>
        `${p.data.name}<br/>通过率: ${p.data.value[0]}%<br/>FPD7: ${p.data.value[1]}%<br/>日进件: ${p.data.value[2].toLocaleString()}件`,
    },
    xAxis: {
      ...baseOption().xAxis,
      type: 'value',
      name: '通过率 %',
      nameTextStyle: { color: '#8f959e', fontSize: 10 },
      min: 18,
      max: 44,
      axisLabel: { formatter: '{value}%', color: '#8f959e', fontSize: 11 },
    },
    yAxis: {
      ...baseOption().yAxis,
      name: 'FPD7 首逾 %',
      inverse: true, // 越低越好 → 越靠下越优
      nameTextStyle: { color: '#8f959e', fontSize: 10 },
      min: 0.5,
      max: 2.6,
      axisLabel: { formatter: '{value}%', color: '#8f959e', fontSize: 11 },
    },
    series: [
      {
        type: 'scatter',
        symbolSize: (val: number[]) => Math.sqrt(val[2]) / 2.4,
        itemStyle: { color: getBrand(), opacity: 0.75, borderColor: '#fff', borderWidth: 1.5 },
        label: { show: true, position: 'top', fontSize: 10, color: '#646a73', formatter: (p: { data: { name: string } }) => p.data.name },
        markLine: {
          symbol: 'none',
          silent: true,
          lineStyle: { color: '#c0c4cc', type: 'dashed' },
          label: { show: false },
          data: [{ xAxis: avgPass }, { yAxis: avgFpd }],
        },
        markArea: {
          silent: true,
          itemStyle: { color: 'rgba(55,194,107,0.06)' },
          label: { show: true, position: 'insideBottomRight', color: '#37c26b', fontSize: 10.5, formatter: '优质区' },
          data: [[{ xAxis: avgPass, yAxis: 2.6 }, { xAxis: 44, yAxis: avgFpd }]],
        },
        data: channelQuality.map((c) => ({ name: c.channel, value: [c.passRate, c.fpd7, c.dailyCnt] })),
      },
    ],
  };

  const trendOption = {
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: trend.map((d) => d.date), boundaryGap: false },
    yAxis: { ...baseOption().yAxis },
    series: (['自营', '信息流', 'API导流'] as const).map((k, i) => ({
      name: k,
      type: 'line',
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2 },
      areaStyle: i === 0 ? { color: areaGradient(getBrand(), 0.1) } : undefined,
      data: trend.map((d) => d[k] as number),
    })),
  };

  const tableCols: FeishuColumn<ChannelRow>[] = [
    { key: 'channel', title: '渠道', sticky: true, width: 132, render: (r) => <span className="font-medium text-slate-800">{r.channel}</span> },
    { key: 'type', title: '类型', width: 84, render: (r) => <StatusTag text={r.type} tone={TYPE_TONE[r.type]} /> },
    { key: 'dailyCnt', title: '日进件', align: 'right', render: (r) => r.dailyCnt.toLocaleString() },
    { key: 'passRate', title: '通过率', align: 'right', render: (r) => `${r.passRate}%`, cellStyle: (r) => heatStyle(r.passRate, 20, 42, 'blue') },
    { key: 'fpd7', title: 'FPD7', align: 'right', render: (r) => `${r.fpd7}%`, cellStyle: (r) => heatStyle(r.fpd7, 0.7, 2.5, 'red') },
    { key: 'm1', title: 'M1+', align: 'right', render: (r) => `${r.m1}%`, cellStyle: (r) => heatStyle(r.m1, 2.5, 7, 'red') },
    { key: 'cac', title: '件均成本', align: 'right', render: (r) => `¥${r.cac}`, cellStyle: (r) => heatStyle(r.cac, 0, 220, 'red') },
    {
      key: 'roi', title: 'ROI', align: 'right',
      render: (r) => `${r.roi}%`,
      cellStyle: (r) => heatStyle(r.roi, 60, 300, 'green'),
    },
  ];

  return (
    <div className="space-y-4 max-w-[1440px] mx-auto">
      {/* 四象限 + 趋势 */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ChartCard title="渠道质量四象限" subtitle="横轴通过率 / 纵轴首逾(倒置) · 气泡=进件量 · 右下为优质区">
          <ReactECharts option={scatterOption} style={{ height: 320 }} notMerge />
        </ChartCard>
        <ChartCard title="分渠道类型进件趋势" subtitle="近30天 · 件" accent="#36cfc9">
          <ReactECharts option={trendOption} style={{ height: 320 }} notMerge />
        </ChartCard>
      </div>

      {/* 渠道矩阵表 */}
      <ChartCard title="渠道质量矩阵" subtitle="通过率/风险/成本/ROI 全景 · 颜色越深越需关注" accent="#ffb020">
        <FeishuTable columns={tableCols} data={channelQuality} rowKey={(r) => r.channel} />
      </ChartCard>

      {/* 专家解读 */}
      <div className="bg-gradient-to-r from-blue-50/80 to-indigo-50/60 border border-blue-100 rounded-xl px-5 py-4">
        <div className="text-[13px] font-semibold text-slate-800 mb-1.5">渠道策略建议（示例解读）</div>
        <ul className="text-[12.5px] text-slate-600 leading-6 list-disc pl-4 space-y-0.5">
          <li><b>地推合伙人</b>：FPD7 2.35% / M1+ 6.72% 全线最差且 ROI 仅 86%，建议压降投放并加面签/电核环节；</li>
          <li><b>API 导流渠道</b>：通过率低于均值 5pct 但件均成本低，建议前置白名单预筛分，把低分客群挡在征信查询前，降低查询成本损耗；</li>
          <li><b>抖音信息流</b>：进件量最大但 FPD7 持续抬升，建议对该渠道 cutoff 上调 10 分并观察 2 周 vintage 变化；</li>
          <li><b>自营/应用市场</b>：质量最优（右下象限），可加大预算倾斜，同时警惕量级增长带来的质量稀释。</li>
        </ul>
      </div>
    </div>
  );
}
