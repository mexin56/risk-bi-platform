// ==================== 风控BI监控平台 · 模拟数据层 ====================
// 使用固定种子的伪随机数，保证每次刷新数据稳定

function seededRandom(seed: number) {
  let s = seed;
  return () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
}

// ---------- 工具 ----------
export interface DailyPoint {
  date: string;
  [key: string]: number | string;
}

function lastNDays(n: number): string[] {
  const res: string[] = [];
  const today = new Date();
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(today.getTime() - i * 86400000);
    res.push(`${d.getMonth() + 1}/${d.getDate()}`);
  }
  return res;
}

function lastNMonths(n: number): string[] {
  const res: string[] = [];
  const now = new Date();
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    res.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
  }
  return res;
}

// ---------- 1. 大盘数据 ----------
export interface OverviewKpi {
  label: string;
  value: string;
  unit?: string;
  mom: number; // 环比 %
  good_when_down?: boolean;
}

export const overviewKpis: OverviewKpi[] = [
  { label: '当日申请量', value: '48,216', unit: '件', mom: 6.8 },
  { label: '审批通过率', value: '32.4', unit: '%', mom: -1.2, good_when_down: true },
  { label: '当日放款金额', value: '6,842', unit: '万元', mom: 4.5 },
  { label: '在贷余额', value: '86.3', unit: '亿元', mom: 1.8 },
  { label: '首逾率 (FPD7)', value: '1.06', unit: '%', mom: 0.08, good_when_down: true },
  { label: 'M1+ 逾期率', value: '3.82', unit: '%', mom: 0.15, good_when_down: true },
  { label: 'M3+ 不良率', value: '1.64', unit: '%', mom: -0.05, good_when_down: true },
  { label: '30日复借率', value: '41.7', unit: '%', mom: 2.3 },
];

export function getLoanTrend(): DailyPoint[] {
  const rnd = seededRandom(42);
  return lastNDays(30).map((date, i) => {
    const weekend = i % 7 === 5 || i % 7 === 6 ? 0.82 : 1;
    return {
      date,
      放款金额: Math.round((5200 + rnd() * 1800 + i * 35) * weekend),
      申请量: Math.round((38000 + rnd() * 14000 + i * 220) * weekend),
      通过量: Math.round((12500 + rnd() * 3800 + i * 60) * weekend),
    };
  });
}

export function getOverdueTrend(): DailyPoint[] {
  const rnd = seededRandom(7);
  return lastNDays(30).map((date, i) => ({
    date,
    'DPD1+': +(4.6 + Math.sin(i / 5) * 0.35 + rnd() * 0.2).toFixed(2),
    'M1+': +(3.6 + Math.sin(i / 6 + 1) * 0.28 + rnd() * 0.15).toFixed(2),
    'M3+': +(1.55 + Math.sin(i / 8 + 2) * 0.16 + rnd() * 0.08).toFixed(2),
  }));
}

export const channelPie = [
  { name: 'APP自然流量', value: 32.5 },
  { name: '信息流投放', value: 24.8 },
  { name: 'API导流', value: 18.2 },
  { name: '应用商店', value: 12.4 },
  { name: '老客复借', value: 8.6 },
  { name: '其他渠道', value: 3.5 },
];

export interface ProductRow {
  product: string;
  balance: string; // 在贷余额
  dailyLoan: string; // 日放款
  passRate: number;
  fpd7: number;
  m1: number;
  m3: number;
  vintageM6: number; // M6 vintage M1+
}

export const productTable: ProductRow[] = [
  { product: '信用贷-标准', balance: '38.2亿', dailyLoan: '2,860万', passRate: 34.1, fpd7: 0.92, m1: 3.42, m3: 1.38, vintageM6: 4.86 },
  { product: '信用贷-大额', balance: '21.6亿', dailyLoan: '1,520万', passRate: 26.8, fpd7: 1.28, m1: 4.15, m3: 1.92, vintageM6: 5.94 },
  { product: '消费分期', balance: '15.4亿', dailyLoan: '1,240万', passRate: 38.5, fpd7: 0.84, m1: 3.05, m3: 1.22, vintageM6: 4.32 },
  { product: '小微经营贷', balance: '8.6亿', dailyLoan: '860万', passRate: 21.3, fpd7: 1.65, m1: 4.88, m3: 2.46, vintageM6: 7.12 },
  { product: '白名单预授信', balance: '2.5亿', dailyLoan: '362万', passRate: 62.7, fpd7: 0.42, m1: 1.86, m3: 0.68, vintageM6: 2.54 },
];

// ---------- 2. 客户生命周期 ----------
export interface FunnelStage {
  stage: string;
  value: number;
  conv: number | null; // 相对上一环节转化率 %
}

export const lifecycleFunnel: FunnelStage[] = [
  { stage: '进件申请', value: 48216, conv: null },
  { stage: '实名认证通过', value: 42108, conv: 87.3 },
  { stage: '授信审批完成', value: 36542, conv: 86.8 },
  { stage: '授信通过', value: 15624, conv: 42.8 },
  { stage: '发起支用', value: 11872, conv: 76.0 },
  { stage: '放款成功', value: 11246, conv: 94.7 },
  { stage: '首借结清', value: 8964, conv: 79.7 },
  { stage: '复借支用', value: 4682, conv: 52.2 },
];

export interface LifecycleStageRow {
  stage: string;
  customers: string;
  ratio: number;
  avgBalance: string;
  m1Rate: number;
  relendRate: number;
}

export const lifecycleStageTable: LifecycleStageRow[] = [
  { stage: '新户期 (首借在贷)', customers: '18.6万', ratio: 22.4, avgBalance: '6,820元', m1Rate: 4.26, relendRate: 0 },
  { stage: '成长期 (首借结清)', customers: '14.2万', ratio: 17.1, avgBalance: '0元', m1Rate: 0, relendRate: 52.2 },
  { stage: '成熟期 (复借2-4次)', customers: '26.8万', ratio: 32.3, avgBalance: '8,450元', m1Rate: 2.86, relendRate: 68.4 },
  { stage: '忠诚期 (复借5次+)', customers: '12.4万', ratio: 14.9, avgBalance: '9,260元', m1Rate: 2.14, relendRate: 74.8 },
  { stage: '沉默期 (90天未动)', customers: '7.8万', ratio: 9.4, avgBalance: '0元', m1Rate: 0, relendRate: 6.8 },
  { stage: '流失召回', customers: '3.2万', ratio: 3.9, avgBalance: '0元', m1Rate: 0, relendRate: 2.4 },
];

export function getLifecycleTrend(): DailyPoint[] {
  const rnd = seededRandom(99);
  return lastNMonths(12).map((date, i) => ({
    date,
    新户放款占比: +(38 - i * 0.8 + rnd() * 2).toFixed(1),
    复借占比: +(52 + i * 0.9 + rnd() * 2).toFixed(1),
    结清流失率: +(9.5 - i * 0.12 + rnd() * 0.6).toFixed(1),
  }));
}

export function getRetentionCurve(): DailyPoint[] {
  const rnd = seededRandom(15);
  const months = ['放款当月', '+1月', '+2月', '+3月', '+4月', '+5月', '+6月'];
  const cohorts = ['2025-11', '2025-12', '2026-01'];
  const base = [100, 62, 48, 40, 35, 31, 28];
  const res: DailyPoint[] = months.map((m, i) => {
    const row: DailyPoint = { date: m };
    cohorts.forEach((c, j) => {
      row[c] = +(base[i] + j * 1.8 + rnd() * 1.5).toFixed(1);
    });
    return row;
  });
  return res;
}

// ---------- 3. Vintage 监控 ----------
export interface VintageCell {
  mob: number;
  rate: number | null; // null = 未到表现期
}

export interface VintageRow {
  cohort: string; // 放款月
  loanAmount: string; // 放款金额
  cnt: string;
  cells: (number | null)[]; // MOB1..MOB12 的逾期率 %
}

export const MOB_LIST = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];

function genVintage(seed: number, metric: 'M1' | 'M3'): VintageRow[] {
  const rnd = seededRandom(seed);
  const cohorts = lastNMonths(13).slice(0, 13);
  const maxMobByCohort = (idx: number) => 12 - idx; // 越新的月份表现期越短
  return cohorts.map((cohort, idx) => {
    const maxMob = metric === 'M1' ? maxMobByCohort(idx) : Math.max(0, maxMobByCohort(idx) - 2);
    const base = metric === 'M1' ? 1.6 : 0.9;
    const growth = metric === 'M1' ? 0.42 : 0.26;
    // 2025年底资产质量稍差，2026年新放款好转
    const cohortEffect = idx < 4 ? 0.35 : idx > 9 ? -0.25 : 0;
    const cells = MOB_LIST.map((mob) => {
      if (mob > maxMob) return null;
      const v = base + growth * Math.pow(mob, 0.82) + cohortEffect + rnd() * 0.22;
      return +v.toFixed(2);
    });
    return {
      cohort,
      loanAmount: `${(4.2 + rnd() * 2.4).toFixed(1)}亿`,
      cnt: `${Math.round(4.8 + rnd() * 3.2)}万`,
      cells,
    };
  });
}

export const vintageM1: VintageRow[] = genVintage(2024, 'M1');
export const vintageM3: VintageRow[] = genVintage(2025, 'M3');

// Vintage 曲线图数据
export function getVintageCurve(metric: 'M1' | 'M3') {
  const rows = metric === 'M1' ? vintageM1 : vintageM3;
  const showCohorts = rows.slice(0, 8);
  return MOB_LIST.map((mob) => {
    const point: Record<string, number | string> = { mob: `MOB${mob}` };
    showCohorts.forEach((r) => {
      const v = r.cells[mob - 1];
      if (v !== null) point[r.cohort] = v;
    });
    return point;
  });
}

// ---------- 4. 模型分监控 ----------
export function getPsiTrend(): DailyPoint[] {
  const rnd = seededRandom(520);
  return lastNDays(30).map((date, i) => {
    // 第 18 天附近有一次投放渠道变化导致 PSI 抬升
    const shock = i >= 18 && i <= 24 ? 0.06 + rnd() * 0.05 : 0;
    return {
      date,
      A卡PSI: +(0.045 + rnd() * 0.03 + shock).toFixed(3),
      B卡PSI: +(0.06 + rnd() * 0.035 + shock * 0.6).toFixed(3),
    };
  });
}

export interface ScoreBin {
  bin: string;
  range: string;
  basePct: number;
  curPct: number;
  psi: number; // psi 贡献
  badRateBase: number;
  badRateCur: number;
}

export const scoreBins: ScoreBin[] = (() => {
  const rnd = seededRandom(88);
  const base = [4.2, 6.8, 9.5, 12.4, 15.8, 17.2, 14.6, 10.2, 6.1, 3.2];
  const bad = [28.6, 19.4, 12.8, 8.6, 5.4, 3.2, 1.8, 0.9, 0.4, 0.2];
  return base.map((b, i) => {
    const drift = i < 3 ? 1 + rnd() * 0.35 : 1 - rnd() * 0.12; // 低分段占比上升
    const cur = +(b * drift).toFixed(1);
    const psiVal = +((cur - b) * Math.log(cur / b) / 100).toFixed(4);
    return {
      bin: `Bin${i + 1}`,
      range: `${350 + i * 30}-${350 + (i + 1) * 30}`,
      basePct: b,
      curPct: cur,
      psi: Math.abs(psiVal),
      badRateBase: bad[i],
      badRateCur: +(bad[i] * (1 + (rnd() - 0.5) * 0.15)).toFixed(1),
    };
  });
})();

export function getScoreDistCompare() {
  return scoreBins.map((s) => ({
    bin: s.bin,
    基准期占比: s.basePct,
    当前期占比: s.curPct,
  }));
}

export function getAucKsTrend(): DailyPoint[] {
  const rnd = seededRandom(360);
  return lastNMonths(12).map((date, i) => ({
    date,
    AUC: +(0.742 + Math.sin(i / 3) * 0.008 + rnd() * 0.006).toFixed(3),
    KS: +(0.386 + Math.sin(i / 3) * 0.012 + rnd() * 0.008).toFixed(3),
  }));
}

export interface GainRow {
  segment: string;
  range: string;
  cnt: number;
  cntPct: number;
  badCnt: number;
  badRate: number;
  cumBadCapture: number; // 累计坏账捕获率
  lift: number; // 提升度
}

export const gainTable: GainRow[] = (() => {
  const totalBad = scoreBins.reduce((s, b) => s + b.badRateCur * b.curPct, 0) / 100;
  let cumBad = 0;
  return scoreBins.map((b, i) => {
    const badCnt = Math.round(b.curPct * 100 * b.badRateCur) / 100;
    cumBad += badCnt;
    return {
      segment: `Group ${i + 1}`,
      range: b.range,
      cnt: Math.round(b.curPct * 1280),
      cntPct: b.curPct,
      badCnt: Math.round(badCnt),
      badRate: b.badRateCur,
      cumBadCapture: +(cumBad / (totalBad * 100) * 100).toFixed(1),
      lift: +(b.badRateCur / totalBad).toFixed(2),
    };
  });
})();

export const modelList = [
  { name: 'A卡-申请评分 v3.2', status: '在线', psi: 0.068, ks: 0.402, auc: 0.756, owner: '风控模型组' },
  { name: 'B卡-行为评分 v2.8', status: '在线', psi: 0.082, ks: 0.371, auc: 0.728, owner: '风控模型组' },
  { name: 'C卡-催收评分 v1.6', status: '在线', psi: 0.054, ks: 0.348, auc: 0.702, owner: '贷后策略组' },
  { name: '反欺诈分 v4.0', status: '灰度', psi: 0.121, ks: 0.456, auc: 0.783, owner: '反欺诈组' },
  { name: '白名单预筛分 v1.2', status: '在线', psi: 0.037, ks: 0.335, auc: 0.689, owner: '风控模型组' },
];
