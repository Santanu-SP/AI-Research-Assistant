/**
 * ProjectCard: A single project card in the projects grid.
 *
 * Shows real backend fields only: name, description, archivedAt, updatedAt.
 * Includes inline edit and archive actions accessible via keyboard.
 */
import React, { useState } from 'react';
import { MoreHorizontal, Pencil, Archive, ExternalLink } from 'lucide-react';
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

export const ProjectCard: React.FC<ProjectCardProps> = ({
  project,
  onOpen,
  onUpdated,
  onArchived,
}) => {
  const [menuOpen, setMenuOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isArchiveOpen, setIsArchiveOpen] = useState(false);
  const isArchived = Boolean(project.archivedAt);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onOpen(project);
    }
  };

  return (
    <>
      <div
        className={`group relative rounded-xl border bg-white transition-all duration-150 ${
          isArchived
            ? 'border-[#e5e7e4] opacity-70'
            : 'border-[#e5e7e4] hover:border-[#cbd0ca] hover:shadow-sm cursor-pointer'
        }`}
        onClick={() => !isArchived && onOpen(project)}
        onKeyDown={handleKeyDown}
        role={isArchived ? undefined : 'button'}
        tabIndex={isArchived ? undefined : 0}
        aria-label={`Open project: ${project.name}`}
      >
        {/* Card header */}
        <div className="p-5 pb-3">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap mb-1">
                {isArchived && (
                  <span className="inline-flex items-center gap-1 text-[10px] font-medium text-[#929792] bg-[#f5f5f2] border border-[#e5e7e4] px-1.5 py-0.5 rounded">
                    <Archive className="w-2.5 h-2.5" />
                    Archived
                  </span>
                )}
              </div>
              <h3
                className={`font-semibold text-sm leading-snug ${
                  isArchived
                    ? 'text-[#6b706c]'
                    : 'text-[#181a18] group-hover:text-[#163328] transition-colors'
                }`}
              >
                {project.name}
              </h3>
            </div>

            {/* Actions menu */}
            <div className="relative shrink-0" onClick={(e) => e.stopPropagation()}>
              <button
                type="button"
                aria-label="Project actions"
                aria-expanded={menuOpen}
                onClick={() => setMenuOpen((o) => !o)}
                className="p-1.5 rounded-md text-[#929792] hover:text-[#181a18] hover:bg-[#f5f5f2] transition-colors"
              >
                <MoreHorizontal className="w-4 h-4" />
              </button>

              {menuOpen && (
                <>
                  <div
                    className="fixed inset-0 z-10"
                    onClick={() => setMenuOpen(false)}
                  />
                  <div className="absolute right-0 top-full mt-1 w-44 bg-white rounded-lg border border-[#e5e7e4] shadow-lg z-20 overflow-hidden py-1">
                    <button
                      type="button"
                      onClick={() => {
                        setMenuOpen(false);
                        onOpen(project);
                      }}
                      className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-[#181a18] hover:bg-[#fafaf8] transition-colors"
                    >
                      <ExternalLink className="w-3.5 h-3.5 shrink-0 text-[#929792]" />
                      Open workspace
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setMenuOpen(false);
                        setIsEditOpen(true);
                      }}
                      className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-[#181a18] hover:bg-[#fafaf8] transition-colors"
                    >
                      <Pencil className="w-3.5 h-3.5 shrink-0 text-[#929792]" />
                      Edit project
                    </button>
                    {!isArchived && (
                      <button
                        type="button"
                        onClick={() => {
                          setMenuOpen(false);
                          setIsArchiveOpen(true);
                        }}
                        className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-[#b91c1c] hover:bg-[#fee2e2]/40 transition-colors"
                      >
                        <Archive className="w-3.5 h-3.5 shrink-0" />
                        Archive project
                      </button>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>

          {project.description && (
            <p className="text-xs text-[#6b706c] mt-2 line-clamp-2 leading-relaxed">
              {project.description}
            </p>
          )}
        </div>

        {/* Card footer */}
        <div className="px-5 pb-4 pt-2 border-t border-[#f5f5f2] flex items-center justify-between text-[11px] text-[#929792]">
          <span>Updated {formatDate(project.updatedAt)}</span>
          <span>Created {formatDate(project.createdAt)}</span>
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
