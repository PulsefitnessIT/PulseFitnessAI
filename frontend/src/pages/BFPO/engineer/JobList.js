import React, { useEffect, useState } from 'react';
import { bfpo, pendingStatusFor } from '../bfpoApi';
import { Card, PriorityBadge, Spinner, Empty, Badge, STATUS_LABEL } from '../ui';
import { AlertTriangle, ChevronRight, ClipboardList } from 'lucide-react';

const FILTERS = [
  { key: 'all_open', label: 'All Open' },
  { key: 'new', label: 'New' },
  { key: 'in_progress', label: 'In Progress' },
  { key: 'waiting_parts', label: 'Waiting for Parts' },
  { key: 'return_visit', label: 'Return Visit' },
  { key: 'completed', label: 'Completed' },
];

export default function JobList({ initialFilter = 'all_open', onOpenJob }) {
  const [filter, setFilter] = useState(initialFilter);
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { setFilter(initialFilter); }, [initialFilter]);

  useEffect(() => {
    let live = true;
    setLoading(true);
    bfpo.get(`/jobs?when=${filter}`).then((r) => { if (live) { setJobs(r.data.jobs); setLoading(false); } });
    return () => { live = false; };
  }, [filter]);

  return (
    <div className="p-4 max-w-2xl mx-auto" data-testid="engineer-joblist">
      <h1 className="text-2xl font-bold text-slate-900 mb-3">Jobs</h1>
      <div className="flex gap-2 overflow-x-auto pb-3 -mx-1 px-1">
        {FILTERS.map((f) => (
          <button key={f.key} onClick={() => setFilter(f.key)} data-testid={`joblist-filter-${f.key}`}
            className={`whitespace-nowrap px-3.5 py-2 rounded-full text-sm font-semibold border transition-colors ${filter === f.key ? 'bg-slate-900 text-white border-slate-900' : 'bg-white text-slate-600 border-slate-200'}`}>
            {f.label}
          </button>
        ))}
      </div>
      {loading ? <Spinner /> : jobs.length === 0 ? (
        <Empty icon={ClipboardList} title="No jobs here" sub="Nothing matches this filter." testid="joblist-empty" />
      ) : (
        <div className="space-y-2">
          {jobs.map((j) => (
            <button key={j.id} onClick={() => onOpenJob(j.id)} className="w-full text-left" data-testid={`joblist-job-${j.id}`}>
              <Card className="p-4 hover:shadow-md transition-shadow flex items-center gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <PriorityBadge p={j.priority} />
                    {j.safety_critical && <Badge className="bg-red-100 text-red-700 border-red-200"><AlertTriangle className="w-3 h-3" /> Safety</Badge>}
                    <Badge className="bg-slate-100 text-slate-600 border-slate-200">{STATUS_LABEL[pendingStatusFor(j.id, j.status)] || pendingStatusFor(j.id, j.status)}</Badge>
                  </div>
                  <p className="font-semibold text-slate-900 truncate mt-1.5">{j.title}</p>
                  <p className="text-sm text-slate-500 truncate">{j.reference} · {j.site_name} · {j.asset_name}</p>
                </div>
                <ChevronRight className="w-5 h-5 text-slate-300 shrink-0" />
              </Card>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
