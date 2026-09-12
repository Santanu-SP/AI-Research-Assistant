/**
 * Central API Client configuration for FastAPI integration.
 * In production or development with a live FastAPI backend, requests
 * route to VITE_API_BASE_URL (defaults to http://localhost:8000/api/v1).
 */

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

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

/**
 * Generic API request helper for future FastAPI consumption.
 */
export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
  const headers = new Headers(options.headers);
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json');
  }

  const config: RequestInit = {
    ...options,
    headers,
  };

  try {
    const response = await fetch(url, config);

    if (!response.ok) {
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

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(
      error instanceof Error ? error.message : 'Unknown network error'
    );
  }
}
