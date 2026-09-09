import type { EChartsOption } from 'echarts';

export interface FundDailyTrendPoint {
  date: string;
  order_count: number;
  abnormal_order_count: number;
  abnormal_rate: number;
}

export interface FundDailyTrendColors {
  bar: string;
  line: string;
}

type BaseOptionFactory = () => EChartsOption;

function objectOption(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function formatDate(value: string) {
  return value ? value.slice(5).replace('-', '/') : '—';
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(value);
}

function formatRate(value: number) {
  return `${(value * 100).toFixed(4)}%`;
}

export function buildFundDailyTrendOption(
  points: FundDailyTrendPoint[],
  colors: FundDailyTrendColors,
  getBaseOption: BaseOptionFactory,
): EChartsOption {
  const base = getBaseOption();
  const baseTooltip = objectOption(base.tooltip);
  const baseLegend = objectOption(base.legend);
  const baseXAxis = objectOption(base.xAxis);
  const baseYAxis = objectOption(base.yAxis);

  return {
    ...base,
    grid: { left: 16, right: 20, top: 38, bottom: 12, containLabel: true },
    legend: { ...baseLegend, top: 2, left: 'center', right: undefined },
    tooltip: {
      ...baseTooltip,
      trigger: 'axis',
      formatter: (params: unknown) => {
        const first = Array.isArray(params) ? params[0] : params;
        const dataIndex = first && typeof first === 'object' && 'dataIndex' in first && typeof first.dataIndex === 'number' ? first.dataIndex : 0;
        const point = points[dataIndex];
        return point
          ? [
              `<b>${point.date}</b>`,
              `异常订单：<b>${formatNumber(point.abnormal_order_count)}</b>`,
              `异常率：<b>${formatRate(point.abnormal_rate)}</b>`,
            ].join('<br/>')
          : '';
      },
    },
    xAxis: { ...baseXAxis, data: points.map((point) => formatDate(point.date)) },
    yAxis: [
      { ...baseYAxis, name: '异常订单', min: 0, nameTextStyle: { color: '#8f959e', fontSize: 10 } },
      {
        ...baseYAxis,
        name: '异常率',
        position: 'right',
        min: 0,
        splitLine: { show: false },
        axisLabel: { color: '#8f959e', fontSize: 10, formatter: (value: number) => `${(value * 100).toFixed(2)}%` },
        nameTextStyle: { color: '#8f959e', fontSize: 10 },
      },
    ],
    series: [
      {
        name: '异常订单数',
        type: 'bar',
        barMaxWidth: 26,
        data: points.map((point) => point.abnormal_order_count),
        itemStyle: { color: colors.bar, borderRadius: [4, 4, 0, 0] },
      },
      {
        name: '异常率',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        symbol: 'circle',
        symbolSize: 5,
        data: points.map((point) => point.abnormal_rate),
        lineStyle: { color: colors.line, width: 2 },
        itemStyle: { color: colors.line },
      },
    ],
  };
}
