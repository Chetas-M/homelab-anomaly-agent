import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from api.main import app, get_db
from api.models import Base, AnomalyScore, NodeMetric
from api.alerts import evaluate_streak_from_records, evaluate_node_alert_state
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

class MockScore:
    def __init__(self, ts, score, is_anomalous):
        self.ts = ts
        self.score = score
        self.is_anomalous = is_anomalous

def test_streak_formation():
    now = datetime.now(timezone.utc)
    # 1 anomaly -> ANOMALOUS SAMPLE, streak=1
    s1 = [MockScore(now, 0.15, True)]
    r1 = evaluate_streak_from_records(s1, threshold=3)
    assert r1["alert_status"] == "ANOMALOUS SAMPLE"
    assert r1["streak_count"] == 1
    assert r1["sustained_anomaly"] is False

    # 2 anomalies -> ANOMALOUS SAMPLE, streak=2
    s2 = [
        MockScore(now, 0.15, True),
        MockScore(now - timedelta(seconds=30), 0.12, True)
    ]
    r2 = evaluate_streak_from_records(s2, threshold=3)
    assert r2["alert_status"] == "ANOMALOUS SAMPLE"
    assert r2["streak_count"] == 2
    assert r2["sustained_anomaly"] is False

    # 3 anomalies -> SUSTAINED ANOMALY, streak=3
    s3 = [
        MockScore(now, 0.15, True),
        MockScore(now - timedelta(seconds=30), 0.12, True),
        MockScore(now - timedelta(seconds=60), 0.10, True)
    ]
    r3 = evaluate_streak_from_records(s3, threshold=3)
    assert r3["alert_status"] == "SUSTAINED ANOMALY"
    assert r3["streak_count"] == 3
    assert r3["sustained_anomaly"] is True

def test_streak_reset_on_normal():
    now = datetime.now(timezone.utc)
    # Latest sample is normal following 3 anomalies -> NORMAL, streak=0
    scores = [
        MockScore(now, -0.05, False),
        MockScore(now - timedelta(seconds=30), 0.15, True),
        MockScore(now - timedelta(seconds=60), 0.12, True),
        MockScore(now - timedelta(seconds=90), 0.10, True)
    ]
    r = evaluate_streak_from_records(scores, threshold=3)
    assert r["alert_status"] == "NORMAL"
    assert r["streak_count"] == 0
    assert r["sustained_anomaly"] is False

def test_streak_interrupted_by_normal():
    now = datetime.now(timezone.utc)
    # 2 anomalies, then normal, then anomaly -> streak is only 2, not 3
    scores = [
        MockScore(now, 0.15, True),
        MockScore(now - timedelta(seconds=30), 0.12, True),
        MockScore(now - timedelta(seconds=60), -0.08, False),
        MockScore(now - timedelta(seconds=90), 0.10, True)
    ]
    r = evaluate_streak_from_records(scores, threshold=3)
    assert r["alert_status"] == "ANOMALOUS SAMPLE"
    assert r["streak_count"] == 2
    assert r["sustained_anomaly"] is False

def test_duplicate_sample_handling():
    now = datetime.now(timezone.utc)
    # Same timestamp repeated multiple times should NOT increment streak
    scores = [
        MockScore(now, 0.15, True),
        MockScore(now, 0.15, True),  # Duplicate
        MockScore(now, 0.15, True),  # Duplicate
        MockScore(now - timedelta(seconds=30), 0.12, True)
    ]
    r = evaluate_streak_from_records(scores, threshold=3)
    # Streak should be 2, not 4
    assert r["streak_count"] == 2
    assert r["sustained_anomaly"] is False

def test_gap_handling():
    now = datetime.now(timezone.utc)
    # Anomaly, then 150s gap (>120s max_gap), then anomaly
    scores = [
        MockScore(now, 0.15, True),
        MockScore(now - timedelta(seconds=150), 0.12, True),  # Gap > 120s
        MockScore(now - timedelta(seconds=180), 0.10, True)
    ]
    r = evaluate_streak_from_records(scores, threshold=3, max_gap_seconds=120)
    # Gap breaks the streak; only the latest 1 sample counts
    assert r["streak_count"] == 1
    assert r["alert_status"] == "ANOMALOUS SAMPLE"
    assert r["sustained_anomaly"] is False

def test_warmup_handling():
    now = datetime.now(timezone.utc)
    # Latest sample is unscored/warmup -> WARMUP, streak=0
    scores = [
        MockScore(now, None, None),
        MockScore(now - timedelta(seconds=30), 0.15, True),
        MockScore(now - timedelta(seconds=60), 0.12, True)
    ]
    r = evaluate_streak_from_records(scores, threshold=3)
    assert r["alert_status"] == "WARMUP"
    assert r["streak_count"] == 0
    assert r["sustained_anomaly"] is False

def test_stale_node_handling():
    now = datetime.now(timezone.utc)
    scores = [
        MockScore(now - timedelta(seconds=300), 0.15, True),
        MockScore(now - timedelta(seconds=330), 0.12, True),
        MockScore(now - timedelta(seconds=360), 0.10, True)
    ]
    # If node is stale (>120s since last seen)
    r = evaluate_streak_from_records(scores, threshold=3, is_stale=True)
    assert r["alert_status"] == "STALE"
    assert r["sustained_anomaly"] is False
    assert r["is_stale"] is True

def test_get_node_alert_endpoint():
    db = TestingSessionLocal()
    try:
        now = datetime.now(timezone.utc)
        # Add metric to mark online
        db.add(NodeMetric(node_id="alert-node", ts=now, cpu_pct=5.0))
        # Add 3 consecutive anomaly scores
        db.add(AnomalyScore(node_id="alert-node", ts=now, score=0.15, is_anomalous=True, model_version="1.0"))
        db.add(AnomalyScore(node_id="alert-node", ts=now - timedelta(seconds=30), score=0.12, is_anomalous=True, model_version="1.0"))
        db.add(AnomalyScore(node_id="alert-node", ts=now - timedelta(seconds=60), score=0.10, is_anomalous=True, model_version="1.0"))
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/nodes/alert-node/alert")
    assert resp.status_code == 200
    data = resp.json()
    assert data["node_id"] == "alert-node"
    assert data["alert_status"] == "SUSTAINED ANOMALY"
    assert data["sustained_anomaly"] is True
    assert data["streak_count"] == 3

    # Check overview endpoint also includes alert fields
    overview_resp = client.get("/api/nodes/alert-node")
    assert overview_resp.status_code == 200
    overview_data = overview_resp.json()
    assert overview_data["alert_status"] == "SUSTAINED ANOMALY"
    assert overview_data["sustained_anomaly"] is True
    assert overview_data["streak_count"] == 3

def test_candidate_model_isolation():
    import os
    import json
    import hashlib
    import joblib
    import numpy as np

    candidate_dir = "models/candidates/beta"
    frozen_dir = "models/beta"

    # 1. Candidate artifacts exist in separate directory
    assert os.path.exists(os.path.join(candidate_dir, "isolation_forest.joblib")), "Candidate model missing"
    assert os.path.exists(os.path.join(candidate_dir, "feature_config.json")), "Candidate feature config missing"
    assert os.path.exists(os.path.join(candidate_dir, "metadata.json")), "Candidate metadata missing"
    assert os.path.exists("models/candidates/candidate_manifest.json"), "Candidate manifest missing"

    # 2. Frozen artifacts exist in models/beta/ and match manifest specification
    assert os.path.exists(os.path.join(frozen_dir, "isolation_forest.joblib")), "Frozen model missing"
    assert os.path.exists(os.path.join(frozen_dir, "feature_config.json")), "Frozen feature config missing"
    assert os.path.exists(os.path.join(frozen_dir, "metadata.json")), "Frozen metadata missing"

    with open("models/model_manifest.json", "r") as f:
        master_manifest = json.load(f)
    assert master_manifest["nodes"]["beta"]["samples"] == 40173, "Master manifest was modified!"

    with open(os.path.join(candidate_dir, "metadata.json"), "r") as f:
        cand_meta = json.load(f)
    assert cand_meta["role"] == "candidate_offline_baseline"
    assert cand_meta["status"] == "candidate_not_promoted"

    # 3. Cryptographic isolation: candidate model is NOT identical to frozen model
    def get_md5(p):
        with open(p, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()

    frozen_md5 = get_md5(os.path.join(frozen_dir, "isolation_forest.joblib"))
    cand_md5 = get_md5(os.path.join(candidate_dir, "isolation_forest.joblib"))
    assert frozen_md5 != cand_md5, "Candidate model was copied from or promoted to frozen model!"

    # 4. Candidate model is loadable and scores correctly
    cand_model = joblib.load(os.path.join(candidate_dir, "isolation_forest.joblib"))
    with open(os.path.join(candidate_dir, "feature_config.json"), "r") as f:
        cand_fc = json.load(f)
    features = cand_fc["features_ordered"]
    assert len(features) == 31

    # Fake input row
    dummy_input = np.zeros((1, len(features)))
    score = -cand_model.decision_function(dummy_input)
    assert len(score) == 1
    assert isinstance(float(score[0]), float)

