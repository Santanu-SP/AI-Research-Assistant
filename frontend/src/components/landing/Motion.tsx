import React, { useEffect, useRef, useState } from 'react';

export const usePrefersReducedMotion = () => {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(query.matches);
    update();
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);

  return reduced;
};

type RevealTag = 'div' | 'li' | 'ol' | 'p' | 'span';

interface RevealProps extends React.HTMLAttributes<HTMLElement> {
  as?: RevealTag;
  delay?: number;
  variant?: 'rise' | 'clip' | 'scale';
}

/** Fades and lifts its content in the first time it scrolls into view. */
export const Reveal: React.FC<RevealProps> = ({
  as = 'div',
  children,
  className = '',
  delay = 0,
  variant = 'rise',
  style,
  ...props
}) => {
  const ref = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    if (typeof IntersectionObserver === 'undefined') {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0, rootMargin: '0px 0px 5% 0px' },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return React.createElement(
    as,
    {
      ref,
      className: `landing-reveal landing-reveal--${variant} ${visible ? 'is-visible' : ''} ${className}`,
      style: { ...style, '--reveal-delay': `${delay}ms` } as React.CSSProperties,
      ...props,
    },
    children,
  );
};

/** Inline style helper for the staggered on-load animation. */
export const loadDelay = (ms: number) => ({ '--load-delay': `${ms}ms` }) as React.CSSProperties;

/** Smooth-scrolls to an in-page anchor instead of jumping. */
export const scrollToHash = (event: React.MouseEvent<HTMLAnchorElement>) => {
  const hash = event.currentTarget.getAttribute('href');
  if (!hash?.startsWith('#')) return;
  const target = document.querySelector(hash);
  if (!target) return;
  event.preventDefault();
  target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  window.history.replaceState(null, '', hash);
};
