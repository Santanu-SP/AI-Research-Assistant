import {
  Research,
  ResearchProgress,
  ResearchReport,
  ResearchDepth,
} from '../types/research';
import { Source } from '../types/source';
import {
  mockResearchList,
  mockActiveInvestigationProgress,
  mockFlagshipReport,
  mockFlagshipSources,
} from '../data/mockResearch';
// In-memory frontend state for demonstrations
let currentResearchList: Research[] = [...mockResearchList];

export const researchService = {
  /**
   * Fetch list of all research projects.
   * Future: GET /api/v1/research
   */
  async getResearchList(): Promise<Research[]> {
    return Promise.resolve([...currentResearchList]);
  },

  /**
   * Fetch single research project by ID.
   * Future: GET /api/v1/research/{id}
   */
  async getResearchById(id: string): Promise<Research | undefined> {
    const item = currentResearchList.find((r) => r.id === id);
    return Promise.resolve(item);
  },

  /**
   * Start a new research investigation.
   * Future: POST /api/v1/research
   */
  async startResearch(payload: {
    question: string;
    depth: ResearchDepth;
    includeWeb: boolean;
    includeDocs: boolean;
  }): Promise<{ id: string }> {
    const newId = `res-${Date.now().toString(36)}`;
    const newResearch: Research = {
      id: newId,
      title: payload.question.slice(0, 70),
      question: payload.question,
      domain: 'General Investigation',
      status: 'researching',
      researchDepth: payload.depth,
      sourceCount: payload.includeDocs ? 12 : 8,
      createdAt: new Date().toISOString(),
      updatedAt: 'Just now',
      description: payload.question,
    };

    currentResearchList = [newResearch, ...currentResearchList];
    return Promise.resolve({ id: newId });
  },

  /**
   * Fetch research progress / status for active investigations.
   * Future: GET /api/v1/research/{id}/status
   */
  async getResearchProgress(id: string): Promise<ResearchProgress> {
    const item = currentResearchList.find((r) => r.id === id);
    return Promise.resolve({
      ...mockActiveInvestigationProgress,
      id,
      question: item?.question || mockActiveInvestigationProgress.question,
    });
  },

  /**
   * Fetch finalized synthesis report.
   * Future: GET /api/v1/research/{id}/report
   */
  async getResearchReport(
    id: string
  ): Promise<{ report: ResearchReport; sources: Source[] }> {
    const item = currentResearchList.find((r) => r.id === id);
    const report: ResearchReport = {
      ...mockFlagshipReport,
      id,
      title: item?.title || mockFlagshipReport.title,
    };
    return Promise.resolve({
      report,
      sources: mockFlagshipSources,
    });
  },
};
