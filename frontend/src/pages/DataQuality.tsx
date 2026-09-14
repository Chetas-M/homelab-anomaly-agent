
import { useParams, Link } from 'react-router-dom';
import { ChevronLeft, ShieldCheck, ShieldAlert, AlertTriangle } from 'lucide-react';
import { getDataQuality } from '../services/api';
import { useApi } from '../hooks/useApi';
import { getDisplayName } from '../utils/displayNames';
import { LoadingState, ErrorState, EmptyState } from '../components/States';

export default function DataQuality() {
  const { nodeId } = useParams<{ nodeId: string }>();
  const { data: quality, loading, error } = useApi(() => getDataQuality(nodeId!), [nodeId]);

  if (loading) return <LoadingState message="Analyzing data quality..." />;
  if (error) return <ErrorState error={error} />;
  if (!quality) return <EmptyState message="No data quality report available." />;

  const isHealthy = quality.coverage_pct > 95;

  return (
    <div>
      <div className="mb-4">
        <Link to={`/node/${nodeId}`} className="btn mb-4" style={{ background: 'transparent' }}>
          <ChevronLeft size={16} /> Back to Node
        </Link>
      </div>

      <div className="header">
        <div>
          <h1 className="flex items-center gap-2">
            {isHealthy ? <ShieldCheck className="text-success" /> : <ShieldAlert className="text-warning" />}
            Data Quality Report
          </h1>
          <div className="text-sm text-muted mt-2">
            Node: <strong>{getDisplayName(quality.node_id)}</strong> • Window: Last {quality.window_hours} hours
          </div>
        </div>
      </div>

      <div className="grid grid-cols-4 mb-8">
        <div className="card">
          <div className="metric-label">Actual Samples</div>
          <div className="metric-value mono text-info">{quality.actual_samples}</div>
          <div className="text-xs text-muted mt-2">Expected: {quality.expected_samples}</div>
        </div>
        <div className="card">
          <div className="metric-label">Coverage</div>
          <div className={`metric-value mono ${quality.coverage_pct < 100 ? 'text-warning' : 'text-success'}`}>
            {quality.coverage_pct.toFixed(2)}%
          </div>
          <div className="text-xs text-muted mt-2">Time covered by telemetry</div>
        </div>
        <div className="card">
          <div className="metric-label">Largest Gap</div>
          <div className={`metric-value mono ${quality.largest_gap_seconds > 60 ? 'text-error' : 'text-success'}`}>
            {quality.largest_gap_seconds.toFixed(1)}s
          </div>
          <div className="text-xs text-muted mt-2">Max time between samples</div>
        </div>
        <div className="card">
          <div className="metric-label">Gaps &gt; 60s</div>
          <div className={`metric-value mono ${quality.gaps_over_60s > 0 ? 'text-error' : 'text-success'}`}>
            {quality.gaps_over_60s}
          </div>
          <div className="text-xs text-muted mt-2">Missing data incidents</div>
        </div>
      </div>

      <div className="card mb-8">
        <div className="flex items-start gap-4 mb-4 p-4" style={{ background: 'rgba(59, 130, 246, 0.1)', borderRadius: '4px', border: '1px solid var(--color-info)' }}>
          <AlertTriangle className="text-info" />
          <div className="text-sm text-primary">
            <strong className="block mb-1">Structural NULLs vs. Missing Telemetry</strong>
            100% NULL values for specific metrics (e.g., Load on Windows, GPU on non-GPU nodes) indicate <em>Structurally Unavailable</em> metrics, not collection failures. Missing telemetry is measured by gaps in time, not column nullability.
          </div>
        </div>

        <h3 className="mb-4">Per-Metric NULL Analysis</h3>
        <div className="grid grid-cols-3">
          {Object.entries(quality.metrics_quality).map(([metric, info]) => {
            const isStructural = info.null_pct === 100;
            const isPartial = info.null_pct > 0 && info.null_pct < 100;
            
            return (
              <div key={metric} className="flex justify-between items-center" style={{ padding: '0.75rem', borderBottom: '1px solid var(--border-light)' }}>
                <span className="mono text-sm">{metric}</span>
                <span className={`mono text-sm ${isStructural ? 'text-muted' : isPartial ? 'text-warning' : 'text-success'}`}>
                  {info.null_pct.toFixed(1)}%
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
