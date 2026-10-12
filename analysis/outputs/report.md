# Phase 2 EDA Report

Generated on: 2026-09-26 23:44:34.521293

## Dataset Inventory
### alpha
- Samples: 13001
- Time Span: 1173321.129532 seconds
- Avg Interval: 90.26 seconds
- Gaps >60s: 38
- Coverage: 33.24%

### gamma
- Samples: 39654
- Time Span: 1213930.000174 seconds
- Avg Interval: 30.61 seconds
- Gaps >60s: 10
- Coverage: 97.99%

### beta
- Samples: 38773
- Time Span: 1164759.219435 seconds
- Avg Interval: 30.04 seconds
- Gaps >60s: 2
- Coverage: 99.86%

## Structural Missingness
Identified metrics with 100% missing values per node:
- **alpha**: temp_c
- **gamma**: gpu_util_pct, gpu_vram_pct
- **beta**: gpu_util_pct, gpu_vram_pct
