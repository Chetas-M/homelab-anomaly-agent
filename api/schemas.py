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
