import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Activity,
  Bell,
  Gauge,
  Layers,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Users,
} from 'lucide-react';
import Overview from '@/pages/Overview';
import Lifecycle from '@/pages/Lifecycle';
import Channel from '@/pages/Channel';
import Fraud from '@/pages/Fraud';
import Vintage from '@/pages/Vintage';
import ModelScore from '@/pages/ModelScore';
import ThemeSettings from '@/components/ThemeSettings';
import { applyTheme, getTheme, type ThemePreset } from '@/lib/theme';

type PageKey = 'overview' | 'lifecycle' | 'channel' | 'fraud' | 'vintage' | 'model';

const NAV: { key: PageKey; label: string; icon: typeof Gauge; desc: string }[] = [
  { key: 'overview', label: '大盘数据', icon: Gauge, desc: '经营全景与资产质量' },
  { key: 'lifecycle', label: '客户生命周期', icon: Users, desc: '贷前·授信·交易·复贷·催收' },
  { key: 'channel', label: '渠道质量', icon: Network, desc: '助贷渠道 · 通过率×风险×成本' },
  { key: 'fraud', label: '反欺诈监控', icon: ShieldAlert, desc: '规则命中 · 设备聚集 · 团伙预警' },
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
    <div className="text-right leading-tight shrink-0">
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
  const [collapsed, setCollapsed] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [themeKey, setThemeKey] = useState(getTheme().key);
  const active = NAV.find((n) => n.key === page)!;

  useEffect(() => {
    applyTheme(getTheme()); // 确保首屏 CSS 变量就位
  }, []);

  const handleTheme = (p: ThemePreset) => {
    applyTheme(p);
    setThemeKey(p.key);
  };

  const handleRefresh = () => {
    setRefreshing(true);
    setTimeout(() => setRefreshing(false), 900);
  };

  return (
    <div className="flex h-screen text-slate-800 overflow-hidden" style={{ background: 'var(--app-bg, #f4f6fa)' }}>
      {/* ============ 侧边栏 ============ */}
      <aside
        className={`relative shrink-0 flex flex-col bg-gradient-to-b from-[#0d1830] via-[#101b33] to-[#0c1526] transition-[width] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] ${
          collapsed ? 'w-[72px]' : 'w-[224px]'
        }`}
      >
        <div className="absolute top-0 left-0 w-full h-52 bg-[radial-gradient(ellipse_at_top_left,rgba(78,131,253,0.16),transparent_65%)] pointer-events-none" />

        {/* 折叠开关（边缘悬浮） */}
        <button
          onClick={() => setCollapsed((v) => !v)}
          className="absolute -right-3.5 top-[72px] z-30 w-7 h-7 rounded-full bg-white border border-slate-200 shadow-md flex items-center justify-center text-slate-500 hover:text-blue-500 hover:border-blue-300 transition-colors"
          title={collapsed ? '展开导航' : '折叠导航'}
        >
          {collapsed ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={14} />}
        </button>

        {/* Logo */}
        <div className={`relative flex items-center h-16 border-b border-white/[0.07] ${collapsed ? 'justify-center px-0' : 'gap-2.5 px-5'}`}>
          <div
            className="w-8 h-8 rounded-xl flex items-center justify-center shrink-0 shadow-lg"
            style={{ background: 'linear-gradient(135deg, var(--brand), var(--brand-300))' }}
          >
            <ShieldCheck size={17} className="text-white" />
          </div>
          {!collapsed && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}>
              <div className="text-[14.5px] font-semibold leading-4 text-white">风控BI平台</div>
              <div className="text-slate-500 text-[10px] tracking-wide mt-0.5">RiskControl BI Suite</div>
            </motion.div>
          )}
        </div>

        {!collapsed && (
          <div className="relative px-4 pt-5 pb-2 text-[10px] text-slate-500 tracking-[0.18em] font-medium whitespace-nowrap">
            监控看板 · MONITOR
          </div>
        )}
        {collapsed && <div className="pt-4" />}

        <nav className={`relative flex-1 space-y-1 ${collapsed ? 'px-2.5' : 'px-3'}`}>
          {NAV.map((n) => {
            const Icon = n.icon;
            const on = page === n.key;
            return (
              <button
                key={n.key}
                onClick={() => setPage(n.key)}
                title={collapsed ? n.label : undefined}
                className={`relative w-full flex items-center rounded-xl transition-colors duration-200 ${
                  collapsed ? 'justify-center py-3' : 'gap-3 px-3 py-2.5'
                } ${on ? 'text-white' : 'text-slate-400 hover:text-slate-100 hover:bg-white/[0.05]'}`}
              >
                {on && (
                  <motion.div
                    layoutId="nav-pill"
                    className="absolute inset-0 rounded-xl border"
                    style={{
                      background: 'linear-gradient(90deg, rgba(var(--brand-rgb),0.28), rgba(var(--brand-rgb),0.10))',
                      borderColor: 'rgba(var(--brand-rgb),0.35)',
                    }}
                    transition={{ type: 'spring', stiffness: 420, damping: 34 }}
                  />
                )}
                <div
                  className="relative w-7 h-7 rounded-lg flex items-center justify-center shrink-0 transition-colors"
                  style={
                    on
                      ? { background: 'rgba(var(--brand-rgb),0.32)', color: 'var(--brand-300)' }
                      : { background: 'rgba(255,255,255,0.04)' }
                  }
                >
                  <Icon size={15} />
                </div>
                {!collapsed && (
                  <div className="relative text-left">
                    <div className="text-[13px] font-medium leading-4 whitespace-nowrap">{n.label}</div>
                    <div className="text-[10px] mt-0.5 whitespace-nowrap" style={{ color: on ? 'var(--brand-300)' : 'rgba(148,163,184,0.5)' }}>
                      {n.desc}
                    </div>
                  </div>
                )}
                {on && !collapsed && (
                  <motion.div
                    layoutId="nav-dot"
                    className="relative ml-auto w-1.5 h-1.5 rounded-full"
                    style={{ background: 'var(--brand-300)', boxShadow: '0 0 8px rgba(var(--brand-rgb),0.9)' }}
                  />
                )}
              </button>
            );
          })}
        </nav>

        {/* 底部用户 */}
        <div className={`relative border-t border-white/[0.07] ${collapsed ? 'p-3 flex justify-center' : 'p-4'}`}>
          <div className="flex items-center gap-2.5">
            <div className="relative shrink-0">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center text-white text-[12px] font-semibold">
                模
              </div>
              <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-400 border-2 border-[#0d1830] animate-pulse" />
            </div>
            {!collapsed && (
              <div>
                <div className="text-slate-200 text-[12px] whitespace-nowrap">风控模型组</div>
                <div className="text-slate-500 text-[10px] whitespace-nowrap">数据更新于 08:30</div>
              </div>
            )}
          </div>
        </div>
      </aside>

      {/* ============ 主区域 ============ */}
      <div className="flex-1 flex flex-col min-w-0">
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
            <div className="hidden lg:flex items-center gap-2 bg-slate-100/80 rounded-lg px-3 py-2 text-[12px] text-slate-400 w-56 border border-transparent focus-within:border-blue-300 focus-within:bg-white transition-colors">
              <Search size={14} />
              <span className="whitespace-nowrap">搜索指标 / 报表 / 模型</span>
              <kbd className="ml-auto text-[10px] bg-white border border-slate-200 rounded px-1 py-0.5 text-slate-400">⌘K</kbd>
            </div>

            <div className="flex items-center gap-1.5 text-[11px] text-slate-500 border border-slate-200 rounded-lg px-2.5 py-2 bg-white whitespace-nowrap">
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
              {page === 'channel' && <Channel />}
              {page === 'fraud' && <Fraud />}
              {page === 'vintage' && <Vintage />}
              {page === 'model' && <ModelScore />}
            </motion.div>
          </AnimatePresence>
        </main>

        <footer className="h-8 shrink-0 flex items-center justify-center gap-2 text-[10.5px] text-slate-400 border-t border-slate-200/80 bg-white/80 backdrop-blur">
          <span className="w-1 h-1 rounded-full" style={{ background: 'var(--brand)' }} />
          风控BI监控平台 · 演示数据仅供产品原型参考 · 指标口径：T-1 日终跑批
        </footer>
      </div>

      {/* 右下角主题配色设置 */}
      <ThemeSettings currentKey={themeKey} onChange={handleTheme} />
    </div>
  );
}
