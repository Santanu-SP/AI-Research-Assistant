import { afterEach, describe, expect, it, vi } from 'vitest';
import { onRequest } from '../../functions/api/[[path]].ts';

describe('Cloudflare Pages /api/* same-origin proxy', () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('returns 503 when BACKEND_ORIGIN is missing or invalid', async () => {
    const response = await onRequest({
      request: new Request('https://ai-research-assistant.pages.dev/api/v1/auth/me'),
      env: {},
    });
    expect(response.status).toBe(503);
    const body = (await response.json()) as { error?: { code?: string } };
    expect(body.error?.code).toBe('proxy_not_configured');
  });

  it('falls back to the origin of an absolute VITE_API_BASE_URL when BACKEND_ORIGIN is not set', async () => {
    let capturedUrl = '';
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      capturedUrl = typeof input === 'string' ? input : input.toString();
      return new Response('{"status":"ok"}', { status: 200 });
    }) as typeof fetch;
    const response = await onRequest({
      request: new Request('https://ai-research-assistant.pages.dev/api/v1/health'),
      env: { VITE_API_BASE_URL: 'https://ara-api.onrender.com/api/v1' },
    });
    expect(response.status).toBe(200);
    expect(capturedUrl).toBe('https://ara-api.onrender.com/api/v1/health');
  });

  it('forwards HTTP requests manually preserving redirects, Set-Cookie, Origin, and stripping cf-* headers', async () => {
    let capturedUrl = '';
    let capturedInit: RequestInit | undefined;

    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      capturedUrl = typeof input === 'string' ? input : input.toString();
      capturedInit = init;
      const headers = new Headers({
        location: 'https://ai-research-assistant.pages.dev/auth/google/complete',
        'set-cookie': 'ara_session=sample-cookie-value; HttpOnly; Path=/api/v1; SameSite=None; Secure',
      });
      return new Response(null, { status: 303, headers });
    }) as typeof fetch;

    const request = new Request(
      'https://ai-research-assistant.pages.dev/api/v1/auth/google/callback?code=abc&state=xyz',
      {
        method: 'GET',
        headers: {
          cookie: 'ara_session=old-cookie',
          origin: 'https://ai-research-assistant.pages.dev',
          'cf-connecting-ip': '203.0.113.10',
          'cf-ray': '123456-BOM',
          'cdn-loop': 'cloudflare',
        },
      },
    );

    const response = await onRequest({
      request,
      env: { BACKEND_ORIGIN: 'https://ai-research-assistant-api-d71s.onrender.com/' },
    });

    expect(capturedUrl).toBe(
      'https://ai-research-assistant-api-d71s.onrender.com/api/v1/auth/google/callback?code=abc&state=xyz',
    );
    expect(capturedInit?.redirect).toBe('manual');
    const forwardedHeaders = new Headers(capturedInit?.headers);
    expect(forwardedHeaders.get('cookie')).toBe('ara_session=old-cookie');
    expect(forwardedHeaders.get('origin')).toBe('https://ai-research-assistant.pages.dev');
    expect(forwardedHeaders.get('x-forwarded-for')).toBe('203.0.113.10');
    expect(forwardedHeaders.get('x-forwarded-host')).toBe('ai-research-assistant.pages.dev');
    expect(forwardedHeaders.get('cf-ray')).toBeNull();
    expect(forwardedHeaders.get('cdn-loop')).toBeNull();

    expect(response.status).toBe(303);
    expect(response.headers.get('location')).toBe(
      'https://ai-research-assistant.pages.dev/auth/google/complete',
    );
    expect(response.headers.get('set-cookie')).toContain('ara_session=sample-cookie-value');
  });

  it('forwards WebSocket upgrade headers directly while stripping cf loop headers', async () => {
    let capturedUrl = '';
    let capturedInit: RequestInit | undefined;

    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      capturedUrl = typeof input === 'string' ? input : input.toString();
      capturedInit = init;
      return new Response('ok', { status: 200 });
    }) as typeof fetch;

    const request = new Request(
      'https://ai-research-assistant.pages.dev/api/v1/ws/research/123',
      {
        headers: {
          upgrade: 'websocket',
          connection: 'Upgrade',
          'sec-websocket-key': 'test-ws-handshake',
          cookie: 'ara_session=sample-cookie-2',
          origin: 'https://ai-research-assistant.pages.dev',
          'cf-ray': 'abc-BOM',
        },
      },
    );

    const response = await onRequest({
      request,
      env: { BACKEND_ORIGIN: 'https://ai-research-assistant-api-d71s.onrender.com' },
    });

    expect(response.status).toBe(200);
    expect(capturedUrl).toBe(
      'https://ai-research-assistant-api-d71s.onrender.com/api/v1/ws/research/123',
    );
    const headers = new Headers(capturedInit?.headers);
    expect(headers.get('upgrade')).toBe('websocket');
    expect(headers.get('connection')).toBe('Upgrade');
    expect(headers.get('cookie')).toBe('ara_session=sample-cookie-2');
    expect(headers.get('cf-ray')).toBeNull();
  });
});
