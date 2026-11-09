/**
 * The selected project id is kept in sessionStorage so a refresh stays in
 * the same project, and a new tab starts with nothing selected.
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
  selectedProject: ResearchProject | null;
  projectLoading: boolean;
  projectError: string | null;
  selectProject: (id: string | null) => void;
  refreshProject: () => Promise<void>;
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
