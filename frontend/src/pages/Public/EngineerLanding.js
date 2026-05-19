/**
 * EngineerLanding — iter 216h148.
 *
 * Public engineer-focused marketing + login surface at /engineer.
 *
 *   • Logged-out: hero pitch + sign-in form + "Apply" CTA.
 *   • Logged-in engineer: instant redirect into /svc/engineer.
 *
 * Designed light-mode GymAxis aesthetic with bold typography. No
 * dependency on the main marketing site so this can be linked from
 * physical supplier cards, ads, or LinkedIn without footer/menu noise.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowRight, Wrench, FileText, Receipt, Wifi, Hand, Bell, ShieldCheck,
  Calendar, Loader2, CheckCircle2, ChevronRight, Sparkles, QrCode,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';

// ── Feature card ──────────────────────────────────────────────
const Feature = ({ icon: Icon, title, body, testid }) => (
  <div
    className="bg-white rounded-2xl border border-slate-200 p-5 hover:shadow-md transition-all"
    data-testid={testid}
  >
    <span className="w-10 h-10 rounded-xl bg-blue-50 text-blue-700 flex items-center justify-center mb-3">
      <Icon size={18} />
    </span>
    <h3 className="text-sm font-extrabold text-slate-900 mb-1">{title}</h3>
    <p className="text-xs text-slate-600 leading-relaxed">{body}</p>
  </div>
);

// ── Login form ────────────────────────────────────────────────
const LoginCard = ({ onSuccess }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      const r = await axios.post(`${API}/auth/login`, { email, password });
      const tok = r.data?.token;
      if (!tok) throw new Error('No token returned');
      localStorage.setItem('token', tok);
      try { localStorage.setItem('user', JSON.stringify(r.data.user || {})); } catch (e2) { /* ignore */ }
      onSuccess?.(r.data.user || {});
    } catch (e) {
      setErr(e?.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      onSubmit={submit}
      className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm"
      data-testid="engineer-landing-login"
    >
      <h3 className="text-base font-extrabold text-slate-900 mb-1">Sign in</h3>
      <p className="text-xs text-slate-500 mb-4">For existing GymAxis engineers.</p>
      <label className="block mb-3">
        <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1 inline-block">
          Email
        </span>
        <input
          required
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@gym.com"
          className="w-full border border-slate-300 focus:border-blue-500 rounded-lg px-3 py-2 text-sm focus:outline-none"
          data-testid="engineer-landing-email"
        />
      </label>
      <label className="block mb-4">
        <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1 inline-block">
          Password
        </span>
        <input
          required
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full border border-slate-300 focus:border-blue-500 rounded-lg px-3 py-2 text-sm focus:outline-none"
          data-testid="engineer-landing-password"
        />
      </label>
      {err ? (
        <p className="text-xs text-red-600 mb-3" data-testid="engineer-landing-error">{err}</p>
      ) : null}
      <button
        type="submit"
        disabled={busy}
        className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 text-white font-bold rounded-lg py-2.5 text-sm flex items-center justify-center gap-2"
        data-testid="engineer-landing-submit"
      >
        {busy ? <Loader2 size={14} className="animate-spin" /> : <ArrowRight size={14} />}
        Sign in
      </button>
      <p className="text-[11px] text-center text-slate-500 mt-3">
        <Link to="/forgot-password" className="hover:underline">Forgot password?</Link>
      </p>
    </form>
  );
};

// ── Main page ──────────────────────────────────────────────────
export default function EngineerLanding() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [bootChecked, setBootChecked] = useState(false);

  // If already logged in, drop straight into the engineer app.
  useEffect(() => {
    const tok = (typeof localStorage !== 'undefined') ? localStorage.getItem('token') : null;
    if (!tok) { setBootChecked(true); return; }
    axios
      .get(`${API}/auth/me`, { headers: { Authorization: `Bearer ${tok}` } })
      .then((r) => {
        // /api/auth/me returns user object directly, not wrapped in {user: ...}
        if (r.data?.id || r.data?.user) {
          navigate(params.get('next') || '/svc/engineer', { replace: true });
        } else {
          setBootChecked(true);
        }
      })
      .catch(() => setBootChecked(true));
  }, [navigate, params]);

  if (!bootChecked) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50" data-testid="engineer-landing-bootcheck">
        <Loader2 size={20} className="animate-spin text-slate-400" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white" data-testid="engineer-landing">
      {/* Slim top bar */}
      <nav className="bg-white/80 backdrop-blur border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-5 py-3 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 text-slate-900 font-extrabold tracking-tight" data-testid="engineer-landing-logo">
            <span className="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-600 to-indigo-600 text-white flex items-center justify-center text-sm">G</span>
            GymAxis · Engineer
          </Link>
          <div className="flex items-center gap-2 text-xs">
            <Link to="/partners/engineers/apply" className="px-3 py-1.5 rounded-lg text-slate-700 hover:bg-slate-100 font-semibold" data-testid="engineer-landing-apply-top">
              Apply
            </Link>
            <a href="#signin" className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold" data-testid="engineer-landing-signin-top">
              Sign in
            </a>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <header className="max-w-6xl mx-auto px-5 pt-12 pb-8 grid grid-cols-1 lg:grid-cols-[1.2fr_1fr] gap-10 items-start">
        <div>
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-50 text-blue-700 text-[11px] font-bold uppercase tracking-wider mb-4">
            <Sparkles size={11} /> Built for fitness-equipment engineers
          </span>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight text-slate-900 leading-[1.05] mb-4">
            Run your own service business.
            <span className="block text-blue-600">Keep 100% of the invoice.</span>
          </h1>
          <p className="text-base sm:text-lg text-slate-600 max-w-xl leading-relaxed mb-6">
            GymAxis Engineer is the workforce-ops app fitness pros run their entire field operation from — jobs, AI-drafted quotes, Stripe-funded invoices, voice reports — without a dispatcher.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <a
              href="#signin"
              className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-bold px-5 py-3 rounded-xl text-sm"
              data-testid="engineer-landing-cta-signin"
            >
              Sign in <ArrowRight size={14} />
            </a>
            <Link
              to="/partners/engineers/apply"
              className="inline-flex items-center gap-2 bg-white border border-slate-300 hover:border-slate-400 text-slate-900 font-bold px-5 py-3 rounded-xl text-sm"
              data-testid="engineer-landing-cta-apply"
            >
              Apply to join <ChevronRight size={14} />
            </Link>
          </div>
          <div className="mt-6 flex items-center gap-5 text-xs text-slate-500">
            <span className="inline-flex items-center gap-1"><CheckCircle2 size={12} className="text-emerald-500" /> No platform fee on invoices</span>
            <span className="inline-flex items-center gap-1"><CheckCircle2 size={12} className="text-emerald-500" /> Stripe Connect direct payouts</span>
            <span className="inline-flex items-center gap-1"><CheckCircle2 size={12} className="text-emerald-500" /> Works offline</span>
          </div>
        </div>

        {/* Login pane */}
        <div id="signin">
          <LoginCard onSuccess={() => { window.location.href = '/svc/engineer'; }} />
          <p className="text-[11px] text-center text-slate-500 mt-3">
            Don&apos;t have a GymAxis account yet?{' '}
            <Link to="/partners/engineers/apply" className="text-blue-700 font-semibold hover:underline">
              Apply to become a partner engineer
            </Link>
          </p>
        </div>
      </header>

      {/* Feature grid */}
      <section className="max-w-6xl mx-auto px-5 py-10">
        <h2 className="text-2xl font-extrabold text-slate-900 mb-2">Everything you need on one screen</h2>
        <p className="text-sm text-slate-500 mb-6 max-w-2xl">
          From the moment a customer scans your card to the second the invoice lands in your bank — GymAxis runs the whole loop.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <Feature icon={Calendar} title="Diary &amp; scheduling" body="Week and day views over jobs, PPMs and personal blocks. Drag-to-reschedule." testid="feat-diary" />
          <Feature icon={Hand}     title="Self-allocate jobs" body="Pick from the org-wide queue — first tap wins, never a dispatcher conflict." testid="feat-queue" />
          <Feature icon={QrCode}   title="Your supplier card" body="A unique QR + printable A6 PDF customers scan to send you work directly." testid="feat-card" />
          <Feature icon={FileText} title="AI quotes &amp; reports" body="GPT-5.2 drafts the brief, line-items the quote and writes the service report." testid="feat-ai" />
          <Feature icon={Receipt}  title="Stripe payouts" body="Direct charges to your connected Stripe account — invoice money lands fast." testid="feat-stripe" />
          <Feature icon={Wifi}     title="Works offline" body="No signal in the basement? Time, mileage and signatures queue and sync." testid="feat-offline" />
          <Feature icon={Bell}     title="Push notifications" body="New jobs and reschedules buzz your phone in real time — Web Push or installed PWA." testid="feat-push" />
          <Feature icon={Wrench}   title="Phase-3 workflow" body="H&amp;S checklists, time tracking, parts allocation, customer signature — built in." testid="feat-workflow" />
          <Feature icon={ShieldCheck} title="Compliance ready" body="PAT, electrical, SafeContractor — qualifications surface on every signature." testid="feat-compliance" />
        </div>
      </section>

      {/* Big closing CTA */}
      <section className="max-w-6xl mx-auto px-5 pb-16">
        <div className="rounded-3xl bg-gradient-to-br from-blue-600 to-indigo-600 text-white p-8 sm:p-10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-5">
          <div>
            <h3 className="text-2xl font-extrabold mb-1">Ready to ditch the dispatcher?</h3>
            <p className="text-sm text-blue-100">Join GymAxis as a partner engineer and start taking work in days.</p>
          </div>
          <div className="flex gap-3 flex-shrink-0">
            <Link
              to="/partners/engineers/apply"
              className="inline-flex items-center gap-2 bg-white text-blue-700 font-bold px-5 py-3 rounded-xl text-sm hover:bg-blue-50"
              data-testid="engineer-landing-cta-apply-bottom"
            >
              Apply now <ArrowRight size={14} />
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-slate-200 py-6 text-center text-xs text-slate-400">
        © {new Date().getFullYear()} GymAxis · For partner engineers ·{' '}
        <Link to="/legal/privacy" className="hover:underline">Privacy</Link>{' · '}
        <Link to="/legal/terms" className="hover:underline">Terms</Link>
      </footer>
    </div>
  );
}
