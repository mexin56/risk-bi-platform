import type { CSSProperties, ReactNode } from 'react';

// ==================== 飞书 BI 风格表格 ====================
// 特点：紧凑行高、细分隔线、表头浅灰吸顶、行 hover 高亮、数字等宽右对齐、支持热力单元格

export interface FeishuColumn<T> {
  key: string;
  title: ReactNode;
  align?: 'left' | 'right' | 'center';
  width?: number | string;
  sticky?: boolean; // 首列冻结
  render?: (row: T, rowIndex: number) => ReactNode;
  cellStyle?: (row: T, rowIndex: number) => CSSProperties | undefined;
}

interface Props<T> {
  columns: FeishuColumn<T>[];
  data: T[];
  maxHeight?: number;
  rowKey?: (row: T, i: number) => string | number;
  footer?: ReactNode;
  zebra?: boolean;
}

export default function FeishuTable<T>({
  columns,
  data,
  maxHeight,
  rowKey,
  footer,
  zebra = true,
}: Props<T>) {
  return (
    <div className="px-4 pb-4 pt-2">
      <div
        className="overflow-auto rounded-lg border border-slate-200"
        style={maxHeight ? { maxHeight } : undefined}
      >
        <table className="w-full border-collapse text-[12.5px] leading-5">
          <thead className="sticky top-0 z-10">
            <tr>
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={`bg-[#f5f6f7] text-slate-600 font-medium px-3 py-2.5 border-b border-slate-200 whitespace-nowrap ${
                    col.align === 'right'
                      ? 'text-right'
                      : col.align === 'center'
                        ? 'text-center'
                        : 'text-left'
                  } ${col.sticky ? 'sticky left-0 z-20 shadow-[1px_0_0_#e2e8f0]' : ''}`}
                  style={col.width ? { width: col.width, minWidth: col.width } : undefined}
                >
                  {col.title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => (
              <tr
                key={rowKey ? rowKey(row, i) : i}
                className={`group transition-colors hover:bg-[#f2f6ff] ${
                  zebra && i % 2 === 1 ? 'bg-[#fafbfc]' : 'bg-white'
                }`}
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={`px-3 py-2 border-b border-slate-100 whitespace-nowrap tabular-nums text-slate-700 ${
                      col.align === 'right'
                        ? 'text-right'
                        : col.align === 'center'
                          ? 'text-center'
                          : 'text-left'
                    } ${col.sticky ? `sticky left-0 z-[5] shadow-[1px_0_0_#eef2f7] ${zebra && i % 2 === 1 ? 'bg-[#fafbfc]' : 'bg-white'} group-hover:bg-[#f2f6ff]` : ''}`}
                    style={col.cellStyle ? col.cellStyle(row, i) : undefined}
                  >
                    {col.render ? col.render(row, i) : String((row as Record<string, unknown>)[col.key] ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          {footer}
        </table>
      </div>
    </div>
  );
}

// ---------- 热力图配色工具 ----------
// 飞书BI 经典红/蓝渐变：值越高颜色越深
export function heatStyle(
  value: number | null | undefined,
  min: number,
  max: number,
  palette: 'red' | 'blue' | 'green' = 'red'
): CSSProperties | undefined {
  if (value === null || value === undefined) return undefined;
  const t = Math.max(0, Math.min(1, (value - min) / (max - min || 1)));
  const scales: Record<string, [number, number, number][]> = {
    // 浅 -> 深
    red: [
      [255, 255, 255],
      [255, 228, 226],
      [254, 192, 186],
      [250, 140, 130],
      [235, 90, 78],
      [210, 50, 42],
    ],
    blue: [
      [255, 255, 255],
      [222, 235, 255],
      [186, 214, 255],
      [140, 184, 250],
      [94, 149, 245],
      [51, 109, 230],
    ],
    green: [
      [255, 255, 255],
      [220, 245, 230],
      [175, 230, 196],
      [120, 208, 158],
      [70, 180, 120],
      [34, 148, 88],
    ],
  };
  const stops = scales[palette];
  const pos = t * (stops.length - 1);
  const idx = Math.min(Math.floor(pos), stops.length - 2);
  const frac = pos - idx;
  const mix = stops[idx].map((c, k) => Math.round(c + (stops[idx + 1][k] - c) * frac));
  const deep = t > 0.62;
  return {
    backgroundColor: `rgb(${mix[0]},${mix[1]},${mix[2]})`,
    color: deep ? '#fff' : '#334155',
    fontWeight: t > 0.4 ? 600 : 400,
  };
}

// 状态徽标（飞书风格 tag）
export function StatusTag({
  text,
  tone,
}: {
  text: string;
  tone: 'green' | 'orange' | 'red' | 'blue' | 'gray';
}) {
  const map = {
    green: 'bg-emerald-50 text-emerald-600 border-emerald-200',
    orange: 'bg-orange-50 text-orange-500 border-orange-200',
    red: 'bg-rose-50 text-rose-500 border-rose-200',
    blue: 'bg-blue-50 text-blue-600 border-blue-200',
    gray: 'bg-slate-100 text-slate-500 border-slate-200',
  };
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-[11px] border ${map[tone]}`}
    >
      {text}
    </span>
  );
}
