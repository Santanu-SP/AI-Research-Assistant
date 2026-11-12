import { createContext, useContext } from 'react';

interface MobileNavState {
  /** Drawer state on small screens. */
  open: boolean;
  toggle: () => void;
  /** Whether the sidebar is hidden on large screens. */
  collapsed?: boolean;
  toggleCollapsed?: () => void;
}

export const MobileNavContext = createContext<MobileNavState | null>(null);

/** Lets the page top bar open the drawer on small screens or bring the sidebar back on large ones. */
export const useMobileNav = (): MobileNavState | null => useContext(MobileNavContext);
