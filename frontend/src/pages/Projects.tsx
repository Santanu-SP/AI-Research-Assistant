import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  FolderOpen,
  Plus,
  Search,
  Archive,
  FolderX,
} from 'lucide-react';
import { TopBar } from '../components/layout/TopBar';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';
import { LoadingState } from '../components/common/LoadingState';
import { PrimaryButton } from '../components/common/PrimaryButton';
import { PageHeader } from '../components/common/PageHeader';
import { ProjectCard } from '../components/projects/ProjectCard';
import { CreateProjectDialog } from '../components/projects/CreateProjectDialog';
import { ArchivedProjectRow } from '../components/projects/ArchivedProjectRow';
import { DeleteProjectDialog } from '../components/projects/DeleteProjectDialog';
import { ResearchProject } from '../types/project';
import {
  getProjectErrorMessage,
  projectsService,
} from '../services/projects.service';
import { useProject } from '../app/ProjectContext';

type ProjectsView = 'active' | 'archived';

const VIEWS: { id: ProjectsView; label: string; icon: React.ElementType }[] = [
  { id: 'active', label: 'Active', icon: FolderOpen },
  { id: 'archived', label: 'Archived', icon: Archive },
];

export const ProjectsPage: React.FC = () => {
  const navigate = useNavigate();
  const { selectProject } = useProject();

  const [projects, setProjects] = useState<ResearchProject[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchParams, setSearchParams] = useSearchParams();
  const view: ProjectsView = searchParams.get('view') === 'archived' ? 'archived' : 'active';
  const [pendingDelete, setPendingDelete] = useState<ResearchProject | null>(null);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await projectsService.listProjects({
        search: searchQuery.trim() || undefined,
        // Active and archived projects come in one list so both tabs can show a count.
        includeArchived: true,
        limit: 100,
      });
      setProjects(res.items);
    } catch (err) {
      setProjects([]);
      setError(getProjectErrorMessage(err, 'Failed to load projects.'));
    } finally {
      setIsLoading(false);
    }
  }, [searchQuery, retryKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // Debounced search
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), searchQuery ? 300 : 0);
    return () => window.clearTimeout(timer);
  }, [load, searchQuery]);

  const handleOpenProject = (project: ResearchProject) => {
    selectProject(project.id);
    navigate(`/projects/${project.id}`);
  };

  const handleCreated = (project: ResearchProject) => {
    setIsCreateOpen(false);
    selectProject(project.id);
    navigate(`/projects/${project.id}`);
  };

  const handleProjectUpdated = (updated: ResearchProject) => {
    setProjects((prev) =>
      prev.map((p) => (p.id === updated.id ? updated : p))
    );
  };

  const handleProjectArchived = (id: string) => {
    const archivedAt = new Date().toISOString();
    setProjects((prev) => prev.map((p) => (p.id === id ? { ...p, archivedAt, updatedAt: archivedAt } : p)));
  };

  const handleProjectRestored = (restored: ResearchProject) => {
    setProjects((prev) => prev.map((p) => (p.id === restored.id ? restored : p)));
  };

  const handleProjectDeleted = (id: string) => {
    setPendingDelete(null);
    setProjects((prev) => prev.filter((p) => p.id !== id));
  };

  const setView = (next: ProjectsView) => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next === 'archived') params.set('view', 'archived');
        else params.delete('view');
        return params;
      },
      { replace: true },
    );
  };

  const hasFilters = Boolean(searchQuery);
  const activeProjects = useMemo(() => projects.filter((p) => !p.archivedAt), [projects]);
  const archivedProjects = useMemo(
    () =>
      projects
        .filter((p) => p.archivedAt)
        .sort((a, b) => (b.archivedAt ?? '').localeCompare(a.archivedAt ?? '')),
    [projects],
  );
  const visible = view === 'archived' ? archivedProjects : activeProjects;

  const projectList = (items: ResearchProject[]) => (
    <div className="rounded-lg border border-line bg-panel shadow-xs">
      <div className="hidden grid-cols-[minmax(0,1fr)_110px_110px_40px] gap-4 rounded-t-lg border-b border-line bg-subtle/50 px-5 py-2 text-xs font-medium text-ink-muted sm:grid">
        <span>Name</span>
        <span>Updated</span>
        <span>Created</span>
        <span className="sr-only">Actions</span>
      </div>
      <div className="divide-y divide-line">
        {items.map((project) => (
          <ProjectCard
            key={project.id}
            project={project}
            onOpen={handleOpenProject}
            onUpdated={handleProjectUpdated}
            onArchived={handleProjectArchived}
          />
        ))}
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen flex-col">
      <TopBar
        breadcrumbs={<span className="font-medium text-ink">Projects</span>}
      />

      <main className="flex-1 px-4 pb-16 pt-14 sm:px-6 lg:px-10">
        <div className="mx-auto max-w-5xl py-8 sm:py-10">
          <PageHeader
            title="Projects"
            description="Each project keeps its own files and research, and questions only search the files inside it."
            actions={
              <PrimaryButton onClick={() => setIsCreateOpen(true)} id="create-project-btn">
                <Plus className="h-4 w-4" />
                New project
              </PrimaryButton>
            }
          />

          <div className="mb-4 mt-8 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative w-full sm:max-w-xs">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" />
              <input
                type="search"
                aria-label="Search projects"
                id="projects-search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search projects"
                className="field h-9 pl-9 text-[13px]"
              />
            </div>

            <div role="tablist" aria-label="Project lists" className="inline-flex rounded-lg border border-line bg-subtle p-0.5">
              {VIEWS.map(({ id, label, icon: Icon }) => {
                const selected = view === id;
                const count = id === 'archived' ? archivedProjects.length : activeProjects.length;
                return (
                  <button
                    key={id}
                    type="button"
                    role="tab"
                    id={`projects-tab-${id}`}
                    aria-selected={selected}
                    aria-controls="projects-panel"
                    onClick={() => setView(id)}
                    className={`inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-[13px] transition-colors ${
                      selected ? 'bg-panel font-medium text-ink shadow-xs' : 'text-ink-soft hover:text-ink'
                    }`}
                  >
                    <Icon className={`h-3.5 w-3.5 ${selected ? 'text-accent' : 'text-ink-muted'}`} />
                    {label}
                    {!isLoading && !error && (
                      <span className="tabular-nums text-xs text-ink-muted">{count}</span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          <div id="projects-panel" role="tabpanel" aria-labelledby={`projects-tab-${view}`}>
          {isLoading ? (
            <LoadingState rows={4} />
          ) : error ? (
            <ErrorState
              title="Could not load projects"
              message={error}
              onRetry={() => setRetryKey((k) => k + 1)}
            />
          ) : visible.length === 0 && hasFilters ? (
            <EmptyState
              icon={FolderX}
              title={view === 'archived' ? 'No archived projects match your search' : 'No projects match your search'}
              description="Try a different search term or clear the filter."
              primaryActionLabel="Clear search"
              onPrimaryAction={() => setSearchQuery('')}
            />
          ) : view === 'archived' && visible.length === 0 ? (
            <EmptyState
              icon={Archive}
              title="No archived projects"
              description="When you archive a project it moves here. You can restore it any time, or delete it for good."
              secondaryActionLabel="Back to projects"
              onSecondaryAction={() => setView('active')}
            />
          ) : visible.length === 0 ? (
            <EmptyState
              icon={FolderOpen}
              title="No projects yet"
              description="Create a project, upload a few files to it, and ask questions that only search those files."
              primaryActionLabel="Create your first project"
              onPrimaryAction={() => setIsCreateOpen(true)}
            />
          ) : view === 'archived' ? (
            <section aria-labelledby="archived-heading">
              <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                <h2 id="archived-heading" className="text-sm font-semibold text-ink">
                  Archived projects <span className="font-normal tabular-nums text-ink-muted">· {archivedProjects.length}</span>
                </h2>
                <p className="text-xs text-ink-muted">Archived projects are read-only. Restore one to keep working in it.</p>
              </div>
              <div className="rounded-lg border border-line bg-panel shadow-xs">
                <div className="hidden grid-cols-[minmax(0,1fr)_130px_auto] gap-4 rounded-t-lg border-b border-line bg-subtle/50 px-5 py-2 text-xs font-medium text-ink-muted sm:grid">
                  <span>Name</span>
                  <span>Archived</span>
                  <span className="sr-only">Actions</span>
                </div>
                <ul className="divide-y divide-line" aria-label="Archived projects">
                  {archivedProjects.map((project) => (
                    <ArchivedProjectRow
                      key={project.id}
                      project={project}
                      onRestored={handleProjectRestored}
                      onDeleteRequest={setPendingDelete}
                    />
                  ))}
                </ul>
              </div>
            </section>
          ) : (
            projectList(activeProjects)
          )}
          </div>
        </div>
      </main>

      {pendingDelete && (
        <DeleteProjectDialog
          project={pendingDelete}
          onCancel={() => setPendingDelete(null)}
          onDeleted={handleProjectDeleted}
        />
      )}

      <CreateProjectDialog
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onCreated={handleCreated}
      />
    </div>
  );
};
