import os
import sys
import time
import json
import logging
import joblib
import pandas as pd
import numpy as np
import signal
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, OperationalError

# Add parent to path to import local modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from api.models import Base, NodeMetric, AnomalyScore
from analysis.features import extract_features

# Configure logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("live_inference")

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///prod_telemetry.db")
MODEL_DIR = os.environ.get("MODEL_DIR", "models")
INFERENCE_POLL_INTERVAL = int(os.environ.get("INFERENCE_POLL_INTERVAL", "30"))
INFERENCE_BATCH_SIZE = int(os.environ.get("INFERENCE_BATCH_SIZE", "1000"))

def setup_database():
    engine = create_engine(DATABASE_URL)
    max_retries = 5
    for attempt in range(max_retries):
        try:
            Base.metadata.create_all(engine)
            return engine
        except OperationalError as e:
            if attempt == max_retries - 1:
                logger.error("Failed to connect to database after multiple retries.")
                raise e
            sleep_time = 2 ** attempt
            logger.warning(f"Database connection failed, retrying in {sleep_time}s...")
            time.sleep(sleep_time)

def load_models():
    """Load model artifacts for all nodes."""
    models = {}
    configs = {}
    metadata = {}
    
    manifest_path = os.path.join(MODEL_DIR, "model_manifest.json")
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
                expected_nodes = list(manifest.get("nodes", {}).keys())
        except Exception as e:
            logger.error(f"Failed to load manifest: {e}")
            expected_nodes = ["alpha", "beta", "gamma"]
    else:
        expected_nodes = ["alpha", "beta", "gamma"]
        
    import sklearn
    current_sklearn = sklearn.__version__

    for node in expected_nodes:
        node_dir = os.path.join(MODEL_DIR, node)
        if not os.path.exists(node_dir):
            logger.warning(f"Model directory for {node} not found at {node_dir}. Skipping.")
            continue
            
        try:
            iso_forest = joblib.load(os.path.join(node_dir, "isolation_forest.joblib"))
            with open(os.path.join(node_dir, "feature_config.json"), "r") as f:
                config = json.load(f)
            with open(os.path.join(node_dir, "metadata.json"), "r") as f:
                meta = json.load(f)
                
            if meta.get("sklearn_version") and meta["sklearn_version"] != current_sklearn:
                logger.warning(f"sklearn version mismatch for {node}: model uses {meta['sklearn_version']}, environment uses {current_sklearn}")
                
            models[node] = iso_forest
            configs[node] = config
            metadata[node] = meta
            logger.info(f"Successfully loaded model for node {node}.")
        except Exception as e:
            logger.error(f"Failed to load model for {node}: {e}")
            
    return models, configs, metadata

def get_watermark(session, node_id):
    """Get the last processed timestamp for a given node."""
    result = session.execute(
        select(func.max(AnomalyScore.ts)).where(AnomalyScore.node_id == node_id)
    ).scalar()
    
    if result is None:
        # If no previous score exists, start from INITIAL_BACKFILL_MINUTES ago based on latest telemetry
        backfill = int(os.environ.get("INITIAL_BACKFILL_MINUTES", "30"))
        latest_ts = session.execute(
            select(func.max(NodeMetric.ts)).where(NodeMetric.node_id == node_id)
        ).scalar()
        if latest_ts is None:
            return None
            
        if latest_ts.tzinfo is None:
            latest_ts = latest_ts.replace(tzinfo=timezone.utc)
            
        return latest_ts - pd.Timedelta(minutes=backfill)
    
    # Ensure timezone awareness
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result

def process_node(engine, node_id, model, config, meta):
    """Process new telemetry for a single node."""
    with Session(engine) as session:
        watermark = get_watermark(session, node_id)
        if watermark is None:
            return 0, 0, 0
            
        # We need a small history buffer to compute 5-minute rolling features and rate-of-change
        # A 6-minute history buffer ensures the first new point > watermark has sufficient context.
        history_start = watermark - pd.Timedelta(minutes=6)
        
        # Query new telemetry + bounded history
        # For sqlite compatibility, convert to naive UTC datetime
        query_start = history_start.replace(tzinfo=None) if engine.url.drivername == "sqlite" else history_start
        
        query = select(NodeMetric).where(
            NodeMetric.node_id == node_id,
            NodeMetric.ts >= query_start
        ).order_by(NodeMetric.ts.asc()).limit(INFERENCE_BATCH_SIZE)
        
        df = pd.read_sql(query, engine.connect())
        
        if df.empty:
            return 0, 0, 0
            
        df['ts'] = pd.to_datetime(df['ts'], utc=True)
            
        # Determine which rows are actually new and need scoring
        new_df = df[df['ts'] > watermark]
        if new_df.empty:
            return 0, 0, 0
            
        new_timestamps = new_df['ts'].values
        
        # 1. Authoritative feature extraction (applies to both history + new points)
        feats_df = extract_features(df, node_id)
        
        if feats_df.empty:
            return 0, 0, 0
            
        # 2. Filter extracted features to only the new timestamps we want to score
        feats_df = feats_df[feats_df['ts'] > watermark]
        if feats_df.empty:
            return 0, 0, 0
            
        expected_features = config["features_ordered"]
        
        # explicitly exclude 'id' as a safety measure just in case it leaked, though config shouldn't have it
        if "id" in expected_features:
            logger.error(f"FATAL: Database identity 'id' found in {node_id} feature config.")
            return 0, 0, 0
            
        # Ensure all expected features are present (even if NaN)
        for f in expected_features:
            if f not in feats_df.columns:
                feats_df[f] = np.nan
                
        # 3. Identify warmup samples (samples lacking sufficient rolling history)
        # Only evaluate to True if features needing rolling history are missing due to lacking historical context.
        temporal_features = [f for f in expected_features if any(sub in f for sub in ['_roll_', '_roc', '_diff', '_mean', '_std'])]
        if temporal_features:
            is_warmup = feats_df[temporal_features].isna().any(axis=1)
        else:
            is_warmup = pd.Series(False, index=feats_df.index)
        
        X = feats_df[expected_features].copy()
        
        # 4. Apply missing value policy identically to training
        if config["missing_value_policy"] == "median_imputation":
            medians = config["medians"]
            for f in expected_features:
                X[f] = X[f].fillna(medians.get(f, 0))
                
        # Ensure exact column order
        X = X[expected_features]
        
        # 5. Score with loaded model
        # Model is frozen, DO NOT call .fit()
        scores = -model.decision_function(X)
        preds = model.predict(X)
        
        # 6. Persist results
        scores_to_insert = []
        anomalies_detected = 0
        warmup_count = 0
        
        for i, (_, row) in enumerate(feats_df.iterrows()):
            is_w = bool(is_warmup.iloc[i])
            if is_w:
                score_val = None
                is_anom_val = None
                warmup_count += 1
            else:
                score_val = float(scores[i])
                is_anom_val = bool(preds[i] == -1)
                if is_anom_val:
                    anomalies_detected += 1
                
            scores_to_insert.append(AnomalyScore(
                node_id=node_id,
                ts=row['ts'],
                score=score_val,
                is_anomalous=is_anom_val,
                model_version=meta.get("methodology_version", "1.0")
            ))
            
        if not scores_to_insert:
            return 0, 0, 0
            
        try:
            if engine.url.drivername == "sqlite":
                from sqlalchemy.dialects.sqlite import insert
            else:
                from sqlalchemy.dialects.postgresql import insert
                
            # Convert models to dicts for bulk insert with on conflict do nothing
            values_to_insert = [
                {
                    "node_id": s.node_id, "ts": s.ts, "score": s.score,
                    "is_anomalous": s.is_anomalous, "model_version": s.model_version
                } for s in scores_to_insert
            ]
            
            stmt = insert(AnomalyScore).values(values_to_insert)
            stmt = stmt.on_conflict_do_nothing(index_elements=['node_id', 'ts'])
            
            session.execute(stmt)
            session.commit()
            return len(scores_to_insert), warmup_count, anomalies_detected
        except Exception as e:
            session.rollback()
            logger.error(f"Error persisting scores for {node_id}: {e}")
            return 0, 0, 0

def run_inference_loop():
    logger.info("Starting Live Inference Worker...")
    engine = setup_database()
    
    models, configs, metadata = load_models()
    if not models:
        logger.error("No models loaded. Exiting.")
        sys.exit(1)
        
    shutdown_flag = False
    def sig_handler(signum, frame):
        nonlocal shutdown_flag
        shutdown_flag = True
        logger.info(f"Received signal {signum}, gracefully shutting down...")
        
    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)
        
    while not shutdown_flag:
        try:
            # Healthcheck touch
            with open("/tmp/worker_health", "w") as f:
                f.write(str(time.time()))
                
            total_scored = 0
            total_warmup = 0
            
            for node, model in models.items():
                scored, warmup, anomalies = process_node(
                    engine, 
                    node, 
                    model, 
                    configs[node], 
                    metadata[node]
                )
                
                total_scored += scored
                total_warmup += warmup
                
                if anomalies > 0:
                    logger.warning(f"Node {node}: Detected {anomalies} anomalies.")
                    
            if total_scored > 0 or total_warmup > 0:
                logger.info(f"Processed batch: {total_scored} scored, {total_warmup} warmup.")
                
        except OperationalError as e:
            logger.error(f"Database operational error: {e}. Retrying in 10s...")
            time.sleep(10)
            continue
        except Exception as e:
            logger.error(f"Unexpected error in inference loop: {e}", exc_info=True)
            time.sleep(10)
            continue
            
        time.sleep(INFERENCE_POLL_INTERVAL)

if __name__ == "__main__":
    run_inference_loop()
