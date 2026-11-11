import React, { useState } from 'react';
import { Archive, Settings2 } from 'lucide-react';
import { ResearchProject } from '../../types/project';
import { EditProjectDialog } from './EditProjectDialog';
import { ArchiveProjectDialog } from './ArchiveProjectDialog';

interface ProjectHeaderProps {
  project: ResearchProject;
  onUpdated: () => void;
  onArchived: () => void;
}

const formatDate = (iso: string): string =>
  new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(new Date(iso));

export const ProjectHeader: React.FC<ProjectHeaderProps> = ({
  project,
  onUpdated,
  onArchived,
}) => {
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isArchiveOpen, setIsArchiveOpen] = useState(false);
  const isArchived = Boolean(project.archivedAt);

  return (
    <>
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-[22px] font-semibold leading-tight tracking-[-0.015em] text-ink sm:text-2xl">
            {project.name}
          </h1>
          {project.description && (
            <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-ink-soft">
              {project.description}
            </p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-muted">
            <span>Created {formatDate(project.createdAt)}</span>
            <span>·</span>
            <span>Updated {formatDate(project.updatedAt)}</span>
            {isArchived && project.archivedAt && (
              <>
                <span>·</span>
                <span className="flex items-center gap-1 text-warning">
                  <Archive className="w-3 h-3" />
                  Archived {formatDate(project.archivedAt)}
                </span>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            aria-label="Edit project settings"
            onClick={() => setIsEditOpen(true)}
            className="inline-flex h-9 items-center gap-1.5 rounded-md border border-line-strong bg-panel px-3 text-[13px] font-medium text-ink shadow-xs transition-colors hover:bg-subtle"
          >
            <Settings2 className="h-4 w-4" />
            <span className="hidden sm:inline">Settings</span>
          </button>
          {!isArchived && (
            <button
              type="button"
              aria-label="Archive this project"
              onClick={() => setIsArchiveOpen(true)}
              className="inline-flex h-9 items-center gap-1.5 rounded-md px-3 text-[13px] font-medium text-ink-soft transition-colors hover:bg-danger-soft hover:text-danger"
            >
              <Archive className="h-4 w-4" />
              <span className="hidden sm:inline">Archive</span>
            </button>
          )}
        </div>
      </div>

      {isArchived && (
        <div className="mt-5 flex items-start gap-3 rounded-lg border border-warning-line bg-warning-soft px-4 py-3 text-[13px] text-warning">
          <Archive className="w-4 h-4 mt-0.5 shrink-0" />
          <p>
            <strong>This project is archived.</strong> You can view existing
            documents and research results, but cannot upload new documents or
            run new research.
          </p>
        </div>
      )}

      <EditProjectDialog
        project={isEditOpen ? project : null}
        onClose={() => setIsEditOpen(false)}
        onUpdated={() => {
          setIsEditOpen(false);
          onUpdated();
        }}
      />

      <ArchiveProjectDialog
        project={isArchiveOpen ? project : null}
        onClose={() => setIsArchiveOpen(false)}
        onArchived={() => {
          setIsArchiveOpen(false);
          onArchived();
        }}
      />
    </>
  );
};
