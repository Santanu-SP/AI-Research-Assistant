import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Check,
  ChevronDown,
  Cpu,
  KeyRound,
  Plug,
  PlugZap,
  Trash2,
  X,
} from 'lucide-react';
import {
  byokService,
  LocalModelStatus,
  ModelsStatusResponse,
  ProviderStatusItem,
} from '../../services/clientAi.service';
import { apiErrorMessage } from '../../services/api';
import { ResearchDepth } from '../../types/research';

export interface ModelControlBarProps {
  depth: ResearchDepth;
  onDepthChange: (depth: ResearchDepth) => void;
  preferredProvider: string | null;
  onPreferredProviderChange: (provider: string | null) => void;
  modelOverride?: string | null;
  onModelOverrideChange?: (model: string | null) => void;
  localFallbackEnabled: boolean | undefined;
  onLocalFallbackChange: (enabled: boolean) => void;
  disabled?: boolean;
  menuPlacement?: 'up' | 'down';
}

const DEPTH_OPTIONS: ReadonlyArray<{
  value: ResearchDepth;
  label: string;
}> = [
  { value: 'quick', label: 'Low' },
  { value: 'standard', label: 'Medium' },
  { value: 'deep', label: 'High' },
];

const FALLBACK_PROVIDER_CATALOG: ProviderStatusItem[] = [
  {
    id: 'gemini',
    label: 'Gemini',
    configuredServer: false,
    configuredByok: false,
    configured: false,
    defaultModel: 'gemini-3.8-flash',
    isLocal: false,
    available: true,
  },
  {
    id: 'groq',
    label: 'Groq',
    configuredServer: false,
    configuredByok: false,
    configured: false,
    defaultModel: 'llama-3.3-70b-versatile',
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
  {
    id: 'claude',
    label: 'Claude',
    configuredServer: false,
    configuredByok: false,
    configured: false,
    defaultModel: 'claude-3-5-haiku-latest',
    isLocal: false,
    available: true,
  },
  {
    id: 'grok',
    label: 'Grok',
    configuredServer: false,
    configuredByok: false,
    configured: false,
    defaultModel: 'grok-3-mini-fast',
    isLocal: false,
    available: true,
  },
  {
    id: 'openrouter',
    label: 'OpenRouter',
    configuredServer: false,
    configuredByok: false,
    configured: false,
    defaultModel: 'openrouter/free',
    isLocal: false,
    available: true,
  },
  {
    id: 'cerebras',
    label: 'Cerebras',
    configuredServer: false,
    configuredByok: false,
    configured: false,
    defaultModel: 'gpt-oss-120b',
    isLocal: false,
    available: true,
  },
  {
    id: 'mistral',
    label: 'Mistral',
    configuredServer: false,
    configuredByok: false,
    configured: false,
    defaultModel: 'mistral-small-4',
    isLocal: false,
    available: true,
  },
  {
    id: 'ollama',
    label: 'Local Ollama',
    configuredServer: false,
    configuredByok: false,
    configured: false,
    defaultModel: 'local',
    isLocal: true,
    available: false,
  },
];

const API_KEY_PROVIDER_CHOICES = [
  { id: 'auto', label: 'Auto-detect' },
  { id: 'gemini', label: 'Gemini' },
  { id: 'groq', label: 'Groq' },
  { id: 'openai', label: 'OpenAI' },
  { id: 'claude', label: 'Claude' },
  { id: 'grok', label: 'Grok' },
  { id: 'openrouter', label: 'OpenRouter' },
  { id: 'cerebras', label: 'Cerebras' },
  { id: 'mistral', label: 'Mistral' },
] as const;

const SUGGESTED_MODELS_BY_PROVIDER: Record<string, string[]> = {
  gemini: ['gemini-3.8-flash', 'gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-3.1-flash-lite'],
  groq: ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'qwen/qwen3-32b'],
  openai: ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini', 'o3-mini'],
  claude: ['claude-3-5-haiku-latest', 'claude-sonnet-4-20250514', 'claude-3-7-sonnet-latest'],
  grok: ['grok-3-mini-fast', 'grok-3-mini', 'grok-3'],
  openrouter: ['openrouter/free', 'meta-llama/llama-3.3-70b-instruct:free', 'google/gemini-2.5-flash'],
  cerebras: ['gpt-oss-120b', 'llama-3.3-70b', 'llama3.1-8b'],
  mistral: ['mistral-small-4', 'mistral-small-latest', 'mistral-large-latest'],
  ollama: ['qwen3.5:9b', 'llama3.2:3b', 'qwen2.5:3b'],
};

const detectProviderPrefix = (rawKey: string): string | null => {
  const cleaned = rawKey.trim();
  if (cleaned.startsWith('AIza')) return 'gemini';
  if (cleaned.startsWith('gsk_')) return 'groq';
  if (cleaned.startsWith('sk-ant-')) return 'claude';
  if (cleaned.startsWith('sk-or-')) return 'openrouter';
  if (cleaned.startsWith('xai-')) return 'grok';
  if (cleaned.startsWith('csk-')) return 'cerebras';
  if (cleaned.startsWith('sk-')) return 'openai';
  return null;
};

const depthDisplayLabel = (depth: ResearchDepth): string => {
  const match = DEPTH_OPTIONS.find((item) => item.value === depth);
  return match ? match.label : 'Medium';
};

const formatCompactTokens = (tokens: number): string => {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`;
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(1)}k`;
  return String(tokens);
};

interface PopoverLayout {
  openUp: boolean;
  maxHeight: number;
  alignRight: boolean;
}

const computePopoverLayout = (
  triggerEl: HTMLElement | null,
  preferredPlacement: 'up' | 'down',
  desiredHeight: number,
  desiredWidth: number
): PopoverLayout => {
  if (typeof window === 'undefined' || !triggerEl) {
    return { openUp: preferredPlacement === 'up', maxHeight: desiredHeight, alignRight: false };
  }
  const rect = triggerEl.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  if (vh === 0 || (rect.width === 0 && rect.height === 0 && rect.top === 0)) {
    return { openUp: preferredPlacement === 'up', maxHeight: desiredHeight, alignRight: false };
  }

  const margin = 12;
  const gap = 6;
  const spaceAbove = Math.max(0, rect.top - margin - gap);
  const spaceBelow = Math.max(0, vh - rect.bottom - margin - gap);

  let openUp = preferredPlacement === 'up';
  if (openUp && spaceAbove < desiredHeight && spaceBelow > spaceAbove) {
    openUp = false;
  } else if (!openUp && spaceBelow < desiredHeight && spaceAbove > spaceBelow) {
    openUp = true;
  }

  const available = openUp ? spaceAbove : spaceBelow;
  const maxHeight = Math.max(220, Math.min(desiredHeight, Math.floor(available)));
  const alignRight =
    rect.left + desiredWidth > vw - margin && rect.right - desiredWidth >= margin;
  return { openUp, maxHeight, alignRight };
};

export const ModelControlBar: React.FC<ModelControlBarProps> = ({
  depth,
  onDepthChange,
  preferredProvider,
  onPreferredProviderChange,
  modelOverride = null,
  onModelOverrideChange,
  localFallbackEnabled,
  onLocalFallbackChange,
  disabled = false,
  menuPlacement = 'up',
}) => {
  const [modelsOpen, setModelsOpen] = useState(false);
  const [keyOpen, setKeyOpen] = useState(false);
  const [modelsLayout, setModelsLayout] = useState<PopoverLayout>({
    openUp: menuPlacement === 'up',
    maxHeight: 540,
    alignRight: false,
  });
  const [keyLayout, setKeyLayout] = useState<PopoverLayout>({
    openUp: menuPlacement === 'up',
    maxHeight: 360,
    alignRight: false,
  });
  const [status, setStatus] = useState<ModelsStatusResponse | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [togglingLocal, setTogglingLocal] = useState(false);

  const [keyProvider, setKeyProvider] = useState<string>('auto');
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [specificModelInput, setSpecificModelInput] = useState('');
  const [savingModel, setSavingModel] = useState(false);
  const [savingKey, setSavingKey] = useState(false);
  const [keyMessage, setKeyMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(
    null
  );

  const containerRef = useRef<HTMLDivElement>(null);
  const modelsButtonRef = useRef<HTMLButtonElement>(null);
  const keyButtonRef = useRef<HTMLButtonElement>(null);

  const applyModelsStatus = useCallback(
    (data: ModelsStatusResponse) => {
      setStatus(data);
      setStatusError(null);
      if (localFallbackEnabled === undefined) {
        onLocalFallbackChange(Boolean(data.local.available && data.local.connected));
      }
    },
    [localFallbackEnabled, onLocalFallbackChange]
  );

  const refreshModelsStatus = useCallback(async () => {
    try {
      const data = await byokService.getModelsStatus();
      applyModelsStatus(data);
    } catch {
      // Keep graceful static catalog when status endpoint is unavailable (e.g. offline/tests)
    }
  }, [applyModelsStatus]);

  useEffect(() => {
    let cancelled = false;
    byokService
      .getModelsStatus()
      .then((data) => {
        if (!cancelled) {
          applyModelsStatus(data);
        }
      })
      .catch(() => {
        // Fallback catalog remains usable
      });
    return () => {
      cancelled = true;
    };
  }, [applyModelsStatus]);

  useEffect(() => {
    const onUsageRefresh = () => {
      void refreshModelsStatus();
    };
    window.addEventListener('models-usage:refresh', onUsageRefresh);
    return () => window.removeEventListener('models-usage:refresh', onUsageRefresh);
  }, [refreshModelsStatus]);

  useEffect(() => {
    const handleOutsideClick = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setModelsOpen(false);
        setKeyOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setModelsOpen(false);
        setKeyOpen(false);
      }
    };
    const handleResize = () => {
      if (modelsOpen) {
        setModelsLayout(
          computePopoverLayout(modelsButtonRef.current, menuPlacement, 540, 660)
        );
      }
      if (keyOpen) {
        setKeyLayout(
          computePopoverLayout(keyButtonRef.current, menuPlacement, 360, 320)
        );
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    document.addEventListener('keydown', handleKeyDown);
    window.addEventListener('resize', handleResize);
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
      document.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('resize', handleResize);
    };
  }, [modelsOpen, keyOpen, menuPlacement]);

  const providers = status?.providers?.length ? status.providers : FALLBACK_PROVIDER_CATALOG;
  const localStatus: LocalModelStatus = status?.local ?? {
    provider: 'ollama',
    available: false,
    connected: false,
    baseUrl: 'http://localhost:11434',
    configuredModel: 'local',
    activeModel: null,
    installedModels: [],
  };
  const isLocalConnected = Boolean(
    localStatus.available && (localFallbackEnabled ?? localStatus.connected)
  );

  const activeProviderLabel =
    preferredProvider === null
      ? 'Auto'
      : providers.find((item) => item.id === preferredProvider)?.label ?? preferredProvider;

  const byokCount = providers.filter((item) => item.configuredByok).length;

  const handleToggleLocalFallback = async () => {
    if (!localStatus.available || togglingLocal) return;
    const nextConnected = !isLocalConnected;
    setTogglingLocal(true);
    setStatusError(null);
    try {
      const updated = await byokService.setLocalFallback(nextConnected);
      onLocalFallbackChange(updated.connected);
      setStatus((prev) =>
        prev
          ? {
              ...prev,
              local: updated,
            }
          : prev
      );
    } catch (error) {
      setStatusError(apiErrorMessage(error, 'Could not update local fallback state.'));
    } finally {
      setTogglingLocal(false);
    }
  };

  const getSuggestionsForProvider = (providerId: string): string[] => {
    const providerItem = providers.find((item) => item.id === providerId);
    const raw =
      providerItem?.suggestedModels && providerItem.suggestedModels.length > 0
        ? providerItem.suggestedModels
        : SUGGESTED_MODELS_BY_PROVIDER[providerId] ?? [];
    const seen = new Set<string>();
    const deduped: string[] = [];
    for (const candidate of [
      ...(providerItem?.selectedModel ? [providerItem.selectedModel] : []),
      ...(providerItem?.defaultModel && providerItem.defaultModel !== 'local'
        ? [providerItem.defaultModel]
        : []),
      ...raw,
    ]) {
      const cleaned = candidate.trim();
      if (cleaned && !seen.has(cleaned)) {
        seen.add(cleaned);
        deduped.push(cleaned);
      }
    }
    return deduped;
  };

  const selectProvider = (providerId: string | null, closeMenu = true) => {
    onPreferredProviderChange(providerId);
    const nextSavedModel =
      providerId === null
        ? null
        : providers.find((item) => item.id === providerId)?.selectedModel ?? null;
    onModelOverrideChange?.(nextSavedModel);
    setSpecificModelInput(nextSavedModel ?? '');
    if (closeMenu) {
      setModelsOpen(false);
    }
  };

  const handleApplySpecificModel = async (providerId: string, rawModel: string | null) => {
    const cleaned = rawModel?.trim() || null;
    onPreferredProviderChange(providerId);
    onModelOverrideChange?.(cleaned);
    setSpecificModelInput(cleaned ?? '');
    setSavingModel(true);
    try {
      await byokService.setProviderModel(providerId, cleaned);
      await refreshModelsStatus();
    } catch {
      // Request-level modelOverride still applies even if status persistence is unavailable
    } finally {
      setSavingModel(false);
    }
  };

  const handleSaveApiKey = async () => {
    const trimmed = apiKeyInput.trim();
    if (trimmed.length < 8) {
      setKeyMessage({ kind: 'error', text: 'Paste a valid API key (at least 8 characters).' });
      return;
    }
    setSavingKey(true);
    setKeyMessage(null);
    try {
      const saved = await byokService.saveKey(keyProvider, trimmed);
      setApiKeyInput('');
      setKeyProvider(saved.provider);
      onPreferredProviderChange(saved.provider);
      onModelOverrideChange?.(null);
      setSpecificModelInput('');
      setKeyMessage({
        kind: 'success',
        text: `${saved.provider.toUpperCase()} key connected (${saved.keyHint}). Select a model in Models anytime.`,
      });
      await refreshModelsStatus();
    } catch (error) {
      setKeyMessage({
        kind: 'error',
        text: apiErrorMessage(error, 'Could not save API key. Check key format and provider.'),
      });
    } finally {
      setSavingKey(false);
    }
  };

  const handleRevokeKey = async (providerId: string) => {
    try {
      await byokService.revokeKey(providerId);
      if (preferredProvider === providerId) {
        onPreferredProviderChange(null);
        onModelOverrideChange?.(null);
        setSpecificModelInput('');
      }
      setKeyMessage({ kind: 'success', text: `Removed ${providerId} API key.` });
      await refreshModelsStatus();
    } catch (error) {
      setKeyMessage({
        kind: 'error',
        text: apiErrorMessage(error, `Could not remove ${providerId} API key.`),
      });
    }
  };

  const detectedProvider = keyProvider === 'auto' ? detectProviderPrefix(apiKeyInput) : null;
  const usage = status?.usage ?? null;
  const selectedProviderItem =
    preferredProvider !== null
      ? providers.find((item) => item.id === preferredProvider) ?? null
      : null;
  const effectiveSelectedModel =
    preferredProvider !== null
      ? modelOverride ?? selectedProviderItem?.selectedModel ?? null
      : null;

  const openKeyPopover = (providerChoice?: string) => {
    if (providerChoice) {
      setKeyProvider(providerChoice);
    }
    setKeyLayout(computePopoverLayout(keyButtonRef.current, menuPlacement, 360, 320));
    setModelsOpen(false);
    setKeyMessage(null);
    setKeyOpen(true);
  };

  const modelsPositionClass = `${modelsLayout.openUp ? 'bottom-full mb-1.5' : 'top-full mt-1.5'} ${
    modelsLayout.alignRight ? 'right-0' : 'left-0'
  }`;
  const keyPositionClass = `${keyLayout.openUp ? 'bottom-full mb-1.5' : 'top-full mt-1.5'} ${
    keyLayout.alignRight ? 'right-0' : 'left-0'
  }`;

  return (
    <div ref={containerRef} className="relative flex flex-wrap items-center gap-2">
      {/* Models dropdown button */}
      <div className="relative">
        <button
          ref={modelsButtonRef}
          type="button"
          disabled={disabled}
          onClick={() => {
            const next = !modelsOpen;
            if (next) {
              setModelsLayout(
                computePopoverLayout(modelsButtonRef.current, menuPlacement, 540, 660)
              );
              setKeyOpen(false);
              void refreshModelsStatus();
            }
            setModelsOpen(next);
          }}
          aria-expanded={modelsOpen}
          aria-haspopup="menu"
          aria-label="Models"
          className="flex h-8 cursor-pointer items-center gap-1.5 rounded-md border border-line bg-panel px-2.5 text-xs font-medium text-ink-soft transition-colors duration-150 hover:border-line-strong hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Cpu className="h-3.5 w-3.5 text-ink-muted" />
          <span className="text-ink-muted">Models</span>
          <span className="text-ink">{activeProviderLabel}</span>
          {effectiveSelectedModel ? (
            <span className="hidden max-w-[120px] truncate text-[10.5px] text-ink-muted sm:inline">
              ({effectiveSelectedModel})
            </span>
          ) : null}
          <span className="rounded bg-subtle px-1.5 py-0.5 text-[10.5px] font-medium text-ink-soft">
            {depthDisplayLabel(depth)}
          </span>
          {usage ? (
            <span
              className={`hidden rounded px-1.5 py-0.5 text-[10px] font-medium sm:inline ${
                usage.userRequestsRemainingToday <= 0
                  ? 'bg-danger/15 text-danger'
                  : usage.userDailyRequestCap > 0
                      && usage.userRequestsRemainingToday
                        <= Math.max(2, Math.ceil(usage.userDailyRequestCap * 0.15))
                    ? 'bg-amber-500/15 text-amber-700 dark:text-amber-300'
                    : 'bg-subtle text-ink-muted'
              }`}
              title={`Shared server daily quota: ${usage.sharedRequestsUsedToday} used of ${usage.userDailyRequestCap} requests today (${usage.userRequestsRemainingToday} left) across ${usage.enrolledUsers} active users. Own API key and Local Ollama are unlimited.`}
            >
              {usage.userRequestsRemainingToday} requests left
            </span>
          ) : null}
          {localStatus.available ? (
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                isLocalConnected ? 'bg-emerald-500' : 'bg-ink-muted/50'
              }`}
              title={isLocalConnected ? 'Local fallback connected' : 'Local fallback disconnected'}
            />
          ) : null}
          <ChevronDown
            className={`h-3.5 w-3.5 text-ink-muted transition-transform duration-150 ${
              modelsOpen ? 'rotate-180' : ''
            }`}
          />
        </button>

        {modelsOpen ? (
          <div
            role="menu"
            aria-label="Models and effort levels"
            style={{ maxHeight: `${modelsLayout.maxHeight}px` }}
            className={`absolute z-40 flex w-[min(660px,calc(100vw-2rem))] flex-col overflow-hidden rounded-lg border border-line bg-panel text-xs shadow-xl ${modelsPositionClass}`}
          >
            {/* Compact header */}
            <div className="flex shrink-0 items-center justify-between gap-2 border-b border-line bg-subtle/40 px-3 py-2">
              <div className="flex min-w-0 items-center gap-2">
                <span className="font-medium text-ink">Select model & effort</span>
                <span className="hidden truncate rounded bg-panel px-1.5 py-0.5 text-[10.5px] text-ink-muted sm:inline">
                  {activeProviderLabel}
                  {effectiveSelectedModel ? ` · ${effectiveSelectedModel}` : ''}
                  {` · ${depthDisplayLabel(depth)}`}
                </span>
              </div>
              <button
                type="button"
                aria-label="Done"
                onClick={() => setModelsOpen(false)}
                className="inline-flex h-6 shrink-0 cursor-pointer items-center gap-1 rounded px-1.5 text-[11px] font-medium text-ink-soft transition-colors hover:bg-subtle hover:text-ink"
              >
                <span>Done</span>
                <X className="h-3 w-3" />
              </button>
            </div>

            {/* Responsive 2-column body (scrolls safely on short screens) */}
            <div className="grid min-h-0 flex-1 grid-cols-1 overflow-y-auto overscroll-contain md:grid-cols-[1.2fr_1fr] md:overflow-hidden">
              {/* Left pane: Auto + providers + effort */}
              <div className="flex min-h-0 flex-col p-1.5 md:border-r md:border-line">
                {/* Auto smart router row */}
                <div
                  className={`flex shrink-0 items-center justify-between gap-2 rounded-md px-2 py-1.5 transition-colors ${
                    preferredProvider === null
                      ? 'bg-subtle ring-1 ring-inset ring-line-strong'
                      : 'hover:bg-subtle/60'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => selectProvider(null, true)}
                    className="flex min-w-0 flex-1 cursor-pointer items-center gap-1.5 text-left"
                  >
                    <span className="w-3.5 shrink-0">
                      {preferredProvider === null ? <Check className="h-3.5 w-3.5 text-accent" /> : null}
                    </span>
                    <div className="min-w-0">
                      <span className="block truncate font-medium text-ink">Auto (Smart Router)</span>
                      <span className="block truncate text-[10px] text-ink-muted">
                        Fastest healthy provider + failover
                      </span>
                    </div>
                  </button>
                  <div role="group" aria-label="Auto effort level" className="flex shrink-0 items-center gap-1">
                    {DEPTH_OPTIONS.map((opt) => {
                      const active = preferredProvider === null && depth === opt.value;
                      return (
                        <button
                          key={opt.value}
                          type="button"
                          aria-label={`Auto ${opt.label}`}
                          onClick={() => {
                            selectProvider(null, true);
                            onDepthChange(opt.value);
                          }}
                          className={`cursor-pointer rounded px-1.5 py-0.5 text-[10.5px] font-medium transition-colors ${
                            active
                              ? 'bg-solid text-on-solid'
                              : 'bg-subtle text-ink-soft hover:text-ink'
                          }`}
                        >
                          {opt.label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="my-1 shrink-0 border-t border-line" />

                {/* Provider list */}
                <div className="min-h-0 flex-1 space-y-0.5 pr-0.5 md:overflow-y-auto md:overscroll-contain">
                  {providers.map((item) => {
                    const isSelected = preferredProvider === item.id;
                    const badgeText = item.isLocal
                      ? item.available
                        ? item.defaultModel
                        : 'Not available'
                      : item.configuredByok
                        ? 'BYOK'
                        : item.configuredServer
                          ? 'Ready'
                          : 'Needs key';

                    return (
                      <div
                        key={item.id}
                        className={`flex items-center justify-between gap-2 rounded-md px-2 py-1 transition-colors ${
                          isSelected
                            ? 'bg-subtle ring-1 ring-inset ring-line-strong'
                            : 'hover:bg-subtle/60'
                        }`}
                      >
                        <button
                          type="button"
                          aria-label={`Select provider ${item.label}`}
                          onClick={() => selectProvider(item.id, false)}
                          className="flex min-w-0 flex-1 cursor-pointer items-center gap-1.5 text-left"
                        >
                          <span className="w-3.5 shrink-0">
                            {isSelected ? <Check className="h-3.5 w-3.5 text-accent" /> : null}
                          </span>
                          <div className="min-w-0">
                            <div className="flex items-center gap-1.5">
                              <span className="truncate font-medium text-ink">{item.label}</span>
                              <span
                                className={`shrink-0 rounded px-1 py-0 text-[10px] ${
                                  item.configured || (item.isLocal && item.available)
                                    ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                                    : 'bg-subtle text-ink-muted'
                                }`}
                              >
                                {badgeText}
                              </span>
                            </div>
                            {!item.isLocal ? (
                              <span className="block truncate text-[10px] text-ink-muted">
                                {isSelected && effectiveSelectedModel
                                  ? effectiveSelectedModel
                                  : item.defaultModel}
                              </span>
                            ) : null}
                          </div>
                        </button>

                        <div
                          role="group"
                          aria-label={`${item.label} effort level`}
                          className="flex shrink-0 items-center gap-1"
                        >
                          {DEPTH_OPTIONS.map((opt) => {
                            const active = isSelected && depth === opt.value;
                            return (
                              <button
                                key={opt.value}
                                type="button"
                                aria-label={`${item.label} ${opt.label}`}
                                onClick={() => {
                                  selectProvider(item.id, true);
                                  onDepthChange(opt.value);
                                }}
                                className={`cursor-pointer rounded px-1.5 py-0.5 text-[10.5px] font-medium transition-colors ${
                                  active
                                    ? 'bg-solid text-on-solid'
                                    : 'bg-subtle text-ink-soft hover:text-ink'
                                }`}
                              >
                                {opt.label}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Right pane: Specific model picker + Local fallback */}
              <div className="flex min-h-0 flex-col justify-between gap-2.5 border-t border-line bg-subtle/25 p-2.5 md:overflow-y-auto md:overscroll-contain md:border-t-0">
                <div className="rounded-md border border-line bg-panel p-2.5">
                  {preferredProvider !== null ? (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[11px] font-medium text-ink">
                          Model for {selectedProviderItem?.label ?? preferredProvider}
                        </span>
                        {effectiveSelectedModel ? (
                          <button
                            type="button"
                            disabled={savingModel}
                            onClick={() => void handleApplySpecificModel(preferredProvider, null)}
                            className="cursor-pointer text-[10.5px] text-ink-muted transition-colors hover:text-ink"
                          >
                            Reset default
                          </button>
                        ) : null}
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {getSuggestionsForProvider(preferredProvider).map((modelName) => {
                          const active = effectiveSelectedModel === modelName;
                          return (
                            <button
                              key={modelName}
                              type="button"
                              disabled={savingModel}
                              aria-label={`Select model ${modelName}`}
                              onClick={() =>
                                void handleApplySpecificModel(preferredProvider, modelName)
                              }
                              className={`cursor-pointer rounded px-1.5 py-0.5 text-[10.5px] transition-colors ${
                                active
                                  ? 'bg-solid text-on-solid'
                                  : 'border border-line bg-subtle text-ink-soft hover:border-line-strong hover:text-ink'
                              }`}
                            >
                              {modelName}
                            </button>
                          );
                        })}
                      </div>
                      <div className="flex items-center gap-1.5">
                        <input
                          type="text"
                          aria-label="Specific model name"
                          value={specificModelInput}
                          onChange={(e) => setSpecificModelInput(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault();
                              void handleApplySpecificModel(preferredProvider, specificModelInput);
                            }
                          }}
                          placeholder="Or type custom model ID"
                          className="h-7 min-w-0 flex-1 rounded border border-line bg-subtle px-2 text-[11px] text-ink placeholder:text-ink-muted outline-none focus:border-accent"
                        />
                        <button
                          type="button"
                          disabled={savingModel || !specificModelInput.trim()}
                          onClick={() =>
                            void handleApplySpecificModel(preferredProvider, specificModelInput)
                          }
                          className="h-7 shrink-0 cursor-pointer rounded bg-solid px-2 text-[11px] font-medium text-on-solid transition-colors hover:bg-solid-hover disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          Use model
                        </button>
                      </div>
                      {selectedProviderItem && !selectedProviderItem.configured && !selectedProviderItem.isLocal ? (
                        <div className="flex items-center justify-between gap-2 border-t border-line pt-1.5 text-[10.5px]">
                          <span className="text-ink-muted">
                            Requires your {selectedProviderItem.label} API key.
                          </span>
                          <button
                            type="button"
                            onClick={() => openKeyPopover(selectedProviderItem.id)}
                            className="shrink-0 cursor-pointer font-medium text-accent hover:underline"
                          >
                            Add {selectedProviderItem.label} key
                          </button>
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <div className="space-y-1">
                      <span className="block text-[11px] font-medium text-ink">
                        Smart model selection
                      </span>
                      <p className="text-[11px] leading-relaxed text-ink-muted">
                        Auto picks the fastest healthy provider with automatic failover. Click any
                        provider on the left to pick a suggested latest model or enter a custom model
                        ID.
                      </p>
                    </div>
                  )}
                </div>

                {/* Local fallback section */}
                <div className="rounded-md border border-line bg-panel p-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-medium text-ink">
                        <span className="whitespace-nowrap">Local model fallback</span>
                        <span
                          className={`whitespace-nowrap rounded px-1.5 py-0 text-[10px] font-medium ${
                            localStatus.available
                              ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                              : 'bg-subtle text-ink-muted'
                          }`}
                        >
                          {localStatus.available ? 'Available' : 'Not available'}
                        </span>
                      </div>
                      <p className="mt-0.5 text-[10.5px] leading-snug text-ink-muted">
                        {localStatus.available
                          ? `Fallback -> ${localStatus.activeModel ?? localStatus.configuredModel}`
                          : 'Start Ollama locally to use it as last fallback'}
                      </p>
                    </div>

                    <button
                      type="button"
                      disabled={!localStatus.available || togglingLocal}
                      onClick={() => void handleToggleLocalFallback()}
                      className={`inline-flex shrink-0 cursor-pointer items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                        isLocalConnected
                          ? 'border-emerald-500/40 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                          : 'border-line bg-subtle text-ink-soft hover:border-line-strong hover:text-ink'
                      }`}
                    >
                      {isLocalConnected ? (
                        <PlugZap className="h-3 w-3" />
                      ) : (
                        <Plug className="h-3 w-3" />
                      )}
                      <span>{isLocalConnected ? 'Connected' : 'Disconnected'}</span>
                    </button>
                  </div>
                  {statusError ? <p className="mt-1 text-[10.5px] text-danger">{statusError}</p> : null}
                </div>

                {/* User usage & dynamic daily cap */}
                {usage ? (
                  <div className="rounded-md border border-line bg-panel p-2.5" aria-label="Model usage and daily cap">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[11px] font-medium text-ink">Daily server quota & usage</span>
                      <span className="text-[10px] text-ink-muted">Resets 00:00 UTC</span>
                    </div>
                    <div className="mt-1.5 flex items-baseline justify-between gap-2 text-[10.5px]">
                      <span className="text-ink-muted">Shared requests used today</span>
                      <span className="font-medium tabular-nums text-ink">
                        {usage.sharedRequestsUsedToday} / {usage.userDailyRequestCap} requests ({usage.userRequestsRemainingToday} left)
                      </span>
                    </div>
                    <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-subtle">
                      <div
                        className={`h-full rounded-full transition-all ${
                          usage.userRequestsRemainingToday <= 0
                            ? 'bg-danger'
                            : 'bg-accent'
                        }`}
                        style={{
                          width: `${
                            usage.userDailyRequestCap > 0
                              ? Math.min(
                                  100,
                                  Math.round(
                                    (usage.sharedRequestsUsedToday / usage.userDailyRequestCap) * 100
                                  )
                                )
                              : 100
                          }%`,
                        }}
                      />
                    </div>
                    <dl className="mt-2 space-y-0.5 text-[10px] leading-snug text-ink-muted">
                      <div className="flex items-center justify-between gap-2">
                        <dt>Global server API pool remaining</dt>
                        <dd className="tabular-nums text-ink-soft">
                          {usage.systemPoolRemaining} of {usage.systemPoolTotal} requests
                        </dd>
                      </div>
                      <div className="flex items-center justify-between gap-2">
                        <dt>Fair share across active accounts</dt>
                        <dd className="tabular-nums text-ink-soft">
                          {usage.enrolledUsers} active {usage.enrolledUsers === 1 ? 'user' : 'users'}
                        </dd>
                      </div>
                      <div className="flex items-center justify-between gap-2">
                        <dt>Your total today (all models)</dt>
                        <dd className="tabular-nums text-ink-soft">
                          {usage.totalRequestsToday} requests · {formatCompactTokens(usage.totalTokensToday)} tokens
                        </dd>
                      </div>
                      <div className="flex items-center justify-between gap-2">
                        <dt>Own API key &amp; local (uncapped)</dt>
                        <dd className="tabular-nums text-ink-soft">
                          {usage.byokRequestsToday} BYOK · {usage.localRequestsToday} Local
                        </dd>
                      </div>
                    </dl>
                    {usage.models.length > 0 ? (
                      <div className="mt-2 space-y-1 border-t border-line pt-1.5">
                        <div className="flex items-center justify-between text-[10px] text-ink-muted">
                          <span className="font-medium">Models you used</span>
                          <span>today · total · tokens</span>
                        </div>
                        <div className="max-h-20 space-y-0.5 overflow-y-auto pr-0.5">
                          {usage.models.map((item) => (
                            <div
                              key={`${item.provider}:${item.modelName}`}
                              className="flex items-center justify-between gap-2 text-[10px]"
                            >
                              <span className="min-w-0 truncate text-ink-soft">
                                {item.provider} / {item.modelName}
                              </span>
                              <span className="shrink-0 tabular-nums text-ink-muted">
                                {item.requestsToday} today · {item.totalRequests} total · {formatCompactTokens(item.totalTokens)} tokens
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <p className="mt-1.5 border-t border-line pt-1.5 text-[10px] text-ink-muted">
                        No model requests recorded on your account yet.
                      </p>
                    )}
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}
      </div>

      {/* Apply my API key button & popover */}
      <div className="relative">
        <button
          ref={keyButtonRef}
          type="button"
          disabled={disabled}
          onClick={() => {
            if (keyOpen) {
              setKeyOpen(false);
            } else {
              openKeyPopover();
            }
          }}
          aria-expanded={keyOpen}
          className="flex h-8 cursor-pointer items-center gap-1.5 rounded-md border border-line bg-panel px-2.5 text-xs font-medium text-ink-soft transition-colors duration-150 hover:border-line-strong hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
        >
          <KeyRound className="h-3.5 w-3.5 text-ink-muted" />
          <span>Apply my API key</span>
          {byokCount > 0 ? (
            <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10.5px] font-medium text-emerald-700 dark:text-emerald-300">
              {byokCount}
            </span>
          ) : null}
        </button>

        {keyOpen ? (
          <div
            role="dialog"
            aria-label="Apply my API key"
            style={{ maxHeight: `${keyLayout.maxHeight}px` }}
            className={`absolute z-40 w-80 max-w-[calc(100vw-2rem)] overflow-y-auto overscroll-contain rounded-lg border border-line bg-panel p-3 text-xs shadow-xl ${keyPositionClass}`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-medium text-ink">Use your own API key</p>
                <p className="mt-0.5 text-[11px] text-ink-muted">Stored encrypted, only for your account.</p>
              </div>
              <div className="flex shrink-0 items-center">
                <button
                  type="button"
                  aria-label="Close API key dialog"
                  onClick={() => setKeyOpen(false)}
                  className="inline-flex h-5 w-5 cursor-pointer items-center justify-center rounded text-ink-muted transition-colors hover:bg-subtle hover:text-ink"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            </div>

            <div className="mt-2.5 space-y-2">
              <label className="block">
                <span className="mb-1 block text-[11px] text-ink-muted">Provider</span>
                <select
                  aria-label="API key provider"
                  value={keyProvider}
                  onChange={(e) => setKeyProvider(e.target.value)}
                  className="h-8 w-full rounded-md border border-line bg-subtle px-2 text-xs text-ink outline-none focus:border-accent"
                >
                  {API_KEY_PROVIDER_CHOICES.map((choice) => (
                    <option key={choice.id} value={choice.id}>
                      {choice.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block">
                <span className="mb-1 flex items-center justify-between text-[11px] text-ink-muted">
                  <span>API key</span>
                  {detectedProvider ? (
                    <span className="text-emerald-700 dark:text-emerald-300">
                      Detected: {detectedProvider}
                    </span>
                  ) : null}
                </span>
                <input
                  type="password"
                  aria-label="Paste API key"
                  value={apiKeyInput}
                  onChange={(e) => {
                    setApiKeyInput(e.target.value);
                    if (keyMessage) setKeyMessage(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      void handleSaveApiKey();
                    }
                  }}
                  placeholder="Paste Gemini, Groq, OpenAI, Claude, or Grok key"
                  className="h-8 w-full rounded-md border border-line bg-subtle px-2.5 text-xs text-ink placeholder:text-ink-muted outline-none focus:border-accent"
                />
              </label>

              <button
                type="button"
                disabled={savingKey || !apiKeyInput.trim()}
                onClick={() => void handleSaveApiKey()}
                className="flex h-8 w-full cursor-pointer items-center justify-center rounded-md bg-solid px-3 text-xs font-medium text-on-solid transition-colors hover:bg-solid-hover disabled:cursor-not-allowed disabled:opacity-50"
              >
                {savingKey ? 'Saving key…' : 'Save & integrate key'}
              </button>

              {keyMessage ? (
                <p
                  className={`text-[11px] ${
                    keyMessage.kind === 'success'
                      ? 'text-emerald-700 dark:text-emerald-300'
                      : 'text-danger'
                  }`}
                >
                  {keyMessage.text}
                </p>
              ) : null}

              {byokCount > 0 ? (
                <div className="border-t border-line pt-2">
                  <span className="block text-[10.5px] font-medium text-ink-muted">
                    Connected keys
                  </span>
                  <div className="mt-1.5 space-y-1">
                    {providers
                      .filter((item) => item.configuredByok)
                      .map((item) => (
                        <div
                          key={item.id}
                          className="flex items-center justify-between rounded bg-subtle px-2 py-1 text-[11px]"
                        >
                          <span className="text-ink">
                            {item.label}{' '}
                            {item.keyHint ? (
                              <span className="text-ink-muted">({item.keyHint})</span>
                            ) : null}
                          </span>
                          <button
                            type="button"
                            onClick={() => void handleRevokeKey(item.id)}
                            aria-label={`Remove ${item.label} key`}
                            className="cursor-pointer text-ink-muted hover:text-danger"
                          >
                            <Trash2 className="h-3 w-3" />
                          </button>
                        </div>
                      ))}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
};
