import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { ShieldAlert, FileText, Download, Loader2, ChevronDown, ChevronUp, RefreshCw, CheckCircle2 } from 'lucide-react';
import { useAuth } from '@/App';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const SEV_LABELS = {
  none: 'No injury', first_aid: 'First aid only', medical: 'Medical attention',
  hospitalised: 'Hospitalised', life_changing: 'Life-changing', fatal: 'Fatal',
};
const CAT_LABELS = {
  slip: 'Slip', trip: 'Trip', impact: 'Impact', electric: 'Electric shock',
  cardiac: 'Cardiac event', equipment: 'Equipment-related', other: 'Other',
};
const SEV_TONE = {
  fatal: 'bg-red-500/15 text-red-500 border-red-500/40',
  life_changing: 'bg-red-500/15 text-red-500 border-red-500/40',
  hospitalised: 'bg-orange-500/15 text-orange-500 border-orange-500/40',
  medical: 'bg-amber-500/15 text-amber-600 border-amber-500/40',
  first_aid: 'bg-emerald-500/15 text-emerald-600 border-emerald-500/40',
  none: 'bg-zinc-500/15 text-zinc-500 border-zinc-500/30',
};

function Row({ label, value }) {
  if (!value) return null;
  return (
    <div>
      <div className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{label}</div>
      <div className="text-sm mt-0.5 whitespace-pre-wrap" style={{ color: 'var(--theme-text)' }}>{value}</div>
    </div>
  );
}

export default function MODIncidentRegister() {
  const { API, user } = useAuth();
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openId, setOpenId] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [closingId, setClosingId] = useState(null);
  const [cf, setCf] = useState({ root_cause: '', contributing_factors: '', corrective_action: '', riddor_submission_ref: '' });
  const canClose = ['owner', 'manager', 'master_admin'].includes(user?.role);

  const headers = { Authorization: `Bearer ${localStorage.getItem('token') || ''}` };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/mod/site/incidents`, { headers });
      setIncidents(data.incidents || []);
    } catch (e) {
      notifyApiError(notify, e, 'Failed to load incidents');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [API]);

  useEffect(() => { load(); }, [load]);

  const openPdf = async (inc) => {
    setBusyId(inc.id + ':pdf');
    try {
      const res = await axios.get(`${API}/mod/site/incidents/${inc.id}/pdf`, { headers, responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      window.open(url, '_blank');
    } catch (e) {
      notifyApiError(notify, e, 'Could not open PDF');
    } finally { setBusyId(null); }
  };

  const saveToDocs = async (inc) => {
    setBusyId(inc.id + ':save');
    try {
      await axios.post(`${API}/mod/site/incidents/${inc.id}/save-to-documents`, {}, { headers });
      notify.success('Saved to Documents', `${inc.incident_ref} filed under Documents › Incidents.`);
    } catch (e) {
      notifyApiError(notify, e, 'Could not save to Documents');
    } finally { setBusyId(null); }
  };

  const openCloseForm = (inc) => {
    setClosingId(inc.id);
    setCf({ root_cause: '', contributing_factors: '', corrective_action: '', riddor_submission_ref: '' });
  };

  const submitClosure = async (inc) => {
    if (cf.root_cause.trim().length < 20) return notify.error('Root cause too short', 'Please give at least 20 characters.');
    if (cf.contributing_factors.trim().length < 10) return notify.error('Contributing factors too short', 'Please give at least 10 characters.');
    if (cf.corrective_action.trim().length < 20) return notify.error('Corrective action too short', 'Please give at least 20 characters.');
    setBusyId(inc.id + ':close');
    try {
      await axios.post(`${API}/mod/site/incidents/${inc.id}/closure`, cf, { headers });
      notify.success('Incident closed', `${inc.incident_ref} closed and re-filed to Documents.`);
      setClosingId(null);
      await load();
    } catch (e) {
      notifyApiError(notify, e, 'Could not close incident');
    } finally { setBusyId(null); }
  };

  return (
    <div className="space-y-3" data-testid="mod-incident-register">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold flex items-center gap-2" style={{ color: 'var(--theme-text)' }}>
            <ShieldAlert size={16} className="text-red-500" /> Incident Register
          </h3>
          <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
            Every personal incident logged at this site — retained and auto-filed to Documents.
          </p>
        </div>
        <button onClick={load} className="p-2 rounded-lg border hover:bg-black/5" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid="incident-register-refresh">
          <RefreshCw size={14} />
        </button>
      </div>

      {loading ? (
        <div className="py-10 text-center"><Loader2 className="animate-spin mx-auto text-[var(--color-brand-cyan)]" /></div>
      ) : incidents.length === 0 ? (
        <div className="rounded-xl border p-8 text-center" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="incident-register-empty">
          <ShieldAlert size={32} className="mx-auto mb-2" style={{ color: 'var(--theme-text-muted)' }} />
          <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>No incidents logged yet.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {incidents.map((inc) => {
            const isOpen = openId === inc.id;
            return (
              <div key={inc.id} className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid={`incident-row-${inc.id}`}>
                <button
                  type="button"
                  onClick={() => setOpenId(isOpen ? null : inc.id)}
                  className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-black/[0.03]"
                  data-testid={`incident-row-toggle-${inc.id}`}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-xs font-bold" style={{ color: 'var(--theme-text)' }}>{inc.incident_ref}</span>
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${SEV_TONE[inc.injury_severity] || SEV_TONE.none}`}>
                        {SEV_LABELS[inc.injury_severity] || inc.injury_severity}
                      </span>
                      {inc.riddor_reportable && (
                        <span className="text-[10px] font-extrabold px-1.5 py-0.5 rounded border border-red-500/40 bg-red-500/15 text-red-500" data-testid={`incident-riddor-${inc.id}`}>RIDDOR</span>
                      )}
                      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>
                        {(inc.status || 'open').toUpperCase()}
                      </span>
                    </div>
                    <div className="text-xs mt-1 truncate" style={{ color: 'var(--theme-text-muted)' }}>
                      {CAT_LABELS[inc.category] || inc.category} · {inc.injured_party_name} · {inc.occurred_at ? new Date(inc.occurred_at).toLocaleDateString('en-GB') : '—'}
                    </div>
                  </div>
                  {isOpen ? <ChevronUp size={16} style={{ color: 'var(--theme-text-muted)' }} /> : <ChevronDown size={16} style={{ color: 'var(--theme-text-muted)' }} />}
                </button>
                {isOpen && (
                  <div className="px-4 pb-4 pt-1 space-y-3 border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`incident-detail-${inc.id}`}>
                    <div className="grid grid-cols-2 gap-3">
                      <Row label="Category" value={CAT_LABELS[inc.category] || inc.category} />
                      <Row label="Injury severity" value={SEV_LABELS[inc.injury_severity] || inc.injury_severity} />
                      <Row label="Injured party" value={inc.injured_party_name} />
                      <Row label="Party type" value={(inc.injured_party_type || '').replace(/^\w/, c => c.toUpperCase())} />
                    </div>
                    <Row label="Description" value={inc.description} />
                    <div className="grid grid-cols-2 gap-3">
                      <Row label="Reporter" value={inc.reporter_name} />
                      <Row label="Reporter email" value={inc.reporter_email} />
                    </div>
                    {inc.closure_questionnaire && (
                      <div className="rounded-lg border p-3 space-y-2" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface-2)' }}>
                        <div className="text-[10px] font-extrabold uppercase tracking-wider text-emerald-500">Closed / investigated</div>
                        <Row label="Root cause" value={inc.closure_questionnaire.root_cause} />
                        <Row label="Contributing factors" value={inc.closure_questionnaire.contributing_factors} />
                        <Row label="Corrective action" value={inc.closure_questionnaire.corrective_action} />
                        <Row label="RIDDOR submission ref" value={inc.closure_questionnaire.riddor_submission_ref} />
                      </div>
                    )}

                    {inc.status !== 'closed' && canClose && closingId === inc.id && (
                      <div className="rounded-lg border p-3 space-y-3" style={{ borderColor: 'var(--color-brand-cyan)', background: 'var(--theme-surface-2)' }} data-testid={`incident-close-form-${inc.id}`}>
                        <div className="text-[10px] font-extrabold uppercase tracking-wider text-[var(--color-brand-cyan)]">Close incident — post-incident review</div>
                        {[
                          { k: 'root_cause', label: 'Root cause *', min: 20, rows: 2, ph: 'What was the underlying cause? (min 20 chars)' },
                          { k: 'contributing_factors', label: 'Contributing factors *', min: 10, rows: 2, ph: 'Environment, equipment, human factors… (min 10 chars)' },
                          { k: 'corrective_action', label: 'Corrective action *', min: 20, rows: 2, ph: 'What has / will be done to prevent recurrence? (min 20 chars)' },
                        ].map(({ k, label, ph, rows }) => (
                          <div key={k}>
                            <label className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{label}</label>
                            <textarea
                              rows={rows}
                              value={cf[k]}
                              onChange={(e) => setCf({ ...cf, [k]: e.target.value })}
                              placeholder={ph}
                              className="mt-1 w-full rounded-lg border px-3 py-2 text-sm"
                              style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                              data-testid={`incident-close-${k}-${inc.id}`}
                            />
                          </div>
                        ))}
                        <div>
                          <label className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>RIDDOR submission ref (if applicable)</label>
                          <input
                            value={cf.riddor_submission_ref}
                            onChange={(e) => setCf({ ...cf, riddor_submission_ref: e.target.value })}
                            placeholder="HSE reference…"
                            className="mt-1 w-full rounded-lg border px-3 py-2 text-sm"
                            style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                            data-testid={`incident-close-riddor-${inc.id}`}
                          />
                        </div>
                        <div className="flex gap-2 justify-end">
                          <button onClick={() => setClosingId(null)} className="px-3 py-2 rounded-lg text-xs font-bold border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid={`incident-close-cancel-${inc.id}`}>Cancel</button>
                          <button onClick={() => submitClosure(inc)} disabled={busyId === inc.id + ':close'} className="px-3 py-2 rounded-lg text-xs font-extrabold bg-emerald-600 text-white flex items-center gap-1.5 disabled:opacity-50" data-testid={`incident-close-submit-${inc.id}`}>
                            {busyId === inc.id + ':close' ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />} Close incident
                          </button>
                        </div>
                      </div>
                    )}

                    <div className="flex flex-wrap gap-2 pt-1">
                      {inc.status !== 'closed' && canClose && closingId !== inc.id && (
                        <button
                          onClick={() => openCloseForm(inc)}
                          className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-extrabold bg-emerald-600/15 text-emerald-500 border border-emerald-600/40 hover:bg-emerald-600/25"
                          data-testid={`incident-open-close-${inc.id}`}
                        >
                          <CheckCircle2 size={13} /> Close incident
                        </button>
                      )}
                      <button
                        onClick={() => openPdf(inc)}
                        disabled={busyId === inc.id + ':pdf'}
                        className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-bold hover:bg-black/5 disabled:opacity-50"
                        style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                        data-testid={`incident-view-pdf-${inc.id}`}
                      >
                        {busyId === inc.id + ':pdf' ? <Loader2 size={13} className="animate-spin" /> : <FileText size={13} />} View PDF
                      </button>
                      <button
                        onClick={() => saveToDocs(inc)}
                        disabled={busyId === inc.id + ':save'}
                        className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-extrabold bg-[var(--color-brand-cyan)] text-[#04121a] disabled:opacity-50"
                        data-testid={`incident-save-docs-${inc.id}`}
                      >
                        {busyId === inc.id + ':save' ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />} Save to Documents
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
