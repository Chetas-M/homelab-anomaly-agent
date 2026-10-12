# Phase 2.5: Model Evaluation Report

## Performance Comparison

| Node | Method | Precision | Recall | F1 | ROC-AUC | TP | FP | FN | TN | Predicted anomalies |
|------|--------|-----------|--------|----|---------|----|----|----|----|---------------------|
| alpha | IF | 0.571 | 1.000 | 0.727 | 1.000 | 4 | 3 | 0 | 64 | 7 |
| alpha | MAD | 0.056 | 1.000 | 0.107 | 0.989 | 4 | 67 | 0 | 0 | 71 |
| beta | IF | 0.353 | 1.000 | 0.522 | 0.998 | 6 | 11 | 0 | 56 | 17 |
| beta | MAD | 0.098 | 1.000 | 0.179 | 0.923 | 6 | 55 | 0 | 12 | 61 |
| gamma | IF | 0.929 | 1.000 | 0.963 | 1.000 | 13 | 1 | 0 | 59 | 14 |
| gamma | MAD | 0.178 | 1.000 | 0.302 | 1.000 | 13 | 60 | 0 | 0 | 73 |

## Population Statistics

### alpha
- Normal instances: 67
- Weakly anomalous instances: 4

### beta
- Normal instances: 67
- Weakly anomalous instances: 6

### gamma
- Normal instances: 60
- Weakly anomalous instances: 13

