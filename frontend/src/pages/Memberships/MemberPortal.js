/**
 * Pulse Fitness Memberships — Member-facing portal (/members).
 *
 * Separate identity from the operator app: uses its own JWT stored under
 * localStorage key `member_token`. The API mints tokens with `kind=member`
 * via `/api/member-auth/{register,login}`; operator endpoints reject them
 * and vice versa.
 *
 * Tabs (mobile-first):
 *   • Home      — feed of nudges
 *   • Book      — weekly timetable, tap to book / waitlist / cancel
 *   • Bookings  — upcoming + past attendance
 *   • Pass      — rotating 30-second TOTP QR for kiosk check-in
 *   • Profile   — details + sign out
 *
 * Design language mirrors the operator console: dark Pulse Fitness surface,
 * cyan (var(--color-brand-cyan)) accent, generous whitespace.
 *
 * Iter 216h173 — Tabs are now lazy chunks (React.lazy + Suspense) so the
 * initial portal bundle ships ~700 LoC instead of 2,300 LoC. The Home tab
 * is the default landing surface (kept eagerly imported); Book / Bookings
 * / Plan / Pass / Profile load on first visit.
 */
import React, { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { Toaster as SonnerToaster } from 'sonner';
import {
  Calendar, Ticket, QrCode, User, LogOut, Users, Sparkles,
  CheckCircle2, X, Loader2, CreditCard, Activity, Home, MoreHorizontal,
} from 'lucide-react';
import { useInlineBanner, notify } from '@/components/notifications';

import FamilyTab from './FamilyTab';
import HomeTab from './MemberHomeTab';
import MemberEventsTab from './MemberEventsTab';
import { StudioVocabProvider, useStudioVocab } from '@/hooks/useStudioVocab';
import { useUnifiedAuth } from '@/components/shared/UnifiedAuthProvider';
import { API, MEMBER_TOKEN_KEY, LabelledInput } from './portalShared';

// Iter 220r — operator-chosen typography + button corner style for the
// member app. Fonts are loaded from Google Fonts on demand; the button
// radius is applied via a tiny scoped stylesheet (member app only).
const FONT_STACKS = {
  inter:   { family: "'Inter', system-ui, sans-serif",         google: 'Inter:wght@400;600;800' },
  poppins: { family: "'Poppins', system-ui, sans-serif",       google: 'Poppins:wght@400;600;800' },
  manrope: { family: "'Manrope', system-ui, sans-serif",       google: 'Manrope:wght@400;600;800' },
  nunito:  { family: "'Nunito', system-ui, sans-serif",        google: 'Nunito:wght@400;700;800' },
  space:   { family: "'Space Grotesk', system-ui, sans-serif", google: 'Space+Grotesk:wght@400;600;700' },
};

function ensureFontLoaded(key) {
  const f = FONT_STACKS[key];
  if (!f || typeof document === 'undefined') return;
  const id = `gym-font-${key}`;
  if (document.getElementById(id)) return;
  const link = document.createElement('link');
  link.id = id;
  link.rel = 'stylesheet';
  link.href = `https://fonts.googleapis.com/css2?family=${f.google}&display=swap`;
  document.head.appendChild(link);
}

function ensureMemberBrandStyles() {
  if (typeof document === 'undefined' || document.getElementById('gym-member-brand-styles')) return;
  const s = document.createElement('style');
  s.id = 'gym-member-brand-styles';
  s.textContent = `
    [data-gym-btn="pill"] button { border-radius: 9999px !important; }
    [data-gym-btn="sharp"] button { border-radius: 0 !important; }
  `;
  document.head.appendChild(s);
}

// Iter 216h173 — Each tab is a lazy chunk. Webpack splits these into
// separate JS files that download on demand, slashing initial JS bundle.
const BookTab     = lazy(() => import('./tabs/BookTab'));
const BookingsTab = lazy(() => import('./tabs/BookingsTab'));
const PlanTab     = lazy(() => import('./tabs/PlanTab'));
const PassTab     = lazy(() => import('./tabs/PassTab'));
const ProfileTab  = lazy(() => import('./tabs/ProfileTab'));

const TabFallback = () => (
  <div className="py-12 grid place-items-center text-white/40" data-testid="member-tab-loading">
    <Loader2 className="animate-spin" />
  </div>
);

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
  const { t } = useTranslation();
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

  // Iter 220r — typography + button-style theming.
  const fontKey = branding?.font || 'inter';
  const fontFamily = (FONT_STACKS[fontKey] || FONT_STACKS.inter).family;
  const buttonStyle = branding?.button_style || 'soft';
  useEffect(() => { ensureMemberBrandStyles(); }, []);
  useEffect(() => { ensureFontLoaded(fontKey); }, [fontKey]);

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
    // Iter 216h202 — credit-pack purchase redirect handler.
    const creditsResult = params.get('credits');
    if (creditsResult) {
      const cleanUrl = window.location.pathname;
      window.history.replaceState({}, '', cleanUrl);
      if (creditsResult === 'purchased') {
        showPayment({
          tone: 'success',
          title: t('memberships_console.mp_credits_added', 'Credits added!'),
          detail: t('memberships_console.mp_credits_added_detail', 'Your new class pack is live — refresh to see your balance.'),
        });
        setTab('book');
      } else if (creditsResult === 'cancelled') {
        showPayment({
          tone: 'info',
          title: t('memberships_console.mp_pack_cancelled', 'Pack purchase cancelled'),
          detail: t('memberships_console.mp_pack_cancelled_detail', 'No charge taken — buy a pack any time from the Book tab.'),
        });
      }
      return;
    }
    if (!result) return;
    const cleanUrl = window.location.pathname;
    window.history.replaceState({}, '', cleanUrl);
    if (result === 'success' && sessionId) {
      setTab('plan');
      pollCheckout(sessionId);
    } else if (result === 'cancel') {
      showPayment({ tone: 'info', title: t('memberships_console.mp_checkout_cancelled', 'Checkout cancelled'), detail: t('memberships_console.mp_checkout_cancelled_detail', 'Your spot is ready whenever you are.') });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, []);

  const pollCheckout = async (sessionId, attempt = 0) => {
    if (attempt > 12) { showPayment({ tone: 'warning', title: t('memberships_console.mp_payment_processing', 'Payment still processing'), detail: t('memberships_console.mp_payment_processing_detail', "Check back in a minute — we'll email you once it settles.") }); return; }
    try {
      const { data } = await axios.get(`${API}/memberships/checkout/status/${sessionId}`);
      if (data.payment_status === 'paid') {
        showPayment({ tone: 'success', title: t('memberships_console.mp_payment_received', 'Payment received — welcome aboard!'), detail: t('memberships_console.mp_payment_received_detail', 'Your membership is now active.') });
        return;
      }
      if (data.status === 'expired') { showPayment({ tone: 'error', title: t('memberships_console.mp_checkout_expired', 'Checkout expired'), detail: t('memberships_console.mp_try_again', 'Please try again.') }); return; }
      setTimeout(() => pollCheckout(sessionId, attempt + 1), 2000);
    } catch { /* retry */
      setTimeout(() => pollCheckout(sessionId, attempt + 1), 3000);
    }
  };

  if (loading) {
    return <div data-theme="dark" className="dark min-h-screen bg-[var(--color-surface-darker)] text-white grid place-items-center"><Loader2 className="animate-spin text-[var(--color-brand-cyan)]" /></div>;
  }
  if (!member) return <AuthGate onAuthed={handleAuthed} branding={branding} slug={slug} />;

  return (
    <StudioVocabProvider vocab={vocab}>
    <div data-theme="dark" data-gym-btn={buttonStyle} style={{ fontFamily }} className="dark min-h-screen bg-[var(--color-surface-darker)] text-white pb-24" data-testid="member-portal">
      {/* Iter 216h201 — Lee reported the "Failed to book" toast renders
         on a white card. Root cause: the global <Toaster> in App.js
         inherits the operator's `theme` localStorage value (default
         'light'). For the public member portal we MUST render a local
         dark-themed Toaster so it doesn't fall back to white. */}
      <SonnerToaster position="top-right" theme="dark" richColors closeButton />
      <TopBar member={member} branding={branding} onSignOut={signOut} />
      <main className="max-w-2xl mx-auto px-4 py-6">
        {paymentBanner && <div className="mb-4">{paymentBanner}</div>}
        <RequiredFormsBanner headers={headers} />
        <ReferralCampaignBanner headers={headers} slug={slug} onCta={() => setTab('profile')} />
        <StreakCard headers={headers} />
        <InstallPrompt brandColor={branding?.primary_color} />
        <Suspense fallback={<TabFallback />}>
          {tab === 'home'     && <HomeTab headers={headers} setTab={setTab} API={API} />}
          {tab === 'book'     && <BookTab headers={headers} slug={slug} />}
          {tab === 'bookings' && <BookingsTab headers={headers} slug={slug} />}
          {tab === 'plan'     && <PlanTab headers={headers} member={member} slug={slug} />}
          {tab === 'family'   && <FamilyTab API={API} headers={headers} />}
          {tab === 'events'   && <MemberEventsTab API={API} headers={headers} />}
          {tab === 'pass'     && <PassTab headers={headers} member={member} />}
          {tab === 'profile'  && <ProfileTab member={member} onSignOut={signOut} slug={slug} />}
        </Suspense>
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
    <section className="mb-5 rounded-xl border border-white/10 bg-zinc-900/[0.04] p-4 sm:p-5" data-testid="member-streak-card">
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
      <div className="mt-3 h-1.5 rounded bg-zinc-900/5 overflow-hidden" aria-hidden>
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
          className="mt-3 rounded-xl bg-white text-slate-900 p-3 dark:bg-zinc-900 dark:text-zinc-100"
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
        className="absolute top-2 right-2 p-1.5 rounded text-white/40 hover:text-white hover:bg-zinc-900/5"
        data-testid="member-referral-campaign-dismiss" aria-label="Dismiss">
        <X size={14} />
      </button>
      <div className="flex items-center gap-2 text-[10px] font-extrabold uppercase tracking-[0.25em] text-[var(--color-brand-cyan)]">
        <Sparkles size={12} /> Refer &amp; earn
      </div>
      <div className="mt-1.5 text-base sm:text-lg font-extrabold leading-tight tracking-tight pr-6">{headline}</div>
      <div className="mt-3 h-1.5 rounded bg-zinc-900/10 overflow-hidden" aria-hidden>
        <div className="h-full rounded bg-[var(--color-brand-cyan)] transition-all" style={{ width: `${percent}%` }} />
      </div>
      <div className="flex items-center justify-between mt-2 gap-3">
        <div className="text-[11px] text-white/60">{earned} / {next_goal.threshold} friends joined</div>
        <div className="flex items-center gap-2">
          <button onClick={onCta} className="text-[10px] font-extrabold uppercase tracking-wider px-2.5 py-1.5 rounded border border-white/15 text-white/80 hover:bg-zinc-900/5" data-testid="member-referral-campaign-cta">
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
  const { t } = useTranslation();
  const [mode, setMode] = useState('login'); // 'login' | 'register'
  const gymName = branding?.name || 'Pulse Fitness';
  const accent = branding?.primary_brand_colour || 'var(--color-brand-cyan)';
  const hero = branding?.hero_image_url || null;
  const apiOrigin = API.replace(/\/api\/?$/, '');
  const fontKey = branding?.font || 'inter';
  const fontFamily = (FONT_STACKS[fontKey] || FONT_STACKS.inter).family;
  const buttonStyle = branding?.button_style || 'soft';

  return (
    <div data-theme="dark" data-gym-btn={buttonStyle} style={{ fontFamily }} className="dark min-h-screen bg-[var(--color-surface-darker)] text-white flex flex-col" data-testid="member-auth-gate">
      {hero && (
        <div className="relative w-full h-40 sm:h-48 overflow-hidden" data-testid="member-auth-hero">
          <img src={hero.startsWith('http') || hero.startsWith('data:') ? hero : `${apiOrigin}${hero}`} alt="" className="w-full h-full object-cover" loading="eager" decoding="async" />
          <div className="absolute inset-0" style={{ background: 'linear-gradient(180deg, rgba(8,9,14,0.10) 0%, var(--color-surface-darker) 100%)' }} />
        </div>
      )}
      <header className={`px-6 ${hero ? 'pt-5' : 'pt-10'} pb-6 text-center flex flex-col items-center`}>
        {branding?.logo_url ? (
          <img src={branding.logo_url} alt={gymName} className={`mx-auto h-12 rounded ${hero ? '-mt-10 mb-4 ring-4 ring-[var(--color-surface-darker)] bg-[var(--color-surface-darker)]' : 'mb-4'}`} loading="eager" decoding="async" />
        ) : (
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full mb-6" style={{ background: `${accent}1a`, border: `1px solid ${accent}33` }}>
            <Sparkles size={12} style={{ color: accent }} />
            <span className="text-[10px] font-bold tracking-[0.2em] uppercase" style={{ color: accent }}>{slug ? gymName : t('memberships_console.mp_member_badge', 'Pulse Fitness Member')}</span>
          </div>
        )}
        <h1 className="text-4xl font-extrabold tracking-tight text-center text-balance max-w-md mx-auto" style={{ letterSpacing: '-0.03em' }} data-testid="member-auth-welcome">
          {slug ? t('memberships_console.mp_welcome_to', 'Welcome to {{name}}.', { name: gymName }) : t('memberships_console.mp_welcome_generic', 'Your studio, in your pocket.')}
        </h1>
        <p className="text-sm text-white/60 mt-2 text-center max-w-xs mx-auto">{t('memberships_console.mp_welcome_sub', 'Book classes, show your QR pass, manage your plan.')}</p>
      </header>

      <div className="flex-1 flex items-start justify-center px-4 pb-10">
        <div className="w-full max-w-sm">
          <div className="flex gap-1 p-1 rounded-xl bg-zinc-900/5 border border-white/10 mb-5">
            <TabPill active={mode === 'login'}    onClick={() => setMode('login')}    testid="member-auth-tab-login" accent={accent}>{t('memberships_console.mp_sign_in', 'Sign in')}</TabPill>
            <TabPill active={mode === 'register'} onClick={() => setMode('register')} testid="member-auth-tab-register" accent={accent}>{t('memberships_console.mp_join', 'Join')}</TabPill>
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
  const { t } = useTranslation();
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
      notify.success(t('memberships_console.mp_welcome_back', 'Welcome back, {{name}}', { name: data.member.first_name }));
    } catch (err) {
      const d = err.response?.data?.detail || '';
      show({
        tone: 'error',
        title: /invalid|credential|incorrect|not found/i.test(d) ? t('memberships_console.mp_login_bad', 'Incorrect email or password') : t('memberships_console.mp_login_fail', "Couldn't sign you in"),
        detail: /invalid|credential|incorrect|not found/i.test(d)
          ? t('memberships_console.mp_login_bad_detail', 'Double-check your email and password. Tap "Forgot password" to reset.')
          : (d || t('memberships_console.mp_conn_retry', 'Please check your connection and try again.')),
      });
    } finally { setBusy(false); }
  };

  return (
    <form onSubmit={submit} className="space-y-3" data-testid="member-login-form">
      {banner}
      <LabelledInput label={t('memberships_console.mp_email', 'Email')} type="email" value={email} onChange={setEmail} required testid="member-login-email" />
      <LabelledInput label={t('memberships_console.mp_password', 'Password')} type="password" value={password} onChange={setPassword} required testid="member-login-password" />
      <button type="submit" disabled={busy}
        className="w-full rounded-lg py-3 text-sm font-extrabold uppercase tracking-wider disabled:opacity-60"
        style={{ background: accent || 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }} data-testid="member-login-submit">
        {busy ? t('memberships_console.mp_signing_in', 'Signing in…') : t('memberships_console.mp_sign_in', 'Sign in')}
      </button>
    </form>
  );
}

function RegisterForm({ onAuthed, branding, slug, accent }) {
  const { t } = useTranslation();
  const [f, setF] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    const ref = (params.get('ref') || '').toUpperCase().trim();
    return {
      first_name: '', last_name: '', email: '', password: '', phone: '',
      // Iter 216h253 — DOB split into day/month/year selects for tap-friendly mobile entry.
      dob_day: '', dob_month: '', dob_year: '',
      address_line1: '', city: '', postcode: '', country: 'United Kingdom',
      emergency_contact_name: '', emergency_contact_phone: '',
      gdpr_consent: false,
      marketing_consent: true,
      referral_code: ref,
    };
  });
  const [busy, setBusy] = useState(false);
  const { banner, show, clear } = useInlineBanner({ autoDismiss: false });

  const submit = async (e) => {
    e.preventDefault();
    clear();
    if (f.password.length < 8) {
      show({ tone: 'error', title: t('memberships_console.mp_pw_short', 'Password too short'), detail: t('memberships_console.mp_pw_short_detail', 'Please use at least 8 characters so your account stays secure.') });
      return;
    }
    if (!f.phone.trim()) {
      show({ tone: 'error', title: t('memberships_console.mp_phone_req', 'Phone number required'), detail: t('memberships_console.mp_phone_req_detail', 'Studios use this to contact you about class changes.') });
      return;
    }
    if (!f.dob_day || !f.dob_month || !f.dob_year) {
      show({ tone: 'error', title: t('memberships_console.mp_dob_req', 'Date of birth required'), detail: t('memberships_console.mp_dob_req_detail', 'Required by gym insurance providers.') });
      return;
    }
    if (!f.emergency_contact_phone.trim()) {
      show({ tone: 'error', title: t('memberships_console.mp_eg_req', 'Emergency contact phone required'), detail: t('memberships_console.mp_eg_req_detail', 'A second number we can call in case of emergency.') });
      return;
    }
    if (!f.gdpr_consent) {
      show({ tone: 'error', title: t('memberships_console.mp_tc_req', 'Please accept the Terms & Conditions'), detail: t('memberships_console.mp_tc_req_detail', 'We need your consent to process your booking & contact details.') });
      return;
    }
    setBusy(true);
    try {
      const dob = `${f.dob_year}-${String(f.dob_month).padStart(2, '0')}-${String(f.dob_day).padStart(2, '0')}`;
      const { referral_code, dob_day: _d, dob_month: _m, dob_year: _y, ...rest } = f;
      const payload = {
        ...rest, dob,
        referral_code: referral_code || undefined,
        ...(slug ? { organization_slug: slug } : { organization_id: 'mbr-demo-org' }),
      };
      const { data } = await axios.post(`${API}/member-auth/register`, payload);
      onAuthed(data.token, data.member);
      notify.success(t('memberships_console.mp_welcome_new', 'Welcome, {{name}}!', { name: data.member.first_name }) + (referral_code ? ` · ${t('memberships_console.mp_referral_applied', 'Friend referral applied')}` : ''));
    } catch (err) {
      const d = err.response?.data?.detail || '';
      show({
        tone: 'error',
        title: /already|exist|taken/i.test(d) ? t('memberships_console.mp_email_taken', 'Email already registered') : t('memberships_console.mp_reg_fail', "Couldn't create your account"),
        detail: /already|exist|taken/i.test(d)
          ? t('memberships_console.mp_email_taken_detail', 'An account with this email already exists — try signing in instead.')
          : (d || t('memberships_console.mp_reg_fail_detail', 'Please review your details and try again. If it still fails, contact support.')),
      });
    } finally { setBusy(false); }
  };

  const up = (k) => (v) => setF((prev) => ({ ...prev, [k]: v }));

  // Iter 216h253 — date dropdowns. Year range covers ages 5-100 so a
  // junior dance student and a senior fitness member both fit.
  const thisYear = new Date().getFullYear();
  const dobYears = Array.from({ length: 96 }, (_, i) => String(thisYear - 5 - i));
  const dobMonths = [
    { v: '1', l: 'Jan' }, { v: '2', l: 'Feb' }, { v: '3', l: 'Mar' }, { v: '4', l: 'Apr' },
    { v: '5', l: 'May' }, { v: '6', l: 'Jun' }, { v: '7', l: 'Jul' }, { v: '8', l: 'Aug' },
    { v: '9', l: 'Sep' }, { v: '10', l: 'Oct' }, { v: '11', l: 'Nov' }, { v: '12', l: 'Dec' },
  ];
  const dobDays = Array.from({ length: 31 }, (_, i) => String(i + 1));

  return (
    <form onSubmit={submit} className="space-y-3" data-testid="member-register-form">
      {banner}
      <div className="grid grid-cols-2 gap-3">
        <LabelledInput label={t('memberships_console.mp_first_name', 'First name')} value={f.first_name} onChange={up('first_name')} required testid="member-reg-first" />
        <LabelledInput label={t('memberships_console.mp_last_name', 'Last name')}  value={f.last_name}  onChange={up('last_name')}  required testid="member-reg-last" />
      </div>
      <LabelledInput label={t('memberships_console.mp_email', 'Email')}    type="email"    value={f.email}    onChange={up('email')}    required testid="member-reg-email" />
      <LabelledInput label={t('memberships_console.mp_phone', 'Phone')}                    value={f.phone}    onChange={up('phone')}    required placeholder="+44 7700 900000" testid="member-reg-phone" />

      {/* Date of birth — day/month/year dropdowns for thumb-friendly mobile entry */}
      <div>
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-white/60 mb-1">{t('memberships_console.mp_dob', 'Date of birth *')}</p>
        <div className="grid grid-cols-3 gap-2">
          <RegisterSelect placeholder={t('memberships_console.mp_day', 'Day')}   value={f.dob_day}   onChange={up('dob_day')}   options={dobDays.map((v) => ({ v, l: v }))} testid="member-reg-dob-day" />
          <RegisterSelect placeholder={t('memberships_console.mp_month', 'Month')} value={f.dob_month} onChange={up('dob_month')} options={dobMonths}                            testid="member-reg-dob-month" />
          <RegisterSelect placeholder={t('memberships_console.mp_year', 'Year')}  value={f.dob_year}  onChange={up('dob_year')}  options={dobYears.map((v) => ({ v, l: v }))} testid="member-reg-dob-year" />
        </div>
      </div>

      {/* Address */}
      <div>
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-white/60 mb-1">{t('memberships_console.mp_address', 'Address')}</p>
        <div className="space-y-2">
          <LabelledInput label={null} value={f.address_line1} onChange={up('address_line1')} placeholder={t('memberships_console.mp_addr1', 'Address line 1')} testid="member-reg-addr1" />
          <div className="grid grid-cols-3 gap-2">
            <LabelledInput label={null} value={f.city}     onChange={up('city')}     placeholder={t('memberships_console.mp_city', 'City')}     testid="member-reg-city" />
            <LabelledInput label={null} value={f.postcode} onChange={(v) => up('postcode')(v.toUpperCase())} placeholder={t('memberships_console.mp_postcode', 'Postcode')} testid="member-reg-postcode" />
            <RegisterSelect
              placeholder={t('memberships_console.mp_country', 'Country')}
              value={f.country}
              onChange={up('country')}
              options={['United Kingdom', 'Ireland', 'United States', 'Canada', 'Australia', 'New Zealand', 'France', 'Germany', 'Spain', 'Other'].map((c) => ({ v: c, l: c }))}
              testid="member-reg-country"
            />
          </div>
        </div>
      </div>

      {/* Emergency contact */}
      <div>
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-white/60 mb-1">{t('memberships_console.mp_emergency', 'Emergency contact')}</p>
        <div className="grid grid-cols-2 gap-3">
          <LabelledInput label={t('memberships_console.mp_name', 'Name')}  value={f.emergency_contact_name}  onChange={up('emergency_contact_name')}  placeholder={t('memberships_console.mp_eg_name_ph', 'e.g. Frank')}      testid="member-reg-eg-name" />
          <LabelledInput label={t('memberships_console.mp_phone', 'Phone')} value={f.emergency_contact_phone} onChange={up('emergency_contact_phone')} placeholder="+44 7700 900000" required testid="member-reg-eg-phone" />
        </div>
      </div>

      <LabelledInput label={t('memberships_console.mp_password_min', 'Password (min 8 characters)')} type="password" value={f.password} onChange={up('password')} required testid="member-reg-password" />
      <LabelledInput label={t('memberships_console.mp_referral_optional', 'Referral code (optional)')} value={f.referral_code} onChange={(v) => up('referral_code')(v.toUpperCase())} testid="member-reg-referral" />

      {/* Consent */}
      <div className="space-y-2 pt-1">
        <label className="flex items-start gap-2 text-[11px] cursor-pointer text-white/80" data-testid="member-reg-gdpr-row">
          <input
            type="checkbox"
            checked={f.gdpr_consent}
            onChange={(e) => up('gdpr_consent')(e.target.checked)}
            className="mt-0.5 h-4 w-4 accent-[color:var(--color-brand-cyan)]"
            data-testid="member-reg-gdpr"
          />
          <span>{t('memberships_console.mp_gdpr', "I agree to {{studio}}'s Terms & Conditions and Privacy Policy.", { studio: branding?.name || t('memberships_console.mp_the_studio', 'the studio') })} <span className="text-white/50">{t('memberships_console.mp_required', '(required)')}</span></span>
        </label>
        <label className="flex items-start gap-2 text-[11px] cursor-pointer text-white/80" data-testid="member-reg-mkt-row">
          <input
            type="checkbox"
            checked={f.marketing_consent}
            onChange={(e) => up('marketing_consent')(e.target.checked)}
            className="mt-0.5 h-4 w-4 accent-[color:var(--color-brand-cyan)]"
            data-testid="member-reg-mkt"
          />
          <span>{t('memberships_console.mp_marketing', 'Send me class reminders and offers from {{studio}}.', { studio: branding?.name || t('memberships_console.mp_the_studio', 'the studio') })} <span className="text-white/50">{t('memberships_console.mp_optional', '(optional)')}</span></span>
        </label>
      </div>

      <button type="submit" disabled={busy}
        className="w-full rounded-lg py-3 text-sm font-extrabold uppercase tracking-wider disabled:opacity-60"
        style={{ background: accent || 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }} data-testid="member-register-submit">
        {busy ? t('memberships_console.mp_creating', 'Creating account…') : t('memberships_console.mp_create_account', 'Create account')}
      </button>
    </form>
  );
}

function RegisterSelect({ placeholder, value, onChange, options, testid }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      data-testid={testid}
      className="rounded-lg px-3 py-2.5 text-sm focus:outline-none w-full"
      style={{
        background: 'rgba(255,255,255,0.06)',
        border: '1px solid rgba(255,255,255,0.18)',
        color: '#ffffff',
      }}
    >
      <option value="" style={{ background: '#0a0c10', color: '#fff' }}>{placeholder}</option>
      {options.map((o) => (
        <option key={o.v} value={o.v} style={{ background: '#0a0c10', color: '#fff' }}>{o.l}</option>
      ))}
    </select>
  );
}


/* ─────────────────── Chrome ─────────────────── */

function TopBar({ member, branding, onSignOut }) {
  const gymLabel = branding?.name || 'Pulse Fitness';
  const accent = branding?.primary_brand_colour || 'var(--color-brand-cyan)';
  return (
    <header className="sticky top-0 z-30 bg-[var(--color-surface-darker)]/90 backdrop-blur border-b border-white/10 px-5 py-3 flex items-center justify-between">
      <div className="flex items-center gap-3 min-w-0">
        {branding?.logo_url && <img src={branding.logo_url} alt={gymLabel} className="h-7 w-7 rounded" loading="eager" decoding="async" />}
        <div className="min-w-0">
          <div className="text-[9px] font-bold uppercase tracking-[0.25em] truncate" style={{ color: accent }}>{gymLabel}</div>
          <div className="text-sm font-extrabold truncate">Hello, {member.first_name}</div>
        </div>
      </div>
      <button onClick={onSignOut} className="p-2 rounded-lg text-white/50 hover:bg-zinc-900/5" data-testid="member-signout"><LogOut size={15} /></button>
    </header>
  );
}

/* ─────────────────── Install prompt (PWA / A2HS · iter 215am) ─────────────────── */
const INSTALL_DISMISS_KEY = 'gymaxis_member_install_dismissed';

function InstallPrompt({ brandColor }) {
  const [deferred, setDeferred] = React.useState(null);
  const [iosHint, setIosHint] = React.useState(false);
  const [dismissed, setDismissed] = React.useState(
    () => localStorage.getItem(INSTALL_DISMISS_KEY) === '1'
  );

  React.useEffect(() => {
    if (dismissed) return undefined;

    if (window.matchMedia('(display-mode: standalone)').matches) {
      return undefined;
    }

    const onBefore = (e) => {
      e.preventDefault();
      setDeferred(e);
    };
    const onInstalled = () => {
      setDeferred(null);
      try { localStorage.setItem(INSTALL_DISMISS_KEY, '1'); } catch { /* storage quota */ }
    };
    window.addEventListener('beforeinstallprompt', onBefore);
    window.addEventListener('appinstalled', onInstalled);

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
    setDismissed(true);
    try { localStorage.setItem(INSTALL_DISMISS_KEY, '1'); } catch { /* storage quota */ }
  };

  if (dismissed) return null;
  if (!deferred && !iosHint) return null;

  const accent = brandColor || 'var(--color-brand-cyan)';
  return (
    <div
      // eslint-disable-next-line gymaxis/no-dark-mode-leakage -- alpha-only overlay (from-white/[0.04]) over the dark portal surface; not a light background.
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
                className={`w-full flex items-center gap-3 px-4 py-3.5 rounded-xl transition ${active ? 'bg-[rgb(var(--rgb-brand-cyan)/0.1)] text-[var(--color-brand-cyan)]' : 'text-white hover:bg-white/5'}`}
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
