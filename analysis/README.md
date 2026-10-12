# Phase 2.5: Anomaly Detection Evaluation

This directory contains the baseline implementation and evaluation of anomaly detection for the 3-node homelab.

## Method

1. **Per-Node Models:** We use independent models for each node (Alpha, Beta, Gamma). This prevents the model from confusing legitimate hardware-specific baseline differences (e.g. Gamma's higher CPU baseline) with anomalies.
2. **Isolation Forest Conceptual Overview:** IF works by recursively partitioning the feature space. Anomalies are "easier" to isolate (require fewer partitions) than normal points. We train it strictly on normal baseline periods.
3. **MAD Baseline:** A robust univariate baseline. We calculate the Median Absolute Deviation for each metric during the training period and compute robust Z-scores during evaluation. The aggregate score is the maximum robust Z-score across features.
4. **Log Transforms:** We applied `log1p` to heavy-tailed non-negative distributions like disk and network rates to normalize their scale.
5. **Rolling Features:** A 5-minute rolling mean and standard deviation are calculated for CPU and Memory to capture temporal state rather than instantaneous spikes, reducing noise.
6. **Robust Scaling:** Robust scaling (via MAD) was chosen because mean/variance scaling is extremely sensitive to the very anomalies we are trying to detect.
7. **Stress Tests (Weak Labels):** Real anomaly labels are rarely available. We generated synthetic stress events (CPU, Disk, Network) and recorded their time windows. Observations during these windows are "weakly anomalous."

## Evaluation

- **Chronological Split:** The earliest synthetic injection experiment marks the end of the training data. Data before this boundary is strictly used for fitting the IF model and MAD baselines. Data after this boundary is for evaluation.
- **Label Construction:** The `experiment_log.json` defines synthetic injection windows. Any telemetry sample falling into an experiment window for the targeted node receives a positive label (`weak_label=True`).
- **Metrics:** We evaluate Precision, Recall, F1 score, and ROC-AUC. We also report the total number of predicted anomalies against the size of the population to contextualize the metrics in a highly imbalanced setting.
- **Synthetic Anomaly Injection Evaluation:** Real physical stress tests (e.g., via `stress-ng`, `fio`, `iperf3`) were **not** performed on the physical hardware. Anomalies were strictly manufactured algorithmically and injected into `test.db`.
- **Database Subtitution:** `test.db` was utilized as a temporary evaluation proxy because the production PostgreSQL database was unavailable. However, subsequent dataset validation definitively established that `test.db` **is not representative** of production telemetry (e.g. CPU medians drifting by >20x, Gamma missing its 25% single-threaded baseline). Model performance metrics measured against `test.db` are invalid for real-world tuning.
- **Weak Labels:** The labels indicate when a stress test was running, but the system might not be genuinely anomalous for every single 30-second observation in that window.
- **No Temporal Baseline:** We do not learn time-of-day or day-of-week baselines, which EDA identified as significant for some nodes.
- **Alpha's Availability:** Alpha goes offline often. Missing data is handled by imputation during inference or ignoring long gaps, but this remains a complex edge case.
- **MAD Multiple-Comparisons (Resolved):** The original univariate MAD baseline failed completely due to a max-over-marginals evaluation across $k=24$ features (including the unintentional inclusion of the database `id` sequence). This compounded into a $>99\%$ false-positive rate. This was remediated via Bonferroni correction and exclusion of non-telemetry features.
- **Gamma Isolation Forest Artifact:** Gamma IF achieved P=0/R=0 during a massive network anomaly. The raw telemetry successfully captured the perturbation, but Isolation Forest suffered from a known bounding-box density artifact: because the synthetic training subset was drawn from a uniform bounding box (no distribution tails), extreme anomalies outside the box fell into the same terminal splits as the dense bounding-box edges. Thus, the anomaly scored perfectly "normal" relative to the training limits. IF cannot safely detect boundary-breaking anomalies when trained on purely synthetically truncated uniform distributions.

## Future Work

- Longer collection period (e.g. 30+ days) to capture true diurnal/weekly cycles.
- Richer temporal baselines (e.g. hour-of-day embeddings).
- Process-level telemetry (e.g. top processes by CPU/Mem) to aid explainability.
- Multivariate residual modeling (using correlations).
- Online scoring and alerting mechanisms.

---
*Note on Gamma CPU Baseline: An investigation using `mpstat -P ALL 1` on Gamma revealed a consistent 25% aggregate CPU usage, corresponding to exactly one fully saturated core (100% utilization on Core 1). This is a persistent single-threaded workload, not an anomaly, and is retained as part of Gamma's normal baseline.*

## Model Training

### Production Model Artifacts (Phase 3A)
We train one model per node (Alpha, Beta, Gamma) rather than a single global model. Node behaviors in the homelab differ radically (e.g., Alpha is an intermittent daily-driver Windows machine, Beta is an always-on data server, Gamma handles network workloads). A single global model would drown out node-specific nuances.

**Why Isolation Forest?**
Isolation Forest is highly appropriate for our unsupervised setup because it isolates anomalies directly rather than profiling normal points, making it robust against training sets that may contain small amounts of hidden anomalous data. Furthermore, our Phase 2.5 evaluation proved that simple univariate methods like MAD collapse on real production data due to natural drift, whereas Isolation Forest effectively handled the high dimensionality and non-normal distributions of 14-day production telemetry.

**14-Day Telemetry Window**
The pipeline leverages 14 days of historical production telemetry (~94k samples). While 14 days provides a solid statistical baseline encompassing weekend and weekday behaviors, it is not a claim of complete coverage. Future seasonality (e.g., monthly backups) will require periodic model retraining.

**Methodology Updates**
During model artifact generation, we identified that the `beta_net_residual` feature was a simple difference between inbound and outbound network traffic, not a true regression residual fitted exclusively on the training set. To prevent methodological confusion and leakage, this feature was renamed to `beta_net_diff`. We also explicitly assert that the database identity `id` is excluded from the feature matrix to avoid leakage.

**Alpha Availability Gaps**
Alpha experiences long expected offline periods. The feature extraction pipeline intentionally strictly respects structural missingness and only extracts features for available windows. We do not interpolate across long offline periods, nor do we convert offline periods into synthetic anomalies. The model is trained purely on the actual collected telemetry.

### Live Inference Worker (Phase 3B)
A lightweight background worker (`scripts/live_inference.py`) continuously polls the production PostgreSQL database for new telemetry every 30 seconds.
- **Incremental Processing**: Maintains a watermark in a dedicated `anomaly_scores` table, ensuring idempotency and efficient querying.
- **Rolling Context**: Fetches a minimal 6-minute history buffer strictly to calculate 5-minute rolling features for the newest samples. 
- **Warmup State**: Samples lacking sufficient history (e.g., right after an Alpha gap) are explicitly scored as `None` (warmup) to prevent unreliable artifacts. 
- **Frozen Models**: Deployed Isolation Forests remain completely frozen (no `.fit()` calls). Thresholds are not aggressively applied to avoid unvalidated alerts.
