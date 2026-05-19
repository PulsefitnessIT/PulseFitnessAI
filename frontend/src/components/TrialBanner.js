/* Trial Banner — sits at top of authenticated shell.
 *
 * Shows a live countdown (days · hours · minutes) until the trial ends, plus
 * a slim progress bar to amplify urgency as expiry approaches. Recomputes
 * once per minute without re-fetching the user.
 */
import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { notify } from '@/components/notifications';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Clock, AlertTriangle, Zap, X } from 'lucide-react';
import { useAuth } from '@/App';

// GymAxis default trial length (days). Used to render the % progress bar
// when the org doesn't return `trial_duration_days`.
const DEFAULT_TRIAL_DAYS = 3;

function useNowTicker(intervalMs = 60_000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

function formatRemaining(msLeft) {
  if (msLeft <= 0) return { primary: 'Expired', secondary: '' };
  const totalMinutes = Math.floor(msLeft / 60_000);
  const days = Math.floor(totalMinutes / (60 * 24));
  const hours = Math.floor((totalMinutes - days * 24 * 60) / 60);
  const minutes = totalMinutes - days * 24 * 60 - hours * 60;
  if (days >= 1) return { primary: `${days}d ${hours}h`, secondary: `${minutes}m` };
  if (hours >= 1) return { primary: `${hours}h ${minutes}m`, secondary: '' };
  return { primary: `${minutes}m`, secondary: '' };
}

export default function TrialBanner() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [dismissed, setDismissed] = useState(false);
  const now = useNowTicker(60_000);

  const trial = user?.trial;

  // Memoized derived figures (must run unconditionally — hooks ordering).
  const { msLeft, totalMs, pctElapsed, remaining } = useMemo(() => {
    const ends = trial?.trial_ends_at ? new Date(trial.trial_ends_at).getTime() : 0;
    const totalDays = trial?.trial_duration_days || DEFAULT_TRIAL_DAYS;
    const total = totalDays * 24 * 60 * 60 * 1000;
    const left = Math.max(0, ends - now);
    const elapsed = Math.max(0, Math.min(100, ((total - left) / total) * 100));
    return {
      msLeft: left,
      totalMs: total,
      pctElapsed: elapsed,
      remaining: formatRemaining(left),
    };
  }, [trial?.trial_ends_at, trial?.trial_duration_days, now]);

  if (!trial?.is_trial || trial?.status === 'converted') return null;
  if (dismissed && trial.status !== 'expiring_soon' && trial.status !== 'expired') return null;
  if (trial.status === 'expired' || trial.status === 'suspended') return null; // full-screen lock handles these

  const isExpiringSoon = trial.status === 'expiring_soon' || msLeft < 24 * 60 * 60 * 1000;
  const canOwnerUpgrade = user.role === 'owner';

  const upgrade = async () => {
    if (!canOwnerUpgrade) {
      notify.info('Ask your organisation owner to upgrade.');
      return;
    }
    // Iter 216o-8 — instead of force-buying the bundle, send the user to
    // /pricing so they can choose between the Pro Bundle and the
    // individual modules (Memberships / CRM / Marketing / Operations).
    // The URL is scoped with `?from=trial` so /pricing can highlight the
    // CTA flow + fall back to a guided Stripe checkout link from there.
    navigate('/pricing?from=trial');
  };

  const barTone = isExpiringSoon
    ? 'bg-amber-50 border-amber-300 text-amber-900'
    : 'bg-blue-50 border-blue-300 text-blue-900';
  const Icon = isExpiringSoon ? AlertTriangle : Clock;
  const progressTone = isExpiringSoon ? 'bg-amber-500' : 'bg-blue-500';

  // Don't render the bar if we don't have a real end timestamp — fall
  // back to the simpler day-only message so the banner still appears.
  const haveLiveCountdown = totalMs > 0 && trial?.trial_ends_at;

  return (
    <div className={`border-b ${barTone}`} data-testid="trial-banner">
      <div className="max-w-full px-4 py-2.5 flex items-center gap-3 flex-wrap">
        <Icon size={16} className="flex-shrink-0" />
        <div className="flex-1 min-w-0 flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium">
            {isExpiringSoon ? 'Trial ending soon —' : 'Free trial —'}
          </span>
          {haveLiveCountdown ? (
            <span
              className="inline-flex items-baseline gap-1.5 font-mono text-sm font-semibold tabular-nums"
              data-testid="trial-banner-countdown"
            >
              <span>{remaining.primary}</span>
              {remaining.secondary && (
                <span className="text-xs opacity-70">{remaining.secondary}</span>
              )}
              <span className="text-xs font-medium opacity-70 font-sans"> remaining</span>
            </span>
          ) : (
            <span className="text-sm font-medium" data-testid="trial-banner-days-fallback">
              {`${trial.days_left || 0} day${trial.days_left === 1 ? '' : 's'} remaining`}
            </span>
          )}
          <Badge className="bg-white/70 text-current capitalize border border-current/20">Trial</Badge>
        </div>
        <Button
          size="sm"
          onClick={upgrade}
          className="bg-blue-600 hover:bg-blue-700 text-white"
          data-testid="trial-upgrade-btn"
        >
          <Zap size={12} className="mr-1" />
          Upgrade Plan
        </Button>
        {!isExpiringSoon && (
          <button
            onClick={() => setDismissed(true)}
            className="p-1 hover:bg-white/50 rounded"
            aria-label="Dismiss"
            data-testid="trial-banner-dismiss"
          >
            <X size={14} />
          </button>
        )}
      </div>
      {haveLiveCountdown && (
        <div
          className="h-1 w-full bg-current/10 overflow-hidden"
          data-testid="trial-banner-progress"
          role="progressbar"
          aria-valuenow={Math.round(pctElapsed)}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className={`h-full ${progressTone} transition-all duration-700 ease-out`}
            style={{ width: `${pctElapsed}%` }}
          />
        </div>
      )}
    </div>
  );
}
