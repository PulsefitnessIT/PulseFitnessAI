/**
 * SetupChecklist — first-login progress tracker.
 *
 * Floats a small "Setup progress" pill in the bottom-left of every
 * authenticated page (sibling of the Ask GymAxis assistant). Clicking
 * expands a checklist drawer with live progress (queried from
 * `/api/help/setup-checklist` on mount + when walkthroughs finish).
 *
 * Auto-hides when:
 *   - user has dismissed it (per-device localStorage flag);
 *   - all items are done;
 *   - the user is on `/help`, `/login`, public pages, or any page where
 *     the existing assistants would be cluttered.
 *
 * Items link directly to the relevant module / open the matching guide
 * in the Help Centre. Walkthroughs from the Help Centre auto-recheck
 * this list when they finish.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { CheckCircle2, Circle, ChevronUp, ChevronDown, X, Sparkles, BookOpen } from 'lucide-react';

const DISMISS_KEY = 'gymaxis_setup_checklist_dismissed';
// Pages where we hide the widget — mostly noise reduction. /help has
// its own progress UX, public pages have no auth.
// Iter 215be — paths where the floating "Setup progress" pill must NOT
// render. Includes:
//   • Public/marketing routes (/, /pricing, /contact, /security, /about,
//     /modules/*) — even when a user is logged in. The pill is for
//     in-app onboarding, not a public-page nudge.
//   • Auth & flow routes (/login, /reset-password, /onboarding/*).
//   • White-label member surfaces (/m/, /instructor, /checkin, /embed,
//     /scan, /supplier).
//   • Internal dev surfaces (/help, /admin/design-system).
const HIDDEN_PATH_PREFIXES = ['/help', '/login', '/reset-password', '/m/', '/instructor', '/checkin', '/embed', '/scan', '/supplier', '/onboarding/', '/admin/design-system', '/pricing', '/contact', '/security', '/about', '/modules/'];

// Exact paths to hide the pill on (no prefix match — these are pages
// that have child routes we still want the pill on).
const HIDDEN_PATH_EXACT = new Set(['/']);

export default function SetupChecklist() {
  // Iter 215dj — global floating pill removed per user feedback (covered
  // bottom-nav on mobile, redundant with the Start tab's "Your first
  // wins" card). Component now no-ops; equivalent UX lives in
  // WelcomeHero / per-module Start tabs.
  return null;
  /* eslint-disable no-unreachable */
  // The legacy implementation below is intentionally kept for reference
  // — see Iter 215dj rollback plan. Wrapped in an eslint-disable region
  // so the unreachable scaffolding doesn't fail the Quality Gate.
  const location = useLocation();
  const navigate = useNavigate();
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState(() => {
    try { return localStorage.getItem(DISMISS_KEY) === 'true'; } catch { return false; }
  });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  // Hide on certain routes (public, help, etc.)
  const hidden = useMemo(() => {
    if (!location?.pathname) return true;
    if (HIDDEN_PATH_EXACT.has(location.pathname)) return true;
    return HIDDEN_PATH_PREFIXES.some((p) => location.pathname.startsWith(p));
  }, [location?.pathname]);

  const loadProgress = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const r = await axios.get(`${API}/help/setup-checklist`, { headers: { Authorization: `Bearer ${token}` } });
      setData(r.data);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [API, token]);

  // Initial load + re-check on walkthrough completion.
  useEffect(() => {
    if (!token || dismissed || hidden) return;
    loadProgress();
    const onWalkthroughDone = () => loadProgress();
    window.addEventListener('gymaxis:walkthrough-done', onWalkthroughDone);
    // Also re-check when other in-app changes happen — the major
    // events that move the needle on the checklist:
    const events = ['gymaxis:equipment-added', 'gymaxis:fault-logged', 'gymaxis:user-invited', 'gymaxis:member-added', 'gymaxis:plan-created', 'gymaxis:campaign-launched'];
    events.forEach((e) => window.addEventListener(e, onWalkthroughDone));
    // Catch-all: refresh when the user returns to the tab after doing
    // anything elsewhere (e.g. configuring Stripe in another window).
    window.addEventListener('focus', onWalkthroughDone);
    return () => {
      window.removeEventListener('gymaxis:walkthrough-done', onWalkthroughDone);
      events.forEach((e) => window.removeEventListener(e, onWalkthroughDone));
      window.removeEventListener('focus', onWalkthroughDone);
    };
  }, [token, dismissed, hidden, loadProgress]);

  const dismiss = () => {
    try { localStorage.setItem(DISMISS_KEY, 'true'); } catch { /* noop */ }
    setDismissed(true);
  };

  // Allow re-opening from the Help Centre with a custom event.
  useEffect(() => {
    const reopen = () => {
      try { localStorage.removeItem(DISMISS_KEY); } catch { /* noop */ }
      setDismissed(false);
      setOpen(true);
    };
    window.addEventListener('gymaxis:reopen-checklist', reopen);
    return () => window.removeEventListener('gymaxis:reopen-checklist', reopen);
  }, []);

  if (!token || dismissed || hidden || !data) return null;
  if (data.total_count === 0) return null;
  if (data.completed_count === data.total_count) return null;

  return (
    <div
      className="fixed bottom-5 left-5 z-[60] pulse-font-body"
      data-testid="setup-checklist-widget"
    >
      {!open ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="rounded-full pl-4 pr-3 py-2 inline-flex items-center gap-2 text-xs font-semibold border shadow-lg transition-all hover:-translate-y-0.5"
          style={{ background: 'var(--theme-surface)', color: 'var(--theme-text)', borderColor: 'var(--theme-border)', boxShadow: '0 16px 30px -12px rgba(0,0,0,0.35)' }}
          data-testid="setup-checklist-pill"
        >
          <Sparkles size={13} style={{ color: 'var(--color-brand-cyan)' }} />
          <span>Setup progress</span>
          <span
            className="ml-1 inline-flex items-center justify-center rounded-full px-2 h-5 text-[11px] font-bold"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}
          >
            {data.completed_count}/{data.total_count}
          </span>
          <ChevronUp size={12} className="opacity-70 ml-0.5" />
        </button>
      ) : (
        <div
          className="rounded-2xl border w-80 max-w-[92vw] overflow-hidden"
          style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', boxShadow: '0 28px 56px -16px rgba(0,0,0,0.45)' }}
          data-testid="setup-checklist-panel"
        >
          {/* Header */}
          <div className="flex items-center gap-2 px-4 pt-3 pb-2">
            <Sparkles size={13} style={{ color: 'var(--color-brand-cyan)' }} />
            <div className="text-sm font-semibold pulse-font-heading flex-1" style={{ color: 'var(--theme-text)' }}>
              Get started in 7 steps
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="opacity-60 hover:opacity-100"
              aria-label="Collapse"
              data-testid="setup-checklist-collapse"
            >
              <ChevronDown size={14} style={{ color: 'var(--theme-text-muted)' }} />
            </button>
            <button
              type="button"
              onClick={dismiss}
              className="opacity-60 hover:opacity-100"
              aria-label="Dismiss"
              data-testid="setup-checklist-dismiss"
            >
              <X size={14} style={{ color: 'var(--theme-text-muted)' }} />
            </button>
          </div>

          {/* Progress bar */}
          <div className="px-4 pb-3">
            <div className="flex items-center justify-between text-[11px] mb-1.5" style={{ color: 'var(--theme-text-muted)' }}>
              <span>{data.completed_count} of {data.total_count} done</span>
              <span>{data.percent}%</span>
            </div>
            <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--theme-border)' }}>
              <div
                className="h-full transition-all"
                style={{ width: `${data.percent}%`, background: 'var(--color-brand-cyan)' }}
                data-testid="setup-checklist-progress-bar"
              />
            </div>
          </div>

          {/* Items */}
          <ul className="max-h-80 overflow-y-auto" data-testid="setup-checklist-items">
            {data.items.map((it) => (
              <li
                key={it.id}
                className="px-4 py-2.5 border-t flex items-start gap-2.5 transition-colors"
                style={{ borderColor: 'var(--theme-border)', background: it.completed ? 'transparent' : 'rgba(25,205,255,0.04)' }}
                data-testid={`setup-checklist-item-${it.id}`}
              >
                {it.completed ? (
                  <CheckCircle2 size={15} className="flex-shrink-0 mt-0.5" style={{ color: 'var(--color-success)' }} />
                ) : (
                  <Circle size={15} className="flex-shrink-0 mt-0.5" style={{ color: 'var(--theme-text-muted)' }} />
                )}
                <div className="min-w-0 flex-1">
                  <div className={`text-xs ${it.completed ? 'line-through opacity-60' : 'font-semibold'} pulse-font-body`} style={{ color: 'var(--theme-text)' }}>
                    {it.label}
                  </div>
                  <div className="mt-1 flex items-center gap-2">
                    {!it.completed && (
                      <button
                        type="button"
                        onClick={() => { setOpen(false); navigate(it.href); }}
                        className="text-[11px] font-semibold inline-flex items-center gap-1 rounded-full px-2.5 py-1 transition-colors"
                        style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}
                        data-testid={`setup-checklist-go-${it.id}`}
                      >
                        Take me there
                      </button>
                    )}
                    {it.guide_id && (
                      <button
                        type="button"
                        onClick={() => { setOpen(false); navigate(`/help/${it.guide_id}`); }}
                        className="text-[11px] inline-flex items-center gap-1 opacity-70 hover:opacity-100"
                        style={{ color: 'var(--theme-text-muted)' }}
                        data-testid={`setup-checklist-guide-${it.id}`}
                      >
                        <BookOpen size={10} /> Guide
                      </button>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>

          <div className="px-4 py-2.5 border-t text-[11px] flex items-center justify-between" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>
            {loading ? <span>Refreshing…</span> : <span>Updates as you complete tasks.</span>}
            <button type="button" onClick={loadProgress} className="opacity-70 hover:opacity-100" data-testid="setup-checklist-refresh">Refresh</button>
          </div>
        </div>
      )}
    </div>
  );
}
