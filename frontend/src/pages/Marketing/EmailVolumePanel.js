/**
 * EmailVolumePanel — customer-facing Email Volume + Bolt-on dialog.
 *
 * Shows the operator their current monthly email cap (base + active
 * bolt-on packs), this period's usage, and the catalog of packs they can
 * add. The end-to-end self-serve attach flow ships in a follow-up; for
 * now packs are attached by master admin so this dialog explains how to
 * request one.
 */
import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Mail, Plus, Sparkles } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { notify } from '@/components/notifications';

const fmtMoney = (pence, ccy = 'GBP') => {
  const sym = ccy === 'GBP' ? '£' : ccy === 'EUR' ? '€' : '$';
  return `${sym}${(Number(pence || 0) / 100).toFixed(2)}`;
};

const EmailVolumePanel = ({ API, headers, onClose }) => {
  const { t } = useTranslation();
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
      notify.error(t('mkt.evp_load_err', 'Could not load email packs'), e.response?.data?.detail);
    }
    setLoading(false);
  }, [API, headers]);

  useEffect(() => { load(); }, [load]);

  const cap = mine.limits?.monthly_emails ?? catalog.base?.included_emails ?? 5000;
  const sent = mine.usage?.emails_sent ?? 0;
  const pct = cap > 0 ? Math.min(100, Math.round((sent / cap) * 100)) : 0;
  const attachedCodes = new Set((mine.rows || []).map((r) => r.code));

  const requestPack = (pack) => {
    const subject = `Pulse Fitness · request to enable ${pack.name}`;
    const body = `Hi Pulse Fitness team,\n\nPlease enable the "${pack.name}" pack on our Marketing module (+${pack.included_emails.toLocaleString()} emails / month at ${fmtMoney(pack.monthly_price_pence)}/mo).\n\nThanks!`;
    window.location.href = `mailto:hello@gymaxis.ai?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  };

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-2xl" data-testid="email-volume-panel">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Mail size={18} className="text-blue-600" />
            {t('mkt.evp_title', 'Email volume & bolt-on packs')}
          </DialogTitle>
        </DialogHeader>

        <div className="mb-5 mt-2 p-4 rounded-lg bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-950/40 dark:to-indigo-950/40 border border-blue-100 dark:border-blue-900/60" data-testid="email-cap-summary">
          <div className="flex items-baseline gap-2 mb-2">
            <span className="text-2xl font-bold tabular-nums text-zinc-900 dark:text-zinc-100">{sent.toLocaleString()}</span>
            <span className="text-sm text-zinc-500">{t('mkt.evp_of_cap', '/ {{cap}} emails this period', { cap: cap.toLocaleString() })}</span>
          </div>
          <div className="h-2 rounded-full bg-zinc-200 overflow-hidden">
            <div
              className={`h-full transition-all ${pct >= 90 ? 'bg-rose-500' : pct >= 70 ? 'bg-amber-500' : 'bg-blue-600'}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="mt-2 flex items-center justify-between text-[11px] text-zinc-500">
            <span>{t('mkt.evp_base_included', 'Base plan: {{n}} included', { n: (catalog.base?.included_emails ?? 5000).toLocaleString() })}</span>
            <span>{t('mkt.evp_from_packs', '+ {{emails}} from {{packs}} packs', { emails: ((mine.limits?.addon_emails) ?? 0).toLocaleString(), packs: (mine.rows || []).length })}</span>
          </div>
        </div>

        {(mine.rows || []).length > 0 && (
          <div className="mb-5">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-zinc-500 mb-2">{t('mkt.evp_active_packs', 'Active bolt-on packs')}</h4>
            <div className="space-y-1.5">
              {mine.rows.map((p) => (
                <div key={p.id} className="flex items-center justify-between p-2.5 rounded border border-zinc-200 bg-white text-sm dark:bg-zinc-900 dark:border-zinc-800" data-testid={`active-pack-${p.code}`}>
                  <div>
                    <p className="font-semibold text-zinc-900 dark:text-zinc-100">{p.name}</p>
                    <p className="text-[11px] text-zinc-500">{t('mkt.evp_pack_line', '+{{emails}} emails / mo · {{price}}/mo', { emails: (p.included_emails || 0).toLocaleString(), price: fmtMoney(p.monthly_price_pence) })}</p>
                  </div>
                  <span className="px-2 py-0.5 rounded-full text-[10px] bg-emerald-100 text-emerald-700 font-semibold">{t('mkt.evp_active', 'Active')}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <h4 className="text-xs font-semibold uppercase tracking-wide text-zinc-500 mb-2 flex items-center gap-2">
          <Sparkles size={12} /> {t('mkt.evp_available_packs', 'Available packs')}
        </h4>
        {loading ? (
          <p className="text-sm text-zinc-400">{t('mkt.evp_loading', 'Loading…')}</p>
        ) : (catalog.rows || []).length === 0 ? (
          <p className="text-sm text-zinc-400">{t('mkt.evp_no_packs', 'No packs available right now.')}</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {catalog.rows.map((pack) => {
              const active = attachedCodes.has(pack.code);
              return (
                <Card key={pack.code} className={`p-3 border ${active ? 'border-emerald-200 bg-emerald-50/50' : 'border-zinc-200'}`} data-testid={`pack-card-${pack.code}`}>
                  <div className="flex items-start justify-between mb-1.5">
                    <p className="font-semibold text-sm text-zinc-900 dark:text-zinc-100">{pack.name}</p>
                    <span className="text-sm font-bold text-zinc-900 dark:text-zinc-100">{fmtMoney(pack.monthly_price_pence)}<span className="text-[10px] text-zinc-400">/mo</span></span>
                  </div>
                  <p className="text-[11px] text-zinc-500 mb-2">
                    {pack.kind === 'sms'
                      ? t('mkt.evp_sms_line', '+{{n}} SMS / month', { n: (pack.included_sms || 0).toLocaleString() })
                      : t('mkt.evp_emails_line', '+{{n}} emails / month', { n: (pack.included_emails || 0).toLocaleString() })}
                  </p>
                  {active ? (
                    <Button size="sm" disabled className="w-full h-7 text-[11px] bg-emerald-100 text-emerald-700">{t('mkt.evp_already_active', 'Already active')}</Button>
                  ) : (
                    <Button size="sm" variant="outline" className="w-full h-7 text-[11px] border-blue-200 text-blue-700 hover:bg-blue-50" onClick={() => requestPack(pack)} data-testid={`pack-request-${pack.code}`}>
                      <Plus size={11} className="mr-1" /> {t('mkt.evp_request_enable', 'Request enable')}
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
