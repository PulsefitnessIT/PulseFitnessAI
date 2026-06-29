import React, { Suspense, lazy, useState, useEffect } from 'react';
import { useAuth } from '@/App';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { Loader2 } from 'lucide-react';

import { useUserPref } from '@/utils/userPrefs';

import Navbar from '../components/shared/Navbar';
import ModuleSwitcher from '../components/shared/ModuleSwitcher';
import { Tabs, TabsContent } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';

// Iter 216h173 — Heavy per-tab dashboards (GymDesign 1,353 LoC, Settings
// 1,198 LoC, etc.) are lazy-loaded. Operators land on Start/Overview;
// every other tab fetches on first visit, shrinking the initial JS
// bundle parsed during the operator's first login.
const GymDesignTab = lazy(() => import('./GymDesignTab'));
const EquipmentInfoTab = lazy(() => import('./EquipmentInfoTab'));
const SettingsTab = lazy(() => import('./SettingsTab'));
const WeeklyDigest = lazy(() => import('./WeeklyDigest'));
const DocumentsTab = lazy(() => import('./DocumentsTab'));
const SupplierDashboardTab = lazy(() => import('./SupplierDashboardTab'));
const MasterAdminPage = lazy(() => import('./MasterAdminPage'));
const FaultsTab = lazy(() => import('./Dashboard/FaultsTab'));
const ReportsSection = lazy(() => import('./Dashboard/ReportsSection'));
const MaintenanceTab = lazy(() => import('./Dashboard/MaintenanceTab'));
const AdminDashboardTab = lazy(() => import('./Dashboard/AdminAnalytics/AdminDashboardTab'));
const AdminEquipmentTab = lazy(() => import('./Dashboard/AdminAnalytics/AdminEquipmentTab'));
const AdminFaultsTab = lazy(() => import('./Dashboard/AdminAnalytics/AdminFaultsTab'));
const AdminCheckSheetsTab = lazy(() => import('./Dashboard/AdminAnalytics/AdminCheckSheetsTab'));
const GlobalDocumentsTab = lazy(() => import('./Dashboard/AdminAnalytics/GlobalDocumentsTab'));
const OperationsStartTab = lazy(() => import('./LiteDashboard/OperationsStartTab'));
const StaffingConsole = lazy(() => import('./LiteDashboard/StaffingConsole'));
const InvoiceImportWizard = lazy(() => import('./InvoiceImportWizard'));
const OnboardingWizard = lazy(() => import('./OnboardingWizard'));

const DashboardTabFallback = () => (
  <div className="flex items-center justify-center py-16 text-zinc-400" data-testid="dashboard-tab-loading">
    <Loader2 size={18} className="animate-spin" />
  </div>
);

import MobileBottomNav from '../components/shared/MobileBottomNav';
import OverviewTab from './Dashboard/OverviewTab';
import DashboardTabs from './Dashboard/DashboardTabs';
import FaultDialogs from './Dashboard/FaultDialogs';
import DocumentQA from '../components/shared/DocumentQA';
import PullToRefresh from '../components/shared/PullToRefresh';
import ProductTour from '../components/shared/ProductTour';

import useDashboardData from './Dashboard/hooks/useDashboardData';
import useIssueWorkflow from './Dashboard/hooks/useIssueWorkflow';
import { getSeverityColor, getSeverityLabel, getStatusColor } from './Dashboard/utils/severity';
import GamifiedOnboarding from './Dashboard/GamifiedOnboarding';
import WelcomeHero from './Dashboard/WelcomeHero';
import NudgeBanner from '../components/shared/NudgeBanner';
import { useSeo } from '../utils/seo';
import { can } from '../utils/capabilities';

const DashboardPage = () => {
  const { user, API, theme } = useAuth();
  // Iter 216o-6 — owns its own document.title so navigating from a SEO
  // page (e.g. /pricing) back to /dashboard correctly resets the tab.
  useSeo({ title: 'Dashboard · Pulse Fitness AI' });
  const { t, i18n } = useTranslation();
  const [searchParams] = useSearchParams();

  // Iter 216c — match LiteDashboardPage: first-time users land on the
  // guided "Start" tab (which now hosts the "Your first wins" card);
  // returning users who completed onboarding (or dismissed Start) land
  // on Dashboard / Overview directly.
  const [activeTab, setActiveTab] = useState(() => {
    try {
      const prefs = JSON.parse(localStorage.getItem('gymaxis_prefs') || '{}');
      return prefs.hideStartTabs ? 'overview' : 'start';
    } catch { return 'overview'; }
  });
  // Iter 216c — when ActivationMilestonesCard auto-completes (all 8 wins
  // hit) it flips `hideStartTabs=true`. If the user happened to be on the
  // Start tab at that moment, snap them to Overview so they don't see a
  // blank tab content.
  const [hideStartTabs] = useUserPref('hideStartTabs', false);
  useEffect(() => {
    if (hideStartTabs && activeTab === 'start') setActiveTab('overview');
  }, [hideStartTabs, activeTab]);
  const [reportSubTab, setReportSubTab] = useState('performance');
  const [showSettingsDialog, setShowSettingsDialog] = useState(false);
  const [showMasterAdmin, setShowMasterAdmin] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [showGamifiedOnboarding, setShowGamifiedOnboarding] = useState(false);
  const [onboardingStatus, setOnboardingStatus] = useState(null);
  const [showInvoiceImport, setShowInvoiceImport] = useState(false);
  const [viewAudit, setViewAudit] = useState(null);
  const [expiryFilterIds, setExpiryFilterIds] = useState(null);
  const [taskFrequencyFilter, setTaskFrequencyFilter] = useState('all');

  // Fault list filters (dashboard-scoped)
  const [faultFilterMachine, setFaultFilterMachine] = useState('all');
  const [faultFilterStatus, setFaultFilterStatus] = useState('all');
  const [faultFilterSeverity, setFaultFilterSeverity] = useState('all');

  const tourRef = React.useRef(null);

  const {
    issues, setIssues, auditHistory, maintenanceTasks, suppliers,
    allEquipment, healthScore, urgentExpiryAlerts,
    loadData, checkPaymentStatus,
  } = useDashboardData(API);

  // Check payment status once on mount (Stripe redirect)
  React.useEffect(() => {
    const sessionId = searchParams.get('session_id');
    if (sessionId) checkPaymentStatus(sessionId, t('dashboard.payment_success'));
    // Iter 216h193 — handle deep-link query params from the "Your first wins"
    // CTA on the Start tab.
    //   ?tab=…           → switch the active tab (equipment / staffing / …)
    //   ?onboarding=1    → open the equipment OnboardingWizard immediately
    const tab = searchParams.get('tab');
    if (tab) setActiveTab(tab);
    const onboarding = searchParams.get('onboarding');
    if (onboarding === '1') setShowOnboarding(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, []);

  // Load onboarding status — drives the welcome hero visibility
  const loadOnboardingStatus = React.useCallback(async () => {
    if (user?.is_master_admin) return;
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get(`${API}/onboarding/status`, { headers: { Authorization: `Bearer ${token}` } });
      setOnboardingStatus(res.data);
      // Iter 215bz — auto-open the OnboardingWizard for brand-new operator
      // accounts (no equipment yet, banner not dismissed, onboarding never
      // completed). Suppressed by `onboarding_wizard_seen:<userId>` localStorage
      // flag so closing once = never auto-shown again on this browser.
      try {
        const data = res.data || {};
        const seenKey = `onboarding_wizard_seen:${user?.id || 'anon'}`;
        const alreadySeen = localStorage.getItem(seenKey);
        const shouldShow = !alreadySeen
          && !data.dismissed
          && !data.completed_at
          && data.percent === 0
          && (data.counts?.equipment_count ?? 0) === 0;
        if (shouldShow) {
          setShowOnboarding(true);
          localStorage.setItem(seenKey, '1');
        }
      } catch (_) { /* localStorage may be unavailable */ }
    } catch { /* ignored */ }
  }, [API, user?.is_master_admin, user?.id]);

  React.useEffect(() => { loadOnboardingStatus(); }, [loadOnboardingStatus]);

  const dismissWelcomeHero = async () => {
    setOnboardingStatus(prev => prev ? { ...prev, dismissed: true } : prev);
    try {
      const token = localStorage.getItem('token');
      await axios.post(`${API}/onboarding/dismiss`, {}, { headers: { Authorization: `Bearer ${token}` } });
    } catch { /* silent */ }
  };

  const handleOnboardingComplete = (nextAction) => {
    loadOnboardingStatus();
    loadData();
    if (nextAction === 'log_fault') wf.setShowIssueDialog(true);
  };

  const wf = useIssueWorkflow({ API, i18n, t, setIssues, loadData, allEquipment, user });

  const filteredIssues = issues.filter(i => {
    if (faultFilterMachine !== 'all' && i.machine_type !== faultFilterMachine) return false;
    if (faultFilterStatus !== 'all' && i.status !== faultFilterStatus) return false;
    if (faultFilterSeverity !== 'all') {
      const legacyMap = { operational_minor: 'low', operational_fault: 'medium', out_of_order: 'critical' };
      const legacy = legacyMap[faultFilterSeverity];
      if (i.severity !== faultFilterSeverity && i.severity !== legacy) return false;
    }
    return true;
  });

  if (showMasterAdmin && (user?.is_master_admin || user?.is_pulse_admin)) {
    return (
      <Suspense fallback={<DashboardTabFallback />}>
        <MasterAdminPage onBack={() => setShowMasterAdmin(false)} />
      </Suspense>
    );
  }

  const showSuppliersTab = can(user, 'view_suppliers');

  return (
    <div
      className={`min-h-screen overflow-x-hidden ${user?.account_type !== 'pulse_pro' && user?.account_type !== 'lite' && theme === 'light' ? 'theme-gymaxis' : ''}`}
      style={{ background: 'var(--theme-bg)' }}
    >
      <Navbar
        onOpenSettings={() => setShowSettingsDialog(true)}
        onOpenMasterAdmin={() => setShowMasterAdmin(true)}
        onStartTour={() => tourRef.current?.resetTour()}
      />

      <div className="pt-24 pb-12 module-fade-in">
        <PullToRefresh
          onRefresh={async () => {
            // Iter 215d8 — user pulls down to refresh the Operations dashboard.
            await loadData();
          }}
        >
        <div className="max-w-7xl mx-auto px-4">
          <div className="mb-8" data-testid="dashboard-header">
            <h1
              className="text-3xl sm:text-4xl tracking-tight font-bold mb-2"
              style={{ color: 'var(--theme-text)' }}
              data-testid="dashboard-title"
            >
              {user?.is_master_admin ? (
                <><span className="gx-grad-text">Global</span> Dashboard</>
              ) : t('dashboard.title')}
            </h1>
            <p style={{ color: 'var(--theme-text-muted)' }} data-testid="dashboard-subtitle">
              {user?.is_master_admin ? 'Cross-gym analytics, documents & management' : `${t('dashboard.welcome')}, ${user?.full_name}`}
            </p>
            {!user?.is_master_admin && (
              <Badge className="mt-2 bg-gradient-to-r from-[var(--color-brand-blue)] to-[var(--color-brand-cyan-deep)] text-white border-0 shadow-[0_4px_12px_-4px_rgba(37,99,235,0.35)]" data-testid="subscription-badge">
                {user?.subscription_tier === 'none' ? t('dashboard.free_tier') : t('dashboard.plan_label', { tier: user?.subscription_tier })}
              </Badge>
            )}
          </div>

          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            {/* Iter 215d1 — module switcher sits *between* the header and
                sub-tabs so Pulse Fitness matches Pulse Fitness Pro's established
                visual order (title → welcome → module pills → sub-tabs). */}
            <div className="mb-4 flex justify-start" data-testid="gymaxis-module-switcher-wrap">
              <ModuleSwitcher user={user} current="operations" />
            </div>
            <DashboardTabs activeTab={activeTab} setActiveTab={setActiveTab} showSuppliers={showSuppliersTab} t={t} />

            {/* Proactive nudges (warranty, PPM, supplier SLA drift) */}
            {!user?.is_master_admin && (
              <NudgeBanner canDismiss={can(user, 'dismiss_nudges')} />
            )}

            {/* Welcome hero (gamified onboarding) — shown for non-master-admin users who haven't dismissed or completed onboarding.
                Iter 216h249 — suppressed for trial operators whose declared primary module is NOT Operations.
                A Memberships / CRM / Marketing trial user landing on /dashboard should never see the
                Equipment / Suppliers wizard meant for gym operators. */}
            {!user?.is_master_admin && onboardingStatus && !onboardingStatus.dismissed && !onboardingStatus.stages?.live && !(user?.primary_module && user.primary_module !== 'operations') && (
              <WelcomeHero
                gymName={user?.organization_name || user?.gym_name || ''}
                status={onboardingStatus}
                onStart={() => setShowGamifiedOnboarding(true)}
                onDismiss={dismissWelcomeHero}
              />
            )}

            <TabsContent value="overview" data-testid="overview-content">
              <Suspense fallback={<DashboardTabFallback />}>
              {user?.is_master_admin ? (
                <AdminDashboardTab />
              ) : (
                <OverviewTab
                  healthScore={healthScore}
                  issues={issues}
                  auditHistory={auditHistory}
                  maintenanceTasks={maintenanceTasks}
                  urgentExpiryAlerts={urgentExpiryAlerts}
                  onLogIssue={() => wf.setShowIssueDialog(true)}
                  onNavigateTab={setActiveTab}
                  onViewExpiryAlerts={() => { setExpiryFilterIds(urgentExpiryAlerts.map(a => a.equipment_id)); setActiveTab('equipment'); }}
                  getStatusColor={getStatusColor}
                  t={t}
                />
              )}
              </Suspense>
            </TabsContent>

            {/* Iter 215d2 — Start tab mirrors Pulse Fitness Pro: guided onboarding
                surface for first-time operators. Reuses OperationsStartTab so
                both brands share one implementation. */}
            <TabsContent value="start" data-testid="start-content">
              <Suspense fallback={<DashboardTabFallback />}>
              <OperationsStartTab
                setTab={setActiveTab}
                onLogFault={() => wf.setShowIssueDialog(true)}
                onOpenEquipmentImport={() => setShowOnboarding(true)}
              />
              </Suspense>
            </TabsContent>

            {/* Iter 215d2 — Staffing tab matches Pulse Fitness Pro. StaffingConsole
                is already brand-agnostic (reads the active org) so master admins
                and operators see the right workforce data. */}
            <TabsContent value="staffing" data-testid="staffing-content">
              <Suspense fallback={<DashboardTabFallback />}>
              <StaffingConsole />
              </Suspense>
            </TabsContent>

            <TabsContent value="issues" data-testid="issues-content">
              <Suspense fallback={<DashboardTabFallback />}>
              {user?.is_master_admin ? (
                <AdminFaultsTab />
              ) : (
                <FaultsTab
                  issues={issues}
                  filteredIssues={filteredIssues}
                  faultFilterMachine={faultFilterMachine}
                  faultFilterStatus={faultFilterStatus}
                  faultFilterSeverity={faultFilterSeverity}
                  selectedIssue={wf.selectedIssue}
                  suppliers={suppliers}
                  onLogIssue={() => wf.setShowIssueDialog(true)}
                  onSelectIssue={wf.setSelectedIssue}
                  onUpdateStatus={wf.handleUpdateIssueStatus}
                  onFilterMachine={setFaultFilterMachine}
                  onFilterStatus={setFaultFilterStatus}
                  onFilterSeverity={setFaultFilterSeverity}
                  getSeverityColor={getSeverityColor}
                  getSeverityLabel={getSeverityLabel}
                  getStatusColor={getStatusColor}
                  t={t}
                />
              )}
              </Suspense>
            </TabsContent>

            <TabsContent value="maintenance" data-testid="maintenance-content">
              <Suspense fallback={<DashboardTabFallback />}>
              {user?.is_master_admin ? (
                <AdminCheckSheetsTab />
              ) : (
                <MaintenanceTab
                  maintenanceTasks={maintenanceTasks}
                  taskFrequencyFilter={taskFrequencyFilter}
                  setTaskFrequencyFilter={setTaskFrequencyFilter}
                  t={t}
                />
              )}
              </Suspense>
            </TabsContent>

            <TabsContent value="gym-design" data-testid="gym-design-content">
              <Suspense fallback={<DashboardTabFallback />}>
              <GymDesignTab allEquipment={allEquipment} />
              </Suspense>
            </TabsContent>

            <TabsContent value="documents" data-testid="documents-content">
              <Suspense fallback={<DashboardTabFallback />}>
              {user?.is_master_admin ? <GlobalDocumentsTab /> : <DocumentsTab />}
              </Suspense>
            </TabsContent>

            <TabsContent value="suppliers" data-testid="suppliers-content">
              <Suspense fallback={<DashboardTabFallback />}>
              <SupplierDashboardTab />
              </Suspense>
            </TabsContent>

            <TabsContent value="equipment" data-testid="equipment-content">
              <Suspense fallback={<DashboardTabFallback />}>
              {user?.is_master_admin ? (
                <AdminEquipmentTab />
              ) : (
                <>
                  {/* Iter 216o-8 — Lifecycle Alerts have moved to the
                      CAPEX Intelligence tab (Reports → CAPEX). The
                      Equipment page is now a clean asset list, matching
                      the Pulse Fitness Operations layout. */}
                  <EquipmentInfoTab
                    expiryFilterIds={expiryFilterIds}
                    onClearExpiryFilter={() => setExpiryFilterIds(null)}
                    onOpenInvoiceImport={() => setShowInvoiceImport(true)}
                    onLogFault={(eq) => {
                      wf.setIssueForm((f) => ({
                        ...f,
                        serial_number: eq.serial_number || '',
                        machine_type: eq.equipment_type || eq.machine_type || '',
                        supplier: eq.supplier || f.supplier || '',
                      }));
                      wf.setShowIssueDialog(true);
                    }}
                  />
                </>
              )}
              </Suspense>
            </TabsContent>

            <Suspense fallback={null}>
            <OnboardingWizard open={showOnboarding} onClose={() => setShowOnboarding(false)} onComplete={loadData} />
            </Suspense>

            <Dialog open={showSettingsDialog} onOpenChange={setShowSettingsDialog}>
              <DialogContent
                className="border max-w-4xl max-h-[90vh] overflow-y-auto"
                style={{ background: 'var(--theme-surface)', color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }}
                data-testid="settings-dialog"
              >
                <DialogHeader>
                  <DialogTitle className="text-xl" style={{ color: 'var(--theme-text)' }}>Settings</DialogTitle>
                </DialogHeader>
                <Suspense fallback={<DashboardTabFallback />}>
                <SettingsTab />
                </Suspense>
              </DialogContent>
            </Dialog>

            <TabsContent value="digest" data-testid="digest-content">
              <Suspense fallback={<DashboardTabFallback />}>
              <WeeklyDigest />
              </Suspense>
            </TabsContent>

            <TabsContent value="reports" data-testid="reports-content">
              <Suspense fallback={<DashboardTabFallback />}>
              <ReportsSection
                reportSubTab={reportSubTab}
                onSubTabChange={setReportSubTab}
                auditHistory={auditHistory}
                viewAudit={viewAudit}
                onViewAudit={setViewAudit}
                user={user}
                t={t}
              />
              </Suspense>
            </TabsContent>
          </Tabs>
        </div>
        </PullToRefresh>
      </div>

      <FaultDialogs
        showIssueDialog={wf.showIssueDialog}
        issueStep={wf.issueStep}
        issueForm={wf.issueForm}
        setIssueForm={wf.setIssueForm}
        requireReporter={wf.requireReporter}
        siteStaff={wf.siteStaff}
        reporterStaffId={wf.reporterStaffId}
        setReporterStaffId={wf.setReporterStaffId}
        allowOtherStaff={wf.allowOtherStaff}
        requireStaffPin={wf.requireStaffPin}
        reporterPin={wf.reporterPin}
        setReporterPin={wf.setReporterPin}
        reporterOther={wf.reporterOther}
        setReporterOther={wf.setReporterOther}
        selectedMachineType={wf.selectedMachineType}
        setSelectedMachineType={wf.setSelectedMachineType}
        allEquipment={allEquipment}
        issueLoading={wf.issueLoading}
        issueMedia={wf.issueMedia}
        setIssueMedia={wf.setIssueMedia}
        faultMachines={wf.faultMachines}
        activeMachineIdx={wf.activeMachineIdx}
        setActiveMachineIdx={wf.setActiveMachineIdx}
        triageResult={wf.triageResult}
        setTriageResult={wf.setTriageResult}
        machineTriageResults={wf.machineTriageResults}
        resolutionNote={wf.resolutionNote}
        setResolutionNote={wf.setResolutionNote}
        selectedFixStep={wf.selectedFixStep}
        setSelectedFixStep={wf.setSelectedFixStep}
        equipmentCoverage={wf.equipmentCoverage}
        coverageLoading={wf.coverageLoading}
        existingFaultWarning={wf.existingFaultWarning}
        setExistingFaultWarning={wf.setExistingFaultWarning}
        onResetDialog={wf.resetIssueDialog}
        onIssueSubmit={wf.handleIssueSubmit}
        onAddMachine={wf.addMachineToFault}
        onRemoveMachine={wf.removeMachineFromFault}
        fetchCoverage={wf.fetchCoverage}
        onResolution={wf.handleResolution}
        onEngineerClick={wf.handleEngineerClick}
        setIssueStep={wf.setIssueStep}
        setIssues={setIssues}
        showPOPrompt={wf.showPOPrompt}
        setShowPOPrompt={wf.setShowPOPrompt}
        poForm={wf.poForm}
        setPOForm={wf.setPOForm}
        poCreating={wf.poCreating}
        onCreatePOAndLog={wf.handleCreatePOAndLog}
        onSkipPOAndLog={wf.handleSkipPOAndLog}
        showFaultSuccess={wf.showFaultSuccess}
        setShowFaultSuccess={wf.setShowFaultSuccess}
        faultSuccessType={wf.faultSuccessType}
        lastIssue={wf.lastIssue}
        showServiceDialog={wf.showServiceDialog}
        setShowServiceDialog={wf.setShowServiceDialog}
        serviceForm={wf.serviceForm}
        setServiceForm={wf.setServiceForm}
        onServiceSubmit={wf.handleServiceRequest}
        getSeverityColor={getSeverityColor}
        getSeverityLabel={getSeverityLabel}
        t={t}
        i18n={i18n}
        issues={issues}
        API={API}
        canManageOrgTemplates={can(user, 'manage_fault_templates')}
      />

      <MobileBottomNav
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onReportFault={() => wf.setShowIssueDialog(true)}
        variant="gymaxis"
      />

      {/* Bottom spacer for mobile nav */}
      <div className="h-20 md:hidden" />

      {activeTab !== 'documents' && <DocumentQA />}

      <ProductTour variant="gymaxis" ref={tourRef} />

      <GamifiedOnboarding
        open={showGamifiedOnboarding}
        onClose={() => setShowGamifiedOnboarding(false)}
        API={API}
        user={user}
        onComplete={handleOnboardingComplete}
      />

      {showInvoiceImport && (
        <Dialog open={showInvoiceImport} onOpenChange={setShowInvoiceImport}>
          <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="text-xl font-semibold" style={{ fontFamily: 'Outfit' }}>AI Equipment Import</DialogTitle>
            </DialogHeader>
            <Suspense fallback={<DashboardTabFallback />}>
            <InvoiceImportWizard
              onComplete={() => { setShowInvoiceImport(false); window.location.reload(); }}
              onClose={() => setShowInvoiceImport(false)}
            />
            </Suspense>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
};

export default DashboardPage;
