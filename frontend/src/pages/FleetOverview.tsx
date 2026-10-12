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
import { Server, AlertTriangle, ShieldCheck, ShieldAlert, Play, Square, RefreshCw, Zap, ExternalLink } from 'lucide-react';

const NodeCard: React.FC<{ node: NodeOverview }> = ({ node }) => {
  const { data: latest, loading, error } = usePolling<MetricRecord>(() => getLatestMetrics(node.node_id), 15000);

  // Derive model score and anomaly decision from either polled latest or node overview
  const score = latest?.score ?? node.latest_score;
  const isAnomalous = latest?.is_anomalous ?? node.latest_is_anomalous;
  const isSustained = node.sustained_anomaly === true || node.alert_status === 'SUSTAINED ANOMALY';
  const streakCount = node.streak_count ?? (isAnomalous ? 1 : 0);
  const telemetryTs = latest?.ts || node.last_seen;

  return (
    <Link to={`/node/${node.node_id}`} style={{ color: 'inherit', textDecoration: 'none' }}>
      <div 
        className="card" 
        style={{ 
          transition: 'all 0.2s ease', 
          cursor: 'pointer', 
          height: '100%', 
          display: 'flex', 
          flexDirection: 'column',
          backgroundColor: 'var(--bg-card)'
        }} 
        onMouseOver={e => e.currentTarget.style.borderColor = 'var(--color-accent)'}
        onMouseOut={e => e.currentTarget.style.borderColor = 'var(--border-color)'}
      >
        
        {/* Node Header */}
        <div className="flex justify-between items-center mb-3">
          <div className="flex items-center gap-2">
            <span style={{ 
              width: '10px', height: '10px', borderRadius: '50%', 
              backgroundColor: getNodeIdentityColor(node.node_id) 
            }}></span>
            <Server size={17} className="text-secondary" />
            <span style={{ fontSize: '1.0625rem', fontWeight: 600 }}>{getDisplayName(node.node_id)}</span>
            <span className="mono text-xs text-muted">({node.node_id})</span>
          </div>
          <div>
            {node.online ? (
              <span className="badge badge-success">
                <span className="status-dot online"></span> LIVE
              </span>
            ) : (
              <span className="badge badge-stale">
                <span className="status-dot offline"></span> HISTORICAL / OFFLINE
              </span>
            )}
          </div>
        </div>

        {/* If node is offline, show informative baseline callout */}
        {!node.online && (
          <div className="text-xs text-secondary mb-3 p-2" style={{ 
            background: 'rgba(255, 255, 255, 0.02)', 
            borderRadius: '4px', 
            border: '1px solid var(--border-light)',
            display: 'flex',
            alignItems: 'center',
            gap: '0.35rem'
          }}>
            <span style={{ color: 'var(--color-warning)' }}>⚠️</span>
            <span>Historical baseline preserved. Edge collector inactive.</span>
          </div>
        )}

        {/* Model Classification & Sustained Alert Banner */}
        <div className="flex justify-between items-center mb-3 p-2.5" style={{
          backgroundColor: isSustained 
            ? 'var(--color-error-bg)' 
            : isAnomalous === true 
              ? 'var(--color-warning-bg)' 
              : isAnomalous === false 
                ? 'var(--color-success-bg)' 
                : 'rgba(113, 113, 122, 0.08)',
          border: `1px solid ${
            isSustained 
              ? 'var(--color-error-border)' 
              : isAnomalous === true 
                ? 'var(--color-warning-border)' 
                : isAnomalous === false 
                  ? 'var(--color-success-border)' 
                  : 'var(--border-color)'
          }`,
          borderRadius: '5px'
        }}>
          <div className="flex items-center gap-1.5">
            {isSustained ? (
              <>
                <ShieldAlert size={15} style={{ color: 'var(--color-error)' }} />
                <span style={{ color: '#f87171', fontWeight: 700, fontSize: '0.75rem' }}>SUSTAINED ANOMALY</span>
              </>
            ) : isAnomalous === true ? (
              <>
                <AlertTriangle size={15} style={{ color: 'var(--color-warning)' }} />
                <span style={{ color: '#fbbf24', fontWeight: 600, fontSize: '0.75rem' }}>ANOMALOUS SAMPLE</span>
              </>
            ) : isAnomalous === false ? (
              <>
                <ShieldCheck size={15} style={{ color: 'var(--color-success)' }} />
                <span style={{ color: '#4ade80', fontWeight: 600, fontSize: '0.75rem' }}>NOMINAL / NORMAL</span>
              </>
            ) : (
              <span className="text-muted" style={{ fontSize: '0.75rem' }}>WARMUP / UNSCORED</span>
            )}

            {/* Streak Pips */}
            <div className="streak-pips ml-2" title={`Streak count: ${streakCount}/3`}>
              <span className={`streak-pip ${streakCount >= 1 ? (isSustained ? 'filled-anom' : 'filled-warn') : ''}`}></span>
              <span className={`streak-pip ${streakCount >= 2 ? (isSustained ? 'filled-anom' : 'filled-warn') : ''}`}></span>
              <span className={`streak-pip ${streakCount >= 3 ? 'filled-anom' : ''}`}></span>
            </div>
          </div>

          <div className="mono text-xs text-secondary">
            Score: <strong style={{ color: 'var(--text-primary)' }}>
              {score !== null && score !== undefined ? score.toFixed(4) : 'Warmup'}
            </strong>
          </div>
        </div>
        
        <div className="text-xs text-secondary mb-3 mono flex justify-between items-center">
          <span>Sample: {formatDateTime(telemetryTs)}</span>
          <span className="text-muted font-normal">thr: 0.00</span>
        </div>

        {error ? (
          <div className="text-xs p-3 text-secondary">Failed to poll latest metrics</div>
        ) : loading && !latest ? (
          <div className="text-xs text-muted p-3">Loading telemetry...</div>
        ) : latest ? (
          <table className="hairline-table text-xs w-full" style={{ marginTop: 'auto' }}>
            <tbody>
              <tr>
                <td className="text-secondary font-medium uppercase" style={{ width: '50px' }}>CPU</td>
                <td className="mono text-right font-semibold" style={{ width: '55px' }}>{formatPercent(latest.cpu_pct)}</td>
                <td className="px-2">
                  <div style={{ height: '4px', background: 'var(--border-color)', borderRadius: '2px', overflow: 'hidden' }}>
                    <div style={{
                      height: '100%', 
                      width: `${Math.min(100, Math.max(0, latest.cpu_pct ?? 0))}%`, 
                      background: 'var(--color-accent)'
                    }}></div>
                  </div>
                </td>
              </tr>
              <tr>
                <td className="text-secondary font-medium uppercase">Mem</td>
                <td className="mono text-right font-semibold">{formatPercent(latest.mem_pct)}</td>
                <td className="px-2">
                  <div style={{ height: '4px', background: 'var(--border-color)', borderRadius: '2px', overflow: 'hidden' }}>
                    <div style={{
                      height: '100%', 
                      width: `${Math.min(100, Math.max(0, latest.mem_pct ?? 0))}%`, 
                      background: 'var(--color-accent)'
                    }}></div>
                  </div>
                </td>
              </tr>
              <tr>
                <td className="text-secondary font-medium uppercase">Disk</td>
                <td className="mono text-right font-semibold">{formatPercent(latest.disk_used_pct)}</td>
                <td className="px-2">
                  <div style={{ height: '4px', background: 'var(--border-color)', borderRadius: '2px', overflow: 'hidden' }}>
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
                  <td className="text-secondary font-medium uppercase">GPU</td>
                  <td className="mono text-right font-semibold">{formatPercent(latest.gpu_util_pct)}</td>
                  <td className="px-2 text-xs text-muted mono text-right">
                    VRAM: {formatPercent(latest.gpu_vram_pct)}
                  </td>
                </tr>
              )}
              {node.capabilities.has_load && !node.capabilities.has_gpu && (
                <tr>
                  <td className="text-secondary font-medium uppercase">Load</td>
                  <td className="mono text-right font-semibold">{latest.load1?.toFixed(2) ?? 'N/A'}</td>
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
  const sustainedAlertNodes = nodes.filter(n => n.sustained_anomaly === true || n.alert_status === 'SUSTAINED ANOMALY');
  const latestSimSample = simMetrics.length > 0 ? simMetrics[simMetrics.length - 1] : null;

  return (
    <div>
      {/* Top Controls Bar */}
      <div className="flex justify-between items-center mb-6 p-3 card" style={{ padding: '0.75rem 1rem' }}>
        <div className="flex items-center gap-3">
          <span className="badge badge-success">
            <span className="status-dot online"></span> LIVE PIPELINE ACTIVE
          </span>
          <span className="text-xs text-secondary mono">
            Edge Cadence: ~30s • UI Poll: 15s • Updated: {lastRefreshed.toLocaleTimeString()}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs text-secondary cursor-pointer" style={{ userSelect: 'none' }}>
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
      <div className="grid grid-cols-4 mb-8" style={{ gap: '1.25rem' }}>
        <div className="card">
          <div className="metric-label">Total Fleet Nodes</div>
          <div className="mono font-bold" style={{ fontSize: '2.25rem', lineHeight: 1.2 }}>{nodes.length}</div>
          <div className="text-xs text-secondary mt-2">Alpha, Beta, Gamma</div>
        </div>
        <div className="card">
          <div className="metric-label">Online / Reporting</div>
          <div className="mono font-bold" style={{ fontSize: '2.25rem', lineHeight: 1.2, color: 'var(--color-success)' }}>{onlineNodes}</div>
          <div className="text-xs text-secondary mt-2">Beta, Gamma (heartbeat &lt;120s)</div>
        </div>
        <div className="card">
          <div className="metric-label">Historical / Offline</div>
          <div className="mono font-bold" style={{ fontSize: '2.25rem', lineHeight: 1.2, color: offlineNodes > 0 ? 'var(--color-stale)' : 'inherit' }}>{offlineNodes}</div>
          <div className="text-xs text-secondary mt-2">Alpha (preserved telemetry)</div>
        </div>
        <div className="card">
          <div className="metric-label">Sustained Alerts</div>
          <div className="mono font-bold" style={{ fontSize: '2.25rem', lineHeight: 1.2, color: sustainedAlertNodes.length > 0 ? 'var(--color-error)' : 'var(--color-success)' }}>
            {sustainedAlertNodes.length}
          </div>
          <div className="text-xs text-secondary mt-2">
            Threshold: 3 consecutive anomalies
          </div>
        </div>
      </div>

      {/* Node Fleet Section */}
      <div className="section-divider">
        <div>
          <h2 className="section-title">Operational Node Fleet</h2>
          <span className="section-subtitle">Real telemetry streams and live Isolation Forest scoring</span>
        </div>
      </div>
      <div className="grid grid-cols-3 mb-8">
        {nodes.map(node => (
          <NodeCard key={node.node_id} node={node} />
        ))}
      </div>

      {/* Recent Anomaly Events & Node Status Table */}
      <div style={{ marginTop: '2.5rem' }}>
        <div className="section-divider">
          <div>
            <h2 className="section-title">Fleet Telemetry & Scoring Ledger</h2>
            <span className="section-subtitle">Node health, latest sample timestamps, and consecutive alert streaks</span>
          </div>
        </div>
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: '130px' }}>Node</th>
                  <th style={{ width: '150px' }}>Connection State</th>
                  <th style={{ width: '220px' }}>Latest Sample Time</th>
                  <th style={{ width: '190px' }}>Sample Classification</th>
                  <th style={{ width: '200px' }}>Sustained Alert State</th>
                  <th>Inference Score (Thr: 0.00)</th>
                  <th style={{ width: '100px', textAlign: 'right' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {nodes.map(node => {
                  const isSustained = node.sustained_anomaly === true || node.alert_status === 'SUSTAINED ANOMALY';
                  const streak = node.streak_count ?? (node.latest_is_anomalous ? 1 : 0);
                  return (
                    <tr key={node.node_id}>
                      <td className="font-semibold">
                        <div className="flex items-center gap-1.5">
                          <span style={{ 
                            width: '8px', height: '8px', borderRadius: '50%', 
                            backgroundColor: getNodeIdentityColor(node.node_id) 
                          }}></span>
                          {getDisplayName(node.node_id)}
                        </div>
                      </td>
                      <td>
                        {node.online ? (
                          <span className="badge badge-success">
                            <span className="status-dot online"></span> ONLINE
                          </span>
                        ) : (
                          <span className="badge badge-stale">
                            <span className="status-dot offline"></span> HISTORICAL / OFFLINE
                          </span>
                        )}
                      </td>
                      <td className="mono text-secondary">
                        {formatDateTime(node.last_seen)}
                      </td>
                      <td>
                        {node.latest_is_anomalous === true ? (
                          <span className="badge badge-warning">
                            <AlertTriangle size={12} /> ANOMALOUS SAMPLE
                          </span>
                        ) : node.latest_is_anomalous === false ? (
                          <span className="badge badge-success">
                            <ShieldCheck size={12} /> NORMAL
                          </span>
                        ) : (
                          <span className="badge badge-stale">
                            WARMUP / UNSCORED
                          </span>
                        )}
                      </td>
                      <td>
                        {isSustained ? (
                          <span className="badge badge-error">
                            <ShieldAlert size={12} /> SUSTAINED ({streak}/3)
                          </span>
                        ) : node.latest_is_anomalous === true ? (
                          <span className="badge badge-warning">
                            ACCUMULATING ({streak}/3)
                          </span>
                        ) : node.online ? (
                          <span className="badge badge-outline">
                            STREAK: 0/3 (NOMINAL)
                          </span>
                        ) : (
                          <span className="text-muted text-xs mono">
                            COLLECTOR OFFLINE
                          </span>
                        )}
                      </td>
                      <td className="mono">
                        {node.latest_score !== null && node.latest_score !== undefined ? (
                          <strong style={{ color: node.latest_is_anomalous ? 'var(--color-warning)' : 'var(--text-primary)' }}>
                            {node.latest_score.toFixed(4)}
                          </strong>
                        ) : (
                          <span className="text-muted">N/A</span>
                        )}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <Link to={`/node/${node.node_id}`} className="btn text-xs py-1 px-2">
                          View <ExternalLink size={11} />
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Auxiliary Tool: Controlled Demo Simulation Card */}
      <div style={{ marginTop: '3rem' }}>
        <div className="section-divider">
          <div>
            <h2 className="section-title text-secondary flex items-center gap-2">
              <Zap size={16} style={{ color: '#c084fc' }} /> 
              Synthetic Anomaly Signal Generator
              <span className="badge badge-purple" style={{ fontSize: '0.625rem' }}>AUXILIARY DEMO TOOL</span>
            </h2>
            <span className="section-subtitle">
              In-memory evaluation stream for baseline metric attribution demo. Does not mutate database or affect production models.
            </span>
          </div>
        </div>

        <div className="card" style={{ 
          border: simStatus?.is_active ? '1px solid #a855f7' : '1px dashed rgba(168, 85, 247, 0.35)',
          backgroundColor: simStatus?.is_active ? 'rgba(168, 85, 247, 0.04)' : 'rgba(20, 20, 24, 0.6)',
          position: 'relative'
        }}>
          <div className="flex justify-between items-center mb-3">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold mono" style={{ color: '#c084fc' }}>
                DEMO SIMULATION CONTROLLER
              </span>
              <span className="badge badge-outline" style={{ fontSize: '0.625rem' }}>
                ISOLATED STREAM
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
                    style={{ backgroundColor: 'var(--bg-secondary)', color: 'var(--text-primary)' }}
                  >
                    <option value="cpu_spike">Scenario: CPU & Load Spike (92%)</option>
                    <option value="network_spike">Scenario: Network Ingress Saturation (16.5 MB/s)</option>
                    <option value="disk_spike">Scenario: Disk Write Burst (82 MB/s)</option>
                  </select>
                  <select 
                    className="btn text-xs py-1 px-2 mono"
                    value={selectedDuration}
                    onChange={e => setSelectedDuration(Number(e.target.value))}
                    style={{ backgroundColor: 'var(--bg-secondary)', color: 'var(--text-primary)' }}
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

          <div className="text-xs text-secondary mb-3">
            Controlled demo simulation exercises the per-metric baseline attribution layer and real-time dashboard updates on an isolated in-memory stream. The frozen Isolation Forest model is not evaluated on simulated streams. Real database telemetry for Alpha, Beta, and Gamma remains 100% unmutated.
          </div>

          {simStatus?.is_active && latestSimSample && (
            <div className="p-3" style={{ 
              backgroundColor: 'rgba(0, 0, 0, 0.35)', 
              borderRadius: '6px', 
              border: '1px solid rgba(168, 85, 247, 0.3)' 
            }}>
              <div className="flex justify-between items-center mb-2">
                <span className="text-xs font-semibold" style={{ color: '#c084fc' }}>
                  Active Scenario: {simStatus.scenario_name} (Node: simulated-node)
                </span>
                <div className="flex items-center gap-3">
                  <span className="badge badge-warning">
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
                  <span className="text-secondary">Triggered Deviations:</span>
                  {latestSimSample.attributions.filter(a => a.status === 'ELEVATED').map(a => (
                    <span key={a.metric_key} className="badge badge-error">
                      {a.display_name}: {a.formatted_val} (+{a.deviation_z}σ)
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
