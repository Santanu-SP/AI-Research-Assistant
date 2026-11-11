import React, { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { PrimaryButton } from '../common/PrimaryButton';
import { ResearchProject } from '../../types/project';
import {
  getProjectErrorMessage,
  projectsService,
} from '../../services/projects.service';
import { useToast } from '../../app/ToastContext';

interface CreateProjectDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (project: ResearchProject) => void;
}

export const CreateProjectDialog: React.FC<CreateProjectDialogProps> = ({
  isOpen,
  onClose,
  onCreated,
}) => {
  const { addToast } = useToast();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  // Focus the name field when dialog opens
  useEffect(() => {
    if (isOpen) {
      setName('');
      setDescription('');
      setError(null);
      setTimeout(() => nameRef.current?.focus(), 50);
    }
  }, [isOpen]);

  // Escape key dismissal
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isSubmitting) onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isOpen, isSubmitting, onClose]);

  if (!isOpen) return null;

  const trimmedName = name.trim();
  const isValid = trimmedName.length >= 1 && trimmedName.length <= 200;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid || isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const project = await projectsService.createProject({
        name: trimmedName,
        description: description.trim() || undefined,
      });
      addToast({ type: 'success', title: 'Project created', description: project.name });
      onCreated(project);
    } catch (err) {
      setError(getProjectErrorMessage(err, 'Failed to create project.'));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 overlay-enter"
      onMouseDown={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-project-title"
        className="w-full max-w-md bg-panel rounded-xl shadow-xl border border-line overflow-hidden dialog-enter"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-4 border-b border-line flex items-center justify-between">
          <div>
            <h3
              id="create-project-title"
              className="font-semibold text-base text-ink"
            >
              New project
            </h3>
            <p className="text-xs text-ink-soft mt-0.5">
              A workspace for your documents and research questions.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="text-ink-muted hover:text-ink p-1.5 rounded-md hover:bg-subtle transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={(e) => void handleSubmit(e)} className="p-6 space-y-4">
          <div>
            <label
              htmlFor="project-name"
              className="field-label"
            >
              Project name <span aria-hidden="true" className="text-danger">*</span>
            </label>
            <input
              ref={nameRef}
              id="project-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Membrane protein folding"
              maxLength={200}
              required
              autoComplete="off"
              className="field"
            />
            <div className="mt-1 text-right text-[11px] text-ink-muted">
              {name.trim().length}/200
            </div>
          </div>

          <div>
            <label
              htmlFor="project-description"
              className="field-label"
            >
              Description{' '}
              <span className="text-ink-muted font-normal">(optional)</span>
            </label>
            <textarea
              id="project-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Research scope, objectives, or background…"
              maxLength={5000}
              rows={3}
              className="field resize-none"
            />
          </div>

          {error && (
            <p role="alert" className="rounded-md border border-danger-line bg-danger-soft px-3 py-2 text-xs text-danger">
              {error}
            </p>
          )}

          <div className="flex items-center justify-end gap-2.5 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-9 items-center rounded-md px-3.5 text-[13px] font-medium text-ink-soft transition-colors hover:bg-subtle hover:text-ink"
            >
              Cancel
            </button>
            <PrimaryButton
              type="submit"
              disabled={!isValid || isSubmitting}
              isLoading={isSubmitting}
            >
              {isSubmitting ? 'Creating…' : 'Create project'}
            </PrimaryButton>
          </div>
        </form>
      </div>
    </div>
  );
};
