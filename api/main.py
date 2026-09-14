import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select, desc, func, asc
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Query

from . import models, schemas
from .db import engine, get_db

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
            
            nodes.append(schemas.NodeOverview(
                node_id=row.node_id,
                first_seen=first_seen,
                last_seen=last_seen,
                online=is_online,
                capabilities=capabilities
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
        return schemas.NodeOverview(
            node_id=node_id,
            first_seen=first_seen,
            last_seen=last_seen,
            online=is_online,
            capabilities=capabilities
        )
    except SQLAlchemyError as e:
        logger.error(f"Database error in /api/nodes/{node_id}: {e}")
        raise HTTPException(status_code=500, detail="Database error")

@app.get("/api/nodes/{node_id}/latest", response_model=schemas.MetricRecord)
def get_node_latest(node_id: str, db: Session = Depends(get_db)):
    try:
        stmt = select(models.NodeMetric).where(models.NodeMetric.node_id == node_id).order_by(desc(models.NodeMetric.ts)).limit(1)
        result = db.execute(stmt).scalar_one_or_none()
        if result is None:
            raise HTTPException(status_code=404, detail="Node not found")
        return result
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
            
        stmt = select(models.NodeMetric).where(models.NodeMetric.node_id == node_id)
        if start:
            stmt = stmt.where(models.NodeMetric.ts >= start)
        if end:
            stmt = stmt.where(models.NodeMetric.ts <= end)
            
        if not start and not end:
            from sqlalchemy.orm import aliased
            subq = select(models.NodeMetric).where(models.NodeMetric.node_id == node_id).order_by(desc(models.NodeMetric.ts)).limit(limit).subquery()
            Alias = aliased(models.NodeMetric, subq)
            stmt = select(Alias).order_by(asc(Alias.ts))
        else:
            stmt = stmt.order_by(asc(models.NodeMetric.ts)).limit(limit)
            
        results = db.execute(stmt).scalars().all()
        return list(results)
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
