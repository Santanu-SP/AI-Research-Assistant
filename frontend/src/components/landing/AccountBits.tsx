import React, { useEffect, useId, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown, LayoutDashboard, LogOut } from 'lucide-react';

interface AccountUser {
  name?: string | null;
  email: string;
}

/** The name we greet people with: their name, or the part of the email before the @. */
export const accountName = (user: AccountUser): string =>
  user.name?.trim() || user.email.split('@')[0] || 'there';

export const accountFirstName = (user: AccountUser): string => accountName(user).split(/\s+/)[0];

export const accountInitials = (user: AccountUser): string => {
  const parts = accountName(user).split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? parts[0][0] + parts[1][0] : parts[0]?.[0] ?? '?';
  return letters.toUpperCase();
};

export const AccountAvatar: React.FC<{ user: AccountUser; size?: 'sm' | 'lg' }> = ({ user, size = 'sm' }) => (
  <span
    aria-hidden="true"
    className={`relative inline-flex shrink-0 items-center justify-center rounded-full bg-solid font-semibold text-on-solid ${
      size === 'lg' ? 'h-12 w-12 text-base' : 'h-7 w-7 text-[11px]'
    }`}
  >
    {accountInitials(user)}
    <span
      className={`absolute rounded-full bg-emerald-400 ring-2 ring-panel ${
        size === 'lg' ? '-bottom-0.5 -right-0.5 h-3.5 w-3.5' : '-bottom-px -right-px h-2.5 w-2.5'
      }`}
    />
  </span>
);

/** Header button with the person's avatar and name; opens a small menu with Sign out. */
export const AccountMenu: React.FC<{ user: AccountUser; onSignOut: () => void }> = ({ user, onSignOut }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        data-testid="account-menu-button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label={`Account menu for ${accountName(user)}`}
        onClick={() => setOpen((value) => !value)}
        className="inline-flex h-9 items-center gap-2 rounded-full border border-line bg-panel py-1 pl-1 pr-2.5 text-[13px] font-medium text-ink shadow-xs transition-colors hover:bg-subtle"
      >
        <AccountAvatar user={user} />
        <span className="max-w-[120px] truncate">{accountFirstName(user)}</span>
        <ChevronDown className={`h-3.5 w-3.5 text-ink-muted transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div
          id={menuId}
          role="menu"
          className="landing-account-menu absolute right-0 top-[calc(100%+8px)] z-50 w-64 overflow-hidden rounded-lg border border-line bg-panel shadow-lg"
        >
          <div className="flex items-center gap-3 border-b border-line px-3.5 py-3">
            <AccountAvatar user={user} />
            <div className="min-w-0">
              <p className="truncate text-[13px] font-medium text-ink">{accountName(user)}</p>
              <p className="truncate text-xs text-ink-muted">{user.email}</p>
            </div>
          </div>
          <div className="p-1.5">
            <Link
              role="menuitem"
              to="/research/new"
              className="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] text-ink hover:bg-subtle"
            >
              <LayoutDashboard className="h-4 w-4 text-ink-muted" />
              Open workspace
            </Link>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onSignOut();
              }}
              className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-[13px] text-ink hover:bg-subtle"
            >
              <LogOut className="h-4 w-4 text-ink-muted" />
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
