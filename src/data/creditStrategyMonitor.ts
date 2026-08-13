// 2026-08-12 业务日 · pb_biz_credit.flexi_cash_jq_result_v1
// 数据由 risk_analysis 下的只读 MaxCompute 核验脚本汇总生成；金额单位均为元。

export interface StrategyScenario {
  label: string;
  averageLimit: number;
  note: string;
  tone: 'base' | 'current' | 'whatIf' | 'target';
}

export interface StrategyScoreRow {
  score: string;
  planScope: '计划内' | '计划外';
  customers: number;
  raisedCustomers: number;
  raiseRate: number;
  beforeAverage: number;
  afterAverage: number;
  delta: number;
}

export interface StrategyCheck {
  name: string;
  value: string;
  detail: string;
  tone: 'green' | 'orange' | 'red' | 'blue';
}

export const strategySnapshot = {
  businessDate: '2026-08-12',
  runWindow: '2026-08-12 07:00 ~ 2026-08-13 05:59',
  table: 'pb_biz_credit.flexi_cash_jq_result_v1',
  targetAverage: 50000,
  validCustomers: 33402,
  baselineAverage: 43206.45,
  currentAverage: 47664.68,
  overallAverage: 46682.1,
  averageIncrease: 4458.23,
  averageIncreaseRate: 10.32,
  upliftTargetAttainment: 65.62,
  targetGap: 2335.32,
  targetGapTotal: 7800.44,
  raisedCustomers: 12942,
  raiseCoverage: 38.75,
  nonRaisedCustomers: 20460,
  positiveConfigNonRaise: 14650,
  coefficientMatchCustomers: 5449,
  coefficientMatchRate: 42.1,
  coefficientLowerCustomers: 3895,
  coefficientHigherCustomers: 3598,
  coefficientNetGap: 2206.61,
  formulaEligibleCustomers: 12942,
  formulaMatchCustomers: 11252,
  formulaMatchRate: 86.94,
  aboveTotalCapCustomers: 238,
  aboveIncreaseCapCustomers: 11,
  legacyShare: 19.68,
  newShare: 79.73,
  otherShare: 0.59,
  legacyDownCustomers: 1165,
  legacyDownAmount: 695.08,
  requiredRaisedAverage: 50460.09,
  actualRaisedAverage: 44432.86,
} as const;

// 同一批次、同一提额客群下的无约束敏感性：用于定位策略系数/提幅配置缺口，非线上预测值。
export const strategyScenarios: StrategyScenario[] = [
  { label: '提额前', averageLimit: 43206.45, note: '新策略有效样本基线', tone: 'base' },
  { label: '实际跑批', averageLimit: 47664.68, note: '+4,458 元 / 户', tone: 'current' },
  { label: '系数表一致', averageLimit: 48325.3, note: '仅修正 cash_remark1 偏差', tone: 'whatIf' },
  { label: '5万方案A幅度', averageLimit: 49238.62, note: '仅 A/B/C 的同批次敏感性', tone: 'whatIf' },
  { label: '目标', averageLimit: 50000, note: '仍差 761 元 / 户', tone: 'target' },
];

export const coefficientDistribution = [
  { name: '系数一致', value: 5449, pct: 42.1, color: '#22a06b' },
  { name: '实际系数偏低', value: 3895, pct: 30.1, color: '#f59e0b' },
  { name: '实际系数偏高', value: 3598, pct: 27.8, color: '#f76965' },
];

export const rolloutMix = [
  { name: '新策略', value: 33407, pct: 79.73, color: '#4e83fd' },
  { name: '旧策略', value: 8248, pct: 19.68, color: '#f59e0b' },
  { name: '其他', value: 245, pct: 0.59, color: '#cbd5e1' },
];

export const strategyScoreRows: StrategyScoreRow[] = [
  { score: 'E', planScope: '计划外', customers: 4865, raisedCustomers: 727, raiseRate: 14.94, beforeAverage: 20251.17, afterAverage: 20561.89, delta: 310.73 },
  { score: 'D', planScope: '计划外', customers: 8247, raisedCustomers: 2428, raiseRate: 29.44, beforeAverage: 28614.1, afterAverage: 29446.81, delta: 832.71 },
  { score: 'C', planScope: '计划内', customers: 9331, raisedCustomers: 4156, raiseRate: 44.54, beforeAverage: 39281.97, afterAverage: 42461.84, delta: 3179.87 },
  { score: 'B', planScope: '计划内', customers: 7450, raisedCustomers: 3789, raiseRate: 50.86, beforeAverage: 59631.74, afterAverage: 66891.05, delta: 7259.31 },
  { score: 'A', planScope: '计划内', customers: 3508, raisedCustomers: 1842, raiseRate: 52.51, beforeAverage: 84850.71, afterAverage: 101037.01, delta: 16186.3 },
];

export const strategyChecks: StrategyCheck[] = [
  {
    name: '策略系数落地',
    value: '42.1%',
    detail: '5,449 / 12,943 名实际提额客户的 cash_remark1 与 315 格系数表一致',
    tone: 'red',
  },
  {
    name: '提额后额度公式',
    value: '86.9%',
    detail: '按 提前额度 × (1 + 提幅)、额度盖帽、单次提幅盖帽 回算一致',
    tone: 'orange',
  },
  {
    name: '5万方案客群范围',
    value: '75.6%',
    detail: '实际提额中 3,155 人（24.4%）为计划外 D/E 风险等级',
    tone: 'red',
  },
  {
    name: '新策略流量切换',
    value: '79.7%',
    detail: '同一业务日仍有 19.7% 流量走旧策略，未完成全量切换',
    tone: 'orange',
  },
];

export const rootCauses = [
  {
    order: '01',
    title: '提额客群的终态额度不足',
    metric: '44,433 → 50,460 元',
    detail: '在 20,460 名未提额客户维持不变的前提下，已提额客户均额须再增加 6,027 元才能把整体推至 5 万。',
    tone: 'red',
  },
  {
    order: '02',
    title: '策略系数未按表稳定落地',
    metric: '净少增约 2,207 万元',
    detail: '实际系数低于策略表的客户数虽与偏高客户接近，但集中在较高额度客群；同口径无约束测算净缺口约 2,207 万元。',
    tone: 'orange',
  },
  {
    order: '03',
    title: '提额闸门覆盖有限',
    metric: '14,650 人未提额',
    detail: 'te_flag=0 客户中有正向配置系数但额度未变化，占新策略有效样本 43.9%，需拆解资格、额度盖帽和数据校验拦截原因。',
    tone: 'orange',
  },
  {
    order: '04',
    title: '策略切换尚未完成',
    metric: '19.7% 仍走旧策略',
    detail: '旧策略中 1,165 人发生降额，合计减少约 695 万元，进一步拉低全量混合口径的平均额度。',
    tone: 'blue',
  },
] as const;
