export type ResearchStatus = 'completed' | 'researching' | 'draft' | 'failed';
export type ResearchDepth = 'quick' | 'standard' | 'deep';
export type ResearchProgressStage = 'PLANNING' | 'SEARCHING' | 'EXTRACTING' | 'SYNTHESIZING' | 'FINALIZING';
export type ResearchProgressStepStatus = 'completed' | 'active' | 'pending';

export interface ResearchProgressStep {
  id: ResearchProgressStage;
  title: string;
  status: ResearchProgressStepStatus;
}

export interface ResearchProgressResponse {
  id: string;
  question: string;
  status: ResearchStatus;
  researchDepth: ResearchDepth;
  currentStage: ResearchProgressStage | null;
  currentStepIndex: number | null;
  totalSteps: number;
  steps: ResearchProgressStep[];
  sourcesDiscovered: number;
  sourcesReviewed: number;
  documentsFound: number;
  startedAt: string | null;
  stageStartedAt: string | null;
  updatedAt: string;
  completedAt: string | null;
  failedAt: string | null;
}
