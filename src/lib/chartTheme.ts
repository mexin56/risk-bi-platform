// ECharts 通用主题（飞书/Metabase 风格浅色系）
import type { EChartsOption } from 'echarts';

export const PALETTE = ['#4e83fd', '#36cfc9', '#ffb020', '#f76965', '#7f6bf2', '#37c26b', '#ff8f4d'];

export function baseOption(): EChartsOption {
  return {
    color: PALETTE,
    grid: { left: 12, right: 16, top: 36, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255,255,255,0.96)',
      borderColor: '#e5e6eb',
      textStyle: { color: '#1f2329', fontSize: 12 },
      extraCssText: 'box-shadow:0 4px 16px rgba(31,35,41,.12);border-radius:8px;',
    },
    legend: {
      top: 0,
      right: 8,
      icon: 'roundRect',
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { fontSize: 11, color: '#646a73' },
    },
    xAxis: {
      type: 'category',
      axisLine: { lineStyle: { color: '#dee0e3' } },
      axisTick: { show: false },
      axisLabel: { color: '#8f959e', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#f0f1f3' } },
      axisLabel: { color: '#8f959e', fontSize: 11 },
    },
  };
}

export const chartHeight = { h: '280px' };
