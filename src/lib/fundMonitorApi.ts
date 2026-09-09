export type Severity = 'slate' | 'yellow' | 'orange' | 'red';
export type RuleStatus = 0 | 1 | 2;
export type FundWindowKey = '1d' | '3d' | '7d';

export interface FundWindowMetric {
  key: FundWindowKey;
  label: string;
  color: string;
  purpose: string;
  observation_days: number;
  baseline_days: number;
  observation_start: string;
  observation_end: string;
  baseline_start: string | null;
  baseline_end: string | null;
  baseline_abnormal_count: number;
  observation_abnormal_count: number;
  baseline_abnormal_daily: number;
  observation_abnormal_daily: number;
  baseline_total_count: number;
  observation_total_count: number;
  baseline_rate: number;
  observation_rate: number;
  growth_factor: number;
  /** 新增异常时为 null，前端展示「新增」 */
  growth_display: number | null;
  rate_lift_factor: number;
  rate_lift_display: number | null;
  rate_change_bp: number;
  z_score: number;
  expected_abnormal_count: number;
  excess_abnormal_count: number;
  structure_lift_factor: number;
  level: number;
  level_label: string;
  severity: Severity;
  special_labels: string[];
  no_baseline: boolean;
  is_new_anomaly: boolean;
}

export interface FundCondition {
  field: string;
  value: string;
  label: string;
}

export interface FundDailyPoint {
  date: string;
  abnormal_order_count: number;
  order_count: number;
  abnormal_rate: number;
}

export interface FundRecord {
  id: string;
  source: string;
  layer: string;
  path: string;
  canonical_path: string;
  conditions: FundCondition[];
  level: number;
  level_label: string;
  severity: Severity;
  anomaly_type: string;
  primary_window: FundWindowKey;
  primary_window_label: string;
  hit_windows: FundWindowKey[];
  hit_window_count: number;
  observation_abnormal_count: number;
  growth_factor: number;
  rate_lift_factor: number;
  z_score: number;
  excess_abnormal_count: number;
  relative_strength: number;
  is_expert_forced: boolean;
  rule_note: string;
  parent_path: string;
  is_suppressed: boolean;
  suppression_reasons: string[];
  special_labels: string[];
  enters_next_level: boolean;
  drilldown_rule: string;
  windows: Record<FundWindowKey, FundWindowMetric>;
  daily: FundDailyPoint[];
  status?: RuleStatus;
  status_updated_at?: string | null;
  status_updated_by?: string | null;
  action_date?: string | null;
  tracking_start_pt?: string | null;
  is_tracked_only?: boolean;
}

export interface FundInternalTop {
  id: string;
  layer: string;
  path: string;
  primary_window_label: string;
  level_label: string;
  observation_abnormal_count: number;
  growth_factor: number | null;
  rate_lift_factor: number | null;
  z_score: number;
  reason: string;
}

export interface FundDashboard {
  meta: {
    version: string;
    scheme_name: string;
    source: string;
    table: string;
    partition: string;
    offset_days: number;
    table_date_min: string | null;
    table_date_max: string | null;
    date_start: string;
    date_end: string;
    date_count: number;
    dimension_count: number;
    generated_at: string;
    candidate_min_observation_count: number;
    top_k: { single_limit: number; pair_limit: number };
    cache_hit: boolean;
    async_refresh?: boolean;
    serving?: boolean;
  };
  summary: {
    date_start: string;
    date_end: string;
    date_count: number;
    total_order_count: number;
    abnormal_order_count: number;
    overall_abnormal_rate: number;
    single_candidate_count: number;
    single_alert_count: number;
    pair_candidate_count: number;
    pair_alert_count: number;
    third_candidate_count: number;
    third_alert_count: number;
    expert_single_count: number;
    expert_pair_alert_count: number;
    expert_third_alert_count: number;
    merged_alert_count: number;
    level1_count: number;
    level2_count: number;
    level3_count: number;
    new_anomaly_alert_count: number;
  };
  daily_trend: FundDailyPoint[];
  window_overview: FundWindowMetric[];
  highlight: FundRecord | null;
  merged_alerts: FundRecord[];
  top_k: {
    single_downstream: FundRecord[];
    pair_downstream: FundRecord[];
    third_alerts: FundRecord[];
    counts: Record<string, number>;
    internal_top: Record<'single' | 'pair' | 'third', FundInternalTop | null>;
  };
  expert: {
    single: FundRecord[];
    pair: FundRecord[];
    third: FundRecord[];
    counts: Record<string, number>;
  };
  review_items: FundRecord[];
  conclusions: string[];
  rules: {
    thresholds: Array<{
      level: number;
      label: string;
      min_observation_count: number;
      min_growth_factor: number;
      min_rate_lift_factor: number;
      min_z_score: number;
    }>;
    windows: Array<{
      key: FundWindowKey;
      label: string;
      purpose: string;
      color: string;
      observation_days: number;
      baseline_days: number;
      observation_start: string;
      observation_end: string;
      baseline_start: string | null;
      baseline_end: string | null;
    }>;
    suppression_rules: Array<{ field: string; value: string; reason: string }>;
    expert_forced_single: Array<{ field: string; values?: string[]; value?: string; label?: string }>;
    expert_forced_pair: Array<{ field: string; values?: string[]; value?: string; label?: string }>;
    expert_forced_third: Array<{ field: string; values?: string[]; value?: string; label?: string }>;
    field_labels: Record<string, string>;
    candidate_min_observation_count: number;
  };
  config_summary: Array<{ item: string; content: string }>;
  field_dictionary: Array<{
    field: string;
    label: string;
    unique_value_count: number;
    null_replaced_rows: string | number;
    suppression: string;
    forced_single: string;
    forced_pair: string;
    forced_third: string;
  }>;
}

export interface FundPathTrend {
  record_id: string;
  path: string;
  source: string;
  level: number;
  level_label: string;
  severity: Severity;
  status: RuleStatus;
  primary_window: {
    key: FundWindowKey;
    label: string;
    observation_start: string | null;
    observation_end: string | null;
    baseline_start: string | null;
    baseline_end: string | null;
    baseline_daily: number;
  };
  daily: FundDailyPoint[];
  summary: {
    period_days: number;
    period_abnormal_count: number;
    latest_abnormal_count: number;
    previous_abnormal_count: number | null;
    latest_day_change_pct: number;
    peak_abnormal_count: number;
    peak_date: string | null;
    latest_abnormal_rate: number;
  };
}

export interface FundRuleStatusHistory {
  id: number;
  canonical_path: string;
  status: 1 | 2;
  rule: FundRecord | null;
  entered_at: string;
  entered_pt: string;
  entered_by: string;
  exited_at: string | null;
  exited_pt: string | null;
  exited_by: string | null;
  is_active: boolean;
}

import { getToken } from '@/lib/auth';

async function getJson<T>(url: string): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(url, { headers });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || '服务端请求失败');
  }
  return body as T;
}

export function fetchFundAttribution(pt?: string, force = false, offset = 0) {
  const query = new URLSearchParams();
  if (pt) query.set('pt', pt);
  if (force) query.set('force', 'true');
  if (offset > 0) query.set('offset', String(offset));
  return getJson<FundDashboard>(`/api/fund-attribution/dashboard${query.size ? `?${query}` : ''}`);
}

export function fetchFundPartitions(force = false) {
  const query = force ? '?force=true' : '';
  return getJson<{ partitions: string[]; ranges?: Record<string, { min: string; max: string }> }>(
    `/api/fund-attribution/partitions${query}`,
  );
}

export function fetchFundPathTrend(recordId: string, pt?: string, offset = 0) {
  const query = new URLSearchParams({ record_id: recordId });
  if (pt) query.set('pt', pt);
  if (offset > 0) query.set('offset', String(offset));
  return getJson<FundPathTrend>(`/api/fund-attribution/path-trend?${query}`);
}

export function updateFundRuleStatus(
  canonicalPath: string,
  status: RuleStatus,
  actionPt: string,
  rule?: FundRecord,
): Promise<{ canonical_path: string; status: RuleStatus; updated_at: string; updated_by: string; action_date: string | null; history: FundRuleStatusHistory | null }> {
  const token = getToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch('/api/fund-attribution/rule-status', {
    method: 'PUT',
    headers,
    body: JSON.stringify({ canonical_path: canonicalPath, status, action_pt: actionPt, rule }),
  }).then(async (response) => {
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.detail || '规则状态更新失败');
    }
    return body;
  });
}

export function fetchFundRuleStatusHistory() {
  return getJson<{ records: FundRuleStatusHistory[] }>('/api/fund-attribution/rule-status-history');
}
