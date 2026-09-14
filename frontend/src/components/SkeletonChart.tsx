import React from 'react';

export const SkeletonChart: React.FC = () => {
  return (
    <div className="skeleton-chart">
      {/* Fake Y-axis lines */}
      <div style={{ position: 'absolute', left: '4%', right: '4%', top: '20%', borderTop: '1px dashed var(--border-color)', opacity: 0.5 }}></div>
      <div style={{ position: 'absolute', left: '4%', right: '4%', top: '50%', borderTop: '1px dashed var(--border-color)', opacity: 0.5 }}></div>
      <div style={{ position: 'absolute', left: '4%', right: '4%', top: '80%', borderTop: '1px dashed var(--border-color)', opacity: 0.5 }}></div>
      
      <span className="text-muted" style={{ zIndex: 1, backgroundColor: 'var(--bg-card)', padding: '0.5rem 1rem' }}>
        Chart will populate here
      </span>
    </div>
  );
};
