import React, { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  AudioLines,
  BookOpen,
  Combine,
  Copy,
  FileDown,
  FileText,
  FolderLock,
  Gauge,
  Globe2,
  Image as ImageIcon,
  KeyRound,
  Layers,
  Link2,
  ListOrdered,
  Newspaper,
  PauseCircle,
  Presentation,
  Scale,
  Sheet,
  Video,
} from 'lucide-react';
import { useOptionalAuth } from '../../app/AuthContext';
import { BrandMark } from '../common/BrandMark';
import { AccountAvatar, accountName } from './AccountBits';
import { CollabPreview, EvidencePreview, FlowPreview, ProductPreview, ProjectsPreview } from './ProductPreview';
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

const HERO_TAGS = ['OpenAlex', 'arXiv', 'Crossref', 'Wikipedia', 'News', 'PDF', 'Slides', 'Audio', 'Video'];

export const Hero: React.FC = () => {
  const mediaRef = useHeroParallax();

  return (
  <section className="landing-hero relative overflow-hidden border-b border-line" aria-labelledby="hero-heading">
    <div className="landing-hero-glow pointer-events-none absolute inset-x-0 top-0 h-[520px]" aria-hidden="true" />
    <Container className="relative pb-16 pt-14 sm:pb-24 sm:pt-20">
      <div className="max-w-3xl">
        <h1
          id="hero-heading"
          className="font-serif text-[40px] leading-[1.08] tracking-[-0.02em] text-ink sm:text-[56px] lg:text-[64px]"
        >
          <span className="landing-title-mask">
            <span className="landing-load landing-load--headline-line" style={loadDelay(150)}>
              Ask a research question.
            </span>
          </span>
          <span className="landing-title-mask">
            <span className="landing-load landing-load--headline-line" style={loadDelay(225)}>
              Get an answer you can <span className="landing-underline">check</span>.
            </span>
          </span>
        </h1>
        <p style={loadDelay(300)} className="landing-load mt-6 max-w-2xl text-[17px] leading-relaxed text-ink-soft">
          It finds papers, articles and encyclopedia pages for you, reads your own PDFs, slides,
          sheets, recordings and links, and writes a clear answer where every sentence points to
          the exact source and page it came from.
        </p>
        <div style={loadDelay(375)} className="landing-load mt-8">
          <HeroActions />
        </div>
        <ul style={loadDelay(450)} className="landing-load mt-8 flex flex-wrap gap-1.5" aria-label="Supported sources">
          {HERO_TAGS.map((tag, index) => (
            <li
              key={tag}
              className="landing-tag rounded-full border border-line bg-panel/80 px-2.5 py-1 text-[12px] text-ink-soft"
              style={{ '--tag-delay': `${520 + index * 45}ms` } as React.CSSProperties}
            >
              {tag}
            </li>
          ))}
        </ul>
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

export const Flow: React.FC = () => (
  <section id="flow" className="scroll-mt-16 border-b border-line py-20 sm:py-28" aria-labelledby="flow-heading">
    <Container>
      <SectionHeading id="flow-heading" kicker="See it in action" title="From a question to a cited answer">
        You type a question. The assistant gathers sources, reads them, and only writes what the
        sources support, with a numbered citation on every claim.
      </SectionHeading>
      <Reveal variant="scale" className="mt-14">
        <FlowPreview />
      </Reveal>
    </Container>
  </section>
);

const STEPS = [
  {
    title: 'Add or discover sources',
    body: 'Upload files, paste a web or YouTube link, or switch on “find sources online” so it searches OpenAlex, arXiv, Crossref, Wikipedia and trusted news for you.',
  },
  {
    title: 'Ask in plain language',
    body: 'Pick Quick, Standard or Deep. Your question is matched with both meaning and keyword search, and the best passages are reranked before anything is written.',
  },
  {
    title: 'Read, verify and follow up',
    body: 'Click any citation to see the exact passage and page. Ask follow-up questions on the same report, copy BibTeX, or export it as Markdown.',
  },
];

export const HowItWorks: React.FC = () => (
  <section id="how-it-works" className="scroll-mt-16 border-b border-line bg-subtle/40 py-20 sm:py-28" aria-labelledby="how-heading">
    <Container>
      <SectionHeading id="how-heading" kicker="How it works" title="Add sources, ask, check the answer">
        Answers are written only from the sources you can see. If the sources don’t cover
        something, it says so instead of making it up.
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

const DISCOVERY_SOURCES = [
  { icon: BookOpen, name: 'OpenAlex', body: 'Hundreds of millions of scholarly works, with open-access PDFs read in full.' },
  { icon: Layers, name: 'arXiv', body: 'Preprints in science, maths and computing, straight from the source.' },
  { icon: Link2, name: 'Crossref', body: 'DOI records with authors, journal and year for proper references.' },
  { icon: Globe2, name: 'Wikipedia', body: 'Background and definitions, pulled section by section.' },
  { icon: Newspaper, name: 'Trusted news', body: 'Recent coverage filtered to outlets like Reuters, AP, BBC and The Hindu.' },
];

const FILE_TYPES = [
  { icon: FileText, label: 'PDF & Word', detail: 'Scanned pages are read with OCR' },
  { icon: Presentation, label: 'Slides', detail: '.pptx' },
  { icon: Sheet, label: 'Spreadsheets', detail: '.xlsx' },
  { icon: Globe2, label: 'Web pages', detail: 'Links and .html' },
  { icon: AudioLines, label: 'Audio', detail: 'Transcribed automatically' },
  { icon: Video, label: 'Video & YouTube', detail: 'Speech and key frames' },
  { icon: ImageIcon, label: 'Images', detail: 'Charts and figures described' },
];

export const Sources: React.FC = () => (
  <section id="sources" className="scroll-mt-16 border-b border-line py-20 sm:py-28" aria-labelledby="sources-heading">
    <Container>
      <SectionHeading id="sources-heading" kicker="Sources" title="Bring your own files, or let it find sources for you">
        Discovery uses free, public research services, so there is nothing to sign up for. Every
        source keeps its title, authors, year and link, so citations are ready for your report.
      </SectionHeading>

      <div className="mt-14 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {DISCOVERY_SOURCES.map(({ icon: Icon, name, body }, index) => (
          <Reveal key={name} delay={index * 70} className="landing-card landing-source-card rounded-xl border border-line bg-panel p-5">
            <span className="landing-source-icon flex h-9 w-9 items-center justify-center rounded-lg bg-accent-soft text-accent">
              <Icon className="h-[18px] w-[18px]" strokeWidth={1.75} aria-hidden="true" />
            </span>
            <h3 className="mt-4 text-[15px] font-semibold text-ink">{name}</h3>
            <p className="mt-1.5 text-[13px] leading-relaxed text-ink-soft">{body}</p>
          </Reveal>
        ))}
      </div>

      <Reveal delay={120} className="mt-10 rounded-xl border border-line bg-subtle/40 p-5 sm:p-6">
        <p className="text-[13px] font-medium text-ink">Files and links you can add</p>
        <ul className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {FILE_TYPES.map(({ icon: Icon, label, detail }) => (
            <li key={label} className="landing-filetype flex items-center gap-3 rounded-lg border border-line bg-panel px-3 py-2.5">
              <Icon className="h-4 w-4 shrink-0 text-accent" strokeWidth={1.75} aria-hidden="true" />
              <span className="min-w-0">
                <span className="block text-[13px] font-medium text-ink">{label}</span>
                <span className="block truncate text-[11.5px] text-ink-muted">{detail}</span>
              </span>
            </li>
          ))}
        </ul>
      </Reveal>
    </Container>
  </section>
);

const FEATURES = [
  {
    icon: Combine,
    title: 'Hybrid search',
    body: 'Meaning-based and keyword search run together and are merged, so exact terms and paraphrases both match.',
  },
  {
    icon: ListOrdered,
    title: 'Reranked evidence',
    body: 'A reranking model reorders the candidates so the passages that actually answer the question are the ones used.',
  },
  {
    icon: KeyRound,
    title: 'Many models, your choice',
    body: 'A router tries Gemini, OpenRouter and others in turn, or runs a local model. Add your own OpenAI, Claude, Grok or Groq key if you like.',
  },
  {
    icon: Gauge,
    title: 'Fair, clear credits',
    body: 'Free credits refill every 3 hours and every 2 days. Follow-ups cost a quarter, and failed runs are refunded. Your own key or a local model is unlimited.',
  },
  {
    icon: PauseCircle,
    title: 'Pause, edit and retry',
    body: 'Pause a run, fix the question in place, or switch model if one is busy, without losing your history.',
  },
  {
    icon: Copy,
    title: 'Duplicate detection',
    body: 'Each upload is fingerprinted, so the same file added twice is caught instead of being indexed again.',
  },
  {
    icon: FolderLock,
    title: 'Private by default',
    body: 'Files, projects and reports belong to you. Search never reaches into anyone else’s files unless they share them.',
  },
  {
    icon: FileDown,
    title: 'Export and cite',
    body: 'Download a report as Markdown and copy a BibTeX entry for any source, ready for your references.',
  },
  {
    icon: Scale,
    title: 'Disagreements shown',
    body: 'When sources disagree, both sides are shown with their own citations, instead of one being quietly picked.',
  },
];

export const Features: React.FC = () => (
  <section id="features" className="scroll-mt-16 border-b border-line py-20 sm:py-28" aria-labelledby="features-heading">
    <Container>
      <SectionHeading id="features-heading" kicker="Features" title="Every answer points back to its source" />

      <div className="mt-14 grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
        <Reveal>
          <h3 className="text-xl font-semibold tracking-[-0.015em] text-ink">Projects keep every file in one place</h3>
          <p className="mt-3 text-[15px] leading-relaxed text-ink-soft">
            Group papers, slides, sheets, links and recordings by topic or assignment. A question asked
            inside a project only searches that project, and it can find new sources online and add
            them for you.
          </p>
        </Reveal>
        <Reveal variant="scale" delay={80}>
          <ProjectsPreview />
        </Reveal>
      </div>

      <div className="mt-16 grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
        <Reveal className="lg:order-2">
          <h3 className="text-xl font-semibold tracking-[-0.015em] text-ink">Work on it together, live</h3>
          <p className="mt-3 text-[15px] leading-relaxed text-ink-soft">
            Invite teammates by email or a share link and give each one a role: owner, editor or
            viewer. You see who is online and what they are doing, and new files and answers show up
            for everyone straight away.
          </p>
        </Reveal>
        <Reveal variant="scale" delay={80} className="lg:order-1">
          <CollabPreview />
        </Reveal>
      </div>

      <div className="mt-16 grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
        <Reveal>
          <h3 className="text-xl font-semibold tracking-[-0.015em] text-ink">It tells you when the sources don’t say</h3>
          <p className="mt-3 text-[15px] leading-relaxed text-ink-soft">
            Before writing, it checks whether the passages are enough to answer. When they aren’t,
            the answer is marked as limited instead of being padded out, and gaps are listed under
            “Not covered in the sources”.
          </p>
        </Reveal>
        <Reveal variant="scale" delay={80}>
          <EvidencePreview />
        </Reveal>
      </div>

      <div className="mt-20 grid gap-x-10 gap-y-10 border-t border-line pt-14 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map(({ icon: Icon, title, body }, index) => (
          <Reveal key={title} delay={(index % 3) * 80} className="landing-feature">
            <span className="landing-feature-icon inline-flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-panel">
              <Icon className="h-[18px] w-[18px] text-accent" strokeWidth={1.75} aria-hidden="true" />
            </span>
            <h3 className="mt-4 text-[15px] font-semibold text-ink">{title}</h3>
            <p className="mt-1.5 text-[14px] leading-relaxed text-ink-soft">{body}</p>
          </Reveal>
        ))}
      </div>
    </Container>
  </section>
);

const PIPELINE = [
  ['Read', 'Docling, or a light reader with OCR for scanned pages'],
  ['Transcribe', 'Whisper for audio and video, vision for images'],
  ['Chunk', 'Pages, sections and tables kept together'],
  ['Embed', 'Qwen3 locally, or Cloudflare bge-m3 in the cloud'],
  ['Store', 'PostgreSQL with pgvector and full-text indexes'],
  ['Retrieve', 'Vector + keyword search, reciprocal rank fusion'],
  ['Rerank', 'Qwen3, Cloudflare or Jina reranker'],
  ['Generate', 'Local Ollama, or the cloud model router'],
  ['Cite', 'Every sentence and table cell checked'],
];

export const Pipeline: React.FC = () => (
  <section id="pipeline" className="scroll-mt-16 border-b border-line bg-subtle/50 py-20 sm:py-28" aria-labelledby="pipeline-heading">
    <Container>
      <div className="grid gap-12 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-16">
        <SectionHeading id="pipeline-heading" kicker="Under the hood" title="Open models, one database, runs local or in the cloud">
          The same pipeline runs fully on your own machine with local models, or on a light cloud
          setup. PostgreSQL holds everything: files, passages, vectors and reports.
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
    'The answer is written only from passages taken from your sources, and each sentence carries a citation to the passage it relies on. If the passages are not enough, the answer is marked as limited.',
  ],
  [
    'Where do the sources come from?',
    'From the files and links you add, and, if you switch it on, from OpenAlex, arXiv, Crossref, Wikipedia and trusted news outlets. Open-access papers are read in full when a free PDF exists.',
  ],
  [
    'Which file types can I add?',
    'PDF, Word, PowerPoint, Excel, HTML, images, audio and video files, plus web page and YouTube links. Files are checked, fingerprinted to catch duplicates, then read and indexed in the background.',
  ],
  [
    'Can other people see my documents?',
    'Only if you share a project or research with them. Each person gets a role (owner, editor or viewer), and everything else stays tied to your account.',
  ],
  [
    'Which AI models does it use?',
    'A local model through Ollama, or a cloud router that tries Gemini, then OpenRouter and other free models. You can also add your own OpenAI, Claude, Grok or Groq key, which is not limited by credits.',
  ],
  [
    'What are credits?',
    'Each model gives you 20 runs every 3 hours and 100 every 2 days. A follow-up question costs a quarter of a run, and runs that fail or find too little evidence are refunded.',
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
            Start with the question you already have.
          </h2>
          <p className="mt-3 text-[15px] leading-relaxed text-ink-soft">
            Create a project, add a few files or let it find sources, and ask your first question.
          </p>
        </div>
        <FinalCtaActions />
      </Reveal>
    </Container>
  </section>
);

const HeroActions: React.FC = () => {
  const auth = useOptionalAuth();
  const navigate = useNavigate();
  const user = auth?.user ?? null;

  const handleSwitchAccount = async () => {
    await auth?.logout();
    navigate('/login');
  };

  if (user) {
    return (
      <div
        data-testid="hero-account-card"
        className="landing-account-card w-full max-w-xl rounded-xl border border-line bg-panel p-4 shadow-sm sm:p-5"
      >
        <div className="flex items-center gap-3.5">
          <AccountAvatar user={user} size="lg" />
          <div className="min-w-0">
            <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="truncate text-[17px] font-semibold text-ink">Welcome back, {accountName(user)}</span>
              <span className="inline-flex items-center gap-1 rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-medium text-accent">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" aria-hidden="true" />
                Signed in
              </span>
            </p>
            <p className="mt-0.5 truncate text-[13px] text-ink-muted">{user.email}</p>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2.5">
          <Link
            to="/research/new"
            className="landing-btn group inline-flex h-11 items-center gap-2 rounded-md bg-solid px-5 text-sm font-medium text-on-solid shadow-sm transition-colors hover:bg-solid-hover"
          >
            Open workspace
            <ArrowRight className="h-4 w-4" />
          </Link>
          <button
            type="button"
            onClick={() => { void handleSwitchAccount(); }}
            className="landing-btn inline-flex h-11 items-center rounded-md border border-line-strong bg-panel px-4 text-sm font-medium text-ink shadow-xs transition-colors hover:bg-subtle"
          >
            Switch account
          </button>
          <button
            type="button"
            onClick={() => { void auth?.logout(); }}
            className="inline-flex h-11 items-center rounded-md px-3 text-sm font-medium text-ink-soft transition-colors hover:bg-subtle hover:text-ink"
          >
            Sign out
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
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
  );
};

const FinalCtaActions: React.FC = () => {
  const auth = useOptionalAuth();
  const user = auth?.user ?? null;

  if (user) {
    return (
      <div className="flex flex-wrap gap-3">
        <Link
          to="/research/new"
          className="landing-btn group inline-flex h-11 items-center gap-2 rounded-md bg-solid px-5 text-sm font-medium text-on-solid shadow-sm transition-colors hover:bg-solid-hover"
        >
          Open workspace
          <ArrowRight className="h-4 w-4" />
        </Link>
        <button
          type="button"
          onClick={() => { void auth?.logout(); }}
          className="landing-btn inline-flex h-11 items-center rounded-md border border-line-strong bg-panel px-5 text-sm font-medium text-ink transition-colors hover:bg-subtle"
        >
          Sign out
        </button>
      </div>
    );
  }

  return (
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
  );
};

export const LandingFooter: React.FC = () => {
  const auth = useOptionalAuth();
  const user = auth?.user ?? null;

  return (
    <footer className="border-t border-line">
      <Container className="flex flex-col gap-6 py-10 sm:flex-row sm:items-center sm:justify-between">
        <Reveal>
          <BrandMark nameClassName="text-[14px]" />
          <p className="mt-2 text-[13px] text-ink-muted">Answers from papers, files and the web, with the sources attached.</p>
        </Reveal>
        <Reveal delay={80}>
        <nav aria-label="Footer" className="flex flex-wrap gap-x-6 gap-y-2 text-[13px] text-ink-soft">
          <a href="#how-it-works" onClick={scrollToHash} className="hover:text-ink">How it works</a>
          <a href="#sources" onClick={scrollToHash} className="hover:text-ink">Sources</a>
          <a href="#features" onClick={scrollToHash} className="hover:text-ink">Features</a>
          <a href="#faq" onClick={scrollToHash} className="hover:text-ink">FAQ</a>
          {user ? (
            <>
              <Link to="/research/new" className="hover:text-ink">Open workspace</Link>
              <button type="button" onClick={() => { void auth?.logout(); }} className="hover:text-ink">Sign out</button>
            </>
          ) : (
            <>
              <Link to="/login" className="hover:text-ink">Sign in</Link>
              <Link to="/register" className="hover:text-ink">Create account</Link>
            </>
          )}
        </nav>
        </Reveal>
      </Container>
    </footer>
  );
};
