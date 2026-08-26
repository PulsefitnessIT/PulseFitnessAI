import { useEffect, useState } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { ShieldCheck, ShieldAlert, ShieldX, Loader2, Package, BellRing, Send, X, CheckCircle2 } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const authHeaders = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const fmtDate = (iso) => {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' }); } catch { return String(iso).slice(0, 10); }
};

const STATUS = {
  active: { label: 'In cover', cls: 'bg-emerald-50 text-emerald-700 ring-emerald-200', icon: ShieldCheck },
  expiring: { label: 'Expiring soon', cls: 'bg-amber-50 text-amber-700 ring-amber-200', icon: ShieldAlert },
  expired: { label: 'Expired', cls: 'bg-red-50 text-red-700 ring-red-200', icon: ShieldX },
  unknown: { label: 'Warranty', cls: 'bg-slate-50 text-slate-600 ring-slate-200', icon: ShieldCheck },
};

export default function CustomerWarrantiesTab() {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [enquire, setEnquire] = useState(null); // { ids: [], label } | null
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  const load = () => axios.get(`${API}/customer/warranties`, authHeaders()).then((r) => setData(r.data)).catch(() => setData({ warranties: [], counts: {} }));
  useEffect(() => { load(); }, []);

  const submitEnquiry = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/customer/warranties/enquire`, { equipment_ids: enquire.ids, message: note.trim() }, authHeaders());
      setEnquire(null); setNote('');
      await load();
    } catch (e) { /* surfaced via reload; keep simple */ }
    setBusy(false);
  };

  if (!data) return <div className="flex items-center justify-center py-20 text-slate-400"><Loader2 className="animate-spin" /></div>;
  const items = data.warranties || [];
  const counts = data.counts || {};
  const enquiryOpen = !!data.renewal_enquiry_open;
  const atRisk = items.filter((w) => w.status === 'expiring' || w.status === 'expired');

  return (
    <div className="space-y-5" data-testid="customer-warranties-tab">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl" style={{ background: 'linear-gradient(135deg, #19CDFF, #0BB0DD)' }}><ShieldCheck size={20} className="text-white" /></div>
        <div>
          <h2 className="text-xl font-bold text-slate-900">{t('warranties.title', 'Warranty Register')}</h2>
          <p className="text-sm text-slate-500">{t('warranties.subtitle', 'Your equipment, its warranty level and how long it stays in cover.')}</p>
        </div>
      </div>

      {/* Renewal nudge — aftersales cover */}
      {atRisk.length > 0 && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4" data-testid="warranty-renewal-nudge">
          <div className="flex items-start gap-3">
            <BellRing size={20} className="mt-0.5 shrink-0 text-amber-600" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-bold text-amber-900">
                {atRisk.length} {atRisk.length === 1 ? t('warranties.unit', 'unit is') : t('warranties.units', 'units are')} {t('warranties.nearing', 'nearing the end of warranty cover')}
              </p>
              <p className="mt-0.5 text-xs text-amber-800">{t('warranties.nudge_body', 'Keep them protected with a Pulse Fitness aftersales contract — parts, labour and priority support once your warranty ends.')}</p>
              {enquiryOpen ? (
                <p className="mt-2 inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-700" data-testid="warranty-enquiry-open"><CheckCircle2 size={13} /> {t('warranties.enquiry_sent', 'Enquiry sent — the Pulse Fitness team will be in touch.')}</p>
              ) : (
                <button onClick={() => setEnquire({ ids: atRisk.map((w) => w.id), label: t('warranties.all_at_risk', 'all equipment nearing end of cover') })}
                  className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700"
                  data-testid="warranty-enquire-all">
                  <Send size={12} /> {t('warranties.enquire_cover', 'Enquire about aftersales cover')}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {items.length > 0 && (
        <div className="grid grid-cols-3 gap-3" data-testid="warranties-counts">
          <div className="rounded-xl border border-slate-200 bg-white p-3 text-center"><p className="text-2xl font-bold text-emerald-600" data-testid="warranties-count-active">{counts.active || 0}</p><p className="text-xs text-slate-500">{t('warranties.in_cover', 'In cover')}</p></div>
          <div className="rounded-xl border border-slate-200 bg-white p-3 text-center"><p className="text-2xl font-bold text-amber-600" data-testid="warranties-count-expiring">{counts.expiring || 0}</p><p className="text-xs text-slate-500">{t('warranties.expiring', 'Expiring soon')}</p></div>
          <div className="rounded-xl border border-slate-200 bg-white p-3 text-center"><p className="text-2xl font-bold text-red-600" data-testid="warranties-count-expired">{counts.expired || 0}</p><p className="text-xs text-slate-500">{t('warranties.expired', 'Expired')}</p></div>
        </div>
      )}

      {items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white py-16 text-center" data-testid="customer-warranties-empty">
          <Package size={32} className="mx-auto mb-2 text-slate-300" />
          <p className="text-sm font-medium text-slate-500">{t('warranties.empty', 'No warranties on record yet. They appear here once your equipment is handed over.')}</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2" data-testid="customer-warranties-list">
          {items.map((w) => {
            const s = STATUS[w.status] || STATUS.unknown;
            const Icon = s.icon;
            const mm = [w.manufacturer, w.model].filter(Boolean).join(' · ');
            const risky = w.status === 'expiring' || w.status === 'expired';
            return (
              <div key={w.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm" data-testid={`customer-warranty-${w.id}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-base font-bold text-slate-900">{w.name}</p>
                    <p className="mt-0.5 text-xs text-slate-500">{w.serial_number ? `S/N ${w.serial_number}` : (mm || '—')}</p>
                  </div>
                  <span className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 shrink-0 ${s.cls}`}><Icon size={12} /> {s.label}</span>
                </div>
                <div className="mt-3 space-y-1.5 text-sm text-slate-600">
                  <p className="flex items-center gap-2"><ShieldCheck size={13} className="text-slate-400" /> {w.warranty_label}</p>
                  <p className="flex items-center gap-2">
                    <span className="text-slate-400">{t('warranties.cover_until', 'Cover until')}</span>
                    <span className="font-semibold text-slate-800">{fmtDate(w.warranty_expiry)}</span>
                    {typeof w.days_remaining === 'number' && w.days_remaining >= 0 && (
                      <span className="text-xs text-slate-400">· {w.days_remaining} {t('warranties.days_left', 'days left')}</span>
                    )}
                  </p>
                  {w.warranty_summary && <p className="text-xs text-slate-400">{w.warranty_summary}</p>}
                </div>
                {risky && !enquiryOpen && (
                  <button onClick={() => setEnquire({ ids: [w.id], label: w.name })}
                    className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-amber-300 px-3 py-1.5 text-xs font-semibold text-amber-700 hover:bg-amber-50"
                    data-testid={`warranty-enquire-${w.id}`}>
                    <Send size={12} /> {t('warranties.enquire_cover_short', 'Enquire about cover')}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Enquiry dialog */}
      {enquire && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => !busy && setEnquire(null)}>
          <div className="w-full max-w-md rounded-2xl bg-white p-5" onClick={(e) => e.stopPropagation()} data-testid="warranty-enquiry-dialog">
            <div className="mb-2 flex items-center justify-between">
              <h4 className="inline-flex items-center gap-1.5 font-bold text-slate-900"><BellRing size={16} className="text-amber-600" /> {t('warranties.enquire_title', 'Enquire about aftersales cover')}</h4>
              <button onClick={() => !busy && setEnquire(null)} data-testid="warranty-enquiry-close"><X size={16} className="text-slate-400" /></button>
            </div>
            <p className="mb-3 text-xs text-slate-500">{t('warranties.enquire_for', 'For')}: <span className="font-medium text-slate-700">{enquire.label}</span>. {t('warranties.enquire_help', 'The Pulse Fitness team will prepare an aftersales contract and get in touch. Add anything helpful below (optional).')}</p>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3}
              placeholder={t('warranties.enquire_placeholder', 'e.g. best time to call, preferred cover level, site notes…')}
              className="w-full resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800 focus:border-sky-400 focus:outline-none" data-testid="warranty-enquiry-note" />
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setEnquire(null)} disabled={busy} className="px-3 py-2 text-sm text-slate-500">{t('common.cancel', 'Cancel')}</button>
              <button onClick={submitEnquiry} disabled={busy} className="inline-flex items-center gap-1.5 rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-600 disabled:opacity-50" data-testid="warranty-enquiry-send">
                {busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />} {t('warranties.send_enquiry', 'Send enquiry')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
