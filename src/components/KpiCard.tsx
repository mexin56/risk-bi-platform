import { motion } from 'framer-motion';
import {
  ArrowDownRight,
  ArrowUpRight,
  BadgeCheck,
  Coins,
  Inbox,
  Repeat2,
  ShieldAlert,
  ShieldCheck,
  Siren,
  TrendingUp,
  type LucideIcon,
} from 'lucide-react';
import type { OverviewKpi } from '@/data/mockData';
import CountUp from '@/components/anim/CountUp';
import Sparkline from '@/components/anim/Sparkline';
import SpotlightCard from '@/components/anim/SpotlightCard';
import { getBrand } from '@/lib/theme';

const ICONS: Record<string, LucideIcon> = {
  inbox: Inbox,
  check: BadgeCheck,
  coins: Coins,
  vault: ShieldCheck,
  alert: Siren,
  trend: TrendingUp,
  shield: ShieldAlert,
  repeat: Repeat2,
};

export default function KpiCard({ kpi, index = 0 }: { kpi: OverviewKpi; index?: number }) {
  const up = kpi.mom >= 0;
  const bad = kpi.good_when_down ? up : !up;
  const Icon = ICONS[kpi.icon] ?? TrendingUp;
  const sparkColor = bad ? '#f76965' : getBrand();

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.05, ease: [0.22, 1, 0.36, 1] }}
    >
      <SpotlightCard className="rounded-2xl border border-white/60 bg-white/60 backdrop-blur-xl shadow-[0_8px_32px_-12px_rgba(15,23,42,0.12)] hover:shadow-[0_16px_40px_-12px_rgba(var(--brand-rgb),0.28)] hover:border-white/80 hover:-translate-y-0.5 transition-all duration-300">
        <div className="px-4 pt-3.5 pb-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[12px] text-slate-500">{kpi.label}</span>
            <div
              className={`w-6 h-6 rounded-md flex items-center justify-center ${bad ? 'bg-rose-50 text-rose-400' : ''}`}
              style={bad ? undefined : { background: 'rgba(var(--brand-rgb),0.10)', color: 'var(--brand)' }}
            >
              <Icon size={13} strokeWidth={2.2} />
            </div>
          </div>

          <div className="flex items-baseline gap-1">
            <span className="text-[24px] leading-7 font-semibold text-slate-800 tracking-tight">
              <CountUp value={kpi.raw} decimals={kpi.decimals} delay={index * 60} />
            </span>
            {kpi.unit && <span className="text-[11.5px] text-slate-400">{kpi.unit}</span>}
          </div>

          <div className="mt-2 flex items-end justify-between">
            <div
              className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md text-[11px] font-medium tabular-nums whitespace-nowrap shrink-0 ${
                bad
                  ? 'bg-rose-50 text-rose-500'
                  : 'bg-emerald-50 text-emerald-600'
              }`}
            >
              {up ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
              {Math.abs(kpi.mom)}%
              <span className="text-slate-400 font-normal ml-0.5">环比</span>
            </div>
            <Sparkline data={kpi.spark} color={sparkColor} width={72} height={24} />
          </div>
        </div>
      </SpotlightCard>
    </motion.div>
  );
}
