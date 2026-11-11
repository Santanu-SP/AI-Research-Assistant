import React from 'react';

interface BrandMarkProps {
  className?: string;
  /** Show the product name next to the mark. */
  withName?: boolean;
  nameClassName?: string;
}

/** Product mark: a page with a highlighted, cited line. */
export const BrandMark: React.FC<BrandMarkProps> = ({
  className = '',
  withName = true,
  nameClassName = '',
}) => (
  <span className={`inline-flex items-center gap-2.5 ${className}`}>
    <svg
      viewBox="0 0 32 32"
      className="h-7 w-7 shrink-0"
      aria-hidden="true"
      focusable="false"
    >
      <rect width="32" height="32" rx="7" className="fill-solid" />
      <path
        d="M10 9.5h8.5M10 14h12M10 18.5h12"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        className="text-on-solid"
      />
      <path d="M10 23h5" stroke="#9fd6bb" strokeWidth="2" strokeLinecap="round" />
    </svg>
    {withName && (
      <span className={`text-[15px] font-semibold tracking-[-0.01em] text-ink ${nameClassName}`}>
        Research Assistant
      </span>
    )}
  </span>
);
