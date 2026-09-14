export function metricTone(value: number | null | undefined): string {
  if (value == null) return 'text-slate-400';
  if (value >= 0.7) return 'bg-emerald-50 text-emerald-700';
  if (value >= 0.6) return 'bg-amber-50 text-amber-700';
  return 'bg-rose-50 text-rose-700';
}

export function metricBarWidth(value: number | null | undefined): number {
  if (value == null || Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(1, value)) * 100;
}

export interface WeeklySampleStatRow {
  week_start: string;
  count: number | null;
  badrate: number | null;
}

export interface CommonWeeklySampleStats {
  count: number;
  badrate: number;
}

export interface WeeklyEffectRow {
  model: string;
  week_start: string;
  auc: number | null;
}

export function modelFieldsWithAuc(
  rows: WeeklyEffectRow[],
  candidateFields: string[],
  selectedField = '',
): string[] {
  const fieldsWithAuc = new Set(
    rows.filter((row) => row.auc != null).map((row) => row.model),
  );
  return candidateFields.filter(
    (field) => (!selectedField || field === selectedField) && fieldsWithAuc.has(field),
  );
}

export function weeksWithAuc(rows: WeeklyEffectRow[], modelFields: string[]): string[] {
  const visibleModels = new Set(modelFields);
  return [...new Set(
    rows
      .filter((row) => visibleModels.has(row.model) && row.auc != null)
      .map((row) => row.week_start),
  )].sort((left, right) => right.localeCompare(left));
}

export function commonWeeklySampleStats(
  rows: WeeklySampleStatRow[],
  week: string,
): CommonWeeklySampleStats | null {
  const weekRows = rows.filter((row) => row.week_start === week);
  const comparableRows = weekRows.filter((row) => row.count != null && row.badrate != null);
  if (!comparableRows.length) return null;

  const first = comparableRows[0];
  if (first.count == null || first.badrate == null) return null;
  const isIdentical = comparableRows.every(
    (row) => row.count === first.count && row.badrate === first.badrate,
  );
  return isIdentical ? { count: first.count, badrate: first.badrate } : null;
}

export function shouldShowWeeklySampleStats(
  rows: WeeklySampleStatRow[],
  week: string,
  canonicalWeek = '2026-08-31',
): boolean {
  if (rows.length <= 1) return true;

  const comparableRows = rows.filter((row) => row.count != null && row.badrate != null);
  if (comparableRows.length === 0) return true;
  if (comparableRows.length === 1) {
    const canonicalRow = rows.find((row) => row.week_start === canonicalWeek);
    return canonicalRow?.count != null && canonicalRow.badrate != null && week === canonicalWeek;
  }

  const first = comparableRows[0];
  const isIdentical = comparableRows.every(
    (row) => row.count === first.count && row.badrate === first.badrate,
  );
  if (!isIdentical) return true;

  const canonicalRow = rows.find((row) => row.week_start === canonicalWeek);
  return canonicalRow?.count != null && canonicalRow.badrate != null && week === canonicalWeek;
}
