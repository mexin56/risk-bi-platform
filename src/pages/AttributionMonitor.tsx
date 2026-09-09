import { useState } from 'react';
import { LockKeyhole } from 'lucide-react';
import { motion } from 'framer-motion';
import CreditAttribution from '@/pages/CreditAttribution';
import FundAttribution from '@/pages/FundAttribution';
import {
  buildAttributionUrl,
  defaultAttributionTab,
  normalizeAttributionTab,
  visibleAttributionTabs,
  type AttributionTab,
} from '@/lib/attributionTab';
import { hasPermission, type AuthUser } from '@/lib/auth';

const TAB_META: Record<AttributionTab, { label: string; description: string }> = {
  credit: { label: '授信归因监控', description: '异常归因 · Top-K · 专家归因' },
  fund: { label: '资金归结监控', description: '异常订单 · 中介团伙路径' },
};

function requestedTab(): AttributionTab {
  const query = new URLSearchParams(window.location.search);
  if (query.get('tab')) return normalizeAttributionTab(query.get('tab'));
  return query.get('page') === 'fundMonitor' ? 'fund' : 'credit';
}

export default function AttributionMonitor({ user }: { user: AuthUser }) {
  const canCredit = hasPermission(user, 'attribution');
  const canFund = hasPermission(user, 'fundMonitor');
  const tabs = visibleAttributionTabs(canCredit, canFund);
  const fallback = defaultAttributionTab(canCredit, canFund);
  const initial = requestedTab();
  const [activeTab, setActiveTab] = useState<AttributionTab>(
    tabs.includes(initial) ? initial : (fallback ?? 'credit'),
  );

  const selectTab = (tab: AttributionTab) => {
    const next = buildAttributionUrl(window.location.href, tab);
    window.history.replaceState(null, '', next);
    setActiveTab(tab);
  };

  if (!fallback) {
    return (
      <div className="flex min-h-[520px] flex-col items-center justify-center rounded-2xl border border-slate-200 bg-white/60 text-center">
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-400">
          <LockKeyhole size={22} />
        </div>
        <div className="text-[15px] font-semibold text-slate-700">暂无归因监控权限</div>
        <div className="mt-2 text-[12px] text-slate-400">请联系管理员开通授信归因或资金归结监控权限</div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1440px] space-y-3 pb-2" data-testid="attribution-monitor-content">
      <div role="tablist" aria-label="归因监控类型" className="flex items-center gap-1 border-b border-slate-200/80">
        {tabs.map((tab) => {
          const active = tab === activeTab;
          const meta = TAB_META[tab];
          return (
            <button
              key={tab}
              role="tab"
              aria-selected={active}
              onClick={() => selectTab(tab)}
              className={`relative min-w-[150px] rounded-t-lg px-4 py-2.5 text-left transition-colors ${
                active ? 'bg-white/70 text-blue-600' : 'text-slate-400 hover:bg-white/50 hover:text-slate-600'
              }`}
            >
              {active && (
                <motion.span
                  layoutId="attribution-tab-indicator"
                  className="absolute inset-x-3 bottom-0 h-0.5 rounded-full bg-blue-500"
                />
              )}
              <div className="text-[12.5px] font-semibold">{meta.label}</div>
              <div className="mt-0.5 text-[10px] text-slate-400">{meta.description}</div>
            </button>
          );
        })}
      </div>
      {activeTab === 'credit' ? <CreditAttribution /> : <FundAttribution />}
    </div>
  );
}
