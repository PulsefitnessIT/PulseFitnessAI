/**
 * Portal invite claim page (iter 216ak · Sprint B · G5 → iter 216h46).
 *
 * Landing page for the magic link an operator sent from the Members tab:
 *   /m/{slug}/claim?t=<invite-token>
 *
 * The member picks a password, we POST /api/member-auth/claim-invite,
 * pipe the returned bearer through UnifiedAuthProvider (scope='member')
 * and bounce them into the normal member portal at /m/{slug}.
 */
import { useEffect, useState } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Lock, CheckCircle2, Loader2, AlertTriangle } from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { useUnifiedAuth } from '@/components/shared/UnifiedAuthProvider';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function MemberClaimPage() {
  const { slug } = useParams();
  const [params] = useSearchParams();
  const token = params.get('t') || '';
  const navigate = useNavigate();
  const unifiedAuth = useUnifiedAuth();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [branding, setBranding] = useState(null);
  const [error, setError] = useState(token ? null : 'This link is missing a token. Please check the email we sent you.');

  useEffect(() => {
    if (!slug) return;
    axios.get(`${API}/m/${slug}/branding`).then((r) => setBranding(r.data)).catch(() => {});
  }, [slug]);

  const submit = async (e) => {
    e.preventDefault();
    if (password.length < 8) { setError('Password must be at least 8 characters'); return; }
    if (password !== confirm) { setError('Passwords do not match'); return; }
    setError(null);
    setBusy(true);
    try {
      const r = await axios.post(`${API}/member-auth/claim-invite`, { token, password });
      // Iter 216h46 — pipe through UnifiedAuthProvider so the rest of
      // the platform (OfflineBanner gating, future provider-aware
      // surfaces) sees the new member session immediately.
      if (r.data?.token) unifiedAuth.login({ scope: 'member', token: r.data.token });
      notify.success(`Welcome to ${branding?.name || 'your studio'}!`);
      navigate(`/m/${slug}`, { replace: true });
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not claim invite');
      notifyApiError(notify, err, 'Could not claim invite');
    }
    setBusy(false);
  };

  const primary = branding?.primary_brand_colour || '#19CDFF';
  const name = branding?.name || 'Your studio';

  return (
    <div className="min-h-screen grid place-items-center p-4 bg-[var(--color-surface-darker,#0A0C10)] text-white"
         data-testid="member-claim-page">
      <div className="w-full max-w-md rounded-2xl border border-white/10 bg-[rgba(255,255,255,0.02)] shadow-2xl overflow-hidden">
        <div className="px-6 py-5" style={{ background: primary }}>
          {branding?.logo_url ? (
            <img src={branding.logo_url} alt="" className="h-10 mb-2" />
          ) : null}
          <p className="text-[10px] font-extrabold uppercase tracking-[0.22em] opacity-80 text-white">Portal invite</p>
          <h1 className="text-2xl font-black text-white">Welcome to {name}</h1>
        </div>
        <form onSubmit={submit} className="p-6 space-y-4">
          <p className="text-sm text-white/70">
            Set a password to finish setting up your parent portal account. You'll use it to book classes, manage your family, and pay invoices on your phone.
          </p>
          <label className="block">
            <span className="block text-[10px] font-extrabold uppercase tracking-wider text-white/50 mb-1">New password</span>
            <div className="relative">
              <Lock size={12} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40" />
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                autoFocus minLength={8} required
                className="w-full pl-8 pr-3 py-2.5 text-sm rounded-lg bg-white/5 border border-white/10 focus:outline-none focus:border-[var(--color-brand-cyan)]"
                placeholder="At least 8 characters"
                data-testid="member-claim-password" />
            </div>
          </label>
          <label className="block">
            <span className="block text-[10px] font-extrabold uppercase tracking-wider text-white/50 mb-1">Confirm password</span>
            <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required
              className="w-full px-3 py-2.5 text-sm rounded-lg bg-white/5 border border-white/10 focus:outline-none focus:border-[var(--color-brand-cyan)]"
              data-testid="member-claim-confirm" />
          </label>
          {error && (
            <p className="text-xs text-amber-400 inline-flex items-start gap-1.5"><AlertTriangle size={11} className="mt-0.5" /> {error}</p>
          )}
          <button type="submit" disabled={busy || !token}
            className="w-full inline-flex items-center justify-center gap-2 py-2.5 rounded-full font-extrabold disabled:opacity-50"
            style={{ background: primary, color: '#0A0C10' }}
            data-testid="member-claim-submit">
            {busy ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
            Activate my portal
          </button>
        </form>
      </div>
    </div>
  );
}
