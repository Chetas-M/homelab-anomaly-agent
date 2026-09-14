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
