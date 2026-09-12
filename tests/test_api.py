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
