/**
 * Requests go to VITE_API_BASE_URL when it is set. It may be absolute
 * (http://localhost:8000/api/v1) or a same-origin path (/api/v1, when a
 * reverse proxy serves the API). Otherwise they use the page
 * hostname on port 8000, so a LAN address stays on the same host.
 */

const pageHostname = window.location.hostname;
const localApiBaseUrl = `${window.location.protocol}//${pageHostname}:8000/api/v1`;
const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL;
const isLoopbackHost = (hostname: string) => hostname === 'localhost' || hostname === '127.0.0.1';
const configuredHost = configuredApiBaseUrl
  ? new URL(configuredApiBaseUrl, window.location.origin).hostname
  : null;

// Older local .env files point at localhost. When the page is opened through a
// LAN IP, that creates a cross-origin request and browsers block it by CORS.
const usePageHostname = !configuredApiBaseUrl
  || (!isLoopbackHost(pageHostname) && configuredHost !== null && isLoopbackHost(configuredHost));

export const API_BASE_URL =
  usePageHostname ? localApiBaseUrl : configuredApiBaseUrl;

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

export const DEFAULT_REQUEST_TIMEOUT_MS = 30_000;
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
