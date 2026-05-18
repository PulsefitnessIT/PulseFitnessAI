/**
 * SellPackAtDeskModal — iter 216h203.
 *
 * Operator-side one-click cash/cash-equivalent class-pack sale. Unlike
 * the existing "Record payment" flow (which kills any open recurring
 * membership), this flow:
 *   • only lets you pick `kind=class_pack` plans
 *   • coexists with the member's existing subscription
 *   • tops up an existing same-plan pack instead of duplicating it
 *
 * Backend: POST /api/memberships/members/{id}/sell-pack-at-desk
 *   body { plan_id, method, reference?, note? }
 */
import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { X, Loader2, Sparkles, CheckCircle2 } from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const METHODS = [
  { id: 'cash',           label: 'Cash' },
  { id: 'card_terminal',  label: 'Card terminal (chip & pin)' },
  { id: 'bank_transfer',  label: 'Bank transfer' },
  { id: 'comp',           label: 'Comp (£0 — staff / influencer)' },
  { id: 'other',          label: 'Other' },
];

export default function SellPackAtDeskModal({ API, headers, memberId, plans, onClose }) {
  const packs = useMemo(
    () => (plans || []).filter((p) => p.kind === 'class_pack' && !p.archived),
    [plans],
  );
  const [planId, setPlanId] = useState(packs[0]?.id || '');
  const [method, setMethod] = useState('cash');
  const [reference, setReference] = useState('');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!planId && packs[0]?.id) setPlanId(packs[0].id);
  }, [packs, planId]);

  const selected = packs.find((p) => p.id === planId);

  const submit = async () => {
    if (!planId) { notify.error('Pick a pack first'); return; }
    setSaving(true);
    try {
      const r = await axios.post(
        `${API}/memberships/members/${memberId}/sell-pack-at-desk`,
        { plan_id: planId, method, reference: reference || null, note: note || null },
        { headers },
      );
      const credits = r.data?.credits_added || (selected?.credits_count ?? 0);
      const action = r.data?.topped_up ? 'Topped up' : 'Sold';
      notify.success(`${action} · +${credits} credit${credits === 1 ? '' : 's'} (${method})`);
      onClose(true);
    } catch (e) {
      notifyApiError(notify, e, 'Failed to sell pack');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[110] bg-black/60 grid place-items-center p-3"
      onClick={() => !saving && onClose(false)}
      data-testid="mbr-sell-pack-modal"
    >
      <div
        className="w-full max-w-md rounded-2xl shadow-2xl bg-[color:var(--theme-surface)] border border-[color:var(--theme-border)] text-[color:var(--theme-text)]"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-3 px-5 py-4 border-b border-[color:var(--theme-border)]">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)]">Desk sale</p>
            <h2 className="text-base font-extrabold mt-0.5">Sell a class pack</h2>
            <p className="text-[11px] mt-1 text-[color:var(--theme-text-muted)]">
              One click. Credits added on the spot. Existing memberships stay intact.
            </p>
          </div>
          <button
            onClick={() => !saving && onClose(false)}
            className="p-1.5 rounded-md hover:bg-white/5 text-[color:var(--theme-text-muted)]"
            aria-label="Close"
            data-testid="mbr-sell-pack-close"
            disabled={saving}
          >
            <X size={16} />
          </button>
        </header>

        <div className="p-5 space-y-4">
          {packs.length === 0 && (
            <div className="rounded-lg border border-amber-400/30 bg-amber-500/5 p-3 text-[12px]" data-testid="mbr-sell-pack-empty">
              No class packs configured. Create one in Plans first (kind = Class pack).
            </div>
          )}

          {packs.length > 0 && (
            <>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-2">Pack</p>
                <div className="space-y-1.5">
                  {packs.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => setPlanId(p.id)}
                      className={`w-full text-left rounded-lg border p-3 transition flex items-center gap-3 ${planId === p.id
                        ? 'border-[var(--color-brand-cyan)] bg-[var(--color-brand-cyan)]/5'
                        : 'border-[color:var(--theme-border)] hover:bg-white/5'}`}
                      data-testid={`mbr-sell-pack-option-${p.id}`}
                    >
                      <div className="w-1 h-9 rounded" style={{ background: p.colour || 'var(--color-brand-cyan)' }} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-extrabold truncate">{p.name}</p>
                        <p className="text-[11px] text-[color:var(--theme-text-muted)] mt-0.5 flex items-center gap-1.5">
                          <Sparkles size={10} className="text-[var(--color-brand-cyan)]" />
                          {p.credits_count} credits
                          {p.pack_expiry_days && <span>· expires {p.pack_expiry_days}d</span>}
                        </p>
                      </div>
                      <div className="font-extrabold text-sm tabular-nums">
                        £{((p.price_pence || 0) / 100).toFixed(2)}
                      </div>
                      {planId === p.id && <CheckCircle2 size={14} className="text-[var(--color-brand-cyan)]" />}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-2">Payment method</p>
                <div className="grid grid-cols-2 gap-1.5">
                  {METHODS.map((m) => (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => setMethod(m.id)}
                      className={`text-left rounded-lg border p-2.5 transition text-[12px] font-bold ${method === m.id
                        ? 'border-[var(--color-brand-cyan)] bg-[var(--color-brand-cyan)]/5'
                        : 'border-[color:var(--theme-border)] hover:bg-white/5'}`}
                      data-testid={`mbr-sell-pack-method-${m.id}`}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
              </div>

              <label className="block">
                <span className="block text-[10px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-1">Reference (optional)</span>
                <input
                  type="text"
                  value={reference}
                  onChange={(e) => setReference(e.target.value)}
                  placeholder="e.g. cash receipt #014"
                  className="w-full h-9 px-3 rounded-lg bg-transparent border border-[color:var(--theme-border)] text-sm focus:outline-none focus:border-[var(--color-brand-cyan)]"
                  data-testid="mbr-sell-pack-reference"
                />
              </label>

              <label className="block">
                <span className="block text-[10px] font-bold uppercase tracking-[0.16em] text-[color:var(--theme-text-muted)] mb-1">Note (optional)</span>
                <input
                  type="text"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="e.g. Birthday gift from the team"
                  className="w-full h-9 px-3 rounded-lg bg-transparent border border-[color:var(--theme-border)] text-sm focus:outline-none focus:border-[var(--color-brand-cyan)]"
                  data-testid="mbr-sell-pack-note"
                />
              </label>
            </>
          )}
        </div>

        <footer className="px-5 py-3 border-t border-[color:var(--theme-border)] flex items-center justify-end gap-2">
          <button
            onClick={() => onClose(false)}
            disabled={saving}
            className="h-9 px-4 rounded-lg text-[11px] font-bold uppercase tracking-wider border border-[color:var(--theme-border)] hover:bg-white/5 disabled:opacity-50"
            data-testid="mbr-sell-pack-cancel"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={saving || packs.length === 0 || !planId}
            className="gx-btn-primary h-9 px-4 rounded-lg text-[11px] font-extrabold uppercase tracking-wider flex items-center gap-1.5 disabled:opacity-50"
            data-testid="mbr-sell-pack-confirm"
          >
            {saving && <Loader2 size={11} className="animate-spin" />}
            {method === 'comp' ? 'Comp pack' : `Take £${((selected?.price_pence || 0) / 100).toFixed(2)}`}
          </button>
        </footer>
      </div>
    </div>
  );
}
