import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Tabs, TabsContent } from '@/components/ui/tabs';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle
} from '@/components/ui/dialog';
import axios from 'axios';
import { toast } from 'sonner';
import { useInlineBanner, useConfirm, notify } from '@/components/notifications';
import { Eye, LayoutDashboard, Dumbbell, AlertTriangle, FileText, ClipboardCheck, ClipboardList, BarChart3, Truck, LayoutGrid, Rocket, Sparkles, Users } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import Navbar from '../components/shared/Navbar';
import MobileBottomNav from '../components/shared/MobileBottomNav';
import MasterAdminPage from './MasterAdminPage';
import PulseCheckSheetsTab from './PulseCheckSheetsTab';
import PulseReportsTab from './PulseReportsTab';
import PullToRefresh from '../components/shared/PullToRefresh';
import PulseUpgradePage from './PulseUpgradePage';
import PulseSettingsTab from './PulseSettingsTab';
import PulseGymLayoutTab from './PulseGymLayoutTab';
import SupplierDashboardTab from './SupplierDashboardTab';
import OnboardingWizard from './OnboardingWizard';
import AddEquipmentDialog from '../components/equipment/AddEquipmentDialog';
import LiteOverviewTab from './LiteDashboard/LiteOverviewTab';
import LiteEquipmentTab from './LiteDashboard/LiteEquipmentTab';
import LiteFaultsTab from './LiteDashboard/LiteFaultsTab';
import LiteDocumentsTab from './LiteDashboard/LiteDocumentsTab';
import LiteDialogs from './LiteDashboard/LiteDialogs';
import GymFloorManagerTab from './LiteDashboard/GymFloorManagerTab';
import OperationsStartTab from './LiteDashboard/OperationsStartTab';
import StaffingConsole from './LiteDashboard/StaffingConsole';
import AllSitesOverview from './LiteDashboard/AllSitesOverview';
import SiteSwitcher from '../components/shared/SiteSwitcher';
import DocumentQA from '../components/shared/DocumentQA';
import ProductTour from '../components/shared/ProductTour';
import NudgeBanner from '../components/shared/NudgeBanner';
import ModuleSwitcher from '../components/shared/ModuleSwitcher';
import CrossModuleTipsBanner from '../components/shared/CrossModuleTipsBanner';
import PulseProUpgradeCta from '../components/shared/PulseProUpgradeCta';
import PillTabBar from '../components/shared/PillTabBar';
import { useUserPref } from '@/utils/userPrefs';

const SEVERITY_OPTIONS = [
  { value: 'operational_minor', label: 'Operational - Minor Issue', color: 'text-emerald-600 bg-emerald-50', desc: 'Machine is fully usable — minor fault or annoyance.' },
  { value: 'operational_fault', label: 'Operational - Fault Present', color: 'text-amber-600 bg-amber-50', desc: 'Machine works but not as intended — could worsen if ignored.' },
  { value: 'limited_use', label: 'Limited Use', color: 'text-orange-600 bg-orange-50', desc: 'Machine partially usable but restricted — some functions unavailable.' },
  { value: 'out_of_order', label: 'Out of Order', color: 'text-red-600 bg-red-50', desc: 'Cannot be used — must be taken out of service.' },
  { value: 'safety_critical', label: 'Safety Critical', color: 'text-red-700 bg-red-100', desc: 'Immediate safety hazard — isolate the machine immediately.' },
];

const getSeverityStyle = (sev) => {
  const map = {
    operational_minor: 'bg-emerald-500/20 text-emerald-400',
    operational_fault: 'bg-amber-500/20 text-amber-400',
    limited_use: 'bg-orange-500/20 text-orange-400',
    out_of_order: 'bg-red-500/20 text-red-400',
    safety_critical: 'bg-red-600/20 text-red-300',
    low: 'bg-emerald-500/20 text-emerald-400',
    medium: 'bg-amber-500/20 text-amber-400',
    critical: 'bg-red-500/20 text-red-400',
  };
  return map[sev] || 'bg-zinc-500/20 text-zinc-400';
};

const getSeverityLabel = (sev) => {
  const map = {
    operational_minor: 'Minor Issue', operational_fault: 'Fault Present',
    limited_use: 'Limited Use', out_of_order: 'Out of Order',
    safety_critical: 'Safety Critical', low: 'Minor Issue',
    medium: 'Fault Present', critical: 'Out of Order',
  };
  return map[sev] || sev;
};

const getStatusColor = (status) => {
  const map = {
    open: 'bg-amber-500/20 text-amber-400',
    in_progress: 'bg-blue-500/20 text-blue-400',
    resolved: 'bg-emerald-500/20 text-emerald-400',
  };
  return map[status] || 'bg-zinc-500/20 text-zinc-400';
};

const LiteDashboardPage = () => {
  const { API, user, logout, theme, toggleTheme, activeSite } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const adminView = searchParams.get('view'); // 'lite' or 'pro' for admin preview
  const isAdmin = user?.is_master_admin || user?.account_type === 'full';
  // Iter 216o-11 — Free-trial users get the FULL Pro tab set so they
  // can evaluate everything (Reports, Suppliers, Staffing, Gym Layout,
  // Check Sheets, Documents) before deciding whether to upgrade. Once
  // their trial converts they keep the same UI seamlessly. The Lite-only
  // 5-tab view (with the "Upgrade to Pro" tab) is reserved for users
  // who explicitly chose the lite tier (no trial, no subscription).
  const isTrialActive = user?.trial?.is_trial === true && user?.trial?.status !== 'expired' && user?.trial?.locked_out !== true;
  const isPro = adminView === 'lite'
    ? false
    : (user?.account_type === 'pulse_pro' || isAdmin || isTrialActive);
  // Iter 216i — multi-site overview toggle. Owners/managers can flip the
  // dashboard into "All sites" mode via the site-switcher dropdown; the
  // choice is local to this tab and clears as soon as they pick a single
  // site.
  const [allSitesActive, setAllSitesActive] = useState(false);
  const [equipment, setEquipment] = useState([]);
  const [issues, setIssues] = useState([]);
  const [files, setFiles] = useState([]);
  const [search, setSearch] = useState('');
  // Default first-time users to the guided 'Start' tab; existing users
  // who dismissed it start on Dashboard.
  const [activeTab, setActiveTab] = useState(() => {
    try {
      const prefs = JSON.parse(localStorage.getItem('gymaxis_prefs') || '{}');
      return prefs.hideStartTabs ? 'overview' : 'start';
    } catch { return 'overview'; }
  });
  const pulsePillBarRef = React.useRef(null);
  const [showFaultDialog, setShowFaultDialog] = useState(false);
  const [selectedEquipment, setSelectedEquipment] = useState(null);
  const [faultForm, setFaultForm] = useState({ equipment_id: '', serial_number: '', machine_type: '', issue_description: '', severity: 'operational_minor', supplier: '', fault_code: null });
  const [faultMedia, setFaultMedia] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [coverage, setCoverage] = useState(null);
  const [duplicateModal, setDuplicateModal] = useState(null);
  const [successModal, setSuccessModal] = useState(null);
  const [showSettingsDialog, setShowSettingsDialog] = useState(false);
  const [showMasterAdmin, setShowMasterAdmin] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [showAddEquipment, setShowAddEquipment] = useState(false);
  const pulseTourRef = React.useRef(null);
  const [faultFilterStatus, setFaultFilterStatus] = useState('all');
  // Tiered notifications — `docBanner` shows inline success/error for document
  // operations; `confirm` replaces browser window.confirm().
  const { banner: docBanner, show: showDocBanner } = useInlineBanner();
  const confirm = useConfirm();
  const [faultFilterSeverity, setFaultFilterSeverity] = useState('all');
  const [selectedIssue, setSelectedIssue] = useState(null);
  const [suppliers, setSuppliers] = useState([]);
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const adminDemoRole = isAdmin ? searchParams.get('role') : null;
  const userRole = adminDemoRole || (isAdmin ? 'owner' : (user?.role || 'staff'));

  const loadData = useCallback(async () => {
    try {
      const siteParam = (activeSite && !activeSite.is_default) ? `?site_id=${activeSite.id}` : '';
      const [eqRes, issRes, fileRes, supRes] = await Promise.all([
        axios.get(`${API}/equipment${siteParam}`, { headers }),
        axios.get(`${API}/issues${siteParam}`, { headers }),
        axios.get(`${API}/files/list`, { headers }),
        axios.get(`${API}/suppliers`, { headers }).catch(() => ({ data: { suppliers: [] } })),
      ]);
      setEquipment(eqRes.data.equipment || eqRes.data || []);
      setIssues(issRes.data.issues || []);
      setFiles(fileRes.data.files || []);
      setSuppliers(supRes.data.suppliers || supRes.data || []);
    } catch { /* ignore */ }
  }, [API, activeSite]);

  useEffect(() => { loadData(); }, [loadData]);

  // Listen for "Log Fault" events from gym layout editor
  useEffect(() => {
    const handler = (e) => {
      const eq = e.detail;
      if (eq) {
        selectEquipmentForFault(eq);
        setShowFaultDialog(true);
      }
    };
    window.addEventListener('open-fault-for-equipment', handler);
    return () => window.removeEventListener('open-fault-for-equipment', handler);
  }, []);

  /**
   * Listen for `gymaxis-jump` events from the Unified AI Assistant so
   * Claude can drive navigation. We honour:
   *   - target='faults|equipment|schedule|service-desk' → switch tab
   *   - deep_link.kind='fault'     → switch to Faults tab + open the issue drawer
   *   - deep_link.kind='equipment' → switch to Equipment tab + open the modal
   */
  useEffect(() => {
    const handler = (e) => {
      const detail = e.detail || {};
      if (detail.mode && detail.mode !== 'operations') return;
      if (typeof detail.target === 'string' && detail.target) {
        setActiveTab(detail.target);
      }
      const dl = detail.deep_link;
      if (dl?.kind === 'fault' && dl.id) {
        const found = issues.find(i => i.id === dl.id);
        if (found) {
          setActiveTab('faults');
          setSelectedIssue(found);
        }
      } else if (dl?.kind === 'equipment' && dl.id) {
        const found = equipment.find(eq => eq.id === dl.id);
        if (found) {
          setActiveTab('equipment');
          setSelectedEquipment(found);
        }
      }
    };
    window.addEventListener('gymaxis-jump', handler);
    return () => window.removeEventListener('gymaxis-jump', handler);
  }, [issues, equipment]);

  const openFaults = issues.filter(i => i.status === 'open');
  const operational = equipment.filter(e => !openFaults.some(f => f.serial_number === (e.serial_number || e.name)));
  const outOfOrder = equipment.length - operational.length;

  // Filtered issues for Faults tab
  const filteredIssues = issues.filter(i => {
    if (faultFilterStatus !== 'all' && i.status !== faultFilterStatus) return false;
    if (faultFilterSeverity !== 'all' && i.severity !== faultFilterSeverity) return false;
    return true;
  });

  // Inline banner for the Fault-logging dialog (validation + submit feedback).
  const { banner: faultBanner, show: showFaultBanner, clear: clearFaultBanner } = useInlineBanner();
  const { banner: faultsTabBanner, show: showFaultsTabBanner } = useInlineBanner();

  const handleFaultSubmit = async (overrides = {}) => {
    clearFaultBanner();
    if (!faultForm.serial_number || !faultForm.issue_description) {
      showFaultBanner({
        tone: 'error',
        title: 'Missing required details',
        detail: !faultForm.serial_number
          ? 'Please pick the affected machine from the list, then describe the issue.'
          : 'Please add a short description of the issue so engineers know where to start.',
      });
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        serial_number: faultForm.serial_number,
        machine_type: faultForm.machine_type,
        issue_description: faultForm.issue_description,
        severity: faultForm.severity,
        supplier: faultForm.supplier,
        steps_taken: faultForm.steps_taken || '',
        fault_code: faultForm.fault_code || null,
        media: faultMedia,
        ...overrides,
      };
      if (overrides.resolution_type === 'self_fix') {
        payload.status = 'resolved';
      }
      const res = await axios.post(`${API}/issues`, payload, { headers });
      const faultId = res.data?.id || res.data?.issue_id || 'N/A';
      const refNumber = `FLT-${faultId.slice(0, 8).toUpperCase()}`;
      setSuccessModal({ ref: refNumber });
      setShowFaultDialog(false);
      setFaultForm({ equipment_id: '', serial_number: '', machine_type: '', issue_description: '', severity: 'operational_minor', supplier: '', steps_taken: '', fault_code: null });
      setFaultMedia([]);
      setCoverage(null);
      loadData();
      // Notify Setup Checklist + analytics listeners that a fault landed.
      try { window.dispatchEvent(new CustomEvent('gymaxis:fault-logged', { detail: { id: faultId } })); } catch (_) {}
    } catch (err) {
      showFaultBanner({
        tone: 'error',
        title: 'Couldn\'t log the fault',
        detail: err?.response?.data?.detail || 'Please check your connection and try again. If the issue persists, contact support.',
      });
    }
    setSubmitting(false);
  };

  const compressImage = (file, maxWidth = 1920, quality = 0.8) => {
    return new Promise((resolve) => {
      if (!file.type.startsWith('image/')) { resolve(file); return; }
      const reader = new FileReader();
      reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
          const canvas = document.createElement('canvas');
          let { width, height } = img;
          if (width > maxWidth) { height = (height * maxWidth) / width; width = maxWidth; }
          canvas.width = width;
          canvas.height = height;
          canvas.getContext('2d').drawImage(img, 0, 0, width, height);
          canvas.toBlob((blob) => {
            if (blob && blob.size < file.size) {
              resolve(new File([blob], file.name, { type: 'image/jpeg' }));
            } else {
              resolve(file);
            }
          }, 'image/jpeg', quality);
        };
        img.src = e.target.result;
      };
      reader.readAsDataURL(file);
    });
  };

  const handleMediaUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    let uploadFile = file;
    if (file.type.startsWith('image/')) {
      uploadFile = await compressImage(file);
    }
    const formData = new FormData();
    formData.append('file', uploadFile);
    try {
      const res = await axios.post(`${API}/files/upload?category=fault-media`, formData, { headers });
      setFaultMedia(prev => [...prev, { url: res.data.download_url, type: file.type, name: file.name }]);
      notify.success(`${file.name} uploaded`);
    } catch { notify.error('Upload failed'); }
  };

  const fetchCoverage = async (equipId) => {
    try {
      const res = await axios.get(`${API}/equipment/${equipId}/coverage`, { headers });
      setCoverage(res.data);
    } catch { setCoverage(null); }
  };

  const selectEquipmentForFault = (eq) => {
    setFaultForm({
      ...faultForm,
      equipment_id: eq.id,
      serial_number: eq.serial_number || eq.name,
      machine_type: eq.equipment_type || '',
      supplier: eq.manufacturer || '',
    });
    fetchCoverage(eq.id);
    const existing = openFaults.filter(f => f.serial_number === (eq.serial_number || eq.name));
    if (existing.length > 0) {
      setDuplicateModal({ count: existing.length, machineName: eq.name });
    }
  };

  const handleDownloadFile = async (file) => {
    try {
      const res = await axios.get(`${API}/files/${file.id}`, { headers, responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = file.original_filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch { notify.error('Download failed'); }
  };

  const handleViewFile = async (file) => {
    try {
      const res = await axios.get(`${API}/files/${file.id}`, { headers, responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      window.open(url, '_blank');
    } catch { notify.error('Failed to open file'); }
  };

  const handleDeleteFile = async (file) => {
    const ok = await confirm({
      title: `Delete ${file.original_filename}?`,
      detail: 'This file will be permanently removed from the Documents library and cannot be recovered.',
      tone: 'danger',
      confirmLabel: 'Delete file',
    });
    if (!ok) return;
    try {
      await axios.delete(`${API}/files/${file.id}`, { headers });
      showDocBanner({ tone: 'success', title: 'Document deleted', detail: `"${file.original_filename}" has been removed.` });
      loadData();
    } catch {
      showDocBanner({ tone: 'error', title: 'Delete failed', detail: 'Something went wrong. Please try again, or contact support if the issue persists.' });
    }
  };

  const handleDocumentUpload = async (e, category = 'general') => {
    const file = e.target.files[0];
    if (!file) return;
    // Iter 216j — full Pulse documents restore. Allow every category
    // shown in the doc tab bar, including RAMS/SOPs/Compliance which the
    // user wants to upload for AI indexing.
    const catMap = {
      general: 'general',
      manuals: 'manuals',
      'service-certificates': 'service-certificates',
      certificates: 'certificates',
      contracts: 'contracts',
      'risk-assessments': 'risk-assessments',
      sops: 'sops',
      compliance: 'compliance',
      invoices: 'invoices',
      other: 'other',
    };
    const cat = catMap[category] || 'general';
    const formData = new FormData();
    formData.append('file', file);
    try {
      await axios.post(`${API}/files/upload?category=${cat}`, formData, {
        headers: { ...headers, 'Content-Type': 'multipart/form-data' },
      });
      showDocBanner({
        tone: 'success',
        title: 'Document uploaded',
        detail: `Added to ${category.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())} · ${file.name}`,
      });
      loadData();
    } catch {
      showDocBanner({
        tone: 'error',
        title: 'Upload failed',
        detail: 'The file couldn\'t be uploaded. Check the file size (max 25MB) and type, then try again.',
      });
    }
    e.target.value = '';
  };

  const handleUpdateIssueStatus = async (issueId, newStatus) => {
    try {
      await axios.patch(`${API}/issues/${issueId}`, { status: newStatus }, { headers });
      showFaultsTabBanner({
        tone: 'success',
        title: `Fault marked as ${newStatus.replace(/_/g, ' ')}`,
        detail: 'Status updated. The timeline has been logged for audit.',
      });
      loadData();
    } catch (err) {
      showFaultsTabBanner({
        tone: 'error',
        title: 'Couldn\'t update status',
        detail: err.response?.data?.detail || 'Please try again. If this keeps happening, contact support.',
      });
    }
  };

  const filteredEquipment = equipment.filter(e =>
    !search || e.name?.toLowerCase().includes(search.toLowerCase()) ||
    e.serial_number?.toLowerCase().includes(search.toLowerCase()) ||
    e.equipment_type?.toLowerCase().includes(search.toLowerCase())
  );

  const getEquipmentFiles = (eq) => files.filter(f =>
    f.equipment_id === eq.id || f.serial_number === eq.serial_number
  );

  const getEquipmentFaults = (eq) => issues.filter(i =>
    i.serial_number === (eq.serial_number || eq.name)
  );

  // User preference — identical to Memberships/CRM/Marketing modules
  // so toggling "Hide Start" in one module hides it everywhere.
  const [hideStart] = useUserPref('hideStartTabs', false);

  // Iter 216c — if Start auto-hides (all activation milestones fired) while
  // the user is sitting on it, snap them to the Dashboard tab so the
  // content area never shows a blank.
  useEffect(() => {
    if (hideStart && activeTab === 'start') setActiveTab('overview');
  }, [hideStart, activeTab]);

  // Build tabs based on role (mirrors Memberships structure — icon + label).
  const buildTabs = () => {
    const start = hideStart ? [] : [{ id: 'start', label: 'Start', icon: Sparkles }];
    const baseLite = [
      ...start,
      { id: 'overview',  label: 'Dashboard',  icon: LayoutDashboard },
      { id: 'equipment', label: 'Equipment',  icon: Dumbbell },
      { id: 'faults',    label: 'Faults',     icon: AlertTriangle },
      { id: 'documents', label: 'Documents',  icon: FileText },
    ];
    if (!isPro) return userRole === 'staff' ? baseLite : [...baseLite, { id: 'upgrade', label: 'Upgrade to Pro', icon: Rocket }];
    // Pulse Pro tab bar — Documents is reinstated per Iter 216i (operators
    // still need quick access to certifications, RAMS and supplier docs
    // without diving into Reports).
    const proBase = [
      ...start,
      { id: 'overview',     label: 'Dashboard',    icon: LayoutDashboard },
      { id: 'equipment',    label: 'Equipment',    icon: Dumbbell },
      { id: 'faults',       label: 'Faults',       icon: AlertTriangle },
      // Iter 216o-11 — labels match GymAxis exactly so the two portals
      // look identical to a customer comparing them side-by-side. The
      // underlying components stay separate (each is brand-tuned for
      // its portal); only the user-facing label is unified.
      { id: 'check-sheets', label: 'Check Sheets', icon: ClipboardCheck },
      { id: 'documents',    label: 'Documents',    icon: FileText },
      // Managers & owners see 'Staffing' (full workforce suite).
      // Staff see the same module labelled 'Gym Floor' (their limited
      // personal view) — enforced by StaffingConsole internally.
      (userRole === 'owner' || userRole === 'manager')
        ? { id: 'staffing', label: 'Staffing',    icon: Users }
        : { id: 'staffing', label: 'Gym Floor',   icon: ClipboardList },
    ];
    if (userRole === 'staff') return proBase;
    // Managers and Owners see everything (Weekly Digest lives inside Reports)
    return [
      ...proBase,
      { id: 'reports',    label: 'Reports',    icon: BarChart3 },
      { id: 'suppliers',  label: 'Suppliers',  icon: Truck },
      // Iter 216o-11 — Gym Layout label matches GymAxis exactly.
      { id: 'gym-layout', label: 'Gym Layout', icon: LayoutGrid },
    ];
  };
  const TABS = buildTabs();

  // Auto-scroll the active pill into view when tab changes (e.g. via bottom nav)
  React.useEffect(() => {
    if (!pulsePillBarRef.current) return;
    const active = pulsePillBarRef.current.querySelector(`[data-testid="mobile-pill-${activeTab}"]`);
    if (active) active.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
  }, [activeTab]);

  if (showMasterAdmin && user?.is_master_admin) {
    return <MasterAdminPage onBack={() => setShowMasterAdmin(false)} />;
  }

  return (
    <div className="min-h-screen overflow-x-hidden" style={{ background: 'var(--theme-bg)' }} data-testid="lite-dashboard" data-portal="pulse">
      <Navbar
        onOpenSettings={() => setShowSettingsDialog(true)}
        onOpenMasterAdmin={() => setShowMasterAdmin(true)}
        onStartTour={isPro ? () => { if (pulseTourRef.current) pulseTourRef.current.resetTour(); } : undefined}
      />

      {/* Admin viewing banner */}
      {isAdmin && (
        <div className="fixed top-20 left-0 right-0 z-40 bg-blue-600 text-white text-center py-1.5 text-xs font-medium flex items-center justify-center gap-2" data-testid="admin-pulse-banner">
          <Eye size={12} />
          <span>Viewing {adminView === 'lite' ? 'Pulse Self-Service (Lite)' : 'Pulse Self-Service Pro'} as Admin{adminDemoRole ? ` — ${adminDemoRole.charAt(0).toUpperCase() + adminDemoRole.slice(1)} View` : ''}</span>
          {adminView === 'lite' ? (
            <button onClick={() => navigate('/pulse?view=pro')} className="ml-2 underline hover:no-underline text-blue-100" data-testid="admin-switch-to-pro">
              Switch to Pro
            </button>
          ) : (
            <button onClick={() => navigate('/pulse?view=lite')} className="ml-2 underline hover:no-underline text-blue-100" data-testid="admin-switch-to-lite">
              Switch to Lite
            </button>
          )}
          <span className="text-blue-200">|</span>
          <button onClick={() => navigate('/dashboard')} className="underline hover:no-underline text-blue-100" data-testid="admin-back-to-gymaxis">
            Back to Admin Console
          </button>
        </div>
      )}

      <div className={`${isAdmin ? 'pt-32' : 'pt-24'} pb-12 module-fade-in`}>
        <PullToRefresh onRefresh={async () => { await loadData(); }}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          {/* Dashboard Header */}
          <div className="mb-6" data-testid="pulse-dashboard-header">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <h1 className="text-3xl sm:text-4xl tracking-tight font-semibold mb-1 pulse-font-heading leading-tight" style={{ color: 'var(--theme-text)' }}>
                  Pulse Fitness {isPro && <span className="text-[var(--color-brand-cyan-hover)]">Pro</span>}
                  {user?.company_name && (
                    <span className="text-base sm:text-lg font-normal ml-2 pulse-font-body" style={{ color: 'var(--theme-text-muted)' }}>
                      · {allSitesActive ? 'All Sites' : (activeSite?.name || user.company_name)}
                    </span>
                  )}
                </h1>
                <p className="pulse-font-body mb-3" style={{ color: 'var(--theme-text-muted)' }}>Welcome back, {user?.full_name}</p>
              </div>
              <div className="flex items-center gap-3 shrink-0 mt-1.5">
                {/* Iter 216i — site switcher (multi-site Pulse Pro only).
                    Hidden automatically by the component when sites.length<2. */}
                {isPro && (userRole === 'owner' || userRole === 'manager') ? (
                  <SiteSwitcher
                    onAllSites={() => setAllSitesActive(true)}
                    onPickSite={() => setAllSitesActive(false)}
                    allSitesActive={allSitesActive}
                  />
                ) : null}
                <div className="text-sm pulse-font-body" style={{ color: 'var(--theme-text-muted)' }} data-testid="module-today-date">
                  {new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
                </div>
              </div>
            </div>
            <ModuleSwitcher user={user} current="operations" />
          </div>

          <CrossModuleTipsBanner mode="operations" />

          {/* Iter 238c — operator-facing 3-day Pro upgrade CTA. Shows
              for `account_type='lite'` only and disappears once the
              org upgrades. One click starts trials of all three
              bolt-ons. */}
          <PulseProUpgradeCta />

          {/* Proactive nudges surfaced to owners/managers */}
          <NudgeBanner canDismiss={userRole === 'owner' || userRole === 'manager'} />

          {/* Iter 216i — All-Sites overview short-circuits the per-site
              tabs when an owner/manager picks "All sites" from the
              switcher. Picking a single site (via the leaderboard or
              the switcher) drops back into the normal tab view. */}
          {allSitesActive ? (
            <AllSitesOverview onPickSite={() => setAllSitesActive(false)} />
          ) : (
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            {/* Desktop tab bar — canonical PillTabBar so overflow
                auto-scrolls the active tab into view (fixing last
                options being hidden behind the rounded border). */}
            <PillTabBar
              className="mb-6 w-full hidden md:block"
              activeId={activeTab}
              testId="pulse-dashboard-tabs"
              ariaLabel="Operations sections"
            >
              {TABS.map(tab => {
                const Icon = tab.icon;
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    data-pill-id={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className="flex-shrink-0 inline-flex items-center gap-2 px-4 py-2.5 rounded-full text-sm font-semibold transition-colors whitespace-nowrap"
                    style={isActive
                      ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
                      : { color: 'var(--theme-text-muted)', background: 'transparent' }}
                    data-testid={`lite-tab-${tab.id}`}
                  >
                    {Icon && <Icon size={14} />} {tab.label}
                  </button>
                );
              })}
            </PillTabBar>

            {/* Mobile: scrollable pill tabs — identical to Memberships console */}
            <div ref={pulsePillBarRef} className="md:hidden mb-5 flex gap-2 overflow-x-auto scrollbar-hide pb-1 -mx-1 px-1" style={{ WebkitOverflowScrolling: 'touch' }} data-testid="mobile-tab-pills">
              {TABS.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className="flex-shrink-0 px-4 py-2 rounded-full text-xs font-medium whitespace-nowrap transition-colors"
                  style={activeTab === tab.id
                    ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
                    : { color: 'var(--theme-text-muted)', background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}
                  data-testid={`mobile-pill-${tab.id}`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Start Tab — guided onboarding for first-time staff. */}
            {!hideStart && (
              <TabsContent value="start" data-testid="start-content">
                <OperationsStartTab
                  setTab={setActiveTab}
                  onLogFault={() => setShowFaultDialog(true)}
                  onOpenEquipmentImport={() => setShowOnboarding(true)}
                />
              </TabsContent>
            )}

            {/* Overview Tab */}
            <TabsContent value="overview" data-testid="overview-content">
              <LiteOverviewTab
                equipment={equipment}
                openFaults={openFaults}
                operational={operational}
                outOfOrder={outOfOrder}
                onLogFault={() => { setActiveTab('faults'); setShowFaultDialog(true); }}
                onViewFault={(f) => { setActiveTab('faults'); setSelectedIssue(f); }}
                getSeverityStyle={getSeverityStyle}
                getSeverityLabel={getSeverityLabel}
              />
            </TabsContent>

            {/* Equipment Tab */}
            <TabsContent value="equipment" data-testid="equipment-content">
              <LiteEquipmentTab
                filteredEquipment={filteredEquipment}
                search={search}
                onSearchChange={setSearch}
                getEquipmentFaults={getEquipmentFaults}
                onSelectEquipment={setSelectedEquipment}
                onEquipmentUpdated={loadData}
                onAddEquipment={() => setShowAddEquipment(true)}
              />
            </TabsContent>

            {/* Faults Tab */}
            <TabsContent value="faults" data-testid="faults-content">
              {faultsTabBanner && <div className="mb-3">{faultsTabBanner}</div>}
              <LiteFaultsTab
                filteredIssues={filteredIssues}
                faultFilterStatus={faultFilterStatus}
                faultFilterSeverity={faultFilterSeverity}
                selectedIssue={selectedIssue}
                onSelectIssue={setSelectedIssue}
                onLogFault={() => setShowFaultDialog(true)}
                onFilterStatus={setFaultFilterStatus}
                onFilterSeverity={setFaultFilterSeverity}
                onUpdateIssueStatus={handleUpdateIssueStatus}
                suppliers={suppliers}
                getSeverityStyle={getSeverityStyle}
                getSeverityLabel={getSeverityLabel}
                getStatusColor={getStatusColor}
              />
            </TabsContent>

            {/* Documents Tab — Iter 216j: re-enabled for Pulse Pro so
                operators can upload all manuals for AI indexing. */}
            <TabsContent value="documents" data-testid="documents-content">
              {docBanner && <div className="mb-3">{docBanner}</div>}
              <LiteDocumentsTab
                  files={files.filter(f => f.category !== 'floor-plans' && f.category !== 'fault-media')}
                  onUpload={handleDocumentUpload}
                  onView={handleViewFile}
                  onDownload={handleDownloadFile}
                  onDelete={handleDeleteFile}
                  isPro={isPro}
                />
              </TabsContent>

            {/* Pro Tabs */}
            {isPro && (
              <TabsContent value="check-sheets" data-testid="check-sheets-content">
                <PulseCheckSheetsTab equipment={equipment} />
              </TabsContent>
            )}
            {isPro && (userRole === 'manager' || userRole === 'owner') && (
              <TabsContent value="reports" data-testid="reports-content">
                <PulseReportsTab />
              </TabsContent>
            )}
            {isPro && (userRole === 'manager' || userRole === 'owner') && (
              <TabsContent value="gym-layout" data-testid="gym-layout-content">
                <PulseGymLayoutTab />
              </TabsContent>
            )}
            {isPro && (
              <TabsContent value="staffing" data-testid="staffing-content">
                <StaffingConsole />
              </TabsContent>
            )}
            {isPro && (
              <TabsContent value="gym-floor" data-testid="gym-floor-content">
                <GymFloorManagerTab />
              </TabsContent>
            )}
            {isPro && (userRole === 'manager' || userRole === 'owner') && (
              <TabsContent value="suppliers" data-testid="suppliers-content">
                <SupplierDashboardTab />
              </TabsContent>
            )}
            {!isPro && (
              <TabsContent value="upgrade" data-testid="upgrade-content">
                <PulseUpgradePage onDismiss={() => setActiveTab('overview')} />
              </TabsContent>
            )}
          </Tabs>
          )}
        </div>
        </PullToRefresh>
      </div>

      {/* Settings Dialog */}
      <Dialog open={showSettingsDialog} onOpenChange={setShowSettingsDialog}>
        <DialogContent className="border max-w-4xl max-h-[90vh] overflow-y-auto" style={{ background: 'var(--theme-surface)', color: 'var(--theme-text)', borderColor: 'var(--theme-border)' }} data-testid="pulse-settings-dialog">
          <DialogHeader>
            <DialogTitle className="text-xl" style={{ color: 'var(--theme-text)' }}>Settings</DialogTitle>
          </DialogHeader>
          <PulseSettingsTab />
        </DialogContent>
      </Dialog>

      {/* Onboarding Wizard (Pro users, skip logo step) */}
      <OnboardingWizard open={showOnboarding} onClose={() => setShowOnboarding(false)} onComplete={loadData} skipLogo={true} />
      <AddEquipmentDialog
        open={showAddEquipment}
        onClose={() => setShowAddEquipment(false)}
        onCreated={() => loadData()}
      />

      {/* All Dialogs: Equipment Detail, Log Fault, Duplicate, Success */}
      <LiteDialogs
        selectedEquipment={selectedEquipment}
        onCloseEquipment={() => setSelectedEquipment(null)}
        getEquipmentFaults={getEquipmentFaults}
        getEquipmentFiles={getEquipmentFiles}
        onDownloadFile={handleDownloadFile}
        onLogFaultForEquipment={(eq) => { setSelectedEquipment(null); selectEquipmentForFault(eq); setActiveTab('faults'); setShowFaultDialog(true); }}
        getSeverityStyle={getSeverityStyle}
        getSeverityLabel={getSeverityLabel}
        getStatusColor={getStatusColor}
        showFaultDialog={showFaultDialog}
        onCloseFaultDialog={setShowFaultDialog}
        equipment={equipment}
        faultForm={faultForm}
        setFaultForm={setFaultForm}
        selectEquipmentForFault={selectEquipmentForFault}
        coverage={coverage}
        faultMedia={faultMedia}
        onMediaUpload={handleMediaUpload}
        onRemoveMedia={(i) => setFaultMedia(faultMedia.filter((_, j) => j !== i))}
        onFaultSubmit={handleFaultSubmit}
        submitting={submitting}
        faultBanner={faultBanner}
        SEVERITY_OPTIONS={SEVERITY_OPTIONS}
        duplicateModal={duplicateModal}
        onDuplicateCancel={() => {
          // Cancel: close duplicate modal, close fault dialog, return to equipment detail
          const eq = equipment.find(e => e.id === faultForm.equipment_id);
          setDuplicateModal(null);
          setShowFaultDialog(false);
          setFaultForm({ equipment_id: '', serial_number: '', machine_type: '', issue_description: '', severity: 'operational_minor', supplier: '', fault_code: null });
          setCoverage(null);
          if (eq) setSelectedEquipment(eq);
        }}
        onDuplicateContinue={() => {
          // Continue: close duplicate modal, keep fault dialog open for user to fill in
          setDuplicateModal(null);
        }}
        successModal={successModal}
        onSuccessDismiss={() => { setSuccessModal(null); setActiveTab('faults'); window.scrollTo({ top: 0, behavior: 'smooth' }); }}
        isPro={isPro}
        headers={headers}
      />

      {/* Mobile Bottom Navigation */}
      <MobileBottomNav
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onReportFault={() => { setActiveTab('faults'); setShowFaultDialog(true); }}
        variant="pulse"
        isPro={isPro}
      />

      {/* Bottom spacer for mobile nav */}
      <div className="h-20 md:hidden" />

      {/* Floating Document Q&A for Pro users */}
      {isPro && activeTab !== 'documents' && <DocumentQA />}

      {/* Interactive Product Tour (Pro users only) */}
      {isPro && <ProductTour variant="pulse" ref={pulseTourRef} />}
    </div>
  );
};

export default LiteDashboardPage;
