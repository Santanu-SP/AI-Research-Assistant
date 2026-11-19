import React, { useState } from 'react';
import { Pencil, Archive, ExternalLink, Folder } from 'lucide-react';
import { ActionMenu } from '../common/ActionMenu';
import { ResearchProject } from '../../types/project';
import { EditProjectDialog } from './EditProjectDialog';
import { ArchiveProjectDialog } from './ArchiveProjectDialog';

interface ProjectCardProps {
  project: ResearchProject;
  onOpen: (project: ResearchProject) => void;
  onUpdated: (updated: ResearchProject) => void;
  onArchived: (id: string) => void;
}

/** "3 files · 1 report", or null when the list did not include counts. */
export const projectCountsLabel = (project: ResearchProject): string | null => {
  if (typeof project.fileCount !== 'number' || typeof project.reportCount !== 'number') return null;
  const files = `${project.fileCount} ${project.fileCount === 1 ? 'file' : 'files'}`;
  const reports = `${project.reportCount} ${project.reportCount === 1 ? 'report' : 'reports'}`;
  return `${files} · ${reports}`;
};

export const formatProjectDate = (iso: string): string =>
  new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year:
      new Date(iso).getFullYear() === new Date().getFullYear()
        ? undefined
        : 'numeric',
  }).format(new Date(iso));

/** One active project in the projects list. Renders as a table-like row. Archived ones use ArchivedProjectRow. */
export const ProjectCard: React.FC<ProjectCardProps> = ({
  project,
  onOpen,
  onUpdated,
  onArchived,
}) => {
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isArchiveOpen, setIsArchiveOpen] = useState(false);
  const counts = projectCountsLabel(project);
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.target !== e.currentTarget) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onOpen(project);
    }
  };

  return (
    <>
      <div
        className="group relative grid cursor-pointer grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-4 py-3.5 transition-colors hover:bg-subtle/60 sm:grid-cols-[minmax(0,1fr)_110px_110px_40px] sm:px-5"
        onClick={() => onOpen(project)}
        onKeyDown={handleKeyDown}
        role="button"
        tabIndex={0}
        aria-label={`Open project: ${project.name}`}
      >
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-line bg-subtle text-ink-soft">
            <Folder className="h-4 w-4" strokeWidth={1.75} />
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="truncate text-sm font-medium text-ink">{project.name}</h3>
              {project.isShared && (
                <span className="shrink-0 rounded-full border border-accent-line bg-accent-soft px-2 py-0.5 text-[11px] font-medium text-accent">
                  {(project.myRole ?? 'owner') === 'owner'
                    ? 'Shared'
                    : project.myRole === 'editor'
                      ? 'Shared · Edit'
                      : 'Shared · View'}
                </span>
              )}
            </div>
            <p className="mt-0.5 truncate text-[13px] text-ink-muted">
              {project.description || 'No description'}
            </p>
            {(counts || (project.ownerName && (project.myRole ?? 'owner') !== 'owner')) && (
              <p className="mt-1 text-xs tabular-nums text-ink-soft">
                {[
                  counts,
                  project.ownerName && (project.myRole ?? 'owner') !== 'owner'
                    ? `Owner: ${project.ownerName}`
                    : null,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </p>
            )}
            <p className="mt-1 text-xs text-ink-muted sm:hidden">
              Updated {formatProjectDate(project.updatedAt)}
            </p>
          </div>
        </div>

        <span className="hidden text-[13px] tabular-nums text-ink-soft sm:block">
          {formatProjectDate(project.updatedAt)}
        </span>
        <span className="hidden text-[13px] tabular-nums text-ink-muted sm:block">
          {formatProjectDate(project.createdAt)}
        </span>

        <ActionMenu
          label={`Actions for ${project.name}`}
          className="justify-self-end"
          items={[
            { label: 'Open project', icon: ExternalLink, onSelect: () => onOpen(project) },
            ...((project.myRole ?? 'owner') === 'owner' || project.myRole === 'editor'
              ? [{ label: 'Rename or edit', icon: Pencil, onSelect: () => setIsEditOpen(true) }]
              : []),
            ...((project.myRole ?? 'owner') === 'owner'
              ? [
                  {
                    label: 'Archive project',
                    icon: Archive,
                    danger: true,
                    separated: true,
                    onSelect: () => setIsArchiveOpen(true),
                  },
                ]
              : []),
          ]}
        />
      </div>

      <EditProjectDialog
        project={isEditOpen ? project : null}
        onClose={() => setIsEditOpen(false)}
        onUpdated={(updated) => {
          setIsEditOpen(false);
          onUpdated(updated);
        }}
      />

      <ArchiveProjectDialog
        project={isArchiveOpen ? project : null}
        onClose={() => setIsArchiveOpen(false)}
        onArchived={() => {
          setIsArchiveOpen(false);
          onArchived(project.id);
        }}
      />
    </>
  );
};
