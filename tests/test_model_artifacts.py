import os
import sys
import json
import joblib
import pandas as pd
import numpy as np
import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from analysis.features import extract_features

@pytest.fixture
def dummy_telemetry():
    # Provide enough samples to support 5min rolling windows
    idx = pd.date_range("2026-09-27 00:00:00", periods=10, freq="1min", tz="UTC")
    df = pd.DataFrame({
        "id": range(10),
        "node_id": ["beta"] * 10,
        "cpu_pct": [10.0] * 10,
        "mem_pct": [20.0] * 10,
        "swap_pct": [0.0] * 10,
        "disk_read_bps": [0.0] * 10,
        "disk_write_bps": [1024.0] * 10,
        "disk_used_pct": [50.0] * 10,
        "net_in_bps": [512.0] * 10,
        "net_out_bps": [1024.0] * 10,
        "load1": [0.1] * 10,
        "load5": [0.05] * 10,
        "load15": [0.01] * 10,
        "temp_c": [45.0] * 10,
        "gpu_util_pct": [0.0] * 10,
        "gpu_vram_pct": [0.0] * 10
    }, index=idx)
    return df.reset_index().rename(columns={"index": "ts"})

def test_load_and_predict_artifact(dummy_telemetry):
    # This test assumes the models have been trained and persisted
    model_dir = os.path.join(os.path.dirname(__file__), "..", "models")
    beta_dir = os.path.join(model_dir, "beta")
    
    if not os.path.exists(beta_dir):
        pytest.skip("Beta model artifacts not found. Run scripts/train_models.py first.")
        
    # 1. Load persisted model and config
    iso_forest = joblib.load(os.path.join(beta_dir, "isolation_forest.joblib"))
    
    with open(os.path.join(beta_dir, "feature_config.json"), "r") as f:
        config = json.load(f)
        
    with open(os.path.join(beta_dir, "metadata.json"), "r") as f:
        metadata = json.load(f)
        
    assert metadata["node_id"] == "beta"
    assert "features_ordered" in config
    
    expected_features = config["features_ordered"]
    
    # 2. Construct valid feature vector
    feats_df = extract_features(dummy_telemetry, "beta")
    
    # Check that database identity 'id' was not used
    assert "id" not in expected_features
    
    # 3. Verify feature names/order
    # Ensure all expected features are present in the constructed vector
    for f in expected_features:
        assert f in feats_df.columns, f"Feature {f} missing from extracted features"
        
    X = feats_df[expected_features].copy()
    
    # Impute missing values as specified in config
    if config["missing_value_policy"] == "median_imputation":
        medians = config["medians"]
        for f in expected_features:
            X[f] = X[f].fillna(medians.get(f, 0))
            
    # Ensure exact order matches
    assert list(X.columns) == expected_features
    
    # 4. Produce anomaly score
    scores = -iso_forest.decision_function(X)
    
    # 5. Verify finite
    assert np.isfinite(scores).all(), "Anomaly scores contain NaN or Inf"
    assert len(scores) == len(feats_df)
