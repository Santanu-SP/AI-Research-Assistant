import React, { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { CenteredLoadingState } from '../common/LoadingState';
import { AppSidebar } from './AppSidebar';
import { MobileNavContext } from './MobileNavContext';

export const AppLayout: React.FC = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const location = useLocation();

  // Close the drawer when the route changes.
  useEffect(() => {
    setMobileMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!mobileMenuOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMobileMenuOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [mobileMenuOpen]);

  const toggle = useCallback(() => setMobileMenuOpen((open) => !open), []);
  const mobileNav = useMemo(() => ({ open: mobileMenuOpen, toggle }), [mobileMenuOpen, toggle]);

  return (
    <MobileNavContext.Provider value={mobileNav}>
      <div className="relative min-h-screen overflow-x-clip bg-canvas text-ink">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[100] focus:rounded-md focus:bg-panel focus:px-3 focus:py-2 focus:text-sm focus:shadow-md"
        >
          Skip to content
        </a>

        <div className="hidden lg:block">
          <AppSidebar />
        </div>

        {mobileMenuOpen && (
          <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
            <div
              className="fixed inset-0 bg-ink/30"
              onClick={() => setMobileMenuOpen(false)}
            />
            <div className="relative z-10 h-full w-[280px] max-w-[85vw] shadow-xl">
              <AppSidebar className="!relative !w-full" onNavigate={() => setMobileMenuOpen(false)} />
            </div>
          </div>
        )}

        <div id="main-content" className="relative flex min-h-screen flex-col lg:pl-[248px]">
          <Suspense fallback={<CenteredLoadingState label="Loading…" />}>
            <Outlet />
          </Suspense>
        </div>
      </div>
    </MobileNavContext.Provider>
  );
};
