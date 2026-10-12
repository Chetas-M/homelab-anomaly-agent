import pandas as pd
from sklearn.ensemble import IsolationForest
import json
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from analysis.eda import load_data
from analysis.features import extract_features

def test_gamma_if_scores():
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
    
    features = [c for c in train_feats.columns if c not in ['ts', 'node_id', 'weak_label', 'id'] and pd.api.types.is_numeric_dtype(train_feats[c])]
    features = [c for c in features if not train_feats[c].isna().all()]
    
    iso_no = IsolationForest(n_estimators=100, contamination=0.01, random_state=42)
    iso_no.fit(train_feats[features].fillna(0))
    
    eval_feats['score'] = -iso_no.decision_function(eval_feats[features].fillna(0))
    
    exp = [e for e in experiments if e['node_id'] == 'gamma'][0]
    start = pd.to_datetime(exp['start_time_utc']).tz_localize(None)
    end = pd.to_datetime(exp['end_time_utc']).tz_localize(None)
    
    eval_feats['ts_naive'] = eval_feats['ts'].dt.tz_localize(None)
    mask = (eval_feats['ts_naive'] >= start) & (eval_feats['ts_naive'] <= end)
    
    print("Normal Scores - Median:", eval_feats.loc[~mask, 'score'].median(), "Max:", eval_feats.loc[~mask, 'score'].max())
    print("Event Scores - Median:", eval_feats.loc[mask, 'score'].median(), "Max:", eval_feats.loc[mask, 'score'].max())
    print("IF threshold offset:", iso_no.offset_)

if __name__ == '__main__':
    test_gamma_if_scores()
