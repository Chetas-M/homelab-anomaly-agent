# Production Model Training Report

## Leakage Audit
- **Training Cutoff Time:** 2026-09-27T05:53:29.896129+00:00
- **Excluded Experiment Periods:**
  - alpha-win: 2026-09-27T06:23:29.896129+00:00 to 2026-09-27T06:25:30.256365+00:00
  - beta: 2026-09-27T06:23:29.897909+00:00 to 2026-09-27T06:26:31.555365+00:00
  - gamma: 2026-09-27T06:23:29.901088+00:00 to 2026-09-27T06:29:55.253731+00:00

## Node: alpha
- **Training Samples:** 13096
- **Feature Count:** 31
- **Time Range:** 2026-09-13T04:16:37.671666+00:00 to 2026-09-27T05:53:16.926648+00:00
- **IF Hyperparameters:** `n_estimators=100`, `contamination=0.01`
- **Median Anomaly Score (Train):** -0.226
- **99th Pct Anomaly Score (Train):** -0.000
### Selected Features
cpu_pct, mem_pct, swap_pct, disk_read_bps, disk_write_bps, disk_used_pct, net_in_bps, net_out_bps, load1, load5, load15, gpu_util_pct, gpu_vram_pct, disk_read_bps_log1p, disk_write_bps_log1p, net_in_bps_log1p, net_out_bps_log1p, cpu_pct_roll_mean_5min, mem_pct_roll_mean_5min, disk_read_bps_roll_mean_5min, disk_write_bps_roll_mean_5min, net_in_bps_roll_mean_5min, net_out_bps_roll_mean_5min, cpu_pct_roll_std_5min, mem_pct_roll_std_5min, disk_read_bps_roll_std_5min, disk_write_bps_roll_std_5min, net_in_bps_roll_std_5min, net_out_bps_roll_std_5min, mem_pct_roc, disk_used_pct_roc

## Node: beta
- **Training Samples:** 40173
- **Feature Count:** 31
- **Time Range:** 2026-09-13T06:39:37.110084+00:00 to 2026-09-27T05:53:06.528997+00:00
- **IF Hyperparameters:** `n_estimators=100`, `contamination=0.01`
- **Median Anomaly Score (Train):** -0.268
- **99th Pct Anomaly Score (Train):** -0.000
### Selected Features
cpu_pct, mem_pct, swap_pct, disk_read_bps, disk_write_bps, disk_used_pct, net_in_bps, net_out_bps, load1, load5, load15, temp_c, disk_read_bps_log1p, disk_write_bps_log1p, net_in_bps_log1p, net_out_bps_log1p, cpu_pct_roll_mean_5min, mem_pct_roll_mean_5min, disk_read_bps_roll_mean_5min, disk_write_bps_roll_mean_5min, net_in_bps_roll_mean_5min, net_out_bps_roll_mean_5min, cpu_pct_roll_std_5min, mem_pct_roll_std_5min, disk_read_bps_roll_std_5min, disk_write_bps_roll_std_5min, net_in_bps_roll_std_5min, net_out_bps_roll_std_5min, mem_pct_roc, disk_used_pct_roc, beta_net_diff

## Node: gamma
- **Training Samples:** 41054
- **Feature Count:** 30
- **Time Range:** 2026-09-12T17:00:06.357363+00:00 to 2026-09-27T05:53:06.701626+00:00
- **IF Hyperparameters:** `n_estimators=100`, `contamination=0.01`
- **Median Anomaly Score (Train):** -0.276
- **99th Pct Anomaly Score (Train):** 0.000
### Selected Features
cpu_pct, mem_pct, swap_pct, disk_read_bps, disk_write_bps, disk_used_pct, net_in_bps, net_out_bps, load1, load5, load15, temp_c, disk_read_bps_log1p, disk_write_bps_log1p, net_in_bps_log1p, net_out_bps_log1p, cpu_pct_roll_mean_5min, mem_pct_roll_mean_5min, disk_read_bps_roll_mean_5min, disk_write_bps_roll_mean_5min, net_in_bps_roll_mean_5min, net_out_bps_roll_mean_5min, cpu_pct_roll_std_5min, mem_pct_roll_std_5min, disk_read_bps_roll_std_5min, disk_write_bps_roll_std_5min, net_in_bps_roll_std_5min, net_out_bps_roll_std_5min, mem_pct_roc, disk_used_pct_roc
