import { useEffect, useState } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { ShieldCheck, ShieldAlert, ShieldX, Loader2, Package } from 'lucide-react';

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

  useEffect(() => {
    axios.get(`${API}/customer/warranties`, authHeaders())
      .then((r) => setData(r.data))
      .catch(() => setData({ warranties: [], counts: {} }));
  }, []);

  if (!data) return <div className="flex items-center justify-center py-20 text-slate-400"><Loader2 className="animate-spin" /></div>;
  const items = data.warranties || [];
  const counts = data.counts || {};

  return (
    <div className="space-y-5" data-testid="customer-warranties-tab">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl" style={{ background: 'linear-gradient(135deg, #19CDFF, #0BB0DD)' }}><ShieldCheck size={20} className="text-white" /></div>
        <div>
          <h2 className="text-xl font-bold text-slate-900">{t('warranties.title', 'Warranty Register')}</h2>
          <p className="text-sm text-slate-500">{t('warranties.subtitle', 'Your equipment, its warranty level and how long it stays in cover.')}</p>
        </div>
      </div>

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
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
