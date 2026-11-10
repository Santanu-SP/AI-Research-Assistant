import React, { Suspense, lazy } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AppLayout } from '../components/layout/AppLayout';
import { useAuth } from './AuthContext';
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
const MyResearchPage = page(() => import('../pages/MyResearch'), 'MyResearchPage');
const ResearchReportPage = page(() => import('../pages/ResearchReport'), 'ResearchReportPage');
const DocumentsPage = page(() => import('../pages/Documents'), 'DocumentsPage');
const ProjectsPage = page(() => import('../pages/Projects'), 'ProjectsPage');
const ProjectWorkspacePage = page(() => import('../pages/ProjectWorkspace'), 'ProjectWorkspacePage');
const NotFoundPage = page(() => import('../pages/NotFound'), 'NotFoundPage');
const GoogleAuthCompletePage = page(
  () => import('../pages/GoogleAuthComplete'),
  'GoogleAuthCompletePage',
);

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
            <Route path="/research" element={<MyResearchPage />} />
            <Route path="/research/:id" element={<ResearchReportPage />} />
            <Route path="/documents" element={<DocumentsPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
};
