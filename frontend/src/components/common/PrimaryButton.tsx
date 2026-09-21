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
    'inline-flex items-center justify-center font-medium rounded-md transition-all duration-150 cursor-pointer select-none group focus:outline-none focus:ring-2 focus:ring-[#163328] focus:ring-offset-1';

  let sizeStyles = 'px-3.5 py-2 text-xs gap-1.5';
  if (size === 'sm') sizeStyles = 'px-2.5 py-1.5 text-xs gap-1';
  if (size === 'lg') sizeStyles = 'px-4 py-2.5 text-sm gap-2';

  let variantStyles =
    'bg-[#163328] text-white hover:bg-[#214f40] active:scale-[0.99] border border-transparent shadow-none';

  if (variant === 'secondary') {
    variantStyles =
      'bg-[#f1f6f3] text-[#163328] hover:bg-[#e4eee7] border border-[#cbe0d5] active:scale-[0.99]';
  } else if (variant === 'outline') {
    variantStyles =
      'bg-white text-[#181a18] hover:bg-[#f5f5f2] border border-[#e5e7e4] hover:border-[#d0d7d2] active:scale-[0.99]';
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
