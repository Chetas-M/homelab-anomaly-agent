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

def test_anomaly_scores_in_api():
    from api.models import AnomalyScore
    now = datetime.now(timezone.utc)
    ts1 = now
    ts2 = now + timedelta(seconds=30)
    
    # Ingest 2 telemetry points
    client.post("/ingest", json={"node_id": "anom-node", "ts": ts1.isoformat(), "cpu_pct": 10.0})
    client.post("/ingest", json={"node_id": "anom-node", "ts": ts2.isoformat(), "cpu_pct": 95.0})
    
    # Add an anomaly score for ts2 via DB session
    with TestingSessionLocal() as session:
        session.add(AnomalyScore(
            node_id="anom-node",
            ts=ts2,
            score=0.42,
            is_anomalous=True,
            model_version="1.0"
        ))
        session.commit()
        
    # Check /api/nodes
    res_nodes = client.get("/api/nodes")
    assert res_nodes.status_code == 200
    n = next(x for x in res_nodes.json() if x["node_id"] == "anom-node")
    assert n["latest_score"] == 0.42
    assert n["latest_is_anomalous"] is True
    
    # Check /api/nodes/anom-node
    res_node = client.get("/api/nodes/anom-node")
    assert res_node.status_code == 200
    assert res_node.json()["latest_score"] == 0.42
    assert res_node.json()["latest_is_anomalous"] is True
    
    # Check /api/nodes/anom-node/latest
    res_latest = client.get("/api/nodes/anom-node/latest")
    assert res_latest.status_code == 200
    assert res_latest.json()["score"] == 0.42
    assert res_latest.json()["is_anomalous"] is True
    
    # Check /api/nodes/anom-node/metrics
    res_metrics = client.get("/api/nodes/anom-node/metrics")
    assert res_metrics.status_code == 200
    metrics = res_metrics.json()
    assert len(metrics) == 2
    # ts1 has no score (None)
    assert metrics[0]["score"] is None
    assert metrics[0]["is_anomalous"] is None
    # ts2 has score and is_anomalous
    assert metrics[1]["score"] == 0.42
    assert metrics[1]["is_anomalous"] is True

def test_get_node_scores():
    from api.models import AnomalyScore
    now = datetime.now(timezone.utc)
    with TestingSessionLocal() as session:
        session.add(AnomalyScore(
            node_id="score-node",
            ts=now,
            score=-0.15,
            is_anomalous=False,
            model_version="1.0"
        ))
        session.commit()
        
    res = client.get("/api/nodes/score-node/scores")
    assert res.status_code == 200
    scores = res.json()
    assert len(scores) == 1
    assert scores[0]["node_id"] == "score-node"
    assert scores[0]["score"] == -0.15
    assert scores[0]["is_anomalous"] is False
    assert scores[0]["model_version"] == "1.0"

