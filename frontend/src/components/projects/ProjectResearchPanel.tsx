/**
 * The question is always submitted with this panel's project id.
 * A project change drops any answer that belonged to the previous project.
 */
import React, { useEffect, useRef, useState } from 'react';
import { Send, RotateCcw, AlertTriangle, Info } from 'lucide-react';
import { ResearchProject } from '../../types/project';
import {
  Citation,
  ResearchDepth,
  ResearchQueryResponse,
} from '../../types/research';
import {
  friendlyResearchError,
  queryResearch,
  researchIdFromError,
  retryResearch,
} from '../../services/research.service';
import { ApiError } from '../../services/api';
import { shortcutLabel } from '../../lib/shortcuts';
import { SafeMarkdown } from '../common/SafeMarkdown';
import { CitationPanel } from '../research/CitationPanel';
import { ModelControlBar } from '../research/ModelControlBar';
import { PrimaryButton } from '../common/PrimaryButton';
import { LoadingOrb } from '../common/LoadingOrb';

interface ProjectResearchPanelProps {
  project: ResearchProject;
  isArchived: boolean;
  /** Documents ready to answer from. Leave undefined when unknown. */
  readyCount?: number;
  preparingCount?: number;
  /** Opens a run's progress page (used after "Try again"). */
  onOpenRun?: (researchId: string) => void;
}

type ResearchState = 'idle' | 'submitting' | 'complete' | 'failed';

const MAX_QUESTION_LENGTH = 2000;

export const ProjectResearchPanel: React.FC<ProjectResearchPanelProps> = ({
  project,
  isArchived,
  readyCount,
  preparingCount = 0,
  onOpenRun,
}) => {
  const [question, setQuestion] = useState('');
  const [researchDepth, setResearchDepth] = useState<ResearchDepth>('standard');
  const [preferredProvider, setPreferredProvider] = useState<string | null>(null);
  const [modelOverride, setModelOverride] = useState<string | null>(null);
  const [localFallbackEnabled, setLocalFallbackEnabled] = useState<boolean | undefined>(undefined);
  const [researchState, setResearchState] = useState<ResearchState>('idle');
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [result, setResult] = useState<ResearchQueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedCitationId, setSelectedCitationId] = useState<string | null>(null);
  // The research item a failed question created. Asking again (edited or
  // not) runs that same item again instead of adding a duplicate.
  const [failedResearchId, setFailedResearchId] = useState<string | null>(null);
  const inFlight = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Track active project id and request epoch so stale responses after a project switch are ignored
  const activeProjectIdRef = useRef(project.id);
  const submittedProjectIdRef = useRef<string | null>(null);
  const requestEpochRef = useRef(0);

  // When project changes, invalidate in-flight work and clear previous results
  useEffect(() => {
    activeProjectIdRef.current = project.id;
    requestEpochRef.current += 1;
    submittedProjectIdRef.current = null;
    setResult(null);
    setError(null);
    setResearchState('idle');
    setSelectedCitationId(null);
    setFailedResearchId(null);
  }, [project.id]);

  useEffect(() => {
    return () => {
      requestEpochRef.current += 1;
      submittedProjectIdRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (researchState !== 'submitting') {
      setElapsedSeconds(0);
      return;
    }
    const started = Date.now();
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - started) / 1000));
    }, 500);
    return () => window.clearInterval(timer);
  }, [researchState]);

  const noReadyDocuments = readyCount === 0;
  const isDisabled =
    isArchived ||
    noReadyDocuments ||
    researchState === 'submitting' ||
    !question.trim() ||
    question.trim().length > MAX_QUESTION_LENGTH;

  const openRun = (researchId: string) => {
    if (onOpenRun) onOpenRun(researchId);
    else window.location.assign(`/research/${researchId}/progress`);
  };

  const runOptions = () => ({
    researchDepth,
    ...(preferredProvider ? { preferredProvider } : {}),
    ...(modelOverride ? { modelOverride } : {}),
    ...(localFallbackEnabled !== undefined ? { localFallbackEnabled } : {}),
  });

  const retryFailed = async (researchId: string) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setResearchState('submitting');
    setError(null);
    try {
      await retryResearch(researchId, { query: question.trim(), ...runOptions() });
      openRun(researchId);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        openRun(researchId);
        return;
      }
      setError(friendlyResearchError(err, 'This question couldn’t be asked again. Please try once more.'));
      setResearchState('failed');
    } finally {
      inFlight.current = false;
    }
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (isDisabled || inFlight.current) return;
    if (failedResearchId) {
      await retryFailed(failedResearchId);
      return;
    }
    inFlight.current = true;

    const currentProjectId = project.id;
    const submitEpoch = requestEpochRef.current + 1;
    requestEpochRef.current = submitEpoch;
    submittedProjectIdRef.current = currentProjectId;

    const isStaleSubmission = () =>
      activeProjectIdRef.current !== currentProjectId ||
      submittedProjectIdRef.current !== currentProjectId ||
      requestEpochRef.current !== submitEpoch;

    setResearchState('submitting');
    setError(null);
    setResult(null);
    setSelectedCitationId(null);

    try {
      const response = await queryResearch({
        query: question.trim(),
        projectId: currentProjectId,
        ...runOptions(),
      });

      // Guard: if project changed or reset while request was in flight, discard result
      if (isStaleSubmission()) return;

      setResult(response);
      setResearchState('complete');
    } catch (err) {
      if (isStaleSubmission()) return;
      const researchId = researchIdFromError(err);
      if (err instanceof ApiError && err.status === 409 && researchId) {
        // The same question is already running; follow that run.
        openRun(researchId);
        return;
      }
      setFailedResearchId(researchId);
      setError(friendlyResearchError(err, 'Research failed. Please try again.'));
      setResearchState('failed');
    } finally {
      inFlight.current = false;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      void handleSubmit();
    }
  };

  const handleReset = () => {
    requestEpochRef.current += 1;
    submittedProjectIdRef.current = null;
    setResearchState('idle');
    setResult(null);
    setError(null);
    setQuestion('');
    setSelectedCitationId(null);
    setFailedResearchId(null);
  };

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-line bg-panel p-4 shadow-xs sm:p-5">
        <p className="mb-3 text-xs text-ink-muted">
          {noReadyDocuments && !isArchived
            ? preparingCount > 0
              ? 'Your documents are almost ready. You can ask as soon as one is ready.'
              : 'Upload a document to this project to start asking questions.'
            : <>Answers come only from documents in <span className="font-medium text-ink-soft">{project.name}</span>.</>}
        </p>

        {isArchived ? (
          <div className="flex items-start gap-2.5 rounded-lg border border-warning-line bg-warning-soft px-4 py-3 text-[13px] text-warning">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            <p>Research is disabled for archived projects.</p>
          </div>
        ) : (
          <form onSubmit={(e) => void handleSubmit(e)} className="space-y-3">
            <div>
              <label
                htmlFor="research-question"
                className="field-label"
              >
                Question
              </label>
              <textarea
                ref={textareaRef}
                id="research-question"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask something these documents can answer"
                rows={3}
                maxLength={MAX_QUESTION_LENGTH}
                disabled={researchState === 'submitting'}
                className="field resize-none"
              />
              <div className="mt-1.5 flex items-center justify-between text-xs text-ink-muted">
                <span>Press <kbd className="rounded border border-line bg-subtle px-1 font-sans text-[10.5px]">{shortcutLabel('Enter')}</kbd> to submit</span>
                <span
                  className={
                    question.length > MAX_QUESTION_LENGTH * 0.9
                      ? 'text-warning'
                      : ''
                  }
                >
                  {question.length}/{MAX_QUESTION_LENGTH}
                </span>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2">
                {(researchState === 'complete' || researchState === 'failed') && (
                  <button
                    type="button"
                    onClick={handleReset}
                    className="inline-flex items-center gap-1.5 text-xs text-ink-soft hover:text-ink transition-colors"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    New question
                  </button>
                )}
                <ModelControlBar
                  depth={researchDepth}
                  onDepthChange={setResearchDepth}
                  preferredProvider={preferredProvider}
                  onPreferredProviderChange={setPreferredProvider}
                  modelOverride={modelOverride}
                  onModelOverrideChange={setModelOverride}
                  localFallbackEnabled={localFallbackEnabled}
                  onLocalFallbackChange={setLocalFallbackEnabled}
                  disabled={researchState === 'submitting'}
                  menuPlacement="down"
                />
              </div>
              <div className="ml-auto">
                <PrimaryButton
                  type="submit"
                  disabled={isDisabled}
                  isLoading={researchState === 'submitting'}
                >
                  <Send className="h-4 w-4" />
                  {researchState === 'submitting' ? 'Researching…' : 'Research'}
                </PrimaryButton>
              </div>
            </div>
          </form>
        )}
      </div>

      {researchState === 'submitting' && (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-line bg-panel p-8 text-center">
          <LoadingOrb size={28} />
          <p className="text-sm font-medium text-ink">
            Researching your question…{elapsedSeconds > 0 ? ` (${elapsedSeconds}s)` : ''}
          </p>
          <p className="text-xs text-ink-muted max-w-xs">
            {researchDepth === 'quick'
              ? 'Fast retrieval and synthesis from top passages.'
              : 'Reading through your documents and writing an answer with citations.'}
          </p>
        </div>
      )}

      {researchState === 'failed' && error && (
        <div role="alert" className="rounded-lg border border-danger-line bg-panel shadow-xs">
          <div className="flex items-start gap-3 p-4">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-danger" />
            <div className="min-w-0">
              <p className="text-[13px] font-medium text-ink">No answer this time</p>
              <p className="mt-1 text-[13px] leading-relaxed text-ink-soft">{error}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-3">
            <button
              type="button"
              className="btn-primary"
              disabled={!question.trim()}
              onClick={() => (failedResearchId ? void retryFailed(failedResearchId) : void handleSubmit())}
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Try again
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => textareaRef.current?.focus()}
            >
              Edit question
            </button>
            {failedResearchId && (
              <span className="w-full text-xs text-ink-muted sm:ml-auto sm:w-auto">
                Asking again reuses the same history item.
              </span>
            )}
          </div>
        </div>
      )}

      {researchState === 'complete' && result && (
        <ResearchResult
          result={result}
          selectedCitationId={selectedCitationId}
          onSelectCitation={setSelectedCitationId}
        />
      )}
    </div>
  );
};


interface ResearchResultProps {
  result: ResearchQueryResponse;
  selectedCitationId: string | null;
  onSelectCitation: (id: string | null) => void;
}

const ResearchResult: React.FC<ResearchResultProps> = ({
  result,
  selectedCitationId,
  onSelectCitation,
}) => {
  return (
    <div className="space-y-4">
      {result.insufficientEvidence && (
        <div className="flex items-start gap-2.5 rounded-lg border border-info-line bg-info-soft px-4 py-3 text-[13px] text-info">
          <Info className="w-4 h-4 shrink-0 mt-0.5" />
          <p>
            <strong>Limited evidence:</strong> The answer below is based on
            insufficient evidence from this project's documents. Results may be
            incomplete.
          </p>
        </div>
      )}

      <div className="rounded-lg border border-line bg-panel p-5 shadow-xs sm:p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-ink">Answer</h3>
          <span className="text-xs tabular-nums text-ink-muted">
            {result.evidenceCount} evidence piece
            {result.evidenceCount !== 1 ? 's' : ''} ·{' '}
            {result.citations.length} citation
            {result.citations.length !== 1 ? 's' : ''}
          </span>
        </div>
        <SafeMarkdown content={result.answer} />

        {result.citations.length > 0 && (
          <div className="mt-4 pt-4 border-t border-line">
            <p className="eyebrow mb-2">
              Citations
            </p>
            <div className="flex flex-wrap gap-2">
              {result.citations.map((citation) => (
                <button
                  key={citation.citationId}
                  type="button"
                  aria-pressed={selectedCitationId === citation.citationId}
                  aria-label={`View citation: ${citation.paperTitle ?? citation.citationId}`}
                  onClick={() =>
                    onSelectCitation(
                      selectedCitationId === citation.citationId
                        ? null
                        : citation.citationId
                    )
                  }
                  className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium transition-colors ${
                    selectedCitationId === citation.citationId
                      ? 'border-accent bg-accent-soft text-accent'
                      : 'border-line bg-panel text-ink-soft hover:border-line-strong hover:text-ink'
                  }`}
                >
                  <InlineCitationLabel citation={citation} />
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {selectedCitationId && (
        <CitationPanel
          citation={
            result.citations.find((c) => c.citationId === selectedCitationId) ??
            null
          }
          onClose={() => onSelectCitation(null)}
        />
      )}
    </div>
  );
};

const InlineCitationLabel: React.FC<{ citation: Citation }> = ({
  citation,
}) => {
  if (citation.paperTitle) {
    const short =
      citation.paperTitle.length > 35
        ? citation.paperTitle.slice(0, 32) + '…'
        : citation.paperTitle;
    return (
      <>
        <span>{short}</span>
        {citation.page && citation.page > 0 && (
          <span className="tabular-nums text-ink-muted">p. {citation.page}</span>
        )}
      </>
    );
  }
  return <span>Source</span>;
};
