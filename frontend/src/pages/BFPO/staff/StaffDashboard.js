import React, { useEffect, useState } from 'react';
import { bfpo } from '../bfpoApi';
import { Spinner, Badge, PriorityBadge, HEALTH } from '../ui';
import { ClipboardList, AlertTriangle, Package, Clock, MapPin, ChevronRight } from 'lucide-react';

const TILES = [
  { key: 'open', label: 'Open Jobs', icon: ClipboardList, badge: 'text-cyan-600 bg-cyan-50 border border-cyan-100/80', filter: { status: 'open' } },
  { key: 'urgent', label: 'Urgent / Safety', icon: AlertTriangle, badge: 'text-red-600 bg-red-50 border border-red-100/80', filter: { safety: 'true' } },
  { key: 'waiting_parts', label: 'Waiting for Parts', icon: Package, badge: 'text-amber-600 bg-amber-50 border border-amber-100/80', filter: { status: 'paused_parts' } },
  { key: 'overdue', label: 'Overdue', icon: Clock, badge: 'text-rose-600 bg-rose-50 border border-rose-100/80', filter: { overdue: 'true' } },
];

export default function StaffDashboard({ userName, role, onOpenJobs, onOpenJob }) {
  const [data, setData] = useState(null);
  useEffect(() => { bfpo.get('/staff/dashboard').then((r) => setData(r.data)); }, []);
  if (!data) return <Spinner />;
  const k = data.kpis;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6" data-testid="staff-dashboard">
      {/* KPI stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4">
        {TILES.map((t) => (
          <button key={t.key} onClick={() => onOpenJobs(t.filter)} data-testid={`staff-tile-${t.key}`} className="text-left group">
            <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all duration-200 h-full">
              <div className={`w-11 h-11 rounded-xl flex items-center justify-center transition-transform group-hover:scale-105 ${t.badge}`}><t.icon className="w-5 h-5" /></div>
              <p className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight mt-3 mb-0.5" data-testid={`staff-kpi-${t.key}`}>{k[t.key] ?? 0}</p>
              <p className="text-xs sm:text-sm font-medium text-slate-500">{t.label}</p>
            </div>
          </button>
        ))}
        <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-sm h-full">
          <div className="w-11 h-11 rounded-xl flex items-center justify-center text-indigo-600 bg-indigo-50 border border-indigo-100/80"><MapPin className="w-5 h-5" /></div>
          <p className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight mt-3 mb-0.5" data-testid="staff-kpi-sites">{k.sites_attention ?? 0}</p>
          <p className="text-xs sm:text-sm font-medium text-slate-500">Sites Need Attention</p>
        </div>
      </div>

      {/* Attention panels */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-8">
        <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-sm">
          <h2 className="text-base font-semibold text-slate-900 flex items-center gap-2 mb-3"><AlertTriangle className="w-4 h-4 text-red-500" /> Needs attention now</h2>
          <div className="space-y-3">
            {data.urgent_jobs.length === 0 ? <p className="text-sm text-slate-400">Nothing urgent.</p> :
              data.urgent_jobs.map((j) => (
                <button key={j.id} onClick={() => onOpenJob(j.id)} className="w-full text-left group" data-testid={`staff-urgent-${j.id}`}>
                  <div className="bg-slate-50/60 hover:bg-slate-100/80 border border-slate-200/60 hover:border-slate-300 rounded-xl p-3.5 flex items-center gap-3 transition-all">
                    <PriorityBadge p={j.priority} />
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-slate-900 truncate">{j.title}</p>
                      <p className="text-xs text-slate-500 truncate">{j.site_name} · {j.assigned_engineer_name || 'Unallocated'}</p>
                    </div>
                    <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-slate-500 transition-colors" />
                  </div>
                </button>
              ))}
          </div>
        </div>
        <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-sm">
          <h2 className="text-base font-semibold text-slate-900 flex items-center gap-2 mb-3"><MapPin className="w-4 h-4 text-amber-500" /> Sites requiring attention</h2>
          <div className="space-y-3">
            {data.attention_sites.length === 0 ? <p className="text-sm text-slate-400">All sites normal.</p> :
              data.attention_sites.map((s) => (
                <div key={s.site_id} className="bg-slate-50/60 border border-slate-200/60 rounded-xl p-3.5 flex items-center gap-3" data-testid={`staff-attention-${s.site_id}`}>
                  <span className={`w-2.5 h-2.5 rounded-full ${HEALTH[s.health].dot}`} />
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-slate-900 truncate">{s.site_name}</p>
                    <p className="text-xs text-slate-500">{s.territory_name} · {s.open_jobs} open</p>
                  </div>
                  <Badge className={HEALTH[s.health].cls}>{HEALTH[s.health].label}</Badge>
                </div>
              ))}
          </div>
        </div>
      </div>
    </div>
  );
}
