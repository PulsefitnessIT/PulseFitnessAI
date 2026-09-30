import React, { useEffect, useState } from 'react';
import { bfpo } from '../bfpoApi';
import { Card, Spinner, Badge, PriorityBadge, HEALTH, STATUS_LABEL } from '../ui';
import { ClipboardList, AlertTriangle, Package, Clock, MapPin, ChevronRight } from 'lucide-react';

const TILES = [
  { key: 'open', label: 'Open Jobs', icon: ClipboardList, color: 'text-cyan-600 bg-cyan-50', filter: { status: 'open' } },
  { key: 'urgent', label: 'Urgent / Safety', icon: AlertTriangle, color: 'text-red-600 bg-red-50', filter: { safety: 'true' } },
  { key: 'waiting_parts', label: 'Waiting for Parts', icon: Package, color: 'text-amber-600 bg-amber-50', filter: { status: 'paused_parts' } },
  { key: 'overdue', label: 'Overdue', icon: Clock, color: 'text-rose-600 bg-rose-50', filter: { overdue: 'true' } },
];

export default function StaffDashboard({ onOpenJobs, onOpenJob }) {
  const [data, setData] = useState(null);
  useEffect(() => { bfpo.get('/staff/dashboard').then((r) => setData(r.data)); }, []);
  if (!data) return <Spinner />;
  const k = data.kpis;

  return (
    <div className="p-6 max-w-6xl mx-auto" data-testid="staff-dashboard">
      <h1 className="text-2xl font-bold text-slate-900">Global BFPO Operations</h1>
      <p className="text-slate-500">Live view across all territories</p>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mt-5">
        {TILES.map((t) => (
          <button key={t.key} onClick={() => onOpenJobs(t.filter)} data-testid={`staff-tile-${t.key}`} className="text-left">
            <Card className="p-5 hover:shadow-md transition-shadow h-full">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${t.color}`}><t.icon className="w-5 h-5" /></div>
              <p className="text-3xl font-bold text-slate-900 mt-3" data-testid={`staff-kpi-${t.key}`}>{k[t.key] ?? 0}</p>
              <p className="text-sm text-slate-500 font-medium">{t.label}</p>
            </Card>
          </button>
        ))}
        <Card className="p-5">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center text-indigo-600 bg-indigo-50"><MapPin className="w-5 h-5" /></div>
          <p className="text-3xl font-bold text-slate-900 mt-3" data-testid="staff-kpi-sites">{k.sites_attention ?? 0}</p>
          <p className="text-sm text-slate-500 font-medium">Sites Need Attention</p>
        </Card>
      </div>

      <div className="grid lg:grid-cols-2 gap-6 mt-6">
        <div>
          <h2 className="font-semibold text-slate-900 mb-2 flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-red-500" /> Needs attention now</h2>
          <div className="space-y-2">
            {data.urgent_jobs.length === 0 ? <p className="text-sm text-slate-400">Nothing urgent.</p> :
              data.urgent_jobs.map((j) => (
                <button key={j.id} onClick={() => onOpenJob(j.id)} className="w-full text-left" data-testid={`staff-urgent-${j.id}`}>
                  <Card className="p-3 flex items-center gap-3 hover:shadow-md">
                    <PriorityBadge p={j.priority} />
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-slate-900 truncate">{j.title}</p>
                      <p className="text-xs text-slate-500 truncate">{j.site_name} · {j.assigned_engineer_name || 'Unallocated'}</p>
                    </div>
                    <ChevronRight className="w-4 h-4 text-slate-300" />
                  </Card>
                </button>
              ))}
          </div>
        </div>
        <div>
          <h2 className="font-semibold text-slate-900 mb-2 flex items-center gap-2"><MapPin className="w-4 h-4 text-amber-500" /> Sites requiring attention</h2>
          <div className="space-y-2">
            {data.attention_sites.length === 0 ? <p className="text-sm text-slate-400">All sites normal.</p> :
              data.attention_sites.map((s) => (
                <Card key={s.site_id} className="p-3 flex items-center gap-3" data-testid={`staff-attention-${s.site_id}`}>
                  <span className={`w-2.5 h-2.5 rounded-full ${HEALTH[s.health].dot}`} />
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-slate-900 truncate">{s.site_name}</p>
                    <p className="text-xs text-slate-500">{s.territory_name} · {s.open_jobs} open</p>
                  </div>
                  <Badge className={HEALTH[s.health].cls}>{HEALTH[s.health].label}</Badge>
                </Card>
              ))}
          </div>
        </div>
      </div>
    </div>
  );
}
