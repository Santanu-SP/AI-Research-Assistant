// @vitest-environment jsdom
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../app/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', name: 'Shubham Rai', email: 'shubham@example.com', isActive: true, createdAt: '2026-09-01T00:00:00Z', updatedAt: '2026-09-01T00:00:00Z' },
    loading: false,
    logout: vi.fn(),
  }),
}));

vi.mock('../app/ToastContext', () => ({ useToast: () => ({ addToast: vi.fn() }) }));

vi.mock('../app/ResearchHistoryContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../app/ResearchHistoryContext')>();
  return {
    ...actual,
    useResearchHistory: () => ({
      items: [],
      total: 0,
      loading: false,
      error: false,
      complete: true,
      reload: vi.fn(),
      rename: vi.fn(),
      remove: vi.fn(),
    }),
  };
});

import { activeSection } from '../lib/navigation';
import { AppSidebar } from '../components/layout/AppSidebar';
import { SidebarRail } from '../components/layout/SidebarRail';

afterEach(cleanup);

describe('activeSection', () => {
  it('maps each route to its sidebar section', () => {
    expect(activeSection('/research/new')).toBe('new-research');
    expect(activeSection('/projects')).toBe('projects');
    expect(activeSection('/projects/abc')).toBe('projects');
    expect(activeSection('/library')).toBe('library');
    expect(activeSection('/library/')).toBe('library');
    expect(activeSection('/settings')).toBe('settings');
    expect(activeSection('/research/abc')).toBe('research');
    expect(activeSection('/projects-old')).toBeNull();
  });
});

const renderSidebar = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <AppSidebar />
    </MemoryRouter>,
  );

describe('AppSidebar navigation', () => {
  it('shows Library instead of Documents and links to /library', () => {
    renderSidebar('/projects');
    expect(screen.getByRole('link', { name: 'Library' })).toHaveAttribute('href', '/library');
    expect(screen.queryByText('Documents')).not.toBeInTheDocument();
  });

  it('marks only the current section as the current page', () => {
    renderSidebar('/projects/p1');
    expect(screen.getByRole('link', { name: 'Projects' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Library' })).not.toHaveAttribute('aria-current');
    expect(screen.getByRole('link', { name: /New research/ })).not.toHaveAttribute('aria-current');
  });

  it('highlights New research only on the new research page', () => {
    renderSidebar('/research/new');
    expect(screen.getByRole('link', { name: /New research/ })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Projects' })).not.toHaveAttribute('aria-current');
  });

  it('has no theme switch in the profile menu', () => {
    renderSidebar('/library');
    fireEvent.click(screen.getByRole('button', { name: /Shubham Rai/ }));
    expect(screen.getByRole('menu')).toBeInTheDocument();
    expect(screen.queryByText(/theme/i)).not.toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Settings' })).toBeInTheDocument();
  });
});

describe('SidebarRail navigation', () => {
  it('marks the current section and has no theme switch', () => {
    render(
      <MemoryRouter initialEntries={['/library']}>
        <SidebarRail onExpand={vi.fn()} onSearch={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('link', { name: 'Library' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'New research' })).not.toHaveAttribute('aria-current');
    fireEvent.click(screen.getByRole('button', { name: /Account/ }));
    expect(screen.queryByText(/theme/i)).not.toBeInTheDocument();
  });
});
