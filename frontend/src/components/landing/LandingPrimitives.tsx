import React, { useEffect, useRef, useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';

export const landingEase = 'cubic-bezier(0.22, 1, 0.36, 1)';

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

interface RevealProps extends React.HTMLAttributes<HTMLDivElement> {
  delay?: number;
  variant?: 'rise' | 'clip' | 'scale';
}

export const Reveal: React.FC<RevealProps> = ({
  children,
  className = '',
  delay = 0,
  variant = 'rise',
  style,
  ...props
}) => {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.01, rootMargin: '0px 0px 18% 0px' },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={`landing-reveal landing-reveal--${variant} ${visible ? 'is-visible' : ''} ${className}`}
      style={{ ...style, '--reveal-delay': `${delay}ms` } as React.CSSProperties}
      {...props}
    >
      {children}
    </div>
  );
};

export const Eyebrow: React.FC<React.PropsWithChildren> = ({ children }) => (
  <span className="landing-eyebrow">{children}</span>
);

export const ArrowLink: React.FC<{
  to: string;
  children: React.ReactNode;
  tone?: 'dark' | 'light' | 'outline';
  className?: string;
}> = ({ to, children, tone = 'dark', className = '' }) => (
  <Link to={to} className={`landing-arrow-link landing-arrow-link--${tone} ${className}`}>
    <span>{children}</span>
    <ArrowRight aria-hidden="true" size={16} strokeWidth={1.8} />
  </Link>
);
