/**
 * PartnerComplianceCard.js (iter 216h283)
 *
 * Gym-entry compliance docs panel for the engineer dashboard.
 * Lists each doc kind (DBS, Right to Work, Safeguarding, Public
 * Liability) with status, upload button, AI check result and an
 * inline expiry date.
 *
 * Status traffic-lights:
 *   • Missing     — no file uploaded yet (grey)
 *   • Uploaded    — file present, AI says it looks legit, admin
 *                   hasn't signed off yet (amber)
 *   • Verified    — admin signed off (green)
 *   • Rejected    — admin marked the doc not-OK (rose)
 *   • Expired     — verified previously but expiry date is past (rose)
 */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { Upload, CheckCircle2, AlertTriangle, Clock, ShieldCheck, FileCheck2, Loader2, Wrench, ArrowRight } from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL;

const KIND_META = {
  dbs:              { label: 'DBS Disclosure', help: 'Basic, Standard, Enhanced or Enhanced + Barred List' },
  rtw:              { label: 'Right to Work', help: 'Passport, BRP or share code from gov.uk' },
  safeguarding:     { label: 'Safeguarding',  help: 'NSPCC or equivalent — refreshed every 3 years' },
  public_liability: { label: 'Public Liability', help: 'General/public liability insurance — recommended minimum cover' },
  // Iter 220p1 — US compliance equivalents.
  work_authorization: { label: 'Work Authorization', help: 'Form I-9, US passport, Green Card, EAD or visa' },
  background_check:   { label: 'Background Check', help: 'Criminal background screening (e.g. Checkr) — refreshed periodically' },
};

const DBS_LEVELS = [
  { value: '',                 label: 'Select level…' },
  { value: 'basic',            label: 'Basic' },
  { value: 'standard',         label: 'Standard' },
  { value: 'enhanced',         label: 'Enhanced' },
  { value: 'enhanced_barred',  label: 'Enhanced + Barred List' },
];

const RTW_TYPES = [
  { value: '',                  label: 'Select doc…' },
  { value: 'passport_uk',       label: 'UK passport' },
  { value: 'passport_eu',       label: 'EU passport' },
  { value: 'passport_other',    label: 'Other passport' },
  { value: 'brp',               label: 'Biometric residence permit' },
  { value: 'share_code_settled',label: 'Settled-status share code' },
  { value: 'share_code_other',  label: 'Other share code' },
  { value: 'birth_cert',        label: 'UK birth certificate' },
  { value: 'naturalisation_cert', label: 'Naturalisation certificate' },
];

function statusFor(blob) {
  if (!blob) return { code: 'missing', label: 'Missing', tone: 'bg-zinc-200 text-zinc-700', Icon: Upload };
  if (blob.expires_at && new Date(blob.expires_at) < new Date()) {
    return { code: 'expired', label: 'Expired', tone: 'bg-rose-100 text-rose-800', Icon: AlertTriangle };
  }
  if (blob.verified_at) return { code: 'verified', label: 'Verified', tone: 'bg-emerald-100 text-emerald-800', Icon: CheckCircle2 };
  if (blob.rejection_note) return { code: 'rejected', label: 'Needs attention', tone: 'bg-rose-100 text-rose-800', Icon: AlertTriangle };
  if (blob.file) return { code: 'pending', label: 'Under review', tone: 'bg-amber-100 text-amber-800', Icon: Clock };
  return { code: 'missing', label: 'Missing', tone: 'bg-zinc-200 text-zinc-700', Icon: Upload };
}

function ConfidenceBadge({ ai }) {
  if (!ai || ai.status === 'skipped' || ai.status === 'unsupported') return null;
  const pct = Math.round((ai.confidence || 0) * 100);
  const tone = pct >= 70 ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
             : pct >= 40 ? 'bg-amber-50 text-amber-700 border-amber-200'
             :             'bg-rose-50 text-rose-700 border-rose-200';
  return (
    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border ${tone}`} title={ai.notes || ''} data-testid="compliance-ai-confidence">
      AI {pct}%
    </span>
  );
}

function DocRow({ kind, blob, onUpload }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [fields, setFields] = useState({});
  const [file, setFile] = useState(null);
  const meta = KIND_META[kind];
  const status = statusFor(blob);
  const StatusIcon = status.Icon;

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await onUpload(kind, fields, file);
      setOpen(false); setFile(null); setFields({});
    } finally { setBusy(false); }
  };

  return (
    <div className="rounded-lg border border-zinc-200 bg-white" data-testid={`compliance-row-${kind}`}>
      <div className="flex items-center gap-3 px-3 py-2.5">
        <FileCheck2 size={18} className="text-zinc-400 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-bold text-zinc-900">{meta.label}</p>
            <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded inline-flex items-center gap-1 ${status.tone}`} data-testid={`compliance-status-${kind}`}>
              <StatusIcon size={10} />{status.label}
            </span>
            <ConfidenceBadge ai={blob?.ai_check} />
          </div>
          <p className="text-[11px] text-zinc-500 truncate">
            {meta.help}
            {blob?.expires_at && <> · expires {new Date(blob.expires_at).toLocaleDateString('en-GB')}</>}
            {blob?.file?.original_filename && <> · {blob.file.original_filename}</>}
          </p>
          {blob?.rejection_note && (
            <p className="mt-1 text-[11px] text-rose-700 italic">Reviewer note: "{blob.rejection_note}"</p>
          )}
        </div>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="px-2.5 py-1.5 text-[11px] font-bold border border-zinc-200 rounded hover:bg-zinc-50 inline-flex items-center gap-1"
          data-testid={`compliance-edit-${kind}`}
        >
          {blob?.file ? 'Update' : 'Upload'}
        </button>
      </div>
      {open && (
        <form onSubmit={submit} className="border-t border-zinc-100 px-3 py-3 space-y-2 bg-zinc-50/40" data-testid={`compliance-form-${kind}`}>
          {kind === 'dbs' && (
            <>
              <div className="grid grid-cols-2 gap-2">
                <select className="border border-zinc-200 rounded px-2 py-1.5 text-sm bg-white" value={fields.dbs_check_level || ''} onChange={(e) => setFields((f) => ({ ...f, dbs_check_level: e.target.value }))} data-testid="dbs-level">
                  {DBS_LEVELS.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
                </select>
                <input type="date" className="border border-zinc-200 rounded px-2 py-1.5 text-sm bg-white" placeholder="Check date" value={fields.dbs_check_date || ''} onChange={(e) => setFields((f) => ({ ...f, dbs_check_date: e.target.value }))} data-testid="dbs-check-date" />
              </div>
              <input className="w-full border border-zinc-200 rounded px-2 py-1.5 text-sm bg-white" placeholder="DBS certificate number" value={fields.dbs_certificate_number || ''} onChange={(e) => setFields((f) => ({ ...f, dbs_certificate_number: e.target.value }))} data-testid="dbs-cert-number" />
              <input className="w-full border border-zinc-200 rounded px-2 py-1.5 text-sm bg-white" placeholder="DBS Update Service number (optional — speeds up verification)" value={fields.dbs_update_service_number || ''} onChange={(e) => setFields((f) => ({ ...f, dbs_update_service_number: e.target.value }))} data-testid="dbs-update-service" />
            </>
          )}
          {kind === 'rtw' && (
            <>
              <select className="border border-zinc-200 rounded px-2 py-1.5 text-sm bg-white w-full" value={fields.rtw_document_type || ''} onChange={(e) => setFields((f) => ({ ...f, rtw_document_type: e.target.value }))} data-testid="rtw-doc-type">
                {RTW_TYPES.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
              </select>
              <input className="w-full border border-zinc-200 rounded px-2 py-1.5 text-sm bg-white" placeholder="Share code (if applicable)" value={fields.rtw_share_code || ''} onChange={(e) => setFields((f) => ({ ...f, rtw_share_code: e.target.value }))} data-testid="rtw-share-code" />
            </>
          )}
          {kind === 'safeguarding' && (
            <div className="grid grid-cols-2 gap-2">
              <input className="border border-zinc-200 rounded px-2 py-1.5 text-sm bg-white" placeholder="Issuer (e.g. NSPCC)" value={fields.safeguarding_issuer || ''} onChange={(e) => setFields((f) => ({ ...f, safeguarding_issuer: e.target.value }))} data-testid="sg-issuer" />
              <input type="date" className="border border-zinc-200 rounded px-2 py-1.5 text-sm bg-white" value={fields.safeguarding_completed_at || ''} onChange={(e) => setFields((f) => ({ ...f, safeguarding_completed_at: e.target.value }))} data-testid="sg-completed" />
            </div>
          )}
          {kind === 'public_liability' && (
            <>
              <div className="grid grid-cols-2 gap-2">
                <input className="border border-zinc-200 rounded px-2 py-1.5 text-sm bg-white" placeholder="Provider (e.g. Hiscox)" value={fields.pl_provider || ''} onChange={(e) => setFields((f) => ({ ...f, pl_provider: e.target.value }))} data-testid="pl-provider" />
                <input type="number" className="border border-zinc-200 rounded px-2 py-1.5 text-sm bg-white" placeholder="Cover £ (e.g. 5000000)" value={fields.pl_cover_amount || ''} onChange={(e) => setFields((f) => ({ ...f, pl_cover_amount: e.target.value }))} data-testid="pl-cover" />
              </div>
              <input className="w-full border border-zinc-200 rounded px-2 py-1.5 text-sm bg-white" placeholder="Policy number" value={fields.pl_policy_number || ''} onChange={(e) => setFields((f) => ({ ...f, pl_policy_number: e.target.value }))} data-testid="pl-policy" />
            </>
          )}
          {kind === 'work_authorization' && (
            <>
              <select className="border border-zinc-200 rounded px-2 py-1.5 text-sm bg-white w-full" value={fields.wa_document_type || ''} onChange={(e) => setFields((f) => ({ ...f, wa_document_type: e.target.value }))} data-testid="wa-doc-type">
                <option value="">Document type…</option>
                <option value="i9">Form I-9</option>
                <option value="us_passport">US Passport</option>
                <option value="green_card">Green Card (Permanent Resident)</option>
                <option value="ead">Employment Authorization (EAD)</option>
                <option value="ssn_card">Social Security Card</option>
                <option value="drivers_license">Driver's License (+ SSN)</option>
                <option value="visa">Work Visa</option>
              </select>
              <input className="w-full border border-zinc-200 rounded px-2 py-1.5 text-sm bg-white" placeholder="Document / reference number (optional)" value={fields.wa_reference || ''} onChange={(e) => setFields((f) => ({ ...f, wa_reference: e.target.value }))} data-testid="wa-reference" />
            </>
          )}
          {kind === 'background_check' && (
            <>
              <div className="grid grid-cols-2 gap-2">
                <input className="border border-zinc-200 rounded px-2 py-1.5 text-sm bg-white" placeholder="Provider (e.g. Checkr)" value={fields.bg_provider || ''} onChange={(e) => setFields((f) => ({ ...f, bg_provider: e.target.value }))} data-testid="bg-provider" />
                <input type="date" className="border border-zinc-200 rounded px-2 py-1.5 text-sm bg-white" placeholder="Completed" value={fields.bg_completed_at || ''} onChange={(e) => setFields((f) => ({ ...f, bg_completed_at: e.target.value }))} data-testid="bg-completed" />
              </div>
              <input className="w-full border border-zinc-200 rounded px-2 py-1.5 text-sm bg-white" placeholder="Reference number (optional)" value={fields.bg_reference || ''} onChange={(e) => setFields((f) => ({ ...f, bg_reference: e.target.value }))} data-testid="bg-reference" />
            </>
          )}
          <div className="grid grid-cols-2 gap-2">
            <input type="date" className="border border-zinc-200 rounded px-2 py-1.5 text-sm bg-white" placeholder="Expires" value={fields.expires_at || ''} onChange={(e) => setFields((f) => ({ ...f, expires_at: e.target.value }))} data-testid={`compliance-expires-${kind}`} />
            <input type="file" accept=".pdf,.png,.jpg,.jpeg" className="text-xs" onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid={`compliance-file-${kind}`} />
          </div>
          <div className="flex items-center justify-between gap-2">
            <p className="text-[10px] text-zinc-500">Files run an AI check on upload — but a human always signs off before you're listed as verified.</p>
            <div className="flex items-center gap-2">
              <button type="button" onClick={() => { setOpen(false); setFields({}); setFile(null); }} className="px-2.5 py-1.5 text-xs font-semibold text-zinc-700 hover:bg-zinc-100 rounded" data-testid={`compliance-cancel-${kind}`}>Cancel</button>
              <button type="submit" disabled={busy} className="px-3 py-1.5 text-xs font-bold text-white rounded inline-flex items-center gap-1.5 disabled:opacity-50" style={{ background: '#0891b2' }} data-testid={`compliance-save-${kind}`}>
                {busy ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />}
                {busy ? 'Uploading…' : 'Save'}
              </button>
            </div>
          </div>
        </form>
      )}
    </div>
  );
}

export default function PartnerComplianceCard() {
  const [data, setData] = useState({ compliance_docs: {}, status: { verified_count: 0, total: 4, complete: false, blocked: false }, grace: { active: false, days_left: 0, until: null } });
  const [loading, setLoading] = useState(true);
  const headers = { Authorization: `Bearer ${localStorage.getItem('token')}` };

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/api/partners/me/compliance-docs`, { headers });
      setData(r.data);
    } catch { /* partner may not exist yet — silent */ }
    setLoading(false);
  };
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const upload = async (kind, fields, file) => {
    const fd = new FormData();
    Object.entries(fields).forEach(([k, v]) => { if (v) fd.append(k, v); });
    if (file) fd.append('file', file);
    try {
      const r = await axios.put(
        `${API}/api/partners/me/compliance-docs/${kind}`,
        fd,
        { headers: { ...headers, 'Content-Type': 'multipart/form-data' } },
      );
      setData(r.data);
      notify.success(`${KIND_META[kind].label} updated`);
    } catch (e) {
      notify.error(e?.response?.data?.detail || `Failed to save ${KIND_META[kind].label}`);
      throw e;
    }
  };

  const { status, compliance_docs: docs, grace } = data;
  // Iter 220p1 — claim-unlock docs are market-specific (UK: DBS/RTW;
  // US: Work Authorization/Background Check).
  const claimKinds = data.claim_doc_kinds?.length ? data.claim_doc_kinds : ['dbs', 'rtw'];
  const claimLabels = claimKinds.map((k) => KIND_META[k]?.label || k).join(' or ');
  const verifiedColor = status.complete ? 'text-emerald-700' : status.verified_count > 0 ? 'text-amber-700' : 'text-zinc-500';

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 space-y-3" data-testid="partner-compliance-card">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <ShieldCheck size={16} className="text-zinc-500" />
          <h3 className="text-sm font-bold text-zinc-900">Gym-entry compliance</h3>
        </div>
        <p className={`text-xs font-bold ${verifiedColor}`} data-testid="compliance-summary">
          {status.verified_count}/{status.total} verified
          {grace?.active && <span className="ml-2 text-cyan-700">· {grace.days_left}d left to upload</span>}
          {!grace?.active && status.blocked && <span className="ml-2 text-rose-700">· action needed (expired doc)</span>}
        </p>
      </div>

      {/* Iter 220ea·47 — trial grace banner: engineers can work right away;
          the deadline nudges them to upload DBS / RTW before grace lapses. */}
      {grace?.active ? (
        <div className="rounded-lg border border-cyan-200 bg-cyan-50 p-3 flex items-start gap-2" data-testid="compliance-grace-banner">
          <Clock size={14} className="text-cyan-600 mt-0.5 shrink-0" />
          <div className="text-[12px] text-cyan-900 leading-relaxed">
            <span className="font-bold">You can start taking jobs right away.</span>{' '}
            Upload your <strong>{claimLabels}</strong> within{' '}
            <strong>{grace.days_left} day{grace.days_left === 1 ? '' : 's'}</strong>
            {grace.until ? <> (by {new Date(grace.until).toLocaleDateString('en-GB')})</> : null}{' '}
            to keep claiming jobs once your trial ends.
          </div>
        </div>
      ) : (status.verified_count === 0 && !status.blocked) ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 flex items-start gap-2" data-testid="compliance-required-banner">
          <AlertTriangle size={14} className="text-amber-600 mt-0.5 shrink-0" />
          <div className="text-[12px] text-amber-900 leading-relaxed">
            <span className="font-bold">Upload your {claimLabels} to claim new jobs.</span>{' '}
            Just one of those unlocks claiming — you don't need everything to get started.
          </div>
        </div>
      ) : null}

      <p className="text-[11px] text-zinc-500 leading-relaxed">
        Gym operators ask for these docs before letting an engineer on site. Upload each one and we'll run an AI sanity-check; a human reviewer signs off before you're marked verified.
      </p>
      {loading ? (
        <p className="text-xs text-zinc-400 py-4 text-center">Loading…</p>
      ) : (
        <div className="space-y-2">
          {(data.required_kinds && data.required_kinds.length ? data.required_kinds : ['dbs', 'rtw', 'safeguarding', 'public_liability']).map((k) => (
            <DocRow key={k} kind={k} blob={docs[k]} onUpload={upload} />
          ))}
        </div>
      )}

      {/* Always-present way forward — engineers should never feel stranded
          on this card. Takes them straight into the Engineer App. */}
      <Link
        to="/svc/engineer"
        className="mt-1 flex items-center justify-center gap-1.5 w-full px-4 py-2.5 rounded-lg bg-zinc-900 text-white text-sm font-bold hover:bg-zinc-800 transition"
        data-testid="compliance-continue-app"
      >
        <Wrench size={14} /> Continue to Engineer App <ArrowRight size={14} />
      </Link>
      <p className="text-[10px] text-center text-zinc-400">
        You can upload these documents anytime — they won't stop you exploring the app.
      </p>
    </div>
  );
}
