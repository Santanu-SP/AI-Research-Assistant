import {
  DiscoveredSourceCandidate,
  DiscoveryImportResponse,
  DiscoverySearchRequest,
  DiscoverySearchResponse,
} from '../types/discovery';
import { DOCUMENTS_CHANGED_EVENT, DocumentsChangedDetail } from './documents.service';
import { ApiError, UPLOAD_REQUEST_TIMEOUT_MS, apiErrorCode, apiErrorMessage, apiRequest } from './api';

const DISCOVERY_SEARCH_TIMEOUT_MS = 25_000;

const notifyImportedDocuments = (docs: DiscoveryImportResponse['documents']): void => {
  if (typeof window === 'undefined' || docs.length === 0) return;
  for (const doc of docs) {
    window.dispatchEvent(
      new CustomEvent<DocumentsChangedDetail>(DOCUMENTS_CHANGED_EVENT, {
        detail: { action: 'upload', document: doc },
      }),
    );
  }
};

export const discoveryService = {
  async search(
    payload: DiscoverySearchRequest,
    signal?: AbortSignal,
  ): Promise<DiscoverySearchResponse> {
    return apiRequest<DiscoverySearchResponse>('/discovery/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: payload.query.trim(),
        scope: payload.scope ?? 'all',
        limit: payload.limit ?? 8,
        ...(payload.projectId ? { projectId: payload.projectId } : {}),
      }),
      signal,
      timeoutMs: DISCOVERY_SEARCH_TIMEOUT_MS,
    });
  },

  async importSources(
    items: DiscoveredSourceCandidate[],
    options: { projectId?: string | null; fetchFullText?: boolean } = {},
  ): Promise<DiscoveryImportResponse> {
    const response = await apiRequest<DiscoveryImportResponse>('/discovery/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        items,
        fetchFullText: options.fetchFullText ?? true,
        ...(options.projectId ? { projectId: options.projectId } : {}),
      }),
      timeoutMs: UPLOAD_REQUEST_TIMEOUT_MS,
    });
    notifyImportedDocuments(response.documents);
    return response;
  },
};

export const getDiscoveryErrorMessage = (error: unknown, fallback: string): string => {
  if (error instanceof ApiError) {
    const code = apiErrorCode(error);
    if (code === 'discovery_disabled') {
      return 'Controlled online discovery is turned off on this server.';
    }
    if (code === 'no_discoverable_sources') {
      return 'No trustworthy external sources with readable text were found for this query.';
    }
    if (error.status === 429) {
      return 'Too many discovery requests. Please wait a moment and try again.';
    }
  }
  return apiErrorMessage(error, fallback);
};
