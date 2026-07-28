/**
 * Master Admin — Dealer & Engineer Onboarding Wizard
 *
 * Provisions Pulse Fitness distribution PARTNERS (dealers + field engineers)
 * who get the Service Desk + Inventory & Distribution modules. Captures as
 * much company/contact detail as possible, then creates the dealer org, an
 * owner, and any engineers (inside the dealer or standalone) — each activated
 * via a self-serve invite link OR a temporary password.
 */
import { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Building2, UserPlus, Plus, Trash2, CheckCircle2, Copy, Loader2,
  Link2, KeyRound, Wrench,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL + '/api';

const emptyEngineer = () => ({
  full_name: '', email: '', phone: '', mode: 'in_dealer',
  region: '', date_of_birth: '', notes: '',
  standalone_company_name: '', send_invite: true, password: '',
});

const Field = ({ label, required, children, hint }) => (
  <label className="block">
    <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
      {label}{required && <span className="text-red-500"> *</span>}
    </span>
    {children}
    {hint && <span className="block text-[11px] text-slate-400 mt-0.5">{hint}</span>}
  </label>
);

const inputCls =
  'mt-1 w-full px-3 py-2 text-sm rounded-lg border border-slate-200 bg-white ' +
  'focus:outline-none focus:ring-2 focus:ring-cyan-500/30 focus:border-cyan-400';

const DealerOnboardingWizard = () => {
  const [form, setForm] = useState({
    company_name: '', trading_name: '', company_number: '', vat_number: '',
    website: '', phone: '', coverage_region: '', notes: '',
    address_line1: '', address_line2: '', address_line3: '',
    city: '', county: '', postcode: '', country: 'United Kingdom',
    primary_contact_name: '', primary_contact_email: '', primary_contact_phone: '',
    owner_send_invite: true, owner_password: '',
  });
  const [engineers, setEngineers] = useState([]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const setEng = (i, k, v) =>
    setEngineers((arr) => arr.map((e, idx) => (idx === i ? { ...e, [k]: v } : e)));
  const addEng = () => setEngineers((arr) => [...arr, emptyEngineer()]);
  const removeEng = (i) => setEngineers((arr) => arr.filter((_, idx) => idx !== i));

  const copy = (txt) => {
    navigator.clipboard?.writeText(txt);
    toast.success('Copied to clipboard');
  };

  const submit = async () => {
    if (!form.company_name.trim()) return toast.error('Dealer company name is required');
    if (!form.primary_contact_name.trim() || !form.primary_contact_email.trim())
      return toast.error('Primary contact name and email are required');
    setBusy(true);
    try {
      const token = localStorage.getItem('token');
      const { data } = await axios.post(
        `${API}/master-admin/onboard-dealer`,
        { ...form, engineers },
        { headers: { Authorization: `Bearer ${token}` }, withCredentials: true },
      );
      setResult(data);
      toast.success(`Dealer "${data.organization?.name}" onboarded`);
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === 'string' ? d : 'Could not onboard dealer');
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    setResult(null);
    setEngineers([]);
    setForm((f) => Object.fromEntries(
      Object.keys(f).map((k) => [k, k === 'country' ? 'United Kingdom'
        : k === 'owner_send_invite' ? true : '']),
    ));
  };

  /* ── Success screen ─────────────────────────────────────────────── */
  if (result) {
    const Cred = ({ label, acc }) => (
      <div className="rounded-lg border border-slate-200 p-3 bg-slate-50">
        <div className="flex items-center justify-between">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-slate-800 truncate">{label}</div>
            <div className="text-[12px] text-slate-500 truncate">{acc.email || acc.full_name}</div>
          </div>
          <span className={`text-[10px] font-bold uppercase px-2 py-1 rounded-full flex items-center gap-1 ${
            acc.mode === 'invite' ? 'bg-cyan-100 text-cyan-700' : 'bg-amber-100 text-amber-700'}`}>
            {acc.mode === 'invite' ? <Link2 size={11} /> : <KeyRound size={11} />}
            {acc.mode === 'invite' ? 'Invite link' : 'Temp password'}
          </span>
        </div>
        {acc.mode === 'invite' ? (
          <div className="mt-2 flex items-center gap-2">
            <input readOnly value={acc.invite_url} className="flex-1 text-[11px] font-mono px-2 py-1.5 rounded border border-slate-200 bg-white truncate" data-testid={`dealer-result-invite-${acc.email}`} />
            <button onClick={() => copy(acc.invite_url)} className="p-1.5 rounded border border-slate-200 hover:bg-white" title="Copy link"><Copy size={13} /></button>
          </div>
        ) : (
          <div className="mt-2 flex items-center gap-2">
            <code className="flex-1 text-[12px] font-mono px-2 py-1.5 rounded border border-slate-200 bg-white" data-testid={`dealer-result-password-${acc.email}`}>{acc.temporary_password}</code>
            <button onClick={() => copy(acc.temporary_password)} className="p-1.5 rounded border border-slate-200 hover:bg-white" title="Copy password"><Copy size={13} /></button>
          </div>
        )}
      </div>
    );
    return (
      <div className="max-w-2xl space-y-4" data-testid="dealer-onboard-result">
        <div className="flex items-center gap-2 text-emerald-600">
          <CheckCircle2 size={20} />
          <h3 className="text-base font-bold text-slate-900">Dealer onboarded</h3>
        </div>
        <p className="text-sm text-slate-600">
          <strong>{result.organization?.name}</strong> now has Operations, Service Desk and
          Inventory &amp; Distribution enabled. Share the credentials below.
        </p>
        <div className="space-y-2">
          <Cred label="Owner" acc={result.owner} />
          {(result.engineers || []).map((e) => (
            <Cred key={e.id} label={`Engineer${e.mode === 'standalone' ? ' (standalone)' : ''}`} acc={e} />
          ))}
        </div>
        <button onClick={reset} className="mt-2 px-4 py-2 rounded-lg bg-cyan-500 text-white text-sm font-semibold hover:bg-cyan-600" data-testid="dealer-onboard-another">
          Onboard another dealer
        </button>
      </div>
    );
  }

  /* ── Form ───────────────────────────────────────────────────────── */
  return (
    <div className="max-w-3xl space-y-6" data-testid="dealer-onboard-wizard">
      {/* Company */}
      <section className="rounded-xl border border-slate-200 p-4 space-y-4">
        <div className="flex items-center gap-2 text-slate-800">
          <Building2 size={16} className="text-cyan-500" />
          <h3 className="text-sm font-bold">Dealer company</h3>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Company name" required>
            <input className={inputCls} value={form.company_name} onChange={(e) => set('company_name', e.target.value)} data-testid="dealer-company-name" />
          </Field>
          <Field label="Trading name">
            <input className={inputCls} value={form.trading_name} onChange={(e) => set('trading_name', e.target.value)} data-testid="dealer-trading-name" />
          </Field>
          <Field label="Company number">
            <input className={inputCls} value={form.company_number} onChange={(e) => set('company_number', e.target.value)} data-testid="dealer-company-number" />
          </Field>
          <Field label="VAT number">
            <input className={inputCls} value={form.vat_number} onChange={(e) => set('vat_number', e.target.value)} data-testid="dealer-vat-number" />
          </Field>
          <Field label="Website">
            <input className={inputCls} value={form.website} onChange={(e) => set('website', e.target.value)} placeholder="https://" data-testid="dealer-website" />
          </Field>
          <Field label="Phone">
            <input className={inputCls} value={form.phone} onChange={(e) => set('phone', e.target.value)} data-testid="dealer-phone" />
          </Field>
          <Field label="Coverage region" hint="Territory / area this dealer services">
            <input className={inputCls} value={form.coverage_region} onChange={(e) => set('coverage_region', e.target.value)} placeholder="e.g. South East England" data-testid="dealer-coverage-region" />
          </Field>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Address line 1"><input className={inputCls} value={form.address_line1} onChange={(e) => set('address_line1', e.target.value)} data-testid="dealer-address1" /></Field>
          <Field label="Address line 2"><input className={inputCls} value={form.address_line2} onChange={(e) => set('address_line2', e.target.value)} /></Field>
          <Field label="City"><input className={inputCls} value={form.city} onChange={(e) => set('city', e.target.value)} data-testid="dealer-city" /></Field>
          <Field label="County"><input className={inputCls} value={form.county} onChange={(e) => set('county', e.target.value)} /></Field>
          <Field label="Postcode"><input className={inputCls} value={form.postcode} onChange={(e) => set('postcode', e.target.value)} data-testid="dealer-postcode" /></Field>
          <Field label="Country"><input className={inputCls} value={form.country} onChange={(e) => set('country', e.target.value)} /></Field>
        </div>
        <Field label="Notes">
          <textarea rows={2} className={inputCls} value={form.notes} onChange={(e) => set('notes', e.target.value)} />
        </Field>
      </section>

      {/* Owner */}
      <section className="rounded-xl border border-slate-200 p-4 space-y-4">
        <div className="flex items-center gap-2 text-slate-800">
          <UserPlus size={16} className="text-cyan-500" />
          <h3 className="text-sm font-bold">Primary contact (dealer owner)</h3>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Full name" required><input className={inputCls} value={form.primary_contact_name} onChange={(e) => set('primary_contact_name', e.target.value)} data-testid="dealer-owner-name" /></Field>
          <Field label="Email" required><input className={inputCls} value={form.primary_contact_email} onChange={(e) => set('primary_contact_email', e.target.value)} data-testid="dealer-owner-email" /></Field>
          <Field label="Phone"><input className={inputCls} value={form.primary_contact_phone} onChange={(e) => set('primary_contact_phone', e.target.value)} data-testid="dealer-owner-phone" /></Field>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="radio" checked={form.owner_send_invite} onChange={() => set('owner_send_invite', true)} data-testid="dealer-owner-invite-mode" />
            Send self-serve invite link (72 h)
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="radio" checked={!form.owner_send_invite} onChange={() => set('owner_send_invite', false)} data-testid="dealer-owner-password-mode" />
            Set a temporary password
          </label>
        </div>
        {!form.owner_send_invite && (
          <Field label="Temporary password" hint="Leave blank to auto-generate one">
            <input className={inputCls} value={form.owner_password} onChange={(e) => set('owner_password', e.target.value)} data-testid="dealer-owner-password" />
          </Field>
        )}
      </section>

      {/* Engineers */}
      <section className="rounded-xl border border-slate-200 p-4 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-slate-800">
            <Wrench size={16} className="text-cyan-500" />
            <h3 className="text-sm font-bold">Engineers <span className="text-slate-400 font-normal">(optional)</span></h3>
          </div>
          <button onClick={addEng} className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-cyan-200 text-cyan-700 hover:bg-cyan-50" data-testid="dealer-add-engineer">
            <Plus size={14} /> Add engineer
          </button>
        </div>
        {engineers.length === 0 && (
          <p className="text-[12px] text-slate-400">No engineers added. You can add field engineers now or later.</p>
        )}
        {engineers.map((e, i) => (
          <div key={i} className="rounded-lg border border-slate-200 p-3 space-y-3 bg-slate-50/50" data-testid={`dealer-engineer-row-${i}`}>
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Engineer {i + 1}</span>
              <button onClick={() => removeEng(i)} className="p-1 text-slate-400 hover:text-red-500" data-testid={`dealer-remove-engineer-${i}`}><Trash2 size={14} /></button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Full name" required><input className={inputCls} value={e.full_name} onChange={(ev) => setEng(i, 'full_name', ev.target.value)} data-testid={`dealer-engineer-name-${i}`} /></Field>
              <Field label="Email" required><input className={inputCls} value={e.email} onChange={(ev) => setEng(i, 'email', ev.target.value)} data-testid={`dealer-engineer-email-${i}`} /></Field>
              <Field label="Phone"><input className={inputCls} value={e.phone} onChange={(ev) => setEng(i, 'phone', ev.target.value)} /></Field>
              <Field label="Date of birth"><input type="date" className={inputCls} value={e.date_of_birth} onChange={(ev) => setEng(i, 'date_of_birth', ev.target.value)} /></Field>
              <Field label="Region"><input className={inputCls} value={e.region} onChange={(ev) => setEng(i, 'region', ev.target.value)} /></Field>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Engineer type">
                <select className={inputCls} value={e.mode} onChange={(ev) => setEng(i, 'mode', ev.target.value)} data-testid={`dealer-engineer-mode-${i}`}>
                  <option value="in_dealer">Within this dealer</option>
                  <option value="standalone">Standalone (own entity)</option>
                </select>
              </Field>
              {e.mode === 'standalone' && (
                <Field label="Standalone company name" hint="Defaults to the engineer's name">
                  <input className={inputCls} value={e.standalone_company_name} onChange={(ev) => setEng(i, 'standalone_company_name', ev.target.value)} data-testid={`dealer-engineer-company-${i}`} />
                </Field>
              )}
            </div>
            <div className="flex items-center gap-4 text-sm">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="radio" checked={e.send_invite} onChange={() => setEng(i, 'send_invite', true)} data-testid={`dealer-engineer-invite-${i}`} />
                Invite link
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="radio" checked={!e.send_invite} onChange={() => setEng(i, 'send_invite', false)} />
                Temp password
              </label>
              {!e.send_invite && (
                <input className={`${inputCls} !mt-0 flex-1`} placeholder="Auto-generate if blank" value={e.password} onChange={(ev) => setEng(i, 'password', ev.target.value)} />
              )}
            </div>
            <Field label="Notes"><input className={inputCls} value={e.notes} onChange={(ev) => setEng(i, 'notes', ev.target.value)} /></Field>
          </div>
        ))}
      </section>

      <div className="flex items-center gap-3">
        <button onClick={submit} disabled={busy} className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-cyan-500 text-white text-sm font-bold hover:bg-cyan-600 disabled:opacity-60" data-testid="dealer-onboard-submit">
          {busy ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
          Onboard dealer
        </button>
        <span className="text-[12px] text-slate-400">Creates the dealer org + owner{engineers.length ? ` + ${engineers.length} engineer(s)` : ''}.</span>
      </div>
    </div>
  );
};

export default DealerOnboardingWizard;
