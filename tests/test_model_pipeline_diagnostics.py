import os
import json
import joblib
import pandas as pd
import numpy as np
import pytest
from analysis.features import extract_features

def test_feature_manifest_consistency():
    manifest_path = "models/model_manifest.json"
    assert os.path.exists(manifest_path)
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    assert "nodes" in manifest
    assert "alpha" in manifest["nodes"]
    assert "beta" in manifest["nodes"]
    assert "gamma" in manifest["nodes"]
    
    # Feature count verification
    assert manifest["nodes"]["alpha"]["features"] == 31
    assert manifest["nodes"]["beta"]["features"] == 31
    assert manifest["nodes"]["gamma"]["features"] == 30

def test_beta_model_features_and_score_convention():
    node_dir = "models/beta"
    with open(os.path.join(node_dir, "feature_config.json")) as f:
        config = json.load(f)
    model = joblib.load(os.path.join(node_dir, "isolation_forest.joblib"))
    
    features = config["features_ordered"]
    assert len(features) == 31
    assert "id" not in features, "Database id column must never be used in model features"
    assert "node_id" not in features
    assert "ts" not in features
    assert "beta_net_diff" in features
    
    # Synthetic normal test vector (using training medians)
    medians = config["medians"]
    x_normal = pd.DataFrame([[medians[f] for f in features]], columns=features)
    
    # Verify score formula: score = -decision_function(X)
    score_normal = -model.decision_function(x_normal)[0]
    pred_normal = model.predict(x_normal)[0]
    
    # Training medians should score negative (normal)
    assert score_normal < 0, f"Baseline sample should be negative score, got {score_normal}"
    assert pred_normal == 1, f"Baseline sample should be normal (1), got {pred_normal}"
    
    # Synthetic extreme anomaly (spiked CPU and network and corresponding rolling/log features)
    x_anomalous = x_normal.copy()
    x_anomalous["cpu_pct"] = 99.0
    x_anomalous["cpu_pct_roll_mean_5min"] = 95.0
    x_anomalous["cpu_pct_roll_std_5min"] = 15.0
    x_anomalous["net_in_bps"] = 50000000.0
    x_anomalous["net_in_bps_log1p"] = float(np.log1p(50000000.0))
    x_anomalous["net_in_bps_roll_mean_5min"] = 45000000.0
    x_anomalous["beta_net_diff"] = -48000000.0
    x_anomalous["net_in_bps_roll_std_5min"] = 5000000.0
    x_anomalous["disk_write_bps_roll_mean_5min"] = 20000000.0
    x_anomalous["disk_write_bps_log1p"] = float(np.log1p(20000000.0))
    x_anomalous["load1"] = 15.0
    x_anomalous["load15"] = 8.0
    
    score_anom = -model.decision_function(x_anomalous)[0]
    pred_anom = model.predict(x_anomalous)[0]
    assert score_anom > 0, f"Extreme anomaly should have positive score, got {score_anom}"
    assert pred_anom == -1, f"Extreme anomaly should have predict -1, got {pred_anom}"

def test_warmup_detection_in_feature_pipeline():
    # Only 1 sample: rolling 5-minute features will have NaNs for rolling std
    now = pd.Timestamp.now(tz="UTC")
    df = pd.DataFrame([{
        "node_id": "beta",
        "ts": now,
        "cpu_pct": 1.0,
        "mem_pct": 13.0,
        "swap_pct": 0.0,
        "disk_read_bps": 0.0,
        "disk_write_bps": 40000.0,
        "disk_used_pct": 36.0,
        "net_in_bps": 2000.0,
        "net_out_bps": 2000.0,
        "load1": 0.02,
        "load5": 0.02,
        "load15": 0.01,
        "temp_c": 28.0
    }])
    
    feats = extract_features(df, "beta")
    assert not feats.empty
    
    # Check that rolling std is NaN on first single sample
    assert pd.isna(feats["cpu_pct_roll_std_5min"].iloc[0])
