import React, { useEffect, useRef, useState } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import {
  ChevronsUpDown,
  FileText,
  Folder,
  LayoutGrid,
  LibraryBig,
  LogOut,
  Moon,
  Plus,
  Sun,
} from 'lucide-react';
import { researchService } from '../../services/research.service';
import { projectsService } from '../../services/projects.service';
import { ResearchResponse } from '../../types/research';
import { ResearchProject } from '../../types/project';
import { useAuth } from '../../app/AuthContext';
import { useProject } from '../../app/ProjectContext';
import { BrandMark } from '../common/BrandMark';
import { applyTheme, getAppliedTheme } from '../../theme';

interface AppSidebarProps {
  className?: string;
  onNavigate?: () => void;
}

const STATUS_DOT: Record<string, string> = {
  completed: 'bg-accent',
  researching: 'bg-warning',
  failed: 'bg-danger',
  draft: 'bg-ink-muted',
};

const researchPath = (item: ResearchResponse) =>
  item.status === 'completed' ? `/research/${item.id}` : `/research/${item.id}/progress`;

const initials = (name?: string) =>
  (name || 'R')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('');

export const AppSidebar: React.FC<AppSidebarProps> = ({ className = '', onNavigate }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { selectedProject } = useProject();
  const [recentItems, setRecentItems] = useState<ResearchResponse[]>([]);
  const [recentProjects, setRecentProjects] = useState<ResearchProject[]>([]);
  const [profileOpen, setProfileOpen] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const profileRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    researchService
      .listResearch({ limit: 4, offset: 0 })
      .then((res) => setRecentItems(res.items))
      .catch(() => {
        // The sidebar lists are supplemental, so a failed load stays silent.
      });
  }, [location.pathname]);

  useEffect(() => {
    projectsService
      .listProjects({ limit: 5 })
      .then((res) => setRecentProjects(res.items.filter((p) => !p.archivedAt)))
      .catch(() => {
        // The sidebar lists are supplemental, so a failed load stays silent.
      });
  }, [location.pathname]);

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
      active
        ? 'bg-subtle font-medium text-ink'
        : 'text-ink-soft hover:bg-subtle hover:text-ink'
    }`;

  const iconClass = (active: boolean) =>
    `h-4 w-4 shrink-0 ${active ? 'text-accent' : 'text-ink-muted group-hover:text-ink-soft'}`;

  const inRecentProject = recentProjects.some((p) => location.pathname === `/projects/${p.id}`);
  const projectsActive =
    location.pathname === '/projects' ||
    (location.pathname.startsWith('/projects/') && !inRecentProject);
  const researchActive = location.pathname === '/research';
  const documentsActive = location.pathname.startsWith('/documents');
  const isDark = getAppliedTheme() === 'dark';

  return (
    <aside
      className={`fixed left-0 top-0 z-50 flex h-full w-[248px] select-none flex-col border-r border-line bg-panel ${className}`}
    >
      <div className="flex h-14 shrink-0 items-center px-4">
        <Link to="/projects" onClick={onNavigate} className="rounded-md" aria-label="Research Assistant home">
          <BrandMark nameClassName="text-[14px]" />
        </Link>
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-3 pb-3">
        <Link
          to="/research/new"
          onClick={onNavigate}
          className="mt-1 flex h-9 items-center gap-2 rounded-md border border-line-strong bg-panel px-2.5 text-[13px] font-medium text-ink shadow-xs transition-colors hover:bg-subtle"
        >
          <Plus className="h-4 w-4" />
          New research
        </Link>

        <nav aria-label="Main navigation" className="mt-5 flex flex-col gap-px">
          <NavLink to="/projects" onClick={onNavigate} className={() => navItem(projectsActive)}>
            <LayoutGrid className={iconClass(projectsActive)} />
            <span>Projects</span>
          </NavLink>
          <NavLink to="/research" end onClick={onNavigate} className={() => navItem(researchActive)}>
            <LibraryBig className={iconClass(researchActive)} />
            <span>My research</span>
          </NavLink>
          <NavLink to="/documents" onClick={onNavigate} className={() => navItem(documentsActive)}>
            <FileText className={iconClass(documentsActive)} />
            <span>Documents</span>
          </NavLink>
        </nav>

        {recentProjects.length > 0 && (
          <section className="mt-6">
            <h2 className="eyebrow mb-1.5 px-2.5">Projects</h2>
            <nav aria-label="Recent projects" className="flex flex-col gap-px">
              {recentProjects.map((project) => {
                const active =
                  location.pathname === `/projects/${project.id}` ||
                  (location.pathname.startsWith('/projects/') && selectedProject?.id === project.id);
                return (
                  <NavLink
                    key={project.id}
                    to={`/projects/${project.id}`}
                    onClick={onNavigate}
                    title={project.name}
                    className={() => navItem(active)}
                  >
                    <Folder className={iconClass(active)} />
                    <span className="truncate">{project.name}</span>
                  </NavLink>
                );
              })}
            </nav>
          </section>
        )}

        {recentItems.length > 0 && (
          <section className="mt-6">
            <h2 className="eyebrow mb-1.5 px-2.5">Recent research</h2>
            <nav aria-label="Recent research" className="flex flex-col gap-px">
              {recentItems.map((item) => {
                const target = researchPath(item);
                const active = location.pathname === target;
                return (
                  <NavLink
                    key={item.id}
                    to={target}
                    onClick={onNavigate}
                    title={item.title}
                    className={() => navItem(active)}
                  >
                    <span className="flex h-4 w-4 shrink-0 items-center justify-center" aria-hidden="true">
                      <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[item.status] ?? 'bg-ink-muted'}`} />
                    </span>
                    <span className="truncate">{item.title}</span>
                    <span className="sr-only">({item.status})</span>
                  </NavLink>
                );
              })}
            </nav>
          </section>
        )}
      </div>

      <div ref={profileRef} className="relative shrink-0 border-t border-line p-2">
        {profileOpen && (
          <div
            role="menu"
            className="absolute bottom-full left-2 right-2 mb-1 overflow-hidden rounded-lg border border-line bg-panel py-1 shadow-lg"
          >
            <div className="border-b border-line px-3 py-2">
              <p className="truncate text-[13px] font-medium text-ink">{user?.name || 'Researcher'}</p>
              <p className="truncate text-xs text-ink-muted">{user?.email}</p>
            </div>
            <button
              type="button"
              role="menuitem"
              onClick={() => applyTheme(isDark ? 'light' : 'dark', true)}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-[13px] text-ink-soft hover:bg-subtle hover:text-ink"
            >
              {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              {isDark ? 'Light theme' : 'Dark theme'}
            </button>
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

        <button
          type="button"
          onClick={() => setProfileOpen((open) => !open)}
          aria-haspopup="menu"
          aria-expanded={profileOpen}
          className="flex w-full items-center gap-2.5 rounded-md p-1.5 text-left transition-colors hover:bg-subtle"
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
      </div>
    </aside>
  );
};
