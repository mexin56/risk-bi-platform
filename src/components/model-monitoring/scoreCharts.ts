import type { EChartsOption } from 'echarts';
import { COUNTS, dateLabel } from './scorePresentation';

export const CHART_COLORS = ['#2563eb', '#b58b27', '#c66d3b', '#708345', '#b06b89'];
const neutral = '#94a3b8';
export type ChartSeries = { name: string; values: Array<number | null>; color?: string; dashed?: boolean };
export const asPercent = (value: number | null | undefined) => value == null ? null : value * 100;

const categoryAxis = (labels: string[]) => ({
  type: 'category' as const, data: labels, axisTick: { show: false },
  axisLine: { lineStyle: { color: '#cbd5e1' } }, axisLabel: { color: '#64748b', fontSize: 11, hideOverlap: true },
});
const valueAxis = (unit: 'percent' | 'count' | 'pp') => ({
  type: 'value' as const, min: unit === 'pp' ? undefined : 0, max: unit === 'percent' ? (v: { max: number }) => Math.min(100, Math.max(1, Math.ceil(v.max * 1.15))) : undefined,
  splitLine: { lineStyle: { color: '#eef2f6' } }, axisLine: { show: true, lineStyle: { color: '#cbd5e1' } },
  axisLabel: { color: '#64748b', fontSize: 11, formatter: (v: number) => unit === 'count' ? (v >= 10000 ? `${+(v / 10000).toFixed(1)}万` : COUNTS.format(v)) : `${+v.toFixed(2)}${unit === 'pp' ? ' pp' : '%'}` },
});
function tooltip(unit: 'percent' | 'count' | 'pp'): EChartsOption['tooltip'] {
  return { trigger: 'axis', confine: true, renderMode: 'richText', backgroundColor: '#ffffff', borderColor: '#e2e8f0', textStyle: { color: '#334155', fontSize: 12 },
    valueFormatter: (value: unknown) => value == null ? '—' : unit === 'count' ? COUNTS.format(Number(value)) : `${Number(value).toFixed(2)}${unit === 'pp' ? ' pp' : '%'}` };
}
function common(): EChartsOption {
  return { animationDuration: 250, textStyle: { fontFamily: 'Inter, system-ui, sans-serif' }, aria: { enabled: true },
    grid: { left: 16, right: 24, top: 44, bottom: 28, containLabel: true },
    legend: { type: 'scroll', top: 4, left: 12, right: 12, itemWidth: 14, itemHeight: 8, textStyle: { color: '#475569', fontSize: 11 } } };
}

export function lineChart(labels: string[], series: ChartSeries[], unit: 'percent' | 'count' = 'percent', temporal = false): EChartsOption {
  const asBar = labels.length < 3 || (temporal && labels.length < 8);
  return { ...common(), tooltip: tooltip(unit), xAxis: { ...categoryAxis(labels), boundaryGap: asBar }, yAxis: valueAxis(unit),
    series: series.map((item, index) => ({ name: item.name, type: asBar ? 'bar' : 'line',
      data: item.values, color: item.color ?? CHART_COLORS[index % 5], connectNulls: false, smooth: false,
      symbol: index % 2 ? 'emptyCircle' : 'circle', symbolSize: 5, showSymbol: labels.length < 15,
      lineStyle: { width: 2, type: item.dashed ? 'dashed' : 'solid' }, barMaxWidth: 25,
    })) };
}

export function bars(labels: string[], series: ChartSeries[], unit: 'percent' | 'count' = 'percent'): EChartsOption {
  return { ...common(), tooltip: tooltip(unit), xAxis: categoryAxis(labels), yAxis: valueAxis(unit),
    series: series.map((item, index) => ({ name: item.name, type: 'bar', data: item.values,
      barMaxWidth: 28, itemStyle: { color: item.color ?? CHART_COLORS[index % 5], borderWidth: 1, borderColor: item.color ?? CHART_COLORS[index % 5] },
      emphasis: { focus: 'series' } })) };
}

export function shareHeatmap(periods: string[], labels: string[], matrix: Array<Array<number | null>>, metricLabel: string, counts?: number[][], scale: 'zero' | 'observed' = 'zero'): EChartsOption {
  const cells = matrix.flatMap((values, x) => values.flatMap((value, y) => value == null ? [] : [[x, y, value, counts?.[x]?.[y] ?? -1]]));
  const values = cells.map(cell => cell[2]);
  const observed = scale === 'observed';
  const min = observed && values.length ? Math.max(0, Math.floor(Math.min(...values) * 10) / 10) : 0;
  const max = observed ? Math.max(min + 0.1, Math.ceil(Math.max(0, ...values) * 10) / 10) : Math.max(1, ...values);
  return { ...common(), grid: { left: 14, right: 20, top: 16, bottom: 72, containLabel: true }, legend: { show: false },
    xAxis: categoryAxis(periods.map(dateLabel)), yAxis: { ...categoryAxis(labels), type: 'category', splitArea: { show: true, areaStyle: { color: ['#f8fafc', '#ffffff'] } } },
    visualMap: { dimension: 2, min, max: +max.toFixed(2), calculable: false, orient: 'horizontal', left: 'center', bottom: 8, itemHeight: 150, itemWidth: 10,
      text: [`${max.toFixed(1)}%`, `${min.toFixed(1)}%`], textStyle: { color: '#64748b', fontSize: 10 },
      inRange: { color: observed ? ['#f1f7fd', '#dcecfb', '#bedbf5', '#9bc6ec', '#77b1e3'] : ['#eff6ff', '#bfdbfe', '#60a5fa', '#2563eb', '#1e3a8a'] } },
    tooltip: { trigger: 'item', confine: true, renderMode: 'richText', formatter: (params: unknown) => {
      const cell = (params as { data: number[] }).data;
      return `${periods[cell[0]]} · ${labels[cell[1]]}\n${metricLabel}：${cell[2].toFixed(2)}%${cell[3] >= 0 ? `\n样本量：${COUNTS.format(cell[3])}` : ''}`;
    } },
    series: [{ type: 'heatmap', data: cells, label: { show: observed || periods.length <= 7, color: observed ? '#1e3a5f' : undefined,
      fontFamily: observed ? 'ui-monospace, monospace' : undefined, fontSize: 10, formatter: (params: unknown) => `${(params as { data: number[] }).data[2].toFixed(1)}%` },
      labelLayout: { hideOverlap: true },
      itemStyle: { borderWidth: 2, borderColor: '#ffffff' }, emphasis: { label: { show: true }, itemStyle: { borderColor: '#334155' } } }],
  };
}

export function composition(periods: string[], labels: string[], matrix: Array<Array<number | null>>): EChartsOption {
  return { ...common(), tooltip: tooltip('percent'), xAxis: categoryAxis(periods.map(dateLabel)), yAxis: { ...valueAxis('percent'), max: 100 },
    series: labels.map((name, index) => ({ name, type: 'bar', stack: 'share', barMaxWidth: 35,
      data: matrix.map(values => values[index]), itemStyle: { color: CHART_COLORS[Math.floor(index * 5 / labels.length)],
        opacity: labels.length === 10 && index % 2 === 0 ? 0.55 : 1, borderWidth: 0.5, borderColor: '#ffffff' }, emphasis: { focus: 'series' },
    })) };
}

export function shareDelta(labels: string[], values: Array<number | null>): EChartsOption {
  return { ...common(), legend: { show: false }, grid: { left: 14, right: 66, top: 16, bottom: 16, containLabel: true },
    tooltip: { ...tooltip('pp'), trigger: 'item' }, xAxis: valueAxis('pp'), yAxis: { ...categoryAxis(labels), inverse: true },
    series: [{ name: '占比变化', type: 'bar', barMaxWidth: 18, data: values.map(value => ({ value,
      itemStyle: { color: value != null && value >= 0 ? CHART_COLORS[0] : '#dbeafe', borderColor: CHART_COLORS[0], borderWidth: 1 } })),
      label: { show: true, position: 'right', color: '#334155', fontSize: 10, formatter: (params: unknown) => {
        const value = (params as { value: unknown }).value;
        return value == null ? '—' : `${Number(value) > 0 ? '+' : ''}${Number(value).toFixed(2)}`;
      } }, markLine: { silent: true, symbol: 'none', data: [{ xAxis: 0 }], lineStyle: { color: neutral, type: 'solid' }, label: { show: false } } }],
  };
}

export function cumulative(labels: string[], series: ChartSeries[]): EChartsOption {
  const accumulated = series.map(item => {
    let total = 0;
    return { ...item, values: item.values.map(value => value == null ? null : (total += value)) };
  });
  return { ...lineChart(labels, accumulated), yAxis: { ...valueAxis('percent'), max: 100 } };
}
