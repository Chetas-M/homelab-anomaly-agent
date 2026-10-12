import pandas as pd
from sklearn.ensemble import IsolationForest
import json
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from analysis.eda import load_data
from analysis.features import extract_features

def test_gamma_if():
    os.environ['DATABASE_URL'] = "sqlite:///test.db"
    df = load_data()
    df['node_id'] = df['node_id'].str.lower()
    
    with open('analysis/outputs/experiment_log.json', 'r') as f:
        experiments = json.load(f)
        
    earliest_exp_start = pd.to_datetime(experiments[0]['start_time_utc'])
    split_time = earliest_exp_start - pd.Timedelta(minutes=30)
    
    train_df = df[df['ts'] < split_time].copy()
    eval_df = df[df['ts'] >= split_time].copy()
    
    train_feats = extract_features(train_df, 'gamma')
    eval_feats = extract_features(eval_df, 'gamma')
    
    exclude = ['ts', 'node_id', 'weak_label']
    features = [c for c in train_feats.columns if c not in exclude and pd.api.types.is_numeric_dtype(train_feats[c])]
    features = [c for c in features if not train_feats[c].isna().all()]
    
    print("Features including 'id':", 'id' in features)
    
    # Let's remove 'id'
    features_no_id = [f for f in features if f != 'id']
    
    # Train IF with 'id'
    iso_with = IsolationForest(n_estimators=100, contamination=0.01, random_state=42)
    iso_with.fit(train_feats[features].fillna(0))
    preds_with = iso_with.predict(eval_feats[features].fillna(0))
    print("Anomalies predicted WITH id:", (preds_with == -1).sum())
    
    # Train IF without 'id'
    iso_no = IsolationForest(n_estimators=100, contamination=0.01, random_state=42)
    iso_no.fit(train_feats[features_no_id].fillna(0))
    preds_no = iso_no.predict(eval_feats[features_no_id].fillna(0))
    print("Anomalies predicted WITHOUT id:", (preds_no == -1).sum())
    
    # Check if the synthetic stress window was caught
    exp = [e for e in experiments if e['node_id'] == 'gamma'][0]
    start = pd.to_datetime(exp['start_time_utc']).tz_localize(None)
    end = pd.to_datetime(exp['end_time_utc']).tz_localize(None)
    
    eval_feats['ts_naive'] = eval_feats['ts'].dt.tz_localize(None)
    mask = (eval_feats['ts_naive'] >= start) & (eval_feats['ts_naive'] <= end)
    
    print("Total samples in event:", mask.sum())
    print("Anomalies inside event WITH id:", (preds_with[mask] == -1).sum())
    print("Anomalies inside event WITHOUT id:", (preds_no[mask] == -1).sum())

if __name__ == '__main__':
    test_gamma_if()
