import { useCallback, useEffect, useState } from 'react';

export type Async<T> =
  | { status: 'loading' }
  | { status: 'error'; error: unknown }
  | { status: 'ready'; value: T };

/**
 * Runs a fetch and keeps its result. Small on purpose: the app has a handful
 * of screens, each loading one thing, and a cache would be more machinery
 * than that needs.
 *
 * `run` must be memoised with `useCallback` — its identity is what says the
 * request has changed. `reload` re-runs it, for after a bill is added or a
 * question is answered; the old value stays on screen until the new one
 * arrives, so answering a question doesn't blank the report.
 */
export function useAsync<T>(run: () => Promise<T>): Async<T> & { reload: () => void } {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ ran: () => Promise<T>; state: Async<T> } | null>(null);

  useEffect(() => {
    let cancelled = false;
    run().then(
      (value) => {
        if (!cancelled) setResult({ ran: run, state: { status: 'ready', value } });
      },
      (error: unknown) => {
        if (!cancelled) setResult({ ran: run, state: { status: 'error', error } });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [run, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  // A result belongs to the request that produced it. Once `run` changes, the
  // screen is loading again even though the old result is still in state.
  const state: Async<T> = result?.ran === run ? result.state : { status: 'loading' };
  return { ...state, reload };
}
