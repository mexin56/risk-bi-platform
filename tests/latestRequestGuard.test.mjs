import assert from 'node:assert/strict';
import test from 'node:test';
import { LatestRequestGuard } from '../src/lib/latestRequestGuard.ts';

test('a completed older request is not current after a newer request starts', () => {
  const guard = new LatestRequestGuard();
  const older = guard.begin();
  const newer = guard.begin();

  assert.equal(guard.isCurrent(older), false);
  assert.equal(guard.isCurrent(newer), true);
});
