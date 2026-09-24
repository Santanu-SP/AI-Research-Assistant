import React, { useEffect, useRef, useState } from 'react';
import { BookOpenCheck, DatabaseZap, FileLock2, FileSearch, Quote, Search, ShieldCheck } from 'lucide-react';
import { Eyebrow, Reveal } from './LandingPrimitives';

const features = [
  {
    badge: 'Hybrid Retrieval',
    title: 'Search across your papers',
    copy: 'Semantic search and exact-term retrieval work together to surface the passages most relevant to your question.',
  },
  {
    badge: 'Evidence',
    title: 'Trace every answer',
    copy: 'Keep the paper, page, section, and supporting excerpt attached to the research result so evidence never disappears behind the answer.',
  },
  {
    badge: 'Private Research',
    title: 'Your workspace stays yours',
    copy: 'User-scoped documents and local AI components keep research isolated inside your own workspace.',
  },
] as const;

const RetrievalVisual = () => (
  <div className="feature-visual feature-retrieval">
    <div className="feature-window__bar"><span /><span /><span /><small>Evidence search</small></div>
    <div className="feature-query"><Search size={17} /><span>How do retrieval systems reduce hallucination?</span></div>
    <div className="retrieval-columns">
      <div><small>SEMANTIC MATCHES</small><div className="match-card"><span>0.91</span><p>Grounding generation in retrieved passages reduces unsupported claims...</p></div><div className="match-card"><span>0.86</span><p>External evidence constrains model output at inference time...</p></div></div>
      <div><small>EXACT-TERM MATCHES</small><div className="match-card"><span>RAG</span><p>Retrieval-augmented generation combines parametric and non-parametric memory...</p></div><div className="match-card"><span>DPR</span><p>Dense passage retrieval selects relevant supporting context...</p></div></div>
    </div>
    <div className="candidate-strip"><DatabaseZap size={17} /><span>24 evidence candidates fused and ranked</span><strong>Ready</strong></div>
  </div>
);

const EvidenceVisual = () => (
  <div className="feature-visual feature-evidence">
    <div className="feature-window__bar"><span /><span /><span /><small>Answer with sources</small></div>
    <div className="evidence-answer">
      <small>ANSWER</small>
      <h4>Retrieval grounds generation in source passages selected for the question.</h4>
      <p>Relevant evidence is retrieved before synthesis, keeping the response connected to the document collection. <b>[S1]</b> Exact terminology can also surface supporting passages that semantic search alone might miss. <b>[S2]</b></p>
      <div className="evidence-citations"><span>S1</span><span>S2</span></div>
    </div>
    <div className="evidence-source">
      <div><Quote size={16} /><small>SOURCE S1</small></div><strong>Retrieval-Augmented Generation</strong><p>Page 3 · Method</p><blockquote>“We combine pre-trained parametric and non-parametric memory for language generation.”</blockquote>
    </div>
  </div>
);

const PrivacyVisual = () => (
  <div className="feature-visual feature-private">
    <div className="feature-window__bar"><span /><span /><span /><small>Private document workspace</small></div>
    <div className="private-user"><span>SP</span><div><small>YOUR WORKSPACE</small><strong>Research library</strong></div><ShieldCheck size={21} /></div>
    <div className="private-files">
      {['Transformer architectures.pdf', 'RAG systems survey.pdf', 'Evaluation notes.pdf'].map((file, index) => (
        <div key={file}><FileLock2 size={17} /><span><strong>{file}</strong><small>{12 + index * 6} chunks indexed</small></span><b>Owned</b></div>
      ))}
    </div>
    <div className="private-pipeline"><span><FileSearch size={17} /> Your documents</span><i /><span><DatabaseZap size={17} /> Local retrieval</span><i /><span><BookOpenCheck size={17} /> Your evidence</span></div>
  </div>
);

const visuals = [RetrievalVisual, EvidenceVisual, PrivacyVisual];

export const ProductShowcase: React.FC = () => {
  const [active, setActive] = useState(0);
  const shellRef = useRef<HTMLDivElement>(null);
  const triggerRefs = useRef<Array<HTMLDivElement | null>>([]);

  useEffect(() => {
    let frame = 0;
    const update = () => {
      frame = 0;
      const shell = shellRef.current;
      if (!shell || window.matchMedia('(max-width: 900px)').matches) return;

      const rect = shell.getBoundingClientRect();
      const scrollableDistance = Math.max(1, rect.height - window.innerHeight);
      const progress = Math.max(0, Math.min(0.9999, -rect.top / scrollableDistance));
      const nextFeature = Math.min(features.length - 1, Math.floor(progress * features.length));
      setActive((current) => current === nextFeature ? current : nextFeature);
    };
    const scheduleUpdate = () => {
      if (!frame) frame = window.requestAnimationFrame(update);
    };

    update();
    window.addEventListener('scroll', scheduleUpdate, { passive: true });
    window.addEventListener('resize', scheduleUpdate);
    return () => {
      window.removeEventListener('scroll', scheduleUpdate);
      window.removeEventListener('resize', scheduleUpdate);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, []);

  const selectFeature = (index: number) => {
    setActive(index);
    triggerRefs.current[index]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  return (
    <section id="product" className="landing-product" aria-labelledby="product-heading">
      <div className="landing-container">
        <Reveal><Eyebrow>Product</Eyebrow></Reveal>
        <Reveal variant="clip" delay={70}><h2 id="product-heading" className="landing-section-title">Research deeper.<br />Stay anchored to evidence.</h2></Reveal>
      </div>

      <div ref={shellRef} className="feature-scroll-shell landing-container">
        <div className="feature-sticky-stage">
          <div className="feature-nav" aria-label="Product features">
            <div className="feature-nav__line"><span style={{ transform: `translateY(${active * 100}%)` }} /></div>
            {features.map((feature, index) => (
              <button key={feature.title} type="button" className={active === index ? 'is-active' : ''} onClick={() => selectFeature(index)}>
                <span>0{index + 1}</span><strong>{feature.title}</strong>
              </button>
            ))}
          </div>

          <div className="feature-display" aria-live="polite">
            <div className="feature-copy-stack">
              {features.map((feature, index) => (
                <div key={feature.title} className={`feature-copy feature-copy-panel ${active === index ? 'is-active' : index < active ? 'is-before' : 'is-after'}`} aria-hidden={active !== index}>
                  <Eyebrow>{feature.badge}</Eyebrow>
                  <h3>{feature.title}</h3>
                  <p>{feature.copy}</p>
                </div>
              ))}
            </div>
            <div className="feature-visual-stack">
              {visuals.map((Visual, index) => (
                <div key={features[index].title} className={`feature-display__visual feature-display__visual--${index} ${active === index ? 'is-active' : index < active ? 'is-before' : 'is-after'}`} aria-hidden={active !== index}>
                  <Visual />
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="feature-scroll-triggers" aria-hidden="true">
          {features.map((feature, index) => (
            <div key={feature.title} ref={(element) => { triggerRefs.current[index] = element; }} data-index={index} />
          ))}
        </div>
      </div>

      <div className="feature-mobile-stack landing-container">
        {features.map((feature, index) => {
          const Visual = visuals[index];
          return <Reveal key={feature.title} className="feature-mobile-item">
            <div className="feature-copy"><Eyebrow>{feature.badge}</Eyebrow><h3>{feature.title}</h3><p>{feature.copy}</p></div>
            <Visual />
          </Reveal>;
        })}
      </div>
    </section>
  );
};

export const PrinciplePanel: React.FC = () => (
  <section className="landing-container landing-principle-wrap">
    <Reveal variant="scale" className="landing-principle">
      <div className="landing-principle__glow" />
      <FileSearch size={24} strokeWidth={1.4} />
      <blockquote>
        <span className="principle-line"><span>“Research answers are only useful</span></span>
        <span className="principle-line"><span>when you can inspect the evidence</span></span>
        <span className="principle-line"><span>behind them.”</span></span>
      </blockquote>
      <div className="landing-principle__footer"><span>Built for traceable research.</span><button type="button" onClick={() => document.querySelector('#workflow')?.scrollIntoView({ behavior: 'smooth' })}>See how it works <span aria-hidden="true">→</span></button></div>
    </Reveal>
  </section>
);
