import { apiRequest } from './api';
import { ResearchProgressResponse } from '../types/progress';

export const progressService = {
  async getResearchProgress(id: string): Promise<ResearchProgressResponse> {
    return apiRequest<ResearchProgressResponse>(`/research/${id}/status`);
  },
};
