import { ApiError, apiRequest } from './api';

export interface ReadinessCheck {
  name: string;
  ok: boolean;
  detail?: string | null;
}

export interface ReadinessResponse {
  status: string;
  checks: ReadinessCheck[];
}

const isReadiness = (value: unknown): value is ReadinessResponse =>
  typeof value === 'object' && value !== null && Array.isArray((value as ReadinessResponse).checks);

/** GET /health/ready answers 503 with the same body when a dependency is down. */
export const getReadiness = async (): Promise<ReadinessResponse> => {
  try {
    return await apiRequest<ReadinessResponse>('/health/ready');
  } catch (error) {
    if (error instanceof ApiError && isReadiness(error.data)) return error.data;
    throw error;
  }
};

export const systemService = { getReadiness };
