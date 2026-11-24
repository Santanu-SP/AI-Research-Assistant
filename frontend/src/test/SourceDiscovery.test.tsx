// @vitest-environment jsdom
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../app/ToastContext';
import { SourceDiscoveryDialog } from '../components/documents/SourceDiscoveryDialog';
import { ProgressStepper } from '../components/research/ProgressStepper';
import { NewResearch } from '../pages/NewResearch';
import { byokService } from '../services/clientAi.service';
import { discoveryService } from '../services/discovery.service';
import { documentsService } from '../services/documents.service';
import { QUERY_REQUEST_TIMEOUT_MS, researchService } from '../services/research.service';
import { DiscoveredSourceCandidate } from '../types/discovery';
import { ResearchProgressResponse } from '../types/progress';
import { makeDocument, makeDocumentList } from './fixtures';

const makeCandidate = (
  overrides: Partial<DiscoveredSourceCandidate> = {},
): DiscoveredSourceCandidate => ({
  candidateId: 'openalex-123',
  provider: 'openalex',
  trustTier: 'peer-reviewed',
  sourceType: 'openalex',
  contentLevel: 'full_text',
  title: 'Attention Is All You Need',
  authors: ['Ashish Vaswani', 'Noam Shazeer'],
  publicationYear: 2017,
  publisher: 'NeurIPS',
  abstract: 'The Transformer relies entirely on self-attention mechanisms.',
  doi: '10.5555/3295222.3295349',
  openalexId: 'W2626778328',
  crossrefId: null,
  url: 'https://papers.nips.cc/paper/7181-attention-is-all-you-need',
  openAccessPdfUrl: 'https://arxiv.org/pdf/1706.03762.pdf',
  citationCount: 98000,
  isOpenAccess: true,
  alreadyInLibrary: false,
  existingDocumentId: null,
  ...overrides,
});

const modelsStatus = {
  local: {
    provider: 'ollama',
    available: true,
    connected: false,
    baseUrl: 'http://127.0.0.1:11434',
    configuredModel: 'qwen3.5:9b',
    activeModel: 'qwen3.5:9b',
    installedModels: ['qwen3.5:9b'],
  },
  providers: [],
  routerOrder: [],
};

const renderNewResearch = () =>
  render(
    <MemoryRouter initialEntries={['/research/new']}>
      <ToastProvider>
        <Routes>
          <Route path="/research/new" element={<NewResearch />} />
          <Route path="/research/:id/progress" element={<p>Progress page</p>} />
        </Routes>
      </ToastProvider>
    </MemoryRouter>,
  );

describe('Controlled Discovery UI', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(byokService, 'getModelsStatus').mockResolvedValue(modelsStatus as never);
    vi.spyOn(documentsService, 'getDocuments').mockResolvedValue(makeDocumentList([]));
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('searches curated sources, renders trust/content badges, and imports selected documents', async () => {
    const candidate = makeCandidate();
    const abstractOnly = makeCandidate({
      candidateId: 'crossref-456',
      provider: 'crossref',
      sourceType: 'crossref',
      contentLevel: 'abstract',
      title: 'Clinical Evidence Synthesis',
      publisher: 'NEJM',
      publicationYear: 2024,
      openAccessPdfUrl: null,
      isOpenAccess: false,
      alreadyInLibrary: true,
      existingDocumentId: 'doc-existing',
    });
    const importedDoc = makeDocument({
      id: 'doc-imported-1',
      name: 'Attention Is All You Need',
      sourceType: 'openalex',
      contentLevel: 'full_text',
      doi: '10.5555/3295222.3295349',
    });

    const searchSpy = vi.spyOn(discoveryService, 'search').mockResolvedValue({
      query: 'transformer attention',
      scope: 'all',
      items: [candidate, abstractOnly],
      providerErrors: [],
    });
    const importSpy = vi.spyOn(discoveryService, 'importSources').mockResolvedValue({
      documents: [importedDoc],
      reusedCount: 0,
      importedCount: 1,
      failed: [],
    });
    const onImported = vi.fn();
    const onClose = vi.fn();

    render(
      <ToastProvider>
        <SourceDiscoveryDialog isOpen onClose={onClose} onImported={onImported} />
      </ToastProvider>,
    );

    const dialog = screen.getByRole('dialog', { name: 'Discover trusted sources' });
    const input = within(dialog).getByLabelText('Search trusted sources');
    fireEvent.change(input, { target: { value: 'transformer attention' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /^Search$/i }));

    await waitFor(() => expect(searchSpy).toHaveBeenCalledTimes(1));
    expect(searchSpy.mock.calls[0][0]).toMatchObject({ query: 'transformer attention', scope: 'all' });

    expect(await within(dialog).findByText('Attention Is All You Need')).toBeInTheDocument();
    expect(within(dialog).getByText('OpenAlex · Peer-reviewed')).toBeInTheDocument();
    expect(within(dialog).getByText('Open-access PDF')).toBeInTheDocument();
    expect(within(dialog).getByText('Abstract only')).toBeInTheDocument();
    expect(within(dialog).getByText('In library')).toBeInTheDocument();

    const firstRow = within(dialog).getAllByRole('checkbox')[0];
    fireEvent.click(firstRow);

    const importBtn = within(dialog).getByRole('button', { name: 'Import 1 source' });
    fireEvent.click(importBtn);

    await waitFor(() => expect(importSpy).toHaveBeenCalledTimes(1));
    expect(importSpy.mock.calls[0][0]).toEqual([candidate]);
    expect(onImported).toHaveBeenCalledWith([importedDoc]);
    expect(onClose).toHaveBeenCalled();
  });

  it('labels news articles as news from their publisher', async () => {
    const news = makeCandidate({
      candidateId: 'news-1',
      provider: 'news',
      trustTier: 'news',
      sourceType: 'web_page',
      contentLevel: 'web_page',
      title: 'Strikes reported overnight',
      publisher: 'Reuters',
      authors: [],
      doi: null,
      openalexId: null,
      openAccessPdfUrl: null,
      citationCount: null,
      url: 'https://www.reuters.com/world/strikes',
    });
    const wiki = makeCandidate({
      candidateId: 'wiki-1',
      provider: 'wikipedia',
      trustTier: 'institutional',
      sourceType: 'web_page',
      contentLevel: 'web_page',
      title: 'Proxy conflict',
      publisher: 'Wikipedia',
      authors: [],
      doi: null,
      openalexId: null,
      openAccessPdfUrl: null,
      citationCount: null,
      url: 'https://en.wikipedia.org/wiki/Proxy_conflict',
    });
    vi.spyOn(discoveryService, 'search').mockResolvedValue({
      query: 'strikes',
      scope: 'all',
      items: [news, wiki],
      providerErrors: [],
    });

    render(
      <ToastProvider>
        <SourceDiscoveryDialog isOpen onClose={vi.fn()} onImported={vi.fn()} />
      </ToastProvider>,
    );

    const dialog = screen.getByRole('dialog', { name: 'Discover trusted sources' });
    fireEvent.change(within(dialog).getByLabelText('Search trusted sources'), {
      target: { value: 'strikes' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: /^Search$/i }));

    expect(await within(dialog).findByText('Reuters · News')).toBeInTheDocument();
    expect(within(dialog).getByText('Wikipedia · Encyclopedia')).toBeInTheDocument();
  });

  it('supports opting into trusted online auto-discovery with scope selection on NewResearch', async () => {
    const startSpy = vi
      .spyOn(researchService, 'startResearchJob')
      .mockResolvedValue({ id: 'res-auto-1' } as never);

    renderNewResearch();

    const questionInput = await screen.findByLabelText('Research question');
    fireEvent.change(questionInput, { target: { value: 'How does self-attention scale?' } });

    const startBtn = screen.getByRole('button', { name: /Start research/i });
    expect(screen.getByText('Add a file first: upload one or pick from your Library')).toBeInTheDocument();
    expect(startBtn).toHaveAttribute('aria-disabled', 'true');

    const toggle = screen.getByRole('switch', { name: 'Enable trusted online discovery' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-checked', 'true');

    fireEvent.click(screen.getByRole('button', { name: 'Scholarly' }));
    expect(startBtn).toBeEnabled();
    expect(startBtn).not.toHaveAttribute('aria-disabled');
    fireEvent.click(startBtn);

    await waitFor(() => expect(startSpy).toHaveBeenCalledTimes(1));
    expect(startSpy.mock.calls[0][0]).toMatchObject({
      query: 'How does self-attention scale?',
      autoDiscover: true,
      discoveryScope: 'scholarly',
    });
    expect(startSpy.mock.calls[0][0].documentIds).toBeUndefined();
    expect(await screen.findByText('Progress page')).toBeInTheDocument();
  });

  it('discovers and attaches curated sources directly into a new research run', async () => {
    const candidate = makeCandidate();
    const importedDoc = makeDocument({
      id: 'doc-discovered-attached',
      name: 'Attention Is All You Need',
      title: 'Attention Is All You Need',
      sourceType: 'openalex',
      contentLevel: 'full_text',
    });
    vi.spyOn(discoveryService, 'search').mockResolvedValue({
      query: 'Attention paper',
      scope: 'all',
      items: [candidate],
      providerErrors: [],
    });
    vi.spyOn(discoveryService, 'importSources').mockResolvedValue({
      documents: [importedDoc],
      reusedCount: 0,
      importedCount: 1,
      failed: [],
    });
    const startSpy = vi
      .spyOn(researchService, 'startResearchJob')
      .mockResolvedValue({ id: 'res-disc-1' } as never);

    renderNewResearch();

    const discoverBtn = await screen.findByRole('button', { name: /Discover/i });
    fireEvent.click(discoverBtn);

    const dialog = await screen.findByRole('dialog', { name: 'Discover trusted sources' });
    fireEvent.change(within(dialog).getByLabelText('Search trusted sources'), {
      target: { value: 'Attention paper' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: /^Search$/i }));
    await within(dialog).findByText('Attention Is All You Need');
    fireEvent.click(within(dialog).getAllByRole('checkbox')[0]);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Import 1 source' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

    const panel = screen.getByRole('region', { name: 'Files for this research' });
    expect(within(panel).getByText('Attention Is All You Need')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Research question'), {
      target: { value: 'What did Vaswani et al. introduce?' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Start research/i }));

    await waitFor(() => expect(startSpy).toHaveBeenCalledTimes(1));
    expect(startSpy.mock.calls[0][0]).toMatchObject({
      query: 'What did Vaswani et al. introduce?',
      documentIds: ['doc-discovered-attached'],
    });
    expect(await screen.findByText('Progress page')).toBeInTheDocument();
  });

  it('runs Low effort auto-discovery as a background job instead of waiting on the request', async () => {
    const startSpy = vi
      .spyOn(researchService, 'startResearchJob')
      .mockResolvedValue({ id: 'res-auto-quick' } as never);
    const querySpy = vi.spyOn(researchService, 'queryResearch');

    renderNewResearch();

    fireEvent.change(await screen.findByLabelText('Research question'), {
      target: { value: 'How does self-attention scale?' },
    });
    fireEvent.click(screen.getByRole('switch', { name: 'Enable trusted online discovery' }));
    fireEvent.click(screen.getByRole('button', { name: 'Models' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Auto Low' }));
    fireEvent.click(screen.getByRole('button', { name: /Start research/i }));

    await waitFor(() => expect(startSpy).toHaveBeenCalledTimes(1));
    expect(startSpy.mock.calls[0][0]).toMatchObject({ researchDepth: 'quick', autoDiscover: true });
    expect(querySpy).not.toHaveBeenCalled();
    expect(await screen.findByText('Progress page')).toBeInTheDocument();
  });

  it('shows the finding sources step in plain words on the progress page', () => {
    const progress = {
      id: 'res-auto-1',
      question: 'How does self-attention scale?',
      status: 'researching',
      researchDepth: 'standard',
      currentStage: 'searching_sources',
      currentStepIndex: 1,
      totalSteps: 5,
      steps: [
        { id: 'planning', title: 'Planning research', status: 'completed' },
        { id: 'searching_sources', title: 'Finding sources', status: 'active' },
        { id: 'finding_documents', title: 'Reading the sources found', status: 'pending' },
        { id: 'reviewing_evidence', title: 'Reviewing evidence', status: 'pending' },
        { id: 'building_synthesis', title: 'Building synthesis', status: 'pending' },
      ],
      sourcesDiscovered: 0,
      sourcesReviewed: 0,
      documentsFound: 0,
      startedAt: null,
      stageStartedAt: null,
      updatedAt: '2026-11-18T00:00:00Z',
      completedAt: null,
      failedAt: null,
      autoDiscover: true,
    } as ResearchProgressResponse;

    render(<ProgressStepper progress={progress} />);

    expect(screen.getByText('Finding sources')).toBeInTheDocument();
    expect(
      screen.getByText('Searching OpenAlex, Crossref, arXiv and Wikipedia for trusted sources.'),
    ).toBeInTheDocument();
    expect(screen.getByText(/Downloading and reading the sources it found/)).toBeInTheDocument();
    expect(screen.queryByText('Looking through your files for relevant passages.')).not.toBeInTheDocument();
  });

  it('uses the extended timeout when starting auto-discovery background research jobs', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 202,
      statusText: 'Accepted',
      json: () => Promise.resolve({ id: 'job-auto-1' }),
      text: () => Promise.resolve(JSON.stringify({ id: 'job-auto-1' })),
    });
    vi.stubGlobal('fetch', fetchMock);

    await researchService.startResearchJob({
      query: 'Lithium carbonate mechanism of action',
      autoDiscover: true,
      discoveryScope: 'all',
    });
    expect(QUERY_REQUEST_TIMEOUT_MS).toBeGreaterThanOrEqual(5 * 60_000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/research\/jobs$/);
    expect(JSON.parse(String(init.body))).toMatchObject({ autoDiscover: true });
    vi.unstubAllGlobals();
  });
});
