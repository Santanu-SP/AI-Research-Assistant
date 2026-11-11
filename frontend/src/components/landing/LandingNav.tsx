import React, { useEffect, useState } from 'react';
import { Menu, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import { BrandMark } from '../common/BrandMark';
import { scrollToHash } from './Motion';

const NAV_ITEMS = [
  ['How it works', '#how-it-works'],
  ['Features', '#features'],
  ['Under the hood', '#pipeline'],
  ['FAQ', '#faq'],
] as const;

export const LandingNav: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <header
      className={`landing-nav-enter sticky top-0 z-40 border-b transition-[background-color,border-color,backdrop-filter] duration-300 ${
        scrolled || open ? 'border-line bg-canvas/90 backdrop-blur-md' : 'border-transparent bg-canvas'
      }`}
    >
      <nav className={`mx-auto flex max-w-6xl transition-[height] duration-300 ${scrolled ? 'h-14' : 'h-16'} items-center justify-between px-5 sm:px-8`} aria-label="Primary">
        <Link to="/" className="rounded-md" aria-label="Research Assistant home">
          <BrandMark />
        </Link>

        <div className="hidden items-center gap-7 md:flex">
          {NAV_ITEMS.map(([label, href]) => (
            <a key={href} href={href} onClick={scrollToHash} className="rounded-sm text-[13px] text-ink-soft transition-colors hover:text-ink">
              {label}
            </a>
          ))}
        </div>

        <div className="hidden items-center gap-2 md:flex">
          <Link
            to="/login"
            className="inline-flex h-9 items-center rounded-md px-3 text-[13px] font-medium text-ink-soft transition-colors hover:bg-subtle hover:text-ink"
          >
            Sign in
          </Link>
          <Link
            to="/register"
            className="inline-flex h-9 items-center rounded-md bg-solid px-3.5 text-[13px] font-medium text-on-solid shadow-xs transition-colors hover:bg-solid-hover"
          >
            Get started
          </Link>
        </div>

        <button
          type="button"
          className="-mr-2 inline-flex h-10 w-10 items-center justify-center rounded-md text-ink-soft hover:bg-subtle md:hidden"
          aria-expanded={open}
          aria-controls="landing-mobile-menu"
          aria-label={open ? 'Close menu' : 'Open menu'}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </nav>

      {open && (
        <div id="landing-mobile-menu" className="border-t border-line bg-canvas px-5 pb-5 pt-2 md:hidden">
          <div className="flex flex-col">
            {NAV_ITEMS.map(([label, href]) => (
              <a
                key={href}
                href={href}
                onClick={(event) => {
                  setOpen(false);
                  scrollToHash(event);
                }}
                className="border-b border-line py-3 text-[15px] text-ink"
              >
                {label}
              </a>
            ))}
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2">
            <Link to="/login" className="inline-flex h-10 items-center justify-center rounded-md border border-line-strong bg-panel text-sm font-medium text-ink">
              Sign in
            </Link>
            <Link to="/register" className="inline-flex h-10 items-center justify-center rounded-md bg-solid text-sm font-medium text-on-solid">
              Get started
            </Link>
          </div>
        </div>
      )}
    </header>
  );
};
