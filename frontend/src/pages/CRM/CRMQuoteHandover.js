import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { CheckCircle2, Circle, ClipboardList, X, Wrench, Sparkles, Lock, RotateCcw } from 'lucide-react';
import { notify } from '@/components/notifications';
import { useAuth } from '@/App';

/* Handover & close panel for a CPQ v2 quote — turn a won deal into linked
   install/service jobs and complete the deal once delivered + invoiced. */
export const QuoteHandoverPanel = ({ quoteId, API, headers, c, isDark }) => {
  const { user } = useAuth();
  const canManage = !!(user && (user.is_master_admin || user.is_pulse_admin
    || ['owner', 'admin', 'manager'].includes((user.role || '').toLowerCase())));
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState('');
  const [jobForm, setJobForm] = useState(null);
  const [forceFor, setForceFor] = useState(false);
  const [forceReason, setForceReason] = useState('');

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/crm/v2/quotes/${quoteId}/handover`, { headers: headers() });
      setData(r.data);
    } catch (e) { console.error(e); }
  }, [API, headers, quoteId]);
  useEffect(() => { load(); }, [load]);

  if (!data) return null;
  const panel = isDark ? 'var(--color-neutral-950)' : 'var(--color-neutral-50)';
  const bd = isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)';
  const comp = data.completion;
  const completed = comp.deal_status === 'completed';
  const JOB_LABEL = { install: 'Install', ppm: 'Service / PPM', repair: 'Repair' };

  const post = async (url, body, key) => {
    setBusy(key);
    try {
      const r = await axios.post(`${API}${url}`, body || {}, { headers: headers() });
      setData(d => ({ ...d, ...r.data, completion: r.data.completion || d.completion, jobs: r.data.jobs || d.jobs }));
      await load();
      return r.data;
    } catch (e) { notify.error(e.response?.data?.detail || 'Action failed'); throw e; }
    finally { setBusy(''); }
  };

  const autoJobs = () => post(`/crm/v2/quotes/${quoteId}/handover/jobs`, { auto: true }, 'auto').then(() => notify.success('Handover jobs created')).catch(() => {});
  const submitJob = () => post(`/crm/v2/quotes/${quoteId}/handover/jobs`, { jobs: [jobForm] }, 'job').then(() => { setJobForm(null); notify.success('Job created'); }).catch(() => {});
  const complete = (force) => post(`/crm/v2/quotes/${quoteId}/complete`, force ? { force: true, reason: forceReason } : {}, 'complete')
    .then(() => { setForceFor(false); setForceReason(''); notify.success('Deal completed'); }).catch(() => {});
  const reopen = () => post(`/crm/v2/quotes/${quoteId}/reopen`, {}, 'reopen').then(() => notify.success('Deal reopened')).catch(() => {});

  const Check = ({ ok, children, testid }) => (
    <div className="flex items-center gap-2 text-sm" style={{ color: ok ? 'var(--color-success-alt)' : c.textMuted }} data-testid={testid}>
      {ok ? <CheckCircle2 size={15} /> : <Circle size={15} />} {children}
    </div>
  );

  return (
    <div className="mt-6 mb-2" data-testid="quote-handover-panel">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold flex items-center gap-1.5" style={{ color: c.text }}>
          <ClipboardList size={15} /> Handover &amp; close
        </h3>
        <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{ background: completed ? 'var(--color-success-alt)22' : `${c.textMuted}22`, color: completed ? 'var(--color-success-alt)' : c.textMuted }} data-testid="deal-status-badge">
          {completed ? 'Completed' : 'Open'}
        </span>
      </div>

      {/* Jobs */}
      <div className="p-3 rounded-lg border mb-3" style={{ background: panel, borderColor: bd }}>
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-medium" style={{ color: c.text }}>Linked jobs</p>
          {canManage && !completed && (
            <div className="flex gap-2">
              <button onClick={autoJobs} disabled={busy === 'auto' || data.suggestions.length === 0} className="text-xs px-2 py-1 rounded border inline-flex items-center gap-1 disabled:opacity-50" style={{ borderColor: bd, color: 'var(--color-info-ios)' }} data-testid="handover-auto-jobs"><Sparkles size={11} /> Auto-create install jobs</button>
              <button onClick={() => setJobForm({ case_type: 'install', title: '', description: '', equipment_id: '' })} className="text-xs px-2 py-1 rounded border" style={{ borderColor: bd, color: c.text }} data-testid="handover-add-job">Add job</button>
            </div>
          )}
        </div>
        {data.jobs.length === 0 ? (
          <p className="text-xs" style={{ color: c.textDim }} data-testid="handover-jobs-empty">No jobs yet. Create install or service jobs so the service team can pick up this deal.</p>
        ) : (
          <div className="space-y-1.5" data-testid="handover-jobs-list">
            {data.jobs.map(j => (
              <div key={j.id} className="flex items-center gap-2 text-sm" style={{ color: c.text }} data-testid={`handover-job-${j.id}`}>
                <Wrench size={13} style={{ color: c.textMuted }} />
                <span className="flex-1 truncate">{j.machine_type}</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: 'var(--color-info-ios)22', color: 'var(--color-info-ios)' }}>{JOB_LABEL[j.case_type] || j.case_type}</span>
                <span className="text-[10px]" style={{ color: c.textDim }}>{j.status}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Customer portal handover */}
      {(() => {
        const cp = data.customer_portal;
        if (!cp) return null;
        return (
          <div className="p-3 rounded-lg border mb-3" style={{ background: panel, borderColor: bd }} data-testid="handover-customer-portal">
            <p className="text-xs font-medium mb-1" style={{ color: c.text }}>Customer register handover</p>
            {!cp.linked ? (
              <p className="text-xs" style={{ color: c.textDim }} data-testid="handover-customer-unlinked">
                {cp.company_name || 'This customer'} isn't linked to a Pulse portal yet, so equipment can't be handed over.
              </p>
            ) : (
              <div className="flex items-center gap-3 flex-wrap">
                <p className="text-xs flex-1" style={{ color: c.textDim }} data-testid="handover-customer-status">
                  {cp.equipment_handed_over}/{cp.equipment_registered} unit(s) pushed to <span style={{ color: c.text }}>{cp.tenant_org_name}</span>'s portal
                </p>
                {canManage && cp.pending_handover > 0 && (
                  <button onClick={() => post(`/crm/v2/quotes/${quoteId}/handover/register`, {}, 'register').then(() => notify.success(`${cp.pending_handover} unit(s) handed to customer`)).catch(() => {})}
                    disabled={busy === 'register'}
                    className="text-xs px-3 py-1.5 rounded-md text-white disabled:opacity-50" style={{ background: 'var(--color-info-ios)' }} data-testid="handover-push-customer">
                    {busy === 'register' ? 'Handing over…' : `Hand over ${cp.pending_handover} unit(s)`}
                  </button>
                )}
                {cp.pending_handover === 0 && cp.equipment_registered > 0 && (
                  <span className="text-[11px]" style={{ color: 'var(--color-success-alt)' }} data-testid="handover-customer-done">All handed over ✓</span>
                )}
              </div>
            )}
          </div>
        );
      })()}

      {/* Completion checklist */}
      <div className="p-3 rounded-lg border" style={{ background: panel, borderColor: bd }}>
        <p className="text-xs font-medium mb-2" style={{ color: c.text }}>Ready to close?</p>
        <div className="space-y-1.5">
          <Check ok={comp.delivered_ok} testid="handover-check-delivered">Delivered — {comp.fulfilment_summary.equipment_created}/{comp.fulfilment_summary.equipment_units_expected} equipment units registered</Check>
          <Check ok={comp.invoiced_ok} testid="handover-check-invoiced">Invoiced in full</Check>
          <div className="flex items-center gap-2 text-sm" style={{ color: c.textMuted }} data-testid="handover-check-jobs">
            <Wrench size={14} /> {comp.open_job_count} open job(s) <span className="text-[11px]" style={{ color: c.textDim }}>· doesn't block close</span>
          </div>
        </div>
        {completed ? (
          <div className="mt-3 flex items-center justify-between">
            <p className="text-xs" style={{ color: 'var(--color-success-alt)' }} data-testid="handover-completed-note">Completed by {comp.completed_by || '—'}</p>
            {canManage && <button onClick={reopen} disabled={busy === 'reopen'} className="text-xs px-2 py-1 rounded border inline-flex items-center gap-1" style={{ borderColor: bd, color: c.textMuted }} data-testid="handover-reopen"><RotateCcw size={11} /> Reopen</button>}
          </div>
        ) : canManage && (
          <div className="mt-3 flex items-center gap-2">
            <button onClick={() => complete(false)} disabled={busy === 'complete' || !comp.ready} className="text-xs px-3 py-1.5 rounded-md text-white disabled:opacity-50" style={{ background: 'var(--color-success-alt)' }} data-testid="handover-complete">
              {busy === 'complete' ? 'Completing…' : 'Complete deal'}
            </button>
            {!comp.ready && (
              <button onClick={() => setForceFor(true)} className="text-xs px-2 py-1.5 rounded-md border inline-flex items-center gap-1" style={{ borderColor: bd, color: 'var(--color-accent-amber)' }} data-testid="handover-force"><Lock size={11} /> Complete anyway</button>
            )}
          </div>
        )}
        {!completed && !comp.ready && comp.reasons.length > 0 && (
          <ul className="mt-2 text-[11px] space-y-0.5" style={{ color: 'var(--color-accent-amber)' }} data-testid="handover-reasons">
            {comp.reasons.map((r, i) => <li key={i}>• {r}</li>)}
          </ul>
        )}
      </div>

      {/* Add job dialog */}
      {jobForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setJobForm(null)}>
          <div className="w-full max-w-md rounded-xl p-5" style={{ background: isDark ? 'var(--color-ink)' : '#fff' }} onClick={e => e.stopPropagation()} data-testid="handover-job-dialog">
            <div className="flex items-center justify-between mb-3"><h4 className="font-semibold" style={{ color: c.text }}>Add handover job</h4><button onClick={() => setJobForm(null)}><X size={16} style={{ color: c.textMuted }} /></button></div>
            <label className="text-xs" style={{ color: c.textDim }}>Type</label>
            <select value={jobForm.case_type} onChange={e => setJobForm(f => ({ ...f, case_type: e.target.value }))} className="w-full mt-1 mb-2 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${bd}`, color: c.text }} data-testid="handover-job-type">
              <option value="install">Install &amp; commission</option>
              <option value="ppm">Service / PPM</option>
              <option value="repair">Repair / follow-up</option>
            </select>
            <label className="text-xs" style={{ color: c.textDim }}>Title</label>
            <input value={jobForm.title} onChange={e => setJobForm(f => ({ ...f, title: e.target.value }))} className="w-full mt-1 mb-2 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${bd}`, color: c.text }} data-testid="handover-job-title" />
            {data.suggestions.some(s => s.equipment_id) && (
              <>
                <label className="text-xs" style={{ color: c.textDim }}>Equipment (optional)</label>
                <select value={jobForm.equipment_id} onChange={e => setJobForm(f => ({ ...f, equipment_id: e.target.value }))} className="w-full mt-1 mb-2 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${bd}`, color: c.text }} data-testid="handover-job-equipment">
                  <option value="">— none —</option>
                  {data.suggestions.filter(s => s.equipment_id).map(s => <option key={s.equipment_id} value={s.equipment_id}>{s.title.replace('Install & commission — ', '')}</option>)}
                </select>
              </>
            )}
            <div className="flex gap-2 justify-end mt-3">
              <button onClick={() => setJobForm(null)} className="px-3 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={submitJob} disabled={busy === 'job' || !jobForm.title.trim()} className="px-3 py-2 text-sm rounded-md bg-[var(--color-info-ios)] text-white disabled:opacity-50" data-testid="handover-job-submit">Create job</button>
            </div>
          </div>
        </div>
      )}

      {/* Force complete dialog */}
      {forceFor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setForceFor(false)}>
          <div className="w-full max-w-sm rounded-xl p-5" style={{ background: isDark ? 'var(--color-ink)' : '#fff' }} onClick={e => e.stopPropagation()} data-testid="handover-force-dialog">
            <h4 className="font-semibold mb-2" style={{ color: c.text }}>Complete anyway?</h4>
            <p className="text-xs mb-3" style={{ color: c.textMuted }}>This deal isn't fully delivered/invoiced. Add a reason for the audit trail.</p>
            <input value={forceReason} onChange={e => setForceReason(e.target.value)} placeholder="Reason" className="w-full px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${bd}`, color: c.text }} data-testid="handover-force-reason" />
            <div className="flex gap-2 justify-end mt-4">
              <button onClick={() => setForceFor(false)} className="px-3 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={() => complete(true)} disabled={busy === 'complete' || !forceReason.trim()} className="px-3 py-2 text-sm rounded-md text-white disabled:opacity-50" style={{ background: 'var(--color-accent-amber)' }} data-testid="handover-force-submit">Force complete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default QuoteHandoverPanel;
