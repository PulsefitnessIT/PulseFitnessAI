import React, { useEffect, useState } from 'react';
import { bfpo } from '../bfpoApi';
import { Card, Spinner, Badge, HEALTH } from '../ui';
import { Globe2, MapPin } from 'lucide-react';

export default function StaffSites({ onOpenJobs }) {
  const [tree, setTree] = useState(null);
  useEffect(() => { bfpo.get('/staff/sites').then((r) => setTree(r.data.tree)); }, []);
  if (!tree) return <Spinner />;
  return (
    <div className="p-6 max-w-6xl mx-auto" data-testid="staff-sites">
      <h1 className="text-2xl font-bold text-slate-900 mb-1">Global Site View</h1>
      <p className="text-slate-500 mb-5">By country and territory</p>
      <div className="space-y-6">
        {tree.map((c) => (
          <div key={c.country} data-testid={`staff-country-${c.country}`}>
            <h2 className="font-bold text-slate-800 flex items-center gap-2 mb-2"><Globe2 className="w-4 h-4 text-cyan-600" /> {c.country}</h2>
            <div className="space-y-3">
              {c.territories.map((t) => (
                <Card key={t.territory_name} className="p-4">
                  <div className="flex items-center justify-between mb-3">
                    <p className="font-semibold text-slate-900">{t.territory_name}</p>
                    <Badge className={HEALTH[t.health].cls}><span className={`w-2 h-2 rounded-full ${HEALTH[t.health].dot}`} /> {HEALTH[t.health].label}</Badge>
                  </div>
                  <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
                    {t.sites.map((s) => (
                      <button key={s.site_id} onClick={() => onOpenJobs({ site: s.site_id })} data-testid={`staff-site-${s.site_id}`}
                        className="text-left border border-slate-200 rounded-xl p-3 hover:bg-slate-50 transition-colors">
                        <div className="flex items-center gap-2">
                          <span className={`w-2.5 h-2.5 rounded-full ${HEALTH[s.health].dot}`} />
                          <span className="font-medium text-slate-800 text-sm truncate">{s.site_name}</span>
                        </div>
                        <p className="text-xs text-slate-500 mt-1">{s.open_jobs} open job(s)</p>
                      </button>
                    ))}
                  </div>
                </Card>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
