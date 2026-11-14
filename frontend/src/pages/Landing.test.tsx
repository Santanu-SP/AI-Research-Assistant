// @vitest-environment jsdom
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { LandingPage } from './Landing';

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  logout: vi.fn(),
  user: null as null | {
    id: string;
    name: string;
    email: string;
    isActive: boolean;
    createdAt: string;
    updatedAt: string;
  },
}));

vi.mock('../app/AuthContext', () => ({
  useOptionalAuth: () => ({
    user: mocks.user,
    loading: false,
    login: vi.fn(),
    logout: mocks.logout,
    logoutAll: vi.fn(),
    refreshUser: vi.fn(),
  }),
}));

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

describe('LandingPage authentication state', () => {
  beforeAll(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  afterEach(cleanup);

  beforeEach(() => {
    mocks.user = null;
    mocks.logout.mockReset();
    mocks.logout.mockResolvedValue(undefined);
    mocks.navigate.mockReset();
  });

  it('shows Sign in and account creation options when logged out', () => {
    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>
    );

    expect(screen.getAllByRole('link', { name: 'Sign in' }).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole('link', { name: 'Get started' })).toHaveAttribute('href', '/register');
    expect(screen.queryByRole('link', { name: 'Open workspace' })).not.toBeInTheDocument();
  });

  it('shows signed-in identity, workspace CTA, sign out, and switch account when logged in', async () => {
    mocks.user = {
      id: 'user-42',
      name: 'Santanu',
      email: 'santanu@example.com',
      isActive: true,
      createdAt: '2026-11-01T00:00:00Z',
      updatedAt: '2026-11-01T00:00:00Z',
    };

    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>
    );

    expect(screen.getByText(/Signed in as/i)).toBeInTheDocument();
    expect(screen.getAllByText(/santanu@example\.com/).length).toBeGreaterThanOrEqual(2);
    const workspaceLinks = screen.getAllByRole('link', { name: /Open workspace/i });
    expect(workspaceLinks[0]).toHaveAttribute('href', '/research/new');

    fireEvent.click(screen.getByRole('button', { name: 'Switch account' }));
    await waitFor(() => {
      expect(mocks.logout).toHaveBeenCalledTimes(1);
      expect(mocks.navigate).toHaveBeenCalledWith('/login');
    });

    fireEvent.click(screen.getAllByRole('button', { name: 'Sign out' })[0]);
    await waitFor(() => {
      expect(mocks.logout).toHaveBeenCalledTimes(2);
    });
  });
});
