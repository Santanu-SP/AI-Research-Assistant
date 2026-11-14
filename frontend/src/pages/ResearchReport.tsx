import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { TopBar } from '../components/layout/TopBar';
import { StatusBadge } from '../components/common/StatusBadge';
import { CitationChip } from '../components/research/CitationChip';
import { SourcesPanel } from '../components/sources/SourcesPanel';
import { CenteredLoadingState } from '../components/common/LoadingState';
import { ErrorState } from '../components/common/ErrorState';
import { reportService } from '../services/report.service';
import { ResearchReportResponse, SourceResponse } from '../types/report';
import { ApiError } from '../services/api';
import {
  BookOpen,
  Check,
  ChevronRight,
  Clock,
  Download,
  Link2,
} from 'lucide-react';

const buildReportMarkdown = (
  report: ResearchReportResponse,
  sources: SourceResponse[],
): string => {
  let markdown = `# ${report.title}\n\n`;
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
  const [report, setReport] = useState<ResearchReportResponse | null>(null);
  const [sources, setSources] = useState<SourceResponse[]>([]);
  const [selectedSourceNumber, setSelectedSourceNumber] = useState<number>(1);
  const [isMobileSourcesOpen, setIsMobileSourcesOpen] = useState(false);
  const [copiedShare, setCopiedShare] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!id) return;
    
    reportService
      .getResearchReport(id)
      .then((data) => {
        setReport(data.report);
        setSources(data.sources);
        if (data.sources.length > 0) {
          setSelectedSourceNumber(data.sources[0].number);
        }
      })
      .catch((err) => {
        setError(err instanceof Error ? err : new Error('Unknown error occurred'));
      });
  }, [id]);

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
    const markdown = buildReportMarkdown(report, sources);
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

  const getSourceByNum = (n: number) => sources.find((s) => s.number === n);
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
          <div className="flex items-center gap-1">
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
            </header>

            <article className="space-y-10">
              {report.summary && showSummary && (
                <section>
                  <h2 className="mb-3 text-[13px] font-semibold uppercase tracking-[0.06em] text-ink-muted">
                    Summary
                  </h2>
                  <p className="font-serif text-[18px] leading-[1.75] text-ink">
                    {report.summary}
                  </p>
                </section>
              )}

              {report.sections.map((section) => (
                <section key={section.id}>
                  <h2 className="mb-3 text-lg font-semibold tracking-[-0.01em] text-ink">
                    {section.heading}
                  </h2>
                  <div className="font-serif text-[17px] leading-[1.8] text-ink sm:text-[18px]">
                    {section.content}{' '}
                    {section.citations && section.citations.length > 0 && section.citations.map((citation, idx) => (
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
    </div>
  );
};
