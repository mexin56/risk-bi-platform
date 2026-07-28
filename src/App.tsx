import { useState } from 'react';
import {
  Activity,
  Gauge,
  Layers,
  Bell,
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
  { key: 'vintage', label: 'Vintage 监控', icon: Layers, desc: '账龄结构与cohort表现' },
  { key: 'model', label: '模型分监控', icon: Activity, desc: 'PSI / KS / 分布漂移' },
];

export default function App() {
  const [page, setPage] = useState<PageKey>('overview');
  const active = NAV.find((n) => n.key === page)!;

  return (
    <div className="flex h-screen bg-[#f5f7fa] text-slate-800 overflow-hidden">
      {/* ============ 侧边栏 ============ */}
      <aside className="w-[218px] shrink-0 bg-[#101b33] flex flex-col">
        <div className="flex items-center gap-2.5 px-5 h-14 border-b border-white/10">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-400 to-indigo-500 flex items-center justify-center">
            <ShieldCheck size={16} className="text-white" />
          </div>
          <div>
            <div className="text-white text-[14px] font-semibold leading-4">风控BI平台</div>
            <div className="text-slate-400 text-[10px]">RiskControl BI Suite</div>
          </div>
        </div>

        <div className="px-3 pt-4 pb-2 text-[10px] text-slate-500 tracking-widest">
          监控看板
        </div>
        <nav className="flex-1 px-3 space-y-1">
          {NAV.map((n) => {
            const Icon = n.icon;
            const on = page === n.key;
            return (
              <button
                key={n.key}
                onClick={() => setPage(n.key)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors ${
                  on
                    ? 'bg-blue-500/15 text-blue-300'
                    : 'text-slate-400 hover:bg-white/5 hover:text-slate-200'
                }`}
              >
                <Icon size={17} />
                <div>
                  <div className="text-[13px] font-medium leading-4">{n.label}</div>
                  <div className="text-[10px] opacity-60 mt-0.5">{n.desc}</div>
                </div>
                {on && <div className="ml-auto w-1.5 h-1.5 rounded-full bg-blue-400" />}
              </button>
            );
          })}
        </nav>

        <div className="p-4 border-t border-white/10">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center text-white text-[12px] font-semibold">
              模
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
        <header className="h-14 shrink-0 bg-white border-b border-slate-200 flex items-center px-6 gap-4">
          <div>
            <div className="text-[15px] font-semibold">{active.label}</div>
            <div className="text-[11px] text-slate-400">{active.desc}</div>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <div className="flex items-center gap-2 bg-slate-100 rounded-lg px-3 py-1.5 text-[12px] text-slate-400 w-56">
              <Search size={14} />
              搜索指标 / 报表
            </div>
            <div className="flex items-center gap-1.5 text-[11px] text-slate-400 border border-slate-200 rounded-lg px-2.5 py-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              数据日期 T-1
            </div>
            <button className="relative p-2 text-slate-400 hover:text-slate-600">
              <Bell size={17} />
              <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-rose-500" />
            </button>
          </div>
        </header>

        {/* 页面内容 */}
        <main className="flex-1 overflow-y-auto p-5">
          {page === 'overview' && <Overview />}
          {page === 'lifecycle' && <Lifecycle />}
          {page === 'vintage' && <Vintage />}
          {page === 'model' && <ModelScore />}
        </main>

        <footer className="h-8 shrink-0 flex items-center justify-center text-[10.5px] text-slate-400 border-t border-slate-200 bg-white">
          风控BI监控平台 · 演示数据仅供产品原型参考 · 指标口径：T-1 日终跑批
        </footer>
      </div>
    </div>
  );
}
