import React from 'react';
import { Search } from 'lucide-react';
import { ThemeToggle } from './ThemeToggle';

interface TopBarProps {
  breadcrumbs?: React.ReactNode;
  rightActions?: React.ReactNode;
  showGlobalSearch?: boolean;
}

export const TopBar: React.FC<TopBarProps> = ({
  breadcrumbs,
  rightActions,
  showGlobalSearch = true,
}) => {
  return (
    <header className="app-chrome-surface fixed top-0 left-0 lg:left-[232px] right-0 h-14 border-b border-[#e5e7e4] z-40 flex items-center justify-between px-6">
      {/* Breadcrumb section */}
      <div className="flex items-center gap-2 text-[13px] overflow-hidden">
        {breadcrumbs}
      </div>

      {/* Right actions / Search trigger */}
      <div className="flex items-center gap-3 shrink-0">
        {rightActions}
        <ThemeToggle className="hidden lg:inline-flex" />

        {showGlobalSearch && (
          <button
            type="button"
            className="bg-[#fafaf8] border border-[#e5e7e4] rounded-md px-3 py-1.5 text-xs text-[#6b706c] flex items-center gap-3 hover:border-[#d0d7d2] focus:outline-none focus:ring-1 focus:ring-[#163328] transition-all duration-150 group"
          >
            <div className="flex items-center gap-1.5">
              <Search className="w-4 h-4 text-[#929792] group-hover:text-[#6b706c] transition-colors" />
              <span className="hidden sm:inline">Search research, documents, sources…</span>
              <span className="sm:hidden">Search…</span>
            </div>
            <kbd className="font-sans text-[10px] bg-white border border-[#e5e7e4] text-[#929792] px-1.5 py-0.5 rounded shadow-xs">
              ⌘K
            </kbd>
          </button>
        )}
      </div>
    </header>
  );
};
