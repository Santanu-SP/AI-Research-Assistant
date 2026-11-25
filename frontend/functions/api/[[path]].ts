/**
 * Cloudflare Pages Function that proxies /api/* (HTTP and WebSocket) to BACKEND_ORIGIN.
 *
 * Keeping API calls on the same origin as the *.pages.dev frontend turns the
 * HttpOnly session cookie into a first-party cookie, so browsers that block
 * cross-site cookies (Brave Shields, Safari ITP, Firefox Strict, Incognito)
 * remain signed in across reloads and Google OAuth popups.
 */

export interface ProxyEnv {
  BACKEND_ORIGIN?: string;
  /** Used when BACKEND_ORIGIN is not set: the build-time API URL, if it is absolute. */
  VITE_API_BASE_URL?: string;
}

export interface PagesFunctionContext {
  request: Request;
  env: ProxyEnv;
}

const HOP_BY_HOP_REQUEST_HEADERS = new Set([
  'host',
  'cdn-loop',
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
]);

const HOP_BY_HOP_RESPONSE_HEADERS = new Set([
  'connection',
  'keep-alive',
  'transfer-encoding',
]);

function resolveBackendOrigin(rawOrigin: string | undefined): string | null {
  const cleaned = (rawOrigin ?? '').trim().replace(/^['"]|['"]$/g, '').replace(/\/+$/, '');
  if (!cleaned) return null;
  try {
    const parsed = new URL(cleaned);
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
      return null;
    }
    return parsed.origin;
  } catch {
    return null;
  }
}

function buildUpstreamHeaders(
  incoming: Headers,
  requestUrl: URL,
  isWebSocket: boolean,
): Headers {
  const headers = new Headers();
  let clientIp: string | null = null;

  incoming.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (lower === 'cf-connecting-ip') {
      clientIp = value.trim() || null;
      return;
    }
    if (lower.startsWith('cf-')) {
      return;
    }
    if (HOP_BY_HOP_REQUEST_HEADERS.has(lower)) {
      if (isWebSocket && (lower === 'upgrade' || lower === 'connection')) {
        headers.set(key, value);
      }
      return;
    }
    headers.set(key, value);
  });

  if (clientIp) {
    const prior = incoming.get('x-forwarded-for');
    headers.set('x-forwarded-for', prior ? `${clientIp}, ${prior}` : clientIp);
  }
  headers.set('x-forwarded-host', requestUrl.host);
  headers.set('x-forwarded-proto', requestUrl.protocol.replace(':', ''));
  return headers;
}

export async function onRequest(context: PagesFunctionContext): Promise<Response> {
  const { request, env } = context;
  const backendOrigin =
    resolveBackendOrigin(env.BACKEND_ORIGIN) ?? resolveBackendOrigin(env.VITE_API_BASE_URL);
  if (!backendOrigin) {
    return new Response(
      JSON.stringify({
        error: {
          code: 'proxy_not_configured',
          message: 'BACKEND_ORIGIN (or an absolute VITE_API_BASE_URL) is not configured on Cloudflare Pages.',
        },
      }),
      {
        status: 503,
        headers: { 'content-type': 'application/json' },
      },
    );
  }

  const incomingUrl = new URL(request.url);
  if (incomingUrl.pathname !== '/api' && !incomingUrl.pathname.startsWith('/api/')) {
    return new Response(
      JSON.stringify({
        error: {
          code: 'invalid_proxy_path',
          message: 'Invalid API proxy path.',
        },
      }),
      {
        status: 400,
        headers: { 'content-type': 'application/json' },
      },
    );
  }

  const upstreamUrl = new URL(`${incomingUrl.pathname}${incomingUrl.search}`, backendOrigin);
  if (upstreamUrl.origin !== backendOrigin) {
    return new Response(
      JSON.stringify({
        error: {
          code: 'invalid_proxy_target',
          message: 'Invalid upstream proxy target.',
        },
      }),
      {
        status: 400,
        headers: { 'content-type': 'application/json' },
      },
    );
  }

  const upgradeHeader = request.headers.get('upgrade');
  const isWebSocket = Boolean(upgradeHeader && upgradeHeader.toLowerCase() === 'websocket');
  const headers = buildUpstreamHeaders(request.headers, incomingUrl, isWebSocket);

  if (isWebSocket) {
    return fetch(upstreamUrl.toString(), {
      method: request.method,
      headers,
    });
  }

  const hasBody = request.method !== 'GET' && request.method !== 'HEAD';
  const upstreamResponse = await fetch(upstreamUrl.toString(), {
    method: request.method,
    headers,
    body: hasBody ? request.body : undefined,
    // Keep 3xx OAuth redirects and Set-Cookie headers intact for the browser.
    redirect: 'manual',
  });

  const responseHeaders = new Headers(upstreamResponse.headers);
  for (const header of HOP_BY_HOP_RESPONSE_HEADERS) {
    responseHeaders.delete(header);
  }

  return new Response(upstreamResponse.body, {
    status: upstreamResponse.status,
    statusText: upstreamResponse.statusText,
    headers: responseHeaders,
  });
}
