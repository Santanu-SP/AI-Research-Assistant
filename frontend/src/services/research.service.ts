import { ApiError, apiRequest } from './api';
import {
  CreateResearchInput,
  ResearchListParams,
  ResearchListResponse,
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

  const serialized = query.toString();
  return serialized ? `/research?${serialized}` : '/research';
};

export const createResearch = (payload: CreateResearchInput): Promise<ResearchResponse> =>
  apiRequest<ResearchResponse>('/research', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

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

  return error.status === 404 ? 'Research not found.' : fallback;
};

export const researchService = {
  createResearch,
  listResearch,
  getResearch,
  updateResearch,
  archiveResearch,
};
