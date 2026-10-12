import os
import sys
import json
import joblib
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from sqlalchemy import create_engine, select, func, text

# Add parent path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from analysis.features import extract_features
from api.models import NodeMetric, AnomalyScore

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://homelab:homelab@anomaly-postgres:5432/homelab_telemetry")
MODEL_DIR = os.environ.get("MODEL_DIR", "models")

def run_diagnosis():
    print("=" * 60)
    print("HOMELAB ANOMALY OBSERVABILITY — PIPELINE & MODEL DIAGNOSIS")
    print("=" * 60)
    
    engine = create_engine(DATABASE_URL)
    
    # 1. Database score distributions
    print("\n--- 1. ANOMALY SCORES POPULATION AUDIT ---")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT node_id, 
                   count(*) as total_samples,
                   sum(CASE WHEN score IS NULL THEN 1 ELSE 0 END) as warmup_count,
                   sum(CASE WHEN is_anomalous THEN 1 ELSE 0 END) as anomalous_count,
                   min(score) as min_score,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY score) as median_score,
                   avg(score) as mean_score,
                   max(score) as max_score
            FROM anomaly_scores
            GROUP BY node_id
            ORDER BY node_id
        """)).fetchall()
        for r in rows:
            scored = max(1, r[1] - r[2])
            pct = (r[3] / scored) * 100
            print(f"Node: {r[0]:<6} | Total: {r[1]:<5} | Warmup: {r[2]:<4} | Anomalous: {r[3]:<4} ({pct:.1f}%) | Min: {r[4]:.4f} if {r[4]} is not None else 'N/A' | Med: {r[5]:.4f} if {r[5]} is not None else 'N/A' | Mean: {r[6]:.4f} if {r[6]} is not None else 'N/A' | Max: {r[7]:.4f} if {r[7]} is not None else 'N/A'")
            
    # 2. Check for duplicates or timestamp anomalies
    print("\n--- 2. DATA INTEGRITY & TIMESTAMP AUDIT ---")
    with engine.connect() as conn:
        for node in ['alpha', 'beta', 'gamma']:
            dups = conn.execute(text(f"""
                SELECT ts, count(*) FROM node_metrics 
                WHERE node_id = '{node}' 
                GROUP BY ts HAVING count(*) > 1
            """)).fetchall()
            score_dups = conn.execute(text(f"""
                SELECT ts, count(*) FROM anomaly_scores 
                WHERE node_id = '{node}' 
                GROUP BY ts HAVING count(*) > 1
            """)).fetchall()
            print(f"Node {node:<6}: Telemetry duplicates: {len(dups)} | Score duplicates: {len(score_dups)}")

    # 3. Top Anomalous Samples for Beta
    print("\n--- 3. TOP ANOMALOUS SAMPLES FOR BETA ---")
    with engine.connect() as conn:
        top_anom = conn.execute(text("""
            SELECT s.ts, s.score, m.cpu_pct, m.mem_pct, m.disk_used_pct, m.net_in_bps, m.net_out_bps, m.load1, m.load15
            FROM anomaly_scores s
            JOIN node_metrics m ON s.node_id = m.node_id AND s.ts = m.ts
            WHERE s.node_id = 'beta' AND s.is_anomalous = true
            ORDER BY s.score DESC
            LIMIT 10
        """)).fetchall()
        for r in top_anom:
            net_diff = r[6] - r[5] if r[6] is not None and r[5] is not None else 0
            print(f"TS: {r[0]} | score: {r[1]:.4f} | CPU: {r[2]}% | Mem: {r[3]}% | Disk: {r[4]}% | net_in: {r[5]:.0f} bps | net_out: {r[6]:.0f} bps | net_diff: {net_diff:.0f} | load1: {r[7]} | load15: {r[8]}")

    # 4. Top Normal Samples for Beta
    print("\n--- 4. TOP NORMAL (LOWEST SCORE) SAMPLES FOR BETA ---")
    with engine.connect() as conn:
        top_norm = conn.execute(text("""
            SELECT s.ts, s.score, m.cpu_pct, m.mem_pct, m.disk_used_pct, m.net_in_bps, m.net_out_bps, m.load1, m.load15
            FROM anomaly_scores s
            JOIN node_metrics m ON s.node_id = m.node_id AND s.ts = m.ts
            WHERE s.node_id = 'beta' AND s.is_anomalous = false
            ORDER BY s.score ASC
            LIMIT 5
        """)).fetchall()
        for r in top_norm:
            net_diff = r[6] - r[5] if r[6] is not None and r[5] is not None else 0
            print(f"TS: {r[0]} | score: {r[1]:.4f} | CPU: {r[2]}% | Mem: {r[3]}% | Disk: {r[4]}% | net_in: {r[5]:.0f} bps | net_out: {r[6]:.0f} bps | net_diff: {net_diff:.0f} | load1: {r[7]} | load15: {r[8]}")

    # 5. Inspect Model Artifacts & Feature Drift
    print("\n--- 5. MODEL ATTRIBUTION / FEATURE CONTRIBUTION ---")
    node_dir = os.path.join(MODEL_DIR, "beta")
    with open(os.path.join(node_dir, "feature_config.json")) as f:
        config = json.load(f)
    model = joblib.load(os.path.join(node_dir, "isolation_forest.joblib"))
    expected_features = config["features_ordered"]
    medians = config["medians"]
    mads = config["mads"]

    with engine.connect() as conn:
        df = pd.read_sql(
            select(NodeMetric).where(NodeMetric.node_id == 'beta').order_by(NodeMetric.ts.desc()).limit(150),
            conn
        )
    df = df.sort_values('ts').reset_index(drop=True)
    df['ts'] = pd.to_datetime(df['ts'], utc=True)
    feats_df = extract_features(df, 'beta')
    
    X = feats_df[expected_features].copy()
    for f in expected_features:
        X[f] = X[f].fillna(medians.get(f, 0))
    X = X[expected_features]
    
    scores = -model.decision_function(X)
    feats_df['score'] = scores
    
    # Take the row with highest score
    max_idx = feats_df['score'].idxmax()
    worst_row = feats_df.loc[max_idx]
    print(f"Worst sample TS: {worst_row['ts']} with score: {worst_row['score']:.4f}")
    
    sample_x = X.loc[[max_idx]].copy()
    base_score = float(worst_row['score'])
    
    ablations = []
    for f in expected_features:
        perturbed_x = sample_x.copy()
        perturbed_x[f] = medians[f]
        perturbed_score = float(-model.decision_function(perturbed_x)[0])
        score_drop = base_score - perturbed_score
        
        val = worst_row[f]
        train_med = medians.get(f, 0)
        train_mad = mads.get(f, 0)
        robust_z = (val - train_med) / (1.4826 * train_mad) if train_mad > 0 else (0.0 if val == train_med else 10.0)
        
        ablations.append({
            "feature": f,
            "current_val": float(val) if pd.notna(val) else None,
            "train_median": float(train_med),
            "robust_z": float(robust_z),
            "score_drop": float(score_drop)
        })
        
    ablation_df = pd.DataFrame(ablations).sort_values(by="score_drop", ascending=False)
    print("\nTop 10 features driving the highest anomaly score on Beta:")
    print(ablation_df.head(10).to_string(index=False))

    print("\n" + "=" * 60)

if __name__ == "__main__":
    run_diagnosis()
