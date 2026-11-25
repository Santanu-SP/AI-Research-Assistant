import type { ModelFailureType, ResearchProgressResponse } from '../types/progress';

const PROVIDER_LABELS: Record<string, string> = {
  gemini: 'Gemini',
  openrouter: 'OpenRouter',
  cerebras: 'Cerebras',
  mistral: 'Mistral',
  groq: 'Groq',
  openai: 'OpenAI',
  claude: 'Claude',
  grok: 'Grok',
  ollama: 'the local model',
};

const UPPERCASE_WORDS = new Set(['gpt', 'ai', 'oss', 'llm']);

/** "gemini-2.5-pro" -> "Gemini 2.5 Pro", "openrouter/free" -> "OpenRouter Free". */
export const prettyModelName = (provider?: string | null, model?: string | null): string => {
  const providerLabel = provider ? PROVIDER_LABELS[provider] ?? provider : 'The model';
  const raw = model?.trim();
  if (!raw) return providerLabel;
  const lastPart = raw.split('/').pop() ?? raw;
  const words = lastPart
    .replace(/:free$/i, '')
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((word) => {
      const lower = word.toLowerCase();
      if (UPPERCASE_WORDS.has(lower)) return lower.toUpperCase();
      if (PROVIDER_LABELS[lower] && lower !== 'ollama') return PROVIDER_LABELS[lower];
      return /^\d/.test(word) ? word : word.charAt(0).toUpperCase() + word.slice(1);
    });
  const name = words.join(' ');
  // Keep the provider in front when the model name doesn't already say it.
  if (provider && PROVIDER_LABELS[provider] && provider !== 'ollama' && !name.toLowerCase().startsWith(PROVIDER_LABELS[provider].toLowerCase())) {
    return `${PROVIDER_LABELS[provider]} ${name}`;
  }
  return name || providerLabel;
};

export interface ModelFailureMessage {
  title: string;
  detail: string;
  /** Whether picking another model is the obvious next step. */
  suggestSwitch: boolean;
}

const MESSAGES: Record<ModelFailureType, (name: string) => ModelFailureMessage> = {
  quota: (name) => ({
    title: `${name} hit its free limit`,
    detail: 'Pick a lighter model such as a Flash one, add your own API key, or try again later.',
    suggestSwitch: true,
  }),
  auth: (name) => ({
    title: `Your API key was rejected by ${name}`,
    detail: 'The key may be wrong, expired or missing access to this model. Update it in Settings, or switch to another model.',
    suggestSwitch: true,
  }),
  timeout: (name) => ({
    title: `${name} timed out`,
    detail: 'It took too long to reply. Try again, use a lighter depth, or switch to a faster model.',
    suggestSwitch: true,
  }),
  unavailable: (name) => ({
    title: `${name} isn’t available right now`,
    detail: 'The model may be busy or switched off. Try again in a moment or switch to another model.',
    suggestSwitch: true,
  }),
  other: (name) => ({
    title: `${name} couldn’t write the answer`,
    detail: 'Try again, or switch to another model.',
    suggestSwitch: true,
  }),
};

/** A plain-words reason for a model failure, or null when the run failed for another reason. */
export const describeModelFailure = (
  progress: Pick<ResearchProgressResponse, 'failureType' | 'failureProvider' | 'failureModel'>,
): ModelFailureMessage | null => {
  if (!progress.failureType) return null;
  const name = prettyModelName(progress.failureProvider, progress.failureModel);
  return (MESSAGES[progress.failureType] ?? MESSAGES.other)(name);
};

const SECRET_PATTERNS: RegExp[] = [
  /AIza[0-9A-Za-z_-]{10,}/g,
  /\bAQ\.[0-9A-Za-z_-]{10,}/g,
  /\b(?:sk|pk|gsk|csk|xai)[-_][0-9A-Za-z_-]{8,}/g,
  /Bearer\s+[0-9A-Za-z._-]{8,}/gi,
  /\b(key|token|secret)=([^&\s]{6,})/gi,
];

/** Hides anything that looks like an API key before text is shown. */
export const redactSecrets = (text: string): string =>
  SECRET_PATTERNS.reduce(
    (out, pattern) => out.replace(pattern, (match, name) => (typeof name === 'string' && match.includes('=') ? `${name}=[hidden]` : '[hidden]')),
    text,
  );
