// @vitest-environment jsdom
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../app/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', name: 'Shubham Rai', email: 'shubham@example.com', isActive: true, createdAt: '2026-09-01T00:00:00Z', updatedAt: '2026-09-01T00:00:00Z' },
    logout: vi.fn(),
    logoutAll: vi.fn(),
  }),
}));
vi.mock('../app/ToastContext', () => ({ useToast: () => ({ addToast: vi.fn() }) }));

import { SettingsPage } from '../pages/Settings';
import { systemService } from '../services/system.service';
import { byokService } from '../services/clientAi.service';

describe('Settings system status', () => {
  beforeEach(() => {
    vi.spyOn(byokService, 'getUsage').mockRejectedValue(new Error('offline'));
    vi.spyOn(byokService, 'getModelsStatus').mockRejectedValue(new Error('offline'));
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('is folded by default and uses plain words', async () => {
    vi.spyOn(systemService, 'getReadiness').mockResolvedValue({
      status: 'not_ready',
      checks: [
        { name: 'database', ok: true, detail: 'postgresql' },
        { name: 'llm_router', ok: false, detail: 'no cloud LLM provider keys configured' },
      ],
    });
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );
    expect(screen.getByRole('heading', { name: 'System status' })).toBeInTheDocument();
    expect(screen.queryByText('Research services')).not.toBeInTheDocument();
    expect(await screen.findByText('Something needs attention')).toBeInTheDocument();

    const details = screen.getByText('Saving your work').closest('details') as HTMLDetailsElement;
    expect(details.open).toBe(false);
    expect(screen.getByText('No model is set up yet. Add an API key above.')).toBeInTheDocument();
    expect(screen.queryByText('postgresql')).not.toBeInTheDocument();
  });
});
