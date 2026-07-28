import { ArrowDown, ArrowUp } from 'lucide-react';
import type { OverviewKpi } from '@/data/mockData';

export default function KpiCard({ kpi }: { kpi: OverviewKpi }) {
  const up = kpi.mom >= 0;
  const bad = kpi.good_when_down ? up : !up;
  return (
    <div className="bg-white rounded-xl border border-slate-200/80 px-4 py-3.5 shadow-[0_1px_2px_rgba(15,23,42,0.04)] hover:shadow-md transition-shadow">
      <div className="text-[12px] text-slate-500 mb-1.5">{kpi.label}</div>
      <div className="flex items-baseline gap-1">
        <span className="text-[22px] font-semibold text-slate-800 tracking-tight tabular-nums">
          {kpi.value}
        </span>
        {kpi.unit && <span className="text-[12px] text-slate-400">{kpi.unit}</span>}
      </div>
      <div className="mt-1.5 flex items-center gap-1 text-[11px]">
        <span className="text-slate-400">环比</span>
        <span
          className={`inline-flex items-center gap-0.5 font-medium tabular-nums ${
            bad ? 'text-rose-500' : 'text-emerald-600'
          }`}
        >
          {up ? <ArrowUp size={12} /> : <ArrowDown size={12} />}
          {Math.abs(kpi.mom)}%
        </span>
      </div>
    </div>
  );
}
