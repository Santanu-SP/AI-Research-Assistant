import React from 'react';
import { ArrowRight } from 'lucide-react';
import { LoadingOrb } from './LoadingOrb';

interface PrimaryButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode;
  showArrow?: boolean;
  isLoading?: boolean;
  variant?: 'primary' | 'secondary' | 'outline';
  size?: 'sm' | 'md' | 'lg';
}

export const PrimaryButton: React.FC<PrimaryButtonProps> = ({
  children,
  showArrow = false,
  isLoading = false,
  variant = 'primary',
  size = 'md',
  className = '',
  disabled,
  ...props
}) => {
  const baseStyles =
    'inline-flex items-center justify-center font-medium rounded-md transition-all duration-150 cursor-pointer select-none group focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-1';

  let sizeStyles = 'px-3.5 py-2 text-xs gap-1.5';
  if (size === 'sm') sizeStyles = 'px-2.5 py-1.5 text-xs gap-1';
  if (size === 'lg') sizeStyles = 'px-4 py-2.5 text-sm gap-2';

  let variantStyles =
    'bg-solid text-on-solid hover:bg-solid-hover active:scale-[0.99] border border-transparent shadow-none';

  if (variant === 'secondary') {
    variantStyles =
      'bg-accent-soft text-accent hover:bg-accent-muted border border-accent-line active:scale-[0.99]';
  } else if (variant === 'outline') {
    variantStyles =
      'bg-panel text-ink hover:bg-subtle border border-line hover:border-line-strong active:scale-[0.99]';
  }

  const disabledStyles = disabled || isLoading
    ? 'opacity-60 cursor-not-allowed pointer-events-none'
    : '';

  return (
    <button
      className={`${baseStyles} ${sizeStyles} ${variantStyles} ${disabledStyles} ${className}`}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? (
        <LoadingOrb size={16} className="loading-orb--on-solid" />
      ) : null}
      <span>{children}</span>
      {showArrow && !isLoading && (
        <ArrowRight className="w-3.5 h-3.5 transition-transform duration-150 group-hover:translate-x-0.5 text-current" />
      )}
    </button>
  );
};
