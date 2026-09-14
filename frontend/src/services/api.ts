import axios from 'axios';
import type { NodeOverview, MetricRecord, DataQuality } from '../types';

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

export const getLatestMetrics = async (nodeId: string): Promise<MetricRecord> => {
  const { data } = await api.get<MetricRecord>(`/api/nodes/${nodeId}/latest`);
  return data;
};

export const getMetricsHistory = async (nodeId: string, start?: string, end?: string): Promise<MetricRecord[]> => {
  const params: Record<string, string> = {};
  if (start) params.start = start;
  if (end) params.end = end;
  
  const { data } = await api.get<MetricRecord[]>(`/api/nodes/${nodeId}/metrics`, { params });
  return data;
};

export const getDataQuality = async (nodeId: string, windowHours: number = 24): Promise<DataQuality> => {
  const { data } = await api.get<DataQuality>(`/api/nodes/${nodeId}/quality`, {
    params: { window_hours: windowHours }
  });
  return data;
};
