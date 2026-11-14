/**
 * Switching :projectId clears the previous project's documents before the
 * next fetch, so a slow response cannot paint the wrong workspace.
 */
import React, { useCallback, useEffect } from 'react';
import { useNavigate, useParams, useSearchParams, Link } from 'react-router-dom';
import { FileText, MessageSquareText, ArrowLeft, Archive, ChevronRight } from 'lucide-react';
import { TopBar } from '../components/layout/TopBar';
import { CenteredLoadingState } from '../components/common/LoadingState';
import { ErrorState } from '../components/common/ErrorState';
import { ProjectHeader } from '../components/projects/ProjectHeader';
import { ProjectSourcesPanel } from '../components/projects/ProjectSourcesPanel';
import { ProjectResearchPanel } from '../components/projects/ProjectResearchPanel';
import { DocumentsPanel } from '../components/documents/DocumentsPanel';
import { useDocumentLibrary } from '../hooks/useDocumentLibrary';
import { useProject } from '../app/ProjectContext';

type WorkspaceTab = 'ask' | 'documents';

const TABS: { id: WorkspaceTab; label: string; icon: typeof FileText }[] = [
  { id: 'ask', label: 'Ask', icon: MessageSquareText },
  { id: 'documents', label: 'Documents', icon: FileText },
];

export const ProjectWorkspacePage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { selectedProject, projectLoading, projectError, selectProject, refreshProject } =
    useProject();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab: WorkspaceTab = searchParams.get('tab') === 'documents' ? 'documents' : 'ask';
  const setActiveTab = useCallback(
    (tab: WorkspaceTab) =>
      setSearchParams(
        (params) => {
          const next = new URLSearchParams(params);
          if (tab === 'ask') next.delete('tab');
          else next.set('tab', tab);
          return next;
        },
        { replace: true },
      ),
    [setSearchParams],
  );
  // The Ask tab shows this project's documents beside the question box.
  const projectReady = Boolean(projectId) && selectedProject?.id === projectId;
  const askLibrary = useDocumentLibrary(
    projectReady && activeTab === 'ask' && projectId ? { projectId } : null,
  );

  // When the URL project changes, update the selected project context
  useEffect(() => {
    if (projectId) {
      selectProject(projectId);
    }
  }, [projectId, selectProject]);

  const isArchived = Boolean(selectedProject?.archivedAt);

  if (projectLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <CenteredLoadingState label="Loading project workspace…" />
      </div>
    );
  }

  if (projectError) {
    return (
      <div className="min-h-screen flex flex-col">
        <TopBar
          breadcrumbs={
            <div className="flex items-center gap-2">
              <Link to="/projects" className="text-ink-soft hover:text-ink">
                Projects
              </Link>
            </div>
          }
        />
        <div className="flex-1 pt-14 flex items-center justify-center">
          <ErrorState
            title="Project not available"
            message={projectError}
            onRetry={() => void refreshProject()}
          />
        </div>
      </div>
    );
  }

  if (!selectedProject) return null;

  return (
    <div className="min-h-screen flex flex-col">
      <TopBar
        breadcrumbs={
          <div className="flex min-w-0 items-center gap-2">
            <Link
              to="/projects"
              className="flex shrink-0 items-center gap-1 rounded-sm text-ink-soft hover:text-ink"
            >
              <ArrowLeft className="h-3.5 w-3.5 sm:hidden" />
              <span className="hidden sm:inline">Projects</span>
            </Link>
            <ChevronRight className="hidden h-3.5 w-3.5 shrink-0 text-ink-muted sm:block" />
            <span className="text-ink font-medium truncate">
              {selectedProject.name}
            </span>
            {isArchived && (
              <span className="inline-flex items-center gap-1 text-[10px] font-medium text-ink-muted bg-subtle border border-line px-1.5 py-0.5 rounded shrink-0">
                <Archive className="w-2.5 h-2.5" />
                Archived
              </span>
            )}
          </div>
        }
      />

      <main className="flex-1 pt-14 flex flex-col">
        <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-4 py-8 sm:px-6 sm:py-10 lg:px-0">
          <ProjectHeader
            project={selectedProject}
            onUpdated={() => void refreshProject()}
            onArchived={() => navigate('/projects')}
          />

          <div role="tablist" aria-label="Project sections" className="mt-8 flex items-center gap-5 border-b border-line">
            {TABS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                id={`tab-${id}`}
                role="tab"
                aria-selected={activeTab === id}
                aria-controls={`panel-${id}`}
                onClick={() => setActiveTab(id)}
                className={`-mb-px flex items-center gap-2 border-b-2 px-0.5 pb-2.5 pt-1 text-[13px] font-medium transition-colors ${
                  activeTab === id ? 'border-ink text-ink' : 'border-transparent text-ink-muted hover:text-ink'
                }`}
              >
                <Icon className="h-4 w-4" />
                {label}
                {id === 'documents' && askLibrary.total > 0 && activeTab === 'ask' && (
                  <span className="rounded-full bg-subtle px-1.5 text-[11px] tabular-nums text-ink-muted">
                    {askLibrary.total}
                  </span>
                )}
              </button>
            ))}
          </div>

          <div className="mt-6 flex-1">
            <div id="panel-ask" role="tabpanel" aria-labelledby="tab-ask" hidden={activeTab !== 'ask'}>
              {activeTab === 'ask' && (
                <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
                  <ProjectResearchPanel
                    project={selectedProject}
                    isArchived={isArchived}
                    readyCount={askLibrary.isLoading || askLibrary.error ? undefined : askLibrary.readyCount}
                    preparingCount={askLibrary.preparingCount}
                    onOpenRun={(researchId) => navigate(`/research/${researchId}/progress`)}
                  />
                  <DocumentsPanel
                    library={askLibrary}
                    projectId={selectedProject.id}
                    readOnly={isArchived}
                    manageHref={`/projects/${selectedProject.id}?tab=documents`}
                    className="lg:sticky lg:top-20 lg:max-h-[calc(100vh-7rem)]"
                  />
                </div>
              )}
            </div>
            <div id="panel-documents" role="tabpanel" aria-labelledby="tab-documents" hidden={activeTab !== 'documents'}>
              {activeTab === 'documents' && (
                <ProjectSourcesPanel project={selectedProject} isArchived={isArchived} />
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};
