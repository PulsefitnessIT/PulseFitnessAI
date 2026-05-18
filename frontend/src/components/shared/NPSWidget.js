import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { X, Send } from 'lucide-react';

/**
 * NPSWidget (iter 215c0)
 * Floating bottom-right NPS prompt. Shows once per 90 days per user.
 * Score 0–10 + optional comment, posted to /api/feedback/nps.
 *
 * Mount once near the root of authenticated layouts (e.g. inside
 * `LiteDashboardPage`). The widget self-checks `should-prompt` and
 * silently no-ops if not eligible.
 */
const NPSWidget = () => {
  const { API, user } = useAuth();
  const [eligible, setEligible] = useState(false);
  const [score, setScore] = useState(null);
  const [comment, setComment] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [open, setOpen] = useState(false);
  // Iter 216h214 — Craig's audit (h212) flagged "NPS popup on every page".
  // Two fixes:
  //   1. Persist closure in localStorage (not sessionStorage) so a refresh
  //      or new tab respects the dismissal until the server-side cooldown
  //      lifts naturally.
  //   2. Add a client-side "last-shown" cooldown of 7 days so even if the
  //      user just *ignores* the widget (doesn't click X), it doesn't
  //      ambush them on every page nav within the cooldown window.
  const [closedLocally, setClosedLocally] = useState(
    () => localStorage.getItem('nps_widget_closed') === '1'
          || sessionStorage.getItem('nps_widget_closed') === '1',
  );

  useEffect(() => {
    if (!user || closedLocally) return;
    // Iter 216h216 — Craig's audit: NPS should NEVER appear until the
    // user has actually used the platform — minimum 5 lifetime logins
    // (asking a brand-new trial user "how would I rate GymAxis" is
    // meaningless and reads as desperate). The login counter is
    // incremented in App.js on successful auth.
    const loginCount = Number(localStorage.getItem('login_count') || 0);
    if (loginCount < 5) return;
    // Client-side 7-day "shown recently" cooldown — silent backstop in
    // case the server's 90-day rule races a page nav.
    const lastShown = Number(localStorage.getItem('nps_widget_last_shown') || 0);
    const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;
    if (lastShown && Date.now() - lastShown < SEVEN_DAYS_MS) {
      return;
    }
    let cancel = false;
    const run = async () => {
      const token = localStorage.getItem('token');
      try {
        const res = await axios.get(`${API}/feedback/should-prompt`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!cancel && res.data?.should_prompt) {
          setEligible(true);
          // Lazy reveal after 8s so we don't ambush a user mid-task.
          setTimeout(() => {
            if (!cancel) {
              setOpen(true);
              localStorage.setItem('nps_widget_last_shown', String(Date.now()));
            }
          }, 8000);
        }
      } catch { /* silently skip */ }
    };
    run();
    return () => { cancel = true; };
  }, [API, user, closedLocally]);

  const submit = async () => {
    if (score == null) return;
    const token = localStorage.getItem('token');
    try {
      await axios.post(`${API}/feedback/nps`,
        { score, comment, page: window.location.pathname },
        { headers: { Authorization: `Bearer ${token}` } });
      setSubmitted(true);
      setTimeout(() => setOpen(false), 1500);
    } catch { /* ignore */ }
  };

  const dismiss = async () => {
    setOpen(false);
    // Iter 216h214 — persist across reloads + tabs (was sessionStorage).
    localStorage.setItem('nps_widget_closed', '1');
    sessionStorage.setItem('nps_widget_closed', '1');
    setClosedLocally(true);
    try {
      const token = localStorage.getItem('token');
      await axios.post(`${API}/feedback/dismiss`, {}, {
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch { /* ignore */ }
  };

  if (!eligible || !open || closedLocally) return null;

  return (
    <div
      data-testid="nps-widget"
      className="fixed bottom-4 right-4 z-[60] w-80 max-w-[92vw] rounded-2xl bg-[var(--theme-surface)] border border-[var(--theme-border)] shadow-xl p-5"
    >
      <button
        type="button"
        onClick={dismiss}
        data-testid="nps-widget-close"
        aria-label="Dismiss"
        className="absolute top-3 right-3 w-7 h-7 rounded-full hover:bg-[var(--theme-surface-hover)] flex items-center justify-center"
      >
        <X className="w-3.5 h-3.5 text-[var(--color-text-muted)]" />
      </button>

      {submitted ? (
        <p data-testid="nps-widget-thanks" className="text-sm text-[var(--theme-text)]">
          Thank you — your feedback helps us improve.
        </p>
      ) : (
        <>
          <p className="text-sm font-semibold text-[var(--theme-text)]">
            How likely are you to recommend GymAxis?
          </p>
          <p className="text-xs text-[var(--color-text-muted)] mt-1 mb-3">
            0 = not likely · 10 = very likely
          </p>

          <div className="grid grid-cols-11 gap-1 mb-3">
            {Array.from({ length: 11 }, (_, i) => (
              <button
                key={i}
                type="button"
                onClick={() => setScore(i)}
                data-testid={`nps-score-${i}`}
                className={`text-xs h-8 rounded-md font-semibold transition ${
                  score === i
                    ? 'bg-[var(--color-brand-blue)] text-white'
                    : 'bg-[var(--theme-surface-hover)] text-[var(--theme-text)] hover:bg-slate-200 dark:hover:bg-slate-700'
                }`}
              >
                {i}
              </button>
            ))}
          </div>

          {score != null && (
            <>
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder={
                  score >= 9 ? 'What do you love about it?' :
                  score >= 7 ? 'What would push it from a good to a great score?' :
                  'What would make it better?'
                }
                data-testid="nps-comment"
                maxLength={500}
                rows={2}
                className="w-full text-sm rounded-md border border-[var(--theme-border)] bg-[var(--theme-surface)] p-2 text-[var(--theme-text)] resize-none focus:outline-none focus:ring-1 focus:ring-[var(--color-brand-blue)]"
              />
              <button
                type="button"
                onClick={submit}
                data-testid="nps-submit"
                className="mt-2 w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-md bg-[var(--color-brand-blue)] text-white text-sm font-medium hover:opacity-90"
              >
                <Send className="w-3.5 h-3.5" /> Send feedback
              </button>
            </>
          )}
        </>
      )}
    </div>
  );
};

export default NPSWidget;
