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
import { byokService, ModelUsageQuotaSummary } from '../services/clientAi.service';
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

const formatCount = (value: number): string =>
  new Intl.NumberFormat().format(Math.max(0, Math.round(value)));

export const SettingsPage: React.FC = () => {
  const navigate = useNavigate();
  const { user, logout, logoutAll } = useAuth();
  const { addToast } = useToast();
  const [theme, setTheme] = useState<ThemePreference>(getThemePreference);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [readinessError, setReadinessError] = useState(false);
  const [checking, setChecking] = useState(true);
  const [usageSummary, setUsageSummary] = useState<ModelUsageQuotaSummary | null>(null);
  const [usageLoading, setUsageLoading] = useState(true);
  const [usageError, setUsageError] = useState(false);
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

  const checkUsage = useCallback(async () => {
    setUsageLoading(true);
    setUsageError(false);
    try {
      setUsageSummary(await byokService.getUsage());
    } catch {
      setUsageSummary(null);
      setUsageError(true);
    } finally {
      setUsageLoading(false);
    }
  }, []);

  useEffect(() => {
    void checkStatus();
    void checkUsage();
  }, [checkStatus, checkUsage]);

  useEffect(() => {
    const refresh = () => {
      void checkUsage();
    };
    window.addEventListener('models-usage:refresh', refresh);
    return () => window.removeEventListener('models-usage:refresh', refresh);
  }, [checkUsage]);

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

            <Section
              id="settings-model-usage"
              title="Model usage & daily quota"
              description="Shared daily cap scales fairly with active users and remaining server AI API requests."
            >
              <div className="overflow-hidden rounded-lg border border-line bg-panel shadow-xs">
                {usageLoading && !usageSummary ? (
                  <div className="space-y-3 p-4">
                    <span className="block h-3 w-48 animate-pulse rounded bg-subtle" />
                    <span className="block h-2 w-full animate-pulse rounded bg-subtle" />
                  </div>
                ) : usageError || !usageSummary ? (
                  <div className="flex items-center gap-2.5 px-4 py-3.5 text-[13px] text-ink-soft">
                    <CircleAlert className="h-4 w-4 shrink-0 text-danger" />
                    Could not load model usage right now.
                  </div>
                ) : (
                  <div className="divide-y divide-line">
                    <div className="p-4">
                      <div className="flex flex-wrap items-center justify-between gap-2 text-[13px]">
                        <span className="font-medium text-ink">
                          Shared server requests used today
                        </span>
                        <span className="font-medium tabular-nums text-ink">
                          {usageSummary.sharedRequestsUsedToday} / {usageSummary.userDailyRequestCap} requests
                          {' '}
                          <span className="text-ink-muted">
                            ({usageSummary.userRequestsRemainingToday} left for you today)
                          </span>
                        </span>
                      </div>
                      <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-subtle">
                        <div
                          className={`h-full rounded-full transition-all ${
                            usageSummary.userRequestsRemainingToday <= 0 ? 'bg-danger' : 'bg-accent'
                          }`}
                          style={{
                            width: `${
                              usageSummary.userDailyRequestCap > 0
                                ? Math.min(
                                    100,
                                    Math.round(
                                      (usageSummary.sharedRequestsUsedToday /
                                        usageSummary.userDailyRequestCap) *
                                        100
                                    )
                                  )
                                : 100
                            }%`,
                          }}
                        />
                      </div>
                      <p className="mt-2 text-xs text-ink-muted">
                        Divided across {formatCount(usageSummary.enrolledUsers)} active{' '}
                        {usageSummary.enrolledUsers === 1 ? 'user' : 'users'} · Global server API pool:{' '}
                        {formatCount(usageSummary.systemPoolRemaining)} of{' '}
                        {formatCount(usageSummary.systemPoolTotal)} requests remaining today.
                      </p>
                    </div>

                    <dl className="divide-y divide-line">
                      <Row
                        label="Your total today (all models)"
                        value={`${formatCount(usageSummary.totalRequestsToday)} requests · ${formatCount(
                          usageSummary.totalTokensToday
                        )} tokens`}
                      />
                      <Row
                        label="Own API key (BYOK) & local today"
                        value={`${formatCount(usageSummary.byokRequestsToday)} BYOK · ${formatCount(
                          usageSummary.localRequestsToday
                        )} Local (unlimited, not counted against shared cap)`}
                      />
                      <Row
                        label="Total usage (all time)"
                        value={`${formatCount(usageSummary.totalRequestsAllTime)} requests · ${formatCount(
                          usageSummary.totalTokensAllTime
                        )} tokens`}
                      />
                    </dl>

                    {usageSummary.models.length > 0 ? (
                      <div className="p-4">
                        <div className="flex items-center justify-between text-xs text-ink-muted">
                          <h3 className="font-medium">Models used</h3>
                          <span>today · all-time · tokens</span>
                        </div>
                        <ul className="mt-2 divide-y divide-line rounded-md border border-line bg-subtle/30">
                          {usageSummary.models.map((item) => (
                            <li
                              key={`${item.provider}:${item.modelName}`}
                              className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-[13px]"
                            >
                              <div className="min-w-0">
                                <span className="font-medium text-ink">{item.modelName}</span>
                                <span className="ml-2 rounded bg-panel px-1.5 py-0.5 text-[11px] uppercase text-ink-muted">
                                  {item.provider}
                                </span>
                              </div>
                              <span className="text-xs tabular-nums text-ink-soft">
                                {formatCount(item.requestsToday)} reqs today ·{' '}
                                {formatCount(item.totalRequests)} total ·{' '}
                                {formatCount(item.totalTokens)} tokens
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : (
                      <p className="px-4 py-3 text-xs text-ink-muted">
                        No model requests recorded on this account yet.
                      </p>
                    )}
                  </div>
                )}

                <div className="flex items-center justify-between gap-3 border-t border-line bg-subtle/50 px-4 py-2.5">
                  <p className="text-xs text-ink-muted">
                    Resets daily at 00:00 UTC.
                  </p>
                  <PrimaryButton
                    variant="ghost"
                    size="sm"
                    onClick={() => void checkUsage()}
                    disabled={usageLoading}
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${usageLoading ? 'animate-spin' : ''}`} />
                    Refresh usage
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
