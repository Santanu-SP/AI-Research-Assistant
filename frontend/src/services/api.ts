/**
 * Requests go to VITE_API_BASE_URL when it is set. It may be absolute
 * (http://localhost:8000/api/v1) or a same-origin path (/api/v1, when a
 * reverse proxy serves the API). Otherwise they use the page
 * hostname on port 8000, so a LAN address stays on the same host.
 */

const isLoopbackHost = (hostname: string) => hostname === 'localhost' || hostname === '127.0.0.1';

/**
 * Pick the API base URL for the page the user opened.
 *
 * Login uses a SameSite cookie, and the browser treats "localhost" and
 * "127.0.0.1" as two different sites. If the page is on one and the API on
 * the other, the cookie is never sent back and login looks like it does
 * nothing. So when both are local, the API follows the page's hostname.
 */
export const resolveApiBaseUrl = (
  page: { protocol: string; hostname: string; origin: string },
  configured?: string,
): string => {
  const fallback = `${page.protocol}//${page.hostname}:8000/api/v1`;
  if (!configured) {
    return fallback;
  }
  const url = new URL(configured, page.origin);
  if (!isLoopbackHost(url.hostname)) {
    return configured.replace(/\/+$/, '');
  }
  // Older local .env files point at localhost. When the page is opened
  // through a LAN IP, that creates a cross-origin request blocked by CORS.
  if (!isLoopbackHost(page.hostname)) {
    return fallback;
  }
  if (url.hostname !== page.hostname) {
    url.hostname = page.hostname;
    return url.toString().replace(/\/$/, '');
  }
  return configured.replace(/\/+$/, '');
};

/** Path of the same-origin API proxy (frontend/functions/api/[[path]].ts on Cloudflare Pages). */
export const SAME_ORIGIN_API_PATH = '/api/v1';
const SAME_ORIGIN_API_STORAGE_KEY = 'ara_api_same_origin';

const readSameOriginPreference = (): boolean => {
  try {
    return window.localStorage.getItem(SAME_ORIGIN_API_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
};

/**
 * The API base URL in use. It is a live binding: it can switch to the
 * same-origin proxy at runtime (see switchToSameOriginApi), and every caller
 * reads it at request time.
 */
export let API_BASE_URL =
  readSameOriginPreference() && !isLoopbackHost(window.location.hostname)
    ? SAME_ORIGIN_API_PATH
    : resolveApiBaseUrl(window.location, import.meta.env.VITE_API_BASE_URL);

/** True when the API lives on another site, so its cookie is a third-party cookie. */
export const isCrossSiteApi = (base: string = API_BASE_URL, page: Location = window.location): boolean => {
  if (!/^https?:\/\//i.test(base)) return false;
  const siteOf = (hostname: string) => hostname.split('.').slice(-2).join('.');
  const api = new URL(base);
  return siteOf(api.hostname) !== siteOf(page.hostname);
};

/**
 * Checks whether this site has a working same-origin API proxy, by asking
 * /api/v1/health on the page's own origin.
 */
export const probeSameOriginApi = async (): Promise<boolean> => {
  try {
    const response = await fetch(`${SAME_ORIGIN_API_PATH}/health`, { credentials: 'omit', cache: 'no-store' });
    if (!response.ok) return false;
    const body = (await response.json()) as { status?: string };
    return body?.status === 'ok';
  } catch {
    return false;
  }
};

/** Send all later API calls through the same-origin proxy, and remember it. */
export const switchToSameOriginApi = () => {
  API_BASE_URL = SAME_ORIGIN_API_PATH;
  try {
    window.localStorage.setItem(SAME_ORIGIN_API_STORAGE_KEY, '1');
  } catch {
    // Private mode may block storage; the switch still holds for this tab.
  }
};

export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
    public data?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export const DEFAULT_REQUEST_TIMEOUT_MS = 75_000;
export const UPLOAD_REQUEST_TIMEOUT_MS = 5 * 60_000;

interface ErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
    details?: Array<{ field?: string; message?: string }>;
  };
  detail?: unknown;
}

const errorEnvelope = (error: unknown): ErrorEnvelope | null =>
  error instanceof ApiError && typeof error.data === 'object' && error.data !== null
    ? (error.data as ErrorEnvelope)
    : null;

/** Stable error code from the backend's `{ error: { code } }` envelope. */
export const apiErrorCode = (error: unknown): string | undefined =>
  errorEnvelope(error)?.error?.code;

export const isTimeoutError = (error: unknown): boolean =>
  error instanceof ApiError && error.data === 'timeout';

export const apiErrorMessage = (error: unknown, fallback: string): string => {
  const data = errorEnvelope(error);
  if (data) {
    const firstDetail = data.error?.details?.find((d) => typeof d.message === 'string');
    if (data.error?.code === 'validation_error' && firstDetail?.message) {
      return firstDetail.field
        ? `${firstDetail.field}: ${firstDetail.message}`
        : firstDetail.message;
    }
    if (typeof data.error?.message === 'string') return data.error.message;
    if (typeof data.detail === 'string') return data.detail;
  }
  if (isTimeoutError(error)) return 'The server took too long to respond. Please try again.';
  if (error instanceof ApiError && error.status === 429) {
    return 'Too many requests. Please wait a moment and try again.';
  }
  return fallback;
};

export interface ApiRequestOptions extends RequestInit {
  /** Abort the request after this many milliseconds. Use 0 to disable. */
  timeoutMs?: number;
}

/**
 * Combines the caller's signal with a timeout. AbortSignal.any is not
 * available everywhere (older Safari, jsdom), so the signals are linked by hand.
 */
function linkedAbort(signal: AbortSignal | null | undefined, timeoutMs: number) {
  const controller = new AbortController();
  let timedOut = false;
  const onAbort = () => controller.abort(signal?.reason);
  if (signal) {
    if (signal.aborted) controller.abort(signal.reason);
    else signal.addEventListener('abort', onAbort, { once: true });
  }
  const timer = timeoutMs > 0
    ? setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, timeoutMs)
    : undefined;
  return {
    signal: controller.signal,
    didTimeOut: () => timedOut,
    cleanup: () => {
      if (timer !== undefined) clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);
    },
  };
}

export async function apiRequest<T>(
  endpoint: string,
  options: ApiRequestOptions = {}
): Promise<T> {
  const { timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS, signal: callerSignal, ...init } = options;
  const url = `${API_BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
  const headers = new Headers(init.headers);
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json');
  }

  const abort = linkedAbort(callerSignal, timeoutMs);
  const config: RequestInit = {
    ...init,
    headers,
    credentials: 'include',
    signal: abort.signal,
  };

  try {
    const response = await fetch(url, config);

    if (!response.ok) {
      if (response.status === 401 && !endpoint.startsWith('/auth/')) {
        window.dispatchEvent(new Event('auth:expired'));
      }
      const errorBody = await response.text();
      let parsedError;
      try {
        parsedError = JSON.parse(errorBody);
      } catch {
        parsedError = errorBody;
      }
      throw new ApiError(
        `API request failed: ${response.status} ${response.statusText}`,
        response.status,
        parsedError
      );
    }

    return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    if (abort.didTimeOut()) {
      throw new ApiError(`Request timed out after ${timeoutMs} ms`, undefined, 'timeout');
    }
    if (callerSignal?.aborted) {
      // Keep the caller's abort visible as an abort, not a network failure.
      throw error;
    }
    throw new ApiError(
      error instanceof Error ? error.message : 'Unknown network error'
    );
  } finally {
    abort.cleanup();
  }
}
