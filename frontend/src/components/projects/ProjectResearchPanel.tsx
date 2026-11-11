/**
 * The question is always submitted with this panel's project id.
 * A project change drops any answer that belonged to the previous project.
 */
import React, { useEffect, useRef, useState } from 'react';
import { Send, RotateCcw, AlertTriangle, Info } from 'lucide-react';
import { ResearchProject } from '../../types/project';
import { ResearchQueryResponse, Citation } from '../../types/research';
import { queryResearch, getResearchErrorMessage } from '../../services/research.service';
import { SafeMarkdown } from '../common/SafeMarkdown';
import { CitationPanel } from '../research/CitationPanel';
import { PrimaryButton } from '../common/PrimaryButton';
import { LoadingOrb } from '../common/LoadingOrb';

interface ProjectResearchPanelProps {
  project: ResearchProject;
  isArchived: boolean;
}

type ResearchState = 'idle' | 'submitting' | 'complete' | 'failed';

const MAX_QUESTION_LENGTH = 2000;

export const ProjectResearchPanel: React.FC<ProjectResearchPanelProps> = ({
  project,
  isArchived,
}) => {
  const [question, setQuestion] = useState('');
  const [researchState, setResearchState] = useState<ResearchState>('idle');
  const [result, setResult] = useState<ResearchQueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedCitationId, setSelectedCitationId] = useState<string | null>(null);

  // Track the project ID at submission time to guard against stale results
  const submittedProjectIdRef = useRef<string | null>(null);

  // When project changes, clear previous results
  useEffect(() => {
    setResult(null);
    setError(null);
    setResearchState('idle');
    setSelectedCitationId(null);
  }, [project.id]);

  const isDisabled =
    isArchived ||
    researchState === 'submitting' ||
    !question.trim() ||
    question.trim().length > MAX_QUESTION_LENGTH;

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (isDisabled) return;

    const currentProjectId = project.id;
    submittedProjectIdRef.current = currentProjectId;

    setResearchState('submitting');
    setError(null);
    setResult(null);
    setSelectedCitationId(null);

    try {
      const response = await queryResearch({
        query: question.trim(),
        projectId: currentProjectId,
      });

      // Guard: if project changed while request was in flight, discard result
      if (submittedProjectIdRef.current !== currentProjectId) return;

      setResult(response);
      setResearchState('complete');
    } catch (err) {
      if (submittedProjectIdRef.current !== currentProjectId) return;
      setError(getResearchErrorMessage(err, 'Research failed. Please try again.'));
      setResearchState('failed');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      void handleSubmit();
    }
  };

  const handleReset = () => {
    setResearchState('idle');
    setResult(null);
    setError(null);
    setQuestion('');
    setSelectedCitationId(null);
  };

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-line bg-panel p-4 shadow-xs sm:p-5">
        <p className="mb-3 text-xs text-ink-muted">
          Only documents in <span className="font-medium text-ink-soft">{project.name}</span> are searched.
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
                <span>Press <kbd className="rounded border border-line bg-subtle px-1 font-mono text-[10.5px]">⌘ Enter</kbd> to submit</span>
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

            <div className="flex items-center justify-between">
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
            Researching your question…
          </p>
          <p className="text-xs text-ink-muted max-w-xs">
            Searching indexed documents, reranking evidence, and generating a
            grounded answer.
          </p>
        </div>
      )}

      {researchState === 'failed' && error && (
        <div role="alert" className="flex items-start gap-3 rounded-lg border border-danger-line bg-danger-soft p-4">
          <AlertTriangle className="w-5 h-5 text-danger shrink-0 mt-0.5" />
          <div>
            <p className="text-[13px] font-medium text-danger">
              Research failed
            </p>
            <p className="text-xs text-ink-soft mt-1">{error}</p>
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
  return <span className="font-mono text-[10px]">[{citation.chunkId.slice(0, 8)}]</span>;
};
