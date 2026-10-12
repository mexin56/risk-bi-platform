import type { ModelScoreCohortTrend, ModelScoreStabilityWeekly, TargetMetric } from '@/lib/modelMonitoringApi';

export const TARGET_LABELS: Record<TargetMetric, string> = {
  fpd1: 'FPD1', fpd7: 'FPD7', fpd10: 'FPD10', fpd15: 'FPD15', fpd30: 'FPD30', term3: 'TERM3',
};
export const COUNTS = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 });
export const percent = (value: number | null | undefined) => value == null || !Number.isFinite(value) ? '—' : `${(value * 100).toFixed(2)}%`;
export const points = (value: number | null | undefined) => value == null || !Number.isFinite(value) ? '—' : `${value > 0 ? '+' : ''}${(value * 100).toFixed(2)} pp`;
export const dateLabel = (day: string) => day.slice(5).replace('-', '/');
export const ratio = (value: number, total: number) => total > 0 ? value / total : null;

export type Grain = 'day' | 'week';
export type WindowDays = 7 | 14 | 30;
export type Distribution = { period: string; counts: number[]; shares: Array<number | null>; total: number; firstDay: string; lastDay: string; days: number };
export type ScoreModel = { field: string; model: string };

export function shiftDay(day: string, delta: number) {
  const date = new Date(`${day}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + delta);
  return date.toISOString().slice(0, 10);
}

export function weekStart(day: string) {
  const date = new Date(`${day}T00:00:00Z`);
  return shiftDay(day, -((date.getUTCDay() + 6) % 7));
}

// Presentation-only rollup of already published daily bin counts. Never average percentages.
export function distributions(rows: ModelScoreCohortTrend[], grain: Grain): Distribution[] {
  const grouped = new Map<string, { counts: number[]; days: Set<string> }>();
  for (const row of rows) {
    if (row.bin < 1 || row.bin > 10) continue;
    const key = grain === 'day' ? row.day : weekStart(row.day);
    const item = grouped.get(key) ?? { counts: Array<number>(10).fill(0), days: new Set<string>() };
    item.counts[row.bin - 1] += row.customer_count;
    item.days.add(row.day);
    grouped.set(key, item);
  }
  return [...grouped].sort(([a], [b]) => a.localeCompare(b)).map(([period, item]) => {
    const days = [...item.days].sort();
    const total = item.counts.reduce((sum, value) => sum + value, 0);
    return { period, counts: item.counts, shares: item.counts.map(value => ratio(value, total)), total, firstDay: days[0], lastDay: days[days.length - 1], days: days.length };
  });
}

export function groupedDistribution(item: Distribution, groups: 5 | 10): Distribution {
  if (groups === 10) return item;
  const counts = Array.from({ length: 5 }, (_, i) => item.counts[i * 2] + item.counts[i * 2 + 1]);
  return { ...item, counts, shares: counts.map(value => ratio(value, item.total)) };
}

export const groupLabels = (groups: 5 | 10) => Array.from({ length: groups }, (_, i) => groups === 10 ? `Q${i + 1}` : `Q${i * 2 + 1}–Q${i * 2 + 2}`);
export const sumCustomers = (rows: ModelScoreStabilityWeekly[]) => rows.reduce((sum, row) => sum + row.customer_count, 0);

export function largestShift(current: Distribution | undefined, baseline: Distribution | undefined) {
  if (!current || !baseline || current.total === 0 || baseline.total === 0) return null;
  return current.shares.reduce<{ bin: number; value: number } | null>((largest, share, index) => {
    const previous = baseline.shares[index];
    if (share == null || previous == null) return largest;
    const value = share - previous;
    return !largest || Math.abs(value) > Math.abs(largest.value) ? { bin: index + 1, value } : largest;
  }, null);
}
