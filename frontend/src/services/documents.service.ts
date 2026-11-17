import { Document, DocumentListResponse } from '../types/document';
import { ApiError, UPLOAD_REQUEST_TIMEOUT_MS, apiErrorCode, apiErrorMessage, apiRequest } from './api';

export const DOCUMENTS_CHANGED_EVENT = 'documents:changed';

export interface DocumentsChangedDetail {
  action: 'upload' | 'delete' | 'retry';
  document?: Document;
  documentId?: string;
}

const notifyDocumentsChanged = (detail: DocumentsChangedDetail): void => {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent<DocumentsChangedDetail>(DOCUMENTS_CHANGED_EVENT, { detail }));
  }
};

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
  async getDocuments(
    params?: ProjectDocumentListParams,
    signal?: AbortSignal,
  ): Promise<DocumentListResponse> {
    return apiRequest<DocumentListResponse>(documentListPath('/documents', params), { signal });
  },

  async uploadDocument(file: File): Promise<Document> {
    const formData = new FormData();
    formData.append('file', file);
    const document = await apiRequest<Document>('/documents', {
      method: 'POST',
      body: formData,
      timeoutMs: UPLOAD_REQUEST_TIMEOUT_MS,
    });
    notifyDocumentsChanged({ action: 'upload', document });
    return document;
  },

  async deleteDocument(id: string): Promise<boolean> {
    await apiRequest<void>(`/documents/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    });
    notifyDocumentsChanged({ action: 'delete', documentId: id });
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

  async getDocument(id: string, signal?: AbortSignal): Promise<Document> {
    return apiRequest<Document>(`/documents/${encodeURIComponent(id)}`, { signal });
  },

  async uploadProjectDocument(projectId: string, file: File): Promise<Document> {
    const formData = new FormData();
    formData.append('file', file);
    const document = await apiRequest<Document>(
      `/projects/${encodeURIComponent(projectId)}/documents`,
      { method: 'POST', body: formData, timeoutMs: UPLOAD_REQUEST_TIMEOUT_MS }
    );
    notifyDocumentsChanged({ action: 'upload', document });
    return document;
  },

  async addUrlDocument(
    url: string,
    title?: string,
    projectId?: string | null,
  ): Promise<Document> {
    const path = projectId
      ? `/projects/${encodeURIComponent(projectId)}/documents/url`
      : '/documents/url';
    const body: { url: string; title?: string; projectId?: string } = {
      url: url.trim(),
    };
    const trimmedTitle = title?.trim();
    if (trimmedTitle) body.title = trimmedTitle;
    if (projectId) body.projectId = projectId;
    const document = await apiRequest<Document>(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      timeoutMs: UPLOAD_REQUEST_TIMEOUT_MS,
    });
    notifyDocumentsChanged({ action: 'upload', document });
    return document;
  },

  /** Queue a failed document for another ingestion attempt. */
  async retryDocument(id: string): Promise<Document> {
    const document = await apiRequest<Document>(`/documents/${encodeURIComponent(id)}/retry`, {
      method: 'POST',
    });
    notifyDocumentsChanged({ action: 'retry', document });
    return document;
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

/** The existing copy named by a duplicate-upload error, if the server sent it. */
export const duplicateDocumentIdFromError = (error: unknown): string | null => {
  if (!(error instanceof ApiError)) return null;
  const data = error.data as { error?: { details?: { documentId?: unknown } } } | null;
  const id = data?.error?.details?.documentId;
  return typeof id === 'string' ? id : null;
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
    const code = apiErrorCode(error);
    if (code === 'document_not_retryable') {
      return 'This file is already being prepared.';
    }
    if (code === 'document_file_missing') {
      return 'The original file is no longer available. Remove it and upload it again.';
    }
    if (code === 'unsupported_document_type' || code === 'document_type_mismatch') {
      return 'This file format is not supported or does not match its extension.';
    }
    if (
      code === 'invalid_source_url' ||
      code === 'unsafe_source_url' ||
      code === 'ssrf_blocked_url' ||
      code === 'invalid_youtube_url'
    ) {
      return 'Please enter a valid public http://, https://, or YouTube URL.';
    }
    if (code === 'youtube_transcript_unavailable') {
      return 'This YouTube video does not expose an accessible transcript.';
    }
    if (code === 'audio_transcription_key_missing' || code === 'vision_api_key_missing') {
      return 'Server transcription/vision key is not configured for this media type.';
    }
    if (error.status === 422) {
      const data = error.data as { detail?: unknown } | null;
      if (typeof data?.detail === 'string') return data.detail;
    }
  }
  return apiErrorMessage(error, fallback);
};
