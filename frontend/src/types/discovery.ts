import { ContentLevel, Document, SourceType } from './document';

export type DiscoveryScope = 'all' | 'scholarly' | 'web';
export type DiscoveryProvider = 'openalex' | 'crossref' | 'arxiv' | 'wikipedia' | 'news' | 'web';
export type DiscoveryTrustTier =
  | 'peer-reviewed'
  | 'preprint'
  | 'institutional'
  | 'official-documentation'
  | 'news';

export interface DiscoveredSourceCandidate {
  candidateId: string;
  provider: DiscoveryProvider;
  trustTier: DiscoveryTrustTier;
  sourceType: SourceType;
  contentLevel: ContentLevel;
  title: string;
  authors: string[];
  publicationYear: number | null;
  publisher: string | null;
  abstract: string | null;
  doi: string | null;
  openalexId: string | null;
  crossrefId: string | null;
  url: string;
  openAccessPdfUrl: string | null;
  citationCount: number | null;
  isOpenAccess: boolean;
  alreadyInLibrary: boolean;
  existingDocumentId: string | null;
}

export interface DiscoverySearchRequest {
  query: string;
  scope?: DiscoveryScope;
  limit?: number;
  projectId?: string | null;
}

export interface DiscoverySearchResponse {
  query: string;
  scope: DiscoveryScope;
  items: DiscoveredSourceCandidate[];
  providerErrors: string[];
}

export interface DiscoveryImportRequest {
  projectId?: string | null;
  items: DiscoveredSourceCandidate[];
  fetchFullText?: boolean;
}

export interface DiscoveryImportFailure {
  title: string;
  url: string;
  reason: string;
}

export interface DiscoveryImportResponse {
  documents: Document[];
  reusedCount: number;
  importedCount: number;
  failed: DiscoveryImportFailure[];
}
