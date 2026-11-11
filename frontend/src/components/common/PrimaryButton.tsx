import React from 'react';
import { ArrowRight } from 'lucide-react';
import { LoadingOrb } from './LoadingOrb';

interface PrimaryButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode;
  showArrow?: boolean;
  isLoading?: boolean;
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
}

const SIZES = {
  sm: 'h-8 px-2.5 text-xs gap-1.5',
  md: 'h-9 px-3.5 text-[13px] gap-2',
  lg: 'h-10 px-4 text-sm gap-2',
} as const;

const VARIANTS = {
  primary: 'bg-solid text-on-solid hover:bg-solid-hover border border-transparent shadow-xs',
  secondary: 'bg-accent-soft text-accent hover:bg-accent-muted border border-accent-line',
  outline: 'bg-panel text-ink hover:bg-subtle border border-line-strong shadow-xs',
  ghost: 'bg-transparent text-ink-soft hover:bg-subtle hover:text-ink border border-transparent',
  danger: 'bg-danger-solid text-on-solid hover:bg-danger-solid-hover border border-transparent shadow-xs',
} as const;

export const PrimaryButton: React.FC<PrimaryButtonProps> = ({
  children,
  showArrow = false,
  isLoading = false,
  variant = 'primary',
  size = 'md',
  className = '',
  disabled,
  type = 'button',
  ...props
}) => {
  const isDisabled = disabled || isLoading;

  return (
    <button
      type={type}
      className={`group inline-flex select-none items-center justify-center whitespace-nowrap rounded-md font-medium transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-55 ${SIZES[size]} ${VARIANTS[variant]} ${className}`}
      disabled={isDisabled}
      aria-busy={isLoading || undefined}
      {...props}
    >
      {isLoading ? <LoadingOrb size={14} className="loading-orb--on-solid" /> : null}
      {children}
      {showArrow && !isLoading && (
        <ArrowRight className="h-3.5 w-3.5 transition-transform duration-150 group-hover:translate-x-0.5" />
      )}
    </button>
  );
};
