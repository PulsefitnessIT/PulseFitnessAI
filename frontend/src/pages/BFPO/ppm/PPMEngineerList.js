import React, { useEffect, useState } from 'react';
import { bfpo } from '../bfpoApi';
import { Card, Spinner, Empty, Badge } from '../ui';
import { ClipboardCheck, ChevronRight, ChevronLeft } from 'lucide-react';

export default function PPMEngineerList({ onOpen, onBack }) {
  const [rows, setRows] = useState(null);
  useEffect(() => { bfpo.get('/ppm/services').then((r) => setRows(r.data.services)); }, []);
  if (!rows) return <Spinner />;
  return (
    <div className="p-4 max-w-2xl mx-auto" data-testid="ppm-engineer-list">
      <div className="flex items-center gap-2 mb-3">
        {onBack && <button onClick={onBack} className="p-1 -ml-1"><ChevronLeft className="w-6 h-6 text-slate-600" /></button>}
        <h1 className="text-2xl font-bold text-slate-900">Services Due</h1>
      </div>
      {rows.length === 0 ? <Empty icon={ClipboardCheck} title="No services scheduled" sub="Nothing to inspect right now." testid="ppm-empty" /> : (
        <div className="space-y-2">
          {rows.map((s) => (
            <button key={s.id} onClick={() => onOpen(s.id)} className="w-full text-left" data-testid={`ppm-row-${s.id}`}>
              <Card className="p-4 flex items-center gap-3 hover:shadow-md transition-shadow">
                <ClipboardCheck className="w-5 h-5 text-cyan-600 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-slate-900 truncate">{s.reference} · {s.site_name}</p>
                  <p className="text-sm text-slate-500">{s.progress?.done}/{s.progress?.total} checked{s.due_date ? ` · due ${s.due_date}` : ''}</p>
                </div>
                <Badge className={s.status === 'completed' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : s.status === 'due' ? 'bg-amber-50 text-amber-700 border-amber-200' : 'bg-cyan-50 text-cyan-700 border-cyan-200'}>
                  {s.status === 'in_progress' ? 'In progress' : s.status === 'due' ? 'Due' : 'Completed'}
                </Badge>
                <ChevronRight className="w-5 h-5 text-slate-300" />
              </Card>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
