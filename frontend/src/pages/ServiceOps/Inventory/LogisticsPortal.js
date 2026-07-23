import { useEffect, useMemo, useState } from 'react';
import { Truck, LogOut, Search, CalendarDays, MapPin, ClipboardList, PackageCheck } from 'lucide-react';
import { useAuth } from '@/App';
import { invApi, fmtDate, statusLabel } from './api';
import { InstallPackModal } from './InvAllocation';
import { Spinner, StatusBadge, Btn } from './ui';

export default function LogisticsPortal() {
  const { user, logout } = useAuth();
  const [installs, setInstalls] = useState(null);
  const [q, setQ] = useState('');
  const [active, setActive] = useState(null);

  useEffect(() => {
    invApi.logisticsInstalls().then((d) => setInstalls(d.installs || [])).catch(() => setInstalls([]));
  }, []);

  const groups = useMemo(() => {
    const list = (installs || []).filter((i) => {
      if (!q.trim()) return true;
      const s = `${i.customer_company_name || ''} ${i.customer_site || ''} ${i.model || ''} ${i.serial_number || ''} ${i.reference || ''}`.toLowerCase();
      return s.includes(q.toLowerCase());
    });
    const map = {};
    list.forEach((i) => {
      const key = i.planned_install_date || 'unscheduled';
      (map[key] = map[key] || []).push(i);
    });
    return Object.entries(map).sort(([a], [b]) => (a === 'unscheduled' ? 1 : b === 'unscheduled' ? -1 : a.localeCompare(b)));
  }, [installs, q]);

  return (
    <div className="min-h-screen bg-slate-50" data-testid="logistics-portal">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg" style={{ background: 'linear-gradient(135deg, #19CDFF, #0BB0DD)' }}><Truck size={18} className="text-white" /></div>
            <div><h1 className="text-base font-bold text-slate-900">Logistics · Installations</h1><p className="text-[11px] text-slate-400">Install team portal</p></div>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden text-sm text-slate-500 sm:inline" data-testid="logistics-portal-user">{user?.email}</span>
            <button onClick={logout} className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50" data-testid="logistics-portal-logout"><LogOut size={14} /> Sign out</button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-6">
        <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-xl font-bold text-slate-900">Upcoming installations</h2>
            <p className="text-sm text-slate-500">Open an install to see the site survey, Health &amp; Safety, drawings and documents.</p>
          </div>
          <div className="relative">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search customer, site, machine…" className="w-full rounded-lg border border-slate-200 py-2 pl-9 pr-3 text-sm sm:w-72" data-testid="logistics-portal-search" />
          </div>
        </div>

        {installs === null ? <div className="py-16"><Spinner /></div> : installs.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-white py-16 text-center" data-testid="logistics-portal-empty">
            <PackageCheck size={32} className="mx-auto mb-2 text-slate-300" />
            <p className="text-sm font-medium text-slate-500">No installations scheduled right now.</p>
          </div>
        ) : (
          <div className="space-y-6" data-testid="logistics-portal-list">
            {groups.map(([date, items]) => (
              <div key={date}>
                <div className="mb-2 flex items-center gap-2 text-sm font-bold text-slate-700"><CalendarDays size={15} className="text-cyan-600" /> {date === 'unscheduled' ? 'Unscheduled' : fmtDate(date)} <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500">{items.length}</span></div>
                <div className="space-y-2">
                  {items.map((i) => (
                    <button key={i.id} onClick={() => setActive(i)} className="flex w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3 text-left transition-colors hover:border-cyan-300 hover:bg-cyan-50/40" data-testid={`logistics-install-${i.reference}`}>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-slate-900">{i.customer_company_name}{i.customer_site ? ` · ${i.customer_site}` : ''}</p>
                        <p className="mt-0.5 flex items-center gap-2 text-xs text-slate-500"><MapPin size={11} /> {i.model || i.product_code} <span className="text-slate-300">·</span> {i.serial_number || i.reference}</p>
                      </div>
                      <div className="flex items-center gap-3">
                        <StatusBadge status={i.status} />
                        <span className="flex items-center gap-1 text-xs font-semibold text-cyan-700"><ClipboardList size={13} /> Install pack</span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      {active && <InstallPackModal alloc={active} onClose={() => setActive(null)} readOnly packFetcher={invApi.logisticsPack} />}
    </div>
  );
}
