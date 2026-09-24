import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { AppLayout } from '../components/layout/AppLayout';
import { NewResearch } from '../pages/NewResearch';
import { ResearchProgressPage } from '../pages/ResearchProgress';
import { MyResearchPage } from '../pages/MyResearch';
import { ResearchReportPage } from '../pages/ResearchReport';
import { DocumentsPage } from '../pages/Documents';
import { NotFoundPage } from '../pages/NotFound';
import { LoginPage } from '../pages/Login';
import { RegisterPage } from '../pages/Register';
import { useAuth } from './AuthContext';
import { CenteredLoadingState } from '../components/common/LoadingState';
import { LandingPage } from '../pages/Landing';
import { GoogleAuthCompletePage } from '../pages/GoogleAuthComplete';

const ProtectedLayout: React.FC = () => {
  const { user, loading } = useAuth();
  if (loading) return <CenteredLoadingState label="Restoring your session…" />;
  return user ? <AppLayout /> : <Navigate to="/login" replace />;
};

export const AppRouter: React.FC = () => {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/auth/google/complete" element={<GoogleAuthCompletePage />} />
      <Route element={<ProtectedLayout />}>
        <Route path="/research/new" element={<NewResearch />} />
        <Route path="/research/:id/progress" element={<ResearchProgressPage />} />
        <Route path="/research" element={<MyResearchPage />} />
        <Route path="/research/:id" element={<ResearchReportPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        {/* Fallback route */}
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
};
