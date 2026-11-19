// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../app/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'u1',
      name: 'Researcher',
      email: 'researcher@example.com',
      isActive: true,
      createdAt: '2026-11-18T00:00:00Z',
      updatedAt: '2026-11-18T00:00:00Z',
    },
    logout: vi.fn(),
    logoutAll: vi.fn(),
  }),
}));

import { ResearchReportPage } from '../pages/ResearchReport';
import { reportService } from '../services/report.service';
import { byokService } from '../services/clientAi.service';
import type { SourceResponse } from '../types/report';

const makeSource = (overrides: Partial<SourceResponse> = {}): SourceResponse => ({
  id: 'src-default',
  number: 1,
  title: 'Default Source',
  publisher: 'Journal of Psychiatry',
  authors: ['Dr. A. Sharma'],
  year: 2025,
  url: 'https://doi.org/10.1000/lithium',
  sourceType: 'peer-reviewed',
  relevantExcerpt: 'Lithium inhibits inositol monophosphatase.',
  citationCount: 1,
  doi: '10.1000/lithium',
  bibtex: null,
  documentId: 'doc-1',
  chunkId: 'chunk-1',
  page: 2,
  section: 'Mechanism',
  rerankScore: 0.9,
  createdAt: '2026-11-18T00:00:00Z',
  updatedAt: '2026-11-18T00:00:00Z',
  ...overrides,
});

const modelsStatus = {
  local: {
    provider: 'ollama',
    available: false,
    connected: false,
    baseUrl: 'http://127.0.0.1:11434',
    configuredModel: 'qwen3.5:9b',
    installedModels: [],
  },
  providers: [
    {
      id: 'gemini',
      label: 'Gemini',
      configuredServer: true,
      configuredByok: false,
      configured: true,
      defaultModel: 'gemini-3.8-flash',
      isLocal: false,
      available: true,
    },
  ],
  routerOrder: ['gemini'],
  usage: {
    overallRemainingPct: 95,
    shortWindowHours: 3,
    longWindowDays: 2,
    shortCreditsPerModel: 20,
    longCreditsPerModel: 100,
    shortResetsAt: '2026-11-18T03:00:00Z',
    longResetsAt: '2026-11-20T00:00:00Z',
    providerCredits: [
      {
        provider: 'gemini',
        label: 'Gemini',
        modelName: 'gemini-3.8-flash',
        mode: 'shared',
        unlimited: false,
        remainingPct: 95,
        shortWindowPct: 95,
        longWindowPct: 99,
        shortResetsAt: '2026-11-18T03:00:00Z',
        longResetsAt: '2026-11-20T00:00:00Z',
        shortRemaining: 19,
        shortCap: 20,
        longRemaining: 99,
        longCap: 100,
      },
    ],
    enrolledUsers: 1,
    sharedRequestsUsedToday: 1,
    userDailyRequestCap: 20,
    userRequestsRemainingToday: 19,
    systemPoolTotal: 100,
    systemPoolUsedToday: 1,
    systemPoolRemaining: 99,
    byokRequestsToday: 0,
    localRequestsToday: 0,
    totalRequestsToday: 1,
    totalTokensToday: 200,
    totalRequestsAllTime: 1,
    totalTokensAllTime: 200,
    resetsAt: '2026-11-18T03:00:00Z',
    models: [],
  },
};

const renderReport = () =>
  render(
    <MemoryRouter initialEntries={['/research/res-1/report']}>
      <Routes>
        <Route path="/research/:id/report" element={<ResearchReportPage />} />
      </Routes>
    </MemoryRouter>,
  );

describe('ResearchReportPage follow-up questions', () => {
  let getModelsSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
    getModelsSpy = vi
      .spyOn(byokService, 'getModelsStatus')
      .mockResolvedValue(modelsStatus as never);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('renders saved followups and appends new grounded followup answers with updated sources', async () => {
    const source1 = makeSource({ id: 'src-1', number: 1, title: 'Lithium Clinical Trial' });
    const source2 = makeSource({ id: 'src-2', number: 2, title: 'Lithium Renal Safety' });

    vi.spyOn(reportService, 'getResearchReport').mockResolvedValue({
      report: {
        id: 'rep-1',
        researchId: 'res-1',
        title: 'Lithium Carbonate Overview',
        summary: 'Lithium stabilizes mood by modulating second-messenger pathways [S1].',
        dossierRef: 'LOCAL RAG · RES1',
        readingTimeMinutes: 2,
        sourceCount: 1,
        status: 'completed',
        version: 1,
        sections: [
          {
            id: 'sec-1',
            heading: 'Grounded answer',
            content: 'Lithium stabilizes mood by modulating second-messenger pathways [S1].',
            quote: null,
            position: 0,
            citationIds: [1],
            citations: [{ id: 'cit-1', sourceId: 'src-1', number: 1, position: 0 }],
            createdAt: '2026-11-18T00:00:00Z',
            updatedAt: '2026-11-18T00:00:00Z',
          },
        ],
        createdAt: '2026-11-18T00:00:00Z',
        updatedAt: '2026-11-18T00:00:00Z',
      },
      sources: [source1],
      followups: [
        {
          id: 'fu-0',
          reportId: 'rep-1',
          question: 'Which enzyme does it inhibit?',
          answer: 'It inhibits inositol monophosphatase [S1].',
          citationIds: [1],
          position: 0,
          provider: 'gemini',
          model: 'gemini-3.8-flash',
          insufficientEvidence: false,
          createdAt: '2026-11-18T00:05:00Z',
          updatedAt: '2026-11-18T00:05:00Z',
        },
      ],
    });

    const askSpy = vi.spyOn(reportService, 'askFollowup').mockResolvedValue({
      followup: {
        id: 'fu-1',
        reportId: 'rep-1',
        question: 'What serum range should be monitored?',
        answer: 'Typical maintenance range is 0.6 to 1.0 mmol/L [S2].',
        citationIds: [2],
        position: 1,
        provider: 'gemini',
        model: 'gemini-3.8-flash',
        insufficientEvidence: false,
        createdAt: '2026-11-18T00:06:00Z',
        updatedAt: '2026-11-18T00:06:00Z',
      },
      sources: [source1, source2],
      creditCost: 0.25,
    });

    renderReport();

    expect(await screen.findByText('Follow-up questions')).toBeInTheDocument();
    await waitFor(() => expect(getModelsSpy).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.getByText('Uses report memory · 0.25× credits')).toBeInTheDocument();
    expect(screen.getByText('Which enzyme does it inhibit?')).toBeInTheDocument();
    expect(screen.getByText(/It inhibits inositol monophosphatase/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Follow-up question'), {
      target: { value: 'What serum range should be monitored?' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Ask follow-up' }));

    await waitFor(() => {
      expect(askSpy).toHaveBeenCalledWith('res-1', {
        question: 'What serum range should be monitored?',
        localFallbackEnabled: false,
      });
    });

    expect(await screen.findByText('What serum range should be monitored?')).toBeInTheDocument();
    expect(screen.getByText(/Typical maintenance range is 0\.6 to 1\.0 mmol\/L/)).toBeInTheDocument();
    expect(screen.getByText('Lithium Renal Safety')).toBeInTheDocument();
  });
});
