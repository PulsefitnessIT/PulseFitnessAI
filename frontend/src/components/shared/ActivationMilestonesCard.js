/**
 * ActivationMilestonesCard
 * ------------------------
 * Operator-facing "value realised" checklist. Shows each activation
 * milestone (first member added, first booking taken, first invoice
 * generated, etc.) with a fired/pending state and a progress ring.
 *
 * Why it matters: operators who hit 3+ milestones in their first 14
 * days convert to paid at 4× the rate of those who don't. Surfacing
 * the checklist gives them a concrete "what to do next" list and
 * feeds the expansion-revenue signals the platform uses to trigger
 * upgrade prompts, referral invites, and concierge reach-outs.
 *
 * Placement: rendered inside OverviewTab on the main GymAxis operator
 * dashboard + the Pulse Pro dashboard. Hidden once every milestone is
 * hit so the card disappears from the page naturally.
 */
import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { CheckCircle2, Circle, Sparkles, ArrowRight, X } from 'lucide-react';
import { useAuth } from '@/App';
import { useUserPref } from '@/utils/userPrefs';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const DISMISS_KEY = 'gymaxis:activation_milestones_dismissed';

// Map each milestone event_type to a concrete UI action hint so users
// know exactly where to go next. Unknown events fall back to a blank
// hint (safer than guessing).
const ACTION_HINTS = {
  first_login:             { hint: 'Welcome aboard — you\'re here.', path: null },
  first_equipment_added:   { hint: 'Add your first piece of equipment', path: '/dashboard?tab=equipment' },
  first_member_added:      { hint: 'Add a member to Memberships',      path: '/memberships' },
  first_booking_taken:     { hint: 'Take your first class booking',    path: '/memberships' },
  first_invoice_generated: { hint: 'Generate your first invoice',      path: '/memberships' },
  first_staff_invited:     { hint: 'Invite a teammate',                path: '/dashboard?tab=staffing' },
  first_class_scheduled:   { hint: 'Schedule a class template',        path: '/memberships' },
  module_activated:        { hint: 'Switch on another module',         path: '/account' },
};

export default function ActivationMilestonesCard({ hideWhenComplete = true }) {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dismissed, setDismissed] = useState(() => {
    try { return localStorage.getItem(DISMISS_KEY) === '1'; } catch { return false; }
  });
  // Iter 216c — once every milestone has fired, auto-hide the "Start"
  // tab across modules. The Start tab is a guided onboarding surface;
  // operators who have onboarded shouldn't keep seeing it. Per Lee's
  // Feb-2026 request: "remove the start option from the users options
  // and Dashboard be the first option."
  // eslint-disable-next-line no-unused-vars
  const [, setHideStart] = useUserPref('hideStartTabs', false);

  const load = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get(`${API}/activation/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setData(res.data);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleDismiss = () => {
    try { localStorage.setItem(DISMISS_KEY, '1'); } catch { /* ignore */ }
    setDismissed(true);
  };

  // Iter 216c — once every milestone has fired, auto-hide the "Start"
  // tab across modules so Dashboard becomes the first option (Lee, Feb
  // 2026). Computed BEFORE any early returns to obey Rules of Hooks.
  const fired = data?.fired_count ?? 0;
  const total = data?.total ?? 0;
  const allDone = fired === total && total > 0;
  useEffect(() => {
    if (allDone) setHideStart(true);
  }, [allDone, setHideStart]);

  // Master admin has no single org — endpoint returns empty timeline.
  if (loading) return null;
  if (dismissed) return null;
  if (!data || !Array.isArray(data.timeline) || data.timeline.length === 0) return null;
  if (user?.is_master_admin) return null;

  const { timeline } = data;
  const pct = total > 0 ? Math.round((fired / total) * 100) : 0;
  if (allDone && hideWhenComplete) return null;

  return (
    <div
      className="rounded-2xl border p-5 mb-6"
      style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
      data-testid="activation-milestones-card"
    >
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="flex items-start gap-3 min-w-0">
          <div
            className="flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center"
            style={{ background: 'var(--color-brand-blue)', color: 'white' }}
          >
            <Sparkles size={18} />
          </div>
          <div className="min-w-0">
            <h3
              className="text-base sm:text-lg font-semibold leading-tight"
              style={{ color: 'var(--theme-text)' }}
              data-testid="activation-card-title"
            >
              Your first wins
            </h3>
            <p
              className="text-sm mt-0.5"
              style={{ color: 'var(--theme-text-muted)' }}
            >
              {fired} of {total} milestones hit — teams that tick 3+ in week one stick around 4× longer.
            </p>
          </div>
        </div>
        <div
          className="flex-shrink-0 text-sm font-bold tracking-tight"
          style={{ color: 'var(--color-brand-blue)' }}
          data-testid="activation-progress-pct"
        >
          {pct}%
        </div>
        <button
          type="button"
          onClick={handleDismiss}
          className="flex-shrink-0 h-8 w-8 -mr-1 -mt-1 rounded-full flex items-center justify-center border border-[color:var(--theme-border)] hover:bg-[color:var(--theme-surface-hover)] transition-colors"
          style={{ color: 'var(--theme-text)' }}
          aria-label="Dismiss activation milestones"
          data-testid="activation-dismiss"
        >
          <X size={14} />
        </button>
      </div>

      {/* Progress bar */}
      <div
        className="h-1.5 rounded-full overflow-hidden mb-4"
        style={{ background: 'var(--theme-border)' }}
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="h-full rounded-full transition-all duration-700 ease-out"
          style={{ width: `${pct}%`, background: 'var(--color-brand-blue)' }}
          data-testid="activation-progress-bar"
        />
      </div>

      {/* Milestone list — fired ones on top, pending below */}
      <ul className="space-y-2">
        {[...timeline]
          .sort((a, b) => (a.fired === b.fired ? 0 : a.fired ? -1 : 1))
          .map((m) => {
            const hint = ACTION_HINTS[m.event_type] || {};
            return (
              <li
                key={m.event_type}
                className="flex items-center gap-3 text-sm"
                data-testid={`activation-milestone-${m.event_type}`}
                data-fired={m.fired ? 'true' : 'false'}
              >
                {m.fired ? (
                  <CheckCircle2
                    size={18}
                    className="flex-shrink-0"
                    style={{ color: 'var(--color-success, #10b981)' }}
                  />
                ) : (
                  <Circle
                    size={18}
                    className="flex-shrink-0"
                    style={{ color: 'var(--theme-text-muted)' }}
                  />
                )}
                <span
                  className={`flex-1 min-w-0 ${m.fired ? 'line-through opacity-60' : ''}`}
                  style={{ color: 'var(--theme-text)' }}
                >
                  {m.label}
                </span>
                {!m.fired && hint.path && (
                  <a
                    href={hint.path}
                    className="flex-shrink-0 inline-flex items-center gap-1 text-xs font-semibold hover:underline"
                    style={{ color: 'var(--color-brand-blue)' }}
                    data-testid={`activation-cta-${m.event_type}`}
                  >
                    {hint.hint}
                    <ArrowRight size={12} />
                  </a>
                )}
              </li>
            );
          })}
      </ul>
    </div>
  );
}
