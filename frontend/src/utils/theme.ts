export const STATUS_COLORS = {
  healthy: 'var(--color-success)',
  stale: 'var(--color-stale)',
  anomaly: 'var(--color-anomaly)',
};

const NODE_COLORS = [
  '#3b82f6', // blue
  '#8b5cf6', // purple
  '#ec4899', // pink
  '#14b8a6', // teal
  '#f59e0b', // amber
  '#6366f1', // indigo
];

export const getNodeIdentityColor = (nodeId: string): string => {
  let hash = 0;
  for (let i = 0; i < nodeId.length; i++) {
    hash = nodeId.charCodeAt(i) + ((hash << 5) - hash);
  }
  const index = Math.abs(hash) % NODE_COLORS.length;
  return NODE_COLORS[index];
};
