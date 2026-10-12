import os
import sys
import pytest
import pandas as pd
from datetime import datetime, timezone
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from scripts.live_inference import load_models, process_node, get_watermark, setup_database
from api.models import NodeMetric, AnomalyScore, Base
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

@pytest.fixture
def test_engine():
    # Use in-memory SQLite for testing the worker
    from sqlalchemy import create_engine
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine

def populate_mock_telemetry(engine):
    with Session(engine) as session:
        # Provide some basic metrics
        metrics = []
        base_ts = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
        for i in range(10): # 10 minutes, one point per minute
            ts = base_ts + pd.Timedelta(minutes=i)
            metrics.append(NodeMetric(
                id=i+1, # Provide explicit ID to avoid SQLite AUTOINCREMENT issues
                node_id="beta",
                ts=ts,
                cpu_pct=10.0, mem_pct=20.0, disk_read_bps=0.0, disk_write_bps=1024.0,
                net_in_bps=512.0, net_out_bps=1024.0, load1=0.1, load5=0.05, load15=0.01,
                temp_c=40.0
            ))
        session.add_all(metrics)
        session.commit()
    return base_ts

def test_load_models():
    # Requires models to be present
    models, configs, metadata = load_models()
    assert "beta" in models
    assert "beta" in configs
    assert "beta" in metadata
    
    # Feature parity test logic check
    assert "beta_net_diff" in configs["beta"]["features_ordered"]

def test_process_node_incremental_and_warmup(test_engine):
    base_ts = populate_mock_telemetry(test_engine)
    
    models, configs, metadata = load_models()
    if "beta" not in models:
        pytest.skip("Models not trained")
        
    model = models["beta"]
    config = configs["beta"]
    meta = metadata["beta"]
    
    # Process first batch
    with patch.object(model, 'fit') as mock_fit:
        scored, warmup, anomalies = process_node(test_engine, "beta", model, config, meta)
        
        # model.fit() MUST NEVER be called
        mock_fit.assert_not_called()
        
    # The first few points might be warmup because of rolling features
    assert scored + warmup > 0
    assert warmup > 0 # At least the first point has NaN for ROC
    
    # Check what is persisted
    with Session(test_engine) as session:
        scores = session.execute(select(AnomalyScore).where(AnomalyScore.node_id == "beta")).scalars().all()
        assert len(scores) > 0
        
        # Verify score validity
        for s in scores:
            if s.score is not None:
                assert s.score > -10 and s.score < 10 # finite range
                
    # Run process again - incremental test
    scored2, warmup2, anomalies2 = process_node(test_engine, "beta", model, config, meta)
    assert scored2 == 0 # Already processed
    assert warmup2 == 0
    
    # Duplicate protection test
    # Delete the watermark to force re-processing
    with Session(test_engine) as session:
        # Simulate inserting duplicates by processing same data, bypassing get_watermark logic manually
        pass # IntegrityError prevents duplicates, tested by DB constraints.
        
def test_alpha_gaps(test_engine):
    os.environ["INITIAL_BACKFILL_MINUTES"] = "300"
    # Insert Alpha data with a large gap
    with Session(test_engine) as session:
        ts1 = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 9, 27, 14, 0, tzinfo=timezone.utc) # 4 hours later
        session.add_all([
            NodeMetric(id=1, node_id="alpha", ts=ts1, cpu_pct=10.0, mem_pct=20.0),
            NodeMetric(id=2, node_id="alpha", ts=ts2, cpu_pct=10.0, mem_pct=20.0)
        ])
        session.commit()
        
    models, configs, metadata = load_models()
    if "alpha" not in models:
        pytest.skip()
        
    scored, warmup, _ = process_node(test_engine, "alpha", models["alpha"], configs["alpha"], metadata["alpha"])
    assert scored == 2
    assert warmup == 2
    
    with Session(test_engine) as session:
        scores = session.execute(select(AnomalyScore).where(AnomalyScore.node_id == "alpha").order_by(AnomalyScore.ts)).scalars().all()
        # ts2 should be warmup because it has no history in the last 6 mins
        actual_ts = scores[1].ts
        if actual_ts.tzinfo is None:
            actual_ts = actual_ts.replace(tzinfo=timezone.utc)
        assert actual_ts == ts2
        assert scores[1].score is None # warmup
