# Telemetry Exploratory Data Analysis (EDA) Pipeline
**Phase 2 — Home Lab Anomaly / Observability Agent**

A standalone, reproducible, and strictly read-only exploratory data analysis pipeline designed to audit, characterize, and visualize historical telemetry stored in the `node_metrics` database table.

---

## 1. Purpose

The objective of this pipeline is to establish a rigorous baseline understanding of raw node metrics before any machine learning (e.g. Isolation Forest) or threshold-based alerting is introduced. 

This pipeline performs:
1. **Sampling Cadence & Gap Analysis:** Quantifies actual observation frequency against the target 30-second cadence and flags collection gaps.
2. **Data Quality & Coverage Auditing:** Measures coverage percentage, duration, duplicate timestamps, and per-metric null rates.
3. **Metric Availability & Capability Classification:** Identifies which hardware sensors are fully available, partially available, or structurally unavailable per node.
4. **Descriptive Statistical Profiling:** Computes uncorrupted raw statistics (mean, median, standard deviation, min, max, percentiles P1–P99) without outlier removal or imputation.
5. **Independent Correlation Analysis:** Computes pairwise Pearson and Spearman correlation matrices independently per node, excluding constant metrics with zero variance.
6. **Time-Series & Distribution Visualization:** Generates publication-ready time-series line charts, histograms, and boxplots for each node and metric.
7. **Architectural Summary Reporting:** Synthesizes factual findings into an automated markdown report.

---

## 2. Core Architectural Principles

### Strict Read-Only Execution
The pipeline is designed to be completely safe to execute against production databases. It only issues `SELECT` queries. It executes zero DDL or DML operations (`INSERT`, `UPDATE`, `DELETE`, `ALTER`, `CREATE`, `DROP`, `TRUNCATE`).

### Strict Database Resolution (No Silent Fallbacks)
To prevent accidental pollution or mistaking scratch/test data for production telemetry, the CLI strictly enforces database resolution:
1. `--db-url` CLI argument
2. `DATABASE_URL` environment variable (from shell or `.env`)
3. **Fails immediately with a `ConfigurationError`** if neither is provided.

*The local `test.db` is scratch test data and is NEVER used implicitly.*

### Preservation of Raw Observations
- **No Outlier Clipping or Winsorizing:** Extreme values are preserved to reflect genuine operating conditions or hardware limits.
- **No Imputation or Zero-Filling:** Missing values remain `NULL` (`NaN`). Unavailable sensors (e.g. GPU on Beta/Gamma, Windows load average) are never converted to zero.
- **Constant Metric Preservation:** If a metric is constant across all samples (e.g., temperature at 25.0°C or swap at 0%), standard deviation is preserved as `0.0` and reported as a constant series. It is excluded *only* from correlation matrices because correlation with a zero-variance series is mathematically undefined.

### Operational Distinction: Telemetry Events vs. System Behavior
- **Telemetry / Data Quality Events:** Gaps in collection, node reboots, duplicate timestamps, or unpolled intervals reflect telemetry pipeline behavior, **not** system anomalies.
- **System Behavior:** Observed resource utilization (e.g., high CPU, high memory) reflects operating system behavior and is reported neutrally without premature labeling as an "anomaly".

---

## 3. Directory & Output Structure

```text
telemetry_eda/
├── README.md                          # Pipeline documentation
├── eda.py                            # CLI & core pipeline engine
├── requirements.txt                  # Minimal Python dependencies
├── tests/
│   ├── __init__.py
│   └── test_eda.py                   # 11 unit tests with synthetic fixtures
└── outputs/
    ├── data_quality.csv              # Node-level samples, duration, coverage, null rates
    ├── sampling_intervals.csv        # Interval percentiles, mean, std, bucket counts, gaps
    ├── descriptive_statistics.csv    # Non-null count, mean, median, std, percentiles P1-P99
    ├── metric_availability.csv       # Status (available, partially_available, unavailable)
    ├── eda_summary.md                # Factual architectural summary report
    ├── correlation_matrices/         # Independent Pearson & Spearman CSVs and heatmaps
    │   ├── <node_id>_pearson.csv
    │   ├── <node_id>_spearman.csv
    │   ├── <node_id>_pearson_heatmap.png
    │   └── <node_id>_spearman_heatmap.png
    └── plots/
        └── <node_id>/
            ├── cpu_pct_timeseries.png
            ├── memory_pct_timeseries.png
            ├── swap_pct_timeseries.png
            ├── disk_usage_pct_timeseries.png
            ├── disk_io_timeseries.png
            ├── network_io_timeseries.png
            ├── load_timeseries.png
            ├── temperature_timeseries.png
            ├── gpu_timeseries.png
            └── distributions/
                ├── <metric>_histogram.png
                └── <metric>_boxplot.png
```

---

## 4. Installation & Requirements

Install dependencies using pip:

```bash
pip install -r telemetry_eda/requirements.txt
```

Core dependencies:
- `pandas>=2.0.0`
- `numpy>=1.24.0`
- `matplotlib>=3.7.0`
- `seaborn>=0.12.0`
- `SQLAlchemy>=2.0.0`
- `psycopg2-binary>=2.9.0`
- `python-dotenv>=1.0.0`
- `pytest>=8.0.0`

---

## 5. How to Run

### Running Against Production PostgreSQL

Provide the connection string via CLI:

```bash
python telemetry_eda/eda.py --db-url "postgresql://anomaly_agent:password@192.168.1.50:5432/homelab_anomaly"
```

Or via environment variable:

```bash
export DATABASE_URL="postgresql://anomaly_agent:password@192.168.1.50:5432/homelab_anomaly"
python telemetry_eda/eda.py
```

### Running Against Local Test / Scratch Data

For validation against a local SQLite database file, explicitly pass `--db-url`:

```bash
python telemetry_eda/eda.py --db-url "sqlite:///test.db"
```

### Additional Options

```bash
# Specify custom output directory
python telemetry_eda/eda.py --db-url "..." --output-dir "/path/to/custom/outputs"

# Fast execution skipping chart generation (numerical analysis only)
python telemetry_eda/eda.py --db-url "..." --no-plots
```

---

## 6. Running Unit Tests

Execute the isolated unit test suite:

```bash
python -m pytest telemetry_eda/tests/test_eda.py -v
```

The test suite runs against in-memory synthetic DataFrames and verifies:
1. Monotonic sampling interval delta calculation
2. Gap detection (> 300s) and largest gap tracking
3. Interval bucketing (<45s, 45s–5m, 5–15m, 15–60m, >1h)
4. Duplicate timestamp identification
5. Preservation of NULLs without zero-substitution
6. Accurate percentile computation (P1 through P99)
7. Constant-series preservation (std = 0.0) and correlation exclusion
8. 100% NULL metric detection as `unavailable`
9. Mixed-value metric detection as `partially_available`
10. Complete per-node analytical separation
11. Strict database URL resolution & error handling without silent fallback.
