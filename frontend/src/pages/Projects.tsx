/**
 * ProjectsPage: The main project library / list view.
 *
 * Shows all user projects. Users can:
 *  - Search/filter projects (search is wired to backend query param)
 *  - Toggle archived projects
 *  - Create a new project
 *  - Open a project workspace
 *  - See empty, loading, and error states
 */
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
  }, [load]);

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

  return (
    <div className="min-h-screen bg-[#fafaf8] flex flex-col">
      <TopBar
        breadcrumbs={
          <div className="flex items-center gap-2">
            <span className="text-[#181a18] font-medium">Projects</span>
          </div>
        }
        rightActions={
          <PrimaryButton
            onClick={() => setIsCreateOpen(true)}
            className="gap-1.5"
            id="create-project-btn"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New Project</span>
          </PrimaryButton>
        }
      />

      <main className="flex-1 pt-14 pb-16 px-4 sm:px-6">
        <div className="max-w-5xl mx-auto py-8">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
            <div>
              <h1 className="font-serif text-2xl sm:text-3xl text-[#181a18] font-normal tracking-tight">
                Research Projects
              </h1>
              <p className="text-xs sm:text-sm text-[#6b706c] mt-1">
                Organize your documents and research within isolated workspaces.
              </p>
            </div>
          </div>

          {/* Filter bar */}
          <div className="p-3 bg-white border border-[#e5e7e4] rounded-xl mb-6 flex flex-wrap items-center gap-3 shadow-xs">
            <div className="relative flex-1 min-w-[220px]">
              <Search className="w-4 h-4 text-[#929792] absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                aria-label="Search projects"
                id="projects-search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search projects by name…"
                className="w-full bg-[#fafaf8] border border-[#e5e7e4] rounded-md pl-9 pr-3 py-1.5 text-xs text-[#181a18] placeholder:text-[#929792] focus:outline-none focus:ring-1 focus:ring-[#163328] focus:border-[#163328] transition-colors"
              />
            </div>

            <label className="flex items-center gap-2 text-xs text-[#6b706c] cursor-pointer select-none">
              <input
                type="checkbox"
                checked={showArchived}
                onChange={(e) => setShowArchived(e.target.checked)}
                className="rounded border-[#d0d7d2] text-[#163328] focus:ring-[#163328]"
              />
              <span className="flex items-center gap-1.5">
                <Archive className="w-3.5 h-3.5" />
                Show archived
              </span>
            </label>
          </div>

          {/* Content */}
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
              description="Create a project to organize your documents and research in a dedicated workspace."
              primaryActionLabel="Create your first project"
              onPrimaryAction={() => setIsCreateOpen(true)}
            />
          ) : (
            <div className="space-y-8">
              {/* Active projects */}
              {activeProjects.length > 0 && (
                <section>
                  {showArchived && (
                    <h2 className="text-[11px] font-semibold uppercase tracking-wider text-[#929792] mb-3">
                      Active ({activeProjects.length})
                    </h2>
                  )}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {activeProjects.map((project) => (
                      <ProjectCard
                        key={project.id}
                        project={project}
                        onOpen={handleOpenProject}
                        onUpdated={handleProjectUpdated}
                        onArchived={handleProjectArchived}
                      />
                    ))}
                  </div>
                </section>
              )}

              {/* Archived projects */}
              {showArchived && archivedProjects.length > 0 && (
                <section>
                  <h2 className="text-[11px] font-semibold uppercase tracking-wider text-[#929792] mb-3">
                    Archived ({archivedProjects.length})
                  </h2>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {archivedProjects.map((project) => (
                      <ProjectCard
                        key={project.id}
                        project={project}
                        onOpen={handleOpenProject}
                        onUpdated={handleProjectUpdated}
                        onArchived={handleProjectArchived}
                      />
                    ))}
                  </div>
                </section>
              )}
            </div>
          )}

          {!isLoading && !error && total > 0 && (
            <div className="mt-4 text-xs text-[#929792] text-right">
              {total} project{total !== 1 ? 's' : ''}
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
