import React, { useEffect, useRef, useState } from 'react';
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
import { Reveal, loadDelay, scrollToHash, usePrefersReducedMotion } from './Motion';

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
    <Reveal as="p" className="text-[13px] font-medium text-accent">{kicker}</Reveal>
    <Reveal variant="clip" delay={60}>
      <h2 id={id} className="mt-2 text-[28px] font-semibold leading-tight tracking-[-0.025em] text-ink sm:text-[34px]">
        {title}
      </h2>
    </Reveal>
    {children && (
      <Reveal as="p" delay={120} className="mt-4 text-base leading-relaxed text-ink-soft">
        {children}
      </Reveal>
    )}
  </div>
);

const useHeroParallax = () => {
  const ref = useRef<HTMLDivElement>(null);
  const reducedMotion = usePrefersReducedMotion();

  useEffect(() => {
    const media = ref.current;
    if (!media || reducedMotion) return;
    let frame = 0;
    const update = () => {
      frame = 0;
      const rect = media.getBoundingClientRect();
      const progress = Math.max(0, Math.min(1, (window.innerHeight - rect.top) / (window.innerHeight + rect.height)));
      media.style.setProperty('--hero-parallax', `${Math.round(progress * 28)}px`);
    };
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(update);
    };
    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [reducedMotion]);

  return ref;
};

export const Hero: React.FC = () => {
  const mediaRef = useHeroParallax();

  return (
  <section className="relative overflow-hidden border-b border-line" aria-labelledby="hero-heading">
    <Container className="pb-16 pt-14 sm:pb-24 sm:pt-20">
      <div className="max-w-3xl">
        <p style={loadDelay(90)} className="landing-load inline-flex items-center gap-2 rounded-full border border-line bg-panel px-3 py-1 text-xs text-ink-soft">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
          Runs on your own machine with a local model
        </p>
        <h1
          id="hero-heading"
          className="mt-6 font-serif text-[40px] leading-[1.08] tracking-[-0.025em] text-ink sm:text-[56px] lg:text-[64px]"
        >
          <span className="landing-title-mask">
            <span className="landing-load landing-load--headline-line" style={loadDelay(150)}>
              Ask your papers a question.
            </span>
          </span>
          <span className="landing-title-mask">
            <span className="landing-load landing-load--headline-line" style={loadDelay(225)}>
              Check every answer against the page.
            </span>
          </span>
        </h1>
        <p style={loadDelay(300)} className="landing-load mt-6 max-w-2xl text-[17px] leading-relaxed text-ink-soft">
          Upload PDF and DOCX files, ask in plain language, and get a written answer where each
          sentence cites the document, page and passage it came from.
        </p>
        <div style={loadDelay(375)} className="landing-load mt-8 flex flex-wrap items-center gap-3">
          <Link
            to="/register"
            className="landing-btn group inline-flex h-11 items-center gap-2 rounded-md bg-solid px-5 text-sm font-medium text-on-solid shadow-sm transition-colors hover:bg-solid-hover"
          >
            Create an account
            <ArrowRight className="h-4 w-4" />
          </Link>
          <Link
            to="/login"
            className="landing-btn inline-flex h-11 items-center rounded-md border border-line-strong bg-panel px-5 text-sm font-medium text-ink shadow-xs transition-colors hover:bg-subtle"
          >
            Sign in
          </Link>
        </div>
      </div>

      <div ref={mediaRef} className="landing-parallax mt-14 sm:mt-20">
        <div className="landing-load landing-load--media" style={loadDelay(500)}>
          <ProductPreview />
        </div>
      </div>
    </Container>
  </section>
  );
};

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
          <Reveal as="li" key={step.title} delay={index * 80} className="landing-step bg-panel p-6 sm:p-8">
            <span className="landing-step-num font-mono text-xs text-ink-muted">0{index + 1}</span>
            <h3 className="mt-4 text-base font-semibold text-ink">{step.title}</h3>
            <p className="mt-2 text-[14px] leading-relaxed text-ink-soft">{step.body}</p>
          </Reveal>
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
        <Reveal>
          <h3 className="text-xl font-semibold tracking-[-0.015em] text-ink">Projects keep each question in scope</h3>
          <p className="mt-3 text-[15px] leading-relaxed text-ink-soft">
            Group papers by topic or assignment. A question asked inside a project only searches that
            project’s documents, so an answer about one literature review never borrows from another.
          </p>
        </Reveal>
        <Reveal variant="scale" delay={80}>
          <ProjectsPreview />
        </Reveal>
      </div>

      <div className="mt-16 grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
        <Reveal className="lg:order-2">
          <h3 className="text-xl font-semibold tracking-[-0.015em] text-ink">It tells you when the papers don’t say</h3>
          <p className="mt-3 text-[15px] leading-relaxed text-ink-soft">
            Before writing, the assistant checks whether the retrieved passages are enough to answer.
            When they aren’t, the answer is marked as limited instead of being padded out.
          </p>
        </Reveal>
        <Reveal variant="scale" delay={80} className="lg:order-1">
          <EvidencePreview />
        </Reveal>
      </div>

      <div className="mt-20 grid gap-x-10 gap-y-10 border-t border-line pt-14 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map(({ icon: Icon, title, body }, index) => (
          <Reveal key={title} delay={(index % 3) * 80} className="landing-feature">
            <Icon className="h-5 w-5 text-accent" strokeWidth={1.75} aria-hidden="true" />
            <h3 className="mt-4 text-[15px] font-semibold text-ink">{title}</h3>
            <p className="mt-1.5 text-[14px] leading-relaxed text-ink-soft">{body}</p>
          </Reveal>
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

        <Reveal as="ol" variant="scale" className="overflow-hidden rounded-xl border border-line bg-panel">
          {PIPELINE.map(([stage, detail], index) => (
            <Reveal
              as="li"
              key={stage}
              delay={160 + index * 60}
              className="landing-row grid grid-cols-[36px_96px_minmax(0,1fr)] items-baseline gap-3 border-b border-line px-5 py-3.5 last:border-b-0 sm:grid-cols-[40px_120px_minmax(0,1fr)]"
            >
              <span className="font-mono text-xs tabular-nums text-ink-muted">{String(index + 1).padStart(2, '0')}</span>
              <span className="text-[14px] font-medium text-ink">{stage}</span>
              <span className="text-[14px] text-ink-soft">{detail}</span>
            </Reveal>
          ))}
        </Reveal>
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

const FaqItem: React.FC<{ question: string; answer: string; index: number }> = ({ question, answer, index }) => {
  const [open, setOpen] = useState(false);
  const panelId = `faq-answer-${index}`;

  return (
    <div className="py-1">
      <h3>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((value) => !value)}
          className="landing-faq-question flex w-full cursor-pointer items-center justify-between gap-6 rounded-sm py-4 text-left text-[15px] font-medium text-ink"
        >
          {question}
          <span
            aria-hidden="true"
            className={`landing-faq-icon relative h-3.5 w-3.5 shrink-0 text-ink-muted before:absolute before:left-0 before:top-1/2 before:h-px before:w-full before:bg-current after:absolute after:left-1/2 after:top-0 after:h-full after:w-px after:bg-current ${
              open ? 'rotate-180 after:scale-y-0' : ''
            }`}
          />
        </button>
      </h3>
      <div id={panelId} role="region" aria-hidden={!open} className={`landing-faq-answer ${open ? 'is-open' : ''}`}>
        <div>
          <p className="max-w-2xl pb-5 pr-8 text-[14px] leading-relaxed text-ink-soft">{answer}</p>
        </div>
      </div>
    </div>
  );
};

export const FAQ: React.FC = () => (
  <section id="faq" className="scroll-mt-16 border-b border-line py-20 sm:py-28" aria-labelledby="faq-heading">
    <Container>
      <div className="grid gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-16">
        <SectionHeading id="faq-heading" kicker="FAQ" title="Common questions" />
        <Reveal delay={120} className="divide-y divide-line border-y border-line">
          {FAQS.map(([question, answer], index) => (
            <FaqItem key={question} question={question} answer={answer} index={index} />
          ))}
        </Reveal>
      </div>
    </Container>
  </section>
);

export const FinalCta: React.FC = () => (
  <section className="py-20 sm:py-24" aria-labelledby="cta-heading">
    <Container>
      <Reveal variant="scale" className="flex flex-col items-start justify-between gap-8 rounded-xl border border-line bg-panel p-8 shadow-sm sm:p-12 lg:flex-row lg:items-center">
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
            className="landing-btn group inline-flex h-11 items-center gap-2 rounded-md bg-solid px-5 text-sm font-medium text-on-solid shadow-sm transition-colors hover:bg-solid-hover"
          >
            Create an account
            <ArrowRight className="h-4 w-4" />
          </Link>
          <Link
            to="/login"
            className="landing-btn inline-flex h-11 items-center rounded-md border border-line-strong bg-panel px-5 text-sm font-medium text-ink transition-colors hover:bg-subtle"
          >
            Sign in
          </Link>
        </div>
      </Reveal>
    </Container>
  </section>
);

export const LandingFooter: React.FC = () => (
  <footer className="border-t border-line">
    <Container className="flex flex-col gap-6 py-10 sm:flex-row sm:items-center sm:justify-between">
      <Reveal>
        <BrandMark nameClassName="text-[14px]" />
        <p className="mt-2 text-[13px] text-ink-muted">Answers from your own papers, with the sources attached.</p>
      </Reveal>
      <Reveal delay={80}>
      <nav aria-label="Footer" className="flex flex-wrap gap-x-6 gap-y-2 text-[13px] text-ink-soft">
        <a href="#how-it-works" onClick={scrollToHash} className="hover:text-ink">How it works</a>
        <a href="#features" onClick={scrollToHash} className="hover:text-ink">Features</a>
        <a href="#faq" onClick={scrollToHash} className="hover:text-ink">FAQ</a>
        <Link to="/login" className="hover:text-ink">Sign in</Link>
        <Link to="/register" className="hover:text-ink">Create account</Link>
      </nav>
      </Reveal>
    </Container>
  </footer>
);
