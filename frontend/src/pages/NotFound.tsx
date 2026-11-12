import React from 'react';
import { useNavigate } from 'react-router-dom';
import { TopBar } from '../components/layout/TopBar';
import { PrimaryButton } from '../components/common/PrimaryButton';

export const NotFoundPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="flex min-h-screen flex-col">
      <TopBar breadcrumbs={<span className="font-medium text-ink">Not found</span>} />
      <main className="flex flex-1 flex-col items-center justify-center px-6 pt-14">
        <div className="max-w-md text-center">
          <p className="font-mono text-xs text-ink-muted">404</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-[-0.015em] text-ink">Page not found</h1>
          <p className="mt-2 text-sm text-ink-soft">
            The page you’re looking for doesn’t exist or may have moved.
          </p>
          <div className="mt-6 flex items-center justify-center gap-2">
            <PrimaryButton variant="outline" onClick={() => navigate('/projects')}>
              Go to projects
            </PrimaryButton>
            <PrimaryButton onClick={() => navigate('/research/new')}>New research</PrimaryButton>
          </div>
        </div>
      </main>
    </div>
  );
};
