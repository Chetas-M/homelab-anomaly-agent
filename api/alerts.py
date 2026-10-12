import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from api import models

logger = logging.getLogger(__name__)

DEFAULT_SUSTAINED_THRESHOLD = 3
DEFAULT_MAX_GAP_SECONDS = 120
DEFAULT_STALE_SECONDS = 120

def evaluate_streak_from_records(
    scores: List[Any],
    threshold: int = DEFAULT_SUSTAINED_THRESHOLD,
    max_gap_seconds: int = DEFAULT_MAX_GAP_SECONDS,
    is_stale: bool = False
) -> Dict[str, Any]:
    """
    Pure evaluation of sustained anomaly streak from a descending chronological
    list of scored records.
    
    Status semantics:
    - NORMAL: Latest scored sample is normal (is_anomalous=False), streak=0.
    - ANOMALOUS SAMPLE: 1 <= streak < threshold. Transient anomaly observed.
    - SUSTAINED ANOMALY: streak >= threshold without intervening gaps or resets.
    - WARMUP: Latest sample is unscored/warmup.
    - STALE: Node telemetry has stopped arriving (> stale_seconds).
    - NO_DATA: No records available.
    """
    if not scores:
        return {
            "alert_status": "STALE" if is_stale else "NO_DATA",
            "sustained_anomaly": False,
            "streak_count": 0,
            "threshold": threshold,
            "latest_score": None,
            "latest_is_anomalous": None,
            "is_stale": is_stale,
            "message": "No telemetry scores available."
        }

    latest = scores[0]
    latest_score = getattr(latest, "score", None)
    latest_is_anom = getattr(latest, "is_anomalous", None)
    latest_ts = getattr(latest, "ts", None)

    # 1. Warmup check
    if latest_score is None or latest_is_anom is None:
        return {
            "alert_status": "STALE" if is_stale else "WARMUP",
            "sustained_anomaly": False,
            "streak_count": 0,
            "threshold": threshold,
            "latest_score": None,
            "latest_is_anomalous": None,
            "is_stale": is_stale,
            "message": "Warmup sample: insufficient rolling history for model inference."
        }

    # 2. Latest sample is normal -> streak is 0
    if not latest_is_anom:
        return {
            "alert_status": "STALE" if is_stale else "NORMAL",
            "sustained_anomaly": False,
            "streak_count": 0,
            "threshold": threshold,
            "latest_score": latest_score,
            "latest_is_anomalous": False,
            "is_stale": is_stale,
            "message": f"Normal behavior: anomaly score {latest_score:.4f} within nominal bounds."
        }

    # 3. Latest sample is anomalous -> count consecutive anomalous samples backwards
    streak = 1
    prev_ts = latest_ts
    if prev_ts and prev_ts.tzinfo is None:
        prev_ts = prev_ts.replace(tzinfo=timezone.utc)

    for sample in scores[1:]:
        sample_ts = getattr(sample, "ts", None)
        if sample_ts and sample_ts.tzinfo is None:
            sample_ts = sample_ts.replace(tzinfo=timezone.utc)

        # Ignore duplicate timestamp observations (idempotency guard)
        if sample_ts == prev_ts:
            continue

        # Check for gap interruption
        if prev_ts and sample_ts:
            gap = (prev_ts - sample_ts).total_seconds()
            if gap > max_gap_seconds:
                # Gap exceeded: streak is broken by missing/delayed telemetry
                break

        sample_is_anom = getattr(sample, "is_anomalous", None)
        if sample_is_anom is True:
            streak += 1
            prev_ts = sample_ts
        else:
            # Normal or unscored sample encountered: streak ends
            break

    sustained = streak >= threshold and not is_stale
    if is_stale:
        status = "STALE"
        msg = f"Node is stale/offline despite prior anomaly streak of {streak}."
    elif sustained:
        status = "SUSTAINED ANOMALY"
        msg = f"Sustained anomaly alert active: {streak} consecutive anomalous samples (threshold: {threshold})."
    else:
        status = "ANOMALOUS SAMPLE"
        msg = f"Transient anomaly detected: {streak}/{threshold} anomalous samples before sustained alert threshold."

    return {
        "alert_status": status,
        "sustained_anomaly": sustained,
        "streak_count": streak,
        "threshold": threshold,
        "latest_score": latest_score,
        "latest_is_anomalous": True,
        "is_stale": is_stale,
        "message": msg
    }

def evaluate_node_alert_state(
    db: Session,
    node_id: str,
    threshold: int = DEFAULT_SUSTAINED_THRESHOLD,
    max_gap_seconds: int = DEFAULT_MAX_GAP_SECONDS,
    stale_seconds: int = DEFAULT_STALE_SECONDS
) -> Dict[str, Any]:
    """
    Evaluates sustained anomaly alert state for a given node directly from PostgreSQL.
    Recovers state deterministically across worker and API restarts.
    """
    # 1. Check node liveness from latest metric
    latest_metric = db.execute(
        select(models.NodeMetric.ts)
        .where(models.NodeMetric.node_id == node_id)
        .order_by(desc(models.NodeMetric.ts))
        .limit(1)
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    is_stale = False
    if latest_metric:
        metric_ts = latest_metric.replace(tzinfo=timezone.utc) if latest_metric.tzinfo is None else latest_metric
        is_stale = (now - metric_ts).total_seconds() > stale_seconds
    else:
        is_stale = True

    # 2. Query recent anomaly scores (limit 20 is sufficient for threshold=3+)
    recent_scores = db.execute(
        select(models.AnomalyScore)
        .where(models.AnomalyScore.node_id == node_id)
        .order_by(desc(models.AnomalyScore.ts))
        .limit(20)
    ).scalars().all()

    result = evaluate_streak_from_records(
        recent_scores,
        threshold=threshold,
        max_gap_seconds=max_gap_seconds,
        is_stale=is_stale
    )
    result["node_id"] = node_id
    result["latest_ts"] = recent_scores[0].ts.isoformat() if recent_scores else None
    return result
