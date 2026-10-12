import React, { useState, useMemo, useEffect, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import { subHours, formatISO } from 'date-fns';
import { getNode, getLatestMetrics, getMetricsHistory, getNodeAttributions, getNodeShadowSummary } from '../services/api';
import { useApi } from '../hooks/useApi';
import { usePolling } from '../hooks/usePolling';
import { getDisplayName } from '../utils/displayNames';
import { formatPercent, formatBytesPerSec, formatTemp, formatDateTime } from '../utils/formatters';
import { LoadingState, ErrorState, EmptyState } from '../components/States';
import { MetricCard } from '../components/MetricCard';
import { SkeletonChart } from '../components/SkeletonChart';
import { getNodeIdentityColor } from '../utils/theme';
import type { MetricRecord, NodeAttributionResponse, MetricAttributionRecord, ShadowComparisonSummary } from '../types';
import { ChevronLeft, ShieldAlert, ShieldCheck, AlertTriangle, Activity, RefreshCw } from 'lucide-react';

interface TimeRangeOption {
  label: string;
  hours: number;
  limit?: number;
}

const TIME_RANGES: TimeRangeOption[] = [
  { label: 'Latest 100', hours: 0, limit: 100 },
  { label: 'Latest 500', hours: 0, limit: 500 },
  { label: '1H', hours: 1 },
  { label: '6H', hours: 6 },
  { label: '24H', hours: 24 },
  { label: '7D', hours: 168 },
];

const getChartOptions = (title: string, data: any[], seriesKeys: string[], seriesNames: string[], yAxisFormatter: string) => ({
  title: {
    text: title,
    textStyle: { color: '#e0e0e0', fontSize: 14, fontWeight: 'normal' },
    left: '10px',
    top: '10px'
  },
  tooltip: {
    trigger: 'axis',
    backgroundColor: '#1a1a1a',
    borderColor: '#333',
    textStyle: { color: '#e0e0e0' }
  },
  legend: {
    data: seriesNames,
    textStyle: { color: '#888' },
    top: '10px',
    right: '10px'
  },
  grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  xAxis: {
    type: 'time',
    axisLabel: { color: '#888' },
    splitLine: { show: false }
  },
  yAxis: {
    type: 'value',
    axisLabel: { color: '#888', formatter: yAxisFormatter },
    splitLine: { lineStyle: { color: '#333' } }
  },
  series: seriesKeys.map((key, i) => ({
    name: seriesNames[i],
    type: 'line',
    showSymbol: false,
    sampling: 'lttb',
    data: data.map(item => [item.ts, item[key]])
  })),
  color: ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444']
});

const getAnomalyChartOptions = (data: any[]) => {
  const lineData = data.map(d => [d.ts, d.score !== null && d.score !== undefined ? d.score : null]);
  const anomaliesData = data.filter(d => d.is_anomalous === true).map(d => [d.ts, d.score]);
  const warmupData = data.filter(d => d.score === null || d.score === undefined).map(d => [d.ts, 0]);

  return {
    title: {
      text: 'Model Anomaly Score & Classification Over Time',
      subtext: 'Isolation Forest inference output: is_anomalous=true indicates anomalous, score=null indicates warmup',
      textStyle: { color: '#e0e0e0', fontSize: 14, fontWeight: 'normal' },
      subtextStyle: { color: '#888', fontSize: 11 },
      left: '10px',
      top: '10px'
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1a1a1a',
      borderColor: '#333',
      textStyle: { color: '#e0e0e0' },
      formatter: (params: any) => {
        if (!params || !params.length) return '';
        const dateStr = formatDateTime(params[0].value[0]);
        const scoreVal = params[0].value[1];
        const pointData = data.find(d => d.ts === params[0].value[0]);
        let statusBadge = '<span style="color:#22c55e;">NORMAL</span>';
        if (pointData?.is_anomalous === true) {
          statusBadge = '<span style="color:#ef4444;font-weight:bold;">ANOMALY</span>';
        } else if (pointData?.is_anomalous === null || pointData?.score === null) {
          statusBadge = '<span style="color:#f59e0b;">WARMUP</span>';
        }

        return `
          <div style="font-family: monospace; font-size: 12px;">
            <div>${dateStr}</div>
            <div style="margin-top: 4px;">Classification: ${statusBadge}</div>
            <div>Score: <strong>${scoreVal !== null && scoreVal !== undefined ? Number(scoreVal).toFixed(4) : 'Warmup/None'}</strong></div>
            ${pointData?.cpu_pct !== undefined ? `<div>CPU: ${pointData.cpu_pct?.toFixed(1)}% | Mem: ${pointData.mem_pct?.toFixed(1)}%</div>` : ''}
          </div>
        `;
      }
    },
    legend: {
      data: ['Anomaly Score', 'Anomalous Sample', 'Warmup Sample'],
      textStyle: { color: '#888' },
      top: '10px',
      right: '10px'
    },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'time',
      axisLabel: { color: '#888' },
      splitLine: { show: false }
    },
    yAxis: {
      type: 'value',
      name: 'Score',
      axisLabel: { color: '#888' },
      splitLine: { lineStyle: { color: '#333' } }
    },
    series: [
      {
        name: 'Anomaly Score',
        type: 'line',
        showSymbol: false,
        sampling: 'lttb',
        connectNulls: false,
        lineStyle: { width: 2, color: '#3b82f6' },
        data: lineData,
        markLine: {
          symbol: 'none',
          silent: true,
          data: [
            {
              yAxis: 0,
              lineStyle: { color: '#f59e0b', type: 'dashed', width: 1.5 },
              label: { formatter: 'Threshold (0.0)', position: 'end', color: '#f59e0b', fontSize: 10 }
            }
          ]
        }
      },
      {
        name: 'Anomalous Sample',
        type: 'scatter',
        symbol: 'circle',
        symbolSize: 8,
        itemStyle: { color: '#ef4444', borderColor: '#ffffff', borderWidth: 1 },
        data: anomaliesData
      },
      {
        name: 'Warmup Sample',
        type: 'scatter',
        symbol: 'triangle',
        symbolSize: 6,
        itemStyle: { color: '#f59e0b' },
        data: warmupData
      }
    ]
  };
};

export default function NodeDetail() {
  const { nodeId } = useParams<{ nodeId: string }>();
  const [timeRange, setTimeRange] = useState<TimeRangeOption>(TIME_RANGES[0]);
  const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date());
  const [attributions, setAttributions] = useState<MetricAttributionRecord[]>([]);

  const { data: node, loading: nodeLoading, error: nodeError } = useApi(() => getNode(nodeId!), [nodeId]);
  
  const { data: latest, refetch: refetchLatest } = usePolling<MetricRecord>(
    () => getLatestMetrics(nodeId!),
    15000,
    true
  );

  const { data: shadowSummary, refetch: refetchShadow } = usePolling<ShadowComparisonSummary>(
    () => getNodeShadowSummary(nodeId!),
    15000,
    true
  );

  // Poll attributions with in-flight guard
  const isFetchingAttrRef = useRef(false);
  useEffect(() => {
    let active = true;
    const fetchAttr = async () => {
      if (!nodeId || isFetchingAttrRef.current) return;
      isFetchingAttrRef.current = true;
      try {
        const resp: NodeAttributionResponse = await getNodeAttributions(nodeId);
        if (active && resp?.attributions) {
          setAttributions(resp.attributions);
          setLastRefreshed(new Date());
        }
      } catch (e) {
        console.error('Failed to load metric attributions', e);
      } finally {
        isFetchingAttrRef.current = false;
      }
    };
    fetchAttr();
    const interval = setInterval(fetchAttr, 15000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [nodeId]);

  const fetchHistory = React.useCallback(async () => {
    if (timeRange.hours === 0 && timeRange.limit) {
      return getMetricsHistory(nodeId!, undefined, undefined, timeRange.limit);
    }
    const end = node?.online || !node?.last_seen ? new Date() : new Date(node.last_seen);
    const start = subHours(end, timeRange.hours);
    return getMetricsHistory(nodeId!, formatISO(start), formatISO(end));
  }, [nodeId, timeRange, node]);

  const { data: history, loading: historyLoading, error: historyError, refetch: refetchHistory } = useApi(fetchHistory, [fetchHistory]);

  // Periodic chart history update for online nodes without page reload
  useEffect(() => {
    let active = true;
    const pollHistory = async () => {
      if (!nodeId || !node?.online) return;
      try {
        await refetchHistory();
        if (active) setLastRefreshed(new Date());
      } catch (e) {
        console.error('Failed to refresh chart history', e);
      }
    };
    const interval = setInterval(pollHistory, 30000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [nodeId, node?.online, refetchHistory]);

  const handleManualRefresh = async () => {
    await Promise.all([refetchLatest(), refetchHistory(), refetchShadow()]);
    if (nodeId) {
      const resp = await getNodeAttributions(nodeId);
      if (resp?.attributions) setAttributions(resp.attributions);
    }
    setLastRefreshed(new Date());
  };

  const chartData = useMemo(() => {
    if (!history) return [];
    return history.map(h => ({
      ...h,
      ts: new Date(h.ts).getTime()
    }));
  }, [history]);

  if (nodeLoading) return <LoadingState message="Loading node details..." />;
  if (nodeError) return <ErrorState error={nodeError} />;
  if (!node) return <EmptyState message="Node not found." />;

  const isAnomalous = latest?.is_anomalous ?? node.latest_is_anomalous;
  const scoreVal = latest?.score ?? node.latest_score;
  const isSustained = node.sustained_anomaly === true || node.alert_status === 'SUSTAINED ANOMALY';
  const streakCount = node.streak_count ?? (isAnomalous ? 1 : 0);

  // Group attributions
  const elevatedMetrics = attributions.filter(a => a.status === 'ELEVATED');

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <Link to="/" className="btn" style={{ background: 'transparent' }}>
          <ChevronLeft size={16} /> Back to Fleet
        </Link>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted mono">
            Auto-refresh: 15s • Updated: {lastRefreshed.toLocaleTimeString()}
          </span>
          <button className="btn text-xs py-1 px-2.5 flex items-center gap-1" onClick={handleManualRefresh}>
            <RefreshCw size={12} /> Refresh
          </button>
        </div>
      </div>
      
      <div className="header">
        <div>
          <h1 className="flex items-center gap-2">
            <span style={{ 
              width: '12px', height: '12px', borderRadius: '50%', 
              backgroundColor: getNodeIdentityColor(node.node_id) 
            }}></span>
            <span style={{ fontSize: '1.75rem', fontWeight: 600 }}>{getDisplayName(node.node_id)}</span>
            <span className="text-sm text-muted mono ml-2">({node.node_id})</span>
          </h1>
          <div className="text-sm text-muted mt-2 flex items-center gap-4">
            <span className="flex items-center gap-1">
              {node.online ? <span className="status-dot online"></span> : <span className="status-dot offline"></span>}
              {node.online ? 'Online (reporting)' : 'Stale / Offline'}
            </span>
            <span>Last seen: {formatDateTime(latest?.ts || node.last_seen)}</span>
            <span>First seen: {formatDateTime(node.first_seen)}</span>
          </div>
        </div>
        <div className="flex gap-2">
          <Link to={`/node/${node.node_id}/quality`} className="btn">
            <ShieldAlert size={16} /> Data Quality
          </Link>
        </div>
      </div>

      {/* Live Shadow Canary Section (Active on Beta) */}
      {shadowSummary?.candidate_active && (
        <div className="card mb-8" style={{ border: '1px solid rgba(139, 92, 246, 0.4)', backgroundColor: 'rgba(139, 92, 246, 0.03)' }}>
          <div className="flex justify-between items-start mb-4">
            <div>
              <div className="flex items-center gap-2">
                <span style={{ 
                  backgroundColor: 'rgba(139, 92, 246, 0.2)', 
                  color: '#c4b5fd', 
                  fontSize: '11px', 
                  fontWeight: 700, 
                  padding: '2px 8px', 
                  borderRadius: '4px',
                  border: '1px solid rgba(139, 92, 246, 0.4)',
                  letterSpacing: '0.05em'
                }}>
                  LIVE SHADOW CANARY
                </span>
                <span className="text-xs text-muted mono">
                  Read-only evaluation against live incoming telemetry
                </span>
              </div>
              <p className="text-sm text-secondary mt-1">
                Candidate model is scoring identical live telemetry concurrently with the frozen production model. Candidate output is strictly isolated and does not influence production alerts or classifications.
              </p>
            </div>
            <div className="text-right">
              <div className="text-xs text-muted">Audited Scored Samples</div>
              <div className="mono font-semibold" style={{ fontSize: '1.25rem', color: '#c4b5fd' }}>
                {shadowSummary.total_scored_samples}
                <span className="text-xs text-muted font-normal ml-1">({shadowSummary.total_warmup_samples} warmup)</span>
              </div>
            </div>
          </div>

          {/* Side-by-side comparison */}
          <div className="grid grid-cols-2 gap-4 mb-4">
            {/* Production Model */}
            <div style={{ backgroundColor: 'rgba(59, 130, 246, 0.05)', border: '1px solid rgba(59, 130, 246, 0.25)', borderRadius: '6px', padding: '12px' }}>
              <div className="flex justify-between items-center mb-2">
                <span className="mono text-xs font-semibold" style={{ color: '#60a5fa' }}>
                  PRODUCTION MODEL (FROZEN)
                </span>
                <span className="text-xs text-muted mono">Version: {shadowSummary.frozen_version}</span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <div className="text-xs text-muted">Anomaly Rate</div>
                  <div className="mono text-lg font-bold" style={{ color: shadowSummary.production_anomaly_rate_pct > 0 ? 'var(--color-warning)' : 'var(--color-success)' }}>
                    {shadowSummary.production_anomaly_rate_pct.toFixed(2)}%
                    <span className="text-xs text-muted font-normal ml-1">({shadowSummary.production_anomaly_count} samples)</span>
                  </div>
                </div>
                <div>
                  <div className="text-xs text-muted">Score Distribution</div>
                  <div className="mono text-xs mt-1">
                    Med: {shadowSummary.frozen_score_distribution.median !== null && shadowSummary.frozen_score_distribution.median !== undefined ? shadowSummary.frozen_score_distribution.median.toFixed(4) : 'N/A'} • P95: {shadowSummary.frozen_score_distribution.p95 !== null && shadowSummary.frozen_score_distribution.p95 !== undefined ? shadowSummary.frozen_score_distribution.p95.toFixed(4) : 'N/A'}
                  </div>
                </div>
              </div>
              <div className="text-xs text-muted mt-2 border-t border-light pt-1">
                Authority: <strong>Active Production</strong> (triggers alerts & sustained state)
              </div>
            </div>

            {/* Shadow Candidate Model */}
            <div style={{ backgroundColor: 'rgba(139, 92, 246, 0.06)', border: '1px solid rgba(139, 92, 246, 0.35)', borderRadius: '6px', padding: '12px' }}>
              <div className="flex justify-between items-center mb-2">
                <span className="mono text-xs font-semibold" style={{ color: '#c4b5fd' }}>
                  SHADOW CANDIDATE (ISOLATED)
                </span>
                <span className="text-xs text-muted mono">Artifact: {shadowSummary.candidate_artifact_id || 'candidate'}</span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <div className="text-xs text-muted">Anomaly Rate</div>
                  <div className="mono text-lg font-bold" style={{ color: shadowSummary.candidate_anomaly_rate_pct > 0 ? '#c4b5fd' : 'var(--color-success)' }}>
                    {shadowSummary.candidate_anomaly_rate_pct.toFixed(2)}%
                    <span className="text-xs text-muted font-normal ml-1">({shadowSummary.candidate_anomaly_count} samples)</span>
                  </div>
                </div>
                <div>
                  <div className="text-xs text-muted">Score Distribution</div>
                  <div className="mono text-xs mt-1">
                    Med: {shadowSummary.candidate_score_distribution.median !== null && shadowSummary.candidate_score_distribution.median !== undefined ? shadowSummary.candidate_score_distribution.median.toFixed(4) : 'N/A'} • P95: {shadowSummary.candidate_score_distribution.p95 !== null && shadowSummary.candidate_score_distribution.p95 !== undefined ? shadowSummary.candidate_score_distribution.p95.toFixed(4) : 'N/A'}
                  </div>
                </div>
              </div>
              <div className="text-xs text-muted mt-2 border-t border-light pt-1">
                Authority: <strong>Read-Only Shadow</strong> (zero alert authority, audit only)
              </div>
            </div>
          </div>

          {/* Concordance and Disagreements Grid */}
          <div className="grid grid-cols-4 gap-3 text-sm">
            <div className="card" style={{ padding: '8px 12px', margin: 0, backgroundColor: 'var(--bg-secondary)' }}>
              <div className="text-xs text-muted">Model Concordance</div>
              <div className="mono font-bold text-base" style={{ color: 'var(--color-success)' }}>
                {shadowSummary.concordance_rate_pct.toFixed(1)}%
              </div>
              <div className="text-xs text-muted">{shadowSummary.concordance_count} matching decisions</div>
            </div>

            <div className="card" style={{ padding: '8px 12px', margin: 0, backgroundColor: 'var(--bg-secondary)' }}>
              <div className="text-xs text-muted">Disagreements</div>
              <div className="mono font-bold text-base" style={{ color: shadowSummary.disagreement_count > 0 ? 'var(--color-warning)' : 'var(--text-muted)' }}>
                {shadowSummary.disagreement_rate_pct.toFixed(1)}%
              </div>
              <div className="text-xs text-muted">{shadowSummary.disagreement_count} split decisions</div>
            </div>

            <div className="card" style={{ padding: '8px 12px', margin: 0, backgroundColor: 'var(--bg-secondary)' }}>
              <div className="text-xs text-muted">Candidate-Only Anomalies</div>
              <div className="mono font-bold text-base" style={{ color: shadowSummary.candidate_only_anomalies > 0 ? '#c4b5fd' : 'var(--text-muted)' }}>
                {shadowSummary.candidate_only_anomalies}
              </div>
              <div className="text-xs text-muted">Flagged by Candidate only</div>
            </div>

            <div className="card" style={{ padding: '8px 12px', margin: 0, backgroundColor: 'var(--bg-secondary)' }}>
              <div className="text-xs text-muted">Frozen-Only Anomalies</div>
              <div className="mono font-bold text-base" style={{ color: shadowSummary.frozen_only_anomalies > 0 ? 'var(--color-warning)' : 'var(--text-muted)' }}>
                {shadowSummary.frozen_only_anomalies}
              </div>
              <div className="text-xs text-muted">Flagged by Frozen only</div>
            </div>
          </div>

          <div className="flex justify-between items-center text-xs text-muted mt-3 pt-2 border-t border-light mono">
            <span>Canary Started: {formatDateTime(shadowSummary.earliest_shadow_ts)}</span>
            <span>Latest Audited Sample: {formatDateTime(shadowSummary.latest_shadow_ts)}</span>
            <span style={{ color: '#22c55e' }}>Idempotency Guard: Active (node_id, ts)</span>
          </div>
        </div>
      )}

      {/* Model Anomaly Status & Latest Telemetry */}
      <h3 className="mb-4 text-muted">Model Inference & Latest Telemetry</h3>
      <div className="grid grid-cols-4 mb-8">
        <div className="card" style={{ 
          borderColor: isAnomalous === true ? 'var(--color-warning)' : isAnomalous === false ? 'var(--color-success)' : 'var(--border-color)' 
        }}>
          <div className="metric-label flex items-center gap-1">
            {isAnomalous === true ? (
              <AlertTriangle size={14} style={{ color: 'var(--color-warning)' }} />
            ) : isAnomalous === false ? (
              <ShieldCheck size={14} style={{ color: 'var(--color-success)' }} />
            ) : (
              <AlertTriangle size={14} style={{ color: 'var(--text-muted)' }} />
            )}
            Sample Classification
          </div>
          <div className="mono" style={{ 
            fontSize: '1.5rem', 
            lineHeight: 1.2, 
            color: isAnomalous === true ? 'var(--color-warning)' : isAnomalous === false ? 'var(--color-success)' : 'var(--text-muted)' 
          }}>
            {isAnomalous === true ? 'ANOMALOUS SAMPLE' : isAnomalous === false ? 'NORMAL' : 'WARMUP'}
          </div>
          <div className="text-xs text-muted mt-2">Latest single scored sample</div>
        </div>

        <div className="card" style={{ 
          borderColor: isSustained ? 'var(--color-error)' : 'var(--border-color)',
          backgroundColor: isSustained ? 'rgba(239, 68, 68, 0.08)' : 'inherit'
        }}>
          <div className="metric-label flex items-center gap-1">
            <ShieldAlert size={14} style={{ color: isSustained ? 'var(--color-error)' : isAnomalous ? 'var(--color-warning)' : 'var(--color-success)' }} />
            Sustained Alert State
          </div>
          <div className="mono" style={{ 
            fontSize: '1.5rem', 
            lineHeight: 1.2, 
            color: isSustained ? 'var(--color-error)' : isAnomalous ? 'var(--color-warning)' : 'var(--color-success)' 
          }}>
            {isSustained ? 'SUSTAINED (3/3)' : isAnomalous ? `STREAK (${streakCount}/3)` : 'NORMAL (0/3)'}
          </div>
          <div className="text-xs text-muted mt-2">
            {isSustained ? 'Active alert (≥ 3 samples)' : `Threshold: 3 consecutive anomalies`}
          </div>
        </div>

        <div className="card">
          <div className="metric-label">Anomaly Score</div>
          <div className="mono" style={{ fontSize: '1.75rem', lineHeight: 1.2 }}>
            {scoreVal !== null && scoreVal !== undefined ? scoreVal.toFixed(4) : 'Warmup'}
          </div>
          <div className="text-xs text-muted mt-2">Threshold: 0.0 (contam=0.01)</div>
        </div>

        <MetricCard title="CPU" value={formatPercent(latest?.cpu_pct)} subValue="Utilization" />
        <MetricCard title="Memory" value={formatPercent(latest?.mem_pct)} subValue="RAM Used" />
        <MetricCard title="Swap" value={formatPercent(latest?.swap_pct)} subValue="Swap Used" />
        <MetricCard title="Disk Usage" value={formatPercent(latest?.disk_used_pct)} subValue="Storage Used" />
        <MetricCard title="Disk Read" value={formatBytesPerSec(latest?.disk_read_bps)} subValue="Read rate" />
        <MetricCard title="Disk Write" value={formatBytesPerSec(latest?.disk_write_bps)} subValue="Write rate" />
        <MetricCard title="Net In" value={formatBytesPerSec(latest?.net_in_bps)} subValue="Ingress" />
        <MetricCard title="Net Out" value={formatBytesPerSec(latest?.net_out_bps)} subValue="Egress" />

        {node.capabilities.has_load && (
          <>
            <MetricCard title="Load 1" value={latest?.load1 !== null && latest?.load1 !== undefined ? latest.load1.toFixed(2) : 'N/A'} subValue="1m Average" />
            <MetricCard title="Load 5" value={latest?.load5 !== null && latest?.load5 !== undefined ? latest.load5.toFixed(2) : 'N/A'} subValue="5m Average" />
          </>
        )}

        {node.capabilities.has_temp && (
          <MetricCard title="Temp" value={formatTemp(latest?.temp_c)} subValue="Package" />
        )}

        {node.capabilities.has_gpu && (
          <>
            <MetricCard title="GPU Util" value={formatPercent(latest?.gpu_util_pct)} subValue="Core" />
            <MetricCard title="GPU VRAM" value={formatPercent(latest?.gpu_vram_pct)} subValue="VRAM" />
          </>
        )}
      </div>

      {/* Priority 2: Per-Metric Anomaly Attribution Layer */}
      <div className="mb-8">
        <div className="flex justify-between items-center mb-2">
          <h3 className="text-muted flex items-center gap-2">
            <Activity size={18} style={{ color: 'var(--color-accent)' }} />
            Per-Metric Baseline Attribution & Deviation Analysis
          </h3>
          {elevatedMetrics.length > 0 && (
            <span style={{
              fontSize: '0.75rem',
              fontWeight: 600,
              padding: '2px 8px',
              borderRadius: '4px',
              backgroundColor: 'rgba(239, 68, 68, 0.15)',
              color: 'var(--color-error)'
            }}>
              {elevatedMetrics.length} Metric{elevatedMetrics.length > 1 ? 's' : ''} Elevated
            </span>
          )}
        </div>
        <p className="text-xs text-muted mb-4">
          Baseline Attribution Layer: Robust Z-Scores computed using rolling median and MAD against trained baseline distributions. Identifies metric-level evidence and abnormal signals without claiming causal explanation of the Isolation Forest tree structure.
        </p>

        <div className="grid grid-cols-3 gap-4">
          {attributions.map(attr => {
            let statusColor = 'var(--text-muted)';
            let statusBg = 'rgba(255, 255, 255, 0.05)';
            if (attr.status === 'ELEVATED') {
              statusColor = 'var(--color-error)';
              statusBg = 'rgba(239, 68, 68, 0.1)';
            } else if (attr.status === 'NORMAL') {
              statusColor = 'var(--color-success)';
              statusBg = 'rgba(34, 197, 94, 0.08)';
            } else if (attr.status === 'LOW') {
              statusColor = '#38bdf8';
              statusBg = 'rgba(56, 189, 248, 0.08)';
            }

            return (
              <div key={attr.metric_key} className="card p-3" style={{
                borderColor: attr.status === 'ELEVATED' ? 'rgba(239, 68, 68, 0.4)' : 'var(--border-color)',
                backgroundColor: attr.status === 'ELEVATED' ? 'rgba(239, 68, 68, 0.03)' : 'inherit'
              }}>
                <div className="flex justify-between items-center mb-1">
                  <span className="text-xs font-semibold">{attr.display_name}</span>
                  <span style={{
                    fontSize: '0.65rem',
                    fontWeight: 700,
                    padding: '1px 6px',
                    borderRadius: '3px',
                    backgroundColor: statusBg,
                    color: statusColor
                  }}>
                    {attr.status}
                  </span>
                </div>

                <div className="flex items-baseline justify-between my-1">
                  <span className="mono font-bold" style={{ fontSize: '1.25rem' }}>
                    {attr.formatted_val}
                  </span>
                  <span className="mono text-xs text-muted">
                    {attr.deviation_z !== null ? `${attr.deviation_z > 0 ? '+' : ''}${attr.deviation_z}σ` : ''}
                  </span>
                </div>

                <div className="text-xs text-muted mono mb-2">
                  Ref Range: {attr.reference_range}
                </div>

                <div className="text-xs text-muted" style={{ fontSize: '0.75rem', lineHeight: 1.3 }}>
                  {attr.explanation}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Historical Telemetry Charts */}
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-muted">Historical Trends & Continuous Inference</h3>
        <div className="flex gap-2">
          {TIME_RANGES.map(range => (
            <button
              key={range.label}
              className={`btn ${timeRange.label === range.label ? 'active' : ''}`}
              onClick={() => setTimeRange(range)}
            >
              {range.label}
            </button>
          ))}
        </div>
      </div>

      {historyLoading && !history ? (
        <div className="grid grid-cols-2 gap-4">
          <SkeletonChart />
          <SkeletonChart />
        </div>
      ) : historyError ? (
        <ErrorState error={historyError} onRetry={refetchHistory} />
      ) : chartData.length === 0 ? (
        <EmptyState message="No historical telemetry available for this range." />
      ) : (
        <div className="space-y-6">
          {/* Dedicated Model Score & Anomaly Timeline Chart */}
          <div className="card" style={{ height: '340px', padding: '10px' }}>
            <ReactECharts 
              option={getAnomalyChartOptions(chartData)} 
              style={{ height: '100%', width: '100%' }} 
              notMerge={true}
            />
          </div>

          <div className="grid grid-cols-2 gap-4" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
            <div className="card" style={{ height: '280px', padding: '10px' }}>
              <ReactECharts 
                option={getChartOptions('CPU & Memory Utilization', chartData, ['cpu_pct', 'mem_pct'], ['CPU %', 'Memory %'], '{value}%')} 
                style={{ height: '100%', width: '100%' }} 
                notMerge={true}
              />
            </div>

            <div className="card" style={{ height: '280px', padding: '10px' }}>
              <ReactECharts 
                option={getChartOptions('Disk I/O Throughput', chartData, ['disk_read_bps', 'disk_write_bps'], ['Read', 'Write'], '{value} B/s')} 
                style={{ height: '100%', width: '100%' }} 
                notMerge={true}
              />
            </div>

            <div className="card" style={{ height: '280px', padding: '10px' }}>
              <ReactECharts 
                option={getChartOptions('Network Traffic', chartData, ['net_in_bps', 'net_out_bps'], ['Inbound', 'Outbound'], '{value} B/s')} 
                style={{ height: '100%', width: '100%' }} 
                notMerge={true}
              />
            </div>

            {node.capabilities.has_load ? (
              <div className="card" style={{ height: '280px', padding: '10px' }}>
                <ReactECharts 
                  option={getChartOptions('System Load Average', chartData, ['load1', 'load5', 'load15'], ['1m', '5m', '15m'], '{value}')} 
                  style={{ height: '100%', width: '100%' }} 
                  notMerge={true}
                />
              </div>
            ) : (
              <div className="card" style={{ height: '280px', padding: '10px' }}>
                <ReactECharts 
                  option={getChartOptions('Disk Used %', chartData, ['disk_used_pct'], ['Disk Used %'], '{value}%')} 
                  style={{ height: '100%', width: '100%' }} 
                  notMerge={true}
                />
              </div>
            )}
          </div>
        </div>
      )}

      <div className="mt-8 text-xs text-muted">
        Note: Model classifications reflect behavioral divergence from learned baseline distributions (Isolation Forest), not proof of hardware failure.
      </div>
    </div>
  );
}
