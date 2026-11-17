// @vitest-environment jsdom
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ResearchResponse } from '../types/research';

vi.mock('../app/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', name: 'Shubham Rai', email: 'shubham@example.com', isActive: true, createdAt: '2026-09-01T00:00:00Z', updatedAt: '2026-09-01T00:00:00Z' },
    loading: false,
    logout: vi.fn(),
  }),
}));

import { ToastProvider } from '../app/ToastContext';
import { ResearchHistoryProvider } from '../app/ResearchHistoryContext';
import { AppSidebar } from '../components/layout/AppSidebar';
import { researchService } from '../services/research.service';

const item: ResearchResponse = {
  id: 'r1',
  title: 'Cool roofs and surface temperature',
  question: 'Do cool roofs lower surface temperature?',
  domain: null,
  status: 'completed',
  researchDepth: 'standard',
  sourceCount: 2,
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
  archivedAt: null,
};

const renderSidebar = () =>
  render(
    <MemoryRouter initialEntries={['/projects']}>
      <ToastProvider>
        <ResearchHistoryProvider>
          <AppSidebar />
        </ResearchHistoryProvider>
      </ToastProvider>
    </MemoryRouter>,
  );

describe('Deleting a research', () => {
  beforeEach(() => {
    vi.spyOn(researchService, 'listResearch').mockResolvedValue({ items: [item], total: 1, limit: 100, offset: 0 });
    vi.spyOn(researchService, 'archiveResearch').mockResolvedValue(undefined);
    vi.spyOn(researchService, 'restoreResearch').mockResolvedValue(item);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('offers Undo, which brings the research back', async () => {
    renderSidebar();
    fireEvent.click(await screen.findByRole('button', { name: `Options for ${item.title}` }));
    fireEvent.click(screen.getByRole('menuitem', { name: /Delete/ }));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(researchService.archiveResearch).toHaveBeenCalledWith('r1'));
    expect(await screen.findByText('Research deleted')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('link', { name: new RegExp(item.title) })).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    await waitFor(() => expect(researchService.restoreResearch).toHaveBeenCalledWith('r1'));
    expect(await screen.findByRole('link', { name: new RegExp(item.title) })).toBeInTheDocument();
    expect(screen.queryByText('Research deleted')).not.toBeInTheDocument();
  });
});
