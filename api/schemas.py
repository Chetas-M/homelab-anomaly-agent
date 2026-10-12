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

class SimulationStartRequest(BaseModel):
    scenario: str
    duration_seconds: int = 120
