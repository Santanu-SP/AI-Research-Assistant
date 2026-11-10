import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiErrorCode, apiErrorMessage, apiRequest, isTimeoutError } from '../services/api';

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

/** A fetch that never resolves until its signal aborts. */
const hangingFetch = () =>
  vi.fn((_url: RequestInfo | URL, init?: RequestInit) =>
    new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () =>
        reject(new DOMException('The operation was aborted.', 'AbortError')),
      );
    }),
  );

describe('apiRequest', () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('times out a request that never answers', async () => {
    vi.stubGlobal('fetch', hangingFetch());
    const error = await apiRequest('/slow', { timeoutMs: 20 }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(isTimeoutError(error)).toBe(true);
    expect(apiErrorMessage(error, 'fallback')).toMatch(/took too long/i);
  });

  it('passes the caller abort through instead of reporting a timeout', async () => {
    vi.stubGlobal('fetch', hangingFetch());
    const controller = new AbortController();
    const pending = apiRequest('/slow', { signal: controller.signal, timeoutMs: 10_000 });
    controller.abort();
    const error = await pending.catch((e: unknown) => e);
    expect(isTimeoutError(error)).toBe(false);
    expect((error as Error).name).toBe('AbortError');
  });

  it('sends cookies and never forwards timeoutMs to fetch', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);
    await apiRequest('/ping', { timeoutMs: 1000 });
    const init = fetchMock.mock.calls[0][1] as RequestInit & { timeoutMs?: number };
    expect(init.credentials).toBe('include');
    expect(init.signal).toBeInstanceOf(AbortSignal);
    expect(init.timeoutMs).toBeUndefined();
  });

  it('reads the error envelope, validation details and rate limits', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: 'validation_error',
              message: 'Request validation failed.',
              details: [{ field: 'body.query', message: 'Field required' }],
            },
          },
          422,
        ),
      ),
    );
    const validation = await apiRequest('/x').catch((e: unknown) => e);
    expect(apiErrorCode(validation)).toBe('validation_error');
    expect(apiErrorMessage(validation, 'fallback')).toBe('body.query: Field required');

    const limited = new ApiError('429', 429, 'Too Many Requests');
    expect(apiErrorMessage(limited, 'fallback')).toMatch(/too many requests/i);
  });
});
