import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, ArrowRight, Cpu, PauseCircle, PencilLine, RotateCcw } from 'lucide-react';
import { ResearchProgressResponse } from '../../types/progress';
import { friendlyResearchError, retryResearch } from '../../services/research.service';
import { ApiError } from '../../services/api';
import { describeModelFailure } from '../../lib/modelErrors';
import { ResearchDepth } from '../../types/research';
import { ModelControlBar } from './ModelControlBar';

interface RunRecoveryProps {
  progress: ResearchProgressResponse;
  /** Called once the run has been restarted (or is already running again). */
  onRestarted: () => void;
}

const MAX_QUESTION_LENGTH = 2000;

const explanation = (progress: ResearchProgressResponse): string => {
  const preparing = progress.documentsPreparing ?? 0;
  switch (progress.failureReason) {
    case 'model_unavailable':
      return 'The model didn’t reply, so no answer could be written. This is usually temporary: the model may be busy, switched off, or not set up yet.';
    case 'quota_reached':
      return 'Today’s shared model requests are used up. Add your own API key or turn on the local model, then try again.';
    case 'no_ready_documents':
      return preparing > 0
        ? 'Your files are still being prepared, so there was nothing to answer from yet. Try again once they’re ready.'
        : 'There are no ready files to answer from yet. Upload a file, then try again.';
    case 'no_discoverable_sources':
      return 'No trusted sources online could be found or read for this question. Try rewording it, or upload a file and try again.';
    case 'discovery_disabled':
      return 'Finding sources online is switched off on this server. Upload a file, then try again.';
    default:
      return 'Something went wrong while the answer was being written. Trying again usually works.';
  }
};

/**
 * Shown in place of a failed run: a plain explanation and ways to recover
 * that keep using this same research item.
 */
export const RunRecovery: React.FC<RunRecoveryProps> = ({ progress, onRestarted }) => {
  const [editing, setEditing] = useState(false);
  const [question, setQuestion] = useState(progress.question);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // "Switch model": the same model picker as the question box, shown inline.
  const [switching, setSwitching] = useState(false);
  const [depth, setDepth] = useState<ResearchDepth>(progress.researchDepth);
  const [preferredProvider, setPreferredProvider] = useState<string | null>(null);
  const [modelOverride, setModelOverride] = useState<string | null>(null);
  const [localFallback, setLocalFallback] = useState<boolean | undefined>(undefined);
  const modelFailure = describeModelFailure(progress);
  const inFlight = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (editing) textareaRef.current?.focus();
  }, [editing]);

  const ready = progress.documentsReady ?? 0;
  const preparing = progress.documentsPreparing ?? 0;
  const isPaused = progress.failureReason === 'paused';
  const documentsHref = progress.projectId ? `/projects/${progress.projectId}?tab=documents` : '/research/new';
  const showDocuments =
    !isPaused && (preparing > 0 || ready === 0 || progress.failureReason === 'no_ready_documents');
  const trimmed = question.trim();

  const restart = async (edited?: string) => {
    if (inFlight.current) return; // ignore double clicks
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      await retryResearch(progress.id, {
        ...(edited && edited !== progress.question ? { query: edited } : {}),
        // Only send model options once the user has picked something new.
        ...(switching
          ? {
              researchDepth: depth,
              preferredProvider,
              modelOverride,
              ...(localFallback !== undefined ? { localFallbackEnabled: localFallback } : {}),
            }
          : {}),
      });
      onRestarted();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        onRestarted();
      } else {
        setError(friendlyResearchError(err, 'This research couldn’t be started again. Please try once more.'));
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  return (
    <section
      aria-labelledby="run-recovery-title"
      className={`mt-5 max-w-3xl rounded-xl border bg-panel shadow-xs ${
        isPaused ? 'border-line' : 'border-danger-line'
      }`}
    >
      <div className="flex gap-3 px-4 py-4 sm:px-5">
        <span
          className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${
            isPaused ? 'bg-subtle text-ink-soft' : 'bg-danger-soft text-danger'
          }`}
        >
          {isPaused ? <PauseCircle className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
        </span>
        <div className="min-w-0 flex-1">
          <h2 id="run-recovery-title" className="text-sm font-medium text-ink">
            {isPaused
              ? 'Research paused'
              : modelFailure
                ? modelFailure.title
                : 'This run stopped before an answer was written'}
          </h2>
          <p className="mt-1 text-[13px] leading-relaxed text-ink-soft">
            {isPaused
              ? 'This run is paused. Edit your question or resume whenever you’re ready.'
              : modelFailure
                ? modelFailure.detail
                : explanation(progress)}
          </p>
          {preparing > 0 && (
            <p className="mt-2 text-[13px] text-ink-soft">
              {preparing} file{preparing === 1 ? ' is' : 's are'} still being prepared.{' '}
              <Link to={documentsHref} className="font-medium text-accent hover:underline">
                Check files
              </Link>
            </p>
          )}
        </div>
      </div>

      {switching && !editing && (
        <div className="border-t border-line px-4 py-3 sm:px-5" aria-label="Pick a model for the next try">
          <p className="mb-2 text-xs text-ink-muted">Pick a model, then press Try again.</p>
          <ModelControlBar
            depth={depth}
            onDepthChange={setDepth}
            preferredProvider={preferredProvider}
            onPreferredProviderChange={setPreferredProvider}
            modelOverride={modelOverride}
            onModelOverrideChange={setModelOverride}
            localFallbackEnabled={localFallback}
            onLocalFallbackChange={setLocalFallback}
            disabled={busy}
            menuPlacement="down"
            openModelsOnMount
          />
        </div>
      )}

      {editing ? (
        <form
          className="border-t border-line px-4 py-4 sm:px-5"
          onSubmit={(event) => {
            event.preventDefault();
            if (trimmed) void restart(trimmed);
          }}
        >
          <label htmlFor="recovery-question" className="field-label">
            Question
          </label>
          <textarea
            ref={textareaRef}
            id="recovery-question"
            rows={3}
            maxLength={MAX_QUESTION_LENGTH}
            value={question}
            disabled={busy}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                event.preventDefault();
                if (trimmed) void restart(trimmed);
              }
              if (event.key === 'Escape') setEditing(false);
            }}
            className="field resize-none"
          />
          <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => {
                setEditing(false);
                setQuestion(progress.question);
              }}
              disabled={busy}
              className="btn-secondary"
            >
              Cancel
            </button>
            <button type="submit" disabled={busy || !trimmed} className="btn-primary">
              <RotateCcw className="h-3.5 w-3.5" />
              {busy ? 'Starting…' : 'Ask edited question'}
            </button>
          </div>
        </form>
      ) : (
        <div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-3 sm:px-5">
          <button type="button" onClick={() => void restart()} disabled={busy} className="btn-primary">
            <RotateCcw className={`h-3.5 w-3.5 ${busy ? 'animate-spin [animation-direction:reverse]' : ''}`} />
            {busy ? 'Starting…' : isPaused ? 'Resume' : 'Try again'}
          </button>
          {!isPaused &&
            (modelFailure || progress.failureReason === 'model_unavailable' || progress.failureReason === 'quota_reached') &&
            !switching && (
              <button type="button" onClick={() => setSwitching(true)} disabled={busy} className="btn-secondary">
                <Cpu className="h-3.5 w-3.5" />
                Switch model
              </button>
            )}
          <button type="button" onClick={() => setEditing(true)} disabled={busy} className="btn-secondary">
            <PencilLine className="h-3.5 w-3.5" />
            Edit question
          </button>
          {showDocuments && (
            <Link to={documentsHref} className="btn-ghost">
              {preparing > 0 ? 'See file status' : 'Add files'}
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          )}
          <span className="w-full text-xs text-ink-muted sm:ml-auto sm:w-auto">
            Runs again here, without adding a new item to your history.
          </span>
        </div>
      )}

      {error && (
        <p role="alert" className="border-t border-line px-4 py-3 text-[13px] text-danger sm:px-5">
          {error}
        </p>
      )}
    </section>
  );
};
