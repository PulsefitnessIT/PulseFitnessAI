/**
 * HeadOfficeOnboardingWizard — iter 215el / refined 215en (Feb 2026)
 *
 * Master Admin onboarding flow for a multi-site customer (e.g. a gym chain
 * with a Head Office + N branches). Creates:
 *   • 1 organisation row (the customer / HQ)
 *   • N site rows (one flagged is_head_office)
 *   • 1 owner user
 *
 * 215en updates:
 *   • Head Office name field is now an autocomplete that searches existing
 *     organisations (by name / company number / VAT / postcode / company
 *     code) so the master admin can pull an existing customer forward
 *     instead of retyping. Picks pre-fill billing address + Co. number +
 *     VAT.
 *   • Address inputs across the whole wizard moved to the new structured
 *     8-field shape (Address 1*, Address 2, Address 3, City, County, Post
 *     code, Country) via the shared `<AddressFields>` component.
 *
 * Sage / Sicon mapping (unchanged):
 *   organisation → SLCustomerAccount / Sicon Customer
 *   site         → SLDeliveryAddress / Sicon SubLocation
 */
import React, { useState } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import InvoiceParseProgress from '@/components/shared/InvoiceParseProgress';
import {
  Building2, MapPin, UserPlus, CheckCircle, ArrowRight, ArrowLeft,
  Loader2, Plus, Trash2, Star, Sparkles, Eye, EyeOff, Download, Upload,
} from 'lucide-react';
import AddressFields, { blankAddress } from '@/components/shared/AddressFields';
import CompanyAutocomplete from '@/components/shared/CompanyAutocomplete';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

// Iter 215em — Tier order grouped by brand: GymAxis on the left column
// (Starter → Professional → Enterprise), Pulse on the right column
// (Lite → Pro). The grid renders 2 columns on md+.
const TIERS = [
  { id: 'starter',      label: 'GymAxis · Starter',      desc: 'CRM + Memberships + basic ops',                brand: 'GymAxis AI' },
  { id: 'lite',         label: 'Pulse · Lite',           desc: 'Equipment + faults + documents',               brand: 'Pulse Fitness' },
  { id: 'professional', label: 'GymAxis · Professional', desc: 'Adds Service Desk + AI triage + Sage outbox',  brand: 'GymAxis AI' },
  { id: 'pro',          label: 'Pulse · Pro',            desc: 'Full Pulse platform with AI + reports',        brand: 'Pulse Fitness' },
  { id: 'enterprise',   label: 'GymAxis · Enterprise',   desc: 'Multi-site, audit, SSO, custom SLA',           brand: 'GymAxis AI' },
];

const STEPS = [
  { id: 'tier',     label: 'Tier' },
  { id: 'org',      label: 'Head Office' },
  { id: 'sites',    label: 'Sites' },
  { id: 'owner',    label: 'Admin' },
  { id: 'review',   label: 'Review' },
];

const blankSite = (isFirst = false) => ({
  // Iter 216e — no auto-HQ. User explicitly picks which site is HQ.
  // Head Office orgs often have HQ = the company registered office (step 1),
  // not a physical gym, so auto-ticking site #1 was wrong.
  name: '', phone: '', email: '',
  default_location: 'Main Floor', is_head_office: false,
  ...blankAddress(),
});

const blankForm = () => ({
  org_name: '',
  company_number: '',
  vat_number: '',
  ...Object.fromEntries(Object.entries(blankAddress()).map(([k, v]) => [`billing_${k}`, v])),
  billing_phone: '',
  sites: [blankSite(true)],
  owner_name: '',
  owner_email: '',
  owner_password: '',
  // Iter 216f — operator picks how to give the admin their first password.
  // 'invite' (default) = send self-serve link; 'set' = type a password now.
  owner_credential_mode: 'invite',
  showPw: false,
});

// HeadOfficeNameAutocomplete extracted to /app/frontend/src/components/shared/CompanyAutocomplete.js (iter 215er)


const HeadOfficeOnboardingWizard = ({ onComplete }) => {
  const [step, setStep] = useState(0);
  const [tier, setTier] = useState('professional');
  const [form, setForm] = useState(blankForm());
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  // Iter 216m — per-site invoice parse progress. Keyed by site index so
  // multiple uploads (one per site) can run independently without
  // their progress bars colliding.
  const [parseProgress, setParseProgress] = useState({});

  const stepId = STEPS[step]?.id;
  const validate = () => {
    if (stepId === 'tier' && !tier) { notify.error('Pick a tier'); return false; }
    if (stepId === 'org' && !form.org_name.trim()) { notify.error('Head Office name is required'); return false; }
    if (stepId === 'sites') {
      if (form.sites.length === 0) { notify.error('At least one site is required'); return false; }
      const blanks = form.sites.findIndex((s) => !s.name.trim());
      if (blanks !== -1) { notify.error(`Site #${blanks + 1} needs a name`); return false; }
      const hqCount = form.sites.filter((s) => s.is_head_office).length;
      if (hqCount > 1) { notify.error('Only one site can be flagged as Head Office'); return false; }
    }
    if (stepId === 'owner') {
      if (!form.owner_name.trim()) { notify.error('Owner name required'); return false; }
      if (!form.owner_email.trim() || !form.owner_email.includes('@')) { notify.error('Valid owner email required'); return false; }
      // Iter 216f — admin password is now OPTIONAL. The operator chooses
      // either: (a) set a password manually, or (b) send an invite link
      // and let the user pick their own. If "set" is selected, the
      // password must still be ≥8 chars.
      if (form.owner_credential_mode === 'set' && (form.owner_password || '').length < 8) {
        notify.error('Password must be at least 8 characters');
        return false;
      }
    }
    return true;
  };
  const next = () => { if (validate()) setStep((s) => Math.min(s + 1, STEPS.length - 1)); };
  const back = () => setStep((s) => Math.max(s - 1, 0));

  // Iter 216h — wizard silent-fail fix. Build the payload once so the
  // initial submit and the duplicate-override retry use IDENTICAL data
  // (the previous retry path referenced fields that don't exist on
  // `form`, so it silently sent nothing). Also fixes notifyApiError
  // call signature: it expects (notify, err, fallback) — passing the
  // error first threw a TypeError inside the catch and swallowed the
  // toast, which is what the operator saw as "button spins then nothing".
  const buildPayload = (allowDuplicate = false) => ({
    tier,
    org_name: form.org_name,
    company_number: form.company_number,
    vat_number: form.vat_number,
    billing_address_line1: form.billing_address_line1,
    billing_address_line2: form.billing_address_line2,
    billing_address_line3: form.billing_address_line3,
    billing_city: form.billing_city,
    billing_county: form.billing_county,
    billing_postcode: form.billing_postcode,
    billing_country: form.billing_country,
    billing_phone: form.billing_phone,
    owner_name: form.owner_name,
    owner_email: form.owner_email,
    owner_password: form.owner_credential_mode === 'set' ? form.owner_password : '',
    send_invite: form.owner_credential_mode === 'invite',
    allow_duplicate: !!allowDuplicate,
    sites: form.sites.map((s) => ({
      name: s.name,
      address_line1: s.address_line1,
      address_line2: s.address_line2,
      address_line3: s.address_line3,
      city: s.city,
      county: s.county,
      postcode: s.postcode,
      country: s.country,
      phone: s.phone, email: s.email,
      default_location: s.default_location,
      is_head_office: !!s.is_head_office,
      equipment: (s.equipment || []).filter((eq) => (eq.name || eq.model || eq.make || eq.serial_number)).map((eq) => ({
        // Iter 216k — preserve every AI-extracted field through to
        // /onboard-head-office (was dropping unit_price + category).
        ...eq,
      })),
    })),
  });

  const submit = async () => {
    if (!validate()) return;
    setSubmitting(true);
    try {
      const r = await axios.post(`${API}/master-admin/onboard-head-office`, buildPayload(false), auth());
      setResult(r.data);
      notify.success('Head Office created', `${r.data?.organization?.name} · ${r.data?.sites?.length || 0} site(s)`);
    } catch (e) {
      // Iter 216d — friendlier 409 (duplicate org). Offer the operator
      // a one-click "Create anyway" that retries with allow_duplicate.
      if (e?.response?.status === 409) {
        const detail = e?.response?.data?.detail || 'An organisation with this name or company number already exists.';
        const proceed = window.confirm(`${detail}\n\nClick OK to create anyway, or Cancel to abort.`);
        if (proceed) {
          try {
            const retry = await axios.post(`${API}/master-admin/onboard-head-office`, buildPayload(true), auth());
            setResult(retry.data);
            notify.success('Head Office created (duplicate override)', `${retry.data?.organization?.name}`);
            return;
          } catch (retryErr) {
            notifyApiError(notify, retryErr, 'Retry failed');
            return;
          }
        }
        notify.info('Onboarding cancelled — open the existing organisation from the list to edit it');
      } else {
        notifyApiError(notify, e, 'Failed to create Head Office');
        // Surface the raw error in the console too so operators screen-
        // sharing with support can copy/paste the stack instead of
        // describing a "silent fail".
         
        console.error('[onboard-head-office] failed', e?.response?.status, e?.response?.data, e);
      }
    } finally { setSubmitting(false); }
  };

  // Pull the picked suggestion into the form. Handles both internal-org
  // picks (existing GymAxis customer) and Companies House picks (UK
  // public-data API). Companies House picks set `company_number` and
  // pre-fill the registered office address; internal picks additionally
  // pull VAT and phone forward.
  const applyOrgPick = (o) => {
    const isCH = o.source === 'companies_house';
    setForm((f) => ({
      ...f,
      org_name: (isCH ? o.company_name : o.name) || f.org_name,
      company_number: o.company_number || f.company_number,
      vat_number: isCH ? f.vat_number : (o.vat_number || f.vat_number),
      billing_address_line1: o.address_line1 || f.billing_address_line1,
      billing_address_line2: o.address_line2 || f.billing_address_line2,
      billing_address_line3: o.address_line3 || f.billing_address_line3,
      billing_city: o.city || f.billing_city,
      billing_county: o.county || f.billing_county,
      billing_postcode: o.postcode || f.billing_postcode,
      billing_country: o.country || f.billing_country,
      billing_phone: isCH ? f.billing_phone : (o.phone || f.billing_phone),
    }));
    notify.success(
      isCH ? 'Pre-filled from Companies House' : 'Pre-filled from existing org',
      isCH ? `${o.company_name} · Co. ${o.company_number}` : o.name,
    );
  };

  // Helpers to read/write the prefixed billing-address slice as a single
  // object that AddressFields understands.
  const billingAddr = {
    address_line1: form.billing_address_line1,
    address_line2: form.billing_address_line2,
    address_line3: form.billing_address_line3,
    city: form.billing_city,
    county: form.billing_county,
    postcode: form.billing_postcode,
    country: form.billing_country,
  };
  const setBillingAddr = (next) => setForm((f) => ({
    ...f,
    billing_address_line1: next.address_line1,
    billing_address_line2: next.address_line2,
    billing_address_line3: next.address_line3,
    billing_city: next.city,
    billing_county: next.county,
    billing_postcode: next.postcode,
    billing_country: next.country,
  }));

  // ── SUCCESS PANEL ─────────────────────────────────────────────
  // Iter 216f — visible "unsaved changes" guard so accidental clicks
  // outside the wizard don't drop everything the operator typed.
  React.useEffect(() => {
    const dirty = form.org_name || form.sites.some((s) => s.name) || form.owner_name || form.owner_email;
    if (!dirty || result) return undefined;
    const handler = (e) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [form, result]);

  if (result) {
    return (
      <Card className="p-8 text-center space-y-4 max-w-2xl mx-auto" data-testid="ho-onboard-success">
        <div className="w-16 h-16 mx-auto rounded-full bg-emerald-50 flex items-center justify-center">
          <CheckCircle size={32} className="text-emerald-600" />
        </div>
        <div>
          <h2 className="text-xl font-bold tracking-tight">Organisation created</h2>
          <p className="text-sm text-zinc-500 mt-1">
            <strong>{result.organization?.name}</strong> · {result.sites?.length || 0} sites · code <code className="bg-zinc-100 px-1.5 py-0.5 rounded text-xs">{result.organization?.company_code}</code>
          </p>
        </div>
        {/* Iter 216f — surface the invite URL right here so the operator
            can copy it before the screen goes anywhere. Backend returns
            `invite_url` when send_invite=true.

            Iter 216k — make it explicit which email this link targets,
            so the operator never sends the link to the wrong inbox. */}
        {result.invite_url && (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-3 text-left max-w-xl mx-auto space-y-2" data-testid="ho-onboard-invite-banner">
            <div className="flex items-start gap-2">
              <UserPlus size={14} className="text-emerald-700 shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <p className="text-[11px] uppercase tracking-wider font-bold text-emerald-700">Password reset link</p>
                <p className="text-[12px] text-emerald-900 mt-0.5">
                  Send this link to <strong className="font-mono">{form.owner_email || result.organization?.primary_contact_email}</strong> — it lets them set their first password (valid 72h).
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 bg-white rounded-md border border-emerald-200 px-2 py-1.5">
              <code className="text-[11px] font-mono text-emerald-900 break-all flex-1">{result.invite_url}</code>
              <Button type="button" size="sm" variant="ghost" className="h-6 px-2 text-[10px] text-emerald-700 hover:bg-emerald-100 shrink-0" data-testid="ho-onboard-invite-copy"
                onClick={async () => { try { await navigator.clipboard.writeText(result.invite_url); notify.success('Reset link copied'); } catch { /* noop */ } }}>
                Copy
              </Button>
              <Button type="button" size="sm" variant="ghost" className="h-6 px-2 text-[10px] text-emerald-700 hover:bg-emerald-100 shrink-0" data-testid="ho-onboard-invite-mailto"
                onClick={() => {
                  const targetEmail = form.owner_email || result.organization?.primary_contact_email || '';
                  const subject = encodeURIComponent(`${result.organization?.name} on GymAxis AI — set your password`);
                  const body = encodeURIComponent(
                    `Hi ${form.owner_name?.split(' ')[0] || ''},\n\n` +
                    `Your account on ${result.organization?.name} is ready. Click the link below to set your password (valid for 72 hours):\n\n` +
                    `${result.invite_url}\n\n` +
                    `If you didn't expect this email please ignore it.\n`,
                  );
                  window.location.href = `mailto:${targetEmail}?subject=${subject}&body=${body}`;
                }}>
                Email
              </Button>
            </div>
          </div>
        )}
        {result.temp_password && (
          <p className="text-sm text-zinc-600">Temp password: <code className="bg-zinc-100 px-2 py-0.5 rounded font-mono">{result.temp_password}</code></p>
        )}
        <ul className="text-left max-w-md mx-auto space-y-2">
          {(result.sites || []).map((s) => (
            <li key={s.id} className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg bg-zinc-50 border border-zinc-200 text-sm">
              <span className="flex items-center gap-2">
                {s.is_head_office ? <Star size={13} className="text-amber-500" /> : <MapPin size={13} className="text-zinc-400" />}
                <span className="font-semibold">{s.name}</span>
                {s.is_head_office ? <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-800 font-bold">HQ</span> : null}
                {s.equipment_count ? <span className="text-[10px] text-zinc-500">· {s.equipment_count} machine(s)</span> : null}
              </span>
              <code className="text-[10px] text-zinc-400">{s.id.slice(0, 8)}…</code>
            </li>
          ))}
        </ul>
        <div className="flex gap-2 justify-center pt-2 flex-wrap">
          <Button onClick={() => { setResult(null); setStep(0); setForm(blankForm()); }} variant="outline" data-testid="ho-onboard-create-another">
            Create another
          </Button>
          {/* Iter 216f — direct link to the org edit drawer so the operator
              can immediately add per-site users without hunting in the list. */}
          <Button onClick={() => onComplete?.(result.organization?.id)} className="bg-emerald-600 text-white hover:bg-emerald-700" data-testid="ho-onboard-edit-org">
            Open Organisation Edit <ArrowRight size={14} className="ml-1.5" />
          </Button>
        </div>
      </Card>
    );
  }

  // ── WIZARD ────────────────────────────────────────────────────
  return (
    <div className="space-y-6" data-testid="ho-onboard-wizard">
      {/* Stepper */}
      <div className="flex items-center justify-between border-b border-zinc-200 pb-4">
        {STEPS.map((s, i) => (
          <div key={s.id} className={`flex items-center gap-2 text-xs font-bold uppercase tracking-wider ${i === step ? 'text-[var(--color-brand-blue)]' : i < step ? 'text-emerald-600' : 'text-zinc-400'}`}>
            <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] ${i === step ? 'bg-[var(--color-brand-blue)] text-white' : i < step ? 'bg-emerald-100' : 'bg-zinc-100'}`}>
              {i < step ? <CheckCircle size={11} /> : i + 1}
            </span>
            <span className="hidden md:inline">{s.label}</span>
          </div>
        ))}
      </div>

      {/* Step bodies */}
      {stepId === 'tier' && (
        <Card className="p-6 space-y-4" data-testid="ho-step-tier">
          <h3 className="text-lg font-bold tracking-tight flex items-center gap-2"><Sparkles size={16} /> Choose tier</h3>
          <p className="text-sm text-zinc-500">Drives module access and the brand the customer's portal renders under.</p>
          <div className="grid md:grid-cols-2 gap-3">
            {TIERS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setTier(t.id)}
                data-testid={`ho-tier-${t.id}`}
                className={`text-left p-4 rounded-xl border-2 transition-all ${tier === t.id ? 'border-[var(--color-brand-blue)] bg-[rgb(var(--rgb-brand-blue)/0.05)] shadow-sm' : 'border-zinc-200 hover:border-zinc-300'}`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-bold text-zinc-900">{t.label}</span>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-400">{t.brand}</span>
                </div>
                <p className="text-xs text-zinc-500 mt-1">{t.desc}</p>
              </button>
            ))}
          </div>
        </Card>
      )}

      {stepId === 'org' && (
        <Card className="p-6 space-y-4" data-testid="ho-step-org">
          <h3 className="text-lg font-bold tracking-tight flex items-center gap-2"><Building2 size={16} /> Head Office details</h3>
          <p className="text-sm text-zinc-500">The corporate entity. Sage will receive this as the SLCustomerAccount; Sicon as the parent Customer record.</p>
          <div>
            <Label className="text-xs text-zinc-500">Head Office Name *</Label>
            <CompanyAutocomplete
              value={form.org_name}
              onChange={(v) => setForm((f) => ({ ...f, org_name: v }))}
              onPick={applyOrgPick}
              testIdPrefix="ho-org-name-autocomplete"
              inputClassName="mt-1"
            />
            <p className="text-[10px] text-zinc-400 mt-1">Start typing to search existing organisations — picking one pre-fills Co. number, VAT and registered address.</p>
          </div>
          <div className="grid md:grid-cols-2 gap-3">
            <div>
              <Label className="text-xs text-zinc-500">Company Number</Label>
              <Input value={form.company_number} onChange={(e) => setForm((f) => ({ ...f, company_number: e.target.value }))} placeholder="08123456" className="mt-1" data-testid="ho-company-number" />
            </div>
            <div>
              <Label className="text-xs text-zinc-500">VAT Number</Label>
              <Input value={form.vat_number} onChange={(e) => setForm((f) => ({ ...f, vat_number: e.target.value }))} placeholder="GB123 4567 89" className="mt-1" data-testid="ho-vat-number" />
            </div>
          </div>

          <div className="pt-2">
            <p className="text-[10px] uppercase tracking-wider font-bold text-zinc-400 mb-2">Registered (billing) address</p>
            <AddressFields
              value={billingAddr}
              onChange={setBillingAddr}
              testIdPrefix="ho-billing"
              required={false}
            />
          </div>

          <div>
            <Label className="text-xs text-zinc-500">Billing Phone</Label>
            <Input value={form.billing_phone} onChange={(e) => setForm((f) => ({ ...f, billing_phone: e.target.value }))} placeholder="020 7123 4567" className="mt-1" data-testid="ho-billing-phone" />
          </div>
        </Card>
      )}

      {stepId === 'sites' && (
        <Card className="p-6 space-y-4" data-testid="ho-step-sites">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div>
              <h3 className="text-lg font-bold tracking-tight flex items-center gap-2"><MapPin size={16} /> Sites under this Head Office</h3>
              <p className="text-sm text-zinc-500">Equipment lives on individual sites. Most Head Offices have 0 machines, but if yours does, just add it as any other site and tick <strong>Head Office</strong> to mark it.<br />You can tick Head Office on any one site — or leave all unticked if the registered office you entered above isn't a physical gym.</p>
            </div>
            <div className="flex items-center gap-1.5 flex-wrap">
              {/* Iter 216d — bulk-import sites from CSV. Mirrors the
                  Sites tab on existing orgs so operators have a single
                  consistent flow whether they're onboarding new or
                  editing existing. */}
              <Button
                onClick={async () => {
                  try {
                    const r = await axios.get(`${API}/master-admin/sites/template.csv`, { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }, responseType: 'blob' });
                    const url = URL.createObjectURL(r.data);
                    const a = document.createElement('a'); a.href = url; a.download = 'gymaxis-sites-template.csv'; a.click();
                    URL.revokeObjectURL(url);
                  } catch (e) { notify.error('Could not download template'); }
                }}
                variant="outline" size="sm" data-testid="ho-sites-csv-template">
                <Download size={14} className="mr-1" /> CSV template
              </Button>
              <label className="inline-flex items-center gap-1 text-xs font-bold px-3 py-2 rounded-md border bg-white text-blue-700 border-blue-200 hover:bg-blue-50 cursor-pointer">
                <Upload size={14} className="mr-1" /> Import CSV
                <input type="file" accept=".csv" className="hidden" data-testid="ho-sites-csv-input"
                  onChange={async (e) => {
                    const file = e.target.files?.[0]; if (!file) return;
                    try {
                      const fd = new FormData(); fd.append('file', file);
                      const r = await axios.post(`${API}/master-admin/sites/preview-csv`, fd, { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } });
                        const csvSites = (r.data?.sites || []).map((s) => ({
                          name: s.name,
                          // Iter 216h50 — Sicon per-site reference number
                          invoice_customer_ref: s.invoice_customer_ref || '',
                          address_line1: s.address_line1 || '', address_line2: s.address_line2 || '', address_line3: s.address_line3 || '',
                          city: s.city || '', county: s.county || '',
                          postcode: s.postcode || '', country: s.country || 'United Kingdom',
                          phone: s.phone || '', email: s.email || '',
                          site_manager_email: s.site_manager_email || '',
                          default_location: s.default_location || 'Main Floor',
                          is_head_office: !!s.is_head_office,
                        }));
                      setForm((f) => ({ ...f, sites: csvSites.length ? csvSites : f.sites }));
                      notify.success(`${csvSites.length} site(s) imported from CSV`);
                    } catch (err) {
                      notify.error(err?.response?.data?.detail || 'CSV parse failed');
                    }
                    e.target.value = '';
                  }} />
              </label>
              <Button onClick={() => setForm((f) => ({ ...f, sites: [...f.sites, blankSite(false)] }))} variant="outline" size="sm" data-testid="ho-sites-add">
                <Plus size={14} className="mr-1" /> Add site
              </Button>
            </div>
          </div>
          {form.sites.map((s, i) => (
            <Card key={i} className="p-4 border border-zinc-200 space-y-3 bg-zinc-50" data-testid={`ho-site-row-${i}`}>
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-zinc-500">Site #{i + 1}</span>
                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-1.5 text-xs cursor-pointer">
                    <input
                      type="checkbox"
                      checked={!!s.is_head_office}
                      onChange={(e) => {
                        const checked = e.target.checked;
                        setForm((f) => ({
                          ...f,
                          sites: f.sites.map((x, idx) => ({
                            ...x, is_head_office: idx === i ? checked : (checked ? false : x.is_head_office),
                          })),
                        }));
                      }}
                      data-testid={`ho-site-hq-${i}`}
                    />
                    <Star size={12} className="text-amber-500" /> Head Office
                  </label>
                  {form.sites.length > 1 ? (
                    <Button onClick={() => setForm((f) => ({ ...f, sites: f.sites.filter((_, idx) => idx !== i) }))} variant="ghost" size="sm" data-testid={`ho-site-remove-${i}`}>
                      <Trash2 size={13} className="text-red-500" />
                    </Button>
                  ) : null}
                </div>
              </div>
              <div className="grid md:grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs text-zinc-500">Site Name *</Label>
                  <Input value={s.name} onChange={(e) => setForm((f) => ({ ...f, sites: f.sites.map((x, idx) => idx === i ? { ...x, name: e.target.value } : x) }))} placeholder="e.g. Tottenham Green Leisure Centre" className="mt-1 bg-white" data-testid={`ho-site-name-${i}`} />
                </div>
                <div>
                  <Label className="text-xs text-zinc-500">Site Email</Label>
                  <Input value={s.email} onChange={(e) => setForm((f) => ({ ...f, sites: f.sites.map((x, idx) => idx === i ? { ...x, email: e.target.value } : x) }))} placeholder="manager@site.com" className="mt-1 bg-white" data-testid={`ho-site-email-${i}`} />
                </div>
              </div>
              <AddressFields
                value={s}
                onChange={(next) => setForm((f) => ({ ...f, sites: f.sites.map((x, idx) => idx === i ? { ...x, ...next } : x) }))}
                testIdPrefix={`ho-site-${i}`}
                bg="bg-white"
                required={false}
                compact
              />
              <div className="grid md:grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs text-zinc-500">Phone</Label>
                  <Input value={s.phone} onChange={(e) => setForm((f) => ({ ...f, sites: f.sites.map((x, idx) => idx === i ? { ...x, phone: e.target.value } : x) }))} placeholder="020 7123 4567" className="mt-1 bg-white" />
                </div>
                <div>
                  <Label className="text-xs text-zinc-500">Default Equipment Location</Label>
                  <Input value={s.default_location} onChange={(e) => setForm((f) => ({ ...f, sites: f.sites.map((x, idx) => idx === i ? { ...x, default_location: e.target.value } : x) }))} placeholder="Main Floor" className="mt-1 bg-white" />
                </div>
              </div>
              {/* Iter 216h50 — Sicon per-site "Invoice Customer Ref".
                  Optional during onboarding but populating it now means
                  equipment imports later can resolve site by this code
                  instead of forcing an exact site-name match. */}
              <div>
                <Label className="text-xs text-zinc-500">Invoice Customer Ref <span className="text-zinc-400 normal-case">(Sicon)</span></Label>
                <Input
                  value={s.invoice_customer_ref || ''}
                  onChange={(e) => setForm((f) => ({ ...f, sites: f.sites.map((x, idx) => idx === i ? { ...x, invoice_customer_ref: e.target.value } : x) }))}
                  placeholder="e.g. INV-CAR-001"
                  className="mt-1 bg-white"
                  data-testid={`ho-site-invoice-ref-${i}`}
                />
              </div>

              {/* Iter 216e — Equipment capture for this site.
                  Two parallel flows so operators pick the fastest path:
                    1. "Import invoice" — AI extracts every machine from
                       a supplier PDF and appends to this site.
                    2. Manual mini-table — fill in the odd machine by
                       hand (Make / Model / Serial / Type).
                  Machines are persisted atomically with the site when
                  the wizard submits (see routes/master_admin.py
                  onboard_head_office). */}
              <div className="border-t border-dashed border-zinc-300 pt-3">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-bold uppercase tracking-wider text-zinc-500 flex items-center gap-1.5">
                    <Sparkles size={12} className="text-[var(--color-brand-blue)]" /> Equipment for this site
                    <span className="ml-1 text-[10px] font-normal text-zinc-400">{(s.equipment || []).length} machine(s)</span>
                  </p>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-7 text-[10px]"
                      onClick={async () => {
                        try {
                          const r = await axios.get(`${API}/master-admin/equipment/template.csv`, { ...auth(), responseType: 'blob' });
                          const url = URL.createObjectURL(r.data);
                          const a = document.createElement('a'); a.href = url; a.download = 'gymaxis-equipment-template.csv'; a.click();
                          URL.revokeObjectURL(url);
                        } catch (e) { notify.error('Could not download template'); }
                      }}
                      data-testid={`ho-site-eq-template-${i}`}
                    >
                      <Download size={11} className="mr-1" /> CSV template
                    </Button>
                    <label className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-1 rounded-md border bg-white text-emerald-700 border-emerald-200 hover:bg-emerald-50 cursor-pointer">
                      <Upload size={11} /> Import CSV
                      <input type="file" accept=".csv" className="hidden" data-testid={`ho-site-csv-${i}`}
                        onChange={async (e) => {
                          const file = e.target.files?.[0]; if (!file) return;
                          try {
                            const fd = new FormData(); fd.append('file', file);
                            const r = await axios.post(`${API}/master-admin/equipment/preview-csv`, fd, auth());
                            const eqRows = r.data?.equipment || [];
                            setForm((f) => ({
                              ...f,
                              sites: f.sites.map((x, idx) => idx === i ? { ...x, equipment: [...(x.equipment || []), ...eqRows] } : x),
                            }));
                            notify.success(`Imported ${eqRows.length} machine(s) from CSV`);
                          } catch (err) {
                            notify.error(err?.response?.data?.detail || 'CSV parse failed');
                          }
                          e.target.value = '';
                        }} />
                    </label>
                    <label className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-1 rounded-md border bg-white text-blue-700 border-blue-200 hover:bg-blue-50 cursor-pointer" title="Big invoices take ~30s–2min — please wait, do not refresh">
                      <Upload size={11} /> Import invoice
                      <input type="file" accept="application/pdf,image/jpeg,image/png,image/webp" className="hidden" data-testid={`ho-site-invoice-${i}`}
                        onChange={async (e) => {
                          const file = e.target.files?.[0]; if (!file) return;
                          // Iter 216m — kick off the phased progress
                          // indicator. We replace the long-lived toast
                          // with an inline bar that shows real upload
                          // progress + a simulated AI-parse phase
                          // tracking the 30–35 s wall-time average.
                          setParseProgress((p) => ({ ...p, [i]: { phase: 'upload', pct: 0 } }));
                          // Try to estimate page count locally so the
                          // "Reading page X of Y…" copy is honest. We
                          // peek at the PDF's `/Type /Page` markers — a
                          // cheap regex on the first 200 KB. Falls
                          // back to 20 if we can't tell.
                          let pageCount = 20;
                          try {
                            const peek = await file.slice(0, Math.min(file.size, 200 * 1024)).text();
                            const m = peek.match(/\/Type\s*\/Page[^s]/g);
                            if (m && m.length) pageCount = m.length;
                          } catch { /* best effort */ }
                          try {
                            const fd = new FormData(); fd.append('file', file);
                            const r = await axios.post(
                              `${API}/master-admin/invoice/parse-for-wizard`,
                              fd,
                              {
                                ...auth(),
                                timeout: 180000,
                                onUploadProgress: (evt) => {
                                  const pct = evt.total ? (evt.loaded / evt.total) * 100 : 0;
                                  setParseProgress((p) => ({
                                    ...p,
                                    [i]: { phase: pct >= 100 ? 'parse' : 'upload', pct, pageCount },
                                  }));
                                },
                              },
                            );
                            const { site: aiSite, equipment: aiEq, supplier_name } = r.data || {};
                            // Iter 216k — back-fill `make`/`manufacturer`
                            // from the supplier when the AI couldn't pin
                            // a brand to the line. Operators were seeing
                            // "Unknown" for every Pulse Fitness item in
                            // multi-site flow.
                            const fallbackMake = (supplier_name || '').trim();
                            const enrichedEq = (aiEq || []).map((eq) => ({
                              ...eq,
                              make: (eq.make && eq.make.trim()) || (fallbackMake && fallbackMake.toLowerCase() !== 'unknown' ? fallbackMake : (eq.make || '')),
                              manufacturer: (eq.manufacturer && eq.manufacturer.trim()) || (eq.make && eq.make.trim()) || fallbackMake || '',
                            }));
                            setForm((f) => ({
                              ...f,
                              sites: f.sites.map((x, idx) => {
                                if (idx !== i) return x;
                                const merged = { ...x };
                                if (!merged.name && aiSite?.name) merged.name = aiSite.name;
                                if (!merged.address_line1 && aiSite?.address_line1) merged.address_line1 = aiSite.address_line1;
                                if (!merged.postcode && aiSite?.postcode) merged.postcode = aiSite.postcode;
                                if (!merged.city && aiSite?.city) merged.city = aiSite.city;
                                merged.equipment = [...(merged.equipment || []), ...enrichedEq];
                                return merged;
                              }),
                            }));
                            setParseProgress((p) => ({ ...p, [i]: { phase: 'done', itemCount: enrichedEq.length } }));
                            // Auto-clear the "Done" bar after 3.5s so
                            // the wizard returns to its compact layout.
                            setTimeout(() => setParseProgress((p) => { const cp = { ...p }; delete cp[i]; return cp; }), 3500);
                            notify.success(`AI extracted ${enrichedEq.length} machine(s) from invoice`);
                          } catch (err) {
                            const detail = err?.response?.data?.detail
                              || (err?.code === 'ECONNABORTED' ? 'Invoice took too long to parse (>3 min). Try splitting the PDF or uploading page-by-page as images.' : null)
                              || (err?.message?.includes?.('Network') ? 'Network error — check your connection and try again.' : null)
                              || 'Invoice parse failed — try a clearer scan or different file';
                            setParseProgress((p) => ({ ...p, [i]: { phase: 'error', message: detail } }));
                            setTimeout(() => setParseProgress((p) => { const cp = { ...p }; delete cp[i]; return cp; }), 6000);
                            notify.error('Invoice parse failed', detail, { duration: 9000 });
                             
                            console.error('[invoice/parse-for-wizard] failed', err?.response?.status, err?.response?.data, err);
                          }
                          e.target.value = '';
                        }} />
                    </label>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-7 text-[10px]"
                      onClick={() => setForm((f) => ({
                        ...f,
                        sites: f.sites.map((x, idx) => idx === i ? {
                          ...x,
                          equipment: [...(x.equipment || []), { name: '', make: '', model: '', serial_number: '', equipment_type: '' }],
                        } : x),
                      }))}
                      data-testid={`ho-site-add-eq-${i}`}
                    >
                      <Plus size={11} className="mr-1" /> Add machine
                    </Button>
                  </div>
                </div>
                {/* Iter 216m — phased AI parse progress for THIS site. */}
                {parseProgress[i] ? <InvoiceParseProgress state={parseProgress[i]} /> : null}
                {(s.equipment || []).length > 0 && (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs bg-white border border-zinc-200 rounded">
                      <thead className="bg-zinc-50 text-zinc-500">
                        <tr>
                          <th className="text-left p-1.5 font-semibold">Make</th>
                          <th className="text-left p-1.5 font-semibold">Model</th>
                          <th className="text-left p-1.5 font-semibold">Serial #</th>
                          <th className="text-left p-1.5 font-semibold">Category</th>
                          <th className="text-left p-1.5 font-semibold">Type</th>
                          <th className="w-6"></th>
                        </tr>
                      </thead>
                      <tbody>
                        {(s.equipment || []).map((eq, j) => (
                          <tr key={j} className="border-t border-zinc-100">
                            <td className="p-1"><input className="w-full px-1.5 py-1 border border-zinc-200 rounded" value={eq.make || ''} placeholder="Pulse Fitness" onChange={(e) => setForm((f) => ({ ...f, sites: f.sites.map((x, idx) => idx === i ? { ...x, equipment: x.equipment.map((y, k) => k === j ? { ...y, make: e.target.value, manufacturer: e.target.value } : y) } : x) }))} data-testid={`ho-site-${i}-eq-${j}-make`} /></td>
                            <td className="p-1"><input className="w-full px-1.5 py-1 border border-zinc-200 rounded" value={eq.model || ''} placeholder="e.g. Club Line Treadmill" onChange={(e) => setForm((f) => ({ ...f, sites: f.sites.map((x, idx) => idx === i ? { ...x, equipment: x.equipment.map((y, k) => k === j ? { ...y, model: e.target.value, name: e.target.value } : y) } : x) }))} data-testid={`ho-site-${i}-eq-${j}-model`} /></td>
                            <td className="p-1"><input className="w-full px-1.5 py-1 border border-zinc-200 rounded font-mono" value={eq.serial_number || ''} placeholder="SN123456" onChange={(e) => setForm((f) => ({ ...f, sites: f.sites.map((x, idx) => idx === i ? { ...x, equipment: x.equipment.map((y, k) => k === j ? { ...y, serial_number: e.target.value } : y) } : x) }))} data-testid={`ho-site-${i}-eq-${j}-serial`} /></td>
                            <td className="p-1">
                              {/* Iter 216k — AI-assigned category. Operator can override via the dropdown. */}
                              <select
                                className="w-full px-1.5 py-1 border border-zinc-200 rounded bg-white"
                                value={eq.equipment_category || ''}
                                onChange={(e) => setForm((f) => ({ ...f, sites: f.sites.map((x, idx) => idx === i ? { ...x, equipment: x.equipment.map((y, k) => k === j ? { ...y, equipment_category: e.target.value } : y) } : x) }))}
                                data-testid={`ho-site-${i}-eq-${j}-category`}
                              >
                                <option value="">—</option>
                                <option value="Cardiovascular">Cardiovascular</option>
                                <option value="Strength">Strength</option>
                                <option value="Free Weights">Free Weights</option>
                                <option value="Functional">Functional</option>
                                <option value="Accessories">Accessories</option>
                              </select>
                            </td>
                            <td className="p-1"><input className="w-full px-1.5 py-1 border border-zinc-200 rounded" value={eq.equipment_type || ''} placeholder="treadmill" onChange={(e) => setForm((f) => ({ ...f, sites: f.sites.map((x, idx) => idx === i ? { ...x, equipment: x.equipment.map((y, k) => k === j ? { ...y, equipment_type: e.target.value } : y) } : x) }))} data-testid={`ho-site-${i}-eq-${j}-type`} /></td>
                            <td className="p-1 text-right">
                              <button type="button" className="text-red-500 hover:bg-red-50 rounded p-0.5" onClick={() => setForm((f) => ({ ...f, sites: f.sites.map((x, idx) => idx === i ? { ...x, equipment: x.equipment.filter((_, k) => k !== j) } : x) }))} data-testid={`ho-site-${i}-eq-${j}-remove`}>
                                <Trash2 size={11} />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {(s.equipment || []).length === 0 && (
                  <p className="text-[11px] text-zinc-400 italic">No equipment yet. Import an invoice to auto-extract, or add machines manually.</p>
                )}
              </div>
            </Card>
          ))}
        </Card>
      )}

      {stepId === 'owner' && (
        <Card className="p-6 space-y-4" data-testid="ho-step-owner">
          <h3 className="text-lg font-bold tracking-tight flex items-center gap-2"><UserPlus size={16} /> Head Office admin</h3>
          <p className="text-sm text-zinc-500">The first user account. Has access to all sites under the Head Office and can invite further site-level admins after onboarding.</p>
          <div className="grid md:grid-cols-2 gap-3">
            <div>
              <Label className="text-xs text-zinc-500">Full Name *</Label>
              <Input value={form.owner_name} onChange={(e) => setForm((f) => ({ ...f, owner_name: e.target.value }))} placeholder="Jane Smith" className="mt-1" data-testid="ho-owner-name" />
            </div>
            <div>
              <Label className="text-xs text-zinc-500">Email *</Label>
              <Input value={form.owner_email} onChange={(e) => setForm((f) => ({ ...f, owner_email: e.target.value.trim().toLowerCase() }))} type="email" placeholder="jane@pulsefitness.co.uk" className="mt-1" data-testid="ho-owner-email" />
            </div>
          </div>
          {/* Iter 216f — credential mode toggle.
              Two options: send invite link (default, self-serve, secure)
              vs. set a password now. Backend already handles the empty-
              password case via the password_reset_tokens flow built in
              Iter 215eu. */}
          <div className="space-y-2">
            <Label className="text-xs text-zinc-500">How will this admin sign in first?</Label>
            <div className="grid md:grid-cols-2 gap-2">
              <label className={`cursor-pointer border rounded-md p-3 text-sm flex gap-2 ${form.owner_credential_mode === 'invite' ? 'border-emerald-300 bg-emerald-50' : 'border-zinc-200 hover:bg-zinc-50'}`} data-testid="ho-cred-mode-invite">
                <input type="radio" name="cred_mode" value="invite" checked={form.owner_credential_mode === 'invite'} onChange={() => setForm((f) => ({ ...f, owner_credential_mode: 'invite', owner_password: '' }))} className="mt-0.5" />
                <div>
                  <p className="font-semibold text-zinc-800">Send invite link</p>
                  <p className="text-[11px] text-zinc-500 leading-snug">After creation we'll generate a one-time link (valid 72h). Email it or DM it — the admin sets their own password. <strong>Recommended.</strong></p>
                </div>
              </label>
              <label className={`cursor-pointer border rounded-md p-3 text-sm flex gap-2 ${form.owner_credential_mode === 'set' ? 'border-blue-300 bg-blue-50' : 'border-zinc-200 hover:bg-zinc-50'}`} data-testid="ho-cred-mode-set">
                <input type="radio" name="cred_mode" value="set" checked={form.owner_credential_mode === 'set'} onChange={() => setForm((f) => ({ ...f, owner_credential_mode: 'set' }))} className="mt-0.5" />
                <div>
                  <p className="font-semibold text-zinc-800">Set a password now</p>
                  <p className="text-[11px] text-zinc-500 leading-snug">Type a temporary password I'll forward verbally or by Signal. The admin will be forced to change it on first sign-in.</p>
                </div>
              </label>
            </div>
          </div>
          {form.owner_credential_mode === 'set' && (
            <div className="relative">
              <Label className="text-xs text-zinc-500">Temporary Password *</Label>
              <Input value={form.owner_password} onChange={(e) => setForm((f) => ({ ...f, owner_password: e.target.value }))} type={form.showPw ? 'text' : 'password'} placeholder="At least 8 characters" className="mt-1 pr-10" data-testid="ho-owner-password" />
              <button type="button" onClick={() => setForm((f) => ({ ...f, showPw: !f.showPw }))} className="absolute right-3 bottom-2.5 text-zinc-400 hover:text-zinc-600">
                {form.showPw ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          )}
        </Card>
      )}

      {stepId === 'review' && (
        <Card className="p-6 space-y-4" data-testid="ho-step-review">
          <h3 className="text-lg font-bold tracking-tight">Review &amp; create</h3>
          <ul className="space-y-2 text-sm">
            <li><strong className="text-zinc-500">Tier:</strong> {TIERS.find((t) => t.id === tier)?.label}</li>
            <li><strong className="text-zinc-500">Head Office:</strong> {form.org_name}{form.company_number ? ` · Co. ${form.company_number}` : ''}</li>
            <li><strong className="text-zinc-500">Owner:</strong> {form.owner_name} · {form.owner_email}</li>
            <li>
              <strong className="text-zinc-500">Sites ({form.sites.length}):</strong>
              <ul className="mt-1 space-y-1 ml-4">
                {form.sites.map((s, i) => (
                  <li key={i} className="flex items-center gap-2">
                    {s.is_head_office ? <Star size={11} className="text-amber-500" /> : <MapPin size={11} className="text-zinc-400" />}
                    <span>{s.name}</span>
                    {s.postcode ? <span className="text-zinc-400 text-xs">· {s.postcode}</span> : null}
                    {s.is_head_office ? <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-800 font-bold">HQ</span> : null}
                  </li>
                ))}
              </ul>
            </li>
          </ul>
          <p className="text-xs text-zinc-500 border-l-2 border-[var(--color-brand-blue)] pl-3 mt-4">
            On submit, the Head Office becomes the SLCustomerAccount in Sage; each site becomes an SLDeliveryAddress / Sicon SubLocation. CRM contacts default to the Head Office and can be re-scoped to a specific site afterwards.
          </p>
        </Card>
      )}

      {/* Footer nav */}
      <div className="flex items-center justify-between">
        <Button variant="outline" onClick={back} disabled={step === 0 || submitting} data-testid="ho-onboard-back">
          <ArrowLeft size={14} className="mr-1.5" /> Back
        </Button>
        {stepId === 'review' ? (
          <Button onClick={submit} disabled={submitting} className="bg-[var(--color-brand-blue)] text-white" data-testid="ho-onboard-submit">
            {submitting ? <Loader2 size={14} className="animate-spin mr-1.5" /> : <Building2 size={14} className="mr-1.5" />}
            {submitting ? 'Creating…' : 'Create Organisation'}
          </Button>
        ) : (
          <Button onClick={next} disabled={submitting} className="bg-[var(--color-brand-blue)] text-white" data-testid="ho-onboard-next">
            Next <ArrowRight size={14} className="ml-1.5" />
          </Button>
        )}
      </div>
    </div>
  );
};

export default HeadOfficeOnboardingWizard;
