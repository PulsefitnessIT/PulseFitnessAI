import React, { useEffect, useState } from 'react';
import { bfpo } from '../bfpoApi';
import { Card, Spinner, Empty, Badge } from '../ui';
import { MapPin, ChevronRight, ChevronLeft, Lock, Wrench, Phone } from 'lucide-react';

export default function Sites() {
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState(null);

  useEffect(() => { bfpo.get('/sites').then((r) => { setSites(r.data.sites); setLoading(false); }); }, []);

  const open = async (id) => { const r = await bfpo.get(`/sites/${id}`); setDetail(r.data); };

  if (loading) return <Spinner />;

  if (detail) {
    const s = detail.site;
    return (
      <div className="p-4 max-w-2xl mx-auto" data-testid="engineer-site-detail">
        <button onClick={() => setDetail(null)} className="flex items-center gap-1 text-slate-600 mb-3"><ChevronLeft className="w-5 h-5" /> Back to sites</button>
        <h1 className="text-2xl font-bold text-slate-900">{s.name}</h1>
        <p className="text-slate-500">{s.territory_name} · {s.country}</p>
        <div className="space-y-3 mt-4">
          {detail.sensitive_visible && s.access_instructions && (
            <Card className="p-4"><p className="text-xs font-semibold text-slate-400 uppercase">Access</p><p className="text-slate-700 mt-1">{s.access_instructions}</p></Card>
          )}
          {detail.sensitive_visible && s.security_notes && (
            <Card className="p-4"><p className="text-xs font-semibold text-slate-400 uppercase flex items-center gap-1"><Lock className="w-3 h-3" /> Security</p><p className="text-slate-700 mt-1">{s.security_notes}</p></Card>
          )}
          {s.contact_name && (
            <Card className="p-4"><p className="text-xs font-semibold text-slate-400 uppercase">Site contact</p><p className="text-slate-700 mt-1 flex items-center gap-2"><Phone className="w-4 h-4 text-slate-400" /> {s.contact_name} · {s.contact_phone}</p></Card>
          )}
          <Card className="p-4">
            <p className="text-xs font-semibold text-slate-400 uppercase flex items-center gap-1"><Wrench className="w-3 h-3" /> Equipment ({detail.equipment.length})</p>
            <div className="mt-2 space-y-1.5">
              {detail.equipment.map((e) => (
                <div key={e.id} className="flex justify-between text-sm border-b border-slate-100 pb-1.5">
                  <span className="text-slate-700">{e.name}</span>
                  <span className="text-slate-400">{e.serial_number}</span>
                </div>
              ))}
            </div>
          </Card>
          <p className="text-sm text-slate-500">{detail.open_jobs} open job(s) at this site.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 max-w-2xl mx-auto" data-testid="engineer-sites">
      <h1 className="text-2xl font-bold text-slate-900 mb-3">My Sites</h1>
      {sites.length === 0 ? <Empty icon={MapPin} title="No sites assigned" testid="sites-empty" /> : (
        <div className="space-y-2">
          {sites.map((s) => (
            <button key={s.id} onClick={() => open(s.id)} className="w-full text-left" data-testid={`site-${s.id}`}>
              <Card className="p-4 flex items-center gap-3 hover:shadow-md transition-shadow">
                <MapPin className="w-5 h-5 text-cyan-600 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-slate-900 truncate">{s.name}</p>
                  <p className="text-sm text-slate-500">{s.territory_name} · {s.country}</p>
                </div>
                <ChevronRight className="w-5 h-5 text-slate-300" />
              </Card>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
