export interface NodeCapabilities {
  has_gpu: boolean;
  has_load: boolean;
  has_temp: boolean;
}

export interface NodeOverview {
  node_id: string;
  first_seen: string | null;
  last_seen: string | null;
  online: boolean;
  capabilities: NodeCapabilities;
  latest_score?: number | null;
  latest_is_anomalous?: boolean | null;
  alert_status?: string | null;
  sustained_anomaly?: boolean | null;
  streak_count?: number | null;
}

export interface NodeAlertState {
  node_id: string;
  status: string;
  is_sustained_anomaly: boolean;
  streak_count: number;
  threshold: number;
  latest_score: number | null;
  latest_is_anomalous: boolean | null;
  latest_ts: string | null;
  message: string;
  last_evaluated_at: string;
}

export interface MetricRecord {
  id: number;
  node_id: string;
  ts: string;
  
  cpu_pct: number | null;
  mem_pct: number | null;
  swap_pct: number | null;
  
  disk_read_bps: number | null;
  disk_write_bps: number | null;
  disk_used_pct: number | null;
  
  net_in_bps: number | null;
  net_out_bps: number | null;
  
  load1: number | null;
  load5: number | null;
  load15: number | null;
  
  temp_c: number | null;
  
  gpu_util_pct: number | null;
  gpu_vram_pct: number | null;

  score: number | null;
  is_anomalous: boolean | null;
}

export interface AnomalyScoreRecord {
  id: number;
  node_id: string;
  ts: string;
  score: number | null;
  is_anomalous: boolean | null;
  model_version: string;
}

export interface MetricQuality {
  null_pct: number;
}

export interface DataQuality {
  node_id: string;
  window_hours: number;
  actual_samples: number;
  expected_samples: number;
  coverage_pct: number;
  missing_samples_pct: number;
  largest_gap_seconds: number;
  gaps_over_60s: number;
  metrics_quality: Record<string, MetricQuality>;
}

export type MetricAttributionStatus = 'NORMAL' | 'ELEVATED' | 'LOW' | 'INSUFFICIENT DATA' | 'UNAVAILABLE';

export interface MetricAttributionRecord {
  metric_key: string;
  display_name: string;
  current_val: number | null;
  formatted_val: string;
  unit: string;
  baseline_median: number | null;
  reference_range: string;
  deviation_z: number | null;
  status: MetricAttributionStatus;
  explanation: string;
}

export interface NodeAttributionResponse {
  node_id: string;
  ts: string | null;
  attributions: MetricAttributionRecord[];
}

export interface SimulationScenario {
  id: string;
  name: string;
  description: string;
}

export interface SimulationStatusResponse {
  is_active: boolean;
  scenario_id: string | null;
  scenario_name: string | null;
  scenario_description: string | null;
  started_at: string | null;
  duration_seconds: number;
  remaining_seconds: number;
  expires_at: string | null;
  available_scenarios: SimulationScenario[];
  total_simulated_samples: number;
  model_status?: string;
}

export interface SimulationMetricRecord {
  ts: string;
  node_id: string;
  cpu_pct: number;
  mem_pct: number;
  swap_pct: number;
  disk_read_bps: number;
  disk_write_bps: number;
  disk_used_pct: number;
  net_in_bps: number;
  net_out_bps: number;
  load1: number;
  load5: number;
  load15: number;
  temp_c: number;
  gpu_util_pct: number | null;
  gpu_vram_pct: number | null;
  score: number | null;
  is_anomalous: boolean | null;
  is_simulated: boolean;
  model_evaluated?: boolean;
  model_status?: string;
  deviation_detected?: boolean;
  max_deviation_z?: number | null;
  attributions?: MetricAttributionRecord[];
}

export interface ScoreDistribution {
  min: number | null;
  p25: number | null;
  median: number | null;
  p75: number | null;
  p95: number | null;
  max: number | null;
}

export interface ShadowScoreRecord {
  id: number;
  node_id: string;
  ts: string;
  score: number | null;
  is_anomalous: boolean | null;
  model_version: string;
  artifact_id: string;
  scoring_status: string;
}

export interface ShadowComparisonSummary {
  node_id: string;
  candidate_active: boolean;
  candidate_artifact_id: string | null;
  candidate_version: string | null;
  frozen_version: string | null;
  earliest_shadow_ts: string | null;
  latest_shadow_ts: string | null;
  total_shadow_samples: number;
  total_scored_samples: number;
  total_warmup_samples: number;
  
  production_anomaly_count: number;
  candidate_anomaly_count: number;
  production_anomaly_rate_pct: number;
  candidate_anomaly_rate_pct: number;
  
  concordance_count: number;
  concordance_rate_pct: number;
  disagreement_count: number;
  disagreement_rate_pct: number;
  
  candidate_only_anomalies: number;
  frozen_only_anomalies: number;
  both_anomalies: number;
  neither_anomalies: number;
  
  frozen_score_distribution: ScoreDistribution;
  candidate_score_distribution: ScoreDistribution;
}

