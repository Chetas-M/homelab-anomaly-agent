import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from analysis.eda import load_data
import pandas as pd

df = load_data('analysis/outputs/dump.csv') if os.path.exists('analysis/outputs/dump.csv') else load_data()

metrics_to_check = ['disk_read_bps', 'disk_write_bps', 'net_in_bps', 'net_out_bps']

for node in df['node_id'].unique():
    ndf = df[df['node_id'] == node]
    print(f"\n--- Node: {node} ---")
    for metric in metrics_to_check:
        if metric in ndf.columns and not ndf[metric].isna().all():
            p99 = ndf[metric].quantile(0.99)
            max_val = ndf[metric].max()
            print(f"{metric}: p99={p99:.2f}, max={max_val:.2f}")
            if max_val > p99 * 5 and max_val > 0: # Arbitrary threshold to inspect
                print(f"  Top 5 {metric} values:")
                print(ndf.nlargest(5, metric)[['ts', metric]].to_string(index=False))
