// @vitest-environment jsdom
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider, SESSION_COOKIE_BLOCKED, useAuth } from '../app/AuthContext';
import { ApiError, apiErrorCode } from '../services/api';
import { authService } from '../services/auth.service';

const user = {
  id: 'user-1',
  name: 'Researcher',
  email: 'researcher@example.com',
  isActive: true,
  createdAt: '2026-11-01T00:00:00Z',
  updatedAt: '2026-11-01T00:00:00Z',
};

let auth: ReturnType<typeof useAuth> | null = null;
const Probe: React.FC = () => {
  auth = useAuth();
  return <p>{auth.user ? `signed in as ${auth.user.email}` : 'signed out'}</p>;
};

describe('sign-in cookie check', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    auth = null;
  });

  it('explains when the browser drops the session cookie after a correct password', async () => {
    vi.spyOn(authService, 'login').mockResolvedValue(user);
    vi.spyOn(authService, 'me').mockRejectedValue(new ApiError('Authentication required', 401));
    render(<AuthProvider><Probe /></AuthProvider>);
    await screen.findByText('signed out');

    let caught: unknown;
    await act(async () => {
      try {
        await auth!.login(user.email, 'Correct-Horse-9');
      } catch (error) {
        caught = error;
      }
    });

    expect(apiErrorCode(caught)).toBe(SESSION_COOKIE_BLOCKED);
    expect(screen.getByText('signed out')).toBeInTheDocument();
  });

  it('signs in normally when the cookie is kept', async () => {
    vi.spyOn(authService, 'login').mockResolvedValue(user);
    const me = vi.spyOn(authService, 'me');
    me.mockRejectedValueOnce(new ApiError('Authentication required', 401));
    me.mockResolvedValue(user);
    render(<AuthProvider><Probe /></AuthProvider>);
    await screen.findByText('signed out');

    await act(async () => {
      await auth!.login(user.email, 'Correct-Horse-9');
    });

    await waitFor(() => expect(screen.getByText(`signed in as ${user.email}`)).toBeInTheDocument());
  });
});
