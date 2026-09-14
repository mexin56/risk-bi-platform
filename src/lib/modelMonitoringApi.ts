import { api } from '@/lib/auth';

export interface StageMetric {
  key: string;
  stage: string;
  label: string;
  numerator: number;
  denominator: number;
  rate: number | null;
  observation: string;
}

export interface BusinessTypeMetric {
  business_type: string;
  applications: number;
  approved: number;
  loan_success: number;
  fpd7_base: number;
  fpd7_bad: number;
  fpd7_rate: number | null;
  fpd30_base: number;
  fpd30_bad: number;
  fpd30_rate: number | null;
  approval_rate: number | null;
  loan_success_rate: number | null;
}

export interface DailyModelMetric {
  day: string;
  applications: number;
  approved: number;
  loan_success: number;
  fpd7_base: number;
  fpd7_bad: number;
  fpd7_rate: number | null;
  fpd7_rate_raw: number | null;
  fpd7_observation_ratio: number | null;
  fpd30_base: number;
  fpd30_bad: number;
  fpd30_rate: number | null;
  fpd30_rate_raw: number | null;
  fpd30_observation_ratio: number | null;
  approval_rate: number | null;
  loan_success_rate: number | null;
  maturity_warning: boolean;
}

export interface ScoreBandMetric {
  band: string;
  band_order: number;
  samples: number;
  fpd7_base: number;
  fpd7_bad: number;
  fpd7_rate: number | null;
  fpd30_base: number;
  fpd30_bad: number;
  fpd30_rate: number | null;
}

export interface ModelCoverage {
  field: string;
  model: string;
  nonempty: number;
  sentinel: number;
  valid: number;
  coverage: number | null;
}

export type EffectMetric = 'auc' | 'ks';
export type TargetMetric = 'fpd1' | 'fpd7' | 'fpd10' | 'fpd15' | 'fpd30' | 'term3';

export interface ModelEffectTrend {
  day: string;
  alias: string;
  model: string;
  target: TargetMetric;
  auc: number | null;
  ks: number | null;
  mature_count: number;
  bad_count: number;
  good_count: number;
  score_valid_count: number;
  score_coverage: number | null;
  maturity_ratio: number | null;
  maturity_warning: boolean;
}

export interface ModelEffectWeekly {
  week_start: string;
  week_end: string;
  alias: string;
  model: string;
  target: TargetMetric;
  count: number | null;
  badrate: number | null;
  auc: number | null;
  ks: number | null;
  mature_count: number;
  bad_count: number;
  good_count: number;
  score_valid_count: number;
  score_coverage: number | null;
  maturity_ratio: number | null;
  maturity_warning: boolean;
}

export type LatestModelEffect = ModelEffectTrend & { status: '可用' | '成熟度不足' };

export interface ModelMonitoringPayload {
  meta: {
    source_table: string;
    partition: string;
    generated_at: string;
    date_field: string;
    maturity_rule: string;
    notes: string[];
    filters?: {
      flag_mob_type: string;
      flag_product: string;
      cash_ser_call_node: string;
    };
  };
  summary: {
    row_count: number;
    business_cnt: number;
    cid_cnt: number;
    min_create_time: string;
    max_create_time: string;
    min_event_date: string;
    max_event_date: string;
    min_loan_date: string;
    max_loan_date: string;
  };
  stage_metrics: StageMetric[];
  business_type_metrics: BusinessTypeMetric[];
  daily_trend: DailyModelMetric[];
  score_bands: ScoreBandMetric[];
  model_coverage: ModelCoverage[];
  model_effect_trend: ModelEffectTrend[];
  model_effect_weekly: ModelEffectWeekly[];
  model_effect_aliases: string[];
  model_effect_mob_types?: string[];
  model_effect_products?: string[];
  model_effect_cash_ser_call_nodes?: string[];
  latest_model_effect: LatestModelEffect[];
}

export interface ModelMonitoringFilters {
  flagMobType?: string;
  flagProduct?: string;
  cashSerCallNode?: string;
}

export interface ModelMonitoringFilterOptions {
  partition: string;
  flag_mob_type_options: string[];
  flag_product_options: string[];
  cash_ser_call_node_options: string[];
}

export function fetchModelMonitoringFilters(pt?: string, force = false): Promise<ModelMonitoringFilterOptions> {
  const params = new URLSearchParams();
  if (pt) params.set('pt', pt);
  if (force) params.set('force', 'true');
  const suffix = params.toString();
  return api<ModelMonitoringFilterOptions>(`/api/model-monitoring/filters${suffix ? `?${suffix}` : ''}`);
}

export function fetchModelMonitoring(pt?: string, force = false, filters: ModelMonitoringFilters = {}): Promise<ModelMonitoringPayload> {
  const params = new URLSearchParams();
  if (pt) params.set('pt', pt);
  if (force) params.set('force', 'true');
  if (filters.flagMobType) params.set('flag_mob_type', filters.flagMobType);
  if (filters.flagProduct) params.set('flag_product', filters.flagProduct);
  if (filters.cashSerCallNode) params.set('cash_ser_call_node', filters.cashSerCallNode);
  const suffix = params.toString();
  return api<ModelMonitoringPayload>(`/api/model-monitoring${suffix ? `?${suffix}` : ''}`);
}
