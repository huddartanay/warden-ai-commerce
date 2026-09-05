import { useEffect, useState } from "react";

/**
 * Poll `fn` every `intervalMs`. Returns `[data, error, refresh]`.
 * `fn` is expected to be stable (wrap in useCallback if it isn't).
 * Stops polling automatically on unmount.
 */
export function usePolling<T>(
  fn: () => Promise<T>,
  intervalMs: number,
  deps: React.DependencyList = [],
): { data: T | null; error: Error | null; refresh: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const value = await fn();
        if (!cancelled) {
          setData(value);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e : new Error(String(e)));
        }
      }
    };
    run();
    const id = window.setInterval(run, intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, tick, ...deps]);

  return { data, error, refresh: () => setTick((t) => t + 1) };
}
