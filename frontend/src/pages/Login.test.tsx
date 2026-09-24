// @vitest-environment jsdom
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LoginPage } from './Login';
import { RegisterPage } from './Register';

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  refreshUser: vi.fn(),
  startGoogleLogin: vi.fn(),
  user: null as null | { id: string; name: string; email: string; isActive: boolean; createdAt: string; updatedAt: string },
}));

vi.mock('../app/AuthContext', () => ({
  useAuth: () => ({
    user: mocks.user,
    loading: false,
    login: mocks.login,
    logout: mocks.logout,
    refreshUser: mocks.refreshUser,
  }),
}));

vi.mock('../services/auth.service', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/auth.service')>();
  return {
    ...actual,
    authService: { ...actual.authService, startGoogleLogin: mocks.startGoogleLogin },
  };
});

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

const signedInUser = {
  id: 'user-1',
  name: 'Researcher',
  email: 'researcher@example.com',
  isActive: true,
  createdAt: '2026-09-24T00:00:00Z',
  updatedAt: '2026-09-24T00:00:00Z',
};

describe('authentication navigation', () => {
  afterEach(cleanup);

  beforeEach(() => {
    mocks.user = null;
    mocks.navigate.mockReset();
    mocks.login.mockReset();
    mocks.refreshUser.mockReset();
    mocks.startGoogleLogin.mockReset();
  });

  it('uses replacement navigation after password login', async () => {
    mocks.login.mockResolvedValue(undefined);
    render(<MemoryRouter><LoginPage /></MemoryRouter>);

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'researcher@example.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'password-123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Login' }));

    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith('/research/new', { replace: true }));
  });

  it('refreshes the HTTP-only-cookie session and replaces login after popup success', async () => {
    mocks.startGoogleLogin.mockResolvedValue(undefined);
    mocks.refreshUser.mockResolvedValue(signedInUser);
    render(<MemoryRouter><LoginPage /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: 'Continue with Google' }));

    await waitFor(() => expect(mocks.refreshUser).toHaveBeenCalledOnce());
    expect(mocks.navigate).toHaveBeenCalledWith('/research/new', { replace: true });
  });

  it.each([
    ['/login', <LoginPage />],
    ['/register', <RegisterPage />],
  ])('redirects an authenticated user away from %s', async (path, page) => {
    mocks.user = signedInUser;
    render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={path} element={page} />
          <Route path="/research/new" element={<p>Authenticated workspace</p>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText('Authenticated workspace')).toBeInTheDocument();
  });
});
