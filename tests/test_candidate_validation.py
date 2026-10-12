import pytest
import numpy as np
import pandas as pd
from scripts.validate_candidate_deep_dive import (
    load_models_and_configs,
    generate_synthetic_scenario,
    score_dataframe,
    audit_dataset_boundaries,
    verify_alert_semantics,
    run_shadow_comparison
)

def test_dataset_boundaries_and_temporal_leakage():
    beta_df, train_feats, test_feats = audit_dataset_boundaries()
    assert len(train_feats) == 32972
    assert len(test_feats) == 10991
    assert train_feats['ts'].max() < test_feats['ts'].min()

def test_known_anomalies_synthetic():
    fm, ffc, cm, cfc = load_models_and_configs()

    # 1. Normal baseline
    normal_df, normal_mask = generate_synthetic_scenario('normal', base_samples=30)
    normal_feats = from_analysis_extract_features(normal_df)
    _, c_anom_norm = score_dataframe(cm, cfc, normal_feats)
    assert c_anom_norm.sum() == 0, "Candidate produced false positives on normal baseline!"

    # 2. Network throughput flood
    net_df, net_mask = generate_synthetic_scenario('net_spike', base_samples=30)
    net_feats = from_analysis_extract_features(net_df)
    c_scores_net, c_anom_net = score_dataframe(cm, cfc, net_feats)
    net_indices = np.where(net_mask)[0]
    assert np.all(c_anom_net[net_indices]), "Candidate failed to detect 50 MB/s network throughput flood!"
    assert c_scores_net[net_indices].max() > 0.05

    # 3. Sustained CPU stress
    cpu_df, cpu_mask = generate_synthetic_scenario('sustained_cpu', base_samples=30)
    cpu_feats = from_analysis_extract_features(cpu_df)
    c_scores_cpu, c_anom_cpu = score_dataframe(cm, cfc, cpu_feats)
    cpu_indices = np.where(cpu_mask)[0]
    assert np.any(c_anom_cpu[cpu_indices]), "Candidate failed to detect sustained CPU stress!"
    assert c_scores_cpu[cpu_indices].max() > 0.0

    # 4. Disk flood
    disk_df, disk_mask = generate_synthetic_scenario('disk_spike', base_samples=30)
    disk_feats = from_analysis_extract_features(disk_df)
    c_scores_disk, c_anom_disk = score_dataframe(cm, cfc, disk_feats)
    disk_indices = np.where(disk_mask)[0]
    assert np.all(c_anom_disk[disk_indices]), "Candidate failed to detect disk flood!"
    assert c_scores_disk[disk_indices].max() > 0.0

def test_alert_semantics_comprehensive():
    verify_alert_semantics()

def from_analysis_extract_features(df):
    from analysis.features import extract_features
    return extract_features(df, 'beta')
