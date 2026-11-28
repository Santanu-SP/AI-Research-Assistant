// @vitest-environment jsdom
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
import { byokService, type ProviderCreditItem } from '../services/clientAi.service';
import { formatLiveQuotaSummary } from '../lib/modelCredits';

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

  it('displays fixed per-model 3-hour and 2-day credit percentages without user-count dilution', async () => {
    vi.spyOn(systemService, 'getReadiness').mockResolvedValue({
      status: 'ready',
      checks: [{ name: 'database', ok: true, detail: 'postgresql' }],
    });
    vi.spyOn(byokService, 'getUsage').mockResolvedValue({
      overallRemainingPct: 90,
      shortWindowHours: 3,
      longWindowDays: 2,
      shortCreditsPerModel: 20,
      longCreditsPerModel: 100,
      shortResetsAt: '2026-11-18T03:00:00Z',
      longResetsAt: '2026-11-20T00:00:00Z',
      providerCredits: [
        {
          provider: 'gemini',
          label: 'Gemini',
          modelName: 'gemini-3.8-flash',
          mode: 'shared',
          unlimited: false,
          remainingPct: 80,
          shortWindowPct: 80,
          longWindowPct: 96,
          shortResetsAt: '2026-11-18T03:00:00Z',
          longResetsAt: '2026-11-20T00:00:00Z',
          shortRemaining: 16,
          shortCap: 20,
          longRemaining: 96,
          longCap: 100,
        },
        {
          provider: 'groq',
          label: 'Groq',
          modelName: 'llama-3.3-70b-versatile',
          mode: 'shared',
          unlimited: false,
          remainingPct: 100,
          shortWindowPct: 100,
          longWindowPct: 100,
          shortResetsAt: '2026-11-18T03:00:00Z',
          longResetsAt: '2026-11-20T00:00:00Z',
          shortRemaining: 20,
          shortCap: 20,
          longRemaining: 100,
          longCap: 100,
        },
      ],
      enrolledUsers: 1,
      sharedRequestsUsedToday: 4,
      userDailyRequestCap: 40,
      userRequestsRemainingToday: 36,
      systemPoolTotal: 200,
      systemPoolUsedToday: 4,
      systemPoolRemaining: 196,
      byokRequestsToday: 0,
      localRequestsToday: 0,
      totalRequestsToday: 4,
      totalTokensToday: 900,
      totalRequestsAllTime: 4,
      totalTokensAllTime: 900,
      resetsAt: '2026-11-18T03:00:00Z',
      models: [],
    });

    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('80% remaining')).toBeInTheDocument();
    expect(screen.getByText('100% remaining')).toBeInTheDocument();
    expect(screen.getByText(/3-hour credits: 80%/)).toBeInTheDocument();
    expect(screen.getByText(/2-day pool: 96%/)).toBeInTheDocument();
    const activityDetails = screen.getByText('Detailed activity counters').closest('details') as HTMLDetailsElement;
    expect(activityDetails.open).toBe(false);
  });

  it('formats and renders real live API balances, header limits, today usage, and live refresh trigger', async () => {
    const baseItem: ProviderCreditItem = {
      provider: 'openrouter',
      label: 'OpenRouter',
      modelName: 'openrouter/free',
      mode: 'byok',
      unlimited: true,
      remainingPct: 100,
      shortWindowPct: 100,
      longWindowPct: 100,
      shortResetsAt: '2026-11-18T03:00:00Z',
      longResetsAt: '2026-11-20T00:00:00Z',
      shortRemaining: 20,
      shortCap: 20,
      longRemaining: 100,
      longCap: 100,
    };
    expect(
      formatLiveQuotaSummary({
        ...baseItem,
        liveSource: 'provider_api',
        liveCreditLimitUsd: 10,
        liveCreditRemainingUsd: 9.88,
        liveLimitRequests: 200,
      }),
    ).toEqual({
      badge: 'Live API',
      detail: '$9.88 / $10.00 left · 200 req',
    });
    expect(
      formatLiveQuotaSummary({
        ...baseItem,
        provider: 'groq',
        label: 'Groq',
        mode: 'shared',
        unlimited: false,
        liveSource: 'response_headers',
        liveLimitRequests: 100,
        liveRemainingRequests: 98,
        liveLimitTokens: 20000,
        liveRemainingTokens: 19800,
      }),
    ).toEqual({
      badge: 'Live headers',
      detail: '98/100 req left · 19.8k/20k tok left',
    });

    vi.spyOn(systemService, 'getReadiness').mockResolvedValue({
      status: 'ready',
      checks: [{ name: 'database', ok: true, detail: 'postgresql' }],
    });
    const getUsageSpy = vi.spyOn(byokService, 'getUsage').mockResolvedValue({
      overallRemainingPct: 95,
      shortWindowHours: 3,
      longWindowDays: 2,
      shortCreditsPerModel: 20,
      longCreditsPerModel: 100,
      shortResetsAt: '2026-11-18T03:00:00Z',
      longResetsAt: '2026-11-20T00:00:00Z',
      providerCredits: [
        {
          provider: 'groq',
          label: 'Groq',
          modelName: 'llama-3.3-70b-versatile',
          mode: 'shared',
          unlimited: false,
          remainingPct: 95,
          shortWindowPct: 95,
          longWindowPct: 99,
          shortResetsAt: '2026-11-18T03:00:00Z',
          longResetsAt: '2026-11-20T00:00:00Z',
          shortRemaining: 19,
          shortCap: 20,
          longRemaining: 99,
          longCap: 100,
          requestsToday: 1,
          tokensToday: 300,
          liveSource: 'response_headers',
          liveLimitRequests: 100,
          liveRemainingRequests: 98,
          liveLimitTokens: 20000,
          liveRemainingTokens: 19800,
        },
        {
          ...baseItem,
          requestsToday: 3,
          tokensToday: 1200,
          liveSource: 'provider_api',
          liveCreditLimitUsd: 10,
          liveCreditRemainingUsd: 9.88,
        },
      ],
      enrolledUsers: 1,
      sharedRequestsUsedToday: 1,
      userDailyRequestCap: 20,
      userRequestsRemainingToday: 19,
      systemPoolTotal: 100,
      systemPoolUsedToday: 1,
      systemPoolRemaining: 99,
      byokRequestsToday: 3,
      localRequestsToday: 0,
      totalRequestsToday: 4,
      totalTokensToday: 1500,
      totalRequestsAllTime: 4,
      totalTokensAllTime: 1500,
      resetsAt: '2026-11-18T03:00:00Z',
      models: [],
    });

    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Live headers')).toBeInTheDocument();
    expect(screen.getByText('98/100 req left · 19.8k/20k tok left')).toBeInTheDocument();
    expect(screen.getByText('Live API')).toBeInTheDocument();
    expect(screen.getByText('$9.88 / $10.00 left')).toBeInTheDocument();
    expect(screen.getByText(/3 runs · 1\.2k tok today/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Refresh credits' }));
    await waitFor(() => expect(getUsageSpy).toHaveBeenCalledWith({ live: true }));
  });
});
