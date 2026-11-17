// @vitest-environment jsdom
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ModelsAndKeysPanel } from '../components/settings/ModelsAndKeysPanel';
import { byokService, type ModelsStatusResponse } from '../services/clientAi.service';
import { ApiError } from '../services/api';
import { DEFAULT_MODEL_STORAGE_KEY, getDefaultModel } from '../lib/defaultModel';

const status: ModelsStatusResponse = {
  local: {
    provider: 'ollama',
    available: false,
    connected: false,
    baseUrl: 'http://127.0.0.1:11434',
    configuredModel: 'qwen3.5:9b',
    installedModels: [],
  },
  providers: [
    {
      id: 'gemini',
      label: 'Gemini',
      configuredServer: false,
      configuredByok: true,
      configured: true,
      keyHint: '••••a1b2',
      defaultModel: 'gemini-2.5-flash',
      suggestedModels: ['gemini-2.5-flash', 'gemini-2.5-pro'],
      isLocal: false,
      available: true,
    },
    {
      id: 'openai',
      label: 'OpenAI',
      configuredServer: false,
      configuredByok: false,
      configured: false,
      defaultModel: 'gpt-4o-mini',
      isLocal: false,
      available: true,
    },
  ],
  routerOrder: ['gemini'],
};

const row = (provider: string) =>
  screen.getByRole('list', { name: 'API keys' }).querySelector(`[data-provider="${provider}"]`) as HTMLElement;

describe('Models & API keys', () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.spyOn(byokService, 'getModelsStatus').mockResolvedValue(status);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('lists keys masked and adds a new one without showing it again', async () => {
    const saveKey = vi
      .spyOn(byokService, 'saveKey')
      .mockResolvedValue({ id: 'k2', provider: 'openai', keyHint: '••••9xyz', isActive: true, usageRequests: 0, usageTokens: 0, createdAt: '' });
    render(<ModelsAndKeysPanel />);

    expect(await screen.findByText('••••a1b2')).toBeInTheDocument();
    expect(within(row('openai')).getByText('No key')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Add OpenAI key' }));
    const input = screen.getByLabelText('OpenAI API key');
    expect(input).toHaveAttribute('type', 'password');
    fireEvent.change(input, { target: { value: 'sk-test-1234567890' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save key' }));

    await waitFor(() => expect(saveKey).toHaveBeenCalledWith('openai', 'sk-test-1234567890'));
    expect(await screen.findByText(/Key saved for OpenAI/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain('sk-test-1234567890');
  });

  it('never shows a pasted key inside an error', async () => {
    vi.spyOn(byokService, 'saveKey').mockRejectedValue(
      new ApiError('bad', 400, { error: { code: 'invalid_api_key', message: 'Key sk-test-1234567890 was rejected' } }),
    );
    render(<ModelsAndKeysPanel />);
    fireEvent.click(await screen.findByRole('button', { name: 'Add OpenAI key' }));
    fireEvent.change(screen.getByLabelText('OpenAI API key'), { target: { value: 'sk-test-1234567890' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save key' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Key [hidden] was rejected');
  });

  it('asks before removing a key', async () => {
    const revoke = vi.spyOn(byokService, 'revokeKey').mockResolvedValue();
    render(<ModelsAndKeysPanel />);
    fireEvent.click(await screen.findByRole('button', { name: 'Remove Gemini key' }));
    expect(revoke).not.toHaveBeenCalled();
    fireEvent.click(within(row('gemini')).getByRole('button', { name: 'Remove' }));
    await waitFor(() => expect(revoke).toHaveBeenCalledWith('gemini'));
  });

  it('saves the default model for new research', async () => {
    const setModel = vi.spyOn(byokService, 'setProviderModel').mockResolvedValue({ provider: 'gemini', selectedModel: 'gemini-2.5-pro' });
    render(<ModelsAndKeysPanel />);
    await screen.findByText('••••a1b2');
    fireEvent.change(screen.getByLabelText('Default provider'), { target: { value: 'gemini' } });
    fireEvent.change(screen.getByLabelText('Default model'), { target: { value: 'gemini-2.5-pro' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save default' }));

    await waitFor(() => expect(setModel).toHaveBeenCalledWith('gemini', 'gemini-2.5-pro'));
    expect(getDefaultModel()).toEqual({ provider: 'gemini', model: 'gemini-2.5-pro' });
    expect(await screen.findByText('New research will start with Gemini 2.5 Pro.')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Default provider'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save default' }));
    await waitFor(() => expect(window.localStorage.getItem(DEFAULT_MODEL_STORAGE_KEY)).toBeNull());
  });
});
