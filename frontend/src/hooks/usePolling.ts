import { useEffect, useRef, useState, useCallback } from 'react';

type FetchFunction<T> = () => Promise<T>;

export function usePolling<T>(
  fetchFn: FetchFunction<T>,
  intervalMs: number = 30000,
  startImmediately: boolean = true
) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(startImmediately);
  const [error, setError] = useState<Error | null>(null);
  
  const fetchFnRef = useRef(fetchFn);
  useEffect(() => {
    fetchFnRef.current = fetchFn;
  }, [fetchFn]);

  const dataRef = useRef(data);
  useEffect(() => {
    dataRef.current = data;
  }, [data]);

  const mountedRef = useRef(false);
  const timerRef = useRef<number | null>(null);

  const execute = useCallback(async () => {
    if (!mountedRef.current) return;
    
    try {
      // Don't set loading true for background polls to avoid UI flicker
      if (dataRef.current === null) {
        setLoading(true);
      }
      const result = await fetchFnRef.current();
      if (mountedRef.current) {
        setData(result);
        setError(null);
      }
    } catch (err: any) {
      if (mountedRef.current) {
        setError(err);
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    
    if (startImmediately) {
      execute();
    }

    timerRef.current = window.setInterval(() => {
      execute();
    }, intervalMs);

    return () => {
      mountedRef.current = false;
      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current);
      }
    };
  }, [execute, intervalMs, startImmediately]);

  return { data, loading, error, refetch: execute };
}
