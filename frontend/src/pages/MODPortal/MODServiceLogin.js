/**
 * MOD Service Portal — Pulse Fitness branded landing & login.
 * (Iter 216h113 update — corrections from user feedback:
 *   • Official MOD / Army / Navy / RAF logos in place of the
 *     inline SVG approximations.
 *   • Stripped the made-up service taglines — only the official
 *     service name appears.
 *   • Removed all CAPEX references from the marketing copy
 *     (end-users don't see CAPEX; that's an HQ-only console).
 *   • Removed the false stats strip ("37+ sites onboarded",
 *     "UK-only data residency"). MOD relationship is integrity-first.
 *   • Portal is global, not UK-only.
 *
 * Identity remains Pulse Fitness (white surfaces, cyan accent
 * #66CCFF, dark Pulse text #212721) because the MOD are Pulse
 * customers.
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '@/App';
import { Loader2, ShieldCheck, ArrowRight, Lock, Mail, CheckCircle2 } from 'lucide-react';
import { useSeo } from '@/utils/seo';

// ── Official artwork (user-supplied) ──────────────────────────────
const PULSE_LOGO = 'https://customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/iscy9t7o_Pulse%20Fitness%20Primary%20Logo%20Badge%20RGB.jpg';
const MOD_LOGO   = 'https://customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/t8x9pm0p_122237.png';
const ARMY_LOGO  = 'https://customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/oygnl6eo_122238.png';
const NAVY_LOGO  = 'https://customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/72uz5alx_122239.png';
const RAF_LOGO   = 'https://customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/do80dken_122240.png';

// ── Pulse brand tokens ────────────────────────────────────────────
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
// No marketing tagline — each service speaks for itself via the
// official logo. Tile background matches the logo's native canvas
// so the badge sits cleanly without a fake card.
const SERVICES = [
  { id: 'army', name: 'British Army',    logo: ARMY_LOGO, bg: '#000000' },
  { id: 'navy', name: 'Royal Navy',      logo: NAVY_LOGO, bg: '#0A1F44' },
  { id: 'raf',  name: 'Royal Air Force', logo: RAF_LOGO,  bg: '#FFFFFF' },
];

// ── Page ──────────────────────────────────────────────────────────

export default function MODServiceLogin() {
  useSeo({
    title: 'MOD Service Portal — Pulse Fitness',
    description:
      'Pulse Fitness Service Portal for the UK Ministry of Defence. Secure access for British Army, Royal Navy, and Royal Air Force gym sites.',
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
      {/* OFFICIAL-SENSITIVE classification stripe */}
      <div
        className="relative z-20 text-center text-[10px] uppercase font-bold py-1.5"
        style={{ background: PULSE.black, color: PULSE.primary, letterSpacing: '0.32em' }}
        data-testid="mod-classification-stripe"
      >
        UK OFFICIAL · SENSITIVE
      </div>

      {/* Top brand bar — MOD logo top-left, Pulse Fitness top-right */}
      <header
        className="relative z-10 flex items-center justify-between px-5 sm:px-10 py-4 gap-4"
        style={{ background: PULSE.surface, borderBottom: `1px solid ${PULSE.border}` }}
      >
        <div className="flex items-center gap-3 min-w-0" data-testid="mod-brand-mod">
          <img
            src={MOD_LOGO}
            alt="UK Ministry of Defence"
            className="h-12 sm:h-14 w-auto object-contain"
            style={{ objectPosition: 'left center', maxWidth: '260px' }}
            data-testid="mod-logo-image"
          />
        </div>
        <div className="flex items-center gap-3 shrink-0" data-testid="mod-brand-pulse">
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
                border: '1px solid rgba(102, 204, 255, 0.4)',
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
              The Pulse Fitness Service Portal for the Ministry of
              Defence — secure fault reporting and equipment registers
              for every MOD gym site, built for Service Personnel.
            </p>

            {/* Service brand panels — official logos, no fake taglines */}
            <div className="mt-9 grid grid-cols-1 sm:grid-cols-3 gap-3" data-testid="mod-login-services">
              {SERVICES.map((s) => (
                <article
                  key={s.id}
                  className="relative overflow-hidden rounded-2xl transition-all duration-200 hover:-translate-y-0.5"
                  style={{
                    background: PULSE.surface,
                    border: `1px solid ${PULSE.border}`,
                    boxShadow: '0 4px 16px -8px rgba(33, 39, 33, 0.08)',
                  }}
                  data-testid={`mod-service-tile-${s.id}`}
                >
                  {/* Logo plate — uses the service's native canvas
                      colour so the official badge sits correctly. */}
                  <div
                    className="flex items-center justify-center px-6 py-5"
                    style={{ background: s.bg, minHeight: 120 }}
                  >
                    <img
                      src={s.logo}
                      alt={s.name}
                      className="max-h-20 w-auto object-contain"
                      data-testid={`mod-service-logo-${s.id}`}
                    />
                  </div>
                  {/* Service name only — no tagline */}
                  <div className="px-4 py-3">
                    <div
                      className="text-[10px] uppercase font-bold mb-0.5"
                      style={{ color: PULSE.primaryDeep, letterSpacing: '0.22em' }}
                    >
                      Service
                    </div>
                    <div className="text-sm font-extrabold leading-tight" style={{ color: PULSE.black }}>
                      {s.name}
                    </div>
                  </div>
                </article>
              ))}
            </div>

            {/* Truthful feature bullets — CAPEX intentionally not
                mentioned here; end users won't see that console. */}
            <ul className="mt-9 space-y-2.5 max-w-lg">
              {[
                'Single sign-in for kiosk and personal credentials',
                'Fault wizard ticketed straight to your maintenance team',
                'Equipment register at every site — searchable by fault history',
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
                    style={{ background: '#FEF2F2', border: '1px solid #FECACA', color: '#B91C1C' }}
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
                Access is monitored and recorded. By signing in you agree
                to the MOD acceptable-use policy. Suspected misuse must be
                reported to your chain of command.
              </p>
            </div>
          </section>
        </div>
      </main>

      {/* Footer */}
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
          UK Official · Sensitive
        </div>
      </footer>
    </div>
  );
}
