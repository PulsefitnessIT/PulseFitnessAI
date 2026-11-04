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
import { lazy, Suspense, useEffect } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/App';
import EngineerErrorBoundary from '@/components/shared/EngineerErrorBoundary';
import { resolveHomePath } from '@/utils/moduleHome';
import { can } from '@/utils/capabilities';
import { isExternalEngineer, isLockedEngineer, lockedEngineerHome } from '@/utils/engineerGuard';

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
import SecurityDocumentPage from '@/pages/Marketing/SecurityDocumentPage';
import PricingMarketingPage from '@/pages/Marketing/PricingMarketingPage';
import ContactMarketingPage from '@/pages/Marketing/ContactMarketingPage';
import TrustPage from '@/pages/TrustPage';
import ModuleAccessGate from '@/components/shared/ModuleAccessGate';
import EngineerOfflineIndicator from '@/components/engineer/EngineerOfflineIndicator';
// Iter 220cx — mic FAB mounted globally on every engineer route
// (not just Home) so engineers can dictate a new job from anywhere.
const EngineerVoiceToJobButton = lazy(() => import('@/pages/ServiceOps/Engineer/VoiceToJobButton'));
const EngineerSpeedDial        = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerSpeedDial'));

// Lazy-loaded authenticated app + secondary marketing pages.
const DemoRequestPage = lazy(() => import('@/pages/DemoRequestPage'));
const FeaturesPage = lazy(() => import('@/pages/FeaturesPage'));
const PricingPage = lazy(() => import('@/pages/PricingPage'));
const AboutPage = lazy(() => import('@/pages/AboutPage'));
const ContactPage = lazy(() => import('@/pages/ContactPage'));
const NotFoundPage = lazy(() => import('@/pages/NotFoundPage'));
const NewStarterPortal = lazy(() => import('@/pages/NewStarterPortal'));
const StaffLogin = lazy(() => import('@/pages/StaffLogin'));
const StaffResetPassword = lazy(() => import('@/pages/StaffResetPassword'));
const StaffPortal = lazy(() => import('@/pages/StaffPortal'));
const BFPOApp = lazy(() => import('@/pages/BFPO/BFPOApp'));
const BFPOInviteSetPassword = lazy(() => import('@/pages/BFPO/BFPOInviteSetPassword'));
const WhatsNewPage = lazy(() => import('@/pages/WhatsNewPage'));
const StatusPage = lazy(() => import('@/pages/StatusPage'));
const DpaPage = lazy(() => import('@/pages/legal/DpaPage'));
const DpiaPage = lazy(() => import('@/pages/legal/DpiaPage'));
// Iter 220ba — public SLA + Sub-processors register (footer-linked)
const SlaPage = lazy(() => import('@/pages/legal/SlaPage'));
const SubProcessorsPage = lazy(() => import('@/pages/legal/SubProcessorsPage'));
const DashboardPage = lazy(() => import('@/pages/DashboardPage'));
const LiteDashboardPage = lazy(() => import('@/pages/LiteDashboardPage'));
const ResetPasswordPage = lazy(() => import('@/pages/ResetPasswordPage'));
const SSOCompletePage = lazy(() => import('@/pages/SSOCompletePage'));
const JoinPage = lazy(() => import('@/pages/PublicSignup/JoinPage'));
const JoinSuccess = lazy(() => import('@/pages/PublicSignup/JoinSuccess'));
const LoginRedirectPage = lazy(() => import('@/pages/LoginRedirectPage'));
const LauncherPage = lazy(() => import('@/pages/LauncherPage'));
const ApiDocsPage = lazy(() => import('@/pages/ApiDocsPage'));
const SupplierCasePage = lazy(() => import('@/pages/SupplierCasePage'));
const PartsRequestsPage = lazy(() => import('@/pages/PartsRequests/PartsRequestsPage'));
const PartsCardPage = lazy(() => import('@/pages/PartsRequests/PartsCardPage'));
const CustomerOnboardingForm = lazy(() => import('@/pages/CustomerOnboardingForm'));
const MODEquipmentCaptureForm = lazy(() => import('@/pages/MODEquipmentCaptureForm'));
const MODVisitBookingForm = lazy(() => import('@/pages/MODVisitBookingForm'));
const QRScanPage = lazy(() => import('@/pages/QRScanPage'));
const EngineerFaultReportPage = lazy(() => import('@/pages/EngineerFaultReportPage'));
const EngineerMachineHistory = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerMachineHistory'));
const BlueLightVisitWizard = lazy(() => import('@/pages/CRM/Contracts/BlueLightVisitWizard'));
const PublicFormPage = lazy(() => import('@/pages/PublicFormPage'));
const PublicLandingPage = lazy(() => import('@/pages/PublicLandingPage'));
const PartnershipProposalPage = lazy(() => import('@/pages/PartnershipProposalPage'));
const IntegrationRequirementsPage = lazy(() => import('@/pages/IntegrationRequirementsPage'));
const DealerPortalStandalone = lazy(() => import('@/pages/DealerWarrantyParts/DealerPortalStandalone'));
const LogisticsPortal = lazy(() => import('@/pages/ServiceOps/Inventory/LogisticsPortal'));
const LearnMorePage = lazy(() => import('@/pages/LearnMorePage'));
const CompareIndex = lazy(() => import('@/pages/Marketing/Compare/CompareIndex'));
const CompareMindbody = lazy(() => import('@/pages/Marketing/Compare/CompareMindbody'));
const CompareGlofox = lazy(() => import('@/pages/Marketing/Compare/CompareGlofox'));
const CompareClubReady = lazy(() => import('@/pages/Marketing/Compare/CompareClubReady'));
const BlogIndex = lazy(() => import('@/pages/Marketing/Blog/BlogIndex'));
const BlogPost = lazy(() => import('@/pages/Marketing/Blog/BlogPost'));
const SolutionsIndex = lazy(() => import('@/pages/Marketing/Landing/SolutionsIndex'));
const SolutionLanding = lazy(() => import('@/pages/Marketing/Landing/SolutionLanding'));
const MaintenanceIndex = lazy(() => import('@/pages/Marketing/Landing/MaintenanceIndex'));
const ManufacturerLanding = lazy(() => import('@/pages/Marketing/Landing/ManufacturerLanding'));
const EquipmentIndex = lazy(() => import('@/pages/Marketing/Landing/EquipmentIndex'));
const EquipmentLanding = lazy(() => import('@/pages/Marketing/Landing/EquipmentLanding'));
const CRMApp = lazy(() => import('@/pages/CRM/CRMApp'));
const CRMSetupWizard = lazy(() => import('@/pages/CRM/CRMSetupWizard'));
const PrivacyPolicyPage = lazy(() => import('@/pages/PrivacyPolicyPage'));
const TermsOfServicePage = lazy(() => import('@/pages/TermsOfServicePage'));
const RefundPolicyPage = lazy(() => import('@/pages/RefundPolicyPage'));
const DirectorsHandout = lazy(() => import('@/pages/DirectorsHandout'));
const PaymentSuccessPage = lazy(() => import('@/pages/PaymentSuccessPage'));
const ChoosePlanPage = lazy(() => import('@/pages/ChoosePlanPage'));
const MasterAdminPage = lazy(() => import('@/pages/MasterAdminPage'));
const DesignSystemPage = lazy(() => import('@/pages/MasterAdmin/DesignSystemPage'));
const AdminPartsRequests = lazy(() => import('@/pages/MasterAdmin/AdminPartsRequests'));
const AdminMODSitesBulkImport = lazy(() => import('@/pages/MasterAdmin/AdminMODSitesBulkImport'));
const MarketingSuite = lazy(() => import('@/pages/MarketingSuite'));
const CommsCentre = lazy(() => import('@/pages/Comms/CommsCentre'));
const PublicPreferencesPage = lazy(() => import('@/pages/Comms/PublicPreferencesPage'));
const PublicUnsubscribePage = lazy(() => import('@/pages/Comms/PublicUnsubscribePage'));
const PublicEmailViewPage = lazy(() => import('@/pages/Comms/PublicEmailViewPage'));
const PublicForwardPage = lazy(() => import('@/pages/Comms/PublicForwardPage'));
const ServiceDeskPage = lazy(() => import('@/pages/ServiceDeskPage'));
const InventoryDistribution = lazy(() => import('@/pages/ServiceOps/Inventory/InventoryDistribution'));
const _ServiceOpsDeskPage = lazy(() => import('@/pages/ServiceOps/ServiceDeskPage'));
const _ServiceOpsScheduler = lazy(() => import('@/pages/ServiceOps/ServiceScheduler'));
const _ServiceOpsEngineers = lazy(() => import('@/pages/ServiceOps/EngineersAdminPage'));
const _ServiceOpsParts = lazy(() => import('@/pages/ServiceOps/PartsInventoryPage'));
const _ServiceOpsBilling = lazy(() => import('@/pages/ServiceOps/BillingPage'));
const _ServiceOpsReports = lazy(() => import('@/pages/ServiceOps/ServiceOpsReportsPage'));
// Iter 216h75 — Partner Engineer Network (Phase 1)
// Iter 216h282 — PartnerApplyWizard removed in favour of the single
// canonical `/partners/engineers/apply` (PartnerApplyPublic). Keeping
// the lazy-import stubs below for any other PartnerEngineer routes.
const PartnerDashboard = lazy(() => import('@/pages/PartnerEngineer/PartnerDashboard'));
// Iter 219f — public activation page (single-use link from approval email).
const PartnerEngineerActivate = lazy(() => import('@/pages/PartnerEngineer/PartnerEngineerActivate'));
const TrialFeedback = lazy(() => import('@/pages/PartnerEngineer/TrialFeedback'));
// Iter 216h88 — public Partner Engineer landing page
const PartnerEngineerLanding = lazy(() => import('@/pages/Marketing/PartnerEngineerLanding'));
const PartnerApplyPublic = lazy(() => import('@/pages/Marketing/PartnerApplyPublic'));
// Iter 216h83 — public customer live-tracking
const PublicTrackingPage = lazy(() => import('@/pages/PublicTracking/PublicTrackingPage'));
// Iter 220e3 — public contract accept (Phase D)
const PublicContractAcceptPage = lazy(() => import('@/pages/CRM/Contracts/PublicContractAcceptPage'));
const PublicQuoteSignPage = lazy(() => import('@/pages/CRM/PublicQuoteSignPage'));
const _ServiceOpsComms = lazy(() => import('@/pages/ServiceOps/CommsHubPage'));
const IntegrationsConsole = lazy(() => import('@/pages/Admin/IntegrationsConsole'));
const IntegrationsSiconConnect = lazy(() => import('@/pages/Admin/IntegrationsSiconConnect'));
const ServiceOpsEngineerHome = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerHomeV2'));
const ServiceOpsEngineerJobsList = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerHome'));
const EngineerSupport = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerSupport'));
const ServiceOpsEngineerJob = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerJobDetailV2'));
const ServiceOpsEngineerQuotes = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerQuotes'));
const ServiceOpsEngineerQuoteBuilder = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerQuoteBuilder'));
const ServiceOpsEngineerInvoices = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerInvoices'));
const ServiceOpsEngineerInvoiceBuilder = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerInvoiceBuilder'));
const ServiceOpsEngineerPayouts = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerPayouts'));
// Iter 216h140 — Engineer App Phase 4: Diary & Admin Dispatch
const ServiceOpsEngineerDiary = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerDiary'));
const ServiceOpsAdminDispatchBoard = lazy(() => import('@/pages/ServiceOps/AdminDispatchBoard'));
// Iter 216h141 — Engineer Workspace (Phase 4 / Slice 4 · desktop 3-column)
const ServiceOpsEngineerWorkspace = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerWorkspace'));
// Iter 216h142 — Engineer Notifications (Phase 4 / Slice 2)
const ServiceOpsEngineerNotifications = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerNotifications'));
// Iter 216h143 — Engineer Sync Panel (Phase 4 / Slice 3 · offline writes)
const ServiceOpsEngineerSyncPanel = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerSyncPanel'));
// Iter 216h144 — Engineer Independence (self-create, AI parse, supplier card)
const ServiceOpsEngineerNewJob = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerNewJob'));
const ServiceOpsEngineerInbox  = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerInbox'));
const PublicEngineerCard       = lazy(() => import('@/pages/Public/PublicEngineerCard'));
const PublicOrgChartPage       = lazy(() => import('@/pages/Public/PublicOrgChartPage'));
// Iter 216h147 — Engineer self-claim queue
const ServiceOpsEngineerQueue  = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerQueue'));
// Iter 216h148 — Public Engineer landing/login page
const PublicEngineerLanding    = lazy(() => import('@/pages/Public/EngineerLanding'));
const PartnerReviewPublic      = lazy(() => import('@/pages/Public/PartnerReviewPublic'));
// Iter 220y — Public Wall of Reviews
const EngineerReviewsWall      = lazy(() => import('@/pages/Public/EngineerReviewsWall'));
// Iter 220aa — Embeddable widget (Log-a-Fault / Get-a-Quote)
const EmbedFaultForm           = lazy(() => import('@/pages/Public/EmbedFaultForm'));
const WitnessStatementPage     = lazy(() => import('@/pages/WitnessStatementPage'));
const EngineerReferralLanding  = lazy(() => import('@/pages/Public/EngineerReferralLanding'));
// Iter 216h159 — Engineer card-conversion analytics
const ServiceOpsEngineerCardAnalytics = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerCardAnalytics'));
const ServiceOpsEngineerAnalytics = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerAnalyticsPage'));
// Iter 220cu — End-of-day timesheet roll-up.
const ServiceOpsEngineerEndOfDay = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerEndOfDay'));
const ServiceOpsEngineerCustomers = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerCustomers'));
// Iter 278 — Expenses Tracker & Receipt Photo Scanner (engineer mobile UI)
const ServiceOpsEngineerExpenses = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerExpenses'));
// Iter 220ci — Engineer Equipment Tab (strict picklists, flows into Ops)
const ServiceOpsEngineerEquipment = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerEquipment'));
// Iter 220ea·19 — Engineer App Phase 5: Stock Control hub
const ServiceOpsEngineerStock = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerStock'));
// Iter 220ea·20 — Phase 5b: Parts Catalogue + Bulk Import
const ServiceOpsPartsCatalogue = lazy(() => import('@/pages/ServiceOps/Engineer/PartsCatalogue'));
const ServiceOpsAdminStock = lazy(() => import('@/pages/ServiceOps/Engineer/AdminStock'));
// Iter 220ea·33 — Legacy report import (PDF/CSV/XLSX → branded PDF via AI)
const ServiceOpsEngineerLegacyImport = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerLegacyImport'));
const ServiceOpsEngineerEquipmentForm = lazy(() =>
  import('@/pages/ServiceOps/Engineer/EngineerEquipment').then((m) => ({ default: m.EngineerEquipmentForm })),
);
// Iter 220 — Work Report custom fields (engineer self-serve)
const ServiceOpsEngineerWorkReportFields = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerWorkReportFields'));
const ServiceOpsEngineerCaseTypes = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerCaseTypes'));
// Iter 220i — Upcoming jobs list (drill-in from home tile)
const ServiceOpsEngineerUpcoming = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerUpcomingList'));
const ServiceOpsEngineerBranding = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerBrandingSettings'));
const ServiceOpsSafetyTemplateAdmin = lazy(() => import('@/pages/ServiceOps/SafetyTemplateAdmin'));
const ServiceOpsEngineerRatings = lazy(() => import('@/pages/ServiceOps/Engineer/EngineerRatings'));
const PublicQuoteAcceptPage = lazy(() => import('@/pages/PublicQuoteAcceptPage'));
const PublicAfsQuoteAcceptPage = lazy(() => import('@/pages/PublicAfsQuoteAcceptPage'));
const _MODSiteDashboard = lazy(() => import('@/pages/MODPortal/MODSiteDashboard'));
const _MODProDashboard = lazy(() => import('@/pages/MODPortal/MODProDashboard'));
const MODServiceLogin = lazy(() => import('@/pages/MODPortal/MODServiceLogin'));
const MODConfirmFixPage = lazy(() => import('@/pages/MODPortal/MODConfirmFixPage'));
// MODService deployment mode — flips the public landing to the MOD sign-in.
// eslint-disable-next-line import/first
import { isModServiceMode, MODSERVICE_URL } from '@/utils/portalMode';

/** Sends the browser to an external URL (used to forward the commercial
 *  domain's /MODService routes to the dedicated MOD deployment). */
function ExternalRedirect({ to }) {
  useEffect(() => { window.location.replace(to); }, [to]);
  return null;
}
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
// Iter 253 — self-serve Service Provider signup + setup wizard
const ServiceProviderSignup = lazy(() => import('@/pages/ServiceProviderSignup'));
const ServiceProviderSetup = lazy(() => import('@/pages/ServiceProviderSetup'));
// Iter 258 — self-serve trial → paid Stripe upgrade for providers
const ServiceProviderUpgrade = lazy(() => import('@/pages/ServiceProviderUpgrade'));
const CompleteProfilePage = lazy(() => import('@/pages/CompleteProfilePage'));
const HelpCentrePage = lazy(() => import('@/pages/HelpCentrePage'));

/**
 * Iter 215bs — `/dashboard` resolver. Role-based routing with a
 * `?as=operator` escape hatch so master admins can preview the
 * Pulse Fitness operator portal without seeding a fake user.
 */
function DashboardRoute({ user }) {
  if (!user) return <Navigate to="/" />;
  // Dealer portal sub-users are confined to their own portal.
  if ((user.role || '').toLowerCase() === 'dealer_user') return <Navigate to="/dealer-portal" replace />;
  // Logistics install-team users are confined to the logistics portal.
  if ((user.role || '').toLowerCase() === 'logistics') return <Navigate to="/logistics" replace />;
  // Iter 274 — independent engineers are locked to the Engineer App.
  if (isLockedEngineer(user)) return <Navigate to={lockedEngineerHome(user)} replace />;
  const params = new URLSearchParams(window.location.search);
  const previewAsOperator = params.get('as') === 'operator';
  // Iter 292 — ?as=global lets a master admin (even one whose home org
  // isn't the operator) reach the Global collective DashboardPage instead
  // of being bounced back to the /master-admin console.
  const previewAsGlobal = params.get('as') === 'global';
  const previewDashboard = previewAsOperator || previewAsGlobal;
  // Iter 220bz — mandatory profile-completion gate. New trial signups
  // collect this on the modal's step 2; legacy trials that signed up
  // before this iter shipped get routed here on first dashboard load.
  // Master admin + non-trial operators are exempt — we only need the
  // KYC-style address for actively-trialling new accounts.
  const t = user.trial;
  const isTrialing = t && (t.is_trial || t.is_trial === undefined);
  if (
    isTrialing
    && !user.is_master_admin
    && !user.profile_completed_at
  ) {
    return <Navigate to="/complete-profile" replace />;
  }
  if (user.is_master_admin && !previewDashboard && !user.org_is_operator) return <Navigate to="/master-admin" />;
  // Iter 216h113 — MOD users land in the standard Pulse Fitness
  // dashboard like every other Pulse customer. Module-level gating
  // (ModuleAccessGate) still hides any modules they're not entitled
  // to. The portal must look identical for MOD users — they ARE
  // Pulse Fitness customers, just inside a different tenant.
  const at = user.account_type;
  if (at === 'mod_site' || at === 'mod_branch' || at === 'mod_org') {
    return <Navigate to="/pulse" />;
  }
  if (!previewAsOperator && (at === 'lite' || at === 'pulse_pro')) {
    return <Navigate to="/pulse" />;
  }
  // Iter 220ea·42 — module-aware deep-link guard. A trial that only
  // unlocked a bolt-on module (e.g. Memberships-only) has no Operations
  // access; if they deep-link to /dashboard, send them to their module
  // home instead of an empty/irrelevant Operations dashboard. Only fires
  // when Operations is NOT entitled (so full/operations trials are
  // unaffected) and honours the ?as=operator preview escape hatch.
  // Iter 220ea·42 / module-access enforcement — a user without Operations
  // entitlement must never render the Operations dashboard, even via a direct
  // /dashboard deep-link or bookmark. Send them to their resolved home:
  // Pulse Fitness Ltd staff get the area selector, other companies go straight
  // to a module they're granted (never the selector). Honours ?as=operator.
  if (!previewAsOperator && user.module_access && !user.module_access.operations) {
    return <Navigate to={resolveHomePath(user)} replace />;
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
 * Pulse Pro main dashboard, Partner-Engineer, the Pulse Fitness operator
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
  // Iter 274 — independent engineers are locked to the Engineer App.
  if (isLockedEngineer(user)) return <Navigate to={lockedEngineerHome(user)} replace />;
  const at = user.account_type;
  const isMaster = user.is_master_admin || user.role === 'master_admin' || user.role === 'master';
  // Master admins always have full CRM access.
  if (isMaster) return <CRMApp />;
  const ma = user.module_access || user.moduleAccess || {};
  // Lite / Pulse Pro / MOD customers get the trial / upgrade gate — that's
  // their self-serve path to buy CRM.
  if (at === 'pulse_pro' || at === 'lite' || at === 'mod_site' || at === 'mod_branch' || at === 'mod_org') {
    return <ModuleAccessGate module="crm"><CRMApp /></ModuleAccessGate>;
  }
  // Everyone else (incl. full-org Pulse Fitness staff) is gated on their
  // resolved per-user entitlement. Previously `account_type === 'full'` was a
  // blanket bypass, letting a staffer with CRM revoked still open /crm. Now a
  // missing grant sends them to their resolved home (selector for Pulse Fitness
  // Ltd staff, their granted module for other companies).
  if (ma.crm === true) return <CRMApp />;
  return <Navigate to={resolveHomePath(user)} replace />;
}

/**
 * Operations dashboard route guard. A user WITHOUT Operations entitlement must
 * never render the Operations surface (`/pulse`), even via a direct link or a
 * remembered-area forward — otherwise the global "Access needed" overlay pops
 * on top of a page they could reveal by dismissing it. Send them to their
 * resolved home instead (Pulse Fitness Ltd staff → the /launch area selector).
 * lite / pulse_pro / MOD accounts keep /pulse as their core home, and admins
 * and the ?as=operator preview are unaffected.
 */
function PulseRouteElement({ user, login }) {
  const loc = useLocation();
  if (!user) return <PulseLandingPage onLogin={(d) => login(d.token, d.user)} />;
  if (isLockedEngineer(user)) return <Navigate to={lockedEngineerHome(user)} replace />;
  const previewAsOperator = new URLSearchParams(loc.search).get('as') === 'operator';
  const isAdmin = user.is_master_admin || user.is_pulse_admin;
  const ma = user.module_access || {};
  // No Operations entitlement → send them to their resolved home (Pulse Fitness
  // Ltd staff → /launch). Guard against a home that is itself /pulse (a genuine
  // single-site pulse_pro/lite customer) to avoid a redirect loop.
  if (!previewAsOperator && !isAdmin && ma.operations === false) {
    const home = resolveHomePath(user);
    if (home !== '/pulse') return <Navigate to={home} replace />;
  }
  return <LiteDashboardPage />;
}

export default function AppRoutes({ user, login }) {
  const location = useLocation();
  const { activeSite, allSitesMode } = useAuth();
  const isEngineerRoute = /^\/svc\/engineer/.test(location.pathname);
  // Multi-site isolation — remount the active page when the site changes
  // so every module re-fetches its now site-scoped data (brief: key tied
  // to the active site). Route navigation within a site is unaffected.
  const siteKey = allSitesMode ? 'all' : (activeSite?.id || 'none');
  return (
    <>
    <Routes key={siteKey}>
      {/* ─── Default landing → Pulse Fitness experience (was GymAxis MarketingHome) ─── */}
      <Route path="/" element={
        user
          ? (user.is_master_admin
              ? (user.org_is_operator
                  ? <Navigate to="/dashboard" replace />
                  : <Navigate to="/master-admin" replace />)
              : isLockedEngineer(user)
                ? <Navigate to={lockedEngineerHome(user)} replace />
                : (user.is_pulse_admin && user.org_is_operator)
                    ? <Navigate to="/dashboard" replace />
                    : <LiteDashboardPage />)
          : (isModServiceMode()
              ? <MODServiceLogin />
              : <PulseLandingPage onLogin={(d) => login(d.token, d.user)} />)
      } />
      {/* MODService mode: keep the commercial /login marketing entry from being
          the public face of the MOD domain — bounce it to the MOD sign-in. */}
      {isModServiceMode() && (
        <Route path="/login" element={<Navigate to="/" replace />} />
      )}
      <Route path="/m/:slug/join" element={<JoinPage />} />
      <Route path="/m/:slug/join/success" element={<JoinSuccess />} />
      {/* Iter 216h83 — public live tracking (no auth, token-gated) */}
      <Route path="/track/:token" element={<PublicTrackingPage />} />
      <Route path="/org/:token" element={<PublicOrgChartPage />} />
      <Route path="/contracts/accept/:token" element={<PublicContractAcceptPage />} />
      <Route path="/quote/sign/:token" element={<PublicQuoteSignPage />} />
      {/* Public email preference centre + one-click unsubscribe (no auth) */}
      <Route path="/preferences/:token" element={<PublicPreferencesPage />} />
      <Route path="/unsubscribe/:token" element={<PublicUnsubscribePage />} />
      <Route path="/c/view/:id" element={<PublicEmailViewPage />} />
      <Route path="/c/forward/:id" element={<PublicForwardPage />} />
      {/* Engineer Partner Network retired (legacy) — public recruitment landing redirected home. */}
      <Route path="/partners/engineers" element={<Navigate to="/" replace />} />
      {/* Iter 216h286 — Gap 8: public review submission page.
          Linked from the find-engineer card; surfaces star + body
          ratings the engineer dashboard then responds to. */}
      <Route path="/engineer/:partnerId/review" element={<PartnerReviewPublic />} />
      {/* Iter 220y — Public Wall of Reviews (read-only) addressed
          by human-readable slug. Linked from the engineer's email
          signature / business card / LinkedIn. */}
      <Route path="/engineers/:slug/reviews" element={<EngineerReviewsWall />} />
      {/* Iter 220aa — Embedded "Log a Fault" / "Get a Quote" form.
          Designed to be loaded inside an iframe on an engineer's or
          company's marketing website. Public, token-gated. */}
      <Route path="/embed/log-fault/:token" element={<EmbedFaultForm />} />
      <Route path="/new-starter/:token" element={<NewStarterPortal />} />
      {/* Staff sign-in unified into the main platform login. The dedicated
          /staff-login page is retired — redirect any old links to /login. */}
      <Route path="/staff-login" element={<Navigate to="/login" replace />} />
      <Route path="/staff-reset/:token" element={<StaffResetPassword />} />
      <Route path="/staff-portal" element={<StaffPortal />} />
      <Route path="/bfpo/invite/:token" element={<BFPOInviteSetPassword />} />
      <Route path="/bfpo/*" element={isExternalEngineer(user) ? <Navigate to="/svc/engineer" replace /> : <BFPOApp />} />
      <Route path="/witness-statement/:token" element={<WitnessStatementPage />} />
      {/* Iter 216h287 — Gap 9: engineer-of-engineer recruit landing.
          Branded one-pager from a peer engineer's referral link. */}
      <Route path="/engineer/r/:code" element={<EngineerReferralLanding />} />
      {/* Engineer Partner Network retired (legacy) — public application form redirected home. */}
      <Route path="/partners/engineers/apply" element={<Navigate to="/" replace />} />
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
      <Route path="/demo-request" element={<DemoRequestPage />} />
      <Route path="/legacy-contact" element={<ContactPage />} />
      {/* Iter 216h280 — renamed from `/api-docs` (which Kubernetes
          ingress routes to the backend due to the `/api*` prefix
          rule, producing a hard 404 before React loaded). */}
      <Route path="/developers" element={<ApiDocsPage />} />
      {/* Legacy redirect for any external bookmarks. */}
      <Route path="/api-docs" element={<Navigate to="/developers" replace />} />
      <Route path="/security" element={<SecurityMarketingPage />} />
      <Route path="/security/details" element={<SecurityDocumentPage />} />
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
      <Route path="/solutions" element={<SolutionsIndex />} />
      <Route path="/solutions/:slug" element={<SolutionLanding />} />
      <Route path="/maintenance" element={<MaintenanceIndex />} />
      <Route path="/maintenance/:slug" element={<ManufacturerLanding />} />
      <Route path="/equipment" element={<EquipmentIndex />} />
      <Route path="/equipment/:slug" element={<EquipmentLanding />} />
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
      {/* Iter 220ba — public SLA + Sub-processors register (footer-linked) */}
      <Route path="/sla" element={<SlaPage />} />
      <Route path="/legal/sla" element={<Navigate to="/sla" replace />} />
      <Route path="/sub-processors" element={<SubProcessorsPage />} />
      <Route path="/legal/sub-processors" element={<Navigate to="/sub-processors" replace />} />
      {/* Iter 216h280 — legacy aliases. We never had `/legal/privacy`,
          `/legal/terms`, `/forgot-password` or `/svc/engineer/parts`
          as real pages, but a handful of links/buttons pointed there
          and a few external bookmarks may. Redirect them in-app so
          users always land on the right page. */}
      <Route path="/legal/privacy" element={<Navigate to="/privacy" replace />} />
      <Route path="/legal/terms"   element={<Navigate to="/terms" replace />} />
      <Route path="/forgot-password" element={<Navigate to="/reset-password" replace />} />
      <Route path="/svc/engineer/parts" element={<Navigate to="/svc/engineer/stock" replace />} />

      {/* ─── Auth & onboarding ─── */}
      {/* Iter 216h68 — always render LoginRedirectPage so it can honour
          `?next=/path` for already-logged-in users (e.g. when the
          SessionResumedBanner deep-links back after a 24h+ expiry). */}
      <Route path="/login" element={<LoginRedirectPage />} />
      <Route path="/launch" element={user ? (isExternalEngineer(user) ? <Navigate to="/svc/engineer" replace /> : <LauncherPage />) : <Navigate to="/login" replace />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/sso-complete" element={<SSOCompletePage />} />
      <Route path="/change-password" element={user ? <ForceChangePasswordPage /> : <Navigate to="/login" replace />} />
      <Route path="/complete-profile" element={user ? <CompleteProfilePage /> : <Navigate to="/" replace />} />
      <Route path="/onboarding/:token" element={<CustomerOnboardingForm />} />
      <Route path="/mod-capture/:token" element={<MODEquipmentCaptureForm />} />
      <Route path="/mod-booking/:token" element={<MODVisitBookingForm />} />
      <Route path="/payment-success" element={<PaymentSuccessPage />} />
      {/* Trial-ending email destination — login-gated paid checkout, no free-trial offer (iter 221) */}
      <Route path="/choose-plan" element={user ? <ChoosePlanPage /> : <Navigate to="/login?next=/choose-plan" replace />} />

      {/* Iter 216h109 — MOD Service portal (branded login).
          On the commercial (pulsefitness.ai) deployment these forward to the
          dedicated MOD deployment so there is one canonical MOD entry point.
          On the MOD deployment itself they render the branded login. */}
      <Route path="/MODService" element={isModServiceMode() ? <MODServiceLogin /> : <ExternalRedirect to={MODSERVICE_URL} />} />
      <Route path="/MODService/login" element={isModServiceMode() ? <MODServiceLogin /> : <ExternalRedirect to={MODSERVICE_URL} />} />
      <Route path="/mod/confirm-fix/:token" element={<MODConfirmFixPage />} />
      <Route path="/modservice" element={isModServiceMode() ? <Navigate to="/MODService" replace /> : <ExternalRedirect to={MODSERVICE_URL} />} />

      {/* ─── Public utility ─── */}
      <Route path="/supplier/case/:token" element={<div className="pulse-font" style={{ display: 'contents' }}><SupplierCasePage /></div>} />
      <Route path="/parts-card/:token" element={<div className="pulse-font" style={{ display: 'contents' }}><PartsCardPage /></div>} />
      <Route path="/parts-requests" element={user ? <div className="pulse-font" style={{ display: 'contents' }}><PartsRequestsPage /></div> : <Navigate to="/login?next=/parts-requests" replace />} />
      <Route path="/scan/:equipmentId" element={<QRScanPage />} />
      <Route path="/r/eq/:equipmentId" element={<EngineerFaultReportPage />} />
      <Route path="/r/c/:code" element={<EngineerFaultReportPage />} />
      <Route path="/forms/:slug" element={<PublicFormPage />} />
      <Route path="/p/:slug" element={<PublicLandingPage />} />

      {/* ─── Master / admin ─── */}
      <Route path="/master-admin" element={(user?.is_master_admin || user?.is_pulse_admin) ? <MasterAdminPage /> : <Navigate to="/login" replace />} />
      <Route path="/admin/design-system" element={user?.is_master_admin ? <DesignSystemPage /> : <Navigate to="/login" replace />} />
      <Route path="/admin/integrations" element={user?.is_master_admin ? <IntegrationsConsole /> : <Navigate to="/login" replace />} />
      <Route path="/admin/integrations/sicon" element={user?.is_master_admin ? <IntegrationsSiconConnect /> : <Navigate to="/login" replace />} />
      <Route path="/admin/parts-requests" element={user?.is_master_admin ? <AdminPartsRequests /> : <Navigate to="/login" replace />} />
      <Route path="/admin/mod-sites/bulk-import" element={user?.is_master_admin ? <AdminMODSitesBulkImport /> : <Navigate to="/login" replace />} />

      {/* ─── Modules (Iter 216h110 — MOD users are firewalled out) ─── */}
      <Route path="/marketing" element={user ? <MODForbidden><ModuleAccessGate module="marketing"><MarketingSuite /></ModuleAccessGate></MODForbidden> : <Navigate to="/login" replace />} />
      <Route path="/comms" element={user ? <MODForbidden><ModuleAccessGate module={["marketing", "memberships", "crm"]}><CommsCentre /></ModuleAccessGate></MODForbidden> : <Navigate to="/login" replace />} />
      <Route path="/crm" element={<MODForbidden><CrmRouteElement user={user} /></MODForbidden>} />
      <Route path="/blue-light/visit/:visitId" element={<BlueLightVisitWizard />} />
      <Route path="/crm/setup" element={user ? <MODForbidden><ModuleAccessGate module="crm"><CRMSetupWizard /></ModuleAccessGate></MODForbidden> : <Navigate to="/login" replace />} />
      <Route path="/memberships" element={user ? <MODForbidden><ModuleAccessGate module="memberships"><MembershipsConsole /></ModuleAccessGate></MODForbidden> : <Navigate to="/login" replace />} />
      <Route path="/memberships/setup" element={user ? <MODForbidden><ModuleAccessGate module="memberships"><MembershipsSetupWizard /></ModuleAccessGate></MODForbidden> : <Navigate to="/login" replace />} />
      <Route path="/memberships/:tab" element={user ? <MODForbidden><ModuleAccessGate module="memberships"><MembershipsConsole /></ModuleAccessGate></MODForbidden> : <Navigate to="/login" replace />} />
      <Route path="/gym-floor" element={<MODForbidden><GymFloorPage /></MODForbidden>} />

      {/* ─── Service Desk (unified — iter 216h53 full merge of Service Ops) ─── */}
      <Route path="/service-desk" element={can(user, 'view_service_desk') ? <div className="pulse-font" style={{ display: 'contents' }}><ServiceDeskPage /></div> : <Navigate to="/login" replace />} />
      {/* Iter 253 — self-serve Service Provider funnel: public signup +
          post-signup setup wizard (branding → SLA → first engineer). */}
      <Route path="/service-provider/signup" element={<ServiceProviderSignup />} />
      <Route path="/service-desk/setup" element={user ? <ServiceProviderSetup /> : <Navigate to="/login?next=/service-desk/setup" replace />} />
      <Route path="/service-desk/upgrade" element={user ? <ServiceProviderUpgrade /> : <Navigate to="/login?next=/service-desk/upgrade" replace />} />
      {/* Inventory & Distribution — Global Dealer Distribution (Phase 1) */}
      <Route path="/service-desk/inventory" element={<Navigate to="/inventory" replace />} />
      <Route path="/inventory" element={can(user, 'view_inventory') ? <div className="pulse-font" style={{ display: 'contents' }}><InventoryDistribution /></div> : ((user?.role || '').toLowerCase() === 'logistics' ? <Navigate to="/logistics" replace /> : <Navigate to="/login?next=/inventory" replace />)} />
      {/* Legacy /service-ops/* URLs redirect to the unified hub. Deep links still work — the merged shell defaults to Dashboard. */}
      <Route path="/service-ops" element={<Navigate to="/service-desk" replace />} />
      <Route path="/service-ops/scheduler" element={<Navigate to="/service-desk" replace />} />
      <Route path="/service-ops/engineers" element={<Navigate to="/service-desk" replace />} />
      <Route path="/service-ops/parts" element={<Navigate to="/service-desk" replace />} />
      <Route path="/service-ops/billing" element={<Navigate to="/service-desk" replace />} />
      <Route path="/service-ops/reports" element={<Navigate to="/service-desk" replace />} />
      <Route path="/service-ops/comms" element={<Navigate to="/service-desk" replace />} />
      <Route path="/svc/engineer" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerHome /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      <Route path="/support" element={user ? <EngineerSupport /> : <Navigate to="/login" replace />} />
      <Route path="/svc/engineer/jobs" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerJobsList /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      <Route path="/svc/engineer/jobs/:caseId" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerJob /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      <Route path="/svc/engineer/quotes" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerQuotes /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      <Route path="/svc/engineer/quotes/new" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerQuoteBuilder /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      <Route path="/svc/engineer/quotes/:id" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerQuoteBuilder /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      <Route path="/svc/engineer/invoices" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerInvoices /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      <Route path="/svc/engineer/invoices/new" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerInvoiceBuilder /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      <Route path="/svc/engineer/invoices/:id" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerInvoiceBuilder /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      <Route path="/svc/engineer/payouts" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerPayouts /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      {/* Iter 216h140 — Engineer App Phase 4 */}
      <Route path="/svc/engineer/diary" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerDiary /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      <Route path="/service-desk/dispatch" element={user ? <ServiceOpsAdminDispatchBoard /> : <Navigate to="/login" replace />} />
      {/* Iter 216h141 — Engineer Workspace (desktop 3-column) */}
      <Route path="/svc/engineer/workspace" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerWorkspace /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      {/* Iter 216h142 — Engineer Notifications */}
      <Route path="/svc/engineer/notifications" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerNotifications /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      {/* Iter 216h143 — Engineer Sync queue (offline writes) */}
      <Route path="/svc/engineer/sync" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerSyncPanel /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      {/* Iter 216h144 — Engineer independence */}
      <Route path="/svc/engineer/jobs/new" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerNewJob /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      <Route path="/svc/engineer/inbox"    element={user ? <EngineerErrorBoundary><ServiceOpsEngineerInbox /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      <Route path="/r/:slug"               element={<PublicEngineerCard />} />
      {/* Iter 216h147 — Engineer self-claim queue */}
      <Route path="/svc/engineer/queue"    element={user ? <EngineerErrorBoundary><ServiceOpsEngineerQueue /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      {/* Iter 216h148 — Public engineer landing/login */}
      <Route path="/engineer"  element={<PublicEngineerLanding />} />
      <Route path="/engineers" element={<Navigate to="/engineer" replace />} />
      {/* Iter 216h159 — Engineer card-conversion analytics */}
      <Route path="/svc/engineer/card-analytics" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerCardAnalytics /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      <Route path="/svc/engineer/analytics" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerAnalytics /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      <Route path="/svc/engineer/end-of-day" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerEndOfDay /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      <Route path="/svc/engineer/customers" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerCustomers /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      <Route path="/svc/engineer/expenses" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerExpenses /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      {/* Iter 220ci — Engineer Equipment Tab */}
      <Route path="/svc/engineer/equipment" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerEquipment /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      {/* Iter 276 — Machine history from an Operations QR scan */}
      <Route path="/svc/engineer/machine/:equipmentId" element={user ? <EngineerErrorBoundary><EngineerMachineHistory /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      <Route path="/svc/engineer/equipment/new" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerEquipmentForm /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      {/* Iter 220ea·19 — Engineer Stock Control hub */}
      <Route path="/svc/engineer/stock" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerStock /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      {/* Iter 220ea·20 — Parts Catalogue + Import */}
      <Route path="/svc/engineer/catalogue" element={user ? <EngineerErrorBoundary><ServiceOpsPartsCatalogue /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      {/* Iter 220ea·22 — Phase 4: Office/Admin stock management */}
      <Route path="/svc/engineer/stock-admin" element={user ? <EngineerErrorBoundary><ServiceOpsAdminStock /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      {/* Iter 220ea·33 — Legacy report import wizard */}
      <Route path="/svc/engineer/legacy-import" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerLegacyImport /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      {/* Iter 220 — Work Report custom fields manager */}
      <Route path="/svc/engineer/work-report-fields" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerWorkReportFields /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      <Route path="/svc/engineer/case-types" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerCaseTypes /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      {/* Iter 220i — Upcoming jobs list */}
      <Route path="/svc/engineer/upcoming" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerUpcoming /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      <Route path="/svc/engineer/branding" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerBranding /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      {/* Iter 220ea·10 — Engineer Account Settings → H&S checklist editor */}
      <Route path="/svc/engineer/h-s-checklist" element={user ? <EngineerErrorBoundary><ServiceOpsSafetyTemplateAdmin /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />
      <Route path="/svc/engineer/ratings" element={user ? <EngineerErrorBoundary><ServiceOpsEngineerRatings /></EngineerErrorBoundary> : <Navigate to="/login" replace />} />

      {/* ─── Public no-login quote-accept landing ─── */}
      <Route path="/q/:shortcode" element={<PublicQuoteAcceptPage />} />
      <Route path="/aq/:shortcode" element={<PublicAfsQuoteAcceptPage />} />

      {/* Iter 216h75 — Partner Engineer Network (Phase 1) — Iter 216h110: MOD-blocked */}
      <Route path="/partner-engineer" element={user ? <MODForbidden><PartnerDashboard /></MODForbidden> : <Navigate to="/login?next=/partner-engineer" replace />} />
      <Route path="/dealer-portal" element={user ? <DealerPortalStandalone /> : <Navigate to="/login?next=/dealer-portal" replace />} />
      <Route path="/logistics" element={user ? <LogisticsPortal /> : <Navigate to="/login?next=/logistics" replace />} />
      {/* Iter 216h282 — Gap 3/7 from BA audit. Single canonical
          application form lives at `/partners/engineers/apply`
          (the public `PartnerApplyPublic`). The duplicate logged-in
          wizard (`PartnerApplyWizard`) has been deleted — the form
          works without login and `_resolve_or_create_partner` on the
          backend dedupes by email so an authed re-application is
          handled by the same endpoint. */}
      <Route path="/partner-engineer/apply" element={<Navigate to="/" replace />} />
      {/* Iter 219f — single-use activation page from approval email.
          Public (no auth) — the engineer doesn't have an account yet. */}
      <Route path="/partner-engineer/activate" element={<PartnerEngineerActivate />} />
      {/* Iter 220ea·31 — public trial-feedback page (tokenised, no auth) */}
      <Route path="/partner-engineer/trial-feedback/:token" element={<TrialFeedback />} />

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

      {/* ─── Pulse (Iter 216h113 — MOD users land here too) ─── */}
      <Route path="/pulse" element={<PulseRouteElement user={user} login={login} />} />
      <Route path="/pulse-pricing" element={<PulsePricingPage onLogin={(d) => login(d.token, d.user)} />} />

      {/* ─── Help ─── */}
      <Route path="/help" element={user ? <HelpCentrePage /> : <Navigate to="/login" replace />} />
      <Route path="/help/:guideId" element={user ? <HelpCentrePage /> : <Navigate to="/login" replace />} />

      {/* ─── Dashboard resolver ─── */}
      <Route path="/dashboard" element={<DashboardRoute user={user} />} />

      {/* ─── 404 ─── */}
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
    {user && isEngineerRoute ? <EngineerOfflineIndicator /> : null}
    {user && isEngineerRoute ? (
      <Suspense fallback={null}>
        {/* Iter 220ea·5 — Single consolidated SpeedDial replaces
            the three independent FABs on engineer routes. The
            modals themselves (voice / ask / feedback) listen for
            `gx:open-*` events fired by the dial. */}
        <EngineerSpeedDial />
        <EngineerVoiceToJobButton />
      </Suspense>
    ) : null}
    </>
  );
}
