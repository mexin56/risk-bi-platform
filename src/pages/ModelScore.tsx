import ReactECharts from 'echarts-for-react';
import ChartCard from '@/components/ChartCard';
import FeishuTable, { heatStyle, StatusTag, type FeishuColumn } from '@/components/FeishuTable';
import { areaGradient, baseOption } from '@/lib/chartTheme';
import { getBrand } from '@/lib/theme';
import {
  gainTable,
  getAucKsTrend,
  getPsiTrend,
  getScoreDistCompare,
  modelList,
  scoreBins,
  type GainRow,
  type ScoreBin,
} from '@/data/mockData';

export default function ModelScore() {
  const psiTrend = getPsiTrend();
  const dist = getScoreDistCompare();
  const aucKs = getAucKsTrend();

  const psiOption = {
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: psiTrend.map((d) => d.date), boundaryGap: false },
    yAxis: { ...baseOption().yAxis, min: 0 },
    series: (['A卡PSI', 'B卡PSI'] as const).map((k) => ({
      name: k,
      type: 'line',
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2 },
      areaStyle: { color: areaGradient(k === 'A卡PSI' ? getBrand() : '#36cfc9', 0.1) },
      markLine:
        k === 'A卡PSI'
          ? {
              symbol: 'none',
              data: [
                { yAxis: 0.1, lineStyle: { color: '#ffb020', type: 'dashed' }, label: { formatter: '关注 0.10', fontSize: 10, color: '#d97706' } },
                { yAxis: 0.25, lineStyle: { color: '#f76965', type: 'dashed' }, label: { formatter: '预警 0.25', fontSize: 10, color: '#f76965' } },
              ],
            }
          : undefined,
      data: psiTrend.map((d) => d[k] as number),
    })),
  };

  const distOption = {
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: dist.map((d) => d.bin) },
    yAxis: { ...baseOption().yAxis, axisLabel: { formatter: '{value}%', color: '#8f959e', fontSize: 11 } },
    series: [
      {
        name: '基准期占比',
        type: 'bar',
        barGap: '10%',
        barMaxWidth: 20,
        itemStyle: { borderRadius: [3, 3, 0, 0], color: '#bcc0c7' },
        data: dist.map((d) => d.基准期占比),
      },
      {
        name: '当前期占比',
        type: 'bar',
        barMaxWidth: 20,
        itemStyle: { borderRadius: [3, 3, 0, 0], color: getBrand() },
        data: dist.map((d) => d.当前期占比),
      },
    ],
  };

  const aucKsOption = {
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: aucKs.map((d) => d.date), boundaryGap: false },
    yAxis: { ...baseOption().yAxis, min: 0.3, max: 0.8 },
    series: (['AUC', 'KS'] as const).map((k) => ({
      name: k,
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { width: 2 },
      data: aucKs.map((d) => d[k] as number),
    })),
  };

  const binCols: FeishuColumn<ScoreBin>[] = [
    { key: 'bin', title: '分箱', sticky: true, width: 70, render: (r) => <span className="font-medium text-slate-800">{r.bin}</span> },
    { key: 'range', title: '分数段', width: 100 },
    { key: 'basePct', title: '基准占比', align: 'right', render: (r) => `${r.basePct}%` },
    {
      key: 'curPct',
      title: '当前占比',
      align: 'right',
      render: (r) => `${r.curPct}%`,
      cellStyle: (r) => heatStyle(r.curPct, 0, 20, 'blue'),
    },
    {
      key: 'psi',
      title: 'PSI贡献',
      align: 'right',
      render: (r) => r.psi.toFixed(4),
      cellStyle: (r) => heatStyle(r.psi, 0, 0.02, 'red'),
    },
    { key: 'badRateBase', title: '基准坏账率', align: 'right', render: (r) => `${r.badRateBase}%` },
    {
      key: 'badRateCur',
      title: '当前坏账率',
      align: 'right',
      render: (r) => `${r.badRateCur}%`,
      cellStyle: (r) => heatStyle(r.badRateCur, 0, 30, 'red'),
    },
  ];

  const gainCols: FeishuColumn<GainRow>[] = [
    { key: 'segment', title: '分组', sticky: true, width: 80, render: (r) => <span className="font-medium text-slate-800">{r.segment}</span> },
    { key: 'range', title: '分数段', width: 100 },
    { key: 'cnt', title: '样本数', align: 'right', render: (r) => r.cnt.toLocaleString() },
    { key: 'cntPct', title: '样本占比', align: 'right', render: (r) => `${r.cntPct}%` },
    { key: 'badCnt', title: '坏账数', align: 'right' },
    {
      key: 'badRate',
      title: '坏账率',
      align: 'right',
      render: (r) => `${r.badRate}%`,
      cellStyle: (r) => heatStyle(r.badRate, 0, 30, 'red'),
    },
    {
      key: 'cumBadCapture',
      title: '累计坏账捕获率',
      align: 'right',
      render: (r) => (
        <div className="flex items-center justify-end gap-2">
          <div className="w-16 h-1.5 rounded-full bg-slate-100 overflow-hidden">
            <div className="h-full rounded-full bg-emerald-500" style={{ width: `${r.cumBadCapture}%` }} />
          </div>
          <span className="w-11 text-right">{r.cumBadCapture}%</span>
        </div>
      ),
    },
    {
      key: 'lift',
      title: '提升度 Lift',
      align: 'right',
      render: (r) => `${r.lift}x`,
      cellStyle: (r) => heatStyle(r.lift, 0, 6, 'blue'),
    },
  ];

  return (
    <div className="space-y-4 max-w-[1440px] mx-auto">
      {/* 模型清单 */}
      <div className="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-5 gap-3">
        {modelList.map((m) => (
          <div
            key={m.name}
            className="bg-white rounded-xl border border-slate-200/80 p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-[13px] font-semibold text-slate-800 truncate">{m.name}</span>
              <StatusTag
                text={m.status}
                tone={m.status === '在线' ? 'green' : 'orange'}
              />
            </div>
            <div className="grid grid-cols-3 gap-1 text-center">
              {[
                { k: 'PSI', v: m.psi.toFixed(3), warn: m.psi >= 0.1 },
                { k: 'KS', v: m.ks.toFixed(3), warn: false },
                { k: 'AUC', v: m.auc.toFixed(3), warn: false },
              ].map((s) => (
                <div key={s.k} className="rounded-lg bg-slate-50 py-1.5">
                  <div className={`text-[14px] font-semibold tabular-nums ${s.warn ? 'text-orange-500' : 'text-slate-800'}`}>
                    {s.v}
                  </div>
                  <div className="text-[10px] text-slate-400">{s.k}</div>
                </div>
              ))}
            </div>
            <div className="mt-2 text-[10.5px] text-slate-400">{m.owner}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ChartCard title="模型 PSI 稳定性趋势" subtitle="近30天 · 虚线为关注/预警阈值">
          <ReactECharts option={psiOption} style={{ height: 270 }} notMerge />
        </ChartCard>
        <ChartCard title="分数分布对比" subtitle="A卡 · 基准期(上线时) vs 当前期(近7天)">
          <ReactECharts option={distOption} style={{ height: 270 }} notMerge />
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ChartCard title="AUC / KS 月度表现" subtitle="近12个月 · 回溯样本口径">
          <ReactECharts option={aucKsOption} style={{ height: 260 }} notMerge />
        </ChartCard>
        <ChartCard title="分箱稳定性明细" subtitle="PSI 贡献度越高颜色越深 · 低分段占比抬升为本次漂移主因">
          <FeishuTable columns={binCols} data={scoreBins} rowKey={(r) => r.bin} maxHeight={260} />
        </ChartCard>
      </div>

      <ChartCard title="Gain Table · 排序能力分析" subtitle="按模型分降序10等分 · 检验区分度与坏账捕获效率">
        <FeishuTable columns={gainCols} data={gainTable} rowKey={(r) => r.segment} />
      </ChartCard>
    </div>
  );
}
