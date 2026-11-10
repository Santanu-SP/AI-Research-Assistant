import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  activeIngestionKey,
  nextPollDelay,
  useBackoffPolling,
} from '../hooks/useBackoffPolling';

describe('nextPollDelay', () => {
  it('doubles and caps', () => {
    expect([0, 1, 2, 3, 4, 5, 9].map((n) => nextPollDelay(n, 2000, 30000))).toEqual([
      2000, 4000, 8000, 16000, 30000, 30000, 30000,
    ]);
  });
});

describe('activeIngestionKey', () => {
  it('only includes pending documents, in a stable order', () => {
    expect(
      activeIngestionKey([
        { id: 'b', status: 'processing' },
        { id: 'c', status: 'indexed' },
        { id: 'a', status: 'uploaded' },
        { id: 'd', status: 'failed' },
      ]),
    ).toBe('a,b');
    expect(activeIngestionKey([{ id: 'c', status: 'indexed' }])).toBe('');
  });
});

describe('useBackoffPolling', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  const advance = async (ms: number) => {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms);
    });
  };

  it('backs off between polls and gives up after the limit', async () => {
    const poll = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() =>
      useBackoffPolling(true, poll, 'k', {
        initialDelayMs: 100,
        maxDelayMs: 400,
        giveUpAfterMs: 1000,
      }),
    );

    await advance(99);
    expect(poll).toHaveBeenCalledTimes(0);
    await advance(1); // t=100
    expect(poll).toHaveBeenCalledTimes(1);
    await advance(200); // t=300
    expect(poll).toHaveBeenCalledTimes(2);
    expect(result.current.timedOut).toBe(false);
    await advance(400); // t=700
    expect(poll).toHaveBeenCalledTimes(3);

    // The next poll would land at t=1100, past the 1000 ms budget, so it stops here.
    await advance(5000);
    expect(poll).toHaveBeenCalledTimes(3);
    expect(result.current.timedOut).toBe(true);
  });

  it('does not poll while inactive and keeps going after a failed poll', async () => {
    const poll = vi.fn().mockRejectedValue(new Error('offline'));
    const { rerender } = renderHook(
      ({ active }) => useBackoffPolling(active, poll, 'k', { initialDelayMs: 50, maxDelayMs: 50 }),
      { initialProps: { active: false } },
    );
    await advance(500);
    expect(poll).not.toHaveBeenCalled();

    rerender({ active: true });
    await advance(50);
    await advance(50);
    expect(poll).toHaveBeenCalledTimes(2);

    rerender({ active: false });
    await advance(500);
    expect(poll).toHaveBeenCalledTimes(2);
  });

  it('starts over with a short delay when the reset key changes', async () => {
    const poll = vi.fn().mockResolvedValue(undefined);
    const { rerender } = renderHook(
      ({ resetKey }) =>
        useBackoffPolling(true, poll, resetKey, { initialDelayMs: 100, maxDelayMs: 10_000 }),
      { initialProps: { resetKey: 'a' } },
    );
    await advance(100);
    await advance(200);
    await advance(400); // three polls; next delay would be 800 ms
    expect(poll).toHaveBeenCalledTimes(3);

    rerender({ resetKey: 'a,b' });
    await advance(100);
    expect(poll).toHaveBeenCalledTimes(4);
  });
});
