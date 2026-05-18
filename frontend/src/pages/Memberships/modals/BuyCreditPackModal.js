/**
 * BuyCreditPackModal — iter 216h202.
 *
 * Member-facing modal that lists the studio's class-packs and kicks
 * the user into a Stripe Checkout for the pack they pick. Used by the
 * BookTab when a 402 fires (no credits) and via a persistent "Buy
 * credits" CTA in the timetable header.
 *
 * Wire: GET /api/member/credit-packs, POST /api/member/credit-pack-checkout
 *       → redirect to session.checkout_url.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { X, Loader2, CreditCard, Sparkles } from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { API } from '../portalShared';

export default function BuyCreditPackModal({ headers, open, onClose, prompt }) {
  const [packs, setPacks] = useState(null);
  const [loadingId, setLoadingId] = useState(null);

  useEffect(() => {
    if (!open) { setPacks(null); return; }
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/member/credit-packs`, { headers });
        if (!cancelled) setPacks(r.data?.packs || []);
      } catch {
        if (!cancelled) {
          notify.error('Failed to load class packs');
          setPacks([]);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [open, headers]);

  const buy = async (plan_id) => {
    setLoadingId(plan_id);
    try {
      const r = await axios.post(`${API}/member/credit-pack-checkout`, { plan_id }, { headers });
      // Hand off to Stripe-hosted checkout.
      if (r.data?.checkout_url) {
        window.location.href = r.data.checkout_url;
        return;
      }
      notify.error('Checkout URL missing — try again');
    } catch (err) {
      notifyApiError(notify, err, 'Could not start checkout');
    } finally {
      setLoadingId(null);
    }
  };

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[120] grid place-items-center bg-black/70 backdrop-blur-sm p-4" data-testid="buy-credits-modal">
      <div className="w-full max-w-md rounded-2xl border border-white/10 bg-zinc-900 text-white shadow-2xl">
        <header className="flex items-start justify-between gap-3 px-5 py-4 border-b border-white/10">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)]">Class pack</p>
            <h2 className="text-base font-extrabold mt-0.5">Top up your credits</h2>
            {prompt && (
              <p className="text-[12px] mt-1 text-white/70" data-testid="buy-credits-prompt">{prompt}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md hover:bg-white/10 text-white/60"
            data-testid="buy-credits-close"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </header>
        <div className="p-5 space-y-3 max-h-[60vh] overflow-y-auto">
          {packs === null && (
            <div className="flex items-center justify-center py-8" data-testid="buy-credits-loading">
              <Loader2 className="animate-spin text-[var(--color-brand-cyan)]" />
            </div>
          )}
          {packs && packs.length === 0 && (
            <div className="text-center py-6" data-testid="buy-credits-empty">
              <CreditCard className="mx-auto mb-2 text-white/30" />
              <p className="text-sm font-bold">No packs on sale</p>
              <p className="text-[12px] text-white/60 mt-1">Ask the studio to enable self-serve class packs.</p>
            </div>
          )}
          {packs && packs.map((p) => {
            const perCreditPence = p.value_per_credit_pence || 0;
            return (
              <button
                key={p.id}
                onClick={() => buy(p.id)}
                disabled={loadingId !== null}
                className="w-full text-left rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 p-4 transition disabled:opacity-50"
                data-testid={`buy-credits-pack-${p.id}`}
              >
                <div className="flex items-baseline justify-between gap-3">
                  <div className="font-extrabold text-sm">{p.name}</div>
                  <div className="font-extrabold text-base">£{(p.price_pence / 100).toFixed(2)}</div>
                </div>
                <div className="mt-1 flex items-center gap-2 text-[12px] text-white/70">
                  <Sparkles size={12} className="text-[var(--color-brand-cyan)]" />
                  <span>{p.credits_count} credits</span>
                  {perCreditPence > 0 && (
                    <span className="text-white/40">· £{(perCreditPence / 100).toFixed(2)} per class</span>
                  )}
                  {p.pack_expiry_days && (
                    <span className="text-white/40">· expires in {p.pack_expiry_days}d</span>
                  )}
                </div>
                {p.description && (
                  <p className="mt-2 text-[11px] text-white/55 leading-snug">{p.description}</p>
                )}
                {loadingId === p.id && (
                  <p className="mt-2 text-[11px] text-[var(--color-brand-cyan)] flex items-center gap-1">
                    <Loader2 size={10} className="animate-spin" /> Redirecting to Stripe…
                  </p>
                )}
              </button>
            );
          })}
        </div>
        <footer className="px-5 py-3 border-t border-white/10 text-[10px] text-white/40 text-center">
          Secure checkout · Stripe · Cancel any time
        </footer>
      </div>
    </div>
  );
}
