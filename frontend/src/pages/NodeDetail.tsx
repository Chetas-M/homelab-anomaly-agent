import React, { useState, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import { subHours, formatISO } from 'date-fns';
import { getNode, getLatestMetrics, getMetricsHistory } from '../services/api';
import { useApi } from '../hooks/useApi';
import { usePolling } from '../hooks/usePolling';
import { getDisplayName } from '../utils/displayNames';
import { formatPercent, formatBytesPerSec, formatTemp, formatDateTime } from '../utils/formatters';
import { LoadingState, ErrorState, EmptyState } from '../components/States';
import { MetricCard } from '../components/MetricCard';
import { SkeletonChart } from '../components/SkeletonChart';
import { getNodeIdentityColor } from '../utils/theme';
import type { MetricRecord } from '../types';
import { ChevronLeft, Database, ShieldAlert, ShieldCheck, AlertTriangle } from 'lucide-react';

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
      subtextStyle: { color: '#777', fontSize: 11 },
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
        const item = data.find(d => d.ts === params[0].value[0]);
        if (!item) return '';

        const dateStr = formatDateTime(new Date(item.ts).toISOString());
        let classificationBadge = '<span style="color: #888">UNSCORED</span>';
        if (item.is_anomalous === true) {
          classificationBadge = '<span style="color: #ef4444; font-weight: bold;">● ANOMALOUS</span>';
        } else if (item.is_anomalous === false) {
          classificationBadge = '<span style="color: #22c55e; font-weight: bold;">● NORMAL</span>';
        } else if (item.score === null) {
          classificationBadge = '<span style="color: #f59e0b; font-weight: bold;">▲ WARMUP</span>';
        }

        const scoreStr = item.score !== null && item.score !== undefined ? item.score.toFixed(4) : 'Warmup / None';
        const cpuStr = item.cpu_pct !== null && item.cpu_pct !== undefined ? `${item.cpu_pct.toFixed(1)}%` : 'N/A';
        const memStr = item.mem_pct !== null && item.mem_pct !== undefined ? `${item.mem_pct.toFixed(1)}%` : 'N/A';
        const diskStr = formatBytesPerSec(item.disk_write_bps);
        const netStr = formatBytesPerSec(item.net_out_bps);

        return `
          <div style="font-family: monospace; font-size: 12px;">
            <div style="font-weight: bold; margin-bottom: 4px;">${dateStr}</div>
            <div style="margin-bottom: 4px;">Status: ${classificationBadge}</div>
            <div style="margin-bottom: 6px;">Score: <strong>${scoreStr}</strong></div>
            <div style="color: #888; border-top: 1px solid #333; padding-top: 4px;">
              CPU: ${cpuStr} | Mem: ${memStr}<br/>
              Disk W: ${diskStr} | Net Out: ${netStr}
            </div>
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
    grid: { left: '3%', right: '4%', bottom: '5%', containLabel: true },
    xAxis: {
      type: 'time',
      axisLabel: { color: '#888' },
      splitLine: { show: false }
    },
    yAxis: {
      type: 'value',
      name: 'Score',
      nameTextStyle: { color: '#888' },
      axisLabel: { color: '#888', formatter: '{value}' },
      splitLine: { lineStyle: { color: '#262626' } }
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

  const { data: node, loading: nodeLoading, error: nodeError } = useApi(() => getNode(nodeId!), [nodeId]);
  
  const { data: latest, loading: latestLoading } = usePolling<MetricRecord>(
    () => getLatestMetrics(nodeId!),
    30000,
    true
  );

  const fetchHistory = React.useCallback(async () => {
    if (timeRange.hours === 0 && timeRange.limit) {
      // Latest N records regardless of date window
      return getMetricsHistory(nodeId!, undefined, undefined, timeRange.limit);
    }
    // For stale nodes, anchor query end to node.last_seen so historical ranges return data
    const end = node?.online || !node?.last_seen ? new Date() : new Date(node.last_seen);
    const start = subHours(end, timeRange.hours);
    return getMetricsHistory(nodeId!, formatISO(start), formatISO(end));
  }, [nodeId, timeRange, node]);

  const { data: history, loading: historyLoading, error: historyError } = useApi(fetchHistory, [fetchHistory]);

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

  return (
    <div>
      <div className="mb-4">
        <Link to="/" className="btn mb-4" style={{ background: 'transparent' }}>
          <ChevronLeft size={16} /> Back to Fleet
        </Link>
      </div>
      
      <div className="header">
        <div>
          <h1 className="flex items-center gap-2">
            <span style={{ 
              width: '12px', height: '12px', borderRadius: '50%', 
              backgroundColor: getNodeIdentityColor(node.node_id) 
            }}></span>
            <ServerIcon node={node} /> {getDisplayName(node.node_id)}
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

      {/* Model Anomaly Status & Latest Telemetry */}
      <h3 className="mb-4 text-muted">Model Inference & Latest Telemetry</h3>
      <div className="grid grid-cols-4 mb-8">
        {/* Model Inference Cards */}
        <div className="card" style={{
          borderLeft: `4px solid ${
            isAnomalous === true ? 'var(--color-error)' : isAnomalous === false ? 'var(--color-success)' : 'var(--color-warning)'
          }`
        }}>
          <div className="metric-label">Model Classification</div>
          <div className="flex items-center gap-2 mt-1">
            {isAnomalous === true ? (
              <>
                <ShieldAlert size={20} style={{ color: 'var(--color-error)' }} />
                <span className="font-semibold text-lg" style={{ color: 'var(--color-error)' }}>ANOMALOUS</span>
              </>
            ) : isAnomalous === false ? (
              <>
                <ShieldCheck size={20} style={{ color: 'var(--color-success)' }} />
                <span className="font-semibold text-lg" style={{ color: 'var(--color-success)' }}>NORMAL</span>
              </>
            ) : (
              <>
                <AlertTriangle size={20} style={{ color: 'var(--color-warning)' }} />
                <span className="font-semibold text-lg" style={{ color: 'var(--color-warning)' }}>WARMUP</span>
              </>
            )}
          </div>
          <div className="text-xs text-muted mt-2">Isolation Forest decision</div>
        </div>

        <div className="card">
          <div className="metric-label">Anomaly Score</div>
          <div className="mono font-semibold text-lg mt-1" style={{
            color: isAnomalous === true ? 'var(--color-error)' : 'var(--text-primary)'
          }}>
            {scoreVal !== null && scoreVal !== undefined ? scoreVal.toFixed(4) : (latest ? 'Warmup' : 'N/A')}
          </div>
          <div className="text-xs text-muted mt-2">Threshold: 0.0 (contam=0.01)</div>
        </div>

        {/* Telemetry Metric Cards */}
        {latest ? (
          <>
            <MetricCard label="CPU" value={formatPercent(latest.cpu_pct)} />
            <MetricCard label="Memory" value={formatPercent(latest.mem_pct)} />
            <MetricCard label="Swap" value={formatPercent(latest.swap_pct)} />
            <MetricCard label="Disk Usage" value={formatPercent(latest.disk_used_pct)} />
            
            <MetricCard label="Disk Read" value={formatBytesPerSec(latest.disk_read_bps)} />
            <MetricCard label="Disk Write" value={formatBytesPerSec(latest.disk_write_bps)} />
            <MetricCard label="Net In" value={formatBytesPerSec(latest.net_in_bps)} />
            <MetricCard label="Net Out" value={formatBytesPerSec(latest.net_out_bps)} />

            {node.capabilities.has_load && (
              <>
                <MetricCard label="Load 1" value={latest.load1?.toFixed(2) ?? 'N/A'} />
                <MetricCard label="Load 5" value={latest.load5?.toFixed(2) ?? 'N/A'} />
              </>
            )}
            
            {node.capabilities.has_temp && (
              <MetricCard label="Temp" value={formatTemp(latest.temp_c)} />
            )}

            {node.capabilities.has_gpu && (
              <>
                <MetricCard label="GPU Util" value={formatPercent(latest.gpu_util_pct)} />
                <MetricCard label="GPU VRAM" value={formatPercent(latest.gpu_vram_pct)} />
              </>
            )}
          </>
        ) : latestLoading ? (
          <div className="col-span-2"><LoadingState message="Loading latest telemetry..." /></div>
        ) : (
          <div className="col-span-2"><EmptyState message="No latest telemetry available" /></div>
        )}
      </div>

      {/* Historical Telemetry & Inference Charts */}
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-muted">Historical Trends & Continuous Inference</h3>
        <div className="flex gap-2">
          {TIME_RANGES.map(r => (
            <button 
              key={r.label}
              className={`btn ${timeRange.label === r.label ? 'active' : ''}`}
              onClick={() => setTimeRange(r)}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {historyError && <ErrorState error={historyError} />}
      {historyLoading ? (
        <LoadingState message="Loading historical data..." />
      ) : chartData.length > 0 ? (
        <div>
          {/* Primary Model Anomaly Detection Chart */}
          <div className="card mb-6" style={{ padding: 0, overflow: 'hidden' }}>
            <ReactECharts 
              option={getAnomalyChartOptions(chartData)} 
              style={{ height: '340px' }} 
            />
            <div className="px-4 py-2 text-xs text-muted" style={{ borderTop: '1px solid var(--border-light)', backgroundColor: 'var(--bg-secondary)' }}>
              Note: Model classifications reflect behavioral divergence from learned baseline distributions (Isolation Forest), not proof of hardware failure.
            </div>
          </div>

          {/* Subsystem Telemetry Charts */}
          <div className="grid grid-cols-2">
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
              <ReactECharts 
                option={getChartOptions('System (%)', chartData, ['cpu_pct', 'mem_pct', 'swap_pct'], ['CPU', 'Memory', 'Swap'], '{value}%')} 
                style={{ height: '280px' }} 
              />
            </div>
            
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
              <ReactECharts 
                option={getChartOptions('Network (B/s)', chartData, ['net_in_bps', 'net_out_bps'], ['Ingress', 'Egress'], '{value}')} 
                style={{ height: '280px' }} 
              />
            </div>

            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
              <ReactECharts 
                option={getChartOptions('Disk R/W (B/s)', chartData, ['disk_read_bps', 'disk_write_bps'], ['Read', 'Write'], '{value}')} 
                style={{ height: '280px' }} 
              />
            </div>

            {node.capabilities.has_load && (
              <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                <ReactECharts 
                  option={getChartOptions('System Load', chartData, ['load1', 'load5', 'load15'], ['1m', '5m', '15m'], '{value}')} 
                  style={{ height: '280px' }} 
                />
              </div>
            )}

            {node.capabilities.has_temp && (
              <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                <ReactECharts 
                  option={getChartOptions('Temperature (°C)', chartData, ['temp_c'], ['Core Temp'], '{value}°C')} 
                  style={{ height: '280px' }} 
                />
              </div>
            )}

            {node.capabilities.has_gpu && (
              <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                <ReactECharts 
                  option={getChartOptions('GPU (%)', chartData, ['gpu_util_pct', 'gpu_vram_pct'], ['Utilization', 'VRAM'], '{value}%')} 
                  style={{ height: '280px' }} 
                />
              </div>
            )}
          </div>
        </div>
      ) : (
        <SkeletonChart />
      )}
    </div>
  );
}

const ServerIcon = ({ node }: { node: any }) => {
  return <Database size={24} className={node.online ? 'text-success' : 'text-muted'} />;
};
