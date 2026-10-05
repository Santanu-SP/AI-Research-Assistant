/**
 * ProjectWorkspacePage: The central workspace for a selected research project.
 *
 * Route: /projects/:projectId
 *
 * Sections:
 *  1. ProjectHeader – project name, archived state, actions
 *  2. Sources tab – project documents, upload
 *  3. Research tab – project-scoped research composer + recent results
 *
 * Changing :projectId in the URL switches context safely. The previous
 * project's data is cleared before the new project loads.
 */
import React, { useEffect, useState } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { FileText, Compass, ArrowLeft, Archive } from 'lucide-react';
import { TopBar } from '../components/layout/TopBar';
import { CenteredLoadingState } from '../components/common/LoadingState';
import { ErrorState } from '../components/common/ErrorState';
import { ProjectHeader } from '../components/projects/ProjectHeader';
import { ProjectSourcesPanel } from '../components/projects/ProjectSourcesPanel';
import { ProjectResearchPanel } from '../components/projects/ProjectResearchPanel';
import { useProject } from '../app/ProjectContext';

type WorkspaceTab = 'sources' | 'research';

export const ProjectWorkspacePage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { selectedProject, projectLoading, projectError, selectProject, refreshProject } =
    useProject();
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('sources');

  // When the URL project changes, update the selected project context
  useEffect(() => {
    if (projectId) {
      selectProject(projectId);
    }
  }, [projectId, selectProject]);

  const isArchived = Boolean(selectedProject?.archivedAt);

  if (projectLoading) {
    return (
      <div className="min-h-screen bg-[#fafaf8] flex items-center justify-center">
        <CenteredLoadingState label="Loading project workspace…" />
      </div>
    );
  }

  if (projectError) {
    return (
      <div className="min-h-screen bg-[#fafaf8] flex flex-col">
        <TopBar
          breadcrumbs={
            <div className="flex items-center gap-2">
              <Link to="/projects" className="text-[#6b706c] hover:text-[#181a18]">
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
    <div className="min-h-screen bg-[#fafaf8] flex flex-col">
      {/* TopBar */}
      <TopBar
        breadcrumbs={
          <div className="flex items-center gap-2 text-xs">
            <Link
              to="/projects"
              className="text-[#6b706c] hover:text-[#181a18] flex items-center gap-1 shrink-0"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Projects</span>
            </Link>
            <span className="text-[#929792]">/</span>
            <span className="text-[#181a18] font-medium truncate">
              {selectedProject.name}
            </span>
            {isArchived && (
              <span className="inline-flex items-center gap-1 text-[10px] font-medium text-[#929792] bg-[#f5f5f2] border border-[#e5e7e4] px-1.5 py-0.5 rounded shrink-0">
                <Archive className="w-2.5 h-2.5" />
                Archived
              </span>
            )}
          </div>
        }
      />

      <main className="flex-1 pt-14 flex flex-col">
        <div className="max-w-5xl mx-auto w-full px-4 sm:px-6 py-6 flex flex-col flex-1">
          {/* Project Header */}
          <ProjectHeader
            project={selectedProject}
            onUpdated={() => void refreshProject()}
            onArchived={() => navigate('/projects')}
          />

          {/* Tab Navigation */}
          <div className="border-b border-[#e5e7e4] mt-6 mb-0 flex items-center gap-0">
            <button
              type="button"
              id="tab-sources"
              role="tab"
              aria-selected={activeTab === 'sources'}
              aria-controls="panel-sources"
              onClick={() => setActiveTab('sources')}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
                activeTab === 'sources'
                  ? 'border-[#163328] text-[#163328]'
                  : 'border-transparent text-[#6b706c] hover:text-[#181a18] hover:border-[#d0d7d2]'
              }`}
            >
              <FileText className="w-4 h-4" />
              Sources
            </button>
            <button
              type="button"
              id="tab-research"
              role="tab"
              aria-selected={activeTab === 'research'}
              aria-controls="panel-research"
              onClick={() => setActiveTab('research')}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
                activeTab === 'research'
                  ? 'border-[#163328] text-[#163328]'
                  : 'border-transparent text-[#6b706c] hover:text-[#181a18] hover:border-[#d0d7d2]'
              }`}
            >
              <Compass className="w-4 h-4" />
              Research
            </button>
          </div>

          {/* Tab Panels */}
          <div className="flex-1 mt-6">
            <div
              id="panel-sources"
              role="tabpanel"
              aria-labelledby="tab-sources"
              hidden={activeTab !== 'sources'}
            >
              {activeTab === 'sources' && (
                <ProjectSourcesPanel
                  project={selectedProject}
                  isArchived={isArchived}
                />
              )}
            </div>
            <div
              id="panel-research"
              role="tabpanel"
              aria-labelledby="tab-research"
              hidden={activeTab !== 'research'}
            >
              {activeTab === 'research' && (
                <ProjectResearchPanel
                  project={selectedProject}
                  isArchived={isArchived}
                />
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};
