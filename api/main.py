import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
import numpy as np

from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select, desc, func, asc
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Query

from . import models, schemas
from .db import engine, get_db
from .attribution import compute_metric_attributions
from .simulation import simulation_manager
from .alerts import evaluate_node_alert_state

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create tables if they don't exist
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Home Lab Anomaly API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:5175"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

STALE_THRESHOLD_SECONDS = 120

@app.get("/health")
def health_check() -> Dict[str, str]:
    return {"status": "ok"}

@app.post("/ingest", status_code=status.HTTP_201_CREATED)
def ingest_metrics(payload: schemas.MetricPayload, db: Session = Depends(get_db)):
    try:
        db_metric = models.NodeMetric(**payload.model_dump())
        db.add(db_metric)
        db.commit()
        return {"status": "success"}
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error during ingestion: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error during ingestion: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload"
        )

@app.get("/last_seen/{node_id}", response_model=schemas.LastSeenResponse)
def get_last_seen(node_id: str, db: Session = Depends(get_db)):
    try:
        stmt = select(models.NodeMetric.ts).where(models.NodeMetric.node_id == node_id).order_by(desc(models.NodeMetric.ts)).limit(1)
        result = db.execute(stmt).scalar_one_or_none()
        
        if result is None:
            return schemas.LastSeenResponse(
                node_id=node_id,
                last_seen=None,
                online=False
            )
        
        # Determine if online
        now = datetime.now(timezone.utc)
        
        # Ensure result timestamp is aware for proper comparison
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
            
        time_diff = (now - result).total_seconds()
        is_online = time_diff <= STALE_THRESHOLD_SECONDS
        
        return schemas.LastSeenResponse(
            node_id=node_id,
            last_seen=result,
            online=is_online
        )
    except SQLAlchemyError as e:
        logger.error(f"Database error checking last_seen: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error"
        )

@app.get("/api/nodes", response_model=list[schemas.NodeOverview])
def get_nodes(db: Session = Depends(get_db)):
    try:
        stmt = (
            select(
                models.NodeMetric.node_id,
                func.min(models.NodeMetric.ts).label("first_seen"),
                func.max(models.NodeMetric.ts).label("last_seen"),
                func.count(models.NodeMetric.gpu_util_pct).label("gpu_count"),
                func.count(models.NodeMetric.load1).label("load_count"),
                func.count(models.NodeMetric.temp_c).label("temp_count")
            )
            .group_by(models.NodeMetric.node_id)
        )
        results = db.execute(stmt).all()
        
        now = datetime.now(timezone.utc)
        nodes = []
        for row in results:
            last_seen = row.last_seen
            if last_seen and last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            first_seen = row.first_seen
            if first_seen and first_seen.tzinfo is None:
                first_seen = first_seen.replace(tzinfo=timezone.utc)
                
            is_online = False
            if last_seen:
                is_online = (now - last_seen).total_seconds() <= STALE_THRESHOLD_SECONDS
                
            capabilities = schemas.NodeCapabilities(
                has_gpu=row.gpu_count > 0,
                has_load=row.load_count > 0,
                has_temp=row.temp_count > 0
            )

            score_stmt = select(models.AnomalyScore).where(models.AnomalyScore.node_id == row.node_id).order_by(desc(models.AnomalyScore.ts)).limit(1)
            score_row = db.execute(score_stmt).scalar_one_or_none()
            latest_score = score_row.score if score_row else None
            latest_is_anomalous = score_row.is_anomalous if score_row else None

            alert_state = evaluate_node_alert_state(db, row.node_id)
            
            nodes.append(schemas.NodeOverview(
                node_id=row.node_id,
                first_seen=first_seen,
                last_seen=last_seen,
                online=is_online,
                capabilities=capabilities,
                latest_score=latest_score,
                latest_is_anomalous=latest_is_anomalous,
                alert_status=alert_state["alert_status"],
                sustained_anomaly=alert_state["sustained_anomaly"],
                streak_count=alert_state["streak_count"],
            ))
        return nodes
    except SQLAlchemyError as e:
        logger.error(f"Database error in /api/nodes: {e}")
        raise HTTPException(status_code=500, detail="Database error")

@app.get("/api/nodes/{node_id}", response_model=schemas.NodeOverview)
def get_node(node_id: str, db: Session = Depends(get_db)):
    try:
        stmt = (
            select(
                func.min(models.NodeMetric.ts).label("first_seen"),
                func.max(models.NodeMetric.ts).label("last_seen"),
                func.count(models.NodeMetric.gpu_util_pct).label("gpu_count"),
                func.count(models.NodeMetric.load1).label("load_count"),
                func.count(models.NodeMetric.temp_c).label("temp_count")
            )
            .where(models.NodeMetric.node_id == node_id)
        )
        row = db.execute(stmt).first()
        if not row or row.first_seen is None:
            raise HTTPException(status_code=404, detail="Node not found")
            
        last_seen = row.last_seen
        if last_seen and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        first_seen = row.first_seen
        if first_seen and first_seen.tzinfo is None:
            first_seen = first_seen.replace(tzinfo=timezone.utc)
            
        now = datetime.now(timezone.utc)
        is_online = (now - last_seen).total_seconds() <= STALE_THRESHOLD_SECONDS if last_seen else False
        
        capabilities = schemas.NodeCapabilities(
            has_gpu=row.gpu_count > 0,
            has_load=row.load_count > 0,
            has_temp=row.temp_count > 0
        )

        score_stmt = select(models.AnomalyScore).where(models.AnomalyScore.node_id == node_id).order_by(desc(models.AnomalyScore.ts)).limit(1)
        score_row = db.execute(score_stmt).scalar_one_or_none()
        latest_score = score_row.score if score_row else None
        latest_is_anomalous = score_row.is_anomalous if score_row else None

        alert_state = evaluate_node_alert_state(db, node_id)

        return schemas.NodeOverview(
            node_id=node_id,
            first_seen=first_seen,
            last_seen=last_seen,
            online=is_online,
            capabilities=capabilities,
            latest_score=latest_score,
            latest_is_anomalous=latest_is_anomalous,
            alert_status=alert_state["alert_status"],
            sustained_anomaly=alert_state["sustained_anomaly"],
            streak_count=alert_state["streak_count"],
        )
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in /api/nodes/{node_id}: {e}")
        raise HTTPException(status_code=500, detail="Database error")

@app.get("/api/nodes/{node_id}/latest", response_model=schemas.MetricRecord)
def get_node_latest(node_id: str, db: Session = Depends(get_db)):
    try:
        stmt = (
            select(models.NodeMetric, models.AnomalyScore.score, models.AnomalyScore.is_anomalous)
            .outerjoin(
                models.AnomalyScore,
                (models.NodeMetric.node_id == models.AnomalyScore.node_id) & (models.NodeMetric.ts == models.AnomalyScore.ts)
            )
            .where(models.NodeMetric.node_id == node_id)
            .order_by(desc(models.NodeMetric.ts))
            .limit(1)
        )
        result = db.execute(stmt).first()
        if result is None:
            raise HTTPException(status_code=404, detail="Node not found")
        metric, score, is_anomalous = result
        record = schemas.MetricRecord.model_validate(metric)
        record.score = score
        record.is_anomalous = is_anomalous
        return record
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Database error")

@app.get("/api/nodes/{node_id}/metrics", response_model=list[schemas.MetricRecord])
def get_node_metrics(
    node_id: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = Query(default=1000, le=10000),
    db: Session = Depends(get_db)
):
    try:
        node_exists = db.execute(select(models.NodeMetric.id).where(models.NodeMetric.node_id == node_id).limit(1)).scalar_one_or_none()
        if node_exists is None:
            raise HTTPException(status_code=404, detail="Node not found")
            
        if not start and not end:
            subq = (
                select(models.NodeMetric.id)
                .where(models.NodeMetric.node_id == node_id)
                .order_by(desc(models.NodeMetric.ts))
                .limit(limit)
                .subquery()
            )
            stmt = (
                select(models.NodeMetric, models.AnomalyScore.score, models.AnomalyScore.is_anomalous)
                .outerjoin(
                    models.AnomalyScore,
                    (models.NodeMetric.node_id == models.AnomalyScore.node_id) & (models.NodeMetric.ts == models.AnomalyScore.ts)
                )
                .where(models.NodeMetric.id.in_(select(subq.c.id)))
                .order_by(asc(models.NodeMetric.ts))
            )
        else:
            stmt = (
                select(models.NodeMetric, models.AnomalyScore.score, models.AnomalyScore.is_anomalous)
                .outerjoin(
                    models.AnomalyScore,
                    (models.NodeMetric.node_id == models.AnomalyScore.node_id) & (models.NodeMetric.ts == models.AnomalyScore.ts)
                )
                .where(models.NodeMetric.node_id == node_id)
            )
            if start:
                stmt = stmt.where(models.NodeMetric.ts >= start)
            if end:
                stmt = stmt.where(models.NodeMetric.ts <= end)
            stmt = stmt.order_by(asc(models.NodeMetric.ts)).limit(limit)
            
        rows = db.execute(stmt).all()
        records = []
        for metric, score, is_anomalous in rows:
            rec = schemas.MetricRecord.model_validate(metric)
            rec.score = score
            rec.is_anomalous = is_anomalous
            records.append(rec)
        return records
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Database error")

@app.get("/api/nodes/{node_id}/scores", response_model=list[schemas.AnomalyScoreRecord])
def get_node_scores(
    node_id: str,
    limit: int = Query(default=100, le=1000),
    db: Session = Depends(get_db)
):
    try:
        stmt = (
            select(models.AnomalyScore)
            .where(models.AnomalyScore.node_id == node_id)
            .order_by(desc(models.AnomalyScore.ts))
            .limit(limit)
        )
        scores = db.execute(stmt).scalars().all()
        return list(scores)
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Database error")

@app.get("/api/nodes/{node_id}/quality", response_model=schemas.DataQuality)
def get_node_quality(
    node_id: str,
    window_hours: int = Query(default=24, ge=1, le=168),
    db: Session = Depends(get_db)
):
    try:
        node_exists = db.execute(select(models.NodeMetric.id).where(models.NodeMetric.node_id == node_id).limit(1)).scalar_one_or_none()
        if node_exists is None:
            raise HTTPException(status_code=404, detail="Node not found")
            
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=window_hours)
        
        stmt = select(models.NodeMetric).where(
            models.NodeMetric.node_id == node_id,
            models.NodeMetric.ts >= start_time,
            models.NodeMetric.ts <= end_time
        ).order_by(asc(models.NodeMetric.ts))
        
        results = db.execute(stmt).scalars().all()
        
        actual_samples = len(results)
        expected_samples = int((window_hours * 3600) / 30)
        coverage_pct = min(100.0, (actual_samples / expected_samples * 100.0)) if expected_samples > 0 else 0.0
        missing_samples_pct = max(0.0, 100.0 - coverage_pct)
        
        largest_gap = 0.0
        gaps_over_60s = 0
        null_counts = {
            "cpu_pct": 0, "mem_pct": 0, "swap_pct": 0, 
            "disk_read_bps": 0, "disk_write_bps": 0, "disk_used_pct": 0,
            "net_in_bps": 0, "net_out_bps": 0,
            "load1": 0, "load5": 0, "load15": 0,
            "temp_c": 0, "gpu_util_pct": 0, "gpu_vram_pct": 0
        }
        
        prev_ts = None
        for i, row in enumerate(results):
            ts = row.ts
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if prev_ts is not None:
                gap = (ts - prev_ts).total_seconds()
                if gap > largest_gap:
                    largest_gap = gap
                if gap > 60:
                    gaps_over_60s += 1
            prev_ts = ts
            
            for k in null_counts.keys():
                if getattr(row, k) is None:
                    null_counts[k] += 1
                    
        metrics_quality = {}
        for k, v in null_counts.items():
            null_pct = (v / actual_samples * 100.0) if actual_samples > 0 else 0.0
            metrics_quality[k] = schemas.MetricQuality(null_pct=null_pct)
            
        return schemas.DataQuality(
            node_id=node_id,
            window_hours=window_hours,
            actual_samples=actual_samples,
            expected_samples=expected_samples,
            coverage_pct=coverage_pct,
            missing_samples_pct=missing_samples_pct,
            largest_gap_seconds=largest_gap,
            gaps_over_60s=gaps_over_60s,
            metrics_quality=metrics_quality
        )
        
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Database error")

@app.get("/api/nodes/{node_id}/attributions", response_model=schemas.NodeAttributionResponse)
def get_node_attributions(node_id: str, db: Session = Depends(get_db)):
    try:
        node_exists = db.execute(select(models.NodeMetric.id).where(models.NodeMetric.node_id == node_id).limit(1)).scalar_one_or_none()
        if node_exists is None:
            raise HTTPException(status_code=404, detail="Node not found")

        latest_stmt = (
            select(models.NodeMetric)
            .where(models.NodeMetric.node_id == node_id)
            .order_by(desc(models.NodeMetric.ts))
            .limit(1)
        )
        latest_metric = db.execute(latest_stmt).scalar_one_or_none()
        if latest_metric is None:
            return schemas.NodeAttributionResponse(node_id=node_id, ts=None, attributions=[])

        latest_dict = {
            c.name: getattr(latest_metric, c.name)
            for c in models.NodeMetric.__table__.columns
        }
        
        attributions = compute_metric_attributions(node_id, latest_dict)
        return schemas.NodeAttributionResponse(
            node_id=node_id,
            ts=latest_metric.ts,
            attributions=attributions
        )
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_node_attributions: {e}")
        raise HTTPException(status_code=500, detail="Database error")

@app.get("/api/simulation/status", response_model=schemas.SimulationStatusResponse)
def get_simulation_status():
    return simulation_manager.get_status()

@app.post("/api/simulation/start", response_model=schemas.SimulationStatusResponse)
def start_simulation(req: schemas.SimulationStartRequest):
    try:
        return simulation_manager.start(req.scenario, req.duration_seconds)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/simulation/stop", response_model=schemas.SimulationStatusResponse)
def stop_simulation():
    return simulation_manager.stop()

@app.get("/api/simulation/metrics")
def get_simulation_metrics():
    return simulation_manager.get_metrics()

@app.get("/api/nodes/{node_id}/alert", response_model=schemas.NodeAlertState)
def get_node_alert(
    node_id: str,
    threshold: int = Query(default=3, ge=1, le=20),
    db: Session = Depends(get_db)
):
    try:
        node_exists = db.execute(select(models.NodeMetric.id).where(models.NodeMetric.node_id == node_id).limit(1)).scalar_one_or_none()
        if node_exists is None:
            raise HTTPException(status_code=404, detail="Node not found")
        return evaluate_node_alert_state(db, node_id, threshold=threshold)
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_node_alert: {e}")
        raise HTTPException(status_code=500, detail="Database error")

def compute_distribution(scores_list: list[float]) -> schemas.ScoreDistribution:
    if not scores_list:
        return schemas.ScoreDistribution()
    arr = np.array(scores_list)
    p = np.percentile(arr, [0, 25, 50, 75, 95, 100])
    return schemas.ScoreDistribution(
        min=float(p[0]),
        p25=float(p[1]),
        median=float(p[2]),
        p75=float(p[3]),
        p95=float(p[4]),
        max=float(p[5]),
    )

@app.get("/api/nodes/{node_id}/shadow/summary", response_model=schemas.ShadowComparisonSummary)
def get_node_shadow_summary(node_id: str, db: Session = Depends(get_db)):
    try:
        node_exists = db.execute(select(models.NodeMetric.id).where(models.NodeMetric.node_id == node_id).limit(1)).scalar_one_or_none()
        if node_exists is None:
            raise HTTPException(status_code=404, detail="Node not found")

        latest_shadow = db.execute(
            select(models.ShadowAnomalyScore)
            .where(models.ShadowAnomalyScore.node_id == node_id)
            .order_by(desc(models.ShadowAnomalyScore.ts))
            .limit(1)
        ).scalar_one_or_none()

        if latest_shadow is None:
            return schemas.ShadowComparisonSummary(
                node_id=node_id,
                candidate_active=False,
                frozen_score_distribution=schemas.ScoreDistribution(),
                candidate_score_distribution=schemas.ScoreDistribution(),
            )

        total_shadow = db.execute(
            select(func.count(models.ShadowAnomalyScore.id))
            .where(models.ShadowAnomalyScore.node_id == node_id)
        ).scalar() or 0

        total_warmup = db.execute(
            select(func.count(models.ShadowAnomalyScore.id))
            .where(
                models.ShadowAnomalyScore.node_id == node_id,
                models.ShadowAnomalyScore.scoring_status == "WARMUP"
            )
        ).scalar() or 0

        earliest_shadow_ts = db.execute(
            select(func.min(models.ShadowAnomalyScore.ts))
            .where(models.ShadowAnomalyScore.node_id == node_id)
        ).scalar()

        latest_shadow_ts = latest_shadow.ts

        stmt = (
            select(models.AnomalyScore, models.ShadowAnomalyScore)
            .join(
                models.ShadowAnomalyScore,
                (models.AnomalyScore.node_id == models.ShadowAnomalyScore.node_id) &
                (models.AnomalyScore.ts == models.ShadowAnomalyScore.ts)
            )
            .where(models.AnomalyScore.node_id == node_id)
            .order_by(desc(models.AnomalyScore.ts))
        )
        pairs = db.execute(stmt).all()

        prod_scores = []
        cand_scores = []
        prod_anom_count = 0
        cand_anom_count = 0
        concordance_count = 0
        disagreement_count = 0
        cand_only = 0
        frozen_only = 0
        both_anom = 0
        neither_anom = 0
        frozen_version = None

        valid_scored_count = 0
        for p_score, s_score in pairs:
            if frozen_version is None and p_score.model_version:
                frozen_version = p_score.model_version

            if p_score.score is not None and s_score.score is not None:
                valid_scored_count += 1
                prod_scores.append(float(p_score.score))
                cand_scores.append(float(s_score.score))

                p_anom = bool(p_score.is_anomalous)
                c_anom = bool(s_score.is_anomalous)

                if p_anom:
                    prod_anom_count += 1
                if c_anom:
                    cand_anom_count += 1

                if p_anom == c_anom:
                    concordance_count += 1
                else:
                    disagreement_count += 1

                if c_anom and not p_anom:
                    cand_only += 1
                elif p_anom and not c_anom:
                    frozen_only += 1
                elif p_anom and c_anom:
                    both_anom += 1
                else:
                    neither_anom += 1

        prod_rate = round((prod_anom_count / valid_scored_count * 100.0), 2) if valid_scored_count > 0 else 0.0
        cand_rate = round((cand_anom_count / valid_scored_count * 100.0), 2) if valid_scored_count > 0 else 0.0
        conc_rate = round((concordance_count / valid_scored_count * 100.0), 2) if valid_scored_count > 0 else 0.0
        disag_rate = round((disagreement_count / valid_scored_count * 100.0), 2) if valid_scored_count > 0 else 0.0

        return schemas.ShadowComparisonSummary(
            node_id=node_id,
            candidate_active=True,
            candidate_artifact_id=latest_shadow.artifact_id,
            candidate_version=latest_shadow.model_version,
            frozen_version=frozen_version or "1.0",
            earliest_shadow_ts=earliest_shadow_ts,
            latest_shadow_ts=latest_shadow_ts,
            total_shadow_samples=total_shadow,
            total_scored_samples=valid_scored_count,
            total_warmup_samples=total_warmup,
            production_anomaly_count=prod_anom_count,
            candidate_anomaly_count=cand_anom_count,
            production_anomaly_rate_pct=prod_rate,
            candidate_anomaly_rate_pct=cand_rate,
            concordance_count=concordance_count,
            concordance_rate_pct=conc_rate,
            disagreement_count=disagreement_count,
            disagreement_rate_pct=disag_rate,
            candidate_only_anomalies=cand_only,
            frozen_only_anomalies=frozen_only,
            both_anomalies=both_anom,
            neither_anomalies=neither_anom,
            frozen_score_distribution=compute_distribution(prod_scores),
            candidate_score_distribution=compute_distribution(cand_scores),
        )
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_node_shadow_summary: {e}")
        raise HTTPException(status_code=500, detail="Database error")

@app.get("/api/nodes/{node_id}/shadow/scores", response_model=list[schemas.ShadowScoreRecord])
def get_node_shadow_scores(
    node_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db)
):
    try:
        node_exists = db.execute(select(models.NodeMetric.id).where(models.NodeMetric.node_id == node_id).limit(1)).scalar_one_or_none()
        if node_exists is None:
            raise HTTPException(status_code=404, detail="Node not found")

        stmt = (
            select(models.ShadowAnomalyScore)
            .where(models.ShadowAnomalyScore.node_id == node_id)
            .order_by(desc(models.ShadowAnomalyScore.ts))
            .limit(limit)
        )
        return db.execute(stmt).scalars().all()
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_node_shadow_scores: {e}")
        raise HTTPException(status_code=500, detail="Database error")

