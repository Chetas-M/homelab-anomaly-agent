import os
import sys
import pytest
import pandas as pd
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from api.models import Base, NodeMetric, AnomalyScore, ShadowAnomalyScore
from api.main import app
from api.alerts import evaluate_node_alert_state
from api.db import get_db
from scripts.live_inference import (
    load_models,
    load_candidate_models,
    process_node,
    get_watermark,
)

@pytest.fixture
def test_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture
def client(test_engine):
    def override_get_db():
        with Session(test_engine) as session:
            yield session
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

def populate_test_telemetry(engine, count=10):
    with Session(engine) as session:
        metrics = []
        base_ts = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
        for i in range(count):
            ts = base_ts + timedelta(minutes=i)
            metrics.append(NodeMetric(
                id=i + 1,
                node_id="beta",
                ts=ts,
                cpu_pct=5.0 + (i * 0.5),
                mem_pct=15.0,
                disk_read_bps=100.0,
                disk_write_bps=2000.0,
                disk_used_pct=35.0,
                net_in_bps=1000.0,
                net_out_bps=1200.0,
                load1=0.2,
                load5=0.15,
                load15=0.1,
                temp_c=38.0
            ))
        session.add_all(metrics)
        session.commit()
    return base_ts

def test_candidate_artifact_and_version_validation():
    """Verify candidate model artifacts, configuration, and metadata."""
    cand_models, cand_configs, cand_metadata = load_candidate_models()
    assert "beta" in cand_models, "Candidate model for Beta must be available"
    assert "beta" in cand_configs, "Candidate feature config for Beta must be available"
    assert "beta" in cand_metadata, "Candidate metadata for Beta must be available"
    
    cand_meta = cand_metadata["beta"]
    assert cand_meta.get("role") == "candidate_offline_baseline"
    assert cand_meta.get("status") == "candidate_not_promoted"
    assert cand_meta.get("artifact_id") == "beta-cand-baseline-v1"
    assert cand_meta.get("model_type") == "IsolationForest"
    
    cand_cfg = cand_configs["beta"]
    assert cand_cfg.get("methodology_version") == "1.0-candidate"
    assert "features_ordered" in cand_cfg
    assert len(cand_cfg["features_ordered"]) == 31
    assert "medians" in cand_cfg

    # Verify frozen production model remains completely separate
    prod_models, prod_configs, prod_metadata = load_models()
    assert "beta" in prod_models
    assert prod_metadata["beta"].get("methodology_version", "1.0") != "1.0-candidate"

def test_shadow_scoring_consistency_and_isolation(test_engine):
    """Verify live inference scores both frozen and candidate models concurrently on identical samples."""
    populate_test_telemetry(test_engine, count=10)
    
    prod_models, prod_configs, prod_metadata = load_models()
    cand_models, cand_configs, cand_metadata = load_candidate_models()
    
    scored, warmup, anomalies = process_node(
        test_engine,
        "beta",
        prod_models["beta"],
        prod_configs["beta"],
        prod_metadata["beta"],
        cand_model=cand_models["beta"],
        cand_config=cand_configs["beta"],
        cand_meta=cand_metadata["beta"],
    )
    
    assert scored + warmup > 0
    
    with Session(test_engine) as session:
        prod_scores = session.execute(
            select(AnomalyScore).where(AnomalyScore.node_id == "beta").order_by(AnomalyScore.ts.asc())
        ).scalars().all()
        
        shadow_scores = session.execute(
            select(ShadowAnomalyScore).where(ShadowAnomalyScore.node_id == "beta").order_by(ShadowAnomalyScore.ts.asc())
        ).scalars().all()
        
        assert len(prod_scores) > 0
        assert len(shadow_scores) == len(prod_scores), "Shadow candidate must score identical sample count"
        
        # Verify timestamp matching and attribute separation
        for p_score, s_score in zip(prod_scores, shadow_scores):
            assert p_score.ts == s_score.ts, "Shadow score must use identical sample timestamp"
            assert s_score.artifact_id == "beta-cand-baseline-v1"
            assert s_score.model_version == "1.0-candidate"
            assert s_score.scoring_status in ("SCORED", "WARMUP")
            
            if s_score.scoring_status == "SCORED":
                assert s_score.score is not None
                assert isinstance(s_score.is_anomalous, bool)
            else:
                assert s_score.score is None
                assert s_score.is_anomalous is None

def test_shadow_scoring_idempotency(test_engine):
    """Verify idempotency: re-running process_node or duplicate polls does not create duplicate shadow rows."""
    populate_test_telemetry(test_engine, count=8)
    
    prod_models, prod_configs, prod_metadata = load_models()
    cand_models, cand_configs, cand_metadata = load_candidate_models()
    
    # First execution
    process_node(
        test_engine, "beta",
        prod_models["beta"], prod_configs["beta"], prod_metadata["beta"],
        cand_model=cand_models["beta"], cand_config=cand_configs["beta"], cand_meta=cand_metadata["beta"]
    )
    
    with Session(test_engine) as session:
        initial_shadow_count = session.execute(
            select(ShadowAnomalyScore).where(ShadowAnomalyScore.node_id == "beta")
        ).scalars().all()
        initial_prod_count = session.execute(
            select(AnomalyScore).where(AnomalyScore.node_id == "beta")
        ).scalars().all()
        assert len(initial_shadow_count) > 0
        
    # Second execution on identical telemetry (e.g. worker restarted or polled again)
    scored2, warmup2, anom2 = process_node(
        test_engine, "beta",
        prod_models["beta"], prod_configs["beta"], prod_metadata["beta"],
        cand_model=cand_models["beta"], cand_config=cand_configs["beta"], cand_meta=cand_metadata["beta"]
    )
    assert scored2 == 0
    assert warmup2 == 0
    
    with Session(test_engine) as session:
        shadow_count_after = session.execute(
            select(ShadowAnomalyScore).where(ShadowAnomalyScore.node_id == "beta")
        ).scalars().all()
        prod_count_after = session.execute(
            select(AnomalyScore).where(AnomalyScore.node_id == "beta")
        ).scalars().all()
        assert len(shadow_count_after) == len(initial_shadow_count), "Shadow scores must be strictly idempotent"
        assert len(prod_count_after) == len(initial_prod_count), "Production scores must be strictly idempotent"

def test_shadow_warmup_and_missing_features(test_engine):
    """Verify handling of rolling warmup and missing features via median imputation."""
    with Session(test_engine) as session:
        # Insert a single isolated metric point (insufficient rolling history)
        ts = datetime(2026, 10, 5, 8, 0, tzinfo=timezone.utc)
        session.add(NodeMetric(
            id=99,
            node_id="beta",
            ts=ts,
            cpu_pct=10.0,
            mem_pct=None, # Missing metric
            disk_read_bps=None,
            disk_write_bps=500.0,
            disk_used_pct=30.0,
            net_in_bps=100.0,
            net_out_bps=100.0,
            load1=None,
            load5=None,
            load15=None,
            temp_c=None
        ))
        session.commit()
        
    prod_models, prod_configs, prod_metadata = load_models()
    cand_models, cand_configs, cand_metadata = load_candidate_models()
    
    process_node(
        test_engine, "beta",
        prod_models["beta"], prod_configs["beta"], prod_metadata["beta"],
        cand_model=cand_models["beta"], cand_config=cand_configs["beta"], cand_meta=cand_metadata["beta"]
    )
    
    with Session(test_engine) as session:
        shadow_record = session.execute(
            select(ShadowAnomalyScore).where(ShadowAnomalyScore.node_id == "beta", ShadowAnomalyScore.ts == ts)
        ).scalar_one_or_none()
        
        assert shadow_record is not None
        # Single isolated point cannot compute rolling rate-of-change -> WARMUP
        assert shadow_record.scoring_status == "WARMUP"
        assert shadow_record.score is None
        assert shadow_record.is_anomalous is None

def test_production_alert_isolation(test_engine):
    """Verify that shadow candidate scores CANNOT trigger or alter production alerts."""
    base_ts = populate_test_telemetry(test_engine, count=5)
    
    # Set up production scores as NORMAL
    with Session(test_engine) as session:
        for i in range(5):
            ts = base_ts + timedelta(minutes=i)
            session.add(AnomalyScore(
                node_id="beta",
                ts=ts,
                score=-0.2,
                is_anomalous=False,
                model_version="1.0"
            ))
            
            # Concurrently, inject extreme anomalous candidate scores into shadow_anomaly_scores
            session.add(ShadowAnomalyScore(
                node_id="beta",
                ts=ts,
                score=1.85, # Highly anomalous candidate score
                is_anomalous=True, # Candidate declares ANOMALY
                model_version="1.0-candidate",
                artifact_id="beta-cand-baseline-v1",
                scoring_status="SCORED"
            ))
        session.commit()
        
    # Evaluate production alert state
    with Session(test_engine) as session:
        alert_state = evaluate_node_alert_state(session, "beta", threshold=3, stale_seconds=8640000)
        
        # Production alert state MUST REMAIN NORMAL
        assert alert_state["alert_status"] == "NORMAL", "Candidate anomalies must NEVER trigger production alerts"
        assert alert_state["sustained_anomaly"] is False
        assert alert_state["streak_count"] == 0
        assert alert_state["latest_is_anomalous"] is False

def test_shadow_summary_and_scores_api(client, test_engine):
    """Verify the shadow summary API returns proper distributions, rates, and distinctions."""
    base_ts = populate_test_telemetry(test_engine, count=10)
    
    prod_models, prod_configs, prod_metadata = load_models()
    cand_models, cand_configs, cand_metadata = load_candidate_models()
    
    process_node(
        test_engine, "beta",
        prod_models["beta"], prod_configs["beta"], prod_metadata["beta"],
        cand_model=cand_models["beta"], cand_config=cand_configs["beta"], cand_meta=cand_metadata["beta"]
    )
    
    # 1. Test Summary Endpoint
    resp = client.get("/api/nodes/beta/shadow/summary")
    assert resp.status_code == 200
    data = resp.json()
    
    assert data["node_id"] == "beta"
    assert data["candidate_active"] is True
    assert data["candidate_artifact_id"] == "beta-cand-baseline-v1"
    assert data["candidate_version"] == "1.0-candidate"
    assert data["total_shadow_samples"] > 0
    assert data["total_scored_samples"] > 0
    assert "concordance_rate_pct" in data
    assert "production_anomaly_rate_pct" in data
    assert "candidate_anomaly_rate_pct" in data
    assert "frozen_score_distribution" in data
    assert "candidate_score_distribution" in data
    assert "min" in data["candidate_score_distribution"]
    assert "median" in data["candidate_score_distribution"]
    
    # 2. Test Scores Endpoint
    scores_resp = client.get("/api/nodes/beta/shadow/scores?limit=20")
    assert scores_resp.status_code == 200
    scores_data = scores_resp.json()
    assert isinstance(scores_data, list)
    assert len(scores_data) > 0
    first = scores_data[0]
    assert first["node_id"] == "beta"
    assert first["artifact_id"] == "beta-cand-baseline-v1"
    assert first["model_version"] == "1.0-candidate"
    assert first["scoring_status"] in ("SCORED", "WARMUP")
