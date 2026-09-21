import { Document, DocumentListResponse } from '../types/document';
import { apiRequest } from './api';

export const documentsService = {
  /**
   * Fetch all documents.
   * GET /api/v1/documents
   */
  async getDocuments(params?: {
    search?: string;
    status?: string;
    type?: string;
    limit?: number;
    offset?: number;
  }): Promise<DocumentListResponse> {
    const query = new URLSearchParams();
    if (params?.search) query.append('search', params.search);
    if (params?.status && params.status !== 'all') query.append('status', params.status);
    if (params?.type && params.type !== 'all') query.append('type', params.type.toLowerCase());
    if (params?.limit) query.append('limit', params.limit.toString());
    if (params?.offset) query.append('offset', params.offset.toString());
    
    const qs = query.toString();
    const endpoint = qs ? `/documents?${qs}` : '/documents';
    
    return apiRequest<DocumentListResponse>(endpoint);
  },

  /**
   * Upload documents to the knowledge workspace.
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
   * Delete a document.
   * DELETE /api/v1/documents/{id}
   */
  async deleteDocument(id: string): Promise<boolean> {
    await apiRequest<void>(`/documents/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    });
    return true;
  }
};
