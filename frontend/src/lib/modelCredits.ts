import {
  ModelUsageQuotaSummary,
  ProviderCreditItem,
  ProviderStatusItem,
} from '../services/clientAi.service';

export interface CreditTone {
  badgeClass: string;
  textClass: string;
  barClass: string;
}

export interface TopBarCreditBadge {
  label: string;
  pct: number;
  unlimited: boolean;
  title: string;
  tone: CreditTone;
}

/** Format an ISO reset timestamp into a concise countdown like "2h 14m" or "1d 14h". */
export const formatResetCountdown = (
  isoString: string | null | undefined,
  nowMs: number = Date.now(),
): string => {
  if (!isoString) return 'soon';
  const targetMs = Date.parse(isoString);
  if (Number.isNaN(targetMs)) return 'soon';
  const diffSec = Math.max(0, Math.floor((targetMs - nowMs) / 1000));
  if (diffSec < 60) return 'soon';
  if (diffSec >= 86_400) {
    const days = Math.floor(diffSec / 86_400);
    const hours = Math.floor((diffSec % 86_400) / 3_600);
    return `${days}d ${hours}h`;
  }
  if (diffSec >= 3_600) {
    const hours = Math.floor(diffSec / 3_600);
    const mins = Math.floor((diffSec % 3_600) / 60);
    return `${hours}h ${mins}m`;
  }
  return `${Math.max(1, Math.floor(diffSec / 60))}m`;
};

/** Pick subtle emerald / amber / danger styling matching credit remaining percentage. */
export const creditToneClasses = (pct: number, unlimited = false): CreditTone => {
  if (unlimited) {
    return {
      badgeClass: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
      textClass: 'text-emerald-700 dark:text-emerald-300',
      barClass: 'bg-emerald-500',
    };
  }
  if (pct <= 0) {
    return {
      badgeClass: 'bg-danger/15 text-danger',
      textClass: 'text-danger',
      barClass: 'bg-danger',
    };
  }
  if (pct <= 20) {
    return {
      badgeClass: 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
      textClass: 'text-amber-700 dark:text-amber-300',
      barClass: 'bg-amber-500',
    };
  }
  return {
    badgeClass: 'bg-subtle text-ink-soft',
    textClass: 'text-ink-soft',
    barClass: 'bg-emerald-500',
  };
};

/** Resolve an overall percentage (0-100) safely even when older fixtures omit providerCredits. */
export const resolveEffectiveUsagePct = (usage: ModelUsageQuotaSummary): number => {
  if (typeof usage.overallRemainingPct === 'number' && !Number.isNaN(usage.overallRemainingPct)) {
    return Math.max(0, Math.min(100, Math.round(usage.overallRemainingPct)));
  }
  if (usage.userDailyRequestCap <= 0) return 100;
  return Math.max(
    0,
    Math.min(100, Math.round((usage.userRequestsRemainingToday / usage.userDailyRequestCap) * 100)),
  );
};

export const getProviderCredit = (
  usage: ModelUsageQuotaSummary | null | undefined,
  providerId: string,
): ProviderCreditItem | null => {
  if (!usage?.providerCredits?.length) return null;
  return usage.providerCredits.find((item) => item.provider === providerId) ?? null;
};

/** Compute the compact credit badge displayed in the top Models button. */
export const resolveTopBarCreditBadge = (
  usage: ModelUsageQuotaSummary,
  preferredProvider: string | null,
  providers: ProviderStatusItem[],
): TopBarCreditBadge => {
  const shortHours = usage.shortWindowHours ?? 3;
  const longDays = usage.longWindowDays ?? 2;
  const shortIn = formatResetCountdown(usage.shortResetsAt ?? usage.resetsAt);
  const longIn = formatResetCountdown(usage.longResetsAt ?? usage.resetsAt);
  const baseSchedule = `Fixed credits per account · Burst credits renew every ${shortHours}h (in ${shortIn}) and full pool every ${longDays} days (in ${longIn}). Own API key & Local Ollama are unlimited.`;

  if (preferredProvider === 'ollama') {
    return {
      label: 'Unlimited',
      pct: 100,
      unlimited: true,
      title: `Local Ollama uses 0 server credits. ${baseSchedule}`,
      tone: creditToneClasses(100, true),
    };
  }

  if (preferredProvider) {
    const prov = providers.find((item) => item.id === preferredProvider);
    const credit = getProviderCredit(usage, preferredProvider);
    if (prov?.configuredByok || credit?.unlimited) {
      return {
        label: 'Unlimited',
        pct: 100,
        unlimited: true,
        title: `${prov?.label ?? preferredProvider} is using your own key (0 server credits used). ${baseSchedule}`,
        tone: creditToneClasses(100, true),
      };
    }
    if (credit) {
      return {
        label: `${credit.remainingPct}% credits`,
        pct: credit.remainingPct,
        unlimited: false,
        title: `${credit.label}: ${credit.remainingPct}% remaining (${shortHours}h cycle: ${credit.shortWindowPct}%, ${longDays}-day cycle: ${credit.longWindowPct}%). ${baseSchedule}`,
        tone: creditToneClasses(credit.remainingPct, false),
      };
    }
  }

  const sharedItems = (usage.providerCredits ?? []).filter((item) => item.mode === 'shared');
  if ((usage.providerCredits?.length ?? 0) > 0 && sharedItems.length === 0) {
    return {
      label: 'Unlimited',
      pct: 100,
      unlimited: true,
      title: `Only unlimited own-key or local models are active. ${baseSchedule}`,
      tone: creditToneClasses(100, true),
    };
  }

  const pct = resolveEffectiveUsagePct(usage);
  return {
    label: `${pct}% credits`,
    pct,
    unlimited: false,
    title: `Overall shared model credits: ${pct}% remaining. ${baseSchedule}`,
    tone: creditToneClasses(pct, false),
  };
};
