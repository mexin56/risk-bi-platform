import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Activity,
  Bell,
  Gauge,
  Layers,
  RefreshCw,
  Search,
  ShieldCheck,
  Users,
} from 'lucide-react';
import Overview from '@/pages/Overview';
import Lifecycle from '@/pages/Lifecycle';
import Vintage from '@/pages/Vintage';
import ModelScore from '@/pages/ModelScore';

type PageKey = 'overview' | 'lifecycle' | 'vintage' | 'model';

const NAV: { key: PageKey; label: string; icon: typeof Gauge; desc: string }[] = [
  { key: 'overview', label: '大盘数据', icon: Gauge, desc: '经营全景与资产质量' },
  { key: 'lifecycle', label: '客户生命周期', icon: Users, desc: '转化漏斗与留存复借' },
  { key: 'vintage', label: 'Vintage 监控', icon: Layers, desc: '账龄结构与 Cohort 表现' },
  { key: 'model', label: '模型分监控', icon: Activity, desc: 'PSI / KS / 分布漂移' },
];

function LiveClock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    <div className="text-right leading-tight">
      <div className="text-[13px] font-semibold text-slate-700 tabular-nums">
        {pad(now.getHours())}:{pad(now.getMinutes())}:{pad(now.getSeconds())}
      </div>
      <div className="text-[10px] text-slate-400">
        {now.getMonth() + 1}月{now.getDate()}日 · 周{'日一二三四五六'[now.getDay()]}
      </div>
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState<PageKey>('overview');
  const [refreshing, setRefreshing] = useState(false);
  const active = NAV.find((n) => n.key === page)!;

  const handleRefresh = () => {
    setRefreshing(true);
    setTimeout(() => setRefreshing(false), 900);
  };

  return (
    <div className="flex h-screen bg-[#f4f6fa] text-slate-800 overflow-hidden">
      {/* ============ 侧边栏 ============ */}
      <aside className="w-[224px] shrink-0 relative flex flex-col bg-gradient-to-b from-[#0d1830] via-[#101b33] to-[#0c1526]">
        {/* 背景装饰光斑 */}
        <div className="absolute top-0 left-0 w-full h-52 bg-[radial-gradient(ellipse_at_top_left,rgba(78,131,253,0.16),transparent_65%)] pointer-events-none" />

        <div className="relative flex items-center gap-2.5 px-5 h-16 border-b border-white/[0.07]">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-blue-400 via-blue-500 to-indigo-600 flex items-center justify-center shadow-[0_4px_12px_rgba(59,110,246,0.45)]">
            <ShieldCheck size={17} className="text-white" />
          </div>
          <div>
            <div className="text-[14.5px] font-semibold leading-4 bg-gradient-to-r from-white to-blue-200 bg-clip-text text-transparent">
              风控BI平台
            </div>
            <div className="text-slate-500 text-[10px] tracking-wide mt-0.5">RiskControl BI Suite</div>
          </div>
        </div>

        <div className="relative px-4 pt-5 pb-2 text-[10px] text-slate-500 tracking-[0.18em] font-medium">
          监控看板 · MONITOR
        </div>

        <nav className="relative flex-1 px-3 space-y-1">
          {NAV.map((n) => {
            const Icon = n.icon;
            const on = page === n.key;
            return (
              <button
                key={n.key}
                onClick={() => setPage(n.key)}
                className={`relative w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left transition-colors duration-200 ${
                  on ? 'text-white' : 'text-slate-400 hover:text-slate-100 hover:bg-white/[0.05]'
                }`}
              >
                {on && (
                  <motion.div
                    layoutId="nav-pill"
                    className="absolute inset-0 rounded-xl bg-gradient-to-r from-blue-500/25 to-indigo-500/10 border border-blue-400/25"
                    transition={{ type: 'spring', stiffness: 420, damping: 34 }}
                  />
                )}
                <div
                  className={`relative w-7 h-7 rounded-lg flex items-center justify-center transition-colors ${
                    on ? 'bg-blue-500/30 text-blue-300' : 'bg-white/[0.04]'
                  }`}
                >
                  <Icon size={15} />
                </div>
                <div className="relative">
                  <div className="text-[13px] font-medium leading-4">{n.label}</div>
                  <div className={`text-[10px] mt-0.5 ${on ? 'text-blue-300/70' : 'opacity-50'}`}>
                    {n.desc}
                  </div>
                </div>
                {on && (
                  <motion.div
                    layoutId="nav-dot"
                    className="relative ml-auto w-1.5 h-1.5 rounded-full bg-blue-400 shadow-[0_0_8px_rgba(96,165,250,0.9)]"
                  />
                )}
              </button>
            );
          })}
        </nav>

        <div className="relative p-4 border-t border-white/[0.07]">
          <div className="flex items-center gap-2.5">
            <div className="relative">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center text-white text-[12px] font-semibold">
                模
              </div>
              <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-400 border-2 border-[#0d1830] animate-pulse" />
            </div>
            <div>
              <div className="text-slate-200 text-[12px]">风控模型组</div>
              <div className="text-slate-500 text-[10px]">数据更新于 08:30</div>
            </div>
          </div>
        </div>
      </aside>

      {/* ============ 主区域 ============ */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* 顶栏 */}
        <header className="h-16 shrink-0 bg-white/85 backdrop-blur-md border-b border-slate-200/80 flex items-center px-6 gap-4 z-20">
          <AnimatePresence mode="wait">
            <motion.div
              key={page}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 8 }}
              transition={{ duration: 0.22 }}
            >
              <div className="text-[15.5px] font-semibold tracking-tight">{active.label}</div>
              <div className="text-[11px] text-slate-400 mt-0.5">{active.desc}</div>
            </motion.div>
          </AnimatePresence>

          <div className="ml-auto flex items-center gap-3">
            <div className="flex items-center gap-2 bg-slate-100/80 rounded-lg px-3 py-2 text-[12px] text-slate-400 w-56 border border-transparent focus-within:border-blue-300 focus-within:bg-white transition-colors">
              <Search size={14} />
              搜索指标 / 报表 / 模型
              <kbd className="ml-auto text-[10px] bg-white border border-slate-200 rounded px-1 py-0.5 text-slate-400">⌘K</kbd>
            </div>

            <div className="flex items-center gap-1.5 text-[11px] text-slate-500 border border-slate-200 rounded-lg px-2.5 py-2 bg-white">
              <span className="relative flex w-1.5 h-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
              </span>
              数据日期 T-1
            </div>

            <button
              onClick={handleRefresh}
              className="p-2 rounded-lg text-slate-400 hover:text-blue-500 hover:bg-blue-50 transition-colors"
              title="刷新数据"
            >
              <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
            </button>

            <button className="relative p-2 rounded-lg text-slate-400 hover:text-blue-500 hover:bg-blue-50 transition-colors">
              <Bell size={16} />
              <span className="absolute top-1 right-1 min-w-[14px] h-[14px] px-0.5 rounded-full bg-rose-500 text-white text-[9px] flex items-center justify-center font-medium">
                3
              </span>
            </button>

            <div className="w-px h-6 bg-slate-200" />
            <LiveClock />
          </div>
        </header>

        {/* 页面内容 */}
        <main className="flex-1 overflow-y-auto p-5 custom-scroll">
          <AnimatePresence mode="wait">
            <motion.div
              key={page}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            >
              {page === 'overview' && <Overview />}
              {page === 'lifecycle' && <Lifecycle />}
              {page === 'vintage' && <Vintage />}
              {page === 'model' && <ModelScore />}
            </motion.div>
          </AnimatePresence>
        </main>

        <footer className="h-8 shrink-0 flex items-center justify-center gap-2 text-[10.5px] text-slate-400 border-t border-slate-200/80 bg-white/80 backdrop-blur">
          <span className="w-1 h-1 rounded-full bg-blue-400" />
          风控BI监控平台 · 演示数据仅供产品原型参考 · 指标口径：T-1 日终跑批
        </footer>
      </div>
    </div>
  );
}
