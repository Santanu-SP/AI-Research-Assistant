/**
 * Switching :projectId clears the previous project's documents before the
 * next fetch, so a slow response cannot paint the wrong workspace.
 */
import React, { useCallback, useEffect, useState } from 'react';
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
import { useRealtimeRoom } from '../hooks/useRealtimeRoom';
import { useProject } from '../app/ProjectContext';
import { useAuth } from '../app/AuthContext';
import { useToast } from '../app/ToastContext';
import type { RealtimeEventEnvelope } from '../types/collaboration';

type WorkspaceTab = 'ask' | 'documents';

const TABS: { id: WorkspaceTab; label: string; icon: typeof FileText }[] = [
  { id: 'ask', label: 'Ask', icon: MessageSquareText },
  { id: 'documents', label: 'Files', icon: FileText },
];

export const ProjectWorkspacePage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { addToast } = useToast();
  const { selectedProject, projectLoading, projectError, selectProject, refreshProject } =
    useProject();
  const [searchParams, setSearchParams] = useSearchParams();
  const [researchSyncSignal, setResearchSyncSignal] = useState(0);
  const activeTab: WorkspaceTab = searchParams.get('tab') === 'documents' ? 'documents' : 'ask';
  const [visitedTabs, setVisitedTabs] = useState<{
    projectId?: string;
    ask: boolean;
    documents: boolean;
  }>(() => ({
    projectId,
    ask: activeTab === 'ask',
    documents: activeTab === 'documents',
  }));
  useEffect(() => {
    setVisitedTabs((prev) => {
      if (prev.projectId !== projectId) {
        return {
          projectId,
          ask: activeTab === 'ask',
          documents: activeTab === 'documents',
        };
      }
      if ((activeTab === 'ask' && prev.ask) || (activeTab === 'documents' && prev.documents)) {
        return prev;
      }
      return {
        ...prev,
        ask: prev.ask || activeTab === 'ask',
        documents: prev.documents || activeTab === 'documents',
      };
    });
  }, [projectId, activeTab]);
  const askMounted = activeTab === 'ask' || (visitedTabs.projectId === projectId && visitedTabs.ask);
  const documentsMounted =
    activeTab === 'documents' || (visitedTabs.projectId === projectId && visitedTabs.documents);

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
    projectReady && askMounted && projectId ? { projectId } : null,
  );
  const reloadAskLibrary = askLibrary.reload;

  const handleRealtimeEvent = useCallback(
    (event: RealtimeEventEnvelope) => {
      const eventProjectId =
        (event.payload as { projectId?: string | null })?.projectId ?? projectId ?? null;
      if (event.type === 'project.updated' || event.type === 'project.archived' || event.type === 'project.restored') {
        void refreshProject();
        return;
      }
      if (event.type === 'project.deleted') {
        addToast({ type: 'info', title: 'Project removed', description: 'This project was deleted by the owner.' });
        navigate('/projects', { replace: true });
        return;
      }
      if (event.type === 'member.removed') {
        const removedUserId = (event.payload as { userId?: string })?.userId;
        if (removedUserId && removedUserId === user?.id) {
          addToast({ type: 'info', title: 'Access removed', description: 'You no longer have access to this project.' });
          navigate('/projects', { replace: true });
          return;
        }
        void refreshProject();
        return;
      }
      if (event.type === 'member.joined' || event.type === 'member.updated') {
        void refreshProject();
        return;
      }
      if (event.type === 'document.added' || event.type === 'document.updated' || event.type === 'document.deleted') {
        reloadAskLibrary();
        window.dispatchEvent(
          new CustomEvent('documents:remote-sync', { detail: { projectId: eventProjectId } }),
        );
        return;
      }
      if (
        event.type.startsWith('research.') ||
        event.type === 'followup.created'
      ) {
        setResearchSyncSignal((prev) => prev + 1);
        window.dispatchEvent(new Event('research-history:refresh'));
      }
    },
    [projectId, refreshProject, reloadAskLibrary, navigate, addToast, user?.id],
  );

  const { connectionState, presence, sendActivity } = useRealtimeRoom({
    resourceType: 'project',
    resourceId: projectId,
    enabled: projectReady,
    onEvent: handleRealtimeEvent,
  });

  // When the URL project changes, update the selected project context
  useEffect(() => {
    if (projectId) {
      selectProject(projectId);
    }
  }, [projectId, selectProject]);

  const isArchived = Boolean(selectedProject?.archivedAt);
  const isViewer = selectedProject?.myRole === 'viewer';
  const isReadOnly = isArchived || isViewer;

  if (projectLoading && !projectReady) {
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
            presence={presence}
            connectionState={connectionState}
            currentUserId={user?.id ?? null}
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
              {askMounted && (
                <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
                  <ProjectResearchPanel
                    project={selectedProject}
                    isArchived={isArchived}
                    readOnly={isReadOnly}
                    readyCount={askLibrary.isLoading || askLibrary.error ? undefined : askLibrary.readyCount}
                    preparingCount={askLibrary.preparingCount}
                    researchSyncSignal={researchSyncSignal}
                    onActivity={(activity) => sendActivity(activity)}
                    onOpenRun={(researchId) => navigate(`/research/${researchId}/progress`)}
                  />
                  <DocumentsPanel
                    library={askLibrary}
                    projectId={selectedProject.id}
                    readOnly={isReadOnly}
                    manageHref={`/projects/${selectedProject.id}?tab=documents`}
                    className="lg:sticky lg:top-20 lg:max-h-[calc(100vh-7rem)]"
                  />
                </div>
              )}
            </div>
            <div id="panel-documents" role="tabpanel" aria-labelledby="tab-documents" hidden={activeTab !== 'documents'}>
              {documentsMounted && (
                <ProjectSourcesPanel
                  project={selectedProject}
                  isArchived={isArchived}
                  readOnly={isViewer}
                  onActivity={(activity) => sendActivity(activity)}
                />
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};
