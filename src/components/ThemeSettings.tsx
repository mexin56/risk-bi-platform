import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Check, Palette, X } from 'lucide-react';
import { THEME_PRESETS, type ThemePreset } from '@/lib/theme';

// 右下角悬浮主题配色设置
export default function ThemeSettings({
  currentKey,
  onChange,
}: {
  currentKey: string;
  onChange: (p: ThemePreset) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3">
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 12, scale: 0.92 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.92 }}
            transition={{ type: 'spring', stiffness: 380, damping: 28 }}
            className="w-[228px] bg-white rounded-2xl border border-slate-200/90 shadow-[0_16px_48px_-12px_rgba(15,23,42,0.25)] p-4"
          >
            <div className="flex items-center justify-between mb-3">
              <div className="text-[13px] font-semibold text-slate-800">主题配色</div>
              <button
                onClick={() => setOpen(false)}
                className="p-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
              >
                <X size={14} />
              </button>
            </div>
            <div className="grid grid-cols-5 gap-2">
              {THEME_PRESETS.map((p) => {
                const on = p.key === currentKey;
                return (
                  <button
                    key={p.key}
                    onClick={() => onChange(p)}
                    className="group flex flex-col items-center gap-1.5"
                    title={p.name}
                  >
                    <span
                      className={`relative w-8 h-8 rounded-full transition-transform group-hover:scale-110 ${
                        on ? 'ring-2 ring-offset-2 ring-slate-300' : ''
                      }`}
                      style={{
                        background: `linear-gradient(135deg, ${p.brand}, ${p.brand300})`,
                        boxShadow: `0 4px 10px ${p.brand}44`,
                      }}
                    >
                      {on && <Check size={14} className="absolute inset-0 m-auto text-white" strokeWidth={3} />}
                    </span>
                    <span className={`text-[10px] ${on ? 'text-slate-800 font-medium' : 'text-slate-400'}`}>
                      {p.name}
                    </span>
                  </button>
                );
              })}
            </div>
            <div className="mt-3 pt-3 border-t border-slate-100 text-[10.5px] text-slate-400 leading-4">
              主色将联动侧边栏高亮、KPI 趋势与全站图表色板
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <motion.button
        whileHover={{ scale: 1.06 }}
        whileTap={{ scale: 0.94 }}
        onClick={() => setOpen((v) => !v)}
        className="w-11 h-11 rounded-full text-white flex items-center justify-center shadow-[0_8px_24px_-4px_rgba(15,23,42,0.35)]"
        style={{ background: 'linear-gradient(135deg, var(--brand), var(--brand-300))' }}
        title="主题配色设置"
      >
        <Palette size={18} />
      </motion.button>
    </div>
  );
}
