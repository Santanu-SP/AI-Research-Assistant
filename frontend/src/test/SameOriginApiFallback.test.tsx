// @vitest-environment jsdom
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  crossSite: true,
  proxyWorks: true,
  switched: false,
}));

vi.mock('../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/api')>();
  return {
    ...actual,
    isCrossSiteApi: () => mocks.crossSite && !mocks.switched,
    probeSameOriginApi: async () => mocks.proxyWorks,
    switchToSameOriginApi: () => {
      mocks.switched = true;
    },
  };
});

import { AuthProvider, SESSION_COOKIE_BLOCKED, useAuth } from '../app/AuthContext';
import { ApiError, apiErrorCode, isCrossSiteApi } from '../services/api';
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

const unauthorized = () => new ApiError('Authentication required', 401);

describe('falling back to the same-origin API proxy', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    mocks.crossSite = true;
    mocks.proxyWorks = true;
    mocks.switched = false;
  });

  it('switches to the proxy and signs in again when the cross-site cookie is dropped', async () => {
    const login = vi.spyOn(authService, 'login').mockResolvedValue(user);
    vi.spyOn(authService, 'me').mockImplementation(async () => {
      if (mocks.switched) return user;
      throw unauthorized();
    });
    render(<AuthProvider><Probe /></AuthProvider>);
    await screen.findByText('signed out');

    await act(async () => {
      await auth!.login(user.email, 'Correct-Horse-9');
    });

    expect(mocks.switched).toBe(true);
    expect(isCrossSiteApi()).toBe(false);
    expect(login).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(screen.getByText(`signed in as ${user.email}`)).toBeInTheDocument());
  });

  it('shows the blocked-cookie message when there is no proxy to fall back to', async () => {
    mocks.proxyWorks = false;
    vi.spyOn(authService, 'login').mockResolvedValue(user);
    vi.spyOn(authService, 'me').mockRejectedValue(unauthorized());
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

    expect(mocks.switched).toBe(false);
    expect(apiErrorCode(caught)).toBe(SESSION_COOKIE_BLOCKED);
  });
});
