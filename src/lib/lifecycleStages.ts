import { BadgeCheck, Coins, PhoneCall, Repeat2, UserPlus, type LucideIcon } from 'lucide-react';

export type StageKey = 'pre' | 'credit' | 'loan' | 'reloan' | 'collect';

// Sidebar navigation stays independent of the lifecycle charts.
export const STAGES: { key: StageKey; label: string; icon: LucideIcon; hint: string }[] = [
  { key: 'pre', label: '贷前注册', icon: UserPlus, hint: '注册→实名→KYC→授信申请' },
  { key: 'credit', label: '授信环节', icon: BadgeCheck, hint: '机审/终审/额度/定价' },
  { key: 'loan', label: '交易环节', icon: Coins, hint: '支用→放款→期限结构' },
  { key: 'reloan', label: '复贷环节', icon: Repeat2, hint: '留存/复借/客户分层' },
  { key: 'collect', label: '催收环节', icon: PhoneCall, hint: '入催/滚动率/委外' },
];
