import { Document, DocumentFormat } from '../types/document';
import { mockDocumentsList } from '../data/mockDocuments';
let currentDocuments: Document[] = [...mockDocumentsList];

export const documentsService = {
  /**
   * Fetch all documents.
   * Future: GET /api/v1/documents
   */
  async getDocuments(): Promise<Document[]> {
    return Promise.resolve([...currentDocuments]);
  },

  /**
   * Upload documents to the knowledge workspace.
   * Future: POST /api/v1/documents (multipart/form-data)
   */
  async uploadDocument(file: File): Promise<Document> {
    const extension = file.name.split('.').pop()?.toUpperCase();
    let docType: DocumentFormat = 'PDF';
    if (extension === 'DOCX' || extension === 'DOC') docType = 'DOCX';
    else if (extension === 'TXT') docType = 'TXT';
    else if (extension === 'MD') docType = 'MD';

    const newDoc: Document = {
      id: `doc-${Date.now()}`,
      name: file.name,
      type: docType,
      size: file.size,
      status: 'processing',
      uploadedAt: 'Just now',
    };

    currentDocuments = [newDoc, ...currentDocuments];

    // Simulate background processing transition to ready after a short delay
    setTimeout(() => {
      currentDocuments = currentDocuments.map((d) =>
        d.id === newDoc.id ? { ...d, status: 'ready' } : d
      );
    }, 2500);

    return Promise.resolve(newDoc);
  },

  /**
   * Delete a document.
   * Future: DELETE /api/v1/documents/{id}
   */
  async deleteDocument(id: string): Promise<boolean> {
    currentDocuments = currentDocuments.filter((doc) => doc.id !== id);
    return Promise.resolve(true);
  },

  /**
   * Retry the frontend-only processing demonstration.
   */
  async retryDocument(id: string): Promise<Document | undefined> {
    const doc = currentDocuments.find((d) => d.id === id);
    if (!doc) return undefined;

    doc.status = 'processing';
    setTimeout(() => {
      doc.status = 'ready';
    }, 2000);

    return Promise.resolve(doc);
  },
};
