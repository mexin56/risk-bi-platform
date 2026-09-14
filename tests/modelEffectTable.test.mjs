import test from 'node:test';
import assert from 'node:assert/strict';
import { metricTone } from '../src/lib/modelEffectTable.ts';

test('returns restrained BI tones for AUC and KS values', () => {
  assert.equal(metricTone(null), 'text-slate-400');
  assert.equal(metricTone(0.59), 'bg-rose-50 text-rose-700');
  assert.equal(metricTone(0.6), 'bg-amber-50 text-amber-700');
  assert.equal(metricTone(0.69), 'bg-amber-50 text-amber-700');
  assert.equal(metricTone(0.7), 'bg-emerald-50 text-emerald-700');
});
