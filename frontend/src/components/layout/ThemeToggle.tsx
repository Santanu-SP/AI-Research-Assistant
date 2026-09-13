import React, { useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';
import {
  applyTheme,
  getAppliedTheme,
  THEME_CHANGE_EVENT,
  type AppTheme,
} from '../../theme';

interface ThemeToggleProps {
  className?: string;
}

export const ThemeToggle: React.FC<ThemeToggleProps> = ({ className = '' }) => {
  const [theme, setTheme] = useState<AppTheme>(getAppliedTheme);

  useEffect(() => {
    const handleThemeChange = (event: Event) => {
      setTheme((event as CustomEvent<AppTheme>).detail);
    };

    window.addEventListener(THEME_CHANGE_EVENT, handleThemeChange);
    return () => window.removeEventListener(THEME_CHANGE_EVENT, handleThemeChange);
  }, []);

  const nextTheme = theme === 'light' ? 'dark' : 'light';
  const label = `Switch to ${nextTheme} mode`;

  return (
    <button
      type="button"
      className={`theme-toggle h-8 w-8 shrink-0 items-center justify-center rounded-md border transition-colors ${className}`}
      aria-label={label}
      title={label}
      onClick={() => applyTheme(nextTheme, true)}
    >
      {theme === 'light' ? (
        <Moon className="h-4 w-4" aria-hidden="true" />
      ) : (
        <Sun className="h-4 w-4" aria-hidden="true" />
      )}
    </button>
  );
};
