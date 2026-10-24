import React, { useEffect, useState, useCallback } from 'react';
import { bfpo } from '../bfpoApi';
import { Card, Btn, Spinner, Badge, PriorityBadge, STATUS_LABEL, inputCls, Field, localTime } from '../ui';
import { ChevronLeft, AlertTriangle, MapPin, Wrench, UserCheck, History, FileText, Loader2, User, ShieldAlert, Camera } from 'lucide-react';

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
        <Card className="p-4"><div className="flex gap-3"><Wrench className="w-5 h-5 text-slate-400" /><div><p className="text-xs font-semibold text-slate-400 uppercase">Equipment</p><p className="font-semibold text-slate-900">{job.asset_name || '—'}</p>{job.asset_serial && <p className="text-sm text-slate-500 font-mono">{job.asset_serial}</p>}</div></div></Card>
      </div>
      <SiteReport job={job} />
      <EngineerPhotos photos={job.photos} />

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
            {!(job.events || []).length && (
              <p className="text-sm text-slate-500" data-testid="staff-timeline-empty">
                No activity yet{job.created_at ? ` — logged ${localTime(job.created_at, job.site_timezone)}` : ''}.
              </p>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}

function SiteReport({ job }) {
  const i = job.mod_issue;
  const reporter = i?.reporter_name || i?.reported_by_name || job.reporter_name;
  const flags = i?.classification_flags || job.classification_flags || [];
  if (!i && !reporter) return null;
  return (
    <Card className="p-4 mt-4" data-testid="staff-site-report">
      <p className="text-xs font-semibold text-slate-400 uppercase mb-2 flex items-center gap-1.5"><User className="w-4 h-4" /> Reported by the site</p>
      <div className="grid sm:grid-cols-2 gap-x-6 gap-y-1 text-sm">
        <p><span className="text-slate-500">Reporter:</span> <span className="font-semibold text-slate-900" data-testid="staff-site-reporter">{reporter || '—'}</span></p>
        {(i?.reporter_email || i?.reporter_phone) && <p className="text-slate-600">{[i.reporter_email, i.reporter_phone].filter(Boolean).join(' · ')}</p>}
        {i?.created_at && <p><span className="text-slate-500">Logged:</span> {localTime(i.created_at)}</p>}
        {i?.status && <p><span className="text-slate-500">Site status:</span> <span className="capitalize" data-testid="staff-site-status">{i.status.replace('_', ' ')}</span></p>}
        {i?.safe_in_service === false && <p className="text-red-700 font-semibold">Taken out of service by the site</p>}
      </div>
      {flags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5" data-testid="staff-site-flags">
          {flags.map((f, k) => <Badge key={k} className="bg-amber-50 text-amber-800 border-amber-200"><ShieldAlert className="w-3 h-3" /> {typeof f === 'string' ? f : (f.label || f.type || 'Sensitive')}</Badge>)}
        </div>
      )}
    </Card>
  );
}

function EngineerPhotos({ photos }) {
  if (!photos?.length) return null;
  return (
    <Card className="p-4 mt-4" data-testid="staff-engineer-photos">
      <p className="text-xs font-semibold text-slate-400 uppercase mb-2 flex items-center gap-1.5"><Camera className="w-4 h-4" /> Engineer photos ({photos.length})</p>
      <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
        {photos.map((p) => (
          <a key={p.id} href={p.file_url} target="_blank" rel="noreferrer" title={p.caption || p.taken_by_name} data-testid={`staff-photo-${p.id}`}>
            <img src={p.file_url} alt={p.caption || 'Engineer photo'} className="w-full aspect-square object-cover rounded-lg border border-slate-200" loading="lazy" />
          </a>
        ))}
      </div>
    </Card>
  );
}
