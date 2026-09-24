import React, { useEffect, useRef } from 'react';
import { BookMarked, Database, FileSearch, LockKeyhole, Search, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';
import { ArrowLink, usePrefersReducedMotion } from './LandingPrimitives';

const trustItems = [
  [FileSearch, 'Grounded in your papers'],
  [BookMarked, 'Traceable evidence'],
  [LockKeyhole, 'Private research workspace'],
  [Database, 'Local RAG architecture'],
] as const;

export const ResearchProductFrame: React.FC<{ compact?: boolean }> = ({ compact = false }) => (
  <div className={`research-frame ${compact ? 'research-frame--compact' : ''}`} aria-label="AI Research Assistant product preview">
    <div className="research-frame__chrome">
      <div className="research-frame__dots"><span /><span /><span /></div>
      <span>Research workspace</span>
      <span className="research-frame__status">Local retrieval</span>
    </div>
    <div className="research-frame__body">
      <aside className="research-frame__library">
        <div className="research-frame__label">YOUR PAPERS</div>
        <div className="research-frame__search"><Search size={12} /> Search library</div>
        <div className="research-paper is-active"><span className="research-paper__icon">PDF</span><div><strong>Attention Is All You Need</strong><small>12 pages · Indexed</small></div></div>
        <div className="research-paper"><span className="research-paper__icon">PDF</span><div><strong>Retrieval-Augmented Generation</strong><small>18 pages · Indexed</small></div></div>
        <div className="research-paper"><span className="research-paper__icon">PDF</span><div><strong>Dense Passage Retrieval</strong><small>9 pages · Indexed</small></div></div>
      </aside>
      <main className="research-frame__answer">
        <div className="research-frame__question"><span>How does attention replace recurrence?</span><Sparkles size={14} /></div>
        <div className="research-frame__answer-label">GROUNDED ANSWER</div>
        <h3>Attention models relationships between every token directly.</h3>
        <p>The architecture replaces recurrent computation with stacked self-attention, allowing the model to connect positions regardless of distance.</p>
        <p className="research-frame__highlight">Multi-head attention lets the model attend to information from different representation subspaces. <span>[S1]</span></p>
        <div className="research-frame__chips"><span>S1 · p. 4</span><span>S2 · p. 6</span></div>
      </main>
      <aside className="research-frame__evidence">
        <div className="research-frame__label">SOURCE EVIDENCE</div>
        <div className="evidence-card is-active"><div><span>S1</span><small>Page 4 · Architecture</small></div><strong>Attention Is All You Need</strong><p>“The Transformer allows significantly more parallelization...”</p></div>
        <div className="evidence-card"><div><span>S2</span><small>Page 6 · Analysis</small></div><strong>Attention heads</strong><p>Each head learns a distinct pattern of contextual relationships.</p></div>
      </aside>
    </div>
  </div>
);

export const HeroSection: React.FC = () => {
  const mediaRef = useRef<HTMLDivElement>(null);
  const reducedMotion = usePrefersReducedMotion();

  useEffect(() => {
    const media = mediaRef.current;
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

  return <section className="landing-hero" aria-labelledby="landing-hero-title">
    <div className="landing-container landing-hero__inner">
      <div className="landing-load landing-load--badge" style={{ '--load-delay': '90ms' } as React.CSSProperties}>
        <span className="landing-pill"><Sparkles size={13} /> Evidence-first research</span>
      </div>
      <h1 id="landing-hero-title" className="landing-hero__headline">
        <span className="landing-hero__title-mask"><span className="landing-load landing-load--headline-line" style={{ '--load-delay': '150ms' } as React.CSSProperties}>Turn research papers</span></span>
        <span className="landing-hero__title-mask"><span className="landing-load landing-load--headline-line" style={{ '--load-delay': '225ms' } as React.CSSProperties}>into answers you can verify.</span></span>
      </h1>
      <p className="landing-hero__lede landing-load" style={{ '--load-delay': '300ms' } as React.CSSProperties}>
        Upload your papers, ask natural-language questions, and explore grounded answers with source-level evidence—powered by local retrieval and research-focused AI.
      </p>
      <div className="landing-hero__actions landing-load" style={{ '--load-delay': '375ms' } as React.CSSProperties}>
        <ArrowLink to="/register">Start Researching</ArrowLink>
        <p>Already have an account? <Link to="/login">Sign in</Link></p>
      </div>
      <div className="landing-trust landing-load" style={{ '--load-delay': '440ms' } as React.CSSProperties}>
        {trustItems.map(([Icon, label]) => <span key={label}><Icon size={15} strokeWidth={1.7} />{label}</span>)}
      </div>
      <div ref={mediaRef} className="landing-hero__media-parallax">
        <div className="landing-hero__media landing-load landing-load--media" style={{ '--load-delay': '500ms' } as React.CSSProperties}>
          <ResearchProductFrame />
        </div>
      </div>
    </div>
  </section>;
};
