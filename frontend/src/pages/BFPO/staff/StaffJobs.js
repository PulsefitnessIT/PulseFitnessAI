import React, { useEffect, useState, useCallback } from 'react';
import { bfpo } from '../bfpoApi';
import { Card, Spinner, Empty, Badge, PriorityBadge, STATUS_LABEL, inputCls, localTime } from '../ui';
import { Filter, AlertTriangle, ChevronRight, ClipboardList } from 'lucide-react';

export default function StaffJobs({ initialFilter = {}, onOpenJob }) {
  const [filters, setFilters] = useState({ status: 'open', territory: '', site: '', engineer: '', priority: '', safety: '', overdue: '', ...initialFilter });
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [meta, setMeta] = useState({ engineers: [], sites: [] });

  useEffect(() => { setFilters((f) => ({ ...f, ...initialFilter })); /* eslint-disable-next-line */ }, [JSON.stringify(initialFilter)]);

  useEffect(() => {
    Promise.all([bfpo.get('/staff/engineers'), bfpo.get('/sites')]).then(([e, s]) =>
      setMeta({ engineers: e.data.engineers, sites: s.data.sites }));
  }, []);

  const fetchJobs = useCallback(() => {
    setLoading(true);
    const qs = Object.entries(filters).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');
    bfpo.get(`/staff/jobs?${qs}`).then((r) => { setJobs(r.data.jobs); setLoading(false); });
  }, [filters]);
  useEffect(() => { fetchJobs(); }, [fetchJobs]);

  const set = (k, v) => setFilters((f) => ({ ...f, [k]: v }));

  return (
    <div className="p-6 max-w-6xl mx-auto" data-testid="staff-jobs">
      <Card className="p-4 mb-4">
        <div className="flex items-center gap-2 text-slate-500 text-sm font-semibold mb-3"><Filter className="w-4 h-4" /> Filters</div>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
          <select className={inputCls} value={filters.status} onChange={(e) => set('status', e.target.value)} data-testid="staff-filter-status">
            <option value="">All statuses</option><option value="open">Open</option><option value="on_site">On site</option>
            <option value="paused_parts">Waiting for parts</option><option value="closed">Completed</option>
          </select>
          <select className={inputCls} value={filters.priority} onChange={(e) => set('priority', e.target.value)} data-testid="staff-filter-priority">
            <option value="">Any priority</option><option value="p1">P1</option><option value="p2">P2</option><option value="p3">P3</option><option value="p4">P4</option>
          </select>
          <select className={inputCls} value={filters.site} onChange={(e) => set('site', e.target.value)} data-testid="staff-filter-site">
            <option value="">All sites</option>{meta.sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <select className={inputCls} value={filters.engineer} onChange={(e) => set('engineer', e.target.value)} data-testid="staff-filter-engineer">
            <option value="">Any engineer</option>{meta.engineers.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
          </select>
          <label className="flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={filters.safety === 'true'} onChange={(e) => set('safety', e.target.checked ? 'true' : '')} data-testid="staff-filter-safety" /> Safety-critical</label>
          <label className="flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={filters.overdue === 'true'} onChange={(e) => set('overdue', e.target.checked ? 'true' : '')} data-testid="staff-filter-overdue" /> Overdue</label>
        </div>
      </Card>

      {loading ? <Spinner /> : jobs.length === 0 ? <Empty icon={ClipboardList} title="No jobs match" testid="staff-jobs-empty" /> : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase">
              <tr><th className="text-left p-3">Ref</th><th className="text-left p-3">Job</th><th className="text-left p-3 hidden md:table-cell">Site</th><th className="text-left p-3 hidden lg:table-cell">Engineer</th><th className="text-left p-3">Priority</th><th className="text-left p-3">Status</th><th className="p-3" /></tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id} onClick={() => onOpenJob(j.id)} className="border-t border-slate-100 hover:bg-slate-50 cursor-pointer" data-testid={`staff-job-row-${j.id}`}>
                  <td className="p-3 font-mono text-xs text-slate-500">{j.reference}</td>
                  <td className="p-3"><div className="flex items-center gap-1.5">{j.safety_critical && <AlertTriangle className="w-3.5 h-3.5 text-red-500" />}<span className="font-medium text-slate-800">{j.title}</span></div></td>
                  <td className="p-3 hidden md:table-cell text-slate-500">{j.site_name}</td>
                  <td className="p-3 hidden lg:table-cell text-slate-500">{j.assigned_engineer_name || <span className="text-amber-600">Unallocated</span>}</td>
                  <td className="p-3"><PriorityBadge p={j.priority} /></td>
                  <td className="p-3"><Badge className="bg-slate-100 text-slate-600 border-slate-200">{STATUS_LABEL[j.status] || j.status}</Badge></td>
                  <td className="p-3"><ChevronRight className="w-4 h-4 text-slate-300" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
