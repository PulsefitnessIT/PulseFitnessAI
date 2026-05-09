import React, { createContext, useState, useContext, useEffect, Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
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

// Eager-loaded: marketing entry points the demo will hit first. These must
// be in the initial bundle to avoid a Suspense fallback on landing.
import PulseLandingPage from './pages/PulseLandingPage';
import PulsePricingPage from './pages/PulsePricingPage';
import MarketingHome from './pages/Marketing/MarketingHome';
import ModulePage from './pages/Marketing/ModulePage';
import moduleService from './pages/Marketing/modules/service';
import moduleCrm from './pages/Marketing/modules/crm';
import moduleMemberships from './pages/Marketing/modules/memberships';
import moduleMarketing from './pages/Marketing/modules/marketing';
import moduleStaffing from './pages/Marketing/modules/staffing';
import moduleReporting from './pages/Marketing/modules/reporting';
import SecurityPage from './pages/SecurityPage';
import SecurityMarketingPage from './pages/Marketing/SecurityMarketingPage';
import PricingMarketingPage from './pages/Marketing/PricingMarketingPage';
import ContactMarketingPage from './pages/Marketing/ContactMarketingPage';
import TrialBanner from './components/TrialBanner';
import ScrollToTop from './components/shared/ScrollToTop';
import TrialLockedPage from './components/TrialLockedPage';
import CookieConsent from './components/shared/CookieConsent';
import OfflineBanner from './components/shared/OfflineBanner';
import PWAInstallPrompt from './components/PWAInstallPrompt';
import AskGymAxis from './components/AskGymAxis';
import NPSWidget from './components/shared/NPSWidget';
import ModuleAccessGate from './components/shared/ModuleAccessGate';
import UnifiedAssistant from './components/UnifiedAssistant';
import CommandPalette, { useCommandPalette } from './components/CommandPalette';
import TrustPage from './pages/TrustPage';

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

// Lazy-loaded: authenticated app + secondary marketing pages. Each becomes
// its own webpack chunk, so the ~2 MB of CRM / Master Admin / Service Desk
// JS no longer blocks the landing page's first paint.
const FeaturesPage = lazy(() => import('./pages/FeaturesPage'));
const PricingPage = lazy(() => import('./pages/PricingPage'));
const AboutPage = lazy(() => import('./pages/AboutPage'));
const ContactPage = lazy(() => import('./pages/ContactPage'));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'));
const WhatsNewPage = lazy(() => import('./pages/WhatsNewPage'));
const StatusPage = lazy(() => import('./pages/StatusPage'));
const DpaPage = lazy(() => import('./pages/legal/DpaPage'));
const DpiaPage = lazy(() => import('./pages/legal/DpiaPage'));
const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const LiteDashboardPage = lazy(() => import('./pages/LiteDashboardPage'));
const ResetPasswordPage = lazy(() => import('./pages/ResetPasswordPage'));
const SSOCompletePage = lazy(() => import('./pages/SSOCompletePage'));
const LoginRedirectPage = lazy(() => import('./pages/GymAxisLoginPage'));
const ApiDocsPage = lazy(() => import('./pages/ApiDocsPage'));
const SupplierCasePage = lazy(() => import('./pages/SupplierCasePage'));
const CustomerOnboardingForm = lazy(() => import('./pages/CustomerOnboardingForm'));
const QRScanPage = lazy(() => import('./pages/QRScanPage'));
const PublicFormPage = lazy(() => import('./pages/PublicFormPage'));
const PublicLandingPage = lazy(() => import('./pages/PublicLandingPage'));
const PartnershipProposalPage = lazy(() => import('./pages/PartnershipProposalPage'));
const IntegrationRequirementsPage = lazy(() => import('./pages/IntegrationRequirementsPage'));
const LearnMorePage = lazy(() => import('./pages/LearnMorePage'));
const CompareIndex = lazy(() => import('./pages/Marketing/Compare/CompareIndex'));
const CompareMindbody = lazy(() => import('./pages/Marketing/Compare/CompareMindbody'));
const CompareGlofox = lazy(() => import('./pages/Marketing/Compare/CompareGlofox'));
const CompareClubReady = lazy(() => import('./pages/Marketing/Compare/CompareClubReady'));
const BlogIndex = lazy(() => import('./pages/Marketing/Blog/BlogIndex'));
const BlogPost = lazy(() => import('./pages/Marketing/Blog/BlogPost'));
const CRMApp = lazy(() => import('./pages/CRM/CRMApp'));
const PrivacyPolicyPage = lazy(() => import('./pages/PrivacyPolicyPage'));
const TermsOfServicePage = lazy(() => import('./pages/TermsOfServicePage'));
const DirectorsHandout = lazy(() => import('./pages/DirectorsHandout'));
const PaymentSuccessPage = lazy(() => import('./pages/PaymentSuccessPage'));
const MasterAdminPage = lazy(() => import('./pages/MasterAdminPage'));
const DesignSystemPage = lazy(() => import('./pages/MasterAdmin/DesignSystemPage'));
const MarketingSuite = lazy(() => import('./pages/MarketingSuite'));
const ServiceDeskPage = lazy(() => import('./pages/ServiceDeskPage'));
const ServiceOpsDeskPage = lazy(() => import('./pages/ServiceOps/ServiceDeskPage'));
const ServiceOpsScheduler = lazy(() => import('./pages/ServiceOps/ServiceScheduler'));
const ServiceOpsEngineers = lazy(() => import('./pages/ServiceOps/EngineersAdminPage'));
const ServiceOpsParts = lazy(() => import('./pages/ServiceOps/PartsInventoryPage'));
const ServiceOpsBilling = lazy(() => import('./pages/ServiceOps/BillingPage'));
const ServiceOpsReports = lazy(() => import('./pages/ServiceOps/ServiceOpsReportsPage'));
const ServiceOpsComms = lazy(() => import('./pages/ServiceOps/CommsHubPage'));
const IntegrationsConsole = lazy(() => import('./pages/Admin/IntegrationsConsole'));
const ServiceOpsEngineerHome = lazy(() => import('./pages/ServiceOps/Engineer/EngineerHome'));
const ServiceOpsEngineerJob = lazy(() => import('./pages/ServiceOps/Engineer/EngineerJobDetail'));
const MODSiteDashboard = lazy(() => import('./pages/MODPortal/MODSiteDashboard'));
const MODProDashboard = lazy(() => import('./pages/MODPortal/MODProDashboard'));
const MembershipsConsole = lazy(() => import('./pages/Memberships/MembershipsConsole'));
const MemberPortal = lazy(() => import('./pages/Memberships/MemberPortal'));
const MemberClaimPage = lazy(() => import('./pages/Memberships/MemberClaimPage'));
const InstructorPortal = lazy(() => import('./pages/Memberships/InstructorPortal'));
const MembershipsSetupWizard = lazy(() => import('./pages/Memberships/SetupWizard'));
const GymFloorPage = lazy(() => import('./pages/GymFloor/GymFloorPage'));
const BrandedMemberApp = lazy(() => import('./pages/Memberships/BrandedMemberApp'));
const PublicClassPage = lazy(() => import('./pages/Memberships/PublicClassPage'));
const PublicInstructorPage = lazy(() => import('./pages/Memberships/PublicInstructorPage'));
const EmbedTimetable = lazy(() => import('./pages/Memberships/EmbedTimetable'));
const KioskCheckin = lazy(() => import('./pages/Memberships/KioskCheckin'));
const StaffingKioskPage = lazy(() => import('./pages/Staffing/KioskPage'));
const BrandedBragPage = lazy(() => import('./pages/Memberships/BrandedBragPage'));
const ForceChangePasswordPage = lazy(() => import('./pages/ForceChangePasswordPage'));
const HelpCentrePage = lazy(() => import('./pages/HelpCentrePage'));
import GuidedTour from './components/shared/GuidedTour';
import SetupChecklist from './components/shared/SetupChecklist';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const AuthContext = createContext();

export const useAuth = () => useContext(AuthContext);

/**
 * Iter 215bs — `/dashboard` resolver. Keeps the existing role-based routing
 * but adds a `?as=operator` escape hatch so master admins can preview the
 * GymAxis operator portal without seeding a fake user. Pulse Fitness/MOD
 * branches stay untouched.
 */
function DashboardRoute({ user }) {
  if (!user) return <Navigate to="/" />;
  const params = new URLSearchParams(window.location.search);
  const previewAsOperator = params.get('as') === 'operator';
  if (user.is_master_admin && !previewAsOperator) return <Navigate to="/master-admin" />;
  if (user.account_type === 'mod_site') return <MODSiteDashboard />;
  if (user.account_type === 'mod_branch' || user.account_type === 'mod_org') return <MODProDashboard />;
  if (!previewAsOperator && (user.account_type === 'lite' || user.account_type === 'pulse_pro')) {
    return <Navigate to="/pulse" />;
  }
  return <DashboardPage />;
}



function App() {
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
 const [sites, setSites] = useState([]);
 const [activeSite, setActiveSite] = useState(null);
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

 const applyBranding = (brandingData) => {
 if (brandingData && brandingData.primary_color && brandingData.primary_color !== 'var(--color-brand-blue)') {
 document.documentElement.style.setProperty('--brand-color', brandingData.primary_color);
 setBranding(brandingData);
 } else {
 document.documentElement.style.setProperty('--brand-color', 'var(--color-brand-blue)');
 setBranding(brandingData || null);
 }
 };

 const loadBranding = async (token) => {
 try {
 const res = await axios.get(`${API}/organization`, { headers: { Authorization: `Bearer ${token}` } });
 if (res.data?.branding) {
 applyBranding(res.data.branding);
 }
 } catch {}
 };

 const loadSites = async (token) => {
 try {
 const res = await axios.get(`${API}/sites`, { headers: { Authorization: `Bearer ${token}` } });
 const siteList = res.data?.sites || [];
 setSites(siteList);
 if (siteList.length > 0 && !activeSite) {
 setActiveSite(siteList[0]);
 }
 } catch {}
 };

 const refreshSites = () => {
 const token = localStorage.getItem('token');
 if (token) loadSites(token);
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
 return;
 }
 // Login (or token refresh) elsewhere → fetch the new user doc.
 setToken(e.newValue);
 axios.get(`${API}/auth/me`, { headers: { Authorization: `Bearer ${e.newValue}` } })
 .then(res => { setUser(res.data); loadBranding(e.newValue); loadSites(e.newValue); })
 .catch(() => { /* ignore — next refresh will heal */ });
 };
 window.addEventListener('storage', onStorage);
 return () => window.removeEventListener('storage', onStorage);
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
 setToken(null);
 setUser(null);
 setBranding(null);
 setSites([]);
 setActiveSite(null);
 document.documentElement.style.setProperty('--brand-color', 'var(--color-brand-blue)');
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

 return (
 <AuthContext.Provider value={{ user, token, login, logout, API, branding, applyBranding, theme, toggleTheme, sites, activeSite, setActiveSite, refreshSites }}>
 <div className="App">
 {/* WCAG: Skip to main content link */}
 <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-[999] focus:bg-[var(--color-brand-blue)] focus:text-white focus:px-4 focus:py-2 focus:rounded-lg focus:text-sm">
 Skip to main content
 </a>
 <BrowserRouter>
 <NotificationConfirmProvider>
 <ScrollToTop />
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
 <Routes>
 <Route path="/" element={<MarketingHome />} />
                <Route path="/legacy-home" element={<Navigate to="/" replace />} />
                <Route path="/platform/service"     element={<ModulePage module={moduleService} />} />
                <Route path="/platform/crm"         element={<ModulePage module={moduleCrm} />} />
                <Route path="/platform/memberships" element={<ModulePage module={moduleMemberships} />} />
                <Route path="/platform/marketing"   element={<ModulePage module={moduleMarketing} />} />
                <Route path="/platform/staffing"    element={<ModulePage module={moduleStaffing} />} />
                <Route path="/platform/reporting"   element={<ModulePage module={moduleReporting} />} />
 <Route path="/features" element={<FeaturesPage />} />
 <Route path="/pricing" element={<PricingMarketingPage />} />
                <Route path="/legacy-pricing" element={<PricingPage />} />
 <Route path="/about" element={<AboutPage />} />
 <Route path="/contact" element={<ContactMarketingPage />} />
                <Route path="/legacy-contact" element={<ContactPage />} />
 <Route path="/api-docs" element={<ApiDocsPage />} />
 <Route path="/supplier/case/:token" element={<SupplierCasePage />} />
 <Route path="/onboarding/:token" element={<CustomerOnboardingForm />} />
 <Route path="/scan/:equipmentId" element={<QRScanPage />} />
 <Route path="/forms/:slug" element={<PublicFormPage />} />
 <Route path="/p/:slug" element={<PublicLandingPage />} />
 <Route path="/partnership-proposal" element={<PartnershipProposalPage />} />
 <Route path="/integration-requirements" element={<IntegrationRequirementsPage />} />
 <Route path="/learn/:slug" element={<LearnMorePage />} />
                {/* Comparison SEO pages (iter 215ee) */}
                <Route path="/compare" element={<CompareIndex />} />
                <Route path="/compare/mindbody" element={<CompareMindbody />} />
                <Route path="/compare/glofox" element={<CompareGlofox />} />
                <Route path="/compare/clubready" element={<CompareClubReady />} />
                {/* Blog scaffold (iter 215ee) */}
                <Route path="/blog" element={<BlogIndex />} />
                <Route path="/blog/:slug" element={<BlogPost />} />
 <Route path="/reset-password" element={<ResetPasswordPage />} />
 <Route path="/security" element={<SecurityMarketingPage />} />
                <Route path="/legacy-security" element={<SecurityPage />} />
 <Route path="/trust" element={<TrustPage />} />
 <Route path="/sso-complete" element={<SSOCompletePage />} />
 <Route path="/login" element={user ? <Navigate to="/dashboard" replace /> : <LoginRedirectPage />} />
 <Route path="/change-password" element={user ? <ForceChangePasswordPage /> : <Navigate to="/login" replace />} />
 <Route path="/master-admin" element={(user?.is_master_admin || user?.is_pulse_admin) ? <MasterAdminPage /> : <Navigate to="/login" replace />} />
 <Route path="/admin/design-system" element={user?.is_master_admin ? <DesignSystemPage /> : <Navigate to="/login" replace />} />
 <Route path="/marketing" element={user ? <MarketingSuite /> : <Navigate to="/login" replace />} />
 <Route path="/service-desk" element={(user?.is_master_admin || user?.is_service_desk) ? <ServiceDeskPage /> : <Navigate to="/login" replace />} />
 <Route path="/service-ops" element={user ? <ServiceOpsDeskPage /> : <Navigate to="/login" replace />} />
 <Route path="/service-ops/scheduler" element={user ? <ServiceOpsScheduler /> : <Navigate to="/login" replace />} />
 <Route path="/service-ops/engineers" element={user ? <ServiceOpsEngineers /> : <Navigate to="/login" replace />} />
 <Route path="/service-ops/parts" element={user ? <ServiceOpsParts /> : <Navigate to="/login" replace />} />
 <Route path="/service-ops/billing" element={user ? <ServiceOpsBilling /> : <Navigate to="/login" replace />} />
 <Route path="/service-ops/reports" element={user ? <ServiceOpsReports /> : <Navigate to="/login" replace />} />
 <Route path="/service-ops/comms" element={user ? <ServiceOpsComms /> : <Navigate to="/login" replace />} />
 <Route path="/admin/integrations" element={user?.is_master_admin ? <IntegrationsConsole /> : <Navigate to="/login" replace />} />
 <Route path="/svc/engineer" element={user ? <ServiceOpsEngineerHome /> : <Navigate to="/login" replace />} />
 <Route path="/svc/engineer/jobs/:caseId" element={user ? <ServiceOpsEngineerJob /> : <Navigate to="/login" replace />} />
 {/* Iter 216c — respect Master Admin's explicit CRM toggle.
     The previous Iter 215dl guard hardcoded "Pulse Pro / Lite / MOD never
     access CRM", which overrode an operator's explicit Master Admin
     decision to enable CRM for a Pulse Pro org. Now we check
     `module_access.crm` (set by Master Admin → Features → CRM toggle,
     resolved by backend resolve_module_access). Only customers WITHOUT
     explicit access get redirected to the CRM Lite contacts surface. */}
 <Route path="/crm" element={(() => {
   if (!user) return <CRMApp />;
   const at = user.account_type;
   const isMasterOrFull = user.is_master_admin || user.role === 'master_admin' || user.role === 'master' || at === 'full';
   if (isMasterOrFull) return <CRMApp />;
   const ma = user.module_access || user.moduleAccess || {};
   if (ma.crm === true) return <CRMApp />;  // explicit master-admin grant wins
   if (at === 'pulse_pro' || at === 'lite' || at === 'mod_site' || at === 'mod_branch' || at === 'mod_org') {
     return <Navigate to="/marketing?tab=contacts&from=crm" replace />;
   }
   return <CRMApp />;
 })()} />
 <Route path="/memberships" element={user ? <MembershipsConsole /> : <Navigate to="/login" replace />} />
 <Route path="/gym-floor" element={<GymFloorPage />} />
 <Route path="/memberships/setup" element={user ? <ModuleAccessGate module="memberships"><MembershipsSetupWizard /></ModuleAccessGate> : <Navigate to="/login" replace />} />
 <Route path="/members" element={<MemberPortal />} />
 <Route path="/m/:slug" element={<BrandedMemberApp />} />
 <Route path="/m/:slug/c/:occId" element={<PublicClassPage />} />
 <Route path="/m/:slug/claim" element={<MemberClaimPage />} />
<Route path="/m/:slug/i/:instructorSlug" element={<PublicInstructorPage />} />
 <Route path="/embed/:slug/timetable" element={<EmbedTimetable />} />
 <Route path="/checkin/kiosk" element={<KioskCheckin />} />
 <Route path="/staffing/kiosk" element={<StaffingKioskPage />} />
 <Route path="/m/:slug/brag" element={<BrandedBragPage />} />
 <Route path="/instructor" element={<InstructorPortal />} />
 <Route path="/privacy" element={<PrivacyPolicyPage />} />
 <Route path="/terms" element={<TermsOfServicePage />} />
 <Route path="/directors" element={<DirectorsHandout />} />
 <Route path="/payment-success" element={<PaymentSuccessPage />} />
 <Route path="/pulse" element={
 user ? (
 <LiteDashboardPage />
 ) : (
 <PulseLandingPage onLogin={(data) => { login(data.token, data.user); }} />
 )
 } />
 <Route path="/pulse-pricing" element={
 <PulsePricingPage onLogin={(data) => { login(data.token, data.user); }} />
 } />
                <Route path="/help" element={user ? <HelpCentrePage /> : <Navigate to="/login" replace />} />
                <Route path="/help/:guideId" element={user ? <HelpCentrePage /> : <Navigate to="/login" replace />} />
 <Route 
 path="/dashboard" 
 element={<DashboardRoute user={user} />}
/>
<Route path="/whats-new" element={<WhatsNewPage />} />
<Route path="/status" element={<StatusPage />} />
<Route path="/legal/dpa" element={<DpaPage />} />
<Route path="/legal/dpia" element={<DpiaPage />} />
<Route path="*" element={<NotFoundPage />} /> </Routes>
 </Suspense>
 </>
 )}
 {user && <UnifiedAssistant />}
 {user && <GuidedTour />}
 {user && <SetupChecklist />}
 {user && <GlobalCommandPalette />}
 <BrandAttrSync user={user} />
 </NotificationConfirmProvider>
 </BrowserRouter>
 <Toaster position="top-right" theme={theme} />
 <CookieConsent />
 <OfflineBanner />
 <PWAInstallPrompt />
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
