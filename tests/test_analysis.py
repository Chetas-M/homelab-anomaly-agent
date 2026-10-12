import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone

from analysis.features import apply_log1p, apply_rolling_features, apply_rate_of_change
from analysis.anomaly_model import calculate_mad, robust_z_score, NodeAnomalyDetector
from analysis.evaluate import generate_weak_labels

def test_apply_log1p():
    df = pd.DataFrame({"disk_read_bps": [0, 10, -5, np.nan]})
    res = apply_log1p(df.copy(), ["disk_read_bps"])
    assert res.loc[0, "disk_read_bps_log1p"] == 0.0
    assert np.isclose(res.loc[1, "disk_read_bps_log1p"], np.log1p(10))
    assert pd.isna(res.loc[2, "disk_read_bps_log1p"])
    assert pd.isna(res.loc[3, "disk_read_bps_log1p"])

def test_apply_rolling_features():
    idx = pd.date_range("2023-01-01", periods=10, freq="1min")
    df = pd.DataFrame({"cpu_pct": [10]*10}, index=idx)
    res = apply_rolling_features(df, ["cpu_pct"], window="5min")
    assert "cpu_pct_roll_mean_5min" in res.columns
    assert "cpu_pct_roll_std_5min" in res.columns
    assert res.loc[idx[4], "cpu_pct_roll_mean_5min"] == 10.0
    assert res.loc[idx[4], "cpu_pct_roll_std_5min"] == 0.0

def test_apply_rate_of_change():
    idx = pd.date_range("2023-01-01", periods=3, freq="1min")
    df = pd.DataFrame({"mem_pct": [10, 20, 30]}, index=idx)
    res = apply_rate_of_change(df, ["mem_pct"])
    assert "mem_pct_roc" in res.columns
    assert pd.isna(res.loc[idx[0], "mem_pct_roc"])
    # 10 units over 60 seconds = 0.166...
    assert np.isclose(res.loc[idx[1], "mem_pct_roc"], 10/60)

def test_calculate_mad():
    s = pd.Series([1, 2, 3, 4, 100])
    med, mad = calculate_mad(s)
    assert med == 3
    # abs diff: 2, 1, 0, 1, 97. Median of abs diffs is 1.
    assert mad == 1

def test_robust_z_score_zero_mad():
    s = pd.Series([5, 5, 5, 10])
    med, mad = calculate_mad(s)
    z = robust_z_score(s, med, mad)
    assert mad == 0
    assert z.iloc[0] == 0.0
    assert z.iloc[3] == 10.0

def test_robust_z_score_normal():
    s = pd.Series([1, 2, 3, 4, 100])
    med, mad = calculate_mad(s)
    z = robust_z_score(s, med, mad)
    assert np.isclose(z.iloc[2], 0.0) # 3 is median
    assert z.iloc[4] > 10.0 # outlier

def test_generate_weak_labels():
    df = pd.DataFrame({
        "node_id": ["alpha", "alpha", "beta"],
        "ts": [
            datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2023, 1, 1, 10, 5, tzinfo=timezone.utc),
            datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc),
        ]
    })
    
    experiments = [
        {
            "node_id": "alpha",
            "start_time_utc": "2023-01-01T10:01:00Z",
            "end_time_utc": "2023-01-01T10:10:00Z"
        }
    ]
    
    res = generate_weak_labels(df, experiments)
    assert res.loc[0, "weak_label"] == False
    assert res.loc[1, "weak_label"] == True
    assert res.loc[2, "weak_label"] == False

def test_node_anomaly_detector_mad_bonferroni():
    # 3 features -> threshold is 3.85
    df = pd.DataFrame({
        "f1": [1, 2, 1, 2, 100],  # 1 extreme
        "f2": [5, 5, 5, 5, 5],    # constant
        "f3": [0, 1, 0, 1, 0]     # normal
    }, index=pd.date_range("2023-01-01", periods=5, freq="1min"))
    
    detector = NodeAnomalyDetector(node_id="test", features=["f1", "f2", "f3"])
    detector.fit(df.iloc[:4])
    
    preds = detector.predict(df)
    assert "if_anomaly" in preds.columns
    assert "mad_anomaly" in preds.columns
    
    # 100 is anomaly for MAD. f1 median=1.5, mad=0.5
    # (100 - 1.5) / (1.4826 * 0.5) = 132 > 3.85
    assert preds.loc[preds.index[4], "mad_anomaly"] == True
    
    # f2 is constant. mad=0. z=0 for normal, 10 for anomaly. 
    # Here f2=5, so z=0.

def test_extract_features_beta_diff():
    from analysis.features import extract_features
    df = pd.DataFrame({
        "ts": pd.date_range("2023-01-01", periods=2, freq="1min"),
        "node_id": ["beta", "beta"],
        "net_in_bps": [1000, 2000],
        "net_out_bps": [1500, 3000]
    })
    res = extract_features(df, "beta")
    assert "beta_net_diff" in res.columns
    assert res.loc[0, "beta_net_diff"] == 500
    assert res.loc[1, "beta_net_diff"] == 1000

def test_disk_net_rolling_features():
    from analysis.features import apply_rolling_features
    idx = pd.date_range("2023-01-01", periods=5, freq="1min")
    df = pd.DataFrame({
        "disk_read_bps": [10, 20, 30, 40, 50],
        "net_out_bps": [100, 100, 100, 100, 100]
    }, index=idx)
    res = apply_rolling_features(df, ["disk_read_bps", "net_out_bps"], window="5min")
    assert "disk_read_bps_roll_mean_5min" in res.columns
    assert "net_out_bps_roll_mean_5min" in res.columns
    assert res.loc[idx[4], "net_out_bps_roll_mean_5min"] == 100
    assert res.loc[idx[4], "disk_read_bps_roll_mean_5min"] == 30
