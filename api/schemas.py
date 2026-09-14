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
