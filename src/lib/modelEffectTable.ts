export function metricTone(value: number | null | undefined): string {
  if (value == null) return 'text-slate-400';
  if (value >= 0.7) return 'bg-emerald-50 text-emerald-700';
  if (value >= 0.6) return 'bg-amber-50 text-amber-700';
  return 'bg-rose-50 text-rose-700';
}
