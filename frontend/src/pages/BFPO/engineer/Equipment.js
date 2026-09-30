import React, { useEffect, useState } from 'react';
import { bfpo } from '../bfpoApi';
import { Card, Spinner, Empty, inputCls, Badge, STATUS_LABEL, localTime } from '../ui';
import { Package, Search, ChevronLeft, ChevronRight } from 'lucide-react';

export default function Equipment() {
  const [q, setQ] = useState('');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState(null);

  const search = (term) => { setLoading(true); bfpo.get(`/equipment?search=${encodeURIComponent(term)}`).then((r) => { setRows(r.data.equipment); setLoading(false); }); };
  useEffect(() => { search(''); }, []);
  useEffect(() => { const t = setTimeout(() => search(q), 300); return () => clearTimeout(t); }, [q]);

  const open = async (id) => { const r = await bfpo.get(`/equipment/${id}`); setDetail(r.data); };

  if (detail) {
    const e = detail.equipment;
    return (
      <div className="p-4 max-w-2xl mx-auto" data-testid="engineer-equipment-detail">
        <button onClick={() => setDetail(null)} className="flex items-center gap-1 text-slate-600 mb-3"><ChevronLeft className="w-5 h-5" /> Back</button>
        <h1 className="text-2xl font-bold text-slate-900">{e.name}</h1>
        <p className="text-slate-500">{e.manufacturer} · Serial {e.serial_number}</p>
        <p className="text-sm text-slate-500">{e.site_name} · {e.country}</p>
        <Card className="p-4 mt-4">
          <p className="text-xs font-semibold text-slate-400 uppercase">Job history</p>
          {detail.history.length === 0 ? <p className="text-sm text-slate-400 mt-2">No prior jobs.</p> : (
            <div className="mt-2 space-y-2">
              {detail.history.map((h) => (
                <div key={h.id} className="border-b border-slate-100 pb-2">
                  <div className="flex justify-between items-center">
                    <p className="text-sm font-medium text-slate-700">{h.title}</p>
                    <Badge className="bg-slate-100 text-slate-600 border-slate-200">{STATUS_LABEL[h.status] || h.status}</Badge>
                  </div>
                  <p className="text-xs text-slate-400">{h.reference} · {localTime(h.closed_at || h.created_at)}</p>
                  {h.resolution_notes && <p className="text-sm text-slate-500 mt-0.5">{h.resolution_notes}</p>}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    );
  }

  return (
    <div className="p-4 max-w-2xl mx-auto" data-testid="engineer-equipment">
      <h1 className="text-2xl font-bold text-slate-900 mb-3">Equipment</h1>
      <div className="relative mb-3">
        <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
        <input className={inputCls + ' pl-9'} placeholder="Search serial, model or make" value={q} onChange={(e) => setQ(e.target.value)} data-testid="equipment-search" />
      </div>
      {loading ? <Spinner /> : rows.length === 0 ? <Empty icon={Package} title="No equipment found" testid="equipment-empty" /> : (
        <div className="space-y-2">
          {rows.map((e) => (
            <button key={e.id} onClick={() => open(e.id)} className="w-full text-left" data-testid={`equipment-${e.id}`}>
              <Card className="p-4 flex items-center gap-3 hover:shadow-md transition-shadow">
                <Package className="w-5 h-5 text-slate-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-slate-900 truncate">{e.name}</p>
                  <p className="text-sm text-slate-500 truncate">{e.serial_number} · {e.site_name}</p>
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
