import React, { Suspense, lazy } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AppLayout } from '../components/layout/AppLayout';
import { useAuth } from './AuthContext';
import { useProject } from './ProjectContext';
import { CenteredLoadingState } from '../components/common/LoadingState';
import { ErrorBoundary } from '../components/common/ErrorBoundary';
import { LandingPage } from '../pages/Landing';
import { LoginPage } from '../pages/Login';
import { RegisterPage } from '../pages/Register';

// The landing and auth pages stay in the main bundle so first paint is fast;
// the signed-in app pages load on demand.
const page = <T extends Record<string, React.ComponentType>>(
  load: () => Promise<T>,
  name: keyof T,
) => lazy(() => load().then((module) => ({ default: module[name] })));

const NewResearch = page(() => import('../pages/NewResearch'), 'NewResearch');
const ResearchProgressPage = page(() => import('../pages/ResearchProgress'), 'ResearchProgressPage');
const SettingsPage = page(() => import('../pages/Settings'), 'SettingsPage');
const ResearchReportPage = page(() => import('../pages/ResearchReport'), 'ResearchReportPage');
const ProjectsPage = page(() => import('../pages/Projects'), 'ProjectsPage');
const ProjectWorkspacePage = page(() => import('../pages/ProjectWorkspace'), 'ProjectWorkspacePage');
const NotFoundPage = page(() => import('../pages/NotFound'), 'NotFoundPage');
const GoogleAuthCompletePage = page(
  () => import('../pages/GoogleAuthComplete'),
  'GoogleAuthCompletePage',
);

/** Documents live inside projects now; send old links to the closest match. */
const DocumentsRedirect: React.FC = () => {
  const { selectedProject } = useProject();
  return (
    <Navigate
      to={selectedProject ? `/projects/${selectedProject.id}?tab=documents` : '/projects'}
      replace
    />
  );
};

const ProtectedLayout: React.FC = () => {
  const { user, loading } = useAuth();
  if (loading) return <CenteredLoadingState label="Restoring your session…" />;
  return user ? <AppLayout /> : <Navigate to="/login" replace />;
};

export const AppRouter: React.FC = () => {
  const location = useLocation();
  return (
    <ErrorBoundary key={location.pathname}>
      <Suspense fallback={<CenteredLoadingState label="Loading…" />}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/auth/google/complete" element={<GoogleAuthCompletePage />} />
          <Route element={<ProtectedLayout />}>
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/projects/:projectId" element={<ProjectWorkspacePage />} />
            <Route path="/research/new" element={<NewResearch />} />
            <Route path="/research/:id/progress" element={<ResearchProgressPage />} />
            {/* Research history lives in the sidebar now; keep old links working. */}
            <Route path="/research" element={<Navigate to="/research/new" replace />} />
            <Route path="/my-research" element={<Navigate to="/research/new" replace />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/research/:id" element={<ResearchReportPage />} />
            <Route path="/documents" element={<DocumentsRedirect />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
};
