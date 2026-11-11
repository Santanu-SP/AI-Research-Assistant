import React from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  Combine,
  Copy,
  FileDown,
  FolderLock,
  ListOrdered,
  RefreshCw,
} from 'lucide-react';
import { BrandMark } from '../common/BrandMark';
import { EvidencePreview, ProductPreview, ProjectsPreview } from './ProductPreview';

const Container: React.FC<React.PropsWithChildren<{ className?: string }>> = ({ className = '', children }) => (
  <div className={`mx-auto max-w-6xl px-5 sm:px-8 ${className}`}>{children}</div>
);

const SectionHeading: React.FC<{ id: string; kicker: string; title: string; children?: React.ReactNode }> = ({
  id,
  kicker,
  title,
  children,
}) => (
  <div className="max-w-2xl">
    <p className="text-[13px] font-medium text-accent">{kicker}</p>
    <h2 id={id} className="mt-2 text-[28px] font-semibold leading-tight tracking-[-0.025em] text-ink sm:text-[34px]">
      {title}
    </h2>
    {children && <p className="mt-4 text-base leading-relaxed text-ink-soft">{children}</p>}
  </div>
);

export const Hero: React.FC = () => (
  <section className="relative overflow-hidden border-b border-line" aria-labelledby="hero-heading">
    <Container className="pb-16 pt-14 sm:pb-24 sm:pt-20">
      <div className="max-w-3xl">
        <p className="inline-flex items-center gap-2 rounded-full border border-line bg-panel px-3 py-1 text-xs text-ink-soft">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
          Runs on your own machine with a local model
        </p>
        <h1
          id="hero-heading"
          className="mt-6 font-serif text-[40px] leading-[1.08] tracking-[-0.025em] text-ink sm:text-[56px] lg:text-[64px]"
        >
          Ask your papers a question. Check every answer against the page.
        </h1>
        <p className="mt-6 max-w-2xl text-[17px] leading-relaxed text-ink-soft">
          Upload PDF and DOCX files, ask in plain language, and get a written answer where each
          sentence cites the document, page and passage it came from.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-3">
          <Link
            to="/register"
            className="group inline-flex h-11 items-center gap-2 rounded-md bg-solid px-5 text-sm font-medium text-on-solid shadow-sm transition-colors hover:bg-solid-hover"
          >
            Create an account
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
          </Link>
          <Link
            to="/login"
            className="inline-flex h-11 items-center rounded-md border border-line-strong bg-panel px-5 text-sm font-medium text-ink shadow-xs transition-colors hover:bg-subtle"
          >
            Sign in
          </Link>
        </div>
      </div>

      <div className="mt-14 sm:mt-20">
        <ProductPreview />
      </div>
    </Container>
  </section>
);

const STEPS = [
  {
    title: 'Upload your papers',
    body: 'PDF and DOCX files are parsed with Docling, split into sections, tables and captions, and indexed in the background. Duplicates are caught before they are stored.',
  },
  {
    title: 'Ask a question',
    body: 'Your question is matched against the papers with both semantic and keyword search, and the strongest passages are reranked before anything is written.',
  },
  {
    title: 'Read and verify',
    body: 'The answer comes back with numbered citations. Click one to see the exact excerpt, page and section it is based on.',
  },
];

export const HowItWorks: React.FC = () => (
  <section id="how-it-works" className="scroll-mt-16 border-b border-line py-20 sm:py-28" aria-labelledby="how-heading">
    <Container>
      <SectionHeading id="how-heading" kicker="How it works" title="From a folder of papers to an answer you can check">
        Three steps. The models run locally, so your papers are not sent to an outside AI service.
      </SectionHeading>

      <ol className="mt-14 grid gap-px overflow-hidden rounded-xl border border-line bg-line md:grid-cols-3">
        {STEPS.map((step, index) => (
          <li key={step.title} className="bg-panel p-6 sm:p-8">
            <span className="font-mono text-xs text-ink-muted">0{index + 1}</span>
            <h3 className="mt-4 text-base font-semibold text-ink">{step.title}</h3>
            <p className="mt-2 text-[14px] leading-relaxed text-ink-soft">{step.body}</p>
          </li>
        ))}
      </ol>
    </Container>
  </section>
);

const FEATURES = [
  {
    icon: Combine,
    title: 'Hybrid search',
    body: 'Vector search and full-text search run together and are merged with reciprocal rank fusion, so exact terms and paraphrases both match.',
  },
  {
    icon: ListOrdered,
    title: 'Reranked evidence',
    body: 'A reranking model reorders the candidates so the passages that actually answer the question are the ones used.',
  },
  {
    icon: Copy,
    title: 'Duplicate detection',
    body: 'Each upload is fingerprinted, so the same paper added twice is flagged instead of being indexed again.',
  },
  {
    icon: RefreshCw,
    title: 'Background indexing',
    body: 'Uploads return straight away. Parsing and indexing run in a job queue with retries, and a failed document can be retried from the list.',
  },
  {
    icon: FolderLock,
    title: 'Private by default',
    body: 'Documents, projects and reports belong to your account. Retrieval never reaches into another user’s files.',
  },
  {
    icon: FileDown,
    title: 'Export to Markdown',
    body: 'Download a report with its references to paste into notes, a draft or a literature review.',
  },
];

export const Features: React.FC = () => (
  <section id="features" className="scroll-mt-16 border-b border-line py-20 sm:py-28" aria-labelledby="features-heading">
    <Container>
      <SectionHeading id="features-heading" kicker="Features" title="Built around the evidence, not the chat window" />

      <div className="mt-14 grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
        <div>
          <h3 className="text-xl font-semibold tracking-[-0.015em] text-ink">Projects keep each question in scope</h3>
          <p className="mt-3 text-[15px] leading-relaxed text-ink-soft">
            Group papers by topic or assignment. A question asked inside a project only searches that
            project’s documents, so an answer about one literature review never borrows from another.
          </p>
        </div>
        <ProjectsPreview />
      </div>

      <div className="mt-16 grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
        <div className="lg:order-2">
          <h3 className="text-xl font-semibold tracking-[-0.015em] text-ink">It tells you when the papers don’t say</h3>
          <p className="mt-3 text-[15px] leading-relaxed text-ink-soft">
            Before writing, the assistant checks whether the retrieved passages are enough to answer.
            When they aren’t, the answer is marked as limited instead of being padded out.
          </p>
        </div>
        <div className="lg:order-1">
          <EvidencePreview />
        </div>
      </div>

      <div className="mt-20 grid gap-x-10 gap-y-10 border-t border-line pt-14 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map(({ icon: Icon, title, body }) => (
          <div key={title}>
            <Icon className="h-5 w-5 text-accent" strokeWidth={1.75} aria-hidden="true" />
            <h3 className="mt-4 text-[15px] font-semibold text-ink">{title}</h3>
            <p className="mt-1.5 text-[14px] leading-relaxed text-ink-soft">{body}</p>
          </div>
        ))}
      </div>
    </Container>
  </section>
);

const PIPELINE = [
  ['Parse', 'Docling, with a pypdf fallback'],
  ['Chunk', 'HybridChunker with pages, sections and tables kept'],
  ['Embed', 'Qwen3 embeddings'],
  ['Store', 'PostgreSQL with pgvector and full-text indexes'],
  ['Retrieve', 'Vector + keyword search, reciprocal rank fusion'],
  ['Rerank', 'Qwen3 reranker'],
  ['Generate', 'qwen3.5:9b through Ollama'],
  ['Cite', 'Sentence-level citation validation'],
];

export const Pipeline: React.FC = () => (
  <section id="pipeline" className="scroll-mt-16 border-b border-line bg-subtle/50 py-20 sm:py-28" aria-labelledby="pipeline-heading">
    <Container>
      <div className="grid gap-12 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-16">
        <SectionHeading id="pipeline-heading" kicker="Under the hood" title="Open models, one database, no hosted AI service">
          Retrieval and generation run locally. PostgreSQL is the single source of truth for
          documents, chunks, vectors and reports.
        </SectionHeading>

        <ol className="overflow-hidden rounded-xl border border-line bg-panel">
          {PIPELINE.map(([stage, detail], index) => (
            <li
              key={stage}
              className="grid grid-cols-[36px_96px_minmax(0,1fr)] items-baseline gap-3 border-b border-line px-5 py-3.5 last:border-b-0 sm:grid-cols-[40px_120px_minmax(0,1fr)]"
            >
              <span className="font-mono text-xs tabular-nums text-ink-muted">{String(index + 1).padStart(2, '0')}</span>
              <span className="text-[14px] font-medium text-ink">{stage}</span>
              <span className="text-[14px] text-ink-soft">{detail}</span>
            </li>
          ))}
        </ol>
      </div>
    </Container>
  </section>
);

const FAQS = [
  [
    'What does “grounded” mean here?',
    'The answer is written only from passages retrieved from your own indexed documents, and each sentence carries a citation to the passage it relies on. If the passages are not enough, the answer is marked as limited.',
  ],
  [
    'Which file types can I upload?',
    'PDF and DOCX. Files are checked, fingerprinted to catch duplicates, and then parsed and indexed in the background.',
  ],
  [
    'Can other users see or search my documents?',
    'No. Documents, projects and reports are tied to your account, and every search is filtered to your own files. Inside a project, only that project’s documents are searched.',
  ],
  [
    'Which models does it use?',
    'Qwen3 models for embeddings and reranking, and qwen3.5:9b through Ollama for writing the answer. All of them run locally.',
  ],
  [
    'What happens if a document fails to process?',
    'It is marked as failed with a short reason, and you can retry it from the documents list once the problem is fixed.',
  ],
] as const;

export const FAQ: React.FC = () => (
  <section id="faq" className="scroll-mt-16 border-b border-line py-20 sm:py-28" aria-labelledby="faq-heading">
    <Container>
      <div className="grid gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-16">
        <SectionHeading id="faq-heading" kicker="FAQ" title="Common questions" />
        <div className="divide-y divide-line border-y border-line">
          {FAQS.map(([question, answer]) => (
            <details key={question} className="group py-1">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-6 rounded-sm py-4 text-[15px] font-medium text-ink [&::-webkit-details-marker]:hidden">
                {question}
                <span
                  aria-hidden="true"
                  className="relative h-3.5 w-3.5 shrink-0 text-ink-muted before:absolute before:left-0 before:top-1/2 before:h-px before:w-full before:bg-current after:absolute after:left-1/2 after:top-0 after:h-full after:w-px after:bg-current after:transition-transform group-open:after:scale-y-0"
                />
              </summary>
              <p className="max-w-2xl pb-5 pr-8 text-[14px] leading-relaxed text-ink-soft">{answer}</p>
            </details>
          ))}
        </div>
      </div>
    </Container>
  </section>
);

export const FinalCta: React.FC = () => (
  <section className="py-20 sm:py-24" aria-labelledby="cta-heading">
    <Container>
      <div className="flex flex-col items-start justify-between gap-8 rounded-xl border border-line bg-panel p-8 shadow-sm sm:p-12 lg:flex-row lg:items-center">
        <div className="max-w-xl">
          <h2 id="cta-heading" className="font-serif text-[28px] leading-tight tracking-[-0.015em] text-ink sm:text-[34px]">
            Start with the papers you already have.
          </h2>
          <p className="mt-3 text-[15px] leading-relaxed text-ink-soft">
            Create a project, upload a few PDFs and ask your first question.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link
            to="/register"
            className="group inline-flex h-11 items-center gap-2 rounded-md bg-solid px-5 text-sm font-medium text-on-solid shadow-sm transition-colors hover:bg-solid-hover"
          >
            Create an account
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
          </Link>
          <Link
            to="/login"
            className="inline-flex h-11 items-center rounded-md border border-line-strong bg-panel px-5 text-sm font-medium text-ink transition-colors hover:bg-subtle"
          >
            Sign in
          </Link>
        </div>
      </div>
    </Container>
  </section>
);

export const LandingFooter: React.FC = () => (
  <footer className="border-t border-line">
    <Container className="flex flex-col gap-6 py-10 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <BrandMark nameClassName="text-[14px]" />
        <p className="mt-2 text-[13px] text-ink-muted">Answers from your own papers, with the sources attached.</p>
      </div>
      <nav aria-label="Footer" className="flex flex-wrap gap-x-6 gap-y-2 text-[13px] text-ink-soft">
        <a href="#how-it-works" className="hover:text-ink">How it works</a>
        <a href="#features" className="hover:text-ink">Features</a>
        <a href="#faq" className="hover:text-ink">FAQ</a>
        <Link to="/login" className="hover:text-ink">Sign in</Link>
        <Link to="/register" className="hover:text-ink">Create account</Link>
      </nav>
    </Container>
  </footer>
);
