import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('credit attribution path column keeps Level0 records clickable', async () => {
  const source = await readFile(new URL('../src/pages/CreditAttribution.tsx', import.meta.url), 'utf8');
  const pathColumn = source.slice(source.indexOf("key: 'path'"), source.indexOf("key: 'layer'"));

  assert.doesNotMatch(pathColumn, /record\.level === 0 && !record\.is_tracked_only/);
  assert.match(pathColumn, /<button[\s\S]*onClick=\{\(\) => selectAlertPath\(record\)\}/);
  assert.doesNotMatch(pathColumn, /<span[\s\S]*>\{record\.path\}<\/span>/);
});
