import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Trash2 } from 'lucide-react';
import { ResearchProject } from '../../types/project';
import { getProjectErrorMessage, projectsService } from '../../services/projects.service';
import { useToast } from '../../app/ToastContext';

interface DeleteProjectDialogProps {
  project: ResearchProject;
  onCancel: () => void;
  onDeleted: (id: string) => void;
}

/** Confirms deleting an archived project for good. Its files and research are kept. */
export const DeleteProjectDialog: React.FC<DeleteProjectDialogProps> = ({ project, onCancel, onDeleted }) => {
  const { addToast } = useToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    cancelRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) {
        event.stopPropagation();
        onCancel();
      }
    };
    document.addEventListener('keydown', onKey, true);
    return () => document.removeEventListener('keydown', onKey, true);
  }, [busy, onCancel]);

  const confirm = async () => {
    setBusy(true);
    setError(null);
    try {
      await projectsService.deleteProjectPermanently(project.id);
      addToast({ type: 'success', title: 'Project deleted', description: `“${project.name}” was deleted.` });
      onDeleted(project.id);
    } catch (err) {
      setError(getProjectErrorMessage(err, 'Could not delete this project.'));
      setBusy(false);
    }
  };

  return createPortal(
    <div
      className="overlay-enter fixed inset-0 z-[80] flex items-center justify-center bg-black/40 p-4"
      onMouseDown={() => !busy && onCancel()}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="delete-project-title"
        aria-describedby="delete-project-description"
        className="dialog-enter w-full max-w-sm overflow-hidden rounded-xl border border-line bg-panel shadow-xl"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="px-6 py-5">
          <div className="mb-3 flex items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-danger-line bg-danger-soft">
              <Trash2 className="h-[18px] w-[18px] text-danger" />
            </div>
            <h3 id="delete-project-title" className="text-base font-semibold text-ink">
              Delete project for good?
            </h3>
          </div>
          <p id="delete-project-description" className="text-sm leading-relaxed text-ink-soft">
            <strong className="font-medium text-ink">“{project.name}”</strong> will be deleted and can’t be restored.
            Its files stay in your Library and its research stays in your history.
          </p>
          {error && (
            <p role="alert" className="mt-3 rounded-lg border border-danger-line bg-danger-soft px-3 py-2 text-xs text-danger">
              {error}
            </p>
          )}
          <div className="mt-5 flex items-center gap-2.5">
            <button
              ref={cancelRef}
              type="button"
              onClick={onCancel}
              disabled={busy}
              className="inline-flex h-9 flex-1 items-center justify-center rounded-md border border-line-strong bg-panel px-4 text-[13px] font-medium text-ink shadow-xs transition-colors hover:bg-subtle disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void confirm()}
              disabled={busy}
              className="inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-md bg-danger-solid px-4 text-[13px] font-medium text-on-solid shadow-xs transition-colors hover:bg-danger-solid-hover disabled:opacity-60"
            >
              {busy ? 'Deleting…' : 'Delete permanently'}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
};
