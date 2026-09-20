# Exploratory Data Analysis (EDA) Summary Report
**Generated:** 2026-09-19 11:35:02 UTC

## 1. Architectural Context & Analytical Principles

This report represents **Phase 2 — Telemetry Exploratory Data Analysis** for the Home Lab Observability Agent. All analyses are strictly read-only and operate directly on raw observations.

> [!IMPORTANT]
> **Operational Distinction: Telemetry Events vs. System Behavior**
> - **Telemetry / Data Quality Events:** Gaps in collection, node reboots, duplicate timestamps, or unpolled intervals are classified as telemetry pipeline events, NOT system anomalies.
> - **System Behavior:** Observed resource metrics (e.g. CPU spikes, high memory utilization) reflect legitimate system behavior and are reported factually without automated anomaly labeling.
> - **Preservation of Raw Values:** No data imputation, clipping, winsorization, or zero-filling has been performed. Unavailable hardware sensors remain strictly NULL.

## 2. Discovered Nodes & Ingestion Coverage

| Node ID | Total Samples | Earliest Timestamp | Latest Timestamp | Observed Duration | Coverage % | Duplicates |
|---|---|---|---|---|---|---|
| **alpha** | 7000 | 2026-09-13T04:16:37.671666+00:00 | 2026-09-19T11:34:24.645533+00:00 | 6 days, 7:17:46 | 38.55% | 0 |
| **beta** | 17845 | 2026-09-13T06:39:37.110084+00:00 | 2026-09-19T11:34:16.142323+00:00 | 6 days, 4:54:39 | 99.86% | 0 |
| **gamma** | 18733 | 2026-09-12T17:00:06.357363+00:00 | 2026-09-19T11:34:18.499462+00:00 | 6 days, 18:34:12 | 96.02% | 0 |

## 3. Sampling Cadence & Telemetry Interval Analysis

The collection agent targets an approximate 30-second cadence. The observed interval distributions are summarized below:

| Node ID | Intervals | Mean (s) | Median (s) | Std (s) | P95 (s) | Max Gap (s) | Gaps > 5m | Intervals > 1h |
|---|---|---|---|---|---|---|---|---|
| **alpha** | 6999 | 77.8 | 30.1 | 1432.9 | 30.2 | 73419.4 | 14 | 9 |
| **beta** | 17844 | 30.0 | 30.0 | 0.8 | 30.1 | 139.5 | 0 | 0 |
| **gamma** | 18732 | 31.2 | 30.0 | 120.1 | 30.1 | 14492.7 | 2 | 2 |

### Telemetry Gaps (> 5 Minutes)
- **Node 'alpha':** Observed **14** collection gap(s) exceeding 5 minutes (largest single gap: 73419.4s / 20.39 hours). Classified as *telemetry / data-quality collection interruptions*.
- **Node 'gamma':** Observed **2** collection gap(s) exceeding 5 minutes (largest single gap: 14492.7s / 4.03 hours). Classified as *telemetry / data-quality collection interruptions*.

## 4. Hardware Capability & Metric Availability

| Node ID | Available Metrics | Partially Available | Unavailable (Structural NULL) |
|---|---|---|---|
| **alpha** | 11 (cpu_pct, mem_pct, swap_pct, disk_used_pct, net_in_bps, net_out_bps, load1, load5, load15, gpu_util_pct, gpu_vram_pct) | 2 (disk_read_bps, disk_write_bps) | 1 (temp_c) |
| **beta** | 10 (cpu_pct, mem_pct, swap_pct, disk_read_bps, disk_write_bps, disk_used_pct, load1, load5, load15, temp_c) | 2 (net_in_bps, net_out_bps) | 2 (gpu_util_pct, gpu_vram_pct) |
| **gamma** | 12 (cpu_pct, mem_pct, swap_pct, disk_read_bps, disk_write_bps, disk_used_pct, net_in_bps, net_out_bps, load1, load5, load15, temp_c) | 0 (None) | 2 (gpu_util_pct, gpu_vram_pct) |

## 5. Constant Metrics & Correlation Exclusions

Mathematically, the correlation coefficient between any series and a constant (zero variance) is undefined (division by zero). Constant metrics are preserved in descriptive statistics with `std = 0.0` but excluded from Pearson and Spearman correlation matrices:

### Node `alpha`
- **Excluded Constant Metrics:** None
- **Excluded Unavailable Metrics (100% NULL):** `temp_c`
- **Evaluated Variable Metrics:** `cpu_pct, mem_pct, swap_pct, disk_read_bps, disk_write_bps, disk_used_pct, net_in_bps, net_out_bps, load1, load5, load15, gpu_util_pct, gpu_vram_pct`

### Node `beta`
- **Excluded Constant Metrics (std = 0.0):** `swap_pct, temp_c`
- **Excluded Unavailable Metrics (100% NULL):** `gpu_util_pct, gpu_vram_pct`
- **Evaluated Variable Metrics:** `cpu_pct, mem_pct, disk_read_bps, disk_write_bps, disk_used_pct, net_in_bps, net_out_bps, load1, load5, load15`

### Node `gamma`
- **Excluded Constant Metrics (std = 0.0):** `swap_pct, temp_c`
- **Excluded Unavailable Metrics (100% NULL):** `gpu_util_pct, gpu_vram_pct`
- **Evaluated Variable Metrics:** `cpu_pct, mem_pct, disk_read_bps, disk_write_bps, disk_used_pct, net_in_bps, net_out_bps, load1, load5, load15`

## 6. Key Descriptive Statistics Highlights

Summary of central tendencies across key system metrics:

| Node ID | Metric | Count | Mean | Median | Std | Min | Max | Status |
|---|---|---|---|---|---|---|---|---|
| **alpha** | `cpu_pct` | 7000 | 9.69 | 7.10 | 7.59 | 1.80 | 71.70 | *variable* |
| **alpha** | `mem_pct` | 7000 | 56.86 | 54.40 | 10.37 | 25.70 | 91.30 | *variable* |
| **alpha** | `disk_used_pct` | 7000 | 79.20 | 78.20 | 2.71 | 76.90 | 88.30 | *variable* |
| **alpha** | `load1` | 7000 | 0.03 | 0.00 | 0.17 | 0.00 | 6.49 | *variable* |
| **alpha** | `temp_c` | 0 | N/A | N/A | N/A | N/A | N/A | *unavailable* |
| **alpha** | `gpu_util_pct` | 7000 | 2.67 | 1.00 | 3.81 | 0.00 | 29.00 | *variable* |
| **beta** | `cpu_pct` | 17845 | 0.73 | 0.70 | 0.46 | 0.50 | 22.20 | *variable* |
| **beta** | `mem_pct` | 17845 | 13.34 | 12.90 | 1.12 | 11.30 | 17.00 | *variable* |
| **beta** | `disk_used_pct` | 17845 | 35.78 | 36.00 | 0.41 | 34.90 | 36.10 | *variable* |
| **beta** | `load1` | 17845 | 0.05 | 0.02 | 0.08 | 0.00 | 1.93 | *variable* |
| **beta** | `temp_c` | 17845 | 27.80 | 27.80 | 0.00 | 27.80 | 27.80 | *constant* |
| **beta** | `gpu_util_pct` | 0 | N/A | N/A | N/A | N/A | N/A | *unavailable* |
| **gamma** | `cpu_pct` | 18733 | 25.02 | 25.00 | 0.16 | 25.00 | 33.40 | *variable* |
| **gamma** | `mem_pct` | 18733 | 15.44 | 15.50 | 0.55 | 13.90 | 21.60 | *variable* |
| **gamma** | `disk_used_pct` | 18733 | 8.07 | 8.10 | 0.06 | 7.90 | 8.20 | *variable* |
| **gamma** | `load1` | 18733 | 1.01 | 1.00 | 0.03 | 1.00 | 2.13 | *variable* |
| **gamma** | `temp_c` | 18733 | 27.80 | 27.80 | 0.00 | 27.80 | 27.80 | *constant* |
| **gamma** | `gpu_util_pct` | 0 | N/A | N/A | N/A | N/A | N/A | *unavailable* |

## 7. Artifact Catalog

The following analytical artifacts have been produced in `telemetry_eda/outputs/`:
- `data_quality.csv`: Per-node sample counts, coverage percentages, duplicate counts, and null rates.
- `sampling_intervals.csv`: Cadence percentiles (P1–P99), mean, std, bucket counts, and gap detection.
- `descriptive_statistics.csv`: Non-null count, mean, median, std, percentiles, min, and max per metric.
- `metric_availability.csv`: Availability percentage and structural classification per metric.
- `correlation_matrices/`: Independent Pearson and Spearman matrices & heatmaps per node.
- `plots/<node_id>/`: Time-series plots for available telemetry groups.
- `plots/<node_id>/distributions/`: Histograms and boxplots for each variable metric.