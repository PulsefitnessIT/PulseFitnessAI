import React, { useEffect, useState, useCallback } from 'react';
import { bfpo, uploadFile } from '../bfpoApi';
import { Card, Btn, Badge, Spinner, PriorityBadge, STATUS_LABEL, Field, inputCls, localTime } from '../ui';
import SignaturePad from './SignaturePad';
import {
  ChevronLeft, AlertTriangle, MapPin, Wrench, ShieldCheck, ShieldAlert, Package,
  RotateCcw, Ban, PlusCircle, Camera, CheckCircle2, Clock, FileText, History, Loader2,
} from 'lucide-react';

const OPEN = ['new', 'triaged', 'assigned', 'en_route', 'on_site', 'paused_parts', 'paused_customer', 'repaired', 'awaiting_sign_off'];

export default function JobDetail({ jobId, onBack, onOpenJob }) {
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [panel, setPanel] = useState(null); // arrive | workflow | parts | outcome:X | report | complete
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');

  const load = useCallback(async () => {
    const r = await bfpo.get(`/jobs/${jobId}`);
    setJob(r.data); setLoading(false);
  }, [jobId]);
  useEffect(() => { load(); }, [load]);

  const flash = (m) => { setToast(m); setTimeout(() => setToast(''), 2500); };
  const act = async (fn, msg) => {
    setBusy(true);
    try { await fn(); await load(); if (msg) flash(msg); setPanel(null); }
    catch (e) { flash(e?.response?.data?.detail || 'Could not save — your work is stored, we will retry.'); }
    finally { setBusy(false); }
  };

  if (loading) return <Spinner />;
  if (!job) return null;
  const status = job.status;
  const isOpen = OPEN.includes(status);

  const primary = () => {
    if (!isOpen) return null;
    if (['new', 'triaged'].includes(status)) return { label: 'Accept Job', onClick: () => act(() => bfpo.post(`/jobs/${jobId}/accept`, {}), 'Job accepted') };
    if (['assigned', 'en_route'].includes(status)) return { label: "I'm on site — Start Job", onClick: () => setPanel('arrive') };
    if (status === 'paused_parts') return { label: 'Continue Job', onClick: () => setPanel('workflow') };
    if (job.return_visit) return { label: 'Continue — Return Visit', onClick: () => setPanel('workflow') };
    return { label: 'Update Job', onClick: () => setPanel('workflow') };
  };
  const pa = primary();

  return (
    <div className="pb-28 max-w-2xl mx-auto" data-testid="engineer-jobdetail">
      <div className="sticky top-0 z-10 bg-white border-b border-slate-200 px-4 py-3 flex items-center gap-3">
        <button onClick={onBack} data-testid="jobdetail-back" className="p-1 -ml-1"><ChevronLeft className="w-6 h-6 text-slate-600" /></button>
        <div className="min-w-0">
          <p className="font-bold text-slate-900 truncate">{job.reference}</p>
          <p className="text-xs text-slate-500">{STATUS_LABEL[status] || status}</p>
        </div>
      </div>

      <div className="p-4 space-y-4">
        <div className="flex items-center gap-2 flex-wrap">
          <PriorityBadge p={job.priority} testid="jobdetail-priority" />
          {job.safety_critical && <Badge className="bg-red-100 text-red-700 border-red-200"><AlertTriangle className="w-3 h-3" /> Safety Critical</Badge>}
          {job.return_visit && <Badge className="bg-indigo-100 text-indigo-700 border-indigo-200"><RotateCcw className="w-3 h-3" /> Return Visit</Badge>}
          {status === 'paused_parts' && <Badge className="bg-amber-100 text-amber-700 border-amber-200"><Package className="w-3 h-3" /> Waiting for Parts</Badge>}
        </div>

        {/* Reported fault — front and centre */}
        <Card className="p-4 border-l-4 border-l-cyan-500">
          <p className="text-xs font-semibold text-cyan-700 uppercase tracking-wide">Reported Fault</p>
          <h1 className="text-lg font-bold text-slate-900 mt-1">{job.title}</h1>
          {job.description && <p className="text-slate-600 mt-1">{job.description}</p>}
        </Card>

        <div className="grid grid-cols-1 gap-3">
          <Card className="p-4">
            <div className="flex items-start gap-3">
              <Wrench className="w-5 h-5 text-slate-400 mt-0.5" />
              <div>
                <p className="text-xs font-semibold text-slate-400 uppercase">Equipment</p>
                <p className="font-semibold text-slate-900">{job.asset_name || '—'}</p>
                {job.equipment?.[0]?.serial_number && <p className="text-sm text-slate-500">Serial {job.equipment[0].serial_number}</p>}
              </div>
            </div>
          </Card>
          <Card className="p-4">
            <div className="flex items-start gap-3">
              <MapPin className="w-5 h-5 text-slate-400 mt-0.5" />
              <div className="min-w-0">
                <p className="text-xs font-semibold text-slate-400 uppercase">Site</p>
                <p className="font-semibold text-slate-900">{job.site_name}</p>
                <p className="text-sm text-slate-500">{job.territory_name} · {job.country}</p>
                {job.site?.access_instructions && (
                  <p className="text-sm text-slate-600 mt-2 bg-slate-50 rounded-lg p-2"><span className="font-semibold">Access:</span> {job.site.access_instructions}</p>
                )}
                {job.site?.contact_name && <p className="text-sm text-slate-500 mt-1">Contact: {job.site.contact_name} · {job.site.contact_phone}</p>}
              </div>
            </div>
          </Card>
        </div>

        {job.diagnosis && (
          <Card className="p-4"><p className="text-xs font-semibold text-slate-400 uppercase">Diagnosis</p><p className="text-slate-700 mt-1">{job.diagnosis}</p></Card>
        )}
        {!isOpen && job.resolution_notes && (
          <Card className="p-4 border-l-4 border-l-emerald-500" data-testid="jobdetail-completed-recap">
            <p className="text-xs font-semibold text-emerald-700 uppercase flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> Completed</p>
            <p className="text-slate-700 mt-1">{job.resolution_notes}</p>
            {job.parts_used && <p className="text-sm text-slate-500 mt-1">Parts used: {job.parts_used}</p>}
            <a href={`${process.env.REACT_APP_BACKEND_URL}/api/bfpo/jobs/${jobId}/job-sheet.pdf`} target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-2 mt-3 text-cyan-600 font-semibold text-sm" data-testid="jobdetail-jobsheet">
              <FileText className="w-4 h-4" /> View job sheet (PDF)
            </a>
          </Card>
        )}

        {/* Panels */}
        {panel === 'arrive' && <ArrivePanel busy={busy} onCancel={() => setPanel(null)}
          onSubmit={(safe, notes) => act(() => bfpo.post(`/jobs/${jobId}/arrive`, { safe, notes }), safe ? 'On site' : 'Safety concern raised')} />}

        {panel === 'workflow' && (
          <WorkflowPanel job={job} busy={busy} onClose={() => setPanel(null)}
            onDiagnosis={(t) => act(() => bfpo.post(`/jobs/${jobId}/diagnosis`, { diagnosis: t }), 'Diagnosis saved')}
            onChoose={setPanel} />
        )}

        {panel === 'parts' && <PartsPanel job={job} busy={busy} onCancel={() => setPanel('workflow')}
          onSubmit={(payload) => act(() => bfpo.post(`/jobs/${jobId}/parts`, payload), 'Parts request logged — job now Waiting for Parts')} />}

        {String(panel).startsWith('outcome:') && (
          <OutcomePanel outcome={panel.split(':')[1]} busy={busy} onCancel={() => setPanel('workflow')}
            onSubmit={(reason, details) => act(() => bfpo.post(`/jobs/${jobId}/outcome`, { outcome: panel.split(':')[1], reason, details }), 'Update sent to MOD staff')} />
        )}

        {panel === 'report' && <ReportFaultPanel job={job} busy={busy} onCancel={() => setPanel('workflow')}
          onDone={(res) => { setPanel(null); flash(res.warning ? res.warning : `Linked case ${res.case.reference} created`); }} jobId={jobId} />}

        {panel === 'complete' && <CompletePanel jobId={jobId} busy={busy} onCancel={() => setPanel('workflow')}
          onDone={() => { load(); setPanel(null); flash('Job completed — job sheet generated'); }} />}

        {/* Timeline */}
        <div>
          <p className="text-xs font-semibold text-slate-400 uppercase flex items-center gap-1 mb-2"><History className="w-3 h-3" /> Activity</p>
          <div className="space-y-2">
            {(job.events || []).slice(0, 12).map((e) => (
              <div key={e.id} className="flex gap-3 text-sm">
                <div className="w-2 h-2 rounded-full bg-cyan-500 mt-1.5 shrink-0" />
                <div>
                  <p className="text-slate-700">{e.body || e.type}</p>
                  <p className="text-xs text-slate-400">{e.actor_name} · {localTime(e.at, job.site_timezone)}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Sticky primary action */}
      {pa && !panel && (
        <div className="fixed bottom-16 left-0 right-0 px-4 pb-3 pt-2 bg-gradient-to-t from-white via-white to-transparent max-w-2xl mx-auto">
          <Btn full variant="primary" onClick={pa.onClick} disabled={busy} data-testid="jobdetail-primary-action" className="shadow-lg py-4 text-base">
            {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : null}{pa.label}
          </Btn>
        </div>
      )}
      {toast && <div className="fixed bottom-32 left-1/2 -translate-x-1/2 bg-slate-900 text-white text-sm px-4 py-2 rounded-full shadow-lg z-20" data-testid="jobdetail-toast">{toast}</div>}
    </div>
  );
}

function ArrivePanel({ onSubmit, onCancel, busy }) {
  const [notes, setNotes] = useState('');
  return (
    <Card className="p-4 space-y-3" data-testid="panel-arrive">
      <p className="font-semibold text-slate-900">Are you on site and is it safe to work?</p>
      <Field label="Any safety notes (optional)"><textarea className={inputCls} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} data-testid="arrive-notes" /></Field>
      <div className="grid grid-cols-1 gap-2">
        <Btn variant="primary" full disabled={busy} onClick={() => onSubmit(true, notes)} data-testid="arrive-safe"><ShieldCheck className="w-4 h-4" /> Yes — safe to work</Btn>
        <Btn variant="danger" full disabled={busy} onClick={() => onSubmit(false, notes)} data-testid="arrive-unsafe"><ShieldAlert className="w-4 h-4" /> No — raise a safety concern</Btn>
        <Btn variant="ghost" full onClick={onCancel}>Cancel</Btn>
      </div>
    </Card>
  );
}

function WorkflowPanel({ job, onDiagnosis, onChoose, onClose, busy }) {
  const [diag, setDiag] = useState(job.diagnosis || '');
  const OPTIONS = [
    { key: 'complete', label: 'Repaired — complete job', icon: CheckCircle2, variant: 'primary' },
    { key: 'parts', label: 'Parts needed', icon: Package, variant: 'outline' },
    { key: 'outcome:return_visit', label: 'Return visit needed', icon: RotateCcw, variant: 'outline' },
    { key: 'outcome:unable_access', label: 'Unable to access', icon: Ban, variant: 'outline' },
    { key: 'outcome:equipment_unsafe', label: 'Equipment unsafe', icon: ShieldAlert, variant: 'outline' },
    { key: 'report', label: 'Report another fault', icon: PlusCircle, variant: 'outline' },
  ];
  return (
    <Card className="p-4 space-y-3" data-testid="panel-workflow">
      <div className="flex items-center justify-between">
        <p className="font-semibold text-slate-900">On-site workflow</p>
        <button onClick={onClose} className="text-sm text-slate-500">Close</button>
      </div>
      <Field label="Diagnosis">
        <textarea className={inputCls} rows={2} value={diag} onChange={(e) => setDiag(e.target.value)} placeholder="What's wrong with the equipment?" data-testid="workflow-diagnosis" />
      </Field>
      <Btn variant="ghost" full disabled={busy || !diag.trim()} onClick={() => onDiagnosis(diag)} data-testid="workflow-save-diagnosis">Save diagnosis</Btn>
      <p className="text-xs font-semibold text-slate-400 uppercase pt-1">Was it repaired?</p>
      <div className="grid grid-cols-1 gap-2">
        {OPTIONS.map((o) => (
          <Btn key={o.key} variant={o.variant} full onClick={() => onChoose(o.key)} data-testid={`workflow-opt-${o.key.replace(':', '-')}`}>
            <o.icon className="w-4 h-4" /> {o.label}
          </Btn>
        ))}
      </div>
    </Card>
  );
}

function PartsPanel({ job, onSubmit, onCancel, busy }) {
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [eqId, setEqId] = useState(job.asset_id || '');
  const [photoUrl, setPhotoUrl] = useState('');
  const [uploading, setUploading] = useState(false);
  const parts = (job.equipment?.[0]?.parts) || [];
  const doUpload = async (e) => {
    const f = e.target.files?.[0]; if (!f) return; setUploading(true);
    try { const r = await uploadFile(f); setPhotoUrl(r.download_url); } finally { setUploading(false); }
  };
  return (
    <Card className="p-4 space-y-3" data-testid="panel-parts">
      <p className="font-semibold text-slate-900">Log a part — no part number needed</p>
      {parts.length > 0 && (
        <Field label="Pick from this equipment's parts">
          <select className={inputCls} value={name} onChange={(e) => setName(e.target.value)} data-testid="parts-pick">
            <option value="">— choose —</option>
            {parts.map((p, i) => <option key={i} value={p.name}>{p.name}</option>)}
          </select>
        </Field>
      )}
      <Field label="Or describe the part"><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. drive belt" data-testid="parts-name" /></Field>
      <Field label="Notes (optional)"><textarea className={inputCls} rows={2} value={desc} onChange={(e) => setDesc(e.target.value)} data-testid="parts-desc" /></Field>
      <Field label="Photo of the part (optional)">
        <label className="flex items-center gap-2 text-sm text-cyan-600 font-semibold cursor-pointer">
          <Camera className="w-4 h-4" /> {uploading ? 'Uploading…' : photoUrl ? 'Photo attached ✓' : 'Add photo'}
          <input type="file" accept="image/*" className="hidden" onChange={doUpload} data-testid="parts-photo" />
        </label>
      </Field>
      <div className="grid grid-cols-1 gap-2">
        <Btn variant="primary" full disabled={busy || (!name.trim() && !photoUrl)} data-testid="parts-submit"
          onClick={() => onSubmit({ name, description: desc, equipment_id: eqId, photo_url: photoUrl })}>Request part & pause job</Btn>
        <Btn variant="ghost" full onClick={onCancel}>Back</Btn>
      </div>
    </Card>
  );
}

const OUTCOME_META = {
  return_visit: { title: 'Return visit needed', hint: 'Why does this need another visit?' },
  unable_access: { title: 'Unable to access', hint: 'What stopped you accessing the equipment?' },
  equipment_unsafe: { title: 'Equipment unsafe', hint: 'Describe the safety issue.' },
};
function OutcomePanel({ outcome, onSubmit, onCancel, busy }) {
  const meta = OUTCOME_META[outcome] || {};
  const [reason, setReason] = useState('');
  const [details, setDetails] = useState('');
  return (
    <Card className="p-4 space-y-3" data-testid="panel-outcome">
      <p className="font-semibold text-slate-900">{meta.title}</p>
      <Field label="Reason"><input className={inputCls} value={reason} onChange={(e) => setReason(e.target.value)} placeholder={meta.hint} data-testid="outcome-reason" /></Field>
      <Field label="Details (optional)"><textarea className={inputCls} rows={2} value={details} onChange={(e) => setDetails(e.target.value)} data-testid="outcome-details" /></Field>
      <div className="grid grid-cols-1 gap-2">
        <Btn variant="primary" full disabled={busy || !reason.trim()} onClick={() => onSubmit(reason, details)} data-testid="outcome-submit">Send update</Btn>
        <Btn variant="ghost" full onClick={onCancel}>Back</Btn>
      </div>
    </Card>
  );
}

function ReportFaultPanel({ job, jobId, onDone, onCancel, busy }) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState('p3');
  const [safety, setSafety] = useState(false);
  const [saving, setSaving] = useState(false);
  const submit = async () => {
    setSaving(true);
    try { const r = await bfpo.post(`/jobs/${jobId}/report-fault`, { title, description, priority, safety_critical: safety, equipment_id: job.asset_id }); onDone(r.data); }
    finally { setSaving(false); }
  };
  return (
    <Card className="p-4 space-y-3" data-testid="panel-report">
      <p className="font-semibold text-slate-900">Report another fault</p>
      <Field label="What's the fault?"><input className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} data-testid="report-title" /></Field>
      <Field label="Details"><textarea className={inputCls} rows={2} value={description} onChange={(e) => setDescription(e.target.value)} data-testid="report-desc" /></Field>
      <Field label="Priority">
        <select className={inputCls} value={priority} onChange={(e) => setPriority(e.target.value)} data-testid="report-priority">
          <option value="p1">P1 · Critical</option><option value="p2">P2 · High</option><option value="p3">P3 · Medium</option><option value="p4">P4 · Low</option>
        </select>
      </Field>
      <label className="flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={safety} onChange={(e) => setSafety(e.target.checked)} data-testid="report-safety" /> Safety critical</label>
      <div className="grid grid-cols-1 gap-2">
        <Btn variant="primary" full disabled={saving || !title.trim()} onClick={submit} data-testid="report-submit">Create linked case</Btn>
        <Btn variant="ghost" full onClick={onCancel}>Back</Btn>
      </div>
    </Card>
  );
}

function CompletePanel({ jobId, onDone, onCancel }) {
  const [summary, setSummary] = useState('');
  const [partsUsed, setPartsUsed] = useState('');
  const [safe, setSafe] = useState(true);
  const [sigName, setSigName] = useState('');
  const [sigRole, setSigRole] = useState('');
  const [sigData, setSigData] = useState('');
  const [sigUnavailable, setSigUnavailable] = useState(false);
  const [sigReason, setSigReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const submit = async () => {
    if (!summary.trim()) { setErr('Please describe the work carried out'); return; }
    setSaving(true); setErr('');
    try {
      await bfpo.post(`/jobs/${jobId}/complete`, { summary, parts_used: partsUsed, safe_and_working: safe });
      if (sigUnavailable) await bfpo.post(`/jobs/${jobId}/signature`, { unavailable: true, reason: sigReason });
      else if (sigName && sigData) await bfpo.post(`/jobs/${jobId}/signature`, { signed_by_name: sigName, signed_by_role: sigRole, image_data: sigData });
      onDone();
    } catch (e) { setErr(e?.response?.data?.detail || 'Could not complete — try again'); }
    finally { setSaving(false); }
  };

  return (
    <Card className="p-4 space-y-3" data-testid="panel-complete">
      <p className="font-semibold text-slate-900">Complete job</p>
      <Field label="Work carried out"><textarea className={inputCls} rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} data-testid="complete-summary" /></Field>
      <Field label="Parts used (optional)"><input className={inputCls} value={partsUsed} onChange={(e) => setPartsUsed(e.target.value)} data-testid="complete-parts" /></Field>
      <label className="flex items-center gap-2 text-sm text-slate-700 font-medium"><input type="checkbox" checked={safe} onChange={(e) => setSafe(e.target.checked)} data-testid="complete-safe" /> I confirm the equipment is safe and working</label>
      <div className="pt-1">
        <p className="text-xs font-semibold text-slate-400 uppercase mb-1">Customer sign-off</p>
        {!sigUnavailable ? (
          <>
            <div className="grid grid-cols-2 gap-2 mb-2">
              <input className={inputCls} placeholder="Signed by (name)" value={sigName} onChange={(e) => setSigName(e.target.value)} data-testid="complete-sig-name" />
              <input className={inputCls} placeholder="Role" value={sigRole} onChange={(e) => setSigRole(e.target.value)} data-testid="complete-sig-role" />
            </div>
            <SignaturePad onChange={setSigData} />
            <button className="text-xs text-slate-500 mt-2" onClick={() => setSigUnavailable(true)} data-testid="complete-sig-unavailable">Signature unavailable?</button>
          </>
        ) : (
          <>
            <input className={inputCls} placeholder="Reason signature unavailable" value={sigReason} onChange={(e) => setSigReason(e.target.value)} data-testid="complete-sig-reason" />
            <button className="text-xs text-slate-500 mt-2" onClick={() => setSigUnavailable(false)}>Capture a signature instead</button>
          </>
        )}
      </div>
      {err && <p className="text-sm text-red-600">{err}</p>}
      <div className="grid grid-cols-1 gap-2">
        <Btn variant="primary" full disabled={saving} onClick={submit} data-testid="complete-submit">{saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />} Complete & generate job sheet</Btn>
        <Btn variant="ghost" full onClick={onCancel}>Back</Btn>
      </div>
    </Card>
  );
}
