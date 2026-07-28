import type { ReactNode } from 'react';

interface Props {
  title: string;
  subtitle?: string;
  extra?: ReactNode;
  children: ReactNode;
  className?: string;
}

export default function ChartCard({ title, subtitle, extra, children, className }: Props) {
  return (
    <div
      className={`bg-white rounded-xl border border-slate-200/80 shadow-[0_1px_2px_rgba(15,23,42,0.04)] ${className ?? ''}`}
    >
      <div className="flex items-center justify-between px-5 pt-4 pb-1">
        <div>
          <div className="text-[14px] font-semibold text-slate-800">{title}</div>
          {subtitle && <div className="text-[11px] text-slate-400 mt-0.5">{subtitle}</div>}
        </div>
        {extra}
      </div>
      <div className="px-2 pb-2">{children}</div>
    </div>
  );
}
