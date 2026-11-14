import React from 'react';
import { Menu, X } from 'lucide-react';
import { ThemeToggle } from './ThemeToggle';
import { useMobileNav } from './MobileNavContext';

interface TopBarProps {
  breadcrumbs?: React.ReactNode;
  rightActions?: React.ReactNode;
}

export const TopBar: React.FC<TopBarProps> = ({
  breadcrumbs,
  rightActions,
}) => {
  const mobileNav = useMobileNav();

  return (
    <header className="fixed left-0 right-0 top-0 z-40 flex h-14 items-center justify-between gap-3 border-b border-line bg-canvas/85 px-3 backdrop-blur-md supports-[backdrop-filter]:bg-canvas/75 sm:px-6 lg:left-[var(--sidebar-w,0px)] transition-[left] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]">
      <div className="flex min-w-0 items-center gap-2">
        {mobileNav && (
          <button
            type="button"
            onClick={mobileNav.toggle}
            aria-label={mobileNav.open ? 'Close navigation' : 'Open navigation'}
            aria-expanded={mobileNav.open}
            className="-ml-1 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-ink-soft hover:bg-subtle hover:text-ink lg:hidden"
          >
            {mobileNav.open ? <X className="h-[18px] w-[18px]" /> : <Menu className="h-[18px] w-[18px]" />}
          </button>
        )}
        <div className="flex min-w-0 items-center gap-2 overflow-hidden text-[13px] text-ink-soft">
          {breadcrumbs}
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {rightActions}
        <ThemeToggle className="hidden lg:inline-flex" />
      </div>
    </header>
  );
};
