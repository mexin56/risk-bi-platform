import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Activity,
  Bell,
  ChevronDown,
  CircleDollarSign,
  Gauge,
  KeyRound,
  Target,
  Layers,
  LogOut,
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
import Lifecycle, { STAGES, type StageKey } from '@/pages/Lifecycle';
import Channel from '@/pages/Channel';
import Fraud from '@/pages/Fraud';
import Vintage from '@/pages/Vintage';
import ModelScore from '@/pages/ModelScore';
import Stability from '@/pages/Stability';
import CreditStrategy from '@/pages/CreditStrategy';
import CreditAttribution from '@/pages/CreditAttribution';
import UsersPage from '@/pages/Users';
import Login from '@/pages/Login';
import ThemeSettings from '@/components/ThemeSettings';
import { applyTheme, getTheme, type ThemePreset } from '@/lib/theme';
import {
  clearToken,
  fetchMe,
  getToken,
  hasPermission,
  logout as apiLogout,
  type AuthSession,
} from '@/lib/auth';

type PageKey = 'overview' | 'lifecycle' | 'creditStrategy' | 'attribution' | 'channel' | 'fraud' | 'vintage' | 'model' | 'stability' | 'users';

const NAV: { key: PageKey; label: string; icon: typeof Gauge; desc: string }[] = [
  { key: 'overview', label: '大盘数据', icon: Gauge, desc: '经营全景与资产质量' },
  { key: 'lifecycle', label: '客户生命周期', icon: Users, desc: '贷前·授信·交易·复贷·催收' },
  { key: 'creditStrategy', label: '提额策略监控', icon: CircleDollarSign, desc: '系数核验 · 额度目标 · 提额归因' },
  { key: 'attribution', label: '授信归因监控', icon: Target, desc: '异常归因 · Top-K · 专家归因' },
  { key: 'channel', label: '渠道质量', icon: Network, desc: '助贷渠道 · 通过率×风险×成本' },
  { key: 'fraud', label: '反欺诈监控', icon: ShieldAlert, desc: '规则命中 · 设备聚集 · 团伙预警' },
  { key: 'vintage', label: 'Vintage 监控', icon: Layers, desc: '账龄结构与 Cohort 表现' },
  { key: 'model', label: '模型分监控', icon: Activity, desc: 'PSI / KS / 分布漂移' },
  { key: 'stability', label: '模型稳定性', icon: ShieldCheck, desc: 'PSI趋势 · 迁移矩阵 · 漂移归因' },
  { key: 'users', label: '权限管理', icon: KeyRound, desc: '用户 · 角色 · 页面权限' },
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
  // 分享链接支持: 初始页面从 ?page= 恢复(无参数或非法值回落大盘)
  const [page, setPageState] = useState<PageKey>(() => {
    const value = new URLSearchParams(window.location.search).get('page');
    return NAV.some((n) => n.key === value) ? (value as PageKey) : 'overview';
  });
  const [collapsed, setCollapsed] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [themeKey, setThemeKey] = useState(getTheme().key);
  const [logoutOpen, setLogoutOpen] = useState(false);
  const [session, setSession] = useState<AuthSession | null>(null);
  const [authStatus, setAuthStatus] = useState<'loading' | 'guest' | 'authed'>('loading');
  const [stage, setStage] = useState<StageKey>('pre');
  const [lifeOpen, setLifeOpen] = useState(true);
  const active = NAV.find((n) => n.key === page)!;

  // 页面切换同步到地址栏(page 参数), 便于直接复制链接分享
  const setPage = (key: PageKey) => {
    setPageState(key);
    const url = new URL(window.location.href);
    if (key === 'overview') url.searchParams.delete('page');
    else url.searchParams.set('page', key);
    window.history.replaceState(null, '', url);
  };

  useEffect(() => {
    applyTheme(getTheme()); // 确保首屏 CSS 变量就位
  }, []);

  // 启动时恢复会话；token 缺失/失效则进入登录页
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const user = await fetchMe();
        if (alive) {
          setSession({ token: getToken() ?? '', user });
          setAuthStatus('authed');
        }
      } catch {
        if (alive) setAuthStatus('guest');
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  // 账号权限变化后，若当前页不可见则回到第一个可见页
  useEffect(() => {
    if (!session) return;
    const allowed = NAV.filter((n) =>
      n.key === 'users' ? hasPermission(session.user, 'users') : hasPermission(session.user, n.key),
    );
    if (allowed.length && !allowed.some((n) => n.key === page)) setPage(allowed[0].key);
  }, [session, page]);

  const handleTheme = (p: ThemePreset) => {
    applyTheme(p);
    setThemeKey(p.key);
  };

  const handleRefresh = () => {
    setRefreshing(true);
    setTimeout(() => setRefreshing(false), 900);
  };

  const handleLogout = async () => {
    setLogoutOpen(false);
    try {
      await apiLogout();
    } catch {
      /* 网络异常也照常清理本地会话 */
    }
    clearToken();
    setSession(null);
    setAuthStatus('guest');
    setPage('overview');
  };

  const handleNavClick = (key: PageKey) => {
    if (key === 'lifecycle') {
      if (page === 'lifecycle' && !collapsed) {
        setLifeOpen((v) => !v); // 已在本页：点击父级折叠/展开
      } else {
        setPage('lifecycle');
        setLifeOpen(true);
      }
    } else {
      setPage(key);
    }
  };

  const handleStageClick = (s: StageKey) => {
    setStage(s);
    setPage('lifecycle');
  };

  if (authStatus === 'loading') {
    return (
      <div className="h-screen flex flex-col items-center justify-center gap-4" style={{ background: 'var(--app-bg, #f4f6fa)' }}>
        <div
          className="w-14 h-14 rounded-2xl flex items-center justify-center"
          style={{ background: 'linear-gradient(135deg, var(--brand), var(--brand-300))', boxShadow: '0 12px 32px rgba(var(--brand-rgb),0.35)' }}
        >
          <ShieldCheck size={26} className="text-white" />
        </div>
        <div className="text-[13px] text-slate-400 animate-pulse">正在验证登录状态…</div>
      </div>
    );
  }

  if (authStatus === 'guest') {
    return <Login onSuccess={(s) => { setSession(s); setAuthStatus('authed'); }} />;
  }

  const visibleNav = session
    ? NAV.filter((n) => (n.key === 'users' ? hasPermission(session.user, 'users') : hasPermission(session.user, n.key)))
    : [];

  return (
    <div className="flex h-screen text-slate-800 overflow-hidden" style={{ background: 'var(--app-bg, #f4f6fa)' }}>
      {/* ============ 侧边栏（浅色） ============ */}
      <aside
        className={`relative shrink-0 flex flex-col bg-white border-r border-slate-200/80 transition-[width] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] ${
          collapsed ? 'w-[72px]' : 'w-[224px]'
        }`}
      >
        <div className="absolute top-0 left-0 w-full h-52 pointer-events-none" style={{ background: 'radial-gradient(ellipse at top left, rgba(var(--brand-rgb),0.07), transparent 65%)' }} />

        {/* 折叠开关（边缘悬浮） */}
        <button
          onClick={() => setCollapsed((v) => !v)}
          className="absolute -right-3.5 top-[72px] z-30 w-7 h-7 rounded-full bg-white border border-slate-200 shadow-md flex items-center justify-center text-slate-500 hover:text-blue-500 hover:border-blue-300 transition-colors"
          title={collapsed ? '展开导航' : '折叠导航'}
        >
          {collapsed ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={14} />}
        </button>

        {/* Logo */}
        <div className={`relative flex items-center h-16 border-b border-slate-100 ${collapsed ? 'justify-center px-0' : 'gap-2.5 px-5'}`}>
          <div
            className="w-8 h-8 rounded-xl flex items-center justify-center shrink-0"
            style={{ background: 'linear-gradient(135deg, var(--brand), var(--brand-300))', boxShadow: '0 4px 12px rgba(var(--brand-rgb),0.35)' }}
          >
            <ShieldCheck size={17} className="text-white" />
          </div>
          {!collapsed && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}>
              <div className="text-[14.5px] font-semibold leading-4 text-slate-800">风控BI平台</div>
              <div className="text-slate-400 text-[10px] tracking-wide mt-0.5">RiskControl BI Suite</div>
            </motion.div>
          )}
        </div>

        {!collapsed && (
          <div className="relative px-4 pt-5 pb-2 text-[10px] text-slate-400 tracking-[0.18em] font-medium whitespace-nowrap">
            监控看板 · MONITOR
          </div>
        )}
        {collapsed && <div className="pt-4" />}

        <nav className={`relative flex-1 space-y-1 overflow-y-auto custom-scroll ${collapsed ? 'px-2.5' : 'px-3'}`}>
          {visibleNav.map((n) => {
            const Icon = n.icon;
            const on = page === n.key;
            const isLife = n.key === 'lifecycle';
            return (
              <div key={n.key}>
                <button
                  onClick={() => handleNavClick(n.key)}
                  title={collapsed ? n.label : undefined}
                  className={`relative w-full flex items-center rounded-xl transition-colors duration-200 ${
                    collapsed ? 'justify-center py-3' : 'gap-3 px-3 py-2.5'
                  } ${on ? 'text-slate-800' : 'text-slate-500 hover:text-slate-800 hover:bg-slate-50'}`}
                >
                  {on && (
                    <motion.div
                      layoutId="nav-pill"
                      className="absolute inset-0 rounded-xl border"
                      style={{
                        background: 'linear-gradient(90deg, rgba(var(--brand-rgb),0.13), rgba(var(--brand-rgb),0.05))',
                        borderColor: 'rgba(var(--brand-rgb),0.22)',
                      }}
                      transition={{ type: 'spring', stiffness: 420, damping: 34 }}
                    />
                  )}
                  <div
                    className="relative w-7 h-7 rounded-lg flex items-center justify-center shrink-0 transition-colors"
                    style={
                      on
                        ? { background: 'rgba(var(--brand-rgb),0.14)', color: 'var(--brand)' }
                        : { background: 'rgba(100,116,139,0.07)' }
                    }
                  >
                    <Icon size={15} />
                  </div>
                  {!collapsed && (
                    <div className="relative text-left">
                      <div className="text-[13.5px] font-medium whitespace-nowrap">{n.label}</div>
                    </div>
                  )}
                  {/* 父级右侧：生命周期为展开箭头，其余为激活光点 */}
                  {on && !collapsed && !isLife && (
                    <motion.div
                      layoutId="nav-dot"
                      className="relative ml-auto w-1.5 h-1.5 rounded-full"
                      style={{ background: 'var(--brand)', boxShadow: '0 0 8px rgba(var(--brand-rgb),0.7)' }}
                    />
                  )}
                  {isLife && !collapsed && (
                    <motion.div
                      animate={{ rotate: lifeOpen ? 180 : 0 }}
                      transition={{ duration: 0.25 }}
                      className="relative ml-auto text-slate-400"
                    >
                      <ChevronDown size={14} />
                    </motion.div>
                  )}
                </button>

                {/* ============ 二级菜单：生命周期五环节 ============ */}
                {isLife && !collapsed && (
                  <AnimatePresence initial={false}>
                    {lifeOpen && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
                        className="overflow-hidden"
                      >
                        <div className="ml-[26px] mt-1 mb-1 pl-3 border-l-2 border-slate-100 space-y-0.5">
                          {STAGES.map((s) => {
                            const SIcon = s.icon;
                            const subOn = page === 'lifecycle' && stage === s.key;
                            return (
                              <button
                                key={s.key}
                                onClick={() => handleStageClick(s.key)}
                                className={`relative w-full flex items-center gap-2 px-2.5 py-[7px] rounded-lg text-left transition-colors duration-150 ${
                                  subOn
                                    ? 'font-medium'
                                    : 'text-slate-500 hover:text-slate-800 hover:bg-slate-50'
                                }`}
                                style={subOn ? { color: 'var(--brand)', background: 'rgba(var(--brand-rgb),0.08)' } : undefined}
                              >
                                {subOn && (
                                  <motion.span
                                    layoutId="life-sub-marker"
                                    className="absolute -left-[14px] top-1/2 -translate-y-1/2 w-[3px] h-[16px] rounded-full"
                                    style={{ background: 'var(--brand)' }}
                                    transition={{ type: 'spring', stiffness: 480, damping: 36 }}
                                  />
                                )}
                                <SIcon size={13} className="shrink-0" />
                                <span className="text-[12.5px] whitespace-nowrap">{s.label}</span>
                              </button>
                            );
                          })}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                )}
              </div>
            );
          })}
        </nav>

        {/* ============ 左下角用户操作区 ============ */}
        <div className={`relative border-t border-slate-100 ${collapsed ? 'px-2.5 py-3' : 'p-3.5'}`}>
          <div className={`flex items-center ${collapsed ? 'justify-center' : 'gap-2.5 px-1.5'}`}>
            <div className="relative shrink-0">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center text-white text-[12px] font-semibold ring-2 ring-emerald-100">
                {(session?.user.display_name || '用').slice(0, 1)}
              </div>
              <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-400 border-2 border-white" />
            </div>
            {!collapsed && (
              <div className="min-w-0">
                <div className="text-slate-700 text-[12.5px] font-medium whitespace-nowrap">{session?.user.display_name}</div>
                <div className="text-slate-400 text-[10px] whitespace-nowrap">{session?.user.role_name} · {session?.user.username}</div>
              </div>
            )}
          </div>

          <div className={`mt-2.5 flex ${collapsed ? 'flex-col items-center gap-1.5' : 'gap-1.5'}`}>
            <ThemeSettings currentKey={themeKey} onChange={handleTheme} collapsed={collapsed} />
            <button
              onClick={() => setLogoutOpen(true)}
              title="退出登录"
              className={`flex items-center rounded-lg text-slate-500 hover:text-rose-500 hover:bg-rose-50 transition-colors duration-200 ${
                collapsed ? 'w-9 h-9 justify-center' : 'flex-1 gap-2 px-2.5 py-2'
              }`}
            >
              <LogOut size={15} className="shrink-0" />
              {!collapsed && <span className="text-[12px] font-medium whitespace-nowrap">退出登录</span>}
            </button>
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

        <main className="relative flex-1 overflow-y-auto p-5 custom-scroll">
          {/* 环境光斑：毛玻璃卡片背后的色彩来源 */}
          <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
            <div
              className="absolute -top-24 -left-20 w-[480px] h-[480px] rounded-full"
              style={{ background: 'radial-gradient(circle at center, rgba(var(--brand-rgb),0.20), transparent 62%)', filter: 'blur(50px)' }}
            />
            <div
              className="absolute top-[38%] -right-28 w-[420px] h-[420px] rounded-full"
              style={{ background: 'radial-gradient(circle at center, rgba(54,201,201,0.16), transparent 62%)', filter: 'blur(56px)' }}
            />
            <div
              className="absolute -bottom-28 left-[30%] w-[500px] h-[380px] rounded-full"
              style={{ background: 'radial-gradient(circle at center, rgba(127,107,242,0.15), transparent 62%)', filter: 'blur(60px)' }}
            />
            <div
              className="absolute top-[10%] left-[45%] w-[360px] h-[360px] rounded-full"
              style={{ background: 'radial-gradient(circle at center, rgba(255,176,32,0.10), transparent 62%)', filter: 'blur(48px)' }}
            />
          </div>
          <div className="relative">
          <AnimatePresence mode="wait">
            <motion.div
              key={page}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            >
              {page === 'overview' && <Overview />}
              {page === 'lifecycle' && <Lifecycle stage={stage} />}
              {page === 'creditStrategy' && <CreditStrategy />}
              {page === 'attribution' && <CreditAttribution />}
              {page === 'channel' && <Channel />}
              {page === 'fraud' && <Fraud />}
              {page === 'vintage' && <Vintage />}
              {page === 'model' && <ModelScore />}
              {page === 'stability' && <Stability />}
              {page === 'users' && session && <UsersPage currentUser={session.user} />}
            </motion.div>
          </AnimatePresence>
          </div>
        </main>

        <footer className="h-8 shrink-0 flex items-center justify-center gap-2 text-[10.5px] text-slate-400 border-t border-slate-200/80 bg-white/80 backdrop-blur">
          <span className="w-1 h-1 rounded-full" style={{ background: 'var(--brand)' }} />
          风控BI监控平台 · 演示数据仅供产品原型参考 · 指标口径：T-1 日终跑批
        </footer>
      </div>

      {/* ============ 退出登录确认弹窗 ============ */}
      <AnimatePresence>
        {logoutOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-[90] bg-slate-900/30 backdrop-blur-[2px]"
              onClick={() => setLogoutOpen(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.92, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.92, y: 12 }}
              transition={{ type: 'spring', stiffness: 420, damping: 30 }}
              className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-[95] w-[320px] bg-white rounded-2xl shadow-[0_24px_64px_-16px_rgba(15,23,42,0.35)] p-6"
            >
              <div
                className="w-11 h-11 rounded-full mx-auto flex items-center justify-center mb-3"
                style={{ background: 'rgba(var(--brand-rgb),0.10)', color: 'var(--brand)' }}
              >
                <LogOut size={18} />
              </div>
              <div className="text-center text-[15px] font-semibold text-slate-800">退出登录</div>
              <div className="text-center text-[12px] text-slate-400 mt-1.5 mb-5">确定要退出当前账号吗？未保存的看板配置将保留在本地。</div>
              <div className="flex gap-2.5">
                <button
                  onClick={() => setLogoutOpen(false)}
                  className="flex-1 py-2.5 rounded-xl border border-slate-200 text-[13px] text-slate-600 hover:bg-slate-50 transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={handleLogout}
                  className="flex-1 py-2.5 rounded-xl text-[13px] text-white transition-opacity hover:opacity-90"
                  style={{ background: 'linear-gradient(135deg, var(--brand), var(--brand-300))' }}
                >
                  确认退出
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
