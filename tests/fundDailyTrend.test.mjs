import test from 'node:test';
import assert from 'node:assert/strict';
import { buildFundDailyTrendOption } from '../src/lib/fundDailyTrend.ts';

const points = [
  { date: '2026-09-02', order_count: 1200, abnormal_order_count: 12, abnormal_rate: 0.01 },
  { date: '2026-09-03', order_count: 1500, abnormal_order_count: 21, abnormal_rate: 0.014 },
];

test('builds the market trend with abnormal orders as bars and abnormal rate as a right-axis line', () => {
  const option = buildFundDailyTrendOption(points, { bar: '#4e83fd', line: '#ed7d31' }, () => ({}));
  const series = option.series;

  assert.equal(Array.isArray(series), true);
  assert.equal(series.length, 2);
  assert.equal(series[0].name, '异常订单数');
  assert.equal(series[0].type, 'bar');
  assert.deepEqual(series[0].data, [12, 21]);
  assert.equal(series[1].name, '异常率');
  assert.equal(series[1].type, 'line');
  assert.equal(series[1].yAxisIndex, 1);
  assert.deepEqual(series[1].data, [0.01, 0.014]);
  assert.deepEqual(option.xAxis.data, ['09/02', '09/03']);
});

test('keeps the percentage axis and tooltip values explicit', () => {
  const option = buildFundDailyTrendOption(points, { bar: '#4e83fd', line: '#ed7d31' }, () => ({
    tooltip: { trigger: 'item' },
  }));

  assert.equal(option.yAxis[1].name, '异常率');
  assert.equal(option.yAxis[1].position, 'right');
  assert.equal(option.yAxis[1].axisLabel.formatter(0.014), '1.40%');
  assert.equal(option.tooltip.trigger, 'axis');
  assert.match(option.tooltip.formatter([{ dataIndex: 1 }]), /异常订单：<b>21<\/b>/);
  assert.match(option.tooltip.formatter([{ dataIndex: 1 }]), /异常率：<b>1\.4000%<\/b>/);
});
