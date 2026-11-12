export const isMacPlatform = (): boolean =>
  typeof navigator !== 'undefined' && /Mac|iPhone|iPad|iPod/i.test(navigator.platform || navigator.userAgent);

/** Human label for a shortcut, e.g. "⌘K" on macOS and "Ctrl K" elsewhere. */
export const shortcutLabel = (key: string, { shift = false } = {}): string =>
  isMacPlatform() ? `${shift ? '⇧' : ''}⌘${key}` : `Ctrl ${shift ? 'Shift ' : ''}${key}`;

/** True when the event is Cmd (macOS) or Ctrl (elsewhere) plus the given key. */
export const isModShortcut = (event: KeyboardEvent, key: string, { shift = false } = {}): boolean =>
  (event.metaKey || event.ctrlKey) &&
  event.shiftKey === shift &&
  !event.altKey &&
  event.key.toLowerCase() === key.toLowerCase();
