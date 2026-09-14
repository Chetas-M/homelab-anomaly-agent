import React, { useState, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import { subHours, formatISO } from 'date-fns';
import { getNode, getLatestMetrics, getMetricsHistory } from '../services/api';
import { useApi } from '../hooks/useApi';
import { usePolling } from '../hooks/usePolling';
import { getDisplayName } from '../utils/displayNames';
import { formatPercent, formatBytesPerSec, formatTemp, formatDateTime } from '../utils/formatters';
import { LoadingState, ErrorState } from '../components/States';
import { MetricCard } from '../components/MetricCard';
import { SkeletonChart } from '../components/SkeletonChart';
import { getNodeIdentityColor } from '../utils/theme';
import type { MetricRecord } from '../types';
import { ChevronLeft, Database, ShieldAlert } from 'lucide-react';

const TIME_RANGES = [
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

export default function NodeDetail() {
  const { nodeId } = useParams<{ nodeId: string }>();
  const [timeRange, setTimeRange] = useState(TIME_RANGES[0]);

  const { data: node, loading: nodeLoading, error: nodeError } = useApi(() => getNode(nodeId!), [nodeId]);
  
  const { data: latest, loading: latestLoading } = usePolling<MetricRecord>(
    () => getLatestMetrics(nodeId!),
    30000,
    true
  );

  const fetchHistory = React.useCallback(async () => {
    const end = new Date();
    const start = subHours(end, timeRange.hours);
    return getMetricsHistory(nodeId!, formatISO(start), formatISO(end));
  }, [nodeId, timeRange]);

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

  return (
    <div>
      <div className="mb-4">
        <Link to="/" className="btn mb-4" style={{ background: 'transparent' }}><ChevronLeft size={16} /> Back to Fleet</Link>
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
              {node.online ? 'Online' : 'Stale'}
            </span>
            <span>Last seen: {formatDateTime(node.last_seen)}</span>
            <span>First seen: {formatDateTime(node.first_seen)}</span>
          </div>
        </div>
        <div className="flex gap-2">
          <Link to={`/node/${node.node_id}/quality`} className="btn">
            <ShieldAlert size={16} /> Data Quality
          </Link>
        </div>
      </div>

      <h3 className="mb-4 text-muted">Latest Telemetry</h3>
      <div className="grid grid-cols-4 mb-8">
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
                <MetricCard label="Load 15" value={latest.load15?.toFixed(2) ?? 'N/A'} />
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
          <div className="col-span-4"><LoadingState message="Loading latest telemetry..." /></div>
        ) : (
          <div className="col-span-4"><EmptyState message="No latest telemetry available" /></div>
        )}
      </div>

      <div className="flex justify-between items-center mb-4">
        <h3 className="text-muted">Historical Trends</h3>
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
        <div className="grid grid-cols-2">
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <ReactECharts 
              option={getChartOptions('System (%)', chartData, ['cpu_pct', 'mem_pct', 'swap_pct'], ['CPU', 'Memory', 'Swap'], '{value}%')} 
              style={{ height: '300px' }} 
            />
          </div>
          
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <ReactECharts 
              option={getChartOptions('Network (B/s)', chartData, ['net_in_bps', 'net_out_bps'], ['Ingress', 'Egress'], '{value}')} 
              style={{ height: '300px' }} 
            />
          </div>

          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <ReactECharts 
              option={getChartOptions('Disk R/W (B/s)', chartData, ['disk_read_bps', 'disk_write_bps'], ['Read', 'Write'], '{value}')} 
              style={{ height: '300px' }} 
            />
          </div>

          {node.capabilities.has_load && (
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
              <ReactECharts 
                option={getChartOptions('System Load', chartData, ['load1', 'load5', 'load15'], ['1m', '5m', '15m'], '{value}')} 
                style={{ height: '300px' }} 
              />
            </div>
          )}

          {node.capabilities.has_temp && (
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
              <ReactECharts 
                option={getChartOptions('Temperature (°C)', chartData, ['temp_c'], ['Core Temp'], '{value}°C')} 
                style={{ height: '300px' }} 
              />
            </div>
          )}

          {node.capabilities.has_gpu && (
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
              <ReactECharts 
                option={getChartOptions('GPU (%)', chartData, ['gpu_util_pct', 'gpu_vram_pct'], ['Utilization', 'VRAM'], '{value}%')} 
                style={{ height: '300px' }} 
              />
            </div>
          )}
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
