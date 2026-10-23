import { useEffect, useState } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Truck, CalendarDays, MapPin, ShieldCheck, Download, PackageCheck, Loader2, Clock } from 'lucide-react';
import { LanguageSwitcher } from '../../components/shared/LanguageSwitcher';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const authHeaders = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const fmtDate = (iso) => {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' }); } catch { return String(iso).slice(0, 10); }
};

export default function CustomerDeliveriesTab() {
  const { t } = useTranslation();
  const [data, setData] = useState(null);

  const STATUS = {
    awaiting_installation: { label: t('deliveries.status_scheduled', 'Scheduled'), cls: 'bg-sky-50 text-sky-700 ring-sky-200', icon: CalendarDays },
    installation_in_progress: { label: t('deliveries.status_in_progress', 'In progress'), cls: 'bg-amber-50 text-amber-700 ring-amber-200', icon: Clock },
    active: { label: t('deliveries.status_installed', 'Installed'), cls: 'bg-emerald-50 text-emerald-700 ring-emerald-200', icon: PackageCheck },
  };

  useEffect(() => {
    axios.get(`${API}/customer/deliveries`, authHeaders())
      .then((r) => setData(r.data))
      .catch(() => setData({ deliveries: [] }));
  }, []);

  const openCert = async (url) => {
    try {
      const r = await axios.get(`${process.env.REACT_APP_BACKEND_URL}${url}`, { responseType: 'blob', ...authHeaders() });
      window.open(URL.createObjectURL(r.data), '_blank');
    } catch { /* noop */ }
  };

  if (!data) return <div className="flex items-center justify-center py-20 text-slate-400"><Loader2 className="animate-spin" /></div>;
  const items = data.deliveries || [];

  return (
    <div className="space-y-5" data-testid="customer-deliveries-tab">
      <div className="flex items-center justify-end gap-3">
        <LanguageSwitcher />
      </div>

      {items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white py-16 text-center" data-testid="customer-deliveries-empty">
          <PackageCheck size={32} className="mx-auto mb-2 text-slate-300" />
          <p className="text-sm font-medium text-slate-500">{t('deliveries.empty', 'No deliveries or installations to show right now.')}</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2" data-testid="customer-deliveries-list">
          {items.map((d) => {
            const s = STATUS[d.status] || { label: d.status, cls: 'bg-slate-50 text-slate-600 ring-slate-200', icon: Truck };
            const Icon = s.icon;
            return (
              <div key={d.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm" data-testid={`customer-delivery-${d.reference}`}>
                <div className="flex items-start justify-between">
                  <div className="min-w-0">
                    <p className="truncate text-base font-bold text-slate-900">{d.model}</p>
                    <p className="mt-0.5 text-xs text-slate-500">{d.serial_number || d.reference}</p>
                  </div>
                  <span className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${s.cls}`}><Icon size={12} /> {s.label}</span>
                </div>
                <div className="mt-3 space-y-1.5 text-sm text-slate-600">
                  {d.site && <p className="flex items-center gap-2"><MapPin size={13} className="text-slate-400" /> {d.site}</p>}
                  <p className="flex items-center gap-2"><CalendarDays size={13} className="text-slate-400" /> {d.status === 'active' ? t('deliveries.installed_on', 'Installed {{date}}', { date: fmtDate(d.installed_at) }) : `${t('deliveries.planned_on', 'Planned {{date}}', { date: fmtDate(d.planned_install_date) })}${d.install_window ? ` · ${d.install_window}` : ''}`}</p>
                  {d.warranty?.warranty_end && <p className="flex items-center gap-2"><ShieldCheck size={13} className="text-emerald-500" /> {t('deliveries.warranty_to', 'Warranty to {{date}}', { date: fmtDate(d.warranty.warranty_end) })}</p>}
                </div>
                {d.certificate_url && (
                  <button onClick={() => openCert(d.certificate_url)} className="mt-3 flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-bold text-white hover:bg-slate-800" data-testid={`customer-delivery-cert-${d.reference}`}>
                    <Download size={13} /> {t('deliveries.certificate', 'Installation certificate')}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
