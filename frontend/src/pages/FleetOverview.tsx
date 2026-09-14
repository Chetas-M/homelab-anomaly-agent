import React from 'react';
import { Link } from 'react-router-dom';
import { getNodes, getLatestMetrics } from '../services/api';
import { useApi } from '../hooks/useApi';
import { usePolling } from '../hooks/usePolling';
import { getDisplayName } from '../utils/displayNames';
import { formatPercent, formatTime } from '../utils/formatters';
import { getNodeIdentityColor } from '../utils/theme';
import { LoadingState, ErrorState, EmptyState } from '../components/States';
import type { NodeOverview, MetricRecord } from '../types';
import { Server, HardDrive, Activity } from 'lucide-react';

const NodeCard: React.FC<{ node: NodeOverview }> = ({ node }) => {
  // Use polling for each node's latest data.
  // Note: in a production massive fleet, this N+1 should be replaced by a single /api/nodes/latest backend endpoint.
  const { data: latest, loading, error } = usePolling<MetricRecord>(() => getLatestMetrics(node.node_id), 30000);

  return (
    <Link to={`/node/${node.node_id}`} style={{ color: 'inherit', textDecoration: 'none' }}>
      <div className="card" style={{ transition: 'border-color 0.2s', cursor: 'pointer' }} 
           onMouseOver={e => e.currentTarget.style.borderColor = 'var(--color-accent)'}
           onMouseOut={e => e.currentTarget.style.borderColor = 'var(--border-color)'}>
        
        <div className="flex justify-between items-center mb-4">
          <div className="flex items-center gap-2">
            <span style={{ 
              width: '10px', height: '10px', borderRadius: '50%', 
              backgroundColor: getNodeIdentityColor(node.node_id) 
            }}></span>
            <Server size={18} className="text-muted" />
            <span style={{ fontSize: '1.125rem', fontWeight: 500 }}>{getDisplayName(node.node_id)}</span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            {node.online ? <span className="status-dot online"></span> : <span className="status-dot offline"></span>}
            <span className="text-muted">{node.online ? 'Online' : 'Stale'}</span>
          </div>
        </div>
        
        <div className="text-xs text-muted mb-4 mono">
          Last seen: {formatTime(node.last_seen)}
        </div>

        {error ? (
          <div className="text-xs" style={{ color: 'var(--color-stale)' }}>Failed to load latest metrics</div>
        ) : loading && !latest ? (
          <div className="text-xs text-muted">Loading metrics...</div>
        ) : latest ? (
          <table className="hairline-table mt-4 w-full text-sm">
            <tbody>
              <tr>
                <td className="text-muted uppercase" style={{fontSize: '0.75rem'}}>CPU</td>
                <td className="mono text-right">{formatPercent(latest.cpu_pct)}</td>
                <td className="w-1/2 px-2">
                  <div style={{ height: '2px', background: 'var(--border-color)', width: '100%' }}>
                    <div style={{ height: '100%', width: `${Math.min(100, Math.max(0, latest.cpu_pct))}%`, background: 'var(--text-secondary)' }} />
                  </div>
                </td>
              </tr>
              <tr>
                <td className="text-muted uppercase" style={{fontSize: '0.75rem'}}>Mem</td>
                <td className="mono text-right">{formatPercent(latest.mem_pct)}</td>
                <td className="w-1/2 px-2">
                  <div style={{ height: '2px', background: 'var(--border-color)', width: '100%' }}>
                    <div style={{ height: '100%', width: `${Math.min(100, Math.max(0, latest.mem_pct))}%`, background: 'var(--text-secondary)' }} />
                  </div>
                </td>
              </tr>
              <tr>
                <td className="text-muted uppercase" style={{fontSize: '0.75rem'}}>Disk</td>
                <td className="mono text-right">{formatPercent(latest.disk_used_pct)}</td>
                <td className="w-1/2 px-2">
                  <div style={{ height: '2px', background: 'var(--border-color)', width: '100%' }}>
                    <div style={{ height: '100%', width: `${Math.min(100, Math.max(0, latest.disk_used_pct))}%`, background: 'var(--text-secondary)' }} />
                  </div>
                </td>
              </tr>
              {node.capabilities.has_gpu && (
                <tr>
                  <td className="text-muted uppercase" style={{fontSize: '0.75rem'}}>GPU</td>
                  <td className="mono text-right">{formatPercent(latest.gpu_util_pct)}</td>
                  <td className="w-1/2 px-2">
                    <div style={{ height: '2px', background: 'var(--border-color)', width: '100%' }}>
                      <div style={{ height: '100%', width: `${Math.min(100, Math.max(0, latest.gpu_util_pct))}%`, background: 'var(--text-secondary)' }} />
                    </div>
                  </td>
                </tr>
              )}
              {node.capabilities.has_load && !node.capabilities.has_gpu && (
                <tr>
                  <td className="text-muted uppercase" style={{fontSize: '0.75rem'}}>Load</td>
                  <td className="mono text-right">{latest.load1?.toFixed(2) ?? 'N/A'}</td>
                  <td></td>
                </tr>
              )}
            </tbody>
          </table>
        ) : (
          <div className="text-xs text-muted">No telemetry</div>
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

  return (
    <div>
      <div className="grid grid-cols-3 mb-8" style={{ gap: '2rem' }}>
        <div className="flex flex-col gap-1">
          <div className="metric-label">Total Nodes</div>
          <div className="mono" style={{ fontSize: '2.5rem', lineHeight: 1 }}>{nodes.length}</div>
        </div>
        <div className="flex flex-col gap-1">
          <div className="metric-label">Online</div>
          <div className="mono" style={{ fontSize: '2.5rem', lineHeight: 1 }}>{onlineNodes}</div>
        </div>
        <div className="flex flex-col gap-1">
          <div className="metric-label">Stale / Offline</div>
          <div className="mono" style={{ fontSize: '2.5rem', lineHeight: 1, color: offlineNodes > 0 ? 'var(--color-stale)' : 'inherit' }}>{offlineNodes}</div>
        </div>
      </div>

      <div className="section-divider">
        <h2 className="section-title">Node Fleet</h2>
      </div>
      <div className="grid grid-cols-3">
        {nodes.map(node => (
          <NodeCard key={node.node_id} node={node} />
        ))}
      </div>

      <div style={{ marginTop: '2rem' }}>
        <div className="section-divider">
          <h2 className="section-title">Recent Alerts</h2>
        </div>
        <table className="hairline-table text-sm w-full">
          <thead>
            <tr>
              <th className="text-left text-muted font-normal pb-2" style={{width: '150px'}}>Time</th>
              <th className="text-left text-muted font-normal pb-2" style={{width: '150px'}}>Node</th>
              <th className="text-left text-muted font-normal pb-2">Event</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={3} className="text-center text-muted py-8" style={{ borderBottom: 'none' }}>No recent alerts.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
