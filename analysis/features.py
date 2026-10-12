import pandas as pd
import numpy as np

def apply_log1p(df, columns):
    """Applies log1p transformation to non-negative features."""
    for col in columns:
        if col in df.columns:
            # Ensure no negative values are transformed blindly
            valid = df[col] >= 0
            df.loc[valid, f"{col}_log1p"] = np.log1p(df.loc[valid, col])
            df.loc[~valid, f"{col}_log1p"] = np.nan
    return df

def apply_rolling_features(df, columns, window='5min'):
    """Calculates rolling mean and std over a time window."""
    # Ensure dataframe is sorted and index is datetime
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame index must be DatetimeIndex for time-based rolling.")
    
    rolling = df[columns].rolling(window)
    means = rolling.mean().add_suffix(f'_roll_mean_{window}')
    stds = rolling.std().add_suffix(f'_roll_std_{window}')
    
    return pd.concat([df, means, stds], axis=1)

def apply_rate_of_change(df, columns):
    """Calculates time-aware rate of change."""
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame index must be DatetimeIndex.")
        
    time_diff = df.index.to_series().diff().dt.total_seconds()
    
    for col in columns:
        if col in df.columns:
            diff = df[col].diff()
            df[f"{col}_roc"] = diff / time_diff
            
    return df

def extract_features(df, node_id, use_log1p=True, use_rolling=True, use_roc=True):
    """
    Extracts features for a specific node, applying selected transformations.
    Structural missingness is respected (features entirely missing remain NaN).
    """
    ndf = df[df['node_id'] == node_id].copy()
    if ndf.empty:
        return ndf
        
    ndf = ndf.sort_values('ts').set_index('ts')
    
    # Base features
    base_metrics = [
        'cpu_pct', 'mem_pct', 'swap_pct', 
        'disk_read_bps', 'disk_write_bps', 'disk_used_pct',
        'net_in_bps', 'net_out_bps', 
        'load1', 'load5', 'load15', 
        'temp_c', 
        'gpu_util_pct', 'gpu_vram_pct'
    ]
    
    available_metrics = [m for m in base_metrics if m in ndf.columns and not ndf[m].isna().all()]
    
    if use_log1p:
        # disk and net bps are typically heavy-tailed
        heavy_metrics = [m for m in ['disk_read_bps', 'disk_write_bps', 'net_in_bps', 'net_out_bps'] if m in available_metrics]
        ndf = apply_log1p(ndf, heavy_metrics)
        
    if use_rolling:
        # Apply rolling to regular metrics and disk/network
        roll_metrics = [m for m in ['cpu_pct', 'mem_pct', 'disk_read_bps', 'disk_write_bps', 'net_in_bps', 'net_out_bps'] if m in available_metrics]
        ndf = apply_rolling_features(ndf, roll_metrics, window='5min')
        
    if use_roc:
        roc_metrics = [m for m in ['mem_pct', 'disk_used_pct'] if m in available_metrics]
        ndf = apply_rate_of_change(ndf, roc_metrics)
        
    if node_id == 'beta' and 'net_in_bps' in available_metrics and 'net_out_bps' in available_metrics:
        # Beta strong correlation difference
        # Renamed from 'residual' to 'diff' because it is a simple difference,
        # not a true regression residual fitted on the training set.
        ndf['beta_net_diff'] = ndf['net_out_bps'] - ndf['net_in_bps']
        
    return ndf.reset_index()
