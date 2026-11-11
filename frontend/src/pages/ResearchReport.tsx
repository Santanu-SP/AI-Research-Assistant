import React, { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
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
  Share2,
  Download,
  Check,
  Clock,
  BookOpen,
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
        <div className="min-h-screen bg-canvas flex items-center justify-center">
          <ErrorState 
            title="Report not available yet" 
            message="This research has not produced a synthesis report." 
            onRetry={() => navigate(`/research/${id}/progress`)} 
          />
        </div>
      );
    }
    return (
      <div className="min-h-screen bg-canvas flex items-center justify-center">
        <ErrorState 
          title="Connection Error" 
          message={error.message} 
          onRetry={() => window.location.reload()} 
        />
      </div>
    );
  }

  if (!report) {
    return (
      <div className="min-h-screen bg-canvas flex items-center justify-center">
        <CenteredLoadingState label="Loading research synthesis…" />
      </div>
    );
  }

  const getSourceByNum = (n: number) => sources.find((s) => s.number === n);
  const showSummary = !(
    report.sections.length > 0 && report.sections[0].content === report.summary
  );

  return (
    <div className="report-reading-page min-h-screen bg-canvas flex flex-col">
      <TopBar
        breadcrumbs={
          <div className="flex items-center gap-2 text-xs truncate">
            <Link
              to="/research"
              className="text-ink-soft hover:text-ink shrink-0"
            >
              My Research
            </Link>
            <span className="text-ink-muted">/</span>
            <span className="text-ink font-medium truncate">
              Synthesis Memo
            </span>
            <span className="text-ink-muted hidden sm:inline">·</span>
            <span className="font-mono text-[11px] text-ink-muted hidden sm:inline">
              {report.dossierRef}
            </span>
          </div>
        }
        rightActions={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIsMobileSourcesOpen(true)}
              className="xl:hidden text-xs font-medium text-accent bg-accent-soft border border-accent-line px-2.5 py-1.5 rounded-md flex items-center gap-1.5"
            >
              <BookOpen className="w-3.5 h-3.5" />
              <span>Sources ({sources.length})</span>
            </button>

            <button
              type="button"
              onClick={() => void handleShare()}
              className="text-xs text-ink-soft hover:text-ink border border-line hover:bg-subtle px-2.5 py-1.5 rounded-md flex items-center gap-1 transition-colors cursor-pointer"
            >
              <Share2 className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">
                {copiedShare ? 'Link copied' : 'Copy link'}
              </span>
            </button>

            <button
              type="button"
              onClick={handleExport}
              className="text-xs text-ink-soft hover:text-ink border border-line hover:bg-subtle px-2.5 py-1.5 rounded-md flex items-center gap-1 transition-colors cursor-pointer"
            >
              <Download className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Export</span>
            </button>

            <div className="hidden sm:flex items-center gap-1 text-xs text-accent bg-accent-soft border border-accent-line px-2.5 py-1 rounded-md">
              <Check className="w-3 h-3 text-accent" />
              <span className="font-medium">Saved</span>
            </div>
          </div>
        }
      />

      <div className="flex-1 pt-14 flex overflow-hidden">
        <main className="report-document-scroll flex-1 overflow-y-auto px-4 sm:px-8 py-10">
          <div className="report-reading-paper max-w-3xl mx-auto">
            <div className="pb-6 mb-8 border-b border-line">
              <div className="font-mono text-xs text-ink-muted tracking-wider uppercase mb-2">
                {report.dossierRef}
              </div>

              <h1 className="font-serif text-3xl sm:text-4xl text-ink font-normal leading-[1.2] mb-4">
                {report.title}
              </h1>

              <div className="flex flex-wrap items-center gap-3 text-xs text-ink-soft">
                <span className="font-medium text-ink">
                  {report.sourceCount} sources cited
                </span>
                <span className="text-ink-muted">·</span>
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  <span>Updated {new Date(report.updatedAt).toLocaleDateString()}</span>
                </span>
                <span className="text-ink-muted">·</span>
                <span>{report.readingTimeMinutes} min read</span>
                <span className="text-ink-muted">·</span>
                <StatusBadge status={report.status} size="sm" />
              </div>
            </div>

            <article className="space-y-10">
              {report.summary && showSummary && (
                <section>
                  <h2 className="font-serif text-2xl text-ink font-normal mb-3">
                    Executive Summary
                  </h2>
                  <div className="font-serif text-[17.5px] sm:text-[18.5px] leading-[1.7] text-ink">
                    {report.summary}
                  </div>
                </section>
              )}

              {report.sections.map((section) => (
                <section key={section.id}>
                  <h2 className="font-serif text-2xl text-ink font-normal mb-3">
                    {section.heading}
                  </h2>
                  <div className="font-serif text-[17.5px] sm:text-[18.5px] leading-[1.7] text-ink mb-4">
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
                    <div className="my-6 p-4 bg-canvas border-l-3 border-accent rounded-r-lg">
                      <div className="font-serif italic text-[16px] text-ink-soft leading-relaxed">
                        &ldquo;{section.quote}&rdquo;
                      </div>
                    </div>
                  )}
                </section>
              ))}
            </article>
          </div>
        </main>

        <aside className="hidden xl:block w-[400px] shrink-0 h-full">
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
            className="fixed inset-0 bg-black/40 backdrop-blur-xs"
            onClick={() => setIsMobileSourcesOpen(false)}
          />
          <div className="relative ml-auto w-full max-w-sm bg-panel h-full shadow-2xl z-10 animate-in slide-in-from-right duration-200">
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
