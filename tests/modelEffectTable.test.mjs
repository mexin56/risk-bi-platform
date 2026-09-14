import test from 'node:test';
import assert from 'node:assert/strict';
import {
  commonWeeklySampleStats,
  metricBarWidth,
  metricTone,
  modelFieldsWithAuc,
  shouldShowWeeklySampleStats,
  weeksWithAuc,
} from '../src/lib/modelEffectTable.ts';

test('returns restrained BI tones for AUC and KS values', () => {
  assert.equal(metricTone(null), 'text-slate-400');
  assert.equal(metricTone(0.59), 'bg-rose-50 text-rose-700');
  assert.equal(metricTone(0.6), 'bg-amber-50 text-amber-700');
  assert.equal(metricTone(0.69), 'bg-amber-50 text-amber-700');
  assert.equal(metricTone(0.7), 'bg-emerald-50 text-emerald-700');
});

test('maps metric values to fixed 0-1 data bar widths', () => {
  assert.equal(metricBarWidth(null), 0);
  assert.equal(metricBarWidth(-0.2), 0);
  assert.equal(metricBarWidth(0.625), 62.5);
  assert.equal(metricBarWidth(1.4), 100);
});

test('shows identical weekly count and badrate only in the canonical week', () => {
  const rows = [
    { week_start: '2026-09-07', count: 1000, badrate: 0.1 },
    { week_start: '2026-08-31', count: 1000, badrate: 0.1 },
    { week_start: '2026-08-24', count: 1000, badrate: 0.1 },
  ];

  assert.equal(shouldShowWeeklySampleStats(rows, '2026-09-07'), false);
  assert.equal(shouldShowWeeklySampleStats(rows, '2026-08-31'), true);
  assert.equal(shouldShowWeeklySampleStats(rows, '2026-08-24'), false);
});

test('keeps weekly count and badrate when either value changes', () => {
  const rows = [
    { week_start: '2026-09-07', count: 1000, badrate: 0.1 },
    { week_start: '2026-08-31', count: 999, badrate: 0.1 },
  ];

  assert.equal(shouldShowWeeklySampleStats(rows, '2026-09-07'), true);
  assert.equal(shouldShowWeeklySampleStats(rows, '2026-08-31'), true);
});

test('does not let an immature blank week disable deduplication', () => {
  const rows = [
    { week_start: '2026-09-07', count: null, badrate: null },
    { week_start: '2026-08-31', count: 1000, badrate: 0.1 },
    { week_start: '2026-08-24', count: 1000, badrate: 0.1 },
  ];

  assert.equal(shouldShowWeeklySampleStats(rows, '2026-09-07'), false);
  assert.equal(shouldShowWeeklySampleStats(rows, '2026-08-31'), true);
  assert.equal(shouldShowWeeklySampleStats(rows, '2026-08-24'), false);
});

test('does not move duplicated sample stats when the canonical week is absent', () => {
  const rows = [
    { week_start: '2026-09-07', count: 1000, badrate: 0.1 },
    { week_start: '2026-08-24', count: 1000, badrate: 0.1 },
  ];

  assert.equal(shouldShowWeeklySampleStats(rows, '2026-09-07'), false);
  assert.equal(shouldShowWeeklySampleStats(rows, '2026-08-24'), false);
});

test('does not move duplicated sample stats when the canonical week is immature', () => {
  const rows = [
    { week_start: '2026-09-07', count: 1000, badrate: 0.1 },
    { week_start: '2026-08-31', count: null, badrate: null },
  ];

  assert.equal(shouldShowWeeklySampleStats(rows, '2026-09-07'), false);
  assert.equal(shouldShowWeeklySampleStats(rows, '2026-08-31'), false);
});

test('moves same-week sample stats shared by all models into the week header', () => {
  const rows = [
    { model: 'm1', week_start: '2026-09-07', count: 1200, badrate: 0.12 },
    { model: 'm2', week_start: '2026-09-07', count: 1200, badrate: 0.12 },
    { model: 'm1', week_start: '2026-08-31', count: 1000, badrate: 0.1 },
    { model: 'm2', week_start: '2026-08-31', count: 1000, badrate: 0.1 },
  ];

  assert.deepEqual(commonWeeklySampleStats(rows, '2026-09-07'), { count: 1200, badrate: 0.12 });
  assert.deepEqual(commonWeeklySampleStats(rows, '2026-08-31'), { count: 1000, badrate: 0.1 });
});

test('keeps per-model sample stats when a week is not shared by all models', () => {
  const rows = [
    { model: 'm1', week_start: '2026-09-07', count: 1200, badrate: 0.12 },
    { model: 'm2', week_start: '2026-09-07', count: 1199, badrate: 0.12 },
  ];

  assert.equal(commonWeeklySampleStats(rows, '2026-09-07'), null);
});

test('ignores immature blank models when finding shared weekly sample stats', () => {
  const rows = [
    { model: 'm1', week_start: '2026-09-07', count: null, badrate: null },
    { model: 'm2', week_start: '2026-09-07', count: 1200, badrate: 0.12 },
    { model: 'm3', week_start: '2026-09-07', count: 1200, badrate: 0.12 },
  ];

  assert.deepEqual(commonWeeklySampleStats(rows, '2026-09-07'), { count: 1200, badrate: 0.12 });
});

test('hides model rows whose AUC is blank for every week', () => {
  const rows = [
    { model: 'm1', week_start: '2026-09-07', auc: 0.7 },
    { model: 'm1', week_start: '2026-08-31', auc: null },
    { model: 'm2', week_start: '2026-09-07', auc: null },
  ];

  assert.deepEqual(modelFieldsWithAuc(rows, ['m1', 'm2']), ['m1']);
  assert.deepEqual(modelFieldsWithAuc(rows, ['m1', 'm2'], 'm2'), []);
});

test('hides weeks whose AUC is blank for every visible model', () => {
  const rows = [
    { model: 'm1', week_start: '2026-09-07', auc: 0.7 },
    { model: 'm1', week_start: '2026-08-31', auc: null },
    { model: 'm2', week_start: '2026-09-07', auc: null },
  ];

  assert.deepEqual(weeksWithAuc(rows, ['m1']), ['2026-09-07']);
});
