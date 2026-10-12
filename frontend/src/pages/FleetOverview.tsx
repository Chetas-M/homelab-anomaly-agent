import React from 'react';
import { Link } from 'react-router-dom';
import { getNodes, getLatestMetrics } from '../services/api';
import { useApi } from '../hooks/useApi';
import { usePolling } from '../hooks/usePolling';
import { getDisplayName } from '../utils/displayNames';
import { formatPercent, formatDateTime } from '../utils/formatters';
import { getNodeIdentityColor } from '../utils/theme';
import { LoadingState, ErrorState, EmptyState } from '../components/States';
import type { NodeOverview, MetricRecord } from '../types';
import { Server, AlertTriangle, ShieldCheck, ShieldAlert } from 'lucide-react';

const NodeCard: React.FC<{ node: NodeOverview }> = ({ node }) => {
  const { data: latest, loading, error } = usePolling<MetricRecord>(() => getLatestMetrics(node.node_id), 30000);

  // Derive model score and anomaly decision from either polled latest or node overview
  const score = latest?.score ?? node.latest_score;
  const isAnomalous = latest?.is_anomalous ?? node.latest_is_anomalous;
  const telemetryTs = latest?.ts || node.last_seen;

  return (
    <Link to={`/node/${node.node_id}`} style={{ color: 'inherit', textDecoration: 'none' }}>
      <div className="card" style={{ transition: 'all 0.2s ease', cursor: 'pointer', height: '100%', display: 'flex', flexDirection: 'column' }} 
           onMouseOver={e => e.currentTarget.style.borderColor = 'var(--color-accent)'}
           onMouseOut={e => e.currentTarget.style.borderColor = 'var(--border-color)'}>
        
        {/* Node Header */}
        <div className="flex justify-between items-center mb-3">
          <div className="flex items-center gap-2">
            <span style={{ 
              width: '10px', height: '10px', borderRadius: '50%', 
              backgroundColor: getNodeIdentityColor(node.node_id) 
            }}></span>
            <Server size={18} className="text-muted" />
            <span style={{ fontSize: '1.125rem', fontWeight: 600 }}>{getDisplayName(node.node_id)}</span>
            <span className="mono text-xs text-muted">({node.node_id})</span>
          </div>
          <div className="flex items-center gap-2">
            {node.online ? (
              <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--color-success)' }}>
                <span className="status-dot online"></span> Live
              </span>
            ) : (
              <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--color-stale)' }}>
                <span className="status-dot offline"></span> Stale
              </span>
            )}
          </div>
        </div>

        {/* Model Classification & Freshness Banner */}
        <div className="flex justify-between items-center mb-3 p-2" style={{
          backgroundColor: isAnomalous === true 
            ? 'rgba(239, 68, 68, 0.12)' 
            : isAnomalous === false 
              ? 'rgba(34, 197, 94, 0.08)' 
              : 'rgba(245, 158, 11, 0.08)',
          border: `1px solid ${
            isAnomalous === true 
              ? 'rgba(239, 68, 68, 0.3)' 
              : isAnomalous === false 
                ? 'rgba(34, 197, 94, 0.2)' 
                : 'rgba(245, 158, 11, 0.2)'
          }`,
          borderRadius: '4px'
        }}>
          <div className="flex items-center gap-1 text-xs font-semibold">
            {isAnomalous === true ? (
              <>
                <ShieldAlert size={14} style={{ color: 'var(--color-error)' }} />
                <span style={{ color: 'var(--color-error)' }}>ANOMALOUS</span>
              </>
            ) : isAnomalous === false ? (
              <>
                <ShieldCheck size={14} style={{ color: 'var(--color-success)' }} />
                <span style={{ color: 'var(--color-success)' }}>NORMAL</span>
              </>
            ) : (
              <>
                <AlertTriangle size={14} style={{ color: 'var(--color-warning)' }} />
                <span style={{ color: 'var(--color-warning)' }}>WARMUP / UNSCORED</span>
              </>
            )}
          </div>
          <div className="mono text-xs text-muted">
            Score: <strong style={{ color: 'var(--text-primary)' }}>
              {score !== null && score !== undefined ? score.toFixed(4) : 'N/A'}
            </strong>
          </div>
        </div>
        
        <div className="text-xs text-muted mb-3 mono">
          Telemetry: {formatDateTime(telemetryTs)}
        </div>

        {error ? (
          <div className="text-xs p-3" style={{ color: 'var(--color-stale)' }}>Failed to load latest metrics</div>
        ) : loading && !latest ? (
          <div className="text-xs text-muted p-3">Loading telemetry...</div>
        ) : latest ? (
          <table className="hairline-table mt-auto w-full text-sm">
            <tbody>
              <tr>
                <td className="text-muted uppercase" style={{fontSize: '0.75rem', width: '45px'}}>CPU</td>
                <td className="mono text-right" style={{width: '60px'}}>{formatPercent(latest.cpu_pct)}</td>
                <td className="px-2">
                  <div style={{ height: '3px', background: 'var(--border-color)', width: '100%', borderRadius: '2px', overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${Math.min(100, Math.max(0, latest.cpu_pct ?? 0))}%`, background: 'var(--text-secondary)' }} />
                  </div>
                </td>
              </tr>
              <tr>
                <td className="text-muted uppercase" style={{fontSize: '0.75rem'}}>Mem</td>
                <td className="mono text-right">{formatPercent(latest.mem_pct)}</td>
                <td className="px-2">
                  <div style={{ height: '3px', background: 'var(--border-color)', width: '100%', borderRadius: '2px', overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${Math.min(100, Math.max(0, latest.mem_pct ?? 0))}%`, background: 'var(--text-secondary)' }} />
                  </div>
                </td>
              </tr>
              <tr>
                <td className="text-muted uppercase" style={{fontSize: '0.75rem'}}>Disk</td>
                <td className="mono text-right">{formatPercent(latest.disk_used_pct)}</td>
                <td className="px-2">
                  <div style={{ height: '3px', background: 'var(--border-color)', width: '100%', borderRadius: '2px', overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${Math.min(100, Math.max(0, latest.disk_used_pct ?? 0))}%`, background: 'var(--text-secondary)' }} />
                  </div>
                </td>
              </tr>
              {node.capabilities.has_gpu && (
                <tr>
                  <td className="text-muted uppercase" style={{fontSize: '0.75rem'}}>GPU</td>
                  <td className="mono text-right">{formatPercent(latest.gpu_util_pct)}</td>
                  <td className="px-2">
                    <div style={{ height: '3px', background: 'var(--border-color)', width: '100%', borderRadius: '2px', overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: `${Math.min(100, Math.max(0, latest.gpu_util_pct ?? 0))}%`, background: 'var(--text-secondary)' }} />
                    </div>
                  </td>
                </tr>
              )}
              {node.capabilities.has_load && !node.capabilities.has_gpu && (
                <tr>
                  <td className="text-muted uppercase" style={{fontSize: '0.75rem'}}>Load</td>
                  <td className="mono text-right">{latest.load1?.toFixed(2) ?? 'N/A'}</td>
                  <td className="px-2 text-xs text-muted mono text-right">
                    5m: {latest.load5?.toFixed(2) ?? 'N/A'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        ) : (
          <div className="text-xs text-muted p-3">No telemetry recorded</div>
        )}
      </div>
    </Link>
  );
};

export default function FleetOverview() {
  const { data: nodes, loading, error, refetch } = useApi<NodeOverview[]>(getNodes);

  if (loading && !nodes) return <LoadingState message="Loading fleet overview..." />;
  if (error) return <ErrorState error={error} onRetry={refetch} />;
  if (!nodes || nodes.length === 0) return <EmptyState message="No nodes discovered in the fleet." />;

  const onlineNodes = nodes.filter(n => n.online).length;
  const offlineNodes = nodes.length - onlineNodes;
  const anomalousNodes = nodes.filter(n => n.latest_is_anomalous === true);

  return (
    <div>
      <div className="grid grid-cols-4 mb-8" style={{ gap: '1.5rem' }}>
        <div className="card">
          <div className="metric-label">Total Nodes</div>
          <div className="mono" style={{ fontSize: '2.5rem', lineHeight: 1 }}>{nodes.length}</div>
          <div className="text-xs text-muted mt-2">Alpha, Beta, Gamma</div>
        </div>
        <div className="card">
          <div className="metric-label">Online / Reporting</div>
          <div className="mono" style={{ fontSize: '2.5rem', lineHeight: 1, color: 'var(--color-success)' }}>{onlineNodes}</div>
          <div className="text-xs text-muted mt-2">Reporting within 120s</div>
        </div>
        <div className="card">
          <div className="metric-label">Stale / Offline</div>
          <div className="mono" style={{ fontSize: '2.5rem', lineHeight: 1, color: offlineNodes > 0 ? 'var(--color-stale)' : 'inherit' }}>{offlineNodes}</div>
          <div className="text-xs text-muted mt-2">Historical telemetry retained</div>
        </div>
        <div className="card">
          <div className="metric-label">Active Anomalies</div>
          <div className="mono" style={{ fontSize: '2.5rem', lineHeight: 1, color: anomalousNodes.length > 0 ? 'var(--color-error)' : 'var(--color-success)' }}>
            {anomalousNodes.length}
          </div>
          <div className="text-xs text-muted mt-2">Isolation Forest output</div>
        </div>
      </div>

      <div className="section-divider">
        <h2 className="section-title">Node Fleet</h2>
      </div>
      <div className="grid grid-cols-3 mb-8">
        {nodes.map(node => (
          <NodeCard key={node.node_id} node={node} />
        ))}
      </div>

      <div style={{ marginTop: '2.5rem' }}>
        <div className="section-divider">
          <h2 className="section-title">Recent Anomaly Events & Node Status</h2>
        </div>
        <table className="hairline-table text-sm w-full">
          <thead>
            <tr>
              <th className="text-left text-muted font-normal pb-2" style={{width: '180px'}}>Latest Sample Time</th>
              <th className="text-left text-muted font-normal pb-2" style={{width: '140px'}}>Node</th>
              <th className="text-left text-muted font-normal pb-2" style={{width: '160px'}}>Model Classification</th>
              <th className="text-left text-muted font-normal pb-2">Inference Status & Score</th>
            </tr>
          </thead>
          <tbody>
            {nodes.map(node => (
              <tr key={node.node_id}>
                <td className="mono text-muted">{formatDateTime(node.last_seen)}</td>
                <td className="font-semibold">{getDisplayName(node.node_id)}</td>
                <td>
                  {node.latest_is_anomalous === true ? (
                    <span style={{ color: 'var(--color-error)', fontWeight: 600 }}>ANOMALY DETECTED</span>
                  ) : node.latest_is_anomalous === false ? (
                    <span style={{ color: 'var(--color-success)' }}>NORMAL</span>
                  ) : (
                    <span style={{ color: 'var(--color-warning)' }}>WARMUP / UNSCORED</span>
                  )}
                </td>
                <td className="mono text-muted">
                  Score: {node.latest_score !== null && node.latest_score !== undefined ? node.latest_score.toFixed(4) : 'Warmup/None'}
                  {' '}({node.online ? 'Online' : 'Offline / Intermittent'})
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
