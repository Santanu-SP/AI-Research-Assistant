import React, { useEffect, useState } from 'react';
import { ArrowRight, BookOpenText, Menu, X } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';

const navItems = [
  ['Product', '#product'],
  ['How it works', '#workflow'],
  ['Privacy', '#privacy'],
  ['FAQ', '#faq'],
] as const;

export const LandingNav: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const location = useLocation();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => setOpen(false), [location.pathname]);

  const goTo = (hash: string) => {
    setOpen(false);
    document.querySelector(hash)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <header className={`landing-nav-shell ${scrolled ? 'is-scrolled' : ''}`}>
      <nav className="landing-nav landing-container" aria-label="Primary navigation">
        <Link to="/" className="landing-brand" aria-label="AI Research Assistant home">
          <span className="landing-brand__mark"><BookOpenText size={17} /></span>
          <span>AI Research Assistant</span>
        </Link>

        <div className="landing-nav__links" aria-label="Landing page sections">
          {navItems.map(([label, hash]) => (
            <button key={hash} type="button" onClick={() => goTo(hash)}>{label}</button>
          ))}
        </div>

        <div className="landing-nav__actions">
          <Link className="landing-nav__signin" to="/login">Sign In</Link>
          <Link className="landing-nav__primary" to="/register">
            <span>Create Account</span><ArrowRight size={14} />
          </Link>
        </div>

        <button
          type="button"
          className="landing-nav__menu"
          aria-expanded={open}
          aria-controls="landing-mobile-menu"
          aria-label={open ? 'Close navigation menu' : 'Open navigation menu'}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <X size={21} /> : <Menu size={21} />}
        </button>
      </nav>

      <div id="landing-mobile-menu" className={`landing-mobile-menu ${open ? 'is-open' : ''}`} aria-hidden={!open}>
        <div className="landing-container">
          {navItems.map(([label, hash]) => (
            <button key={hash} type="button" onClick={() => goTo(hash)}>{label}</button>
          ))}
          <div className="landing-mobile-menu__actions">
            <Link to="/login">Sign In</Link>
            <Link to="/register">Create Account <ArrowRight size={14} /></Link>
          </div>
        </div>
      </div>
    </header>
  );
};
