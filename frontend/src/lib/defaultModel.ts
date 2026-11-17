/** The model new research starts with. Chosen in Settings, kept on this device. */
export interface DefaultModelChoice {
  /** null means Auto: the app picks the best model that is available. */
  provider: string | null;
  model: string | null;
}

export const DEFAULT_MODEL_STORAGE_KEY = 'research-assistant-default-model';
export const DEFAULT_MODEL_CHANGE_EVENT = 'default-model:change';

const AUTO: DefaultModelChoice = { provider: null, model: null };

export const getDefaultModel = (): DefaultModelChoice => {
  try {
    const raw = window.localStorage.getItem(DEFAULT_MODEL_STORAGE_KEY);
    if (!raw) return AUTO;
    const parsed = JSON.parse(raw) as Partial<DefaultModelChoice>;
    const provider = typeof parsed.provider === 'string' && parsed.provider ? parsed.provider : null;
    const model = provider && typeof parsed.model === 'string' && parsed.model ? parsed.model : null;
    return { provider, model };
  } catch {
    return AUTO;
  }
};

export const setDefaultModel = (choice: DefaultModelChoice): void => {
  try {
    if (!choice.provider) {
      window.localStorage.removeItem(DEFAULT_MODEL_STORAGE_KEY);
    } else {
      window.localStorage.setItem(
        DEFAULT_MODEL_STORAGE_KEY,
        JSON.stringify({ provider: choice.provider, model: choice.model || null }),
      );
    }
  } catch {
    // Private mode or full storage: the choice simply isn't remembered.
  }
  window.dispatchEvent(new Event(DEFAULT_MODEL_CHANGE_EVENT));
};
