/**
 * EngineerNewJob — iter 216h144 (Phase 5).
 *
 * Engineer-initiated job creation with optional AI email-paste assist.
 *
 *   /svc/engineer/jobs/new
 *
 * Two-pane on desktop, single pane on mobile:
 *  • Left  — clean form (customer, site, fault, priority, scheduled time)
 *  • Right — "Pasted from an email?" AI helper that calls
 *            POST /api/svc/engineer/jobs/parse-email and pre-fills the form.
 *
 * Submit → POST /api/svc/engineer/jobs/self-create with an Idempotency-Key.
 * Lands on the new job's detail page on success.
 */
import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  ChevronLeft, Loader2, Sparkles, Wand2, ClipboardPaste,
  Wrench, Building2, AlertCircle, CheckCircle2, AlertTriangle,
  Search, BookmarkPlus, History, X, MapPin, Calendar,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import useEngineerOrgBrand from './hooks/useEngineerOrgBrand';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const PRIORITIES = [
  { v: 'P1', label: 'P1 — Critical' },
  { v: 'P2', label: 'P2 — Major'    },
  { v: 'P3', label: 'P3 — Standard' },
  { v: 'P4', label: 'P4 — Low'      },
];

// Iter 220cp/cr — Enquiry channels for ENGINEER-initiated jobs.
// Iter 220cr: dropped "counter" — engineers operate in the field,
// not from a physical shop. The default "On-site" covers spotting
// faults while attending a site or a customer flagging one to the
// engineer in person. `portal`, `inbound_email`, `embed_widget`,
// `supplier_card` and `service_desk` are set automatically by the
// backend when a case is pushed in from those modules.
const CHANNELS = [
  { v: 'manual', label: 'On-site' },
  { v: 'phone',  label: 'Phone call' },
  { v: 'email',  label: 'Email request' },
  { v: 'other',  label: 'Other / referral' },
];

const Field = ({ label, children, required }) => (
  <label className="block">
    <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1 inline-block">
      {label}{required ? <span className="text-red-500">&nbsp;*</span> : null}
    </span>
    {children}
  </label>
);

const inputCls = 'w-full border border-slate-300 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 rounded-lg px-3 py-2 text-sm focus:outline-none';

export default function EngineerNewJob() {
  const orgBrand = useEngineerOrgBrand();
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [emailText, setEmailText] = useState('');
  const [emailSubject, setEmailSubject] = useState('');
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [saveAsCustomer, setSaveAsCustomer] = useState(false);
  // Iter 220ct — Open-jobs warning. Polls /open-cases as the
  // engineer fills the customer fields so they can spot duplicates
  // BEFORE creating a third "treadmill broken" case at the same site.
  const [openCases, setOpenCases] = useState({ count: 0, cases: [] });
  // Iter 220cx — Voice-to-job low-confidence indicator.
  const [voiceConfidence, setVoiceConfidence] = useState(null);
  const [voiceTranscript, setVoiceTranscript] = useState('');
  const [form, setForm] = useState({
    title: '', description: '', priority: 'P3',
    customer_name: '', customer_email: '', customer_phone: '',
    site_name: '', site_address: '', site_postcode: '',
    scheduled_at: '', estimated_minutes: 60,
    intake_channel: 'manual', source_note: '',
  });

  // Iter 220cw — Voice-to-job consumer. When VoiceToJobButton
  // navigates here with ?from=voice we read the parsed payload it
  // stashed in sessionStorage and merge it onto the form.
  useEffect(() => {
    const params = new URLSearchParams(typeof window !== 'undefined' ? window.location.search : '');
    if (params.get('from') !== 'voice') return;
    try {
      const raw = sessionStorage.getItem('svc.engineer.voiceJobDraft');
      if (!raw) return;
      const draft = JSON.parse(raw);
      const parsed = draft.parsed || {};
      setForm((f) => ({
        ...f,
        title:          parsed.title          || f.title,
        description:    parsed.description    || draft.transcript || f.description,
        priority:       parsed.priority       || f.priority,
        customer_name:  parsed.customer_name  || f.customer_name,
        customer_email: parsed.customer_email || f.customer_email,
        customer_phone: parsed.customer_phone || f.customer_phone,
        site_name:      parsed.site_name      || f.site_name,
        site_address:   parsed.site_address   || f.site_address,
        site_postcode:  parsed.site_postcode  || f.site_postcode,
        scheduled_at:   parsed.scheduled_at_hint || f.scheduled_at,
      }));
      // Iter 220cx — confidence banner. The parser self-rates the
      // extraction; below 0.6 we tell the engineer to double-check
      // every field before submitting.
      const c = typeof parsed.confidence === 'number' ? parsed.confidence : 1;
      setVoiceConfidence(c);
      setVoiceTranscript(draft.transcript || '');
      sessionStorage.removeItem('svc.engineer.voiceJobDraft');
    } catch { /* private mode / corrupt JSON — fall through */ }
   
  }, []);

  const set = (k, v) => setForm((s) => {
    const next = { ...s, [k]: v };
    // Iter 220f — auto-enable the "save as customer" tickbox the first
    // time the engineer types a name when no saved customer was picked.
    if (k === 'customer_name' && !selectedCustomer && !saveAsCustomer && (v || '').trim().length >= 2) {
      setSaveAsCustomer(true);
    }
    return next;
  });

  // Iter 220ct — debounced open-cases lookup. Fires whenever the
  // engineer changes the customer name / email / phone / site so the
  // duplicate-warning panel reflects the latest typed values. We
  // never block submission — the panel is purely informational.
  useEffect(() => {
    const name = (form.customer_name || '').trim();
    const email = (form.customer_email || '').trim();
    const phone = (form.customer_phone || '').trim();
    const site = (form.site_name || '').trim();
    const minName = name.length >= 2;
    if (!minName && !email && !phone) {
      setOpenCases({ count: 0, cases: [] });
      return;
    }
    let alive = true;
    const id = setTimeout(async () => {
      try {
        const r = await axios.get(
          `${API}/svc/engineer/customers/open-cases`,
          { ...auth(), params: { name, email, phone, site_name: site } },
        );
        if (alive) setOpenCases(r.data || { count: 0, cases: [] });
      } catch { /* silent — informational only */ }
    }, 400);
    return () => { alive = false; clearTimeout(id); };
  }, [form.customer_name, form.customer_email, form.customer_phone, form.site_name]);

  const aiParse = async () => {
    if (!emailText.trim()) {
      notify.error('Paste the email body first');
      return;
    }
    setAiBusy(true);
    try {
      const r = await axios.post(
        `${API}/svc/engineer/jobs/parse-email`,
        { email_body: emailText, subject: emailSubject || null },
        auth(),
      );
      const p = r.data?.parsed || {};
      setForm((s) => ({
        ...s,
        title:           p.title           || s.title,
        description:     p.description     || s.description,
        priority:        (p.priority || s.priority || 'P3').toUpperCase(),
        customer_name:   p.customer_name   || s.customer_name,
        customer_email:  p.customer_email  || s.customer_email,
        customer_phone:  p.customer_phone  || s.customer_phone,
        site_name:       p.site_name       || s.site_name,
        site_address:    p.site_address    || s.site_address,
        site_postcode:   p.site_postcode   || s.site_postcode,
        scheduled_at:    p.scheduled_at_hint
          ? new Date(p.scheduled_at_hint).toISOString().slice(0, 16)
          : s.scheduled_at,
        intake_channel: 'email',
      }));
      notify.success('Pre-filled from email');
    } catch (e) {
      notify.error('AI parse failed', e?.response?.data?.detail || e.message);
    } finally {
      setAiBusy(false);
    }
  };

  const pasteFromClipboard = async () => {
    try {
      const txt = await navigator.clipboard.readText();
      setEmailText((s) => s + (s ? '\n\n' : '') + txt);
    } catch {
      notify.error('Clipboard unavailable — paste manually');
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!form.title.trim()) {
      notify.error('Add a job title');
      return;
    }
    setSubmitting(true);
    try {
      const idempo = (crypto?.randomUUID && crypto.randomUUID()) || `nj-${Date.now()}`;
      const payload = {
        ...form,
        scheduled_at: form.scheduled_at
          ? new Date(form.scheduled_at).toISOString()
          : null,
        estimated_minutes: Number(form.estimated_minutes) || 60,
      };
      const r = await axios.post(
        `${API}/svc/engineer/jobs/self-create`,
        payload,
        {
          headers: {
            ...auth().headers,
            'Idempotency-Key': idempo,
            'Content-Type': 'application/json',
          },
        },
      );
      notify.success(`Job ${r.data.reference} created`);
      // Iter 220f — Save customer to the address book if the engineer
      // didn't pick one and ticked the box. Non-blocking — a save
      // failure here shouldn't stop the navigation.
      if (saveAsCustomer && !selectedCustomer && form.customer_name.trim()) {
        try {
          await axios.post(`${API}/svc/engineer/customers`, {
            name:         form.customer_name.trim(),
            email:        form.customer_email.trim() || null,
            phone:        form.customer_phone.trim() || null,
            site_name:    form.site_name.trim() || null,
            site_address: form.site_address.trim() || null,
          }, auth());
        } catch (e) {
          // Soft fail — non-blocking. Most common cause: duplicate email
          // already saved, which is fine.
        }
      }
      navigate(`/svc/engineer/jobs/${r.data.case_id}`);
    } catch (e) {
      notify.error('Create failed', e?.response?.data?.detail || e.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-new-job">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/svc/engineer')}
            className="text-slate-500 hover:text-slate-900"
            data-testid="newjob-back"
            aria-label="Back"
          >
            <ChevronLeft size={22} />
          </button>
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-blue-700">
              {orgBrand.label}
            </p>
            <h1 className="text-xl font-extrabold text-slate-900 flex items-center gap-2">
              <Wrench size={20} /> Log a new job
            </h1>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-4 grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* Left — main form */}
        <form
          onSubmit={submit}
          className="lg:col-span-3 bg-white border border-slate-200 rounded-2xl p-5 space-y-4"
          data-testid="newjob-form"
        >
          {/* Iter 220cx — Voice-to-job low-confidence banner.
              The parser self-rates its extraction; below 0.6 we
              warn the engineer to double-check every field. */}
          {voiceConfidence != null && voiceConfidence < 0.6 && (
            <div
              className="rounded-xl bg-amber-50 border border-amber-200 px-3 py-2 flex items-start gap-2"
              data-testid="newjob-voice-confidence-low"
            >
              <AlertTriangle size={14} className="text-amber-700 mt-0.5 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-xs font-bold text-amber-900">
                  Low-confidence dictation ({Math.round(voiceConfidence * 100)}%)
                </p>
                <p className="text-[11px] text-amber-800 mt-0.5">
                  Please double-check every field below — your transcript was:
                </p>
                {voiceTranscript && (
                  <p className="text-[11px] italic text-slate-700 mt-1 line-clamp-3">
                    "{voiceTranscript}"
                  </p>
                )}
              </div>
            </div>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="sm:col-span-2">
              <Field label="Job title" required>
                <input
                  required
                  value={form.title}
                  onChange={(e) => set('title', e.target.value)}
                  placeholder="e.g. Treadmill #4 belt slip"
                  className={inputCls}
                  data-testid="newjob-title"
                />
              </Field>
            </div>
            <Field label="Priority" required>
              <select
                value={form.priority}
                onChange={(e) => set('priority', e.target.value)}
                className={inputCls}
                data-testid="newjob-priority"
              >
                {PRIORITIES.map((p) => (
                  <option key={p.v} value={p.v}>{p.label}</option>
                ))}
              </select>
            </Field>
            <Field label="Source">
              <select
                value={form.intake_channel}
                onChange={(e) => set('intake_channel', e.target.value)}
                className={inputCls}
                data-testid="newjob-channel"
              >
                {CHANNELS.map((c) => (
                  <option key={c.v} value={c.v}>{c.label}</option>
                ))}
              </select>
            </Field>
            <div className="sm:col-span-2">
              <Field label="Description / fault details">
                <textarea
                  rows={3}
                  value={form.description}
                  onChange={(e) => set('description', e.target.value)}
                  placeholder="What's broken, when did it start, anything safety critical?"
                  className={inputCls}
                  data-testid="newjob-description"
                />
              </Field>
            </div>
          </div>

          <div className="pt-2">
            <div className="flex items-center justify-between mb-2">
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                <Building2 size={12} /> Customer & site
              </p>
              {(form.customer_name || form.customer_email || form.site_name) && (
                <button
                  type="button"
                  onClick={() => {
                    if (!window.confirm('Clear customer & site fields?')) return;
                    setForm((s) => ({
                      ...s,
                      customer_name: '', customer_email: '', customer_phone: '',
                      site_name: '', site_address: '', site_postcode: '',
                    }));
                    setSelectedCustomer(null);
                  }}
                  className="text-[10px] font-bold text-slate-500 hover:text-rose-600"
                  data-testid="newjob-customer-clear"
                >
                  Clear
                </button>
              )}
            </div>

            <CustomerTypeahead
              onPick={(c) => {
                // Auto-fill from the selected customer/case row.
                setForm((s) => ({
                  ...s,
                  customer_name:  c.name          || s.customer_name,
                  customer_email: c.email         || s.customer_email,
                  customer_phone: c.phone         || s.customer_phone,
                  site_name:      c.site_name     || s.site_name,
                  site_address:   c.site_address  || s.site_address,
                  site_postcode:  c.site_postcode || s.site_postcode,
                }));
                setSelectedCustomer(c);
                notify.success(`Loaded ${c.name}`);
              }}
            />

            {selectedCustomer && (
              <div className="mt-2 inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-[11px] text-emerald-900" data-testid="newjob-customer-selected-pill">
                <CheckCircle2 size={11} className="text-emerald-600" />
                <span className="font-bold">{selectedCustomer.name}</span>
                {selectedCustomer.source === 'history' && (
                  <span className="text-[10px] uppercase font-bold text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded">history</span>
                )}
                <button
                  type="button"
                  onClick={() => setSelectedCustomer(null)}
                  className="opacity-60 hover:opacity-100"
                  aria-label="Clear pinned customer"
                >
                  <X size={11} />
                </button>
              </div>
            )}

            {/* Iter 220ct — Duplicate-job warning. Lets the engineer
                see existing open cases for this customer BEFORE creating
                another one. Informational only — never blocks submit. */}
            {openCases.count > 0 && (
              <div
                className="mt-3 rounded-xl border border-amber-200 bg-amber-50/70 p-3"
                data-testid="newjob-open-cases-warning"
              >
                <div className="flex items-start gap-2">
                  <AlertTriangle size={14} className="text-amber-700 mt-0.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-bold text-amber-900">
                      {openCases.count} open {openCases.count === 1 ? 'job' : 'jobs'} already at this customer
                    </p>
                    <p className="text-[11px] text-amber-800 mt-0.5">
                      Open one of these instead of creating a duplicate, or carry on if it's truly a new fault.
                    </p>
                    <ul className="mt-2 space-y-1" data-testid="newjob-open-cases-list">
                      {openCases.cases.map((c) => (
                        <li key={c.id}>
                          <button
                            type="button"
                            onClick={() => navigate(`/svc/engineer/jobs/${c.id}`)}
                            className="w-full text-left inline-flex items-center gap-2 px-2 py-1 rounded-lg bg-white border border-amber-200 hover:border-amber-300 text-xs"
                            data-testid={`newjob-open-case-${c.id}`}
                          >
                            <span className="font-bold text-blue-700 tabular-nums">{c.reference || c.id?.slice(0, 8)}</span>
                            <span className="flex-1 truncate text-slate-700">{c.title || '(untitled)'}</span>
                            {c.priority && (
                              <span className="text-[10px] font-bold uppercase tracking-wide text-slate-500">{c.priority}</span>
                            )}
                            <span className="text-[10px] font-bold uppercase tracking-wide text-amber-700 bg-amber-100 px-1.5 py-0.5 rounded">{c.status}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
              <Field label="Customer name">
                <input value={form.customer_name} onChange={(e) => set('customer_name', e.target.value)} className={inputCls} data-testid="newjob-customer-name" />
              </Field>
              <Field label="Customer email">
                <input type="email" value={form.customer_email} onChange={(e) => set('customer_email', e.target.value)} className={inputCls} data-testid="newjob-customer-email" />
              </Field>
              <Field label="Phone">
                <input value={form.customer_phone} onChange={(e) => set('customer_phone', e.target.value)} className={inputCls} data-testid="newjob-customer-phone" />
              </Field>
              <Field label="Site name">
                <input value={form.site_name} onChange={(e) => set('site_name', e.target.value)} className={inputCls} data-testid="newjob-site-name" />
              </Field>
              <div className="sm:col-span-2">
                <Field label="Site address">
                  <input value={form.site_address} onChange={(e) => set('site_address', e.target.value)} className={inputCls} data-testid="newjob-site-address" />
                </Field>
              </div>
              <Field label="Postcode">
                <input value={form.site_postcode} onChange={(e) => set('site_postcode', e.target.value)} className={inputCls} data-testid="newjob-site-postcode" />
              </Field>
            </div>
          </div>

          <SmartSchedulingPanel
            postcode={form.site_postcode}
            currentScheduledAt={form.scheduled_at}
            onPick={(isoDate) => {
              // Default to 9 AM on the suggested day.
              set('scheduled_at', `${isoDate}T09:00`);
            }}
          />

          <div className="pt-2 grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Scheduled for">
              <input type="datetime-local" value={form.scheduled_at} onChange={(e) => set('scheduled_at', e.target.value)} className={inputCls} data-testid="newjob-scheduled" />
            </Field>
            <Field label="Estimated time">
              <div className="flex items-center gap-2" data-testid="newjob-estimated-wrap">
                <select
                  value={Math.floor((Number(form.estimated_minutes) || 0) / 60)}
                  onChange={(e) => {
                    const h = Number(e.target.value);
                    const m = (Number(form.estimated_minutes) || 0) % 60;
                    set('estimated_minutes', h * 60 + m);
                  }}
                  className={`${inputCls} flex-1`}
                  data-testid="newjob-estimated-hours"
                  aria-label="Hours"
                >
                  {Array.from({ length: 9 }, (_, i) => (
                    <option key={i} value={i}>{i} hr{i === 1 ? '' : 's'}</option>
                  ))}
                </select>
                <select
                  value={(Number(form.estimated_minutes) || 0) % 60}
                  onChange={(e) => {
                    const m = Number(e.target.value);
                    const h = Math.floor((Number(form.estimated_minutes) || 0) / 60);
                    set('estimated_minutes', h * 60 + m);
                  }}
                  className={`${inputCls} flex-1`}
                  data-testid="newjob-estimated-minutes"
                  aria-label="Minutes"
                >
                  {[0, 15, 30, 45].map((m) => (
                    <option key={m} value={m}>{m} min</option>
                  ))}
                </select>
              </div>
            </Field>
          </div>

          <div className="pt-2">
            <Field label="Source note (optional)">
              <input value={form.source_note} onChange={(e) => set('source_note', e.target.value)} placeholder="Referred by ..., supplier rep ..., etc." className={inputCls} data-testid="newjob-source-note" />
            </Field>
          </div>

          {/* Iter 220f — Offer to save this customer to the address book
              after creation, so the same engineer doesn't retype it next
              week. Default ON when no saved customer was picked AND the
              engineer typed enough detail for it to be worth saving. */}
          {/* Iter 220h — Proactive "save new customer" prompt. The moment
              the engineer types a customer that isn't already in their
              database, we show an explicit confirm strip rather than
              relying on the engineer to spot the passive checkbox. */}
          <NewCustomerPrompt
            name={form.customer_name}
            siteName={form.site_name}
            email={form.customer_email}
            phone={form.customer_phone}
            address={form.site_address}
            selectedCustomer={selectedCustomer}
            onSaved={(saved) => {
              // Pretend they picked this customer so the next prompt
              // doesn't re-fire and the save-on-submit doesn't double up.
              setSelectedCustomer({ ...saved, source: 'saved' });
              setSaveAsCustomer(false);
              notify.success(`${saved.name} added to your customers`);
            }}
          />

          {!selectedCustomer && form.customer_name.trim().length >= 2 && (
            <label className="flex items-center gap-2 pt-1 text-xs text-slate-700 select-none cursor-pointer" data-testid="newjob-save-customer-toggle">
              <input
                type="checkbox"
                checked={saveAsCustomer}
                onChange={(e) => setSaveAsCustomer(e.target.checked)}
              />
              <BookmarkPlus size={12} className="text-blue-600" />
              Save <b className="mx-0.5">{form.customer_name.trim()}</b> to my customers so I don't have to retype next time
            </label>
          )}

          <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
            <button type="button" onClick={() => navigate('/svc/engineer')} className="px-4 py-2 rounded-lg border border-slate-300 text-sm font-semibold">
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 text-white text-sm font-bold flex items-center gap-2"
              data-testid="newjob-submit"
            >
              {submitting ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
              Create & assign to me
            </button>
          </div>
        </form>

        {/* Right — AI assist */}
        <aside className="lg:col-span-2 bg-gradient-to-br from-indigo-50 to-blue-50 border border-blue-200 rounded-2xl p-5">
          <div className="flex items-start gap-3 mb-3">
            <span className="w-10 h-10 rounded-xl bg-blue-600 text-white flex items-center justify-center">
              <Wand2 size={18} />
            </span>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-blue-700">AI helper</p>
              <h3 className="text-base font-extrabold text-slate-900">Pasted from an email?</h3>
              <p className="text-xs text-slate-600 mt-0.5">
                Drop the email body below and we'll pre-fill the form. GPT‑5.2 extracts customer, site, fault and priority.
              </p>
            </div>
          </div>

          <label className="block mb-2">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1 inline-block">
              Subject (optional)
            </span>
            <input
              value={emailSubject}
              onChange={(e) => setEmailSubject(e.target.value)}
              placeholder="Re: Bike #2 not working at Soho"
              className={inputCls}
              data-testid="newjob-ai-subject"
            />
          </label>

          <label className="block">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1 inline-block">
              Email body
            </span>
            <textarea
              rows={8}
              value={emailText}
              onChange={(e) => setEmailText(e.target.value)}
              placeholder="Paste the email body here…"
              className={`${inputCls} font-mono text-xs`}
              data-testid="newjob-ai-body"
            />
          </label>

          <div className="flex items-center gap-2 mt-3">
            <button
              type="button"
              onClick={pasteFromClipboard}
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white hover:bg-slate-50 border border-slate-200 text-xs font-semibold text-slate-700"
              data-testid="newjob-ai-paste"
            >
              <ClipboardPaste size={14} /> Paste
            </button>
            <button
              type="button"
              onClick={aiParse}
              disabled={aiBusy || !emailText.trim()}
              className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 text-white text-xs font-bold"
              data-testid="newjob-ai-run"
            >
              {aiBusy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
              Extract with AI
            </button>
          </div>
          <p className="text-[10px] text-slate-500 mt-3 flex items-start gap-1.5">
            <AlertCircle size={12} className="mt-0.5 flex-shrink-0" />
            Always review the pre-filled fields before saving — the AI can guess wrong on ambiguous emails.
          </p>
        </aside>
      </main>
    </div>
  );
}

// Iter 220f — Customer typeahead used by the New Job card.
// Hits /api/svc/engineer/customers/typeahead with a 250ms debounce, shows
// up to 8 matches (saved address-book first, then case-history fallback).
function CustomerTypeahead({ onPick }) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef(null);
  const wrapperRef = useRef(null);
  const debounceRef = useRef(null);

  useEffect(() => {
    if (!q.trim()) {
      setResults([]);
      return undefined;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const r = await axios.get(
          `${API}/svc/engineer/customers/typeahead?q=${encodeURIComponent(q.trim())}`,
          auth(),
        );
        setResults(r.data?.results || []);
        setOpen(true);
        setActiveIdx(0);
      } catch (e) {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [q]);

  // Close on outside click.
  useEffect(() => {
    const handler = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const pick = (r) => {
    onPick?.(r);
    setQ('');
    setResults([]);
    setOpen(false);
  };

  const onKeyDown = (e) => {
    if (!open || !results.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      pick(results[activeIdx]);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div ref={wrapperRef} className="relative" data-testid="newjob-customer-typeahead">
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => results.length && setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder="Search saved customers or past jobs — type name, site, postcode, phone…"
          className={`${inputCls} pl-9`}
          data-testid="newjob-customer-search-input"
          autoComplete="off"
        />
        {loading && (
          <Loader2 size={12} className="animate-spin absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" />
        )}
      </div>
      {open && results.length > 0 && (
        <div
          className="absolute left-0 right-0 mt-1 max-h-72 overflow-auto bg-white border border-slate-200 rounded-xl shadow-lg z-20"
          data-testid="newjob-customer-results"
        >
          {results.map((r, idx) => {
            const subtitle = [r.site_name, r.site_postcode, r.email, r.phone].filter(Boolean).join(' · ');
            const isHistory = r.source === 'history';
            return (
              <button
                type="button"
                key={`${r.id || 'h'}-${idx}`}
                onClick={() => pick(r)}
                onMouseEnter={() => setActiveIdx(idx)}
                className={`w-full text-left px-3 py-2 border-b border-slate-100 last:border-b-0 flex items-start gap-2 ${idx === activeIdx ? 'bg-blue-50' : 'hover:bg-slate-50'}`}
                data-testid={`newjob-customer-result-${idx}`}
              >
                <span className="mt-0.5">
                  {isHistory ? (
                    <History size={12} className="text-amber-600" />
                  ) : (
                    <CheckCircle2 size={12} className="text-emerald-600" />
                  )}
                </span>
                <span className="flex-1 min-w-0">
                  <span className="text-sm font-bold text-slate-900 block truncate">{r.name || '—'}</span>
                  {subtitle && <span className="text-[11px] text-slate-500 block truncate">{subtitle}</span>}
                </span>
                {isHistory && (
                  <span className="text-[9px] uppercase font-bold text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded">past job</span>
                )}
              </button>
            );
          })}
        </div>
      )}
      {open && !loading && q.trim() && results.length === 0 && (
        <div
          className="absolute left-0 right-0 mt-1 bg-white border border-slate-200 rounded-xl shadow-lg z-20 px-3 py-2 text-xs text-slate-500"
          data-testid="newjob-customer-no-results"
        >
          No matches — fill the fields below and we'll save them as a new customer.
        </div>
      )}
    </div>
  );
}

// Iter 220g — Smart scheduling suggestions.
// Once the engineer enters a UK postcode (≥5 chars), hit the backend
// to find days they already have nearby jobs (≤ 10 miles). 350ms
// debounce. Surfaced as tappable date chips that pre-fill the
// "Scheduled for" field at 9 AM. Manual booking still always works.
function SmartSchedulingPanel({ postcode, currentScheduledAt, onPick }) {
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [meta, setMeta] = useState(null);
  const debounceRef = useRef(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const cleaned = (postcode || '').replace(/\s+/g, '').toUpperCase();
    if (cleaned.length < 5) {
      setSuggestions([]);
      setMeta(null);
      return undefined;
    }
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const r = await axios.get(
          `${API}/svc/engineer/scheduling-suggestions?postcode=${encodeURIComponent(postcode)}`,
          auth(),
        );
        setSuggestions(r.data?.suggestions || []);
        setMeta({
          radius: r.data?.radius_miles,
          window: r.data?.window_days,
          geocoded: r.data?.target_geocoded,
        });
      } catch (e) {
        setSuggestions([]);
        setMeta(null);
      } finally {
        setLoading(false);
      }
    }, 350);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [postcode]);

  if (!postcode || postcode.trim().length < 5) return null;
  if (loading) {
    return (
      <div className="mt-3 rounded-xl border border-blue-100 bg-blue-50 p-3 flex items-center gap-2 text-xs text-blue-900" data-testid="smart-sched-loading">
        <Loader2 size={12} className="animate-spin" />
        Checking your diary for nearby jobs…
      </div>
    );
  }
  if (!suggestions.length) {
    return (
      <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-500 flex items-center gap-2" data-testid="smart-sched-empty">
        <MapPin size={12} className="text-slate-400" />
        No nearby jobs in your next {meta?.window || 14} days — feel free to pick any date below.
      </div>
    );
  }
  const currentDay = (currentScheduledAt || '').slice(0, 10);
  return (
    <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50/60 p-3" data-testid="smart-sched-panel">
      <div className="flex items-center gap-2 mb-2">
        <MapPin size={13} className="text-amber-700" />
        <p className="text-[11px] font-bold uppercase tracking-wide text-amber-900">
          You already have jobs near here
        </p>
        <span className="text-[10px] text-amber-800/70">
          within {meta?.radius || 10} miles
        </span>
      </div>
      <div className="flex flex-wrap gap-2" data-testid="smart-sched-chip-list">
        {suggestions.map((s) => {
          const d = new Date(`${s.date}T09:00:00`);
          const friendly = d.toLocaleDateString(undefined, {
            weekday: 'short', day: '2-digit', month: 'short',
          });
          const isPicked = currentDay === s.date;
          return (
            <button
              type="button"
              key={s.date}
              onClick={() => onPick?.(s.date)}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-[11px] font-bold transition-colors ${
                isPicked
                  ? 'bg-emerald-100 border-emerald-300 text-emerald-900'
                  : 'bg-white border-amber-200 text-amber-900 hover:bg-amber-100'
              }`}
              data-testid={`smart-sched-chip-${s.date}`}
            >
              <Calendar size={11} />
              {friendly}
              <span className="ml-0.5 inline-flex items-center justify-center min-w-[1.25rem] h-4 rounded-full bg-amber-200/70 text-amber-900 text-[9px] px-1">
                {s.job_count}
              </span>
              {Number.isFinite(s.min_distance_miles) && (
                <span className="text-[10px] text-amber-800/70">
                  · {s.min_distance_miles} mi
                </span>
              )}
              {isPicked && <CheckCircle2 size={11} className="text-emerald-700" />}
            </button>
          );
        })}
      </div>
      <p className="text-[10px] text-amber-800/70 mt-1.5">
        Tap to book that day, or pick any date below manually.
      </p>
    </div>
  );
}


// Iter 220h — Proactive new-customer prompt.
// Watches the customer name/site (450ms debounce). When the engineer
// types a name that doesn't match anything in their saved book, an
// inline amber strip appears asking "Save <name> to my customers?".
// Picking Yes saves immediately so the engineer doesn't need to
// remember at submit time. "Not now" dismisses for this session.
function NewCustomerPrompt({
  name, siteName, email, phone, address, selectedCustomer, onSaved,
}) {
  const [state, setState] = useState({ checking: false, isNew: false });
  const [dismissed, setDismissed] = useState(false);
  const [saving, setSaving] = useState(false);
  const debounceRef = useRef(null);
  const lastNameRef = useRef('');

  useEffect(() => {
    // Reset dismissal whenever the engineer types a meaningfully
    // different name (so they get re-prompted for the next customer).
    const cleaned = (name || '').trim();
    if (cleaned !== lastNameRef.current) {
      setDismissed(false);
      lastNameRef.current = cleaned;
    }
  }, [name]);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const cleaned = (name || '').trim();
    if (selectedCustomer || cleaned.length < 2) {
      setState({ checking: false, isNew: false });
      return undefined;
    }
    debounceRef.current = setTimeout(async () => {
      setState({ checking: true, isNew: false });
      try {
        const params = new URLSearchParams({ name: cleaned });
        if ((siteName || '').trim()) params.set('site_name', siteName.trim());
        if ((email || '').trim()) params.set('email', email.trim());
        if ((phone || '').trim()) params.set('phone', phone.trim());
        const r = await axios.get(
          `${API}/svc/engineer/customers/lookup?${params.toString()}`,
          auth(),
        );
        const found = !!r.data?.found;
        setState({ checking: false, isNew: !found });
      } catch (e) {
        setState({ checking: false, isNew: false });
      }
    }, 450);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [name, siteName, email, phone, selectedCustomer]);

  if (selectedCustomer) return null;
  if ((name || '').trim().length < 2) return null;
  if (dismissed) return null;
  if (state.checking || !state.isNew) return null;

  const onSave = async () => {
    setSaving(true);
    try {
      const r = await axios.post(`${API}/svc/engineer/customers`, {
        name: name.trim(),
        email: (email || '').trim() || null,
        phone: (phone || '').trim() || null,
        site_name: (siteName || '').trim() || null,
        site_address: (address || '').trim() || null,
      }, auth());
      onSaved?.(r.data);
    } catch (e) {
      notify.error('Could not save customer', e?.response?.data?.detail || e?.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="mt-2 rounded-xl border border-amber-200 bg-amber-50/60 p-3 flex items-start gap-2"
      data-testid="newjob-new-customer-prompt"
    >
      <BookmarkPlus size={14} className="text-amber-700 flex-shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <p className="text-xs text-amber-900">
          <span className="font-bold">{name.trim()}</span> isn't in your customer database yet — save them so you don't have to retype next time?
        </p>
      </div>
      <button
        type="button"
        onClick={onSave}
        disabled={saving}
        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-amber-600 hover:bg-amber-700 text-white text-[11px] font-bold disabled:opacity-50"
        data-testid="newjob-new-customer-save"
      >
        {saving ? <Loader2 size={10} className="animate-spin" /> : <BookmarkPlus size={10} />}
        Save
      </button>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-white border border-amber-200 text-amber-800 text-[11px] font-bold hover:bg-amber-50"
        data-testid="newjob-new-customer-dismiss"
      >
        Not now
      </button>
    </div>
  );
}

