import React, { useEffect, useState, useCallback } from 'react';
import { bfpo } from '../bfpoApi';
import { Card, Btn, Spinner, Badge, PriorityBadge, STATUS_LABEL, inputCls, Field, localTime } from '../ui';
import { ChevronLeft, AlertTriangle, MapPin, Wrench, UserCheck, History, FileText, Loader2 } from 'lucide-react';

export default function StaffJobDetail({ jobId, onBack }) {
  const [job, setJob] = useState(null);
  const [engineers, setEngineers] = useState([]);
  const [engId, setEngId] = useState('');
  const [handover, setHandover] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  const load = useCallback(async () => {
    const [j, e] = await Promise.all([bfpo.get(`/staff/jobs/${jobId}`), bfpo.get('/staff/engineers')]);
    setJob(j.data); setEngineers(e.data.engineers);
    setEngId(j.data.assigned_engineer_id || '');
  }, [jobId]);
  useEffect(() => { load(); }, [load]);

  const allocate = async () => {
    setBusy(true); setMsg('');
    try {
      await bfpo.post(`/staff/jobs/${jobId}/allocate`, { engineer_id: engId, handover });
      setHandover(''); await load(); setMsg('Allocation saved');
    } catch (e) { setMsg(e?.response?.data?.detail || 'Could not allocate'); }
    finally { setBusy(false); }
  };

  if (!job) return <Spinner />;

  return (
    <div className="p-6 max-w-4xl mx-auto" data-testid="staff-job-detail">
      <button onClick={onBack} className="flex items-center gap-1 text-slate-600 mb-3"><ChevronLeft className="w-5 h-5" /> Back to jobs</button>
      <div className="flex items-center gap-2 flex-wrap mb-2">
        <PriorityBadge p={job.priority} />
        {job.safety_critical && <Badge className="bg-red-100 text-red-700 border-red-200"><AlertTriangle className="w-3 h-3" /> Safety Critical</Badge>}
        <Badge className="bg-slate-100 text-slate-600 border-slate-200">{STATUS_LABEL[job.status] || job.status}</Badge>
        <span className="font-mono text-xs text-slate-400">{job.reference}</span>
      </div>
      <h1 className="text-2xl font-bold text-slate-900">{job.title}</h1>
      <p className="text-slate-600">{job.description}</p>

      <div className="grid md:grid-cols-2 gap-4 mt-5">
        <Card className="p-4"><div className="flex gap-3"><MapPin className="w-5 h-5 text-slate-400" /><div><p className="text-xs font-semibold text-slate-400 uppercase">Site</p><p className="font-semibold text-slate-900">{job.site_name}</p><p className="text-sm text-slate-500">{job.territory_name} · {job.country}</p></div></div></Card>
        <Card className="p-4"><div className="flex gap-3"><Wrench className="w-5 h-5 text-slate-400" /><div><p className="text-xs font-semibold text-slate-400 uppercase">Equipment</p><p className="font-semibold text-slate-900">{job.asset_name || '—'}</p></div></div></Card>
      </div>

      {/* Allocation / handover */}
      <Card className="p-4 mt-4" data-testid="staff-allocate">
        <p className="font-semibold text-slate-900 flex items-center gap-2 mb-3"><UserCheck className="w-4 h-4 text-cyan-600" /> Allocate / Reallocate</p>
        <p className="text-sm text-slate-500 mb-2">Currently: <span className="font-medium text-slate-700">{job.assigned_engineer_name || 'Unallocated'}</span></p>
        <div className="grid md:grid-cols-2 gap-3">
          <Field label="Assign to engineer">
            <select className={inputCls} value={engId} onChange={(e) => setEngId(e.target.value)} data-testid="staff-allocate-engineer">
              <option value="">— choose —</option>
              {engineers.map((e) => <option key={e.id} value={e.id}>{e.full_name} ({e.bfpo_role})</option>)}
            </select>
          </Field>
          <Field label="Handover note (optional)"><input className={inputCls} value={handover} onChange={(e) => setHandover(e.target.value)} placeholder="Context for the next engineer" data-testid="staff-allocate-handover" /></Field>
        </div>
        <div className="flex items-center gap-3 mt-3">
          <Btn variant="primary" disabled={busy || !engId} onClick={allocate} data-testid="staff-allocate-submit">{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null} Save allocation</Btn>
          {msg && <span className="text-sm text-slate-500" data-testid="staff-allocate-msg">{msg}</span>}
        </div>
      </Card>

      {job.resolution_notes && (
        <a href={`${process.env.REACT_APP_BACKEND_URL}/api/bfpo/jobs/${jobId}/job-sheet.pdf`} target="_blank" rel="noreferrer"
          className="inline-flex items-center gap-2 mt-4 text-cyan-600 font-semibold text-sm" data-testid="staff-jobsheet"><FileText className="w-4 h-4" /> View job sheet (PDF)</a>
      )}

      <div className="mt-5">
        <p className="font-semibold text-slate-900 flex items-center gap-2 mb-2"><History className="w-4 h-4" /> Activity Timeline</p>
        <Card className="p-4">
          <div className="space-y-3">
            {(job.events || []).map((e) => (
              <div key={e.id} className="flex gap-3 text-sm" data-testid={`staff-timeline-${e.id}`}>
                <div className="w-2 h-2 rounded-full bg-cyan-500 mt-1.5 shrink-0" />
                <div>
                  <p className="text-slate-700">{e.body || e.type}</p>
                  <p className="text-xs text-slate-400">{e.type} · {e.actor_name} · {localTime(e.at, job.site_timezone)}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
