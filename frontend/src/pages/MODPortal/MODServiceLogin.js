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
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '@/App';
import { useSignedOutNotice } from '@/hooks/useSignedOutNotice';import { Loader2, ShieldCheck, ArrowRight, Lock, Mail, CheckCircle2, Eye, EyeOff } from 'lucide-react';
import { useSeo } from '@/utils/seo';
import { COMMERCIAL_URL } from '@/utils/portalMode';

// ── Official artwork (user-supplied) ──────────────────────────────
const _PULSE_LOGO = 'https://customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/iscy9t7o_Pulse%20Fitness%20Primary%20Logo%20Badge%20RGB.jpg';
const MOD_LOGO   = 'https://customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/t8x9pm0p_122237.png';
const ARMY_LOGO  = 'https://customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/so1rjamy_122250.webp';
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
  const { prefillEmail } = useSignedOutNotice();
  const [email, setEmail] = useState(prefillEmail);
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  // A commercial/staff account tried to sign in on the MOD portal — show a
  // friendly block that points them to pulsefitness.ai rather than a raw 403.
  const [blockedCommercial, setBlockedCommercial] = useState(false);
  // Iter 216h118 — Mandatory MFA flow handling for MOD HQ (mod_org /
  // mod_branch) accounts. The /auth/login response either contains a
  // direct ``token`` or one of:
  //   • requires_mfa            (TOTP challenge, user already enrolled)
  //   • requires_mfa_enrolment  (first login — show QR + verify)
  // Without this we used to blindly call login(undefined, undefined),
  // which stored "undefined" in localStorage.token and triggered the
  // session-expired toast on the very next /api/* call.
  const [mfaStage, setMfaStage] = useState(null); // null | 'verify' | 'enrol_setup' | 'enrol_confirm'
  const [mfaTempToken, setMfaTempToken] = useState('');
  const [mfaCode, setMfaCode] = useState('');
  const [mfaSecret, setMfaSecret] = useState('');
  const [mfaQrUrl, setMfaQrUrl] = useState('');
  const [_mfaProvisioningUri, setMfaProvisioningUri] = useState('');

  const apiBase = `${process.env.REACT_APP_BACKEND_URL}/api`;

  const completeLoginFromResponse = (data) => {
    if (!data?.token) {
      setError('Sign-in succeeded but no token was returned. Try again.');
      return;
    }
    login(data.token, data.user, data.refresh_token);
    navigate('/dashboard');
  };

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!email || !password) { setError('Email or site code and password required'); return; }
    setError(''); setBusy(true);
    try {
      const r = await axios.post(`${apiBase}/auth/login`, {
        email: email.trim().toLowerCase(),
        password,
        portal: 'mod',
      });
      const data = r.data || {};
      // ── MFA challenge (already enrolled) ──
      if (data.requires_mfa && data.temp_token) {
        setMfaTempToken(data.temp_token);
        setMfaStage('verify');
        return;
      }
      // ── Mandatory enrolment (MOD HQ first login) ──
      if (data.requires_mfa_enrolment && data.temp_token) {
        setMfaTempToken(data.temp_token);
        setMfaStage('enrol_setup');
        try {
          const setup = await axios.post(`${apiBase}/auth/mfa/enrol/setup`, {
            temp_token: data.temp_token,
          });
          setMfaSecret(setup.data?.secret || '');
          setMfaQrUrl(setup.data?.qrcode_data_url || '');
          setMfaProvisioningUri(setup.data?.provisioning_uri || '');
          setMfaStage('enrol_confirm');
        } catch (err) {
          setError(err.response?.data?.detail || 'Failed to start MFA enrolment');
        }
        return;
      }
      completeLoginFromResponse(data);
    } catch (err) {
      const status = err.response?.status;
      const detail = err.response?.data?.detail || '';
      // Commercial/staff account on the MOD portal → friendly redirect notice.
      if (status === 403 && /MOD Service Portal/i.test(detail)) {
        setBlockedCommercial(true);
      } else {
        setError(detail || 'Invalid credentials');
      }
    } finally {
      setBusy(false);
    }
  };

  const verifyMfaCode = async (e) => {
    e?.preventDefault?.();
    if (!mfaCode || mfaCode.length < 6) { setError('Enter the 6-digit code'); return; }
    setError(''); setBusy(true);
    try {
      const r = await axios.post(`${apiBase}/auth/mfa/verify`, {
        temp_token: mfaTempToken,
        code: mfaCode.trim(),
      });
      completeLoginFromResponse(r.data || {});
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid code');
    } finally {
      setBusy(false);
    }
  };

  const completeMfaEnrolment = async (e) => {
    e?.preventDefault?.();
    if (!mfaCode || mfaCode.length < 6) { setError('Enter the 6-digit code from your authenticator app'); return; }
    setError(''); setBusy(true);
    try {
      const r = await axios.post(`${apiBase}/auth/mfa/enrol/complete`, {
        temp_token: mfaTempToken,
        code: mfaCode.trim(),
      });
      completeLoginFromResponse(r.data || {});
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid code');
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
      {/* Top brand bar — matches pulsefitness.ai landing header (black) with
          the MoD logo inverted to white so it stands out. */}
      <header
        className="relative z-10 flex items-center justify-between px-5 sm:px-10 py-4 gap-4"
        style={{ background: '#000000', borderBottom: '1px solid rgba(255,255,255,0.1)' }}
      >
        <div className="flex items-center gap-3 min-w-0" data-testid="mod-brand-mod">
          <img
            src={MOD_LOGO}
            alt="UK Ministry of Defence"
            className="h-12 sm:h-14 w-auto object-contain"
            style={{ objectPosition: 'left center', maxWidth: '260px', background: 'transparent', filter: 'brightness(0) invert(1)' }}
            data-testid="mod-logo-image"
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
                  {/* Logo plate */}
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
                  {/* Service name */}
                  <div className="px-4 py-3">
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
              onSubmit={mfaStage === 'verify' ? verifyMfaCode : (mfaStage === 'enrol_confirm' ? completeMfaEnrolment : submit)}
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
                {blockedCommercial ? 'Wrong portal' : (mfaStage ? 'Multi-factor' : 'Sign in')}
              </div>
              <h2 className="text-2xl sm:text-[28px] font-extrabold tracking-tight leading-tight" style={{ color: PULSE.black, letterSpacing: '-0.01em' }}>
                {blockedCommercial && 'This portal is for MOD sites'}
                {!blockedCommercial && mfaStage === 'verify' && 'Enter authenticator code'}
                {!blockedCommercial && mfaStage === 'enrol_confirm' && 'Enrol MFA'}
                {!blockedCommercial && mfaStage === 'enrol_setup' && 'Preparing MFA…'}
                {!blockedCommercial && !mfaStage && 'Service credentials'}
              </h2>
              <p className="mt-2 text-[13px] leading-relaxed" style={{ color: PULSE.greyDark }}>
                {blockedCommercial && 'Your account is a standard Pulse Fitness account, not a MOD Service account. Please sign in on the main Pulse Fitness portal instead.'}
                {!blockedCommercial && mfaStage === 'verify' && 'Open your authenticator app and enter the 6-digit code for this account.'}
                {!blockedCommercial && mfaStage === 'enrol_confirm' && 'Scan the QR with Google Authenticator / Authy, then enter the 6-digit code.'}
                {!blockedCommercial && mfaStage === 'enrol_setup' && 'Generating QR code…'}
                {!blockedCommercial && !mfaStage && 'Use the email issued by your unit, or the site code for shared kiosk logins.'}
              </p>

              {/* ── Commercial/staff account signed in on the MOD portal ── */}
              {blockedCommercial && (
                <div className="mt-6 space-y-4" data-testid="mod-login-commercial-block">
                  <a
                    href={COMMERCIAL_URL}
                    className="w-full inline-flex items-center justify-center gap-2 rounded-lg font-extrabold py-3 text-[13px] uppercase transition-all"
                    style={{
                      background: PULSE.primary,
                      color: PULSE.black,
                      letterSpacing: '0.14em',
                      boxShadow: '0 8px 22px -8px rgba(102, 204, 255, 0.55), inset 0 1px 0 rgba(255,255,255,0.5)',
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.background = PULSE.primaryHover; }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = PULSE.primary; }}
                    data-testid="mod-login-commercial-cta"
                  >
                    <ArrowRight size={14} /> Go to Pulse Fitness
                  </a>
                  <button
                    type="button"
                    onClick={() => { setBlockedCommercial(false); setError(''); setPassword(''); }}
                    className="w-full text-[11px] font-semibold underline-offset-2 hover:underline"
                    style={{ color: PULSE.greyDark }}
                    data-testid="mod-login-commercial-back"
                  >
                    Back to MOD sign in
                  </button>
                </div>
              )}

              {/* ── Stage: enrol_confirm — QR + secret + code input ── */}
              {mfaStage === 'enrol_confirm' && (
                <div className="mt-6 space-y-4">
                  <div
                    className="rounded-xl p-4 flex flex-col items-center gap-3"
                    style={{ background: '#F8F9FA', border: `1px solid ${PULSE.border}` }}
                    data-testid="mod-login-mfa-qr"
                  >
                    {mfaQrUrl ? (
                      <img src={mfaQrUrl} alt="MFA QR" className="w-44 h-44" />
                    ) : (
                      <Loader2 size={24} className="animate-spin" style={{ color: PULSE.primary }} />
                    )}
                    {mfaSecret && (
                      <div className="text-center">
                        <div className="text-[10px] uppercase font-bold" style={{ color: PULSE.greyDark, letterSpacing: '0.16em' }}>
                          Manual secret
                        </div>
                        <code className="text-[12px] font-mono break-all" style={{ color: PULSE.black }}>{mfaSecret}</code>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* ── Stage: verify or enrol_confirm — 6-digit input ── */}
              {(mfaStage === 'verify' || mfaStage === 'enrol_confirm') && (
                <div className="mt-4">
                  <label className="block">
                    <span className="text-[10.5px] uppercase font-bold" style={{ color: PULSE.greyDark, letterSpacing: '0.18em' }}>
                      6-digit code
                    </span>
                    <input
                      type="text"
                      inputMode="numeric"
                      pattern="[0-9]*"
                      maxLength={6}
                      autoFocus
                      value={mfaCode}
                      onChange={(e) => setMfaCode(e.target.value.replace(/[^0-9]/g, ''))}
                      placeholder="123456"
                      className="mt-1.5 w-full px-3 py-3 rounded-lg text-center text-xl font-mono tracking-[0.4em] focus:outline-none"
                      style={{
                        background: PULSE.surface,
                        border: `1px solid ${PULSE.border}`,
                        color: PULSE.black,
                        caretColor: PULSE.primary,
                      }}
                      onFocus={(e) => { e.currentTarget.style.borderColor = PULSE.primary; }}
                      onBlur={(e) => { e.currentTarget.style.borderColor = PULSE.border; }}
                      data-testid="mod-login-mfa-code"
                    />
                  </label>
                </div>
              )}

              {/* ── Stage: default — email + password ── */}
              {!mfaStage && !blockedCommercial && (
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
                      type={showPassword ? 'text' : 'password'}
                      autoComplete="current-password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="w-full pl-9 pr-10 py-2.5 rounded-lg text-sm focus:outline-none transition-colors"
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
                    <button
                      type="button"
                      onClick={() => setShowPassword((v) => !v)}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 rounded transition-colors hover:bg-black/5"
                      style={{ color: PULSE.greyLight }}
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                      aria-pressed={showPassword}
                      title={showPassword ? 'Hide password' : 'Show password'}
                      data-testid="mod-login-password-toggle"
                    >
                      {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                </label>
              </div>
              )}

              <div className="mt-4 space-y-4">
                {error && !blockedCommercial && (
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
                  disabled={busy || mfaStage === 'enrol_setup'}
                  className="w-full inline-flex items-center justify-center gap-2 rounded-lg font-extrabold py-3 text-[13px] uppercase transition-all disabled:opacity-60"
                  style={{
                    background: PULSE.primary,
                    color: PULSE.black,
                    letterSpacing: '0.22em',
                    boxShadow: '0 8px 22px -8px rgba(102, 204, 255, 0.55), inset 0 1px 0 rgba(255,255,255,0.5)',
                    display: blockedCommercial ? 'none' : undefined,
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = PULSE.primaryHover; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = PULSE.primary; }}
                  data-testid="mod-login-submit"
                >
                  {busy ? <Loader2 size={14} className="animate-spin" /> : <ArrowRight size={14} />}
                  {mfaStage === 'verify' && 'Verify code'}
                  {mfaStage === 'enrol_confirm' && 'Enrol & sign in'}
                  {mfaStage === 'enrol_setup' && 'Preparing…'}
                  {!mfaStage && 'Sign in'}
                </button>

                {mfaStage && (
                  <button
                    type="button"
                    onClick={() => {
                      setMfaStage(null); setMfaCode(''); setMfaTempToken('');
                      setMfaSecret(''); setMfaQrUrl(''); setMfaProvisioningUri('');
                      setError('');
                    }}
                    className="w-full text-[11px] font-semibold underline-offset-2 hover:underline"
                    style={{ color: PULSE.greyDark }}
                    data-testid="mod-login-mfa-cancel"
                  >
                    Use a different account
                  </button>
                )}

                <p className="text-[11px] leading-relaxed pt-1" style={{ color: PULSE.greyDark }}>
                  Trouble signing in? Contact your unit PTI or
                  <a
                    href="mailto:support@modservice.pulsefitness.com"
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
        className="relative z-10 px-5 sm:px-10 py-5"
        style={{ background: PULSE.black, color: '#FFFFFF' }}
      >
        <div className="text-[10px] uppercase font-bold" style={{ letterSpacing: '0.28em', color: PULSE.greyLight }}>
          © {new Date().getFullYear()} MOD Service Portal
        </div>
      </footer>
    </div>
  );
}
