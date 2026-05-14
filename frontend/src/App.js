import React, { createContext, useState, useContext, useEffect, Suspense } from 'react';
import { BrowserRouter, useLocation } from 'react-router-dom';
import axios from 'axios';
import '@/App.css';
import './i18n';
import { ConfirmProvider as NotificationConfirmProvider } from '@/components/notifications';

// ═══ Cookie-based session support ═══
// The backend sets an HttpOnly `ga_session` cookie on login/register/MFA.
// Enabling `withCredentials` globally lets axios send that cookie on every
// subsequent same-origin request — defending the JWT from XSS extraction.
// The Authorization header remains in place for backward-compat and for
// cross-origin API integrations, so this is a pure additive change.
axios.defaults.withCredentials = true;

// ═══ Iter 216h68 — silent JWT refresh + session-resumed banner ═══
// When ANY operator API call returns 401, attempt ONE silent
// `/api/auth/refresh` with the current localStorage token. If the
// refresh succeeds, retry the original request transparently with
// the new token (the user never sees the failure). If the refresh
// also fails (token genuinely expired, >24 h), dispatch a global
// `gymaxis:session-expired` event so the <SessionResumedBanner>
// can offer a friendly re-auth CTA instead of the operator's
// next save silently 401-ing into the void.
//
// Concurrent 401s share a single in-flight refresh promise so we
// never spam `/auth/refresh` when a dashboard fires 6 parallel
// fetches against an expired token.
{
  const __API = `${process.env.REACT_APP_BACKEND_URL}/api`;
  let __refreshInflight = null;
  axios.interceptors.response.use(
    (resp) => resp,
    async (error) => {
      const cfg = error?.config;
      const status = error?.response?.status;
      if (!cfg || status !== 401) return Promise.reject(error);
      const url = String(cfg.url || '');
      // Only proxy operator-side `/api/*` calls. Skip auth endpoints
      // (avoid loops), CRM (UnifiedAuthProvider handles cross-login),
      // and member portal (different token kind).
      if (!url.includes('/api/')) return Promise.reject(error);
      if (
        url.includes('/api/auth/login') ||
        url.includes('/api/auth/register') ||
        url.includes('/api/auth/refresh') ||
        url.includes('/api/auth/me') ||
        url.includes('/api/crm/') ||
        url.includes('/api/member/')
      ) {
        return Promise.reject(error);
      }
      if (cfg.__sessionRetried) return Promise.reject(error);
      const currentToken = (() => {
        try { return localStorage.getItem('token'); } catch { return null; }
      })();
      if (!currentToken) return Promise.reject(error);
      if (!__refreshInflight) {
        __refreshInflight = axios.post(
          `${__API}/auth/refresh`, {},
          { headers: { Authorization: `Bearer ${currentToken}` }, timeout: 8000 },
        ).then((r) => {
          const next = r?.data?.token || null;
          if (next) {
            try { localStorage.setItem('token', next); } catch { /* quota */ }
            try {
              window.dispatchEvent(new CustomEvent('gymaxis:token-refreshed', { detail: { token: next } }));
            } catch { /* ignore */ }
          }
          return next;
        }).catch(() => null).finally(() => {
          // Release the gate on next macrotask so callers waiting on
          // the same promise still get the resolved value, but the
          // NEXT wave of 401s can re-trigger.
          setTimeout(() => { __refreshInflight = null; }, 0);
        });
      }
      const next = await __refreshInflight;
      if (!next) {
        try {
          window.dispatchEvent(new CustomEvent('gymaxis:session-expired'));
        } catch { /* ignore */ }
        return Promise.reject(error);
      }
      cfg.__sessionRetried = true;
      cfg.headers = cfg.headers || {};
      cfg.headers.Authorization = `Bearer ${next}`;
      return axios(cfg);
    },
  );
}

import AppRoutes from '@/routes/AppRoutes';
import TrialBanner from './components/TrialBanner';
import ScrollToTop from './components/shared/ScrollToTop';
import GlobalDragGuard from './components/shared/GlobalDragGuard';
import { UploadQueueProvider } from './components/shared/UploadQueue';
import { UnifiedAuthProvider } from './components/shared/UnifiedAuthProvider';
import TrialLockedPage from './components/TrialLockedPage';
import CookieConsent from './components/shared/CookieConsent';
import OfflineBanner from './components/shared/OfflineBanner';
import PWAInstallPrompt from './components/PWAInstallPrompt';
import AskGymAxis from './components/AskGymAxis';
import NPSWidget from './components/shared/NPSWidget';
import FeedbackWidget from './components/shared/FeedbackWidget';
import SessionResumedBanner from './components/shared/SessionResumedBanner';
import UnifiedAssistant from './components/UnifiedAssistant';
import CommandPalette, { useCommandPalette } from './components/CommandPalette';

/**
 * Show the legacy AskGymAxis purple-orb only on routes where the new
 * UnifiedAssistant doesn't take over. UnifiedAssistant covers /pulse,
 * /memberships, /marketing — anywhere else (landing, dashboards, master
 * admin) AskGymAxis still appears for now. Lives outside BrowserRouter
 * so we read window.location directly.
 */
function AskGymAxisGuard() {
 const path = typeof window !== 'undefined' ? window.location.pathname : '/';
 const handledByUnified =
 path === '/' ||
 path.startsWith('/platform/') ||
 path.startsWith('/marketing') ||
 path.startsWith('/pulse') ||
 path.startsWith('/memberships') ||
 path.startsWith('/master-admin') ||
 path.startsWith('/crm') ||
 path === '/dashboard';
 if (handledByUnified) return null;
 return <AskGymAxis />;
}
import { Toaster } from 'sonner';

import GuidedTour from './components/shared/GuidedTour';
import SetupChecklist from './components/shared/SetupChecklist';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const AuthContext = createContext();

export const useAuth = () => useContext(AuthContext);

function App() {
 // ── Iter 216h111 — Custom-domain SPA gate ───────────────────────
 // If the current window.location.host is NOT a recognised platform
 // host, this hook hits the public host-config endpoint exactly
 // once. When a verified custom domain is found AND the visitor
 // landed on `/`, it does a single window.location.replace to the
 // tenant's configured surface (/m/{slug}/join, /m/{slug}, etc.)
 // so the SPA mounts BrandedMemberApp / JoinPage instead of the
 // GymAxis marketing site. Idempotent — never loops because the
 // redirect target path is never `/`.
 const [hostCheckDone, setHostCheckDone] = useState(false);
 const [customHostBranding, setCustomHostBranding] = useState(null);

 useEffect(() => {
   const PLATFORM_HOSTS = [
     'gymaxisai.com', 'www.gymaxisai.com',
     'pulsefitness.ai', 'www.pulsefitness.ai',
     'localhost', '127.0.0.1',
   ];
   const isPlatformHost = (hn) => {
     if (!hn) return true;
     if (PLATFORM_HOSTS.includes(hn)) return true;
     if (hn.endsWith('.preview.emergentagent.com')) return true;
     if (hn.endsWith('.emergentagent.com')) return true;
     return false;
   };
   const hostname = (typeof window !== 'undefined' && window.location.hostname) || '';
   if (isPlatformHost(hostname)) {
     setHostCheckDone(true);
     return;
   }
   // Custom domain — ask the backend if it routes anywhere.
   let cancelled = false;
   (async () => {
     try {
       const r = await axios.get(`${API}/public/host-config`, { params: { host: hostname } });
       if (cancelled) return;
       const cfg = r?.data;
       if (cfg?.matched && cfg.redirect_path) {
         setCustomHostBranding(cfg.branding || null);
         const here = window.location.pathname || '/';
         // Only redirect when the visitor is on the bare root. Any
         // explicit deep-link is preserved (lets a customer email
         // people `/m/{slug}/join?invite=…` style links).
         if (here === '/' || here === '') {
           window.location.replace(cfg.redirect_path);
           return; // Don't flip hostCheckDone — browser is navigating.
         }
       }
     } catch { /* silent; fall back to marketing site */ }
     if (!cancelled) setHostCheckDone(true);
   })();
   return () => { cancelled = true; };
 }, []);

 const [user, setUser] = useState(null);
 const [loading, setLoading] = useState(true);
 const [branding, setBranding] = useState(null);
 // Iter 215be (Phase 6) — flipped default theme from `dark` → `light`.
 // Reasoning: the entire authenticated app shell + Master Admin + CRM +
 // Memberships + Operations + Marketing + Service Desk now have premium
 // light-mode designs (Phases 1–5). Existing users keep their saved
 // preference; only first-time visitors / users who never toggled get
 // the new light default. The toggle button in the Navbar still flips
 // both ways for users who prefer dark.
 const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'light');
 // Iter 216h48 — Pre-hydrate sites + activeSite from localStorage so the
 // SiteSwitcher renders on first paint instead of flashing blank while
 // the network round-trip for /api/sites completes. Lee Somers reported
 // the switcher "disappearing" intermittently on production; root cause
 // was the page rendering with `sites = []` before `loadSites()` finished.
 // The prior fixes (auto-HQ insert, role-gating widening, dropdown viewport)
 // patched the *correctness* paths but never the *hydration race*, so the
 // bug class kept recurring under different disguises. localStorage cache
 // is refreshed every time /api/sites resolves, so it stays in sync.
 const [sites, setSites] = useState(() => {
   try {
     const cached = localStorage.getItem('sites_cache');
     if (!cached) return [];
     const parsed = JSON.parse(cached);
     return Array.isArray(parsed) ? parsed : [];
   } catch { return []; }
 });
 const [activeSite, setActiveSite] = useState(() => {
   try {
     const cached = localStorage.getItem('active_site_cache');
     return cached ? JSON.parse(cached) : null;
   } catch { return null; }
 });
 // Iter 215bz — elevate token to AuthContext so consumers can do
 // `const { token } = useAuth()` instead of reaching into localStorage
 // independently (source-of-truth divergence caused the Product Tour
 // bug where some pages read a stale token). Reads from localStorage
 // as initial value so existing `localStorage.getItem('token')` calls
 // continue to work unchanged (fully backwards-compatible).
 const [token, setToken] = useState(() => {
   try { return localStorage.getItem('token'); } catch { return null; }
 });

 useEffect(() => {
 document.documentElement.setAttribute('data-theme', theme);
 localStorage.setItem('theme', theme);
 }, [theme]);

 // Iter 215az — global brand resolver. The HTML root receives `data-brand`
 // ("pulse" | "gymaxis") so brand-token CSS rules can swap the navbar /
 // CTA cyan to the new navy → purple GymAxis palette without any per-page
 // wiring. Pulse-account / Pulse-internal users keep the legacy cyan
 // identity. The CRM has its own override (user.crm_brand) which takes
 // precedence inside that route only. Note: the route-aware update is
 // mounted inside the Router via <BrandAttrSync /> below; this initial
 // useEffect just ensures the attribute is set before first render.
 useEffect(() => {
 const path = typeof window !== 'undefined' ? window.location.pathname : '/';
 const isPulseRoute = path.startsWith('/pulse');
 const isPulseAccount = user?.account_type === 'pulse_pro' || user?.account_type === 'lite';
 // Iter 215bc — match BrandAttrSync logic so the initial render of
 // member-facing routes (/members, /m/:slug) doesn't briefly flash
 // GymAxis branding before the route-aware effect runs.
 const isMemberFacingRoute = path === '/members' || path.startsWith('/m/');
 const brandAttr = (isPulseRoute || isPulseAccount || isMemberFacingRoute) ? 'pulse' : 'gymaxis';
 document.documentElement.setAttribute('data-brand', brandAttr);
 }, [user?.account_type]);

 // Register service worker for PWA + auto-refresh on new deploy.
 //
 // Iter 215db — when a new SW activates (after the user has been on
 // the site through a deploy), we get a `controllerchange` event.
 // We do ONE clean reload so the page re-fetches the latest HTML +
 // JS bundles. Without this, users see a half-old / half-new app
 // until they manually clear cache (which is what bit us on the last
 // deploy: stale menu drawer with broken module list).
 useEffect(() => {
   if (!('serviceWorker' in navigator)) return undefined;
   let didReload = false;
   const handleControllerChange = () => {
     if (didReload) return;
     didReload = true;
     // Tiny delay so any in-flight fetch resolves before reload.
     setTimeout(() => window.location.reload(), 200);
   };
   navigator.serviceWorker.addEventListener('controllerchange', handleControllerChange);
   navigator.serviceWorker.register('/sw.js').then((reg) => {
     // Poll for updates every 5 minutes — catches deploys that land
     // while the user has the tab open without them having to refresh.
     const interval = setInterval(() => {
       reg.update().catch(() => {});
     }, 5 * 60 * 1000);
     reg.__gymaxisInterval = interval;
   }).catch(() => {});
   return () => {
     navigator.serviceWorker.removeEventListener('controllerchange', handleControllerChange);
   };
 }, []);

 const toggleTheme = () => setTheme(prev => prev === 'dark' ? 'light' : 'dark');

 const applyBranding = (brandingData, themeOverrides) => {
 if (brandingData && brandingData.primary_color && brandingData.primary_color !== 'var(--color-brand-blue)') {
 document.documentElement.style.setProperty('--brand-color', brandingData.primary_color);
 setBranding(brandingData);
 } else {
 document.documentElement.style.setProperty('--brand-color', 'var(--color-brand-blue)');
 setBranding(brandingData || null);
 }
 // Iter 216h95 — per-tenant theme overrides applied as CSS variables.
 // Picked from Master Admin → Settings & Compliance → Theme settings.
 const root = document.documentElement;
 const TOKEN_MAP = {
 primary:       ['--pulse-primary',       '--gx-brand-from'],
 primary_hover: ['--pulse-primary-hover'],
 surface:       ['--pulse-surface',       '--gx-bg-paper'],
 text:          ['--pulse-text',          '--gx-text'],
 text_muted:    ['--pulse-text-muted',    '--gx-text-muted'],
 border:        ['--pulse-border'],
 accent:        ['--gx-accent-memberships'],
 };
 const overrides = themeOverrides || {};
 Object.entries(TOKEN_MAP).forEach(([key, vars]) => {
 const v = overrides[key];
 vars.forEach((cssVar) => {
 if (v) root.style.setProperty(cssVar, v);
 else   root.style.removeProperty(cssVar);
 });
 });
 };

 const loadBranding = async (token) => {
 try {
 const res = await axios.get(`${API}/organization`, { headers: { Authorization: `Bearer ${token}` } });
 if (res.data?.branding || res.data?.theme_overrides) {
 applyBranding(res.data.branding, res.data.theme_overrides);
 }
 } catch {}
 };

 const loadSites = async (token) => {
 try {
 const res = await axios.get(`${API}/sites`, { headers: { Authorization: `Bearer ${token}` } });
 const siteList = res.data?.sites || [];
 setSites(siteList);
 // Iter 216h48 — persist for next-page-load hydration so the
 // SiteSwitcher never flashes empty between refreshes.
 try { localStorage.setItem('sites_cache', JSON.stringify(siteList)); } catch { /* quota */ }
 if (siteList.length > 0 && !activeSite) {
 setActiveSite(siteList[0]);
 try { localStorage.setItem('active_site_cache', JSON.stringify(siteList[0])); } catch { /* quota */ }
 }
 } catch {}
 };

 const refreshSites = () => {
 const token = localStorage.getItem('token');
 if (token) loadSites(token);
 };

 // Iter 216h48 — Wrapped setter that also persists the active site
 // to localStorage so a full page reload restores the operator's
 // last selection on first paint (no flash, no fallback to the first
 // site in the list).
 const setActiveSitePersisted = (site) => {
 setActiveSite(site);
 try {
 if (site) localStorage.setItem('active_site_cache', JSON.stringify(site));
 else localStorage.removeItem('active_site_cache');
 } catch { /* quota */ }
 };

 useEffect(() => {
 // Handle Service Desk impersonation: ?impersonation_token=... overrides the stored token for this tab.
 const params = new URLSearchParams(window.location.search);
 const imp = params.get('impersonation_token');
 if (imp) {
 localStorage.setItem('token', imp);
 localStorage.setItem('impersonation_active', '1');
 setToken(imp);
 params.delete('impersonation_token');
 const clean = window.location.pathname + (params.toString() ? `?${params}` : '');
 window.history.replaceState({}, '', clean);
 }
 const token = localStorage.getItem('token');
 if (token) {
 // Iter 215ac — single-retry helper so a transient /auth/me
 // failure doesn't silently log the operator out (surfaced in
 // 215z/215aa test reports as "session lost when switching
 // modules"). We retry ONCE after 800ms before giving up.
 const bootAuthMe = (attempt = 0) => {
 axios.get(`${API}/auth/me`, {
 headers: { Authorization: `Bearer ${token}` }
 })
 .then(res => {
 setUser(res.data);
 try { localStorage.setItem('user_cache', JSON.stringify({ id: res.data?.id, is_master_admin: !!res.data?.is_master_admin, account_type: res.data?.account_type })); } catch { /* quota */ }
 loadBranding(token);
 loadSites(token);
 setLoading(false);

 // Auto-refresh token (refresh every 12 hours)
 const refreshToken = () => {
 const currentToken = localStorage.getItem('token');
 if (!currentToken) return;
 axios.post(`${API}/auth/refresh`, {}, {
 headers: { Authorization: `Bearer ${currentToken}` }
 }).then(r => {
 if (r.data?.token) {
   localStorage.setItem('token', r.data.token);
   setToken(r.data.token);
 }
 }).catch(() => {});
 };
 refreshToken(); // Refresh on load
 const interval = setInterval(refreshToken, 12 * 60 * 60 * 1000);
 return () => clearInterval(interval);
 })
 .catch((err) => {
 // Only wipe the token for HARD 401/403 (actually invalid).
 // Transient failures (network / 500) → retry once, keep token.
 const code = err?.response?.status;
 const hardFail = code === 401 || code === 403;
 if (hardFail) {
 localStorage.removeItem('token');
 localStorage.removeItem('user_cache');
 setToken(null);
 setLoading(false);
 return;
 }
 if (attempt < 1) {
 setTimeout(() => bootAuthMe(attempt + 1), 800);
 return;
 }
 // Two transient failures — hydrate from cache if we have one
 // so the UI doesn't bounce to /login on a flaky network. The
 // next successful request will re-hydrate the full user doc.
 try {
 const cached = JSON.parse(localStorage.getItem('user_cache') || 'null');
 if (cached && cached.id) setUser(cached);
 } catch { /* ignore */ }
 setLoading(false);
 });
 };
 bootAuthMe();
 } else {
 setLoading(false);
 }
 }, []);

 // Iter 215ac — Cross-tab sync. If another tab logs in/out, reflect
 // it here so module-switcher navigations in a background tab don't
 // bounce to /login.
 useEffect(() => {
 const onStorage = (e) => {
 if (e.key !== 'token') return;
 if (!e.newValue) { // logout elsewhere
 setUser(null);
 setBranding(null);
 setSites([]);
 setActiveSite(null);
 setToken(null);
 // Iter 216h48 — wipe the site caches too on cross-tab logout.
 try {
 localStorage.removeItem('sites_cache');
 localStorage.removeItem('active_site_cache');
 } catch { /* quota */ }
 return;
 }
 // Login (or token refresh) elsewhere → fetch the new user doc.
 setToken(e.newValue);
 axios.get(`${API}/auth/me`, { headers: { Authorization: `Bearer ${e.newValue}` } })
 .then(res => { setUser(res.data); loadBranding(e.newValue); loadSites(e.newValue); })
 .catch(() => { /* ignore — next refresh will heal */ });
 };
 window.addEventListener('storage', onStorage);
 // Iter 216h68 — also listen for the in-tab `gymaxis:token-refreshed`
 // event fired by the axios interceptor's silent refresh. Without
 // this, useAuth().token returns the stale value until the next full
 // re-render (rare race but real on tab-focus refreshes).
 const onTokenRefreshed = (e) => {
   const next = e?.detail?.token;
   if (next) setToken(next);
 };
 window.addEventListener('gymaxis:token-refreshed', onTokenRefreshed);
 return () => {
   window.removeEventListener('storage', onStorage);
   window.removeEventListener('gymaxis:token-refreshed', onTokenRefreshed);
 };
 }, []);

 const login = (token, userData) => {
 localStorage.setItem('token', token);
 setToken(token);
 try { localStorage.setItem('user_cache', JSON.stringify({ id: userData?.id, is_master_admin: !!userData?.is_master_admin, account_type: userData?.account_type })); } catch { /* quota */ }
 setUser(userData);
 loadBranding(token);
 loadSites(token);
 window.dispatchEvent(new Event('pwa-check-install'));
 };

 const logout = () => {
 localStorage.removeItem('token');
 localStorage.removeItem('user_cache');
 // Iter 216h48 — also clear site caches so the next user logging in
 // on this device doesn't see the previous operator's sites flash
 // before /api/sites resolves.
 localStorage.removeItem('sites_cache');
 localStorage.removeItem('active_site_cache');
 // Iter 216h113h — preserve the MOD context on sign-out: visitors
 // who came in via /MODService go back to the MOD login page,
 // not the standard GymAxis marketing surface.
 const wasMOD = ['mod_site', 'mod_branch', 'mod_org'].includes(user?.account_type);
 setToken(null);
 setUser(null);
 setBranding(null);
 setSites([]);
 setActiveSite(null);
 document.documentElement.style.setProperty('--brand-color', 'var(--color-brand-blue)');
 if (wasMOD && typeof window !== 'undefined') {
   window.location.replace('/MODService');
 }
 };

 if (loading) {
 // Only show loading for protected routes that need auth
 // Public routes (/, /crm, /pulse, /features, etc.) render immediately
 const protectedRoutes = ['/dashboard', '/master-admin', '/service-desk', '/memberships', '/marketing'];
 const isProtectedRoute = typeof window !== 'undefined' && protectedRoutes.includes(window.location.pathname);
 if (isProtectedRoute) {
 return (
 <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--theme-bg)' }}>
 <div className="text-xl" style={{ color: 'var(--brand-color, var(--color-brand-blue))' }}>Loading...</div>
 </div>
 );
 }
 }

 // Iter 216h111 — while the custom-domain host-check is in flight on a
 // non-platform host, render a neutral splash so the visitor doesn't
 // see a flash of the GymAxis marketing site before being redirected
 // to the tenant's branded surface.
 if (!hostCheckDone && typeof window !== 'undefined' && window.location.pathname === '/') {
   const tint = customHostBranding?.primary_color || '#19CDFF';
   return (
     <div
       className="min-h-screen flex items-center justify-center"
       style={{ background: '#0A0C10' }}
       data-testid="custom-domain-splash"
     >
       <div className="text-sm tracking-widest uppercase" style={{ color: tint }}>Loading…</div>
     </div>
   );
 }

 return (
 <AuthContext.Provider value={{ user, token, login, logout, API, branding, applyBranding, theme, toggleTheme, sites, activeSite, setActiveSite: setActiveSitePersisted, refreshSites }}>
 <div className="App">
 {/* WCAG: Skip to main content link */}
 <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-[999] focus:bg-[var(--color-brand-blue)] focus:text-white focus:px-4 focus:py-2 focus:rounded-lg focus:text-sm">
 Skip to main content
 </a>
 <BrowserRouter>
 <NotificationConfirmProvider>
 <UnifiedAuthProvider>
 <ScrollToTop />
 <GlobalDragGuard />
 <UploadQueueProvider>
 {localStorage.getItem('impersonation_active') === '1' && (
 <div
 className="bg-red-600 text-white text-center text-xs py-1.5 px-3 flex items-center justify-center gap-3 sticky top-0 z-[200]"
 data-testid="impersonation-banner"
 >
 <span className="font-semibold">⚠ Impersonation Session Active</span>
 <span className="opacity-90">You are viewing as {user?.email}. Every action is logged.</span>
 <button
 onClick={() => { localStorage.removeItem('impersonation_active'); localStorage.removeItem('token'); window.location.href = '/service-desk'; }}
 className="underline hover:opacity-90"
 data-testid="impersonation-end-btn"
 >End session</button>
 </div>
 )}
 {user?.trial?.is_trial && !user?.is_master_admin && (user.trial.status === 'expired' || user.trial.status === 'suspended') ? (
 <TrialLockedPage />
 ) : (
 <>
 {user?.trial?.is_trial && !user?.is_master_admin && (
 <div className="fixed top-20 inset-x-0 z-40" data-testid="trial-banner-wrapper">
 <TrialBanner />
 </div>
 )}
 <Suspense fallback={
 <div className="min-h-screen flex items-center justify-center bg-black">
 <div className="animate-pulse text-sm" style={{ color: 'var(--brand-color, var(--color-brand-blue))' }}>Loading…</div>
 </div>
 }>
 <AppRoutes user={user} login={login} />
 </Suspense>
 </>
 )}
 {user && <UnifiedAssistant />}
 {user && <FeedbackWidget />}
 {user && <GuidedTour />}
 {user && <SetupChecklist />}
 {user && <GlobalCommandPalette />}
 <BrandAttrSync user={user} />
 </UploadQueueProvider>
 </UnifiedAuthProvider>
 </NotificationConfirmProvider>
 </BrowserRouter>
 <Toaster position="top-right" theme={theme} />
 <CookieConsent />
 <OfflineBanner />
 <PWAInstallPrompt />
 <SessionResumedBanner />
 {user && <AskGymAxisGuard />}
 {user && <NPSWidget />}
 </div>
 </AuthContext.Provider>
 );
}

export default App;


/**
 * Global Cmd-K wrapper. Mounts the keyboard listener and renders the
 * palette for any authenticated route. Kept inside `App.js` so the
 * router context is available.
 */
function GlobalCommandPalette() {
  const [open, setOpen] = useCommandPalette();
  return <CommandPalette open={open} setOpen={setOpen} />;
}/**
 * BrandAttrSync — keeps `<html data-brand>` in sync with the current
 * route + user account type. Mounted inside `<BrowserRouter>` so it
 * has access to react-router's location. Sets `data-brand="pulse"` on
 * any /pulse route OR for a Pulse-account user (pulse_pro / lite); else
 * `data-brand="gymaxis"`. The CSS in index.css uses this attribute to
 * swap the legacy cyan brand tokens to the new GymAxis navy → purple
 * palette globally without per-page wiring.
 */
function BrandAttrSync({ user }) {
  const location = useLocation();
  useEffect(() => {
    const path = location.pathname;
    const isPulseRoute = path.startsWith('/pulse');
    const isPulseAccount = user?.account_type === 'pulse_pro' || user?.account_type === 'lite';
    // Iter 215bc — member-facing routes (`/members` and any white-labelled
    // `/m/:slug`) are end-customer surfaces. Studios choose their own
    // brand (Pulse studios = cyan/black; custom orgs = their own logo
    // via BrandedMemberApp). To avoid leaking the GymAxis navy → purple
    // palette into a Pulse studio's member portal, we default these
    // routes to `data-brand="pulse"` so the legacy cyan tokens stay.
    // BrandedMemberApp can override per-studio if needed.
    const isMemberFacingRoute = path === '/members' || path.startsWith('/m/');
    const brandAttr = (isPulseRoute || isPulseAccount || isMemberFacingRoute) ? 'pulse' : 'gymaxis';
    document.documentElement.setAttribute('data-brand', brandAttr);
  }, [user?.account_type, location.pathname]);
  return null;
}
