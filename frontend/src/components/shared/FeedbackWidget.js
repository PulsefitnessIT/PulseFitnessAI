/**
 * In-product feedback widget — Iter 216bc.
 *
 * Floating "How was this page?" button that drops a 👍/👎 + optional
 * comment into /api/feedback/in-product. Surfaces in Master Admin
 * alongside marketing chat insights.
 *
 * Mounted globally inside authed shells (Pulse, Memberships, CRM,
 * Marketing, Master Admin) — NOT on the marketing site (where the
 * MarketingChat is the equivalent).
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { ThumbsUp, ThumbsDown, MessageSquarePlus, X, Send, Check } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const DISMISS_KEY = 'gx_feedback_widget_dismissed_until';

export default function FeedbackWidget() {
  const [open, setOpen] = useState(false);
  const [sentiment, setSentiment] = useState(null);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [hidden, setHidden] = useState(true);

  useEffect(() => {
    const until = parseInt(localStorage.getItem(DISMISS_KEY) || '0', 10);
    if (Date.now() < until) return undefined;
    setHidden(false);
    return undefined;
  }, []);

  if (hidden) return null;

  const submit = async () => {
    if (!sentiment) return;
    setBusy(true);
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
      await axios.post(`${API}/feedback/in-product`, {
        sentiment,
        comment: comment || null,
        page_path: window.location.pathname,
      }, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      setDone(true);
      // Auto-collapse after 1.5s, dismiss for 24h.
      setTimeout(() => {
        localStorage.setItem(DISMISS_KEY, String(Date.now() + 24 * 60 * 60 * 1000));
        setOpen(false); setDone(false); setSentiment(null); setComment('');
      }, 1500);
    } catch { /* swallow — user feedback is best-effort */ }
    setBusy(false);
  };

  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="fixed bottom-5 left-5 z-[40] w-11 h-11 rounded-full bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 shadow-lg flex items-center justify-center hover:scale-105 transition-transform"
          aria-label="Send feedback"
          data-testid="gx-feedback-launcher"
          data-fab-rail
          data-fab-slot="secondary"
        >
          <MessageSquarePlus size={16} className="text-zinc-700 dark:text-zinc-300" />
        </button>
      )}

      {open && (
        <div
          className="fixed bottom-5 left-5 z-[45] w-[calc(100%-2.5rem)] max-w-sm rounded-2xl bg-white dark:bg-zinc-900 shadow-[0_24px_60px_-15px_rgba(15,23,42,0.4)] border border-zinc-200 dark:border-zinc-800 p-4"
          data-testid="gx-feedback-panel"
        >
          <div className="flex items-start justify-between mb-3">
            <p className="text-sm font-bold text-zinc-900 dark:text-zinc-100">How's this page?</p>
            <button onClick={() => setOpen(false)} className="p-1 -mt-1 -mr-1 text-zinc-400 hover:text-zinc-700" aria-label="Close" data-testid="gx-feedback-close">
              <X size={14} />
            </button>
          </div>

          {done ? (
            <p className="text-sm text-emerald-600 inline-flex items-center gap-1.5" data-testid="gx-feedback-thanks">
              <Check size={14} /> Thanks — logged.
            </p>
          ) : (
            <>
              <div className="flex items-center gap-2 mb-3">
                <button type="button" onClick={() => setSentiment('up')}
                  className={`flex-1 h-10 rounded-lg border text-xs font-bold inline-flex items-center justify-center gap-1.5 transition ${sentiment === 'up' ? 'bg-emerald-500 text-white border-emerald-500' : 'border-zinc-200 dark:border-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800'}`}
                  data-testid="gx-feedback-up">
                  <ThumbsUp size={13} /> Helpful
                </button>
                <button type="button" onClick={() => setSentiment('down')}
                  className={`flex-1 h-10 rounded-lg border text-xs font-bold inline-flex items-center justify-center gap-1.5 transition ${sentiment === 'down' ? 'bg-rose-500 text-white border-rose-500' : 'border-zinc-200 dark:border-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800'}`}
                  data-testid="gx-feedback-down">
                  <ThumbsDown size={13} /> Confusing
                </button>
              </div>
              <textarea
                value={comment} onChange={(e) => setComment(e.target.value)}
                placeholder="What would make this better? (optional)"
                className="w-full h-20 rounded-lg border border-zinc-200 dark:border-zinc-800 bg-transparent text-sm p-2 resize-none"
                maxLength={1000}
                data-testid="gx-feedback-comment"
              />
              <div className="flex items-center justify-between mt-3">
                <p className="text-[10px] text-zinc-500">Goes to the founder, not a spam folder.</p>
                <button type="button" onClick={submit} disabled={!sentiment || busy}
                  className="rounded-full bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 text-xs font-bold px-3 py-1.5 inline-flex items-center gap-1 disabled:opacity-50"
                  data-testid="gx-feedback-send">
                  {busy ? '...' : <><Send size={11} /> Send</>}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
}
