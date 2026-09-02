export type Severity = 'slate' | 'yellow' | 'orange' | 'red';
export type RuleStatus = 0 | 1 | 2;

export interface WindowMetric {
  key: '1d' | '3d' | '7d';
  label: string;
  color: string;
  purpose: string;
  baseline_start: string | null;
  baseline_end: string | null;
  observation_start: string;
  observation_end: string;
  baseline_days: number;
  observation_days: number;
  baseline_count: number;
  observation_count: number;
  approval_count: number | null;
  approval_rate_pct: number | null;
  cid_cnt: number | null;
  approval_cid_cnt: number | null;
  cid_approval_rate_pct: number | null;
  baseline_daily: number;
  observation_daily: number;
  baseline_share: number;
  observation_share: number;
  growth_factor: number;
  structure_lift_factor: number;
  structure_change: number;
  expected_count: number;
  excess_count: number;
  z_score: number;
  level: number;
  level_label: string;
  severity: Severity;
}

export interface AttributionCondition {
  field: string;
  value: string;
  label: string;
}

export interface AttributionRecord {
  id: string;
  source: string;
  layer: string;
  path: string;
  canonical_path: string;
  conditions: AttributionCondition[];
  level: number;
  level_label: string;
  severity: Severity;
  anomaly_type: string;
  primary_window: '1d' | '3d' | '7d';
  primary_window_label: string;
  hit_windows: string[];
  hit_window_count: number;
  observation_count: number;
  approval_rate_pct: number | null;
  cid_approval_rate_pct: number | null;
  growth_factor: number;
  structure_lift_factor: number;
  z_score: number;
  excess_count: number;
  relative_strength: number;
  is_expert_forced: boolean;
  rule_note: string;
  is_suppressed: boolean;
  suppression_reasons: string[];
  status: RuleStatus;
  status_updated_at: string | null;
  status_updated_by: string | null;
  action_date: string | null;
  is_tracked_only?: boolean;
  enters_next_level: boolean;
  drilldown_rule: string;
  windows: Record<'1d' | '3d' | '7d', WindowMetric>;
}

export interface AttributionRuleStatusHistory {
  id: number;
  canonical_path: string;
  status: 1 | 2;
  rule: AttributionRecord | null;
  entered_at: string;
  entered_pt: string;
  entered_by: string;
  exited_at: string | null;
  exited_pt: string | null;
  exited_by: string | null;
  is_active: boolean;
}

export interface AttributionRuleStatusUpdateResponse {
  canonical_path: string;
  status: RuleStatus;
  updated_at: string;
  updated_by: string;
  action_date: string | null;
  history: AttributionRuleStatusHistory | null;
}

export interface AttributionPathTrend {
  record_id: string;
  path: string;
  source: string;
  level: number;
  level_label: string;
  severity: Severity;
  primary_window: {
    key: '1d' | '3d' | '7d';
    label: string;
    observation_start: string | null;
    observation_end: string | null;
    baseline_daily: number;
  };
  daily: Array<{
    date: string;
    application_count: number;
    total_application_count: number;
    application_share_pct: number;
    approval_count: number | null;
    approval_rate_pct: number | null;
    cid_cnt: number | null;
    approval_cid_cnt: number | null;
    cid_approval_rate_pct: number | null;
  }>;
  summary: {
    period_days: number;
    period_application_count: number;
    latest_application_count: number;
    previous_application_count: number | null;
    latest_day_change_pct: number;
    peak_application_count: number;
    peak_date: string;
    latest_application_share_pct: number;
    latest_approval_rate_pct: number | null;
    latest_cid_approval_rate_pct: number | null;
  };
}

export interface AttributionDashboard {
  meta: {
    source: string;
    table: string;
    partition: string;
    version: string;
    date_start: string;
    date_end: string;
    date_count: number;
    aggregate_row_count: number;
    dimension_count: number;
    generated_at: string;
    note: string;
    cache_hit: boolean;
    async_refresh?: boolean;
    table_date_min?: string | null;
    table_date_max?: string | null;
  };
  summary: {
    total_application_count: number;
    latest_application_count: number;
    previous_application_count: number;
    latest_day_change_pct: number;
    latest_approval_rate: number;
    latest_cid_approval_rate_pct: number;
    approval_count: number;
    cid_cnt: number;
    approval_cid_cnt: number;
    approval_jy0_count: number;
    merged_alert_count: number;
    level3_count: number;
    level2_count: number;
    level1_count: number;
    expert_alert_count: number;
    suppressed_alert_count: number;
    highlight_path: string | null;
  };
  daily_trend: Array<{
    date: string;
    application_count: number;
    approval_count: number;
    expert_seed_count: number;
    focus_path_count: number;
  }>;
  highlight: AttributionRecord | null;
  merged_alerts: AttributionRecord[];
  merged_alert_total: number;
  top_k: {
    single_downstream: AttributionRecord[];
    pair_downstream: AttributionRecord[];
    third_alerts: AttributionRecord[];
    counts: Record<string, number>;
  };
  expert: {
    single: AttributionRecord | null;
    pair: AttributionRecord | null;
    third_alerts: AttributionRecord[];
    third_calculated: AttributionRecord[];
    counts: Record<string, number>;
  };
  suppressed_alerts: AttributionRecord[];
  suppressed_alert_total: number;
  rules: {
    thresholds: Array<{
      level: number;
      label: string;
      min_observation_count: number;
      min_growth_factor: number;
      min_structure_lift_factor: number;
      min_z_score: number;
    }>;
    windows: Array<{
      key: '1d' | '3d' | '7d';
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
    expert_path: Array<{ field: string; value: string; label: string }>;
    field_labels: Record<string, string>;
  };
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

export function fetchCreditAttribution(pt?: string, force = false, offset = 0) {
  const query = new URLSearchParams();
  if (pt) query.set('pt', pt);
  if (force) query.set('force', 'true');
  if (offset > 0) query.set('offset', String(offset));
  return getJson<AttributionDashboard>(`/api/credit-attribution/dashboard${query.size ? `?${query}` : ''}`);
}

export function fetchAttributionPartitions(force = false) {
  const query = force ? '?force=true' : '';
  return getJson<{ partitions: string[]; ranges?: Record<string, { min: string; max: string }> }>(`/api/credit-attribution/partitions${query}`);
}

export function fetchAttributionPathTrend(recordId: string, pt?: string, offset = 0) {
  const query = new URLSearchParams({ record_id: recordId });
  if (pt) query.set('pt', pt);
  if (offset > 0) query.set('offset', String(offset));
  return getJson<AttributionPathTrend>(`/api/credit-attribution/path-trend?${query}`);
}

export function updateAttributionRuleStatus(
  canonicalPath: string,
  status: RuleStatus,
  actionPt: string,
  rule?: AttributionRecord,
): Promise<AttributionRuleStatusUpdateResponse> {
  const token = getToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch('/api/credit-attribution/rule-status', {
    method: 'PUT',
    headers,
    body: JSON.stringify({ canonical_path: canonicalPath, status, action_pt: actionPt, rule }),
  }).then(async (response) => {
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(body.detail || '规则状态更新失败');
    }
    return body as AttributionRuleStatusUpdateResponse;
  });
}

export function fetchAttributionRuleStatusHistory(): Promise<{
  records: AttributionRuleStatusHistory[];
}> {
  return getJson<{ records: AttributionRuleStatusHistory[] }>(
    '/api/credit-attribution/rule-status-history',
  );
}
