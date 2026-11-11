import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
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
import { ResearchProject } from '../types/project';
import {
  getProjectErrorMessage,
  projectsService,
} from '../services/projects.service';
import { useProject } from '../app/ProjectContext';

export const ProjectsPage: React.FC = () => {
  const navigate = useNavigate();
  const { selectProject } = useProject();

  const [projects, setProjects] = useState<ResearchProject[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [showArchived, setShowArchived] = useState(false);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await projectsService.listProjects({
        search: searchQuery.trim() || undefined,
        includeArchived: showArchived,
        limit: 100,
      });
      setProjects(res.items);
      setTotal(res.total);
    } catch (err) {
      setProjects([]);
      setTotal(0);
      setError(getProjectErrorMessage(err, 'Failed to load projects.'));
    } finally {
      setIsLoading(false);
    }
  }, [searchQuery, showArchived, retryKey]); // eslint-disable-line react-hooks/exhaustive-deps

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
    if (!showArchived) {
      setProjects((prev) => prev.filter((p) => p.id !== id));
    } else {
      setRetryKey((k) => k + 1);
    }
  };

  const hasFilters = Boolean(searchQuery);
  const activeProjects = projects.filter((p) => !p.archivedAt);
  const archivedProjects = projects.filter((p) => p.archivedAt);

  const projectList = (items: ResearchProject[]) => (
    <div className="overflow-hidden rounded-lg border border-line bg-panel shadow-xs">
      <div className="hidden grid-cols-[minmax(0,1fr)_110px_110px_40px] gap-4 border-b border-line bg-subtle/50 px-5 py-2 text-xs font-medium text-ink-muted sm:grid">
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
            description="Each project keeps its own documents and research, and questions only search the papers inside it."
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

            <div className="flex items-center justify-between gap-4 sm:justify-end">
              {!isLoading && !error && total > 0 && (
                <span className="text-xs tabular-nums text-ink-muted">
                  {total} project{total !== 1 ? 's' : ''}
                </span>
              )}
              <label className="flex cursor-pointer select-none items-center gap-2 text-[13px] text-ink-soft">
                <input
                  type="checkbox"
                  checked={showArchived}
                  onChange={(e) => setShowArchived(e.target.checked)}
                  className="h-4 w-4 rounded border-line-strong accent-[var(--app-solid)]"
                />
                <span className="flex items-center gap-1.5">
                  <Archive className="h-3.5 w-3.5" />
                  Show archived
                </span>
              </label>
            </div>
          </div>

          {isLoading ? (
            <LoadingState rows={4} />
          ) : error ? (
            <ErrorState
              title="Could not load projects"
              message={error}
              onRetry={() => setRetryKey((k) => k + 1)}
            />
          ) : projects.length === 0 && hasFilters ? (
            <EmptyState
              icon={FolderX}
              title="No projects match your search"
              description="Try a different search term or clear the filter."
              primaryActionLabel="Clear search"
              onPrimaryAction={() => setSearchQuery('')}
            />
          ) : projects.length === 0 ? (
            <EmptyState
              icon={FolderOpen}
              title="No projects yet"
              description="Create a project, upload a few papers to it, and ask questions that only search those papers."
              primaryActionLabel="Create your first project"
              onPrimaryAction={() => setIsCreateOpen(true)}
            />
          ) : (
            <div className="space-y-8">
              {activeProjects.length > 0 && (
                <section>
                  {showArchived && (
                    <h2 className="eyebrow mb-2">Active · {activeProjects.length}</h2>
                  )}
                  {projectList(activeProjects)}
                </section>
              )}

              {showArchived && archivedProjects.length > 0 && (
                <section>
                  <h2 className="eyebrow mb-2">Archived · {archivedProjects.length}</h2>
                  {projectList(archivedProjects)}
                </section>
              )}
            </div>
          )}
        </div>
      </main>

      <CreateProjectDialog
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onCreated={handleCreated}
      />
    </div>
  );
};
