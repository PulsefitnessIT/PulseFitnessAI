/**
 * GymAxis Login Page (iter 215av).
 *
 * Premium-branded `/login` experience that matches the new marketing site:
 * Satoshi heading, light SaaS surface, brand-gradient submit. Reuses the
 * same auth contract as HomeLoginModal (POST /auth/login + gym-floor
 * fallback + must_change_password handling).
 *
 * Uses MarketingShell chrome so the user keeps a consistent header/footer
 * across the marketing → login transition.
 *
 * Old behaviour preserved: visiting /login while authenticated redirects
 * to the right destination (/master-admin / /pulse / /dashboard).
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { Link, useNavigate } from 'react-router-dom';
import { Loader2, ArrowRight, ShieldCheck } from 'lucide-react';

import { useAuth } from '@/App';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import MarketingShell from './Marketing/MarketingShell';
import './Marketing/marketing.css';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function GymAxisLoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);

  // Auth-aware redirect — same routing as the legacy LoginRedirectPage.
  useEffect(() => {
    if (!user) return;
    const dest = (user.is_master_admin || user.is_pulse_admin)
      ? '/master-admin'
      : (user.account_type === 'lite' || user.account_type === 'pulse_pro')
        ? '/pulse'
        : '/dashboard';
    navigate(dest, { replace: true });
  }, [user, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await axios.post(`${API}/auth/login`, { email, password });
      if (!data?.token) throw new Error('No token returned');
      login(data.token, data.user);
      const u = data.user || {};
      if (u.must_change_password) {
        navigate('/change-password', { replace: true });
        return;
      }
      const dest = (u.is_master_admin || u.is_pulse_admin)
        ? '/master-admin'
        : (u.account_type === 'lite' || u.account_type === 'pulse_pro')
          ? '/pulse'
          : '/dashboard';
      navigate(dest, { replace: true });
    } catch (err) {
      // Gym-floor kiosk fallback — username (no '@') + 401 → try /gym-floor/login.
      if (err.response?.status === 401 && email && !email.includes('@')) {
        try {
          const gf = await axios.post(`${API}/gym-floor/login`, { username: email, password });
          const session = { ...gf.data, logged_in_at: new Date().toISOString() };
          localStorage.setItem('gym_floor_session', JSON.stringify(session));
          navigate('/gym-floor', { replace: true });
          setLoading(false);
          return;
        } catch (_gfErr) {
          // fall through
        }
      }
      notifyApiError(notify, err, 'Invalid credentials');
    }
    setLoading(false);
  };

  return (
    <MarketingShell>
      <main
        className="gx-marketing min-h-screen pt-24 pb-16 gx-grid-bg"
        data-testid="gx-login-page"
      >
        <div className="max-w-md mx-auto px-6">
          {/* Eyebrow */}
          <div className="flex items-center justify-center mb-6">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white/70 backdrop-blur px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-600">
              <ShieldCheck size={12} className="text-[var(--gx-brand-from)]" />
              Secure sign in
            </span>
          </div>

          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-slate-900 text-center" data-testid="gx-login-title">
            Welcome back to <span className="gx-gradient-text">GymAxis</span>
          </h1>
          <p className="mt-3 text-center text-sm text-slate-500">
            Sign in to your operating system for gym performance.
          </p>

          {/* Login card */}
          <div
            className="mt-8 rounded-3xl border border-slate-200 bg-white shadow-[0_20px_50px_-20px_rgba(15,23,42,0.15)] p-6 sm:p-8"
            data-testid="gx-login-card"
          >
            <form onSubmit={handleSubmit} className="space-y-5" data-testid="gx-login-form">
              <div>
                <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5 block">
                  Email or site code
                </label>
                <input
                  type="text"
                  autoCapitalize="none"
                  autoCorrect="off"
                  spellCheck={false}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoFocus
                  className="w-full h-11 px-3 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-[var(--gx-brand-from)] focus:bg-white focus:ring-4 focus:ring-[var(--gx-brand-from)]/10 transition"
                  placeholder="you@gym.com or kiosk username"
                  data-testid="gx-login-email"
                />
              </div>

              <div>
                <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5 block">
                  Password
                </label>
                <div className="relative">
                  <input
                    type={showPass ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    className="w-full h-11 px-3 pr-16 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-[var(--gx-brand-from)] focus:bg-white focus:ring-4 focus:ring-[var(--gx-brand-from)]/10 transition"
                    placeholder="••••••••"
                    data-testid="gx-login-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPass(!showPass)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 px-2 py-1 text-[11px] font-semibold text-slate-500 hover:text-slate-900"
                    tabIndex={-1}
                    data-testid="gx-login-toggle-pass"
                  >
                    {showPass ? 'Hide' : 'Show'}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="gx-cta w-full h-12 rounded-full inline-flex items-center justify-center gap-2 font-bold text-sm disabled:opacity-60"
                data-testid="gx-login-submit"
              >
                {loading ? (
                  <><Loader2 size={16} className="animate-spin" /> Signing in…</>
                ) : (
                  <>Sign In <ArrowRight size={16} /></>
                )}
              </button>

              <div className="flex items-center justify-between text-xs text-slate-500 pt-1">
                <Link to="/reset-password" className="hover:text-slate-900 transition-colors" data-testid="gx-login-forgot">
                  Forgot password?
                </Link>
                <Link to="/contact" className="hover:text-slate-900 transition-colors" data-testid="gx-login-need-account">
                  Need an account?
                </Link>
              </div>
            </form>
          </div>

          <p className="mt-6 text-center text-[11px] text-slate-400">
            Protected with end-to-end encryption · SOC 2 evidence available
          </p>
        </div>
      </main>
    </MarketingShell>
  );
}
