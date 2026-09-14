import sys
import os

# Add the project root to sys.path so we can import from api
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.orm import Session
from datetime import datetime, timezone
import random
from api.db import SessionLocal, engine
from api.models import Base, NodeMetric

# Ensure tables exist
Base.metadata.create_all(bind=engine)

def add_gamma():
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    
    # Check if gamma already exists
    exists = db.query(NodeMetric).filter(NodeMetric.node_id == "Gamma").first()
    if exists:
        print("Gamma already exists!")
        return

    # Add 10 metrics for Gamma
    for i in range(10):
        metric = NodeMetric(
            node_id="Gamma",
            ts=now,
            cpu_pct=random.uniform(10, 40),
            mem_pct=random.uniform(20, 60),
            swap_pct=0,
            disk_read_bps=random.uniform(100, 5000),
            disk_write_bps=random.uniform(100, 5000),
            disk_used_pct=random.uniform(40, 50),
            net_in_bps=random.uniform(1000, 10000),
            net_out_bps=random.uniform(1000, 10000),
            load1=random.uniform(0.1, 1.0),
            load5=random.uniform(0.1, 1.0),
            load15=random.uniform(0.1, 1.0),
            temp_c=random.uniform(30, 50),
            gpu_util_pct=random.uniform(0, 10),
            gpu_vram_pct=random.uniform(0, 5),
        )
        db.add(metric)
    db.commit()
    db.close()
    print("Gamma added successfully!")

if __name__ == "__main__":
    add_gamma()
