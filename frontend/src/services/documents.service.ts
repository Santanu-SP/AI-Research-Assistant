import { Document, DocumentListResponse } from '../types/document';
import { ApiError, apiRequest } from './api';

export interface ProjectDocumentListParams {
  search?: string;
  status?: string;
  type?: string;
  limit?: number;
  offset?: number;
}

/**
 * Documents service for both global and project-scoped endpoints.
 * Global: /api/v1/documents
 * Project-scoped: /api/v1/projects/{projectId}/documents
 */
export const documentsService = {
  /**
   * Fetch all global (non-project-scoped) documents.
   * GET /api/v1/documents
   */
  async getDocuments(params?: ProjectDocumentListParams): Promise<DocumentListResponse> {
    const query = new URLSearchParams();
    if (params?.search) query.append('search', params.search);
    if (params?.status && params.status !== 'all') query.append('status', params.status);
    if (params?.type && params.type !== 'all') query.append('type', params.type.toLowerCase());
    if (params?.limit) query.append('limit', params.limit.toString());
    if (params?.offset) query.append('offset', params.offset.toString());

    const qs = query.toString();
    return apiRequest<DocumentListResponse>(qs ? `/documents?${qs}` : '/documents');
  },

  /**
   * Upload a document to the global workspace.
   * POST /api/v1/documents (multipart/form-data)
   */
  async uploadDocument(file: File): Promise<Document> {
    const formData = new FormData();
    formData.append('file', file);
    return apiRequest<Document>('/documents', {
      method: 'POST',
      body: formData,
    });
  },

  /**
   * Delete a global document.
   * DELETE /api/v1/documents/{id}
   */
  async deleteDocument(id: string): Promise<boolean> {
    await apiRequest<void>(`/documents/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    });
    return true;
  },

  // ─── Project-scoped endpoints ────────────────────────────────────────────

  /**
   * Fetch documents belonging to a specific project.
   * GET /api/v1/projects/{projectId}/documents
   */
  async getProjectDocuments(
    projectId: string,
    params?: ProjectDocumentListParams,
    signal?: AbortSignal
  ): Promise<DocumentListResponse> {
    const query = new URLSearchParams();
    if (params?.search) query.append('search', params.search);
    if (params?.status && params.status !== 'all') query.append('status', params.status);
    if (params?.type && params.type !== 'all') query.append('type', params.type.toLowerCase());
    if (params?.limit) query.append('limit', params.limit.toString());
    if (params?.offset) query.append('offset', params.offset.toString());

    const qs = query.toString();
    const base = `/projects/${encodeURIComponent(projectId)}/documents`;
    return apiRequest<DocumentListResponse>(qs ? `${base}?${qs}` : base, { signal });
  },

  /**
   * Upload a document to a specific project.
   * POST /api/v1/projects/{projectId}/documents (multipart/form-data)
   */
  async uploadProjectDocument(projectId: string, file: File): Promise<Document> {
    const formData = new FormData();
    formData.append('file', file);
    return apiRequest<Document>(
      `/projects/${encodeURIComponent(projectId)}/documents`,
      { method: 'POST', body: formData }
    );
  },
};

/**
 * Check whether an API error represents a duplicate document.
 * The backend raises HTTP 409 for duplicate files within a project.
 */
export const isDuplicateDocumentError = (error: unknown): boolean => {
  if (!(error instanceof ApiError)) return false;
  if (error.status !== 409) return false;
  // Check for a stable error code in the response body if available
  const data = error.data as { detail?: string; error?: { code?: string } } | null;
  if (data?.error?.code === 'duplicate_document') return true;
  if (typeof data?.detail === 'string' && data.detail.toLowerCase().includes('duplicate')) return true;
  return true; // 409 from document endpoints is treated as duplicate
};

/**
 * Map a document API error to a user-safe string.
 */
export const getDocumentErrorMessage = (
  error: unknown,
  fallback: string
): string => {
  if (isDuplicateDocumentError(error)) {
    return 'This document already exists in this project.';
  }
  if (error instanceof ApiError) {
    if (error.status === 403) return 'You do not have permission to upload to this project.';
    if (error.status === 413) return 'File is too large to upload.';
    if (error.status === 422) {
      const data = error.data as { detail?: unknown } | null;
      if (typeof data?.detail === 'string') return data.detail;
    }
  }
  return fallback;
};
