import React, { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { CenteredLoadingState } from '../common/LoadingState';
import { AppSidebar } from './AppSidebar';
import { AnimatedResearchBackground } from './AnimatedResearchBackground';
import { MobileNavContext } from './MobileNavContext';
import { ResearchHistoryProvider } from '../../app/ResearchHistoryContext';
import { isModShortcut } from '../../lib/shortcuts';

const SIDEBAR_WIDTH = 260;
const COLLAPSED_KEY = 'research-assistant-sidebar-collapsed';

const readCollapsed = () => {
  try {
    return window.localStorage.getItem(COLLAPSED_KEY) === '1';
  } catch {
    return false;
  }
};

const isLargeScreen = () => window.matchMedia('(min-width: 1024px)').matches;

export const AppLayout: React.FC = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [searchFocusSignal, setSearchFocusSignal] = useState(0);
  const location = useLocation();
  const navigate = useNavigate();

  // Close the drawer when the route changes.
  useEffect(() => {
    setMobileMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    try {
      window.localStorage.setItem(COLLAPSED_KEY, collapsed ? '1' : '0');
    } catch {
      // The sidebar still toggles when storage is unavailable.
    }
  }, [collapsed]);

  const toggleCollapsed = useCallback(() => setCollapsed((value) => !value), []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && mobileMenuOpen) {
        setMobileMenuOpen(false);
        return;
      }
      if (isModShortcut(event, 'k')) {
        event.preventDefault();
        if (isLargeScreen()) setCollapsed(false);
        else setMobileMenuOpen(true);
        setSearchFocusSignal((value) => value + 1);
        return;
      }
      if (isModShortcut(event, 'o', { shift: true })) {
        event.preventDefault();
        navigate('/research/new');
        return;
      }
      if (isModShortcut(event, 's', { shift: true })) {
        event.preventDefault();
        if (isLargeScreen()) toggleCollapsed();
        else setMobileMenuOpen((open) => !open);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [mobileMenuOpen, navigate, toggleCollapsed]);

  const toggle = useCallback(() => setMobileMenuOpen((open) => !open), []);
  const mobileNav = useMemo(
    () => ({ open: mobileMenuOpen, toggle, collapsed, toggleCollapsed }),
    [mobileMenuOpen, toggle, collapsed, toggleCollapsed],
  );

  const motionMode = location.pathname.endsWith('/progress')
    ? 'progress'
    : location.pathname === '/research/new'
      ? 'composer'
      : /^\/research\/[^/]+$/.test(location.pathname)
        ? 'reading'
        : 'workspace';

  const layoutStyle = {
    '--sidebar-w': collapsed ? '0px' : `${SIDEBAR_WIDTH}px`,
  } as React.CSSProperties;

  return (
    <ResearchHistoryProvider>
      <MobileNavContext.Provider value={mobileNav}>
        <div className="relative isolate min-h-screen overflow-x-clip bg-canvas text-ink" style={layoutStyle}>
          <a
            href="#main-content"
            className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[100] focus:rounded-md focus:bg-panel focus:px-3 focus:py-2 focus:text-sm focus:shadow-md"
          >
            Skip to content
          </a>

          <AnimatedResearchBackground mode={motionMode} />

          <div
            className={`fixed inset-y-0 left-0 z-50 hidden transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] lg:block ${
              collapsed ? '-translate-x-full' : 'translate-x-0'
            }`}
            style={{ width: SIDEBAR_WIDTH }}
            aria-hidden={collapsed}
            inert={collapsed ? true : undefined}
          >
            <AppSidebar variant="desktop" searchFocusSignal={searchFocusSignal} />
          </div>

          {mobileMenuOpen && (
            <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
              <div className="overlay-enter fixed inset-0 bg-ink/30" onClick={() => setMobileMenuOpen(false)} />
              <div className="drawer-enter relative z-10 h-full w-[300px] max-w-[86vw] shadow-xl">
                <AppSidebar
                  variant="drawer"
                  searchFocusSignal={searchFocusSignal}
                  onNavigate={() => setMobileMenuOpen(false)}
                />
              </div>
            </div>
          )}

          <div
            id="main-content"
            className="app-content-surface relative z-10 flex min-h-screen flex-col transition-[padding] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] lg:pl-[var(--sidebar-w)]"
          >
            <Suspense fallback={<CenteredLoadingState label="Loading…" />}>
              <div key={location.pathname} className="page-enter flex min-h-screen flex-1 flex-col">
                <Outlet />
              </div>
            </Suspense>
          </div>
        </div>
      </MobileNavContext.Provider>
    </ResearchHistoryProvider>
  );
};
