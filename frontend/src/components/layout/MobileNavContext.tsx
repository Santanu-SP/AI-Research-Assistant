import { createContext, useContext } from 'react';

interface MobileNavState {
  open: boolean;
  toggle: () => void;
}

export const MobileNavContext = createContext<MobileNavState | null>(null);

/** Lets the page top bar open the navigation drawer on small screens. */
export const useMobileNav = (): MobileNavState | null => useContext(MobileNavContext);
