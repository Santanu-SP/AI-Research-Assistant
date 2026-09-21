import React from 'react';
import { ThemeToggle } from './ThemeToggle';

interface TopBarProps {
  breadcrumbs?: React.ReactNode;
  rightActions?: React.ReactNode;
}

export const TopBar: React.FC<TopBarProps> = ({
  breadcrumbs,
  rightActions,
}) => {
  return (
    <header className="app-chrome-surface fixed top-0 left-0 lg:left-[232px] right-0 h-14 border-b border-[#e5e7e4] z-40 flex items-center justify-between px-6">
      {/* Breadcrumb section */}
      <div className="flex items-center gap-2 text-[13px] overflow-hidden">
        {breadcrumbs}
      </div>

      {/* Right actions */}
      <div className="flex items-center gap-3 shrink-0">
        {rightActions}
        <ThemeToggle className="hidden lg:inline-flex" />

      </div>
    </header>
  );
};
