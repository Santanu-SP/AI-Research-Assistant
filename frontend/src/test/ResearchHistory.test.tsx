// @vitest-environment jsdom
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ResearchResponse } from '../types/research';

const now = new Date('2026-11-12T15:00:00');
const daysAgo = (days: number) => new Date(now.getTime() - days * 24 * 60 * 60 * 1000).toISOString();

const research = (id: string, title: string, updatedAt: string, status: ResearchResponse['status'] = 'completed'): ResearchResponse => ({
  id,
  title,
  question: `${title}?`,
  domain: null,
  status,
  researchDepth: 'standard',
  sourceCount: 2,
  createdAt: updatedAt,
  updatedAt,
  archivedAt: null,
});

const items = [
  research('a', 'Reranker impact on citation accuracy', daysAgo(0)),
  research('b', 'Residence time versus affinity', daysAgo(1)),
  research('c', 'Cool roofs and surface temperature', daysAgo(4), 'researching'),
  research('d', 'Urban heat island survey', daysAgo(20)),
  research('e', 'Membrane protein folding', daysAgo(90)),
];

vi.mock('../app/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', name: 'Shubham Rai', email: 'shubham@example.com', isActive: true, createdAt: daysAgo(100), updatedAt: daysAgo(1) },
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
      items,
      total: items.length,
      loading: false,
      error: false,
      complete: true,
      reload: vi.fn(),
      rename: vi.fn(),
      remove: vi.fn(),
    }),
  };
});

import { groupByDate } from '../app/ResearchHistoryContext';
import { AppSidebar } from '../components/layout/AppSidebar';

afterEach(cleanup);

describe('groupByDate', () => {
  it('buckets research by how recently it was updated', () => {
    const groups = groupByDate(items, now);
    expect(groups.map((group) => [group.label, group.items.map((item) => item.id)])).toEqual([
      ['Today', ['a']],
      ['Yesterday', ['b']],
      ['Previous 7 days', ['c']],
      ['Previous 30 days', ['d']],
      ['Older', ['e']],
    ]);
  });
});

describe('AppSidebar research history', () => {
  const renderSidebar = () =>
    render(
      <MemoryRouter initialEntries={['/research/b']}>
        <AppSidebar />
      </MemoryRouter>,
    );

  it('lists every research item and no separate "My research" link', () => {
    renderSidebar();
    const history = screen.getByLabelText('Research history');
    for (const item of items) expect(within(history).getByText(item.title)).toBeInTheDocument();
    expect(screen.queryByText('My research')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Residence time versus affinity/ })).toHaveAttribute('aria-current', 'page');
  });

  it('filters by title as you type and says when nothing matches', () => {
    renderSidebar();
    const search = screen.getByRole('searchbox', { name: 'Search research' });

    fireEvent.change(search, { target: { value: 'heat' } });
    const history = screen.getByLabelText('Research history');
    expect(within(history).getAllByRole('listitem')).toHaveLength(1);
    expect(within(history).getByRole('link', { name: /Urban heat island survey/ })).toBeInTheDocument();

    fireEvent.change(search, { target: { value: 'no such thing' } });
    expect(screen.getByText(/No research matches/)).toBeInTheDocument();
  });
});
