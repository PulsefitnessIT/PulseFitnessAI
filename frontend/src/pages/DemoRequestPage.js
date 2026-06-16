/**
 * Public Demo Request landing page — Iter 220ak / Phase A.3.
 *
 * Captures inbound demo requests from the Pulse Fitness public marketing
 * site. POST to /api/public/demo-request which:
 *   1. drops the visitor into the master-admin CRM as a Lead deal +
 *      contact + activity row,
 *   2. fires a Growth Hub "new inbound" alert (badge on the Hub),
 *   3. auto-enrols them into the cold-to-demo B2B journey, and
 *   4. notifies the sales inbox.
 *
 * The form ships with:
 *   - a honeypot ``website`` field (hidden via CSS, invisible to
 *     humans; bots fill every input and trip it);
 *   - inline UTM passthrough (we read the visitor's source so the
 *     CRM can attribute deals back to specific campaigns);
 *   - a clean two-column hero with social-proof bullets on the left
 *     and the form on the right.
 */
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import {
  Rocket, ShieldCheck, Sparkles, ArrowRight, Check, Loader2,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

function useUtm() {
  return useMemo(() => {
    try {
      const u = new URL(window.location.href);
      return {
        utm_source:   u.searchParams.get('utm_source')   || undefined,
        utm_medium:   u.searchParams.get('utm_medium')   || undefined,
        utm_campaign: u.searchParams.get('utm_campaign') || undefined,
      };
    } catch {
      return {};
    }
  }, []);
}

const PROOF_POINTS = [
  {
    icon: Sparkles,
    title: 'Built for multi-site fitness operators',
    body: 'Equipment downtime, partner engineers, CAPEX forecasting, accident reporting — one platform.',
  },
  {
    icon: ShieldCheck,
    title: 'Sage 200 + Sicon Service ready',
    body: 'Posts to your ledger, no double entry. RIDDOR + HSE compliance baked in.',
  },
  {
    icon: Rocket,
    title: '20-min demo · 30-day pilot · 3 weeks to value',
    body: 'See the dashboard your area manager would use, with your data shadow-loaded.',
  },
];

export default function DemoRequestPage() {
  const utm = useUtm();
  const [form, setForm] = useState({
    name: '', email: '', company: '', site_count: 3, message: '',
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [success, setSuccess] = useState(null);

  useEffect(() => {
    document.title = 'Book a demo · Pulse Fitness';
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    const honeypot = (e.target.elements.website || {}).value || '';
    try {
      const r = await axios.post(`${API}/api/public/demo-request`, {
        ...form,
        site_count: Number(form.site_count) || 1,
        website: honeypot,
        ...utm,
      });
      setSuccess(r.data);
    } catch (e2) {
      const detail = e2?.response?.data?.detail;
      setErr(typeof detail === 'string' ? detail : 'Could not submit your request — please try again.');
    } finally { setBusy(false); }
  };

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-fuchsia-50 via-white to-blue-50 px-4" data-testid="demo-request-success">
        <div className="max-w-md w-full bg-white rounded-3xl shadow-[0_30px_80px_-20px_rgba(217,70,239,0.25)] border border-fuchsia-100 p-8 text-center">
          <div className="w-14 h-14 mx-auto rounded-2xl bg-gradient-to-br from-fuchsia-500 to-blue-600 text-white flex items-center justify-center">
            <Check size={24} strokeWidth={3}/>
          </div>
          <h1 className="text-2xl font-extrabold mt-5 tracking-tight">Thanks — we&apos;re on it.</h1>
          <p className="text-sm text-zinc-600 mt-2">
            Your demo request is logged. A member of the Pulse Fitness team will reach out within
            one working day to book a 20-minute walkthrough tailored to your sites.
          </p>
          <p className="text-[11px] text-zinc-400 mt-5 tabular-nums">Receipt: {success.receipt_id}</p>
          <Link
            to="/"
            className="mt-6 inline-flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-bold border border-zinc-200 hover:border-fuchsia-400"
            data-testid="demo-request-success-home"
          >
            Back to Pulse Fitness
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-fuchsia-50 via-white to-blue-50">
      <div className="max-w-6xl mx-auto px-4 py-12 lg:py-20">
        <div className="grid lg:grid-cols-[1.05fr_1fr] gap-8 lg:gap-14 items-start">
          {/* Left — social proof */}
          <div data-testid="demo-request-hero">
            <p className="text-[11px] uppercase tracking-[0.18em] font-bold text-fuchsia-700">
              Pulse Fitness · Book a demo
            </p>
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight mt-3 leading-[1.05]">
              See how Pulse Fitness<br/>kills equipment downtime.
            </h1>
            <p className="text-base sm:text-lg text-zinc-600 mt-5 max-w-md">
              A 20-minute walkthrough with your sites and equipment shadow-loaded.
              No PowerPoint. Just the exact dashboard your area manager would use.
            </p>
            <div className="mt-8 space-y-5">
              {PROOF_POINTS.map((p) => (
                <div key={p.title} className="flex items-start gap-3">
                  <span className="shrink-0 w-9 h-9 rounded-xl bg-white border border-fuchsia-100 text-fuchsia-700 flex items-center justify-center">
                    <p.icon size={15} />
                  </span>
                  <div>
                    <p className="text-sm font-extrabold">{p.title}</p>
                    <p className="text-sm text-zinc-600 mt-0.5">{p.body}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Right — form */}
          <form
            onSubmit={submit}
            className="bg-white rounded-3xl shadow-[0_30px_80px_-20px_rgba(217,70,239,0.25)] border border-fuchsia-100 p-6 sm:p-8"
            data-testid="demo-request-form"
            noValidate
          >
            <h2 className="text-xl font-extrabold tracking-tight">Tell us about your sites</h2>
            <p className="text-sm text-zinc-500 mt-1">We&apos;ll come back within one working day.</p>

            {err ? (
              <div className="mt-4 rounded-md border border-rose-200 bg-rose-50 text-rose-700 text-sm px-3 py-2" data-testid="demo-request-error">
                {err}
              </div>
            ) : null}

            <div className="mt-5 grid gap-3">
              <label className="grid gap-1.5">
                <span className="text-xs font-bold text-zinc-700">Your name *</span>
                <input
                  type="text" required minLength={2} maxLength={80}
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="px-3 py-2.5 rounded-md border border-zinc-300 focus:border-fuchsia-400 focus:ring-1 focus:ring-fuchsia-200 outline-none text-sm"
                  data-testid="demo-request-name"
                  placeholder="Alex Carter"
                />
              </label>
              <label className="grid gap-1.5">
                <span className="text-xs font-bold text-zinc-700">Work email *</span>
                <input
                  type="email" required maxLength={120}
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  className="px-3 py-2.5 rounded-md border border-zinc-300 focus:border-fuchsia-400 focus:ring-1 focus:ring-fuchsia-200 outline-none text-sm"
                  data-testid="demo-request-email"
                  placeholder="alex@yourgym.com"
                />
              </label>
              <div className="grid grid-cols-[1.4fr_1fr] gap-3">
                <label className="grid gap-1.5">
                  <span className="text-xs font-bold text-zinc-700">Company *</span>
                  <input
                    type="text" required minLength={2} maxLength={120}
                    value={form.company}
                    onChange={(e) => setForm({ ...form, company: e.target.value })}
                    className="px-3 py-2.5 rounded-md border border-zinc-300 focus:border-fuchsia-400 focus:ring-1 focus:ring-fuchsia-200 outline-none text-sm"
                    data-testid="demo-request-company"
                    placeholder="Anytime Fitness UK"
                  />
                </label>
                <label className="grid gap-1.5">
                  <span className="text-xs font-bold text-zinc-700">Sites *</span>
                  <input
                    type="number" required min={1} max={999}
                    value={form.site_count}
                    onChange={(e) => setForm({ ...form, site_count: e.target.value })}
                    className="px-3 py-2.5 rounded-md border border-zinc-300 focus:border-fuchsia-400 focus:ring-1 focus:ring-fuchsia-200 outline-none text-sm"
                    data-testid="demo-request-sites"
                  />
                </label>
              </div>
              <label className="grid gap-1.5">
                <span className="text-xs font-bold text-zinc-700">What are you hoping Pulse Fitness solves? (optional)</span>
                <textarea
                  maxLength={2000} rows={3}
                  value={form.message}
                  onChange={(e) => setForm({ ...form, message: e.target.value })}
                  className="px-3 py-2.5 rounded-md border border-zinc-300 focus:border-fuchsia-400 focus:ring-1 focus:ring-fuchsia-200 outline-none text-sm resize-y"
                  data-testid="demo-request-message"
                  placeholder="Cut equipment downtime, kill the WhatsApp service thread, Sage integration..."
                />
              </label>
              {/* Honeypot — hidden from humans, picked up by bots. */}
              <label aria-hidden="true" tabIndex={-1} style={{ position: 'absolute', left: '-9999px', height: 0, overflow: 'hidden' }}>
                Website
                <input
                  type="text" name="website" autoComplete="off"
                  tabIndex={-1}
                  data-testid="demo-request-honeypot"
                />
              </label>
            </div>

            <button
              type="submit" disabled={busy}
              className="mt-5 w-full inline-flex items-center justify-center gap-1.5 px-4 py-3 rounded-md text-sm font-extrabold text-white bg-gradient-to-r from-fuchsia-600 to-blue-600 hover:opacity-90 disabled:opacity-50 transition-opacity"
              data-testid="demo-request-submit"
            >
              {busy ? <Loader2 size={14} className="animate-spin"/> : <Rocket size={14}/>}
              Request demo <ArrowRight size={14}/>
            </button>
            <p className="text-[11px] text-zinc-400 mt-3 text-center">
              By submitting you agree to our <Link to="/privacy" className="underline">privacy policy</Link>.
              We never sell your data and you can unsubscribe at any time.
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}
