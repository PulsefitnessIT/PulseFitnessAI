/**
 * PublicEngineerCard — iter 216h144 (Phase 5).
 *
 * Public landing page for an engineer's supplier card / QR code.
 * Anyone with the link can submit a service request — no login.
 *
 *   /r/<slug>
 *
 * On submit it lands in the engineer's incoming-requests inbox as
 * status='pending'. The engineer triages and accepts or declines.
 *
 * No auth, no sidebar — clean customer-facing branded form.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { useParams } from 'react-router-dom';
import {
  Loader2, Wrench, ShieldCheck, CheckCircle2, AlertCircle,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';

const PRIORITIES = [
  { v: 'P1', label: 'Critical · safety / outage' },
  { v: 'P2', label: 'Major · multiple machines' },
  { v: 'P3', label: 'Standard · one machine' },
  { v: 'P4', label: 'Low priority' },
];

const inputCls = 'w-full border border-slate-300 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 rounded-lg px-3 py-2 text-sm focus:outline-none';
const Field = ({ label, children, required }) => (
  <label className="block">
    <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1 inline-block">
      {label}{required ? <span className="text-red-500">&nbsp;*</span> : null}
    </span>
    {children}
  </label>
);

export default function PublicEngineerCard() {
  const { slug } = useParams();
  const [card, setCard]       = useState(null);
  const [loadErr, setLoadErr] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [form, setForm] = useState({
    customer_name: '', customer_email: '', customer_phone: '',
    site_name: '', site_address: '', site_postcode: '',
    title: '', description: '', priority: 'P3', consent: false,
  });
  const set = (k, v) => setForm((s) => ({ ...s, [k]: v }));

  useEffect(() => {
    let mounted = true;
    axios
      .get(`${API}/r/${slug}`)
      .then((r) => { if (mounted) setCard(r.data); })
      .catch((e) => { if (mounted) setLoadErr(e?.response?.status === 404 ? 'Card not found' : 'Unable to load card'); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [slug]);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.consent) return;
    setSubmitting(true);
    try {
      await axios.post(`${API}/r/${slug}/request`, form);
      setDone(true);
    } catch (e) {
      const detail = e?.response?.data?.detail || e.message;
      window.alert(`Submit failed: ${detail}`);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center" data-testid="public-card-loading">
        <Loader2 size={24} className="animate-spin text-slate-400" />
      </div>
    );
  }
  if (loadErr) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6" data-testid="public-card-error">
        <div className="text-center max-w-sm">
          <AlertCircle size={28} className="mx-auto text-red-500 mb-2" />
          <p className="text-sm font-semibold text-slate-900">{loadErr}</p>
          <p className="text-xs text-slate-500 mt-1">
            This link may have been regenerated. Please contact your engineer for the new one.
          </p>
        </div>
      </div>
    );
  }
  if (done) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6" data-testid="public-card-success">
        <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center max-w-sm">
          <CheckCircle2 size={36} className="mx-auto text-emerald-500 mb-2" />
          <h2 className="text-lg font-extrabold text-slate-900">Request sent</h2>
          <p className="text-sm text-slate-600 mt-1">
            {card?.engineer?.full_name || 'The engineer'} will be in touch shortly. You can close this page.
          </p>
        </div>
      </div>
    );
  }

  const eng = card?.engineer || {};
  const org = card?.organization || {};

  return (
    <div className="min-h-screen bg-slate-50" data-testid="public-card-page">
      {/* Branded header */}
      <header
        className="text-white"
        style={{
          background: org.brand_color
            ? `linear-gradient(135deg, ${org.brand_color}, #1e293b)`
            : 'linear-gradient(135deg, #1e3a8a, #1e293b)',
        }}
      >
        <div className="max-w-2xl mx-auto px-5 py-6 flex items-center gap-4">
          {org.logo_url ? (
            <img
              src={org.logo_url}
              alt=""
              className="w-12 h-12 rounded-xl bg-white p-1 object-contain"
            />
          ) : (
            <span className="w-12 h-12 rounded-xl bg-white/10 flex items-center justify-center font-extrabold">
              {(org.name || 'G').slice(0, 1)}
            </span>
          )}
          <div className="min-w-0">
            <p className="text-[11px] uppercase tracking-[0.18em] opacity-80">{org.name || 'GymAxis Service'}</p>
            <h1 className="text-xl font-extrabold flex items-center gap-2">
              <Wrench size={20} /> Request service from {eng.full_name || 'your engineer'}
            </h1>
          </div>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-5 py-6 space-y-4">
        {/* Engineer card */}
        <section className="bg-white border border-slate-200 rounded-2xl p-4 flex items-center gap-3">
          {eng.photo_url ? (
            <img src={eng.photo_url} alt="" className="w-14 h-14 rounded-full object-cover flex-shrink-0" />
          ) : (
            <span className="w-14 h-14 rounded-full bg-blue-100 text-blue-700 font-extrabold flex items-center justify-center flex-shrink-0">
              {(eng.full_name || 'E').slice(0, 1).toUpperCase()}
            </span>
          )}
          <div className="min-w-0">
            <p className="text-sm font-bold text-slate-900">{eng.full_name}</p>
            {eng.bio ? <p className="text-xs text-slate-600 mt-0.5">{eng.bio}</p> : null}
            {(eng.qualifications || []).length ? (
              <div className="flex items-center gap-1 mt-1 flex-wrap">
                {eng.qualifications.map((q) => (
                  <span key={q} className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700">
                    <ShieldCheck size={9} /> {q}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        </section>

        {/* Form */}
        <form
          onSubmit={submit}
          className="bg-white border border-slate-200 rounded-2xl p-5 space-y-4"
          data-testid="public-card-form"
        >
          <h2 className="text-sm font-extrabold text-slate-900">Tell us about the problem</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="sm:col-span-2">
              <Field label="What's wrong?" required>
                <input
                  required
                  value={form.title}
                  onChange={(e) => set('title', e.target.value)}
                  placeholder="e.g. Treadmill #3 belt slipping under load"
                  className={inputCls}
                  data-testid="public-card-title"
                />
              </Field>
            </div>
            <div className="sm:col-span-2">
              <Field label="More detail (optional)">
                <textarea
                  rows={3}
                  value={form.description}
                  onChange={(e) => set('description', e.target.value)}
                  placeholder="When did it start, what model, any noises, photos to follow?"
                  className={inputCls}
                  data-testid="public-card-description"
                />
              </Field>
            </div>
            <Field label="Urgency">
              <select
                value={form.priority}
                onChange={(e) => set('priority', e.target.value)}
                className={inputCls}
                data-testid="public-card-priority"
              >
                {PRIORITIES.map((p) => (
                  <option key={p.v} value={p.v}>{p.v} — {p.label}</option>
                ))}
              </select>
            </Field>
            <Field label="Site name">
              <input value={form.site_name} onChange={(e) => set('site_name', e.target.value)} className={inputCls} data-testid="public-card-site" />
            </Field>
            <div className="sm:col-span-2">
              <Field label="Site address (optional)">
                <input value={form.site_address} onChange={(e) => set('site_address', e.target.value)} className={inputCls} data-testid="public-card-site-address" />
              </Field>
            </div>
            <Field label="Postcode (optional)">
              <input value={form.site_postcode} onChange={(e) => set('site_postcode', e.target.value)} className={inputCls} data-testid="public-card-postcode" />
            </Field>
          </div>

          <div className="pt-3 border-t border-slate-100">
            <h3 className="text-sm font-extrabold text-slate-900 mb-2">Your contact details</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Name" required>
                <input
                  required
                  value={form.customer_name}
                  onChange={(e) => set('customer_name', e.target.value)}
                  className={inputCls}
                  data-testid="public-card-name"
                />
              </Field>
              <Field label="Email" required>
                <input
                  required
                  type="email"
                  value={form.customer_email}
                  onChange={(e) => set('customer_email', e.target.value)}
                  className={inputCls}
                  data-testid="public-card-email"
                />
              </Field>
              <Field label="Phone (optional)">
                <input
                  value={form.customer_phone}
                  onChange={(e) => set('customer_phone', e.target.value)}
                  className={inputCls}
                  data-testid="public-card-phone"
                />
              </Field>
            </div>
          </div>

          <label className="flex items-start gap-2 pt-2">
            <input
              type="checkbox"
              checked={form.consent}
              onChange={(e) => set('consent', e.target.checked)}
              className="mt-0.5"
              data-testid="public-card-consent"
            />
            <span className="text-xs text-slate-600">
              I agree to {org.name || 'GymAxis'} contacting me about this service request.
            </span>
          </label>

          <button
            type="submit"
            disabled={submitting || !form.consent || !form.title || !form.customer_name || !form.customer_email}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 text-white font-bold py-3 rounded-lg flex items-center justify-center gap-2"
            data-testid="public-card-submit"
          >
            {submitting ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
            Send request
          </button>
          <p className="text-[10px] text-slate-400 text-center">
            Powered by GymAxis · your details stay with {eng.full_name || 'your engineer'} and their service team
          </p>
        </form>
      </main>
    </div>
  );
}
