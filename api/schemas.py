from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class MetricPayload(BaseModel):
    node_id: str
    ts: datetime
    
    cpu_pct: Optional[float] = None
    mem_pct: Optional[float] = None
    swap_pct: Optional[float] = None
    
    disk_read_bps: Optional[float] = None
    disk_write_bps: Optional[float] = None
    disk_used_pct: Optional[float] = None
    
    net_in_bps: Optional[float] = None
    net_out_bps: Optional[float] = None
    
    load1: Optional[float] = None
    load5: Optional[float] = None
    load15: Optional[float] = None
    
    temp_c: Optional[float] = None
    
    gpu_util_pct: Optional[float] = None
    gpu_vram_pct: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)

class LastSeenResponse(BaseModel):
    node_id: str
    last_seen: Optional[datetime]
    online: bool

class NodeCapabilities(BaseModel):
    has_gpu: bool
    has_load: bool
    has_temp: bool

class NodeOverview(BaseModel):
    node_id: str
    first_seen: Optional[datetime]
    last_seen: Optional[datetime]
    online: bool
    capabilities: NodeCapabilities
    latest_score: Optional[float] = None
    latest_is_anomalous: Optional[bool] = None
    alert_status: Optional[str] = None
    sustained_anomaly: Optional[bool] = None
    streak_count: Optional[int] = None

class NodeAlertState(BaseModel):
    node_id: str
    alert_status: str
    sustained_anomaly: bool
    streak_count: int
    threshold: int
    latest_score: Optional[float] = None
    latest_is_anomalous: Optional[bool] = None
    latest_ts: Optional[datetime] = None
    is_stale: bool
    message: str

class MetricRecord(BaseModel):
    id: int
    node_id: str
    ts: datetime
    
    cpu_pct: Optional[float] = None
    mem_pct: Optional[float] = None
    swap_pct: Optional[float] = None
    
    disk_read_bps: Optional[float] = None
    disk_write_bps: Optional[float] = None
    disk_used_pct: Optional[float] = None
    
    net_in_bps: Optional[float] = None
    net_out_bps: Optional[float] = None
    
    load1: Optional[float] = None
    load5: Optional[float] = None
    load15: Optional[float] = None
    
    temp_c: Optional[float] = None
    
    gpu_util_pct: Optional[float] = None
    gpu_vram_pct: Optional[float] = None

    score: Optional[float] = None
    is_anomalous: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)

class AnomalyScoreRecord(BaseModel):
    id: int
    node_id: str
    ts: datetime
    score: Optional[float] = None
    is_anomalous: Optional[bool] = None
    model_version: str

    model_config = ConfigDict(from_attributes=True)

class MetricHistory(BaseModel):
    node_id: str
    metrics: list[MetricRecord]

class MetricQuality(BaseModel):
    null_pct: float

class DataQuality(BaseModel):
    node_id: str
    window_hours: int
    actual_samples: int
    expected_samples: int
    coverage_pct: float
    missing_samples_pct: float
    largest_gap_seconds: float
    gaps_over_60s: int
    metrics_quality: dict[str, MetricQuality]

class MetricAttributionRecord(BaseModel):
    metric_key: str
    display_name: str
    current_val: Optional[float] = None
    formatted_val: str
    unit: str
    baseline_median: Optional[float] = None
    reference_range: str
    deviation_z: Optional[float] = None
    status: str  # NORMAL, ELEVATED, LOW, INSUFFICIENT DATA, UNAVAILABLE
    explanation: str

class NodeAttributionResponse(BaseModel):
    node_id: str
    ts: Optional[datetime] = None
    attributions: list[MetricAttributionRecord]

class SimulationScenario(BaseModel):
    id: str
    name: str
    description: str

class SimulationStatusResponse(BaseModel):
    is_active: bool
    scenario_id: Optional[str] = None
    scenario_name: Optional[str] = None
    scenario_description: Optional[str] = None
    started_at: Optional[datetime] = None
    duration_seconds: int
    remaining_seconds: int
    expires_at: Optional[datetime] = None
    available_scenarios: list[SimulationScenario]
    total_simulated_samples: int
    model_status: str = "SIMULATED SIGNAL — MODEL NOT EVALUATED"

class SimulationMetricRecord(BaseModel):
    ts: datetime
    node_id: str
    cpu_pct: Optional[float] = None
    mem_pct: Optional[float] = None
    swap_pct: Optional[float] = None
    disk_read_bps: Optional[float] = None
    disk_write_bps: Optional[float] = None
    disk_used_pct: Optional[float] = None
    net_in_bps: Optional[float] = None
    net_out_bps: Optional[float] = None
    load1: Optional[float] = None
    load5: Optional[float] = None
    load15: Optional[float] = None
    temp_c: Optional[float] = None
    gpu_util_pct: Optional[float] = None
    gpu_vram_pct: Optional[float] = None
    is_simulated: bool = True
    model_evaluated: bool = False
    model_status: str = "SIMULATED SIGNAL — MODEL NOT EVALUATED"
    score: Optional[float] = None
    is_anomalous: Optional[bool] = None
    deviation_detected: bool = False
    max_deviation_z: Optional[float] = None
    attributions: list[MetricAttributionRecord] = []

class SimulationStartRequest(BaseModel):
    scenario: str
    duration_seconds: int = 120

class ScoreDistribution(BaseModel):
    min: Optional[float] = None
    p25: Optional[float] = None
    median: Optional[float] = None
    p75: Optional[float] = None
    p95: Optional[float] = None
    max: Optional[float] = None

class ShadowScoreRecord(BaseModel):
    id: int
    node_id: str
    ts: datetime
    score: Optional[float] = None
    is_anomalous: Optional[bool] = None
    model_version: str
    artifact_id: str
    scoring_status: str

    model_config = ConfigDict(from_attributes=True)

class ShadowComparisonSummary(BaseModel):
    node_id: str
    candidate_active: bool
    candidate_artifact_id: Optional[str] = None
    candidate_version: Optional[str] = None
    frozen_version: Optional[str] = None
    earliest_shadow_ts: Optional[datetime] = None
    latest_shadow_ts: Optional[datetime] = None
    total_shadow_samples: int = 0
    total_scored_samples: int = 0
    total_warmup_samples: int = 0
    
    production_anomaly_count: int = 0
    candidate_anomaly_count: int = 0
    production_anomaly_rate_pct: float = 0.0
    candidate_anomaly_rate_pct: float = 0.0
    
    concordance_count: int = 0
    concordance_rate_pct: float = 0.0
    disagreement_count: int = 0
    disagreement_rate_pct: float = 0.0
    
    candidate_only_anomalies: int = 0
    frozen_only_anomalies: int = 0
    both_anomalies: int = 0
    neither_anomalies: int = 0
    
    frozen_score_distribution: ScoreDistribution
    candidate_score_distribution: ScoreDistribution

