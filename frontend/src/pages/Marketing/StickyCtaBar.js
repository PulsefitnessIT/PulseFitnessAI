/**
 * Sticky scroll-CTA bar — Iter 216ba.
 *
 * Appears after the user scrolls past the hero on any marketing page.
 * Slim, dismissible, with the always-on "Start Free Trial" anchor so
 * the CTA is never more than one tap away no matter how far the user
 * scrolls.
 */
import { useEffect, useState } from 'react';
import { ArrowRight, X, Sparkles } from 'lucide-react';
import { openTrial } from './TrialSignupModal';

const DISMISS_KEY = 'gx_sticky_cta_dismissed_at';
const DISMISS_TTL_MS = 1000 * 60 * 60 * 24;     // 24h cool-off after dismiss

export default function StickyCtaBar() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // Honour a recent dismiss
    const last = parseInt(localStorage.getItem(DISMISS_KEY) || '0', 10);
    if (last && Date.now() - last < DISMISS_TTL_MS) return undefined;

    const onScroll = () => {
      const past = (window.scrollY || document.documentElement.scrollTop) > 600;
      const nearBottom = (window.innerHeight + window.scrollY) >= (document.body.offsetHeight - 200);
      // Show after hero, hide right at the bottom (final CTA already there).
      setVisible(past && !nearBottom);
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  if (!visible) return null;

  return (
    <div
      role="region" aria-label="Start free trial"
      className="fixed bottom-3 left-1/2 -translate-x-1/2 z-[60] w-[calc(100%-1.5rem)] max-w-3xl rounded-2xl bg-white shadow-[0_24px_60px_-20px_rgba(15,23,42,0.35)] border border-slate-200 px-4 py-3 flex items-center gap-3 animate-in fade-in slide-in-from-bottom-2 duration-300 dark:bg-zinc-900 dark:border-zinc-800"
      data-testid="gx-sticky-cta"
    >
      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[var(--gx-brand-from)] to-[var(--gx-brand-to)] flex items-center justify-center text-white shrink-0">
        <Sparkles size={14} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[13px] font-bold text-slate-900 truncate dark:text-zinc-100">Try GymAxis free for 3 days</p>
        <p className="text-[11px] text-slate-500 truncate">All 6 modules unlocked. No credit card. Cancel any time.</p>
      </div>
      <button type="button" onClick={openTrial}
        className="gx-cta inline-flex items-center gap-1 rounded-full px-4 py-2 text-[13px] font-bold whitespace-nowrap"
        data-testid="gx-sticky-cta-trial">
        Start free <ArrowRight size={13} />
      </button>
      <button type="button" aria-label="Dismiss"
        onClick={() => { localStorage.setItem(DISMISS_KEY, String(Date.now())); setVisible(false); }}
        className="p-1.5 text-slate-400 hover:text-slate-700 shrink-0"
        data-testid="gx-sticky-cta-dismiss">
        <X size={14} />
      </button>
    </div>
  );
}
