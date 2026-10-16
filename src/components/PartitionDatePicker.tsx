import { useMemo, useState } from 'react';
import { CalendarDays } from 'lucide-react';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';

interface PartitionDatePickerProps {
  /** 已发布的分区列表, 格式 YYYYMMDD (如 20260902) */
  partitions: string[];
  /** 当前选中的分区 (YYYYMMDD) */
  value: string;
  onChange: (pt: string) => void;
  ariaLabel?: string;
}

const PT_PATTERN = /^\d{8}$/;

/** YYYYMMDD -> 本地 Date (避免 new Date('YYYY-MM-DD') 的 UTC 偏移问题) */
function ptToDate(pt: string): Date | undefined {
  if (!PT_PATTERN.test(pt)) return undefined;
  const year = Number(pt.slice(0, 4));
  const month = Number(pt.slice(4, 6)) - 1;
  const day = Number(pt.slice(6, 8));
  const date = new Date(year, month, day);
  return Number.isNaN(date.getTime()) ? undefined : date;
}

/** 本地 Date -> YYYYMMDD */
function dateToPt(date: Date): string {
  const y = String(date.getFullYear());
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}${m}${d}`;
}

/** YYYYMMDD -> YYYY-MM-DD, 用于展示 */
function ptToLabel(pt: string): string {
  if (!PT_PATTERN.test(pt)) return pt || '—';
  return `${pt.slice(0, 4)}-${pt.slice(4, 6)}-${pt.slice(6, 8)}`;
}

/**
 * 数据日期筛选器: 日历里只允许点击已发布分区对应的日期,
 * 没有数据的日期自动置灰, 选中后按 pt 切换数据。
 */
export default function PartitionDatePicker({ partitions, value, onChange, ariaLabel = '选择数据日期' }: PartitionDatePickerProps) {
  const [open, setOpen] = useState(false);

  const available = useMemo(() => new Set(partitions.filter((pt) => PT_PATTERN.test(pt))), [partitions]);

  const { startMonth, endMonth } = useMemo(() => {
    const dates = partitions.map(ptToDate).filter((d): d is Date => Boolean(d)).sort((a, b) => a.getTime() - b.getTime());
    return { startMonth: dates[0], endMonth: dates[dates.length - 1] };
  }, [partitions]);

  const selected = ptToDate(value);
  const disabled = partitions.length === 0;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={disabled}
          aria-label={ariaLabel}
          title="选择有数据的日期, 灰色日期暂无数据"
          className="theme-select inline-flex items-center gap-1.5 pr-3 tabular-nums disabled:opacity-60"
        >
          <CalendarDays size={13} className="text-[var(--brand,#4e83fd)]" />
          {ptToLabel(value)}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-auto p-2">
        <Calendar
          mode="single"
          selected={selected}
          defaultMonth={selected ?? endMonth}
          startMonth={startMonth}
          endMonth={endMonth}
          disabled={(date) => !available.has(dateToPt(date))}
          onSelect={(date) => {
            if (!date) return;
            const pt = dateToPt(date);
            if (!available.has(pt)) return;
            setOpen(false);
            if (pt !== value) onChange(pt);
          }}
        />
      </PopoverContent>
    </Popover>
  );
}
