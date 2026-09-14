import React from 'react';

interface MetricCardProps {
  label: string;
  value: string;
  subValue?: string;
  colorClass?: string;
}

export const MetricCard: React.FC<MetricCardProps> = ({ label, value, subValue }) => {
  const isPercent = value.includes('%');
  const numericValue = isPercent ? parseFloat(value) : null;

  return (
    <div style={{ marginBottom: '1rem' }}>
      <div className="metric-label">{label}</div>
      <div className="metric-value mono">{value}</div>
      {subValue && <div className="text-xs text-muted mt-2">{subValue}</div>}
      
      {isPercent && numericValue !== null && !isNaN(numericValue) && (
        <div style={{ height: '2px', background: 'var(--border-color)', marginTop: '8px', width: '100%', borderRadius: '1px' }}>
          <div style={{ height: '100%', width: `${Math.min(100, Math.max(0, numericValue))}%`, background: 'var(--text-secondary)', borderRadius: '1px' }} />
        </div>
      )}
    </div>
  );
};
