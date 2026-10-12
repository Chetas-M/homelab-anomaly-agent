import sys
import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import matplotlib.pyplot as plt
from sklearn.metrics import precision_score, recall_score, f1_score, roc_auc_score, roc_curve

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from analysis.eda import load_data
from analysis.features import extract_features
from analysis.anomaly_model import NodeAnomalyDetector

def generate_weak_labels(df, experiments):
    # Default normal
    df['weak_label'] = False
    
    for exp in experiments:
        node = exp['node_id'].lower()
        if node == 'alpha-win':
            node = 'alpha'
        start = pd.to_datetime(exp['start_time_utc'])
        end = pd.to_datetime(exp['end_time_utc'])
        
        # Ensure timezone awareness
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
            
        mask = (df['node_id'] == node) & (df['ts'] >= start) & (df['ts'] <= end)
        df.loc[mask, 'weak_label'] = True
        
    return df

def calculate_metrics(y_true, y_pred, y_score=None):
    if len(y_true) == 0:
        return {"precision": 0, "recall": 0, "f1": 0, "roc_auc": 0}
        
    p = precision_score(y_true, y_pred, zero_division=0)
    r = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    
    roc_auc = None
    if y_score is not None and len(np.unique(y_true)) > 1:
        try:
            roc_auc = roc_auc_score(y_true, y_score)
        except ValueError:
            pass
            
    tp = sum((y_true == 1) & (y_pred == 1))
    fp = sum((y_true == 0) & (y_pred == 1))
    tn = sum((y_true == 0) & (y_pred == 0))
    fn = sum((y_true == 1) & (y_pred == 0))
    
    return {
        "precision": float(p),
        "recall": float(r),
        "f1": float(f1),
        "roc_auc": float(roc_auc) if roc_auc else None,
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn)
    }

def main():
    out_dir = 'analysis/outputs'
    os.makedirs(out_dir, exist_ok=True)
    
    # 1. Load data and experiments
    print("Loading data...")
    df = load_data()
    df['node_id'] = df['node_id'].str.lower()
    
    exp_file = os.getenv('EXPERIMENT_LOG', 'experiment_log.json')
    with open(os.path.join(out_dir, exp_file), 'r') as f:
        experiments = json.load(f)
        
    # 2. Add weak labels
    df = generate_weak_labels(df, experiments)
    
    # 3. Chronological split
    # Find the earliest experiment start time, and split a bit before it
    earliest_exp_start = min([pd.to_datetime(e['start_time_utc']) for e in experiments])
    if earliest_exp_start.tzinfo is None:
        earliest_exp_start = earliest_exp_start.replace(tzinfo=timezone.utc)
        
    split_time = earliest_exp_start - pd.Timedelta(minutes=30)
    
    train_df = df[df['ts'] < split_time].copy()
    eval_df = df[df['ts'] >= split_time].copy()
    
    print(f"Train samples: {len(train_df)}, Eval samples: {len(eval_df)}")
    
    results = {}
    all_eval_preds = []
    
    for node in df['node_id'].unique():
        print(f"\nProcessing node: {node}")
        
        # 4. Feature engineering
        train_feats = extract_features(train_df, node)
        eval_feats = extract_features(eval_df, node)
        
        if train_feats.empty or eval_feats.empty:
            print(f"Skipping {node} - insufficient data")
            continue
            
        # Determine features to use (numeric columns excluding ts, node_id, weak_label, id)
        exclude = ['ts', 'node_id', 'weak_label', 'id']
        feature_cols = [c for c in train_feats.columns if c not in exclude and pd.api.types.is_numeric_dtype(train_feats[c])]
        
        # Remove columns that are all NaN in training
        feature_cols = [c for c in feature_cols if not train_feats[c].isna().all()]
        
        # Save feature selection for report
        feature_selection = [{"feature": c, "source": "extracted", "status": "selected"} for c in feature_cols]
        
        # 5. Initialize and fit models
        detector = NodeAnomalyDetector(node_id=node, features=feature_cols)
        detector.fit(train_feats)
        
        # 6. Predict on evaluation set
        preds = detector.predict(eval_feats)
        
        # Combine back with eval_feats for true labels
        eval_with_preds = eval_feats.copy()
        for col in preds.columns:
            eval_with_preds[col] = preds[col].values
            
        # Merge weak_labels
        node_eval = eval_df[eval_df['node_id'] == node].sort_values('ts')
        eval_with_preds['weak_label'] = node_eval['weak_label'].values
        
        all_eval_preds.append(eval_with_preds)
        
        # 7. Calculate metrics
        y_true = eval_with_preds['weak_label'].astype(int)
        
        if_metrics = calculate_metrics(y_true, eval_with_preds['if_anomaly'], eval_with_preds['if_score'])
        mad_metrics = calculate_metrics(y_true, eval_with_preds['mad_anomaly'], eval_with_preds['mad_score'])
        
        results[node] = {
            "if_metrics": if_metrics,
            "mad_metrics": mad_metrics,
            "population": {
                "normal": int((y_true == 0).sum()),
                "weakly_anomalous": int((y_true == 1).sum()),
                "predicted_anomalies_if": int(eval_with_preds['if_anomaly'].sum()),
                "predicted_anomalies_mad": int(eval_with_preds['mad_anomaly'].sum())
            },
            "features_selected": feature_cols
        }
        
        print(f"IF: P={if_metrics['precision']:.3f}, R={if_metrics['recall']:.3f}, F1={if_metrics['f1']:.3f} | TP={if_metrics['tp']} FP={if_metrics['fp']} TN={if_metrics['tn']} FN={if_metrics['fn']}")
        print(f"MAD: P={mad_metrics['precision']:.3f}, R={mad_metrics['recall']:.3f}, F1={mad_metrics['f1']:.3f} | TP={mad_metrics['tp']} FP={mad_metrics['fp']} TN={mad_metrics['tn']} FN={mad_metrics['fn']}")
        
        # 8. Plots
        plt.figure(figsize=(12, 6))
        plt.plot(eval_with_preds['ts'], eval_with_preds['if_score'], label='IF Score', alpha=0.7)
        plt.plot(eval_with_preds['ts'], eval_with_preds['mad_score'], label='MAD Score', alpha=0.7)
        
        # Highlight stress windows
        for exp in experiments:
            if exp['node_id'] == node:
                start = pd.to_datetime(exp['start_time_utc'])
                end = pd.to_datetime(exp['end_time_utc'])
                plt.axvspan(start, end, color='red', alpha=0.2, label='Stress Window')
                
        plt.title(f"Anomaly Scores - {node}")
        plt.legend(loc='upper right')
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, f'eval_scores_{node}.png'))
        plt.close()
        
    # Combine predictions and save
    final_preds = pd.concat(all_eval_preds, ignore_index=True)
    final_preds.to_csv(os.path.join(out_dir, 'predictions.csv'), index=False)
    
    with open(os.path.join(out_dir, 'evaluation.json'), 'w') as f:
        json.dump({"split_time_utc": split_time.isoformat(), "results": results}, f, indent=2)
        
    # Generate human readable report
    generate_report(results, out_dir)
    print("Evaluation complete. Outputs saved.")

def generate_report(results, out_dir):
    with open(os.path.join(out_dir, 'model_report.md'), 'w') as f:
        f.write("# Phase 2.5: Model Evaluation Report\n\n")
        f.write("## Performance Comparison\n\n")
        f.write("| Node | Method | Precision | Recall | F1 | ROC-AUC | TP | FP | FN | TN | Predicted anomalies |\n")
        f.write("|------|--------|-----------|--------|----|---------|----|----|----|----|---------------------|\n")
        
        for node, data in results.items():
            ifm = data['if_metrics']
            mad = data['mad_metrics']
            pop = data['population']
            
            f.write(f"| {node} | IF | {ifm['precision']:.3f} | {ifm['recall']:.3f} | {ifm['f1']:.3f} | {ifm['roc_auc'] or 0:.3f} | {ifm['tp']} | {ifm['fp']} | {ifm['fn']} | {ifm['tn']} | {pop['predicted_anomalies_if']} |\n")
            f.write(f"| {node} | MAD | {mad['precision']:.3f} | {mad['recall']:.3f} | {mad['f1']:.3f} | {mad['roc_auc'] or 0:.3f} | {mad['tp']} | {mad['fp']} | {mad['fn']} | {mad['tn']} | {pop['predicted_anomalies_mad']} |\n")
            
        f.write("\n## Population Statistics\n\n")
        for node, data in results.items():
            pop = data['population']
            f.write(f"### {node}\n")
            f.write(f"- Normal instances: {pop['normal']}\n")
            f.write(f"- Weakly anomalous instances: {pop['weakly_anomalous']}\n\n")

if __name__ == "__main__":
    main()
