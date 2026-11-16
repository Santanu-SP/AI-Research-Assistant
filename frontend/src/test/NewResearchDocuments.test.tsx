// @vitest-environment jsdom
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../app/ToastContext';
import { NewResearch } from '../pages/NewResearch';
import { byokService } from '../services/clientAi.service';
import { documentsService } from '../services/documents.service';
import { researchService } from '../services/research.service';
import { documentsBlockedReason } from '../lib/researchDocuments';
import { makeDocument, makeDocumentList } from './fixtures';

const marketing = makeDocument({ id: 'doc-marketing', name: 'Digital_Marketing.pdf', title: null });
const mcp = makeDocument({ id: 'doc-mcp', name: 'MCP_A2A_Master_Document.docx', title: null });

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

const renderPage = () =>
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

const startButton = () => screen.getByRole('button', { name: /Start research/i });

describe('New research documents', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(byokService, 'getModelsStatus').mockResolvedValue(modelsStatus as never);
    vi.spyOn(documentsService, 'getDocuments').mockResolvedValue(makeDocumentList([marketing, mcp]));
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('starts with no documents and asks for one before sending', async () => {
    renderPage();
    const panel = await screen.findByRole('region', { name: 'Documents for this research' });
    expect(await within(panel).findByRole('button', { name: /Add from library/i })).toBeInTheDocument();
    // Earlier uploads are not listed or used until picked.
    expect(screen.queryByText('Digital_Marketing.pdf')).not.toBeInTheDocument();
    expect(screen.queryByText('MCP_A2A_Master_Document.docx')).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Research question'), { target: { value: 'What is SEO?' } });
    expect(screen.getByText('Upload or pick a document first')).toBeInTheDocument();
    expect(startButton()).toBeDisabled();
  });

  it('sends only the picked documents with the question', async () => {
    const start = vi.spyOn(researchService, 'startResearchJob').mockResolvedValue({ id: 'res-9' } as never);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /Add from library/i }));

    const dialog = await screen.findByRole('dialog', { name: 'Add from your library' });
    fireEvent.click(within(dialog).getByText('Digital_Marketing.pdf'));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Use these' }));

    const panel = screen.getByRole('region', { name: 'Documents for this research' });
    expect(within(panel).getByText('Digital_Marketing.pdf')).toBeInTheDocument();
    expect(within(panel).queryByText('MCP_A2A_Master_Document.docx')).not.toBeInTheDocument();
    expect(within(panel).getByText('1 ready')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Research question'), { target: { value: 'What is SEO?' } });
    expect(startButton()).toBeEnabled();
    fireEvent.click(startButton());

    await waitFor(() => expect(start).toHaveBeenCalledTimes(1));
    expect(start.mock.calls[0][0]).toMatchObject({ query: 'What is SEO?', documentIds: ['doc-marketing'] });
    expect(await screen.findByText('Progress page')).toBeInTheDocument();
  });

  it('removing the last document blocks sending again', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: /Add from library/i }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByText('MCP_A2A_Master_Document.docx'));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Use these' }));

    fireEvent.click(
      screen.getByRole('button', { name: 'Remove from this research: MCP_A2A_Master_Document.docx' }),
    );
    expect(screen.queryByText('MCP_A2A_Master_Document.docx')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Research question'), { target: { value: 'Anything?' } });
    expect(startButton()).toBeDisabled();
  });
});

describe('documentsBlockedReason', () => {
  it('explains what is missing', () => {
    const ready = makeDocument({ id: 'a', status: 'indexed' });
    const preparing = makeDocument({ id: 'b', status: 'processing' });
    const failed = makeDocument({ id: 'c', status: 'failed' });
    expect(documentsBlockedReason([], 0)).toBe('Upload or pick a document first');
    expect(documentsBlockedReason([preparing], 1)).toBe('Your documents are still being prepared');
    // Just uploaded and not in the list yet.
    expect(documentsBlockedReason([], 1)).toBe('Your documents are still being prepared');
    expect(documentsBlockedReason([failed], 1)).toMatch(/could be read/);
    expect(documentsBlockedReason([ready, preparing], 2)).toBeNull();
  });
});
