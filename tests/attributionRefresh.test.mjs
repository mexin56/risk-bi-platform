import test from 'node:test';
import assert from 'node:assert/strict';
import { isAttributionRefreshReady } from '../src/lib/attributionRefresh.ts';

test('does not finish refresh while the old serving snapshot is still being recomputed', () => {
  assert.equal(isAttributionRefreshReady('same', 'same', { serving: true, async_refresh: true }), false);
});

test('finishes refresh when the serving snapshot is ready even if generated_at is unchanged', () => {
  assert.equal(isAttributionRefreshReady('same', 'same', { serving: true, async_refresh: false }), true);
});

test('finishes refresh when a newer generated result is available', () => {
  assert.equal(isAttributionRefreshReady('new', 'old', { serving: false, async_refresh: true }), true);
});
