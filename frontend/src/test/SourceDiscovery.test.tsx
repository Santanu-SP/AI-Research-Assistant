// @vitest-environment jsdom
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../app/ToastContext';
import { SourceDiscoveryDialog } from '../components/documents/SourceDiscoveryDialog';
import { NewResearch } from '../pages/NewResearch';
import { byokService } from '../services/clientAi.service';
import { discoveryService } from '../services/discovery.service';
import { documentsService } from '../services/documents.service';
import { researchService } from '../services/research.service';
import { DiscoveredSourceCandidate } from '../types/discovery';
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

  it('supports opting into trusted online auto-discovery with scope selection on NewResearch', async () => {
    const startSpy = vi
      .spyOn(researchService, 'startResearchJob')
      .mockResolvedValue({ id: 'res-auto-1' } as never);

    renderNewResearch();

    const questionInput = await screen.findByLabelText('Research question');
    fireEvent.change(questionInput, { target: { value: 'How does self-attention scale?' } });

    const startBtn = screen.getByRole('button', { name: /Start research/i });
    expect(screen.getByText('Upload or pick a document first')).toBeInTheDocument();
    expect(startBtn).toBeDisabled();

    const toggle = screen.getByRole('switch', { name: 'Enable trusted online discovery' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-checked', 'true');

    fireEvent.click(screen.getByRole('button', { name: 'Scholarly' }));
    expect(startBtn).toBeEnabled();
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

    const panel = screen.getByRole('region', { name: 'Documents for this research' });
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
});
