// @vitest-environment jsdom
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../app/ToastContext';
import { LibraryPage } from '../pages/Library';
import { documentsService } from '../services/documents.service';
import { makeDocument, makeDocumentList } from './fixtures';

const used = makeDocument({
  id: 'doc-used',
  name: 'survey.pdf',
  title: null,
  projectId: 'proj-1',
  projectName: 'Thesis',
  usedIn: [{ id: 'run-1', title: 'Survey review' }],
  usedInCount: 3,
});
const unused = makeDocument({ id: 'doc-unused', name: 'notes.pdf', title: null, projectId: null });

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={['/library']}>
      <ToastProvider>
        <LibraryPage />
      </ToastProvider>
    </MemoryRouter>,
  );

describe('Library page', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(documentsService, 'getDocuments').mockResolvedValue(makeDocumentList([used, unused]));
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('shows where each file is used', async () => {
    renderPage();
    const row = (await screen.findByText('survey.pdf')).closest('[data-document-id]') as HTMLElement;
    expect(within(row).getByRole('link', { name: 'Thesis' })).toHaveAttribute('href', '/projects/proj-1');
    expect(within(row).getByRole('link', { name: 'Survey review' })).toHaveAttribute('href', '/research/run-1');
    expect(within(row).getByText('+2 more')).toBeInTheDocument();
    const other = screen.getByText('notes.pdf').closest('[data-document-id]') as HTMLElement;
    expect(within(other).getByText(/Not used in any project or research yet/)).toBeInTheDocument();
  });

  it('asks the server for the chosen file type and search', async () => {
    const getDocuments = vi.mocked(documentsService.getDocuments);
    renderPage();
    await screen.findByText('survey.pdf');

    fireEvent.click(screen.getByRole('button', { name: 'Images' }));
    await waitFor(() =>
      expect(getDocuments).toHaveBeenLastCalledWith(expect.objectContaining({ kind: 'images' }), expect.anything()),
    );
    expect(screen.getByRole('button', { name: 'Images' })).toHaveAttribute('aria-pressed', 'true');

    fireEvent.change(screen.getByRole('searchbox', { name: 'Search files' }), { target: { value: 'survey' } });
    await waitFor(() =>
      expect(getDocuments).toHaveBeenLastCalledWith(
        expect.objectContaining({ kind: 'images', search: 'survey' }),
        expect.anything(),
      ),
    );
  });

  it('offers to clear filters when nothing matches', async () => {
    renderPage();
    await screen.findByText('survey.pdf');
    vi.mocked(documentsService.getDocuments).mockResolvedValue(makeDocumentList([]));
    fireEvent.click(screen.getByRole('button', { name: 'Video' }));
    expect(await screen.findByText('No files match')).toBeInTheDocument();
    vi.mocked(documentsService.getDocuments).mockResolvedValue(makeDocumentList([used, unused]));
    fireEvent.click(screen.getByRole('button', { name: 'Clear search and filters' }));
    expect(await screen.findByText('survey.pdf')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'true');
  });
});
