import { motion } from 'framer-motion';
import type { ReactNode } from 'react';

interface Props {
  title: string;
  subtitle?: string;
  extra?: ReactNode;
  children: ReactNode;
  className?: string;
  delay?: number;
  accent?: string; // 标题左侧色条
}

export default function ChartCard({
  title,
  subtitle,
  extra,
  children,
  className,
  delay = 0,
  accent = 'var(--brand)',
}: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-30px' }}
      transition={{ duration: 0.5, delay, ease: [0.22, 1, 0.36, 1] }}
      className={`bg-white/60 backdrop-blur-xl rounded-2xl border border-white/60 shadow-[0_8px_32px_-12px_rgba(15,23,42,0.12)] hover:shadow-[0_16px_40px_-12px_rgba(15,23,42,0.18)] transition-shadow duration-300 ${className ?? ''}`}
    >
      <div className="flex items-center justify-between px-5 pt-4 pb-1">
        <div className="flex items-start gap-2.5">
          <div
            className="w-[3px] h-[15px] rounded-full mt-[3px]"
            style={{ background: `linear-gradient(180deg, ${accent}, ${accent}55)` }}
          />
          <div>
            <div className="text-[14px] font-semibold text-slate-800">{title}</div>
            {subtitle && <div className="text-[11px] text-slate-400 mt-0.5">{subtitle}</div>}
          </div>
        </div>
        {extra}
      </div>
      <div className="px-2 pb-2">{children}</div>
    </motion.div>
  );
}
