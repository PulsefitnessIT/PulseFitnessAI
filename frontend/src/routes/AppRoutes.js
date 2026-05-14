/**
 * Centralised application routes — Iter 216bf.
 *
 * Carved out of `App.js` so the auth shell stays focused on session
 * lifecycle. All Suspense-wrapped, lazy-loaded route components live
 * here. Eager-loaded marketing entries are also imported here so the
 * route table is a single source of truth.
 *
 * Public marketing routes (PulseLandingPage, MarketingHome, ModulePage,
 * legal pages, etc.) and authenticated module routes (CRM, Memberships,
 * Master Admin, Service Ops, Memberships member-facing surfaces, etc.)
 * are all declared here. Auth gates are inline so each surface can
 * negotiate its own redirect.
 */
import React, { lazy } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';

// Eager-loaded marketing entry points — must be in the initial bundle
// to avoid a Suspense fallback on landing.
import PulseLandingPage from '@/pages/PulseLandingPage';
import PulsePricingPage from '@/pages/PulsePricingPage';
import MarketingHome from '@/pages/Marketing/MarketingHome';
import ModulePage from '@/pages/Marketing/ModulePage';
import moduleService from '@/pages/Marketing/modules/service';
import moduleCrm from '@/pages/Marketing/modules/crm';
import moduleMemberships from '@/pages/Marketing/modules/memberships';
import moduleMarketing from '@/pages/Marketing/modules/marketing';
import moduleStaffing from '@/pages/Marketing/modules/staffing';
import moduleReporting from '@/pages/Marketing/modules/reporting';
import SecurityPage from '@/pages/SecurityPage';
import SecurityMarketingPage from '@/pages/Marketing/SecurityMarketingPage';
import PricingMarketingPage from '@/pages/Marketing/PricingMarketingPage';
import ContactMarketingPage from '@/pages/Marketing/ContactMarketingPage';
import TrustPage from '@/pages/TrustPage';
import ModuleAccessGate from '@/components/shared/ModuleAccessGate';

// Lazy-loaded authenticated app + secondary marketing pages.
const FeaturesPage = lazy(() => import('@/pages/FeaturesPage'));
const PricingPage = lazy(() => import('@/pages/PricingPage'));
const AboutPage = lazy(() => import('@/pages/AboutPage'));
const ContactPage = lazy(() => import('@/pages/ContactPage'));
const NotFoundPage = lazy(() => import('@/pages/NotFoundPage'));
const WhatsNewPage = lazy(() => import('@/pages/WhatsNewPage'));
const StatusPage = lazy(() => import('@/pages/StatusPage'));
const DpaPage = lazy(() => import('@/pages/legal/DpaPage'));
const DpiaPage = lazy(() => import('@/pages/legal/DpiaPage'));
const DashboardPage = lazy(() => import('@/pages/DashboardPage'));
const LiteDashboardPage = lazy(() => import('@/pages/LiteDashboardPage'));
const ResetPasswordPage = lazy(() => import('@/pages/ResetPasswordPage'));
const SSOCompletePage = lazy(() => import('@/pages/SSOCompletePage'));
const JoinPage = lazy(() => import('@/pages/PublicSignup/JoinPage'));
const JoinSuccess = lazy(() => import('@/pages/PublicSignup/JoinSuccess'));
const LoginRedirectPage = lazy(() => import('@/pages/LoginRedirectPage'));
const ApiDocsPage = lazy(() => import('@/pages/ApiDocsPage'));
const SupplierCasePage = lazy(() => import('@/pages/SupplierCasePage'));
const CustomerOnboardingForm = lazy(() => import('@/pages/CustomerOnboardingForm'));
const QRScanPage = lazy(() => import('@/pages/QRScanPage'));
const PublicFormPage = lazy(() => import('@/pages/PublicFormPage'));
const PublicLandingPage = lazy(() => import('@/pages/PublicLandingPage'));
const PartnershipProposalPage = lazy(() => import('@/pages/PartnershipProposalPage'));
const IntegrationRequirementsPage = lazy(() => import('@/pages/IntegrationRequirementsPage'));
const LearnMorePage = lazy(() => import('@/pages/LearnMorePage'));
const CompareIndex = lazy(() => import('@/pages/Marketing/Compare/CompareIndex'));
const CompareMindbody = lazy(() => import('@/pages/Marketing/Compare/CompareMindbody'));
const CompareGlofox = lazy(() => import('@/pages/Marketing/Compare/CompareGlofox'));
const CompareClubReady = lazy(() => import('@/pages/Marketing/Compare/CompareClubReady'));
const BlogIndex = lazy(() => import('@/pages/Marketing/Blog/BlogIndex'));
const BlogPost = lazy(() => import('@/pages/Marketing/Blog/BlogPost'));
const CRMApp = lazy(() => import('@/pages/CRM/CRMApp'));
const CRMSetupWizard = lazy(() => import('@/pages/CRM/CRMSetupWizard'));
const PrivacyPolicyPage = lazy(() => import('@/pages/PrivacyPolicyPage'));
const TermsOfServicePage = lazy(() => import('@/pages/TermsOfServicePage'));
const RefundPolicyPage = lazy(() => import('@/pages/RefundPolicyPage'));
const DirectorsHandout = lazy(() => import('@/pages/DirectorsHandout'));
const PaymentSuccessPage = lazy(() => import('@/pages/PaymentSuccessPage'));
const MasterAdminPage = lazy(() => import('@/pages/MasterAdminPage'));
const DesignSystemPage = lazy(() => import('@/pages/MasterAdmin/DesignSystemPage'));
const MarketingSuite = lazy(() => import('@/pages/MarketingSuite'));
const ServiceDeskPage = lazy(() => import('@/pages/ServiceDeskPage'));
const ServiceOpsDeskPage = lazy(() => import('@/pages/ServiceOps/ServiceDeskPage'));
const ServiceOpsScheduler = lazy(() => import('@/pages/ServiceOps/ServiceScheduler'));
const ServiceOpsEngineers = lazy(() => import('@/pages/ServiceOps/EngineersAdminPage'));
const ServiceOpsParts = lazy(() => import('@/pages/ServiceOps/PartsInventoryPage'));
const ServiceOpsBilling = lazy(() => import('@/pages/ServiceOps/BillingPage'));
const ServiceOpsReports = lazy(() => import('@/pages/ServiceOps/ServiceOpsReportsPage'));
// Iter 216h75 — Partner Engineer Network (Phase 1)
const PartnerApplyWizard = lazy(() => import('@/pages/PartnerEngineer/PartnerApplyWizard'));
const PartnerDashboard = lazy(() => import('@/pages/PartnerEngineer/PartnerDashboard'));
// Iter 216h88 — public Partner Engineer landing page
const PartnerEngineerLanding = lazy(() => import('@/pages/Marketing/PartnerEngineerLanding'));
const PartnerApplyPublic = lazy(() => import('@/pages/Marketing/PartnerApplyPublic'));
// Iter 216h83 — public customer live-tracking
const PublicTrackingPage = lazy(() => import('@/pages/PublicTracking/PublicTrackingPage'));
const ServiceOpsComms = lazy(() => import('@/pages/ServiceOps/CommsHubPage'));
const IntegrationsConsole = lazy(() => import('@/pages/Admin/IntegrationsConsole'));
const ServiceOpsEngineerHome = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerHome'));
const ServiceOpsEngineerJob = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerJobDetail'));
const MODSiteDashboard = lazy(() => import('@/pages/MODPortal/MODSiteDashboard'));
const MODProDashboard = lazy(() => import('@/pages/MODPortal/MODProDashboard'));
const MODServiceLogin = lazy(() => import('@/pages/MODPortal/MODServiceLogin'));
const MembershipsConsole = lazy(() => import('@/pages/Memberships/MembershipsConsole'));
const MemberPortal = lazy(() => import('@/pages/Memberships/MemberPortal'));
const MemberClaimPage = lazy(() => import('@/pages/Memberships/MemberClaimPage'));
const InstructorPortal = lazy(() => import('@/pages/Memberships/InstructorPortal'));
const MembershipsSetupWizard = lazy(() => import('@/pages/Memberships/SetupWizard'));
const GymFloorPage = lazy(() => import('@/pages/GymFloor/GymFloorPage'));
const BrandedMemberApp = lazy(() => import('@/pages/Memberships/BrandedMemberApp'));
const PublicClassPage = lazy(() => import('@/pages/Memberships/PublicClassPage'));
const PublicInstructorPage = lazy(() => import('@/pages/Memberships/PublicInstructorPage'));
const EmbedTimetable = lazy(() => import('@/pages/Memberships/EmbedTimetable'));
const KioskCheckin = lazy(() => import('@/pages/Memberships/KioskCheckin'));
const StaffingKioskPage = lazy(() => import('@/pages/Staffing/KioskPage'));
const BrandedBragPage = lazy(() => import('@/pages/Memberships/BrandedBragPage'));
const ForceChangePasswordPage = lazy(() => import('@/pages/ForceChangePasswordPage'));
const HelpCentrePage = lazy(() => import('@/pages/HelpCentrePage'));

/**
 * Iter 215bs — `/dashboard` resolver. Role-based routing with a
 * `?as=operator` escape hatch so master admins can preview the
 * GymAxis operator portal without seeding a fake user.
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

/**
 * Iter 216h110 — MOD route firewall. Any direct URL access to
 * non-Operations / non-CAPEX / non-Reports surfaces by a MOD user
 * (`account_type` in {mod_site, mod_branch, mod_org}) is forced
 * back to /dashboard, which then renders the correct MOD dashboard.
 *
 * Routes the MOD user IS allowed to reach:
 *   /MODService(/login)  · /dashboard  · /service-desk (Operations)
 *   /scan/:id            · /help       · /capex
 *   /reports             · /account*   · /change-password
 *   /m/* (public member surfaces — they're token-gated anyway)
 *
 * Anything else (Memberships, Marketing, CRM, Staffing, Layout,
 * Pulse Pro main dashboard, Partner-Engineer, the GymAxis operator
 * dashboard) is for non-MOD operators only.
 */
function MODForbidden({ children }) {
  const stored = typeof window !== 'undefined' ? localStorage.getItem('user_cache') : null;
  let at = '';
  try { at = stored ? (JSON.parse(stored).account_type || '') : ''; } catch { /* ignore */ }
  if (at === 'mod_site' || at === 'mod_branch' || at === 'mod_org') {
    return <Navigate to="/dashboard" replace />;
  }
  return children;
}

/**
 * Iter 216c — explicit-toggle-aware CRM route. Master Admin's CRM
 * feature flag (module_access.crm) wins over the legacy hardcoded
 * "Pulse Pro / Lite / MOD never access CRM" guard.
 */
function CrmRouteElement({ user }) {
  if (!user) return <CRMApp />;
  const at = user.account_type;
  const isMasterOrFull = user.is_master_admin || user.role === 'master_admin' || user.role === 'master' || at === 'full';
  if (isMasterOrFull) return <CRMApp />;
  const ma = user.module_access || user.moduleAccess || {};
  if (ma.crm === true) return <ModuleAccessGate module="crm"><CRMApp /></ModuleAccessGate>;
  if (at === 'pulse_pro' || at === 'lite' || at === 'mod_site' || at === 'mod_branch' || at === 'mod_org') {
    return <ModuleAccessGate module="crm"><CRMApp /></ModuleAccessGate>;
  }
  return <CRMApp />;
}

export default function AppRoutes({ user, login }) {
  return (
    <Routes>
      {/* ─── Marketing site ─── */}
      <Route path="/" element={<MarketingHome />} />
      <Route path="/m/:slug/join" element={<JoinPage />} />
      <Route path="/m/:slug/join/success" element={<JoinSuccess />} />
      {/* Iter 216h83 — public live tracking (no auth, token-gated) */}
      <Route path="/track/:token" element={<PublicTrackingPage />} />
      {/* Iter 216h88 — public Engineer Partner marketing landing */}
      <Route path="/partners/engineers" element={<PartnerEngineerLanding />} />
      {/* Iter 216h104 — public Engineer Partner application form (no login required) */}
      <Route path="/partners/engineers/apply" element={<PartnerApplyPublic />} />
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
      <Route path="/security" element={<SecurityMarketingPage />} />
      <Route path="/legacy-security" element={<SecurityPage />} />
      <Route path="/trust" element={<TrustPage />} />
      <Route path="/whats-new" element={<WhatsNewPage />} />
      <Route path="/status" element={<StatusPage />} />
      <Route path="/compare" element={<CompareIndex />} />
      <Route path="/compare/mindbody" element={<CompareMindbody />} />
      <Route path="/compare/glofox" element={<CompareGlofox />} />
      <Route path="/compare/clubready" element={<CompareClubReady />} />
      <Route path="/blog" element={<BlogIndex />} />
      <Route path="/blog/:slug" element={<BlogPost />} />
      <Route path="/partnership-proposal" element={<PartnershipProposalPage />} />
      <Route path="/integration-requirements" element={<IntegrationRequirementsPage />} />
      <Route path="/learn/:slug" element={<LearnMorePage />} />
      <Route path="/directors" element={<DirectorsHandout />} />

      {/* ─── Legal ─── */}
      <Route path="/privacy" element={<PrivacyPolicyPage />} />
      <Route path="/terms" element={<TermsOfServicePage />} />
      <Route path="/refunds" element={<RefundPolicyPage />} />
      <Route path="/legal/dpa" element={<DpaPage />} />
      <Route path="/legal/dpia" element={<DpiaPage />} />

      {/* ─── Auth & onboarding ─── */}
      {/* Iter 216h68 — always render LoginRedirectPage so it can honour
          `?next=/path` for already-logged-in users (e.g. when the
          SessionResumedBanner deep-links back after a 24h+ expiry). */}
      <Route path="/login" element={<LoginRedirectPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/sso-complete" element={<SSOCompletePage />} />
      <Route path="/change-password" element={user ? <ForceChangePasswordPage /> : <Navigate to="/login" replace />} />
      <Route path="/onboarding/:token" element={<CustomerOnboardingForm />} />
      <Route path="/payment-success" element={<PaymentSuccessPage />} />

      {/* Iter 216h109 — MOD Service portal (branded login). */}
      <Route path="/MODService" element={<MODServiceLogin />} />
      <Route path="/MODService/login" element={<MODServiceLogin />} />
      <Route path="/modservice" element={<Navigate to="/MODService" replace />} />

      {/* ─── Public utility ─── */}
      <Route path="/supplier/case/:token" element={<SupplierCasePage />} />
      <Route path="/scan/:equipmentId" element={<QRScanPage />} />
      <Route path="/forms/:slug" element={<PublicFormPage />} />
      <Route path="/p/:slug" element={<PublicLandingPage />} />

      {/* ─── Master / admin ─── */}
      <Route path="/master-admin" element={(user?.is_master_admin || user?.is_pulse_admin) ? <MasterAdminPage /> : <Navigate to="/login" replace />} />
      <Route path="/admin/design-system" element={user?.is_master_admin ? <DesignSystemPage /> : <Navigate to="/login" replace />} />
      <Route path="/admin/integrations" element={user?.is_master_admin ? <IntegrationsConsole /> : <Navigate to="/login" replace />} />

      {/* ─── Modules (Iter 216h110 — MOD users are firewalled out) ─── */}
      <Route path="/marketing" element={user ? <MODForbidden><ModuleAccessGate module="marketing"><MarketingSuite /></ModuleAccessGate></MODForbidden> : <Navigate to="/login" replace />} />
      <Route path="/crm" element={<MODForbidden><CrmRouteElement user={user} /></MODForbidden>} />
      <Route path="/crm/setup" element={user ? <MODForbidden><ModuleAccessGate module="crm"><CRMSetupWizard /></ModuleAccessGate></MODForbidden> : <Navigate to="/login" replace />} />
      <Route path="/memberships" element={user ? <MODForbidden><ModuleAccessGate module="memberships"><MembershipsConsole /></ModuleAccessGate></MODForbidden> : <Navigate to="/login" replace />} />
      <Route path="/memberships/setup" element={user ? <MODForbidden><ModuleAccessGate module="memberships"><MembershipsSetupWizard /></ModuleAccessGate></MODForbidden> : <Navigate to="/login" replace />} />
      <Route path="/gym-floor" element={<MODForbidden><GymFloorPage /></MODForbidden>} />

      {/* ─── Service Desk (unified — iter 216h53 full merge of Service Ops) ─── */}
      <Route path="/service-desk" element={(user?.is_master_admin || user?.is_service_desk) ? <ServiceDeskPage /> : <Navigate to="/login" replace />} />
      {/* Legacy /service-ops/* URLs redirect to the unified hub. Deep links still work — the merged shell defaults to Dashboard. */}
      <Route path="/service-ops" element={<Navigate to="/service-desk" replace />} />
      <Route path="/service-ops/scheduler" element={<Navigate to="/service-desk" replace />} />
      <Route path="/service-ops/engineers" element={<Navigate to="/service-desk" replace />} />
      <Route path="/service-ops/parts" element={<Navigate to="/service-desk" replace />} />
      <Route path="/service-ops/billing" element={<Navigate to="/service-desk" replace />} />
      <Route path="/service-ops/reports" element={<Navigate to="/service-desk" replace />} />
      <Route path="/service-ops/comms" element={<Navigate to="/service-desk" replace />} />
      <Route path="/svc/engineer" element={user ? <ServiceOpsEngineerHome /> : <Navigate to="/login" replace />} />
      <Route path="/svc/engineer/jobs/:caseId" element={user ? <ServiceOpsEngineerJob /> : <Navigate to="/login" replace />} />

      {/* Iter 216h75 — Partner Engineer Network (Phase 1) — Iter 216h110: MOD-blocked */}
      <Route path="/partner-engineer" element={user ? <MODForbidden><PartnerDashboard /></MODForbidden> : <Navigate to="/login?next=/partner-engineer" replace />} />
      <Route path="/partner-engineer/apply" element={user ? <MODForbidden><PartnerApplyWizard /></MODForbidden> : <Navigate to="/login?next=/partner-engineer/apply" replace />} />

      {/* ─── Member-facing surfaces (white-label) ─── */}
      <Route path="/members" element={<MemberPortal />} />
      <Route path="/m/:slug" element={<BrandedMemberApp />} />
      <Route path="/m/:slug/c/:occId" element={<PublicClassPage />} />
      <Route path="/m/:slug/claim" element={<MemberClaimPage />} />
      <Route path="/m/:slug/i/:instructorSlug" element={<PublicInstructorPage />} />
      <Route path="/m/:slug/brag" element={<BrandedBragPage />} />
      <Route path="/embed/:slug/timetable" element={<EmbedTimetable />} />
      <Route path="/checkin/kiosk" element={<KioskCheckin />} />
      <Route path="/staffing/kiosk" element={<StaffingKioskPage />} />
      <Route path="/instructor" element={<InstructorPortal />} />

      {/* ─── Pulse (Iter 216h110 — MOD redirects to MOD dashboard) ─── */}
      <Route path="/pulse" element={
        user ? <MODForbidden><LiteDashboardPage /></MODForbidden> : <PulseLandingPage onLogin={(d) => login(d.token, d.user)} />
      } />
      <Route path="/pulse-pricing" element={<PulsePricingPage onLogin={(d) => login(d.token, d.user)} />} />

      {/* ─── Help ─── */}
      <Route path="/help" element={user ? <HelpCentrePage /> : <Navigate to="/login" replace />} />
      <Route path="/help/:guideId" element={user ? <HelpCentrePage /> : <Navigate to="/login" replace />} />

      {/* ─── Dashboard resolver ─── */}
      <Route path="/dashboard" element={<DashboardRoute user={user} />} />

      {/* ─── 404 ─── */}
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
