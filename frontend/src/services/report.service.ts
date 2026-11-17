import { apiRequest } from './api';
import {
  ComposedReportResponse,
  ReportFollowupCreateResponse,
  ReportFollowupRequest,
} from '../types/report';
import { QUERY_REQUEST_TIMEOUT_MS } from './research.service';

export const reportService = {
  async getResearchReport(id: string): Promise<ComposedReportResponse> {
    return apiRequest<ComposedReportResponse>(`/research/${id}/report`);
  },

  async askFollowup(
    researchId: string,
    payload: ReportFollowupRequest,
  ): Promise<ReportFollowupCreateResponse> {
    try {
      return await apiRequest<ReportFollowupCreateResponse>(`/research/${researchId}/followups`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        timeoutMs: QUERY_REQUEST_TIMEOUT_MS,
      });
    } finally {
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new Event('models-usage:refresh'));
      }
    }
  },
};
