# Repository Context & Implementation History
**Homelab Anomaly Observability Agent**
*Last Updated: October 2026*

---

## 1. Executive Summary & Purpose

The **Homelab Anomaly Observability Agent** is an end-to-end, local-first telemetry ingestion, time-series monitoring, and machine-learning-driven anomaly detection platform built specifically for a heterogeneous multi-host home lab.

Unlike generic monitoring stacks that treat every operating system identically or rely on arbitrary, hard-coded alert thresholds, this project accounts for the operational realities of home lab infrastructure:
* Multi-OS disparity (Windows workstation vs. Ubuntu server nodes).
* Variable hardware availability (intermittent daily driver vs. 24/7 dedicated nodes).
* Hardware sensor constraints (Windows lack of Linux load averages; dedicated nodes without discrete GPUs).
* Machine-learned behavioral baselines using per-node Isolation Forest models with feature engineering designed specifically for heavy-tailed infrastructure metrics.
* Real-time continuous inference decoupled from data ingestion via an asynchronous worker container.

The repository currently encompasses the completed implementations of **Phase 1** (Telemetry Ingestion & Edge Collection), **Phase 1.75** (React/Vite Observability Dashboard), **Phase 2** (Exploratory Data Analysis & Characterization), **Phase 3A** (Feature Engineering & Frozen Model Training), and **Phase 3B** (Continuous Live Inference Worker).

---

## 2. High-Level Architecture

```text
┌────────────────────────────────────────────────────────────────────────┐
│                              EDGE COLLECTORS                           │
├────────────────────────────────┬───────────────────────────────────────┤
│ Alpha (Windows 11 Workstation) │ Beta (Ubuntu 24.04 Server)            │ Gamma (Ubuntu 24.04 Srv)
│ psutil + pynvml (GPU metrics)  │ psutil                                │ psutil
│ Intermittent / Workstation     │ 24/7 Server                           │ 24/7 Dedicated Network Host
└───────────────┬────────────────┴──────────────────┬────────────────────┴───────────┬────────────┘
                │                                   │                                │
                │ HTTP POST /ingest                 │ HTTP POST /ingest              │ HTTP POST /ingest
                ▼                                   ▼                                ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                  CENTRAL SERVER: BETA                                           │
│                                                                                                 │
│  ┌─────────────────────────┐                ┌────────────────────────────────────────────────┐  │
│  │ anomaly-api             │                │ anomaly-worker (Live Inference)                │  │
│  │ (FastAPI, Port 8001:8002│                │ (scripts/live_inference.py)                    │  │
│  │  Pydantic Validation)   │                │ - Watermark bootstrap (INITIAL_BACKFILL=30m)   │  │
│  └────────────┬────────────┘                │ - Warmup tracking (10 samples for rolling/ROC) │  │
│               │                             │ - Frozen Isolation Forest models (Alpha/Beta/G)│  │
│               │ Writes telemetry            │ - Bulk conflict-safe inserts                   │  │
│               ▼                             └──────────────┬───────────────────▲─────────────┘  │
│  ┌─────────────────────────────────────────────────────────┴───────────────────┼─────────────┐  │
│  │                    anomaly-postgres (PostgreSQL 16, Internal Docker Network)│             │  │
│  │  Tables:                                                                    │             │  │
│  │  - node_metrics: Raw telemetry snapshots                                    │             │  │
│  │  - anomaly_scores: Real-time inference scores & anomalous flags ────────────┘             │  │
│  └───────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                 │
│  ┌───────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ Frontend Observability Dashboard (React 18 + Vite + Apache ECharts, Host Port 5173/Static)│  │
│  └───────────────────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Node Inventory & Operational Profiles

| Node ID | Operating System | Hardware Specifications | Primary Role | Availability & Baseline Profile | Sensor Constraints |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Alpha** (`alpha-win`) | Windows 11 Pro | Intel Multi-core, 32GB RAM, NVIDIA RTX 4060 | Daily driver & ML development workstation | Intermittent (shuts down/sleeps at night and during breaks). Dynamic GPU workload bursts. | Load averages (`load1`, `load5`, `load15`) structurally unavailable (`null`). GPU sensors (`gpu_util_pct`, `gpu_vram_pct`) active via NVML. |
| **Beta** (`beta-srv`) | Ubuntu 24.04 LTS | Multi-core x86_64, 16GB RAM | Main home server & central collector hub | 24/7 continuous uptime. Hosts Docker Compose network, PostgreSQL database, API, and worker. | No discrete GPU (`gpu_util_pct` and `gpu_vram_pct` are `null`). Linux load averages and CPU temperature available. |
| **Gamma** (`gamma-srv`) | Ubuntu 24.04 LTS | Quad-core x86_64, 8GB RAM | Dedicated networking & container workloads | 24/7 continuous uptime. Exhibits a persistent single-threaded nominal workload: 1 core pinned at 100% (~25% aggregate CPU). | No discrete GPU. Swap usage is constantly 0% (zero variance). Linux load averages and CPU temperature available. |

---

## 4. Phase-by-Phase Implementation History

### Phase 1: Ingestion API, Telemetry Collector & Database Pipeline
* **Telemetry Collector (`collector/`)**:
  * Implemented modular metric collection using `psutil` for host telemetry (CPU%, Memory%, Swap%, Disk I/O bytes/sec, Disk used%, Network I/O bytes/sec, Load averages, CPU Temperature).
  * Implemented `pynvml` GPU telemetry monitoring for NVIDIA hardware (Alpha), with cached device handles and graceful fallback if GPU drivers/libraries are unavailable.
  * Robust counter delta logic: calculates disk and network throughput rates safely by handling counter wrap-around or system reboot resets.
  * Resilience: Retries failed network transmissions, reads `.env` dynamically with fallback to default ingest endpoints, and maintains session pooling via `requests.Session`.
* **Ingestion API (`api/`)**:
  * Built with FastAPI and SQLAlchemy 2.0.
  * Defined `node_metrics` schema with composite index `(node_id, ts)`.
  * Implemented endpoints:
    * `POST /ingest`: Pydantic-validated ingestion.
    * `GET /health`: Health and database ping check.
    * `GET /last_seen/{node_id}`: Host availability monitor (offline after 120s of silence).
    * `GET /api/nodes`: Node capability directory.
    * `GET /api/nodes/{node_id}/latest`: Most recent snapshot.
    * `GET /api/nodes/{node_id}/metrics`: Queryable time-series windowing with `start`, `end`, and `limit`.
    * `GET /api/nodes/{node_id}/quality`: Data quality summary and missingness auditor over `window_hours`.
* **Containerized Deployment (`docker-compose.yml`, `deploy/`)**:
  * `anomaly-postgres`: PostgreSQL 16 Alpine container with private volume storage, isolated inside the internal Docker network `anomaly-net` (port 5432 not exposed to host).
  * `anomaly-api`: Containerized FastAPI service exposing port `8002` (mapped to internal `8001`).

### Phase 1.75: Frontend Observability Dashboard
* **React 18 + Vite + Apache ECharts (`frontend/`)**:
  * High-performance single-page application for infrastructure monitoring.
  * Dynamic multi-node dashboard rendering real-time CPU, Memory, Disk I/O, Network Throughput, and GPU performance.
  * Node health indicators, data quality badges, and sampling interval latency trackers.
  * Configurable API base URL via `VITE_API_BASE_URL`.

### Phase 2: Exploratory Data Analysis & Characterization
* **Auditing Production Telemetry (`telemetry_eda/`, `analysis/eda.py`)**:
  * Audited 14 consecutive days of production home lab telemetry (~94,000 samples).
  * Key discoveries that governed subsequent ML architectural decisions:
    1. **Distinct Node Baselines:** Verified that Alpha, Beta, and Gamma have orthogonal statistical distributions. A unified global model would yield mass false positives or miss localized incidents.
    2. **Gamma Nominal Core Saturation:** Revealed Gamma's 25% CPU baseline was a single saturated core running legitimate nominal services. Disproved initial assumptions that 25% CPU was an anomaly.
    3. **Alpha Offline Regime:** Identified Alpha's recurring overnight offline windows. Proved that sampling gaps reflect power management, not node degradation.
    4. **Heavy-Tailed Distributions:** Disk I/O and network transfer rates span 5+ orders of magnitude. Identified necessity of logarithmic transforms (`log1p`).
    5. **Failure of Univariate Baselines (MAD):** Proved that naive univariate Median Absolute Deviation (MAD) across 20+ metrics suffers from multiple-comparison compounding (>99% false positive rate) without Bonferroni corrections and multivariate contextualization.

### Phase 3A: Feature Engineering & Frozen Model Training
* **Feature Pipeline (`analysis/features.py`)**:
  * Formulated standardized feature transformation logic applied consistently across training and live inference:
    * `log1p` transformation for throughput metrics (`disk_read_bps`, `disk_write_bps`, `net_in_bps`, `net_out_bps`).
    * 5-minute rolling statistics (`rolling_mean`, `rolling_std`) for CPU and Memory to capture temporal state and filter transient 1-sample spikes.
    * 1-step rate-of-change (`diff`) capturing acceleration in resource consumption.
  * Node-Specific Feature Sets:
    * **Alpha (31 features):** Raw metrics, rolling stats, ROC diffs, and GPU utilization/VRAM. Excludes load averages.
    * **Beta (31 features):** Raw metrics, rolling stats, ROC diffs, load averages, CPU temp. Excludes GPU.
    * **Gamma (30 features):** Raw metrics, rolling stats, ROC diffs, load averages, CPU temp. Excludes GPU and zero-variance swap.
* **Model Training & Artifact Freezing (`scripts/train_models.py`, `models/`)**:
  * Trained independent `IsolationForest` models per node (`contamination=0.01`, `n_estimators=100`, `max_samples='auto'`, `random_state=42`).
  * Pinned runtime dependencies: `scikit-learn==1.8.0`.
  * Artifact storage structure:
    * `models/alpha/`: `isolation_forest.joblib`, `feature_config.json`, `metadata.json`
    * `models/beta/`: `isolation_forest.joblib`, `feature_config.json`, `metadata.json`
    * `models/gamma/`: `isolation_forest.joblib`, `feature_config.json`, `metadata.json`
    * `models/model_manifest.json`: Cryptographic integrity manifest detailing feature counts, training sample windows, and scikit-learn version.
    * `models/training_report.md`: Detailed documentation of model training runs.

### Phase 3B: Continuous Live Inference Worker
* **Live Inference Engine (`scripts/live_inference.py`)**:
  * Built as a continuous background daemon operating against production PostgreSQL.
  * **Zero Live Fitting Guarantee:** Evaluates frozen models strictly using `model.score_samples()`. Absolutely no `.fit()` or `.partial_fit()` calls exist in the inference path.
  * **Watermark Bootstrap Policy:**
    * Queries `MAX(ts)` from `anomaly_scores` per node to determine the last scored record.
    * On clean/empty database boot, sets the initial watermark to `MAX(ts) - INTERVAL '30 minutes'` (controlled by `INITIAL_BACKFILL_MINUTES=30`) from `node_metrics`. This prevents the worker from blocking on startup by attempting to score millions of historical rows.
  * **Warmup & Imputation Policy:**
    * Implemented strict distinction between raw missing metrics and temporal warmup:
      * **Imputation:** Raw metrics missing due to hardware differences (e.g. Windows load averages) or occasional sensor nulls are imputed using the node's frozen training medians loaded from `feature_config.json`.
      * **Warmup:** Temporal features (rolling mean, rolling std, rate-of-change) require at least 10 consecutive observations (`WARMUP_MIN_SAMPLES = 10`). During the warmup window, rows are inserted into `anomaly_scores` with `score = None` and `is_anomalous = None`.
  * **Database Resiliency & Graceful Degradation:**
    * Custom `DatabaseUnavailableError` wrapper.
    * Bounded exponential backoff connection retry loop with jitter (1s base, 30s cap) ensuring the worker survives database restarts or network interruptions.
  * **Idempotency & Re-entrancy:**
    * Defined `AnomalyScore` model in `api/models.py` with unique constraint `(node_id, ts)`.
    * Implemented bulk upsert utilizing PostgreSQL dialect `ON CONFLICT (node_id, ts) DO NOTHING` (with fallback for SQLite unit testing).
    * Restarts or overlapping batch windows cannot produce duplicate key constraint crashes.
  * **Signal Handling & Container Healthcheck:**
    * Clean interception of `SIGTERM` and `SIGINT` allowing currently in-flight batches to commit before process termination.
    * Periodically touches `/tmp/worker_health` upon every completed polling cycle.
    * Configured Docker healthcheck in `docker-compose.yml` to inspect file mtime freshness (`< 60s`), enabling automated container health recovery.
* **Worker Packaging (`deploy/Dockerfile.worker`, `docker-compose.yml`)**:
  * Containerized worker environment pinned with `scikit-learn==1.8.0` and `sqlalchemy==2.0.29`.
  * Integrated as `anomaly-worker` service into `docker-compose.yml` dependent on healthy `anomaly-postgres`.

---

## 5. Repository File Structure

```text
homelab-anomaly-agent/
├── .env.example                     # Environment template (database credentials & collector settings)
├── .gitignore                       # Standardized ignore rules (credentials, .venv, *.db, __pycache__)
├── docker-compose.yml               # Multi-service Compose stack (Postgres, API, Worker)
├── readme.md                        # Master project documentation & architectural guide
├── REPOSITORY_CONTEXT.md            # Detailed implementation history and operational context (this file)
├── requirements.txt                 # Pinned Python package dependencies
│
├── analysis/                        # Feature extraction & statistical analysis library
│   ├── anomaly_model.py             # Isolation Forest & robust MAD anomaly detection wrappers
│   ├── eda.py                       # Automated Exploratory Data Analysis script
│   ├── evaluate.py                  # Evaluation framework & synthetic stress metric benchmarks
│   ├── features.py                  # Standardized feature extraction (log1p, rolling stats, diffs)
│   ├── README.md                    # Detailed documentation of Phase 2.5 analysis & modeling decisions
│   └── outputs/                     # Statistical summaries, correlation charts, and diagnostic reports
│
├── api/                             # FastAPI telemetry ingestion engine
│   ├── database.py                  # SQLAlchemy engine & session dependency injection
│   ├── main.py                      # FastAPI routes (/health, /ingest, /last_seen, /api/nodes/*)
│   ├── models.py                    # ORM entities (NodeMetric and AnomalyScore)
│   └── schemas.py                   # Pydantic validation schemas
│
├── collector/                       # Lightweight multi-node edge metrics collector
│   └── agent.py                     # psutil + pynvml metric polling agent
│
├── deploy/                          # Infrastructure and container build definitions
│   ├── Dockerfile                   # Container definition for anomaly-api
│   ├── Dockerfile.worker            # Container definition for anomaly-worker (scikit-learn 1.8.0)
│   ├── homelab-server.service       # Systemd service for Docker Compose on Beta
│   └── homelab-collector.service    # Systemd service for Python collector on Linux nodes
│
├── frontend/                        # Observability dashboard (React 18 + Vite + Apache ECharts)
│   ├── package.json
│   ├── src/
│   │   ├── components/              # Node cards, time-series charts, data quality tables
│   │   ├── App.jsx
│   │   └── main.jsx
│   └── vite.config.js
│
├── models/                          # Frozen machine learning artifacts (Phase 3A)
│   ├── model_manifest.json          # Master manifest (features, scikit-learn version, sample counts)
│   ├── training_report.md           # Report detailing model convergence and parameter selection
│   ├── alpha/                       # isolation_forest.joblib, feature_config.json, metadata.json
│   ├── beta/                        # isolation_forest.joblib, feature_config.json, metadata.json
│   └── gamma/                       # isolation_forest.joblib, feature_config.json, metadata.json
│
├── scripts/                         # Operational & diagnostic utility scripts
│   ├── live_inference.py            # Phase 3B live inference worker daemon
│   ├── train_models.py              # Phase 3A model training & freezing script
│   ├── export_prod_db.py            # Database dump & export utility
│   ├── diagnose.py                  # Statistical diagnostic script
│   └── run_real_experiments.py     # Evaluation experiments runner
│
├── telemetry_eda/                   # Phase 2 exploratory data analysis artifacts
│   ├── README.md                    # Detailed Phase 2 EDA methodology and findings
│   └── outputs/                     # Descriptive stats, data quality CSVs, correlation matrices
│
└── tests/                           # Complete automated pytest test suite (39 tests)
    ├── test_analysis.py             # Tests for feature extraction, rolling stats, MAD, and Bonferroni
    ├── test_api.py                  # Tests for FastAPI endpoints, schemas, CORS, and data quality
    ├── test_collector.py            # Tests for edge collector, NVML fallback, and counter resets
    ├── test_inference.py            # Tests for live inference worker, watermarks, warmup, and gap recovery
    └── test_model_artifacts.py      # Tests verifying frozen Isolation Forest artifacts load and score
```

---

## 6. Verification & Quality Gates

The entire test suite is verified using `pytest`:

```bash
uv run pytest tests/ -v
```

### Verified Test Capabilities (39 Passed, 0 Failed):
1. **Analysis & Features (`tests/test_analysis.py`)**:
   * Mathematical correctness of `log1p` compression.
   * Rolling mean and rolling standard deviation calculations.
   * Rate-of-change calculation on non-negative diffs.
   * Robust Median Absolute Deviation (MAD) and Bonferroni-corrected thresholding.
2. **API & Endpoints (`tests/test_api.py`)**:
   * Ingest payload validation (rejects invalid JSON, accepts valid schemas).
   * Node health check (`/health`) and heartbeat tracking (`/last_seen`).
   * Quality auditing endpoints and historical telemetry slice querying.
3. **Edge Collector (`tests/test_collector.py`)**:
   * Telemetry generation across all CPU, Memory, Disk, and Network groups.
   * Graceful fallback when NVML / GPU libraries are absent.
   * Network session re-use and counter wrap-around handling.
4. **Frozen Model Artifacts (`tests/test_model_artifacts.py`)**:
   * Successful deserialization of joblib files for Alpha, Beta, and Gamma.
   * Validation of feature vector alignment against `feature_config.json`.
5. **Live Inference Worker (`tests/test_inference.py`)**:
   * Model loader and version verification.
   * Incremental batch processing, warmup handling, and database idempotency.
   * Alpha intermittent gap recovery (watermark progression across multi-hour downtime).

---

## 7. Known Environment Constraints & Operational Notes

1. **Docker Container DNS Limitation on Host Environment**:
   * During Docker image construction on some host setups (specifically Docker Desktop with internal bridge resolver `192.168.65.7`), `apt-get` lookups to `deb.debian.org` may encounter temporary DNS timeouts (`SERVFAIL`).
   * The application code, database schema, and test suite are completely self-contained and run natively or under Docker without modification once the base OS image is cached.
2. **PostgreSQL Credentials**:
   * In production, `POSTGRES_PASSWORD` is injected via environment variables or a local `.env` file. No plain-text passwords or secret strings are hard-coded into repository source files.
3. **Database Port Publishing**:
   * `anomaly-postgres` communicates strictly over the private Docker bridge network `anomaly-net`. Port 5432 is deliberately unexposed to external network interfaces for security.

---

## 8. Transition to Phase 3C (Upcoming Scope)

Phase 3B provides real-time anomaly scoring written back into `anomaly_scores`. The planned **Phase 3C** milestone will build upon this foundation:
* **Alerting Engine**: An event-driven evaluation service polling `anomaly_scores` for sustained anomalies (e.g. 3 consecutive anomalous observations over 90 seconds) to filter transient noise.
* **Notification Channels**: Webhook dispatchers and Telegram bot notifications reporting node, severity, and top contributing metrics.
* **Frontend Visualization**: Real-time anomaly overlays on the React/ECharts dashboard charting anomaly score trends alongside raw telemetry.
* **Model Retraining Pipeline**: Scheduled cron/systemd jobs to periodically refresh model baselines against 30-day rolling windows.
