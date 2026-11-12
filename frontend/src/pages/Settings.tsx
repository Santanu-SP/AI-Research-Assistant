import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CheckCircle2, CircleAlert, LogOut, Monitor, Moon, RefreshCw, Sun } from 'lucide-react';
import { TopBar } from '../components/layout/TopBar';
import { PageHeader } from '../components/common/PageHeader';
import { PrimaryButton } from '../components/common/PrimaryButton';
import { useAuth } from '../app/AuthContext';
import { useToast } from '../app/ToastContext';
import {
  getThemePreference,
  setThemePreference,
  THEME_CHANGE_EVENT,
  type ThemePreference,
} from '../theme';
import { ReadinessResponse, systemService } from '../services/system.service';
import { authErrorMessage } from '../services/auth.service';
import { shortcutLabel } from '../lib/shortcuts';

const Section: React.FC<
  React.PropsWithChildren<{ id: string; title: string; description?: string; className?: string }>
> = ({ id, title, description, className = 'grid', children }) => (
  <section aria-labelledby={id} className={`${className} gap-4 border-t border-line py-8 first:border-t-0 first:pt-2 md:grid-cols-[220px_minmax(0,1fr)] md:gap-10`}>
    <div>
      <h2 id={id} className="text-[15px] font-semibold text-ink">
        {title}
      </h2>
      {description && <p className="mt-1 text-[13px] leading-relaxed text-ink-muted">{description}</p>}
    </div>
    <div className="min-w-0">{children}</div>
  </section>
);

const Row: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div className="flex flex-col gap-0.5 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
    <dt className="text-[13px] text-ink-muted">{label}</dt>
    <dd className="min-w-0 truncate text-[14px] text-ink">{value}</dd>
  </div>
);

const THEME_OPTIONS: { value: ThemePreference; label: string; icon: React.ElementType }[] = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'System', icon: Monitor },
];

const CHECK_LABELS: Record<string, string> = {
  database: 'Database',
  ollama: 'Language model',
};

const formatDate = (value?: string) =>
  value
    ? new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'long', day: 'numeric' }).format(new Date(value))
    : '—';

export const SettingsPage: React.FC = () => {
  const navigate = useNavigate();
  const { user, logout, logoutAll } = useAuth();
  const { addToast } = useToast();
  const [theme, setTheme] = useState<ThemePreference>(getThemePreference);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [readinessError, setReadinessError] = useState(false);
  const [checking, setChecking] = useState(true);
  const [signingOut, setSigningOut] = useState<'this' | 'all' | null>(null);

  useEffect(() => {
    const sync = () => setTheme(getThemePreference());
    window.addEventListener(THEME_CHANGE_EVENT, sync);
    return () => window.removeEventListener(THEME_CHANGE_EVENT, sync);
  }, []);

  const checkStatus = useCallback(async () => {
    setChecking(true);
    setReadinessError(false);
    try {
      setReadiness(await systemService.getReadiness());
    } catch {
      setReadiness(null);
      setReadinessError(true);
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    void checkStatus();
  }, [checkStatus]);

  const signOut = async (scope: 'this' | 'all') => {
    setSigningOut(scope);
    try {
      await (scope === 'all' ? logoutAll() : logout());
      navigate('/login', { replace: true });
    } catch (error) {
      addToast({
        type: 'error',
        title: 'Could not sign out',
        description: authErrorMessage(error, 'Could not reach the server. Please try again.'),
      });
      setSigningOut(null);
    }
  };

  return (
    <div className="flex min-h-screen flex-col">
      <TopBar breadcrumbs={<span className="font-medium text-ink">Settings</span>} />

      <main className="flex-1 px-4 pb-16 pt-14 sm:px-6 lg:px-10">
        <div className="mx-auto max-w-4xl py-8 sm:py-10">
          <PageHeader title="Settings" description="Your account, how the app looks, and whether the research services are reachable." />

          <div className="mt-8">
            <Section id="settings-profile" title="Profile" description="The details on your account.">
              <dl className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-panel shadow-xs">
                <Row label="Name" value={user?.name || '—'} />
                <Row label="Email" value={user?.email || '—'} />
                <Row label="Member since" value={formatDate(user?.createdAt)} />
              </dl>
            </Section>

            <Section id="settings-appearance" title="Appearance" description="System follows your device’s light or dark setting.">
              <div role="radiogroup" aria-labelledby="settings-appearance" className="grid grid-cols-3 gap-2 sm:max-w-md">
                {THEME_OPTIONS.map(({ value, label, icon: Icon }) => {
                  const selected = theme === value;
                  return (
                    <button
                      key={value}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      onClick={() => {
                        setThemePreference(value);
                        setTheme(value);
                      }}
                      className={`flex h-20 flex-col items-center justify-center gap-2 rounded-lg border text-[13px] font-medium transition-[border-color,background-color,box-shadow] duration-200 ${
                        selected
                          ? 'border-accent bg-accent-soft text-ink shadow-xs ring-1 ring-accent'
                          : 'border-line bg-panel text-ink-soft hover:border-line-strong hover:text-ink'
                      }`}
                    >
                      <Icon className={`h-[18px] w-[18px] ${selected ? 'text-accent' : 'text-ink-muted'}`} />
                      {label}
                    </button>
                  );
                })}
              </div>
            </Section>

            <Section
              id="settings-shortcuts"
              title="Keyboard shortcuts"
              description="Available anywhere in the app."
              className="hidden sm:grid"
            >
              <dl className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-panel shadow-xs">
                {[
                  ['Search research', shortcutLabel('K')],
                  ['New research', shortcutLabel('O', { shift: true })],
                  ['Show or hide the sidebar', shortcutLabel('S', { shift: true })],
                ].map(([label, keys]) => (
                  <Row
                    key={label}
                    label={label}
                    value={
                      <kbd className="inline-flex h-6 items-center rounded border border-line bg-subtle px-2 font-sans text-xs font-medium text-ink-soft">
                        {keys}
                      </kbd>
                    }
                  />
                ))}
              </dl>
            </Section>

            <Section
              id="settings-status"
              title="Research services"
              description="Research needs the database and the local language model to be running."
            >
              <div className="overflow-hidden rounded-lg border border-line bg-panel shadow-xs">
                <div className="divide-y divide-line">
                  {checking && !readiness ? (
                    [0, 1].map((index) => (
                      <div key={index} className="flex h-[52px] items-center px-4">
                        <span className="h-2.5 w-40 animate-pulse rounded bg-subtle" />
                      </div>
                    ))
                  ) : readinessError || !readiness ? (
                    <div className="flex items-center gap-2.5 px-4 py-3.5 text-[13px] text-ink-soft">
                      <CircleAlert className="h-4 w-4 shrink-0 text-danger" />
                      The server didn’t respond, so the services couldn’t be checked.
                    </div>
                  ) : (
                    readiness.checks.map((check) => (
                      <div key={check.name} className="flex min-h-[52px] items-center justify-between gap-4 px-4 py-2.5">
                        <div className="min-w-0">
                          <p className="text-[14px] text-ink">{CHECK_LABELS[check.name] ?? check.name}</p>
                          {check.detail && <p className="truncate font-mono text-[11.5px] text-ink-muted">{check.detail}</p>}
                        </div>
                        <span
                          className={`inline-flex shrink-0 items-center gap-1.5 text-[13px] font-medium ${
                            check.ok ? 'text-accent' : 'text-danger'
                          }`}
                        >
                          {check.ok ? <CheckCircle2 className="h-4 w-4" /> : <CircleAlert className="h-4 w-4" />}
                          {check.ok ? 'Available' : 'Unavailable'}
                        </span>
                      </div>
                    ))
                  )}
                </div>
                <div className="flex items-center justify-between gap-3 border-t border-line bg-subtle/50 px-4 py-2.5">
                  <p className="text-xs text-ink-muted">
                    {readiness ? (readiness.status === 'ready' ? 'Everything is ready.' : 'Some services need attention.') : ' '}
                  </p>
                  <PrimaryButton variant="ghost" size="sm" onClick={() => void checkStatus()} disabled={checking}>
                    <RefreshCw className={`h-3.5 w-3.5 ${checking ? 'animate-spin' : ''}`} />
                    Check again
                  </PrimaryButton>
                </div>
              </div>
            </Section>

            <Section id="settings-session" title="Sign out" description="Signing out of all devices ends every session on this account, including this one.">
              <div className="flex flex-wrap gap-2">
                <PrimaryButton variant="outline" onClick={() => void signOut('this')} disabled={signingOut !== null}>
                  <LogOut className="h-4 w-4" />
                  {signingOut === 'this' ? 'Signing out…' : 'Sign out'}
                </PrimaryButton>
                <PrimaryButton variant="ghost" onClick={() => void signOut('all')} disabled={signingOut !== null}>
                  {signingOut === 'all' ? 'Signing out…' : 'Sign out of all devices'}
                </PrimaryButton>
              </div>
            </Section>
          </div>
        </div>
      </main>
    </div>
  );
};
