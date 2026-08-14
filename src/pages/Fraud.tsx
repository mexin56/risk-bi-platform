import ReactECharts from 'echarts-for-react';
import { motion } from 'framer-motion';
import { ArrowDownRight, ArrowUpRight } from 'lucide-react';
import ChartCard from '@/components/ChartCard';
import FeishuTable, { heatStyle, StatusTag, type FeishuColumn } from '@/components/FeishuTable';
import { areaGradient, baseOption } from '@/lib/chartTheme';
import { getBrand } from '@/lib/theme';
import {
  deviceAlerts,
  fraudKpis,
  fraudRules,
  fraudTypePie,
  getFraudTrend,
  type DeviceAlertRow,
  type FraudRuleRow,
  type StageKpi,
} from '@/data/mockData';

function FraudKpiCard({ kpi, index }: { kpi: StageKpi; index: number }) {
  const up = kpi.mom >= 0;
  const bad = kpi.goodDown ? up : !up;
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: index * 0.05 }}
      className="bg-white/60 backdrop-blur-xl rounded-2xl border border-white/60 px-4 py-3.5 shadow-[0_1px_2px_rgba(15,23,42,0.04)] hover:shadow-md hover:-translate-y-0.5 transition-all duration-300"
    >
      <div className="text-[12px] text-slate-500 mb-1.5">{kpi.label}</div>
      <div className="flex items-baseline gap-1">
        <span className="text-[22px] font-semibold text-slate-800 tracking-tight tabular-nums">{kpi.value}</span>
        {kpi.unit && <span className="text-[12px] text-slate-400">{kpi.unit}</span>}
      </div>
      <div
        className={`mt-1.5 inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md text-[11px] font-medium tabular-nums ${
          bad ? 'bg-rose-50 text-rose-500' : 'bg-emerald-50 text-emerald-600'
        }`}
      >
        {up ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
        {Math.abs(kpi.mom)}%
        <span className="text-slate-400 font-normal ml-0.5">环比</span>
      </div>
    </motion.div>
  );
}

export default function Fraud() {
  const trend = getFraudTrend();

  const trendOption = {
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: trend.map((d) => d.date) },
    yAxis: [
      { ...baseOption().yAxis, name: '命中(件)', nameTextStyle: { color: '#8f959e', fontSize: 10 } },
      { ...baseOption().yAxis, name: '拦截率(%)', splitLine: { show: false }, nameTextStyle: { color: '#8f959e', fontSize: 10 } },
    ],
    series: [
      {
        name: '规则命中量',
        type: 'bar',
        barMaxWidth: 14,
        itemStyle: { borderRadius: [3, 3, 0, 0], color: '#ffb020', opacity: 0.85 },
        data: trend.map((d) => d.规则命中),
      },
      {
        name: '欺诈拦截率',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2.2, color: '#f76965' },
        areaStyle: { color: areaGradient('#f76965', 0.1) },
        data: trend.map((d) => d.拦截率),
      },
    ],
  };

  const pieOption = {
    color: [getBrand(), '#ffb020', '#f76965', '#7f6bf2', '#bcc0c7'],
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
        data: fraudTypePie,
      },
    ],
  };

  const ruleCols: FeishuColumn<FraudRuleRow>[] = [
    { key: 'rule', title: '规则', sticky: true, width: 220, render: (r) => <span className="font-medium text-slate-800 text-[12px]">{r.rule}</span> },
    { key: 'type', title: '类型', width: 90, render: (r) => <span className="text-slate-500">{r.type}</span> },
    { key: 'hit', title: '当日命中', align: 'right' },
    { key: 'block', title: '当日拦截', align: 'right' },
    {
      key: 'precision', title: '准确率', align: 'right',
      render: (r) => `${r.precision}%`,
      cellStyle: (r) => heatStyle(r.precision, 60, 100, 'green'),
    },
    {
      key: 'status', title: '状态', width: 88,
      render: (r) => (
        <StatusTag
          text={r.status}
          tone={r.status === '生效中' ? 'green' : r.status === '观察中' ? 'orange' : 'gray'}
        />
      ),
    },
  ];

  const deviceCols: FeishuColumn<DeviceAlertRow>[] = [
    { key: 'fingerprint', title: '设备指纹', sticky: true, width: 140, render: (r) => <span className="font-mono text-[12px] text-slate-800">{r.fingerprint}</span> },
    { key: 'applyCnt', title: '关联申请', align: 'right', cellStyle: (r) => heatStyle(r.applyCnt, 0, 15, 'red') },
    { key: 'passCnt', title: '关联通过', align: 'right' },
    { key: 'region', title: '归属地' },
    {
      key: 'level', title: '风险等级', width: 90,
      render: (r) => <StatusTag text={r.level === '高' ? '高风险' : '中风险'} tone={r.level === '高' ? 'red' : 'orange'} />,
    },
    { key: 'action', title: '处置措施', render: (r) => <span className="text-slate-600">{r.action}</span> },
  ];

  return (
    <div className="space-y-4 max-w-[1440px] mx-auto">
      {/* KPI */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
        {fraudKpis.map((k, i) => (
          <FraudKpiCard key={k.label} kpi={k} index={i} />
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ChartCard title="拦截趋势" subtitle="近30天 · 命中量(柱) × 拦截率(线) · 7/14-7/18 为中介攻击波次" accent="#f76965">
          <ReactECharts option={trendOption} style={{ height: 280 }} notMerge />
        </ChartCard>
        <ChartCard title="欺诈类型分布" subtitle="近7天拦截件归因 (%)" accent="#7f6bf2">
          <ReactECharts option={pieOption} style={{ height: 280 }} notMerge />
        </ChartCard>
      </div>

      <ChartCard title="欺诈规则命中 TOP" subtitle="按当日命中量排序 · 准确率<75% 的规则建议进入观察名单" accent="#f76965">
        <FeishuTable columns={ruleCols} data={fraudRules} rowKey={(r) => r.rule} />
      </ChartCard>

      <ChartCard title="设备聚集 / 团伙预警" subtitle="同设备关联多申请 · 实时风控输出" accent="#ffb020">
        <FeishuTable columns={deviceCols} data={deviceAlerts} rowKey={(r) => r.fingerprint} />
      </ChartCard>
    </div>
  );
}
