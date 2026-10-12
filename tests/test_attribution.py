import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from api.main import app, get_db
from api.models import Base
from api.attribution import compute_metric_attributions
from tests.test_api import engine, TestingSessionLocal

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def test_compute_metric_attributions_normal():
    # Beta baseline: cpu ~ 0.7%, mem ~ 12.8%, net_in ~ 1896 bps
    metrics = {
        "cpu_pct": 0.8,
        "mem_pct": 13.0,
        "swap_pct": 0.0,
        "disk_used_pct": 36.1,
        "net_in_bps": 1950.0,
        "net_out_bps": 1800.0,
        "load1": 0.03,
        "load5": 0.03,
        "load15": 0.01,
        "temp_c": 28.0,
        "gpu_util_pct": None,
        "gpu_vram_pct": None,
    }
    attrs = compute_metric_attributions("beta", metrics)
    attr_map = {a["metric_key"]: a for a in attrs}
    
    assert "cpu_pct" in attr_map
    assert attr_map["cpu_pct"]["status"] == "NORMAL"
    assert "within normal" in attr_map["cpu_pct"]["explanation"].lower()
    
    # GPU should be UNAVAILABLE on Beta
    assert attr_map["gpu_util_pct"]["status"] == "UNAVAILABLE"
    assert "not present" in attr_map["gpu_util_pct"]["explanation"].lower()

def test_compute_metric_attributions_elevated():
    # Heavy CPU & network burst on Beta
    metrics = {
        "cpu_pct": 85.0,
        "mem_pct": 13.0,
        "swap_pct": 0.0,
        "disk_used_pct": 36.0,
        "net_in_bps": 20000000.0,  # 20 MB/s
        "net_out_bps": 1800.0,
        "load1": 4.5,
        "load5": 2.0,
        "load15": 1.0,
        "temp_c": 28.0,
    }
    attrs = compute_metric_attributions("beta", metrics)
    attr_map = {a["metric_key"]: a for a in attrs}
    
    assert attr_map["cpu_pct"]["status"] == "ELEVATED"
    assert attr_map["cpu_pct"]["deviation_z"] > 3.0
    assert "significantly elevated" in attr_map["cpu_pct"]["explanation"].lower()
    
    assert attr_map["net_in_bps"]["status"] == "ELEVATED"
    assert attr_map["net_in_bps"]["deviation_z"] > 3.0
    
    assert attr_map["load1"]["status"] == "ELEVATED"

def test_get_node_attributions_endpoint():
    # Test with existing test node
    # First post a metric
    ts = datetime.now(timezone.utc).isoformat()
    client.post("/ingest", json={
        "node_id": "test-attr-node",
        "ts": ts,
        "cpu_pct": 1.2,
        "mem_pct": 15.0
    })
    
    resp = client.get("/api/nodes/test-attr-node/attributions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["node_id"] == "test-attr-node"
    assert isinstance(data["attributions"], list)
    assert len(data["attributions"]) > 0

def test_attribution_hardware_availability_and_zero_mad():
    # Alpha (Windows): has GPU, does NOT have Linux load or package temp
    alpha_metrics = {
        "cpu_pct": 6.8,
        "mem_pct": 52.9,
        "swap_pct": 2.7,
        "disk_used_pct": 81.8,
        "gpu_util_pct": 10.0,
        "gpu_vram_pct": 20.0,
        "load1": None,
        "load5": None,
        "load15": None,
        "temp_c": None,
    }
    attrs = compute_metric_attributions("alpha", alpha_metrics)
    attr_map = {a["metric_key"]: a for a in attrs}
    
    # Load and temp should be UNAVAILABLE, not INSUFFICIENT DATA
    assert attr_map["load1"]["status"] == "UNAVAILABLE"
    assert attr_map["load5"]["status"] == "UNAVAILABLE"
    assert attr_map["load15"]["status"] == "UNAVAILABLE"
    assert attr_map["temp_c"]["status"] == "UNAVAILABLE"
    
    # GPU should be evaluated (NORMAL)
    assert attr_map["gpu_util_pct"]["status"] == "NORMAL"
    assert attr_map["gpu_vram_pct"]["status"] == "NORMAL"
    
    # Beta CPU has MAD=0.0 in training, mad_floor must prevent division by zero or infinite Z
    beta_metrics = {"cpu_pct": 0.7}
    beta_attrs = compute_metric_attributions("beta", beta_metrics)
    beta_map = {a["metric_key"]: a for a in beta_attrs}
    assert beta_map["cpu_pct"]["status"] == "NORMAL"
    assert beta_map["cpu_pct"]["deviation_z"] == 0.0
    assert "0.0%" in beta_map["cpu_pct"]["reference_range"]
