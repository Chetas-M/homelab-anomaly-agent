# Phase 2.5: Production Evaluation Report

## 1. Experimental Methodology
We transitioned the evaluation from the synthetic, temporally compressed `test.db` surrogate over to the true 14-day PostgreSQL telemetry dataset on Beta. 

The evaluation was structured rigorously to prevent data leakage and evaluate real-world performance:
1. **Chronological Split:** The models were trained exclusively on 14 days of historical production telemetry prior to the real-world test window.
2. **Physical Injection Events:** We algorithmically commanded the physical hardware to undergo controlled 3-minute physical stress events:
    - **Alpha (Windows):** Python Multiprocessing core saturation (CPU Stress)
    - **Beta (Ubuntu):** `dd` direct block-level zero-write loop (Disk IO Stress)
    - **Gamma (Ubuntu):** `wget` 1GB null-routed loop (Network Stress)
3. **External Labelling:** The exact physical start and end timestamps (UTC) were logged independently into `real_experiment_log.json`.
4. **Evaluation:** The pipeline parsed the new telemetry database and evaluated model predictions strictly against the chronological windows defined in the log.

## 2. Production Evaluation Results

```text
Processing node: alpha (CPU Stress)
IF: P=0.571, R=1.000, F1=0.727 | TP=4  FP=3  TN=64 FN=0
MAD: P=0.056, R=1.000, F1=0.107 | TP=4  FP=67 TN=0  FN=0

Processing node: beta (Disk IO Stress)
IF: P=0.353, R=1.000, F1=0.522 | TP=6  FP=11 TN=56 FN=0
MAD: P=0.098, R=1.000, F1=0.179 | TP=6  FP=55 TN=12 FN=0

Processing node: gamma (Network Stress)
IF: P=0.929, R=1.000, F1=0.963 | TP=13 FP=1  TN=59 FN=0
MAD: P=0.178, R=1.000, F1=0.302 | TP=13 FP=60 TN=0  FN=0
```

## 3. Key Findings & Insights

1. **The Gamma Bounding-Box Artifact is Resolved:** 
   In the synthetic `test.db` evaluation, Gamma's Isolation Forest scored 0.000 F1 on a massive network spike due to an algorithmic bounding-box artifact caused by uniform, tail-less synthetic boundaries. In this production evaluation, the 14 days of natural telemetry provided genuine statistical tails, completely resolving the artifact. Gamma IF achieved a **96.3% F1 score**, successfully identifying 13 of 13 physical anomaly samples with only 1 false positive.

2. **MAD is Fundamentally Incompatible with Real Production Telemetry:**
   Despite the Bonferroni statistical corrections applied earlier, the MAD baseline completely collapsed on real production data. Over a 14-day chronological window, physical hardware experiences significant natural drift and minor volatility (e.g. OS background indexers, cron jobs). MAD flags all of these as anomalies, resulting in horrific precision (5% - 17%). Univariate statistical boundaries are strictly insufficient for modern heterogeneous nodes.

3. **Isolation Forest Provides an Initial Experimental Baseline:**
   Without further algorithmic tuning, Isolation Forest adapted to the 14-day production distributions well enough to detect the specific controlled physical stresses injected during the experiment. It achieved **100% recall** strictly for these three specific, extreme anomaly events (CPU, Disk, and Network). Precision ranged from 35% on Beta to 92% on Gamma. The lower precision on Beta (11 false positives) highlights that the true baseline on Beta is noisy, and these false positives in a short window suggest that precision in long-term production may be significantly lower. 

## 4. Final Conclusion
The methodology has been experimentally verified against controlled physical perturbations using chronologically isolated production telemetry. While Isolation Forest drastically outperforms the univariate statistical baseline in this specific test, this is only experimental evidence and not a claim of broad production reliability. It provides a functional, deployable starting point for the anomaly observation agent, but its true real-world precision and recall remain unknown. No additional algorithmic tuning is recommended until extensive long-term, organic production labels are gathered.
