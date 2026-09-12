export type ResearchStatus = 'completed' | 'researching' | 'draft' | 'failed';
export type ResearchDepth = 'quick' | 'standard' | 'deep';

export interface Research {
  id: string;
  title: string;
  question: string;
  domain: string;
  status: ResearchStatus;
  researchDepth: ResearchDepth;
  sourceCount: number;
  createdAt: string;
  updatedAt: string;
  description?: string;
}

export interface ResearchProgress {
  id: string;
  question: string;
  dossierRef: string;
  depth: ResearchDepth;
  startedAt: string;
  currentStepIndex: number;
  totalSteps: number;
  currentStepTitle: string;
  currentStepDescription?: string;
  steps: {
    id: string;
    number: string;
    title: string;
    status: 'completed' | 'active' | 'pending';
    detail: string;
  }[];
  sourcesDiscovered: number;
  sourcesReviewed: number;
  webAcademicCount: number;
  uploadedDocumentsCount: number;
  liveEvidence: {
    id: string;
    publisher: string;
    year: number;
    title: string;
    excerpt: string;
    statusTag: string;
    identifierLabel?: string;
    identifierValue?: string;
    authors?: string;
  }[];
  discoveredSources: {
    id: string;
    title: string;
    publisher: string;
    year: number;
    sourceType: string;
    authors: string;
  }[];
  ingestingQueueCount: number;
}

export interface ResearchSection {
  id: string;
  heading: string;
  content: string;
  quote?: string;
  citationIds: number[];
}

export interface ResearchReport {
  id: string;
  title: string;
  summary: string;
  dossierRef: string;
  readingTimeMinutes: number;
  sourceCount: number;
  status: ResearchStatus;
  sections: ResearchSection[];
  createdAt: string;
  updatedAt: string;
}
