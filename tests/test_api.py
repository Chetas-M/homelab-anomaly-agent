import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timezone, timedelta

from api.main import app, get_db
from api.models import Base

# Setup in-memory SQLite DB for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_ingest_valid_payload():
    payload = {
        "node_id": "test-node",
        "ts": datetime.now(timezone.utc).isoformat(),
        "cpu_pct": 45.2,
        "mem_pct": 60.1,
        "swap_pct": 1.0,
        "disk_read_bps": 1024.0,
        "disk_write_bps": 2048.0,
        "disk_used_pct": 50.0,
        "net_in_bps": 100.0,
        "net_out_bps": 200.0,
        "load1": 1.5,
        "load5": 1.2,
        "load15": 1.0,
        "temp_c": 45.5,
        "gpu_util_pct": 30.0,
        "gpu_vram_pct": 10.0
    }
    
    response = client.post("/ingest", json=payload)
    assert response.status_code == 201
    assert response.json() == {"status": "success"}

def test_ingest_invalid_payload():
    payload = {
        "node_id": "test-node",
        # Missing required field "ts"
    }
    
    response = client.post("/ingest", json=payload)
    assert response.status_code == 422 # FastAPI validation error

def test_last_seen_offline():
    response = client.get("/last_seen/unknown-node")
    assert response.status_code == 200
    data = response.json()
    assert data["node_id"] == "unknown-node"
    assert data["online"] is False
    assert data["last_seen"] is None

def test_last_seen_online():
    ts = datetime.now(timezone.utc).isoformat()
    payload = {
        "node_id": "test-node-online",
        "ts": ts
    }
    client.post("/ingest", json=payload)
    
    response = client.get("/last_seen/test-node-online")
    assert response.status_code == 200
    data = response.json()
    assert data["node_id"] == "test-node-online"
    assert data["online"] is True
    assert data["last_seen"] is not None

def test_last_seen_stale():
    # Node reported 180 seconds ago (> 120s STALE_THRESHOLD)
    stale_ts = (datetime.now(timezone.utc) - timedelta(seconds=180)).isoformat()
    payload = {
        "node_id": "test-node-stale",
        "ts": stale_ts
    }
    client.post("/ingest", json=payload)
    
    response = client.get("/last_seen/test-node-stale")
    assert response.status_code == 200
    data = response.json()
    assert data["node_id"] == "test-node-stale"
    assert data["online"] is False
    assert data["last_seen"] is not None

def test_get_nodes_empty():
    response = client.get("/api/nodes")
    assert response.status_code == 200
    assert response.json() == []

def test_get_nodes_and_node():
    ts = datetime.now(timezone.utc).isoformat()
    client.post("/ingest", json={"node_id": "n1", "ts": ts, "gpu_util_pct": 50.0, "load1": 1.0, "temp_c": 40.0})
    
    response = client.get("/api/nodes")
    assert response.status_code == 200
    data = response.json()
    # Filter to only the one we care about in case of test ordering issues
    n1_data = next((n for n in data if n["node_id"] == "n1"), None)
    assert n1_data is not None
    assert n1_data["node_id"] == "n1"
    assert n1_data["online"] is True
    assert n1_data["capabilities"]["has_gpu"] is True
    assert n1_data["capabilities"]["has_load"] is True
    assert n1_data["capabilities"]["has_temp"] is True
    
    response = client.get("/api/nodes/n1")
    assert response.status_code == 200
    data = response.json()
    assert data["node_id"] == "n1"
    assert data["capabilities"]["has_gpu"] is True

def test_get_node_not_found():
    response = client.get("/api/nodes/nonexistent")
    assert response.status_code == 404

def test_get_node_latest():
    client.post("/ingest", json={"node_id": "latest-node", "ts": datetime.now(timezone.utc).isoformat(), "cpu_pct": 10.0})
    client.post("/ingest", json={"node_id": "latest-node", "ts": (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(), "cpu_pct": 20.0})
    
    response = client.get("/api/nodes/latest-node/latest")
    assert response.status_code == 200
    data = response.json()
    assert data["cpu_pct"] == 20.0

def test_get_node_metrics():
    now = datetime.now(timezone.utc)
    for i in range(5):
        client.post("/ingest", json={"node_id": "metrics-node", "ts": (now + timedelta(seconds=i)).isoformat(), "cpu_pct": i * 10.0})
        
    response = client.get("/api/nodes/metrics-node/metrics")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5
    assert data[0]["cpu_pct"] == 0.0
    assert data[-1]["cpu_pct"] == 40.0
    
    # Test limit (neither start nor end)
    response = client.get("/api/nodes/metrics-node/metrics?limit=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["cpu_pct"] == 30.0
    assert data[1]["cpu_pct"] == 40.0
    
    # Test start and end
    start = (now + timedelta(seconds=1)).isoformat()
    end = (now + timedelta(seconds=3)).isoformat()
    response = client.get(f"/api/nodes/metrics-node/metrics", params={"start": start, "end": end})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert data[0]["cpu_pct"] == 10.0
    assert data[-1]["cpu_pct"] == 30.0

def test_get_node_quality():
    now = datetime.now(timezone.utc)
    client.post("/ingest", json={"node_id": "quality-node", "ts": (now - timedelta(seconds=30)).isoformat(), "cpu_pct": 10.0, "gpu_util_pct": None})
    client.post("/ingest", json={"node_id": "quality-node", "ts": now.isoformat(), "cpu_pct": 20.0, "gpu_util_pct": None})
    
    response = client.get("/api/nodes/quality-node/quality?window_hours=1")
    assert response.status_code == 200
    data = response.json()
    assert data["actual_samples"] == 2
    assert data["largest_gap_seconds"] == 30.0
    assert data["gaps_over_60s"] == 0
    assert data["metrics_quality"]["gpu_util_pct"]["null_pct"] == 100.0
    assert data["metrics_quality"]["cpu_pct"]["null_pct"] == 0.0
    
def test_cors():
    response = client.options(
        "/api/nodes",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"}
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
