import React from 'react';
import { Link } from 'react-router-dom';
import { BrandMark } from '../common/BrandMark';

interface AuthShellProps {
  title: string;
  description: string;
}

/** Two-column sign-in layout: the form, and a short note on how answers are sourced. */
export const AuthShell: React.FC<React.PropsWithChildren<AuthShellProps>> = ({
  title,
  description,
  children,
}) => (
  <main className="grid min-h-screen bg-canvas text-ink lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
    <div className="flex flex-col px-5 py-6 sm:px-10">
      <Link to="/" className="self-start rounded-md" aria-label="Research Assistant home">
        <BrandMark />
      </Link>

      <div className="flex flex-1 items-center justify-center py-12">
        <div className="w-full max-w-[380px]">
          <h1 className="text-2xl font-semibold tracking-[-0.02em] text-ink">{title}</h1>
          <p className="mt-2 text-sm text-ink-soft">{description}</p>
          <div className="mt-8">{children}</div>
        </div>
      </div>

      <p className="text-xs text-ink-muted">
        Your documents stay in your own workspace and are only searched for your questions.
      </p>
    </div>

    <aside className="relative hidden overflow-hidden border-l border-line bg-subtle lg:flex lg:flex-col lg:justify-center lg:px-14 xl:px-20">
      <div className="max-w-[520px]">
        <p className="eyebrow">How answers are built</p>
        <p className="mt-3 font-serif text-[28px] leading-[1.25] tracking-[-0.01em] text-ink">
          Every sentence in an answer points back to the page it came from.
        </p>

        <figure className="mt-10 rounded-xl border border-line bg-panel p-5 shadow-md">
          <figcaption className="flex items-center justify-between text-xs text-ink-muted">
            <span>Answer</span>
            <span className="font-mono">3 sources</span>
          </figcaption>
          <p className="mt-3 font-serif text-[15px] leading-7 text-ink">
            Slow dissociation extends receptor occupancy beyond plasma clearance
            <Cite n={1} />, and affinity alone failed to rank compounds by efficacy in four of
            six series <Cite n={2} />.
          </p>
          <div className="mt-4 rounded-lg border border-line bg-subtle/60 p-3.5">
            <div className="flex items-center gap-2 text-xs">
              <span className="inline-flex h-5 min-w-5 items-center justify-center rounded bg-accent-soft px-1 font-mono text-[11px] font-medium text-accent">
                1
              </span>
              <span className="font-medium text-ink">kinetic-selectivity.pdf</span>
              <span className="text-ink-muted">· p. 6 · Results</span>
            </div>
            <p className="mt-2 text-xs leading-5 text-ink-soft">
              “Residence time explained 61% of the variance in duration of action across the
              tested compounds.”
            </p>
          </div>
        </figure>
      </div>
    </aside>
  </main>
);

const Cite: React.FC<{ n: number }> = ({ n }) => (
  <sup className="ml-0.5 inline-flex h-4 min-w-4 -translate-y-px items-center justify-center rounded bg-accent-soft px-1 align-middle font-mono text-[10px] font-medium text-accent">
    {n}
  </sup>
);

export const authInputClass = 'field h-10';
export const authLabelClass = 'field-label';
