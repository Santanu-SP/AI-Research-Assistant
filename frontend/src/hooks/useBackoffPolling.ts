import { useEffect, useRef, useState } from 'react';

export const POLL_INITIAL_DELAY_MS = 2000;
export const POLL_MAX_DELAY_MS = 30000;
export const POLL_GIVE_UP_AFTER_MS = 15 * 60 * 1000;

/** Delay before poll number `attempt` (0-based): 2s, 4s, 8s, 16s, then 30s. */
export function nextPollDelay(
  attempt: number,
  initialDelayMs = POLL_INITIAL_DELAY_MS,
  maxDelayMs = POLL_MAX_DELAY_MS,
): number {
  return Math.min(maxDelayMs, initialDelayMs * 2 ** Math.max(0, attempt));
}

export interface BackoffPollingOptions {
  initialDelayMs?: number;
  maxDelayMs?: number;
  giveUpAfterMs?: number;
}

/**
 * Calls `poll` while `active` is true, waiting longer between calls each time.
 * Polling starts over when `resetKey` changes (for example when a different
 * set of documents is being processed) and stops for good once `giveUpAfterMs`
 * has passed, so a stuck job cannot keep a tab polling forever.
 */
export function useBackoffPolling(
  active: boolean,
  poll: () => Promise<unknown> | void,
  resetKey: string = '',
  options: BackoffPollingOptions = {},
): { timedOut: boolean } {
  const {
    initialDelayMs = POLL_INITIAL_DELAY_MS,
    maxDelayMs = POLL_MAX_DELAY_MS,
    giveUpAfterMs = POLL_GIVE_UP_AFTER_MS,
  } = options;
  const pollRef = useRef(poll);
  const [timedOutKey, setTimedOutKey] = useState<string | null>(null);

  useEffect(() => {
    pollRef.current = poll;
  }, [poll]);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    let timer: number | undefined;
    let attempt = 0;
    const startedAt = Date.now();

    const schedule = () => {
      const delay = nextPollDelay(attempt, initialDelayMs, maxDelayMs);
      if (Date.now() + delay - startedAt > giveUpAfterMs) {
        setTimedOutKey(resetKey);
        return;
      }
      timer = window.setTimeout(async () => {
        if (cancelled) return;
        attempt += 1;
        try {
          await pollRef.current();
        } catch {
          // A failed poll keeps the last good data on screen; the next poll retries.
        }
        if (!cancelled) schedule();
      }, delay);
    };

    schedule();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [active, resetKey, initialDelayMs, maxDelayMs, giveUpAfterMs]);

  return { timedOut: active && timedOutKey === resetKey };
}

/** Stable key for the documents that are still being ingested. */
export function activeIngestionKey(
  documents: ReadonlyArray<{ id: string; status: string }>,
): string {
  return documents
    .filter((d) => d.status === 'uploaded' || d.status === 'processing')
    .map((d) => d.id)
    .sort()
    .join(',');
}
