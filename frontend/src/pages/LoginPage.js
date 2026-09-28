/**
 * Pulse Fitness dedicated /login page (replaces the legacy dark HomePage).
 *
 * A focused, Pulse Fitness-branded sign-in surface that lives on the same light
 * marketing aesthetic as MarketingHome. Wraps a single email/password form
 * with the gym-floor kiosk fallback (username login) so on-site terminals
 * keep working.
 */
import { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { ArrowLeft, ArrowRight, Eye, EyeOff, Loader2, ShieldCheck } from 'lucide-react';

import { useAuth } from '@/App';
import BrandWordmark from '@/components/shared/BrandWordmark';
import { notify, useInlineBanner } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function LoginPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();
  const [searchParams] = useSearchParams();
  // Iter 274 — pre-fill email when arriving with ?email= (e.g. engineer sign-out).
  const [email, setEmail] = useState(() => searchParams.get('email') || '');
  const [password, setPassword] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);
  // TOTP MFA second step — kept in memory only (never persisted). Set when
  // /auth/login responds with {requires_mfa, temp_token} for an MFA-enrolled
  // account (e.g. the master admin who has enabled an authenticator).
  const [mfa, setMfa] = useState(null); // { tempToken, email }
  const [mfaCode, setMfaCode] = useState('');
  const [mfaBusy, setMfaBusy] = useState(false);
  const [mfaErr, setMfaErr] = useState('');
  // Forced enrolment DURING login (when ENFORCE_MASTER_ADMIN_MFA is on and the
  // account isn't enrolled). All memory-only; temp_token never persisted.
  const [enrol, setEnrol] = useState(null); // { tempToken, email, secret, qrDataUrl }
  const [enrolCode, setEnrolCode] = useState('');
  const [enrolBusy, setEnrolBusy] = useState(false);
  const [enrolErr, setEnrolErr] = useState('');
  const [enrolBackup, setEnrolBackup] = useState(null); // { codes:[], data:{token,user} }
  const [enrolSaved, setEnrolSaved] = useState(false);
  const { banner, _show, clear } = useInlineBanner({ autoDismiss: false });

  // Resume an MFA challenge handed off from the homepage LoginModal (which has
  // no MFA UI). The temp_token arrives via in-memory router state only.
  useEffect(() => {
    const ch = location.state?.mfaChallenge;
    if (!ch || !ch.temp_token) return;
    // Prevent replay on refresh / back-navigation.
    window.history.replaceState({}, document.title);
    if (ch.email) setEmail(ch.email);
    if (ch.kind === 'verify') {
      setMfa({ tempToken: ch.temp_token, email: ch.email || '' });
    } else {
      (async () => {
        try {
          const setup = await axios.post(`${API}/auth/mfa/enrol/setup`, { temp_token: ch.temp_token });
          setEnrol({
            tempToken: ch.temp_token,
            email: ch.email || '',
            secret: setup.data.secret || '',
            qrDataUrl: setup.data.qrcode_data_url || '',
          });
        } catch { /* fall back to the password form */ }
      })();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Iter 274 — confirm sign-out: show a success toast when arriving from a
  // sign-out. The password field auto-focuses (autoFocus={!!email}) since the
  // email is already pre-filled.
  useEffect(() => {
    if (searchParams.get('signedout') === '1') {
      notify.success('Signed out successfully');
      // strip the flag so a refresh doesn't re-toast
      const url = new URL(window.location.href);
      url.searchParams.delete('signedout');
      window.history.replaceState({}, '', url.pathname + url.search);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Iter 216h68 — `?next=/some/path` lets the SessionResumedBanner
  // (and any other deep-link sender) bounce the user back to where
  // they were AFTER successful re-auth. We only honour relative
  // paths to avoid open-redirect abuse.
  //
  // Iter 220av · F-05 — tightened against the famous open-redirect
  // bypasses: protocol-relative `//evil.com`, backslash tricks
  // `/\evil.com`, control chars, embedded scheme prefixes.
  const nextParam = (() => {
    try {
      const sp = new URLSearchParams(location.search);
      const raw = sp.get('next');
      if (!raw) return null;
      if (raw.length > 512) return null;
      // Reject anything that contains a backslash, CRLF, NUL or tab.
      if (/[\\\r\n\t\0]/.test(raw)) return null;
      // Must be a single-leading-slash relative path.
      if (!raw.startsWith('/') || raw.startsWith('//')) return null;
      // Must not look like a URI scheme.
      if (/^[A-Za-z][A-Za-z0-9+\-.]*:/.test(raw)) return null;
      return raw;
    } catch { /* ignore */ }
    return null;
  })();

  const handleSubmit = async (e) => {
    e.preventDefault();
    clear();
    setLoading(true);
    try {
      const { data } = await axios.post(`${API}/auth/login`, { email, password });
      // TOTP MFA gate: an MFA-enrolled account gets a temp_token, NOT a real
      // token. Branch on requires_mfa BEFORE the token check so enabling MFA
      // never locks the account out of login.
      if (data?.requires_mfa === true) {
        if (!data.temp_token) throw new Error('MFA challenge incomplete');
        setMfa({ tempToken: data.temp_token, email: data.user?.email || email });
        setMfaCode('');
        setMfaErr('');
        setLoading(false);
        return;
      }
      if (data?.requires_mfa_enrolment === true) {
        if (!data.temp_token) throw new Error('MFA enrolment incomplete');
        try {
          const setup = await axios.post(`${API}/auth/mfa/enrol/setup`, { temp_token: data.temp_token });
          setEnrol({
            tempToken: data.temp_token,
            email: data.user?.email || email,
            secret: setup.data.secret || '',
            qrDataUrl: setup.data.qrcode_data_url || '',
          });
          setEnrolCode('');
          setEnrolErr('');
          setEnrolSaved(false);
        } catch (e2) {
          notifyApiError(notify, e2, 'Could not start MFA enrolment');
        }
        setLoading(false);
        return;
      }
      if (!data?.token) throw new Error('No token returned');
      routeAfterLogin(data);
    } catch (err) {
      // Gym-floor fallback — same form, but POST against /gym-floor/login
      // when the field looks like a kiosk username (no '@') and the
      // standard portal returned 401.
      if (err.response?.status === 401 && email && !email.includes('@')) {
        try {
          const gf = await axios.post(`${API}/gym-floor/login`, { username: email, password });
          const session = { ...gf.data, logged_in_at: new Date().toISOString() };
          localStorage.setItem('gym_floor_session', JSON.stringify(session));
          navigate('/gym-floor', { replace: true });
          return;
        } catch (_gfErr) { /* fall through */ }
      }
      notifyApiError(notify, err, 'Invalid credentials');
    } finally {
      setLoading(false);
    }
  };

  // Second step: verify the authenticator (or backup) code against the
  // short-lived temp_token, then complete login with the returned real token.
  const submitMfa = async (e) => {
    e?.preventDefault?.();
    if (mfaBusy || !mfa) return;
    const code = mfaCode.replace(/[\s-]/g, '');
    if (!/^(?:\d{6}|[A-Za-z0-9]{8,})$/.test(code)) {
      setMfaErr('Enter your 6-digit authenticator code or an 8-character backup code.');
      return;
    }
    setMfaBusy(true);
    setMfaErr('');
    try {
      const { data } = await axios.post(`${API}/auth/mfa/verify`, {
        temp_token: mfa.tempToken, code,
      });
      if (!data?.token) throw new Error('No token returned');
      routeAfterLogin(data);
    } catch (err) {
      const status = err.response?.status;
      if (status === 429) {
        setMfaErr('Too many attempts. Please wait a moment before trying again.');
      } else if (status === 401 || status === 400) {
        setMfaErr('Invalid or expired code. Try again, or start over.');
      } else {
        setMfaErr('Verification failed. Please try again.');
      }
      setMfaBusy(false);
    }
  };

  // Forced enrolment (login step 2b): verify first TOTP, enable MFA, and get
  // a verified session + backup codes in one call. We hold routing until the
  // user acknowledges saving the backup codes.
  const submitEnrol = async (e) => {
    e?.preventDefault?.();
    if (enrolBusy || !enrol) return;
    const code = enrolCode.replace(/\D/g, '');
    if (code.length !== 6) {
      setEnrolErr('Enter the 6-digit code from your authenticator app.');
      return;
    }
    setEnrolBusy(true);
    setEnrolErr('');
    try {
      const { data } = await axios.post(`${API}/auth/mfa/enrol/complete`, {
        temp_token: enrol.tempToken, code,
      });
      if (!data?.token) throw new Error('No token returned');
      setEnrolBackup({ codes: data.backup_codes || [], data });
    } catch (err) {
      const status = err.response?.status;
      setEnrolErr((status === 400 || status === 401)
        ? 'Invalid or expired code. Please try again.'
        : 'Verification failed. Please try again.');
      setEnrolBusy(false);
    }
  };

  const finishEnrol = () => {
    const d = enrolBackup?.data;
    setEnrol(null); setEnrolBackup(null); setEnrolCode(''); setEnrolSaved(false);
    if (d) routeAfterLogin(d);
  };

  // Shared post-login routing (used by both the password and MFA steps).
  const routeAfterLogin = (data) => {
      login(data.token, data.user);
      // Iter 216h216 — track lifetime login count for NPS trust-gating.
      try {
        const n = Number(localStorage.getItem('login_count') || 0);
        localStorage.setItem('login_count', String(n + 1));
      } catch (_) { /* private-mode storage failure — non-blocking */ }
      const u = data.user || {};
      if (u.must_change_password) {
        navigate('/change-password', { replace: true });
        return;
      }
      if (u.role === 'dealer_user') {
        navigate('/dealer-portal', { replace: true });
        return;
      }
      if (u.role === 'logistics') {
        navigate('/logistics', { replace: true });
        return;
      }
      const fallback = (u.is_master_admin || u.is_pulse_admin)
        ? '/master-admin'
        : u.is_service_desk
          // Iter 250 — Service-Desk-nominated users go straight to the desk.
          // Iter 253 — self-serve providers finish the setup wizard first.
          ? (u.service_ops_setup_complete === false ? '/service-desk/setup' : '/service-desk')
          : (u.is_partner_engineer || u.account_type === 'partner_engineer' || u.role === 'engineer_partner')
            ? '/partner-engineer'
            : (u.account_type === 'lite' || u.account_type === 'pulse_pro'
               || u.account_type === 'mod_site' || u.account_type === 'mod_branch' || u.account_type === 'mod_org')
              ? '/pulse'
              // Non-dedicated Pulse Fitness staff/operators land on the area
              // selector (/launch), which lists ONLY the areas they're granted
              // and forwards automatically when there's just one. This stops a
              // CRM-only (or any non-Operations) staffer being dropped into the
              // Operations portal they have no access to.
              : '/launch';
      navigate(nextParam || fallback, { replace: true });
  };

  return (
    <div
      className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-100 flex flex-col theme-gymaxis"
      data-theme="light"
      data-testid="gx-login-page"
    >
      {/* Top bar — solid black, on-brand with pulsefitness.com */}
      <header data-theme="dark" className="px-6 lg:px-10 h-16 flex items-center justify-between border-b border-white/10 bg-black">
        <Link to="/" className="flex items-center" data-testid="gx-login-logo">
          <BrandWordmark height={36} />
        </Link>
        <div className="flex items-center gap-4">
          <select
            value={['en', 'fr', 'de'].includes((i18n.language || 'en').slice(0, 2)) ? (i18n.language || 'en').slice(0, 2) : 'en'}
            onChange={(e) => i18n.changeLanguage(e.target.value)}
            aria-label="Language"
            className="text-xs font-bold text-white/80 bg-transparent border border-white/25 rounded-full px-2 py-1 cursor-pointer hover:border-white/60 focus:outline-none"
            data-testid="gx-login-lang-select"
          >
            <option className="text-slate-900" value="en">EN</option>
            <option className="text-slate-900" value="fr">FR</option>
            <option className="text-slate-900" value="de">DE</option>
          </select>
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-white/80 hover:text-white"
            data-testid="gx-login-back"
          >
            <ArrowLeft size={13} /> {t('auth.back_home', 'Back to home')}
          </Link>
        </div>
      </header>

      {/* Form card */}
      <main className="flex-1 flex items-center justify-center px-4 pt-10 pb-40 sm:pb-44">
        <div
          className="w-full max-w-md rounded-3xl bg-white border border-slate-200 shadow-[0_30px_80px_-40px_rgba(15,23,42,0.25)] p-8 sm:p-10"
          data-testid="gx-login-card"
        >
          <div className="mb-6">
            <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-slate-900">{t('auth.login_title', 'Welcome back')}</h1>
            <p className="mt-1 text-sm text-slate-500">{t('auth.subtitle', 'Sign in to your Pulse Fitness portal.')}</p>
          </div>

          {banner && <div className="mb-3">{banner}</div>}

          {enrolBackup ? (
            <div className="space-y-4" data-testid="gx-login-enrol-backup">
              <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-3">
                <p className="text-sm font-semibold text-emerald-900">Two-factor enabled</p>
                <p className="text-xs text-emerald-700 mt-0.5">Save these backup codes — each works once if you lose your authenticator. They won't be shown again.</p>
              </div>
              <pre className="rounded-xl bg-slate-50 border border-slate-200 p-3 text-sm font-mono grid grid-cols-2 gap-1 text-slate-800" data-testid="gx-login-enrol-codes">
                {(enrolBackup.codes || []).join('\n')}
              </pre>
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input type="checkbox" checked={enrolSaved} onChange={(e) => setEnrolSaved(e.target.checked)} data-testid="gx-login-enrol-saved" />
                I've saved my backup codes
              </label>
              <button
                type="button"
                onClick={finishEnrol}
                disabled={!enrolSaved}
                className="gx-cta w-full h-11 rounded-xl font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-60"
                data-testid="gx-login-enrol-continue"
              >
                Continue <ArrowRight size={14} />
              </button>
            </div>
          ) : enrol ? (
            <form onSubmit={submitEnrol} className="space-y-4" data-testid="gx-login-enrol-form">
              <div className="flex items-center gap-3 rounded-xl bg-slate-50 border border-slate-200 p-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--gx-brand-from)]/15">
                  <ShieldCheck size={18} className="text-[var(--gx-brand-from)]" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-slate-900">Set up two-factor authentication</p>
                  <p className="text-xs text-slate-500 truncate">Required for {enrol.email}. Scan the code, then enter the 6 digits.</p>
                </div>
              </div>
              {enrol.qrDataUrl && (
                <img src={enrol.qrDataUrl} alt="Scan in your authenticator app" className="w-40 h-40 mx-auto rounded-lg border border-slate-200 p-2 bg-white" data-testid="gx-login-enrol-qr" />
              )}
              <div>
                <p className="text-[11px] text-slate-500 mb-1">Can't scan? Enter this key manually:</p>
                <code className="block break-all rounded-lg bg-slate-100 px-3 py-2 text-xs font-mono text-slate-800" data-testid="gx-login-enrol-secret">{enrol.secret}</code>
              </div>
              <input
                autoFocus
                inputMode="numeric"
                maxLength={6}
                value={enrolCode}
                onChange={(e) => setEnrolCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                className="w-full h-11 px-3 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 text-center text-lg tracking-[0.35em] placeholder:tracking-normal placeholder:text-slate-400 focus:outline-none focus:border-[var(--gx-brand-from)] focus:bg-white transition"
                placeholder="123456"
                data-testid="gx-login-enrol-code"
              />
              {enrolErr && (
                <div className="rounded-xl bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-600" data-testid="gx-login-enrol-error">{enrolErr}</div>
              )}
              <button
                type="submit"
                disabled={enrolBusy || enrolCode.length !== 6}
                className="gx-cta w-full h-11 rounded-xl font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-60"
                data-testid="gx-login-enrol-submit"
              >
                {enrolBusy ? <><Loader2 size={14} className="animate-spin" /> Verifying…</> : <>Verify & enable <ArrowRight size={14} /></>}
              </button>
              <button
                type="button"
                onClick={() => { setEnrol(null); setEnrolCode(''); setEnrolErr(''); }}
                className="w-full text-xs font-semibold text-slate-500 hover:text-slate-900"
                data-testid="gx-login-enrol-startover"
              >
                Start over
              </button>
            </form>
          ) : mfa ? (
            <form onSubmit={submitMfa} className="space-y-4" data-testid="gx-login-mfa-form">
              <div className="flex items-center gap-3 rounded-xl bg-slate-50 border border-slate-200 p-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--gx-brand-from)]/15">
                  <ShieldCheck size={18} className="text-[var(--gx-brand-from)]" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-slate-900">Two-factor verification</p>
                  <p className="text-xs text-slate-500 truncate">Enter the code from your authenticator for {mfa.email}</p>
                </div>
              </div>
              <div>
                <label className="text-[11px] font-bold uppercase tracking-[0.16em] text-slate-500 mb-1.5 block">
                  Authenticator or backup code
                </label>
                <input
                  autoFocus
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={32}
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value)}
                  className="w-full h-11 px-3 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 text-center text-lg tracking-[0.35em] placeholder:tracking-normal placeholder:text-slate-400 focus:outline-none focus:border-[var(--gx-brand-from)] focus:bg-white transition"
                  placeholder="123456"
                  data-testid="gx-login-mfa-code"
                />
              </div>
              {mfaErr && (
                <div className="rounded-xl bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-600" data-testid="gx-login-mfa-error">
                  {mfaErr}
                </div>
              )}
              <button
                type="submit"
                disabled={mfaBusy || !mfaCode.trim()}
                className="gx-cta w-full h-11 rounded-xl font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-60"
                data-testid="gx-login-mfa-submit"
              >
                {mfaBusy ? <><Loader2 size={14} className="animate-spin" /> Verifying…</> : <>Verify & sign in <ArrowRight size={14} /></>}
              </button>
              <button
                type="button"
                onClick={() => { setMfa(null); setMfaCode(''); setMfaErr(''); }}
                className="w-full text-xs font-semibold text-slate-500 hover:text-slate-900"
                data-testid="gx-login-mfa-startover"
              >
                Start over
              </button>
            </form>
          ) : (
          <form onSubmit={handleSubmit} className="space-y-4" data-testid="gx-login-form">
            <div>
              <label className="text-[11px] font-bold uppercase tracking-[0.16em] text-slate-500 mb-1.5 block">
                {t('auth.email_or_kiosk', 'Email or kiosk username')}
              </label>
              <input
                type="email"
                autoCapitalize="none"
                autoCorrect="off"
                autoComplete="email"
                inputMode="email"
                spellCheck={false}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus={!email}
                className="w-full h-11 px-3 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-[var(--gx-brand-from)] focus:bg-white transition"
                placeholder="you@gym.com"
                data-testid="gx-login-email"
              />
            </div>
            <div>
              <label className="text-[11px] font-bold uppercase tracking-[0.16em] text-slate-500 mb-1.5 block">
                {t('auth.password', 'Password')}
              </label>
              <div className="relative">
                <input
                  type={showPass ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoFocus={!!email}
                  className="w-full h-11 px-3 pr-11 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-[var(--gx-brand-from)] focus:bg-white transition"
                  placeholder="••••••••"
                  data-testid="gx-login-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPass((s) => !s)}
                  tabIndex={-1}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1.5 text-slate-400 hover:text-slate-700"
                  data-testid="gx-login-toggle-password"
                  aria-label={showPass ? t('auth.hide_password', 'Hide password') : t('auth.show_password', 'Show password')}
                >
                  {showPass ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>
            <button
              type="submit"
              onClick={handleSubmit}
              disabled={loading}
              className="gx-cta w-full h-11 rounded-xl font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-60"
              data-testid="gx-login-submit"
            >
              {loading ? <><Loader2 size={14} className="animate-spin" /> {t('auth.signing_in', 'Signing in…')}</> : <>{t('auth.login_btn', 'Sign In')} <ArrowRight size={14} /></>}
            </button>
          </form>
          )}

          <div className="flex items-center justify-between text-xs text-slate-500 mt-5 pt-5 border-t border-slate-100">
            <Link to="/reset-password" className="hover:text-slate-900 font-semibold" data-testid="gx-login-forgot">
              {t('auth.forgot_password', 'Forgot password?')}
            </Link>
            <Link to="/contact" className="hover:text-slate-900 font-semibold" data-testid="gx-login-need-account">
              {t('auth.need_account', 'Need an account?')}
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
