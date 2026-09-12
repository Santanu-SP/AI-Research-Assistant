import React from 'react';
import { useNavigate } from 'react-router-dom';
import { TopBar } from '../components/layout/TopBar';
import { EmptyState } from '../components/common/EmptyState';
import { FileQuestion } from 'lucide-react';

export const NotFoundPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-[#fafaf8] flex flex-col">
      <TopBar
        breadcrumbs={
          <span className="text-[#181a18] font-medium">Not Found</span>
        }
      />
      <main className="flex-1 flex flex-col items-center justify-center p-6">
        <div className="w-full max-w-lg">
          <EmptyState
            icon={FileQuestion}
            title="Page not found"
            description="The page you’re looking for doesn’t exist or may have moved."
            primaryActionLabel="New research"
            onPrimaryAction={() => navigate('/research/new')}
            secondaryActionLabel="My research"
            onSecondaryAction={() => navigate('/research')}
          />
        </div>
      </main>
    </div>
  );
};
