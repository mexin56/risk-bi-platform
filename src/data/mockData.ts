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
  raw: number; // 用于 CountUp 动画
  decimals: number;
  unit?: string;
  mom: number; // 环比 %
  good_when_down?: boolean;
  spark: number[]; // 近14天迷你趋势
  icon: string; // 图标 key
}

function sparkSeries(seed: number, base: number, volatility: number, trend: number): number[] {
  const rnd = seededRandom(seed);
  return Array.from({ length: 14 }, (_, i) => +(base + trend * i + (rnd() - 0.5) * volatility).toFixed(2));
}

export const overviewKpis: OverviewKpi[] = [
  { label: '当日申请量', value: '48,216', raw: 48216, decimals: 0, unit: '件', mom: 6.8, spark: sparkSeries(11, 40000, 6000, 620), icon: 'inbox' },
  { label: '审批通过率', value: '32.4', raw: 32.4, decimals: 1, unit: '%', mom: -1.2, good_when_down: true, spark: sparkSeries(12, 33.5, 1.6, -0.08), icon: 'check' },
  { label: '当日放款金额', value: '6,842', raw: 6842, decimals: 0, unit: '万元', mom: 4.5, spark: sparkSeries(13, 5900, 700, 70), icon: 'coins' },
  { label: '在贷余额', value: '86.3', raw: 86.3, decimals: 1, unit: '亿元', mom: 1.8, spark: sparkSeries(14, 82.5, 1.2, 0.28), icon: 'vault' },
  { label: '首逾率 (FPD7)', value: '1.06', raw: 1.06, decimals: 2, unit: '%', mom: 0.08, good_when_down: true, spark: sparkSeries(15, 0.98, 0.12, 0.008), icon: 'alert' },
  { label: 'M1+ 逾期率', value: '3.82', raw: 3.82, decimals: 2, unit: '%', mom: 0.15, good_when_down: true, spark: sparkSeries(16, 3.6, 0.3, 0.018), icon: 'trend' },
  { label: 'M3+ 不良率', value: '1.64', raw: 1.64, decimals: 2, unit: '%', mom: -0.05, good_when_down: true, spark: sparkSeries(17, 1.72, 0.14, -0.007), icon: 'shield' },
  { label: '30日复借率', value: '41.7', raw: 41.7, decimals: 1, unit: '%', mom: 2.3, spark: sparkSeries(18, 38.5, 1.5, 0.24), icon: 'repeat' },
];

// 综合风险健康度（仪表盘）
export const riskHealth = {
  score: 82,
  level: '健康',
  dims: [
    { name: '资产质量', score: 78 },
    { name: '模型稳定', score: 86 },
    { name: '增长质量', score: 84 },
    { name: '流动性', score: 90 },
  ],
};

// 告警滚动条
export const alertTicker = [
  { level: '预警', text: '小微经营贷 M1+ 4.88% 超阈值 4.5%，连续 5 日' },
  { level: '关注', text: '信息流渠道 FPD7 升至 1.42%，环比 +0.18pct' },
  { level: '关注', text: '反欺诈分 v4.0 灰度 PSI 0.121 触及关注线' },
  { level: '恢复', text: '信用贷-标准 M3+ 回落至 1.38%，低于阈值' },
  { level: '提示', text: '明日 02:00 跑批窗口，模型回溯任务已排队' },
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

// ---------- 4.5 模型分稳定性监控 ----------
export interface StabilityPsiPoint {
  date: string;
  A卡PSI: number;
  B卡PSI: number;
}

// A卡在第 20 天附近发生渠道投放变化, PSI 持续抬升并突破 0.10 关注线
export function getStabilityPsiTrend(): StabilityPsiPoint[] {
  const rnd = seededRandom(731);
  return lastNDays(30).map((date, i) => {
    const shock = i >= 20 ? 0.075 + (i - 20) * 0.004 + rnd() * 0.012 : 0;
    return {
      date,
      A卡PSI: +(0.052 + rnd() * 0.028 + shock).toFixed(3),
      B卡PSI: +(0.044 + rnd() * 0.024 + shock * 0.45).toFixed(3),
    };
  });
}

export interface StabilityBin {
  bin: string;
  range: string;
  basePct: number;
  curPct: number;
  psiContrib: number; // PSI 贡献
  drift: number; // 占比变化 pp
}

// 低分段占比抬升、中高分段占比下降 → 客群下沉
const stabilityBase = [2.4, 6.8, 12.5, 18.2, 24.6, 22.1, 13.4];
export const stabilityBins: StabilityBin[] = (() => {
  const cur = [1.9, 5.6, 10.8, 15.7, 27.9, 24.8, 13.3];
  return stabilityBase.map((b, i) => {
    const drift = +(cur[i] - b).toFixed(1);
    return {
      bin: `Bin${i + 1}`,
      range: ['≤400', '401-480', '481-560', '561-640', '641-720', '721-800', '≥801'][i],
      basePct: b,
      curPct: cur[i],
      psiContrib: +(Math.abs((cur[i] - b) * Math.log(cur[i] / b) / 100)).toFixed(4),
      drift,
    };
  });
})();

// 迁移矩阵: 行=基准分箱, 列=当前分箱, 单位 %
export const migrationMatrix: number[][] = [
  [72.1, 18.4, 5.2, 2.1, 1.1, 0.7, 0.4],
  [11.2, 65.8, 14.6, 4.8, 2.0, 1.0, 0.6],
  [3.4, 12.7, 61.9, 13.8, 5.2, 2.1, 0.9],
  [1.8, 4.6, 12.2, 58.4, 15.3, 5.6, 2.1],
  [1.1, 2.3, 5.1, 13.6, 56.8, 15.2, 5.9],
  [0.6, 1.2, 2.4, 5.8, 14.7, 60.2, 15.1],
  [0.5, 0.8, 1.6, 2.9, 6.2, 16.4, 71.6],
];

export type AlertLevel = 'crit' | 'warn' | 'info' | 'ok';
export interface StabilityAlert {
  level: AlertLevel;
  model: string;
  detail: string;
  time: string;
  tag: string;
}

export const stabilityAlerts: StabilityAlert[] = [
  { level: 'crit', model: 'A卡 · 贷前信用分', detail: 'PSI 0.182 连续 5 日 > 0.10 关注线, 7/28 触及 0.213', time: '今天 09:42', tag: '严重' },
  { level: 'warn', model: 'A卡 · 贷前信用分', detail: '通过率 +2.14pp 超出 ±1.5pp 阈值, 低分段占比抬升 3.3pp', time: '今天 08:15', tag: '偏高' },
  { level: 'warn', model: 'A卡 · 贷前信用分', detail: '641-720 分箱迁移率 15.3% > 历史均值 9.8%', time: '昨天 22:30', tag: '偏高' },
  { level: 'info', model: 'B卡 · 贷中行为分', detail: 'PSI 0.087 连续 3 日上行, 距关注线 0.013, 建议持续观察', time: '昨天 18:05', tag: '观察' },
  { level: 'ok', model: 'D卡 · 定价分', detail: 'PSI 回落至 0.042, 告警自动解除', time: '7/29 10:12', tag: '已恢复' },
];

export interface ModelHealthRank {
  name: string;
  score: number;
  status: '健康' | '关注' | '预警';
}

export const modelHealthRanks: ModelHealthRank[] = [
  { name: 'C卡 · 反欺诈分', score: 94, status: '健康' },
  { name: 'D卡 · 定价分', score: 88, status: '健康' },
  { name: 'B卡 · 贷中行为分', score: 81, status: '健康' },
  { name: 'A卡 · 贷前信用分', score: 72, status: '关注' },
  { name: 'E卡 · 老客提额分', score: 63, status: '预警' },
];

export interface DriftAttr {
  name: string;
  pct: number;
  note: string;
}

export const driftAttrs: DriftAttr[] = [
  { name: '特征_收入区间', pct: 41, note: '客群下沉, 中低收入占比↑' },
  { name: '特征_职业类型', pct: 23, note: '自由职业占比↑' },
  { name: '特征_申请渠道', pct: 14, note: '新渠道投放放量' },
  { name: '特征_负债收入比', pct: 9, note: '—' },
  { name: '其他特征', pct: 13, note: '—' },
];

// ==================== 生命周期 · 五环节数据 ====================
export interface StageKpi {
  label: string;
  value: string;
  unit?: string;
  mom: number; // 环比 %
  goodDown?: boolean;
}

// ---------- 贷前注册环节 ----------
export const regKpis: StageKpi[] = [
  { label: '新增注册用户', value: '12,436', unit: '人', mom: 8.2 },
  { label: '实名认证通过率', value: '87.3', unit: '%', mom: 0.6 },
  { label: '人脸核身通过率', value: '96.2', unit: '%', mom: -0.3 },
  { label: 'KYC 一次通过率', value: '81.4', unit: '%', mom: 1.2 },
  { label: '设备信息授权率', value: '88.4', unit: '%', mom: 0.8 },
  { label: 'GPS 定位授权率', value: '76.1', unit: '%', mom: -1.6, goodDown: true },
  { label: '资料完善率', value: '76.5', unit: '%', mom: 1.8 },
  { label: '授信申请转化率', value: '68.2', unit: '%', mom: 2.4 },
];

export const regFunnel: FunnelStage[] = [
  { stage: '启动/下载APP', value: 58200, conv: null },
  { stage: '注册完成', value: 42100, conv: 72.3 },
  { stage: '实名认证通过', value: 36750, conv: 87.3 },
  { stage: '完善职业/联系人', value: 32240, conv: 87.7 },
  { stage: '发起授信申请', value: 28600, conv: 88.7 },
];

export function getRegTrend(): DailyPoint[] {
  const rnd = seededRandom(301);
  return lastNDays(30).map((date, i) => ({
    date,
    新增注册: Math.round(10500 + rnd() * 3500 + i * 60),
    实名通过: Math.round(9000 + rnd() * 3000 + i * 52),
  }));
}

// ---------- 授信环节 ----------
export const creditKpis: StageKpi[] = [
  { label: '授信申请量', value: '28,642', unit: '件', mom: 5.4 },
  { label: '机审通过率', value: '45.6', unit: '%', mom: -0.8, goodDown: true },
  { label: '终审通过率', value: '32.4', unit: '%', mom: -1.2, goodDown: true },
  { label: '平均授信额度', value: '8,650', unit: '元', mom: 2.1 },
  { label: '额度使用率', value: '42.8', unit: '%', mom: 1.5 },
  { label: '平均定价 (APR)', value: '18.6', unit: '%', mom: -0.3 },
  { label: '平均审批时效', value: '38', unit: '秒', mom: -6.5 },
];

export const rejectPie = [
  { name: '综合评分不足', value: 38.2 },
  { name: '多头共债', value: 24.6 },
  { name: '信息校验失败', value: 15.8 },
  { name: '欺诈拦截', value: 12.4 },
  { name: '其他原因', value: 9.0 },
];

export const limitDist = [
  { range: '0-3千', pct: 12.4 },
  { range: '3-5千', pct: 21.8 },
  { range: '5-8千', pct: 26.5 },
  { range: '8千-1.2万', pct: 19.6 },
  { range: '1.2-2万', pct: 13.2 },
  { range: '2万+', pct: 6.5 },
];

export function getCreditPassTrend(): DailyPoint[] {
  const rnd = seededRandom(302);
  return lastNDays(30).map((date, i) => ({
    date,
    机审通过率: +(45.5 + Math.sin(i / 4) * 2 + rnd() * 1.5).toFixed(1),
    终审通过率: +(32.4 + Math.sin(i / 5 + 1) * 1.6 + rnd() * 1.2).toFixed(1),
  }));
}

// ---------- 交易环节 ----------
export const loanKpis: StageKpi[] = [
  { label: '授信支用率', value: '76.0', unit: '%', mom: 1.4 },
  { label: '放款成功率', value: '94.7', unit: '%', mom: 0.3 },
  { label: '户均支用金额', value: '6,820', unit: '元', mom: 3.2 },
  { label: '平均借款期限', value: '9.2', unit: '期', mom: 0.0 },
];

export const loanFunnel: FunnelStage[] = [
  { stage: '授信通过客户', value: 15624, conv: null },
  { stage: '发起支用', value: 11872, conv: 76.0 },
  { stage: '放款申请', value: 11480, conv: 96.7 },
  { stage: '放款成功', value: 11246, conv: 98.0 },
];

export const termDist = [
  { range: '3期', pct: 8.4 },
  { range: '6期', pct: 22.6 },
  { range: '9期', pct: 28.4 },
  { range: '12期', pct: 31.2 },
  { range: '18期+', pct: 9.4 },
];

// ---------- 复贷环节 ----------
export const relendKpis: StageKpi[] = [
  { label: '30日复借率', value: '41.7', unit: '%', mom: 2.3 },
  { label: '复借户均次数', value: '2.8', unit: '次', mom: 1.1 },
  { label: '结清7日复借率', value: '18.5', unit: '%', mom: -0.6, goodDown: true },
  { label: '老户余额贡献占比', value: '63.2', unit: '%', mom: 1.6 },
];

// ---------- 催收环节 ----------
export const collectKpis: StageKpi[] = [
  { label: '入催率 (DPD1+)', value: '4.24', unit: '%', mom: 0.12, goodDown: true },
  { label: 'M0 到期回收率', value: '78.5', unit: '%', mom: -0.4 },
  { label: 'M1 催回率', value: '42.3', unit: '%', mom: 1.8 },
  { label: 'PTP 承诺履约率', value: '71.2', unit: '%', mom: 2.4 },
  { label: '人均在催案件', value: '486', unit: '件', mom: -3.2 },
  { label: '合规触达率', value: '99.2', unit: '%', mom: 0.1 },
  { label: '催收投诉率', value: '0.08', unit: '%', mom: -0.02 },
];

export interface RollRow {
  from: string;
  bal: string; // 入催余额
  cure: number; // 当月结清 %
  stay: number; // 维持同阶段 %
  worse: number; // 恶化至下阶段 %
}

export const rollTable: RollRow[] = [
  { from: 'M0 (到期未还)', bal: '3.42亿', cure: 78.5, stay: 15.2, worse: 6.3 },
  { from: 'M1', bal: '1.86亿', cure: 42.3, stay: 29.1, worse: 28.6 },
  { from: 'M2', bal: '0.94亿', cure: 24.8, stay: 26.4, worse: 48.8 },
  { from: 'M3+', bal: '0.62亿', cure: 12.6, stay: 21.3, worse: 66.1 },
];

export function getCollectTrend(): DailyPoint[] {
  const rnd = seededRandom(303);
  return lastNMonths(12).map((date, i) => ({
    date,
    入催率: +(4.0 + Math.sin(i / 3) * 0.5 + rnd() * 0.3).toFixed(2),
    M1催回率: +(41.5 + Math.cos(i / 3) * 3 + rnd() * 2).toFixed(1),
  }));
}

export const collectChannels = [
  { name: 'AI智能外呼', rate: 68.2 },
  { name: '人工电催', rate: 45.6 },
  { name: '短信/触达', rate: 18.4 },
  { name: '委外/法催', rate: 8.2 },
];

// ==================== 渠道质量监控（助贷/导流） ====================
export interface ChannelRow {
  channel: string;
  type: '自营' | '信息流' | 'API导流' | '应用市场' | '地推';
  dailyCnt: number; // 日进件
  passRate: number; // 通过率 %
  fpd7: number; // 首逾 %
  m1: number; // M1+ %
  cac: number; // 件均成本 元
  roi: number; // ROI %
}

export const channelQuality: ChannelRow[] = [
  { channel: 'APP自然流量', type: '自营', dailyCnt: 12480, passRate: 38.5, fpd7: 0.86, m1: 3.12, cac: 12, roi: 286 },
  { channel: '抖音信息流', type: '信息流', dailyCnt: 9640, passRate: 30.2, fpd7: 1.42, m1: 4.66, cac: 185, roi: 128 },
  { channel: '快手信息流', type: '信息流', dailyCnt: 5210, passRate: 28.6, fpd7: 1.58, m1: 4.94, cac: 168, roi: 112 },
  { channel: '腾讯广告', type: '信息流', dailyCnt: 4360, passRate: 31.4, fpd7: 1.26, m1: 4.25, cac: 172, roi: 135 },
  { channel: 'API-星辰钱包', type: 'API导流', dailyCnt: 6820, passRate: 26.8, fpd7: 1.72, m1: 5.42, cac: 96, roi: 154 },
  { channel: 'API-云分期', type: 'API导流', dailyCnt: 3980, passRate: 24.5, fpd7: 1.95, m1: 5.88, cac: 88, roi: 141 },
  { channel: '华为应用市场', type: '应用市场', dailyCnt: 3240, passRate: 35.2, fpd7: 0.94, m1: 3.35, cac: 45, roi: 224 },
  { channel: 'AppStore', type: '应用市场', dailyCnt: 2180, passRate: 36.8, fpd7: 0.88, m1: 3.05, cac: 52, roi: 238 },
  { channel: '地推合伙人', type: '地推', dailyCnt: 1306, passRate: 22.4, fpd7: 2.35, m1: 6.72, cac: 210, roi: 86 },
];

export function getChannelTrend(): DailyPoint[] {
  const rnd = seededRandom(701);
  return lastNDays(30).map((date, i) => ({
    date,
    自营: Math.round(11500 + rnd() * 2200 + i * 30),
    信息流: Math.round(18000 + rnd() * 3500 + i * 20),
    API导流: Math.round(9800 + rnd() * 2400 - i * 15),
  }));
}

// ==================== 反欺诈监控 ====================
export const fraudKpis: StageKpi[] = [
  { label: '欺诈拦截率', value: '3.8', unit: '%', mom: 0.4, goodDown: true },
  { label: '当日规则命中', value: '1,286', unit: '件', mom: 12.6, goodDown: true },
  { label: '人脸核身通过率', value: '96.2', unit: '%', mom: -0.3 },
  { label: '团伙欺诈预警', value: '12', unit: '起', mom: 3, goodDown: true },
];

export function getFraudTrend(): DailyPoint[] {
  const rnd = seededRandom(702);
  return lastNDays(30).map((date, i) => {
    const shock = i >= 16 && i <= 20 ? 1.4 : 0; // 中介攻击波次
    return {
      date,
      拦截率: +(3.2 + rnd() * 0.8 + shock).toFixed(2),
      规则命中: Math.round(950 + rnd() * 400 + shock * 380),
    };
  });
}

export const fraudTypePie = [
  { name: '身份伪造', value: 32.4 },
  { name: '设备农场/模拟器', value: 25.8 },
  { name: '中介包装', value: 21.6 },
  { name: '团伙欺诈', value: 12.2 },
  { name: '其他类型', value: 8.0 },
];

export interface FraudRuleRow {
  rule: string;
  type: string;
  hit: number; // 命中量
  block: number; // 拦截量
  precision: number; // 准确率 %
  status: '生效中' | '观察中' | '已下线';
}

export const fraudRules: FraudRuleRow[] = [
  { rule: 'FR-1024 设备聚集(同设备≥5人)', type: '设备指纹', hit: 326, block: 312, precision: 94.2, status: '生效中' },
  { rule: 'FR-0981 GPS漂移异常', type: '位置核验', hit: 284, block: 268, precision: 91.6, status: '生效中' },
  { rule: 'FR-0876 人脸比对置信度<阈值', type: '生物核身', hit: 198, block: 186, precision: 88.4, status: '生效中' },
  { rule: 'FR-1203 中介手机号段聚集', type: '关系图谱', hit: 152, block: 141, precision: 86.8, status: '生效中' },
  { rule: 'FR-0742 紧急联系人重复(≥3人)', type: '关系图谱', hit: 128, block: 96, precision: 72.5, status: '观察中' },
  { rule: 'FR-0665 模拟器/改机识别', type: '设备指纹', hit: 96, block: 94, precision: 96.8, status: '生效中' },
  { rule: 'FR-0558 黑名单证件号匹配', type: '名单核验', hit: 62, block: 62, precision: 100, status: '生效中' },
  { rule: 'FR-0311 IP代理/机房识别', type: '网络环境', hit: 40, block: 28, precision: 68.2, status: '观察中' },
];

export interface DeviceAlertRow {
  fingerprint: string;
  applyCnt: number; // 关联申请
  passCnt: number; // 关联通过
  region: string;
  level: '高' | '中';
  action: string;
}

export const deviceAlerts: DeviceAlertRow[] = [
  { fingerprint: 'DEV-8f2a91**', applyCnt: 14, passCnt: 3, region: '福建泉州', level: '高', action: '已拦截+设备拉黑' },
  { fingerprint: 'DEV-3c7bd2**', applyCnt: 11, passCnt: 2, region: '广东东莞', level: '高', action: '已拦截+人脸加验' },
  { fingerprint: 'DEV-55e1f8**', applyCnt: 9, passCnt: 4, region: '河南周口', level: '中', action: '观察名单' },
  { fingerprint: 'DEV-a04c66**', applyCnt: 8, passCnt: 1, region: '广西南宁', level: '高', action: '已拦截+团伙溯源' },
  { fingerprint: 'DEV-72d9b3**', applyCnt: 7, passCnt: 2, region: '湖南衡阳', level: '中', action: '降额处置' },
];

// ==================== 定价与资金（大盘） ====================
export const aprDist = [
  { range: '≤12%', pct: 8.4 },
  { range: '12-18%', pct: 32.6 },
  { range: '18-24%', pct: 41.2 },
  { range: '24-36%', pct: 17.8 },
];

export function getFundingTrend(): DailyPoint[] {
  const rnd = seededRandom(703);
  return lastNMonths(12).map((date, i) => ({
    date,
    平均IRR: +(21.5 - i * 0.18 + rnd() * 0.4).toFixed(1),
    资金成本: +(6.8 - i * 0.08 + rnd() * 0.2).toFixed(1),
    净息差NIM: +(14.2 - i * 0.06 + rnd() * 0.3).toFixed(1),
  }));
}

export const assetFiveClass = [
  { name: '正常类', pct: 94.2, color: '#37c26b' },
  { name: '关注类', pct: 2.6, color: '#ffb020' },
  { name: '次级类', pct: 1.4, color: '#ff8f4d' },
  { name: '可疑类', pct: 1.1, color: '#f76965' },
  { name: '损失类', pct: 0.7, color: '#b91c1c' },
];

// ==================== 催收·委外机构效能 ====================
export interface AgencyRow {
  name: string;
  cases: string; // 在委案件
  recovery: number; // 回收率 %
  ptp: number; // PTP履约率 %
  complaint: number; // 投诉率 %
  score: number; // 综合评分
}

export const agencyTable: AgencyRow[] = [
  { name: '华信催收（自催团队）', cases: '12,400件', recovery: 46.8, ptp: 74.2, complaint: 0.05, score: 92 },
  { name: '中联律所', cases: '8,600件', recovery: 38.4, ptp: 68.6, complaint: 0.09, score: 85 },
  { name: '安信联催收', cases: '7,200件', recovery: 35.2, ptp: 65.4, complaint: 0.14, score: 78 },
  { name: '恒信资产', cases: '5,800件', recovery: 31.6, ptp: 61.8, complaint: 0.22, score: 68 },
];
