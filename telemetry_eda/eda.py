"""
Reproducible Telemetry Exploratory Data Analysis (EDA) Pipeline
Home Lab Anomaly / Observability Agent

This module implements a read-only, reproducible EDA pipeline for telemetry
stored in the `node_metrics` table. It performs data quality checks, sampling
cadence analysis, descriptive statistics, metric availability reporting,
distribution and time-series plotting, and independent correlation analyses.
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")  # Non-interactive headless backend
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("telemetry_eda")

# Standard telemetry metrics tracked in node_metrics
METRICS = [
    "cpu_pct",
    "mem_pct",
    "swap_pct",
    "disk_read_bps",
    "disk_write_bps",
    "disk_used_pct",
    "net_in_bps",
    "net_out_bps",
    "load1",
    "load5",
    "load15",
    "temp_c",
    "gpu_util_pct",
    "gpu_vram_pct",
]


class ConfigurationError(Exception):
    """Raised when required configuration or database URL is missing or invalid."""
    pass


def resolve_database_url(cli_db_url: Optional[str] = None) -> str:
    """
    Resolve the database connection URL with strict precedence:
    1. --db-url CLI argument
    2. DATABASE_URL environment variable (from environment or project .env)
    3. Fail immediately with ConfigurationError.

    Silent fallback to scratch databases (e.g. test.db) is strictly forbidden.
    """
    # Load .env file if available in project root
    project_root = Path(__file__).resolve().parent.parent
    env_file = project_root / ".env"
    if env_file.exists():
        load_dotenv(dotenv_path=env_file, override=False)

    if cli_db_url and cli_db_url.strip():
        logger.info("Using database URL provided via CLI argument.")
        return cli_db_url.strip()

    env_url = os.getenv("DATABASE_URL")
    if env_url and env_url.strip():
        logger.info("Using database URL from DATABASE_URL environment variable.")
        return env_url.strip()

    raise ConfigurationError(
        "No database URL provided. Database resolution requires an explicit '--db-url' "
        "argument or a 'DATABASE_URL' environment variable. "
        "Silent fallback to test.db is forbidden to prevent test/scratch data from "
        "being treated as production telemetry."
    )


def get_read_only_engine(db_url: str):
    """Create a SQLAlchemy engine with read-only intent."""
    connect_args: Dict[str, Any] = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(db_url, connect_args=connect_args)


def load_telemetry(engine, query: Optional[str] = None) -> pd.DataFrame:
    """
    Load raw telemetry data using a strictly read-only SELECT query.
    Preserves original timestamps and node IDs without resampling.
    """
    sql_query = query or "SELECT * FROM node_metrics ORDER BY node_id ASC, ts ASC;"
    logger.info("Querying node_metrics table...")
    
    with engine.connect() as conn:
        df = pd.read_sql(text(sql_query), conn)

    if df.empty:
        logger.warning("Loaded telemetry dataframe is empty.")
        return df

    # Standardize timestamps to UTC datetime
    df["ts"] = pd.to_datetime(df["ts"], utc=True)

    # Ensure all standard metrics exist in dataframe columns even if missing from table
    for metric in METRICS:
        if metric not in df.columns:
            df[metric] = np.nan

    logger.info(f"Loaded {len(df)} telemetry samples across {df['node_id'].nunique()} nodes.")
    return df


def compute_sampling_intervals(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Analyze consecutive sampling intervals per node.
    Returns:
      1. detailed_intervals_df: [node_id, ts, prev_ts, interval_seconds]
      2. sampling_summary_df: Summary metrics per node matching requirements.
    """
    detailed_records = []
    summary_records = []

    for node_id, group in df.groupby("node_id"):
        group_sorted = group.sort_values("ts").copy()
        ts_series = group_sorted["ts"]

        if len(ts_series) <= 1:
            # Not enough samples to compute intervals
            summary_records.append({
                "node_id": node_id,
                "interval_count": 0,
                "mean_interval": np.nan,
                "median_interval": np.nan,
                "std_interval": np.nan,
                "min_interval": np.nan,
                "P1": np.nan,
                "P5": np.nan,
                "P25": np.nan,
                "P50": np.nan,
                "P75": np.nan,
                "P95": np.nan,
                "P99": np.nan,
                "max_interval": np.nan,
                "count_lt_45s": 0,
                "count_45s_to_5m": 0,
                "count_5m_to_15m": 0,
                "count_15m_to_60m": 0,
                "count_gt_1h": 0,
                "gap_count_gt_5m": 0,
                "largest_gap": 0.0,
            })
            continue

        deltas = ts_series.diff().dt.total_seconds().iloc[1:]
        prev_ts = ts_series.iloc[:-1].values
        curr_ts = ts_series.iloc[1:].values

        for p_t, c_t, dt in zip(prev_ts, curr_ts, deltas):
            detailed_records.append({
                "node_id": node_id,
                "prev_ts": p_t,
                "ts": c_t,
                "interval_seconds": dt
            })

        count = len(deltas)
        mean_val = float(deltas.mean())
        median_val = float(deltas.median())
        std_val = float(deltas.std()) if count > 1 else 0.0
        min_val = float(deltas.min())
        max_val = float(deltas.max())

        p1 = float(np.percentile(deltas, 1))
        p5 = float(np.percentile(deltas, 5))
        p25 = float(np.percentile(deltas, 25))
        p50 = float(np.percentile(deltas, 50))
        p75 = float(np.percentile(deltas, 75))
        p95 = float(np.percentile(deltas, 95))
        p99 = float(np.percentile(deltas, 99))

        # Bucket classifications
        count_lt_45s = int((deltas < 45.0).sum())
        count_45s_to_5m = int(((deltas >= 45.0) & (deltas < 300.0)).sum())
        count_5m_to_15m = int(((deltas >= 300.0) & (deltas < 900.0)).sum())
        count_15m_to_60m = int(((deltas >= 900.0) & (deltas < 3600.0)).sum())
        count_gt_1h = int((deltas >= 3600.0).sum())
        gap_count_gt_5m = int((deltas >= 300.0).sum())

        summary_records.append({
            "node_id": node_id,
            "interval_count": count,
            "mean_interval": mean_val,
            "median_interval": median_val,
            "std_interval": std_val,
            "min_interval": min_val,
            "P1": p1,
            "P5": p5,
            "P25": p25,
            "P50": p50,
            "P75": p75,
            "P95": p95,
            "P99": p99,
            "max_interval": max_val,
            "count_lt_45s": count_lt_45s,
            "count_45s_to_5m": count_45s_to_5m,
            "count_5m_to_15m": count_5m_to_15m,
            "count_15m_to_60m": count_15m_to_60m,
            "count_gt_1h": count_gt_1h,
            "gap_count_gt_5m": gap_count_gt_5m,
            "largest_gap": max_val,
        })

    detailed_df = pd.DataFrame(detailed_records)
    summary_df = pd.DataFrame(summary_records)
    return detailed_df, summary_df


def compute_data_quality(df: pd.DataFrame, sampling_summary_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute comprehensive data quality indicators per node:
    sample count, time bounds, expected samples, coverage %, duplicate timestamps,
    interval bucket distribution, and per-metric null statistics.
    """
    quality_records = []
    sampling_by_node = sampling_summary_df.set_index("node_id").to_dict(orient="index") if not sampling_summary_df.empty else {}

    for node_id, group in df.groupby("node_id"):
        sample_count = len(group)
        first_ts = group["ts"].min()
        last_ts = group["ts"].max()
        
        if sample_count > 0:
            duration_s = (last_ts - first_ts).total_seconds()
            duration_fmt = str(timedelta(seconds=int(duration_s)))
            # Cadence target is 30s. Expected count over duration is int(duration / 30) + 1
            expected_samples = int(duration_s / 30.0) + 1 if duration_s >= 0 else 1
            coverage_pct = min(100.0, (sample_count / expected_samples) * 100.0) if expected_samples > 0 else 0.0
        else:
            duration_s = 0.0
            duration_fmt = "0s"
            expected_samples = 0
            coverage_pct = 0.0

        duplicate_ts_count = int(sample_count - group["ts"].nunique())

        node_sampling = sampling_by_node.get(node_id, {})
        int_lt_45s = node_sampling.get("count_lt_45s", 0)
        int_45s_5m = node_sampling.get("count_45s_to_5m", 0)
        int_5m_15m = node_sampling.get("count_5m_to_15m", 0)
        int_15m_60m = node_sampling.get("count_15m_to_60m", 0)
        int_gt_1h = node_sampling.get("count_gt_1h", 0)

        # Count available vs unavailable metrics
        avail_metrics = 0
        unavail_metrics = 0
        null_counts: Dict[str, Any] = {}

        for m in METRICS:
            null_c = int(group[m].isna().sum()) if m in group.columns else sample_count
            null_p = (null_c / sample_count * 100.0) if sample_count > 0 else 100.0
            null_counts[f"{m}_null_count"] = null_c
            null_counts[f"{m}_null_pct"] = round(null_p, 2)

            if null_c < sample_count:
                avail_metrics += 1
            else:
                unavail_metrics += 1

        record = {
            "node_id": node_id,
            "sample_count": sample_count,
            "first_timestamp": first_ts.isoformat() if pd.notna(first_ts) else None,
            "last_timestamp": last_ts.isoformat() if pd.notna(last_ts) else None,
            "duration_seconds": duration_s,
            "duration_formatted": duration_fmt,
            "expected_sample_count": expected_samples,
            "coverage_percentage": round(coverage_pct, 2),
            "duplicate_timestamp_count": duplicate_ts_count,
            "intervals_lt_45s": int_lt_45s,
            "intervals_45s_to_5m": int_45s_5m,
            "intervals_5m_to_15m": int_5m_15m,
            "intervals_15m_to_60m": int_15m_60m,
            "intervals_gt_1h": int_gt_1h,
            "available_metric_count": avail_metrics,
            "unavailable_metric_count": unavail_metrics,
            **null_counts
        }
        quality_records.append(record)

    return pd.DataFrame(quality_records)


def compute_descriptive_statistics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate raw descriptive statistics for every numeric metric per node.
    Preserves constant series (std = 0.0) and unavailable metrics (NaNs),
    strictly avoiding artificial zeros or imputation.
    """
    records = []

    for node_id, group in df.groupby("node_id"):
        for metric in METRICS:
            if metric not in group.columns:
                series = pd.Series(dtype=float)
            else:
                series = group[metric].dropna().astype(float)

            count = len(series)
            if count == 0:
                records.append({
                    "node_id": node_id,
                    "metric": metric,
                    "count": 0,
                    "mean": np.nan,
                    "median": np.nan,
                    "std": np.nan,
                    "min": np.nan,
                    "P1": np.nan,
                    "P5": np.nan,
                    "P25": np.nan,
                    "P50": np.nan,
                    "P75": np.nan,
                    "P95": np.nan,
                    "P99": np.nan,
                    "max": np.nan,
                    "status": "unavailable"
                })
            else:
                mean_v = float(series.mean())
                median_v = float(series.median())
                # If series is constant, std must be preserved as 0.0
                if series.nunique() <= 1:
                    std_v = 0.0
                    status_v = "constant"
                else:
                    std_v = float(series.std()) if count > 1 else 0.0
                    status_v = "variable"

                min_v = float(series.min())
                max_v = float(series.max())
                p1 = float(np.percentile(series, 1))
                p5 = float(np.percentile(series, 5))
                p25 = float(np.percentile(series, 25))
                p50 = float(np.percentile(series, 50))
                p75 = float(np.percentile(series, 75))
                p95 = float(np.percentile(series, 95))
                p99 = float(np.percentile(series, 99))

                records.append({
                    "node_id": node_id,
                    "metric": metric,
                    "count": count,
                    "mean": mean_v,
                    "median": median_v,
                    "std": std_v,
                    "min": min_v,
                    "P1": p1,
                    "P5": p5,
                    "P25": p25,
                    "P50": p50,
                    "P75": p75,
                    "P95": p95,
                    "P99": p99,
                    "max": max_v,
                    "status": status_v
                })

    return pd.DataFrame(records)


def compute_metric_availability(df: pd.DataFrame) -> pd.DataFrame:
    """
    Determine availability status for every node x metric:
    - 'available' (100% non-null)
    - 'partially_available' (0% < non-null < 100%)
    - 'unavailable' (0% non-null)
    """
    records = []

    for node_id, group in df.groupby("node_id"):
        total_rows = len(group)
        for metric in METRICS:
            if metric not in group.columns:
                non_null_rows = 0
            else:
                non_null_rows = int(group[metric].notna().sum())

            null_rows = total_rows - non_null_rows
            avail_pct = (non_null_rows / total_rows * 100.0) if total_rows > 0 else 0.0

            if non_null_rows == 0:
                status = "unavailable"
            elif non_null_rows == total_rows:
                status = "available"
            else:
                status = "partially_available"

            records.append({
                "node_id": node_id,
                "metric": metric,
                "total_rows": total_rows,
                "non_null_rows": non_null_rows,
                "null_rows": null_rows,
                "availability_percentage": round(avail_pct, 2),
                "status": status
            })

    return pd.DataFrame(records)


def compute_correlations(
    df: pd.DataFrame,
    output_dir: Path
) -> Dict[str, Dict[str, Any]]:
    """
    Compute pairwise Pearson and Spearman correlation matrices independently per node.
    Excludes:
    - Metrics that are 100% NULL for that node.
    - Constant metrics (std == 0.0, zero variance) where correlation is undefined.
    Saves CSV matrices and heatmap PNGs.
    """
    corr_dir = output_dir / "correlation_matrices"
    corr_dir.mkdir(parents=True, exist_ok=True)
    metadata: Dict[str, Dict[str, Any]] = {}

    for node_id, group in df.groupby("node_id"):
        metadata[node_id] = {
            "evaluated_metrics": [],
            "excluded_unavailable": [],
            "excluded_constant": [],
            "pearson_csv": None,
            "spearman_csv": None,
            "pearson_heatmap": None,
            "spearman_heatmap": None,
        }

        # Identify available and non-constant metrics
        valid_cols = []
        for m in METRICS:
            if m not in group.columns:
                metadata[node_id]["excluded_unavailable"].append(m)
                continue

            series = group[m].dropna()
            if len(series) == 0:
                metadata[node_id]["excluded_unavailable"].append(m)
            elif series.nunique() <= 1:
                metadata[node_id]["excluded_constant"].append(m)
            else:
                valid_cols.append(m)

        metadata[node_id]["evaluated_metrics"] = valid_cols

        if len(valid_cols) < 2:
            logger.info(f"Node '{node_id}' has fewer than 2 variable metrics; skipping correlation matrix.")
            continue

        sub_df = group[valid_cols].astype(float)
        pearson_corr = sub_df.corr(method="pearson")
        spearman_corr = sub_df.corr(method="spearman")

        # Save CSVs
        p_csv_path = corr_dir / f"{node_id}_pearson.csv"
        s_csv_path = corr_dir / f"{node_id}_spearman.csv"
        pearson_corr.to_csv(p_csv_path)
        spearman_corr.to_csv(s_csv_path)
        metadata[node_id]["pearson_csv"] = str(p_csv_path)
        metadata[node_id]["spearman_csv"] = str(s_csv_path)

        # Generate Heatmap Plots
        for method, c_matrix, filename in [
            ("Pearson", pearson_corr, f"{node_id}_pearson_heatmap.png"),
            ("Spearman", spearman_corr, f"{node_id}_spearman_heatmap.png")
        ]:
            fig, ax = plt.subplots(figsize=(10, 8))
            sns.heatmap(
                c_matrix,
                annot=True,
                fmt=".2f",
                cmap="coolwarm",
                vmin=-1.0,
                vmax=1.0,
                square=True,
                cbar_kws={"label": f"{method} Correlation Coefficient"},
                ax=ax,
                linewidths=0.5
            )
            ax.set_title(f"{node_id.upper()} — {method} Correlation Matrix (Variable Metrics)", fontsize=13, pad=12)
            plt.xticks(rotation=45, ha="right", fontsize=9)
            plt.yticks(rotation=0, fontsize=9)
            plt.tight_layout()

            plot_path = corr_dir / filename
            fig.savefig(plot_path, dpi=150)
            plt.close(fig)

            if method == "Pearson":
                metadata[node_id]["pearson_heatmap"] = str(plot_path)
            else:
                metadata[node_id]["spearman_heatmap"] = str(plot_path)

    return metadata


def generate_plots(df: pd.DataFrame, output_dir: Path):
    """
    Generate time series and distribution plots for all available metrics per node.
    """
    plots_base_dir = output_dir / "plots"

    # Define grouped time series configurations
    timeseries_configs = [
        ("cpu_pct_timeseries.png", "CPU Utilization (%)", [("cpu_pct", "CPU %")]),
        ("memory_pct_timeseries.png", "Memory Utilization (%)", [("mem_pct", "Memory %")]),
        ("swap_pct_timeseries.png", "Swap Utilization (%)", [("swap_pct", "Swap %")]),
        ("disk_usage_pct_timeseries.png", "Disk Used (%)", [("disk_used_pct", "Disk Used %")]),
        ("disk_io_timeseries.png", "Disk I/O Rates (Bytes/sec)", [
            ("disk_read_bps", "Read Bps"),
            ("disk_write_bps", "Write Bps")
        ]),
        ("network_io_timeseries.png", "Network I/O Rates (Bytes/sec)", [
            ("net_in_bps", "Net In Bps"),
            ("net_out_bps", "Net Out Bps")
        ]),
        ("load_timeseries.png", "System Load Averages", [
            ("load1", "Load 1m"),
            ("load5", "Load 5m"),
            ("load15", "Load 15m")
        ]),
        ("temperature_timeseries.png", "Temperature (°C)", [("temp_c", "Temperature °C")]),
        ("gpu_timeseries.png", "GPU Metrics (%)", [
            ("gpu_util_pct", "GPU Util %"),
            ("gpu_vram_pct", "GPU VRAM %")
        ]),
    ]

    for node_id, group in df.groupby("node_id"):
        node_dir = plots_base_dir / node_id
        dist_dir = node_dir / "distributions"
        node_dir.mkdir(parents=True, exist_ok=True)
        dist_dir.mkdir(parents=True, exist_ok=True)

        group_sorted = group.sort_values("ts").copy()
        ts = group_sorted["ts"]

        # 1. Time-series plots
        for filename, title, col_specs in timeseries_configs:
            # Check if at least one metric in col_specs is available (non-empty)
            available_cols = [(col, label) for col, label in col_specs if col in group_sorted and group_sorted[col].notna().sum() > 0]
            if not available_cols:
                continue

            fig, ax = plt.subplots(figsize=(12, 4.5))
            for col, label in available_cols:
                valid_mask = group_sorted[col].notna()
                ax.plot(
                    ts[valid_mask],
                    group_sorted.loc[valid_mask, col],
                    label=label,
                    alpha=0.85,
                    linewidth=1.2
                )

            ax.set_title(f"{node_id.upper()} — {title}", fontsize=12, fontweight="bold")
            ax.set_xlabel("Timestamp (UTC)", fontsize=10)
            ax.set_ylabel(title, fontsize=10)
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
            fig.autofmt_xdate()
            ax.grid(True, linestyle="--", alpha=0.5)
            ax.legend(loc="upper right", frameon=True)
            plt.tight_layout()

            fig.savefig(node_dir / filename, dpi=150)
            plt.close(fig)

        # 2. Distribution plots (histogram & boxplot) per available metric
        for metric in METRICS:
            if metric not in group_sorted:
                continue
            series = group_sorted[metric].dropna().astype(float)
            if len(series) == 0:
                continue

            # Histogram
            fig_hist, ax_hist = plt.subplots(figsize=(7, 4))
            ax_hist.hist(series, bins=30, color="#3b82f6", edgecolor="#1e3a8a", alpha=0.75)
            ax_hist.set_title(f"{node_id.upper()} — {metric} Distribution (Histogram)", fontsize=11)
            ax_hist.set_xlabel(metric, fontsize=9)
            ax_hist.set_ylabel("Frequency", fontsize=9)
            ax_hist.grid(True, linestyle=":", alpha=0.5)
            plt.tight_layout()
            fig_hist.savefig(dist_dir / f"{metric}_histogram.png", dpi=130)
            plt.close(fig_hist)

            # Boxplot
            fig_box, ax_box = plt.subplots(figsize=(6, 3.5))
            ax_box.boxplot(series, vert=False, patch_artist=True, boxprops=dict(facecolor="#93c5fd", color="#1d4ed8"))
            ax_box.set_title(f"{node_id.upper()} — {metric} Boxplot", fontsize=11)
            ax_box.set_xlabel(metric, fontsize=9)
            ax_box.grid(True, linestyle=":", alpha=0.5)
            plt.tight_layout()
            fig_box.savefig(dist_dir / f"{metric}_boxplot.png", dpi=130)
            plt.close(fig_box)


def generate_eda_summary(
    df: pd.DataFrame,
    data_quality_df: pd.DataFrame,
    sampling_summary_df: pd.DataFrame,
    desc_stats_df: pd.DataFrame,
    availability_df: pd.DataFrame,
    correlation_meta: Dict[str, Dict[str, Any]],
    output_path: Path
):
    """
    Generate an authoritative, neutral markdown summary adhering strictly to:
    - Factual observations (cadence, gaps, distributions)
    - Distinction between Telemetry / Data Quality Events vs System Behavior
    - Explicit recording of excluded constant metrics from correlation
    - Explanation of raw value preservation (no imputation or clipping).
    """
    lines = []
    lines.append("# Exploratory Data Analysis (EDA) Summary Report")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
    lines.append("## 1. Architectural Context & Analytical Principles\n")
    lines.append(
        "This report represents **Phase 2 — Telemetry Exploratory Data Analysis** for the Home Lab "
        "Observability Agent. All analyses are strictly read-only and operate directly on raw observations."
    )
    lines.append("\n> [!IMPORTANT]")
    lines.append("> **Operational Distinction: Telemetry Events vs. System Behavior**")
    lines.append(
        "> - **Telemetry / Data Quality Events:** Gaps in collection, node reboots, duplicate timestamps, "
        "or unpolled intervals are classified as telemetry pipeline events, NOT system anomalies."
    )
    lines.append(
        "> - **System Behavior:** Observed resource metrics (e.g. CPU spikes, high memory utilization) "
        "reflect legitimate system behavior and are reported factually without automated anomaly labeling."
    )
    lines.append(
        "> - **Preservation of Raw Values:** No data imputation, clipping, winsorization, or zero-filling "
        "has been performed. Unavailable hardware sensors remain strictly NULL."
    )

    lines.append("\n## 2. Discovered Nodes & Ingestion Coverage\n")
    lines.append("| Node ID | Total Samples | Earliest Timestamp | Latest Timestamp | Observed Duration | Coverage % | Duplicates |")
    lines.append("|---|---|---|---|---|---|---|")
    for _, row in data_quality_df.iterrows():
        lines.append(
            f"| **{row['node_id']}** | {row['sample_count']} | {row['first_timestamp']} | "
            f"{row['last_timestamp']} | {row['duration_formatted']} | {row['coverage_percentage']}% | "
            f"{row['duplicate_timestamp_count']} |"
        )

    lines.append("\n## 3. Sampling Cadence & Telemetry Interval Analysis\n")
    lines.append("The collection agent targets an approximate 30-second cadence. The observed interval distributions are summarized below:")
    lines.append("\n| Node ID | Intervals | Mean (s) | Median (s) | Std (s) | P95 (s) | Max Gap (s) | Gaps > 5m | Intervals > 1h |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for _, row in sampling_summary_df.iterrows():
        lines.append(
            f"| **{row['node_id']}** | {row['interval_count']} | {row['mean_interval']:.1f} | "
            f"{row['median_interval']:.1f} | {row['std_interval']:.1f} | {row['P95']:.1f} | "
            f"{row['largest_gap']:.1f} | {row['gap_count_gt_5m']} | {row['count_gt_1h']} |"
        )

    lines.append("\n### Telemetry Gaps (> 5 Minutes)")
    gaps_found = False
    for _, row in sampling_summary_df.iterrows():
        if row["gap_count_gt_5m"] > 0:
            gaps_found = True
            lines.append(
                f"- **Node '{row['node_id']}':** Observed **{row['gap_count_gt_5m']}** collection gap(s) exceeding 5 minutes "
                f"(largest single gap: {row['largest_gap']:.1f}s / {row['largest_gap']/3600.0:.2f} hours). "
                f"Classified as *telemetry / data-quality collection interruptions*."
            )
    if not gaps_found:
        lines.append("- No collection gaps exceeding 5 minutes were detected across any node.")

    lines.append("\n## 4. Hardware Capability & Metric Availability\n")
    lines.append("| Node ID | Available Metrics | Partially Available | Unavailable (Structural NULL) |")
    lines.append("|---|---|---|---|")
    for node_id, group in availability_df.groupby("node_id"):
        avail = group[group["status"] == "available"]["metric"].tolist()
        partial = group[group["status"] == "partially_available"]["metric"].tolist()
        unavail = group[group["status"] == "unavailable"]["metric"].tolist()
        lines.append(
            f"| **{node_id}** | {len(avail)} ({', '.join(avail) if avail else 'None'}) | "
            f"{len(partial)} ({', '.join(partial) if partial else 'None'}) | "
            f"{len(unavail)} ({', '.join(unavail) if unavail else 'None'}) |"
        )

    lines.append("\n## 5. Constant Metrics & Correlation Exclusions\n")
    lines.append(
        "Mathematically, the correlation coefficient between any series and a constant (zero variance) "
        "is undefined (division by zero). Constant metrics are preserved in descriptive statistics "
        "with `std = 0.0` but excluded from Pearson and Spearman correlation matrices:\n"
    )
    for node_id, meta in correlation_meta.items():
        lines.append(f"### Node `{node_id}`")
        if meta["excluded_constant"]:
            lines.append(f"- **Excluded Constant Metrics (std = 0.0):** `{', '.join(meta['excluded_constant'])}`")
        else:
            lines.append("- **Excluded Constant Metrics:** None")

        if meta["excluded_unavailable"]:
            lines.append(f"- **Excluded Unavailable Metrics (100% NULL):** `{', '.join(meta['excluded_unavailable'])}`")
        else:
            lines.append("- **Excluded Unavailable Metrics:** None")

        if meta["evaluated_metrics"]:
            lines.append(f"- **Evaluated Variable Metrics:** `{', '.join(meta['evaluated_metrics'])}`")
        else:
            lines.append("- **Evaluated Variable Metrics:** None (insufficient variable metrics)")
        lines.append("")

    lines.append("## 6. Key Descriptive Statistics Highlights\n")
    lines.append("Summary of central tendencies across key system metrics:")
    lines.append("\n| Node ID | Metric | Count | Mean | Median | Std | Min | Max | Status |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    key_metrics = ["cpu_pct", "mem_pct", "disk_used_pct", "temp_c", "gpu_util_pct", "load1"]
    for _, row in desc_stats_df[desc_stats_df["metric"].isin(key_metrics)].iterrows():
        count_str = f"{row['count']}"
        mean_str = f"{row['mean']:.2f}" if pd.notna(row['mean']) else "N/A"
        median_str = f"{row['median']:.2f}" if pd.notna(row['median']) else "N/A"
        std_str = f"{row['std']:.2f}" if pd.notna(row['std']) else "N/A"
        min_str = f"{row['min']:.2f}" if pd.notna(row['min']) else "N/A"
        max_str = f"{row['max']:.2f}" if pd.notna(row['max']) else "N/A"
        lines.append(
            f"| **{row['node_id']}** | `{row['metric']}` | {count_str} | {mean_str} | {median_str} | "
            f"{std_str} | {min_str} | {max_str} | *{row['status']}* |"
        )

    lines.append("\n## 7. Artifact Catalog\n")
    lines.append("The following analytical artifacts have been produced in `telemetry_eda/outputs/`:")
    lines.append("- `data_quality.csv`: Per-node sample counts, coverage percentages, duplicate counts, and null rates.")
    lines.append("- `sampling_intervals.csv`: Cadence percentiles (P1–P99), mean, std, bucket counts, and gap detection.")
    lines.append("- `descriptive_statistics.csv`: Non-null count, mean, median, std, percentiles, min, and max per metric.")
    lines.append("- `metric_availability.csv`: Availability percentage and structural classification per metric.")
    lines.append("- `correlation_matrices/`: Independent Pearson and Spearman matrices & heatmaps per node.")
    lines.append("- `plots/<node_id>/`: Time-series plots for available telemetry groups.")
    lines.append("- `plots/<node_id>/distributions/`: Histograms and boxplots for each variable metric.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info(f"Generated EDA summary at: {output_path}")


def run_eda_pipeline(
    db_url: Optional[str] = None,
    output_dir: Optional[Path] = None,
    generate_visualizations: bool = True
) -> Dict[str, Any]:
    """
    Execute the full end-to-end read-only EDA pipeline.
    """
    # 1. Resolve DB URL strictly (no silent fallback)
    resolved_url = resolve_database_url(db_url)
    out_dir = output_dir or (Path(__file__).resolve().parent / "outputs")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 2. Connect & Load Telemetry
    engine = get_read_only_engine(resolved_url)
    df = load_telemetry(engine)

    if df.empty:
        logger.warning("No data found in node_metrics table. Exiting pipeline.")
        return {"status": "empty_database"}

    # 3. Sampling Intervals Analysis
    logger.info("Computing sampling intervals...")
    detailed_intervals_df, sampling_summary_df = compute_sampling_intervals(df)
    sampling_summary_df.to_csv(out_dir / "sampling_intervals.csv", index=False)

    # 4. Data Quality Analysis
    logger.info("Computing data quality...")
    data_quality_df = compute_data_quality(df, sampling_summary_df)
    data_quality_df.to_csv(out_dir / "data_quality.csv", index=False)

    # 5. Descriptive Statistics
    logger.info("Computing descriptive statistics...")
    desc_stats_df = compute_descriptive_statistics(df)
    desc_stats_df.to_csv(out_dir / "descriptive_statistics.csv", index=False)

    # 6. Metric Availability
    logger.info("Computing metric availability...")
    availability_df = compute_metric_availability(df)
    availability_df.to_csv(out_dir / "metric_availability.csv", index=False)

    # 7. Correlation Matrices
    logger.info("Computing correlation matrices...")
    correlation_meta = compute_correlations(df, out_dir)

    # 8. Visualizations (Plots)
    if generate_visualizations:
        logger.info("Generating time-series and distribution plots...")
        generate_plots(df, out_dir)
    else:
        logger.info("Skipping visualization generation (--no-plots).")

    # 9. Summary Markdown Report
    logger.info("Generating summary report...")
    summary_path = out_dir / "eda_summary.md"
    generate_eda_summary(
        df,
        data_quality_df,
        sampling_summary_df,
        desc_stats_df,
        availability_df,
        correlation_meta,
        summary_path
    )

    logger.info("EDA pipeline completed successfully.")
    return {
        "status": "success",
        "nodes": df["node_id"].unique().tolist(),
        "total_samples": len(df),
        "output_dir": str(out_dir)
    }


def main():
    parser = argparse.ArgumentParser(description="Reproducible Telemetry EDA Pipeline")
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="Database connection URL (e.g. postgresql://user:pass@host:5432/db). If omitted, reads DATABASE_URL env var."
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory to save analytical outputs (default: telemetry_eda/outputs)."
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Skip plot generation for faster numerical analysis."
    )

    args = parser.parse_args()
    out_dir = Path(args.output_dir) if args.output_dir else None

    try:
        run_eda_pipeline(
            db_url=args.db_url,
            output_dir=out_dir,
            generate_visualizations=not args.no_plots
        )
    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Unexpected error running EDA pipeline: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
