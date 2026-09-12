import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select, desc

from . import models, schemas
from .db import engine, get_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create tables if they don't exist
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Home Lab Anomaly API")

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
