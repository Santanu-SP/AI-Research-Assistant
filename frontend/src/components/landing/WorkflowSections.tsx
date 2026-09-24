import React from 'react';
import { ArrowDown, Binary, BookOpenCheck, Boxes, Database, FileCheck2, FileText, Fingerprint, GitMerge, ScanSearch, SearchCheck, ShieldCheck, Sparkles, UserRoundCheck } from 'lucide-react';
import { ArrowLink, Eyebrow, Reveal } from './LandingPrimitives';

const workflow = [
  [FileText, 'Upload PDFs'],
  [Boxes, 'Extract & chunk'],
  [Binary, 'Qwen embeddings'],
  [Database, 'PostgreSQL + pgvector'],
  [GitMerge, 'Hybrid retrieval'],
  [ScanSearch, 'Reranking'],
  [Sparkles, 'Grounded synthesis'],
  [FileCheck2, 'Validated citations'],
] as const;

const workflowDelays = [80, 200, 320, 440, 920, 800, 680, 560];

export const WorkflowSection: React.FC = () => (
  <section id="workflow" className="landing-workflow" aria-labelledby="workflow-heading">
    <div className="landing-container">
      <div className="landing-section-intro landing-section-intro--center">
        <Reveal><Eyebrow>Workflow</Eyebrow></Reveal>
        <Reveal variant="clip" delay={60}><h2 id="workflow-heading" className="landing-section-title">From paper to evidence,<br />in one research flow.</h2></Reveal>
        <Reveal delay={120}><p>Your documents move through a grounded retrieval pipeline before evidence is shown back to you.</p></Reveal>
      </div>
      <Reveal variant="scale" className="workflow-map">
        <div className="workflow-map__rail workflow-map__rail--top" />
        <div className="workflow-map__rail workflow-map__rail--turn" />
        <div className="workflow-map__rail workflow-map__rail--bottom" />
        {workflow.map(([Icon, title], index) => (
          <React.Fragment key={title}>
            <div className={`workflow-node workflow-node--${index}`} style={{ '--node-delay': `${workflowDelays[index]}ms` } as React.CSSProperties}>
              <span><Icon size={20} strokeWidth={1.55} /></span>
              <strong>{title}</strong>
              <small>{index < 4 ? 'Prepare' : index < 6 ? 'Retrieve' : 'Answer'}</small>
            </div>
            {index === 3 && <div className="workflow-turn"><ArrowDown size={17} /></div>}
          </React.Fragment>
        ))}
        <div className="workflow-pulse workflow-pulse--one" /><div className="workflow-pulse workflow-pulse--two" />
      </Reveal>
      <p className="workflow-note">Retrieval is active today. Reranking, grounded synthesis, and validated citations show the planned continuation of the local pipeline.</p>
    </div>
  </section>
);

const benefits = [
  { icon: BookOpenCheck, title: 'Evidence-first', copy: 'Answers remain connected to the passages that support them.', visual: 'citation' },
  { icon: GitMerge, title: 'Hybrid retrieval', copy: 'Semantic meaning and exact terminology work together to find stronger research evidence.', visual: 'retrieval' },
  { icon: Binary, title: 'Local AI pipeline', copy: 'Embedding, retrieval, reranking, and generation are designed around a local RAG workflow.', visual: 'pipeline' },
  { icon: FileText, title: 'Your document workspace', copy: 'Upload and organize the papers relevant to your own research questions.', visual: 'documents' },
] as const;

const BenefitVisual: React.FC<{ type: string }> = ({ type }) => {
  if (type === 'citation') return <div className="benefit-visual benefit-citation"><p>Evidence can be inspected at the source.</p><span>[S1] Page 4 · Methods</span><span>[S2] Page 9 · Results</span></div>;
  if (type === 'retrieval') return <div className="benefit-visual benefit-retrieval"><div><i>Semantic</i><b>0.92</b></div><div><i>Keyword</i><b>RAG</b></div><span>Fused evidence</span></div>;
  if (type === 'pipeline') return <div className="benefit-visual benefit-pipeline"><span>Qwen</span><i /><span>pgvector</span><i /><span>Evidence</span></div>;
  return <div className="benefit-visual benefit-documents"><span><FileText size={15} /> papers.pdf <b>Indexed</b></span><span><FileText size={15} /> methods.pdf <b>Indexed</b></span><span><FileText size={15} /> notes.pdf <b>Ready</b></span></div>;
};

export const BenefitsSection: React.FC = () => (
  <section className="landing-benefits" aria-labelledby="benefits-heading">
    <div className="landing-container">
      <div className="benefits-heading-row">
        <div><Reveal><Eyebrow>Why this approach</Eyebrow></Reveal><Reveal variant="clip" delay={60}><h2 id="benefits-heading" className="landing-section-title">Built for research<br />you can inspect.</h2></Reveal></div>
        <Reveal delay={100}><ArrowLink to="/register" tone="outline">Create your workspace</ArrowLink></Reveal>
      </div>
      <div className="benefits-grid">
        {benefits.map(({ icon: Icon, title, copy, visual }, index) => (
          <Reveal key={title} delay={index * 80} className={`benefit-card benefit-card--${index + 1}`}>
            <div className="benefit-card__copy"><span><Icon size={18} /></span><h3>{title}</h3><p>{copy}</p></div>
            <BenefitVisual type={visual} />
          </Reveal>
        ))}
      </div>
    </div>
  </section>
);

export const PrivacySection: React.FC = () => (
  <section id="privacy" className="landing-privacy" aria-labelledby="privacy-heading">
    <div className="landing-container privacy-grid">
      <div className="privacy-copy">
        <Reveal><Eyebrow>Research workspace</Eyebrow></Reveal>
        <Reveal variant="clip" delay={60}><h2 id="privacy-heading" className="landing-section-title">Your sources.<br />Your research context.</h2></Reveal>
        <Reveal delay={120}><p>Your authenticated workspace scopes retrieval to the papers you own, while local model components keep the research path inspectable.</p></Reveal>
        <div className="privacy-points">
          {[['User-scoped documents', UserRoundCheck], ['Local model path', Fingerprint], ['Evidence traceability', SearchCheck]].map(([label, Icon], index) => (
            <Reveal key={label as string} delay={160 + index * 70}><span><Icon size={18} />{label as string}</span></Reveal>
          ))}
        </div>
      </div>
      <Reveal variant="scale" className="privacy-orbit" aria-label="User-owned research pipeline illustration">
        <div className="privacy-orbit__glow" />
        <div className="privacy-orbit__ring privacy-orbit__ring--outer" />
        <div className="privacy-orbit__ring privacy-orbit__ring--inner" />
        <i className="privacy-orbit__connector privacy-orbit__connector--one" aria-hidden="true" />
        <i className="privacy-orbit__connector privacy-orbit__connector--two" aria-hidden="true" />
        <i className="privacy-orbit__connector privacy-orbit__connector--three" aria-hidden="true" />
        <div className="privacy-orbit__core"><ShieldCheck size={26} /><strong>Your workspace</strong><small>Authenticated & scoped</small></div>
        <span className="privacy-orbit__node privacy-orbit__node--one"><FileText size={17} /> Owned documents</span>
        <span className="privacy-orbit__node privacy-orbit__node--two"><Database size={17} /> Local retrieval</span>
        <span className="privacy-orbit__node privacy-orbit__node--three"><BookOpenCheck size={17} /> Evidence</span>
      </Reveal>
    </div>
  </section>
);
