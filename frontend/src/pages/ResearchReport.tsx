import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { TopBar } from '../components/layout/TopBar';
import { StatusBadge } from '../components/common/StatusBadge';
import { CitationChip } from '../components/research/CitationChip';
import { SourcesPanel } from '../components/sources/SourcesPanel';
import { researchService } from '../services/research.service';
import { ResearchReport as IResearchReport } from '../types/research';
import { Source } from '../types/source';
import {
  Share2,
  Download,
  Check,
  Clock,
  BookOpen,
} from 'lucide-react';

export const ResearchReportPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<IResearchReport | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [selectedSourceNumber, setSelectedSourceNumber] = useState<number>(1);
  const [isMobileSourcesOpen, setIsMobileSourcesOpen] = useState(false);
  const [copiedShare, setCopiedShare] = useState(false);

  useEffect(() => {
    researchService
      .getResearchReport(id || 'res-genai-2025')
      .then((data) => {
        setReport(data.report);
        setSources(data.sources);
      });
  }, [id]);

  const handleCitationSelect = (num: number) => {
    setSelectedSourceNumber(num);
    // On small screens, open the drawer to show the source
    if (window.innerWidth < 1280) {
      setIsMobileSourcesOpen(true);
    }
  };

  const handleShare = () => {
    navigator.clipboard.writeText(window.location.href);
    setCopiedShare(true);
    setTimeout(() => setCopiedShare(false), 2000);
  };

  const handleExport = () => {
    if (!report) return;
    let md = `# ${report.title}\n\n`;
    md += `${report.dossierRef} | ${report.readingTimeMinutes} min read\n\n`;
    md += `## Executive Summary\n${report.summary}\n\n`;
    report.sections.forEach((sec) => {
      md += `## ${sec.heading}\n${sec.content}\n\n`;
      if (sec.quote) {
        md += `> "${sec.quote}"\n\n`;
      }
    });
    md += `## References\n`;
    sources.forEach((s) => {
      md += `[${s.number}] ${s.authors.join(', ')} (${s.year}). "${s.title}". ${s.publisher}.\n`;
    });

    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `${report.id}-synthesis-memo.md`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (!report) {
    return (
      <div className="min-h-screen bg-[#fafaf8] flex items-center justify-center">
        <div className="text-xs text-[#6b706c]">Loading research synthesis…</div>
      </div>
    );
  }

  const getSourceByNum = (n: number) => sources.find((s) => s.number === n);

  return (
    <div className="min-h-screen bg-[#fafaf8] flex flex-col">
      {/* TopBar */}
      <TopBar
        breadcrumbs={
          <div className="flex items-center gap-2 text-xs truncate">
            <Link
              to="/research"
              className="text-[#6b706c] hover:text-[#181a18] shrink-0"
            >
              My Research
            </Link>
            <span className="text-[#929792]">/</span>
            <span className="text-[#181a18] font-medium truncate">
              Synthesis Memo
            </span>
            <span className="text-[#929792] hidden sm:inline">·</span>
            <span className="font-mono text-[11px] text-[#929792] hidden sm:inline">
              {report.dossierRef}
            </span>
          </div>
        }
        rightActions={
          <div className="flex items-center gap-2">
            {/* Mobile toggle for Sources Drawer */}
            <button
              type="button"
              onClick={() => setIsMobileSourcesOpen(true)}
              className="xl:hidden text-xs font-medium text-[#163328] bg-[#f1f6f3] border border-[#d8e5df] px-2.5 py-1.5 rounded-md flex items-center gap-1.5"
            >
              <BookOpen className="w-3.5 h-3.5" />
              <span>Sources ({sources.length})</span>
            </button>

            <button
              type="button"
              onClick={handleShare}
              className="text-xs text-[#6b706c] hover:text-[#181a18] border border-[#e5e7e4] hover:bg-[#f5f5f2] px-2.5 py-1.5 rounded-md flex items-center gap-1 transition-colors cursor-pointer"
            >
              <Share2 className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">
                {copiedShare ? 'Link Copied!' : 'Share'}
              </span>
            </button>

            <button
              type="button"
              onClick={handleExport}
              className="text-xs text-[#6b706c] hover:text-[#181a18] border border-[#e5e7e4] hover:bg-[#f5f5f2] px-2.5 py-1.5 rounded-md flex items-center gap-1 transition-colors cursor-pointer"
            >
              <Download className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Export</span>
            </button>

            <div className="hidden sm:flex items-center gap-1 text-xs text-[#163328] bg-[#f1f6f3] border border-[#d8e5df] px-2.5 py-1 rounded-md">
              <Check className="w-3 h-3 text-[#163328]" />
              <span className="font-medium">Saved</span>
            </div>
          </div>
        }
      />

      {/* Main Layout: Split between Report document and Sources panel */}
      <div className="flex-1 pt-14 flex overflow-hidden">
        {/* Left/Center Document Content */}
        <main className="flex-1 overflow-y-auto px-4 sm:px-8 py-10">
          <div className="max-w-3xl mx-auto">
            {/* Memo Dossier Header */}
            <div className="pb-6 mb-8 border-b border-[#e5e7e4]">
              <div className="font-mono text-xs text-[#929792] tracking-wider uppercase mb-2">
                {report.dossierRef}
              </div>

              <h1 className="font-serif text-3xl sm:text-4xl text-[#181a18] font-normal leading-[1.2] mb-4">
                {report.title}
              </h1>

              {/* Metadata row */}
              <div className="flex flex-wrap items-center gap-3 text-xs text-[#6b706c]">
                <span className="font-medium text-[#181a18]">
                  {report.sourceCount} sources cited
                </span>
                <span className="text-[#929792]">·</span>
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  <span>Updated {report.updatedAt}</span>
                </span>
                <span className="text-[#929792]">·</span>
                <span>{report.readingTimeMinutes} min read</span>
                <span className="text-[#929792]">·</span>
                <StatusBadge status={report.status} size="sm" />
              </div>
            </div>

            {/* Structured Report Sections with EB Garamond Serif Prose */}
            <article className="space-y-10">
              {/* Section: Executive Summary */}
              <section>
                <h2 className="font-serif text-2xl text-[#181a18] font-normal mb-3">
                  Executive Summary
                </h2>
                <div className="font-serif text-[17.5px] sm:text-[18.5px] leading-[1.7] text-[#2c302d]">
                  The integration of large language models into software
                  engineering represents an ontological evolution rather than mere
                  incremental automation. Development is migrating from manual syntax
                  articulation to higher-order intent specification, critical code
                  review, and holistic system design. Rather than replacing engineers,
                  generative assistants operate as cognitive amplifiers for routine
                  code patterns while shifting the critical bottleneck toward
                  verification, architectural boundaries, and correctness proofs{' '}
                  <CitationChip
                    number={1}
                    source={getSourceByNum(1)}
                    isSelected={selectedSourceNumber === 1}
                    onSelect={handleCitationSelect}
                  />{' '}
                  <CitationChip
                    number={3}
                    source={getSourceByNum(3)}
                    isSelected={selectedSourceNumber === 3}
                    onSelect={handleCitationSelect}
                  />
                  .
                </div>
              </section>

              {/* Section: Productivity & Velocity */}
              <section>
                <h2 className="font-serif text-2xl text-[#181a18] font-normal mb-3">
                  Productivity &amp; Velocity
                </h2>
                <div className="font-serif text-[17.5px] sm:text-[18.5px] leading-[1.7] text-[#2c302d] mb-4">
                  Empirical field trials and controlled double-blind studies
                  reveal an asymmetrical distribution of velocity gains. For
                  standardized algorithmic tasks, boilerplate scaffolding, and
                  test harness generation, developers routinely demonstrate
                  completion speedups between 26% and 55%{' '}
                  <CitationChip
                    number={1}
                    source={getSourceByNum(1)}
                    isSelected={selectedSourceNumber === 1}
                    onSelect={handleCitationSelect}
                  />{' '}
                  <CitationChip
                    number={4}
                    source={getSourceByNum(4)}
                    isSelected={selectedSourceNumber === 4}
                    onSelect={handleCitationSelect}
                  />
                  . However, this velocity curve flattens significantly when
                  dealing with distributed state management, legacy system
                  integration, or non-deterministic debugging{' '}
                  <CitationChip
                    number={2}
                    source={getSourceByNum(2)}
                    isSelected={selectedSourceNumber === 2}
                    onSelect={handleCitationSelect}
                  />
                  .
                </div>

                {/* Pull Quote Callout Box */}
                <div className="my-6 p-4 bg-[#fafaf8] border-l-3 border-[#163328] rounded-r-lg">
                  <div className="font-serif italic text-[16px] text-[#424744] leading-relaxed">
                    &ldquo;Controlled trials observed a 55.8% execution speedup in
                    generating initial boilerplate and tests, counterbalanced by an
                    18% increase in human inspection latency during pull request
                    verification.&rdquo;
                  </div>
                </div>
              </section>

              {/* Section: Code Quality and Reliability */}
              <section>
                <h2 className="font-serif text-2xl text-[#181a18] font-normal mb-3">
                  Code Quality and Reliability
                </h2>
                <div className="font-serif text-[17.5px] sm:text-[18.5px] leading-[1.7] text-[#2c302d] mb-4">
                  The acceleration of raw code generation has introduced downstream
                  consequences in artifact integrity. Multi-month observational
                  analyses reveal elevated code churn—files rewritten within two
                  weeks of commit—along with subtle package typosquatting risks
                  and recurring cryptographic oversights{' '}
                  <CitationChip
                    number={2}
                    source={getSourceByNum(2)}
                    isSelected={selectedSourceNumber === 2}
                    onSelect={handleCitationSelect}
                  />{' '}
                  <CitationChip
                    number={5}
                    source={getSourceByNum(5)}
                    isSelected={selectedSourceNumber === 5}
                    onSelect={handleCitationSelect}
                  />
                  .
                </div>

                {/* Pull Quote Callout Box */}
                <div className="my-6 p-4 bg-[#fafaf8] border-l-3 border-[#163328] rounded-r-lg">
                  <div className="font-serif italic text-[16px] text-[#424744] leading-relaxed">
                    &ldquo;While syntactically flawless, model suggestions
                    frequently bypass application-layer defense-in-depth
                    principles, leaving authorization context evaluations missing in
                    up to 34% of synthesized controller endpoints.&rdquo;
                  </div>
                </div>
              </section>

              {/* Section: Developer Workflow Changes */}
              <section>
                <h2 className="font-serif text-2xl text-[#181a18] font-normal mb-3">
                  Developer Workflow Changes
                </h2>
                <div className="font-serif text-[17.5px] sm:text-[18.5px] leading-[1.7] text-[#2c302d]">
                  The role of senior developers is pivoting toward verification
                  gatekeeping and declarative architectural governance. As
                  synthesis tools manage intermediate syntax, code review becomes
                  the focal point of intellectual friction. Reviewers can no longer
                  presuppose the author&apos;s intimate familiarity with edge
                  cases, necessitating automated formal verification and
                  metamorphic fuzzing pipelines{' '}
                  <CitationChip
                    number={3}
                    source={getSourceByNum(3)}
                    isSelected={selectedSourceNumber === 3}
                    onSelect={handleCitationSelect}
                  />{' '}
                  <CitationChip
                    number={6}
                    source={getSourceByNum(6)}
                    isSelected={selectedSourceNumber === 6}
                    onSelect={handleCitationSelect}
                  />
                  .
                </div>
              </section>

              {/* Section: Limitations of Current Evidence & Conclusion */}
              <section className="pb-12">
                <h2 className="font-serif text-2xl text-[#181a18] font-normal mb-3">
                  Limitations of Current Evidence &amp; Conclusion
                </h2>
                <div className="font-serif text-[17.5px] sm:text-[18.5px] leading-[1.7] text-[#2c302d]">
                  The prevailing consensus across technical literature
                  demonstrates that sustained value realization stems from
                  organizational guardrails rather than personal prompt acumen{' '}
                  <CitationChip
                    number={1}
                    source={getSourceByNum(1)}
                    isSelected={selectedSourceNumber === 1}
                    onSelect={handleCitationSelect}
                  />{' '}
                  <CitationChip
                    number={7}
                    source={getSourceByNum(7)}
                    isSelected={selectedSourceNumber === 7}
                    onSelect={handleCitationSelect}
                  />
                  . While generative models excel in localized syntactical
                  drafting, system resilience remains bounded by architectural
                  rigor, defensive review paradigms, and disciplined verification
                  workflows.
                </div>
              </section>
            </article>
          </div>
        </main>

        {/* Right Desktop Sources Panel */}
        <aside className="hidden xl:block w-[400px] shrink-0 h-full">
          <SourcesPanel
            sources={sources}
            selectedSourceNumber={selectedSourceNumber}
            onSelectSource={setSelectedSourceNumber}
          />
        </aside>
      </div>

      {/* Mobile Sources Drawer / Sheet */}
      {isMobileSourcesOpen && (
        <div className="fixed inset-0 z-50 xl:hidden flex">
          <div
            className="fixed inset-0 bg-black/40 backdrop-blur-xs"
            onClick={() => setIsMobileSourcesOpen(false)}
          />
          <div className="relative ml-auto w-full max-w-sm bg-white h-full shadow-2xl z-10 animate-in slide-in-from-right duration-200">
            <SourcesPanel
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
