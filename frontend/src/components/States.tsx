import React from 'react';
import { AlertCircle, Loader } from 'lucide-react';

export const LoadingState: React.FC<{ message?: string }> = ({ message = 'Loading...' }) => (
  <div className="card flex items-center justify-center gap-2" style={{ padding: '3rem' }}>
    <Loader className="text-muted" style={{ animation: 'spin 2s linear infinite' }} />
    <span className="text-muted">{message}</span>
  </div>
);

export const ErrorState: React.FC<{ error: Error | null; onRetry?: () => void }> = ({ error, onRetry }) => (
  <div className="card" style={{ borderColor: 'var(--border-color)' }}>
    <div className="flex items-center gap-2 mb-4" style={{ color: 'var(--color-stale)' }}>
      <AlertCircle />
      <strong>Error loading data</strong>
    </div>
    <div className="text-sm text-muted mb-4 mono">
      {error?.message || 'Unknown error occurred'}
    </div>
    {onRetry && (
      <button onClick={onRetry} className="btn">
        Retry Request
      </button>
    )}
  </div>
);

export const EmptyState: React.FC<{ message?: string }> = ({ message = 'No data available' }) => (
  <div className="card flex items-center justify-center" style={{ padding: '3rem' }}>
    <span className="text-muted">{message}</span>
  </div>
);
