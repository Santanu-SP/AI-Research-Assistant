import React from 'react';

interface PageHeaderProps {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  meta?: React.ReactNode;
  className?: string;
}

/** Title block shared by the signed-in pages. */
export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  description,
  actions,
  meta,
  className = '',
}) => (
  <header
    className={`flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between ${className}`}
  >
    <div className="min-w-0">
      {meta && <div className="mb-2 text-xs text-ink-muted">{meta}</div>}
      <h1 className="text-[22px] font-semibold leading-tight tracking-[-0.015em] text-ink sm:text-2xl">
        {title}
      </h1>
      {description && (
        <p className="mt-1.5 max-w-2xl text-sm text-ink-soft">{description}</p>
      )}
    </div>
    {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
  </header>
);
