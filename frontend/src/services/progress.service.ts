import { apiRequest } from './api';
import { ResearchProgressResponse } from '../types/progress';

export const progressService = {
  /**
   * Fetch research progress / status for active investigations.
   * GET /api/v1/research/{id}/status
   */
  async getResearchProgress(id: string): Promise<ResearchProgressResponse> {
    return apiRequest<ResearchProgressResponse>(`/research/${id}/status`);
  },
};
