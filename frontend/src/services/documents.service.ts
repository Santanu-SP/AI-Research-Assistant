import { Document, DocumentListResponse } from '../types/document';
import { apiRequest, API_BASE_URL } from './api';

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

    const url = `${API_BASE_URL}/documents`;
    const response = await fetch(url, {
      method: 'POST',
      body: formData,
      headers: {
        'Accept': 'application/json',
      }
    });

    if (!response.ok) {
      const errText = await response.text().catch(() => '');
      throw new Error(`Failed to upload document: ${response.statusText} ${errText}`);
    }

    return (await response.json()) as Document;
  },

  /**
   * Delete a document.
   * DELETE /api/v1/documents/{id}
   */
  async deleteDocument(id: string): Promise<boolean> {
    const url = `${API_BASE_URL}/documents/${id}`;
    const response = await fetch(url, {
      method: 'DELETE',
    });

    if (!response.ok) {
      throw new Error(`Failed to delete document: ${response.statusText}`);
    }
    
    return true;
  }
};
