/**
 * ProjectResearchPanel: Project-scoped research composer and result display.
 *
 * Critical safety rule: research submissions always include the projectId
 * from props (never from stale global state). When the project changes,
 * any in-flight result is discarded.
 *
 * States:
 *  idle → submitting → complete | failed
 *
 * Shows answer with SafeMarkdown + citation chips + evidence drawer.
 * Insufficient evidence state is clearly communicated.
 */
import React, { useEffect, useRef, useState } from 'react';
import { Send, RotateCcw, AlertTriangle, Info } from 'lucide-react';
import { ResearchProject } from '../../types/project';
import { ResearchQueryResponse, Citation } from '../../types/research';
import { queryResearch, getResearchErrorMessage } from '../../services/research.service';
import { SafeMarkdown } from '../common/SafeMarkdown';
import { CitationPanel } from '../research/CitationPanel';
import { PrimaryButton } from '../common/PrimaryButton';

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
      {/* Composer */}
      <div className="bg-white border border-[#e5e7e4] rounded-xl p-5">
        <div className="flex items-center gap-2 mb-3">
          <p className="text-xs font-semibold text-[#929792] uppercase tracking-wider">
            Researching within
          </p>
          <span className="text-xs font-semibold text-[#163328] bg-[#f1f6f3] border border-[#d8e5df] px-2 py-0.5 rounded">
            {project.name}
          </span>
        </div>

        {isArchived ? (
          <div className="flex items-start gap-2.5 text-sm text-[#b45309] bg-[#fef3c7]/60 border border-[#fde68a] rounded-lg px-4 py-3">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            <p>Research is disabled for archived projects.</p>
          </div>
        ) : (
          <form onSubmit={(e) => void handleSubmit(e)} className="space-y-3">
            <div>
              <label
                htmlFor="research-question"
                className="block text-xs font-medium text-[#181a18] mb-1.5"
              >
                Research question
              </label>
              <textarea
                id="research-question"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="What would you like to investigate within this project's documents?"
                rows={3}
                maxLength={MAX_QUESTION_LENGTH}
                disabled={researchState === 'submitting'}
                className="w-full border border-[#e5e7e4] rounded-lg px-3 py-2.5 text-sm text-[#181a18] placeholder:text-[#929792] focus:outline-none focus:ring-1 focus:ring-[#163328] focus:border-[#163328] transition-colors resize-none disabled:bg-[#fafaf8] disabled:text-[#929792]"
              />
              <div className="mt-1 flex items-center justify-between text-[11px] text-[#929792]">
                <span>⌘ + Enter to submit</span>
                <span
                  className={
                    question.length > MAX_QUESTION_LENGTH * 0.9
                      ? 'text-[#b45309]'
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
                  className="inline-flex items-center gap-1.5 text-xs text-[#6b706c] hover:text-[#181a18] transition-colors"
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
                  className="gap-1.5"
                >
                  <Send className="w-3.5 h-3.5" />
                  {researchState === 'submitting' ? 'Researching…' : 'Research'}
                </PrimaryButton>
              </div>
            </div>
          </form>
        )}
      </div>

      {/* Submitting state */}
      {researchState === 'submitting' && (
        <div className="bg-white border border-[#e5e7e4] rounded-xl p-8 flex flex-col items-center gap-3 text-center">
          <span className="w-8 h-8 border-2 border-[#163328]/20 border-t-[#163328] rounded-full animate-spin block" />
          <p className="text-sm font-medium text-[#181a18]">
            Researching your question…
          </p>
          <p className="text-xs text-[#929792] max-w-xs">
            Searching indexed documents, reranking evidence, and generating a
            grounded answer.
          </p>
        </div>
      )}

      {/* Error state */}
      {researchState === 'failed' && error && (
        <div className="bg-white border border-[#fecaca] rounded-xl p-5 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-[#b91c1c] shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-[#b91c1c]">
              Research failed
            </p>
            <p className="text-xs text-[#6b706c] mt-1">{error}</p>
          </div>
        </div>
      )}

      {/* Result */}
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

// ─── ResearchResult ──────────────────────────────────────────────────────────

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
      {/* Insufficient evidence warning */}
      {result.insufficientEvidence && (
        <div className="flex items-start gap-2.5 text-sm text-[#0369a1] bg-[#e0f2fe]/50 border border-[#bae6fd] rounded-xl px-4 py-3">
          <Info className="w-4 h-4 shrink-0 mt-0.5" />
          <p>
            <strong>Limited evidence:</strong> The answer below is based on
            insufficient evidence from this project's documents. Results may be
            incomplete.
          </p>
        </div>
      )}

      {/* Answer */}
      <div className="bg-white border border-[#e5e7e4] rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-[#181a18]">Answer</h3>
          <span className="text-[10px] text-[#929792]">
            {result.evidenceCount} evidence piece
            {result.evidenceCount !== 1 ? 's' : ''} ·{' '}
            {result.citations.length} citation
            {result.citations.length !== 1 ? 's' : ''}
          </span>
        </div>
        <SafeMarkdown content={result.answer} />

        {/* Inline citations */}
        {result.citations.length > 0 && (
          <div className="mt-4 pt-4 border-t border-[#f5f5f2]">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[#929792] mb-2">
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
                  className={`inline-flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1 rounded-md border transition-all duration-100 ${
                    selectedCitationId === citation.citationId
                      ? 'bg-[#163328] text-white border-[#163328]'
                      : 'text-[#163328] bg-[#f1f6f3] border-[#d8e5df] hover:bg-[#e4eee7]'
                  }`}
                >
                  <InlineCitationLabel citation={citation} />
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Citation detail panel */}
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
        <span className="font-mono text-[10px]">[{citation.chunkId.slice(0, 6)}]</span>
        <span>{short}</span>
        {citation.page && citation.page > 0 && (
          <span className="text-[10px] opacity-70">p. {citation.page}</span>
        )}
      </>
    );
  }
  return <span className="font-mono text-[10px]">[{citation.chunkId.slice(0, 8)}]</span>;
};
