import os
import sys
import json
import joblib
import pandas as pd
import numpy as np
import sklearn
from datetime import datetime, timezone
import platform

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from analysis.eda import load_data
from analysis.features import extract_features
from analysis.anomaly_model import NodeAnomalyDetector

def main():
    print("Starting production model training pipeline...")
    
    # Configuration
    model_dir = "models"
    out_dir = "analysis/outputs"
    os.makedirs(model_dir, exist_ok=True)
    
    # 1. Load Data
    print("Loading production telemetry...")
    if 'DATABASE_URL' not in os.environ:
        os.environ['DATABASE_URL'] = "sqlite:///prod_telemetry.db"
    df = load_data()
    df['node_id'] = df['node_id'].str.lower()
    df['node_id'] = df['node_id'].replace('alpha-win', 'alpha') # normalize alpha node
    
    # 2. Leakage Audit - Establish chronological cutoff
    exp_file = os.path.join(out_dir, "real_experiment_log.json")
    if not os.path.exists(exp_file):
        raise FileNotFoundError(f"Experiment log not found at {exp_file}. Required for chronological split.")
        
    with open(exp_file, 'r') as f:
        experiments = json.load(f)
        
    earliest_exp_start = min([pd.to_datetime(e['start_time_utc']) for e in experiments])
    if earliest_exp_start.tzinfo is None:
        earliest_exp_start = earliest_exp_start.replace(tzinfo=timezone.utc)
        
    # Strictly earlier than experiments (add small buffer as before)
    cutoff_time = earliest_exp_start - pd.Timedelta(minutes=30)
    
    print(f"Chronological Cutoff (Strictly before experiments): {cutoff_time.isoformat()}")
    
    train_df = df[df['ts'] < cutoff_time].copy()
    print(f"Total training samples: {len(train_df)}")
    
    # Excluded periods documentation
    excluded_periods = [{"node": e.get('node_id', 'unknown'), "start": e['start_time_utc'], "end": e['end_time_utc']} for e in experiments]
    
    manifest = {
        "pipeline_version": "1.0",
        "training_time_utc": datetime.now(timezone.utc).isoformat(),
        "cutoff_time_utc": cutoff_time.isoformat(),
        "excluded_experiment_periods": excluded_periods,
        "nodes": {}
    }
    
    report_lines = [
        "# Production Model Training Report",
        "",
        "## Leakage Audit",
        f"- **Training Cutoff Time:** {cutoff_time.isoformat()}",
        "- **Excluded Experiment Periods:**",
    ]
    for e in excluded_periods:
        report_lines.append(f"  - {e['node']}: {e['start']} to {e['end']}")
    report_lines.append("")
    
    nodes = ['alpha', 'beta', 'gamma']
    for node in nodes:
        print(f"\nTraining model for node: {node}")
        node_dir = os.path.join(model_dir, node)
        os.makedirs(node_dir, exist_ok=True)
        
        # Extract features
        train_feats = extract_features(train_df, node)
        if train_feats.empty:
            print(f"Warning: No training data for node {node}")
            continue
            
        # Select feature columns strictly avoiding database identities
        exclude = ['ts', 'node_id', 'id']
        feature_cols = [c for c in train_feats.columns if c not in exclude and pd.api.types.is_numeric_dtype(train_feats[c])]
        
        # Remove columns that are all NaN in training
        feature_cols = [c for c in feature_cols if not train_feats[c].isna().all()]
        
        # Explicit assertion for requirement 3: never use database identity
        assert 'id' not in feature_cols, f"Database identity 'id' leaked into features for {node}"
        
        # Initialize and fit
        detector = NodeAnomalyDetector(node_id=node, features=feature_cols)
        detector.fit(train_feats)
        
        # Sanity Checks: Predict on training data
        preds = detector.predict(train_feats)
        if_scores = preds['if_score']
        
        # Prepare metadata
        n_samples = len(train_feats)
        n_features = len(feature_cols)
        train_start = train_feats['ts'].min().isoformat() if n_samples > 0 else None
        train_end = train_feats['ts'].max().isoformat() if n_samples > 0 else None
        
        node_metadata = {
            "node_id": node,
            "model_type": "IsolationForest",
            "hyperparameters": detector.if_config,
            "training_samples": n_samples,
            "feature_count": n_features,
            "training_start_utc": train_start,
            "training_end_utc": train_end,
            "random_seed": detector.if_config.get('random_state', 42),
            "sklearn_version": sklearn.__version__,
            "python_version": platform.python_version(),
            "creation_time_utc": datetime.now(timezone.utc).isoformat()
        }
        
        feature_config = {
            "node_id": node,
            "features_ordered": feature_cols,
            "missing_value_policy": "median_imputation",
            "medians": detector.medians,
            "mads": detector.mads,
            "methodology_version": "1.0"
        }
        
        # Persist artifacts
        joblib.dump(detector.iso_forest, os.path.join(node_dir, "isolation_forest.joblib"))
        
        with open(os.path.join(node_dir, "metadata.json"), "w") as f:
            json.dump(node_metadata, f, indent=2)
            
        with open(os.path.join(node_dir, "feature_config.json"), "w") as f:
            json.dump(feature_config, f, indent=2)
            
        manifest["nodes"][node] = {
            "status": "trained",
            "samples": n_samples,
            "features": n_features
        }
        
        # Add to report
        report_lines.extend([
            f"## Node: {node}",
            f"- **Training Samples:** {n_samples}",
            f"- **Feature Count:** {n_features}",
            f"- **Time Range:** {train_start} to {train_end}",
            f"- **IF Hyperparameters:** `n_estimators={detector.if_config.get('n_estimators')}`, `contamination={detector.if_config.get('contamination')}`",
            f"- **Median Anomaly Score (Train):** {if_scores.median():.3f}",
            f"- **99th Pct Anomaly Score (Train):** {if_scores.quantile(0.99):.3f}",
            "### Selected Features",
            ", ".join(feature_cols),
            ""
        ])
        print(f"Node {node} training complete. {n_samples} samples, {n_features} features.")
        
    with open(os.path.join(model_dir, "model_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
        
    with open(os.path.join(model_dir, "training_report.md"), "w") as f:
        f.write("\n".join(report_lines))
        
    print(f"\nPipeline complete. Artifacts saved in {model_dir}/")

if __name__ == "__main__":
    main()
