import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Check, Palette } from 'lucide-react';
import { THEME_PRESETS, type ThemePreset } from '@/lib/theme';

// 侧边栏左下角 · 主题配色触发器 + 上弹面板
export default function ThemeSettings({
  currentKey,
  onChange,
  collapsed = false,
}: {
  currentKey: string;
  onChange: (p: ThemePreset) => void;
  collapsed?: boolean;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className={`relative ${collapsed ? '' : 'flex-1'}`}>
      {/* 触发按钮 */}
      <button
        onClick={() => setOpen((v) => !v)}
        title="主题配色"
        className={`flex items-center rounded-lg transition-colors duration-200 ${
          collapsed
            ? 'w-9 h-9 justify-center'
            : 'w-full gap-2 px-2.5 py-2'
        } ${
          open
            ? 'text-slate-800'
            : 'text-slate-500 hover:text-slate-800 hover:bg-slate-100/80'
        }`}
        style={open ? { background: 'rgba(var(--brand-rgb),0.10)', color: 'var(--brand)' } : undefined}
      >
        <Palette size={15} className="shrink-0" />
        {!collapsed && <span className="text-[12px] font-medium whitespace-nowrap">主题配色</span>}
        {!collapsed && (
          <span
            className="ml-auto w-3.5 h-3.5 rounded-full border border-white shadow-sm"
            style={{ background: 'linear-gradient(135deg, var(--brand), var(--brand-300))' }}
          />
        )}
      </button>

      {/* 上弹面板 */}
      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
            <motion.div
              initial={{ opacity: 0, y: 10, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 10, scale: 0.95 }}
              transition={{ type: 'spring', stiffness: 400, damping: 30 }}
              className="absolute bottom-11 left-0 z-50 w-[252px] bg-white rounded-2xl border border-slate-200/90 shadow-[0_16px_48px_-12px_rgba(15,23,42,0.28)] p-4 origin-bottom-left"
            >
              <div className="flex items-center justify-between mb-3">
                <div className="text-[13px] font-semibold text-slate-800">主题配色</div>
                <div className="text-[10px] text-slate-400">{THEME_PRESETS.length} 套预设</div>
              </div>
              <div className="grid grid-cols-5 gap-x-2 gap-y-2.5">
                {THEME_PRESETS.map((p) => {
                  const on = p.key === currentKey;
                  return (
                    <button
                      key={p.key}
                      onClick={() => onChange(p)}
                      className="group flex flex-col items-center gap-1"
                      title={p.name}
                    >
                      <span
                        className={`relative w-8 h-8 rounded-full transition-transform duration-200 group-hover:scale-110 ${
                          on ? 'ring-2 ring-offset-2 ring-slate-300' : ''
                        }`}
                        style={{
                          background: `linear-gradient(135deg, ${p.brand}, ${p.brand300})`,
                          boxShadow: `0 4px 10px ${p.brand}44`,
                        }}
                      >
                        {on && <Check size={14} className="absolute inset-0 m-auto text-white" strokeWidth={3} />}
                      </span>
                      <span className={`text-[10px] leading-3 ${on ? 'text-slate-800 font-medium' : 'text-slate-400'}`}>
                        {p.name}
                      </span>
                    </button>
                  );
                })}
              </div>
              <div className="mt-3 pt-3 border-t border-slate-100 text-[10.5px] text-slate-400 leading-4">
                主色联动侧边栏高亮、KPI 趋势与全站图表色板，背景色同步切换
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
