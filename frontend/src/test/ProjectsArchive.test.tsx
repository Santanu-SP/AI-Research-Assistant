// @vitest-environment jsdom
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ResearchProject } from '../types/project';

vi.mock('../app/ToastContext', () => ({ useToast: () => ({ addToast: vi.fn() }) }));
vi.mock('../app/ProjectContext', () => ({ useProject: () => ({ selectProject: vi.fn() }) }));

import { projectsService } from '../services/projects.service';
import { ProjectsPage } from '../pages/Projects';

const project = (id: string, name: string, archivedAt: string | null = null): ResearchProject => ({
  id,
  name,
  description: null,
  archivedAt,
  createdAt: '2026-10-01T10:00:00Z',
  updatedAt: '2026-11-10T10:00:00Z',
});

const items = [
  { ...project('a1', 'Thesis draft'), fileCount: 3, reportCount: 1 },
  project('a2', 'RAG survey'),
  project('z1', 'Old semester notes', '2026-11-01T10:00:00Z'),
  project('z2', 'Climate datasets', '2026-11-12T10:00:00Z'),
];

const renderPage = (path = '/projects?view=archived') =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <ProjectsPage />
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.spyOn(projectsService, 'listProjects').mockResolvedValue({ items, total: items.length, limit: 100, offset: 0 });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('Projects archive', () => {
  it('shows active and archived counts in tabs and lists archived projects newest first', async () => {
    renderPage();
    const list = await screen.findByRole('list', { name: 'Archived projects' });
    expect(within(list).getAllByRole('heading').map((h) => h.textContent)).toEqual(['Climate datasets', 'Old semester notes']);
    expect(screen.getByRole('tab', { name: /Active\s*2/ })).toHaveAttribute('aria-selected', 'false');
    expect(screen.getByRole('tab', { name: /Archived\s*2/ })).toHaveAttribute('aria-selected', 'true');
    expect(projectsService.listProjects).toHaveBeenCalledWith(expect.objectContaining({ includeArchived: true }));
  });

  it('opens the actions menu, closes it with Escape and on an outside click', async () => {
    renderPage();
    const trigger = await screen.findByRole('button', { name: 'Actions for Climate datasets' });
    fireEvent.click(trigger);
    expect(await screen.findByRole('menuitem', { name: 'Delete permanently' })).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());

    fireEvent.click(trigger);
    await screen.findByRole('menu');
    fireEvent.pointerDown(document.body);
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
  });

  it('restores a project back to the active list', async () => {
    const restore = vi
      .spyOn(projectsService, 'restoreProject')
      .mockResolvedValue({ ...items[3], archivedAt: null });
    renderPage();
    const list = await screen.findByRole('list', { name: 'Archived projects' });
    const row = within(list).getByText('Climate datasets').closest('li') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: 'Restore' }));

    await waitFor(() => expect(restore).toHaveBeenCalledWith('z2'));
    await waitFor(() => expect(screen.getByRole('tab', { name: /Archived\s*1/ })).toBeInTheDocument());
    expect(screen.getByRole('tab', { name: /Active\s*3/ })).toBeInTheDocument();
  });

  it('deletes a project permanently only after confirming', async () => {
    const remove = vi.spyOn(projectsService, 'deleteProjectPermanently').mockResolvedValue();
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Actions for Old semester notes' }));
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete permanently' }));

    const dialog = await screen.findByRole('alertdialog');
    expect(remove).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete permanently' }));

    await waitFor(() => expect(remove).toHaveBeenCalledWith('z1'));
    await waitFor(() => expect(screen.queryByText('Old semester notes')).not.toBeInTheDocument());
  });

  it('shows a friendly empty state when nothing is archived', async () => {
    vi.mocked(projectsService.listProjects).mockResolvedValue({ items: items.slice(0, 2), total: 2, limit: 100, offset: 0 });
    renderPage();
    expect(await screen.findByText('No archived projects')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Back to projects' }));
    expect(await screen.findByText('Thesis draft')).toBeInTheDocument();
  });

  it('keeps the active project menu working', async () => {
    renderPage('/projects');
    fireEvent.click(await screen.findByRole('button', { name: 'Actions for RAG survey' }));
    const menu = await screen.findByRole('menu');
    expect(within(menu).getAllByRole('menuitem').map((item) => item.textContent)).toEqual([
      'Open project',
      'Rename or edit',
      'Archive project',
    ]);
  });

  it('shows how many files and reports each project has', async () => {
    renderPage('/projects');
    expect(await screen.findByText('3 files · 1 report')).toBeInTheDocument();
    // Projects without counts from the server simply skip the line.
    expect(screen.queryByText(/0 files/)).not.toBeInTheDocument();
  });
});
