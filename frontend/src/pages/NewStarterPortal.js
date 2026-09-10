/**
 * NewStarterPortal — secure recruit portal (invite → set password → onboarding).
 * Route: /new-starter/:token. Same account becomes the Staff Portal after activation.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import {
  Loader2, Upload, CheckCircle2, FileText, ShieldCheck, PenLine, Send, Circle, Download,
  X, AlertCircle, BookOpen, LogOut, Camera,
} from 'lucide-react';

// Resolve a stored photo_url (relative "/api/..." proxy path or data: URI) to a
// browser-loadable src.
const photoSrc = (u) => (u ? (u.startsWith('/api') ? `${process.env.REACT_APP_BACKEND_URL}${u}` : u) : '');

function StaffPhotoUpload({ H, currentUrl, onUploaded, label = 'Profile photo', hint }) {
  const ref = useRef(null);
  const [busy, setBusy] = useState(false);
  const [url, setUrl] = useState(currentUrl || '');
  const [err, setErr] = useState('');
  useEffect(() => { setUrl(currentUrl || ''); }, [currentUrl]);
  const pick = () => ref.current && ref.current.click();
  const onFile = async (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    setBusy(true); setErr('');
    try {
      const fd = new FormData(); fd.append('file', file);
      const r = await axios.post(`${API}/new-starter/portal/photo`, fd, { headers: { ...H } });
      setUrl(r.data.photo_url); onUploaded && onUploaded(r.data.photo_url);
    } catch (e2) {
      setErr(e2?.response?.data?.detail || 'Could not upload photo.');
    } finally { setBusy(false); if (ref.current) ref.current.value = ''; }
  };
  return (
    <div className="flex items-center gap-4" data-testid="staff-photo-upload">
      <div className="h-20 w-20 rounded-full overflow-hidden bg-slate-100 border border-slate-200 flex items-center justify-center shrink-0">
        {url ? <img src={photoSrc(url)} alt="Headshot" className="h-full w-full object-cover" data-testid="staff-photo-img" />
             : <Camera size={26} className="text-slate-400" />}
      </div>
      <div>
        <div className="text-sm font-semibold text-slate-800">{label}</div>
        {hint && <div className="text-xs text-slate-500 mb-1">{hint}</div>}
        <input ref={ref} type="file" accept="image/*" className="hidden" onChange={onFile} data-testid="staff-photo-input" />
        <button type="button" onClick={pick} disabled={busy} data-testid="staff-photo-btn"
          className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border border-slate-300 text-slate-600 hover:border-cyan-400 disabled:opacity-50">
          {busy ? <Loader2 size={13} className="animate-spin" /> : <Camera size={13} />} {url ? 'Change photo' : 'Add photo'}
        </button>
        {err && <div className="text-xs text-rose-600 mt-1">{err}</div>}
      </div>
    </div>
  );
}

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

async function openPdf(url, headers) {
  const r = await axios.get(url, { headers, responseType: 'blob' });
  const blobUrl = URL.createObjectURL(new Blob([r.data], { type: 'application/pdf' }));
  window.open(blobUrl, '_blank');
}
const CORE = '#19CDFF';
const STEP_LABELS = { forms: 'Forms', documents: 'Documents', verification: 'Verification', policies: 'Policies', agreements: 'Agreements', offer: 'Offer', contract: 'Contract', ready_to_start: 'Ready to Start' };

export default function NewStarterPortal({ staffMode = false }) {
  const { token } = useParams();
  const storeKey = staffMode ? 'staff_jwt' : `nsp:${token}`;
  const [jwt, setJwt] = useState(() => sessionStorage.getItem(storeKey) || '');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [me, setMe] = useState(null);
  const [inviteInfo, setInviteInfo] = useState(null);
  const H = jwt ? { Authorization: `Bearer ${jwt}` } : {};
  const logout = () => {
    sessionStorage.removeItem(storeKey); setJwt(''); setMe(null); setPassword('');
    if (staffMode && typeof window !== 'undefined') window.location.href = '/staff-login';
  };

  const fmtErr = (d) => (typeof d === 'string' ? d : Array.isArray(d) ? d.map((e) => e?.msg || '').join(' ') : d?.msg || 'Something went wrong.');

  const loadMe = useCallback(async (tk) => {
    try {
      const r = await axios.get(`${API}/new-starter/me`, { headers: { Authorization: `Bearer ${tk}` } });
      setMe(r.data);
    } catch (e) { setErr('Could not load your portal. Please sign in again.'); setJwt(''); sessionStorage.removeItem(storeKey); }
  }, [storeKey]);

  useEffect(() => { if (jwt) loadMe(jwt); }, [jwt, loadMe]);
  useEffect(() => {
    if (staffMode) { if (!jwt && typeof window !== 'undefined') window.location.href = '/staff-login'; return; }
    if (!jwt) axios.get(`${API}/new-starter/invite/${token}`).then((r) => setInviteInfo(r.data)).catch(() => setInviteInfo({ found: false }));
  }, [jwt, token, staffMode]);

  const returning = !!inviteInfo?.accepted;

  const acceptInvite = async () => {
    setBusy(true); setErr('');
    try {
      const url = returning ? 'login' : 'accept-invite';
      const r = await axios.post(`${API}/new-starter/${url}`, { token, password });
      sessionStorage.setItem(storeKey, r.data.token);
      setJwt(r.data.token);
    } catch (e) { setErr(fmtErr(e?.response?.data?.detail) || 'Invalid or expired invitation'); }
    finally { setBusy(false); }
  };

  if (!jwt) {
    if (staffMode) return null; // redirecting to /staff-login
    return (
      <Shell>
        <div className="max-w-md mx-auto mt-16 rounded-2xl bg-white shadow-xl p-8 border border-slate-200" data-testid="nsp-signin">
          <h1 className="text-2xl font-bold text-slate-900">{returning ? `Welcome back${inviteInfo?.full_name ? ', ' + inviteInfo.full_name.split(' ')[0] : ''}` : 'Welcome to Pulse Fitness'}</h1>
          <p className="text-slate-500 mt-1 text-sm">{returning ? 'Enter your password to get back into your portal.' : 'Set a password to access your New Starter Portal and complete your onboarding.'}</p>
          <label className="block mt-5 text-sm font-medium text-slate-700">{returning ? 'Your password' : 'Create a password'}</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} data-testid="nsp-password"
            onKeyDown={(e) => { if (e.key === 'Enter' && password.length >= 8) acceptInvite(); }}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5" placeholder={returning ? 'Enter your password' : 'At least 12 characters'} />
          {err && <div className="text-red-500 text-sm mt-2" data-testid="nsp-error">{err}</div>}
          <button onClick={acceptInvite} disabled={busy || password.length < 8} data-testid="nsp-signin-btn"
            className="mt-4 w-full rounded-lg py-2.5 font-semibold text-slate-900 disabled:opacity-40" style={{ background: CORE }}>
            {busy ? (returning ? 'Logging in…' : 'Setting up…') : (returning ? 'Log in' : 'Enter my portal')}
          </button>
        </div>
      </Shell>
    );
  }

  if (!me) return <Shell><div className="flex justify-center mt-24"><Loader2 className="animate-spin text-cyan-500" size={32} /></div></Shell>;

  return (
    <Shell>
      <div className="max-w-4xl mx-auto py-8 px-4" data-testid="nsp-portal">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">{me.portal_name}</h1>
            <p className="text-slate-500 text-sm">Hello {me.person?.full_name} — {me.employment?.job_title || me.employment?.position || 'welcome aboard'}.</p>
          </div>
          <div className="flex items-center gap-2">
            {me.activated && <span className="px-3 py-1 rounded-full bg-emerald-100 text-emerald-700 text-sm font-semibold">Active employee ✓</span>}
            <button onClick={logout} data-testid="nsp-logout"
              className="inline-flex items-center gap-1.5 text-sm font-semibold px-3 py-1.5 rounded-lg border border-slate-300 text-slate-600 hover:border-slate-400">
              <LogOut size={14} /> Log out</button>
          </div>
        </div>

        {/* progress checklist (click a step to jump to it) */}
        {(() => {
          const DONE = ['submitted', 'verified', 'accepted', 'fully_signed', 'complete'];
          const TARGET = { forms: 'forms', documents: 'documents', policies: 'policies', agreements: 'agreements', offer: 'offer', contract: 'contract' };
          const doneCount = me.steps.filter((s) => DONE.includes(me.progress[s])).length;
          const jump = (s) => { const el = document.getElementById('sec-' + TARGET[s]); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); };
          return (
            <div className="mt-5" data-testid="nsp-checklist">
              <div className="text-xs font-semibold text-slate-500 mb-2">Your checklist — {doneCount} of {me.steps.length} complete</div>
              <div className="flex flex-wrap gap-2" data-testid="nsp-progress">
                {me.steps.map((s) => {
                  const v = me.progress[s];
                  const done = DONE.includes(v);
                  const clickable = !!TARGET[s];
                  return (
                    <button key={s} onClick={() => clickable && jump(s)} disabled={!clickable} data-testid={`nsp-step-${s}`}
                      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition ${clickable ? 'cursor-pointer hover:ring-2 hover:ring-cyan-300' : 'cursor-default'} ${done ? 'bg-emerald-50 text-emerald-700' : v && v !== 'not_started' ? 'bg-cyan-50 text-cyan-700' : 'bg-slate-100 text-slate-500'}`}>
                      {done ? <CheckCircle2 size={13} /> : <Circle size={13} />} {STEP_LABELS[s]}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })()}

        <div className="mt-6 space-y-5">
          <YourDetails H={H} me={me} reload={() => loadMe(jwt)} />
          <Documents H={H} me={me} reload={() => loadMe(jwt)} />
          <Policies H={H} me={me} reload={() => loadMe(jwt)} />
          <Agreements H={H} me={me} reload={() => loadMe(jwt)} />
          <SubmitPack H={H} me={me} reload={() => loadMe(jwt)} />
          {me.offer && <OfferCard H={H} me={me} reload={() => loadMe(jwt)} />}
          {me.contract && <ContractCard H={H} me={me} reload={() => loadMe(jwt)} />}
        </div>
      </div>
    </Shell>
  );
}

function Section({ title, icon: Icon, children, testId, secId }) {
  return (
    <div id={secId ? `sec-${secId}` : undefined} className="rounded-2xl bg-white border border-slate-200 shadow-sm p-5 scroll-mt-4" data-testid={testId}>
      <div className="flex items-center gap-2 mb-3"><Icon size={18} className="text-cyan-600" />
        <h2 className="font-bold text-slate-900">{title}</h2></div>
      {children}
    </div>
  );
}

function YourDetails({ H, me, reload }) {
  const saved = me.forms?.new_starter?.data || {};
  const [f, setF] = useState({ dob: saved.dob || '', ni_number: saved.ni_number || '', emergency_contact_name: saved.emergency_contact_name || '', emergency_contact_phone: saved.emergency_contact_phone || '', bank_account: saved.bank_account || '', home_address: saved.home_address || '' });
  const [busy, setBusy] = useState(false); const [ok, setOk] = useState(false);
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e.target.value }));
  const save = async () => { setBusy(true); try { await axios.put(`${API}/new-starter/forms`, { form_key: 'new_starter', data: f }, { headers: H }); setOk(true); reload(); } finally { setBusy(false); } };
  return (
    <Section title="Your Details, Emergency Contact & Payroll" icon={FileText} testId="nsp-details" secId="forms">
      <div className="mb-4 pb-4 border-b border-slate-100">
        <StaffPhotoUpload H={H} currentUrl={me.person?.photo_url}
          hint="A clear headshot so your manager can put a face to your name." />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <PortalField label="Home address" k="home_address" value={f.home_address} onChange={set('home_address')} />
        <PortalField label="Date of birth" k="dob" type="date" value={f.dob} onChange={set('dob')} />
        <PortalField label="National Insurance number" k="ni_number" value={f.ni_number} onChange={set('ni_number')} />
        <PortalField label="Emergency contact name" k="emergency_contact_name" value={f.emergency_contact_name} onChange={set('emergency_contact_name')} />
        <PortalField label="Emergency contact phone" k="emergency_contact_phone" value={f.emergency_contact_phone} onChange={set('emergency_contact_phone')} />
        <PortalField label="Bank account (masked)" k="bank_account" value={f.bank_account} onChange={set('bank_account')} />
      </div>
      <button onClick={save} disabled={busy} data-testid="nsp-save-details"
        className="mt-3 rounded-lg px-4 py-2 text-sm font-semibold text-slate-900" style={{ background: CORE }}>
        {busy ? 'Saving…' : ok ? 'Saved ✓' : 'Save my details'}
      </button>
    </Section>
  );
}

function PortalField({ label, k, value, onChange, type = 'text' }) {
  return (
    <label className="block"><span className="text-xs text-slate-500">{label}</span>
      <input type={type} value={value} onChange={onChange} data-testid={`nsp-field-${k}`}
        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" /></label>
  );
}

function Documents({ H, me, reload }) {
  const [busy, setBusy] = useState(false);
  const upload = async (e, type) => {
    const file = e.target.files?.[0]; if (!file) return;
    setBusy(true);
    const fd = new FormData(); fd.append('file', file); fd.append('document_type', type);
    try { await axios.post(`${API}/new-starter/upload`, fd, { headers: { ...H } }); reload(); } finally { setBusy(false); }
  };
  const TYPES = [['passport', 'Passport / ID'], ['proof_of_address', 'Proof of address'], ['right_to_work', 'Right to Work'], ['driving_licence', 'Driving Licence'], ['qualification', 'Qualification']];
  return (
    <Section title="Identity & Proof-of-Address Documents" icon={Upload} testId="nsp-documents" secId="documents">
      <p className="text-xs text-slate-500 mb-2">Upload a clear photo or scan of each document. A driving licence is optional unless your role requires driving.</p>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
        {TYPES.map(([t, label]) => (
          <label key={t} className="cursor-pointer rounded-xl border border-dashed border-slate-300 p-3 text-center hover:border-cyan-400" data-testid={`nsp-upload-${t}`}>
            <Upload size={16} className="mx-auto text-slate-400" />
            <div className="text-xs mt-1 text-slate-600">{label}</div>
            <input type="file" accept="image/*,application/pdf" className="hidden" onChange={(e) => upload(e, t)} />
          </label>
        ))}
      </div>
      {busy && <div className="text-xs text-cyan-600 mt-2">Uploading…</div>}
      {me.documents?.length > 0 && (
        <div className="mt-3 text-sm text-slate-600" data-testid="nsp-doc-list">
          {me.documents.map((d) => <div key={d.id} className="flex items-center gap-2 py-0.5"><CheckCircle2 size={13} className="text-emerald-500" /> {d.original_filename} <span className="text-xs text-slate-400">({d.document_type})</span></div>)}
        </div>
      )}
    </Section>
  );
}

function Policies({ H, me, reload }) {
  const [busy, setBusy] = useState('');
  const [reading, setReading] = useState(null);
  const ack = async (key) => {
    setBusy(key);
    try { await axios.post(`${API}/new-starter/policies/${key}/acknowledge`, { signature_name: me.person?.full_name }, { headers: H }); setReading(null); reload(); }
    finally { setBusy(''); }
  };
  return (
    <Section title="Company Policies" icon={ShieldCheck} testId="nsp-policies" secId="policies">
      <p className="text-xs text-slate-500 mb-2">Open each policy to read it, then acknowledge at the bottom.</p>
      <div className="space-y-2">
        {me.policies.map((p) => {
          const acked = !!me.acknowledgements?.[p.key];
          return (
            <div key={p.key} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 px-3 py-2">
              <div className="text-sm text-slate-700">{p.title}{p.is_sample && <span className="ml-1 text-[10px] text-amber-600">SAMPLE</span>}</div>
              {acked ? <span className="text-emerald-600 text-xs font-semibold">Acknowledged ✓</span>
                : <button onClick={() => setReading(p)} data-testid={`nsp-read-${p.key}`}
                    className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg text-slate-900" style={{ background: CORE }}>
                    <BookOpen size={13} /> Read policy</button>}
            </div>
          );
        })}
      </div>
      {reading && (
        <PortalModal title={reading.title} onClose={() => setReading(null)}>
          <pre className="whitespace-pre-wrap text-sm bg-slate-50 rounded-lg p-4 max-h-[55vh] overflow-auto text-slate-700 border border-slate-200" data-testid="nsp-policy-body">
{reading.body || reading.summary || 'The full policy text will be provided by Pulse Fitness HR.'}
          </pre>
          <div className="mt-4 flex justify-end gap-2">
            <button onClick={() => setReading(null)} className="text-sm font-semibold px-4 py-2 rounded-lg border border-slate-300 text-slate-600">Close</button>
            <button onClick={() => ack(reading.key)} disabled={busy === reading.key} data-testid={`nsp-ack-${reading.key}`}
              className="text-sm font-semibold px-4 py-2 rounded-lg text-slate-900 disabled:opacity-50" style={{ background: CORE }}>
              {busy === reading.key ? 'Saving…' : 'I have read & acknowledge'}</button>
          </div>
        </PortalModal>
      )}
    </Section>
  );
}

function PortalModal({ title, onClose, children }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow; document.body.style.overflow = 'hidden';
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev; };
  }, [onClose]);
  return createPortal(
    <div className="fixed inset-0 z-[300] bg-black/60 flex items-start justify-center p-4 overflow-y-auto"
      data-testid="nsp-modal" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="w-full max-w-2xl bg-white rounded-2xl shadow-xl my-8 max-h-[calc(100vh-4rem)] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200 sticky top-0 bg-white z-10">
          <h3 className="font-bold text-slate-900">{title}</h3>
          <button onClick={onClose} data-testid="portal-modal-close"><X size={18} className="text-slate-500" /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>,
    document.body,
  );
}

function Agreements({ H, me, reload }) {
  const [busy, setBusy] = useState('');
  const sign = async (key) => { setBusy(key); try { await axios.post(`${API}/new-starter/agreements/${key}/sign`, { signature_name: me.person?.full_name, acknowledge: true }, { headers: H }); reload(); } finally { setBusy(''); } };
  return (
    <Section title="Agreements — Electronic Signature" icon={PenLine} testId="nsp-agreements" secId="agreements">
      <div className="space-y-2">
        {me.agreements.map((a) => {
          const signed = me.agreement_state?.[a.key]?.status === 'signed';
          const sigFields = a.signature_fields || [];
          return (
            <div key={a.key} className="rounded-lg border border-slate-200 px-3 py-2">
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm text-slate-700">{a.title}{a.is_sample && <span className="ml-1 text-[10px] text-amber-600">SAMPLE</span>}</div>
                {signed ? <span className="text-emerald-600 text-xs font-semibold">Signed ✓</span>
                  : <button onClick={() => sign(a.key)} disabled={busy === a.key} data-testid={`nsp-sign-${a.key}`}
                      className="text-xs font-semibold px-3 py-1.5 rounded-lg text-slate-900" style={{ background: CORE }}>
                      {busy === a.key ? '…' : 'Sign'}</button>}
              </div>
              {sigFields.length > 0 && !signed && (
                <div className="mt-1.5 text-[11px] text-slate-500" data-testid={`nsp-sigfields-${a.key}`}>
                  Signature points detected: {sigFields.map((f) => f.label).join(', ')}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Section>
  );
}

function SubmitPack({ H, me, reload }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const details = me.forms?.new_starter?.data || {};
  const detailsOk = !!(details.home_address && details.dob && details.ni_number);
  const reqPolicies = (me.policies || []).filter((p) => p.acknowledgement_required !== false);
  const policiesOk = reqPolicies.length === 0 || reqPolicies.every((p) => me.acknowledgements?.[p.key]);
  const agreementsOk = (me.agreements || []).every((a) => me.agreement_state?.[a.key]?.status === 'signed');
  const docsOk = (me.documents || []).length > 0;

  // Required (block submit) vs recommended (warn but allow — you can return later)
  const checklist = [
    { label: 'Your details, emergency contact & payroll', ok: detailsOk, required: true },
    { label: 'Company policies acknowledged', ok: policiesOk, required: true },
    { label: 'Agreements signed', ok: agreementsOk, required: true },
    { label: 'Identity & proof-of-address documents', ok: docsOk, required: false },
  ];
  const blocking = checklist.filter((c) => c.required && !c.ok);
  const recommendedMissing = checklist.filter((c) => !c.required && !c.ok);
  const submitted = !!me.submitted;

  const submit = async () => {
    setBusy(true); setErr('');
    try { await axios.post(`${API}/new-starter/submit`, {}, { headers: H }); reload(); }
    catch (e) { setErr(e?.response?.data?.detail || 'Could not submit — please try again.'); }
    finally { setBusy(false); }
  };

  return (
    <Section title="Review & Submit" icon={Send} testId="nsp-submit">
      {submitted ? (
        <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-4" data-testid="nsp-submitted-banner">
          <div className="flex items-center gap-2 text-emerald-700 font-semibold"><CheckCircle2 size={18} /> Pack submitted to Pulse Fitness HR ✓</div>
          <p className="text-sm text-emerald-700/80 mt-1">Thank you — HR will now review your pack. You can still return here any time to upload outstanding documents.</p>
        </div>
      ) : (
        <>
          <p className="text-sm text-slate-500 mb-3">Submit your pack to Pulse Fitness HR for review. Required items must be complete; documents can be uploaded now or after you submit.</p>
          <div className="space-y-1.5 mb-3" data-testid="nsp-submit-checklist">
            {checklist.map((c) => (
              <div key={c.label} className={`flex items-center gap-2 text-sm rounded-lg px-3 py-2 ${c.ok ? 'text-emerald-700 bg-emerald-50' : c.required ? 'text-red-600 bg-red-50' : 'text-amber-700 bg-amber-50'}`}>
                {c.ok ? <CheckCircle2 size={15} /> : <AlertCircle size={15} />}
                <span>{c.label}</span>
                {!c.ok && <span className="ml-auto text-xs font-semibold">{c.required ? 'Required — outstanding' : 'Recommended — you can return later'}</span>}
              </div>
            ))}
          </div>
          {blocking.length > 0 && (
            <div className="text-sm text-red-600 mb-2" data-testid="nsp-submit-reason">
              You can’t submit yet — please complete: {blocking.map((b) => b.label).join(', ')}.
            </div>
          )}
          {blocking.length === 0 && recommendedMissing.length > 0 && (
            <div className="text-xs text-amber-700 mb-2" data-testid="nsp-submit-warn">
              You can submit now and return later to upload: {recommendedMissing.map((b) => b.label).join(', ')}.
            </div>
          )}
          {err && <div className="text-sm text-red-500 mb-2" data-testid="nsp-submit-error">{err}</div>}
          <button onClick={submit} disabled={busy || blocking.length > 0} data-testid="nsp-submit-btn"
            className="rounded-lg px-4 py-2 text-sm font-semibold text-slate-900 disabled:opacity-40" style={{ background: CORE }}>
            {busy ? 'Submitting…' : 'Submit my onboarding pack'}
          </button>
        </>
      )}
    </Section>
  );
}

function OfferCard({ H, me, reload }) {
  const offer = me.offer; const [name, setName] = useState(me.person?.full_name || ''); const [busy, setBusy] = useState('');
  const respond = async (action) => {
    setBusy(action);
    try { await axios.post(`${API}/new-starter/offer/respond`, { action, signature_name: name }, { headers: H }); reload(); }
    finally { setBusy(''); }
  };
  return (
    <Section title="Your Offer Letter" icon={FileText} testId="nsp-offer" secId="offer">
      <div className="flex justify-end mb-2">
        <button onClick={() => openPdf(`${API}/new-starter/offer.pdf`, H)} data-testid="nsp-offer-pdf"
          className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-slate-300 text-slate-600 hover:border-cyan-400">
          <Download size={13} /> Download PDF</button>
      </div>
      <pre className="whitespace-pre-wrap text-xs bg-slate-50 rounded-lg p-3 max-h-60 overflow-auto text-slate-700" data-testid="nsp-offer-text">{offer.rendered}</pre>
      {offer.status === 'issued' ? (
        <div className="mt-3 space-y-2">
          <input value={name} onChange={(e) => setName(e.target.value)} data-testid="nsp-offer-signature"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" placeholder="Type your legal name to accept" />
          <div className="flex gap-2">
            <button onClick={() => respond('accept')} disabled={busy || !name} data-testid="nsp-accept-offer"
              className="rounded-lg px-4 py-2 text-sm font-semibold text-slate-900" style={{ background: CORE }}>{busy === 'accept' ? '…' : 'Accept offer'}</button>
            <button onClick={() => respond('decline')} disabled={busy} data-testid="nsp-decline-offer"
              className="rounded-lg px-4 py-2 text-sm font-semibold border border-slate-300 text-slate-600">Decline</button>
          </div>
        </div>
      ) : <div className="mt-2 text-sm font-semibold text-emerald-600">Offer {offer.status} ✓</div>}
    </Section>
  );
}

function ContractCard({ H, me, reload }) {
  const con = me.contract; const [name, setName] = useState(me.person?.full_name || ''); const [ackd, setAckd] = useState(false); const [busy, setBusy] = useState(false);
  const sign = async () => { setBusy(true); try { await axios.post(`${API}/new-starter/contract/sign`, { signature_name: name, signature_method: 'typed', acknowledge: true }, { headers: H }); reload(); } finally { setBusy(false); } };
  return (
    <Section title="Your Employment Contract" icon={FileSignatureIcon} testId="nsp-contract" secId="contract">
      <div className="flex justify-end mb-2">
        <button onClick={() => openPdf(`${API}/new-starter/contract.pdf`, H)} data-testid="nsp-contract-pdf"
          className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-slate-300 text-slate-600 hover:border-cyan-400">
          <Download size={13} /> Download PDF</button>
      </div>
      <pre className="whitespace-pre-wrap text-xs bg-slate-50 rounded-lg p-3 max-h-60 overflow-auto text-slate-700" data-testid="nsp-contract-text">{con.rendered}</pre>
      {con.status === 'issued' ? (
        <div className="mt-3 space-y-2">
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input type="checkbox" checked={ackd} onChange={(e) => setAckd(e.target.checked)} data-testid="nsp-contract-ack" />
            I have read the contract and understand the schedules form part of it.
          </label>
          <input value={name} onChange={(e) => setName(e.target.value)} data-testid="nsp-contract-signature"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" placeholder="Type your legal name to sign" />
          <button onClick={sign} disabled={busy || !ackd || !name} data-testid="nsp-sign-contract"
            className="rounded-lg px-4 py-2 text-sm font-semibold text-slate-900 disabled:opacity-40" style={{ background: CORE }}>
            {busy ? 'Signing…' : 'Sign contract'}</button>
        </div>
      ) : <div className="mt-2 text-sm font-semibold text-emerald-600">Contract {con.status.replace(/_/g, ' ')} ✓</div>}
    </Section>
  );
}
function FileSignatureIcon(props) { return <PenLine {...props} />; }

function Shell({ children }) {
  return (
    <div className="min-h-screen bg-slate-50">
      <div className="bg-white border-b border-slate-200">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center gap-2">
          <img src="/brand/pulse-logo-dark.svg" alt="Pulse Fitness" className="h-6" onError={(e) => { e.target.style.display = 'none'; }} />
          <span className="font-bold text-slate-800">Pulse Fitness</span>
        </div>
      </div>
      {children}
    </div>
  );
}
