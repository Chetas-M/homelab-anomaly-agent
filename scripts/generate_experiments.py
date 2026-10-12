import sys
import os
import json
from datetime import datetime, timezone, timedelta
import random

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from sqlalchemy.orm import Session
from api.db import SessionLocal, engine
from api.models import Base, NodeMetric

def run_stress_test(db, node_id, start_time, duration_minutes, stress_type):
    metrics = []
    end_time = start_time + timedelta(minutes=duration_minutes)
    current_time = start_time
    
    while current_time < end_time:
        cpu_pct = random.uniform(5, 20)
        mem_pct = random.uniform(30, 50)
        disk_write = random.uniform(100, 1000)
        net_out = random.uniform(1000, 5000)
        
        if stress_type == "cpu":
            cpu_pct = random.uniform(95, 100)
        elif stress_type == "disk":
            disk_write = random.uniform(50000, 100000)
        elif stress_type == "net":
            net_out = random.uniform(80000, 150000)
            
        metric = NodeMetric(
            node_id=node_id,
            ts=current_time,
            cpu_pct=cpu_pct,
            mem_pct=mem_pct,
            swap_pct=0,
            disk_read_bps=random.uniform(100, 1000),
            disk_write_bps=disk_write,
            disk_used_pct=random.uniform(40, 50),
            net_in_bps=random.uniform(1000, 5000),
            net_out_bps=net_out,
            load1=random.uniform(1.0, 5.0) if stress_type == "cpu" else random.uniform(0.1, 1.0),
            load5=random.uniform(1.0, 3.0) if stress_type == "cpu" else random.uniform(0.1, 1.0),
            load15=random.uniform(0.5, 1.5) if stress_type == "cpu" else random.uniform(0.1, 1.0),
            temp_c=random.uniform(70, 85) if stress_type == "cpu" else random.uniform(30, 50),
            gpu_util_pct=0,
            gpu_vram_pct=0,
        )
        metrics.append(metric)
        current_time += timedelta(seconds=30)
        
    db.add_all(metrics)
    db.commit()
    
    return {
        "experiment_id": f"exp_{node_id}_{stress_type}_{int(start_time.timestamp())}",
        "node_id": node_id,
        "type": stress_type,
        "start_time_utc": start_time.isoformat(),
        "end_time_utc": end_time.isoformat(),
        "description": f"Synthetic {stress_type} stress test"
    }

def generate_experiments():
    db = SessionLocal()
    
    # Get the latest timestamp in the db to append experiments after it
    latest_metric = db.query(NodeMetric).order_by(NodeMetric.ts.desc()).first()
    if not latest_metric:
        base_time = datetime.now(timezone.utc)
    else:
        # Ensure it's tz-aware
        base_time = latest_metric.ts
        if base_time.tzinfo is None:
            base_time = base_time.replace(tzinfo=timezone.utc)
            
    # Add a gap before eval
    eval_start = base_time + timedelta(hours=1)
    
    experiments = []
    
    # Alpha CPU stress
    exp = run_stress_test(db, "alpha", eval_start + timedelta(minutes=10), 5, "cpu")
    experiments.append(exp)
    
    # Beta Disk stress
    exp = run_stress_test(db, "beta", eval_start + timedelta(minutes=30), 5, "disk")
    experiments.append(exp)
    
    # Gamma Net stress
    exp = run_stress_test(db, "gamma", eval_start + timedelta(minutes=50), 5, "net")
    experiments.append(exp)
    
    # Generate some normal baseline data in the eval period too, and some for training
    for node in ["alpha", "beta", "gamma"]:
        # Training data (2 hours before eval_start)
        current = eval_start - timedelta(hours=2)
        end = eval_start + timedelta(hours=2)
        metrics = []
        while current < end:
            # Skip if during an experiment
            in_exp = False
            for e in experiments:
                if e["node_id"] == node and datetime.fromisoformat(e["start_time_utc"]) <= current <= datetime.fromisoformat(e["end_time_utc"]):
                    in_exp = True
                    break
            if not in_exp:
                metrics.append(NodeMetric(
                    node_id=node,
                    ts=current,
                    cpu_pct=random.uniform(5, 20),
                    mem_pct=random.uniform(30, 50),
                    swap_pct=0,
                    disk_read_bps=random.uniform(100, 1000),
                    disk_write_bps=random.uniform(100, 1000),
                    disk_used_pct=random.uniform(40, 50),
                    net_in_bps=random.uniform(1000, 5000),
                    net_out_bps=random.uniform(1000, 5000),
                    load1=random.uniform(0.1, 1.0),
                    load5=random.uniform(0.1, 1.0),
                    load15=random.uniform(0.1, 1.0),
                    temp_c=random.uniform(30, 50),
                    gpu_util_pct=0,
                    gpu_vram_pct=0,
                ))
            current += timedelta(seconds=30)
        db.add_all(metrics)
    
    db.commit()
    db.close()
    
    # Save log
    os.makedirs('analysis/outputs', exist_ok=True)
    with open('analysis/outputs/experiment_log.json', 'w') as f:
        json.dump(experiments, f, indent=2)
        
    print("Experiments generated and saved.")

if __name__ == "__main__":
    generate_experiments()
