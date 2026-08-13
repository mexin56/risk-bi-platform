import { useState } from 'react';
import ReactECharts from 'echarts-for-react';
import ChartCard from '@/components/ChartCard';
import FeishuTable, { StatusTag, type FeishuColumn } from '@/components/FeishuTable';
import { areaGradient, baseOption } from '@/lib/chartTheme';
import { getBrand } from '@/lib/theme';
import {
  driftAttrs,
  getStabilityPsiTrend,
  migrationMatrix,
  modelHealthRanks,
  stabilityAlerts,
  stabilityBins,
  type AlertLevel,
  type StabilityAlert,
  type StabilityBin,
} from '@/data/mockData';

/* ==================== KPI 卡 ==================== */
function KpiCard({
  label,
  value,
  delta,
  deltaTone,
  dot,
  valueColor,
}: {
  label: string;
  value: string;
  delta?: string;
  deltaTone?: 'good' | 'warn' | 'bad';
  dot: string;
  valueColor?: string;
}) {
  const toneCls =
    deltaTone === 'good'
      ? 'bg-emerald-50 text-emerald-600'
      : deltaTone === 'bad'
        ? 'bg-rose-50 text-rose-600'
        : 'bg-orange-50 text-orange-600';
  return (
    <div className="bg-white rounded-xl border border-slate-200/80 shadow-[0_1px_2px_rgba(15,23,42,0.04)] p-4 hover:shadow-[0_6px_20px_-6px_rgba(15,23,42,0.08)] transition-shadow duration-300">
      <div className="flex items-center gap-1.5 text-[10.5px] font-semibold tracking-wider text-slate-500">
        <span className="w-1.5 h-1.5 rounded-full" style={{ background: dot }} />
        {label}
      </div>
      <div
        className="text-[26px] font-semibold tracking-tight tabular-nums mt-2 mb-1.5"
        style={valueColor ? { color: valueColor } : undefined}
      >
        {value}
      </div>
      {delta && <span className={`inline-flex items-center gap-1 text-[11.5px] font-medium px-2 py-0.5 rounded-full ${toneCls}`}>{delta}</span>}
    </div>
  );
}

/* ==================== 告警状态映射 ==================== */
const ALERT_META: Record<AlertLevel, { badge: string; dot: string; icon: string; bg: string }> = {
  crit: { badge: 'bg-rose-50 text-rose-600', dot: 'bg-rose-500', icon: '⚠', bg: 'bg-rose-50' },
  warn: { badge: 'bg-orange-50 text-orange-600', dot: 'bg-orange-500', icon: '▲', bg: 'bg-orange-50' },
  info: { badge: 'bg-blue-50 text-blue-600', dot: 'bg-blue-500', icon: '▣', bg: 'bg-blue-50' },
  ok: { badge: 'bg-emerald-50 text-emerald-600', dot: 'bg-emerald-500', icon: '✓', bg: 'bg-emerald-50' },
};

/* ==================== 迁移矩阵热力格 ==================== */
function MigrationCell({ v, diag }: { v: number; diag: boolean }) {
  const alpha = v >= 55 ? 0.3 : v >= 12 ? 0.16 : 0.09;
  return (
    <span
      className={`block rounded-md px-1 py-1.5 text-center text-[11.5px] transition-transform hover:scale-105 ${
        diag ? 'ring-[1.5px] ring-[#4e83fd] ring-offset-[-1px]' : ''
      }`}
      style={{
        background: `rgba(78,131,253,${alpha})`,
        color: v >= 55 ? '#1d4ed8' : '#475569',
        fontWeight: v >= 55 ? 600 : 400,
      }}
    >
      {v}%
    </span>
  );
}

export default function Stability() {
  const [range, setRange] = useState<'7' | '30' | '90'>('30');
  const [model, setModel] = useState('A卡 · 贷前信用分');
  const psiTrend = getStabilityPsiTrend();
  const brand = getBrand();
  const alertMeta = (l: AlertLevel) => ALERT_META[l];

  /* ---------- PSI 日度趋势 ---------- */
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
      areaStyle: { color: areaGradient(k === 'A卡PSI' ? brand : '#36cfc9', 0.12) },
      markLine:
        k === 'A卡PSI'
          ? {
              symbol: 'none',
              data: [
                { yAxis: 0.1, lineStyle: { color: '#ef7d3c', type: 'dashed' }, label: { formatter: '关注 0.10', fontSize: 10, color: '#c2600f', position: 'insideEndTop' } },
                { yAxis: 0.25, lineStyle: { color: '#f76965', type: 'dashed' }, label: { formatter: '预警 0.25', fontSize: 10, color: '#dc2626', position: 'insideEndTop' } },
              ],
            }
          : undefined,
      data: psiTrend.map((d) => d[k] as number),
    })),
  };

  /* ---------- 分数分布对比 ---------- */
  const distOption = {
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: stabilityBins.map((b) => b.range) },
    yAxis: { ...baseOption().yAxis, axisLabel: { formatter: '{value}%', color: '#8f959e', fontSize: 11 } },
    series: [
      {
        name: '基准期',
        type: 'bar',
        barGap: '10%',
        barMaxWidth: 22,
        itemStyle: { borderRadius: [3, 3, 0, 0], color: '#cbd5e1' },
        label: {
          show: true,
          position: 'top',
          fontSize: 10,
          color: '#94a3b8',
          formatter: (p: { value: number; dataIndex: number }) =>
            Math.abs(p.value - stabilityBins[p.dataIndex].curPct) >= 3 ? '▼' : '',
        },
        data: stabilityBins.map((b) => b.basePct),
      },
      {
        name: '当前期',
        type: 'bar',
        barMaxWidth: 22,
        itemStyle: { borderRadius: [3, 3, 0, 0], color: brand },
        data: stabilityBins.map((b) => b.curPct),
      },
    ],
  };

  /* ---------- 模型健康排行 ---------- */
  const rankColors: Record<string, string> = { 健康: '#22a06b', 关注: '#ef7d3c', 预警: '#f76965' };
  const rankOption = {
    ...baseOption(),
    grid: { left: 12, right: 44, top: 8, bottom: 8, containLabel: true },
    xAxis: { ...baseOption().xAxis, show: false, max: 100 },
    yAxis: {
      ...baseOption().yAxis,
      type: 'category',
      inverse: true,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#475569', fontSize: 12 },
      splitLine: { show: false },
    },
    series: [
      {
        type: 'bar',
        barWidth: 14,
        data: modelHealthRanks.map((r) => ({
          value: r.score,
          itemStyle: { color: rankColors[r.status], borderRadius: [0, 4, 4, 0] },
        })),
        label: { show: true, position: 'right', formatter: '{c} 分', fontSize: 12, color: '#334155', fontWeight: 600 },
        backgroundStyle: { color: '#f1f5f9', borderRadius: [0, 4, 4, 0] },
        showBackground: true,
      },
    ],
    tooltip: { show: false },
    legend: { show: false },
  };

  /* ---------- 漂移归因 ---------- */
  const attrOption = {
    ...baseOption(),
    grid: { left: 12, right: 36, top: 8, bottom: 8, containLabel: true },
    xAxis: { ...baseOption().xAxis, show: false, max: 50 },
    yAxis: {
      ...baseOption().yAxis,
      type: 'category',
      inverse: true,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#475569', fontSize: 12 },
      splitLine: { show: false },
    },
    series: [
      {
        type: 'bar',
        barWidth: 14,
        data: driftAttrs.map((a, i) => ({
          value: a.pct,
          itemStyle: {
            color: i === 0 ? '#ef7d3c' : i === 1 ? '#f7c948' : brand,
            borderRadius: [0, 4, 4, 0],
            opacity: i === 0 ? 1 : 0.85,
          },
        })),
        label: { show: true, position: 'right', formatter: '{c}%', fontSize: 12, color: '#334155', fontWeight: 600 },
        backgroundStyle: { color: '#f1f5f9', borderRadius: [0, 4, 4, 0] },
        showBackground: true,
      },
    ],
    tooltip: { show: false },
    legend: { show: false },
  };

  /* ---------- 分箱稳定性明细表 ---------- */
  const binCols: FeishuColumn<StabilityBin>[] = [
    { key: 'bin', title: '分箱', sticky: true, width: 64, render: (r) => <span className="font-medium text-slate-800">{r.bin}</span> },
    { key: 'range', title: '分数段', width: 86 },
    { key: 'basePct', title: '基准占比', align: 'right', render: (r) => `${r.basePct}%` },
    { key: 'curPct', title: '当前占比', align: 'right', render: (r) => `${r.curPct}%` },
    {
      key: 'drift',
      title: '占比变化',
      align: 'right',
      render: (r) => (
        <span className={r.drift > 0 ? 'text-rose-500 font-medium' : r.drift < 0 ? 'text-emerald-600 font-medium' : ''}>
          {r.drift > 0 ? '+' : ''}
          {r.drift}pp
        </span>
      ),
    },
    {
      key: 'psiContrib',
      title: 'PSI 贡献',
      align: 'right',
      render: (r) => (
        <span className={r.psiContrib >= 0.05 ? 'text-rose-500 font-semibold' : 'text-slate-600'}>
          {r.psiContrib.toFixed(4)}
        </span>
      ),
    },
  ];

  /* ---------- 告警列表 ---------- */
  const alerts = (stabilityAlerts as StabilityAlert[]).map((a) => {
    const m = alertMeta(a.level);
    return (
      <div key={a.time + a.model} className="flex items-center gap-3 py-2.5 border-b border-slate-100 last:border-none">
        <div className={`w-7 h-7 rounded-full ${m.bg} flex items-center justify-center text-[12px] shrink-0`}>{m.icon}</div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[12.5px] font-semibold text-slate-800">{a.model}</span>
            <span className={`inline-flex items-center gap-1 text-[10.5px] font-semibold px-2 py-0.5 rounded-full ${m.badge}`}>
              <span className={`w-1 h-1 rounded-full ${m.dot}`} />
              {a.tag}
            </span>
          </div>
          <div className="text-[11.5px] text-slate-500 mt-0.5 truncate">{a.detail}</div>
        </div>
        <span className="text-[10.5px] text-slate-400 whitespace-nowrap shrink-0">{a.time}</span>
      </div>
    );
  });

  /* ---------- 迁移矩阵 ---------- */
  const matrixHead = ['基准 \\ 当前', ...stabilityBins.map((b) => b.range)];

  return (
    <div className="space-y-4 max-w-[1440px] mx-auto">
      {/* 工具条: 模型切换 + 时间范围 + 操作 */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2.5 flex-wrap">
          {['A卡 · 贷前信用分', 'B卡 · 贷中行为分', 'C卡 · 反欺诈分', 'D卡 · 定价分'].map((m) => (
            <button
              key={m}
              onClick={() => setModel(m)}
              className={`px-3.5 py-1.5 rounded-full text-[12px] font-medium transition-colors ${
                model === m ? 'bg-white text-slate-800 shadow-[0_1px_2px_rgba(15,23,42,0.08)] border border-slate-200' : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              {m}
            </button>
          ))}
          <span className="w-px h-4 bg-slate-200 mx-1" />
          {(['7', '30', '90'] as const).map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`px-3 py-1.5 rounded-full text-[12px] font-medium transition-colors ${
                range === r ? 'bg-white text-slate-800 shadow-[0_1px_2px_rgba(15,23,42,0.08)] border border-slate-200' : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              近{r}日
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button className="px-3.5 py-1.5 rounded-full border border-blue-500 text-blue-600 text-[12px] font-medium hover:bg-blue-50 transition-colors">
            ⤓ 导出报告
          </button>
          <button
            className="px-3.5 py-1.5 rounded-full text-white text-[12px] font-medium transition-opacity hover:opacity-90"
            style={{ background: 'linear-gradient(135deg, var(--brand), var(--brand-300))' }}
          >
            ＋ 配置告警
          </button>
        </div>
      </div>

      {/* KPI 行 */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <KpiCard label="当前 PSI" value="0.182" delta="▲ 0.047 较上周" deltaTone="bad" dot={brand} valueColor="#dc2626" />
        <KpiCard label="7日 PSI 峰值" value="0.213" delta="7月28日 触发预警" deltaTone="warn" dot="#ef7d3c" valueColor="#c2600f" />
        <KpiCard label="样本量(当前期)" value="128,640" delta="▼ 3.2% 较基准期" deltaTone="good" dot="#22a06b" />
        <KpiCard label="通过率 Δ" value="+2.14pp" delta="▲ 阈值 ±1.5pp" deltaTone="bad" dot={brand} valueColor="#dc2626" />
        <KpiCard label="坏账率 Δ" value="-0.38pp" delta="▼ 优于基准" deltaTone="good" dot={brand} valueColor="#15803d" />
        <KpiCard label="模型健康分" value="72" delta="状态: 关注" deltaTone="warn" dot="#22a06b" valueColor="#c2600f" />
      </div>

      {/* PSI 趋势 + 分数分布 */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ChartCard
          title="PSI 日度趋势"
          subtitle="橙色虚线 = 关注阈值 0.10 · 红色虚线 = 预警阈值 0.25"
          extra={
            <div className="flex items-center gap-4 text-[11.5px] text-slate-500">
              <span className="flex items-center gap-1.5">
                <span className="w-4 h-[3px] rounded-full" style={{ background: brand }} />
                A卡 PSI
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-4 h-[3px] rounded-full bg-cyan-400" />
                B卡 PSI
              </span>
            </div>
          }
        >
          <ReactECharts option={psiOption} style={{ height: 280 }} notMerge />
        </ChartCard>
        <ChartCard
          title="分数分布对比"
          subtitle="基准期(上线日) vs 当前期(近30天) · ▼ = 漂移超过 3pp 的分箱"
          extra={<StatusTag text="PSI 贡献 Top3 已标注" tone="blue" />}
        >
          <ReactECharts option={distOption} style={{ height: 280 }} notMerge />
        </ChartCard>
      </div>

      {/* 迁移矩阵 + 告警 */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ChartCard
          title="分箱迁移矩阵"
          subtitle="基准期分箱 → 当前期分箱 · 对角高亮为稳定客户 · 浅蓝格 = 向上迁移(风险上升)"
          extra={<span className="text-[10.5px] text-slate-400">单位: % · 每行和为 100%</span>}
        >
          <div className="overflow-x-auto px-3 pb-2">
            <table className="w-full border-collapse text-[12.5px]">
              <thead>
                <tr>
                  {matrixHead.map((h, i) => (
                    <th
                      key={h}
                      className={`px-2 py-2 text-[10.5px] font-semibold tracking-wide text-slate-400 border-b border-slate-200 whitespace-nowrap ${
                        i === 0 ? 'text-left' : 'text-center'
                      }`}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {migrationMatrix.map((row, i) => (
                  <tr key={i}>
                    <td className="px-2 py-1.5 text-[11.5px] text-slate-500 whitespace-nowrap border-b border-slate-100">
                      {stabilityBins[i].range}
                    </td>
                    {row.map((v, j) => (
                      <td key={j} className="px-1 py-1.5 border-b border-slate-100">
                        <MigrationCell v={v} diag={i === j} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </ChartCard>
        <ChartCard
          title="稳定性告警"
          subtitle="近 30 天触发 · 按严重程度排序"
          extra={
            <button className="px-3 py-1 rounded-full border border-blue-500 text-blue-600 text-[11px] font-medium hover:bg-blue-50 transition-colors">
              查看全部 12 条
            </button>
          }
        >
          <div className="px-4 pb-2 pt-1">{alerts}</div>
        </ChartCard>
      </div>

      {/* 健康排行 + 漂移归因 */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ChartCard
          title="模型健康排行"
          subtitle="综合 PSI / 迁移率 / 排序能力 / 通过率 四维加权"
          extra={
            <div className="flex items-center gap-3 text-[11.5px] text-slate-500">
              <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />健康</span>
              <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-orange-400" />关注</span>
              <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-rose-500" />预警</span>
            </div>
          }
        >
          <ReactECharts option={rankOption} style={{ height: 250 }} notMerge />
        </ChartCard>
        <ChartCard
          title="漂移归因分析"
          subtitle="PSI 贡献度分解 · 定位漂移来源(建议结合特征监控联动)"
          extra={<StatusTag text="2 个特征贡献 > 30%" tone="orange" />}
        >
          <ReactECharts option={attrOption} style={{ height: 250 }} notMerge />
        </ChartCard>
      </div>

      {/* 分箱稳定性明细 */}
      <ChartCard title="分箱稳定性明细" subtitle="PSI 贡献度 ≥ 0.05 标红 · 定位漂移集中分箱">
        <FeishuTable columns={binCols} data={stabilityBins} rowKey={(r) => r.bin} maxHeight={280} />
      </ChartCard>
    </div>
  );
}
