import { Document, DocumentListResponse } from '../types/document';
import { ApiError, UPLOAD_REQUEST_TIMEOUT_MS, apiErrorCode, apiErrorMessage, apiRequest } from './api';

export interface ProjectDocumentListParams {
  search?: string;
  status?: string;
  type?: string;
  limit?: number;
  offset?: number;
}

const documentListPath = (
  path: string,
  params?: ProjectDocumentListParams,
): string => {
  const query = new URLSearchParams();
  if (params?.search) query.append('search', params.search);
  if (params?.status && params.status !== 'all') query.append('status', params.status);
  if (params?.type && params.type !== 'all') query.append('type', params.type.toLowerCase());
  if (params?.limit) query.append('limit', params.limit.toString());
  if (params?.offset) query.append('offset', params.offset.toString());

  const serialized = query.toString();
  return serialized ? `${path}?${serialized}` : path;
};

export const documentsService = {
  async getDocuments(params?: ProjectDocumentListParams): Promise<DocumentListResponse> {
    return apiRequest<DocumentListResponse>(documentListPath('/documents', params));
  },

  async uploadDocument(file: File): Promise<Document> {
    const formData = new FormData();
    formData.append('file', file);
    return apiRequest<Document>('/documents', {
      method: 'POST',
      body: formData,
      timeoutMs: UPLOAD_REQUEST_TIMEOUT_MS,
    });
  },

  async deleteDocument(id: string): Promise<boolean> {
    await apiRequest<void>(`/documents/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    });
    return true;
  },

  async getProjectDocuments(
    projectId: string,
    params?: ProjectDocumentListParams,
    signal?: AbortSignal
  ): Promise<DocumentListResponse> {
    const path = `/projects/${encodeURIComponent(projectId)}/documents`;
    return apiRequest<DocumentListResponse>(documentListPath(path, params), { signal });
  },

  async uploadProjectDocument(projectId: string, file: File): Promise<Document> {
    const formData = new FormData();
    formData.append('file', file);
    return apiRequest<Document>(
      `/projects/${encodeURIComponent(projectId)}/documents`,
      { method: 'POST', body: formData, timeoutMs: UPLOAD_REQUEST_TIMEOUT_MS }
    );
  },

  /** Queue a failed document for another ingestion attempt. */
  async retryDocument(id: string): Promise<Document> {
    return apiRequest<Document>(`/documents/${encodeURIComponent(id)}/retry`, {
      method: 'POST',
    });
  },
};

/** True while the server is still parsing and indexing the document. */
export const isDocumentPending = (document: Pick<Document, 'status'>): boolean =>
  document.status === 'uploaded' || document.status === 'processing';

export const isDuplicateDocumentError = (error: unknown): boolean => {
  if (!(error instanceof ApiError) || error.status !== 409) return false;
  const data = error.data as { detail?: string; error?: { code?: string } } | null;
  if (data?.error?.code === 'duplicate_document') return true;
  // Other 409s (for example document_not_retryable) carry their own code.
  if (data?.error?.code) return false;
  if (typeof data?.detail === 'string' && data.detail.toLowerCase().includes('duplicate')) {
    return true;
  }
  // Document routes use 409 only for duplicates, including older bodies
  // that did not include the stable error code.
  return true;
};

export const getDocumentErrorMessage = (
  error: unknown,
  fallback: string
): string => {
  if (isDuplicateDocumentError(error)) {
    return 'This file has already been added.';
  }
  if (error instanceof ApiError) {
    if (error.status === 403) return 'You do not have permission to upload to this project.';
    if (error.status === 413) return 'File is too large to upload.';
    if (error.status === 429) return 'Too many uploads. Please wait a minute and try again.';
    if (apiErrorCode(error) === 'document_not_retryable') {
      return 'This file is already being prepared.';
    }
    if (apiErrorCode(error) === 'document_file_missing') {
      return 'The original file is no longer available. Remove it and upload it again.';
    }
    if (error.status === 422) {
      const data = error.data as { detail?: unknown } | null;
      if (typeof data?.detail === 'string') return data.detail;
    }
  }
  return apiErrorMessage(error, fallback);
};
