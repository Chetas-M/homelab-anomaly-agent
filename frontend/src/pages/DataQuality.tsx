import { useParams, Link } from 'react-router-dom';
import { ChevronLeft, Info } from 'lucide-react';
import { getDataQuality } from '../services/api';
import { useApi } from '../hooks/useApi';
import { getDisplayName } from '../utils/displayNames';
import { LoadingState, ErrorState, EmptyState } from '../components/States';

export default function DataQuality() {
  const { nodeId } = useParams<{ nodeId: string }>();
  const { data: quality, loading, error, refetch } = useApi(() => getDataQuality(nodeId!), [nodeId]);

  if (loading) return <LoadingState message="Analyzing data quality..." />;
  if (error) return <ErrorState error={error} onRetry={refetch} />;
  if (!quality) return <EmptyState message="No data quality report available." />;

  const isHealthy = quality.coverage_pct >= 95;

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <Link to={`/node/${nodeId}`} className="btn" style={{ background: 'transparent' }}>
          <ChevronLeft size={16} /> Back to Node Details
        </Link>
        <div className="text-xs text-muted mono">
          Audited Window: Last {quality.window_hours} hours
        </div>
      </div>

      <div className="header">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span style={{ fontSize: '1.75rem', fontWeight: 700, letterSpacing: '-0.02em' }}>
              Data Quality & Ingestion Health
            </span>
            <span className="badge badge-outline ml-2">{getDisplayName(quality.node_id)}</span>
            {isHealthy ? (
              <span className="badge badge-success">● INGESTION HEALTHY</span>
            ) : (
              <span className="badge badge-warning">▲ DEGRADED COVERAGE</span>
            )}
          </div>
          <div className="text-xs text-muted">
            Continuous telemetry ingestion integrity audit for node <strong className="text-secondary mono">{quality.node_id}</strong>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="card">
          <div className="metric-label">Actual Telemetry Samples</div>
          <div className="mono font-bold text-2xl text-primary mt-1">{quality.actual_samples}</div>
          <div className="text-xs text-muted mt-2">Expected in window: <span className="mono">{quality.expected_samples}</span></div>
        </div>

        <div className="card">
          <div className="metric-label">Temporal Coverage</div>
          <div className={`mono font-bold text-2xl mt-1 ${quality.coverage_pct < 95 ? 'text-warning' : 'text-success'}`}>
            {quality.coverage_pct.toFixed(2)}%
          </div>
          <div className="text-xs text-muted mt-2">Time covered by recorded samples</div>
        </div>

        <div className="card">
          <div className="metric-label">Largest Telemetry Gap</div>
          <div className={`mono font-bold text-2xl mt-1 ${quality.largest_gap_seconds > 60 ? 'text-error' : 'text-success'}`}>
            {quality.largest_gap_seconds.toFixed(1)}s
          </div>
          <div className="text-xs text-muted mt-2">Target cadence: ~30 seconds</div>
        </div>

        <div className="card">
          <div className="metric-label">Cadence Gaps (&gt; 60s)</div>
          <div className={`mono font-bold text-2xl mt-1 ${quality.gaps_over_60s > 0 ? 'text-warning' : 'text-success'}`}>
            {quality.gaps_over_60s}
          </div>
          <div className="text-xs text-muted mt-2">Potential collector or network pauses</div>
        </div>
      </div>

      {/* Structural NULLs vs Real Gaps Explanation */}
      <div className="card mb-6" style={{ 
        backgroundColor: 'rgba(59, 130, 246, 0.05)', 
        border: '1px solid rgba(59, 130, 246, 0.25)',
        padding: '14px 18px'
      }}>
        <div className="flex items-center gap-2 mb-1">
          <Info size={16} className="text-info" />
          <span className="mono font-bold text-xs text-info tracking-wider">
            METHODOLOGY: STRUCTURAL NULLs VS. DATA DROPS
          </span>
        </div>
        <p className="text-xs text-secondary leading-relaxed">
          In this telemetry architecture, <strong>100% NULL values</strong> for specific metrics indicate <strong>Structurally Unavailable</strong> hardware or OS capabilities (e.g., UNIX Load on Windows systems, NVIDIA GPU metrics on CPU-only nodes, or thermal probes not exposed by virtual machines). Structural NULLs are normal and correctly handled by node-specific feature masks. Telemetry health is measured by <em>time coverage continuity</em>, not by nullability of unsupported sensors.
        </p>
      </div>

      {/* Per-Metric Null Analysis Table */}
      <div className="card">
        <h3 className="text-muted mb-3 flex items-center justify-between">
          <span>Per-Metric Population & Null Rate Analysis</span>
          <span className="text-xs mono text-muted">Audited Metrics: {Object.keys(quality.metrics_quality).length}</span>
        </h3>

        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: '30%' }}>Metric Identifier</th>
                <th style={{ width: '20%' }}>NULL Rate</th>
                <th style={{ width: '30%' }}>Classification</th>
                <th style={{ width: '20%' }}>Pipeline Status</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(quality.metrics_quality).map(([metric, info]) => {
                const isStructural = info.null_pct === 100;
                const isPartial = info.null_pct > 0 && info.null_pct < 100;
                
                return (
                  <tr key={metric}>
                    <td>
                      <span className="mono font-semibold text-primary">{metric}</span>
                    </td>
                    <td>
                      <span className={`mono font-bold ${isStructural ? 'text-muted' : isPartial ? 'text-warning' : 'text-success'}`}>
                        {info.null_pct.toFixed(1)}%
                      </span>
                    </td>
                    <td>
                      {isStructural ? (
                        <span className="badge badge-outline">STRUCTURAL NULL (N/A)</span>
                      ) : isPartial ? (
                        <span className="badge badge-warning">PARTIAL NULL (DROPS)</span>
                      ) : (
                        <span className="badge badge-success">POPULATED (100%)</span>
                      )}
                    </td>
                    <td>
                      <span className="text-xs text-muted">
                        {isStructural ? 'Excluded from feature vector' : isPartial ? 'Imputed via forward-fill' : 'Active feature in model'}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
