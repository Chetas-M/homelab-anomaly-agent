import os
import json
import logging
from typing import Dict, Any, List, Optional
import math

logger = logging.getLogger(__name__)

MODEL_DIR = os.environ.get("MODEL_DIR", "models")

# Metric definitions with metadata, units, and minimum MAD floors to avoid micro-jitter false positives
METRIC_SPECS = [
    {
        "key": "cpu_pct",
        "display_name": "CPU Utilization",
        "unit": "%",
        "mad_floor": 1.5,
        "format": "{:.1f}%",
        "higher_is_bad": True,
    },
    {
        "key": "mem_pct",
        "display_name": "Memory Utilization",
        "unit": "%",
        "mad_floor": 1.0,
        "format": "{:.1f}%",
        "higher_is_bad": True,
    },
    {
        "key": "swap_pct",
        "display_name": "Swap Utilization",
        "unit": "%",
        "mad_floor": 1.0,
        "format": "{:.1f}%",
        "higher_is_bad": True,
    },
    {
        "key": "disk_used_pct",
        "display_name": "Disk Used",
        "unit": "%",
        "mad_floor": 1.0,
        "format": "{:.1f}%",
        "higher_is_bad": True,
    },
    {
        "key": "disk_read_bps",
        "display_name": "Disk Read Throughput",
        "unit": "B/s",
        "mad_floor": 10240.0,  # 10 KB/s
        "format": "bytes",
        "higher_is_bad": True,
    },
    {
        "key": "disk_write_bps",
        "display_name": "Disk Write Throughput",
        "unit": "B/s",
        "mad_floor": 10240.0,  # 10 KB/s
        "format": "bytes",
        "higher_is_bad": True,
    },
    {
        "key": "net_in_bps",
        "display_name": "Network Ingress",
        "unit": "B/s",
        "mad_floor": 2048.0,  # 2 KB/s
        "format": "bytes",
        "higher_is_bad": True,
    },
    {
        "key": "net_out_bps",
        "display_name": "Network Egress",
        "unit": "B/s",
        "mad_floor": 2048.0,  # 2 KB/s
        "format": "bytes",
        "higher_is_bad": True,
    },
    {
        "key": "load1",
        "display_name": "System Load (1m)",
        "unit": "",
        "mad_floor": 0.10,
        "format": "{:.2f}",
        "higher_is_bad": True,
    },
    {
        "key": "load5",
        "display_name": "System Load (5m)",
        "unit": "",
        "mad_floor": 0.10,
        "format": "{:.2f}",
        "higher_is_bad": True,
    },
    {
        "key": "load15",
        "display_name": "System Load (15m)",
        "unit": "",
        "mad_floor": 0.10,
        "format": "{:.2f}",
        "higher_is_bad": True,
    },
    {
        "key": "temp_c",
        "display_name": "Temperature",
        "unit": "°C",
        "mad_floor": 2.0,
        "format": "{:.1f}°C",
        "higher_is_bad": True,
    },
    {
        "key": "gpu_util_pct",
        "display_name": "GPU Utilization",
        "unit": "%",
        "mad_floor": 5.0,
        "format": "{:.1f}%",
        "higher_is_bad": True,
    },
    {
        "key": "gpu_vram_pct",
        "display_name": "GPU VRAM Utilization",
        "unit": "%",
        "mad_floor": 5.0,
        "format": "{:.1f}%",
        "higher_is_bad": True,
    },
]

def format_value(val: Optional[float], spec: dict) -> str:
    if val is None:
        return "N/A"
    fmt = spec["format"]
    if fmt == "bytes":
        v = float(val)
        if v >= 1024 * 1024:
            return f"{v / (1024 * 1024):.2f} MB/s"
        elif v >= 1024:
            return f"{v / 1024:.2f} KB/s"
        else:
            return f"{v:.0f} B/s"
    elif fmt.startswith("{:"):
        return fmt.format(val)
    return f"{val} {spec['unit']}".strip()

def load_node_baseline(node_id: str) -> Optional[dict]:
    """Load baseline statistics (medians and MADs) from the trained feature config."""
    # Normalize node names
    lookup_id = node_id.lower()
    if lookup_id in ("alpha-win", "alpha"):
        lookup_id = "alpha"
    elif lookup_id in ("gamma-server", "gamma-srv", "gamma"):
        lookup_id = "gamma"
    elif lookup_id in ("beta-srv", "beta"):
        lookup_id = "beta"

    config_path = os.path.join(MODEL_DIR, lookup_id, "feature_config.json")
    if not os.path.exists(config_path):
        return None
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read baseline for {node_id}: {e}")
        return None

def compute_metric_attributions(
    node_id: str,
    latest_metrics: Dict[str, Any],
    supported_metrics: Optional[set] = None
) -> List[Dict[str, Any]]:
    """
    Computes robust Z-scores and deviation statuses for each telemetry metric.
    
    Status semantics:
    - NORMAL: Within baseline range (|z| <= 3.0).
    - ELEVATED: Significantly above baseline (z > 3.0).
    - LOW: Significantly below baseline (z < -3.0).
    - INSUFFICIENT DATA: Metric is supported on this hardware but latest telemetry is null.
    - UNAVAILABLE: Metric is structurally unavailable on this hardware (e.g., GPU on non-GPU nodes).
    """
    baseline_cfg = load_node_baseline(node_id)
    medians = baseline_cfg.get("medians", {}) if baseline_cfg else {}
    mads = baseline_cfg.get("mads", {}) if baseline_cfg else {}
    features_ordered = set(baseline_cfg.get("features_ordered", [])) if baseline_cfg else set()

    attributions = []

    for spec in METRIC_SPECS:
        key = spec["key"]
        display_name = spec["display_name"]
        unit = spec["unit"]
        mad_floor = spec["mad_floor"]
        
        # Check if hardware supports this metric
        is_supported = True
        if supported_metrics is not None:
            is_supported = key in supported_metrics
        elif features_ordered:
            # If not in features_ordered and never reported, hardware doesn't have it
            is_supported = key in features_ordered
        else:
            # Fallback heuristic
            if "gpu" in key and node_id.lower() not in ("alpha", "alpha-win"):
                is_supported = False

        current_val = latest_metrics.get(key)
        if current_val is not None:
            try:
                current_val = float(current_val)
            except (ValueError, TypeError):
                current_val = None

        if not is_supported and current_val is None:
            attributions.append({
                "metric_key": key,
                "display_name": display_name,
                "current_val": None,
                "formatted_val": "Unavailable",
                "unit": unit,
                "baseline_median": None,
                "reference_range": "N/A",
                "deviation_z": None,
                "status": "UNAVAILABLE",
                "explanation": f"{display_name} is not present on this node hardware architecture."
            })
            continue

        if current_val is None:
            attributions.append({
                "metric_key": key,
                "display_name": display_name,
                "current_val": None,
                "formatted_val": "No Data",
                "unit": unit,
                "baseline_median": medians.get(key),
                "reference_range": "Insufficient data",
                "deviation_z": None,
                "status": "INSUFFICIENT DATA",
                "explanation": f"No recent telemetry sample received for {display_name}."
            })
            continue

        train_median = medians.get(key)
        train_mad = mads.get(key)

        if train_median is None or train_mad is None:
            # No baseline available for this specific metric
            attributions.append({
                "metric_key": key,
                "display_name": display_name,
                "current_val": current_val,
                "formatted_val": format_value(current_val, spec),
                "unit": unit,
                "baseline_median": None,
                "reference_range": "Uncalibrated",
                "deviation_z": 0.0,
                "status": "NORMAL",
                "explanation": f"Current {display_name} is {format_value(current_val, spec)}. Baseline not calibrated."
            })
            continue

        effective_mad = max(train_mad, mad_floor)
        robust_z = (current_val - train_median) / (1.4826 * effective_mad)
        
        # Calculate reference range [median - 3*scale, median + 3*scale]
        lower_bound = max(0.0, train_median - 3.0 * 1.4826 * effective_mad) if "pct" in key or "bps" in key else train_median - 3.0 * 1.4826 * effective_mad
        upper_bound = train_median + 3.0 * 1.4826 * effective_mad
        if "pct" in key:
            upper_bound = min(100.0, upper_bound)
            
        ref_range_str = f"[{format_value(lower_bound, spec)} – {format_value(upper_bound, spec)}]"

        if robust_z > 3.0:
            status = "ELEVATED"
            explanation = (
                f"{display_name} is significantly elevated ({format_value(current_val, spec)}) "
                f"above baseline median {format_value(train_median, spec)} "
                f"(+{robust_z:.1f}σ from reference distribution)."
            )
        elif robust_z < -3.0:
            status = "LOW"
            explanation = (
                f"{display_name} is unusually low ({format_value(current_val, spec)}) "
                f"below baseline median {format_value(train_median, spec)} "
                f"({robust_z:.1f}σ from reference distribution)."
            )
        else:
            status = "NORMAL"
            explanation = (
                f"{display_name} is operating within normal baseline range "
                f"({format_value(current_val, spec)}, baseline {format_value(train_median, spec)})."
            )

        attributions.append({
            "metric_key": key,
            "display_name": display_name,
            "current_val": current_val,
            "formatted_val": format_value(current_val, spec),
            "unit": unit,
            "baseline_median": float(train_median),
            "reference_range": ref_range_str,
            "deviation_z": round(float(robust_z), 2),
            "status": status,
            "explanation": explanation
        })

    return attributions
