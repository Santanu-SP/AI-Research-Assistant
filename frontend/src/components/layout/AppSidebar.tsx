import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import {
  ChevronsUpDown,
  FileText,
  LayoutGrid,
  LogOut,
  Moon,
  PanelLeftClose,
  Plus,
  Search,
  Settings,
  Sun,
  X,
} from 'lucide-react';
import { useAuth } from '../../app/AuthContext';
import { groupByDate, useResearchHistory } from '../../app/ResearchHistoryContext';
import { researchService } from '../../services/research.service';
import { ResearchResponse } from '../../types/research';
import { BrandMark } from '../common/BrandMark';
import { applyTheme, getAppliedTheme } from '../../theme';
import { shortcutLabel } from '../../lib/shortcuts';
import { useMobileNav } from './MobileNavContext';
import { ResearchHistoryItem } from './ResearchHistoryItem';
import { DeleteResearchDialog } from './DeleteResearchDialog';

interface AppSidebarProps {
  variant?: 'desktop' | 'drawer';
  className?: string;
  onNavigate?: () => void;
  /** Changes whenever the research search should take focus (Cmd/Ctrl+K). */
  searchFocusSignal?: number;
}

export const researchPath = (item: ResearchResponse) =>
  item.status === 'completed' ? `/research/${item.id}` : `/research/${item.id}/progress`;

const initials = (name?: string) =>
  (name || 'R')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('');

const Kbd: React.FC<React.PropsWithChildren<{ className?: string }>> = ({ children, className = '' }) => (
  <kbd
    className={`hidden h-5 items-center rounded border border-line bg-subtle px-1.5 font-sans text-[10.5px] font-medium text-ink-muted sm:inline-flex ${className}`}
  >
    {children}
  </kbd>
);

export const AppSidebar: React.FC<AppSidebarProps> = ({
  variant = 'desktop',
  className = '',
  onNavigate,
  searchFocusSignal = 0,
}) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const history = useResearchHistory();
  const nav = useMobileNav();
  const [query, setQuery] = useState('');
  const [remoteMatches, setRemoteMatches] = useState<ResearchResponse[] | null>(null);
  const [pendingDelete, setPendingDelete] = useState<ResearchResponse | null>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const profileRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const items = useMemo(() => history?.items ?? [], [history?.items]);
  const trimmed = query.trim().toLowerCase();

  // Everything loaded is filtered in place. If the history is larger than what
  // was loaded, the server's own search fills in the rest.
  useEffect(() => {
    if (!trimmed || history?.complete !== false) {
      setRemoteMatches(null);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      researchService
        .listResearch({ search: trimmed, limit: 50 })
        .then((res) => {
          if (!cancelled) setRemoteMatches(res.items);
        })
        .catch(() => {
          if (!cancelled) setRemoteMatches(null);
        });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [trimmed, history?.complete]);

  const visible = useMemo(() => {
    if (!trimmed) return items;
    const local = items.filter(
      (item) => item.title.toLowerCase().includes(trimmed) || item.question.toLowerCase().includes(trimmed),
    );
    if (!remoteMatches) return local;
    const seen = new Set(local.map((item) => item.id));
    return [...local, ...remoteMatches.filter((item) => !seen.has(item.id))];
  }, [items, trimmed, remoteMatches]);

  const groups = useMemo(() => groupByDate(visible), [visible]);

  useEffect(() => {
    if (!searchFocusSignal) return;
    const input = searchRef.current;
    // Only the sidebar that is actually on screen takes focus.
    if (!input || input.offsetParent === null) return;
    window.requestAnimationFrame(() => {
      input.focus();
      input.select();
    });
  }, [searchFocusSignal]);

  useEffect(() => {
    if (!profileOpen) return;
    const close = (event: MouseEvent) => {
      if (!profileRef.current?.contains(event.target as Node)) setProfileOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setProfileOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', onKey);
    };
  }, [profileOpen]);

  const navItem = (active: boolean) =>
    `group flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13px] transition-colors ${
      active ? 'bg-subtle font-medium text-ink' : 'text-ink-soft hover:bg-subtle hover:text-ink'
    }`;

  const iconClass = (active: boolean) =>
    `h-4 w-4 shrink-0 ${active ? 'text-accent' : 'text-ink-muted group-hover:text-ink-soft'}`;

  const projectsActive = location.pathname.startsWith('/projects');
  const documentsActive = location.pathname.startsWith('/documents');
  const settingsActive = location.pathname.startsWith('/settings');
  const isDark = getAppliedTheme() === 'dark';

  const handleDeleted = (item: ResearchResponse) => {
    setPendingDelete(null);
    if (location.pathname.startsWith(`/research/${item.id}`)) navigate('/research/new', { replace: true });
  };

  return (
    <aside
      className={`flex h-full w-full select-none flex-col border-r border-line bg-panel ${className}`}
      aria-label="Sidebar"
    >
      <div className="flex h-14 shrink-0 items-center justify-between gap-2 pl-4 pr-2">
        <Link to="/research/new" onClick={onNavigate} className="rounded-md" aria-label="Research Assistant home">
          <BrandMark nameClassName="text-[14px]" />
        </Link>
        {variant === 'desktop' && nav?.toggleCollapsed && (
          <button
            type="button"
            onClick={nav.toggleCollapsed}
            title={`Hide sidebar (${shortcutLabel('S', { shift: true })})`}
            aria-label="Hide sidebar"
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-subtle hover:text-ink"
          >
            <PanelLeftClose className="h-[18px] w-[18px]" />
          </button>
        )}
        {variant === 'drawer' && (
          <button
            type="button"
            onClick={onNavigate}
            aria-label="Close navigation"
            className="inline-flex h-9 w-9 items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-subtle hover:text-ink"
          >
            <X className="h-[18px] w-[18px]" />
          </button>
        )}
      </div>

      <div className="shrink-0 px-3">
        <Link
          to="/research/new"
          onClick={onNavigate}
          className="flex h-9 items-center gap-2 rounded-md bg-solid px-2.5 text-[13px] font-medium text-on-solid shadow-xs transition-colors hover:bg-solid-hover"
        >
          <Plus className="h-4 w-4" />
          <span className="flex-1">New research</span>
          <kbd className="hidden font-sans text-[10.5px] font-medium tracking-wide text-on-solid/60 sm:inline">
            {shortcutLabel('O', { shift: true })}
          </kbd>
        </Link>

        <nav aria-label="Main navigation" className="mt-3 flex flex-col gap-px">
          <NavLink to="/projects" onClick={onNavigate} className={() => navItem(projectsActive)}>
            <LayoutGrid className={iconClass(projectsActive)} />
            <span>Projects</span>
          </NavLink>
          <NavLink to="/documents" onClick={onNavigate} className={() => navItem(documentsActive)}>
            <FileText className={iconClass(documentsActive)} />
            <span>Documents</span>
          </NavLink>
        </nav>

        <div className="mt-4 border-t border-line pt-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-muted" />
            <input
              ref={searchRef}
              type="search"
              aria-label="Search research"
              aria-keyshortcuts="Control+K Meta+K"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Escape' && query) {
                  event.stopPropagation();
                  setQuery('');
                }
              }}
              placeholder="Search research"
              className="h-8 w-full rounded-md border border-line bg-canvas pl-8 pr-14 text-[13px] text-ink placeholder:text-ink-muted transition-colors focus:border-accent-line focus:bg-panel focus:outline-none [&::-webkit-search-cancel-button]:hidden"
            />
            {!query && (
              <Kbd className="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2">{shortcutLabel('K')}</Kbd>
            )}
          </div>
        </div>
      </div>

      <div className="sidebar-scroll mt-2 min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 pb-3" aria-label="Research history">
        {!history || (history.loading && items.length === 0) ? (
          <div className="space-y-1.5 px-1 pt-3" aria-hidden="true">
            {[72, 88, 64, 80, 56].map((width) => (
              <div key={width} className="flex h-8 items-center px-1.5">
                <span className="h-2.5 animate-pulse rounded bg-subtle" style={{ width: `${width}%` }} />
              </div>
            ))}
          </div>
        ) : history.error && items.length === 0 ? (
          <div className="px-2.5 py-4 text-[13px] text-ink-soft">
            Couldn’t load your research.{' '}
            <button type="button" onClick={history.reload} className="font-medium text-accent hover:underline">
              Try again
            </button>
          </div>
        ) : items.length === 0 ? (
          <div className="px-2.5 py-4">
            <p className="text-[13px] font-medium text-ink">No research yet</p>
            <p className="mt-1 text-xs leading-relaxed text-ink-muted">
              Questions you ask will show up here so you can come back to them.
            </p>
          </div>
        ) : groups.length === 0 ? (
          <div className="px-2.5 py-4">
            <p className="text-[13px] text-ink-soft">
              No research matches <span className="font-medium text-ink">“{query.trim()}”</span>
            </p>
            <button type="button" onClick={() => setQuery('')} className="mt-1 text-xs font-medium text-accent hover:underline">
              Clear search
            </button>
          </div>
        ) : (
          groups.map((group) => (
            <section key={group.label} className="pt-3">
              <h2 className="sticky top-0 z-[1] bg-panel px-2.5 pb-1 text-[11px] font-medium text-ink-muted">
                {group.label}
              </h2>
              <ul className="flex flex-col gap-px">
                {group.items.map((item) => (
                  <ResearchHistoryItem
                    key={item.id}
                    item={item}
                    to={researchPath(item)}
                    active={location.pathname.startsWith(`/research/${item.id}`)}
                    highlight={trimmed}
                    onNavigate={onNavigate}
                    onRename={(title) => history.rename(item.id, title)}
                    onDelete={() => setPendingDelete(item)}
                  />
                ))}
              </ul>
            </section>
          ))
        )}
      </div>

      <div ref={profileRef} className="relative shrink-0 border-t border-line p-2">
        {profileOpen && (
          <div
            role="menu"
            className="menu-enter absolute bottom-full left-2 right-2 mb-1 overflow-hidden rounded-lg border border-line bg-panel py-1 shadow-lg"
          >
            <div className="border-b border-line px-3 py-2">
              <p className="truncate text-[13px] font-medium text-ink">{user?.name || 'Researcher'}</p>
              <p className="truncate text-xs text-ink-muted">{user?.email}</p>
            </div>
            <Link
              to="/settings"
              role="menuitem"
              onClick={() => {
                setProfileOpen(false);
                onNavigate?.();
              }}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13px] text-ink-soft hover:bg-subtle hover:text-ink"
            >
              <Settings className="h-4 w-4" /> Settings
            </Link>
            <button
              type="button"
              role="menuitem"
              onClick={() => applyTheme(isDark ? 'light' : 'dark', true)}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13px] text-ink-soft hover:bg-subtle hover:text-ink"
            >
              {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              {isDark ? 'Light theme' : 'Dark theme'}
            </button>
            <div className="my-1 border-t border-line" />
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setLogoutError(null);
                void logout()
                  .then(() => navigate('/login', { replace: true }))
                  .catch(() => {
                    setLogoutError('Could not reach the server. Please try again.');
                  });
              }}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13px] text-ink-soft hover:bg-subtle hover:text-ink"
            >
              <LogOut className="h-4 w-4" /> Sign out
            </button>
            {logoutError && (
              <p role="alert" className="px-3 pb-2 text-xs text-danger">
                {logoutError}
              </p>
            )}
          </div>
        )}

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setProfileOpen((open) => !open)}
            aria-haspopup="menu"
            aria-expanded={profileOpen}
            className="flex min-w-0 flex-1 items-center gap-2.5 rounded-md p-1.5 text-left transition-colors hover:bg-subtle"
          >
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-muted text-[11px] font-semibold text-accent">
              {initials(user?.name)}
            </span>
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="truncate text-[13px] font-medium leading-tight text-ink">
                {user?.name || 'Researcher'}
              </span>
              <span className="truncate text-xs leading-tight text-ink-muted">{user?.email}</span>
            </span>
            <ChevronsUpDown className="h-4 w-4 shrink-0 text-ink-muted" />
          </button>
          <Link
            to="/settings"
            onClick={onNavigate}
            aria-label="Settings"
            title="Settings"
            className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md transition-colors ${
              settingsActive ? 'bg-subtle text-accent' : 'text-ink-muted hover:bg-subtle hover:text-ink'
            }`}
          >
            <Settings className="h-4 w-4" />
          </Link>
        </div>
      </div>

      {pendingDelete && history && (
        <DeleteResearchDialog
          item={pendingDelete}
          onCancel={() => setPendingDelete(null)}
          onConfirm={async () => {
            await history.remove(pendingDelete.id);
            handleDeleted(pendingDelete);
          }}
        />
      )}
    </aside>
  );
};
