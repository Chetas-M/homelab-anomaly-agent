const DISPLAY_NAMES: Record<string, string> = {
  'alpha': 'Alpha',
  'beta': 'Beta',
  'gamma-server': 'Gamma',
};

export const getDisplayName = (nodeId: string): string => {
  return DISPLAY_NAMES[nodeId] || nodeId;
};
