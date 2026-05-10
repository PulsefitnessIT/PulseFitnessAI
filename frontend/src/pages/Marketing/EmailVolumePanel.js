/**
 * EmailVolumePanel — customer-facing Email Volume + Bolt-on dialog.
 *
 * Shows the operator their current monthly email cap (base + active
 * bolt-on packs), this period's usage, and the catalog of packs they can
 * add. The end-to-end self-serve attach flow ships in a follow-up; for
 * now packs are attached by master admin so this dialog explains how to
 * request one.
 */
import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { Mail, X as Close, Plus, Sparkles } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { notify } from '@/components/notifications';

const fmtMoney = (pence, ccy = 'GBP') => {
  const sym = ccy === 'GBP' ? '£' : ccy === 'EUR' ? '€' : '$';
  return `${sym}${(Number(pence || 0) / 100).toFixed(2)}`;
};

const EmailVolumePanel = ({ API, headers, onClose }) => {
  const [catalog, setCatalog] = useState({ rows: [], base: { included_emails: 5000 } });
  const [mine, setMine] = useState({ rows: [], limits: null, usage: { emails_sent: 0 } });
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [c, m] = await Promise.all([
        axios.get(`${API}/marketing/addons/catalog`, { headers: headers() }),
        axios.get(`${API}/marketing/addons/mine`, { headers: headers() }),
      ]);
      setCatalog(c.data || { rows: [] });
      setMine(m.data || { rows: [] });
    } catch (e) {
      notify.error('Could not load email packs', e.response?.data?.detail);
    }
    setLoading(false);
  }, [API, headers]);

  useEffect(() => { load(); }, [load]);

  const cap = mine.limits?.monthly_emails ?? catalog.base?.included_emails ?? 5000;
  const sent = mine.usage?.emails_sent ?? 0;
  const pct = cap > 0 ? Math.min(100, Math.round((sent / cap) * 100)) : 0;
  const attachedCodes = new Set((mine.rows || []).map((r) => r.code));

  const requestPack = (pack) => {
    const subject = `GymAxis · request to enable ${pack.name}`;
    const body = `Hi GymAxis team,\n\nPlease enable the "${pack.name}" pack on our Marketing module (+${pack.included_emails.toLocaleString()} emails / month at ${fmtMoney(pack.monthly_price_pence)}/mo).\n\nThanks!`;
    window.location.href = `mailto:hello@gymaxis.ai?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  };

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-2xl" data-testid="email-volume-panel">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Mail size={18} className="text-blue-600" />
            Email volume & bolt-on packs
          </DialogTitle>
        </DialogHeader>

        <div className="mb-5 mt-2 p-4 rounded-lg bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-100" data-testid="email-cap-summary">
          <div className="flex items-baseline gap-2 mb-2">
            <span className="text-2xl font-bold tabular-nums text-zinc-900">{sent.toLocaleString()}</span>
            <span className="text-sm text-zinc-500">/ {cap.toLocaleString()} emails this period</span>
          </div>
          <div className="h-2 rounded-full bg-zinc-200 overflow-hidden">
            <div
              className={`h-full transition-all ${pct >= 90 ? 'bg-rose-500' : pct >= 70 ? 'bg-amber-500' : 'bg-blue-600'}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="mt-2 flex items-center justify-between text-[11px] text-zinc-500">
            <span>Base plan: {(catalog.base?.included_emails ?? 5000).toLocaleString()} included</span>
            <span>+ {((mine.limits?.addon_emails) ?? 0).toLocaleString()} from {(mine.rows || []).length} pack{(mine.rows || []).length === 1 ? '' : 's'}</span>
          </div>
        </div>

        {(mine.rows || []).length > 0 && (
          <div className="mb-5">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-zinc-500 mb-2">Active bolt-on packs</h4>
            <div className="space-y-1.5">
              {mine.rows.map((p) => (
                <div key={p.id} className="flex items-center justify-between p-2.5 rounded border border-zinc-200 bg-white text-sm" data-testid={`active-pack-${p.code}`}>
                  <div>
                    <p className="font-semibold text-zinc-900">{p.name}</p>
                    <p className="text-[11px] text-zinc-500">+{(p.included_emails || 0).toLocaleString()} emails / mo · {fmtMoney(p.monthly_price_pence)}/mo</p>
                  </div>
                  <span className="px-2 py-0.5 rounded-full text-[10px] bg-emerald-100 text-emerald-700 font-semibold">Active</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <h4 className="text-xs font-semibold uppercase tracking-wide text-zinc-500 mb-2 flex items-center gap-2">
          <Sparkles size={12} /> Available packs
        </h4>
        {loading ? (
          <p className="text-sm text-zinc-400">Loading…</p>
        ) : (catalog.rows || []).length === 0 ? (
          <p className="text-sm text-zinc-400">No packs available right now.</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {catalog.rows.map((pack) => {
              const active = attachedCodes.has(pack.code);
              return (
                <Card key={pack.code} className={`p-3 border ${active ? 'border-emerald-200 bg-emerald-50/50' : 'border-zinc-200'}`} data-testid={`pack-card-${pack.code}`}>
                  <div className="flex items-start justify-between mb-1.5">
                    <p className="font-semibold text-sm text-zinc-900">{pack.name}</p>
                    <span className="text-sm font-bold text-zinc-900">{fmtMoney(pack.monthly_price_pence)}<span className="text-[10px] text-zinc-400">/mo</span></span>
                  </div>
                  <p className="text-[11px] text-zinc-500 mb-2">
                    {pack.kind === 'sms'
                      ? `+${(pack.included_sms || 0).toLocaleString()} SMS / month`
                      : `+${(pack.included_emails || 0).toLocaleString()} emails / month`}
                  </p>
                  {active ? (
                    <Button size="sm" disabled className="w-full h-7 text-[11px] bg-emerald-100 text-emerald-700">Already active</Button>
                  ) : (
                    <Button size="sm" variant="outline" className="w-full h-7 text-[11px] border-blue-200 text-blue-700 hover:bg-blue-50" onClick={() => requestPack(pack)} data-testid={`pack-request-${pack.code}`}>
                      <Plus size={11} className="mr-1" /> Request enable
                    </Button>
                  )}
                </Card>
              );
            })}
          </div>
        )}

        <p className="mt-4 text-[11px] text-zinc-400">
          Self-serve checkout for bolt-on packs ships in our next iteration. For now, tap "Request enable" — we'll add the pack to your account within one business day.
        </p>
      </DialogContent>
    </Dialog>
  );
};

export default EmailVolumePanel;
