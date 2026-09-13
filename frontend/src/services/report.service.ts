import { apiRequest } from './api';
import { ComposedReportResponse } from '../types/report';

export const reportService = {
  /**
   * Fetch research report
   * GET /api/v1/research/{id}/report
   */
  async getResearchReport(id: string): Promise<ComposedReportResponse> {
    return apiRequest<ComposedReportResponse>(`/research/${id}/report`);
  },
};
