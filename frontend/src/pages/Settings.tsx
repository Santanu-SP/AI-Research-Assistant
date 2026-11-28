import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CheckCircle2, ChevronDown, CircleAlert, LogOut, Monitor, Moon, RefreshCw, Sun } from 'lucide-react';
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
import {
  creditToneClasses,
  formatCompactTokens,
  formatLiveQuotaSummary,
  formatResetCountdown,
} from '../lib/modelCredits';
import { ModelsAndKeysPanel } from '../components/settings/ModelsAndKeysPanel';

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

const CHECK_LABELS: Record<string, { title: string; ok: string; bad: string }> = {
  database: {
    title: 'Saving your work',
    ok: 'Projects, files and reports can be saved.',
    bad: 'Your work can’t be saved right now.',
  },
  ollama: {
    title: 'Built-in model',
    ok: 'The model on this server can write answers.',
    bad: 'The model on this server isn’t running.',
  },
  llm_router: {
    title: 'Models',
    ok: 'At least one model is ready to answer.',
    bad: 'No model is set up yet. Add an API key above.',
  },
};

const checkLabel = (name: string) =>
  CHECK_LABELS[name] ?? { title: name.replace(/_/g, ' '), ok: 'Working', bad: 'Not working' };

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

  const checkUsage = useCallback(async (options?: { live?: boolean }) => {
    setUsageLoading(true);
    setUsageError(false);
    try {
      setUsageSummary(await byokService.getUsage(options));
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
          <PageHeader title="Settings" description="Your account, how the app looks, your models and API keys, and whether everything is working." />

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
              id="settings-models"
              title="Models & API keys"
              description="Add your own keys to use more models, and pick the model new research starts with."
            >
              <ModelsAndKeysPanel />
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
              title="System status"
              description="Whether the app can save your work and reach its models."
            >
              <details className="status-details group overflow-hidden rounded-lg border border-line bg-panel shadow-xs">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-[13px] [&::-webkit-details-marker]:hidden">
                  <span className="inline-flex items-center gap-2">
                    {checking && !readiness ? (
                      <span className="h-2.5 w-32 animate-pulse rounded bg-subtle" />
                    ) : readiness?.status === 'ready' ? (
                      <>
                        <CheckCircle2 className="h-4 w-4 text-accent" />
                        <span className="font-medium text-ink">Everything is working</span>
                      </>
                    ) : (
                      <>
                        <CircleAlert className="h-4 w-4 text-danger" />
                        <span className="font-medium text-ink">
                          {readiness ? 'Something needs attention' : 'Couldn’t check right now'}
                        </span>
                      </>
                    )}
                  </span>
                  <span className="inline-flex items-center gap-1 text-xs text-ink-muted">
                    <span className="group-open:hidden">Show details</span>
                    <span className="hidden group-open:inline">Hide details</span>
                    <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
                  </span>
                </summary>
                <div className="divide-y divide-line border-t border-line">
                  {checking && !readiness ? (
                    [0, 1].map((index) => (
                      <div key={index} className="flex h-[52px] items-center px-4">
                        <span className="h-2.5 w-40 animate-pulse rounded bg-subtle" />
                      </div>
                    ))
                  ) : readinessError || !readiness ? (
                    <div className="flex items-center gap-2.5 px-4 py-3.5 text-[13px] text-ink-soft">
                      <CircleAlert className="h-4 w-4 shrink-0 text-danger" />
                      The server didn’t respond, so nothing could be checked.
                    </div>
                  ) : (
                    readiness.checks.map((check) => (
                      <div key={check.name} className="flex min-h-[52px] items-center justify-between gap-4 px-4 py-2.5">
                        <div className="min-w-0">
                          <p className="text-[14px] text-ink">{checkLabel(check.name).title}</p>
                          <p className="truncate text-xs text-ink-muted" title={check.detail ?? undefined}>
                            {check.ok ? checkLabel(check.name).ok : checkLabel(check.name).bad}
                          </p>
                        </div>
                        <span
                          className={`inline-flex shrink-0 items-center gap-1.5 text-[13px] font-medium ${
                            check.ok ? 'text-accent' : 'text-danger'
                          }`}
                        >
                          {check.ok ? <CheckCircle2 className="h-4 w-4" /> : <CircleAlert className="h-4 w-4" />}
                          {check.ok ? 'Working' : 'Not working'}
                        </span>
                      </div>
                    ))
                  )}
                </div>
                <div className="flex items-center justify-between gap-3 border-t border-line bg-subtle/50 px-4 py-2.5">
                  <p className="text-xs text-ink-muted">Checked when you opened this page.</p>
                  <PrimaryButton variant="ghost" size="sm" onClick={() => void checkStatus()} disabled={checking}>
                    <RefreshCw className={`h-3.5 w-3.5 ${checking ? 'animate-spin' : ''}`} />
                    Check again
                  </PrimaryButton>
                </div>
              </details>
            </Section>

            <Section
              id="settings-model-usage"
              title="AI credits & renewal"
              description="Every account gets fixed per-model credits that never change when users join or leave. Burst credits renew every 3 hours and your full pool renews every 2 days."
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
                    Could not load AI credit status right now.
                  </div>
                ) : (
                  <div className="divide-y divide-line">
                    <div className="space-y-3.5 p-4">
                      {(() => {
                        const credits = usageSummary.providerCredits ?? [];
                        const sharedCredits = credits.filter((item) => item.mode === 'shared');
                        const unlimitedCredits = credits.filter((item) => item.unlimited);
                        const shortHours = usageSummary.shortWindowHours ?? 3;
                        const longDays = usageSummary.longWindowDays ?? 2;

                        return (
                          <>
                            {sharedCredits.length > 0 ? (
                              <div className="space-y-3">
                                {sharedCredits.map((credit) => {
                                  const tone = creditToneClasses(credit.remainingPct, false);
                                  const live = formatLiveQuotaSummary(credit);
                                  const hasToday = (credit.requestsToday ?? 0) > 0 || (credit.tokensToday ?? 0) > 0;
                                  return (
                                    <div key={credit.provider} className="space-y-1.5">
                                      <div className="flex flex-wrap items-baseline justify-between gap-2 text-[13px]">
                                        <span className="flex flex-wrap items-center gap-1.5 font-medium text-ink">
                                          <span>{credit.label}</span>
                                          {credit.modelName ? (
                                            <span className="text-xs font-normal text-ink-muted">
                                              {credit.modelName}
                                            </span>
                                          ) : null}
                                          <span className="rounded bg-subtle px-1.5 py-0.5 text-[10px] font-medium text-ink-muted">
                                            {live.badge}
                                          </span>
                                        </span>
                                        <span className={`font-semibold tabular-nums ${tone.textClass}`}>
                                          {credit.remainingPct}% remaining
                                        </span>
                                      </div>
                                      <div className="h-2 w-full overflow-hidden rounded-full bg-subtle">
                                        <div
                                          className={`h-full rounded-full transition-all ${tone.barClass}`}
                                          style={{ width: `${credit.remainingPct}%` }}
                                        />
                                      </div>
                                      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-muted">
                                        <span>
                                          {shortHours}-hour credits: {credit.shortWindowPct}% (resets in{' '}
                                          {formatResetCountdown(credit.shortResetsAt)})
                                        </span>
                                        <span>
                                          {longDays}-day pool: {credit.longWindowPct}% (resets in{' '}
                                          {formatResetCountdown(credit.longResetsAt)})
                                        </span>
                                      </div>
                                      {live.detail || hasToday ? (
                                        <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-ink-soft">
                                          {live.detail ? <span>{live.detail}</span> : <span />}
                                          {hasToday ? (
                                            <span className="tabular-nums text-ink-muted">
                                              Today: {formatCount(credit.requestsToday ?? 0)} runs
                                              {(credit.tokensToday ?? 0) > 0
                                                ? ` · ${formatCompactTokens(credit.tokensToday ?? 0)} tok`
                                                : ''}
                                            </span>
                                          ) : null}
                                        </div>
                                      ) : null}
                                    </div>
                                  );
                                })}
                              </div>
                            ) : (
                              <p className="text-[13px] text-ink-muted">
                                Unlimited access active with your own API key or Local Ollama (0 app credits used).
                              </p>
                            )}

                            {unlimitedCredits.length > 0 ? (
                              <div className="space-y-2 border-t border-line pt-3 text-xs">
                                <span className="text-ink-muted">Own keys &amp; local models (live provider status):</span>
                                <div className="space-y-1.5">
                                  {unlimitedCredits.map((credit) => {
                                    const live = formatLiveQuotaSummary(credit);
                                    const hasToday = (credit.requestsToday ?? 0) > 0 || (credit.tokensToday ?? 0) > 0;
                                    return (
                                      <div
                                        key={credit.provider}
                                        className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-line bg-subtle/40 px-2.5 py-1.5"
                                      >
                                        <div className="flex flex-wrap items-center gap-1.5">
                                          <span className="font-medium text-ink">
                                            {credit.label} ({credit.mode === 'local' ? 'Local' : 'Own key'})
                                          </span>
                                          <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 dark:text-emerald-300">
                                            {live.badge}
                                          </span>
                                        </div>
                                        <div className="flex flex-wrap items-center gap-2 text-[11px] tabular-nums text-ink-soft">
                                          {live.detail ? <span>{live.detail}</span> : null}
                                          {hasToday ? (
                                            <span className="text-ink-muted">
                                              {formatCount(credit.requestsToday ?? 0)} runs
                                              {(credit.tokensToday ?? 0) > 0
                                                ? ` · ${formatCompactTokens(credit.tokensToday ?? 0)} tok today`
                                                : ' today'}
                                            </span>
                                          ) : !live.detail ? (
                                            <span className="text-ink-muted">No usage recorded yet today</span>
                                          ) : null}
                                        </div>
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            ) : null}
                          </>
                        );
                      })()}
                    </div>

                    <details className="group">
                      <summary className="flex cursor-pointer items-center justify-between px-4 py-2.5 text-xs font-medium text-ink-muted hover:text-ink">
                        <span>Detailed activity counters</span>
                        <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
                      </summary>
                      <div className="border-t border-line">
                        <dl className="divide-y divide-line">
                          <Row
                            label="Your runs today (all models)"
                            value={`${formatCount(usageSummary.totalRequestsToday)} runs · ${formatCount(
                              usageSummary.byokRequestsToday
                            )} own key · ${formatCount(usageSummary.localRequestsToday)} Local`}
                          />
                          <Row
                            label="All-time completed runs"
                            value={`${formatCount(usageSummary.totalRequestsAllTime)} runs · ${formatCount(
                              usageSummary.totalTokensAllTime
                            )} tokens`}
                          />
                        </dl>
                        {usageSummary.models.length > 0 ? (
                          <div className="border-t border-line p-4">
                            <ul className="divide-y divide-line rounded-md border border-line bg-subtle/30">
                              {usageSummary.models.map((item) => (
                                <li
                                  key={`${item.provider}:${item.modelName}`}
                                  className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-xs"
                                >
                                  <span className="font-medium text-ink">
                                    {item.provider} / {item.modelName}
                                  </span>
                                  <span className="tabular-nums text-ink-soft">
                                    {formatCount(item.requestsToday)} today · {formatCount(item.totalRequests)} total
                                  </span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        ) : null}
                      </div>
                    </details>
                  </div>
                )}

                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line bg-subtle/50 px-4 py-2.5">
                  <p className="text-xs text-ink-muted">
                    {usageSummary
                      ? `Next ${usageSummary.shortWindowHours ?? 3}h renewal in ${formatResetCountdown(
                          usageSummary.shortResetsAt ?? usageSummary.resetsAt
                        )} · Next ${usageSummary.longWindowDays ?? 2}-day renewal in ${formatResetCountdown(
                          usageSummary.longResetsAt ?? usageSummary.resetsAt
                        )}`
                      : 'Fixed credits renew every 3 hours and every 2 days.'}
                  </p>
                  <PrimaryButton
                    variant="ghost"
                    size="sm"
                    onClick={() => void checkUsage({ live: true })}
                    disabled={usageLoading}
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${usageLoading ? 'animate-spin' : ''}`} />
                    Refresh credits
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
