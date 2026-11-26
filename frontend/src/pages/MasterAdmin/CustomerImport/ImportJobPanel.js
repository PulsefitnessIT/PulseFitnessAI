import { useState } from 'react';
import axios from 'axios';
import { CheckCircle2, AlertTriangle, Download, Loader2, RotateCcw, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import ImportRowsTable, { CAT } from './ImportRowsTable';

const API = `${process.env.REACT_APP_BACKEND_URL}/api/master-admin/customer-import`;

const BOX = { zinc: 'bg-zinc-50 border-zinc-200', emerald: 'bg-emerald-50 border-emerald-200', amber: 'bg-amber-50 border-amber-200' };

const Stat = ({ label, value, tone = 'zinc', testId }) => (
  <div className={`rounded-lg border px-3 py-2 ${BOX[tone]}`} data-testid={testId}>
    <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">{label}</p>
    <p className="text-lg font-bold text-zinc-900 tabular-nums">{value}</p>
  </div>
);

const Detection = ({ job }) => {
  const d = job.detection || {};
  const c = d.counts || {};
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-xs" data-testid="ci-detection">
      {[['File', job.filename], ['Detected format', d.format === 'sage_accounts' ? 'Sage Customer Accounts' : 'Sicon Customer Contacts'],
        ['File type', (job.file_type || '').toUpperCase()], ['Worksheet', d.worksheet], ['Header row', d.header_row],
        ['Fields recognised', `${d.fields_recognised} of ${d.fields_total}`], ['Physical rows', d.physical_rows],
        ['Metadata rows', c.metadata], ['Example rows (excluded)', (c.example || 0) + (c.suspected_example || 0)],
        ['Genuine candidate records', (c.genuine || 0) + (c.uncertain || 0)]].map(([k, v]) => (
        <div key={k} className="rounded-md bg-zinc-50 border border-zinc-200 px-2.5 py-1.5">
          <p className="text-[10px] text-zinc-500">{k}</p>
          <p className="font-semibold text-zinc-800 truncate" title={String(v ?? '')}>{v ?? '—'}</p>
        </div>
      ))}
      {d.unrecognised_fields?.length > 0 && (
        <p className="col-span-full text-amber-700">Unrecognised columns (ignored): {d.unrecognised_fields.join(', ')}</p>
      )}
      {d.excluded_fields?.length > 0 && (
        <p className="col-span-full text-zinc-500">Not stored: {d.excluded_fields.join(', ')}</p>
      )}
      {d.requires_range_confirmation && (
        <p className="col-span-full text-amber-700 font-medium" data-testid="ci-range-warning">
          Some rows look like template samples or sit after the example block. They are excluded unless you tick Include for each one.
        </p>
      )}
    </div>
  );
};

export default function ImportJobPanel({ job, setJob, headers, onDone }) {
  const [busy, setBusy] = useState('');
  const [err, setErr] = useState('');
  const s = job.summary || {};
  const p = job.preview || {};
  const call = async (path, label) => {
    setBusy(label); setErr('');
    try {
      const { data } = await axios.post(`${API}/jobs/${job.id}/${path}`, {}, { headers });
      setJob(data);
      if (path === 'commit') poll();
    } catch (e) { setErr(e.response?.data?.detail || e.message); } finally { setBusy(''); }
  };
  const poll = async () => {
    for (;;) {
      await new Promise((r) => setTimeout(r, 1500));
      const { data } = await axios.get(`${API}/jobs/${job.id}`, { headers });
      setJob(data);
      if (data.status !== 'committing') { onDone?.(); return; }
    }
  };
  const download = async () => {
    const r = await axios.get(`${API}/jobs/${job.id}/report.csv`, { headers, responseType: 'blob' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(r.data); a.download = `import-reconciliation-${job.id.slice(0, 8)}.csv`; a.click();
  };
  const rollback = async () => {
    if (!window.confirm('Undo this import? Organisations it created that nobody has access to are removed, and values it overwrote are restored.')) return;
    setBusy('rollback');
    try { await axios.post(`${API}/jobs/${job.id}/rollback`, {}, { headers }); const { data } = await axios.get(`${API}/jobs/${job.id}`, { headers }); setJob(data); }
    catch (e) { setErr(e.response?.data?.detail || e.message); } finally { setBusy(''); }
  };
  const sage = job.kind === 'sage_accounts';
  const finished = ['completed', 'completed_with_errors', 'interrupted'].includes(job.status);

  return (
    <Card className="p-5 rounded-xl border-zinc-200 space-y-4" data-testid="ci-job-panel">
      <Detection job={job} />
      {job.previously_imported && (
        <p className="text-xs text-sky-700" data-testid="ci-previously-imported">This exact file was imported before — re-importing only adds what is new or changed.</p>
      )}
      <div>
        <p className="text-xs font-semibold text-zinc-700 mb-2 flex items-center gap-1.5"><ShieldCheck size={14} className="text-emerald-600" /> Commercial provisioning summary</p>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          {sage && <Stat label="New LITE organisations" value={s.new_lite_organisations} tone="emerald" testId="ci-sum-new" />}
          {sage && <Stat label="Existing organisations" value={s.existing_organisations} testId="ci-sum-existing" />}
          {sage && <Stat label="Paid customers preserved" value={s.existing_paid_preserved} testId="ci-sum-paid" />}
          {sage && <Stat label="Branches under head office" value={s.branches_merged} testId="ci-sum-branches" />}
          <Stat label="Contacts to create" value={s.contacts_to_create} testId="ci-sum-contacts-new" />
          <Stat label="Contacts to update" value={s.contacts_to_update} testId="ci-sum-contacts-upd" />
          <Stat label="Unresolved / held" value={s.unresolved} tone={s.unresolved ? 'amber' : 'zinc'} testId="ci-sum-unresolved" />
          <Stat label="Paid subscriptions activated" value={0} testId="ci-sum-paid-activated" />
          <Stat label="Login invitations sent" value={0} testId="ci-sum-invites" />
          <Stat label="User accounts created" value={0} testId="ci-sum-users" />
        </div>
        <div className="flex flex-wrap gap-1.5 mt-3">
          {Object.entries(p).map(([k, v]) => (
            <span key={k} className="text-[11px] px-2 py-0.5 rounded-full bg-zinc-100 text-zinc-700">{CAT[k]?.label || k}: <b>{v}</b></span>
          ))}
        </div>
      </div>

      <ImportRowsTable job={job} headers={headers} setJob={setJob} locked={!['analysed', 'approved'].includes(job.status)} />

      {job.status === 'analysing' && <p className="text-xs text-zinc-500 flex items-center gap-1.5" data-testid="ci-analysing"><Loader2 size={12} className="animate-spin" />Checking records against the platform…</p>}
      {job.status === 'analysis_failed' && <p className="text-sm text-red-600" data-testid="ci-analysis-failed">The file could not be checked: {job.error}</p>}
      {err && <p className="text-sm text-red-600 flex items-center gap-1.5" data-testid="ci-error"><AlertTriangle size={14} />{err}</p>}
      <div className="flex flex-wrap items-center gap-2 border-t border-zinc-100 pt-4">
        {job.status === 'analysed' && (
          <Button onClick={() => call('approve', 'approve')} disabled={!!busy || s.blocking > 0} data-testid="ci-approve-btn">
            {busy === 'approve' ? <Loader2 size={14} className="animate-spin mr-1" /> : <CheckCircle2 size={14} className="mr-1" />}
            Approve import
          </Button>
        )}
        {s.blocking > 0 && job.status === 'analysed' && <span className="text-xs text-amber-700" data-testid="ci-blocking-note">{s.blocking} record(s) need a decision first</span>}
        {(job.status === 'approved' || job.status === 'completed_with_errors' || job.status === 'interrupted') && (
          <Button onClick={() => call('commit', 'commit')} disabled={!!busy} data-testid="ci-commit-btn">
            {job.status === 'approved' ? 'Run import' : 'Retry failed records'}
          </Button>
        )}
        {job.status === 'committing' && (
          <span className="text-sm text-zinc-600 flex items-center gap-2" data-testid="ci-progress">
            <Loader2 size={14} className="animate-spin" /> Importing… {job.progress?.done || 0} of {job.progress?.total || '…'}
          </span>
        )}
        {finished && (
          <span className={`text-sm font-medium ${job.status === 'completed' ? 'text-emerald-700' : 'text-amber-700'}`} data-testid="ci-finished">
            {job.status === 'completed' ? 'Import complete' : job.status === 'interrupted' ? 'Import interrupted — retry to continue' : `Finished with ${job.results?.failed || 0} failed record(s)`}
            {sage && job.results ? ` · ${job.results.org_created_lite || 0} new LITE organisations` : ''}
          </span>
        )}
        {job.status === 'rolled_back' && <span className="text-sm text-zinc-500" data-testid="ci-rolled-back">Rolled back</span>}
        <div className="flex-1" />
        <Button variant="outline" size="sm" onClick={download} data-testid="ci-report-btn"><Download size={14} className="mr-1" />Reconciliation report</Button>
        {finished && <Button variant="outline" size="sm" onClick={rollback} disabled={!!busy} data-testid="ci-rollback-btn"><RotateCcw size={14} className="mr-1" />Undo import</Button>}
      </div>
    </Card>
  );
}
