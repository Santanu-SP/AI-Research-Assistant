import React, { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { LayoutGrid, LogOut, Moon, PanelLeftOpen, Plus, Search, Settings, Sun } from 'lucide-react';
import { useAuth } from '../../app/AuthContext';
import { BrandMark } from '../common/BrandMark';
import { applyTheme, getAppliedTheme } from '../../theme';
import { shortcutLabel } from '../../lib/shortcuts';

interface SidebarRailProps {
  onExpand: () => void;
  /** Opens the full sidebar with the search box focused. */
  onSearch: () => void;
}

const initials = (name?: string) =>
  (name || 'R')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('');

const railButton = (active = false) =>
  `rail-tip inline-flex h-9 w-9 items-center justify-center rounded-md transition-colors ${
    active ? 'bg-subtle text-accent' : 'text-ink-muted hover:bg-subtle hover:text-ink'
  }`;

/** The slim column of icons shown on desktop while the sidebar is hidden. */
export const SidebarRail: React.FC<SidebarRailProps> = ({ onExpand, onSearch }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const isDark = getAppliedTheme() === 'dark';

  const projectsActive = location.pathname.startsWith('/projects');
  const settingsActive = location.pathname.startsWith('/settings');
  const newActive = location.pathname === '/research/new';

  useEffect(() => {
    if (!menuOpen) return;
    const onPointer = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMenuOpen(false);
    };
    document.addEventListener('pointerdown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [menuOpen]);

  useEffect(() => setMenuOpen(false), [location.pathname]);

  return (
    <aside
      className="flex h-full w-full select-none flex-col items-center border-r border-line bg-panel py-2.5"
      aria-label="Sidebar"
    >
      <Link
        to="/research/new"
        aria-label="Research Assistant home"
        data-tip="Research Assistant"
        className="rail-tip mb-1 inline-flex h-9 w-9 items-center justify-center rounded-md"
      >
        <BrandMark withName={false} />
      </Link>

      <button
        type="button"
        onClick={onExpand}
        aria-label="Show sidebar"
        data-tip={`Show sidebar  ${shortcutLabel('S', { shift: true })}`}
        className={railButton()}
      >
        <PanelLeftOpen className="h-[18px] w-[18px]" />
      </button>

      <nav aria-label="Main navigation" className="mt-3 flex flex-col items-center gap-1 border-t border-line pt-3">
        <Link
          to="/research/new"
          aria-label="New research"
          data-tip={`New research  ${shortcutLabel('O', { shift: true })}`}
          aria-current={newActive ? 'page' : undefined}
          className="rail-tip inline-flex h-9 w-9 items-center justify-center rounded-md bg-solid text-on-solid shadow-xs transition-colors hover:bg-solid-hover"
        >
          <Plus className="h-4 w-4" />
        </Link>
        <button
          type="button"
          onClick={onSearch}
          aria-label="Search research"
          data-tip={`Search  ${shortcutLabel('K')}`}
          className={railButton()}
        >
          <Search className="h-4 w-4" />
        </button>
        <Link
          to="/projects"
          aria-label="Projects"
          data-tip="Projects"
          aria-current={projectsActive ? 'page' : undefined}
          className={railButton(projectsActive)}
        >
          <LayoutGrid className="h-4 w-4" />
        </Link>
        <Link
          to="/settings"
          aria-label="Settings"
          data-tip="Settings"
          aria-current={settingsActive ? 'page' : undefined}
          className={railButton(settingsActive)}
        >
          <Settings className="h-4 w-4" />
        </Link>
      </nav>

      <div ref={menuRef} className="relative mt-auto">
        {menuOpen && (
          <div
            role="menu"
            className="menu-enter absolute bottom-0 left-full z-50 ml-2 w-56 overflow-hidden rounded-lg border border-line bg-panel py-1 shadow-lg"
          >
            <div className="border-b border-line px-3 py-2">
              <p className="truncate text-[13px] font-medium text-ink">{user?.name || 'Researcher'}</p>
              <p className="truncate text-xs text-ink-muted">{user?.email}</p>
            </div>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                applyTheme(isDark ? 'light' : 'dark', true);
                setMenuOpen(false);
              }}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13px] text-ink-soft hover:bg-subtle hover:text-ink"
            >
              {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              {isDark ? 'Light theme' : 'Dark theme'}
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                void logout()
                  .then(() => navigate('/login', { replace: true }))
                  .catch(() => setMenuOpen(false));
              }}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13px] text-ink-soft hover:bg-subtle hover:text-ink"
            >
              <LogOut className="h-4 w-4" /> Sign out
            </button>
          </div>
        )}
        <button
          type="button"
          onClick={() => setMenuOpen((open) => !open)}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          aria-label={`Account: ${user?.name || 'Researcher'}`}
          data-tip={menuOpen ? undefined : user?.name || 'Account'}
          className="rail-tip inline-flex h-9 w-9 items-center justify-center rounded-full transition-colors hover:bg-subtle"
        >
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-muted text-[11px] font-semibold text-accent">
            {initials(user?.name)}
          </span>
        </button>
      </div>
    </aside>
  );
};
