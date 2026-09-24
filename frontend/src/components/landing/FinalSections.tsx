import React from 'react';
import { ArrowRight, BookOpenText } from 'lucide-react';
import { Link } from 'react-router-dom';
import { ArrowLink, Eyebrow, Reveal } from './LandingPrimitives';

const scrollTo = (hash: string) => document.querySelector(hash)?.scrollIntoView({ behavior: 'smooth' });

export const FinalCTA: React.FC = () => (
  <section className="landing-container landing-final-wrap">
    <Reveal variant="scale" className="landing-final">
      <div className="landing-final__glow" />
      <Eyebrow>Start your research workspace</Eyebrow>
      <h2><span className="final-line"><span>Ask better questions.</span></span><span className="final-line"><span>Keep the evidence in view.</span></span></h2>
      <p>Bring your paper collection into one grounded research workflow.</p>
      <div><ArrowLink to="/register" tone="light">Create Account</ArrowLink><Link to="/login" className="landing-final__signin">Sign In <ArrowRight size={14} /></Link></div>
    </Reveal>
  </section>
);

export const LandingFooter: React.FC = () => (
  <footer className="landing-footer">
    <div className="landing-container landing-footer__grid">
      <Reveal className="landing-footer__brand"><span><BookOpenText size={18} /></span><strong>AI Research Assistant</strong><p>Evidence-first research across your own paper collection.</p></Reveal>
      <Reveal delay={80}><strong>Explore</strong><button type="button" onClick={() => scrollTo('#product')}>Product</button><button type="button" onClick={() => scrollTo('#workflow')}>How it works</button><button type="button" onClick={() => scrollTo('#privacy')}>Privacy</button><button type="button" onClick={() => scrollTo('#faq')}>FAQ</button></Reveal>
      <Reveal delay={160}><strong>Account</strong><Link to="/login">Sign In</Link><Link to="/register">Create Account</Link></Reveal>
    </div>
    <Reveal delay={220} className="landing-container landing-footer__bottom"><span>© {new Date().getFullYear()} AI Research Assistant</span><span>Research with evidence, not guesswork.</span></Reveal>
  </footer>
);
