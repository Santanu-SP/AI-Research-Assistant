/**
 * Remembers, per project and per browser, whether "Also find sources online"
 * was left on. It is off until someone turns it on.
 */
const storageKey = (projectId: string) => `ara.projectFindOnline.${projectId}`;

export const loadFindOnline = (projectId: string): boolean => {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(storageKey(projectId)) === '1';
  } catch {
    return false;
  }
};

export const saveFindOnline = (projectId: string, enabled: boolean): void => {
  if (typeof window === 'undefined') return;
  try {
    if (enabled) window.localStorage.setItem(storageKey(projectId), '1');
    else window.localStorage.removeItem(storageKey(projectId));
  } catch {
    // Private mode or full storage: the switch still works for this visit.
  }
};
