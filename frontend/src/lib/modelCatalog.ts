/** Models offered for each provider when the server doesn't send its own list. */
export const SUGGESTED_MODELS_BY_PROVIDER: Record<string, string[]> = {
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
