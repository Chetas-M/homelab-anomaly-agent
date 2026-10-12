const DISPLAY_NAMES: Record<string, string> = {
  'alpha': 'Alpha',
  'alpha-win': 'Alpha',
  'beta': 'Beta',
  'beta-srv': 'Beta',
  'gamma': 'Gamma',
  'gamma-srv': 'Gamma',
  'gamma-server': 'Gamma',
};

export const getDisplayName = (nodeId: string): string => {
  return DISPLAY_NAMES[nodeId] || nodeId;
};
