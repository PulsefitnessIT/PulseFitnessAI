/**
 * Iter 220e5 — Engineer App entitlement panel + feedback composer.
 *
 * Mobile-first read-only panel that consumes the CRM → Contracts
 * entitlement endpoint (no duplicated data — the contract record
 * lives only in CRM). Engineer sees plain-English yes/no badges
 * (Covered / Not covered / Chargeable) for the items that drive
 * billability decisions in the field: callout, labour, parts,
 * wear & tear, treadmill belts, beds, upholstery.
 *
 * A "Send to coordinator" composer lets the engineer flag asset
 * condition, recommend exclusions, recommend CAPEX replacement, or
 * note upsell opportunities — feeding the CRM Contract Review Queue.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { ShieldCheck, X as XIcon, MessageSquarePlus, Check, ChevronDown } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

const KINDS = [
  { key: 'asset_condition',       label: 'Asset condition note' },
  { key: 'exclusion_recommended', label: 'Recommend excluding asset' },
  { key: 'upgrade_recommended',   label: 'Recommend upgraded cover' },
  { key: 'renewal_review',        label: 'Flag for renewal review' },
  { key: 'repeated_fault',        label: 'Repeated fault' },
  { key: 'capex_replacement',     label: 'CAPEX replacement needed' },
  { key: 'upsell_opportunity',    label: 'Upsell opportunity' },
  { key: 'chargeable_flag',       label: 'Chargeable work flag' },
  { key: 'general_note',          label: 'General note' },
];

function CoveredPill({ covered, label }) {
  return (
    <div
      data-testid={`entitlement-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
      data-covered={covered ? 'yes' : 'no'}
      className="flex items-center justify-between px-2.5 py-1.5 rounded-md border text-[11px]"
      style={{
        borderColor: covered ? 'var(--color-success-alt)40' : 'var(--color-danger)40',
        background:  covered ? 'var(--color-success-alt)10' : 'var(--color-danger)08',
        color:       covered ? 'var(--color-success-alt)'  : 'var(--color-danger)',
      }}>
      <span className="font-medium">{label}</span>
      <span className="text-[10px] font-bold uppercase tracking-wider">
        {covered ? 'Covered' : 'Chargeable'}
      </span>
    </div>
  );
}
CoveredPill.displayName = 'CoveredPill';

export function EngineerEntitlementPanel({ caseId, getAuthHeaders }) {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(true);
  const [composerOpen, setComposerOpen] = useState(false);
  const [kind, setKind] = useState('asset_condition');
  const [body, setBody] = useState('');
  const [severity, setSeverity] = useState('medium');
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    if (!caseId) return;
    axios.get(`${API}/svc/engineer/jobs/${caseId}/contract-entitlement`,
              { headers: getAuthHeaders() })
      .then(r => setData(r.data))
      .catch(() => setData({ active: false, label: 'No cover information', tone: 'red', fields: [] }));
  }, [caseId, getAuthHeaders]);

  const submit = async () => {
    if (!body.trim()) { alert('Add a short note before sending.'); return; }
    setSubmitting(true);
    try {
      await axios.post(`${API}/svc/engineer/jobs/${caseId}/contract-feedback`,
                       { kind, body: body.trim(), severity },
                       { headers: getAuthHeaders() });
      setSubmitted(true);
      setBody('');
      setTimeout(() => { setSubmitted(false); setComposerOpen(false); }, 1800);
    } catch (e) {
      alert(e?.response?.data?.detail || 'Send failed');
    }
    setSubmitting(false);
  };

  if (!data) {
    return (
      <div className="rounded-2xl border p-3 bg-slate-50 text-xs text-slate-500 animate-pulse" data-testid="entitlement-panel-loading">
        Checking contract entitlement…
      </div>
    );
  }

  const cardStyle = data.active
    ? { borderColor: 'var(--color-success-alt)30', background: 'var(--color-success-alt)05' }
    : { borderColor: 'var(--color-danger)30', background: 'var(--color-danger)05' };

  return (
    <div className="rounded-2xl border" data-testid="engineer-entitlement-panel" data-active={data.active ? 'yes' : 'no'} style={cardStyle}>
      <button onClick={() => setOpen(!open)} data-testid="entitlement-toggle"
              className="w-full flex items-center gap-2 px-3 py-2.5 text-left">
        <ShieldCheck size={14} style={{ color: data.active ? 'var(--color-success-alt)' : 'var(--color-danger)' }} />
        <div className="flex-1 min-w-0">
          <p className="text-[12px] font-extrabold leading-tight"
             style={{ color: data.active ? 'var(--color-success-alt)' : 'var(--color-danger)' }}
             data-testid="entitlement-label">
            {data.label}
          </p>
          {data.contract_number && (
            <p className="text-[10px] opacity-70" data-testid="entitlement-contract-number">
              {data.contract_number} · Emergency SLA {data.sla_emergency_hours}h
            </p>
          )}
        </div>
        <ChevronDown size={12} className={`transition-transform ${open ? 'rotate-180' : ''}`} style={{ color: '#94a3b8' }} />
      </button>

      {open && (
        <div className="px-3 pb-3 space-y-2">
          {data.fields?.length > 0 && (
            <div className="grid grid-cols-2 gap-1.5" data-testid="entitlement-fields">
              {data.fields.map(f => (
                <CoveredPill key={f.key} covered={f.covered} label={f.label} />
              ))}
            </div>
          )}

          {(data.exclusions || []).length > 0 && (
            <div className="text-[10px] mt-1" data-testid="entitlement-exclusions">
              <p className="font-bold uppercase tracking-wider opacity-70 mb-0.5">Exclusions</p>
              <p className="opacity-80">{data.exclusions.map(e => e.label).join(' · ')}</p>
            </div>
          )}

          {/* Engineer → CRM feedback composer */}
          <div className="pt-2 border-t" style={{ borderColor: 'rgba(148,163,184,0.2)' }}>
            {!composerOpen ? (
              <button onClick={() => setComposerOpen(true)} data-testid="entitlement-open-feedback-btn"
                      className="w-full py-2 rounded text-[11px] font-semibold flex items-center justify-center gap-1.5"
                      style={{ background: 'var(--color-info-ios)15', color: 'var(--color-info-ios)' }}>
                <MessageSquarePlus size={12} /> Send feedback to coordinator
              </button>
            ) : submitted ? (
              <div className="text-center py-2 text-[11px] font-semibold text-emerald-700"
                   data-testid="entitlement-feedback-confirmation">
                <Check size={14} className="inline mr-1" /> Sent to the contracts coordinator
              </div>
            ) : (
              <div className="space-y-1.5">
                <select value={kind} onChange={e => setKind(e.target.value)}
                        data-testid="entitlement-feedback-kind"
                        className="w-full px-2 py-1.5 rounded border text-[11px]"
                        style={{ borderColor: '#cbd5e1' }}>
                  {KINDS.map(k => <option key={k.key} value={k.key}>{k.label}</option>)}
                </select>
                <select value={severity} onChange={e => setSeverity(e.target.value)}
                        data-testid="entitlement-feedback-severity"
                        className="w-full px-2 py-1.5 rounded border text-[11px]"
                        style={{ borderColor: '#cbd5e1' }}>
                  <option value="low">Low severity</option>
                  <option value="medium">Medium severity</option>
                  <option value="high">High severity</option>
                </select>
                <textarea value={body} onChange={e => setBody(e.target.value)}
                          placeholder="What should the contracts coordinator know?"
                          data-testid="entitlement-feedback-body"
                          rows={3}
                          className="w-full px-2 py-1.5 rounded border text-[11px]"
                          style={{ borderColor: '#cbd5e1' }} />
                <div className="flex gap-1.5">
                  <button onClick={() => setComposerOpen(false)} data-testid="entitlement-cancel-feedback-btn"
                          className="flex-1 py-1.5 rounded text-[11px] font-semibold border" style={{ borderColor: '#cbd5e1', color: '#475569' }}>
                    <XIcon size={11} className="inline mr-0.5" />Cancel
                  </button>
                  <button onClick={submit} disabled={submitting || !body.trim()}
                          data-testid="entitlement-submit-feedback-btn"
                          className="flex-1 py-1.5 rounded text-[11px] font-semibold bg-[var(--color-info-ios)] text-white disabled:opacity-50">
                    {submitting ? 'Sending…' : 'Send'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

EngineerEntitlementPanel.displayName = 'EngineerEntitlementPanel';
export default EngineerEntitlementPanel;
