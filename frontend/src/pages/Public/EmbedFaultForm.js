/**
 * EmbedFaultForm — Iter 220aa.
 *
 * Public, unauthenticated, iframe-embedded "Log a Fault" / "Get a Quote"
 * form. Lives at `/embed/log-fault/:token`.
 *
 * Engineers and gym companies paste this iframe on their own site:
 *
 *   <iframe src="https://app.gymaxis.ai/embed/log-fault/<token>"
 *           width="100%" height="640" style="border:0"></iframe>
 *
 * The form auto-resizes its viewport, includes a honeypot field, and
 * after submission shows a branded "Thanks" panel then auto-redirects
 * (or auto-closes) after 5 seconds.
 */
import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import {
  Star, ShieldCheck, AlertCircle, Loader2, Send, CheckCircle2,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';

const URGENCY_OPTIONS = [
  { v: 'low', label: 'Low — when convenient' },
  { v: 'normal', label: 'Normal — within a few days' },
  { v: 'high', label: 'High — same day if possible' },
  { v: 'urgent', label: 'Urgent — equipment down' },
];

const Field = ({ label, required, hint, children, testId }) => (
  <label className="block" data-testid={testId ? `${testId}-wrap` : undefined}>
    <span className="text-xs font-semibold text-zinc-700">
      {label}{required ? <span className="text-rose-500 ml-0.5">*</span> : null}
    </span>
    {children}
    {hint ? <span className="text-[11px] text-zinc-500 mt-1 block">{hint}</span> : null}
  </label>
);

export default function EmbedFaultForm() {
  const { token } = useParams();
  const [config, setConfig] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [form, setForm] = useState({
    customer_name: '', customer_email: '', customer_phone: '',
    site_name: '', site_postcode: '',
    title: '', description: '', urgency: 'normal',
    website: '', // honeypot
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [countdown, setCountdown] = useState(5);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/widget/embed/${encodeURIComponent(token)}`);
        if (!cancelled) setConfig(r.data);
      } catch (e) {
        if (!cancelled) setLoadError(
          e?.response?.status === 404 ? 'This form has been revoked or the link is invalid.'
            : 'Could not load the form, please try again later.',
        );
      }
    })();
    return () => { cancelled = true; };
  }, [token]);

  // Post-submit countdown → redirect / auto-close.
  useEffect(() => {
    if (!submitted) return undefined;
    if (countdown <= 0) {
      if (config?.redirect_url) {
        window.top.location.href = config.redirect_url;
      } else {
        try { window.parent.postMessage({ source: 'gymaxis-widget', event: 'close' }, '*'); } catch (_e) { /* noop */ }
      }
      return undefined;
    }
    const t = setTimeout(() => setCountdown((n) => n - 1), 1000);
    return () => clearTimeout(t);
  }, [submitted, countdown, config?.redirect_url]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const isFault = config?.kind === 'log_fault';

  const submit = async (e) => {
    e?.preventDefault?.();
    setSubmitError(null);
    if (!form.customer_name.trim() || !form.customer_email.trim() || !form.description.trim()) {
      setSubmitError('Please fill in your name, email, and a short description.');
      return;
    }
    setSubmitting(true);
    try {
      await axios.post(`${API}/widget/embed/${encodeURIComponent(token)}/submit`, form);
      setSubmitted(true);
    } catch (e2) {
      const detail = e2?.response?.data?.detail;
      setSubmitError(
        typeof detail === 'string' ? detail :
          'Could not submit, please try again in a moment.',
      );
    } finally {
      setSubmitting(false);
    }
  };

  const reviewBadge = useMemo(() => {
    if (!config?.show_reviews_badge || !config?.summary?.count) return null;
    const avg = config.summary.average?.toFixed(1);
    return (
      <span
        className="inline-flex items-center gap-1 text-xs font-bold text-amber-900 bg-amber-50 rounded-full px-2 py-0.5"
        data-testid="embed-reviews-badge"
      >
        <Star size={11} className="text-amber-500 fill-amber-500" />
        {avg} · {config.summary.count} reviews
      </span>
    );
  }, [config]);

  if (loadError) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white px-4">
        <div className="max-w-sm text-center" data-testid="embed-not-found">
          <AlertCircle size={28} className="text-rose-500 mx-auto mb-2" />
          <h1 className="text-base font-bold text-zinc-900">{loadError}</h1>
        </div>
      </div>
    );
  }

  if (!config) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white">
        <Loader2 className="animate-spin text-blue-600" size={24} />
      </div>
    );
  }

  if (submitted) {
    return (
      <div
        className="min-h-screen flex items-center justify-center bg-white px-4"
        data-testid="embed-thanks-panel"
      >
        <div className="max-w-sm text-center">
          <div className="w-14 h-14 rounded-full bg-green-100 mx-auto mb-3 flex items-center justify-center">
            <CheckCircle2 size={28} className="text-green-600" />
          </div>
          <h1 className="text-xl font-bold text-zinc-900">Thanks — we'll be in touch</h1>
          <p className="text-sm text-zinc-600 mt-2">
            {config.owner?.name?.split(' ')[0] || 'The team'} will reply to{' '}
            <span className="font-semibold">{form.customer_email}</span> shortly.
          </p>
          <p className="text-[11px] text-zinc-400 mt-4">
            {config.redirect_url ? `Redirecting in ${countdown}s…` : `Closing in ${countdown}s…`}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white" data-testid="embed-fault-form">
      <div className="max-w-md mx-auto px-4 py-6 sm:py-8">
        {/* Brand header */}
        <header className="mb-5" data-testid="embed-header">
          <div className="flex items-center gap-3">
            {config.owner?.photo_url ? (
              <img
                src={config.owner.photo_url}
                alt={config.owner.name}
                className="w-12 h-12 rounded-full object-cover border border-zinc-200"
              />
            ) : (
              <div className="w-12 h-12 rounded-full bg-blue-600 text-white flex items-center justify-center font-bold text-lg">
                {(config.owner?.name || 'G').charAt(0).toUpperCase()}
              </div>
            )}
            <div className="flex-1 min-w-0">
              <p className="text-base font-bold text-zinc-900 truncate">{config.owner?.name}</p>
              {config.owner?.company_name ? (
                <p className="text-xs text-zinc-500 truncate">{config.owner.company_name}</p>
              ) : null}
              <div className="mt-1 flex items-center gap-1.5 flex-wrap">
                {reviewBadge}
                <span className="inline-flex items-center gap-1 text-[10px] text-zinc-400">
                  <ShieldCheck size={10} /> Powered by GymAxis
                </span>
              </div>
            </div>
          </div>
          <h2 className="text-xl font-extrabold text-zinc-900 mt-5">
            {config.label}
          </h2>
          <p className="text-xs text-zinc-500 mt-1">
            {isFault
              ? 'Tell us what\'s broken — we\'ll usually reply within a couple of hours.'
              : 'Tell us about your project — we\'ll be in touch shortly.'}
          </p>
        </header>

        <form onSubmit={submit} className="space-y-4">
          {/* Honeypot — hidden from humans via CSS. */}
          <input
            type="text"
            name="website"
            value={form.website}
            onChange={set('website')}
            tabIndex={-1}
            autoComplete="off"
            aria-hidden="true"
            style={{ position: 'absolute', left: '-9999px', height: 0, width: 0, opacity: 0 }}
            data-testid="embed-honeypot"
          />

          <div className="grid grid-cols-2 gap-3">
            <Field label="Your name" required testId="embed-name">
              <input
                type="text"
                value={form.customer_name}
                onChange={set('customer_name')}
                className="mt-1 w-full text-sm rounded-md border border-zinc-300 px-3 py-2 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
                data-testid="embed-name-input"
                required
              />
            </Field>
            <Field label="Phone" testId="embed-phone">
              <input
                type="tel"
                value={form.customer_phone}
                onChange={set('customer_phone')}
                className="mt-1 w-full text-sm rounded-md border border-zinc-300 px-3 py-2 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
                data-testid="embed-phone-input"
              />
            </Field>
          </div>

          <Field label="Email" required testId="embed-email">
            <input
              type="email"
              value={form.customer_email}
              onChange={set('customer_email')}
              className="mt-1 w-full text-sm rounded-md border border-zinc-300 px-3 py-2 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
              data-testid="embed-email-input"
              required
            />
          </Field>

          <div className="grid grid-cols-[2fr_1fr] gap-3">
            <Field label={isFault ? 'Site / gym name' : 'Company'} testId="embed-site">
              <input
                type="text"
                value={form.site_name}
                onChange={set('site_name')}
                className="mt-1 w-full text-sm rounded-md border border-zinc-300 px-3 py-2 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none"
                data-testid="embed-site-input"
              />
            </Field>
            <Field label="Postcode" testId="embed-postcode">
              <input
                type="text"
                value={form.site_postcode}
                onChange={set('site_postcode')}
                className="mt-1 w-full text-sm rounded-md border border-zinc-300 px-3 py-2 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none uppercase"
                data-testid="embed-postcode-input"
              />
            </Field>
          </div>

          <Field
            label={isFault ? 'What\'s the fault?' : 'How can we help?'}
            required
            testId="embed-description"
          >
            <textarea
              rows={4}
              value={form.description}
              onChange={set('description')}
              className="mt-1 w-full text-sm rounded-md border border-zinc-300 px-3 py-2 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none resize-none"
              placeholder={isFault
                ? 'e.g. Treadmill #4 stops mid-run, makes a clicking sound...'
                : 'e.g. We\'re a new studio in Manchester planning to open in Q3...'}
              data-testid="embed-description-input"
              required
            />
          </Field>

          {isFault ? (
            <Field label="Urgency" testId="embed-urgency">
              <select
                value={form.urgency}
                onChange={set('urgency')}
                className="mt-1 w-full text-sm rounded-md border border-zinc-300 px-3 py-2 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none bg-white"
                data-testid="embed-urgency-input"
              >
                {URGENCY_OPTIONS.map((o) => (
                  <option key={o.v} value={o.v}>{o.label}</option>
                ))}
              </select>
            </Field>
          ) : null}

          {submitError ? (
            <p
              className="text-sm text-rose-600 bg-rose-50 border border-rose-100 rounded-md px-3 py-2"
              data-testid="embed-submit-error"
            >
              {submitError}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={submitting}
            className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-md text-sm font-bold text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 transition-colors"
            data-testid="embed-submit-btn"
          >
            {submitting ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Send size={14} />
            )}
            {submitting ? 'Sending…' : (isFault ? 'Send fault report' : 'Send enquiry')}
          </button>

          <p className="text-[10px] text-center text-zinc-400 mt-3">
            By submitting, you agree to be contacted about your enquiry.
            We don't share your details with anyone else.
          </p>
        </form>
      </div>
    </div>
  );
}
