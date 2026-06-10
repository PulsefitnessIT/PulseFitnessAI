/**
 * GymAxis dedicated /login page (replaces the legacy dark HomePage).
 *
 * A focused, GymAxis-branded sign-in surface that lives on the same light
 * marketing aesthetic as MarketingHome. Wraps a single email/password form
 * with the gym-floor kiosk fallback (username login) so on-site terminals
 * keep working.
 */
import { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { ArrowLeft, ArrowRight, Eye, EyeOff, Loader2 } from 'lucide-react';

import { useAuth } from '@/App';
import { notify, useInlineBanner } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { moduleHomePath } from '@/utils/moduleHome';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);
  const { banner, _show, clear } = useInlineBanner({ autoDismiss: false });

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
      if (!data?.token) throw new Error('No token returned');
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
      const fallback = (u.is_master_admin || u.is_pulse_admin)
        ? '/master-admin'
        : (u.is_partner_engineer || u.account_type === 'partner_engineer' || u.role === 'engineer_partner')
          ? '/partner-engineer'
          : (u.account_type === 'lite' || u.account_type === 'pulse_pro')
            ? '/pulse'
            : (moduleHomePath(u) || '/dashboard');
      navigate(nextParam || fallback, { replace: true });
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

  return (
    <div
      className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-100 flex flex-col theme-gymaxis"
      data-theme="light"
      data-testid="gx-login-page"
    >
      {/* Top bar */}
      <header className="px-6 lg:px-10 h-16 flex items-center justify-between border-b border-slate-200/60 bg-white/60 backdrop-blur">
        <Link to="/" className="text-slate-900 font-black tracking-tighter text-lg" data-testid="gx-login-logo">
          GymAxis<span className="text-[var(--gx-brand-from)]">.AI</span>
        </Link>
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900"
          data-testid="gx-login-back"
        >
          <ArrowLeft size={13} /> {t('auth.back_home', 'Back to home')}
        </Link>
      </header>

      {/* Form card */}
      <main className="flex-1 flex items-center justify-center px-4 py-10">
        <div
          className="w-full max-w-md rounded-3xl bg-white border border-slate-200 shadow-[0_30px_80px_-40px_rgba(15,23,42,0.25)] p-8 sm:p-10"
          data-testid="gx-login-card"
        >
          <div className="mb-6">
            <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-slate-900">{t('auth.login_title', 'Welcome back')}</h1>
            <p className="mt-1 text-sm text-slate-500">{t('auth.subtitle', 'Sign in to your GymAxis portal.')}</p>
          </div>

          {banner && <div className="mb-3">{banner}</div>}

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
                autoFocus
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
