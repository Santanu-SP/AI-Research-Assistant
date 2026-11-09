import { apiRequest } from './api';
import { ComposedReportResponse } from '../types/report';

export const reportService = {
  async getResearchReport(id: string): Promise<ComposedReportResponse> {
    return apiRequest<ComposedReportResponse>(`/research/${id}/report`);
  },
};
