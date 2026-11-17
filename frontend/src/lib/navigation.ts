/** Which main sidebar section a route belongs to, so the sidebar can show where the user is. */
export type NavSection = 'new-research' | 'projects' | 'library' | 'settings' | 'research' | null;

const startsWithSegment = (pathname: string, base: string) =>
  pathname === base || pathname.startsWith(`${base}/`);

export const activeSection = (pathname: string): NavSection => {
  const path = pathname.replace(/\/+$/, '') || '/';
  if (path === '/research/new') return 'new-research';
  if (startsWithSegment(path, '/projects')) return 'projects';
  if (startsWithSegment(path, '/library')) return 'library';
  if (startsWithSegment(path, '/settings')) return 'settings';
  // An open report or run: the matching item in the research history is highlighted instead.
  if (startsWithSegment(path, '/research')) return 'research';
  return null;
};

/** Main navigation item: a soft accent background and a small bar on the left when active. */
export const navItemClass = (active: boolean) =>
  `group relative flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13px] transition-colors ${
    active
      ? "bg-accent-muted font-medium text-ink before:absolute before:inset-y-1.5 before:left-0 before:w-[3px] before:rounded-full before:bg-accent before:content-['']"
      : 'text-ink-soft hover:bg-subtle hover:text-ink'
  }`;

export const navIconClass = (active: boolean) =>
  `h-4 w-4 shrink-0 ${active ? 'text-accent' : 'text-ink-muted group-hover:text-ink-soft'}`;

/**
 * "New research" is an action, so it keeps its own outlined button look on every page
 * and only takes the accent colours while the user is actually on the new research page.
 */
export const newResearchClass = (active: boolean) =>
  `flex h-9 items-center gap-2 rounded-md border px-2.5 text-[13px] font-medium shadow-xs transition-colors ${
    active
      ? 'border-accent-line bg-accent-muted text-ink'
      : 'border-line-strong bg-panel text-ink hover:border-accent-line hover:bg-accent-soft'
  }`;

/** Icon buttons in the collapsed sidebar rail. */
export const railButtonClass = (active = false) =>
  `rail-tip inline-flex h-9 w-9 items-center justify-center rounded-md transition-colors ${
    active ? 'bg-accent-muted text-accent' : 'text-ink-muted hover:bg-subtle hover:text-ink'
  }`;
