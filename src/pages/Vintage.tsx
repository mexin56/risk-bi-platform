import { useMemo, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import ChartCard from '@/components/ChartCard';
import FeishuTable, { heatStyle, type FeishuColumn } from '@/components/FeishuTable';
import { baseOption } from '@/lib/chartTheme';
import {
  getVintageCurve,
  vintageM1,
  vintageM3,
  MOB_LIST,
  type VintageRow,
} from '@/data/mockData';

type Metric = 'M1' | 'M3';

export default function Vintage() {
  const [metric, setMetric] = useState<Metric>('M1');
  const rows = metric === 'M1' ? vintageM1 : vintageM3;
  const curve = getVintageCurve(metric);
  const cohortNames = rows.slice(0, 8).map((r) => r.cohort);

  // 热力范围：按当前指标的全表非空值动态计算
  const { vmin, vmax } = useMemo(() => {
    const vals = rows.flatMap((r) => r.cells.filter((v): v is number => v !== null));
    return { vmin: Math.min(...vals), vmax: Math.max(...vals) };
  }, [rows]);

  const tableCols: FeishuColumn<VintageRow>[] = useMemo(
    () => [
      {
        key: 'cohort',
        title: '放款月份',
        sticky: true,
        width: 96,
        render: (r) => <span className="font-semibold text-slate-800">{r.cohort}</span>,
      },
      { key: 'loanAmount', title: '放款金额', align: 'right', width: 84 },
      { key: 'cnt', title: '放款户数', align: 'right', width: 78 },
      ...MOB_LIST.map((mob, i) => ({
        key: `mob${mob}`,
        title: `MOB${mob}`,
        align: 'center' as const,
        width: 68,
        render: (r: VintageRow) => {
          const v = r.cells[i];
          return v === null ? (
            <span className="text-slate-300">未到表现期</span>
          ) : (
            `${v.toFixed(2)}%`
          );
        },
        cellStyle: (r: VintageRow) => heatStyle(r.cells[i], vmin, vmax, 'red'),
      })),
    ],
    [vmin, vmax]
  );

  const curveOption = {
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: curve.map((d) => d.mob as string), boundaryGap: false },
    yAxis: { ...baseOption().yAxis, axisLabel: { formatter: '{value}%', color: '#8f959e', fontSize: 11 } },
    series: cohortNames.map((c, idx) => ({
      name: c,
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { width: idx < 2 ? 3 : 1.8, type: idx < 2 ? 'solid' : 'solid' },
      emphasis: { focus: 'series' },
      data: curve.map((d) => (d[c] as number) ?? null),
    })),
  };

  // MOB6 截面趋势：各 cohort 在 MOB6 的逾期率（横向可比）
  const mob6Rows = rows.filter((r) => r.cells[5] !== null);
  const mob6Option = {
    ...baseOption(),
    grid: { left: 12, right: 16, top: 30, bottom: 8, containLabel: true },
    xAxis: { ...baseOption().xAxis, data: mob6Rows.map((r) => r.cohort) },
    yAxis: { ...baseOption().yAxis, axisLabel: { formatter: '{value}%', color: '#8f959e', fontSize: 11 } },
    series: [
      {
        name: `MOB6 截面 ${metric}+`,
        type: 'bar',
        barMaxWidth: 22,
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: (p: { value: number }) => (p.value >= (metric === 'M1' ? 4.5 : 2.2) ? '#f76965' : '#4e83fd'),
        },
        markLine: {
          symbol: 'none',
          lineStyle: { color: '#f76965', type: 'dashed' },
          label: { formatter: '阈值 {c}%', fontSize: 10, color: '#f76965' },
          data: [{ yAxis: metric === 'M1' ? 4.5 : 2.2 }],
        },
        data: mob6Rows.map((r) => r.cells[5]),
      },
    ],
  };

  const metricToggle = (
    <div className="flex bg-slate-100 rounded-lg p-0.5">
      {(['M1', 'M3'] as Metric[]).map((m) => (
        <button
          key={m}
          onClick={() => setMetric(m)}
          className={`px-3 py-1 rounded-md text-[12px] font-medium transition-colors ${
            metric === m ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'
          }`}
        >
          {m}+ 逾期率
        </button>
      ))}
    </div>
  );

  return (
    <div className="space-y-4 max-w-[1440px] mx-auto">
      {/* Vintage 热力表 */}
      <ChartCard
        title={`Vintage 账龄表 · ${metric}+ 逾期率`}
        subtitle="行=放款月份cohort，列=账龄MOB · 颜色越深表现越差 · 灰字为未到表现期"
        extra={metricToggle}
      >
        <FeishuTable
          columns={tableCols}
          data={rows}
          rowKey={(r) => r.cohort}
          maxHeight={430}
          footer={
            <tfoot>
              <tr className="bg-[#f5f6f7]">
                <td className="px-3 py-2 text-[11.5px] text-slate-500 font-medium sticky left-0 bg-[#f5f6f7] shadow-[1px_0_0_#e2e8f0]">
                  口径说明
                </td>
                <td
                  colSpan={2 + MOB_LIST.length}
                  className="px-3 py-2 text-[11.5px] text-slate-400"
                >
                  {metric}+ Vintage = 该cohort在对应MOB月末 {metric}+ 余额 / 放款金额；表现期不足 30×MOB 天的单元格置灰
                </td>
              </tr>
            </tfoot>
          }
        />
      </ChartCard>

      <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
        <ChartCard
          title={`Vintage 曲线 · ${metric}+`}
          subtitle="近8个放款月cohort · 粗线为最新两个月份"
          className="xl:col-span-3"
        >
          <ReactECharts option={curveOption} style={{ height: 300 }} notMerge />
        </ChartCard>
        <ChartCard
          title="MOB6 截面对比"
          subtitle="各cohort在相同账龄下的表现 · 红色为超阈值"
          className="xl:col-span-2"
        >
          <ReactECharts option={mob6Option} style={{ height: 300 }} notMerge />
        </ChartCard>
      </div>

      {/* 观察结论 */}
      <div className="bg-gradient-to-r from-blue-50/80 to-indigo-50/60 border border-blue-100 rounded-xl px-5 py-4">
        <div className="text-[13px] font-semibold text-slate-800 mb-1.5">监控结论（示例解读）</div>
        <ul className="text-[12.5px] text-slate-600 leading-6 list-disc pl-4 space-y-0.5">
          <li>2025 年末（11-12月）cohort 的 {metric}+ 曲线整体抬升，同账龄下高于年中约 0.3~0.5pct，与年末渠道放量节奏一致；</li>
          <li>2026 年新放款月份曲线回落至历史中位以下，前置风控收紧（A卡cutoff上调 + 白名单占比提升）效果显现；</li>
          <li>建议重点回溯 2025-12 月信息流渠道进件，并对该 cohort 提前介入 M0 催收策略。</li>
        </ul>
      </div>
    </div>
  );
}
