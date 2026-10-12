import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest

def calculate_mad(series):
    median = series.median()
    # Fill NA just in case, though we expect caller to handle NAs or pass clean data
    mad = np.median(np.abs(series.dropna() - median))
    return median, mad

def robust_z_score(series, median, mad):
    if mad == 0:
        z = np.where(series == median, 0.0, np.sign(series - median) * 10.0)
        return pd.Series(z, index=series.index)
    return (series - median) / (1.4826 * mad)

class NodeAnomalyDetector:
    def __init__(self, node_id, features, if_config=None, mad_threshold=3.0):
        self.node_id = node_id
        self.features = features
        self.if_config = if_config or {
            'n_estimators': 100,
            'max_samples': 'auto',
            'contamination': 0.01,
            'random_state': 42
        }
        self.mad_threshold = mad_threshold
        self.iso_forest = IsolationForest(**self.if_config)
        self.medians = {}
        self.mads = {}
        
    def fit(self, df):
        # We assume missing values are handled before fitting (e.g., filled or dropped)
        X = df[self.features].copy()
        
        # Isolation Forest cannot handle NaN, so we fill with median during fit
        # Or require pre-imputed data. Let's do simple median imputation for missing features
        for feature in self.features:
            median, mad = calculate_mad(X[feature])
            self.medians[feature] = median
            self.mads[feature] = mad
            X[feature] = X[feature].fillna(median)
            
        self.iso_forest.fit(X)

    def predict(self, df):
        X = df[self.features].copy()
        
        # IF predictions
        # Impute missing values with training medians for inference
        X_imputed = X.copy()
        for feature in self.features:
            X_imputed[feature] = X_imputed[feature].fillna(self.medians.get(feature, 0))
            
        # sklearn IsolationForest decision_function: >0 is normal, <0 is anomalous
        # Invert so higher score = more anomalous
        if_scores = -self.iso_forest.decision_function(X_imputed)
        if_preds = self.iso_forest.predict(X_imputed)
        
        results = pd.DataFrame(index=df.index)
        results['if_score'] = if_scores
        results['if_anomaly'] = if_preds == -1
        
        # MAD predictions
        mad_scores = []
        for feature in self.features:
            z = robust_z_score(X[feature], self.medians[feature], self.mads[feature])
            # For NaNs, robust_z_score will be NaN.
            results[f'{feature}_robust_z'] = z
            mad_scores.append(np.abs(z.fillna(0))) # Fill NA with 0 for aggregate score
            
        mad_score = np.max(mad_scores, axis=0)
        results['mad_score'] = mad_score
        
        # Bonferroni correction for k features
        # p_family = 0.0027 -> p_indiv = 0.0027 / k
        # For k~25, z ~ 3.85. We use 3.85 dynamically or simply scale the threshold.
        # A threshold of 3.85 is a safe approximation for k in [10, 30]
        adjusted_threshold = 3.85 
        results['mad_anomaly'] = mad_score > adjusted_threshold
        
        return results
