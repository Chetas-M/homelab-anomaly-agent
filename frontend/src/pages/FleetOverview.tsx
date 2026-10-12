import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { getNodes, getLatestMetrics, getSimulationStatus, startSimulation, stopSimulation, getSimulationMetrics } from '../services/api';
import { useApi } from '../hooks/useApi';
import { usePolling } from '../hooks/usePolling';
import { getDisplayName } from '../utils/displayNames';
import { formatPercent, formatDateTime } from '../utils/formatters';
import { getNodeIdentityColor } from '../utils/theme';
import { LoadingState, ErrorState, EmptyState } from '../components/States';
import type { NodeOverview, MetricRecord, SimulationStatusResponse, SimulationMetricRecord } from '../types';
import { Server, AlertTriangle, ShieldCheck, ShieldAlert, Play, Square, RefreshCw, Zap } from 'lucide-react';

const NodeCard: React.FC<{ node: NodeOverview }> = ({ node }) => {
  const { data: latest, loading, error } = usePolling<MetricRecord>(() => getLatestMetrics(node.node_id), 15000);

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
          <table className="hairline-table text-xs w-full" style={{ marginTop: 'auto' }}>
            <tbody>
              <tr>
                <td className="text-muted uppercase" style={{width: '60px', fontSize: '0.75rem'}}>CPU</td>
                <td className="mono text-right">{formatPercent(latest.cpu_pct)}</td>
                <td className="px-2" style={{width: '50%'}}>
                  <div style={{height: '4px', background: 'var(--border-color)', borderRadius: '2px', overflow: 'hidden'}}>
                    <div style={{
                      height: '100%', 
                      width: `${Math.min(100, Math.max(0, latest.cpu_pct ?? 0))}%`, 
                      background: 'var(--color-accent)'
                    }}></div>
                  </div>
                </td>
              </tr>
              <tr>
                <td className="text-muted uppercase" style={{fontSize: '0.75rem'}}>Mem</td>
                <td className="mono text-right">{formatPercent(latest.mem_pct)}</td>
                <td className="px-2">
                  <div style={{height: '4px', background: 'var(--border-color)', borderRadius: '2px', overflow: 'hidden'}}>
                    <div style={{
                      height: '100%', 
                      width: `${Math.min(100, Math.max(0, latest.mem_pct ?? 0))}%`, 
                      background: 'var(--color-accent)'
                    }}></div>
                  </div>
                </td>
              </tr>
              <tr>
                <td className="text-muted uppercase" style={{fontSize: '0.75rem'}}>Disk</td>
                <td className="mono text-right">{formatPercent(latest.disk_used_pct)}</td>
                <td className="px-2">
                  <div style={{height: '4px', background: 'var(--border-color)', borderRadius: '2px', overflow: 'hidden'}}>
                    <div style={{
                      height: '100%', 
                      width: `${Math.min(100, Math.max(0, latest.disk_used_pct ?? 0))}%`, 
                      background: 'var(--color-accent)'
                    }}></div>
                  </div>
                </td>
              </tr>
              {node.capabilities.has_gpu && (
                <tr>
                  <td className="text-muted uppercase" style={{fontSize: '0.75rem'}}>GPU</td>
                  <td className="mono text-right">{formatPercent(latest.gpu_util_pct)}</td>
                  <td className="px-2 text-xs text-muted mono text-right">
                    VRAM: {formatPercent(latest.gpu_vram_pct)}
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
  const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date());
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);
  const isFetchingRef = useRef<boolean>(false);

  // Simulation state
  const [simStatus, setSimStatus] = useState<SimulationStatusResponse | null>(null);
  const [simMetrics, setSimMetrics] = useState<SimulationMetricRecord[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<string>('cpu_spike');
  const [selectedDuration, setSelectedDuration] = useState<number>(120);
  const [simLoading, setSimLoading] = useState<boolean>(false);

  // Refresh Fleet Overview periodically
  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(async () => {
      if (isFetchingRef.current) return;
      isFetchingRef.current = true;
      try {
        await refetch();
        setLastRefreshed(new Date());
      } finally {
        isFetchingRef.current = false;
      }
    }, 15000);
    return () => clearInterval(interval);
  }, [autoRefresh, refetch]);

  // Poll simulation status & metrics when active
  useEffect(() => {
    let active = true;
    const checkSim = async () => {
      try {
        const status = await getSimulationStatus();
        if (!active) return;
        setSimStatus(status);
        if (status.is_active) {
          const metrics = await getSimulationMetrics();
          if (active) setSimMetrics(metrics);
        } else {
          setSimMetrics([]);
        }
      } catch (err) {
        console.error('Failed to poll simulation status', err);
      }
    };

    checkSim();
    const interval = setInterval(checkSim, 5000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  const handleStartSimulation = async () => {
    setSimLoading(true);
    try {
      const res = await startSimulation(selectedScenario, selectedDuration);
      setSimStatus(res);
      const metrics = await getSimulationMetrics();
      setSimMetrics(metrics);
    } catch (err) {
      alert(`Simulation failed to start: ${err}`);
    } finally {
      setSimLoading(false);
    }
  };

  const handleStopSimulation = async () => {
    setSimLoading(true);
    try {
      const res = await stopSimulation();
      setSimStatus(res);
      setSimMetrics([]);
    } catch (err) {
      alert(`Simulation failed to stop: ${err}`);
    } finally {
      setSimLoading(false);
    }
  };

  if (loading && !nodes) return <LoadingState message="Loading fleet overview..." />;
  if (error) return <ErrorState error={error} onRetry={refetch} />;
  if (!nodes || nodes.length === 0) return <EmptyState message="No nodes discovered in the fleet." />;

  const onlineNodes = nodes.filter(n => n.online).length;
  const offlineNodes = nodes.length - onlineNodes;
  const anomalousNodes = nodes.filter(n => n.latest_is_anomalous === true);
  const latestSimSample = simMetrics.length > 0 ? simMetrics[simMetrics.length - 1] : null;

  return (
    <div>
      {/* Top Controls Bar */}
      <div className="flex justify-between items-center mb-6 p-3 card" style={{ padding: '0.75rem 1rem' }}>
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5 text-xs font-semibold" style={{ color: 'var(--color-success)' }}>
            <span className="status-dot online"></span> Live Pipeline Active
          </span>
          <span className="text-xs text-muted mono">
            Cadence: ~30s edge collector • Auto-poll: 15s
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted mono">
            Last Updated: {lastRefreshed.toLocaleTimeString()}
          </span>
          <label className="flex items-center gap-1.5 text-xs text-muted cursor-pointer" style={{ userSelect: 'none' }}>
            <input 
              type="checkbox" 
              checked={autoRefresh} 
              onChange={e => setAutoRefresh(e.target.checked)} 
            />
            Auto-refresh
          </label>
          <button 
            className="btn text-xs py-1 px-2.5 flex items-center gap-1"
            onClick={() => { refetch(); setLastRefreshed(new Date()); }}
          >
            <RefreshCw size={12} /> Refresh
          </button>
        </div>
      </div>

      {/* Summary KPI Cards */}
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

      {/* Priority 4: Controlled Anomaly Simulation Card */}
      <div className="card mb-8" style={{ 
        border: simStatus?.is_active ? '1px solid #a855f7' : '1px solid var(--border-color)',
        backgroundColor: simStatus?.is_active ? 'rgba(168, 85, 247, 0.04)' : 'inherit',
        position: 'relative',
        overflow: 'hidden'
      }}>
        <div className="flex justify-between items-center mb-3">
          <div className="flex items-center gap-2">
            <Zap size={18} style={{ color: '#a855f7' }} />
            <span style={{ fontSize: '1.125rem', fontWeight: 600 }}>Controlled Demo Simulation</span>
            <span style={{
              fontSize: '0.65rem',
              fontWeight: 700,
              padding: '2px 8px',
              borderRadius: '999px',
              backgroundColor: simStatus?.is_active ? '#a855f7' : 'rgba(168, 85, 247, 0.15)',
              color: simStatus?.is_active ? '#ffffff' : '#c084fc',
              letterSpacing: '0.05em'
            }}>
              [SIMULATED - DEMO MODE]
            </span>
          </div>

          <div className="flex items-center gap-3">
            {simStatus?.is_active ? (
              <div className="flex items-center gap-2">
                <span className="mono text-xs font-semibold" style={{ color: '#c084fc' }}>
                  Auto-expires in: {simStatus.remaining_seconds}s
                </span>
                <button 
                  className="btn text-xs py-1.5 px-3 flex items-center gap-1.5"
                  style={{ backgroundColor: 'var(--color-error)', color: '#ffffff', borderColor: 'var(--color-error)' }}
                  onClick={handleStopSimulation}
                  disabled={simLoading}
                >
                  <Square size={13} /> Stop Simulation
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <select 
                  className="btn text-xs py-1 px-2 mono"
                  value={selectedScenario}
                  onChange={e => setSelectedScenario(e.target.value)}
                  style={{ backgroundColor: 'var(--card-bg)', color: 'var(--text-primary)' }}
                >
                  <option value="cpu_spike">CPU & System Load Spike (92%)</option>
                  <option value="network_spike">Network Ingress Saturation (16.5 MB/s)</option>
                  <option value="disk_spike">Disk Write I/O Burst (82 MB/s)</option>
                </select>
                <select 
                  className="btn text-xs py-1 px-2 mono"
                  value={selectedDuration}
                  onChange={e => setSelectedDuration(Number(e.target.value))}
                  style={{ backgroundColor: 'var(--card-bg)', color: 'var(--text-primary)' }}
                >
                  <option value={60}>60s duration</option>
                  <option value={120}>120s duration</option>
                  <option value={300}>300s duration</option>
                </select>
                <button 
                  className="btn text-xs py-1.5 px-3 flex items-center gap-1.5"
                  style={{ backgroundColor: '#a855f7', color: '#ffffff', borderColor: '#a855f7' }}
                  onClick={handleStartSimulation}
                  disabled={simLoading}
                >
                  <Play size={13} /> Start Demo
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="text-xs text-muted mb-3">
          Controlled demo simulation exercises the per-metric baseline attribution layer and real-time dashboard updates on an isolated in-memory stream. The frozen Isolation Forest model is not evaluated on simulated streams. Real database telemetry for Alpha, Beta, and Gamma remains 100% unmutated.
        </div>

        {simStatus?.is_active && latestSimSample && (
          <div className="p-3" style={{ 
            backgroundColor: 'rgba(0, 0, 0, 0.25)', 
            borderRadius: '6px', 
            border: '1px solid rgba(168, 85, 247, 0.25)' 
          }}>
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs font-semibold" style={{ color: '#c084fc' }}>
                Active Scenario: {simStatus.scenario_name} (Node: simulated-node)
              </span>
              <div className="flex items-center gap-3">
                <span className="text-xs" style={{ 
                  backgroundColor: 'rgba(234, 179, 8, 0.15)', 
                  color: '#eab308', 
                  padding: '2px 8px', 
                  borderRadius: '4px', 
                  fontWeight: 600 
                }}>
                  SIMULATED SIGNAL — MODEL NOT EVALUATED
                </span>
                <span className="text-xs">
                  Attribution:{' '}
                  <strong style={{ color: latestSimSample.deviation_detected ? 'var(--color-error)' : 'var(--color-success)' }}>
                    {latestSimSample.deviation_detected ? 'DEVIATED' : 'NORMAL'}
                  </strong>
                </span>
              </div>
            </div>

            <div className="grid grid-cols-5 gap-2 text-xs mono pt-1 border-t border-border">
              <div>CPU: <strong>{latestSimSample.cpu_pct.toFixed(1)}%</strong></div>
              <div>Load 1: <strong>{latestSimSample.load1.toFixed(2)}</strong></div>
              <div>Net In: <strong>{(latestSimSample.net_in_bps / (1024 * 1024)).toFixed(2)} MB/s</strong></div>
              <div>Disk Write: <strong>{(latestSimSample.disk_write_bps / (1024 * 1024)).toFixed(2)} MB/s</strong></div>
              <div>Samples: <strong>{simStatus.total_simulated_samples}</strong></div>
            </div>

            {latestSimSample.attributions && latestSimSample.attributions.filter(a => a.status === 'ELEVATED').length > 0 && (
              <div className="mt-2 text-xs pt-1 border-t border-border flex items-center gap-2">
                <span className="text-muted">Triggered Deviations:</span>
                {latestSimSample.attributions.filter(a => a.status === 'ELEVATED').map(a => (
                  <span key={a.metric_key} style={{
                    color: 'var(--color-error)',
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    padding: '1px 6px',
                    borderRadius: '4px',
                    fontWeight: 600
                  }}>
                    {a.display_name}: {a.formatted_val} (+{a.deviation_z}σ)
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Node Fleet Cards */}
      <div className="section-divider">
        <h2 className="section-title">Node Fleet</h2>
      </div>
      <div className="grid grid-cols-3 mb-8">
        {nodes.map(node => (
          <NodeCard key={node.node_id} node={node} />
        ))}
      </div>

      {/* Historical Anomaly Events Table */}
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
