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
 * Placement: rendered inside OverviewTab on the main Pulse Fitness operator
 * dashboard + the Pulse Pro dashboard. Hidden once every milestone is
 * hit so the card disappears from the page naturally.
 */
import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { CheckCircle2, Circle, Sparkles, ArrowRight, X } from 'lucide-react';
import { useAuth } from '@/App';
import { useTranslation } from 'react-i18next';
import { useUserPref } from '@/utils/userPrefs';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const DISMISS_KEY = 'gymaxis:activation_milestones_dismissed';

// Map each milestone event_type to a concrete UI action hint so users
// know exactly where to go next. Iter 216h193 — paths are now resolved
// at click-time so Pulse Pro orgs (account_type === 'pulse_pro' / 'lite')
// land on `/pulse?…` and full Pulse Fitness orgs land on `/dashboard?…`. The
// `equipment` CTA also passes `onboarding=1` so the operations dashboard
// auto-opens the OnboardingWizard (Step 1: Add Your Equipment) rather
// than just switching tab — which was Craig's bug report.
//
// Iter 216h227 — added per-module CTAs for the new CRM / Marketing /
// Operations-fault milestones so each trial mode now has every "first
// win" actionable straight from the card (Lee's audit: a Marketing
// trial should never see "add a machine" as a suggested win).
const ACTION_HINTS = {
  first_login:             { hint: 'Welcome aboard — you\'re here.',  ops: false, suffix: null },
  first_staff_invited:     { hint: 'Invite a teammate',               ops: true,  suffix: '?tab=staffing' },
  module_activated:        { hint: 'Switch on another module',        ops: false, suffix: '/account?tab=modules' },
  // Operations
  first_equipment_added:   { hint: 'Add your first piece of equipment', ops: true,  suffix: '?tab=equipment&onboarding=1' },
  first_fault_logged:      { hint: 'Log your first fault',            ops: true,  suffix: '?tab=faults' },
  // Memberships
  first_member_added:      { hint: 'Add a member to Memberships',     ops: false, suffix: '/memberships?tab=members&add=1' },
  first_booking_taken:     { hint: 'Take your first class booking',   ops: false, suffix: '/memberships?tab=schedule' },
  first_invoice_generated: { hint: 'Generate your first invoice',     ops: false, suffix: '/memberships?tab=billing' },
  first_class_scheduled:   { hint: 'Schedule a class template',       ops: false, suffix: '/memberships?tab=schedule' },
  // CRM
  first_lead_added:        { hint: 'Add your first lead',             ops: false, suffix: '/crm?tab=companies&add=1' },
  first_deal_created:      { hint: 'Create your first deal',          ops: false, suffix: '/crm?tab=deals&add=1' },
  first_quote_sent:        { hint: 'Send your first quote',           ops: false, suffix: '/crm?tab=quotes' },
  // Marketing
  first_brand_discovered:  { hint: 'Discover your brand',             ops: false, suffix: '/marketing?tab=brand-discovery' },
  first_audience_built:    { hint: 'Build your first audience',       ops: false, suffix: '/marketing?tab=audiences&add=1' },
  first_campaign_launched: { hint: 'Launch your first campaign',      ops: false, suffix: '/marketing?tab=campaigns&add=1' },
};

export default function ActivationMilestonesCard({ hideWhenComplete = true }) {
  const { user } = useAuth();
  const { t } = useTranslation();
  const navigate = useNavigate();
  // Iter 216h193 — Operations base path swings between brands:
  //   • Pulse Fitness Pro / Lite orgs       → /pulse
  //   • Full Pulse Fitness Pro / everything else  → /dashboard
  // Picking the right one here means the equipment CTA opens the
  // OnboardingWizard on the user's actual operations page rather than
  // a stale /dashboard route that 404s for Pulse customers.
  const opsBase = (user?.account_type === 'pulse_pro' || user?.account_type === 'lite') ? '/pulse' : '/dashboard';
  const handleGo = (hint) => {
    if (!hint?.suffix && hint?.suffix !== '') return;
    const target = hint.ops ? `${opsBase}${hint.suffix}` : hint.suffix;
    navigate(target);
  };
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
              {t('activation.title', 'Your first wins')}
            </h3>
            <p
              className="text-sm mt-0.5"
              style={{ color: 'var(--theme-text-muted)' }}
            >
              {t('activation.subtitle', { fired, total, defaultValue: '{{fired}} of {{total}} milestones hit — teams that tick 3+ in week one stick around 4× longer.' })}
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
          aria-label={t('activation.dismiss', 'Dismiss activation milestones')}
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
                  className={`flex-1 min-w-0 ${m.fired ? 'opacity-70' : ''}`}
                  style={{ color: 'var(--theme-text)' }}
                >
                  {t(`activation.${m.event_type}`, m.label)}
                </span>
                {!m.fired && hint.suffix && (
                  <button
                    type="button"
                    onClick={() => handleGo(hint)}
                    className="flex-shrink-0 inline-flex items-center gap-1 text-xs font-semibold hover:underline cursor-pointer bg-transparent border-0 p-0"
                    style={{ color: 'var(--color-brand-blue)' }}
                    data-testid={`activation-cta-${m.event_type}`}
                  >
                    {t(`activation.hint_${m.event_type}`, hint.hint)}
                    <ArrowRight size={12} />
                  </button>
                )}
              </li>
            );
          })}
      </ul>
    </div>
  );
}
