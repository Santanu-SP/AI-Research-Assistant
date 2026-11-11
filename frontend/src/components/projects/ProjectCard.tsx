import React, { useEffect, useRef, useState } from 'react';
import { MoreHorizontal, Pencil, Archive, ExternalLink, Folder } from 'lucide-react';
import { ResearchProject } from '../../types/project';
import { EditProjectDialog } from './EditProjectDialog';
import { ArchiveProjectDialog } from './ArchiveProjectDialog';

interface ProjectCardProps {
  project: ResearchProject;
  onOpen: (project: ResearchProject) => void;
  onUpdated: (updated: ResearchProject) => void;
  onArchived: (id: string) => void;
}

const formatDate = (iso: string): string =>
  new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year:
      new Date(iso).getFullYear() === new Date().getFullYear()
        ? undefined
        : 'numeric',
  }).format(new Date(iso));

/** One project in the projects list. Renders as a table-like row. */
export const ProjectCard: React.FC<ProjectCardProps> = ({
  project,
  onOpen,
  onUpdated,
  onArchived,
}) => {
  const [menuOpen, setMenuOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isArchiveOpen, setIsArchiveOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const isArchived = Boolean(project.archivedAt);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMenuOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', onKey);
    };
  }, [menuOpen]);

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
        className={`group relative grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-4 py-3.5 transition-colors sm:grid-cols-[minmax(0,1fr)_110px_110px_40px] sm:px-5 ${
          isArchived ? 'opacity-70' : 'cursor-pointer hover:bg-subtle/60'
        }`}
        onClick={() => !isArchived && onOpen(project)}
        onKeyDown={handleKeyDown}
        role={isArchived ? undefined : 'button'}
        tabIndex={isArchived ? undefined : 0}
        aria-label={`Open project: ${project.name}`}
      >
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-line bg-subtle text-ink-soft">
            <Folder className="h-4 w-4" strokeWidth={1.75} />
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="truncate text-sm font-medium text-ink">{project.name}</h3>
              {isArchived && (
                <span className="inline-flex shrink-0 items-center gap-1 rounded border border-line bg-subtle px-1.5 py-px text-[11px] font-medium text-ink-muted">
                  <Archive className="h-3 w-3" />
                  Archived
                </span>
              )}
            </div>
            <p className="mt-0.5 truncate text-[13px] text-ink-muted">
              {project.description || 'No description'}
            </p>
            <p className="mt-1 text-xs text-ink-muted sm:hidden">
              Updated {formatDate(project.updatedAt)}
            </p>
          </div>
        </div>

        <span className="hidden text-[13px] tabular-nums text-ink-soft sm:block">
          {formatDate(project.updatedAt)}
        </span>
        <span className="hidden text-[13px] tabular-nums text-ink-muted sm:block">
          {formatDate(project.createdAt)}
        </span>

        <div ref={menuRef} className="relative justify-self-end" onClick={(e) => e.stopPropagation()}>
          <button
            type="button"
            aria-label="Project actions"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((o) => !o)}
            className="flex h-8 w-8 items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-sunken hover:text-ink"
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>

          {menuOpen && (
            <div
              role="menu"
              className="absolute right-0 top-full z-20 mt-1 w-48 overflow-hidden rounded-lg border border-line bg-panel py-1 shadow-lg"
            >
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setMenuOpen(false);
                  onOpen(project);
                }}
                className="flex w-full items-center gap-2.5 px-3 py-2 text-[13px] text-ink hover:bg-subtle"
              >
                <ExternalLink className="h-4 w-4 shrink-0 text-ink-muted" />
                Open workspace
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setMenuOpen(false);
                  setIsEditOpen(true);
                }}
                className="flex w-full items-center gap-2.5 px-3 py-2 text-[13px] text-ink hover:bg-subtle"
              >
                <Pencil className="h-4 w-4 shrink-0 text-ink-muted" />
                Rename or edit
              </button>
              {!isArchived && (
                <>
                  <div className="my-1 h-px bg-line" />
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setMenuOpen(false);
                      setIsArchiveOpen(true);
                    }}
                    className="flex w-full items-center gap-2.5 px-3 py-2 text-[13px] text-danger hover:bg-danger-soft"
                  >
                    <Archive className="h-4 w-4 shrink-0" />
                    Archive project
                  </button>
                </>
              )}
            </div>
          )}
        </div>
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
