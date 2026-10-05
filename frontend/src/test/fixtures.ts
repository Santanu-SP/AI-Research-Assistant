/**
 * Reusable test fixtures matching actual backend schemas.
 * Do NOT add fields that don't exist in the backend responses.
 */
import { ResearchProject, ResearchProjectListResponse } from '../types/project';
import { Document, DocumentListResponse } from '../types/document';
import { ResearchQueryResponse } from '../types/research';

export const makeProject = (
  overrides: Partial<ResearchProject> = {}
): ResearchProject => ({
  id: 'proj-alpha-123',
  name: 'Project Alpha',
  description: 'Test project for membrane protein research',
  archivedAt: null,
  createdAt: '2025-01-15T10:00:00Z',
  updatedAt: '2025-03-20T14:30:00Z',
  ...overrides,
});

export const makeArchivedProject = (
  overrides: Partial<ResearchProject> = {}
): ResearchProject =>
  makeProject({
    id: 'proj-archived-456',
    name: 'Archived Project',
    description: null,
    archivedAt: '2025-06-01T00:00:00Z',
    ...overrides,
  });

export const makeProjectList = (
  items: ResearchProject[] = [makeProject()]
): ResearchProjectListResponse => ({
  items,
  total: items.length,
  limit: 20,
  offset: 0,
});

export const makeDocument = (
  overrides: Partial<Document> = {}
): Document => ({
  id: 'doc-001',
  projectId: 'proj-alpha-123',
  name: 'paper.pdf',
  type: 'pdf',
  mimeType: 'application/pdf',
  size: 1048576,
  sourceType: 'uploaded_file',
  sourceUri: null,
  sourceUrl: null,
  contentLevel: 'user_document',
  status: 'indexed',
  ingestionStatus: 'indexed',
  title: 'A Study of Membrane Proteins',
  authors: ['Smith, J.', 'Doe, A.'],
  abstract: null,
  doi: null,
  openalexId: null,
  crossrefId: null,
  publicationYear: null,
  publishedAt: null,
  canonicalMetadata: null,
  metadataProvenance: null,
  parserName: 'docling',
  parserVersion: null,
  ingestionVersion: null,
  pageCount: 12,
  uploadedAt: '2025-03-01T09:00:00Z',
  processingError: null,
  chunkCount: 48,
  createdAt: '2025-03-01T09:00:00Z',
  updatedAt: '2025-03-01T09:05:00Z',
  ...overrides,
});

export const makeProcessingDocument = (
  overrides: Partial<Document> = {}
): Document =>
  makeDocument({
    id: 'doc-002',
    name: 'draft.pdf',
    status: 'processing',
    ingestionStatus: 'processing',
    title: null,
    chunkCount: 0,
    ...overrides,
  });

export const makeFailedDocument = (
  overrides: Partial<Document> = {}
): Document =>
  makeDocument({
    id: 'doc-003',
    name: 'corrupted.pdf',
    status: 'failed',
    ingestionStatus: 'failed',
    processingError: 'Failed to parse PDF: invalid structure',
    chunkCount: 0,
    ...overrides,
  });

export const makeDocumentList = (
  items: Document[] = [makeDocument()]
): DocumentListResponse => ({
  items,
  total: items.length,
  limit: 20,
  offset: 0,
});

export const makeResearchQueryResponse = (
  overrides: Partial<ResearchQueryResponse> = {}
): ResearchQueryResponse => ({
  researchId: 'res-001',
  projectId: 'proj-alpha-123',
  answer:
    'Membrane proteins are integral to cellular signaling pathways. Studies demonstrate **high specificity** in binding interactions.',
  citations: [
    {
      citationId: 'cit-001',
      nodeId: null,
      documentId: 'doc-001',
      projectId: 'proj-alpha-123',
      sourceType: 'uploaded_file',
      contentLevel: 'user_document',
      chunkId: 'chunk-aabbcc',
      paperTitle: 'A Study of Membrane Proteins',
      authors: ['Smith, J.'],
      doi: null,
      page: 4,
      pageEnd: null,
      section: 'Results',
      sectionPath: null,
      excerpt:
        'The binding affinity of the studied protein was measured at 12 nM, consistent with previous findings.',
    },
  ],
  hybridCandidateCount: 8,
  evidenceCount: 3,
  insufficientEvidence: false,
  ...overrides,
});
