/**
 * ProjectHeader: Shows the project name, archived status, and key actions.
 * Reusable across the workspace and any project-scoped sub-pages.
 */
import React, { useState } from 'react';
import { Archive, Pencil, Settings2 } from 'lucide-react';
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
          <h1 className="font-serif text-2xl sm:text-3xl text-[#181a18] font-normal tracking-tight leading-tight">
            {project.name}
          </h1>
          {project.description && (
            <p className="mt-2 text-sm text-[#6b706c] leading-relaxed max-w-2xl">
              {project.description}
            </p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-[#929792]">
            <span>Created {formatDate(project.createdAt)}</span>
            <span>·</span>
            <span>Updated {formatDate(project.updatedAt)}</span>
            {isArchived && project.archivedAt && (
              <>
                <span>·</span>
                <span className="flex items-center gap-1 text-[#b45309]">
                  <Archive className="w-3 h-3" />
                  Archived {formatDate(project.archivedAt)}
                </span>
              </>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            aria-label="Edit project settings"
            onClick={() => setIsEditOpen(true)}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-[#6b706c] hover:text-[#181a18] border border-[#e5e7e4] hover:bg-[#f5f5f2] px-3 py-2 rounded-lg transition-colors"
          >
            <Settings2 className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Settings</span>
          </button>
          {!isArchived && (
            <button
              type="button"
              aria-label="Archive this project"
              onClick={() => setIsArchiveOpen(true)}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-[#6b706c] hover:text-[#b91c1c] border border-[#e5e7e4] hover:border-[#fecaca] hover:bg-[#fee2e2]/30 px-3 py-2 rounded-lg transition-colors"
            >
              <Pencil className="w-3.5 h-3.5 hidden" />
              <Archive className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Archive</span>
            </button>
          )}
        </div>
      </div>

      {/* Archived banner */}
      {isArchived && (
        <div className="mt-4 flex items-start gap-3 rounded-xl border border-[#fde68a] bg-[#fef3c7]/60 px-4 py-3 text-sm text-[#b45309]">
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
