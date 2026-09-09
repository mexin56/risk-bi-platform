import test from 'node:test';
import assert from 'node:assert/strict';
import {
  normalizeAttributionTab,
  normalizePageParam,
  defaultAttributionTab,
  buildAttributionUrl,
  visibleAttributionTabs,
} from '../src/lib/attributionTab.ts';

test('normalizes fund tab and invalid values', () => {
  assert.equal(normalizeAttributionTab('fund'), 'fund');
  assert.equal(normalizeAttributionTab('bad'), 'credit');
  assert.equal(normalizeAttributionTab(null), 'credit');
});

test('maps legacy fund page to unified attribution page', () => {
  assert.equal(normalizePageParam('fundMonitor'), 'attribution');
  assert.equal(normalizePageParam('attribution'), 'attribution');
});

test('chooses a tab only when the user has permission', () => {
  assert.equal(defaultAttributionTab(true, true), 'credit');
  assert.equal(defaultAttributionTab(false, true), 'fund');
  assert.equal(defaultAttributionTab(false, false), null);
});

test('exposes only tabs granted to the current user', () => {
  assert.deepEqual(visibleAttributionTabs(true, true), ['credit', 'fund']);
  assert.deepEqual(visibleAttributionTabs(true, false), ['credit']);
  assert.deepEqual(visibleAttributionTabs(false, true), ['fund']);
  assert.deepEqual(visibleAttributionTabs(false, false), []);
});

test('writes tab without changing unrelated query parameters', () => {
  const result = buildAttributionUrl('http://localhost/?page=fundMonitor&pt=20260903', 'fund');
  assert.equal(result, 'http://localhost/?page=attribution&pt=20260903&tab=fund');
});
