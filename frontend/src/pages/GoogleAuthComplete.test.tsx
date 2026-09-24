// @vitest-environment jsdom
import React from 'react';
import { cleanup, render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GoogleAuthCompletePage } from './GoogleAuthComplete';

const mocks = vi.hoisted(() => ({
  user: {
    id: 'user-1', name: 'Researcher', email: 'researcher@example.com', isActive: true,
    createdAt: '2026-09-24T00:00:00Z', updatedAt: '2026-09-24T00:00:00Z',
  },
}));

vi.mock('../app/AuthContext', () => ({
  useAuth: () => ({ user: mocks.user, loading: false }),
}));

describe('Google OAuth completion page', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    Object.defineProperty(window, 'opener', { configurable: true, value: null });
  });

  it('notifies only its opener with a token-free success message and closes', async () => {
    const opener = { closed: false, postMessage: vi.fn() };
    Object.defineProperty(window, 'opener', { configurable: true, value: opener });
    const close = vi.spyOn(window, 'close').mockImplementation(() => undefined);

    render(<MemoryRouter><GoogleAuthCompletePage /></MemoryRouter>);

    await waitFor(() => expect(opener.postMessage).toHaveBeenCalledWith(
      { type: 'google-auth-success' },
      window.location.origin,
    ));
    expect(close).toHaveBeenCalledOnce();
  });
});
