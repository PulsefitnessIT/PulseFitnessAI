import React, { useEffect, useState } from 'react';
import { bfpo } from '../bfpoApi';
import { Card, Spinner, Empty, Badge, STATUS_LABEL, localTime } from '../ui';
import { History as HistoryIcon, ChevronRight } from 'lucide-react';

export default function History({ onOpenJob }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => { bfpo.get('/history').then((r) => { setRows(r.data.jobs); setLoading(false); }); }, []);
  if (loading) return <Spinner />;
  return (
    <div className="p-4 max-w-2xl mx-auto" data-testid="engineer-history">
      <h1 className="text-2xl font-bold text-slate-900 mb-3">Job History</h1>
      {rows.length === 0 ? <Empty icon={HistoryIcon} title="No completed jobs yet" testid="history-empty" /> : (
        <div className="space-y-2">
          {rows.map((j) => (
            <button key={j.id} onClick={() => onOpenJob(j.id)} className="w-full text-left" data-testid={`history-${j.id}`}>
              <Card className="p-4 flex items-center gap-3 hover:shadow-md transition-shadow">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200">{STATUS_LABEL[j.status] || j.status}</Badge>
                    <span className="text-xs text-slate-400">{localTime(j.closed_at)}</span>
                  </div>
                  <p className="font-semibold text-slate-900 truncate mt-1">{j.title}</p>
                  <p className="text-sm text-slate-500 truncate">{j.reference} · {j.site_name}</p>
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
