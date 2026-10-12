import sys
import os
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timezone
from sklearn.linear_model import LinearRegression

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from analysis.eda import load_data
from analysis.features import extract_features
from analysis.anomaly_model import calculate_mad, robust_z_score

def diagnose_mad(df, experiments, split_time):
    print("Diagnosing MAD...")
    train_df = df[df['ts'] < split_time].copy()
    eval_df = df[df['ts'] >= split_time].copy()
    
    mad_diagnosis = {}
    
    for node in df['node_id'].unique():
        train_feats = extract_features(train_df, node)
        eval_feats = extract_features(eval_df, node)
        if train_feats.empty or eval_feats.empty:
            continue
            
        exclude = ['ts', 'node_id', 'weak_label']
        features = [c for c in train_feats.columns if c not in exclude and pd.api.types.is_numeric_dtype(train_feats[c])]
        features = [c for c in features if not train_feats[c].isna().all()]
        
        k = len(features)
        
        node_stats = {
            "num_features": k,
            "features_with_mad_zero": 0,
            "median_mad": 0,
            "feature_details": {},
            "eval_exceedance_rates": {}
        }
        
        mads = []
        eval_z_scores = {}
        for f in features:
            med, mad = calculate_mad(train_feats[f])
            mads.append(mad)
            if mad == 0:
                node_stats["features_with_mad_zero"] += 1
                
            eval_f = eval_feats[f].fillna(med)
            z = robust_z_score(eval_f, med, mad).fillna(0)
            eval_z_scores[f] = np.abs(z)
            
            exceed_count = (np.abs(z) > 3.0).sum()
            node_stats["feature_details"][f] = {
                "train_median": float(med),
                "train_mad": float(mad),
                "eval_exceeds_3": int(exceed_count),
                "eval_exceeds_pct": float(exceed_count / len(eval_f))
            }
            
        node_stats["median_mad"] = float(np.median(mads))
        
        z_df = pd.DataFrame(eval_z_scores)
        exceed_mask = z_df > 3.0
        exceed_counts_per_row = exceed_mask.sum(axis=1)
        
        node_stats["eval_exceedance_rates"] = {
            "at_least_1": float((exceed_counts_per_row >= 1).mean()),
            "at_least_2": float((exceed_counts_per_row >= 2).mean()),
            "at_least_3": float((exceed_counts_per_row >= 3).mean()),
        }
        
        p_single = 0.0027
        theoretical_at_least_1 = 1 - (1 - p_single)**k
        node_stats["theoretical_family_wise_exceedance"] = float(theoretical_at_least_1)
        
        mad_diagnosis[node] = node_stats
        
    with open('analysis/outputs/mad_diagnosis.json', 'w') as f:
        json.dump(mad_diagnosis, f, indent=2)

def diagnose_gamma(df, experiments):
    print("Diagnosing Gamma...")
    gamma_exps = [e for e in experiments if e['node_id'] == 'gamma']
    if not gamma_exps:
        return
        
    exp = gamma_exps[0]
    start = pd.to_datetime(exp['start_time_utc'])
    end = pd.to_datetime(exp['end_time_utc'])
    
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
        
    window_start = start - pd.Timedelta(minutes=30)
    window_end = end + pd.Timedelta(minutes=30)
    
    gamma_df = df[(df['node_id'] == 'gamma') & (df['ts'] >= window_start) & (df['ts'] <= window_end)].sort_values('ts')
    
    diagnosis = {
        "experiment_id": exp["experiment_id"],
        "start_time": exp["start_time_utc"],
        "end_time": exp["end_time_utc"],
        "affected_metric": "net_out_bps",
        "baseline_stats": {},
        "during_event_stats": {}
    }
    
    baseline = gamma_df[(gamma_df['ts'] < start) | (gamma_df['ts'] > end)]
    event = gamma_df[(gamma_df['ts'] >= start) & (gamma_df['ts'] <= end)]
    
    for metric in ['net_out_bps', 'net_in_bps', 'cpu_pct', 'mem_pct', 'disk_read_bps', 'disk_write_bps']:
        if metric in gamma_df.columns and not gamma_df[metric].isna().all():
            diagnosis["baseline_stats"][metric] = {
                "median": float(baseline[metric].median()),
                "p95": float(baseline[metric].quantile(0.95)),
                "p99": float(baseline[metric].quantile(0.99))
            }
            diagnosis["during_event_stats"][metric] = {
                "median": float(event[metric].median()),
                "p95": float(event[metric].quantile(0.95)),
                "max": float(event[metric].max())
            }
            
    with open('analysis/outputs/gamma_diagnosis.json', 'w') as f:
        json.dump(diagnosis, f, indent=2)
        
    # Plot Gamma event
    plt.figure(figsize=(10, 5))
    plt.plot(gamma_df['ts'], gamma_df['net_out_bps'], marker='.', label='net_out_bps')
    plt.axvspan(start, end, color='red', alpha=0.2, label='Experiment Window')
    plt.title("Gamma Network Out - Synthetic Perturbation")
    plt.legend()
    plt.tight_layout()
    plt.savefig('analysis/outputs/gamma_net_out_event.png')
    plt.close()

def validate_dataset(df):
    print("Validating Dataset...")
    if not os.path.exists('analysis/outputs/summary.json'):
        print("Production summary.json not found.")
        return
        
    with open('analysis/outputs/summary.json', 'r') as f:
        prod_summary = json.load(f)
        
    dataset_comp = {}
    for node in df['node_id'].unique():
        prod_inv = prod_summary.get("dataset_inventory", {}).get(node, {})
        prod_met = prod_summary.get("metric_inventory", {}).get(node, {})
        
        ndf = df[df['node_id'] == node]
        
        comp = {
            "sample_count": {"prod": prod_inv.get("sample_count"), "test_db": len(ndf)},
            "first_timestamp": {"prod": prod_inv.get("first_timestamp"), "test_db": str(ndf['ts'].min())},
            "last_timestamp": {"prod": prod_inv.get("last_timestamp"), "test_db": str(ndf['ts'].max())},
            "metrics": {}
        }
        
        for m in ['cpu_pct', 'mem_pct', 'net_out_bps', 'disk_write_bps']:
            if m in ndf.columns and not ndf[m].isna().all():
                test_med = float(ndf[m].median())
                prod_med = prod_met.get(m, {}).get("median")
                comp["metrics"][m] = {
                    "median": {"prod": prod_med, "test_db": test_med},
                    "rel_diff": abs(test_med - prod_med) / (prod_med + 1e-9) if prod_med else None
                }
                
        dataset_comp[node] = comp
        
    with open('analysis/outputs/dataset_comparison.json', 'w') as f:
        json.dump(dataset_comp, f, indent=2)

def investigate_beta_residual(df, split_time):
    print("Investigating Beta Residual...")
    train_df = df[(df['node_id'] == 'beta') & (df['ts'] < split_time)].dropna(subset=['net_in_bps', 'net_out_bps']).copy()
    if len(train_df) < 10:
        return
        
    X = train_df[['net_in_bps']].values
    y = train_df['net_out_bps'].values
    
    lr = LinearRegression()
    lr.fit(X, y)
    r2 = lr.score(X, y)
    
    residual = y - lr.predict(X)
    
    res_stats = {
        "r2": float(r2),
        "residual_mean": float(np.mean(residual)),
        "residual_std": float(np.std(residual)),
        "residual_mad": float(np.median(np.abs(residual - np.median(residual))))
    }
    
    print(f"Beta Residual R2: {r2:.3f}")
    with open('analysis/outputs/beta_residual_diagnosis.json', 'w') as f:
        json.dump(res_stats, f, indent=2)

def check_window_sizes(df, experiments):
    counts = {}
    for exp in experiments:
        start = pd.to_datetime(exp['start_time_utc'])
        end = pd.to_datetime(exp['end_time_utc'])
        if start.tzinfo is None: start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None: end = end.replace(tzinfo=timezone.utc)
        
        duration = (end - start).total_seconds()
        expected = int(duration / 30) + 1
        
        mask = (df['node_id'] == exp['node_id']) & (df['ts'] >= start) & (df['ts'] <= end)
        actual = mask.sum()
        
        counts[exp['experiment_id']] = {
            "expected_samples": expected,
            "actual_samples": int(actual),
            "missing_samples": expected - int(actual)
        }
        
    with open('analysis/outputs/window_sizes.json', 'w') as f:
        json.dump(counts, f, indent=2)

def main():
    print("Loading data...")
    os.environ['DATABASE_URL'] = "sqlite:///test.db"
    df = load_data()
    df['node_id'] = df['node_id'].str.lower()
    
    with open('analysis/outputs/experiment_log.json', 'r') as f:
        experiments = json.load(f)
        
    earliest_exp_start = min([pd.to_datetime(e['start_time_utc']) for e in experiments])
    if earliest_exp_start.tzinfo is None:
        earliest_exp_start = earliest_exp_start.replace(tzinfo=timezone.utc)
    split_time = earliest_exp_start - pd.Timedelta(minutes=30)
    
    diagnose_mad(df, experiments, split_time)
    diagnose_gamma(df, experiments)
    validate_dataset(df)
    investigate_beta_residual(df, split_time)
    check_window_sizes(df, experiments)
    
    print("Diagnosis complete.")

if __name__ == "__main__":
    main()
