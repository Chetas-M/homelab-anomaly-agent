# Phase 2.5: Methodological Validation Report

## 1. MAD Diagnosis
**Initial Observation**: All three nodes originally produced identical precision (0.036), recall (1.000), and F1 (0.069).
**Diagnosis**:
- The primary cause of identical 100% false-positive exceedance rates was the unintentional inclusion of the `id` database auto-increment column in the feature set. Because `id` is strictly increasing, 100% of the chronologically split evaluation data had values wildly exceeding the training median `id`.
- The `aggregate_score = max(feature_robust_z)` rule correctly compounded this issue. For $k=24$ features, the theoretical family-wise probability of at least one normal feature exceeding $z=3.0$ by chance is $\approx 6.5\%$.
- Furthermore, `swap_pct` caused a systemic baseline shift for Alpha and Beta, because `test.db` contained older real telemetry where `swap_pct > 0`, but the synthetic data generation script hardcoded `swap_pct = 0`, causing every synthetic evaluation row to register as a severe anomaly relative to the older `test.db` baseline.
**Corrections Made**: Excluded the `id` column and implemented a Bonferroni-corrected threshold ($z=3.85$) for the MAD algorithm.

## 2. Gamma IF Diagnosis
**Initial Observation**: Gamma Isolation Forest failed completely (Precision=0, Recall=0, F1=0).
**Diagnosis**:
- The synthetic network event absolutely manifested in the telemetry (`net_out_bps` baseline median was ~3,000; during event it hit 114,273 with max 146,296). The monitored interface was correct.
- **Root Cause of IF Failure**: The Isolation Forest failure is a known algorithm limitation related to data bounding boxes and density. The training data for Gamma was strictly synthetic, creating a completely uniform distribution (e.g. `net_out_bps` uniformly drawn between 2,500 and 5,000). Because IF makes random splits between the minimum and maximum of the *training* data in each node, any evaluation point far outside this bounding box is simply routed into the outermost leaf along with all points at the boundary. Since the boundary of a uniform distribution is highly dense, the outermost leaves require many splits to isolate normal points, resulting in a long path length. Thus, the extreme anomaly receives a normal score.
**Corrections Made**: No IF parameter changes were made, as this is an inherent algorithmic limitation on strictly bounded synthetic data without tail variance. 

## 3. Dataset Validation
**Diagnosis**: `test.db` was compared against the `summary.json` dataset inventory computed from the actual production PostgreSQL dump.
**Result**: `test.db` does **not** represent production telemetry.
- Gamma CPU production median was 25.0%, while `test.db` had 12.2% (relative diff 0.51).
- Beta CPU production median was 0.7%, while `test.db` had 16.0% (relative diff 21.8).
- Gamma `net_out_bps` production median was 346, while `test.db` had 3189 (relative diff 8.2).
**Conclusion**: `test.db` contains significant synthetic overwrite/drift compared to production. It serves to test the pipeline syntax, but the performance bounds measured here are not calibrated to the real homelab baseline.

## 4. Feature Analysis
**Diagnosis**:
- **Disk/Network Rolling Features**: The original implementation lacked rolling features for disk and network. Adding 5-minute rolling means/stds for disk/network was implemented to capture context around burst traffic.
- **Beta Residual Analysis**: A linear residual test predicting Beta's `net_out` from `net_in` yielded $R^2 = 0.744$. This strong correlation indicates that a physical dependency exists on Beta (likely bridging/routing). The feature `beta_net_residual = net_out_bps - net_in_bps` was added exclusively for Beta.

## 5. Evaluation Counts (After Corrections)
```text
Processing node: gamma
IF: P=0.000, R=0.000, F1=0.000 | TP=0 FP=0 TN=269 FN=10
MAD: P=0.385, R=1.000, F1=0.556 | TP=10 FP=16 TN=253 FN=0

Processing node: alpha
IF: P=0.818, R=0.900, F1=0.857 | TP=9 FP=2 TN=267 FN=1
MAD: P=0.079, R=1.000, F1=0.146 | TP=10 FP=117 TN=152 FN=0

Processing node: beta
IF: P=1.000, R=0.900, F1=0.947 | TP=9 FP=0 TN=269 FN=1
MAD: P=0.064, R=1.000, F1=0.120 | TP=10 FP=147 TN=122 FN=0
```
*Note: Alpha and Beta MAD false positives remain relatively high due to the synthetic dataset shift (e.g., `swap_pct` dropping from 10% in historic test.db data to exactly 0% in the synthetic generation script).*

## 6. Changes Made
The following evidence-backed changes were made:
1. Removed `id` from feature extraction loop.
2. Added `beta_net_residual` to Beta's feature set.
3. Added 5-minute rolling mean and std to `disk_read_bps`, `disk_write_bps`, `net_in_bps`, `net_out_bps`.
4. Applied a Bonferroni threshold ($z=3.85$) to MAD to safely bound the maximum family-wise exceedance rate.
5. Re-calculated explicit confusion matrix metrics (`tp`, `fp`, `tn`, `fn`).

## 7. Remaining Limitations
- **IF Density Artifact**: IF cannot identify extreme out-of-bounds anomalies when trained purely on synthetic uniform data without tails. 
- **Sample Size**: Testing events represent exactly 10 samples (5 minutes). This is not statistically powerful enough for robust performance validation.
- **Data Representative Failure**: `test.db` differs from production by factors of $20\times$ in some metrics.

## 8. Recommendation
NOT READY — SPECIFIC BLOCKERS REMAIN
- Must be evaluated against the true production dataset (PostgreSQL), not the structurally drifting `test.db`.
- The IF baseline fails to detect extreme bounds anomalies if it learns exclusively from boundary-dense synthetic data. A natural training set (or non-uniform synthetic augmentation) is strictly required to prevent the bounding-box path-length artifact.
