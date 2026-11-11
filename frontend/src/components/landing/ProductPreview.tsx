import React from 'react';
import { ChevronRight, FileText, Search } from 'lucide-react';

const step = (ms: number) => ({ '--step-delay': `${ms}ms` }) as React.CSSProperties;

/**
 * A static rendering of the report screen, used on the landing page.
 * It mirrors the real layout so the preview never drifts into a mock-up of
 * something the app does not do.
 */
export const ProductPreview: React.FC = () => (
  <div className="overflow-hidden rounded-xl border border-line-strong bg-panel shadow-xl" aria-hidden="true">
    <div className="flex h-10 items-center justify-between border-b border-line bg-subtle/60 px-4">
      <div className="flex items-center gap-1.5 text-xs text-ink-muted">
        <span>My research</span>
        <ChevronRight className="h-3 w-3" />
        <span className="font-medium text-ink">Report</span>
      </div>
      <span className="font-mono text-[11px] text-ink-muted">3 sources · 4 min read</span>
    </div>

    <div className="grid md:grid-cols-[minmax(0,1fr)_300px]">
      <div className="px-6 py-7 sm:px-10 sm:py-9">
        <p className="preview-step text-xs text-ink-muted" style={step(800)}>Asked across 14 papers in “Retrieval methods”</p>
        <h3 style={step(880)} className="preview-step mt-2 font-serif text-[22px] leading-snug tracking-[-0.01em] text-ink sm:text-[26px]">
          Does reranking improve citation accuracy in retrieval-augmented answers?
        </h3>

        <div className="mt-6 space-y-4 font-serif text-[15px] leading-[1.75] text-ink sm:text-base">
          <p className="preview-step" style={step(960)}>
            <span className="preview-highlight">
              Adding a cross-encoder reranker after hybrid retrieval raised the share of correctly
              cited sentences from 71% to 86% on the evaluated question set
            </span>
            <Marker n={1} active />. The gain was largest for questions whose answer sat in a
            single table or figure caption <Marker n={2} />.
          </p>
          <p className="preview-step" style={step(1040)}>
            Two of the papers note that reranking adds latency per query and recommend limiting it to
            the top 50 candidates <Marker n={3} />.
          </p>
        </div>

        <div style={step(1120)} className="preview-step mt-6 flex items-center gap-2 rounded-md border border-line bg-subtle/50 px-3 py-2 text-xs text-ink-soft">
          <span className="preview-breathe h-1.5 w-1.5 rounded-full bg-accent" />
          Citations are checked sentence by sentence before the answer is saved.
        </div>
      </div>

      <div className="hidden border-l border-line bg-canvas/40 md:block">
        <div className="border-b border-line px-4 py-3">
          <p className="text-[13px] font-medium text-ink">
            Sources <span className="text-ink-muted">3</span>
          </p>
          <div className="mt-2.5 flex h-8 items-center gap-2 rounded-md border border-line bg-panel px-2.5 text-xs text-ink-muted">
            <Search className="h-3.5 w-3.5" />
            Filter sources
          </div>
        </div>
        <div className="space-y-1 p-3">
          <div style={step(1100)} className="preview-source rounded-lg border border-accent-line bg-panel p-3.5 shadow-sm ring-1 ring-accent-line">
            <div className="flex items-center gap-1.5 text-[11px] text-ink-muted">
              <span className="flex h-5 min-w-5 items-center justify-center rounded bg-solid px-1 font-mono text-[11px] text-on-solid">1</span>
              reranking-eval.pdf · p. 7
            </div>
            <p className="mt-2 text-[13px] font-medium leading-snug text-ink">Cross-encoder reranking for grounded QA</p>
            <p className="mt-2 border-l-2 border-accent-line pl-2.5 font-serif text-xs italic leading-relaxed text-ink-soft">
              “Citation precision increased from 0.71 to 0.86 when the reranker was applied to the
              fused candidate list.”
            </p>
          </div>
          {[
            ['2', 'table-qa-study.pdf · p. 12', 'Answering from tables and captions'],
            ['3', 'latency-notes.docx · p. 3', 'Cost of reranking in practice'],
          ].map(([n, meta, title], index) => (
            <div key={n} style={step(1180 + index * 80)} className="preview-source flex items-start gap-2.5 rounded-lg px-3 py-2.5">
              <span className="mt-0.5 flex h-5 min-w-5 items-center justify-center rounded bg-subtle font-mono text-[11px] text-ink-soft">{n}</span>
              <div className="min-w-0">
                <p className="truncate text-[11px] text-ink-muted">{meta}</p>
                <p className="truncate text-[13px] font-medium text-ink">{title}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  </div>
);

const Marker: React.FC<{ n: number; active?: boolean }> = ({ n, active = false }) => (
  <span
    className={`${active ? 'preview-marker-ping ' : ''}ml-1 inline-flex h-[18px] min-w-[18px] -translate-y-px items-center justify-center rounded px-1 align-middle font-mono text-[11px] font-medium leading-none ${
      active ? 'bg-solid text-on-solid' : 'bg-accent-soft text-accent'
    }`}
  >
    {n}
  </span>
);

/** Small project list used beside the "projects" feature copy. */
export const ProjectsPreview: React.FC = () => (
  <div className="landing-card overflow-hidden rounded-xl border border-line bg-panel shadow-md" aria-hidden="true">
    <div className="grid grid-cols-[minmax(0,1fr)_72px] gap-3 border-b border-line bg-subtle/50 px-4 py-2 text-[11px] font-medium text-ink-muted">
      <span>Document</span>
      <span>Status</span>
    </div>
    {[
      ['Kinetic selectivity of GPCR ligands', 'PDF · 14 pages', 'Indexed'],
      ['β-arrestin recruitment: a review', 'PDF · 22 pages', 'Indexed'],
      ['Lab notes, October', 'DOCX · 6 pages', 'Indexing'],
    ].map(([title, meta, status]) => (
      <div key={title} className="grid grid-cols-[minmax(0,1fr)_72px] items-center gap-3 border-b border-line px-4 py-3 last:border-b-0">
        <div className="flex min-w-0 items-center gap-2.5">
          <FileText className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} />
          <div className="min-w-0">
            <p className="truncate text-[13px] font-medium text-ink">{title}</p>
            <p className="text-[11px] text-ink-muted">{meta}</p>
          </div>
        </div>
        <span
          className={`inline-flex h-5 w-fit items-center gap-1 rounded-md border px-1.5 text-[11px] font-medium ${
            status === 'Indexed'
              ? 'border-accent-line bg-accent-soft text-accent'
              : 'border-warning-line bg-warning-soft text-warning'
          }`}
        >
          {status === 'Indexing' && <span className="preview-breathe h-1.5 w-1.5 rounded-full bg-current" />}
          {status}
        </span>
      </div>
    ))}
  </div>
);

/** The notice shown when the documents do not hold enough evidence. */
export const EvidencePreview: React.FC = () => (
  <div className="space-y-3" aria-hidden="true">
    <div className="landing-card rounded-xl border border-line bg-panel p-5 shadow-md">
      <p className="text-xs text-ink-muted">Question</p>
      <p className="mt-1 text-[14px] font-medium text-ink">What dose was used in the phase III trial?</p>
      <div className="mt-4 rounded-lg border border-info-line bg-info-soft px-3.5 py-3 text-[13px] leading-relaxed text-info">
        <span className="font-medium">Limited evidence.</span> The documents in this project only
        partly cover the question, so the answer below may be incomplete.
      </div>
    </div>
  </div>
);
