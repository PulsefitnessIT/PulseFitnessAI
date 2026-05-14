/**
 * MOD Service Portal — Pulse Fitness branded landing & login.
 * (Iter 216h109 created · Iter 216h112 full rebuild · Iter 216h113
 * re-skinned to Pulse Fitness brand at the customer's request.)
 *
 * MOD orgs are Pulse Fitness customers, so the surface must feel like
 * Pulse Fitness — not a separate navy + gold experience. Identity:
 *   • Pulse primary cyan #66CCFF (CTAs, accents, eyebrows)
 *   • Pulse black #212721 (text + dark hero stripe)
 *   • Pulse surface white #FFFFFF (cards) on neutral background
 *   • Pulse border #E4E4E7
 *
 * The three Service identities (Army olive, Navy navy, RAF blue) are
 * preserved inside their crests so the MOD context still reads, but
 * the surrounding chrome is unmistakably Pulse Fitness.
 *
 * Auth flow unchanged — still piggy-backs on /api/auth/login and lets
 * AppRoutes /dashboard route to MODSiteDashboard / MODProDashboard
 * based on account_type.
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '@/App';
import { Loader2, ShieldCheck, ArrowRight, Lock, Mail, CheckCircle2 } from 'lucide-react';
import { useSeo } from '@/utils/seo';

const PULSE_LOGO = 'https://customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/iscy9t7o_Pulse%20Fitness%20Primary%20Logo%20Badge%20RGB.jpg';

// ── Pulse brand tokens (mirrored from index.css for inline use) ────
const PULSE = {
  primary:        '#66CCFF',
  primaryHover:   '#4DBFFF',
  primaryDeep:    '#33B8FF',
  black:          '#212721',
  greyDark:       '#505759',
  greyLight:      '#A2ACAB',
  bg:             '#F8F9FA',
  surface:        '#FFFFFF',
  border:         '#E4E4E7',
};

// ── Service identities ────────────────────────────────────────────
const SERVICES = [
  {
    id: 'army',
    name: 'British Army',
    motto: 'The Army the nation needs',
    tone: '#5A6234',
    Crest: ArmyCrest,
  },
  {
    id: 'navy',
    name: 'Royal Navy',
    motto: 'Lead · Fight · Win',
    tone: '#0E2B5C',
    Crest: NavyAnchorCrest,
  },
  {
    id: 'raf',
    name: 'Royal Air Force',
    motto: 'Ready to fly and fight',
    tone: '#1F4E89',
    Crest: RafRoundelCrest,
  },
];

// ── MOD crown crest (kept gold for authenticity — gov device) ─────
function MODCrest({ className }) {
  return (
    <svg viewBox="0 0 64 76" className={className} aria-label="UK Ministry of Defence">
      <defs>
        <linearGradient id="modGold" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#F2D27B" />
          <stop offset="55%" stopColor="#C8A35C" />
          <stop offset="100%" stopColor="#8B6A2E" />
        </linearGradient>
      </defs>
      <g fill="url(#modGold)" stroke="#5A3F0A" strokeWidth="0.6">
        <rect x="31" y="2" width="2" height="7" rx="0.4" />
        <rect x="28.5" y="4" width="7" height="2" rx="0.4" />
        <circle cx="32" cy="11" r="2.4" />
        <path d="M14 24 C18 14 32 9 32 9 C32 9 46 14 50 24 L46 24 C44 18 38 14 32 14 C26 14 20 18 18 24 Z" />
        <path d="M8 38 C8 30 14 23 32 23 C50 23 56 30 56 38 C56 41 54 43 50 43 L14 43 C10 43 8 41 8 38 Z" />
        <rect x="9" y="45" width="46" height="4" rx="1" />
        <circle cx="16" cy="47" r="1.2" fill="#C8102E" stroke="none" />
        <circle cx="26" cy="47" r="1.2" fill="#1F4E89" stroke="none" />
        <circle cx="38" cy="47" r="1.2" fill="#C8102E" stroke="none" />
        <circle cx="48" cy="47" r="1.2" fill="#1F4E89" stroke="none" />
      </g>
      <g>
        <rect x="2" y="55" width="60" height="14" rx="2" fill="#212721" />
        <text x="32" y="64.4" fontSize="6.6" fontWeight="900" fontFamily="ui-sans-serif, system-ui, sans-serif" letterSpacing="2.4" textAnchor="middle" fill="#66CCFF">
          DEFENCE
        </text>
      </g>
    </svg>
  );
}

// ── Service crests ────────────────────────────────────────────────
function ArmyCrest({ className }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-label="British Army crest">
      <defs>
        <linearGradient id="armyGold" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#E6CC85" />
          <stop offset="100%" stopColor="#8B6A2E" />
        </linearGradient>
      </defs>
      <path d="M32 4 L56 12 V32 C56 46 44 56 32 60 C20 56 8 46 8 32 V12 Z"
        fill="#5A6234" stroke="url(#armyGold)" strokeWidth="1.3" />
      <g fill="url(#armyGold)" stroke="#3A2C0A" strokeWidth="0.4">
        <path d="M19 19 C20 14 26 12 32 12 C38 12 44 14 45 19 C45 21 43 22 41 22 H23 C21 22 19 21 19 19 Z" />
        <rect x="20" y="23" width="24" height="3" rx="0.6" />
        <circle cx="32" cy="9" r="1.6" />
        <rect x="31" y="6" width="2" height="6" rx="0.4" />
      </g>
      <g fill="url(#armyGold)" stroke="#3A2C0A" strokeWidth="0.4">
        <path d="M22 42 C22 38 24 36 27 36 C30 36 31 38 33 38 C35 38 36 36 39 36 C42 36 44 39 44 42 C44 44 42 46 40 46 H24 C22 46 22 44 22 42 Z" />
        <circle cx="40" cy="35" r="3" />
        <path d="M42 32 L44 30 L43 33 Z" />
        <path d="M22 42 C18 42 17 39 19 37 L21 39 Z" />
        <rect x="26" y="46" width="2.5" height="5" rx="0.5" />
        <rect x="36" y="46" width="2.5" height="5" rx="0.5" />
      </g>
      <rect x="10" y="52" width="44" height="7" rx="1.4" fill="#3A4220" />
      <text x="32" y="56.8" fontSize="3.6" fontWeight="800" letterSpacing="1.4" textAnchor="middle" fill="#F2D27B" fontFamily="ui-sans-serif, system-ui, sans-serif">
        BRITISH ARMY
      </text>
    </svg>
  );
}

function NavyAnchorCrest({ className }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-label="Royal Navy crest">
      <defs>
        <linearGradient id="navyGold" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#F2D27B" />
          <stop offset="100%" stopColor="#8B6A2E" />
        </linearGradient>
      </defs>
      <path d="M32 4 L56 12 V32 C56 46 44 56 32 60 C20 56 8 46 8 32 V12 Z"
        fill="#0E2B5C" stroke="url(#navyGold)" strokeWidth="1.3" />
      <g fill="none" stroke="url(#navyGold)" strokeWidth="2.4" strokeLinecap="round">
        <circle cx="32" cy="14" r="3" />
        <path d="M24 21 L40 21" />
        <path d="M32 17 L32 45" />
        <path d="M19 38 C19 46 27 49 32 45" />
        <path d="M45 38 C45 46 37 49 32 45" />
        <path d="M19 38 L16 41" />
        <path d="M45 38 L48 41" />
      </g>
      <g fill="none" stroke="#F2D27B" strokeWidth="1.2" strokeLinecap="round" opacity="0.85">
        <path d="M28 28 C34 26 36 32 30 34 C26 35 26 39 32 39" />
      </g>
      <rect x="10" y="52" width="44" height="7" rx="1.4" fill="#06173B" stroke="url(#navyGold)" strokeWidth="0.5" />
      <text x="32" y="56.8" fontSize="3.6" fontWeight="800" letterSpacing="1.4" textAnchor="middle" fill="#F2D27B" fontFamily="ui-sans-serif, system-ui, sans-serif">
        ROYAL NAVY
      </text>
    </svg>
  );
}

function RafRoundelCrest({ className }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-label="Royal Air Force crest">
      <defs>
        <linearGradient id="rafGold" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#F2D27B" />
          <stop offset="100%" stopColor="#8B6A2E" />
        </linearGradient>
      </defs>
      <path d="M32 4 L56 12 V32 C56 46 44 56 32 60 C20 56 8 46 8 32 V12 Z"
        fill="#1F4E89" stroke="url(#rafGold)" strokeWidth="1.3" />
      <circle cx="32" cy="28" r="14" fill="#1F4E89" />
      <circle cx="32" cy="28" r="9" fill="#FFFFFF" />
      <circle cx="32" cy="28" r="4" fill="#C8102E" />
      <g fill="url(#rafGold)" stroke="#3A2C0A" strokeWidth="0.4">
        <path d="M14 26 C11 23 11 31 16 32 C13 33 12 36 16 36 Z" />
        <path d="M50 26 C53 23 53 31 48 32 C51 33 52 36 48 36 Z" />
      </g>
      <rect x="10" y="52" width="44" height="7" rx="1.4" fill="#142F58" />
      <text x="32" y="56.8" fontSize="3.6" fontWeight="800" letterSpacing="1.4" textAnchor="middle" fill="#F2D27B" fontFamily="ui-sans-serif, system-ui, sans-serif">
        ROYAL AIR FORCE
      </text>
    </svg>
  );
}

// ── Page ──────────────────────────────────────────────────────────

export default function MODServiceLogin() {
  useSeo({
    title: 'MOD Service Portal — Pulse Fitness',
    description:
      'Pulse Fitness Service Portal for the UK Ministry of Defence. Secure access for British Army, Royal Navy, and Royal Air Force gym sites — fault reporting, equipment, and CAPEX consoles.',
  });

  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!email || !password) { setError('Email or site code and password required'); return; }
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
      className="min-h-screen relative flex flex-col"
      data-testid="mod-service-login"
      style={{
        background: PULSE.bg,
        color: PULSE.black,
        fontFamily: 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
      }}
    >
      {/* OFFICIAL-SENSITIVE classification stripe (UK gov convention,
          re-tinted with Pulse cyan accent text on a black bar) */}
      <div
        className="relative z-20 text-center text-[10px] uppercase font-bold py-1.5"
        style={{ background: PULSE.black, color: PULSE.primary, letterSpacing: '0.32em' }}
        data-testid="mod-classification-stripe"
      >
        UK OFFICIAL · SENSITIVE
      </div>

      {/* Top brand bar */}
      <header
        className="relative z-10 flex items-center justify-between px-5 sm:px-10 py-4"
        style={{ background: PULSE.surface, borderBottom: `1px solid ${PULSE.border}` }}
      >
        <div className="flex items-center gap-3" data-testid="mod-brand-mod">
          <MODCrest className="w-11 h-14" />
          <div className="hidden sm:block">
            <div className="text-[10px] uppercase font-bold" style={{ color: PULSE.greyDark, letterSpacing: '0.28em' }}>
              Ministry of Defence
            </div>
            <div className="text-base font-extrabold tracking-tight" style={{ color: PULSE.black }}>
              Service Portal
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3" data-testid="mod-brand-pulse">
          <div className="hidden sm:block text-right">
            <div className="text-[10px] uppercase font-bold" style={{ color: PULSE.greyDark, letterSpacing: '0.28em' }}>
              Powered by
            </div>
            <div className="text-sm font-extrabold tracking-tight" style={{ color: PULSE.black }}>
              Pulse Fitness
            </div>
          </div>
          <img
            src={PULSE_LOGO}
            alt="Pulse Fitness"
            className="h-11 w-auto rounded-lg object-contain"
            style={{ background: PULSE.surface, padding: '4px', border: `1px solid ${PULSE.border}` }}
          />
        </div>
      </header>

      {/* Main grid */}
      <main className="relative z-10 flex-1 px-5 sm:px-10 py-10 sm:py-16">
        <div className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-14 items-start">

          {/* Left — hero */}
          <section className="lg:col-span-7 order-2 lg:order-1">
            <div
              className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 mb-6"
              style={{
                background: 'rgba(102, 204, 255, 0.10)',
                border: `1px solid rgba(102, 204, 255, 0.4)`,
                color: PULSE.primaryDeep,
              }}
            >
              <ShieldCheck size={12} />
              <span className="text-[10px] uppercase font-bold" style={{ letterSpacing: '0.22em' }}>
                Secure access · Service personnel only
              </span>
            </div>

            <h1
              className="text-4xl sm:text-5xl lg:text-[3.5rem] font-extrabold tracking-tight leading-[1.05]"
              style={{ color: PULSE.black, letterSpacing: '-0.02em' }}
              data-testid="mod-hero-headline"
            >
              One platform.
              <br />
              <span style={{ color: PULSE.primary }}>Three Services.</span>
              <br />
              Always ready.
            </h1>

            <p
              className="mt-5 max-w-xl text-[15px] leading-relaxed"
              style={{ color: PULSE.greyDark }}
            >
              Pulse Fitness Service Portal for the Ministry of Defence —
              fault reporting, equipment registers and CAPEX consoles for
              every MOD gym site. Built for Service Personnel, operated
              by Pulse Fitness.
            </p>

            {/* Service brand panels */}
            <div className="mt-9 grid grid-cols-1 sm:grid-cols-3 gap-3" data-testid="mod-login-services">
              {SERVICES.map((s) => (
                <article
                  key={s.id}
                  className="relative overflow-hidden rounded-2xl px-4 pt-4 pb-3 transition-all duration-200 hover:-translate-y-0.5"
                  style={{
                    background: PULSE.surface,
                    border: `1px solid ${PULSE.border}`,
                    boxShadow: '0 4px 16px -8px rgba(33, 39, 33, 0.08)',
                  }}
                  data-testid={`mod-service-tile-${s.id}`}
                >
                  <div className="flex items-start gap-3">
                    <s.Crest className="w-12 h-12 shrink-0" />
                    <div className="min-w-0">
                      <div className="text-[10px] uppercase font-bold" style={{ color: PULSE.primaryDeep, letterSpacing: '0.22em' }}>
                        Service
                      </div>
                      <div className="text-sm font-extrabold leading-tight" style={{ color: PULSE.black }}>
                        {s.name}
                      </div>
                    </div>
                  </div>
                  <p
                    className="mt-3 text-[11px] uppercase font-bold"
                    style={{ color: PULSE.greyDark, letterSpacing: '0.14em' }}
                  >
                    {s.motto}
                  </p>
                  {/* Service-coloured accent bar */}
                  <span
                    aria-hidden="true"
                    className="absolute left-0 right-0 bottom-0 h-1"
                    style={{ background: s.tone }}
                  />
                </article>
              ))}
            </div>

            {/* Trust strip */}
            <div className="mt-8 grid grid-cols-3 gap-3 max-w-lg" data-testid="mod-trust-strip">
              {[
                { k: '37+', l: 'Sites onboarded' },
                { k: '24/7', l: 'Fault routing' },
                { k: 'UK-only', l: 'Data residency' },
              ].map((t) => (
                <div
                  key={t.l}
                  className="rounded-xl px-3 py-2.5"
                  style={{ background: PULSE.surface, border: `1px solid ${PULSE.border}` }}
                >
                  <div className="text-lg font-extrabold leading-none" style={{ color: PULSE.black }}>
                    {t.k}
                  </div>
                  <div
                    className="text-[10px] uppercase font-bold mt-1"
                    style={{ color: PULSE.greyDark, letterSpacing: '0.18em' }}
                  >
                    {t.l}
                  </div>
                </div>
              ))}
            </div>

            {/* Feature bullets */}
            <ul className="mt-8 space-y-2.5 max-w-lg">
              {[
                'Single sign-in for kiosk and personal credentials',
                'Fault wizard ticketed straight to your maintenance team',
                'CAPEX & availability reporting per HQ, branch, and site',
              ].map((line) => (
                <li key={line} className="flex items-start gap-2.5">
                  <CheckCircle2 size={16} className="shrink-0 mt-0.5" style={{ color: PULSE.primary }} />
                  <span className="text-sm" style={{ color: PULSE.greyDark }}>{line}</span>
                </li>
              ))}
            </ul>
          </section>

          {/* Right — sign-in card */}
          <section className="lg:col-span-5 order-1 lg:order-2 w-full">
            <form
              onSubmit={submit}
              className="relative rounded-3xl p-7 sm:p-8"
              style={{
                background: PULSE.surface,
                border: `1px solid ${PULSE.border}`,
                boxShadow: '0 30px 60px -25px rgba(33, 39, 33, 0.18), 0 0 0 1px rgba(102, 204, 255, 0.08) inset',
              }}
              data-testid="mod-login-form"
            >
              {/* Cyan corner accents */}
              <span aria-hidden="true" className="absolute left-0 top-0 w-10 h-[3px] rounded-r" style={{ background: PULSE.primary }} />
              <span aria-hidden="true" className="absolute right-0 top-0 w-[3px] h-10 rounded-b" style={{ background: PULSE.primary }} />

              <div className="text-[10px] uppercase font-bold mb-2" style={{ color: PULSE.primaryDeep, letterSpacing: '0.32em' }}>
                Sign in
              </div>
              <h2 className="text-2xl sm:text-[28px] font-extrabold tracking-tight leading-tight" style={{ color: PULSE.black, letterSpacing: '-0.01em' }}>
                Service credentials
              </h2>
              <p className="mt-2 text-[13px] leading-relaxed" style={{ color: PULSE.greyDark }}>
                Use the email issued by your unit, or the site code for shared
                kiosk logins.
              </p>

              <div className="mt-6 space-y-4">
                <label className="block">
                  <span className="text-[10.5px] uppercase font-bold" style={{ color: PULSE.greyDark, letterSpacing: '0.18em' }}>
                    Email or site code
                  </span>
                  <div className="mt-1.5 relative">
                    <Mail size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: PULSE.greyLight }} />
                    <input
                      type="text"
                      autoComplete="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="rank.firstname.lastname@army.mod.local"
                      className="w-full pl-9 pr-3 py-2.5 rounded-lg text-sm focus:outline-none transition-colors"
                      style={{
                        background: PULSE.surface,
                        border: `1px solid ${PULSE.border}`,
                        color: PULSE.black,
                        caretColor: PULSE.primary,
                      }}
                      onFocus={(e) => { e.currentTarget.style.borderColor = PULSE.primary; }}
                      onBlur={(e) => { e.currentTarget.style.borderColor = PULSE.border; }}
                      data-testid="mod-login-email"
                    />
                  </div>
                </label>
                <label className="block">
                  <span className="text-[10.5px] uppercase font-bold" style={{ color: PULSE.greyDark, letterSpacing: '0.18em' }}>
                    Password
                  </span>
                  <div className="mt-1.5 relative">
                    <Lock size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: PULSE.greyLight }} />
                    <input
                      type="password"
                      autoComplete="current-password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="w-full pl-9 pr-3 py-2.5 rounded-lg text-sm focus:outline-none transition-colors"
                      style={{
                        background: PULSE.surface,
                        border: `1px solid ${PULSE.border}`,
                        color: PULSE.black,
                        caretColor: PULSE.primary,
                      }}
                      onFocus={(e) => { e.currentTarget.style.borderColor = PULSE.primary; }}
                      onBlur={(e) => { e.currentTarget.style.borderColor = PULSE.border; }}
                      data-testid="mod-login-password"
                    />
                  </div>
                </label>

                {error && (
                  <div
                    className="rounded-lg text-xs px-3 py-2.5"
                    style={{
                      background: '#FEF2F2',
                      border: '1px solid #FECACA',
                      color: '#B91C1C',
                    }}
                    data-testid="mod-login-error"
                  >
                    {error}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={busy}
                  className="w-full inline-flex items-center justify-center gap-2 rounded-lg font-extrabold py-3 text-[13px] uppercase transition-all disabled:opacity-60"
                  style={{
                    background: PULSE.primary,
                    color: PULSE.black,
                    letterSpacing: '0.22em',
                    boxShadow: '0 8px 22px -8px rgba(102, 204, 255, 0.55), inset 0 1px 0 rgba(255,255,255,0.5)',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = PULSE.primaryHover; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = PULSE.primary; }}
                  data-testid="mod-login-submit"
                >
                  {busy ? <Loader2 size={14} className="animate-spin" /> : <ArrowRight size={14} />}
                  Sign in
                </button>

                <p className="text-[11px] leading-relaxed pt-1" style={{ color: PULSE.greyDark }}>
                  Trouble signing in? Contact your unit PTI or
                  <a
                    href="mailto:support@pulsefitness.ai"
                    className="ml-1 font-semibold underline-offset-2 hover:underline"
                    style={{ color: PULSE.primaryDeep }}
                  >
                    Pulse Fitness Support
                  </a>.
                </p>
              </div>
            </form>

            {/* Notice card */}
            <div
              className="mt-4 rounded-2xl p-4 flex items-start gap-3"
              style={{ background: PULSE.surface, border: `1px solid ${PULSE.border}` }}
              data-testid="mod-login-notice"
            >
              <ShieldCheck size={16} className="shrink-0 mt-0.5" style={{ color: PULSE.primary }} />
              <p className="text-[12px] leading-relaxed" style={{ color: PULSE.greyDark }}>
                Access is monitored and recorded. By signing in you agree to
                the MOD acceptable-use policy. Suspected misuse must be
                reported to your chain of command.
              </p>
            </div>
          </section>
        </div>
      </main>

      {/* Footer — Pulse-dark stripe */}
      <footer
        className="relative z-10 px-5 sm:px-10 py-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3"
        style={{ background: PULSE.black, color: '#FFFFFF' }}
      >
        <div className="flex items-center gap-3">
          <img
            src={PULSE_LOGO}
            alt="Pulse Fitness"
            className="h-7 w-auto rounded object-contain"
            style={{ background: PULSE.surface, padding: '3px' }}
          />
          <div className="text-[10px] uppercase font-bold" style={{ letterSpacing: '0.28em', color: PULSE.greyLight }}>
            © {new Date().getFullYear()} Pulse Fitness · MOD Service Portal
          </div>
        </div>
        <div className="text-[10px] uppercase font-bold" style={{ color: PULSE.primary, letterSpacing: '0.28em' }}>
          UK Restricted · Official-Sensitive
        </div>
      </footer>
    </div>
  );
}
