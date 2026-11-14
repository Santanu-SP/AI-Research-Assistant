import { ApiError, apiErrorMessage, apiRequest } from './api';
import {
  CreateResearchInput,
  ResearchListParams,
  ResearchListResponse,
  ResearchQueryRequest,
  ResearchQueryResponse,
  ResearchResponse,
  UpdateResearchInput,
} from '../types/research';

const buildResearchQuery = (params: ResearchListParams = {}): string => {
  const query = new URLSearchParams();

  if (params.search?.trim()) query.set('search', params.search.trim());
  if (params.domain?.trim()) query.set('domain', params.domain.trim());
  if (params.status) query.set('status', params.status);
  if (params.limit !== undefined) query.set('limit', String(params.limit));
  if (params.offset !== undefined) query.set('offset', String(params.offset));
  if (params.includeArchived !== undefined) {
    query.set('includeArchived', String(params.includeArchived));
  }
  if (params.projectId) query.set('projectId', params.projectId);

  const serialized = query.toString();
  return serialized ? `/research?${serialized}` : '/research';
};

export const createResearch = (payload: CreateResearchInput): Promise<ResearchResponse> =>
  apiRequest<ResearchResponse>('/research', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

/** Local generation can take a while, so the answer gets a longer timeout. */
export const QUERY_REQUEST_TIMEOUT_MS = 5 * 60_000;

const notifyUsageUpdated = (): void => {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('models-usage:refresh'));
  }
};

export const queryResearch = async (
  payload: ResearchQueryRequest
): Promise<ResearchQueryResponse> => {
  try {
    return await apiRequest<ResearchQueryResponse>('/research/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      timeoutMs: QUERY_REQUEST_TIMEOUT_MS,
    });
  } finally {
    notifyUsageUpdated();
  }
};

/**
 * Starts a research run on the server's background worker and returns the
 * research record straight away. Follow it at /research/:id/progress.
 */
export const startResearchJob = async (
  payload: ResearchQueryRequest
): Promise<ResearchResponse> => {
  try {
    return await apiRequest<ResearchResponse>('/research/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } finally {
    notifyUsageUpdated();
  }
};

export const listResearch = (
  params: ResearchListParams = {}
): Promise<ResearchListResponse> =>
  apiRequest<ResearchListResponse>(buildResearchQuery(params));

export const getResearch = (researchId: string): Promise<ResearchResponse> =>
  apiRequest<ResearchResponse>(`/research/${encodeURIComponent(researchId)}`);

export const updateResearch = (
  researchId: string,
  payload: UpdateResearchInput
): Promise<ResearchResponse> =>
  apiRequest<ResearchResponse>(`/research/${encodeURIComponent(researchId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

export const archiveResearch = async (researchId: string): Promise<void> => {
  await apiRequest<void>(`/research/${encodeURIComponent(researchId)}`, { method: 'DELETE' });
};

export const getResearchErrorMessage = (
  error: unknown,
  fallback: string
): string => {
  if (!(error instanceof ApiError)) return fallback;

  const envelopeMessage = apiErrorMessage(error, '');
  if (envelopeMessage) return envelopeMessage;

  const data = error.data;
  if (typeof data === 'object' && data !== null && 'detail' in data) {
    const detail = (data as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      const firstMessage = detail.find(
        (item): item is { msg: string } =>
          typeof item === 'object' &&
          item !== null &&
          'msg' in item &&
          typeof (item as { msg?: unknown }).msg === 'string'
      );
      if (firstMessage) return firstMessage.msg;
    }
  }

  if (typeof data === 'object' && data !== null && 'error' in data) {
    const apiError = (data as { error?: { message?: unknown } }).error;
    if (typeof apiError?.message === 'string') return apiError.message;
  }

  return error.status === 404 ? 'Research not found.' : fallback;
};

export const researchService = {
  createResearch,
  queryResearch,
  startResearchJob,
  listResearch,
  getResearch,
  updateResearch,
  archiveResearch,
};
