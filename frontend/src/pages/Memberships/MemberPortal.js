/**
 * GymAxis Memberships — Member-facing portal (/members).
 *
 * Separate identity from the operator app: uses its own JWT stored under
 * localStorage key `member_token`. The API mints tokens with `kind=member`
 * via `/api/member-auth/{register,login}`; operator endpoints reject them
 * and vice versa.
 *
 * Tabs (mobile-first):
 *   • Book      — weekly timetable, tap to book / waitlist / cancel
 *   • Bookings  — upcoming + past attendance
 *   • Pass      — rotating 30-second TOTP QR for kiosk check-in
 *   • Profile   — details + sign out
 *
 * Design language mirrors the operator console: dark GymAxis surface,
 * cyan (var(--color-brand-cyan)) accent, generous whitespace.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { InlineBanner, useInlineBanner, useConfirm, notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import QRCode from 'qrcode';
import {
  Calendar, Ticket, QrCode, User, LogOut, ChevronLeft, ChevronRight,
  Clock, MapPin, Users as UsersIcon, Users, Sparkles, CheckCircle2, X, Loader2, CreditCard, Activity,
  CalendarPlus, ArrowLeftRight, Download, Link as LinkIcon, Home, MoreHorizontal, RefreshCw,
} from 'lucide-react';

import FamilyTab from './FamilyTab';
import HomeTab from './MemberHomeTab';
import MemberEventsTab from './MemberEventsTab';
import { StudioVocabProvider, useStudioVocab, capNoun } from '@/hooks/useStudioVocab';
import { useUnifiedAuth } from '@/components/shared/UnifiedAuthProvider';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;
const MEMBER_TOKEN_KEY = 'member_token';

// Bottom-nav: 5 primary tabs + More sheet. Plan/Family/Profile move into the
// More bottom-sheet so each tab keeps an ergonomic ≥75px tap target at 375px.
const TABS = [
  { id: 'home',     label: 'Home',     icon: Home },
  { id: 'book',     label: 'Book',     icon: Calendar },
  { id: 'bookings', label: 'Bookings', icon: Ticket },
  { id: 'pass',     label: 'Pass',     icon: QrCode },
  { id: 'more',     label: 'More',     icon: MoreHorizontal },
];

const MORE_ITEMS = [
  { id: 'plan',    label: 'My plan',           icon: CreditCard },
  { id: 'family',  label: 'Family accounts',   icon: Users },
  { id: 'events',  label: 'Events & shows',    icon: Sparkles },
  { id: 'profile', label: 'Profile & settings',icon: User },
];

export default function MemberPortal({ slug }) {
  // Iter 216h46 — member token now flows through UnifiedAuthProvider.
  // The portal still keeps its own `token` state for tight local
  // re-renders, but writes/reads route through the provider so the
  // rest of the platform (OfflineBanner, future cross-module APIs)
  // stays in lock-step.
  const unifiedAuth = useUnifiedAuth();
  const [token, setToken] = useState(() => localStorage.getItem(MEMBER_TOKEN_KEY));
  const [member, setMember] = useState(null);
  const [branding, setBranding] = useState(null);
  const [vocab, setVocab] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('home');
  // The "More" bottom-sheet is not a real tab — clicking the More pill
  // toggles this overlay so Plan / Family / Profile remain reachable
  // without a 7-tab nav (which broke the ergonomic 75px tap target at
  // 375px viewport).
  const [moreOpen, setMoreOpen] = useState(false);
  const { banner: paymentBanner, show: showPayment } = useInlineBanner();

  const headers = useMemo(() => (token ? { Authorization: `Bearer ${token}` } : {}), [token]);

  // Fetch gym branding if we have a slug (white-label mode)
  useEffect(() => {
    if (!slug) { setBranding(null); return; }
    axios.get(`${API}/m/${slug}/branding`).then((r) => setBranding(r.data)).catch(() => {});
  }, [slug]);

  // Apply brand colour as CSS custom property
  useEffect(() => {
    const c = branding?.primary_brand_colour || 'var(--color-brand-cyan)';
    document.documentElement.style.setProperty('--gym-accent', c);
    return () => { document.documentElement.style.removeProperty('--gym-accent'); };
  }, [branding]);

  const handleAuthed = useCallback((t, m) => {
    unifiedAuth.login({ scope: 'member', token: t });
    setToken(t);
    setMember(m);
  }, [unifiedAuth]);

  const signOut = useCallback(() => {
    unifiedAuth.logout('member');
    setToken(null);
    setMember(null);
  }, [unifiedAuth]);

  useEffect(() => {
    if (!token) { setLoading(false); return; }
    axios.get(`${API}/member-auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => setMember(r.data.member))
      .catch(() => { unifiedAuth.logout('member'); setToken(null); })
      .finally(() => setLoading(false));
  }, [token, unifiedAuth]);

  // Pull the studio vocabulary once per session so every tab/toast can
  // swap "member" → the industry noun (athlete, dancer, swimmer, etc).
  useEffect(() => {
    if (!token) { setVocab(null); return; }
    axios.get(`${API}/member/studio/vocabulary`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => setVocab(r.data))
      .catch(() => setVocab(null));
  }, [token]);

  // Handle Stripe checkout redirect (?checkout=success&session_id=... or ?checkout=cancel)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const result = params.get('checkout');
    const sessionId = params.get('session_id');
    if (!result) return;
    const cleanUrl = window.location.pathname;
    window.history.replaceState({}, '', cleanUrl);
    if (result === 'success' && sessionId) {
      setTab('plan');
      pollCheckout(sessionId);
    } else if (result === 'cancel') {
      showPayment({ tone: 'info', title: 'Checkout cancelled', detail: 'Your spot is ready whenever you are.' });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pollCheckout = async (sessionId, attempt = 0) => {
    if (attempt > 12) { showPayment({ tone: 'warning', title: 'Payment still processing', detail: 'Check back in a minute — we\'ll email you once it settles.' }); return; }
    try {
      const { data } = await axios.get(`${API}/memberships/checkout/status/${sessionId}`);
      if (data.payment_status === 'paid') {
        showPayment({ tone: 'success', title: 'Payment received — welcome aboard!', detail: 'Your membership is now active.' });
        return;
      }
      if (data.status === 'expired') { showPayment({ tone: 'error', title: 'Checkout expired', detail: 'Please try again.' }); return; }
      setTimeout(() => pollCheckout(sessionId, attempt + 1), 2000);
    } catch { /* retry */
      setTimeout(() => pollCheckout(sessionId, attempt + 1), 3000);
    }
  };

  if (loading) {
    return <div className="min-h-screen bg-[var(--color-surface-darker)] text-white grid place-items-center"><Loader2 className="animate-spin text-[var(--color-brand-cyan)]" /></div>;
  }
  if (!member) return <AuthGate onAuthed={handleAuthed} branding={branding} slug={slug} />;

  return (
    <StudioVocabProvider vocab={vocab}>
    <div className="min-h-screen bg-[var(--color-surface-darker)] text-white pb-24" data-testid="member-portal">
      <TopBar member={member} branding={branding} onSignOut={signOut} />
      <main className="max-w-2xl mx-auto px-4 py-6">
        {paymentBanner && <div className="mb-4">{paymentBanner}</div>}
        <RequiredFormsBanner headers={headers} />
        <ReferralCampaignBanner headers={headers} slug={slug} onCta={() => setTab('profile')} />
        <StreakCard headers={headers} />
        <InstallPrompt brandColor={branding?.primary_color} />
        {tab === 'home'     && <HomeTab headers={headers} setTab={setTab} API={API} />}
        {tab === 'book'     && <BookTab headers={headers} slug={slug} />}
        {tab === 'bookings' && <BookingsTab headers={headers} slug={slug} />}
        {tab === 'plan'     && <PlanTab headers={headers} member={member} slug={slug} />}
        {tab === 'family'   && <FamilyTab API={API} headers={headers} />}
        {tab === 'events'   && <MemberEventsTab API={API} headers={headers} />}
        {tab === 'pass'     && <PassTab headers={headers} member={member} />}
        {tab === 'profile'  && <ProfileTab member={member} onSignOut={signOut} slug={slug} />}
      </main>
      <BottomNav tab={tab} setTab={(t) => {
        if (t === 'more') { setMoreOpen(true); return; }
        setTab(t);
      }} />
      <MoreSheet
        open={moreOpen}
        currentTab={tab}
        onSelect={(target) => { setTab(target); setMoreOpen(false); }}
        onClose={() => setMoreOpen(false)}
      />
    </div>
    </StudioVocabProvider>
  );
}

/* ─────────────────── Streak card ─────────────────── */

function StreakCard({ headers }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    axios.get(`${API}/member/streak`, { headers })
      .then((r) => setData(r.data))
      .catch(() => {});
  }, [headers]);

  if (!data) return null;
  const { current_streak_days: streak, weekly_count, weekly_goal, weekly_remaining, at_risk } = data;
  if (streak === 0 && weekly_count === 0) return null;
  const goalPct = Math.min(100, Math.round((weekly_count / Math.max(weekly_goal, 1)) * 100));
  const goalHit = weekly_remaining === 0 && weekly_count > 0;
  const headline = at_risk
    ? `Don't let it slip — show up today to keep your ${streak}-day streak alive.`
    : streak >= 3
    ? `🔥 ${streak}-day streak · you're on fire.`
    : streak > 0
    ? `You're on day ${streak} — let's keep it going.`
    : `${weekly_count}/${weekly_goal} this week · you got this.`;

  return (
    <section className="mb-5 rounded-xl border border-white/10 bg-white dark:bg-zinc-900/[0.04] p-4 sm:p-5" data-testid="member-streak-card">
      <div className="flex items-center gap-2 text-[10px] font-extrabold uppercase tracking-[0.25em] text-[var(--color-brand-cyan)]">
        <Activity size={12} /> Attendance streak
      </div>
      <div className="mt-1.5 text-base sm:text-lg font-extrabold leading-tight tracking-tight">{headline}</div>
      <div className="grid grid-cols-2 gap-3 mt-3">
        <div>
          <div className="text-[10px] text-white/50 font-bold uppercase tracking-wider">Current</div>
          <div className="text-2xl font-extrabold" style={{ color: streak > 0 ? 'var(--color-brand-cyan)' : 'rgba(255,255,255,0.5)' }} data-testid="member-streak-current">{streak}d</div>
        </div>
        <div>
          <div className="text-[10px] text-white/50 font-bold uppercase tracking-wider">This week</div>
          <div className="text-2xl font-extrabold" data-testid="member-streak-weekly">{weekly_count}<span className="text-white/40 text-base font-bold"> / {weekly_goal}</span></div>
        </div>
      </div>
      <div className="mt-3 h-1.5 rounded bg-white dark:bg-zinc-900/5 overflow-hidden" aria-hidden>
        <div className="h-full rounded transition-all" style={{ width: `${goalPct}%`, background: goalHit ? 'var(--color-success-light)' : 'var(--color-brand-cyan)' }} />
      </div>
      {goalHit && (
        <div className="mt-2 text-[11px] font-extrabold text-emerald-400 flex items-center gap-1" data-testid="member-streak-goal-hit">
          <CheckCircle2 size={12} /> Weekly goal smashed 🎉
        </div>
      )}
      {at_risk && !goalHit && (
        <div className="mt-2 text-[11px] font-bold text-amber-400" data-testid="member-streak-risk">
          24+ hours since your last session.
        </div>
      )}
    </section>
  );
}

/* ─────────────────── Required consent forms banner (Phase C) ─────────────────── */

function RequiredFormsBanner({ headers }) {
  const [pending, setPending] = useState(null); // null=loading, []=none, [forms]=show
  const [vocab, setVocab] = useState(null);
  const [signing, setSigning] = useState(null);
  const [signature, setSignature] = useState('');

  const reload = useCallback(async () => {
    try {
      const [forms, voc] = await Promise.all([
        axios.get(`${API}/member/consent-forms`, { headers }),
        axios.get(`${API}/member/studio/vocabulary`, { headers }).catch(() => ({ data: null })),
      ]);
      const need = (forms.data?.forms || []).filter((f) => f.required && !f.signed);
      setPending(need);
      setVocab(voc.data);
    } catch {
      setPending([]);
    }
  }, [headers]);
  useEffect(() => { reload(); }, [reload]);

  const sign = async () => {
    if (!signing || !signature.trim()) return;
    try {
      await axios.post(`${API}/member/consent-forms/${signing.id}/sign`,
        { signature_text: signature.trim() }, { headers });
      setSigning(null);
      setSignature('');
      reload();
    } catch (e) {
      alert(e?.response?.data?.detail || 'Could not sign — please try again.');
    }
  };

  if (!pending || pending.length === 0) return null;
  const guardian = vocab?.guardian_noun || 'guardian';
  const memberWord = vocab?.member_singular || 'member';
  return (
    <div
      className="mb-4 rounded-2xl border p-4"
      style={{ borderColor: '#fbbf24', background: 'rgba(251,191,36,0.12)', color: 'inherit' }}
      data-testid="member-required-forms-banner"
    >
      <div className="flex items-start gap-3">
        <span className="rounded-full p-1.5" style={{ background: 'rgba(245,158,11,0.25)' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#b45309" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"/></svg>
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold">
            {pending.length} form{pending.length > 1 ? 's' : ''} to sign before your next booking
          </p>
          <p className="text-[12px] opacity-80 mt-0.5">
            As the {guardian} of your {memberWord}, please confirm the following so we can keep everyone safe.
          </p>
          <ul className="mt-2 space-y-1">
            {pending.map((f) => (
              <li
                key={f.id}
                className="flex items-center gap-2"
                data-testid={`member-required-form-${f.id}`}
              >
                <span className="text-[11px] flex-1 truncate font-bold">{f.title} · v{f.version}</span>
                <button
                  type="button"
                  onClick={() => { setSigning(f); setSignature(''); }}
                  className="px-2 py-1 rounded text-[11px] font-bold"
                  style={{ background: '#b45309', color: '#fff' }}
                  data-testid={`member-required-form-sign-${f.id}`}
                >
                  Read & sign
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {signing ? (
        <div
          className="mt-3 rounded-xl bg-white text-slate-900 p-3"
          data-testid="member-required-form-signing"
        >
          <p className="text-sm font-bold">{signing.title}</p>
          <div className="text-[12px] mt-1 max-h-48 overflow-y-auto pr-2"
               dangerouslySetInnerHTML={{ __html: signing.body_html }} />
          <label className="block mt-2">
            <span className="text-[10px] uppercase tracking-wider font-bold opacity-60">
              Type your full name to confirm
            </span>
            <input
              value={signature}
              onChange={(e) => setSignature(e.target.value)}
              className="w-full px-2 py-1 text-sm rounded border"
              style={{ borderColor: '#cbd5e1' }}
              data-testid="member-required-form-signature"
            />
          </label>
          <div className="flex items-center gap-2 justify-end mt-2">
            <button
              type="button"
              onClick={() => setSigning(null)}
              className="px-2 py-1 rounded text-[11px] border"
              style={{ borderColor: '#cbd5e1' }}
              data-testid="member-required-form-cancel"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={sign}
              disabled={!signature.trim()}
              className="px-3 py-1.5 rounded text-[11px] font-bold"
              style={{ background: '#1d4ed8', color: '#fff', opacity: signature.trim() ? 1 : 0.5 }}
              data-testid="member-required-form-submit"
            >
              I agree & sign
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/* ─────────────────── Referral campaign banner ─────────────────── */

function ReferralCampaignBanner({ headers, slug, onCta }) {
  const [progress, setProgress] = useState(null);
  const [dismissed, setDismissed] = useState(false);
  useEffect(() => {
    axios.get(`${API}/member/referral-progress`, { headers })
      .then((r) => {
        setProgress(r.data);
        if (r.data.campaign_dismissed_at) setDismissed(true);
      })
      .catch(() => {});
  }, [headers]);

  const dismiss = async () => {
    setDismissed(true);
    try { await axios.post(`${API}/member/referral-progress/dismiss`, {}, { headers }); } catch { /* silent */ }
  };
  const share = async () => {
    const base = slug ? `${window.location.origin}/m/${slug}` : `${window.location.origin}/members`;
    const url = `${base}?ref=${progress.code}`;
    const text = `Train with me — use my code ${progress.code} for £5 off your first class at the studio.`;
    if (navigator.share) {
      try { await navigator.share({ title: 'Join me at the studio', url, text }); return; }
      catch { /* fallthrough */ }
    }
    try { await navigator.clipboard.writeText(url); notify.success('Share link copied'); }
    catch { window.prompt('Share this link:', url); }
  };

  if (!progress || dismissed || !progress.next_goal) return null;
  const { gap, percent, earned, next_goal } = progress;
  const headline = gap === 1
    ? `One more friend and you unlock ${next_goal.reward.toLowerCase()}.`
    : `Refer ${gap} more friends, get ${next_goal.reward.toLowerCase()}.`;

  return (
    <section className="mb-5 rounded-xl border border-[rgb(var(--rgb-brand-cyan)/0.3)] bg-gradient-to-br from-[rgb(var(--rgb-brand-cyan)/0.15)] via-[rgb(var(--rgb-brand-cyan)/0.05)] to-transparent p-4 sm:p-5 relative" data-testid="member-referral-campaign">
      <button onClick={dismiss}
        className="absolute top-2 right-2 p-1.5 rounded text-white/40 hover:text-white hover:bg-white dark:bg-zinc-900/5"
        data-testid="member-referral-campaign-dismiss" aria-label="Dismiss">
        <X size={14} />
      </button>
      <div className="flex items-center gap-2 text-[10px] font-extrabold uppercase tracking-[0.25em] text-[var(--color-brand-cyan)]">
        <Sparkles size={12} /> Refer &amp; earn
      </div>
      <div className="mt-1.5 text-base sm:text-lg font-extrabold leading-tight tracking-tight pr-6">{headline}</div>
      <div className="mt-3 h-1.5 rounded bg-white dark:bg-zinc-900/10 overflow-hidden" aria-hidden>
        <div className="h-full rounded bg-[var(--color-brand-cyan)] transition-all" style={{ width: `${percent}%` }} />
      </div>
      <div className="flex items-center justify-between mt-2 gap-3">
        <div className="text-[11px] text-white/60">{earned} / {next_goal.threshold} friends joined</div>
        <div className="flex items-center gap-2">
          <button onClick={onCta} className="text-[10px] font-extrabold uppercase tracking-wider px-2.5 py-1.5 rounded border border-white/15 text-white/80 hover:bg-white dark:bg-zinc-900/5" data-testid="member-referral-campaign-cta">
            My code
          </button>
          <button onClick={share} className="text-[10px] font-extrabold uppercase tracking-wider px-3 py-1.5 rounded bg-[var(--color-brand-cyan)] text-black" data-testid="member-referral-campaign-share">
            Share now
          </button>
        </div>
      </div>
    </section>
  );
}


/* ─────────────────── Auth ─────────────────── */

function AuthGate({ onAuthed, branding, slug }) {
  const [mode, setMode] = useState('login'); // 'login' | 'register'
  const gymName = branding?.name || 'GymAxis';
  const accent = branding?.primary_brand_colour || 'var(--color-brand-cyan)';

  return (
    <div className="min-h-screen bg-[var(--color-surface-darker)] text-white flex flex-col" data-testid="member-auth-gate">
      <header className="px-6 pt-10 pb-6 text-center">
        {branding?.logo_url ? (
          <img src={branding.logo_url} alt={gymName} className="mx-auto h-12 mb-4 rounded" />
        ) : (
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full mb-6" style={{ background: `${accent}1a`, border: `1px solid ${accent}33` }}>
            <Sparkles size={12} style={{ color: accent }} />
            <span className="text-[10px] font-bold tracking-[0.2em] uppercase" style={{ color: accent }}>{slug ? gymName : 'GymAxis Member'}</span>
          </div>
        )}
        <h1 className="text-4xl font-extrabold tracking-tight" style={{ letterSpacing: '-0.03em' }}>
          {slug ? `Welcome to ${gymName}.` : 'Your studio, in your pocket.'}
        </h1>
        <p className="text-sm text-white/60 mt-2">Book classes, show your QR pass, manage your plan.</p>
      </header>

      <div className="flex-1 flex items-start justify-center px-4 pb-10">
        <div className="w-full max-w-sm">
          <div className="flex gap-1 p-1 rounded-xl bg-white dark:bg-zinc-900/5 border border-white/10 mb-5">
            <TabPill active={mode === 'login'}    onClick={() => setMode('login')}    testid="member-auth-tab-login" accent={accent}>Sign in</TabPill>
            <TabPill active={mode === 'register'} onClick={() => setMode('register')} testid="member-auth-tab-register" accent={accent}>Join</TabPill>
          </div>
          {mode === 'login'    ? <LoginForm    onAuthed={onAuthed} accent={accent} />
                               : <RegisterForm onAuthed={onAuthed} branding={branding} slug={slug} accent={accent} />}
        </div>
      </div>
    </div>
  );
}

function TabPill({ active, onClick, children, testid, accent }) {
  return (
    <button onClick={onClick} data-testid={testid}
      className={`flex-1 rounded-lg py-2 text-xs font-extrabold uppercase tracking-wider transition ${active ? 'text-[var(--color-surface-darker)]' : 'text-white/60 hover:text-white'}`}
      style={active ? { background: accent || 'var(--color-brand-cyan)' } : {}}>
      {children}
    </button>
  );
}

function LoginForm({ onAuthed, accent }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const { banner, show, clear } = useInlineBanner({ autoDismiss: false });

  const submit = async (e) => {
    e.preventDefault();
    clear();
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/member-auth/login`, { email, password });
      onAuthed(data.token, data.member);
      notify.success(`Welcome back, ${data.member.first_name}`);
    } catch (err) {
      const d = err.response?.data?.detail || '';
      show({
        tone: 'error',
        title: /invalid|credential|incorrect|not found/i.test(d) ? 'Incorrect email or password' : 'Couldn\'t sign you in',
        detail: /invalid|credential|incorrect|not found/i.test(d)
          ? 'Double-check your email and password. Tap "Forgot password" to reset.'
          : (d || 'Please check your connection and try again.'),
      });
    } finally { setBusy(false); }
  };

  return (
    <form onSubmit={submit} className="space-y-3" data-testid="member-login-form">
      {banner}
      <LabelledInput label="Email" type="email" value={email} onChange={setEmail} required testid="member-login-email" />
      <LabelledInput label="Password" type="password" value={password} onChange={setPassword} required testid="member-login-password" />
      <button type="submit" disabled={busy}
        className="w-full rounded-lg py-3 text-sm font-extrabold uppercase tracking-wider disabled:opacity-60"
        style={{ background: accent || 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }} data-testid="member-login-submit">
        {busy ? 'Signing in…' : 'Sign in'}
      </button>
    </form>
  );
}

function RegisterForm({ onAuthed, branding, slug, accent }) {
  const [f, setF] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    const ref = (params.get('ref') || '').toUpperCase().trim();
    return { first_name: '', last_name: '', email: '', password: '', phone: '',
             referral_code: ref };
  });
  const [busy, setBusy] = useState(false);
  const { banner, show, clear } = useInlineBanner({ autoDismiss: false });

  const submit = async (e) => {
    e.preventDefault();
    clear();
    if (f.password.length < 8) {
      show({ tone: 'error', title: 'Password too short', detail: 'Please use at least 8 characters so your account stays secure.' });
      return;
    }
    setBusy(true);
    try {
      const payload = {
        ...f, referral_code: f.referral_code || undefined,
        ...(slug ? { organization_slug: slug } : { organization_id: 'mbr-demo-org' }),
      };
      const { data } = await axios.post(`${API}/member-auth/register`, payload);
      onAuthed(data.token, data.member);
      notify.success(`Welcome, ${data.member.first_name}!${f.referral_code ? ' · Friend referral applied' : ''}`);
    } catch (err) {
      const d = err.response?.data?.detail || '';
      show({
        tone: 'error',
        title: /already|exist|taken/i.test(d) ? 'Email already registered' : 'Couldn\'t create your account',
        detail: /already|exist|taken/i.test(d)
          ? 'An account with this email already exists — try signing in instead.'
          : (d || 'Please review your details and try again. If it still fails, contact support.'),
      });
    } finally { setBusy(false); }
  };

  const up = (k) => (v) => setF((prev) => ({ ...prev, [k]: v }));

  return (
    <form onSubmit={submit} className="space-y-3" data-testid="member-register-form">
      {banner}
      <div className="grid grid-cols-2 gap-3">
        <LabelledInput label="First name" value={f.first_name} onChange={up('first_name')} required testid="member-reg-first" />
        <LabelledInput label="Last name"  value={f.last_name}  onChange={up('last_name')}  required testid="member-reg-last" />
      </div>
      <LabelledInput label="Email"    type="email"    value={f.email}    onChange={up('email')}    required testid="member-reg-email" />
      <LabelledInput label="Phone"                    value={f.phone}    onChange={up('phone')}             testid="member-reg-phone" />
      <LabelledInput label="Password" type="password" value={f.password} onChange={up('password')} required testid="member-reg-password" />
      <LabelledInput label="Referral code (optional)" value={f.referral_code} onChange={(v) => up('referral_code')(v.toUpperCase())} testid="member-reg-referral" />
      <p className="text-[10px] text-white/40 leading-relaxed">
        By joining you agree to {branding?.name || 'the studio'}'s terms. You'll select your plan after signup.
      </p>
      <button type="submit" disabled={busy}
        className="w-full rounded-lg py-3 text-sm font-extrabold uppercase tracking-wider disabled:opacity-60"
        style={{ background: accent || 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }} data-testid="member-register-submit">
        {busy ? 'Creating account…' : 'Create account'}
      </button>
    </form>
  );
}


/* ─────────────────── Chrome ─────────────────── */

function TopBar({ member, branding, onSignOut }) {
  const gymLabel = branding?.name || 'GymAxis';
  const accent = branding?.primary_brand_colour || 'var(--color-brand-cyan)';
  return (
    <header className="sticky top-0 z-30 bg-[var(--color-surface-darker)]/90 backdrop-blur border-b border-white/10 px-5 py-3 flex items-center justify-between">
      <div className="flex items-center gap-3 min-w-0">
        {branding?.logo_url && <img src={branding.logo_url} alt={gymLabel} className="h-7 w-7 rounded" />}
        <div className="min-w-0">
          <div className="text-[9px] font-bold uppercase tracking-[0.25em] truncate" style={{ color: accent }}>{gymLabel}</div>
          <div className="text-sm font-extrabold truncate">Hello, {member.first_name}</div>
        </div>
      </div>
      <button onClick={onSignOut} className="p-2 rounded-lg text-white/50 hover:bg-white dark:bg-zinc-900/5" data-testid="member-signout"><LogOut size={15} /></button>
    </header>
  );
}

/* ─────────────────── Install prompt (PWA / A2HS · iter 215am) ─────────────────── */
/**
 * Captures the browser's `beforeinstallprompt` event (Chrome/Android) and,
 * once ready, shows a tiny dismissible banner that fires the native
 * install dialog when tapped. iOS Safari doesn't fire the event so we
 * fall back to a hint-style banner ("Tap [Share] then [Add to Home
 * Screen]") on iPhones, which is the only supported A2HS path on iOS.
 *
 * The banner is dismissible per-device via localStorage so a member who
 * said "no thanks" never sees it again. Once installed, the
 * `appinstalled` event clears the deferredPrompt and we hide.
 */
const INSTALL_DISMISS_KEY = 'gymaxis_member_install_dismissed';

function InstallPrompt({ brandColor }) {
  const [deferred, setDeferred] = React.useState(null);
  const [iosHint, setIosHint] = React.useState(false);
  const [dismissed, setDismissed] = React.useState(
    () => localStorage.getItem(INSTALL_DISMISS_KEY) === '1'
  );

  React.useEffect(() => {
    if (dismissed) return undefined;

    // Already installed → no banner.
    if (window.matchMedia('(display-mode: standalone)').matches) {
      return undefined;
    }

    const onBefore = (e) => {
      e.preventDefault();
      setDeferred(e);
    };
    const onInstalled = () => {
      setDeferred(null);
      // Persist so we don't pester them again on reload of older Chrome.
      try { localStorage.setItem(INSTALL_DISMISS_KEY, '1'); } catch { /* storage quota */ }
    };
    window.addEventListener('beforeinstallprompt', onBefore);
    window.addEventListener('appinstalled', onInstalled);

    // iOS fallback — Safari never fires beforeinstallprompt.
    const ua = window.navigator.userAgent;
    const isIos = /iPhone|iPad|iPod/i.test(ua) && !/CriOS|FxiOS/i.test(ua);
    if (isIos) setIosHint(true);

    return () => {
      window.removeEventListener('beforeinstallprompt', onBefore);
      window.removeEventListener('appinstalled', onInstalled);
    };
  }, [dismissed]);

  const close = () => {
    setDismissed(true);
    try { localStorage.setItem(INSTALL_DISMISS_KEY, '1'); } catch { /* storage quota */ }
  };

  const install = async () => {
    if (!deferred) return;
    deferred.prompt();
    try {
      await deferred.userChoice;
    } catch { /* user dismissed */ }
    setDeferred(null);
    // Either way, don't re-show the banner this session.
    setDismissed(true);
    try { localStorage.setItem(INSTALL_DISMISS_KEY, '1'); } catch { /* storage quota */ }
  };

  if (dismissed) return null;
  if (!deferred && !iosHint) return null;

  const accent = brandColor || 'var(--color-brand-cyan)';
  return (
    <div
      className="mb-4 rounded-xl border border-white/10 bg-gradient-to-br from-white/[0.04] to-transparent p-3 flex items-start gap-3"
      data-testid="member-install-prompt"
      style={{ borderColor: `${accent}33` }}
    >
      <div
        className="shrink-0 w-9 h-9 rounded-lg flex items-center justify-center font-extrabold text-black text-sm"
        style={{ background: accent }}
        aria-hidden="true"
      >
        +
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-extrabold text-white leading-tight" data-testid="member-install-prompt-title">
          Install for one-tap access
        </p>
        <p className="text-[11px] text-white/60 mt-0.5 leading-snug">
          {deferred
            ? 'Add to your home screen so you can book classes in seconds.'
            : 'Tap the share icon, then "Add to Home Screen" to install.'}
        </p>
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        {deferred && (
          <button
            onClick={install}
            className="rounded-md px-3 py-1.5 text-[11px] font-extrabold text-black"
            style={{ background: accent }}
            data-testid="member-install-prompt-cta"
          >
            Install
          </button>
        )}
        <button
          onClick={close}
          aria-label="Dismiss install prompt"
          className="p-1 rounded-md text-white/50 hover:text-white/90 hover:bg-white/5"
          data-testid="member-install-prompt-dismiss"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}

function BottomNav({ tab, setTab }) {
  // When tab is in the More sheet (plan / family / profile), light up the
  // More pill so the user always sees where they are.
  const moreActive = ['plan', 'family', 'profile'].includes(tab);
  return (
    <nav className="fixed bottom-0 inset-x-0 z-40 bg-[var(--color-ink)] border-t border-white/10 grid grid-cols-5">
      {TABS.map((t) => {
        const Icon = t.icon;
        const active = t.id === 'more' ? moreActive : tab === t.id;
        return (
          <button key={t.id} onClick={() => setTab(t.id)} data-testid={`member-tab-${t.id}`}
            className={`flex flex-col items-center gap-0.5 py-3 text-[10px] font-bold uppercase tracking-wider transition ${active ? 'text-[var(--color-brand-cyan)]' : 'text-white/50 hover:text-white/80'}`}>
            <Icon size={18} />
            {t.label}
          </button>
        );
      })}
    </nav>
  );
}


/* ─────────────────── More sheet ─────────────────── */
/**
 * Bottom sheet shown when the user taps the "More" pill. Houses the
 * secondary tabs (Plan / Family / Profile). Renders inside the existing
 * portal frame so brand colour theming carries through.
 */
function MoreSheet({ open, currentTab, onSelect, onClose }) {
  const vocab = useStudioVocab();
  if (!open) return null;
  // Thread vocab.member_plural into the Family entry so a parent at a
  // cheer club sees "Your athletes", a swim school sees "Your swimmers".
  const items = MORE_ITEMS.map((item) => (
    item.id === 'family'
      ? { ...item, label: `Your ${vocab.member_plural}` }
      : item
  ));
  return (
    <div
      className="fixed inset-0 z-50 flex flex-col justify-end"
      onClick={onClose}
      data-testid="member-more-sheet-overlay"
    >
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
      <div
        className="relative bg-[var(--color-ink)] border-t border-white/10 rounded-t-2xl pb-[env(safe-area-inset-bottom)] pt-3 px-3 animate-in slide-in-from-bottom duration-200"
        onClick={(e) => e.stopPropagation()}
        data-testid="member-more-sheet"
      >
        <div className="mx-auto w-10 h-1.5 rounded-full bg-white/20 mb-3" aria-hidden />
        <div className="space-y-1 pb-4">
          {items.map((item) => {
            const Icon = item.icon;
            const active = currentTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelect(item.id)}
                className={`w-full flex items-center gap-3 px-4 py-3.5 rounded-xl transition ${active ? 'bg-[rgb(var(--rgb-brand-cyan)/0.1)] text-[var(--color-brand-cyan)]' : 'text-white hover:bg-white/5 dark:bg-zinc-900'}`}
                data-testid={`member-more-item-${item.id}`}
              >
                <Icon size={20} />
                <span className="text-base font-semibold">{item.label}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}


/* ─────────────────── Book ─────────────────── */

function BookTab({ headers, slug }) {
  const vocab = useStudioVocab();
  const [occs, setOccs] = useState([]);
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [loading, setLoading] = useState(true);
  const [actingId, setActingId] = useState(null);
  const [familyPickerOcc, setFamilyPickerOcc] = useState(null);
  const [subProfiles, setSubProfiles] = useState([]);
  const confirmFn = useConfirm();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const from = weekStart.toISOString();
      const to = new Date(weekStart.getTime() + 7 * 86400000).toISOString();
      const [tt, sps] = await Promise.all([
        axios.get(`${API}/member/timetable`, { headers, params: { from, to } }),
        axios.get(`${API}/member/sub-profiles`, { headers }).catch(() => ({ data: { sub_profiles: [] } })),
      ]);
      setOccs(tt.data.occurrences || []);
      setSubProfiles(sps.data?.sub_profiles || []);
    } catch { notify.error('Failed to load timetable'); }
    finally { setLoading(false); }
  }, [headers, weekStart]);
  useEffect(() => { load(); }, [load]);

  const book = async (occ) => {
    // If member has sub-profiles, open the multi-attendee picker so they
    // can include kids/partner. Otherwise straight-through book.
    if (subProfiles.length > 0) {
      setFamilyPickerOcc(occ);
      return;
    }
    setActingId(occ.id);
    try {
      await axios.post(`${API}/member/bookings`, { occurrence_id: occ.id }, { headers });
      notify.success(`Booked · ${occ.name}`);
      load();
    } catch (err) { notifyApiError(notify, err, 'Failed to book'); }
    finally { setActingId(null); }
  };

  const confirmFamilyBooking = async (attendees) => {
    const occ = familyPickerOcc;
    setFamilyPickerOcc(null);
    setActingId(occ.id);
    try {
      const r = await axios.post(`${API}/member/bookings`,
        { occurrence_id: occ.id, attendees },
        { headers });
      const booked = r.data.booked ?? (r.data.booking ? 1 : 0);
      const wl = r.data.waitlisted || 0;
      // Iter 216ae+ — vocab-aware booking toast so a cheer club says
      // "2 athletes booked" and a swim school says "2 swimmers booked".
      const peopleNoun = booked === 1 ? vocab.member_singular : vocab.member_plural;
      notify.success(
        booked && wl
          ? `${booked} ${peopleNoun} booked, ${wl} on waitlist for ${occ.name}`
          : booked > 1
          ? `${booked} ${peopleNoun} booked for ${occ.name}`
          : `Booked · ${occ.name}`,
      );
      load();
    } catch (err) { notifyApiError(notify, err, 'Failed to book'); }
    finally { setActingId(null); }
  };

  const cancel = async (bookingId, occ) => {
    const ok = await confirmFn({
      title: `Cancel booking for ${occ.name}?`,
      detail: occ.starts_at ? `Scheduled ${new Date(occ.starts_at).toLocaleString()}. If you cancel within the studio's late window, your class credit may not be refunded.` : undefined,
      tone: 'warning',
      confirmLabel: 'Yes, cancel',
      cancelLabel: 'Keep booking',
    });
    if (!ok) return;
    setActingId(occ.id);
    try {
      const { data } = await axios.delete(`${API}/member/bookings/${bookingId}`, { headers });
      notify.success(data.status === 'late_cancel' ? 'Late cancel — credit not refunded' : 'Booking cancelled');
      load();
    } catch (err) { notifyApiError(notify, err, 'Failed'); }
    finally { setActingId(null); }
  };

  const byDay = groupByDay(occs, weekStart);

  return (
    <div data-testid="member-book">
      <AdSlot slug={slug} placement="book_top" />
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-extrabold tracking-tight" style={{ letterSpacing: '-0.02em' }}>Book a class</h2>
        <div className="flex items-center gap-1">
          <button onClick={() => setWeekStart(new Date(weekStart.getTime() - 7 * 86400000))} className="p-1.5 rounded-lg border border-white/10 hover:bg-white dark:bg-zinc-900/5" data-testid="member-book-prev-week"><ChevronLeft size={14} /></button>
          <button onClick={() => setWeekStart(new Date(weekStart.getTime() + 7 * 86400000))} className="p-1.5 rounded-lg border border-white/10 hover:bg-white dark:bg-zinc-900/5" data-testid="member-book-next-week"><ChevronRight size={14} /></button>
        </div>
      </div>
      <div className="text-xs text-white/50 mb-3">{weekStart.toLocaleDateString([], { month: 'short', day: 'numeric' })} – {new Date(weekStart.getTime() + 6 * 86400000).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })}</div>

      {loading ? <CenterLoader /> : occs.length === 0 ? (
        <EmptyCard text="No classes this week. Try another week." />
      ) : (
        <div className="space-y-5">
          {byDay.map(({ day, items }) => (
            <section key={day.toISOString()} data-testid={`member-book-day-${day.getDay()}`}>
              <h3 className="text-[10px] uppercase tracking-[0.25em] font-extrabold text-white/50 mb-2">
                {day.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'short' })}
              </h3>
              {items.length === 0 ? <div className="text-xs text-white/30 italic">No classes.</div> : (
                <div className="space-y-2">
                  {items.map((o) => (
                    <ClassCard key={o.id} occ={o} busy={actingId === o.id} studioSlug={slug}
                      onBook={() => book(o)}
                      onCancel={() => cancel(o.my_booking.id, o)} />
                  ))}
                </div>
              )}
            </section>
          ))}
        </div>
      )}
      {familyPickerOcc && (
        <FamilyBookingPicker
          occ={familyPickerOcc}
          subProfiles={subProfiles}
          onClose={() => setFamilyPickerOcc(null)}
          onConfirm={confirmFamilyBooking}
        />
      )}
    </div>
  );
}


function FamilyBookingPicker({ occ, subProfiles, onClose, onConfirm }) {
  const [selectedSelf, setSelectedSelf] = useState(true);
  const [selectedSubs, setSelectedSubs] = useState(new Set());

  const toggleSub = (id) => {
    setSelectedSubs((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };

  const total = (selectedSelf ? 1 : 0) + selectedSubs.size;

  const submit = () => {
    if (total === 0) {
      notify.error('Pick at least one person');
      return;
    }
    const attendees = [];
    if (selectedSelf) attendees.push({ kind: 'self' });
    for (const id of selectedSubs) {
      attendees.push({ kind: 'sub_profile', sub_profile_id: id });
    }
    onConfirm(attendees);
  };

  return (
    <div className="fixed inset-0 z-[80] bg-black/80 grid place-items-center p-3" onClick={onClose}>
      <div className="w-full max-w-md bg-zinc-900 border border-white/10 rounded-2xl shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        data-testid="member-family-booking-picker">
        <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between">
          <div>
            <p className="text-[10px] uppercase tracking-[0.2em] font-extrabold text-[var(--color-brand-cyan)]">Who's coming?</p>
            <h3 className="text-lg font-extrabold text-white mt-0.5">{occ.name}</h3>
            <p className="text-xs text-white/50 mt-0.5">
              {new Date(occ.starts_at).toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
            </p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-white/10 text-white/60"><X size={14} /></button>
        </div>
        <div className="p-5 space-y-2">
          <label className="flex items-center gap-3 px-3 py-2.5 rounded-lg border border-white/10 cursor-pointer hover:bg-white/[0.03]"
            data-testid="member-fpicker-self">
            <input type="checkbox" checked={selectedSelf}
              onChange={(e) => setSelectedSelf(e.target.checked)}
              className="accent-[var(--color-brand-cyan)]" />
            <span className="font-bold text-white text-sm">Me</span>
          </label>
          {subProfiles.map((sp) => (
            <label key={sp.id}
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg border border-white/10 cursor-pointer hover:bg-white/[0.03]"
              data-testid={`member-fpicker-sub-${sp.id}`}>
              <input type="checkbox" checked={selectedSubs.has(sp.id)}
                onChange={() => toggleSub(sp.id)}
                className="accent-[var(--color-brand-cyan)]" />
              <span className="font-bold text-white text-sm">
                {sp.first_name} {sp.last_name}
                <span className="ml-2 text-[10px] font-extrabold tracking-wider px-1.5 py-0.5 rounded bg-white/10 text-white/60 uppercase">
                  {sp.relationship}
                </span>
              </span>
            </label>
          ))}
        </div>
        <div className="px-5 py-4 border-t border-white/10 flex items-center justify-between">
          <span className="text-xs text-white/60">
            {total === 0 ? 'No-one selected' : total === 1 ? '1 spot' : `${total} spots`}
          </span>
          <button onClick={submit} disabled={total === 0}
            className="px-4 py-2 rounded-md text-sm font-extrabold disabled:opacity-50"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
            data-testid="member-fpicker-confirm">
            Book {total > 1 ? `${total} spots` : ''}
          </button>
        </div>
      </div>
    </div>
  );
}

function ClassCard({ occ, busy, onBook, onCancel, studioSlug }) {
  const myStatus = occ.my_booking?.status;
  const wlPos = occ.my_booking?.waitlist_position;
  const pct = occ.capacity > 0 ? Math.min(100, ((occ.bookings_count || 0) / occ.capacity) * 100) : 0;
  const barColor = pct >= 95 ? 'var(--color-danger)' : pct >= 70 ? 'var(--color-warning)' : 'var(--color-success)';

  let cta;
  if (myStatus === 'booked')   cta = <CTAButton tone="cancel"  onClick={onCancel} busy={busy} testid={`member-cancel-${occ.id}`}>Cancel</CTAButton>;
  else if (myStatus === 'waitlist') cta = <CTAButton tone="cancel" onClick={onCancel} busy={busy} testid={`member-cancel-${occ.id}`}>Leave waitlist</CTAButton>;
  else if (occ.full && !occ.my_booking) cta = <CTAButton tone="waitlist" onClick={onBook} busy={busy} testid={`member-waitlist-${occ.id}`}>Join waitlist</CTAButton>;
  else                          cta = <CTAButton tone="book"   onClick={onBook}   busy={busy} testid={`member-book-${occ.id}`}>Book</CTAButton>;

  const wlCount = occ.waitlist_count || 0;
  const instructor = occ.instructor;  // { id, name, slug, photo_url } — iter 215w
  const instructorHref = instructor && studioSlug ? `/m/${studioSlug}/i/${instructor.slug}` : null;
  return (
    <div className="rounded-xl border border-white/10 bg-white dark:bg-zinc-900/[0.03] p-3.5 flex items-stretch gap-3" data-testid={`member-class-${occ.id}`}
         style={{ borderLeft: `3px solid ${occ.colour || 'var(--color-brand-cyan)'}` }}>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span className="font-bold text-white text-sm truncate">{occ.name}</span>
          {myStatus === 'booked'   && <Pill tone="emerald">Booked</Pill>}
          {myStatus === 'waitlist' && (
            <Pill tone="violet" testid={`member-waitlist-position-${occ.id}`}>
              {wlPos ? `Waitlist · #${wlPos}${wlCount ? ` of ${wlCount}` : ''}` : 'Waitlist'}
            </Pill>
          )}
        </div>
        <div className="text-xs text-white/60 flex items-center gap-3 flex-wrap">
          <span className="flex items-center gap-1"><Clock size={10} /> {formatTime(occ.starts_at)}–{formatTime(occ.ends_at)}</span>
          {instructorHref ? (
            <a href={instructorHref} onClick={(e) => e.stopPropagation()}
               className="flex items-center gap-1.5 hover:text-white transition"
               data-testid={`member-class-instructor-${occ.id}`}>
              {instructor.photo_url && (
                <img src={instructor.photo_url} alt="" className="w-4 h-4 rounded-full object-cover" />
              )}
              <span>· {instructor.name} →</span>
            </a>
          ) : occ.instructor_name && (
            <span>· {occ.instructor_name}</span>
          )}
          {occ.room_name && <span className="flex items-center gap-1"><MapPin size={10} /> {occ.room_name}</span>}
          {occ.full && wlCount > 0 && !myStatus && (
            <span className="text-violet-300 font-semibold">· {wlCount} on waitlist</span>
          )}
        </div>
        <div className="mt-2 flex items-center gap-2">
          <div className="w-24 h-1 rounded bg-white dark:bg-zinc-900/10 overflow-hidden"><div className="h-full" style={{ width: `${pct}%`, background: barColor }} /></div>
          <span className="text-[10px] text-white/50 flex items-center gap-1"><UsersIcon size={9} />{occ.bookings_count || 0}/{occ.capacity}</span>
        </div>
        <SocialPulse occId={occ.id} />
      </div>
      <div className="flex items-center">{cta}</div>
    </div>
  );
}

function SocialPulse({ occId }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    let cancel = false;
    axios.get(`${API}/member/social-pulse/${occId}`, {
      headers: { Authorization: `Bearer ${localStorage.getItem(MEMBER_TOKEN_KEY)}` },
    }).then((r) => { if (!cancel) setData(r.data); }).catch(() => {});
    return () => { cancel = true; };
  }, [occId]);
  if (!data) return null;
  const { booked_this_week, recent_names } = data;
  if (!booked_this_week && !recent_names?.length) return null;
  const pieces = [];
  if (booked_this_week > 0) pieces.push(`🔥 ${booked_this_week} booked this week`);
  if (recent_names?.length > 0) pieces.push(`${recent_names.slice(0, 2).join(', ')} just joined`);
  return (
    <div className="mt-1.5 text-[10px] text-white/55 font-medium truncate" data-testid={`member-social-pulse-${occId}`}>
      {pieces.join(' · ')}
    </div>
  );
}

function CTAButton({ tone, onClick, busy, children, testid }) {
  const styles = {
    book:     'bg-[var(--color-brand-cyan)] text-[var(--color-surface-darker)] hover:brightness-110',
    waitlist: 'bg-violet-500/20 text-violet-200 border border-violet-400/40',
    cancel:   'bg-transparent text-white/70 border border-white/20 hover:bg-white dark:bg-zinc-900/5',
  };
  return (
    <button onClick={onClick} disabled={busy} data-testid={testid}
      className={`px-3 py-2 rounded-lg text-xs font-extrabold uppercase tracking-wider transition shrink-0 ${styles[tone]} disabled:opacity-50`}>
      {busy ? '…' : children}
    </button>
  );
}

function Pill({ tone, children, testid }) {
  const map = {
    emerald: 'bg-emerald-500/20 text-emerald-300',
    violet: 'bg-violet-500/20 text-violet-300',
    amber: 'bg-amber-500/20 text-amber-300',
  };
  return <span data-testid={testid} className={`text-[9px] font-extrabold uppercase tracking-wider px-1.5 py-0.5 rounded ${map[tone]}`}>{children}</span>;
}


/* ─────────────────── Bookings ─────────────────── */

function BookingsTab({ headers, slug }) {
  const [data, setData] = useState({ upcoming: [], past: [] });
  const [loading, setLoading] = useState(true);
  const [feedUrl, setFeedUrl] = useState(null);
  const [swappingFrom, setSwappingFrom] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [payingAll, setPayingAll] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/member/bookings`, { headers });
      setData(data);
      // Iter 215u — celebrate fresh waitlist promotions.
      try {
        const seenAt = localStorage.getItem('mbr_waitlist_promo_seen_at') || '';
        let newest = seenAt;
        const fresh = (data?.upcoming || []).filter((b) => {
          const at = b.promoted_from_waitlist_at;
          if (!at) return false;
          if (at > newest) newest = at;
          return at > seenAt;
        });
        if (fresh.length > 0) {
          const first = fresh[0];
          const occName = first.occurrence?.name || 'your class';
          notify.success(`🎉 You're in! A spot just opened for ${occName}.`,
            { duration: 7000, id: `wl-promo-${first.id}` });
        }
        if (newest && newest !== seenAt) {
          localStorage.setItem('mbr_waitlist_promo_seen_at', newest);
        }
      } catch { /* badge is best-effort */ }
    }
    catch { notify.error('Failed to load bookings'); }
    finally { setLoading(false); }
  }, [headers]);
  useEffect(() => { load(); }, [load]);

  // Iter 215w — load my unpaid invoices for the Pay-all flow.
  const loadInvoices = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/member/invoices`, { headers });
      setInvoices(data.invoices || []);
    } catch { /* silent — billing is optional */ }
  }, [headers]);
  useEffect(() => { loadInvoices(); }, [loadInvoices]);

  // Returning from Stripe Checkout — show a toast & refresh.
  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    if (qs.get('paid_all')) {
      notify.success('Payment received — thank you! 🎉');
      loadInvoices();
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, [loadInvoices]);

  const unpaid = useMemo(
    () => (invoices || []).filter((i) => i.status === 'draft' || i.status === 'sent'),
    [invoices],
  );
  const outstandingPence = unpaid.reduce((s, i) => s + (i.total_pence || 0), 0);

  const payAll = async () => {
    if (unpaid.length === 0) { notify.info("You're all paid up."); return; }
    setPayingAll(true);
    try {
      const { data } = await axios.post(`${API}/member/invoices/pay-all`, {}, { headers });
      window.location.href = data.checkout_url;
    } catch (e) {
      notifyApiError(notify, e, 'Could not start checkout');
    } finally {
      setPayingAll(false);
    }
  };

  const showFeedUrl = async () => {
    try {
      const { data } = await axios.get(`${API}/member/calendar-feed`, { headers });
      setFeedUrl(data);
    } catch (e) { notifyApiError(notify, e, 'Could not get calendar feed'); }
  };

  const downloadIcs = (booking) => {
    // Token-free: the member is authed; the request opens a new tab and
    // the backend resolves the member from the bearer token. To avoid
    // sending a header on a window.open, we fetch as blob with axios
    // then trigger the download client-side.
    axios.get(`${API}/member/bookings/${booking.id}/calendar.ics`,
      { headers, responseType: 'blob' })
      .then((r) => {
        const url = URL.createObjectURL(r.data);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${(booking.occurrence?.name || 'class').replace(/\s+/g, '-').toLowerCase()}.ics`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 5000);
      })
      .catch((e) => notifyApiError(notify, e, 'Calendar download failed'));
  };

  return (
    <div data-testid="member-bookings">
      <AdSlot slug={slug} placement="bookings_top" />
      <div className="flex items-end justify-between gap-3 mb-4 flex-wrap">
        <h2 className="text-xl font-extrabold tracking-tight" style={{ letterSpacing: '-0.02em' }}>Your bookings</h2>
        <button onClick={showFeedUrl}
          className="text-[10px] uppercase tracking-wider font-bold text-[var(--color-brand-cyan)] hover:underline flex items-center gap-1"
          data-testid="member-bookings-calendar-feed">
          <CalendarPlus size={11} /> Subscribe to calendar
        </button>
      </div>
      {loading ? <CenterLoader /> : (
        <>
          <section className="mb-6">
            <h3 className="text-[10px] uppercase tracking-[0.25em] font-extrabold text-white/50 mb-2">Upcoming</h3>
            {data.upcoming.length === 0 ? <EmptyCard text="No upcoming bookings. Head to Book to grab a class." /> : (
              <AttendeeGroupedList
                bookings={data.upcoming}
                renderRow={(b) => (
                  <BookingRow key={b.id} b={b}
                    onSwap={() => setSwappingFrom(b)}
                    onAddToCalendar={() => downloadIcs(b)} />
                )} />
            )}
          </section>
          <section>
            <h3 className="text-[10px] uppercase tracking-[0.25em] font-extrabold text-white/50 mb-2">Past</h3>
            {data.past.length === 0 ? <EmptyCard text="No history yet." /> : (
              <div className="space-y-2">
                {data.past.map((b) => <BookingRow key={b.id} b={b} past onRebook={async (src) => {
                  try {
                    const { data: r } = await axios.post(`${API}/member/bookings/rebook`, { source_booking_id: src.id }, { headers });
                    if (r.already_booked) notify.info('Already booked', "You're already on the next session — see you there.");
                    else notify.success('Booked', r.status === 'waitlist' ? "You're on the waitlist." : `See you on ${new Date(r.starts_at).toLocaleString([], { weekday:'short', day:'numeric', month:'short', hour:'2-digit', minute:'2-digit' })}`);
                    load();
                  } catch (e) { notifyApiError(notify, e, 'Book again failed'); }
                }} />)}
              </div>
            )}
          </section>
        </>
      )}

      {/* Iter 215w — Outstanding invoices with one-tap Pay-all */}
      {unpaid.length > 0 && (
        <section data-testid="member-billing-outstanding">
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 flex items-center gap-4 flex-wrap">
            <div className="flex-1 min-w-0">
              <div className="text-[10px] uppercase tracking-[0.25em] font-extrabold text-amber-300 mb-1">
                {unpaid.length} invoice{unpaid.length === 1 ? '' : 's'} outstanding
              </div>
              <div className="text-xl font-black text-white">£{(outstandingPence / 100).toFixed(2)}</div>
              <div className="text-xs text-white/60 mt-0.5">
                Pay all outstanding invoices in one secure checkout.
              </div>
            </div>
            <button onClick={payAll} disabled={payingAll}
              className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-full text-sm font-extrabold"
              style={{ background: 'var(--color-brand-cyan)', color: '#0A0C10' }}
              data-testid="member-pay-all">
              {payingAll ? 'Opening checkout…' : `Pay £${(outstandingPence / 100).toFixed(2)} now →`}
            </button>
          </div>
          <div className="mt-3 space-y-1.5">
            {unpaid.map((inv) => (
              <div key={inv.id} className="flex items-center justify-between text-xs text-white/70 px-3 py-2 rounded-lg bg-white/5"
                data-testid={`member-invoice-${inv.id}`}>
                <span>{inv.period} · {inv.lines?.length || 0} line item{(inv.lines?.length || 0) === 1 ? '' : 's'}</span>
                <span className="font-bold text-white">£{(inv.total_pence / 100).toFixed(2)}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {feedUrl && <CalendarFeedModal feed={feedUrl} onClose={() => setFeedUrl(null)} headers={headers} onRotate={async () => {
        try {
          await axios.post(`${API}/member/calendar-feed/rotate`, {}, { headers });
          showFeedUrl();
          notify.success('New calendar URL — old links are now invalid');
        } catch (e) { notifyApiError(notify, e, 'Failed'); }
      }} />}
      {swappingFrom && (
        <SwapModal headers={headers} booking={swappingFrom}
          onClose={(refresh) => { setSwappingFrom(null); if (refresh) load(); }} />
      )}
    </div>
  );
}

/**
 * Iter 215y — Parent dashboard: group bookings by attendee so a parent
 * with multiple kids sees "Jamie · 3 classes / Casey · 2 classes"
 * sub-headings instead of an undifferentiated mix.
 *
 * When every booking is for the primary member (no sub-profiles), we
 * render flat — no visual noise for single-adult accounts.
 */
function AttendeeGroupedList({ bookings, renderRow }) {
  const groups = React.useMemo(() => {
    const byKey = new Map();
    for (const b of bookings) {
      const name = b.attendee_name || 'You';
      const key = b.attendee_sub_profile_id || `name:${name}:${b.attendee_kind || 'self'}`;
      if (!byKey.has(key)) byKey.set(key, { name, kind: b.attendee_kind || 'self', rows: [] });
      byKey.get(key).rows.push(b);
    }
    return Array.from(byKey.values());
  }, [bookings]);

  if (groups.length <= 1) {
    return <div className="space-y-2">{bookings.map(renderRow)}</div>;
  }
  return (
    <div className="space-y-4" data-testid="member-bookings-grouped">
      {groups.map((g) => (
        <div key={g.name + g.kind} data-testid={`member-bookings-group-${(g.name || '').toLowerCase().replace(/\s+/g, '-')}`}>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[10px] font-extrabold uppercase tracking-[0.22em] text-white/70">
              {g.name}
            </span>
            <span className="text-[10px] text-white/40">
              {g.rows.length} class{g.rows.length === 1 ? '' : 'es'}
            </span>
          </div>
          <div className="space-y-2">{g.rows.map(renderRow)}</div>
        </div>
      ))}
    </div>
  );
}


function BookingRow({ b, past, onSwap, onAddToCalendar, onRebook }) {
  const tone = {
    booked: 'emerald', waitlist: 'violet', attended: 'emerald',
    cancelled: 'amber', late_cancel: 'amber', no_show: 'amber',
  }[b.status] || 'amber';
  const canManage = !past && (b.status === 'booked' || b.status === 'waitlist');
  return (
    <div className="rounded-xl border border-white/10 bg-white dark:bg-zinc-900/[0.03] p-3.5"
      data-testid={`member-booking-${b.id}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="font-bold text-white text-sm truncate">
            {b.occurrence?.name || 'Class'}
            {b.attendee_kind === 'sub_profile' && (
              <span className="ml-1.5 text-[9px] font-extrabold tracking-wider px-1.5 py-0.5 rounded bg-fuchsia-500/20 text-fuchsia-300 uppercase">
                {b.attendee_name || 'family'}
              </span>
            )}
            {b.attendee_kind === 'guest' && (
              <span className="ml-1.5 text-[9px] font-extrabold tracking-wider px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 uppercase">
                guest: {b.attendee_name}
              </span>
            )}
            {b.swapped_from_occurrence_id && (
              <span className="ml-1.5 text-[9px] font-extrabold tracking-wider px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300 uppercase">swapped</span>
            )}
            {b.promoted_from_waitlist_at && (
              <span className="ml-1.5 text-[9px] font-extrabold tracking-wider px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 uppercase"
                data-testid={`member-booking-promoted-${b.id}`}>
                Promoted
              </span>
            )}
          </div>
          <div className="text-xs text-white/60">
            {b.occurrence?.starts_at && new Date(b.occurrence.starts_at).toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
            {b.occurrence?.room_name && ` · ${b.occurrence.room_name}`}
          </div>
        </div>
        <Pill tone={tone} testid={b.status === 'waitlist' ? `member-booking-waitlist-pos-${b.id}` : undefined}>
          {b.status === 'waitlist' && b.waitlist_position
            ? `Waitlist · #${b.waitlist_position}`
            : (b.status || '').replace('_', ' ')}
        </Pill>
      </div>
      {canManage && (
        <div className="flex gap-2 mt-3 -mx-1">
          <button onClick={onAddToCalendar}
            className="flex-1 px-2 py-1.5 rounded-md text-[10px] font-bold uppercase tracking-wider border border-white/10 text-white/80 hover:bg-white dark:bg-zinc-900/5 hover:text-white flex items-center justify-center gap-1"
            data-testid={`member-booking-cal-${b.id}`}>
            <Download size={10} /> .ics
          </button>
          {b.status === 'booked' && (
            <button onClick={onSwap}
              className="flex-1 px-2 py-1.5 rounded-md text-[10px] font-bold uppercase tracking-wider border border-blue-400/40 text-blue-300 hover:bg-blue-500/10 flex items-center justify-center gap-1"
              data-testid={`member-booking-swap-${b.id}`}>
              <ArrowLeftRight size={10} /> Swap
            </button>
          )}
        </div>
      )}
      {past && onRebook && (b.status === 'attended' || b.status === 'booked') && (
        <div className="flex mt-3 -mx-1">
          <button onClick={() => onRebook(b)}
            className="flex-1 px-2 py-1.5 rounded-md text-[10px] font-bold uppercase tracking-wider border border-[color:var(--color-brand-cyan)]/50 text-[color:var(--color-brand-cyan)] hover:bg-[color:var(--color-brand-cyan)]/10 flex items-center justify-center gap-1"
            data-testid={`member-booking-rebook-${b.id}`}>
            <RefreshCw size={10} /> Book again
          </button>
        </div>
      )}
    </div>
  );
}


function CalendarFeedModal({ feed, onClose, onRotate }) {
  const copy = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      notify.success('Copied');
    } catch { notify.error('Copy failed'); }
  };
  return (
    <div className="fixed inset-0 z-[80] bg-black/80 grid place-items-center p-3" onClick={onClose}>
      <div className="w-full max-w-md bg-zinc-900 border border-white/10 rounded-2xl p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        data-testid="member-calendar-feed-modal">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div>
            <p className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)]">Auto-syncing calendar</p>
            <h3 className="text-lg font-extrabold text-white mt-1">Subscribe — never miss a class</h3>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-white dark:bg-zinc-900/10 text-white/60"><X size={14} /></button>
        </div>

        <p className="text-xs text-white/60 mb-3">{feed.instructions}</p>

        <div className="space-y-3">
          <div>
            <p className="text-[10px] uppercase tracking-wider font-bold text-white/50 mb-1">Apple / iOS</p>
            <button onClick={() => copy(feed.webcal_url)}
              className="w-full text-left px-3 py-2 rounded-md border border-white/10 bg-white dark:bg-zinc-900/5 text-xs font-mono text-[var(--color-brand-cyan)] hover:bg-white dark:bg-zinc-900/10 truncate"
              data-testid="member-calendar-feed-webcal">
              <LinkIcon size={10} className="inline mr-1" /> {feed.webcal_url}
            </button>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider font-bold text-white/50 mb-1">Google / Outlook (paste as URL)</p>
            <button onClick={() => copy(feed.https_url)}
              className="w-full text-left px-3 py-2 rounded-md border border-white/10 bg-white dark:bg-zinc-900/5 text-xs font-mono text-[var(--color-brand-cyan)] hover:bg-white dark:bg-zinc-900/10 truncate"
              data-testid="member-calendar-feed-https">
              <LinkIcon size={10} className="inline mr-1" /> {feed.https_url}
            </button>
          </div>
        </div>

        <button onClick={onRotate}
          className="mt-4 text-[10px] uppercase tracking-wider font-bold text-white/40 hover:text-red-300"
          data-testid="member-calendar-feed-rotate">
          Reset URL (invalidates old links)
        </button>
      </div>
    </div>
  );
}


function SwapModal({ headers, booking, onClose }) {
  const [occs, setOccs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [swapping, setSwapping] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const from = new Date().toISOString();
        const to = new Date(Date.now() + 14 * 86400000).toISOString();
        const { data } = await axios.get(`${API}/member/timetable`, { headers, params: { from, to } });
        // Filter — same class name (likely same template), exclude current
        const myName = booking.occurrence?.name;
        const list = (data.occurrences || []).filter((o) =>
          o.id !== booking.occurrence_id
          && (myName ? o.name === myName : true)
          && !o.full
          && !o.my_booking
        );
        setOccs(list);
      } catch (e) {
        notifyApiError(notify, e, 'Failed');
      }
      setLoading(false);
    })();
  // eslint-disable-next-line
  }, []);

  const swap = async (target) => {
    setSwapping(target.id);
    try {
      await axios.post(`${API}/member/bookings/${booking.id}/swap`,
        { target_occurrence_id: target.id }, { headers });
      notify.success(`Swapped to ${new Date(target.starts_at).toLocaleString([], { weekday: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`);
      onClose(true);
    } catch (e) {
      notifyApiError(notify, e, 'Swap failed');
    }
    setSwapping(null);
  };

  return (
    <div className="fixed inset-0 z-[80] bg-black/80 grid place-items-center p-3" onClick={() => onClose(false)}>
      <div className="w-full max-w-md bg-zinc-900 border border-white/10 rounded-2xl shadow-2xl max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
        data-testid="member-swap-modal">
        <div className="px-5 py-4 border-b border-white/10 flex items-start justify-between">
          <div>
            <p className="text-[10px] uppercase tracking-[0.2em] font-extrabold text-blue-400">Swap booking</p>
            <h3 className="text-lg font-extrabold text-white mt-0.5">{booking.occurrence?.name}</h3>
            <p className="text-xs text-white/50 mt-0.5">
              From {new Date(booking.occurrence?.starts_at).toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
            </p>
          </div>
          <button onClick={() => onClose(false)} className="p-1.5 rounded hover:bg-white dark:bg-zinc-900/10 text-white/60"><X size={14} /></button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-3">
          {loading ? <CenterLoader /> : occs.length === 0 ? (
            <div className="text-center text-xs text-white/50 py-8">
              No alternative slots in the next 14 days. Try cancelling and rebooking.
            </div>
          ) : (
            <div className="space-y-2">
              {occs.map((o) => (
                <button key={o.id} onClick={() => swap(o)}
                  disabled={!!swapping}
                  className="w-full text-left rounded-lg border border-white/10 bg-white dark:bg-zinc-900/[0.03] p-3 hover:border-blue-400/50 hover:bg-blue-500/5 disabled:opacity-50 transition"
                  data-testid={`member-swap-target-${o.id}`}>
                  <div className="font-bold text-white text-sm">
                    {new Date(o.starts_at).toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                  </div>
                  <div className="text-[11px] text-white/60 mt-0.5">
                    {o.instructor_name} · {o.capacity - (o.bookings_count || 0)} spots left
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


/* ─────────────────── Plan (checkout + current plan) ─────────────────── */

function PlanTab({ headers, member, slug }) {
  const [plans, setPlans] = useState([]);
  const [memberships, setMemberships] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyPlan, setBusyPlan] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // Public-ish — member token allowed to read plans for their org via checkout; we'll
      // do a cheap fetch via member timetable call to confirm org, then use the plans endpoint
      // served via the member auth (memberships_payments endpoint).
      const [p, me] = await Promise.all([
        axios.get(`${API}/member/plans`, { headers }),
        axios.get(`${API}/member-auth/me`, { headers }),
      ]);
      setPlans(p.data.plans || []);
      setMemberships([]);
    } catch { notify.error('Failed to load plans'); }
    finally { setLoading(false); }
  }, [headers]);
  useEffect(() => { load(); }, [load]);

  const [checkoutPlan, setCheckoutPlan] = useState(null);
  const startCheckout = (plan) => setCheckoutPlan(plan);

  const openBillingPortal = () => {};  // deprecated — gym collects via their own channel

  return (
    <div data-testid="member-plan">
      <h2 className="text-xl font-extrabold tracking-tight mb-4" style={{ letterSpacing: '-0.02em' }}>Your plan</h2>
      <div className="rounded-xl border border-white/10 bg-white dark:bg-zinc-900/[0.03] p-4 mb-6" data-testid="member-plan-current">
        <div className="text-[10px] uppercase tracking-[0.25em] font-extrabold text-white/50 mb-2">Current status</div>
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <div className="font-bold text-white">{member.status === 'active' ? 'Active member' : 'No active plan'}</div>
            <div className="text-xs text-white/50 mt-0.5">{member.email}</div>
          </div>
          <Pill tone={member.status === 'active' ? 'emerald' : 'amber'}>{member.status}</Pill>
        </div>
      </div>
      <h3 className="text-[10px] uppercase tracking-[0.25em] font-extrabold text-white/50 mb-2">{member.status === 'active' ? 'Top up or change' : 'Choose a plan'}</h3>
      {loading ? <CenterLoader /> : plans.length === 0 ? <EmptyCard text="No plans available yet." /> : (
        <div className="space-y-2">
          {plans.map((p) => (
            <div key={p.id} className="rounded-xl border border-white/10 bg-white dark:bg-zinc-900/[0.03] p-4" data-testid={`member-plan-${p.id}`}
              style={{ borderLeft: `3px solid ${p.colour || 'var(--color-brand-cyan)'}` }}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-bold text-white text-sm flex items-center gap-2 flex-wrap">
                    {p.name}
                    {p.trial_days > 0 && (
                      <span className="text-[9px] font-extrabold tracking-wider px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 uppercase">
                        {p.trial_days}-day trial
                      </span>
                    )}
                    {p.kind === 'course' && (
                      <span className="text-[9px] font-extrabold tracking-wider px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 uppercase">
                        {p.course_session_count}-week course
                      </span>
                    )}
                    {p.kind === 'bundle' && (
                      <span className="text-[9px] font-extrabold tracking-wider px-1.5 py-0.5 rounded bg-fuchsia-500/20 text-fuchsia-300 uppercase">Bundle</span>
                    )}
                  </div>
                  <div className="text-xs text-white/60 mt-0.5 capitalize">{p.kind.replace('_', ' ')} · {p.billing_cycle}</div>
                  <div className="text-[11px] text-white/50 mt-1">
                    {p.included_classes === 'unlimited' ? 'Unlimited classes' :
                     p.credits_count ? `${p.credits_count} credits${p.pack_expiry_days ? ` · expire in ${p.pack_expiry_days}d` : ''}` : 'Credits only'}
                    {p.pt_credits_count ? ` · ${p.pt_credits_count} PT credits` : ''}
                    {p.freeze_allowed ? ' · freezable' : ''}
                    {p.cancel_notice_days > 0 ? ` · ${p.cancel_notice_days}d notice` : ''}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className="text-xl font-extrabold tracking-tight">£{(p.price_pence / 100).toFixed(2)}</div>
                  <div className="text-[10px] text-white/50 uppercase tracking-wider">{p.billing_cycle === 'oneoff' ? 'one-off' : `per ${p.billing_cycle === 'annual' ? 'year' : 'month'}`}</div>
                </div>
              </div>
              <button onClick={() => startCheckout(p)} disabled={!!busyPlan}
                className="mt-3 w-full rounded-lg py-2.5 text-xs font-extrabold uppercase tracking-wider disabled:opacity-60"
                style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
                data-testid={`member-plan-buy-${p.id}`}>
                {busyPlan === p.id ? '…' : (p.trial_days > 0 ? `Start ${p.trial_days}-day free trial` : 'Subscribe / Buy')}
              </button>
            </div>
          ))}
        </div>
      )}
      <p className="text-[10px] text-white/40 mt-5 leading-relaxed">Pay securely via Stripe — your details never touch our servers. Have a promo code? You can apply it at the next step.</p>
      {checkoutPlan && (
        <CheckoutModal API={API} headers={headers} plan={checkoutPlan} member={member}
          onClose={() => setCheckoutPlan(null)} />
      )}
    </div>
  );
}


/* ─────────────────── Checkout modal — promo + Stripe ─────────────────── */

function CheckoutModal({ API, headers, plan, member, onClose }) {
  const [code, setCode] = useState('');
  const [validating, setValidating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState(null);

  const validate = async () => {
    if (!code.trim()) { setPreview(null); setError(null); return; }
    setValidating(true); setError(null);
    try {
      const { data } = await axios.post(`${API}/memberships/promo-codes/validate`,
        { code: code.trim(), plan_id: plan.id, member_id: member.id },
        { headers });
      setPreview(data);
    } catch (e) {
      setPreview(null);
      setError(e.response?.data?.detail || 'Invalid promo code');
    }
    setValidating(false);
  };

  const [waiverDue, setWaiverDue] = useState(false);
  const [waiverName, setWaiverName] = useState('');
  const [waiverAck, setWaiverAck] = useState(false);
  const [signingWaiver, setSigningWaiver] = useState(false);

  const proceed = async () => {
    // Iter 215r — waiver gate. If this plan requires a signed waiver
    // and the member hasn't signed yet for this plan_id, surface the
    // waiver UI before we initiate Stripe checkout.
    if (plan.waiver_required && !waiverDue && !(preview && preview._waiver_cleared)) {
      // Check member's signed waivers.
      try {
        const r = await axios.get(`${API}/member/waivers/me`, { headers });
        const signed = (r.data?.waivers || []).some((w) => w.plan_id === plan.id);
        if (!signed) {
          setWaiverDue(true);
          return;
        }
      } catch { /* if we can't check, fall through — backend will enforce */ }
    }
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/memberships/checkout`, {
        plan_id: plan.id,
        origin_url: window.location.origin,
        ...(preview?.code ? { promo_code: preview.code } : {}),
      }, { headers });
      if (data?.url) {
        window.location.href = data.url;
      } else {
        notify.error('Checkout could not start');
        setBusy(false);
      }
    } catch (e) {
      notifyApiError(notify, e, 'Checkout failed');
      setBusy(false);
    }
  };

  const signWaiver = async () => {
    if (!waiverName.trim() || !waiverAck) return;
    setSigningWaiver(true);
    try {
      await axios.post(`${API}/member/waivers`, {
        plan_id: plan.id,
        signature_name: waiverName.trim(),
        acknowledged: true,
      }, { headers });
      notify.success('Waiver signed');
      setWaiverDue(false);
      // Continue straight into checkout.
      setTimeout(() => proceed(), 100);
    } catch (e) {
      notifyApiError(notify, e, 'Signing failed');
    } finally {
      setSigningWaiver(false);
    }
  };

  const finalPence = preview?.discounted_pence ?? plan.price_pence;
  const savingsPence = preview?.savings_pence || 0;

  return (
    <div className="fixed inset-0 z-[80] bg-black/80 grid place-items-center p-3" onClick={onClose}>
      <div className="w-full max-w-md bg-[color:var(--theme-surface)] dark:bg-zinc-900 border border-white/10 rounded-2xl p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}
        data-testid="member-checkout-modal">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)]">Confirm purchase</p>
            <h3 className="text-xl font-extrabold tracking-tight text-white mt-1">{plan.name}</h3>
            <p className="text-xs text-white/50 mt-0.5 capitalize">{plan.kind.replace('_', ' ')} · {plan.billing_cycle}</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-white dark:bg-zinc-900/10 text-white/60" data-testid="member-checkout-close">✕</button>
        </div>

        {plan.trial_days > 0 && (
          <div className="mt-3 rounded-lg bg-emerald-500/15 border border-emerald-500/30 px-3 py-2">
            <p className="text-xs font-bold text-emerald-300">
              {plan.trial_days}-day free trial — your card won't be charged for {plan.trial_days} days.
            </p>
          </div>
        )}

        <div className="mt-4">
          <label className="block">
            <span className="text-[10px] uppercase tracking-wider font-bold text-white/50">Promo code (optional)</span>
            <div className="flex gap-2 mt-1">
              <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())}
                onBlur={validate}
                onKeyDown={(e) => e.key === 'Enter' && validate()}
                placeholder="SUMMER25"
                className="flex-1 px-3 py-2 rounded-md text-sm font-mono uppercase border border-white/10 bg-white dark:bg-zinc-900/5 text-white focus:outline-none focus:border-[var(--color-brand-cyan)]"
                data-testid="member-checkout-promo-input" />
              <button onClick={validate} disabled={validating || !code.trim()}
                className="px-3 py-2 rounded-md text-xs font-bold border border-white/15 text-white/80 hover:bg-white dark:bg-zinc-900/10 disabled:opacity-50"
                data-testid="member-checkout-promo-apply">
                {validating ? '…' : 'Apply'}
              </button>
            </div>
          </label>
          {error && <p className="text-xs text-red-400 mt-2" data-testid="member-checkout-promo-error">{error}</p>}
          {preview && (
            <p className="text-xs text-emerald-400 mt-2" data-testid="member-checkout-promo-success">
              Promo applied · saving £{(savingsPence / 100).toFixed(2)} ({preview.duration === 'once' ? 'first invoice' : preview.duration === 'forever' ? 'every invoice' : 'first ' + preview.duration_in_months + ' months'})
            </p>
          )}
        </div>

        <div className="mt-4 rounded-lg bg-white dark:bg-zinc-900/5 border border-white/10 p-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-white/60">Plan price</span>
            <span className={savingsPence > 0 ? 'line-through text-white/40' : 'text-white font-bold'}>
              £{(plan.price_pence / 100).toFixed(2)}
            </span>
          </div>
          {savingsPence > 0 && (
            <div className="flex items-center justify-between text-sm mt-1">
              <span className="text-emerald-300">Discount</span>
              <span className="text-emerald-300 font-bold">−£{(savingsPence / 100).toFixed(2)}</span>
            </div>
          )}
          <div className="flex items-center justify-between mt-2 pt-2 border-t border-white/10">
            <span className="text-white/80 text-sm font-bold">Total today</span>
            <span className="text-2xl font-extrabold text-white" data-testid="member-checkout-final-price">
              £{(finalPence / 100).toFixed(2)}
            </span>
          </div>
        </div>

        {waiverDue ? (
          <div className="mt-4 space-y-2" data-testid="member-waiver-gate">
            <p className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-amber-400">Waiver required</p>
            <div className="max-h-40 overflow-y-auto rounded-lg border border-white/10 bg-white dark:bg-zinc-900/5 p-2.5 text-xs text-white/80 whitespace-pre-wrap" data-testid="member-waiver-text">
              {plan.waiver_text || 'By signing, you acknowledge the risks of participating in this class and confirm you are medically fit to take part.'}
            </div>
            <input type="text" placeholder="Type your full name to sign"
              value={waiverName} onChange={(e) => setWaiverName(e.target.value)}
              className="w-full h-10 rounded-lg border border-white/10 bg-transparent px-3 text-sm text-white"
              data-testid="member-waiver-name" />
            <label className="flex items-start gap-2 text-xs text-white/70">
              <input type="checkbox" className="mt-0.5" checked={waiverAck} onChange={(e) => setWaiverAck(e.target.checked)}
                data-testid="member-waiver-ack" />
              I acknowledge and accept the terms above.
            </label>
            <button onClick={signWaiver} disabled={!waiverName.trim() || !waiverAck || signingWaiver}
              className="mt-2 w-full rounded-lg py-3 text-sm font-extrabold uppercase tracking-wider disabled:opacity-60"
              style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
              data-testid="member-waiver-sign">
              {signingWaiver ? 'Signing…' : 'Sign & continue to payment'}
            </button>
          </div>
        ) : (
          <>
            <button onClick={proceed} disabled={busy}
              className="mt-4 w-full rounded-lg py-3 text-sm font-extrabold uppercase tracking-wider disabled:opacity-60"
              style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
              data-testid="member-checkout-proceed">
              {busy ? 'Redirecting to Stripe…' : 'Pay securely with Stripe'}
            </button>
            <p className="text-[10px] text-white/40 mt-3 text-center">Secured by Stripe · we never see your card details.</p>
          </>
        )}
      </div>
    </div>
  );
}


/* ─────────────────── QR Pass ─────────────────── */

function PassTab({ headers, member }) {
  const [qr, setQr] = useState(null);
  const [dataUrl, setDataUrl] = useState('');
  const [expiresIn, setExpiresIn] = useState(30);
  const pollRef = useRef(null);

  const fetchQr = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/member/qr`, { headers });
      setQr(data);
      setExpiresIn(data.expires_in || 30);
      const url = await QRCode.toDataURL(data.payload, { width: 320, margin: 1, color: { dark: 'var(--color-surface-darker)', light: 'var(--color-white)' } });
      setDataUrl(url);
    } catch { notify.error('Failed to generate pass'); }
  }, [headers]);

  useEffect(() => {
    fetchQr();
    return () => clearInterval(pollRef.current);
  }, [fetchQr]);

  useEffect(() => {
    clearInterval(pollRef.current);
    pollRef.current = setInterval(() => {
      setExpiresIn((s) => {
        if (s <= 1) { fetchQr(); return 30; }
        return s - 1;
      });
    }, 1000);
    return () => clearInterval(pollRef.current);
  }, [fetchQr, qr?.code]);

  return (
    <div data-testid="member-pass">
      <h2 className="text-xl font-extrabold tracking-tight mb-4" style={{ letterSpacing: '-0.02em' }}>Check-in pass</h2>
      <div className="rounded-2xl border border-[rgb(var(--rgb-brand-cyan)/0.3)] bg-gradient-to-br from-[rgb(var(--rgb-brand-cyan)/0.1)] to-transparent p-6 text-center">
        <div className="text-[10px] font-extrabold uppercase tracking-[0.25em] text-[var(--color-brand-cyan)] mb-3">Rotating QR · scan at reception</div>
        {dataUrl ? (
          <div className="inline-block p-4 rounded-2xl bg-white dark:bg-zinc-900" data-testid="member-qr-image">
            <img src={dataUrl} alt="Member QR pass" className="w-64 h-64" />
          </div>
        ) : <div className="w-64 h-64 mx-auto bg-white dark:bg-zinc-900/5 rounded-2xl grid place-items-center"><Loader2 className="animate-spin" /></div>}
        <div className="mt-4 text-[36px] font-extrabold tracking-[0.4em]" style={{ color: 'var(--color-brand-cyan)' }} data-testid="member-qr-code">{qr?.code || '––––––'}</div>
        <div className="mt-2 text-xs text-white/50">Refreshes in <span className="font-extrabold text-white">{expiresIn}s</span></div>
        <div className="mt-1 text-[10px] text-white/40 tracking-wider uppercase">{member.first_name} {member.last_name}</div>
      </div>
      <p className="text-xs text-white/50 mt-4 leading-relaxed">
        Show this screen at reception or the check-in kiosk. The code rotates every 30 seconds — expired codes won't scan.
      </p>
    </div>
  );
}


/* ─────────────────── Profile ─────────────────── */

function WalletCard() {
  const headers = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem(MEMBER_TOKEN_KEY)}` }), []);
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [showLedger, setShowLedger] = useState(false);
  const QUICK_AMOUNTS = [2500, 5000, 10000];  // £25 / £50 / £100

  const load = useCallback(async () => {
    try {
      const { data: d } = await axios.get(`${API}/member/wallet`, { headers });
      setData(d);
    } catch { /* non-fatal */ }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  // React to ?wallet=topped_up returning from Stripe
  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    if (qs.get('wallet') === 'topped_up') {
      notify.success('Top-up received — wallet credited');
      setTimeout(load, 1200);
    } else if (qs.get('wallet') === 'cancelled') {
      notify.info('Top-up cancelled');
    }
  }, [load]);

  const topup = async (amountPence) => {
    setBusy(true);
    try {
      const { data: d } = await axios.post(`${API}/member/wallet/topup`, { amount_pence: amountPence }, { headers });
      if (d?.checkout_url) window.location.href = d.checkout_url;
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not start top-up');
    } finally {
      setBusy(false);
    }
  };

  const balance = data?.balance_pence || 0;
  const ledger = data?.ledger || [];

  return (
    <section className="mt-5 rounded-xl border border-[rgb(var(--rgb-brand-cyan)/0.3)] bg-gradient-to-br from-[rgb(var(--rgb-brand-cyan)/0.08)] to-transparent p-4" data-testid="member-wallet-card">
      <div className="flex items-center justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="text-[10px] uppercase tracking-[0.22em] font-extrabold text-[var(--color-brand-cyan)]">Family wallet</div>
          <div className="text-3xl font-black tracking-tight mt-0.5 tabular-nums" data-testid="member-wallet-balance">
            £{(balance / 100).toFixed(2)}
          </div>
          <p className="text-[11px] text-white/50 mt-1 leading-relaxed">
            Pre-paid balance. We deduct from here first on the 1st of each month before charging your card.
          </p>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {QUICK_AMOUNTS.map((a) => (
          <button key={a} onClick={() => topup(a)} disabled={busy}
            className="rounded-lg px-3 py-2 text-[11px] font-extrabold uppercase tracking-wider border border-white/15 hover:bg-white/5"
            data-testid={`member-wallet-topup-${a}`}>
            + £{a / 100}
          </button>
        ))}
        <button onClick={() => setShowLedger((v) => !v)}
          className="ml-auto text-[10px] font-bold uppercase tracking-wider text-white/60 hover:text-white"
          data-testid="member-wallet-toggle-ledger">
          {showLedger ? 'Hide history' : 'View history'}
        </button>
      </div>
      {showLedger && (
        <div className="mt-3 pt-3 border-t border-white/10" data-testid="member-wallet-ledger">
          {ledger.length === 0 ? (
            <p className="text-[11px] text-white/40 italic">No wallet activity yet.</p>
          ) : (
            <ul className="space-y-1.5">
              {ledger.map((e) => (
                <li key={e.id} className="flex items-center justify-between text-[11px] py-0.5">
                  <span className="text-white/70">
                    <span className="font-bold uppercase tracking-wider text-[10px] text-white/50 mr-2">{e.kind}</span>
                    {e.note || '—'}
                  </span>
                  <span className={`tabular-nums font-bold ${e.amount_pence >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>
                    {e.amount_pence >= 0 ? '+' : ''}£{(e.amount_pence / 100).toFixed(2)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

function AutoPayCard() {
  const headers = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem(MEMBER_TOKEN_KEY)}` }), []);
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/member/billing/auto-pay`, { headers });
      setStatus(data);
    } catch { /* non-fatal */ }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  // If we just came back from Stripe with ?autopay=saved, poll once.
  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    if (qs.get('autopay') === 'saved') {
      notify.success('Card saved — Auto-Bill is now active');
      setTimeout(load, 800);
    } else if (qs.get('autopay') === 'cancelled') {
      notify.info('Card save cancelled');
    }
  }, [load]);

  const startSetup = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/member/billing/auto-pay/setup`, {}, { headers });
      if (data?.checkout_url) window.location.href = data.checkout_url;
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not start Auto-Bill setup');
    } finally {
      setBusy(false);
    }
  };

  const disable = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/member/billing/auto-pay/disable`, {}, { headers });
      notify.success('Auto-Bill turned off');
      await load();
    } catch {
      notify.error('Could not disable Auto-Bill');
    } finally {
      setBusy(false);
    }
  };

  const enabled = !!status?.enabled;

  return (
    <section className="mt-5 rounded-xl border border-white/10 bg-white dark:bg-zinc-900/[0.03] p-4" data-testid="member-autopay-card">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-extrabold flex items-center gap-2">
            Family Auto-Bill
            {enabled && (
              <span className="text-[9px] font-extrabold uppercase tracking-wider px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300"
                data-testid="member-autopay-badge">Active</span>
            )}
          </p>
          <p className="text-[11px] text-white/50 mt-1 leading-relaxed">
            {enabled
              ? `We'll quietly charge ${status?.card_brand ? status.card_brand.toUpperCase() : 'your card'}${status?.card_last4 ? ` •••• ${status.card_last4}` : ''} on the 1st of each month for last month's classes. Never log in to pay again.`
              : 'Save a card once — we charge it on the 1st of each month for last month\'s invoice. One less login for busy parents.'}
          </p>
        </div>
        {enabled ? (
          <button onClick={disable} disabled={busy}
            className="shrink-0 rounded-lg px-3 py-2 text-[10px] font-extrabold uppercase tracking-wider border border-red-500/30 text-red-300 hover:bg-red-500/10"
            data-testid="member-autopay-disable">
            {busy ? '…' : 'Turn off'}
          </button>
        ) : (
          <button onClick={startSetup} disabled={busy}
            className="shrink-0 rounded-lg px-3 py-2 text-[11px] font-extrabold uppercase tracking-wider"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
            data-testid="member-autopay-enable">
            {busy ? 'Loading…' : 'Set up →'}
          </button>
        )}
      </div>
    </section>
  );
}

function ProfileTab({ member, onSignOut, slug }) {
  const [ref, setRef] = useState(null);
  const headers = useMemo(() => ({ Authorization: `Bearer ${localStorage.getItem(MEMBER_TOKEN_KEY)}` }), []);
  const [dropInOptIn, setDropInOptIn] = useState(!!member.drop_in_optin);
  const [dropInBusy, setDropInBusy] = useState(false);
  useEffect(() => {
    axios.get(`${API}/member/referrals`, { headers }).then((r) => setRef(r.data)).catch(() => {});
  }, [headers]);

  const toggleDropIn = async () => {
    const next = !dropInOptIn;
    setDropInBusy(true);
    setDropInOptIn(next);
    try {
      await axios.post(`${API}/member/dropin-optin`, { opt_in: next }, { headers });
      notify.success(next ? "You'll get drop-in invites" : 'Drop-in invites turned off');
    } catch (e) {
      setDropInOptIn(!next);  // revert
      notify.error('Could not save preference');
    }
    setDropInBusy(false);
  };

  const baseUrl = slug ? `${window.location.origin}/m/${slug}` : `${window.location.origin}/members`;
  const shareUrl = ref ? `${baseUrl}?ref=${ref.code}` : '';
  const copyCode = async () => {
    try { await navigator.clipboard.writeText(ref.code); notify.success('Code copied'); }
    catch { window.prompt('Your referral code:', ref.code); }
  };
  const shareLink = async () => {
    if (navigator.share) {
      try { await navigator.share({ title: 'Join me at the studio', url: shareUrl, text: `Use my code ${ref.code} for £5 off your first class.` }); return; }
      catch { /* fallthrough to copy */ }
    }
    try { await navigator.clipboard.writeText(shareUrl); notify.success('Share link copied'); }
    catch { window.prompt('Share this link:', shareUrl); }
  };

  return (
    <div data-testid="member-profile">
      <h2 className="text-xl font-extrabold tracking-tight mb-4" style={{ letterSpacing: '-0.02em' }}>Profile</h2>
      <div className="rounded-xl border border-white/10 bg-white dark:bg-zinc-900/[0.03] p-5 space-y-3">
        <Row label="Name" value={`${member.first_name} ${member.last_name || ''}`} />
        <Row label="Email" value={member.email} />
        <Row label="Phone" value={member.phone || '—'} />
        <Row label="Status" value={<Pill tone={member.status === 'active' ? 'emerald' : 'amber'}>{member.status}</Pill>} />
        <Row label="Member since" value={member.created_at ? new Date(member.created_at).toLocaleDateString() : '—'} />
      </div>

      <section className="mt-5 rounded-xl border border-white/10 bg-white dark:bg-zinc-900/[0.03] p-4" data-testid="member-dropin-card">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-extrabold">Drop-in invites</p>
            <p className="text-[11px] text-white/50 dark:text-white/50 mt-1 leading-relaxed">
              Get a heads-up email when a class you'd like opens up at the last minute.
            </p>
          </div>
          <button onClick={toggleDropIn} disabled={dropInBusy}
            className={`relative w-12 h-6 rounded-full transition flex-shrink-0 ${dropInOptIn ? 'bg-emerald-500' : 'bg-white/15 dark:bg-zinc-900'}`}
            data-testid="member-dropin-optin-toggle">
            <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-transform ${dropInOptIn ? 'translate-x-6' : 'translate-x-0.5'}`} />
          </button>
        </div>
      </section>
      <AutoPayCard />
      <WalletCard />
      {ref && (
        <section className="mt-6" data-testid="member-referral">
          <div className="rounded-xl border border-[rgb(var(--rgb-brand-cyan)/0.3)] bg-gradient-to-br from-[rgb(var(--rgb-brand-cyan)/0.1)] to-transparent p-5">
            <div className="text-[10px] uppercase tracking-[0.25em] font-extrabold text-[var(--color-brand-cyan)] mb-2">Bring a friend · £5 each</div>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-[9px] font-bold uppercase tracking-[0.2em] text-white/50">Your code</div>
                <div className="text-2xl font-extrabold tracking-tight mt-0.5" data-testid="member-referral-code">{ref.code}</div>
              </div>
              <div className="flex gap-2">
                <button onClick={copyCode} className="px-3 py-2 rounded-lg text-[10px] font-extrabold uppercase tracking-wider border border-white/15 text-white/80 hover:bg-white dark:bg-zinc-900/5" data-testid="member-referral-copy">Copy</button>
                <button onClick={shareLink} className="px-3 py-2 rounded-lg text-[10px] font-extrabold uppercase tracking-wider" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }} data-testid="member-referral-share">Share</button>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3 mt-4 pt-4 border-t border-white/10">
              <Stat label="Friends joined" value={ref.stats.friends_joined} />
              <Stat label="Pending"         value={ref.stats.pending} />
              <Stat label="Credit earned"   value={`£${(ref.stats.credit_earned_pence / 100).toFixed(2)}`} />
            </div>
          </div>
          <p className="text-[10px] text-white/40 mt-3 leading-relaxed text-center">Credit lands the moment your friend pays for their first plan.</p>
        </section>
      )}
      <button onClick={onSignOut} className="mt-5 w-full rounded-lg py-3 text-sm font-bold border border-red-500/30 bg-red-500/5 text-red-300 hover:bg-red-500/15" data-testid="member-profile-signout">
        Sign out
      </button>
      <div className="mt-6 text-[10px] text-white/30 text-center tracking-wider uppercase">GymAxis Memberships · Phase 1a</div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div>
      <div className="text-xl font-extrabold tracking-tight">{value}</div>
      <div className="text-[9px] font-bold uppercase tracking-[0.2em] text-white/50 mt-0.5">{label}</div>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1">
      <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/40">{label}</span>
      <span className="text-sm font-bold text-white text-right">{value}</span>
    </div>
  );
}


/* ─────────────────── Ads ─────────────────── */

function AdSlot({ slug, placement }) {
  const [ads, setAds] = useState([]);
  useEffect(() => {
    if (!slug) { setAds([]); return; }
    axios.get(`${API}/m/${slug}/ads`, { params: { placement } })
      .then((r) => setAds(r.data.ads || [])).catch(() => {});
  }, [slug, placement]);
  if (ads.length === 0) return null;
  const ad = ads[0];  // one-at-a-time for now
  const click = () => {
    if (slug) axios.post(`${API}/m/${slug}/ads/${ad.id}/click`).catch(() => {});
    if (ad.cta_url) window.open(ad.cta_url, '_blank', 'noopener');
  };
  const bg = ad.background_colour || 'var(--color-brand-cyan)';
  return (
    <div onClick={click} data-testid={`member-ad-${ad.id}`}
      className={`rounded-xl p-4 mb-4 cursor-pointer transition hover:scale-[1.01]`}
      style={{ background: `linear-gradient(135deg, ${bg}22, transparent)`, border: `1px solid ${bg}44` }}>
      <div className="flex items-center gap-3">
        {ad.image_url && <img src={ad.image_url} alt="" className="h-12 w-12 rounded-lg object-cover" />}
        <div className="flex-1 min-w-0">
          <div className="font-extrabold text-sm text-white truncate">{ad.headline}</div>
          {ad.body && <div className="text-xs text-white/70 truncate">{ad.body}</div>}
        </div>
        {ad.cta_label && <div className="text-[10px] font-extrabold uppercase tracking-wider px-2.5 py-1 rounded shrink-0" style={{ background: bg, color: 'var(--color-surface-darker)' }}>{ad.cta_label}</div>}
      </div>
    </div>
  );
}


/* ─────────────────── Helpers ─────────────────── */

function LabelledInput({ label, value, onChange, type = 'text', required, testid }) {
  return (
    <label className="block">
      <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/50">{label}{required ? ' *' : ''}</span>
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)} required={required}
        autoCapitalize={type === 'email' ? 'none' : undefined}
        autoCorrect={type === 'email' ? 'off' : undefined}
        className="mt-1 w-full rounded-lg bg-black/40 border border-white/10 px-3 py-2.5 text-sm text-white placeholder-white/30 focus:outline-none focus:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
        data-testid={testid} />
    </label>
  );
}

function CenterLoader() {
  return <div className="py-12 grid place-items-center text-white/40"><Loader2 className="animate-spin" /></div>;
}

function EmptyCard({ text }) {
  return <div className="rounded-xl border border-white/10 bg-white dark:bg-zinc-900/[0.02] p-5 text-center text-white/50 text-sm">{text}</div>;
}

function formatTime(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function startOfWeek(d) {
  const copy = new Date(d); copy.setHours(0, 0, 0, 0);
  const day = copy.getDay();
  copy.setDate(copy.getDate() - day);  // Sunday
  return copy;
}

function groupByDay(occs, weekStart) {
  const days = [...Array(7)].map((_, i) => {
    const d = new Date(weekStart.getTime() + i * 86400000); d.setHours(0, 0, 0, 0); return d;
  });
  return days.map((day) => ({
    day,
    items: occs.filter((o) => new Date(o.starts_at).toDateString() === day.toDateString())
               .sort((a, b) => new Date(a.starts_at) - new Date(b.starts_at)),
  }));
}
