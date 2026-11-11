import React, { Suspense, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { CenteredLoadingState } from '../common/LoadingState';
import { AppSidebar } from './AppSidebar';
import { AnimatedResearchBackground } from './AnimatedResearchBackground';
import { ThemeToggle } from './ThemeToggle';
import { Menu, X } from 'lucide-react';
import { useAuth } from '../../app/AuthContext';

export const AppLayout: React.FC = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const location = useLocation();
  const { user } = useAuth();

  // Close mobile drawer on route transition
  React.useEffect(() => {
    setMobileMenuOpen(false);
  }, [location.pathname]);

  const motionMode = location.pathname.endsWith('/progress')
    ? 'progress'
    : location.pathname === '/research/new'
      ? 'composer'
      : /^\/research\/[^/]+$/.test(location.pathname)
        ? 'reading'
        : 'workspace';

  return (
    <div className="relative isolate min-h-screen overflow-x-clip bg-canvas text-ink">
      <AnimatedResearchBackground mode={motionMode} />

      <div className="hidden lg:block">
        <AppSidebar />
      </div>

      <div className="app-chrome-surface lg:hidden fixed top-0 left-0 right-0 h-14 border-b border-line z-50 flex items-center justify-between px-4">
        <button
          type="button"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="p-1.5 rounded-md text-ink hover:bg-accent-soft transition-colors"
          aria-label="Toggle navigation menu"
        >
          {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>

        <span className="font-semibold text-sm tracking-tight text-ink">
          Research Assistant
        </span>

        <div className="flex items-center gap-2">
          <ThemeToggle className="inline-flex lg:hidden" />
          <div className="w-8 h-8 rounded-full bg-accent-muted text-accent font-semibold text-xs flex items-center justify-center border border-line-strong">
            {user?.name.slice(0, 1).toUpperCase() || 'R'}
          </div>
        </div>
      </div>

      {mobileMenuOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="fixed inset-0 bg-black/40 backdrop-blur-xs transition-opacity"
            onClick={() => setMobileMenuOpen(false)}
          />
          <div className="relative w-[280px] h-full bg-canvas shadow-2xl z-10 animate-in slide-in-from-left duration-200">
            <AppSidebar className="w-full relative shadow-none border-r border-line" />
          </div>
        </div>
      )}

      <div className="app-content-surface relative z-10 lg:pl-[232px] pt-14 lg:pt-0 min-h-screen flex flex-col">
        <Suspense fallback={<CenteredLoadingState label="Loading…" />}>
          <Outlet />
        </Suspense>
      </div>
    </div>
  );
};
