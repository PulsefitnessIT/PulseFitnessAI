/**
 * MOD Service — branded login page (Iter 216h109).
 *
 * Lives at /MODService (and /MODService/login). Skin is dark navy
 * with the MOD Crown Crest and Pulse Fitness logo side-by-side at
 * the top. Authentication piggy-backs on the standard /api/auth/login
 * — once the JWT is set, the AppRoutes /dashboard resolver routes the
 * user to the correct MOD dashboard based on their `account_type`
 * (`mod_site` / `mod_branch` / `mod_org`).
 *
 * Eventually the same component will be served at
 *   www.pulsefitness.ai/MODService
 * once the domain transfer completes — until then it answers from
 *   www.gymaxisai.com/MODService.
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '@/App';
import { Loader2, ShieldCheck, ArrowRight, Lock, Mail } from 'lucide-react';
import { useSeo } from '@/utils/seo';

const PULSE_LOGO = 'https://customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/iscy9t7o_Pulse%20Fitness%20Primary%20Logo%20Badge%20RGB.jpg';

// Iter 216h109 — inline UK MOD Crown Crest (St Edward's Crown).
// Royalty-free public-domain SVG (simplified outline trace).
function MODCrest({ className }) {
  return (
    <svg viewBox="0 0 64 80" className={className} aria-label="UK Ministry of Defence">
      <defs>
        <linearGradient id="modGold" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#FFD972" />
          <stop offset="50%" stopColor="#E8B23A" />
          <stop offset="100%" stopColor="#A77C1C" />
        </linearGradient>
      </defs>
      {/* Crown band */}
      <g fill="url(#modGold)" stroke="#5A3F0A" strokeWidth="0.8">
        <path d="M8 38 C8 30 14 22 32 22 C50 22 56 30 56 38 C56 40 54 42 50 42 L14 42 C10 42 8 40 8 38 Z" />
        {/* Arch top */}
        <path d="M14 22 C18 14 32 6 32 6 C32 6 46 14 50 22 L46 22 C46 22 38 12 32 12 C26 12 18 22 18 22 Z" />
        {/* Orb */}
        <circle cx="32" cy="5" r="3" />
        <rect x="31" y="2" width="2" height="6" rx="0.4" />
        <rect x="29" y="4" width="6" height="2" rx="0.4" />
        {/* Base/jewels */}
        <rect x="10" y="44" width="44" height="4" rx="1" />
        <circle cx="16" cy="46" r="1.2" fill="#E0202A" stroke="none" />
        <circle cx="26" cy="46" r="1.2" fill="#2D7CE6" stroke="none" />
        <circle cx="38" cy="46" r="1.2" fill="#E0202A" stroke="none" />
        <circle cx="48" cy="46" r="1.2" fill="#2D7CE6" stroke="none" />
      </g>
      {/* Banner */}
      <g>
        <rect x="6" y="56" width="52" height="12" rx="1.5" fill="#0B1E4A" />
        <text x="32" y="64.5" fontSize="6" fontWeight="900" fontFamily="system-ui, sans-serif" letterSpacing="1" textAnchor="middle" fill="#E0B557">
          DEFENCE
        </text>
      </g>
    </svg>
  );
}

export default function MODServiceLogin() {
  useSeo({
    title: 'MOD Service — Sign in · Pulse Fitness',
    description: 'Ministry of Defence Service Portal — secure login for British Army, Royal Navy, and Royal Air Force gym sites.',
  });

  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!email || !password) { setError('Email and password required'); return; }
    setError(''); setBusy(true);
    try {
      const r = await axios.post(`${process.env.REACT_APP_BACKEND_URL}/api/auth/login`, {
        email: email.trim().toLowerCase(), password,
      });
      const data = r.data || {};
      login(data.token, data.user, data.refresh_token);
      navigate('/dashboard');
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid credentials');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="min-h-screen relative overflow-hidden flex flex-col"
      data-testid="mod-service-login"
      style={{
        background: 'radial-gradient(ellipse at top, #1a3a6e 0%, #0a1224 50%, #050811 100%)',
        color: '#f1f5f9',
      }}
    >
      {/* Subtle MOD-style grid + scanline overlay */}
      <div
        className="absolute inset-0 opacity-[0.08] pointer-events-none"
        style={{
          backgroundImage: 'linear-gradient(rgba(255,255,255,0.4) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.4) 1px, transparent 1px)',
          backgroundSize: '48px 48px',
        }}
      />

      {/* Top brand bar */}
      <header className="relative z-10 flex items-center justify-between px-6 sm:px-10 py-5 border-b border-white/10">
        <div className="flex items-center gap-3" data-testid="mod-brand-mod">
          <MODCrest className="w-10 h-12" />
          <div className="hidden sm:block">
            <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-amber-300">UK Ministry of Defence</div>
            <div className="text-base font-extrabold tracking-tight text-white">MOD Service Portal</div>
          </div>
        </div>
        <div className="flex items-center gap-3" data-testid="mod-brand-pulse">
          <img src={PULSE_LOGO} alt="Pulse Fitness" className="h-10 w-auto rounded-md object-contain bg-white/95 p-1.5" />
          <div className="hidden sm:block">
            <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-sky-300">Powered by</div>
            <div className="text-sm font-bold text-white">Pulse Fitness</div>
          </div>
        </div>
      </header>

      <main className="relative z-10 flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-md">
          <div className="text-center mb-8">
            <div className="inline-flex items-center gap-2 mb-4 rounded-full bg-amber-400/15 border border-amber-400/30 px-3 py-1 text-[10px] uppercase tracking-[0.18em] font-bold text-amber-300">
              <ShieldCheck size={12} /> Secure access · Service personnel only
            </div>
            <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white">
              MOD Service<br />
              <span className="text-amber-300">Sign in</span>
            </h1>
            <p className="mt-3 text-sm text-slate-300 leading-relaxed">
              Sign in with your service credentials to access the
              fault-reporting, equipment, and CAPEX consoles for your
              gym site.
            </p>
          </div>

          <form
            onSubmit={submit}
            className="rounded-3xl bg-slate-900/60 backdrop-blur-md border border-white/10 p-7 shadow-2xl space-y-4"
            data-testid="mod-login-form"
          >
            <label className="block">
              <span className="text-[11px] uppercase tracking-wider font-bold text-slate-300">Service email</span>
              <div className="mt-1.5 relative">
                <Mail size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="rank.firstname.lastname@army.mod.local"
                  className="w-full pl-9 pr-3 py-2.5 rounded-lg text-sm bg-slate-950/60 border border-white/10 focus:outline-none focus:border-amber-400/60 text-white placeholder-slate-500"
                  data-testid="mod-login-email"
                />
              </div>
            </label>
            <label className="block">
              <span className="text-[11px] uppercase tracking-wider font-bold text-slate-300">Password</span>
              <div className="mt-1.5 relative">
                <Lock size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pl-9 pr-3 py-2.5 rounded-lg text-sm bg-slate-950/60 border border-white/10 focus:outline-none focus:border-amber-400/60 text-white placeholder-slate-500"
                  data-testid="mod-login-password"
                />
              </div>
            </label>
            {error && (
              <div className="rounded-lg bg-rose-500/15 border border-rose-500/30 text-rose-200 text-xs px-3 py-2" data-testid="mod-login-error">
                {error}
              </div>
            )}
            <button
              type="submit"
              disabled={busy}
              className="w-full inline-flex items-center justify-center gap-2 rounded-full bg-amber-400 hover:bg-amber-300 text-slate-900 font-extrabold py-3 text-sm uppercase tracking-wider disabled:opacity-50 transition-colors"
              data-testid="mod-login-submit"
            >
              {busy ? <Loader2 size={14} className="animate-spin" /> : <ArrowRight size={14} />}
              Sign in
            </button>
            <p className="text-[11px] text-slate-400 leading-relaxed text-center pt-1">
              Trouble signing in? Contact your unit PTI or
              <a href="mailto:support@pulsefitness.ai" className="text-amber-300 ml-1 underline-offset-2 hover:underline">Pulse Fitness Support</a>.
            </p>
          </form>

          <div className="mt-7 grid grid-cols-3 gap-3 text-center" data-testid="mod-login-services">
            {[
              { l: 'British Army', c: '#a3a86b' },
              { l: 'Royal Navy', c: '#1d4ed8' },
              { l: 'Royal Air Force', c: '#0ea5e9' },
            ].map((s) => (
              <div key={s.l} className="rounded-xl border border-white/10 bg-white/5 py-2.5">
                <div className="w-2 h-2 rounded-full mx-auto mb-1" style={{ background: s.c }} />
                <div className="text-[10px] uppercase tracking-wider font-bold text-slate-300">{s.l}</div>
              </div>
            ))}
          </div>
        </div>
      </main>

      <footer className="relative z-10 px-6 sm:px-10 py-4 text-[10px] uppercase tracking-[0.18em] text-slate-500 flex items-center justify-between border-t border-white/5">
        <span>UK Restricted · Official-Sensitive</span>
        <span>© Pulse Fitness — MOD Service</span>
      </footer>
    </div>
  );
}
