import React, { useCallback, useEffect, useState } from 'react';
import { CircleAlert, KeyRound } from 'lucide-react';
import { PrimaryButton } from '../common/PrimaryButton';
import { SUGGESTED_MODELS_BY_PROVIDER } from '../../lib/modelCatalog';
import { byokService, type ProviderStatusItem } from '../../services/clientAi.service';
import { apiErrorMessage } from '../../services/api';
import { getDefaultModel, setDefaultModel } from '../../lib/defaultModel';
import { prettyModelName, redactSecrets } from '../../lib/modelErrors';

type Notice = { kind: 'success' | 'error'; text: string } | null;

const friendlyError = (error: unknown, fallback: string): string =>
  redactSecrets(apiErrorMessage(error, fallback));

const modelsFor = (provider: ProviderStatusItem | undefined): string[] => {
  if (!provider) return [];
  const list = [
    provider.selectedModel,
    provider.defaultModel !== 'local' ? provider.defaultModel : null,
    ...(provider.suggestedModels?.length ? provider.suggestedModels : SUGGESTED_MODELS_BY_PROVIDER[provider.id] ?? []),
  ];
  return Array.from(new Set(list.filter((item): item is string => Boolean(item && item.trim()))));
};

/** Settings section: the API keys saved on this account and the model new research starts with. */
export const ModelsAndKeysPanel: React.FC = () => {
  const [providers, setProviders] = useState<ProviderStatusItem[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [keyInput, setKeyInput] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);
  const [defaultProvider, setDefaultProvider] = useState<string | null>(() => getDefaultModel().provider);
  const [defaultModelName, setDefaultModelName] = useState<string | null>(() => getDefaultModel().model);

  const load = useCallback(async () => {
    setLoadError(false);
    try {
      const status = await byokService.getModelsStatus();
      setProviders(status.providers ?? []);
    } catch {
      setLoadError(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const cloudProviders = (providers ?? []).filter((item) => !item.isLocal);
  const usable = (providers ?? []).filter((item) => item.configured || (item.isLocal && item.available));

  const saveKey = async (providerId: string) => {
    const trimmed = keyInput.trim();
    if (trimmed.length < 8) {
      setNotice({ kind: 'error', text: 'Paste the full API key (at least 8 characters).' });
      return;
    }
    setBusy(providerId);
    setNotice(null);
    try {
      const saved = await byokService.saveKey(providerId, trimmed);
      setKeyInput('');
      setEditing(null);
      setNotice({ kind: 'success', text: `Key saved for ${prettyModelName(saved.provider)} (ends ${saved.keyHint.replace(/^[•.*\s]+/, '')}).` });
      window.dispatchEvent(new Event('models-usage:refresh'));
      await load();
    } catch (error) {
      setNotice({ kind: 'error', text: friendlyError(error, 'That key couldn’t be saved. Check that it belongs to this provider.') });
    } finally {
      setBusy(null);
    }
  };

  const removeKey = async (providerId: string) => {
    setBusy(providerId);
    setNotice(null);
    try {
      await byokService.revokeKey(providerId);
      setConfirmRemove(null);
      if (defaultProvider === providerId) {
        setDefaultProvider(null);
        setDefaultModelName(null);
        setDefaultModel({ provider: null, model: null });
      }
      setNotice({ kind: 'success', text: `Key removed for ${prettyModelName(providerId)}.` });
      window.dispatchEvent(new Event('models-usage:refresh'));
      await load();
    } catch (error) {
      setNotice({ kind: 'error', text: friendlyError(error, 'That key couldn’t be removed. Please try again.') });
    } finally {
      setBusy(null);
    }
  };

  const saveDefault = async () => {
    setBusy('default');
    setNotice(null);
    setDefaultModel({ provider: defaultProvider, model: defaultModelName });
    try {
      if (defaultProvider && defaultProvider !== 'ollama') {
        await byokService.setProviderModel(defaultProvider, defaultModelName);
      }
      setNotice({
        kind: 'success',
        text: defaultProvider
          ? `New research will start with ${prettyModelName(defaultProvider, defaultModelName)}.`
          : 'New research will pick the best available model.',
      });
    } catch (error) {
      setNotice({ kind: 'error', text: friendlyError(error, 'Saved on this device, but the server didn’t store the model.') });
    } finally {
      setBusy(null);
    }
  };

  const selectedProvider = (providers ?? []).find((item) => item.id === defaultProvider);
  const modelChoices = modelsFor(selectedProvider);

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-lg border border-line bg-panel shadow-xs">
        <div className="space-y-3 p-4">
          <p className="text-[13px] font-medium text-ink">Default model for new research</p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <label className="flex-1 text-xs text-ink-muted">
              Provider
              <select
                aria-label="Default provider"
                className="field mt-1 h-9 text-[13px]"
                value={defaultProvider ?? ''}
                onChange={(e) => {
                  const next = e.target.value || null;
                  setDefaultProvider(next);
                  const item = (providers ?? []).find((p) => p.id === next);
                  setDefaultModelName(item?.selectedModel ?? null);
                }}
              >
                <option value="">Auto (best available)</option>
                {usable.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex-1 text-xs text-ink-muted">
              Model
              <select
                aria-label="Default model"
                className="field mt-1 h-9 text-[13px]"
                value={defaultModelName ?? ''}
                disabled={!defaultProvider}
                onChange={(e) => setDefaultModelName(e.target.value || null)}
              >
                <option value="">{defaultProvider ? 'Provider’s default' : 'Chosen for you'}</option>
                {modelChoices.map((model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-ink-muted">You can still switch models for any single research.</p>
            <PrimaryButton size="sm" onClick={() => void saveDefault()} disabled={busy === 'default'}>
              {busy === 'default' ? 'Saving…' : 'Save default'}
            </PrimaryButton>
          </div>
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-line bg-panel shadow-xs">
        <div className="border-b border-line px-4 py-2.5">
          <p className="text-[13px] font-medium text-ink">Your API keys</p>
          <p className="text-xs text-ink-muted">Keys are stored encrypted and only the last few characters are ever shown.</p>
        </div>
        {loadError ? (
          <div className="flex items-center gap-2.5 px-4 py-3.5 text-[13px] text-ink-soft">
            <CircleAlert className="h-4 w-4 shrink-0 text-danger" />
            Couldn’t load your models.
            <button type="button" onClick={() => void load()} className="font-medium text-accent hover:underline">
              Try again
            </button>
          </div>
        ) : providers === null ? (
          <div className="space-y-3 p-4" aria-hidden="true">
            <span className="block h-3 w-48 animate-pulse rounded bg-subtle" />
            <span className="block h-3 w-40 animate-pulse rounded bg-subtle" />
          </div>
        ) : (
          <ul className="divide-y divide-line" aria-label="API keys">
            {cloudProviders.map((item) => {
              const isEditing = editing === item.id;
              const isBusy = busy === item.id;
              return (
                <li key={item.id} className="px-4 py-3" data-provider={item.id}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-[14px] text-ink">{item.label}</p>
                      <p className="text-xs text-ink-muted">
                        {item.configuredByok ? (
                          <>
                            Your key <span className="font-mono tracking-wide">{item.keyHint || '••••'}</span>
                          </>
                        ) : item.configuredServer ? (
                          'Included with the app'
                        ) : (
                          'No key'
                        )}
                      </p>
                    </div>
                    {!isEditing && confirmRemove !== item.id && (
                      <div className="flex items-center gap-1.5">
                        <PrimaryButton
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setEditing(item.id);
                            setKeyInput('');
                            setConfirmRemove(null);
                            setNotice(null);
                          }}
                          aria-label={`${item.configuredByok ? 'Replace' : 'Add'} ${item.label} key`}
                        >
                          <KeyRound className="h-3.5 w-3.5" />
                          {item.configuredByok ? 'Replace' : 'Add key'}
                        </PrimaryButton>
                        {item.configuredByok && (
                          <PrimaryButton
                            size="sm"
                            variant="ghost"
                            onClick={() => setConfirmRemove(item.id)}
                            aria-label={`Remove ${item.label} key`}
                          >
                            Remove
                          </PrimaryButton>
                        )}
                      </div>
                    )}
                    {confirmRemove === item.id && (
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs text-ink-soft">Remove this key?</span>
                        <PrimaryButton size="sm" variant="danger" onClick={() => void removeKey(item.id)} disabled={isBusy}>
                          {isBusy ? 'Removing…' : 'Remove'}
                        </PrimaryButton>
                        <PrimaryButton size="sm" variant="ghost" onClick={() => setConfirmRemove(null)}>
                          Cancel
                        </PrimaryButton>
                      </div>
                    )}
                  </div>
                  {isEditing && (
                    <form
                      className="mt-2.5 flex flex-col gap-2 sm:flex-row"
                      onSubmit={(e) => {
                        e.preventDefault();
                        void saveKey(item.id);
                      }}
                    >
                      <input
                        type="password"
                        autoComplete="off"
                        spellCheck={false}
                        aria-label={`${item.label} API key`}
                        placeholder={`Paste your ${item.label} API key`}
                        value={keyInput}
                        onChange={(e) => setKeyInput(e.target.value)}
                        className="field h-8 flex-1 font-mono text-[13px]"
                        autoFocus
                      />
                      <div className="flex gap-1.5">
                        <PrimaryButton size="sm" type="submit" disabled={isBusy}>
                          {isBusy ? 'Saving…' : 'Save key'}
                        </PrimaryButton>
                        <PrimaryButton
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            setEditing(null);
                            setKeyInput('');
                          }}
                        >
                          Cancel
                        </PrimaryButton>
                      </div>
                    </form>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {notice && (
        <p
          role={notice.kind === 'error' ? 'alert' : 'status'}
          className={`text-[13px] ${notice.kind === 'error' ? 'text-danger' : 'text-ink-soft'}`}
        >
          {notice.text}
        </p>
      )}
    </div>
  );
};
