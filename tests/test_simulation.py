import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from api.main import app, get_db
from api.models import Base
from api.simulation import simulation_manager
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

def test_simulation_lifecycle():
    # 1. Check initial status
    resp = client.get("/api/simulation/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "is_active" in data
    assert "available_scenarios" in data
    assert len(data["available_scenarios"]) >= 3

    # 2. Start simulation with cpu_spike
    start_resp = client.post("/api/simulation/start", json={
        "scenario": "cpu_spike",
        "duration_seconds": 60
    })
    assert start_resp.status_code == 200
    start_data = start_resp.json()
    assert start_data["is_active"] is True
    assert start_data["scenario_id"] == "cpu_spike"
    assert start_data["duration_seconds"] == 60
    assert start_data["remaining_seconds"] > 0

    # 3. Check metrics endpoint returns simulated points with honest status labeling
    metrics_resp = client.get("/api/simulation/metrics")
    assert metrics_resp.status_code == 200
    metrics = metrics_resp.json()
    assert isinstance(metrics, list)
    assert len(metrics) > 0
    latest = metrics[-1]
    assert latest["node_id"] == "simulated-node"
    assert latest["is_simulated"] is True
    assert latest["cpu_pct"] > 80.0
    assert latest["model_evaluated"] is False
    assert latest["model_status"] == "SIMULATED SIGNAL — MODEL NOT EVALUATED"
    assert latest["score"] is None
    assert latest["is_anomalous"] is None
    assert latest["deviation_detected"] is True
    assert latest["max_deviation_z"] > 3.0
    assert "attributions" in latest

    # 4. Stop simulation
    stop_resp = client.post("/api/simulation/stop")
    assert stop_resp.status_code == 200
    stop_data = stop_resp.json()
    assert stop_data["is_active"] is False

def test_simulation_invalid_scenario():
    resp = client.post("/api/simulation/start", json={
        "scenario": "nonexistent_scenario_xyz",
        "duration_seconds": 60
    })
    assert resp.status_code == 400
    assert "Unknown scenario" in resp.json()["detail"]

def test_simulation_duration_bounds():
    # Too large duration should be bounded to 300
    resp = client.post("/api/simulation/start", json={
        "scenario": "network_spike",
        "duration_seconds": 99999
    })
    assert resp.status_code == 200
    assert resp.json()["duration_seconds"] == 300
    simulation_manager.stop()
