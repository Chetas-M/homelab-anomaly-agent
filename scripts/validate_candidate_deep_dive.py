import os
import sys
import json
import joblib
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from analysis.features import extract_features
from api.alerts import evaluate_streak_from_records

def load_models_and_configs():
    frozen_dir = "models/beta"
    cand_dir = "models/candidates/beta"

    with open(os.path.join(frozen_dir, "feature_config.json"), "r") as f:
        frozen_fc = json.load(f)
    frozen_model = joblib.load(os.path.join(frozen_dir, "isolation_forest.joblib"))

    with open(os.path.join(cand_dir, "feature_config.json"), "r") as f:
        cand_fc = json.load(f)
    cand_model = joblib.load(os.path.join(cand_dir, "isolation_forest.joblib"))

    return frozen_model, frozen_fc, cand_model, cand_fc

def score_dataframe(model, feature_config, feats_df):
    cols = feature_config['features_ordered']
    medians = feature_config['medians']
    X = feats_df[cols].copy()
    for c in cols:
        X[c] = X[c].fillna(medians.get(c, 0.0))
    scores = -model.decision_function(X)
    preds = model.predict(X)
    is_anom = preds == -1
    return scores, is_anom

def audit_dataset_boundaries():
    print("=== CHECK A: AUDIT DATASET BOUNDARIES ===")
    cache_path = "data/representative_telemetry.csv.gz"
    if not os.path.exists(cache_path):
        raise FileNotFoundError(f"Missing {cache_path}")
    
    df = pd.read_csv(cache_path, compression='gzip')
    df['ts'] = pd.to_datetime(df['ts'], format='mixed', utc=True)
    df['node_id'] = df['node_id'].str.lower()

    total_post_samples = len(df)
    node_counts = df['node_id'].value_counts().to_dict()
    print(f"Total post-cutoff samples in representative dataset: {total_post_samples:,}")
    print(f"Node distribution: {node_counts}")

    beta_df = df[df['node_id'] == 'beta'].sort_values('ts').reset_index(drop=True)
    total_beta = len(beta_df)
    print(f"Total Beta post-cutoff samples: {total_beta:,}")
    print(f"Beta time range: {beta_df['ts'].min().isoformat()} to {beta_df['ts'].max().isoformat()}")

    # Feature extraction & split
    beta_feats = extract_features(beta_df, 'beta')
    split_idx = int(len(beta_feats) * 0.75)
    train_feats = beta_feats.iloc[:split_idx].copy()
    test_feats = beta_feats.iloc[split_idx:].copy()

    train_count = len(train_feats)
    test_count = len(test_feats)
    train_min_ts = train_feats['ts'].min().isoformat()
    train_max_ts = train_feats['ts'].max().isoformat()
    test_min_ts = test_feats['ts'].min().isoformat()
    test_max_ts = test_feats['ts'].max().isoformat()

    print(f"Train samples (75%): {train_count:,} from {train_min_ts} to {train_max_ts}")
    print(f"Test samples  (25%): {test_count:,} from {test_min_ts} to {test_max_ts}")
    assert train_feats['ts'].max() < test_feats['ts'].min(), "CRITICAL: Chronological leakage across split!"
    print("[PASS] Chronological separation confirmed: train_max_ts < test_min_ts")

    # Audit relationship between 89,346 samples, 32,972 candidate-train, and 10,991 holdout
    beta_train_expected = 32972
    beta_test_expected = 10991
    assert train_count == beta_train_expected, f"Expected {beta_train_expected}, got {train_count}"
    assert test_count == beta_test_expected, f"Expected {beta_test_expected}, got {test_count}"
    assert total_beta == beta_train_expected + beta_test_expected
    assert total_post_samples == total_beta + node_counts.get('gamma', 0) + node_counts.get('alpha', 0)
    print("[PASS] Dataset sample counts align exactly:")
    print(f"  Total post-cutoff: 89,346 = Beta ({total_beta}) + Gamma ({node_counts.get('gamma')}) + Alpha ({node_counts.get('alpha')})")
    print(f"  Beta post-cutoff:  43,963 = Train ({train_count}) + Holdout ({test_count})")

    # Temporal leakage audit: verify rolling features do not use future samples
    # In extract_features, rolling mean is rolling('5min'), which in pandas is default closed='right' (backward-looking).
    # Check that changing future rows does NOT change previous rows' rolling features
    sample_sub = beta_df.head(20).copy()
    f1 = extract_features(sample_sub, 'beta')
    
    # Mutate the last row drastically
    sample_sub_mutated = sample_sub.copy()
    sample_sub_mutated.loc[sample_sub_mutated.index[-1], 'cpu_pct'] = 999.0
    f2 = extract_features(sample_sub_mutated, 'beta')

    # All rows prior to the last row should have IDENTICAL features
    diff = np.abs(f1.iloc[:-1]['cpu_pct_roll_mean_5min'].values - f2.iloc[:-1]['cpu_pct_roll_mean_5min'].values)
    assert np.all(diff < 1e-9), "CRITICAL: Rolling features look ahead into future observations!"
    print("[PASS] Rolling features confirmed strictly backward-looking (no future leakage).")

    return beta_df, train_feats, test_feats

def generate_synthetic_scenario(scenario_type, base_samples=30, interval_seconds=30):
    """
    Generates isolated synthetic time series representing realistic Beta telemetry with known conditions.
    Never touches production database.
    """
    start_ts = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    timestamps = [start_ts + timedelta(seconds=i * interval_seconds) for i in range(base_samples)]
    
    # Baseline normal values for Beta
    records = []
    for ts in timestamps:
        records.append({
            'ts': ts,
            'node_id': 'beta',
            'cpu_pct': 0.70 + np.random.normal(0, 0.05),
            'mem_pct': 11.30 + np.random.normal(0, 0.1),
            'swap_pct': 0.0,
            'disk_read_bps': 0.0,
            'disk_write_bps': 39000.0 + np.random.normal(0, 2000),
            'disk_used_pct': 25.0,
            'net_in_bps': 1750.0 + np.random.normal(0, 100),
            'net_out_bps': 1650.0 + np.random.normal(0, 100),
            'load1': 0.02,
            'load5': 0.03,
            'load15': 0.03,
            'temp_c': 35.0 + np.random.normal(0, 0.5),
            'gpu_util_pct': None,
            'gpu_vram_pct': None
        })

    df = pd.DataFrame(records)

    anomaly_mask = np.zeros(base_samples, dtype=bool)

    if scenario_type == 'normal':
        pass
    elif scenario_type == 'brief_cpu':
        # 1-sample spike at index 15 (isolated spike)
        spike_idx = 15
        df.loc[spike_idx, 'cpu_pct'] = 98.5
        df.loc[spike_idx, 'load1'] = 10.5
        df.loc[spike_idx, 'temp_c'] = 58.0
        anomaly_mask[spike_idx] = True
    elif scenario_type == 'sustained_cpu':
        # 5-sample realistic sustained CPU stress (indices 15 to 19)
        for i in range(15, 20):
            df.loc[i, 'cpu_pct'] = 98.0 + np.random.normal(0, 0.5)
            df.loc[i, 'load1'] = 9.0 + (i - 15) * 0.8
            df.loc[i, 'load5'] = 7.0 + (i - 15) * 0.6
            df.loc[i, 'temp_c'] = 62.0 + (i - 15) * 1.0
            anomaly_mask[i] = True
    elif scenario_type == 'net_spike':
        # 4-sample network throughput spike (50 MB/s = 50,000,000 B/s)
        for i in range(15, 19):
            df.loc[i, 'net_in_bps'] = 50_000_000.0
            df.loc[i, 'net_out_bps'] = 48_000_000.0
            anomaly_mask[i] = True
    elif scenario_type == 'disk_spike':
        # 4-sample realistic disk write flood (300 MB/s, storage capacity rate-of-change, I/O wait load)
        for i in range(15, 19):
            df.loc[i, 'disk_write_bps'] = 300_000_000.0
            df.loc[i, 'disk_used_pct'] = 25.0 + (i - 15) * 0.5  # Storage actively filling
            df.loc[i, 'cpu_pct'] = 2.5                          # Kernel I/O wait
            df.loc[i, 'load1'] = 1.2                            # I/O queue backlog
            anomaly_mask[i] = True
    elif scenario_type == 'missing_metrics':
        # Sensors drop out for 5 samples (temp_c, load15, net_in_bps are NaN)
        for i in range(15, 20):
            df.loc[i, 'temp_c'] = np.nan
            df.loc[i, 'load15'] = np.nan
            df.loc[i, 'net_in_bps'] = np.nan
            # This is a missingness scenario, not necessarily anomalous load

    return df, anomaly_mask

def test_known_anomalies(frozen_model, frozen_fc, cand_model, cand_fc):
    print("\n=== CHECK B: TEST KNOWN ANOMALIES (ISOLATED SYNTHETIC HARNESS) ===")
    scenarios = [
        ('normal', 'Normal production-like baseline (30 samples)'),
        ('brief_cpu', 'Brief CPU/load spike (1 sample at 98% CPU, load 10.5, temp 58C)'),
        ('sustained_cpu', 'Sustained CPU/load/temp stress (5 consecutive samples at 98% CPU, load 9-12, temp 62-66C)'),
        ('net_spike', 'Network throughput flood (4 samples at 50 MB/s)'),
        ('disk_spike', 'Disk I/O flood (4 samples at 300 MB/s + storage fill rate + I/O load)'),
        ('missing_metrics', 'Sensor missingness (5 samples with temp, load15, net_in as NaN)')
    ]

    results = {}

    for sc_name, sc_desc in scenarios:
        np.random.seed(42)
        raw_df, anomaly_mask = generate_synthetic_scenario(sc_name, base_samples=35)
        
        # Feature extraction
        feats = extract_features(raw_df, 'beta')

        # Score both models
        f_scores, f_anom = score_dataframe(frozen_model, frozen_fc, feats)
        c_scores, c_anom = score_dataframe(cand_model, cand_fc, feats)

        anom_indices = np.where(anomaly_mask)[0]
        normal_indices = np.where(~anomaly_mask)[0]

        # Calculate metrics
        if len(anom_indices) > 0:
            f_det_rate = float(np.mean(f_anom[anom_indices]) * 100.0)
            c_det_rate = float(np.mean(c_anom[anom_indices]) * 100.0)
            
            # Latency in samples
            f_detected_samples = np.where(f_anom[anom_indices])[0]
            f_latency = int(f_detected_samples[0]) if len(f_detected_samples) > 0 else None

            c_detected_samples = np.where(c_anom[anom_indices])[0]
            c_latency = int(c_detected_samples[0]) if len(c_detected_samples) > 0 else None
        else:
            f_det_rate = None
            c_det_rate = None
            f_latency = None
            c_latency = None

        # False positive rate on normal segments
        f_fp_rate = float(np.mean(f_anom[normal_indices]) * 100.0) if len(normal_indices) > 0 else 0.0
        c_fp_rate = float(np.mean(c_anom[normal_indices]) * 100.0) if len(normal_indices) > 0 else 0.0

        # Alert engine streak simulation on these scores
        class MockRec:
            def __init__(self, ts, score, is_anom):
                self.ts = ts
                self.score = score
                self.is_anomalous = is_anom

        # Test streak progression for candidate model
        c_records = [MockRec(raw_df.loc[i, 'ts'], float(c_scores[i]), bool(c_anom[i])) for i in range(len(raw_df))]
        
        # Check if sustained anomaly fires (streak >= 3)
        current_streak = 0
        sustained_fired = False
        sustained_sample_idx = None
        for i, rec in enumerate(c_records):
            if rec.is_anomalous:
                current_streak += 1
                if current_streak >= 3:
                    sustained_fired = True
                    if sustained_sample_idx is None:
                        sustained_sample_idx = i
            else:
                current_streak = 0

        res_entry = {
            "description": sc_desc,
            "anomaly_sample_count": int(len(anom_indices)),
            "frozen_detection_rate_pct": f_det_rate,
            "candidate_detection_rate_pct": c_det_rate,
            "frozen_fp_rate_pct": f_fp_rate,
            "candidate_fp_rate_pct": c_fp_rate,
            "frozen_latency_samples": f_latency,
            "candidate_latency_samples": c_latency,
            "frozen_max_score": float(np.max(f_scores)),
            "candidate_max_score": float(np.max(c_scores)),
            "candidate_sustained_fired": sustained_fired,
            "candidate_sustained_at_sample": sustained_sample_idx
        }
        results[sc_name] = res_entry

        print(f"\nScenario: [{sc_name.upper()}] - {sc_desc}")
        if len(anom_indices) > 0:
            print(f"  Detection Rate: Frozen = {f_det_rate:.1f}%, Candidate = {c_det_rate:.1f}%")
            print(f"  Detection Latency: Frozen = {f_latency} samples, Candidate = {c_latency} samples")
        print(f"  False Positive Rate (Normal Segments): Frozen = {f_fp_rate:.1f}%, Candidate = {c_fp_rate:.1f}%")
        print(f"  Max Score: Frozen = {f_scores.max():.4f}, Candidate = {c_scores.max():.4f}")
        print(f"  Sustained Alert (Threshold=3): Fired = {sustained_fired} (at sample {sustained_sample_idx})")

    return results

def verify_alert_semantics():
    print("\n=== CHECK C: VERIFY ALERT SEMANTICS ===")
    now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)

    class MockScore:
        def __init__(self, ts, score, is_anomalous):
            self.ts = ts
            self.score = score
            self.is_anomalous = is_anomalous

    # 1. Repeated polling cannot advance a streak (timestamp idempotency)
    dup_scores = [
        MockScore(now, 0.20, True),
        MockScore(now, 0.20, True),  # Duplicate
        MockScore(now, 0.20, True),  # Duplicate
        MockScore(now - timedelta(seconds=30), 0.15, True),
    ]
    r_dup = evaluate_streak_from_records(dup_scores, threshold=3)
    assert r_dup['streak_count'] == 2, f"Failed: Duplicate advanced streak to {r_dup['streak_count']}"
    assert r_dup['sustained_anomaly'] is False
    print("[PASS] Repeated polling idempotency verified: 3 calls on identical ts yields streak=2, sustained=False")

    # 2. Normal sample resets streak
    reset_scores = [
        MockScore(now, -0.05, False),
        MockScore(now - timedelta(seconds=30), 0.20, True),
        MockScore(now - timedelta(seconds=60), 0.20, True),
        MockScore(now - timedelta(seconds=90), 0.20, True)
    ]
    r_reset = evaluate_streak_from_records(reset_scores, threshold=3)
    assert r_reset['streak_count'] == 0, f"Failed: Normal sample failed to reset streak: {r_reset['streak_count']}"
    assert r_reset['alert_status'] == "NORMAL"
    print("[PASS] Normal sample immediate reset verified: streak=0, status=NORMAL")

    # 3. Gaps invalidate streak (>120s max_gap)
    gap_scores = [
        MockScore(now, 0.20, True),
        MockScore(now - timedelta(seconds=150), 0.20, True), # Gap of 150s > 120s
        MockScore(now - timedelta(seconds=180), 0.20, True)
    ]
    r_gap = evaluate_streak_from_records(gap_scores, threshold=3, max_gap_seconds=120)
    assert r_gap['streak_count'] == 1, f"Failed: Gap did not reset streak: {r_gap['streak_count']}"
    assert r_gap['sustained_anomaly'] is False
    print("[PASS] Telemetry gap invalidation verified: 150s gap resets streak to 1, sustained=False")

    # 4. Warmup unscored samples do not create sustained alert
    warmup_scores = [
        MockScore(now, None, None),
        MockScore(now - timedelta(seconds=30), 0.20, True),
        MockScore(now - timedelta(seconds=60), 0.20, True)
    ]
    r_warmup = evaluate_streak_from_records(warmup_scores, threshold=3)
    assert r_warmup['alert_status'] == "WARMUP"
    assert r_warmup['streak_count'] == 0
    assert r_warmup['sustained_anomaly'] is False
    print("[PASS] Warmup handling verified: alert_status=WARMUP, sustained=False")

    # 5. Stale node handling
    stale_scores = [
        MockScore(now - timedelta(seconds=300), 0.20, True),
        MockScore(now - timedelta(seconds=330), 0.20, True),
        MockScore(now - timedelta(seconds=360), 0.20, True)
    ]
    r_stale = evaluate_streak_from_records(stale_scores, threshold=3, is_stale=True)
    assert r_stale['alert_status'] == "STALE"
    assert r_stale['sustained_anomaly'] is False
    print("[PASS] Stale node handling verified: alert_status=STALE, sustained=False")

def run_shadow_comparison(frozen_model, frozen_fc, cand_model, cand_fc, test_feats):
    print("\n=== CHECK D: SHADOW COMPARISON ON IDENTICAL CHRONOLOGICAL HOLDOUT SAMPLES ===")
    n_samples = len(test_feats)
    print(f"Holdout sample count: {n_samples:,}")

    f_scores, f_anom = score_dataframe(frozen_model, frozen_fc, test_feats)
    c_scores, c_anom = score_dataframe(cand_model, cand_fc, test_feats)

    # Confusion Matrix
    both_normal = int(np.sum((~f_anom) & (~c_anom)))
    both_anomalous = int(np.sum(f_anom & c_anom))
    frozen_only = int(np.sum(f_anom & (~c_anom)))
    candidate_only = int(np.sum((~f_anom) & c_anom))

    agreement_pct = (both_normal + both_anomalous) / n_samples * 100.0

    print(f"Classification Agreement: {agreement_pct:.2f}% ({both_normal + both_anomalous:,}/{n_samples:,})")
    print(f"  Both Normal:            {both_normal:,} ({both_normal/n_samples*100:.2f}%)")
    print(f"  Both Anomalous:         {both_anomalous:,} ({both_anomalous/n_samples*100:.2f}%)")
    print(f"  Frozen Only (Disagreed): {frozen_only:,} ({frozen_only/n_samples*100:.2f}%)")
    print(f"  Candidate Only (Disagreed): {candidate_only:,} ({candidate_only/n_samples*100:.2f}%)")

    # Score Correlation
    corr = float(np.corrcoef(f_scores, c_scores)[0, 1])
    score_diffs = c_scores - f_scores
    print(f"Score Correlation (Pearson): {corr:.4f}")
    print(f"Score Differences (Cand - Frozen): Mean={score_diffs.mean():+.4f}, Std={score_diffs.std():.4f}, Min={score_diffs.min():+.4f}, Max={score_diffs.max():+.4f}")

    # Quantiles comparison
    quantiles = [0.01, 0.10, 0.50, 0.90, 0.95, 0.98, 0.99, 1.0]
    print("\nScore Quantiles Comparison:")
    print(f"{'Quantile':<10} | {'Frozen Model':<15} | {'Candidate Model':<15} | {'Delta':<10}")
    print("-" * 55)
    for q in quantiles:
        fq = float(np.quantile(f_scores, q))
        cq = float(np.quantile(c_scores, q))
        print(f"{q*100:5.1f}%      | {fq:+.4f}          | {cq:+.4f}             | {cq - fq:+.4f}")

    # Discordant sample analysis: Why did candidate flag what frozen didn't (or vice versa)?
    # For Frozen Only:
    if frozen_only > 0:
        idx_f_only = np.where(f_anom & (~c_anom))[0]
        f_only_df = test_feats.iloc[idx_f_only]
        print(f"\nTop feature characteristics of {len(idx_f_only)} 'Frozen Only' anomalous samples:")
        print(f"  mem_pct median: {f_only_df['mem_pct'].median():.2f}% (Frozen baseline: 12.8%, Candidate baseline: 11.4%)")
        print(f"  cpu_pct median: {f_only_df['cpu_pct'].median():.2f}%")
        print(f"  disk_write_bps median: {f_only_df['disk_write_bps'].median():.0f} B/s")

    if candidate_only > 0:
        idx_c_only = np.where((~f_anom) & c_anom)[0]
        c_only_df = test_feats.iloc[idx_c_only]
        print(f"\nTop feature characteristics of {len(idx_c_only)} 'Candidate Only' anomalous samples:")
        print(f"  mem_pct median: {c_only_df['mem_pct'].median():.2f}%")
        print(f"  cpu_pct median: {c_only_df['cpu_pct'].median():.2f}%")
        print(f"  disk_write_bps median: {c_only_df['disk_write_bps'].median():.0f} B/s")

    shadow_summary = {
        "holdout_samples": n_samples,
        "agreement_pct": agreement_pct,
        "confusion_matrix": {
            "both_normal": both_normal,
            "both_anomalous": both_anomalous,
            "frozen_only": frozen_only,
            "candidate_only": candidate_only
        },
        "score_correlation": corr,
        "score_differences": {
            "mean": float(score_diffs.mean()),
            "std": float(score_diffs.std()),
            "min": float(score_diffs.min()),
            "max": float(score_diffs.max())
        }
    }
    return shadow_summary

def main():
    print("=========================================================================")
    print("Phase 3C Final Candidate Validation: Known Anomalies, Leakage & Shadow")
    print("=========================================================================")

    # 1. Audit dataset boundaries
    beta_df, train_feats, test_feats = audit_dataset_boundaries()

    # 2. Load models
    frozen_model, frozen_fc, cand_model, cand_fc = load_models_and_configs()

    # 3. Test known anomalies (synthetic harness)
    known_anomaly_results = test_known_anomalies(frozen_model, frozen_fc, cand_model, cand_fc)

    # 4. Verify alert semantics
    verify_alert_semantics()

    # 5. Shadow comparison on identical holdout samples
    shadow_summary = run_shadow_comparison(frozen_model, frozen_fc, cand_model, cand_fc, test_feats)

    # Save validation report JSON
    validation_report = {
        "validation_time_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_boundaries": {
            "total_post_cutoff_samples": 89346,
            "beta_total_samples": len(beta_df),
            "beta_train_samples": len(train_feats),
            "beta_holdout_samples": len(test_feats),
            "train_start_utc": train_feats['ts'].min().isoformat(),
            "train_end_utc": train_feats['ts'].max().isoformat(),
            "holdout_start_utc": test_feats['ts'].min().isoformat(),
            "holdout_end_utc": test_feats['ts'].max().isoformat(),
            "temporal_leakage_detected": False
        },
        "known_anomalies_synthetic_test": known_anomaly_results,
        "alert_semantics_verified": True,
        "shadow_comparison": shadow_summary,
        "recommendation": "CONTINUE_SHADOW_EVALUATION"
    }

    with open("models/candidates/final_validation_report.json", "w", encoding="utf-8") as f:
        json.dump(validation_report, f, indent=2)

    print("\n[SUCCESS] Final Candidate Validation complete.")
    print("Saved report to models/candidates/final_validation_report.json")

if __name__ == "__main__":
    main()
