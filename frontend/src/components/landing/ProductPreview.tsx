import React from 'react';
import { ChevronRight, FileAudio, FileSpreadsheet, FileText, Globe2, MessageSquareText, Presentation, Quote, Search } from 'lucide-react';

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
    {([
      ['Sleep and memory consolidation', 'PDF · 14 pages', 'Indexed', FileText],
      ['Week 3 lecture slides', 'PPTX · 22 slides', 'Indexed', Presentation],
      ['Survey results', 'XLSX · 3 sheets', 'Indexed', FileSpreadsheet],
      ['Sleep, explained (Wikipedia)', 'Web page', 'Indexed', Globe2],
      ['Interview recording', 'Audio · 12 min', 'Indexing', FileAudio],
    ] as const).map(([title, meta, status, Icon]) => (
      <div key={title} className="grid grid-cols-[minmax(0,1fr)_72px] items-center gap-3 border-b border-line px-4 py-3 last:border-b-0">
        <div className="flex min-w-0 items-center gap-2.5">
          <Icon className="h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} />
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
        <span className="font-medium">Limited evidence.</span> The sources only partly cover this
        question, so the gap is flagged instead of guessed. Credits for an ungrounded run are refunded.
      </div>
    </div>
    <div className="landing-card ml-6 rounded-xl border border-line bg-panel p-4 shadow-sm sm:ml-10">
      <p className="text-[12px] font-medium text-ink">Competing accounts</p>
      <p className="mt-1 text-[12.5px] leading-relaxed text-ink-soft">
        Source <span className="font-mono text-accent">[2]</span> reports 40 mg, while source{' '}
        <span className="font-mono text-accent">[4]</span> reports 20 mg. Both are shown, side by side.
      </p>
    </div>
  </div>
);

const FLOW_SOURCES: Array<[string, string]> = [
  ['OpenAlex', 'Scholarly'],
  ['arXiv', 'Preprint'],
  ['Crossref', 'DOI record'],
  ['Wikipedia', 'Encyclopedia'],
  ['Reuters · BBC', 'News'],
  ['lecture-notes.pptx', 'Your file'],
];

/**
 * The question → sources → cited answer flow. Each stage animates in once the
 * parent Reveal becomes visible (see the .flow-* rules in index.css).
 */
export const FlowPreview: React.FC = () => (
  <div className="flow grid items-stretch gap-4 lg:grid-cols-[minmax(0,0.9fr)_40px_minmax(0,1.1fr)_40px_minmax(0,1.2fr)] lg:gap-0" aria-hidden="true">
    <div className="flow-card landing-card rounded-xl border border-line bg-panel p-5 shadow-md" style={step(0)}>
      <p className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-ink-muted">
        <MessageSquareText className="h-3.5 w-3.5" /> 1 · You ask
      </p>
      <p className="mt-3 text-[15px] font-medium leading-snug text-ink">
        How does sleep affect memory in students?
        <span className="flow-caret ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 bg-accent" />
      </p>
      <div className="mt-4 flex flex-wrap gap-1.5 text-[11px]">
        <span className="rounded-md border border-line bg-subtle px-2 py-0.5 text-ink-soft">Standard depth</span>
        <span className="rounded-md border border-accent-line bg-accent-soft px-2 py-0.5 text-accent">Find sources online</span>
      </div>
    </div>

    <FlowLink delay={350} />

    <div className="flow-card landing-card rounded-xl border border-line bg-panel p-5 shadow-md" style={step(450)}>
      <p className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-ink-muted">
        <Globe2 className="h-3.5 w-3.5" /> 2 · Sources are found and read
      </p>
      <ul className="mt-3 grid grid-cols-2 gap-1.5">
        {FLOW_SOURCES.map(([name, kind], index) => (
          <li
            key={name}
            className="flow-chip flex min-w-0 flex-col rounded-lg border border-line bg-canvas/60 px-2.5 py-1.5"
            style={step(600 + index * 110)}
          >
            <span className="truncate text-[12px] font-medium text-ink">{name}</span>
            <span className="text-[10.5px] text-ink-muted">{kind}</span>
          </li>
        ))}
      </ul>
    </div>

    <FlowLink delay={1300} />

    <div className="flow-card landing-card rounded-xl border border-line bg-panel p-5 shadow-md" style={step(1400)}>
      <p className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-ink-muted">
        <Quote className="h-3.5 w-3.5" /> 3 · Cited answer
      </p>
      <p className="mt-3 font-serif text-[14.5px] leading-[1.7] text-ink">
        <span className="flow-line" style={step(1550)}>Students who sleep 7–9 hours remember more of what they studied</span>
        <Marker n={1} />
        <span className="flow-line" style={step(1800)}>, mostly because sleep helps lock in new memories</span>
        <Marker n={2} />.
      </p>
      <div className="flow-chip mt-3 rounded-md border border-info-line bg-info-soft px-2.5 py-1.5 text-[11.5px] text-info" style={step(2100)}>
        <span className="font-medium">Not covered:</span> exam-week caffeine use.
      </div>
    </div>
  </div>
);

const FlowLink: React.FC<{ delay: number }> = ({ delay }) => (
  <div className="flow-link relative mx-auto h-8 w-px lg:h-auto lg:w-full" style={step(delay)}>
    <span className="flow-link-track absolute bg-line-strong" />
    <span className="flow-link-dot absolute h-2 w-2 rounded-full bg-accent" />
  </div>
);

/** Live collaboration: who is here and what they are doing. */
export const CollabPreview: React.FC = () => (
  <div className="landing-card overflow-hidden rounded-xl border border-line bg-panel shadow-md" aria-hidden="true">
    <div className="flex items-center justify-between border-b border-line bg-subtle/50 px-4 py-2.5">
      <p className="text-[13px] font-medium text-ink">Thesis literature review</p>
      <div className="flex -space-x-1.5">
        {[
          ['SR', 'bg-accent text-on-solid'],
          ['SP', 'bg-solid text-on-solid'],
          ['AK', 'bg-subtle text-ink border border-line-strong'],
        ].map(([initials, tone], index) => (
          <span
            key={initials}
            className={`collab-avatar flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-semibold ring-2 ring-panel ${tone}`}
            style={step(200 + index * 140)}
          >
            {initials}
          </span>
        ))}
      </div>
    </div>
    <ul className="divide-y divide-line">
      {[
        ['Shubham', 'Owner', 'asking a question', true],
        ['Santanu', 'Editor', 'uploading slides.pptx', true],
        ['Guest reviewer', 'Viewer', 'viewing the report', false],
      ].map(([name, role, activity, live], index) => (
        <li key={name as string} className="collab-row flex items-center justify-between gap-3 px-4 py-3" style={step(500 + index * 160)}>
          <div className="min-w-0">
            <p className="text-[13px] font-medium text-ink">{name}</p>
            <p className="flex items-center gap-1.5 truncate text-[11.5px] text-ink-muted">
              {live && <span className="preview-breathe h-1.5 w-1.5 rounded-full bg-accent" />}
              {activity}
            </p>
          </div>
          <span className="rounded-md border border-line px-1.5 py-0.5 text-[11px] text-ink-soft">{role}</span>
        </li>
      ))}
    </ul>
  </div>
);
