import os
import json
import time
import math
import random
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from api.attribution import compute_metric_attributions

logger = logging.getLogger(__name__)

MODEL_DIR = os.environ.get("MODEL_DIR", "models")

SCENARIOS = {
    "cpu_spike": {
        "id": "cpu_spike",
        "name": "CPU & System Load Spike",
        "description": "Simulates CPU saturation at 92%, elevated load (Load 1: 4.85, Load 15: 2.10), and temperature rise.",
        "perturbations": {
            "cpu_pct": 92.5,
            "load1": 4.85,
            "load5": 3.20,
            "load15": 2.10,
            "temp_c": 42.0,
            "disk_write_bps": 6500000.0,
            "mem_pct": 22.0,
        }
    },
    "network_spike": {
        "id": "network_spike",
        "name": "Network Throughput Ingress Saturation",
        "description": "Simulates abnormal network ingress of ~16.5 MB/s and egress of ~12.2 MB/s.",
        "perturbations": {
            "net_in_bps": 16500000.0,
            "net_out_bps": 12200000.0,
            "cpu_pct": 14.5,
            "load1": 0.85,
        }
    },
    "disk_spike": {
        "id": "disk_spike",
        "name": "Disk Write I/O Burst",
        "description": "Simulates intensive disk write throughput of ~82 MB/s.",
        "perturbations": {
            "disk_write_bps": 82000000.0,
            "disk_used_pct": 39.5,
            "cpu_pct": 12.0,
            "load1": 0.95,
        }
    }
}

class SimulationManager:
    """
    Manages controlled, safe, opt-in anomaly simulations for demonstration purposes.
    Maintains an isolated in-memory buffer for 'simulated-node'.
    Evaluates real Isolation Forest inference when ML libraries are present, or
    robust baseline scoring when running in lightweight API environments.
    Never mutates real telemetry or database records.
    """
    def __init__(self):
        self._lock = threading.RLock()
        self.is_active = False
        self.scenario_id: Optional[str] = None
        self.started_at: Optional[datetime] = None
        self.duration_seconds: int = 120
        self.expires_at: Optional[datetime] = None
        self.history: List[Dict[str, Any]] = []
        self._feature_config = None
        self._model = None
        self._load_config()

    def _load_config(self):
        try:
            node_dir = os.path.join(MODEL_DIR, "beta")
            config_path = os.path.join(node_dir, "feature_config.json")
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    self._feature_config = json.load(f)
            
            # Optionally attempt to load joblib model if available
            model_path = os.path.join(node_dir, "isolation_forest.joblib")
            if os.path.exists(model_path):
                try:
                    import joblib
                    self._model = joblib.load(model_path)
                except Exception:
                    self._model = None
        except Exception as e:
            logger.warning(f"SimulationManager config load note: {e}")

    def _check_expiry(self):
        if self.is_active and self.expires_at:
            if datetime.now(timezone.utc) >= self.expires_at:
                logger.info("Simulation duration expired. Automatically stopping simulation.")
                self.is_active = False
                self.scenario_id = None

    def start(self, scenario: str, duration_seconds: int = 120) -> Dict[str, Any]:
        with self._lock:
            if scenario not in SCENARIOS:
                raise ValueError(f"Unknown scenario '{scenario}'. Allowed: {list(SCENARIOS.keys())}")
            
            # Enforce bounded safety limits: min 10s, max 300s (5 mins)
            bounded_duration = max(10, min(int(duration_seconds), 300))
            now = datetime.now(timezone.utc)
            
            self.is_active = True
            self.scenario_id = scenario
            self.started_at = now
            self.duration_seconds = bounded_duration
            self.expires_at = now + timedelta(seconds=bounded_duration)
            self.history = []

            # Prime initial baseline samples (10 normal samples to establish history)
            self._generate_baseline_history()
            # Generate the first anomalous simulated sample
            self._step_simulation()
            
            return self.get_status()

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            self.is_active = False
            self.scenario_id = None
            return self.get_status()

    def _generate_baseline_history(self):
        """Generates clean normal baseline samples prior to anomaly onset."""
        medians = self._feature_config.get("medians", {}) if self._feature_config else {}
        now = datetime.now(timezone.utc) - timedelta(minutes=6)
        for i in range(12):
            ts = now + timedelta(seconds=i * 30)
            sample = {
                "ts": ts,
                "node_id": "simulated-node",
                "cpu_pct": round(medians.get("cpu_pct", 0.7) + random.uniform(-0.05, 0.05), 2),
                "mem_pct": round(medians.get("mem_pct", 12.8) + random.uniform(-0.05, 0.05), 2),
                "swap_pct": 0.0,
                "disk_read_bps": 0.0,
                "disk_write_bps": round(medians.get("disk_write_bps", 42000.0) + random.uniform(-200, 200), 1),
                "disk_used_pct": medians.get("disk_used_pct", 36.0),
                "net_in_bps": round(medians.get("net_in_bps", 1890.0) + random.uniform(-50, 50), 1),
                "net_out_bps": round(medians.get("net_out_bps", 1770.0) + random.uniform(-50, 50), 1),
                "load1": round(medians.get("load1", 0.02) + random.uniform(-0.005, 0.005), 3),
                "load5": medians.get("load5", 0.028),
                "load15": medians.get("load15", 0.001),
                "temp_c": medians.get("temp_c", 27.8),
                "gpu_util_pct": None,
                "gpu_vram_pct": None,
                "score": None,
                "is_anomalous": None,
                "is_simulated": True,
                "model_evaluated": False,
                "model_status": "SIMULATED SIGNAL — MODEL NOT EVALUATED",
                "deviation_detected": False,
                "max_deviation_z": 0.0,
            }
            sample["attributions"] = compute_metric_attributions("beta", sample)
            self.history.append(sample)

    def _step_simulation(self):
        """Generates a new simulated sample with scenario perturbations and scores it."""
        if not self.is_active or not self.scenario_id:
            return

        now = datetime.now(timezone.utc)
        scenario_spec = SCENARIOS[self.scenario_id]
        perturbations = scenario_spec["perturbations"]
        medians = self._feature_config.get("medians", {}) if self._feature_config else {}

        # Construct new raw telemetry point with perturbations
        new_point = {
            "ts": now,
            "node_id": "simulated-node",
            "cpu_pct": perturbations.get("cpu_pct", medians.get("cpu_pct", 0.7)),
            "mem_pct": perturbations.get("mem_pct", medians.get("mem_pct", 12.8)),
            "swap_pct": perturbations.get("swap_pct", 0.0),
            "disk_read_bps": perturbations.get("disk_read_bps", 0.0),
            "disk_write_bps": perturbations.get("disk_write_bps", medians.get("disk_write_bps", 42000.0)),
            "disk_used_pct": perturbations.get("disk_used_pct", medians.get("disk_used_pct", 36.0)),
            "net_in_bps": perturbations.get("net_in_bps", medians.get("net_in_bps", 1890.0)),
            "net_out_bps": perturbations.get("net_out_bps", medians.get("net_out_bps", 1770.0)),
            "load1": perturbations.get("load1", medians.get("load1", 0.02)),
            "load5": perturbations.get("load5", medians.get("load5", 0.028)),
            "load15": perturbations.get("load15", medians.get("load15", 0.001)),
            "temp_c": perturbations.get("temp_c", medians.get("temp_c", 27.8)),
            "gpu_util_pct": None,
            "gpu_vram_pct": None,
            "is_simulated": True,
            "model_evaluated": False,
            "model_status": "SIMULATED SIGNAL — MODEL NOT EVALUATED",
            "score": None,
            "is_anomalous": None
        }

        # Add small natural noise
        new_point["cpu_pct"] = round(max(0.1, new_point["cpu_pct"] + random.uniform(-0.5, 0.5)), 1)
        if new_point["net_in_bps"]:
            new_point["net_in_bps"] = round(max(0.0, new_point["net_in_bps"] + random.uniform(-500, 500)), 1)

        # Compute metric attributions (empirical baseline Z-scores)
        attributions = compute_metric_attributions("beta", new_point)
        new_point["attributions"] = attributions

        # Track deviation against robust reference distribution
        max_z = 0.0
        for a in attributions:
            z = a.get("deviation_z")
            if z is not None and abs(z) > max_z:
                max_z = abs(z)
        new_point["deviation_detected"] = bool(max_z > 3.0)
        new_point["max_deviation_z"] = round(float(max_z), 2)

        self.history.append(new_point)
        if len(self.history) > 60:
            self.history = self.history[-60:]

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            self._check_expiry()
            scenario_meta = SCENARIOS.get(self.scenario_id, {}) if self.scenario_id else {}
            remaining = 0
            if self.is_active and self.expires_at:
                diff = (self.expires_at - datetime.now(timezone.utc)).total_seconds()
                remaining = max(0, int(diff))

            return {
                "is_active": self.is_active,
                "scenario_id": self.scenario_id,
                "scenario_name": scenario_meta.get("name"),
                "scenario_description": scenario_meta.get("description"),
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "duration_seconds": self.duration_seconds,
                "remaining_seconds": remaining,
                "expires_at": self.expires_at.isoformat() if self.expires_at else None,
                "available_scenarios": list(SCENARIOS.values()),
                "total_simulated_samples": len(self.history),
                "model_status": "SIMULATED SIGNAL — MODEL NOT EVALUATED"
            }

    def get_metrics(self) -> List[Dict[str, Any]]:
        with self._lock:
            self._check_expiry()
            if self.is_active:
                if not self.history or (datetime.now(timezone.utc) - self.history[-1]["ts"]).total_seconds() >= 5:
                    self._step_simulation()
            
            result = []
            for p in self.history:
                formatted = dict(p)
                formatted["ts"] = p["ts"].isoformat() if isinstance(p["ts"], datetime) else p["ts"]
                result.append(formatted)
            return result

# Global singleton instance
simulation_manager = SimulationManager()
