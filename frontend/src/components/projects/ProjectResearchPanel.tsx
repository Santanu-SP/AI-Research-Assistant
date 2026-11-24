/**
 * The question is always submitted with this panel's project id.
 * A project change drops any answer that belonged to the previous project.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Send, RotateCcw, AlertTriangle, Info, Clock, Globe } from 'lucide-react';
import { ResearchProject } from '../../types/project';
import {
  Citation,
  ResearchDepth,
  ResearchQueryResponse,
  ResearchResponse,
} from '../../types/research';
import {
  friendlyResearchError,
  queryResearch,
  researchIdFromError,
  retryResearch,
  startResearchJob,
} from '../../services/research.service';
import { getDiscoveryErrorMessage } from '../../services/discovery.service';
import * as researchServiceNs from '../../services/research.service';
import { ApiError, apiErrorCode } from '../../services/api';
import { shortcutLabel } from '../../lib/shortcuts';
import { SafeMarkdown } from '../common/SafeMarkdown';
import { CitationPanel } from '../research/CitationPanel';
import { ModelControlBar } from '../research/ModelControlBar';
import { PrimaryButton } from '../common/PrimaryButton';
import { LoadingOrb } from '../common/LoadingOrb';
import { getDefaultModel } from '../../lib/defaultModel';
import { loadFindOnline, saveFindOnline } from '../../lib/projectDiscovery';

interface ProjectResearchPanelProps {
  project: ResearchProject;
  isArchived: boolean;
  readOnly?: boolean;
  /** Documents ready to answer from. Leave undefined when unknown. */
  readyCount?: number;
  preparingCount?: number;
  researchSyncSignal?: number;
  onActivity?: (activity: 'idle' | 'asking') => void;
  /** Opens a run's progress page (used after "Try again"). */
  onOpenRun?: (researchId: string) => void;
}

type ResearchState = 'idle' | 'submitting' | 'complete' | 'failed';

const MAX_QUESTION_LENGTH = 2000;

export const ProjectResearchPanel: React.FC<ProjectResearchPanelProps> = ({
  project,
  isArchived,
  readOnly = false,
  readyCount,
  preparingCount = 0,
  researchSyncSignal = 0,
  onActivity,
  onOpenRun,
}) => {
  const [question, setQuestion] = useState('');
  const [researchDepth, setResearchDepth] = useState<ResearchDepth>('standard');
  const [preferredProvider, setPreferredProvider] = useState<string | null>(() => getDefaultModel().provider);
  const [modelOverride, setModelOverride] = useState<string | null>(() => getDefaultModel().model);
  const [localFallbackEnabled, setLocalFallbackEnabled] = useState<boolean | undefined>(undefined);
  // "Also find sources online": off by default, remembered per project.
  const [findOnline, setFindOnline] = useState(() => loadFindOnline(project.id));
  const [researchState, setResearchState] = useState<ResearchState>('idle');
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [result, setResult] = useState<ResearchQueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedCitationId, setSelectedCitationId] = useState<string | null>(null);
  // The research item a failed question created. Asking again (edited or
  // not) runs that same item again instead of adding a duplicate.
  const [failedResearchId, setFailedResearchId] = useState<string | null>(null);
  const [recentRuns, setRecentRuns] = useState<ResearchResponse[]>([]);
  const inFlight = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const loadRecentRuns = useCallback(async () => {
    const keys = Object.keys(researchServiceNs);
    const listFn = keys.includes('listResearch')
      ? researchServiceNs.listResearch
      : keys.includes('researchService')
        ? researchServiceNs.researchService?.listResearch
        : undefined;
    if (typeof listFn !== 'function') return;
    try {
      const res = await listFn({
        projectId: project.id,
        limit: 10,
      });
      setRecentRuns(res.items);
    } catch {
      // Non-critical list; keep UI responsive even if unreachable.
    }
  }, [project.id]);

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
    setRecentRuns([]);
    setFindOnline(loadFindOnline(project.id));
  }, [project.id]);

  const toggleFindOnline = () => {
    const next = !findOnline;
    setFindOnline(next);
    saveFindOnline(project.id, next);
  };

  useEffect(() => {
    void loadRecentRuns();
  }, [loadRecentRuns, researchSyncSignal]);

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
  const effectiveReadOnly = isArchived || readOnly;
  // With "find sources online" on, an empty project can still be asked.
  const isDisabled =
    effectiveReadOnly ||
    (noReadyDocuments && !findOnline) ||
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
    onActivity?.('asking');
    setError(null);
    setResult(null);
    setSelectedCitationId(null);

    if (findOnline) {
      // Finding and reading sources takes a while, so this runs in the
      // background and the progress page shows each step.
      try {
        const research = await startResearchJob({
          query: question.trim(),
          projectId: currentProjectId,
          autoDiscover: true,
          discoveryScope: 'all',
          ...runOptions(),
        });
        if (isStaleSubmission()) return;
        openRun(research.id);
      } catch (err) {
        if (isStaleSubmission()) return;
        const researchId = researchIdFromError(err);
        if (err instanceof ApiError && err.status === 409 && researchId) {
          openRun(researchId);
          return;
        }
        const code = apiErrorCode(err);
        setError(
          code === 'discovery_disabled' || code === 'no_discoverable_sources'
            ? getDiscoveryErrorMessage(err, 'Sources online could not be searched.')
            : friendlyResearchError(err, 'Research could not be started. Please try again.'),
        );
        setResearchState('failed');
      } finally {
        inFlight.current = false;
        onActivity?.('idle');
      }
      return;
    }

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
      void loadRecentRuns();
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
      onActivity?.('idle');
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
          {findOnline && !effectiveReadOnly
            ? <>Answers use files in <span className="font-medium text-ink-soft">{project.name}</span> plus trusted sources found online. New sources are saved to this project&rsquo;s Files.</>
            : noReadyDocuments && !isArchived
              ? preparingCount > 0
                ? 'Your files are almost ready. You can ask as soon as one is ready.'
                : effectiveReadOnly
                  ? 'This project has no files yet.'
                  : 'Upload a file, or turn on “Also find sources online”, to start asking questions.'
              : <>Answers come only from files in <span className="font-medium text-ink-soft">{project.name}</span>.</>}
        </p>

        {isArchived ? (
          <div className="flex items-start gap-2.5 rounded-lg border border-warning-line bg-warning-soft px-4 py-3 text-[13px] text-warning">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            <p>Research is disabled for archived projects.</p>
          </div>
        ) : effectiveReadOnly ? (
          <div className="flex items-start gap-2.5 rounded-lg border border-line bg-subtle/40 px-4 py-3 text-[13px] text-ink-soft">
            <Info className="w-4 h-4 mt-0.5 shrink-0 text-ink-muted" />
            <p>View-only collaborators can read existing research reports and follow-ups, but cannot start new research or add sources found online.</p>
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
                placeholder={findOnline ? 'Ask anything; sources will be found online' : 'Ask something these files can answer'}
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

            <div className="flex items-start justify-between gap-3 rounded-lg border border-line bg-canvas/70 px-3 py-2.5">
              <div className="min-w-0">
                <p className="flex items-center gap-1.5 text-xs font-medium text-ink">
                  <Globe className="h-3.5 w-3.5 shrink-0 text-accent" />
                  <span id="find-online-label">Also find sources online</span>
                </p>
                <p className="mt-0.5 text-[11px] leading-snug text-ink-muted">
                  Searches OpenAlex, Crossref, arXiv, Wikipedia and trusted news, then adds the best new sources to this project&rsquo;s Files.
                </p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={findOnline}
                aria-labelledby="find-online-label"
                disabled={researchState === 'submitting'}
                onClick={toggleFindOnline}
                className={`relative mt-0.5 inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${findOnline
                  ? 'border-accent bg-solid'
                  : 'border-line-strong bg-subtle'
                  }`}
              >
                <span
                  className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow-xs transition-transform ${findOnline ? 'translate-x-4' : 'translate-x-0.5'}`}
                />
              </button>
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
            {findOnline
              ? 'Starting the search for sources online…'
              : researchDepth === 'quick'
              ? 'Fast retrieval and synthesis from top passages.'
              : 'Reading through your files and writing an answer with citations.'}
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

      {recentRuns.length > 0 && (
        <section
          aria-label="Recent project research"
          className="rounded-lg border border-line bg-panel shadow-xs overflow-hidden"
        >
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
              Shared project research ({recentRuns.length})
            </h3>
          </div>
          <div className="divide-y divide-line">
            {recentRuns.map((run) => {
              const targetPath =
                run.status === 'completed'
                  ? `/research/${run.id}`
                  : `/research/${run.id}/progress`;
              return (
                <Link
                  key={run.id}
                  to={targetPath}
                  className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm transition-colors hover:bg-subtle/60"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium text-ink">{run.title}</p>
                    <p className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-muted">
                      {run.ownerName ? <span>by {run.ownerName}</span> : null}
                      {run.ownerName ? <span aria-hidden="true">·</span> : null}
                      <span className="capitalize">{run.status}</span>
                    </p>
                  </div>
                  <span className="inline-flex shrink-0 items-center gap-1 text-xs text-ink-muted">
                    <Clock className="h-3 w-3" />
                    {new Date(run.updatedAt).toLocaleDateString(undefined, {
                      month: 'short',
                      day: 'numeric',
                    })}
                  </span>
                </Link>
              );
            })}
          </div>
        </section>
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
            insufficient evidence from this project's files. Results may be
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
        <SafeMarkdown
          content={result.answer}
          renderCitation={(sourceNumber, key) => {
            const citationId = `S${sourceNumber}`;
            if (!result.citations.some((c) => c.citationId === citationId)) {
              return null;
            }
            return (
              <button
                key={key}
                type="button"
                aria-label={`View citation ${citationId}`}
                onClick={() =>
                  onSelectCitation(selectedCitationId === citationId ? null : citationId)
                }
                className="mx-0.5 inline-flex h-[18px] min-w-[18px] -translate-y-px items-center justify-center rounded bg-accent-soft px-1 align-middle font-mono text-[11px] font-medium leading-none text-accent hover:bg-accent-muted"
              >
                {sourceNumber}
              </button>
            );
          }}
        />

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
                  className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium transition-colors ${selectedCitationId === citation.citationId
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
