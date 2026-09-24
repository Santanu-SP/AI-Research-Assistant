import React, { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, BookOpen, Braces, FileSearch, GraduationCap, Search, Quote } from 'lucide-react';
import { Eyebrow, Reveal } from './LandingPrimitives';

const slides = [
  { label: 'Student Research', title: 'Question a collection without losing the source.', copy: 'Ask targeted questions across a paper collection while keeping evidence close.', icon: GraduationCap, query: 'What evidence supports the authors’ conclusion?', source: 'Page 18 · Discussion' },
  { label: 'Literature Review', title: 'Compare findings across papers with context intact.', copy: 'Compare findings across multiple papers without losing track of the source passages.', icon: BookOpen, query: 'Where do these studies disagree?', source: '3 papers · 7 passages' },
  { label: 'Technical Research', title: 'Find the exact methods, models, and terminology.', copy: 'Find exact terminology, methods, model names, and supporting context.', icon: Braces, query: 'Find every reference to HNSW parameters.', source: 'Methods · Appendix B' },
  { label: 'Evidence Checking', title: 'Inspect the passage behind every research result.', copy: 'Open the source behind a research answer and inspect the supporting excerpt.', icon: FileSearch, query: 'Show the evidence for this claim.', source: 'Source S2 · Page 6' },
] as const;

export const UseCasesCarousel: React.FC = () => {
  const [active, setActive] = useState(0);
  const [previous, setPrevious] = useState<number | null>(null);
  const [direction, setDirection] = useState<1 | -1>(1);
  const [transitioning, setTransitioning] = useState(false);
  const touchStart = useRef<number | null>(null);
  const lockRef = useRef(false);
  const timerRef = useRef<number | null>(null);

  useEffect(() => () => {
    if (timerRef.current) window.clearTimeout(timerRef.current);
  }, []);

  const changeSlide = (index: number, nextDirection: 1 | -1) => {
    if (lockRef.current || index === active) return;
    lockRef.current = true;
    setTransitioning(true);
    setPrevious(active);
    setDirection(nextDirection);
    setActive(index);
    timerRef.current = window.setTimeout(() => {
      setPrevious(null);
      setTransitioning(false);
      lockRef.current = false;
    }, 680);
  };

  const next = () => changeSlide((active + 1) % slides.length, 1);
  const previousSlide = () => changeSlide((active - 1 + slides.length) % slides.length, -1);

  const visual = (index: number, phase: 'current' | 'outgoing') => {
    const slide = slides[index];
    const Icon = slide.icon;
    return <div key={`visual-${phase}-${index}`} className={`use-case-visual use-case-layer is-${phase} direction-${direction === 1 ? 'next' : 'previous'}`} aria-hidden={phase === 'outgoing'}>
      <div className="use-case-visual__top"><span><Icon size={18} /></span><small>{slide.label}</small></div>
      <div className="use-case-query"><Search size={16} /><span>{slide.query}</span></div>
      <div className="use-case-result"><Quote size={18} /><p>Evidence remains attached to the research result, ready to inspect in context.</p><span>{slide.source}</span></div>
      <div className="use-case-lines"><i /><i /><i /></div>
    </div>;
  };

  const copy = (index: number, phase: 'current' | 'outgoing') => {
    const slide = slides[index];
    return <div key={`copy-${phase}-${index}`} className={`use-case-copy use-case-layer is-${phase} direction-${direction === 1 ? 'next' : 'previous'}`} aria-hidden={phase === 'outgoing'}>
      <span>0{index + 1} / 0{slides.length}</span>
      <small>{slide.label}</small>
      <h3>{slide.title}</h3>
      <p>{slide.copy}</p>
      {phase === 'current' && <div className="use-case-controls">
        <button type="button" onClick={previousSlide} disabled={transitioning} aria-label="Previous use case"><ArrowLeft size={18} /></button>
        <button type="button" onClick={next} disabled={transitioning} aria-label="Next use case"><ArrowRight size={18} /></button>
      </div>}
    </div>;
  };

  return (
    <section className="landing-use-cases" aria-labelledby="use-cases-heading">
      <div className="landing-container">
        <div className="landing-section-intro"><Reveal><Eyebrow>Use cases</Eyebrow></Reveal><Reveal variant="clip" delay={60}><h2 id="use-cases-heading" className="landing-section-title">From reading papers<br />to building understanding.</h2></Reveal></div>
        <Reveal variant="scale" className="use-case-reveal">
          <div
            className="use-case-carousel"
            tabIndex={0}
            role="region"
            aria-roledescription="carousel"
            aria-label="Research use cases"
            onKeyDown={(event) => { if (event.key === 'ArrowRight') next(); if (event.key === 'ArrowLeft') previousSlide(); }}
            onTouchStart={(event) => { touchStart.current = event.touches[0].clientX; }}
            onTouchEnd={(event) => {
              if (touchStart.current === null) return;
              const distance = event.changedTouches[0].clientX - touchStart.current;
              if (Math.abs(distance) > 45) {
                if (distance < 0) next();
                else previousSlide();
              }
              touchStart.current = null;
            }}
          >
            <div className="use-case-visual-stage">
              {previous !== null && visual(previous, 'outgoing')}
              {visual(active, 'current')}
            </div>
            <div className="use-case-copy-stage" aria-live="polite">
              {previous !== null && copy(previous, 'outgoing')}
              {copy(active, 'current')}
            </div>
          </div>
          <div className="use-case-pagination" aria-label="Choose a use case">
            {slides.map((item, index) => <button key={item.label} type="button" className={index === active ? 'is-active' : ''} onClick={() => changeSlide(index, index > active ? 1 : -1)} disabled={transitioning} aria-label={`Show ${item.label}`} aria-current={index === active ? 'true' : undefined}><span /></button>)}
          </div>
        </Reveal>
      </div>
    </section>
  );
};
