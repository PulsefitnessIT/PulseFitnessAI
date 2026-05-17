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
import React, { useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  ChevronLeft, Loader2, Sparkles, Wand2, ClipboardPaste,
  Wrench, Mail, Building2, AlertCircle, CheckCircle2,
} from 'lucide-react';
import { notify } from '@/components/notifications';

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

const CHANNELS = [
  { v: 'manual',  label: 'Walked in / phone' },
  { v: 'email',   label: 'Email request' },
  { v: 'phone',   label: 'Phone call' },
  { v: 'other',   label: 'Other / referral' },
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
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [emailText, setEmailText] = useState('');
  const [emailSubject, setEmailSubject] = useState('');
  const [form, setForm] = useState({
    title: '', description: '', priority: 'P3',
    customer_name: '', customer_email: '', customer_phone: '',
    site_name: '', site_address: '', site_postcode: '',
    scheduled_at: '', estimated_minutes: 60,
    intake_channel: 'manual', source_note: '',
  });

  const set = (k, v) => setForm((s) => ({ ...s, [k]: v }));

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
              GymAxis · Engineer
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
            <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1.5">
              <Building2 size={12} /> Customer & site
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
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

          <div className="pt-2 grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Scheduled for">
              <input type="datetime-local" value={form.scheduled_at} onChange={(e) => set('scheduled_at', e.target.value)} className={inputCls} data-testid="newjob-scheduled" />
            </Field>
            <Field label="Estimated minutes">
              <input type="number" min={15} max={600} step={15} value={form.estimated_minutes} onChange={(e) => set('estimated_minutes', e.target.value)} className={inputCls} data-testid="newjob-estimated" />
            </Field>
          </div>

          <div className="pt-2">
            <Field label="Source note (optional)">
              <input value={form.source_note} onChange={(e) => set('source_note', e.target.value)} placeholder="Referred by ..., supplier rep ..., etc." className={inputCls} data-testid="newjob-source-note" />
            </Field>
          </div>

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
