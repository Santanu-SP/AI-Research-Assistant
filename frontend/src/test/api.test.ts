import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  apiErrorCode,
  apiErrorMessage,
  apiRequest,
  isCrossSiteApi,
  isTimeoutError,
  probeSameOriginApi,
  resolveApiBaseUrl,
} from '../services/api';

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

describe('resolveApiBaseUrl', () => {
  const page = (url: string) => {
    const { protocol, hostname, origin } = new URL(url);
    return { protocol, hostname, origin };
  };

  it('uses the page hostname on port 8000 when nothing is configured', () => {
    expect(resolveApiBaseUrl(page('http://127.0.0.1:3000/'))).toBe('http://127.0.0.1:8000/api/v1');
  });

  it('keeps the login cookie working when localhost and 127.0.0.1 are mixed', () => {
    expect(resolveApiBaseUrl(page('http://localhost:3000/'), 'http://127.0.0.1:8000/api/v1')).toBe(
      'http://localhost:8000/api/v1',
    );
    expect(resolveApiBaseUrl(page('http://127.0.0.1:3000/'), 'http://localhost:8000/api/v1')).toBe(
      'http://127.0.0.1:8000/api/v1',
    );
  });

  it('leaves a matching local URL, a same-origin path and a real domain alone', () => {
    expect(resolveApiBaseUrl(page('http://127.0.0.1:3000/'), 'http://127.0.0.1:8000/api/v1')).toBe(
      'http://127.0.0.1:8000/api/v1',
    );
    expect(resolveApiBaseUrl(page('http://localhost:3000/'), '/api/v1')).toBe('/api/v1');
    expect(resolveApiBaseUrl(page('https://app.example.com/'), 'https://api.example.com/api/v1')).toBe(
      'https://api.example.com/api/v1',
    );
  });

  it('follows a LAN page address instead of a local .env URL', () => {
    expect(resolveApiBaseUrl(page('http://192.168.1.5:3000/'), 'http://localhost:8000/api/v1')).toBe(
      'http://192.168.1.5:8000/api/v1',
    );
  });
});

describe('cross-site API detection', () => {
  const page = (hostname: string) => ({ hostname } as Location);

  it('treats a backend on another site as cross-site', () => {
    expect(isCrossSiteApi('https://ara-api.onrender.com/api/v1', page('ai-research-assistant.pages.dev'))).toBe(true);
  });

  it('treats the same-origin proxy path and same-site hosts as first-party', () => {
    expect(isCrossSiteApi('/api/v1', page('ai-research-assistant.pages.dev'))).toBe(false);
    expect(isCrossSiteApi('https://api.example.com/api/v1', page('app.example.com'))).toBe(false);
  });
});

describe('probeSameOriginApi', () => {
  const originalFetch = globalThis.fetch;
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('is true only when /api/v1/health answers like the API', async () => {
    globalThis.fetch = vi.fn(async () => jsonResponse({ status: 'ok', service: 'ai-research-assistant-api' })) as typeof fetch;
    await expect(probeSameOriginApi()).resolves.toBe(true);
    globalThis.fetch = vi.fn(async () => new Response('<html></html>', { status: 200 })) as typeof fetch;
    await expect(probeSameOriginApi()).resolves.toBe(false);
    globalThis.fetch = vi.fn(async () => jsonResponse({ error: { code: 'proxy_not_configured' } }, 503)) as typeof fetch;
    await expect(probeSameOriginApi()).resolves.toBe(false);
  });
});
