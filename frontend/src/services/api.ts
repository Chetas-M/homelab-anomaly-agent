import axios from 'axios';
import type { NodeOverview, MetricRecord, DataQuality, AnomalyScoreRecord } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002';

const api = axios.create({
  baseURL: API_BASE_URL,
});

export const getNodes = async (): Promise<NodeOverview[]> => {
  const { data } = await api.get<NodeOverview[]>('/api/nodes');
  return data;
};

export const getNode = async (nodeId: string): Promise<NodeOverview> => {
  const { data } = await api.get<NodeOverview>(`/api/nodes/${nodeId}`);
  return data;
};

export const getNodeAlert = async (nodeId: string, threshold: number = 3): Promise<import('../types').NodeAlertState> => {
  const { data } = await api.get<import('../types').NodeAlertState>(`/api/nodes/${nodeId}/alert`, {
    params: { threshold }
  });
  return data;
};

export const getLatestMetrics = async (nodeId: string): Promise<MetricRecord> => {
  const { data } = await api.get<MetricRecord>(`/api/nodes/${nodeId}/latest`);
  return data;
};

export const getMetricsHistory = async (nodeId: string, start?: string, end?: string, limit?: number): Promise<MetricRecord[]> => {
  const params: Record<string, string | number> = {};
  if (start) params.start = start;
  if (end) params.end = end;
  if (limit) params.limit = limit;
  
  const { data } = await api.get<MetricRecord[]>(`/api/nodes/${nodeId}/metrics`, { params });
  return data;
};

export const getNodeScores = async (nodeId: string, limit: number = 100): Promise<AnomalyScoreRecord[]> => {
  const { data } = await api.get<AnomalyScoreRecord[]>(`/api/nodes/${nodeId}/scores`, {
    params: { limit }
  });
  return data;
};

export const getDataQuality = async (nodeId: string, windowHours: number = 24): Promise<DataQuality> => {
  const { data } = await api.get<DataQuality>(`/api/nodes/${nodeId}/quality`, {
    params: { window_hours: windowHours }
  });
  return data;
};

export const getNodeAttributions = async (nodeId: string): Promise<import('../types').NodeAttributionResponse> => {
  const { data } = await api.get<import('../types').NodeAttributionResponse>(`/api/nodes/${nodeId}/attributions`);
  return data;
};

export const getSimulationStatus = async (): Promise<import('../types').SimulationStatusResponse> => {
  const { data } = await api.get<import('../types').SimulationStatusResponse>('/api/simulation/status');
  return data;
};

export const startSimulation = async (
  scenario: string,
  durationSeconds: number = 120
): Promise<import('../types').SimulationStatusResponse> => {
  const { data } = await api.post<import('../types').SimulationStatusResponse>('/api/simulation/start', {
    scenario,
    duration_seconds: durationSeconds
  });
  return data;
};

export const stopSimulation = async (): Promise<import('../types').SimulationStatusResponse> => {
  const { data } = await api.post<import('../types').SimulationStatusResponse>('/api/simulation/stop');
  return data;
};

export const getSimulationMetrics = async (): Promise<import('../types').SimulationMetricRecord[]> => {
  const { data } = await api.get<import('../types').SimulationMetricRecord[]>('/api/simulation/metrics');
  return data;
};
