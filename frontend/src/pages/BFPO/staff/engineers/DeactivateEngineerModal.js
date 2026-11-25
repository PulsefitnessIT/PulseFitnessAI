import { useState } from 'react';
import { X } from 'lucide-react';
import { bfpo } from '../../bfpoApi';
import { Btn, inputCls } from '../../ui';

const ACTIONS = [['reassign', 'Reassign to another engineer'], ['unassign', 'Return to the unassigned queue'], ['keep', 'Keep with management']];

export default function DeactivateEngineerModal({ engineer, jobs, engineers, onClose, onDone }) {
  const [dec, setDec] = useState(() => Object.fromEntries(jobs.map((j) => [j.id, { action: 'unassign', engineer_id: '', reason: '' }])));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const others = engineers.filter((e) => e.id !== engineer.id && e.is_active !== false && e.bfpo_role !== 'staff');
  const set = (id, patch) => setDec((d) => ({ ...d, [id]: { ...d[id], ...patch } }));
  const ready = jobs.every((j) => dec[j.id].reason.trim() && (dec[j.id].action !== 'reassign' || dec[j.id].engineer_id));
  const submit = async () => {
    setBusy(true); setErr('');
    try {
      await bfpo.post(`/staff/engineers/${engineer.id}/status`, { active: false, job_decisions: jobs.map((j) => ({ case_id: j.id, ...dec[j.id] })) });
      onDone();
    } catch (e) {
      const d = e?.response?.data?.detail;
      setErr(typeof d === 'string' ? d : d?.message || 'Could not deactivate');
    } finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 z-[60] bg-black/40 flex items-center justify-center p-4" data-testid="deactivate-modal" onMouseDown={onClose}>
      <div className="bg-white rounded-2xl w-full max-w-2xl p-6 max-h-[90vh] overflow-y-auto" onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-lg font-bold text-slate-900">Deactivate {engineer.full_name}</h2>
          <button onClick={onClose} aria-label="Close" className="p-1 text-slate-400 hover:text-slate-600"><X className="w-5 h-5" /></button>
        </div>
        <p className="text-sm text-slate-600 mb-4">{jobs.length} open job(s) are still assigned. Decide what happens to each one — the decision and reason are kept in the job history.</p>
        <div className="space-y-3">
          {jobs.map((j) => (
            <div key={j.id} className="border border-slate-200 rounded-xl p-3 space-y-2" data-testid={`deactivate-job-${j.id}`}>
              <p className="text-sm font-semibold text-slate-900">{j.reference} · {j.title}</p>
              <p className="text-xs text-slate-500">{j.site_name} · {String(j.status).replace(/_/g, ' ')}</p>
              <div className="grid sm:grid-cols-2 gap-2">
                <select className={inputCls} value={dec[j.id].action} aria-label="What happens to this job"
                  onChange={(e) => set(j.id, { action: e.target.value })} data-testid={`deactivate-action-${j.id}`}>
                  {ACTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
                {dec[j.id].action === 'reassign' && (
                  <select className={inputCls} value={dec[j.id].engineer_id} aria-label="New engineer"
                    onChange={(e) => set(j.id, { engineer_id: e.target.value })} data-testid={`deactivate-engineer-${j.id}`}>
                    <option value="">Choose engineer…</option>
                    {others.map((o) => <option key={o.id} value={o.id}>{o.full_name}</option>)}
                  </select>
                )}
              </div>
              <input className={inputCls} placeholder="Reason (required)" value={dec[j.id].reason}
                onChange={(e) => set(j.id, { reason: e.target.value })} data-testid={`deactivate-reason-${j.id}`} />
            </div>
          ))}
        </div>
        {err && <p className="text-sm text-red-600 mt-3" data-testid="deactivate-error">{err}</p>}
        <div className="flex justify-end gap-2 mt-4">
          <Btn onClick={onClose}>Cancel</Btn>
          <Btn variant="primary" disabled={!ready || busy} onClick={submit} data-testid="deactivate-confirm">Deactivate engineer</Btn>
        </div>
      </div>
    </div>
  );
}
