"""
Unit Tests for Telemetry EDA Pipeline
Home Lab Anomaly / Observability Agent

Tests core EDA calculations using synthetic in-memory fixtures:
1. Sampling interval calculation
2. Gap detection
3. Interval bucket classification
4. Duplicate timestamp detection
5. NULL preservation
6. Percentile calculation
7. Constant-series handling (std = 0.0, excluded from correlation)
8. Unavailable metric detection (100% NULL, NaN stats)
9. Partial metric availability
10. Per-node separation
11. Strict database URL resolution & failure (no silent fallback to test.db)
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
import pytest

from telemetry_eda.eda import (
    ConfigurationError,
    METRICS,
    compute_correlations,
    compute_data_quality,
    compute_descriptive_statistics,
    compute_metric_availability,
    compute_sampling_intervals,
    resolve_database_url,
)


@pytest.fixture
def sample_timestamps():
    """Generate known timestamps with predictable intervals."""
    base = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
    return [
        base,                                # t0
        base + timedelta(seconds=30),         # +30s (<45s)
        base + timedelta(seconds=60),         # +30s (<45s)
        base + timedelta(seconds=160),        # +100s (45s–5m)
        base + timedelta(seconds=760),        # +600s (5m–15m gap)
        base + timedelta(seconds=2760),       # +2000s (15m–60m gap)
        base + timedelta(seconds=7760),       # +5000s (>1h gap)
    ]


@pytest.fixture
def synthetic_dataframe(sample_timestamps):
    """
    Generate synthetic multi-node dataframe with known properties:
    - node_alpha: variable CPU, constant temperature (25.0), unavailable GPU (all NaN)
    - node_beta: duplicate timestamps, partially available GPU, variable load
    """
    records = []

    # Node Alpha
    for i, ts in enumerate(sample_timestamps):
        records.append({
            "node_id": "alpha",
            "ts": ts,
            "cpu_pct": 10.0 + i * 5.0,     # Variable (10, 15, 20, 25, 30, 35, 40)
            "mem_pct": 50.0,               # Constant (std = 0.0)
            "swap_pct": 0.0,               # Constant
            "disk_read_bps": 1000.0,
            "disk_write_bps": 2000.0,
            "disk_used_pct": 40.0,
            "net_in_bps": 500.0,
            "net_out_bps": 500.0,
            "load1": 1.0,
            "load5": 0.8,
            "load15": 0.5,
            "temp_c": 25.0,                # Constant temperature
            "gpu_util_pct": np.nan,        # Unavailable (all NaN)
            "gpu_vram_pct": np.nan,        # Unavailable
        })

    # Node Beta with duplicate timestamp and partial GPU
    beta_base = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)
    beta_ts = [
        beta_base,
        beta_base + timedelta(seconds=30),
        beta_base + timedelta(seconds=30),  # Duplicate timestamp
        beta_base + timedelta(seconds=60),
    ]
    for i, ts in enumerate(beta_ts):
        records.append({
            "node_id": "beta",
            "ts": ts,
            "cpu_pct": 20.0 + i * 2.0,
            "mem_pct": 60.0,
            "swap_pct": 0.0,
            "disk_read_bps": 1500.0,
            "disk_write_bps": 2500.0,
            "disk_used_pct": 45.0,
            "net_in_bps": 600.0,
            "net_out_bps": 600.0,
            "load1": 1.5,
            "load5": 1.2,
            "load15": 1.0,
            "temp_c": 30.0 + i,
            "gpu_util_pct": 50.0 if i % 2 == 0 else np.nan,  # Partial availability (50% null)
            "gpu_vram_pct": 40.0 if i % 2 == 0 else np.nan,
        })

    return pd.DataFrame(records)


def test_sampling_interval_calculation(synthetic_dataframe):
    """1. Test that consecutive monotonic timestamp differences are accurately calculated."""
    detailed_df, summary_df = compute_sampling_intervals(synthetic_dataframe)
    alpha_summary = summary_df[summary_df["node_id"] == "alpha"].iloc[0]

    # Sample timestamps have 7 points -> 6 intervals: [30, 30, 100, 600, 2000, 5000]
    expected_intervals = [30.0, 30.0, 100.0, 600.0, 2000.0, 5000.0]
    assert alpha_summary["interval_count"] == 6
    assert pytest.approx(alpha_summary["min_interval"]) == 30.0
    assert pytest.approx(alpha_summary["max_interval"]) == 5000.0
    assert pytest.approx(alpha_summary["mean_interval"]) == sum(expected_intervals) / 6.0


def test_gap_detection(synthetic_dataframe):
    """2. Test detection of gaps > 300s (5m) and largest_gap."""
    _, summary_df = compute_sampling_intervals(synthetic_dataframe)
    alpha_summary = summary_df[summary_df["node_id"] == "alpha"].iloc[0]

    # Gaps >= 300s are: 600s, 2000s, 5000s -> count = 3
    assert alpha_summary["gap_count_gt_5m"] == 3
    assert pytest.approx(alpha_summary["largest_gap"]) == 5000.0


def test_interval_bucket_classification(synthetic_dataframe):
    """3. Test accurate bucketing into <45s, 45s–5m, 5–15m, 15–60m, >1h."""
    _, summary_df = compute_sampling_intervals(synthetic_dataframe)
    alpha_summary = summary_df[summary_df["node_id"] == "alpha"].iloc[0]

    # Intervals:
    # 30, 30 -> 2 in <45s
    # 100 -> 1 in 45s–5m (300s)
    # 600 -> 1 in 5–15m (300s–900s)
    # 2000 -> 1 in 15–60m (900s–3600s)
    # 5000 -> 1 in >1h (>= 3600s)
    assert alpha_summary["count_lt_45s"] == 2
    assert alpha_summary["count_45s_to_5m"] == 1
    assert alpha_summary["count_5m_to_15m"] == 1
    assert alpha_summary["count_15m_to_60m"] == 1
    assert alpha_summary["count_gt_1h"] == 1


def test_duplicate_timestamp_detection(synthetic_dataframe):
    """4. Test detection of duplicate timestamps in data quality."""
    _, summary_df = compute_sampling_intervals(synthetic_dataframe)
    quality_df = compute_data_quality(synthetic_dataframe, summary_df)

    alpha_quality = quality_df[quality_df["node_id"] == "alpha"].iloc[0]
    beta_quality = quality_df[quality_df["node_id"] == "beta"].iloc[0]

    # Alpha has all unique timestamps
    assert alpha_quality["duplicate_timestamp_count"] == 0

    # Beta has 4 samples with 1 duplicate (3 unique)
    assert beta_quality["duplicate_timestamp_count"] == 1


def test_null_preservation(synthetic_dataframe):
    """5. Test that NULL values are preserved and never replaced with 0."""
    stats_df = compute_descriptive_statistics(synthetic_dataframe)

    # For Alpha, gpu_util_pct is entirely NULL
    alpha_gpu = stats_df[(stats_df["node_id"] == "alpha") & (stats_df["metric"] == "gpu_util_pct")].iloc[0]
    assert alpha_gpu["count"] == 0
    assert np.isnan(alpha_gpu["mean"])
    assert np.isnan(alpha_gpu["min"])
    assert np.isnan(alpha_gpu["max"])
    assert alpha_gpu["status"] == "unavailable"


def test_percentile_calculation():
    """6. Test accurate percentile calculation (P1, P5, P25, P50, P75, P95, P99)."""
    # Create a linear distribution 1 to 100
    ts_base = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
    df = pd.DataFrame({
        "node_id": ["node1"] * 100,
        "ts": [ts_base + timedelta(seconds=30 * i) for i in range(100)],
        "cpu_pct": [float(i + 1) for i in range(100)],
    })
    for m in METRICS:
        if m not in df.columns:
            df[m] = np.nan

    stats_df = compute_descriptive_statistics(df)
    cpu_stats = stats_df[(stats_df["node_id"] == "node1") & (stats_df["metric"] == "cpu_pct")].iloc[0]

    assert pytest.approx(cpu_stats["P50"], abs=0.5) == 50.5
    assert pytest.approx(cpu_stats["P25"], abs=0.5) == 25.75
    assert pytest.approx(cpu_stats["P75"], abs=0.5) == 75.25
    assert pytest.approx(cpu_stats["min"]) == 1.0
    assert pytest.approx(cpu_stats["max"]) == 100.0


def test_constant_series_handling(synthetic_dataframe, tmp_path):
    """7. Test that constant metrics preserve std = 0.0 and are excluded from correlations."""
    stats_df = compute_descriptive_statistics(synthetic_dataframe)
    alpha_temp = stats_df[(stats_df["node_id"] == "alpha") & (stats_df["metric"] == "temp_c")].iloc[0]

    # In synthetic fixture, temp_c is constant at 25.0
    assert alpha_temp["count"] == 7
    assert pytest.approx(alpha_temp["mean"]) == 25.0
    assert alpha_temp["std"] == 0.0
    assert alpha_temp["status"] == "constant"

    # Verify correlation calculation excludes constant metrics
    corr_meta = compute_correlations(synthetic_dataframe, tmp_path)
    assert "temp_c" in corr_meta["alpha"]["excluded_constant"]
    assert "mem_pct" in corr_meta["alpha"]["excluded_constant"]
    assert "temp_c" not in corr_meta["alpha"]["evaluated_metrics"]


def test_unavailable_metric_detection(synthetic_dataframe):
    """8. Test that 100% NULL metrics are marked 'unavailable'."""
    avail_df = compute_metric_availability(synthetic_dataframe)

    alpha_gpu = avail_df[(avail_df["node_id"] == "alpha") & (avail_df["metric"] == "gpu_util_pct")].iloc[0]
    assert alpha_gpu["status"] == "unavailable"
    assert alpha_gpu["non_null_rows"] == 0
    assert alpha_gpu["availability_percentage"] == 0.0


def test_partial_metric_availability(synthetic_dataframe):
    """9. Test that metrics with mixed NULL and non-NULL are marked 'partially_available'."""
    avail_df = compute_metric_availability(synthetic_dataframe)

    beta_gpu = avail_df[(avail_df["node_id"] == "beta") & (avail_df["metric"] == "gpu_util_pct")].iloc[0]
    assert beta_gpu["status"] == "partially_available"
    assert beta_gpu["non_null_rows"] == 2
    assert beta_gpu["null_rows"] == 2
    assert beta_gpu["availability_percentage"] == 50.0


def test_per_node_separation(synthetic_dataframe, tmp_path):
    """10. Test that calculations and correlations for separate nodes do not mix."""
    _, summary_df = compute_sampling_intervals(synthetic_dataframe)
    assert set(summary_df["node_id"]) == {"alpha", "beta"}

    corr_meta = compute_correlations(synthetic_dataframe, tmp_path)
    assert "alpha" in corr_meta
    assert "beta" in corr_meta

    # Alpha and Beta have different evaluated metrics (Beta has variable temp_c, Alpha has constant temp_c)
    assert "temp_c" in corr_meta["beta"]["evaluated_metrics"]
    assert "temp_c" not in corr_meta["alpha"]["evaluated_metrics"]


def test_db_resolution_strictness():
    """11. Test strict database resolution rules (fails without explicit DB, no silent fallback)."""
    # 1. CLI argument takes precedence
    assert resolve_database_url("postgresql://custom:5432/db") == "postgresql://custom:5432/db"

    # 2. Environment variable is used if CLI is absent
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql://env:5432/db"}):
        assert resolve_database_url(None) == "postgresql://env:5432/db"

    # 3. Fails immediately if neither is provided (no silent test.db fallback)
    with patch.dict(os.environ, {}, clear=True):
        # Also ensure project .env is mocked out so it doesn't supply a fallback
        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(ConfigurationError) as excinfo:
                resolve_database_url(None)
            assert "Silent fallback to test.db is forbidden" in str(excinfo.value)
