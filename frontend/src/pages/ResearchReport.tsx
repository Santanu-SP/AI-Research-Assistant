import React, { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { TopBar } from '../components/layout/TopBar';
import { StatusBadge } from '../components/common/StatusBadge';
import { CitationChip } from '../components/research/CitationChip';
import { SafeMarkdown } from '../components/common/SafeMarkdown';
import { SourcesPanel } from '../components/sources/SourcesPanel';
import { CenteredLoadingState } from '../components/common/LoadingState';
import { ErrorState } from '../components/common/ErrorState';
import { PrimaryButton } from '../components/common/PrimaryButton';
import { ModelControlBar } from '../components/research/ModelControlBar';
import { PresenceBar } from '../components/collaboration/PresenceBar';
import { ShareDialog } from '../components/collaboration/ShareDialog';
import { useAuth } from '../app/AuthContext';
import { useRealtimeRoom } from '../hooks/useRealtimeRoom';
import { reportService } from '../services/report.service';
import { editResearchQuestion, friendlyResearchError } from '../services/research.service';
import { useResearchHistory } from '../app/ResearchHistoryContext';
import {
  ReportFollowupResponse,
  ResearchReportResponse,
  SourceResponse,
} from '../types/report';
import type { RealtimeEventEnvelope } from '../types/collaboration';
import { ResearchDepth } from '../types/research';
import { getDefaultModel } from '../lib/defaultModel';
import { shortcutLabel } from '../lib/shortcuts';
import { prettyModelName, redactSecrets } from '../lib/modelErrors';
import { ApiError, apiErrorMessage } from '../services/api';
import {
  BookOpen,
  Check,
  ChevronRight,
  Clock,
  Download,
  Link2,
  MessageSquarePlus,
  PencilLine,
  RotateCcw,
  Send,
  Sparkles,
  Users,
} from 'lucide-react';

const INLINE_CITATION = /\[S\d+\]/;

const buildReportMarkdown = (
  report: ResearchReportResponse,
  sources: SourceResponse[],
  followups: ReportFollowupResponse[] = [],
): string => {
  let markdown = `# ${report.title}\n\n`;
  if (report.question && report.question.trim() !== report.title.trim()) {
    markdown += `> **Question:** ${report.question}\n\n`;
  }
  markdown += `${report.dossierRef} | ${report.readingTimeMinutes} min read\n\n`;
  const summaryAlreadyInFirstSection =
    report.sections.length > 0 && report.sections[0].content === report.summary;
  if (!summaryAlreadyInFirstSection) {
    markdown += `## Executive Summary\n${report.summary}\n\n`;
  }
  report.sections.forEach((section) => {
    markdown += `## ${section.heading}\n${section.content}\n\n`;
    if (section.quote) {
      markdown += `> "${section.quote}"\n\n`;
    }
  });
  if (followups.length > 0) {
    markdown += `## Follow-up Questions\n\n`;
    followups.forEach((turn) => {
      markdown += `### ${turn.question}\n${turn.answer}\n\n`;
    });
  }
  markdown += `## References\n`;
  sources.forEach((source) => {
    const metadata = [
      source.authors.join(', '),
      source.year ? `(${source.year})` : '',
      source.title ? `"${source.title}"` : '',
      source.publisher || '',
      source.page ? `p. ${source.page}` : '',
    ].filter(Boolean).join(' ');
    markdown += `[S${source.number}] ${metadata}\n`;
  });
  return markdown;
};

export const ResearchReportPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const history = useResearchHistory();
  const reloadHistory = history?.reload;
  const [report, setReport] = useState<ResearchReportResponse | null>(null);
  const [sources, setSources] = useState<SourceResponse[]>([]);
  const [followups, setFollowups] = useState<ReportFollowupResponse[]>([]);
  const [followupQuestion, setFollowupQuestion] = useState('');
  const [followupSubmitting, setFollowupSubmitting] = useState(false);
  const [followupError, setFollowupError] = useState<string | null>(null);
  const [editingQuestion, setEditingQuestion] = useState(false);
  const [draftQuestion, setDraftQuestion] = useState('');
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [researchDepth, setResearchDepth] = useState<ResearchDepth>('quick');
  const [preferredProvider, setPreferredProvider] = useState<string | null>(() => getDefaultModel().provider);
  const [modelOverride, setModelOverride] = useState<string | null>(() => getDefaultModel().model);
  const [localFallbackEnabled, setLocalFallbackEnabled] = useState<boolean | undefined>(undefined);
  const [selectedSourceNumber, setSelectedSourceNumber] = useState<number>(1);
  const [isMobileSourcesOpen, setIsMobileSourcesOpen] = useState(false);
  const [isShareOpen, setIsShareOpen] = useState(false);
  const [copiedShare, setCopiedShare] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const refreshReport = useCallback(() => {
    if (!id) return;
    reportService
      .getResearchReport(id)
      .then((data) => {
        setReport(data.report);
        setSources(data.sources);
        setFollowups(data.followups ?? []);
        if (data.sources.length > 0) {
          setSelectedSourceNumber((prev) =>
            data.sources.some((s) => s.number === prev) ? prev : data.sources[0].number,
          );
        }
      })
      .catch((err) => {
        setError(err instanceof Error ? err : new Error('Unknown error occurred'));
      });
  }, [id]);

  useEffect(() => {
    refreshReport();
  }, [refreshReport]);

  const handleRealtimeEvent = useCallback(
    (event: RealtimeEventEnvelope) => {
      if (event.type === 'followup.created') {
        const payload = event.payload as {
          followup?: ReportFollowupResponse;
          sources?: SourceResponse[];
        };
        if (payload.followup) {
          const incoming = payload.followup;
          setFollowups((prev) =>
            prev.some((item) => item.id === incoming.id)
              ? prev
              : [...prev, incoming].sort((a, b) => a.position - b.position),
          );
        }
        if (Array.isArray(payload.sources)) {
          setSources(payload.sources);
        }
        return;
      }

      if (
        event.type === 'research.updated' ||
        event.type === 'research.completed' ||
        event.type === 'member.added' ||
        event.type === 'member.updated' ||
        event.type === 'member.removed'
      ) {
        refreshReport();
        return;
      }

      if (event.type === 'research.deleted') {
        navigate('/');
      }
    },
    [navigate, refreshReport],
  );

  const { connectionState, presence, sendActivity } = useRealtimeRoom({
    resourceType: 'research',
    resourceId: id,
    enabled: Boolean(id && report),
    onEvent: handleRealtimeEvent,
  });

  const handleCitationSelect = (num: number) => {
    setSelectedSourceNumber(num);
    if (window.innerWidth < 1280) {
      setIsMobileSourcesOpen(true);
    }
  };

  const handleShare = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopiedShare(true);
      setTimeout(() => setCopiedShare(false), 2000);
    } catch {
      setCopiedShare(false);
    }
  };

  const handleExport = () => {
    if (!report) return;
    const markdown = buildReportMarkdown(report, sources, followups);
    const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `${report.id}-synthesis-memo.md`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleFollowupSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    const cleaned = followupQuestion.trim();
    if (!id || !cleaned || followupSubmitting) return;
    setFollowupSubmitting(true);
    setFollowupError(null);
    sendActivity('asking');
    try {
      const response = await reportService.askFollowup(id, {
        question: cleaned,
        ...(preferredProvider ? { preferredProvider } : {}),
        ...(modelOverride ? { modelOverride } : {}),
        ...(localFallbackEnabled !== undefined ? { localFallbackEnabled } : {}),
      });
      setFollowups((prev) =>
        prev.some((item) => item.id === response.followup.id)
          ? prev
          : [...prev, response.followup].sort((a, b) => a.position - b.position),
      );
      setSources(response.sources);
      setFollowupQuestion('');
    } catch (err) {
      setFollowupError(
        redactSecrets(
          apiErrorMessage(err, 'Could not answer your follow-up right now. Please try again.'),
        ),
      );
    } finally {
      setFollowupSubmitting(false);
      sendActivity('viewing');
    }
  };

  if (error) {
    if (error instanceof ApiError && error.status === 404) {
      return (
        <div className="flex min-h-screen items-center justify-center px-4">
          <ErrorState 
            title="Report not available yet" 
            message="This research has not finished yet. Open its progress page to follow along." 
            onRetry={() => navigate(`/research/${id}/progress`)} 
          />
        </div>
      );
    }
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <ErrorState 
          title="Could not load the report" 
          message={error.message} 
          onRetry={() => window.location.reload()} 
        />
      </div>
    );
  }

  if (!report) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <CenteredLoadingState label="Loading report…" />
      </div>
    );
  }

  const myRole = report.myRole ?? 'owner';
  const canEdit = myRole === 'owner' || myRole === 'editor';
  const currentQuestionText = (report.question || report.title).trim();
  const trimmedEditQuestion = draftQuestion.trim();

  const handleEditQuestionSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!report.researchId || !trimmedEditQuestion || editSubmitting) return;
    setEditSubmitting(true);
    setEditError(null);
    try {
      await editResearchQuestion(report.researchId, { query: trimmedEditQuestion });
      setEditingQuestion(false);
      reloadHistory?.();
      navigate(`/research/${report.researchId}/progress`, { replace: true });
    } catch (err) {
      setEditError(
        friendlyResearchError(
          err,
          'Could not update the research question right now. Please try again.',
        ),
      );
    } finally {
      setEditSubmitting(false);
    }
  };

  const getSourceByNum = (n: number) => sources.find((s) => s.number === n);
  const renderCitation = (sourceNumber: number, key: string) => (
    <CitationChip
      key={key}
      number={sourceNumber}
      source={getSourceByNum(sourceNumber)}
      isSelected={selectedSourceNumber === sourceNumber}
      onSelect={handleCitationSelect}
    />
  );
  const showSummary = !(
    report.sections.length > 0 && report.sections[0].content === report.summary
  );

  return (
    <div className="report-reading-page flex min-h-screen flex-col">
      <TopBar
        breadcrumbs={
          <div className="flex min-w-0 items-center gap-2">
            <span className="shrink-0 text-ink-soft">Research</span>
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-ink-muted" />
            <span className="truncate font-medium text-ink" title={report.title}>{report.title}</span>
          </div>
        }
        rightActions={
          <div className="flex items-center gap-1.5">
            <PresenceBar
              presence={presence}
              currentUserId={user?.id ?? null}
              connectionState={connectionState}
            />

            <button
              type="button"
              onClick={() => setIsMobileSourcesOpen(true)}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line-strong bg-panel px-2.5 text-[13px] font-medium text-ink shadow-xs xl:hidden"
            >
              <BookOpen className="h-4 w-4" />
              <span>Sources</span>
              <span className="tabular-nums text-ink-muted">{sources.length}</span>
            </button>

            <button
              type="button"
              onClick={() => setIsShareOpen(true)}
              aria-label="Share research"
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line bg-panel px-2.5 text-[13px] font-medium text-ink-soft transition-colors hover:border-line-strong hover:bg-subtle hover:text-ink"
            >
              <Users className="h-4 w-4" />
              <span className="hidden md:inline">Share</span>
            </button>

            <button
              type="button"
              onClick={() => void handleShare()}
              aria-label={copiedShare ? 'Link copied' : 'Copy link'}
              className="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-[13px] font-medium text-ink-soft transition-colors hover:bg-subtle hover:text-ink"
            >
              {copiedShare ? <Check className="h-4 w-4 text-accent" /> : <Link2 className="h-4 w-4" />}
              <span className="hidden md:inline">{copiedShare ? 'Copied' : 'Copy link'}</span>
            </button>

            <button
              type="button"
              onClick={handleExport}
              aria-label="Export as Markdown"
              className="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-[13px] font-medium text-ink-soft transition-colors hover:bg-subtle hover:text-ink"
            >
              <Download className="h-4 w-4" />
              <span className="hidden md:inline">Export</span>
            </button>
          </div>
        }
      />

      <div className="flex flex-1 pt-14">
        <main className="min-w-0 flex-1 bg-panel px-5 py-10 sm:px-10 lg:py-14">
          <div className="mx-auto max-w-[680px]">
            <header className="mb-10 border-b border-line pb-8">
              <div className="mb-4 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-muted">
                <StatusBadge status={report.status} size="sm" />
                <span className="tabular-nums">{report.sourceCount} {report.sourceCount === 1 ? 'source' : 'sources'}</span>
                <span aria-hidden="true">·</span>
                <span className="tabular-nums">{report.readingTimeMinutes} min read</span>
                <span aria-hidden="true">·</span>
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  Updated {new Date(report.updatedAt).toLocaleDateString(undefined, { dateStyle: 'medium' })}
                </span>
              </div>

              <h1 className="font-serif text-[30px] leading-[1.2] tracking-[-0.015em] text-ink sm:text-[36px]">
                {report.title}
              </h1>
              {report.question && report.question.trim() !== report.title.trim() && (
                <p className="mt-2.5 text-[15px] leading-relaxed text-ink-soft">
                  {report.question}
                </p>
              )}

              {canEdit && !editingQuestion && (
                <div className="mt-4">
                  <button
                    type="button"
                    onClick={() => {
                      setEditError(null);
                      setDraftQuestion(currentQuestionText);
                      setEditingQuestion(true);
                    }}
                    className="btn-secondary"
                  >
                    <PencilLine className="h-3.5 w-3.5" />
                    Edit question
                  </button>
                </div>
              )}

              {canEdit && editingQuestion && (
                <form
                  onSubmit={(e) => void handleEditQuestionSubmit(e)}
                  className="mt-4 rounded-xl border border-line bg-subtle/30 p-4"
                >
                  <label htmlFor="report-edit-question-input" className="field-label">
                    Edit question
                  </label>
                  <textarea
                    id="report-edit-question-input"
                    rows={3}
                    maxLength={2000}
                    disabled={editSubmitting}
                    value={draftQuestion}
                    onChange={(e) => setDraftQuestion(e.target.value)}
                    onKeyDown={(e) => {
                      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                        e.preventDefault();
                        void handleEditQuestionSubmit();
                      }
                      if (e.key === 'Escape') {
                        setEditingQuestion(false);
                        setEditError(null);
                      }
                    }}
                    className="field resize-none bg-panel"
                  />
                  {editError && (
                    <p role="alert" className="mt-2 text-xs text-danger">
                      {editError}
                    </p>
                  )}
                  <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setEditingQuestion(false);
                        setEditError(null);
                      }}
                      disabled={editSubmitting}
                      className="btn-secondary"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={editSubmitting || !trimmedEditQuestion}
                      className="btn-primary"
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                      {editSubmitting ? 'Restarting…' : 'Save & restart'}
                    </button>
                  </div>
                </form>
              )}
            </header>

            <article className="space-y-9">
              {report.summary && showSummary && (
                <section className="rounded-xl border border-line bg-subtle/40 px-5 py-4 sm:px-6 sm:py-5">
                  <h2 className="mb-2.5 text-[12px] font-semibold uppercase tracking-[0.06em] text-accent">
                    Summary
                  </h2>
                  <SafeMarkdown
                    content={report.summary}
                    className="font-serif text-[17px] leading-[1.75] sm:text-[18px]"
                    renderCitation={renderCitation}
                  />
                </section>
              )}

              {report.sections.map((section, sectionIdx) => (
                <section
                  key={section.id}
                  className={sectionIdx > 0 ? 'border-t border-line/70 pt-8' : undefined}
                >
                  <h2 className="mb-3 text-lg font-semibold tracking-[-0.01em] text-ink">
                    {section.heading}
                  </h2>
                  <div className="font-serif text-[17px] leading-[1.8] text-ink sm:text-[18px]">
                    <SafeMarkdown
                      content={section.content}
                      className="text-[17px] leading-[1.8] sm:text-[18px]"
                      renderCitation={renderCitation}
                    />
                    {/* Older reports have no inline markers; list their sources at the end. */}
                    {!INLINE_CITATION.test(section.content) && section.citations && section.citations.length > 0 && section.citations.map((citation, idx) => (
                      <React.Fragment key={citation.id}>
                        <CitationChip
                          number={citation.number}
                          source={getSourceByNum(citation.number)}
                          isSelected={selectedSourceNumber === citation.number}
                          onSelect={handleCitationSelect}
                        />
                        {idx < section.citations.length - 1 ? ' ' : ''}
                      </React.Fragment>
                    ))}
                  </div>

                  {section.quote && (
                    <blockquote className="my-6 border-l-2 border-accent-line pl-5 font-serif text-[17px] italic leading-relaxed text-ink-soft">
                      &ldquo;{section.quote}&rdquo;
                    </blockquote>
                  )}
                </section>
              ))}
            </article>

            {/* Grounded follow-up thread + lightweight composer */}
            <section
              aria-labelledby="report-followups-heading"
              className="mt-14 border-t border-line pt-10"
            >
              <div className="mb-5 flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <MessageSquarePlus className="h-4 w-4 text-accent" />
                  <h2
                    id="report-followups-heading"
                    className="text-base font-semibold tracking-[-0.01em] text-ink"
                  >
                    Follow-up questions
                  </h2>
                </div>
                <span className="inline-flex items-center gap-1 rounded-full bg-subtle px-2.5 py-0.5 text-[11px] font-medium text-ink-muted">
                  <Sparkles className="h-3 w-3 text-accent" />
                  Uses report memory · 0.25× credits
                </span>
              </div>

              {followups.length > 0 && (
                <div className="mb-6 space-y-5">
                  {followups.map((turn) => (
                    <div
                      key={turn.id}
                      className="rounded-xl border border-line bg-subtle/30 p-4 sm:p-5"
                    >
                      <p className="text-[14px] font-semibold text-ink">
                        {turn.question}
                      </p>
                      <div className="mt-2.5 font-serif text-[16px] leading-[1.75] text-ink">
                        <SafeMarkdown
                          content={turn.answer}
                          className="text-[16px] leading-[1.75]"
                          renderCitation={renderCitation}
                        />
                      </div>
                      <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-ink-muted">
                        {turn.authorName ? (
                          <span className="font-medium text-ink-soft">
                            Asked by {turn.authorName}
                          </span>
                        ) : null}
                        {turn.provider ? (
                          <span>{prettyModelName(turn.provider, turn.model)}</span>
                        ) : null}
                        {turn.insufficientEvidence ? (
                          <span className="rounded bg-subtle px-1.5 py-0.5 text-ink-soft">
                            0 credits charged
                          </span>
                        ) : null}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {canEdit ? (
                <form
                  onSubmit={(e) => void handleFollowupSubmit(e)}
                  className="rounded-xl border border-line bg-subtle/25 p-4 shadow-xs"
                >
                  <label
                    htmlFor="followup-question-input"
                    className="mb-2 block text-xs font-medium text-ink-muted"
                  >
                    Ask a follow-up grounded in this report and its attached sources
                  </label>
                  <textarea
                    id="followup-question-input"
                    aria-label="Follow-up question"
                    rows={2}
                    maxLength={2000}
                    disabled={followupSubmitting}
                    value={followupQuestion}
                    onChange={(e) => {
                      const next = e.target.value;
                      setFollowupQuestion(next);
                      sendActivity(next.trim().length > 0 ? 'typing' : 'viewing');
                    }}
                    onBlur={() => {
                      if (!followupSubmitting) sendActivity('viewing');
                    }}
                    onKeyDown={(e) => {
                      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                        e.preventDefault();
                        void handleFollowupSubmit();
                      }
                    }}
                    placeholder="Ask a follow-up (e.g. explain this point simpler, or compare doses mentioned)…"
                    className="w-full resize-none rounded-lg border border-line bg-panel px-3 py-2.5 text-[14px] text-ink placeholder:text-ink-muted focus:border-line-strong focus:outline-none disabled:opacity-60"
                  />

                  {followupError ? (
                    <p role="alert" className="mt-2 text-xs text-danger">
                      {followupError}
                    </p>
                  ) : null}

                  <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                    <ModelControlBar
                      depth={researchDepth}
                      onDepthChange={setResearchDepth}
                      preferredProvider={preferredProvider}
                      onPreferredProviderChange={setPreferredProvider}
                      modelOverride={modelOverride}
                      onModelOverrideChange={setModelOverride}
                      localFallbackEnabled={localFallbackEnabled}
                      onLocalFallbackChange={setLocalFallbackEnabled}
                      disabled={followupSubmitting}
                      menuPlacement="up"
                    />
                    <div className="flex items-center gap-2">
                      <span className="hidden text-[11px] text-ink-muted sm:inline">
                        {shortcutLabel('Enter')}
                      </span>
                      <PrimaryButton
                        type="submit"
                        size="sm"
                        disabled={followupSubmitting || !followupQuestion.trim()}
                      >
                        <Send className="h-3.5 w-3.5" />
                        {followupSubmitting ? 'Answering…' : 'Ask follow-up'}
                      </PrimaryButton>
                    </div>
                  </div>
                </form>
              ) : (
                <div className="rounded-xl border border-line bg-subtle/25 px-4 py-3 text-xs text-ink-muted">
                  You have view-only access to this research report. Ask an owner to grant edit
                  permission to ask follow-up questions.
                </div>
              )}
            </section>
          </div>
        </main>

        <aside className="sticky top-14 hidden h-[calc(100vh-3.5rem)] w-[380px] shrink-0 self-start xl:block">
          <SourcesPanel
            reportId={report.id}
            sources={sources}
            selectedSourceNumber={selectedSourceNumber}
            onSelectSource={setSelectedSourceNumber}
          />
        </aside>
      </div>

      {isMobileSourcesOpen && (
        <div className="fixed inset-0 z-50 xl:hidden flex">
          <div
            className="fixed inset-0 bg-black/40 overlay-enter"
            onClick={() => setIsMobileSourcesOpen(false)}
          />
          <div className="relative z-10 ml-auto h-full w-full max-w-sm bg-panel shadow-xl">
            <SourcesPanel
              reportId={report.id}
              sources={sources}
              selectedSourceNumber={selectedSourceNumber}
              onSelectSource={setSelectedSourceNumber}
              onCloseMobileDrawer={() => setIsMobileSourcesOpen(false)}
              isMobileDrawer
            />
          </div>
        </div>
      )}

      {isShareOpen && (
        <ShareDialog
          isOpen={isShareOpen}
          resourceType="research"
          resourceId={id ?? report.researchId}
          resourceTitle={report.title}
          onClose={() => setIsShareOpen(false)}
          onChanged={refreshReport}
        />
      )}
    </div>
  );
};
