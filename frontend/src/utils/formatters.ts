import { format, parseISO } from 'date-fns';

export const formatBytesPerSec = (bytes: number | null | undefined): string => {
  if (bytes === null || bytes === undefined) return 'N/A';
  if (bytes === 0) return '0 B/s';
  const k = 1024;
  const sizes = ['B/s', 'KB/s', 'MB/s', 'GB/s', 'TB/s'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

export const formatPercent = (val: number | null | undefined): string => {
  if (val === null || val === undefined) return 'N/A';
  return val.toFixed(1) + '%';
};

export const formatTemp = (val: number | null | undefined): string => {
  if (val === null || val === undefined) return 'N/A';
  return val.toFixed(1) + '°C';
};

export const formatNumber = (val: number | null | undefined): string => {
  if (val === null || val === undefined) return 'N/A';
  return val.toFixed(2);
};

export const formatTime = (ts: string | null): string => {
  if (!ts) return 'Never';
  return format(parseISO(ts), 'HH:mm:ss');
};

export const formatDateTime = (ts: string | null): string => {
  if (!ts) return 'Never';
  return format(parseISO(ts), 'yyyy-MM-dd HH:mm:ss');
};
