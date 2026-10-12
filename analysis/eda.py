import os
import sys
import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sqlalchemy import create_engine
import json
from datetime import datetime

sns.set_theme(style="whitegrid")

METRICS = [
    'cpu_pct', 'mem_pct', 'swap_pct', 
    'disk_read_bps', 'disk_write_bps', 'disk_used_pct',
    'net_in_bps', 'net_out_bps', 
    'load1', 'load5', 'load15', 
    'temp_c', 
    'gpu_util_pct', 'gpu_vram_pct'
]

def load_data(csv_path=None):
    if csv_path:
        print(f"Loading data from CSV: {csv_path}")
        try:
            df = pd.read_csv(csv_path, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding='utf-16')
        df['ts'] = pd.to_datetime(df['ts'])
        return df

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL environment variable is not set and no --csv argument provided.")
        sys.exit(1)
        
    print(f"Connecting to database...")
    engine = create_engine(db_url)
    query = "SELECT * FROM node_metrics ORDER BY node_id, ts"
    print("Loading data from database...")
    df = pd.read_sql(query, engine)
    df['ts'] = pd.to_datetime(df['ts'])
    if df['ts'].dt.tz is None:
        df['ts'] = df['ts'].dt.tz_localize('UTC')
    return df

def dataset_inventory(df):
    results = {}
    for node in df['node_id'].unique():
        ndf = df[df['node_id'] == node].sort_values('ts')
        count = len(ndf)
        first_ts = ndf['ts'].min()
        last_ts = ndf['ts'].max()
        time_span = (last_ts - first_ts).total_seconds() if count > 1 else 0
        
        intervals = ndf['ts'].diff().dt.total_seconds().dropna()
        if len(intervals) > 0:
            avg_interval = intervals.mean()
            median_interval = intervals.median()
            std_interval = intervals.std()
            p01 = intervals.quantile(0.01)
            p05 = intervals.quantile(0.05)
            p95 = intervals.quantile(0.95)
            p99 = intervals.quantile(0.99)
            gaps_gt_60 = (intervals > 60).sum()
            largest_gap = intervals.max()
        else:
            avg_interval = median_interval = std_interval = p01 = p05 = p95 = p99 = gaps_gt_60 = largest_gap = 0
        
        # Nominal interval 30s
        expected_samples = (time_span / 30) + 1 if time_span > 0 else count
        coverage_pct = (count / expected_samples) * 100 if expected_samples > 0 else 100
        
        results[node] = {
            "sample_count": int(count),
            "first_timestamp": str(first_ts),
            "last_timestamp": str(last_ts),
            "observed_time_span_seconds": float(time_span),
            "approx_sampling_interval_seconds": float(avg_interval),
            "median_interval": float(median_interval),
            "std_interval": float(std_interval),
            "p01_interval": float(p01),
            "p05_interval": float(p05),
            "p95_interval": float(p95),
            "p99_interval": float(p99),
            "gaps_gt_60s": int(gaps_gt_60),
            "largest_gap_seconds": float(largest_gap),
            "expected_samples": int(expected_samples),
            "coverage_pct": float(coverage_pct)
        }
    return results

def metric_inventory(df):
    results = {}
    for node in df['node_id'].unique():
        ndf = df[df['node_id'] == node]
        node_res = {}
        for metric in METRICS:
            if metric not in df.columns:
                continue
            series = ndf[metric]
            count = len(series)
            null_count = series.isna().sum()
            valid_count = count - null_count
            null_pct = (null_count / count) * 100 if count > 0 else 0
            
            if valid_count > 0:
                stats = {
                    "count": int(count),
                    "null_count": int(null_count),
                    "null_pct": float(null_pct),
                    "valid_count": int(valid_count),
                    "min": float(series.min()),
                    "max": float(series.max()),
                    "mean": float(series.mean()),
                    "median": float(series.median()),
                    "std": float(series.std() if valid_count > 1 else 0),
                    "p01": float(series.quantile(0.01)),
                    "p05": float(series.quantile(0.05)),
                    "p25": float(series.quantile(0.25)),
                    "p50": float(series.quantile(0.50)),
                    "p75": float(series.quantile(0.75)),
                    "p95": float(series.quantile(0.95)),
                    "p99": float(series.quantile(0.99))
                }
            else:
                stats = {
                    "count": int(count),
                    "null_count": int(null_count),
                    "null_pct": float(null_pct),
                    "valid_count": 0
                }
            node_res[metric] = stats
        results[node] = node_res
    return results

def plot_distributions(df, out_dir):
    for metric in METRICS:
        if metric not in df.columns:
            continue
        plt.figure(figsize=(10, 6))
        sns.histplot(data=df, x=metric, hue='node_id', bins=50, kde=True, element="step", stat="density", common_norm=False)
        plt.title(f"Distribution of {metric}")
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, f"dist_{metric}.png"))
        plt.close()

def time_analysis(df, nodes, out_dir, prefix="time_of_day", time_col='hour'):
    for metric in METRICS:
        if metric not in df.columns:
            continue
        
        plt.figure(figsize=(10, 6))
        for node in nodes:
            ndf = df[df['node_id'] == node]
            if ndf[metric].notna().sum() == 0:
                continue
            
            # Group by time col
            grouped = ndf.groupby(time_col)[metric].agg(['mean', lambda x: x.quantile(0.95)]).reset_index()
            grouped.columns = [time_col, 'mean', 'p95']
            
            plt.plot(grouped[time_col], grouped['mean'], label=f"{node} Mean", marker='o')
            plt.plot(grouped[time_col], grouped['p95'], label=f"{node} p95", linestyle='--', alpha=0.7)
            
        plt.title(f"{prefix.replace('_', ' ').title()} - {metric}")
        plt.xlabel(time_col.title())
        plt.ylabel(metric)
        plt.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, f"{prefix}_{metric}.png"))
        plt.close()

def correlation_analysis(df, out_dir):
    results = {}
    for node in df['node_id'].unique():
        ndf = df[df['node_id'] == node][METRICS].dropna(axis=1, how='all')
        if ndf.empty:
            continue
        
        pearson = ndf.corr(method='pearson')
        spearman = ndf.corr(method='spearman')
        
        plt.figure(figsize=(12, 10))
        sns.heatmap(pearson, annot=True, cmap='coolwarm', fmt=".2f", vmin=-1, vmax=1)
        plt.title(f"Pearson Correlation - {node}")
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, f"corr_pearson_{node}.png"))
        plt.close()
        
        results[node] = {
            "pearson": pearson.to_dict(),
            "spearman": spearman.to_dict()
        }
    return results

def temporal_aggregation(df, nodes, out_dir):
    results = {}
    for node in nodes:
        ndf = df[df['node_id'] == node].set_index('ts').sort_index()
        node_res = {}
        for window in ['1min', '5min']:
            # Resample numeric cols
            agg_df = ndf[METRICS].resample(window).agg(['count', 'mean', 'std', 'max'])
            
            win_res = {}
            for metric in METRICS:
                if metric not in ndf.columns or ndf[metric].notna().sum() == 0:
                    continue
                win_res[metric] = {
                    "raw_samples": int(ndf[metric].count()),
                    "agg_bins": int(len(agg_df)),
                    "empty_bins": int((agg_df[metric]['count'] == 0).sum()),
                    "agg_mean": float(agg_df[metric]['mean'].mean()),
                    "agg_max": float(agg_df[metric]['max'].max()),
                    "agg_std_of_means": float(agg_df[metric]['mean'].std())
                }
            node_res[window] = win_res
        results[node] = node_res
    return results

def baseline_stability(df, nodes, out_dir):
    # Rolling stats
    for node in nodes:
        ndf = df[df['node_id'] == node].sort_values('ts').set_index('ts')
        # Time-based rolling window
        rolling = ndf[METRICS].rolling('1h')
        
        for metric in ['cpu_pct', 'mem_pct', 'temp_c']:
            if metric not in ndf.columns or ndf[metric].notna().sum() == 0:
                continue
                
            rmean = rolling[metric].mean()
            rstd = rolling[metric].std()
            
            plt.figure(figsize=(12, 6))
            plt.plot(ndf.index, rmean, label='Rolling Mean (1h)')
            plt.fill_between(ndf.index, rmean - rstd, rmean + rstd, alpha=0.2, label='±1 Std')
            plt.title(f"Baseline Stability - {node} - {metric}")
            plt.legend()
            plt.tight_layout()
            plt.savefig(os.path.join(out_dir, f"stability_{node}_{metric}.png"))
            plt.close()

def alpha_analysis(df, out_dir):
    ndf = df[df['node_id'] == 'alpha'].sort_values('ts').copy()
    if ndf.empty:
        return {}
    
    # Identify sessions > 10 min gap
    ndf['gap'] = ndf['ts'].diff().dt.total_seconds()
    ndf['session_id'] = (ndf['gap'] > 600).cumsum()
    
    sessions = []
    for sid, group in ndf.groupby('session_id'):
        sessions.append({
            "session_id": int(sid),
            "start": str(group['ts'].min()),
            "end": str(group['ts'].max()),
            "duration_seconds": float((group['ts'].max() - group['ts'].min()).total_seconds()),
            "samples": len(group)
        })
        
    return {"sessions": sessions, "total_sessions": len(sessions)}

def main():
    parser = argparse.ArgumentParser(description="EDA for Homelab Anomaly Agent")
    parser.add_argument('--csv', type=str, help="Path to CSV dump of node_metrics")
    parser.add_argument('--out', type=str, default="outputs", help="Output directory")
    args = parser.parse_args()
    
    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)
    
    df = load_data(args.csv)
    
    # Enrich dataframe for time analysis
    df['ts_local'] = df['ts'].dt.tz_convert('Asia/Kolkata')
    df['hour'] = df['ts_local'].dt.hour
    df['day_of_week'] = df['ts_local'].dt.dayofweek
    
    print("A. Dataset inventory...")
    inv_data = dataset_inventory(df)
    
    print("B. Metric inventory...")
    met_data = metric_inventory(df)
    
    print("C. Distribution analysis...")
    plot_distributions(df, out_dir)
    
    # Baselines
    continuous_nodes = [n for n in ['beta', 'gamma'] if n in df['node_id'].unique()]
    
    print("D. Time-of-day analysis...")
    time_analysis(df, continuous_nodes, out_dir, prefix="time_of_day", time_col='hour')
    
    print("E. Day-of-week analysis...")
    time_analysis(df, continuous_nodes, out_dir, prefix="day_of_week", time_col='day_of_week')
    
    print("F. Correlation analysis...")
    corr_data = correlation_analysis(df, out_dir)
    
    print("H. Temporal aggregation...")
    agg_data = temporal_aggregation(df, continuous_nodes, out_dir)
    
    print("I. Baseline stability...")
    baseline_stability(df, continuous_nodes, out_dir)
    
    print("J. Alpha-specific analysis...")
    alpha_data = alpha_analysis(df, out_dir)
    
    summary = {
        "timestamp": str(datetime.now()),
        "dataset_inventory": inv_data,
        "metric_inventory": met_data,
        "correlations": corr_data,
        "temporal_aggregation": agg_data,
        "alpha_analysis": alpha_data
    }
    
    with open(os.path.join(out_dir, 'summary.json'), 'w') as f:
        json.dump(summary, f, indent=2)
        
    # Generate Markdown Report
    with open(os.path.join(out_dir, 'report.md'), 'w') as f:
        f.write("# Phase 2 EDA Report\n\n")
        f.write(f"Generated on: {summary['timestamp']}\n\n")
        f.write("## Dataset Inventory\n")
        for node, data in inv_data.items():
            f.write(f"### {node}\n")
            f.write(f"- Samples: {data['sample_count']}\n")
            f.write(f"- Time Span: {data['observed_time_span_seconds']} seconds\n")
            f.write(f"- Avg Interval: {data['approx_sampling_interval_seconds']:.2f} seconds\n")
            f.write(f"- Gaps >60s: {data['gaps_gt_60s']}\n")
            f.write(f"- Coverage: {data['coverage_pct']:.2f}%\n\n")
        
        f.write("## Structural Missingness\n")
        f.write("Identified metrics with 100% missing values per node:\n")
        for node, mdata in met_data.items():
            missing = [m for m, d in mdata.items() if d['null_pct'] == 100]
            f.write(f"- **{node}**: {', '.join(missing) if missing else 'None'}\n")
            
    print(f"EDA complete. Outputs saved to {out_dir}")

if __name__ == "__main__":
    main()
