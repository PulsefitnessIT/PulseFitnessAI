import React, { useEffect, useState } from 'react';
import { bfpo } from '../bfpoApi';
import { Card, PriorityBadge, Spinner, Empty, Badge, HEALTH, ROLE_LABEL } from '../ui';
import { AlertTriangle, Package, RotateCcw, ClipboardList, ChevronRight, Clock, ClipboardCheck } from 'lucide-react';

const TILES = [
  { key: 'all_open', label: 'Open Jobs', icon: ClipboardList, color: 'text-cyan-600 bg-cyan-50', kpi: 'open' },
  { key: 'urgent', label: 'Urgent / Safety', icon: AlertTriangle, color: 'text-red-600 bg-red-50', kpi: 'urgent' },
  { key: 'waiting_parts', label: 'Waiting for Parts', icon: Package, color: 'text-amber-600 bg-amber-50', kpi: 'waiting_parts' },
  { key: 'return_visit', label: 'Return Visits', icon: RotateCcw, color: 'text-indigo-600 bg-indigo-50', kpi: 'return_visit' },
];

export default function EngineerHome({ onOpenJobs, onOpenJob, onOpenServices }) {
  const [me, setMe] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [servicesDue, setServicesDue] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [m, j, s] = await Promise.all([bfpo.get('/me'), bfpo.get('/jobs?when=all_open'), bfpo.get('/ppm/services')]);
        setMe(m.data); setJobs(j.data.jobs);
        setServicesDue((s.data.services || []).filter((x) => x.status !== 'completed').length);
      } finally { setLoading(false); }
    })();
  }, []);

  if (loading) return <Spinner />;
  const k = me?.kpis || {};

  return (
    <div className="p-4 space-y-5 max-w-2xl mx-auto" data-testid="engineer-home">
      <div>
        <p className="text-sm text-slate-500">Welcome back,</p>
        <h1 className="text-2xl font-bold text-slate-900">{me?.user?.name}</h1>
        <p className="text-sm font-semibold text-cyan-700 mt-0.5" data-testid="engineer-role-label">{ROLE_LABEL[me?.user?.role] || 'MOD / BFPO Engineer'}</p>
        <div className="flex flex-wrap gap-2 mt-2">
          {(me?.territories || []).map((t) => (
            <Badge key={t.id} className="bg-slate-100 text-slate-600 border-slate-200">{t.name}</Badge>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {TILES.map((t) => (
          <button key={t.key} onClick={() => onOpenJobs(t.key)} data-testid={`home-tile-${t.key}`}
            className="text-left">
            <Card className="p-4 hover:shadow-md transition-shadow h-full">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${t.color}`}>
                <t.icon className="w-5 h-5" />
              </div>
              <p className="text-3xl font-bold text-slate-900 mt-3" data-testid={`home-kpi-${t.key}`}>{k[t.kpi] ?? 0}</p>
              <p className="text-sm text-slate-500 font-medium">{t.label}</p>
            </Card>
          </button>
        ))}
      </div>

      <button onClick={onOpenServices} className="w-full text-left" data-testid="home-services-due">
        <Card className="p-4 flex items-center gap-3 hover:shadow-md transition-shadow">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center text-cyan-600 bg-cyan-50">
            <ClipboardCheck className="w-5 h-5" />
          </div>
          <div className="flex-1">
            <p className="font-semibold text-slate-900">Services Due</p>
            <p className="text-sm text-slate-500">Planned maintenance inspections</p>
          </div>
          <span className="text-2xl font-bold text-slate-900" data-testid="home-services-count">{servicesDue}</span>
          <ChevronRight className="w-5 h-5 text-slate-300" />
        </Card>
      </button>

      <div>
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-semibold text-slate-900">My Jobs</h2>
          <button className="text-sm text-cyan-600 font-semibold" onClick={() => onOpenJobs('all_open')} data-testid="home-see-all">See all</button>
        </div>
        {jobs.length === 0 ? (
          <Empty icon={ClipboardList} title="No open jobs" sub="You're all caught up." testid="home-empty" />
        ) : (
          <div className="space-y-2">
            {jobs.slice(0, 6).map((j) => (
              <button key={j.id} onClick={() => onOpenJob(j.id)} className="w-full text-left" data-testid={`home-job-${j.id}`}>
                <Card className="p-4 hover:shadow-md transition-shadow flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <PriorityBadge p={j.priority} />
                      {j.safety_critical && <Badge className="bg-red-100 text-red-700 border-red-200"><AlertTriangle className="w-3 h-3" /> Safety</Badge>}
                    </div>
                    <p className="font-semibold text-slate-900 truncate mt-1.5">{j.title}</p>
                    <p className="text-sm text-slate-500 truncate">{j.site_name} · {j.asset_name}</p>
                  </div>
                  <ChevronRight className="w-5 h-5 text-slate-300 shrink-0" />
                </Card>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
