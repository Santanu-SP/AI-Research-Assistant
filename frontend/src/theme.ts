export type AppTheme = 'light' | 'dark';

export const THEME_CHANGE_EVENT = 'research-assistant-theme-change';

const THEME_STORAGE_KEY = 'research-assistant-theme';

const getStoredTheme = (): AppTheme | null => {
  try {
    const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
    return storedTheme === 'light' || storedTheme === 'dark' ? storedTheme : null;
  } catch {
    return null;
  }
};

export const getAppliedTheme = (): AppTheme =>
  document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';

export const applyTheme = (theme: AppTheme, persist = false) => {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;

  if (persist) {
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      // Theme selection still works when storage is unavailable.
    }
  }

  window.dispatchEvent(
    new CustomEvent<AppTheme>(THEME_CHANGE_EVENT, { detail: theme }),
  );
};

export const initializeTheme = () => {
  const storedTheme = getStoredTheme();
  const systemTheme: AppTheme = window.matchMedia('(prefers-color-scheme: dark)')
    .matches
    ? 'dark'
    : 'light';

  applyTheme(storedTheme ?? systemTheme);

  const colorSchemeQuery = window.matchMedia('(prefers-color-scheme: dark)');
  colorSchemeQuery.addEventListener('change', (event) => {
    if (getStoredTheme() === null) {
      applyTheme(event.matches ? 'dark' : 'light');
    }
  });
};
