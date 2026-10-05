/**
 * ProjectContext: Provides the currently selected ResearchProject to the app.
 *
 * The selected project is stored by ID in sessionStorage so that:
 *  - Refreshing a page within a project preserves context.
 *  - Navigating away and back restores the selection.
 *  - A new browser tab always starts fresh.
 *
 * Components that display project-scoped data must consume this context
 * and re-fetch whenever selectedProjectId changes.
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from 'react';
import { ResearchProject } from '../types/project';
import { projectsService } from '../services/projects.service';

const SESSION_KEY = 'selected_project_id';

interface ProjectState {
  /** The currently selected project (null = no project selected). */
  selectedProject: ResearchProject | null;
  /** True while the project is being loaded from the API. */
  projectLoading: boolean;
  /** Error encountered when loading the selected project. */
  projectError: string | null;
  /** Select a project by its ID, triggering a fetch if needed. */
  selectProject: (id: string | null) => void;
  /** Force-refresh the selected project from the API. */
  refreshProject: () => Promise<void>;
  /** Clear the selected project and remove it from session. */
  clearProject: () => void;
}

const ProjectContext = createContext<ProjectState | null>(null);

export const ProjectProvider: React.FC<React.PropsWithChildren> = ({
  children,
}) => {
  const [selectedId, setSelectedId] = useState<string | null>(() => {
    try {
      return sessionStorage.getItem(SESSION_KEY);
    } catch {
      return null;
    }
  });
  const [selectedProject, setSelectedProject] =
    useState<ResearchProject | null>(null);
  const [projectLoading, setProjectLoading] = useState(false);
  const [projectError, setProjectError] = useState<string | null>(null);

  const fetchProject = useCallback(async (id: string) => {
    setProjectLoading(true);
    setProjectError(null);
    try {
      const project = await projectsService.getProject(id);
      setSelectedProject(project);
    } catch {
      setSelectedProject(null);
      setProjectError('Project could not be loaded.');
      // Remove stale session entry on 404/403
      try {
        sessionStorage.removeItem(SESSION_KEY);
      } catch {
        // Storage unavailable
      }
      setSelectedId(null);
    } finally {
      setProjectLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setSelectedProject(null);
      return;
    }
    void fetchProject(selectedId);
  }, [selectedId, fetchProject]);

  const selectProject = useCallback((id: string | null) => {
    try {
      if (id) {
        sessionStorage.setItem(SESSION_KEY, id);
      } else {
        sessionStorage.removeItem(SESSION_KEY);
      }
    } catch {
      // Storage unavailable – continue without persistence
    }
    setSelectedId(id);
  }, []);

  const refreshProject = useCallback(async () => {
    if (selectedId) {
      await fetchProject(selectedId);
    }
  }, [selectedId, fetchProject]);

  const clearProject = useCallback(() => {
    try {
      sessionStorage.removeItem(SESSION_KEY);
    } catch {
      // Storage unavailable
    }
    setSelectedId(null);
    setSelectedProject(null);
    setProjectError(null);
  }, []);

  return (
    <ProjectContext.Provider
      value={{
        selectedProject,
        projectLoading,
        projectError,
        selectProject,
        refreshProject,
        clearProject,
      }}
    >
      {children}
    </ProjectContext.Provider>
  );
};

export const useProject = (): ProjectState => {
  const state = useContext(ProjectContext);
  if (!state) throw new Error('ProjectProvider is missing from the tree');
  return state;
};
