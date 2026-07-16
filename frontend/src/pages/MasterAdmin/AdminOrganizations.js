import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
 Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetClose } from '@/components/ui/sheet';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem,
} from '@/components/ui/dropdown-menu';
import {
 Building2, Search, Shield, Users, X, Plus, Save, Loader2, UserPlus, Archive, Edit2, Mail,
 CheckCircle2, AlertTriangle, ShieldCheck, Trash2, AlertCircle, Copy, Wrench, Calendar, Megaphone, MoreHorizontal, Undo2, KeyRound, LockOpen, Crown,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { useBackGestureClose } from '@/lib/useBackGestureClose';
import AddressFields from '@/components/shared/AddressFields';
import CompanyAutocomplete from '@/components/shared/CompanyAutocomplete';
import OrgIntegrationsTab from './OrgIntegrationsTab';

// Iter 216bg — module-scope API base for the user-credentials side-drawer
// handlers (Reset Link, Temp Password). Several inner onClick handlers
// elsewhere in this file declare their own `const API = ...` shadow,
// but the credentials drawer was missing one — silently throwing a
// ReferenceError that the catch surfaced as the misleading
// "Network unreachable" toast.
const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// ── Iter 215ar — module checkbox grid + reveal-password helpers ─────
// Iter 216f — colour values are intentionally hex literals here because
// they're consumed as inline `style={{color}}` props on `<Icon>` components
// (lucide-react doesn't accept CSS vars in its `color` prop). The
// inline hex values below are intentional for icon coloring only.
const MODULE_OPTIONS = [
  { id: 'operations',  label: 'Operations',  icon: Wrench,    color: '#06B6D4' },
  { id: 'crm',         label: 'CRM',         icon: Users,     color: '#6366F1' },
  { id: 'memberships', label: 'Memberships', icon: Calendar,  color: '#8B5CF6' },
  { id: 'marketing',   label: 'Marketing',   icon: Megaphone, color: '#D946EF' },
];

const modulesFromPortalType = (pt) => {
  if (pt === 'crm') return ['crm'];
  if (pt === 'both') return ['operations', 'crm'];
  return ['operations'];
};

// MOD orgs run ONLY the MOD Operations portal (no CRM/memberships/marketing/etc).
const isModAccount = (at) => ['mod_site', 'mod_branch', 'mod_org'].includes(at);
// Industry is derived from the MOD service/force so the record self-describes.
const MOD_FORCE_INDUSTRY = {
  army: 'Defence — British Army',
  raf: 'Defence — Royal Air Force',
  navy: 'Defence — Royal Navy',
};

/** Six-checkbox module picker. Always keeps at least one module selected. */
const ModulesPicker = ({ value, onChange, testIdPrefix = 'org-modules', isLite = false }) => {
  const selected = Array.isArray(value) && value.length ? value : modulesFromPortalType(value);
  const toggle = (id) => {
    if (isLite && id !== 'operations') return; // bolt-ons are Pro-only
    const next = selected.includes(id) ? selected.filter((m) => m !== id) : [...selected, id];
    onChange(next.length ? next : [id]); // never let the set go empty
  };
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mt-1" data-testid={testIdPrefix}>
      {MODULE_OPTIONS.map((m) => {
        const Icon = m.icon;
        const locked = isLite && m.id !== 'operations';
        const on = selected.includes(m.id) && !locked;
        return (
          <button
            type="button"
            key={m.id}
            onClick={() => toggle(m.id)}
            disabled={locked}
            title={locked ? 'Available on Pro — upgrade this org to enable' : undefined}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm font-medium transition-all ${
              locked
                ? 'bg-zinc-50 border-zinc-200 text-zinc-400 cursor-not-allowed'
                : on
                ? 'bg-white border-zinc-900 text-zinc-900 shadow-sm ring-1 ring-zinc-900'
                : 'bg-white border-zinc-200 text-zinc-500 hover:border-zinc-300'
            }`}
            data-testid={`${testIdPrefix}-${m.id}`}
            aria-pressed={on}
          >
            <span
              className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${
                on ? 'border-zinc-900' : 'border-zinc-300'
              }`}
              style={on ? { background: m.color, borderColor: m.color } : {}}
            >
              {on && <CheckCircle2 size={12} className="text-white" strokeWidth={3} />}
            </span>
            <Icon size={14} style={{ color: locked ? '#a1a1aa' : m.color }} />
            <span>{m.label}</span>
            {locked && <span className="ml-auto text-[9px] font-bold px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">PRO</span>}
          </button>
        );
      })}
    </div>
  );
};

/** Primary contact login — Iter 215ev refactor. *
 *  REMOVED: the "Reveal password" pattern (admin could see plaintext).
 *  REPLACED with a secure invite-link flow — master-admin clicks "Issue
 *  invite link" → backend mints a 72h signed token → admin copies the
 *  URL and sends manually (WhatsApp, own email, Slack) or waits for
 *  Resend DNS verification to auto-deliver. User sets their own
 *  password on arrival. Admin never handles plaintext.
 */
const PrimaryContactPasswordReveal = ({ _orgId, primaryContactEmail, primaryContactUserId }) => {
  const [loading, setLoading] = useState(false);
  const [invite, setInvite] = useState(null); // {invite_url, expires_at, email}
  const [error, setError] = useState('');

  const issue = async () => {
    if (!primaryContactUserId) {
      setError('Primary contact not provisioned yet — set the email and save.');
      return;
    }
    setLoading(true); setError('');
    try {
      const API = process.env.REACT_APP_BACKEND_URL;
      const token = localStorage.getItem('token');
      const res = await axios.post(
        `${API}/api/master-admin/users/${primaryContactUserId}/invite-link`,
        {},
        { headers: { Authorization: `Bearer ${token}` } },
      );
      setInvite(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not generate invite link');
    } finally {
      setLoading(false);
    }
  };

  const copy = async () => {
    if (!invite?.invite_url) return;
    try { await navigator.clipboard.writeText(invite.invite_url); notify.success('Copied to clipboard'); }
    catch { notify.error('Copy failed'); }
  };

  return (
    <div className="mt-2 rounded-md border border-zinc-200 bg-zinc-50/60 px-3 py-2" data-testid="org-edit-primary-credentials">
      <div className="flex items-center justify-between gap-2">
        <div className="text-[11px] uppercase tracking-wider text-zinc-500 font-semibold">
          Primary contact login
        </div>
        <button
          type="button"
          onClick={issue}
          disabled={loading || !primaryContactEmail}
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-zinc-700 hover:text-zinc-900 disabled:opacity-50"
          data-testid="org-edit-issue-invite-btn"
        >
          {loading ? <Loader2 size={12} className="animate-spin" /> : <KeyRound size={13} />}
          {invite ? 'Re-issue invite link' : 'Issue invite link'}
        </button>
      </div>
      {error && <p className="text-[11px] text-rose-600 mt-1">{error}</p>}
      {!primaryContactEmail && <p className="text-[11px] text-zinc-400 italic mt-1">Set a primary contact email above to enable.</p>}
      {invite?.invite_url && (
        <div className="mt-2 space-y-1.5 text-xs text-zinc-700">
          <div className="flex items-center gap-2">
            <span className="text-zinc-500">Email:</span>
            <span className="font-mono text-zinc-900">{invite.email || primaryContactEmail}</span>
          </div>
          <div className="flex items-center gap-2">
            <Input readOnly value={invite.invite_url} className="bg-white font-mono text-[11px] h-7 flex-1" data-testid="org-edit-invite-url-value" />
            <button type="button" onClick={copy} className="shrink-0 inline-flex items-center gap-1 rounded-md border border-zinc-300 bg-white hover:bg-zinc-50 px-2.5 py-1 text-[11px] font-bold text-zinc-700" data-testid="org-edit-copy-invite-btn">
              <Copy size={11} /> Copy
            </button>
          </div>
          <p className="text-[11px] text-zinc-500 flex items-center gap-1.5">
            <ShieldCheck size={11} className="text-emerald-600" />
            Single-use · 72h expiry · user sets own password · admin never sees plaintext.
          </p>
        </div>
      )}
      {!invite && primaryContactEmail && (
        <p className="text-[11px] text-zinc-400 mt-1">
          Generate a single-use set-password link to copy-paste to the user.
        </p>
      )}
    </div>
  );
};

import FeatureControlPanel from './FeatureControlPanel';
import OrgSitesPanel from './OrgSitesPanel';
import { OrgRowSkeleton } from '@/components/shared/Skeleton';

/**
 * Iter 215au — Audit tab content for the Org Manage drawer.
 *
 * Fetches the last 30 days of audit events filtered by organization_id
 * from /api/master-admin/audit-log. Read-only, lightweight, lazy-loaded
 * the moment the tab is selected.
 */
const OrgAuditLogTab = ({ orgId }) => {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (loaded || !orgId) return;
    const run = async () => {
      setLoading(true); setError('');
      try {
        const API = process.env.REACT_APP_BACKEND_URL;
        const token = localStorage.getItem('token');
        const res = await axios.get(
          `${API}/api/master-admin/audit-log?organization_id=${orgId}&since_days=30&limit=50`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        setEvents(res.data?.events || []);
        setLoaded(true);
      } catch (e) {
        setError(e?.response?.data?.detail || 'Could not load audit events');
      } finally {
        setLoading(false);
      }
    };
    run();
  }, [orgId, loaded]);

  if (loading) {
    return (
      <div className="py-10 flex items-center justify-center text-zinc-400" data-testid="org-audit-loading">
        <Loader2 size={16} className="animate-spin mr-2" /> Loading audit events…
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700" data-testid="org-audit-error">
        {error}
      </div>
    );
  }
  if (!events.length) {
    return (
      <div className="text-sm text-zinc-400 py-8 text-center" data-testid="org-audit-empty">
        No audit events for this organisation in the last 30 days.
      </div>
    );
  }
  return (
    <div className="space-y-2" data-testid="org-audit-list">
      {events.map((e, idx) => {
        const key = `${e.timestamp || e.created_at || idx}-${e.kind || e.action || idx}`;
        const when = (e.timestamp || e.created_at || '').replace('T', ' ').slice(0, 16);
        const summary = e.summary || e.description || (typeof e.details === 'string' ? e.details : '') || '';
        const actor = e.actor_email || e.user_email || (e.actor_type === 'system' ? 'system' : '');
        return (
          <div key={key} className="rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm" data-testid={`org-audit-event-${idx}`}>
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold text-zinc-900 text-[13px]">{e.kind || e.action || 'event'}</span>
              <span className="text-[11px] text-zinc-400">{when}</span>
            </div>
            {summary && <p className="text-[12px] text-zinc-600 mt-0.5">{summary}</p>}
            {actor && (
              <p className="text-[11px] text-zinc-400 mt-0.5">by {actor}</p>
            )}
          </div>
        );
      })}
    </div>
  );
};

// ── Type-to-confirm hard-delete modal ─────────────────────────────────
const HardDeleteUserDialog = ({ open, user, onClose, onConfirm }) => {
 const [typed, setTyped] = useState('');
 const [busy, setBusy] = useState(false);
 useEffect(() => { setTyped(''); setBusy(false); }, [user?.id, open]);
 if (!open || !user) return null;
 const matches = typed.trim().toLowerCase() === (user.email || '').toLowerCase();
 return (
 <Dialog open={open} onOpenChange={(o) => !o && !busy && onClose()}>
 <DialogContent className="sm:max-w-md bg-white border-red-200" data-testid="hard-delete-user-dialog">
 <DialogHeader>
 <DialogTitle className="flex items-center gap-2 text-red-700">
 <AlertCircle size={18} /> Permanently delete user
 </DialogTitle>
 </DialogHeader>
 <div className="space-y-3 text-sm text-zinc-700">
 <p>This will <strong>permanently delete</strong> <span className="font-mono">{user.email}</span> and cascade-remove their personal data (issues, notes, files, audit entries, sessions, MFA secrets, API keys).</p>
 <p className="text-red-600 font-medium">This action cannot be undone.</p>
 <div className="space-y-1">
 <Label className="text-xs text-zinc-600">Type the user's email to confirm:</Label>
 <Input
 value={typed}
 onChange={(e) => setTyped(e.target.value)}
 placeholder={user.email}
 autoComplete="off"
 autoFocus
 data-testid="hard-delete-confirm-input"
 />
 </div>
 </div>
 <div className="flex justify-end gap-2 mt-2">
 <Button variant="outline" onClick={onClose} disabled={busy} data-testid="hard-delete-cancel">Cancel</Button>
 <Button
 onClick={async () => {
 setBusy(true);
 const ok = await onConfirm(user.id, typed.trim());
 setBusy(false);
 if (ok) onClose();
 }}
 disabled={!matches || busy}
 className="bg-red-600 text-white hover:bg-red-700 disabled:bg-zinc-300"
 data-testid="hard-delete-confirm-btn"
 >
 {busy ? <Loader2 size={14} className="mr-1 animate-spin" /> : <Trash2 size={14} className="mr-1" />}
 Delete permanently
 </Button>
 </div>
 </DialogContent>
 </Dialog>
 );
};

const STATUS_STYLES = {
 active: 'bg-emerald-50 text-emerald-700 border-emerald-200',
 trial: 'bg-blue-50 text-blue-700 border-blue-200',
 suspended: 'bg-amber-50 text-amber-700 border-amber-200',
 cancelled: 'bg-red-50 text-red-700 border-red-200',
 archived: 'bg-zinc-200 text-zinc-500 border-zinc-300',
};

// Coloured left-border tint per org status — visual rhythm recommended in design review
const STATUS_BORDER = {
 active: 'border-l-[3px] border-l-emerald-400',
 trial: 'border-l-[3px] border-l-blue-500',
 suspended: 'border-l-[3px] border-l-amber-500',
 cancelled: 'border-l-[3px] border-l-red-500',
 archived: 'border-l-[3px] border-l-zinc-300',
};

const TIER_STYLES = {
 free: 'bg-zinc-100 text-zinc-600',
 starter: 'bg-zinc-100 text-zinc-600',
 pro: 'bg-blue-50 text-blue-700',
 professional: 'bg-blue-50 text-blue-700',
 premium: 'bg-amber-50 text-amber-700',
 enterprise: 'bg-violet-50 text-violet-700',
 lite: 'bg-sky-50 text-sky-700',
 pulse_pro: 'bg-blue-50 text-blue-700',
};

const _PORTAL_STYLES = {
 service_portal: 'bg-blue-50 text-blue-700 border-blue-200',
 crm: 'bg-emerald-50 text-emerald-700 border-emerald-200',
 both: 'bg-purple-50 text-purple-700 border-purple-200',
};

const _PORTAL_LABELS = { service_portal: 'Operations Portal', crm: 'CRM', both: 'Both' };

const ACCOUNT_TYPE_STYLES = {
 full: 'bg-indigo-50 text-indigo-700 border-indigo-200 font-medium',
 pulse_pro: 'bg-blue-50 text-blue-700 border-blue-200 font-medium',
 lite: 'bg-sky-50 text-sky-700 border-sky-200 font-medium',
 partner_engineer: 'bg-amber-50 text-amber-700 border-amber-200 font-medium',
};
const ACCOUNT_TYPE_LABELS = { full: 'Pulse Fitness', pulse_pro: 'Pulse Pro', lite: 'Pulse Lite', partner_engineer: 'Independent Engineer' };

const _FEATURE_LIST = [
 { key: 'ai_audits', label: 'AI Audits', group: 'portal' },
 { key: 'qr_scanning', label: 'QR Scanning', group: 'portal' },
 { key: 'multi_site', label: 'Multi-Site', group: 'portal' },
 { key: 'ppm_engine', label: 'PPM Scheduling', group: 'portal' },
 { key: 'api_access', label: 'API Access', group: 'general' },
 { key: 'white_label', label: 'White Label', group: 'general' },
 { key: 'crm_pipeline', label: 'Pipeline', group: 'crm' },
 { key: 'crm_quotes', label: 'Quotes / CPQ', group: 'crm' },
 { key: 'crm_tenders', label: 'Tenders', group: 'crm' },
 { key: 'crm_ai_tools', label: 'AI Tools', group: 'crm' },
 { key: 'crm_workflows', label: 'Workflows', group: 'crm' },
 { key: 'crm_documents', label: 'Documents', group: 'crm' },
 // Pulse Fitness Enterprise — off by default for Pulse accounts, on by default for Pulse Fitness
 { key: 'kpi_engine', label: 'KPI / Performance Engine', group: 'enterprise' },
 { key: 'sicon_integration', label: 'Sicon Integration', group: 'enterprise' },
 { key: 'sage_integration', label: 'Sage 200 Integration', group: 'enterprise' },
];

const EMPLOYEE_RANGES = ['1-10', '11-50', '51-200', '201-500', '501-1000', '1000+'];
const INDUSTRY_OPTIONS = [
 'Fitness & Leisure', 'Healthcare', 'Manufacturing', 'Technology', 'Retail',
 'Construction', 'Education', 'Finance', 'Hospitality', 'Property', 'Other'
];

const AdminOrganizations = ({
 filteredOrgs, search, onSearchChange,
 orgFilter, onOrgFilterChange,
 accountTypeFilter, onAccountTypeFilterChange,
 onUpdateTier, onUpdateStatus, _onUpdateAccountType,
 onToggleTest, _onSetFeatures, onSelectOrg, selectedOrg,
 users = [], _onImpersonate, onResetPassword, onDisableUser, onUnlockUser,
 onUpdateFeatures, onCreateOrg, onAddUserToOrg, portalFilter, onArchiveUser, onHardDeleteUser,
 onEditUser, onSendEmailPreview, accountTypesIn, onReloadOrgs,
}) => {
 const [expandedOrg, setExpandedOrg] = useState(null);
 const [expandedView, setExpandedView] = useState('users');
 const [showCreateOrg, setShowCreateOrg] = useState(false);
 const [creating, setCreating] = useState(false);
 const [orgForm, setOrgForm] = useState({ name: '', portal_type: 'service_portal', enabled_modules: ['operations'], account_type: 'full', subscription_tier: 'starter', industry: '', employee_count: '', website: '', phone: '', address: '', address_line1: '', address_line2: '', address_line3: '', city: '', county: '', postcode: '', country: 'United Kingdom', primary_contact_name: '', primary_contact_email: '', primary_contact_phone: '', notes: '' });
 const [showAddUser, setShowAddUser] = useState(null);
 // Iter 222 — assigning "Master Admin" to a user in a Pulse org makes
 // them a Pulse Master Admin (data-scoped), not a full platform admin.
 const isPulseOrg = ['pulse_pro', 'pulse_lite', 'pulse'].includes(selectedOrg?.account_type)
   || ['pulse', 'pulse_fitness'].includes((selectedOrg?.brand || '').toLowerCase());
 const masterAdminRoleLabel = isPulseOrg ? 'Master Admin (Pulse)' : 'Master Admin (full platform)';
 const [addingUser, setAddingUser] = useState(false);
 const [userForm, setUserForm] = useState({ email: '', full_name: '', password: '', role: 'staff', module_overrides: {} });
 const [lastInvite, setLastInvite] = useState(null); // Iter 215ev — post-create invite link panel
 const [editingOrg, setEditingOrg] = useState(null);
 const [savingEdit, setSavingEdit] = useState(false);
 const [editingUser, setEditingUser] = useState(null);
 const [savingUser, setSavingUser] = useState(false);
 // Iter 215bi — temp password from in-dialog reset, surfaced inline.
 const [lastResetTempPw, setLastResetTempPw] = useState(null);
 const [lastInviteUrl, setLastInviteUrl] = useState(null);
// Iter 216h16 — sites listing for the user-edit drawer's site allocation block.
const [editUserSites, setEditUserSites] = useState([]);
const [editUserSitesLoading, setEditUserSitesLoading] = useState(false);

 // Iter 215bh — module filter (filters by enabled_modules array on org).

// Iter 216h16 — when the user-edit drawer opens, fetch the parent
// org's sites so the operator can pin the user to a subset of sites
// (mirrors the owner-side Team & Roles chip selector).
useEffect(() => {
  if (!editingUser?.organization_id) { setEditUserSites([]); return undefined; }
  let cancelled = false;
  (async () => {
    setEditUserSitesLoading(true);
    try {
      const tk = localStorage.getItem('token');
      const r = await axios.get(
        `${API}/master-admin/organizations/${editingUser.organization_id}/sites`,
        { headers: { Authorization: `Bearer ${tk}` } },
      );
      if (!cancelled) setEditUserSites(r.data?.sites || []);
    } catch {
      if (!cancelled) setEditUserSites([]);
    }
    if (!cancelled) setEditUserSitesLoading(false);
  })();
  return () => { cancelled = true; };
}, [editingUser?.organization_id]);

 const [moduleFilter, setModuleFilter] = useState('all');
 const [hqFilter, setHqFilter] = useState(false);

 // Iter 215au — when ⌘K (CommandPalette) selects an org, the parent
 // sets `selectedOrg`; we open the drawer for that org automatically.
 // Iter 216f — also support ?expand=<orgId>&view=users URL param so the
 // onboarding success screen can deep-link straight to "Add user" tab.
 useEffect(() => {
   try {
     const params = new URLSearchParams(window.location.search);
     const expand = params.get('expand');
     const view = params.get('view');
     if (expand) {
       setExpandedOrg(expand);
       if (view) setExpandedView(view);
       // Strip the params so refresh doesn't re-trigger.
       window.history.replaceState({}, '', window.location.pathname);
     }
   } catch { /* noop */ }
 }, []);

 /* Iter 216f — back-gesture handler.
    The org-detail panel is a Sheet (not a route), so a browser back
    gesture would pop the user all the way out of the Master Admin
    page (Lee's prod report). Use the shared `useBackGestureClose`
    hook so this pattern stays consistent across every modal in the
    app — see `lib/useBackGestureClose.js`. */
 const closeOrgPanel = useCallback(() => {
   setExpandedOrg(null);
   setEditingOrg(null);
 }, [setExpandedOrg, setEditingOrg]);
 useBackGestureClose(!!expandedOrg, closeOrgPanel, 'gymaxis-org-panel');
 useEffect(() => {
   if (selectedOrg && selectedOrg.id) {
     // Initialise the editing form from the selected org so the Details
     // tab loads instantly (mirrors openEditOrg without forward-reffing it).
     setEditingOrg({
       id: selectedOrg.id,
       name: selectedOrg.name || '',
       industry: selectedOrg.industry || '',
       employee_count: selectedOrg.employee_count || '',
       website: selectedOrg.website || '',
       phone: selectedOrg.phone || '',
       address: selectedOrg.address || '',
       address_line1: selectedOrg.address_line1 || selectedOrg.address || '',
       address_line2: selectedOrg.address_line2 || '',
       address_line3: selectedOrg.address_line3 || '',
       city: selectedOrg.city || '',
       county: selectedOrg.county || '',
       postcode: selectedOrg.postcode || '',
       country: selectedOrg.country || 'United Kingdom',
       portal_type: selectedOrg.portal_type || 'service_portal',
       enabled_modules: selectedOrg.enabled_modules || [],
       primary_contact_name: selectedOrg.primary_contact_name || '',
       primary_contact_email: selectedOrg.primary_contact_email || '',
       primary_contact_phone: selectedOrg.primary_contact_phone || '',
       notes: selectedOrg.notes || '',
       customer_account_number: selectedOrg.customer_account_number || '',
       sage_customer_number: selectedOrg.sage_customer_number || '',
     });
     setExpandedOrg(selectedOrg.id);
     setExpandedView('details');
     // Clear the parent's selectedOrg so the next selection retriggers.
     if (onSelectOrg) onSelectOrg(null);
   }
   // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
 }, [selectedOrg]);
 const [hardDeleteTarget, setHardDeleteTarget] = useState(null);
 const [emailPreviewOrg, setEmailPreviewOrg] = useState(null);
 const [emailPreviewTo, setEmailPreviewTo] = useState('');
 const [emailPreviewKind, setEmailPreviewKind] = useState('comment');
 const [sendingPreview, setSendingPreview] = useState(false);
 const [verifyResult, setVerifyResult] = useState(null);
 const [verifyBusy, setVerifyBusy] = useState(false);
 const [moduleStatus, setModuleStatus] = useState({});
 // Iter 215as · QW#4 — inline "Saved HH:MM" chip after Org details save
 // so the user gets visible confirmation without the page reloading.
 const [savedAt, setSavedAt] = useState(null);
 const [saveError, setSaveError] = useState('');
 // Iter 215as · QW#5 — Archive Undo: when an org is just archived from
 // this view we keep its previous status in state for 5s so the bottom
 // banner can offer a one-click revert.
 const [archivedToast, setArchivedToast] = useState(null);
 // Iter 215at — bulk-select on the org list. Holds the ids of currently-
 // checked org rows. Bulk actions bar appears at the top while > 0.
 const [selectedIds, setSelectedIds] = useState([]);
 const [bulkBusy, setBulkBusy] = useState(false);
 const [bulkResult, setBulkResult] = useState('');

 useEffect(() => {
 let cancel = false;
 (async () => {
 try {
 const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
 const r = await axios.get(`${API}/master-admin/module-status`,
 { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } });
 if (!cancel) setModuleStatus(r.data?.data || {});
 } catch { /* silent — chip is best-effort */ }
 })();
 return () => { cancel = true; };
 }, [expandedOrg]); // re-fetch after toggling overrides closes a panel

 const toggleExpand = (orgId, view) => {
 if (expandedOrg === orgId && expandedView === view) {
 setExpandedOrg(null);
 } else {
 setExpandedOrg(orgId);
 setExpandedView(view);
 }
 };

 const getOrgUsers = (orgId) => users.filter(u => u.organization_id === orgId);

 // Apply portal filter if provided (for CRM tab view)
 // Iter 216h277 — robust filter. Historically this checked `portal_type`
 // only, but the Features tab writes module enablement to the per-module
 // `org.modules.{key}.enabled` dict and the Details tab writes to the
 // `enabled_modules` array. The three storages aren't always coherent on
 // older orgs, so the CRM Orgs tab was rendering empty even when admins
 // had enabled CRM. Match on the UNION of all three signals.
 let displayOrgs = filteredOrgs;
 if (portalFilter) {
   const moduleKey = portalFilter === 'crm' ? 'crm' : 'operations';
   displayOrgs = filteredOrgs.filter((o) => {
     const portalMatch =
       portalFilter === 'crm'
         ? o.portal_type === 'crm' || o.portal_type === 'both'
         : o.portal_type === 'service_portal' || o.portal_type === 'both';
     const enabledModulesMatch = Array.isArray(o.enabled_modules) && o.enabled_modules.includes(moduleKey);
     const featuresMatch = !!(o.modules && o.modules[moduleKey] && o.modules[moduleKey].enabled);
     return portalMatch || enabledModulesMatch || featuresMatch;
   });
 }

 // Apply multi-account-type filter (used by the MoD tab to show only mod_* orgs)
 if (Array.isArray(accountTypesIn) && accountTypesIn.length > 0) {
 displayOrgs = displayOrgs.filter(o => accountTypesIn.includes(o.account_type));
 }

 // Apply account type filter
 if (accountTypeFilter && accountTypeFilter !== 'all') {
 displayOrgs = displayOrgs.filter(o => (o.account_type || 'full') === accountTypeFilter);
 }

 // Iter 215bh — apply module filter. Matches orgs whose enabled_modules
 // array contains the selected key. "all-modules" matches orgs that have
 // every core module enabled (operations + crm + memberships + marketing).
 if (moduleFilter && moduleFilter !== 'all') {
   const CORE = ['operations', 'crm', 'memberships', 'marketing'];
   displayOrgs = displayOrgs.filter((o) => {
     const mods = Array.isArray(o.enabled_modules) ? o.enabled_modules : [];
     if (moduleFilter === 'all-modules') return CORE.every((m) => mods.includes(m));
     return mods.includes(moduleFilter);
   });
 }

 // Head Office filter — show only orgs flagged as a Head Office.
 if (hqFilter) {
   displayOrgs = displayOrgs.filter((o) => !!o.is_head_office);
 }

 const handleCreateOrg = async () => {
 if (!orgForm.name.trim()) return;
 setCreating(true);
 if (onCreateOrg) await onCreateOrg(orgForm);
 setCreating(false);
 setShowCreateOrg(false);
 setOrgForm({ name: '', portal_type: 'service_portal', enabled_modules: ['operations'], account_type: 'full', subscription_tier: 'starter', industry: '', employee_count: '', website: '', phone: '', address: '', address_line1: '', address_line2: '', address_line3: '', city: '', county: '', postcode: '', country: 'United Kingdom', primary_contact_name: '', primary_contact_email: '', primary_contact_phone: '', notes: '' });
 };

 const openEditOrg = (org) => {
 setEditingOrg({
 id: org.id, name: org.name || '', industry: org.industry || '', employee_count: org.employee_count || '',
 website: org.website || '', phone: org.phone || '', address: org.address || '',
 address_line1: org.address_line1 || org.address || '', address_line2: org.address_line2 || '', address_line3: org.address_line3 || '',
 city: org.city || '', county: org.county || '',
 postcode: org.postcode || '', country: org.country || 'United Kingdom', portal_type: org.portal_type || 'service_portal',
 // Iter 215em — `enabled_modules` was missing from this snapshot, so the
 // ModulesPicker fell back to portal_type-derived defaults every time the
 // edit panel was re-opened — making module saves *appear* to vanish even
 // though they were correctly persisted on the server. Carry it through
 // explicitly. Falls back to portal_type-derivation only on the very first
 // edit of a legacy org that has no `enabled_modules` field yet.
 enabled_modules: Array.isArray(org.enabled_modules) && org.enabled_modules.length > 0
   ? [...org.enabled_modules]
   : modulesFromPortalType(org.portal_type || 'service_portal'),
 primary_contact_name: org.primary_contact_name || '', primary_contact_email: org.primary_contact_email || '',
 primary_contact_phone: org.primary_contact_phone || '', notes: org.notes || '',
 customer_account_number: org.customer_account_number || '',
 sage_customer_number: org.sage_customer_number || '',
 });
 setExpandedOrg(org.id);
 setExpandedView('details');
 };

 const handleAddUser = async () => {
   if (!userForm.email || !userForm.full_name) return;
   setAddingUser(true);
   let created = null;
   if (onAddUserToOrg) created = await onAddUserToOrg(showAddUser, userForm);
   setAddingUser(false);
   // Iter 215ev — if the user was created in invite mode, stash the
   // returned invite link so the dialog can surface a "Copy invite link"
   // panel until the admin closes it. Resend DNS verification isn't
   // done yet, so this is the admin's primary way to share the link
   // (WhatsApp / their own email / Slack).
   if (created?.invite_url) {
     setLastInvite(created);
     setUserForm({ email: '', full_name: '', password: '', role: 'staff', module_overrides: {} });
     return;
   }
   setShowAddUser(null);
   setUserForm({ email: '', full_name: '', password: '', role: 'staff', module_overrides: {} });
 };

 return (
 <div className="space-y-4">
 <div className="flex items-center gap-3">
 <div className="relative flex-1">
 <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
 <Input value={search} onChange={e => onSearchChange(e.target.value)} placeholder="Search organisations..." className="bg-white border-slate-200 text-slate-900 pl-10 h-10 rounded-xl focus-visible:border-[var(--gx-brand-from)] focus-visible:ring-2 focus-visible:ring-[var(--gx-brand-from)]/15" data-testid="org-search" />
 </div>
 <Select value={orgFilter} onValueChange={onOrgFilterChange}>
 <SelectTrigger className="w-40 bg-white border-slate-200 text-slate-900 h-10 rounded-xl" data-testid="org-status-filter">
 <SelectValue />
 </SelectTrigger>
 <SelectContent className="bg-white border-slate-200">
 <SelectItem value="all">All Statuses</SelectItem>
 <SelectItem value="active">Active</SelectItem>
 <SelectItem value="trial">Trial</SelectItem>
 <SelectItem value="suspended">Suspended</SelectItem>
 <SelectItem value="cancelled">Cancelled</SelectItem>
 <SelectItem value="archived">Archived</SelectItem>
 </SelectContent>
 </Select>
 {/* Iter 233 — hide the Platforms dropdown when the surrounding tab
     already pins account types (MoD context): the dropdown would
     duplicate/contradict the fixed scope. */}
 {!(Array.isArray(accountTypesIn) && accountTypesIn.length > 0) && (
 <Select value={accountTypeFilter || 'all'} onValueChange={onAccountTypeFilterChange}>
 <SelectTrigger className="w-40 bg-white border-slate-200 text-slate-900 h-10 rounded-xl" data-testid="org-account-type-filter">
 <SelectValue />
 </SelectTrigger>
 <SelectContent className="bg-white border-slate-200">
 <SelectItem value="all">All Platforms</SelectItem>
 <SelectItem value="full">Pulse Fitness</SelectItem>
 <SelectItem value="pulse_pro">Pulse Pro</SelectItem>
 <SelectItem value="lite">Pulse Lite</SelectItem>
 <SelectItem value="partner_engineer">Independent Engineer</SelectItem>
 </SelectContent>
 </Select>
 )}
 {/* Iter 233 — hide the Modules dropdown when the module context is
     already fixed by the hosting tab (e.g. CRM → Organisations passes
     portalFilter): the card/tab acts as the filter, so the dropdown
     was a duplicate. */}
 {!portalFilter && !(Array.isArray(accountTypesIn) && accountTypesIn.length > 0) && (
 <Select value={moduleFilter} onValueChange={setModuleFilter}>
 <SelectTrigger className="w-44 bg-white border-slate-200 text-slate-900 h-10 rounded-xl" data-testid="org-module-filter">
 <SelectValue />
 </SelectTrigger>
 <SelectContent className="bg-white border-slate-200">
 <SelectItem value="all">All Modules</SelectItem>
 <SelectItem value="all-modules">Full Bundle (all 4)</SelectItem>
 <SelectItem value="operations">Operations</SelectItem>
 <SelectItem value="crm">CRM</SelectItem>
 <SelectItem value="memberships">Memberships</SelectItem>
 <SelectItem value="marketing">Marketing</SelectItem>
 </SelectContent>
 </Select>
 )}
 <button
   type="button"
   onClick={() => setHqFilter((v) => !v)}
   className={`h-10 px-3 rounded-xl border text-sm inline-flex items-center gap-1.5 transition-colors ${hqFilter ? 'bg-amber-500 text-white border-amber-500' : 'bg-white text-slate-700 border-slate-200 hover:bg-amber-50'}`}
   title="Show only Head Office organisations"
   data-testid="org-head-office-filter"
 >
   <Crown size={14} className={hqFilter ? 'text-white' : 'text-amber-500'} /> Head Offices
 </button>
 <Button className="h-10 text-sm rounded-full bg-gradient-to-r from-[var(--gx-brand-from)] to-[var(--gx-brand-to)] text-white hover:opacity-90 shadow-[0_6px_16px_-6px_rgba(25, 205, 255,0.35)] border-0" onClick={() => { setOrgForm({ name: '', portal_type: portalFilter || 'service_portal', account_type: 'full', subscription_tier: 'starter' }); setShowCreateOrg(true); }} data-testid="create-org-btn">
 <Plus size={14} className="mr-1" /> Create Organisation
 </Button>
 </div>

 {/* Iter 215at — bulk actions bar. Appears once 1+ orgs are selected.
     Pulse-only admin and the master admin both see this. */}
 {selectedIds.length > 0 && (
 <div
 className="flex flex-wrap items-center gap-3 rounded-xl border border-zinc-900 bg-zinc-900 text-white px-4 py-2.5 shadow-lg"
 data-testid="org-bulk-actions"
 >
 <span className="text-sm font-bold">{selectedIds.length} selected</span>
 <span className="text-zinc-500 text-sm">·</span>
 <button
 type="button"
 disabled={bulkBusy}
 onClick={async () => {
 setBulkBusy(true); setBulkResult('');
 try {
 const ids = [...selectedIds];
 await Promise.all(ids.map((id) => onUpdateStatus(id, 'archived')));
 setBulkResult(`Archived ${ids.length}`);
 setSelectedIds([]);
 } catch (e) { setBulkResult('Bulk archive failed'); }
 setBulkBusy(false);
 setTimeout(() => setBulkResult(''), 4000);
 }}
 className="inline-flex items-center gap-1.5 text-sm font-bold text-amber-300 hover:text-amber-200 disabled:opacity-50"
 data-testid="org-bulk-archive"
 >
 <Archive size={13} /> Archive
 </button>
 <button
 type="button"
 disabled={bulkBusy}
 onClick={async () => {
 setBulkBusy(true); setBulkResult('');
 try {
 const ids = [...selectedIds];
 await Promise.all(ids.map((id) => onUpdateStatus(id, 'active')));
 setBulkResult(`Activated ${ids.length}`);
 setSelectedIds([]);
 } catch (e) { setBulkResult('Bulk activate failed'); }
 setBulkBusy(false);
 setTimeout(() => setBulkResult(''), 4000);
 }}
 className="inline-flex items-center gap-1.5 text-sm font-bold text-emerald-300 hover:text-emerald-200 disabled:opacity-50"
 data-testid="org-bulk-activate"
 >
 <CheckCircle2 size={13} /> Activate
 </button>
 <button
 type="button"
 disabled={bulkBusy}
 onClick={async () => {
 setBulkBusy(true); setBulkResult('');
 try {
 const ids = [...selectedIds];
 const orgsById = Object.fromEntries(displayOrgs.map((o) => [o.id, o]));
 await Promise.all(ids.map((id) => onToggleTest(id, !orgsById[id]?.is_test)));
 setBulkResult(`Toggled TEST flag on ${ids.length}`);
 setSelectedIds([]);
 } catch (e) { setBulkResult('Bulk toggle failed'); }
 setBulkBusy(false);
 setTimeout(() => setBulkResult(''), 4000);
 }}
 className="inline-flex items-center gap-1.5 text-sm font-bold text-violet-300 hover:text-violet-200 disabled:opacity-50"
 data-testid="org-bulk-toggle-test"
 >
 <Shield size={13} /> Toggle TEST
 </button>
 <div className="flex-1" />
 {bulkBusy && <Loader2 size={13} className="animate-spin text-zinc-400" />}
 {bulkResult && <span className="text-xs text-emerald-300 font-semibold">{bulkResult}</span>}
 <button
 type="button"
 onClick={() => setSelectedIds([])}
 className="text-xs text-zinc-400 hover:text-white font-semibold"
 data-testid="org-bulk-clear"
 >
 Clear
 </button>
 </div>
 )}

 <div className="space-y-3">
 {displayOrgs.length === 0 && filteredOrgs.length === 0 ? (
 <>
 <OrgRowSkeleton />
 <OrgRowSkeleton />
 <OrgRowSkeleton />
 </>
 ) : displayOrgs.map(org => {
 const isExpanded = expandedOrg === org.id;
 const orgUsers = getOrgUsers(org.id);
 const _portalType = org.portal_type || 'service_portal';

 return (
 <Card key={org.id} className={`bg-white border-slate-200 rounded-2xl shadow-[0_1px_2px_rgba(15,23,42,0.04)] overflow-hidden transition-shadow hover:shadow-[0_8px_24px_-8px_rgba(15,23,42,0.10)] ${STATUS_BORDER[org.status || 'active']}`} data-testid={`org-card-${org.id}`}>
 <div className="p-4">
 {/* Iter 215ex — mobile: stack the 3 sections vertically. Previously
     the outer flex kept everything on ONE row at all breakpoints, so
     on phones the tier dropdown + status select + stats row all
     collided and overflowed. Must remain flex-col below md. */}
 <div className="flex flex-col md:flex-row md:items-center gap-3 md:min-w-0">
 <input
 type="checkbox"
 className="w-4 h-4 rounded border-zinc-300 text-zinc-900 cursor-pointer flex-shrink-0 hidden md:block"
 checked={selectedIds.includes(org.id)}
 onChange={(e) => {
   const id = org.id;
   setSelectedIds((cur) => e.target.checked ? [...cur, id] : cur.filter((x) => x !== id));
 }}
 onClick={(e) => e.stopPropagation()}
 data-testid={`org-select-${org.id}`}
 aria-label={`Select ${org.name}`}
 />
 <div className="flex items-center gap-2 min-w-0 md:min-w-[200px] flex-1 md:flex-initial flex-wrap">
 <div className="w-9 h-9 rounded-md bg-blue-50 flex items-center justify-center flex-shrink-0">
 <Building2 size={16} className="text-blue-600" />
 </div>
 <div>
 <p className="font-medium text-zinc-900 text-sm">{org.name}</p>
 <p className="text-[11px] text-zinc-400">{org.owner_email || 'No owner'}</p>
 </div>
 {org.is_test && <Badge className="bg-violet-50 text-violet-600 text-[10px] border-violet-200">TEST</Badge>}
 <Badge className={`text-[10px] border ${ACCOUNT_TYPE_STYLES[org.account_type || 'full']}`} data-testid={`org-account-type-badge-${org.id}`}>
 {ACCOUNT_TYPE_LABELS[org.account_type || 'full']}
 </Badge>
 {org.is_head_office && (
   <Badge className="text-[10px] border bg-amber-50 text-amber-700 border-amber-200 inline-flex items-center gap-1" data-testid={`org-head-office-badge-${org.id}`}>
     <Crown size={10} className="text-amber-500" /> Head Office
   </Badge>
 )}
              {(() => {
                const crm = (org.modules || {}).crm || {};
                const crmOn = crm.enabled === true || crm.business_enabled === true;
                if (!crmOn) return null;
                const biz = !!crm.business_enabled;
                const lei = crm.leisure_enabled !== false;
                const label = biz && lei ? 'CRM: Both' : biz ? 'CRM: Corporate' : 'CRM: Gym';
                const style = biz && lei
                  ? 'bg-indigo-50 text-indigo-600 border-indigo-200'
                  : biz ? 'bg-sky-50 text-sky-700 border-sky-200' : 'bg-emerald-50 text-emerald-700 border-emerald-200';
                return (
                  <Badge className={`text-[10px] border ${style}`} data-testid={`org-crm-mode-badge-${org.id}`}>
                    {label}
                  </Badge>
                );
              })()}
 {(() => {
 const ms = moduleStatus[org.id];
 if (!ms) return null;
 const disabledN = (ms.org_disabled || []).length;
 const overrideN = ms.sites_with_overrides || 0;
 if (disabledN === 0 && overrideN === 0) return null;
 const tip = [
 disabledN > 0 ? `Org-level off: ${ms.org_disabled.join(', ')}` : null,
 overrideN > 0 ? `${overrideN} site${overrideN === 1 ? '' : 's'} with module override${overrideN === 1 ? '' : 's'}` : null,
 ].filter(Boolean).join(' · ');
 return (
 <button onClick={() => toggleExpand(org.id, 'sites')}
 title={tip}
 className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 transition-colors"
 data-testid={`org-module-chip-${org.id}`}>
 <ShieldCheck size={10} />
 {disabledN > 0 && <span>{disabledN} off</span>}
 {disabledN > 0 && overrideN > 0 && <span>·</span>}
 {overrideN > 0 && <span>{overrideN} override{overrideN === 1 ? '' : 's'}</span>}
 </button>
 );
 })()}
 </div>

 <div className="flex items-center gap-x-3 gap-y-1 text-xs md:text-sm flex-wrap min-w-0">
 <button onClick={() => toggleExpand(org.id, 'users')}
 className={`flex items-center gap-1 px-2 py-1 rounded-md transition-colors ${isExpanded && expandedView === 'users' ? 'bg-blue-50 text-blue-700' : 'text-zinc-700 hover:bg-zinc-100'}`}
 data-testid={`org-users-btn-${org.id}`}>
 <Users size={13} />
 <span className="font-semibold">{org.user_count}</span>
 <span className="text-zinc-400 text-xs">users</span>
 </button>
 <span className="text-zinc-400">|</span>
 {org.employee_count && <><span className="text-zinc-700"><span className="font-semibold">{org.employee_count}</span> <span className="text-zinc-400 text-xs">employees</span></span><span className="text-zinc-400">|</span></>}
 {org.industry && <><span className="text-zinc-500 text-xs">{org.industry}</span><span className="text-zinc-400">|</span></>}
 <span className="text-zinc-700"><span className="font-semibold">{org.equipment_count}</span> <span className="text-zinc-400 text-xs">equip</span></span>
 <span className="text-zinc-400">|</span>
 <span className="text-zinc-700"><span className="font-semibold">{org.open_issues}</span><span className="text-zinc-400">/{org.issue_count}</span> <span className="text-zinc-400 text-xs">issues</span></span>
 </div>

 <div className="flex items-center gap-2 md:ml-auto flex-wrap w-full md:w-auto">
 {(() => {
   // Pulse Fitness operations product = Lite (free) + Pro (paid).
   // Applies to all Pulse Fitness orgs (account_type full/pulse_pro/lite).
   const isPulseFamily = ['full', 'pulse_pro', 'lite'].includes(org.account_type);
   const val = isPulseFamily
     ? ((org.subscription_tier === 'lite' || org.account_type === 'lite') ? 'lite' : 'pulse_pro')
     : (['free', 'pro', 'premium', 'enterprise', 'starter', 'professional'].includes(org.subscription_tier) ? org.subscription_tier : 'starter');
   return (
   <Select value={val} onValueChange={(v) => onUpdateTier(org.id, v)}>
   <SelectTrigger className={`h-7 text-xs border-0 w-full md:w-28 ${TIER_STYLES[org.subscription_tier || 'free'] || 'bg-zinc-100 text-zinc-600'}`} data-testid={`org-tier-${org.id}`}><SelectValue /></SelectTrigger>
   <SelectContent className="bg-white border-zinc-200">
   {isPulseFamily ? (
   <>
   <SelectItem value="lite">Lite</SelectItem>
   <SelectItem value="pulse_pro">Pro</SelectItem>
   </>
   ) : (
   <>
   <SelectItem value="starter">Starter</SelectItem>
   <SelectItem value="professional">Professional</SelectItem>
   <SelectItem value="enterprise">Enterprise</SelectItem>
   </>
   )}
   </SelectContent>
   </Select>
   );
 })()}
 <Select value={org.status || 'active'} onValueChange={(v) => onUpdateStatus(org.id, v)}>
 <SelectTrigger className={`h-7 text-xs border w-full md:w-24 ${STATUS_STYLES[org.status || 'active']}`} data-testid={`org-status-${org.id}`}><SelectValue /></SelectTrigger>
 <SelectContent className="bg-white border-zinc-200">
 <SelectItem value="active">Active</SelectItem>
 <SelectItem value="trial">Trial</SelectItem>
 <SelectItem value="suspended">Suspended</SelectItem>
 <SelectItem value="cancelled">Cancelled</SelectItem>
 <SelectItem value="archived">Archived</SelectItem>
 </SelectContent>
 </Select>
 <Button size="sm" variant="ghost" className={`h-7 w-7 p-0 ${isExpanded && expandedView === 'details' ? 'text-blue-600 bg-blue-50' : 'text-zinc-400 hover:text-blue-600'}`} onClick={() => openEditOrg(org)} title="Organisation Details" data-testid={`org-edit-${org.id}`}>
 <Edit2 size={14} />
 </Button>
 {/* QW#5 + QW#6 — secondary actions (Archive / Toggle Test / Email Preview)
     consolidated into a single "More" menu so the row scans cleanly.
     Archive carries an Undo flow via a 5s bottom banner. */}
 <DropdownMenu>
 <DropdownMenuTrigger asChild>
 <Button
 size="sm" variant="ghost"
 className="h-7 w-7 p-0 text-zinc-400 hover:text-zinc-900"
 title="More actions"
 data-testid={`org-more-${org.id}`}
 >
 <MoreHorizontal size={14} />
 </Button>
 </DropdownMenuTrigger>
 <DropdownMenuContent align="end" className="w-56 bg-white border-zinc-200">
 <DropdownMenuItem
 onClick={() => {
 const wasArchived = org.status === 'archived';
 const nextStatus = wasArchived ? 'active' : 'archived';
 onUpdateStatus(org.id, nextStatus);
 if (!wasArchived) {
 // Show 5s undo banner — clears itself or on Undo click.
 setArchivedToast({ orgId: org.id, name: org.name, prevStatus: org.status || 'active' });
 setTimeout(() => setArchivedToast((cur) => (cur && cur.orgId === org.id ? null : cur)), 5000);
 }
 }}
 data-testid={`org-archive-${org.id}`}
 >
 <Archive size={14} className="mr-2 text-amber-600" />
 {org.status === 'archived' ? 'Unarchive' : 'Archive'}
 </DropdownMenuItem>
 <DropdownMenuItem onClick={() => onToggleTest(org.id, !org.is_test)} data-testid={`org-test-${org.id}`}>
 <Shield size={14} className="mr-2 text-violet-600" />
 {org.is_test ? 'Remove TEST flag' : 'Mark as TEST'}
 </DropdownMenuItem>
 {onSendEmailPreview && (
 <DropdownMenuItem
 onClick={() => { setEmailPreviewOrg(org); setEmailPreviewTo(''); }}
 data-testid={`org-email-preview-${org.id}`}
 >
 <Mail size={14} className="mr-2 text-indigo-600" />
 Send email preview
 </DropdownMenuItem>
 )}
 </DropdownMenuContent>
 </DropdownMenu>
 </div>
 </div>
 </div>

 {/* Iter 215au — Side-drawer org drill-down. Opens whenever
            isExpanded becomes true. The internal <Tabs> mirrors
            expandedView so all the existing buttons (org-edit, org-users,
            org-features, org-sites) keep working unchanged — they just
            now render their content inside this single slide-in drawer
            with two NEW tabs (Billing, Audit). */}
            {isExpanded && (
            <Sheet open onOpenChange={(o) => { if (!o) { setExpandedOrg(null); setEditingOrg(null); } }}>
              <SheetContent
                side="right"
                className="w-full sm:max-w-2xl overflow-y-auto p-0 bg-white text-slate-900 theme-gymaxis"
                data-testid={`org-manage-drawer-${org.id}`}
              >
                <SheetHeader className="px-5 py-4 pr-14 border-b border-slate-100 sticky top-0 bg-white z-10">
                  <SheetTitle className="text-base font-bold tracking-tight flex items-center gap-2 text-slate-900">
                    <Building2 size={16} className="text-slate-500" /> {org.name}
                  </SheetTitle>
                  {/* Iter 216f — explicit close button. shadcn's <SheetContent>
                      already renders an X at top-right but the sticky
                      `SheetHeader` with `bg-white z-10` was painting over it on
                      mobile (Lee's Feb-2026 screenshot). Adding an explicit
                      close in the header guarantees a visible affordance. */}
                  <SheetClose asChild>
                    <button
                      type="button"
                      aria-label="Close panel"
                      className="absolute right-3 top-3 inline-flex items-center justify-center w-9 h-9 rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      data-testid={`org-manage-close-${org.id}`}
                    >
                      <X size={18} />
                    </button>
                  </SheetClose>
                </SheetHeader>

                <Tabs
                  value={expandedView || 'details'}
                  onValueChange={(v) => {
                    setExpandedView(v);
                    // Initialise the edit form when switching to Details
                    // if it isn't already opened for this org.
                    if (v === 'details' && (!editingOrg || editingOrg.id !== org.id)) {
                      openEditOrg(org);
                    }
                  }}
                  className="px-5 pt-3"
                >
                  <TabsList className="grid grid-cols-4 sm:grid-cols-7 w-full bg-slate-100 h-auto" data-testid={`org-manage-tabs-${org.id}`}>
                    <TabsTrigger value="details"      data-testid={`org-tab-details-${org.id}`}>Profile</TabsTrigger>
                    <TabsTrigger value="sites"        data-testid={`org-tab-sites-${org.id}`}>Sites</TabsTrigger>
                    <TabsTrigger value="users"        data-testid={`org-tab-users-${org.id}`}>People</TabsTrigger>
                    <TabsTrigger value="features"     data-testid={`org-tab-features-${org.id}`}>Modules</TabsTrigger>
                    <TabsTrigger value="billing"      data-testid={`org-tab-billing-${org.id}`}>Billing</TabsTrigger>
                    <TabsTrigger value="integrations" data-testid={`org-tab-integrations-${org.id}`}>Integrations</TabsTrigger>
                    <TabsTrigger value="audit"        data-testid={`org-tab-audit-${org.id}`}>Activity</TabsTrigger>
                  </TabsList>
                </Tabs>

                <div className="p-5">

 {/* Expanded: Users */}
 {isExpanded && expandedView === 'users' && (
 <div className="bg-white" data-testid={`org-users-panel-${org.id}`}>
 <div className="flex items-center justify-between mb-3">
 <p className="text-sm font-medium text-zinc-700">Users in {org.name} ({orgUsers.length})</p>
 <div className="flex items-center gap-2">
 <Button size="sm" className="h-7 text-xs" onClick={() => { setShowAddUser(org.id); setUserForm({ email: '', full_name: '', password: '', role: 'staff', module_overrides: {} }); }} data-testid={`org-add-user-btn-${org.id}`}>
 <UserPlus size={12} className="mr-1" /> Add User
 </Button>
 </div>
 </div>
 {orgUsers.length > 0 ? (
 <div className="space-y-2">
 {orgUsers.map(u => (
 <div key={u.id} className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-3 bg-white rounded-md border border-zinc-200" data-testid={`org-user-${u.id}`}>
 <div className="flex items-center gap-3 min-w-0">
 <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-xs font-bold text-blue-700 flex-shrink-0">
 {(u.full_name || u.email || '?')[0].toUpperCase()}
 </div>
 <div className="min-w-0 flex-1">
 <p className="text-sm text-zinc-900 font-medium truncate" data-testid={`org-user-name-${u.id}`}>{u.full_name || 'Unnamed'}</p>
 <p className="text-[11px] text-zinc-500 truncate" data-testid={`org-user-email-${u.id}`}>{u.email}</p>
 </div>
 </div>
 <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap sm:flex-shrink-0">
 <Select value={u.is_master_admin ? 'master_admin' : ((u.is_pulse_admin || u.role === 'pulse_master_admin') ? 'pulse_master_admin' : (u.role || 'staff'))} onValueChange={(v) => onEditUser && onEditUser(u.id, { role: v })}>
 <SelectTrigger className={`h-7 text-xs border w-24 ${u.role === 'owner' ? 'bg-amber-50 text-amber-700 border-amber-200' : u.role === 'manager' ? 'bg-blue-50 text-blue-700 border-blue-200' : 'bg-zinc-100 text-zinc-600 border-zinc-200'}`} data-testid={`user-role-${u.id}`}><SelectValue /></SelectTrigger>
 <SelectContent className="bg-white border-zinc-200">
 <SelectItem value="owner">Owner</SelectItem>
 <SelectItem value="manager">Manager</SelectItem>
 <SelectItem value="staff">Staff</SelectItem>
 {/* Iter 260 — Engineer selectable inline (parity with Add/Edit dialogs).
     Backend PATCH /master-admin/users/{id} provisions svc_engineers on
     role→engineer and deactivates it when switching away. */}
 <SelectItem value="engineer">Engineer</SelectItem>
 <SelectItem value="master_admin">{masterAdminRoleLabel}</SelectItem>
 {(u.role === 'pulse_master_admin' || u.is_pulse_admin) && <SelectItem value="pulse_master_admin">Master Admin (Pulse)</SelectItem>}
 </SelectContent>
 </Select>
 {u.user_type === 'crm' && <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200 text-[9px]">CRM</Badge>}
 {u.invited_role && u.invited_role !== u.role && (
 <Badge
 className="bg-amber-50 text-amber-700 border border-amber-200 text-[9px] cursor-help"
 title={`This user was originally invited as "${u.invited_role}" but their current role is "${u.role || 'staff'}". If this is unexpected, change the role back via the dropdown.`}
 data-testid={`role-mismatch-${u.id}`}
 >
 ⚠ Was invited as {u.invited_role}
 </Badge>
 )}
 {u.disabled && <Badge className="bg-red-50 text-red-600">Disabled</Badge>}
 {u.archived && <Badge className="bg-zinc-200 text-zinc-500">Archived</Badge>}
 <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-zinc-400 hover:text-blue-600" onClick={() => setEditingUser({ ...u })} title="Edit details" data-testid={`edit-user-${u.id}`}>
 <Edit2 size={13} />
 </Button>
 {onResetPassword && (
 <Button size="sm" variant="ghost" className="h-7 px-2 text-[11px] text-zinc-500 hover:text-zinc-800" onClick={() => onResetPassword(u.id)} data-testid={`reset-pw-${u.id}`}>Reset PW</Button>
 )}
 {onUnlockUser && (
 <Button size="sm" variant="ghost" className="h-7 px-2 text-[11px] text-zinc-500 hover:text-emerald-700" onClick={() => onUnlockUser(u.id)} title="Clear login lockout / rate-limit so the user can sign in now" data-testid={`unlock-user-${u.id}`}>
 <LockOpen size={11} className="mr-0.5" /> Unlock
 </Button>
 )}
 {onDisableUser && (
 <Button size="sm" variant="ghost" className={`h-7 px-2 text-[11px] ${u.disabled ? 'text-emerald-600' : 'text-red-500'}`} onClick={() => onDisableUser(u.id, !u.disabled)}>
 {u.disabled ? 'Enable' : 'Disable'}
 </Button>
 )}
 {onArchiveUser && (
 <Button size="sm" variant="ghost" className={`h-7 px-2 text-[11px] ${u.archived ? 'text-blue-500' : 'text-amber-600'}`} onClick={() => onArchiveUser(u.id, !u.archived)} title={u.archived ? 'Unarchive' : 'Archive'}>
 <Archive size={11} className="mr-0.5" /> {u.archived ? 'Unarchive' : 'Archive'}
 </Button>
 )}
 {onHardDeleteUser && u.archived && !u.is_master_admin && (u.email || '').toLowerCase() !== 'admin@pulsefitness.ai' && (
 <Button
 size="sm" variant="ghost"
 className="h-7 px-2 text-[11px] text-red-600 hover:bg-red-50"
 onClick={() => setHardDeleteTarget(u)}
 title="Delete permanently"
 data-testid={`hard-delete-user-${u.id}`}
 >
 <Trash2 size={11} className="mr-0.5" /> Delete
 </Button>
 )}
 </div>
 </div>
 ))}
 </div>
 ) : (
 <p className="text-sm text-zinc-400 text-center py-4">No users yet — add the first user above</p>
 )}
 </div>
 )}

 {/* Expanded: Feature Control (with presets, copy-from-org, audit log) */}
 {isExpanded && expandedView === 'features' && (
 <FeatureControlPanel
 org={org}
 allOrgs={displayOrgs}
 onClose={() => setExpandedOrg(null)}
 onUpdateFeatures={onUpdateFeatures}
 />
 )}

 {/* Expanded: Sites & per-site module overrides */}
 {isExpanded && expandedView === 'sites' && (
 <OrgSitesPanel org={org} onClose={() => setExpandedOrg(null)} />
 )}

 {/* Expanded: Organisation Details */}
 {isExpanded && expandedView === 'details' && editingOrg?.id === org.id && (
 <div className="bg-white" data-testid={`org-details-panel-${org.id}`}>
 <div className="flex items-center justify-between mb-3">
 <p className="text-sm font-medium text-zinc-700">Organisation Details — {org.name}</p>
 </div>
 <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
 <div>
 <Label className="text-zinc-500 text-[10px] uppercase tracking-wider">Organisation Name</Label>
 <Input value={editingOrg.name} onChange={e => setEditingOrg({...editingOrg, name: e.target.value})} className="mt-1 bg-white h-8 text-sm" data-testid="org-edit-name" />
 </div>
 <div>
 <Label className="text-zinc-500 text-[10px] uppercase tracking-wider">Industry</Label>
 <Select value={editingOrg.industry || '_none'} onValueChange={v => setEditingOrg({...editingOrg, industry: v === '_none' ? '' : v})}>
 <SelectTrigger className="mt-1 bg-white h-8 text-sm" data-testid="org-edit-industry"><SelectValue placeholder="Select..." /></SelectTrigger>
 <SelectContent className="bg-white border-zinc-200">
 <SelectItem value="_none">Select...</SelectItem>
 {INDUSTRY_OPTIONS.map(i => <SelectItem key={i} value={i}>{i}</SelectItem>)}
 </SelectContent>
 </Select>
 </div>
 <div>
 <Label className="text-zinc-500 text-[10px] uppercase tracking-wider">Employees</Label>
 <Select value={editingOrg.employee_count || '_none'} onValueChange={v => setEditingOrg({...editingOrg, employee_count: v === '_none' ? '' : v})}>
 <SelectTrigger className="mt-1 bg-white h-8 text-sm" data-testid="org-edit-employees"><SelectValue placeholder="Select..." /></SelectTrigger>
 <SelectContent className="bg-white border-zinc-200">
 <SelectItem value="_none">Select...</SelectItem>
 {EMPLOYEE_RANGES.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}
 </SelectContent>
 </Select>
 </div>
 <div>
 <Label className="text-zinc-500 text-[10px] uppercase tracking-wider">Website</Label>
 <Input value={editingOrg.website} onChange={e => setEditingOrg({...editingOrg, website: e.target.value})} placeholder="https://..." className="mt-1 bg-white h-8 text-sm" data-testid="org-edit-website" />
 </div>
 <div>
 <Label className="text-zinc-500 text-[10px] uppercase tracking-wider">Phone</Label>
 <Input value={editingOrg.phone} onChange={e => setEditingOrg({...editingOrg, phone: e.target.value})} className="mt-1 bg-white h-8 text-sm" data-testid="org-edit-phone" />
 </div>
 {/* Iter 215ev — Modules removed from Details tab. Single source of
     truth is the Features tab (Module Access card). Was duplicated
     here and causing confusion when toggles disagreed. */}
 <div className="sm:col-span-2">
 <Label className="text-zinc-500 text-[10px] uppercase tracking-wider">Address</Label>
 <AddressFields
   value={editingOrg}
   onChange={(addr) => setEditingOrg({ ...editingOrg, ...addr })}
   testIdPrefix="org-edit-address"
   bg="bg-white"
   required={false}
 />
 </div>
 </div>
 <p className="text-[10px] uppercase tracking-wider font-bold text-zinc-400 mt-4 mb-2">Tenant identifiers</p>
 <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
 <div>
 <Label className="text-zinc-500 text-[10px] uppercase tracking-wider">Customer account number</Label>
 <Input
 value={editingOrg.customer_account_number}
 onChange={e => setEditingOrg({...editingOrg, customer_account_number: e.target.value})}
 placeholder="e.g. PULSENC01"
 className="mt-1 bg-white h-8 text-sm font-mono"
 data-testid="org-edit-customer-account-number"
 />
 <p className="text-[10px] text-zinc-400 mt-1">Used by Bulk Imports to auto-route equipment / customer rows to this tenant.</p>
 </div>
 <div>
 <Label className="text-zinc-500 text-[10px] uppercase tracking-wider">Sage customer number <span className="text-zinc-300 normal-case">(optional)</span></Label>
 <Input
 value={editingOrg.sage_customer_number}
 onChange={e => setEditingOrg({...editingOrg, sage_customer_number: e.target.value})}
 placeholder="Sage 200 / Sicon code"
 className="mt-1 bg-white h-8 text-sm font-mono"
 data-testid="org-edit-sage-customer-number"
 />
 </div>
 </div>
 {/* Verify mappings */}
 <div className="mt-3 flex items-center gap-3">
 <Button
 size="sm"
 variant="outline"
 disabled={verifyBusy}
 className="border-emerald-200 text-emerald-700 hover:bg-emerald-50 h-8 text-xs"
 data-testid="org-verify-mappings-btn"
 onClick={async () => {
 setVerifyBusy(true);
 setVerifyResult(null);
 try {
 const API = process.env.REACT_APP_BACKEND_URL;
 const token = localStorage.getItem('token');
 const res = await fetch(`${API}/api/master-admin/organizations/${editingOrg.id}/verify-mappings`, {
 method: 'POST',
 headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
 body: JSON.stringify({
 customer_account_number: editingOrg.customer_account_number || '',
 sage_customer_number: editingOrg.sage_customer_number || '',
 }),
 });
 const data = await res.json();
 setVerifyResult(data);
 } catch (e) {
 setVerifyResult({ ok: false, error: String(e) });
 }
 setVerifyBusy(false);
 }}
 >
 {verifyBusy ? <Loader2 size={12} className="mr-1 animate-spin" /> : <ShieldCheck size={12} className="mr-1" />}
 Verify mappings
 </Button>
 <p className="text-[10px] text-zinc-400">Checks for typos, collisions, and Sicon / Orbit 4 connection status.</p>
 </div>
 {verifyResult && (
 <div
 className={`mt-2 rounded-lg p-3 text-[11px] border ${verifyResult.all_green ? 'bg-emerald-50 border-emerald-200' : 'bg-amber-50 border-amber-200'}`}
 data-testid="org-verify-result"
 >
 {Object.entries(verifyResult.fields || {}).map(([fname, r]) => {
 const label = fname.replace(/_/g, ' ');
 if (!r.value) {
 return (
 <p key={fname} className="text-zinc-500 mb-1">
 · {label}: <span className="italic">empty</span>
 </p>
 );
 }
 const ok = r.format_ok && !r.collision;
 return (
 <p key={fname} className={`mb-1 flex items-start gap-1.5 ${ok ? 'text-emerald-800' : 'text-amber-800'}`}>
 {ok ? <CheckCircle2 size={12} className="mt-0.5 shrink-0" /> : <AlertTriangle size={12} className="mt-0.5 shrink-0" />}
 <span>
 <strong className="font-mono">{r.value}</strong> ({label})
 {!r.format_ok && <span> — invalid format</span>}
 {r.collision && (
 <span> — already used by <strong>{r.collision.name}</strong></span>
 )}
 </span>
 </p>
 );
 })}
 <p className="mt-2 text-zinc-500 flex flex-wrap gap-3">
 <span>
 Sicon: <strong className={verifyResult.integrations?.sicon?.configured ? 'text-emerald-700' : 'text-zinc-400'}>
 {verifyResult.integrations?.sicon?.configured ? 'connected' : 'not configured'}
 </strong>
 </span>
 <span>
 Orbit 4: <strong className={verifyResult.integrations?.orbit4?.configured ? 'text-emerald-700' : 'text-zinc-400'}>
 {verifyResult.integrations?.orbit4?.configured ? 'connected' : 'not configured'}
 </strong>
 </span>
 </p>
 </div>
 )}
 <p className="text-[10px] uppercase tracking-wider font-bold text-zinc-400 mt-4 mb-2">Primary Contact</p>
 <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
 <div>
 <Label className="text-zinc-500 text-[10px] uppercase tracking-wider">Name</Label>
 <Input value={editingOrg.primary_contact_name} onChange={e => setEditingOrg({...editingOrg, primary_contact_name: e.target.value})} className="mt-1 bg-white h-8 text-sm" data-testid="org-edit-contact-name" />
 </div>
 <div>
 <Label className="text-zinc-500 text-[10px] uppercase tracking-wider">Email</Label>
 <Input value={editingOrg.primary_contact_email} onChange={e => setEditingOrg({...editingOrg, primary_contact_email: e.target.value})} className="mt-1 bg-white h-8 text-sm" data-testid="org-edit-contact-email" />
 </div>
 <div>
 <Label className="text-zinc-500 text-[10px] uppercase tracking-wider">Phone</Label>
 <Input value={editingOrg.primary_contact_phone} onChange={e => setEditingOrg({...editingOrg, primary_contact_phone: e.target.value})} className="mt-1 bg-white h-8 text-sm" />
 </div>
 </div>
 <PrimaryContactPasswordReveal
   orgId={editingOrg.id}
   primaryContactEmail={editingOrg.primary_contact_email}
   primaryContactUserId={editingOrg.primary_contact_user_id}
 />
 <div className="mt-3">
 <Label className="text-zinc-500 text-[10px] uppercase tracking-wider">Notes</Label>
 <textarea value={editingOrg.notes} onChange={e => setEditingOrg({...editingOrg, notes: e.target.value})} rows={2} className="mt-1 w-full bg-white text-sm px-3 py-2 rounded-md border border-zinc-200 resize-none" data-testid="org-edit-notes" />
 </div>
 <div className="flex items-center justify-end gap-3 mt-3">
            {savedAt && !saveError && (
              <span
                className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-1 rounded-md"
                data-testid="org-edit-saved-chip"
              >
                <CheckCircle2 size={12} /> Saved {savedAt}
              </span>
            )}
            {saveError && (
              <span
                className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-rose-700 bg-rose-50 border border-rose-200 px-2 py-1 rounded-md"
                data-testid="org-edit-save-error"
              >
                <AlertCircle size={12} /> {saveError}
              </span>
            )}
            <Button className="h-8 text-sm" disabled={savingEdit} onClick={async () => {
 setSavingEdit(true);
 setSaveError('');
 try {
 const { id, ...updates } = editingOrg;
 // The Details tab does NOT own modules — the Modules tab (Feature
 // Control) is the single source of truth. A stale enabled_modules /
 // portal_type snapshot taken when this panel opened would otherwise
 // clobber modules the admin just toggled → the recurring "enable a
 // module, press Save, it disables" bug. Strip them from the payload.
 delete updates.enabled_modules;
 delete updates.portal_type;
 const API = process.env.REACT_APP_BACKEND_URL;
 const token = localStorage.getItem('token');
 const res = await fetch(`${API}/api/master-admin/organizations/${id}/details`, {
 method: 'PUT', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
 body: JSON.stringify(updates),
 });
 if (!res.ok) {
   const detail = await res.json().catch(() => ({}));
   throw new Error(detail?.detail || `Save failed (${res.status})`);
 }
 // QW#4 — refresh the parent's org list in place. No more full
 // window.location.reload — keeps scroll, filters, and search.
 if (onReloadOrgs) await onReloadOrgs();
 const now = new Date();
 setSavedAt(`${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}`);
 setTimeout(() => setSavedAt(null), 4000);
 // Close panel after a short beat so the user actually sees the chip.
 setTimeout(() => {
   setExpandedOrg(null); setEditingOrg(null);
 }, 1500);
 } catch (e) {
   setSaveError(e?.message || 'Save failed');
   setTimeout(() => setSaveError(''), 5000);
 }
 setSavingEdit(false);
 }} data-testid="org-save-details-btn">
 {savingEdit ? <Loader2 size={14} className="animate-spin mr-1" /> : <Save size={14} className="mr-1" />} Save Details
 </Button>
 </div>
 </div>
 )}

 {/* NEW Tab — Billing.
     Holds the high-signal commercial fields together: Tier, Customer
     account number, Sage / Sicon refs. Tier and customer numbers ALSO
     show on Details, but having them on a dedicated Billing tab makes
     a billing review fast for finance admins. */}
 {isExpanded && expandedView === 'billing' && (
 <div className="bg-white" data-testid={`org-billing-panel-${org.id}`}>
 <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
 <div>
 <Label className="text-zinc-500 text-[10px] uppercase tracking-wider">Subscription tier</Label>
 {/* Iter 216d — context-aware tier list. Pulse Pro orgs get Pulse
     tiers, MOD orgs get MOD tiers, Pulse Fitness customers keep the
     Starter/Growth/Enterprise lineup. */}
 {(() => {
   const isPulse = ['full', 'pulse_pro', 'lite'].includes(org.account_type);
   const isMod = (org.account_type || '').startsWith('mod_');
   const cur = isPulse
     ? ((org.subscription_tier === 'lite' || org.account_type === 'lite') ? 'lite' : 'pulse_pro')
     : (org.subscription_tier || (isMod ? 'mod_branch' : 'starter'));
   return (
     <Select value={cur} onValueChange={(v) => onUpdateTier(org.id, v)}>
       <SelectTrigger className="mt-1 bg-white h-8 text-sm" data-testid={`org-billing-tier-${org.id}`}><SelectValue /></SelectTrigger>
       <SelectContent className="bg-white border-zinc-200">
         {isPulse && (
           <>
             <SelectItem value="lite">Pulse Lite (free)</SelectItem>
             <SelectItem value="pulse_pro">Pulse Pro</SelectItem>
           </>
         )}
         {isMod && (
           <>
             <SelectItem value="mod_site">MOD Site</SelectItem>
             <SelectItem value="mod_branch">MOD Branch</SelectItem>
             <SelectItem value="mod_org">MOD Org</SelectItem>
           </>
         )}
         {!isPulse && !isMod && (
           <>
             <SelectItem value="starter">Starter</SelectItem>
             <SelectItem value="growth">Growth</SelectItem>
             <SelectItem value="enterprise">Enterprise</SelectItem>
           </>
         )}
       </SelectContent>
     </Select>
   );
 })()}
 </div>
 <div>
 <Label className="text-zinc-500 text-[10px] uppercase tracking-wider">Status</Label>
 <Select value={org.status || 'active'} onValueChange={(v) => onUpdateStatus(org.id, v)}>
 <SelectTrigger className="mt-1 bg-white h-8 text-sm"><SelectValue /></SelectTrigger>
 <SelectContent className="bg-white border-zinc-200">
 <SelectItem value="active">Active</SelectItem>
 <SelectItem value="trial">Trial</SelectItem>
 <SelectItem value="suspended">Suspended</SelectItem>
 <SelectItem value="archived">Archived</SelectItem>
 </SelectContent>
 </Select>
 </div>
 <div>
 <Label className="text-zinc-500 text-[10px] uppercase tracking-wider">Customer account #</Label>
 <Input
 value={(editingOrg?.id === org.id ? editingOrg.customer_account_number : org.customer_account_number) || ''}
 onChange={(e) => editingOrg?.id === org.id && setEditingOrg({ ...editingOrg, customer_account_number: e.target.value })}
 onFocus={() => { if (!editingOrg || editingOrg.id !== org.id) openEditOrg(org); }}
 className="mt-1 bg-white h-8 text-sm font-mono"
 data-testid={`org-billing-account-${org.id}`}
 />
 </div>
 <div>
 <Label className="text-zinc-500 text-[10px] uppercase tracking-wider">Sage 200 ref</Label>
 <Input
 value={(editingOrg?.id === org.id ? editingOrg.sage_customer_number : org.sage_customer_number) || ''}
 onChange={(e) => editingOrg?.id === org.id && setEditingOrg({ ...editingOrg, sage_customer_number: e.target.value })}
 onFocus={() => { if (!editingOrg || editingOrg.id !== org.id) openEditOrg(org); }}
 className="mt-1 bg-white h-8 text-sm font-mono"
 data-testid={`org-billing-sage-${org.id}`}
 />
 </div>
 </div>
 <p className="mt-3 text-[11px] text-zinc-400">
 Edits to the customer references are saved when you click Save Details on the Details tab.
 </p>
 </div>
 )}

{/* NEW Tab — Integrations (Iter 216h21).
    Per-org connection snapshot for Stripe Connect, Sicon, Orbit 4
    and Sage 200, with one-click jumps to the global consoles. */}
{isExpanded && expandedView === 'integrations' && (
<div className="bg-white" data-testid={`org-integrations-panel-${org.id}`}>
<OrgIntegrationsTab org={org} />
</div>
)}


 {/* NEW Tab — Audit log scoped to this org. */}
 {isExpanded && expandedView === 'audit' && (
 <div className="bg-white" data-testid={`org-audit-panel-${org.id}`}>
 <p className="text-xs text-zinc-500 mb-3">
 Master-admin events affecting <strong className="text-zinc-700">{org.name}</strong> in the last 30 days.
 </p>
 <OrgAuditLogTab orgId={org.id} />
 </div>
 )}

                </div>
              </SheetContent>
            </Sheet>
            )}
 </Card>
 );
 })}
 {displayOrgs.length === 0 && filteredOrgs.length > 0 && <p className="text-center text-zinc-400 py-12 text-sm">No organisations match your filters</p>}
 </div>

 {/* QW#5 — Archive Undo banner. Sits at the bottom of the screen for 5s
     after archiving an org. Click Undo to revert in place. */}
 {archivedToast && (
 <div
 className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 rounded-xl bg-zinc-900 text-white px-4 py-3 shadow-2xl border border-zinc-800 animate-in fade-in slide-in-from-bottom-2"
 role="status"
 data-testid="org-archive-undo-banner"
 >
 <Archive size={14} className="text-amber-300 shrink-0" />
 <span className="text-sm">
 Archived <strong>{archivedToast.name}</strong>
 </span>
 <button
 type="button"
 onClick={() => {
 onUpdateStatus(archivedToast.orgId, archivedToast.prevStatus || 'active');
 setArchivedToast(null);
 }}
 className="ml-2 inline-flex items-center gap-1.5 text-amber-300 hover:text-amber-200 font-bold text-sm"
 data-testid="org-archive-undo-btn"
 >
 <Undo2 size={13} /> Undo
 </button>
 <button
 type="button"
 onClick={() => setArchivedToast(null)}
 className="ml-1 text-zinc-400 hover:text-white"
 data-testid="org-archive-undo-dismiss"
 aria-label="Dismiss"
 >
 <X size={14} />
 </button>
 </div>
 )}

 {/* Create Organisation Dialog */}
 <Dialog open={showCreateOrg} onOpenChange={setShowCreateOrg}>
 <DialogContent className="bg-white border-zinc-200 text-zinc-900 max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="create-org-dialog">
 <DialogHeader><DialogTitle>Create Organisation</DialogTitle></DialogHeader>
 <div className="space-y-3 mt-2">
 <div className="grid grid-cols-2 gap-3">
 <div className="col-span-2">
 <Label className="text-zinc-600 text-xs">Organisation Name *</Label>
 <CompanyAutocomplete
   value={orgForm.name}
   onChange={(v) => setOrgForm({ ...orgForm, name: v })}
   onPick={(picked) => {
     const isCH = picked.source === 'companies_house';
     setOrgForm((f) => ({
       ...f,
       name: (isCH ? picked.company_name : picked.name) || f.name,
       phone: isCH ? f.phone : (picked.phone || f.phone),
       address_line1: picked.address_line1 || f.address_line1,
       address_line2: picked.address_line2 || f.address_line2,
       address_line3: picked.address_line3 || f.address_line3,
       city: picked.city || f.city,
       county: picked.county || f.county,
       postcode: picked.postcode || f.postcode,
       country: picked.country || f.country,
     }));
     notify.success(
       isCH ? 'Pre-filled from Companies House' : 'Pre-filled from existing org',
       isCH ? `${picked.company_name} · Co. ${picked.company_number}` : picked.name,
     );
   }}
   testIdPrefix="org-form-name-autocomplete"
   placeholder="Start typing — searches existing orgs + Companies House (UK)"
   inputClassName="mt-1"
 />
 </div>
 <div className="col-span-2">
 <Label className="text-zinc-600 text-xs">Modules</Label>
 {isModAccount(orgForm.account_type) ? (
   <div className="mt-1 flex items-center gap-2 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2.5" data-testid="org-form-mod-modules-locked">
     <Shield size={15} className="text-zinc-500" />
     <span className="text-sm text-zinc-700 font-medium">MOD Operations portal only</span>
     <span className="text-[10px] text-zinc-400 ml-auto">MOD organisations have no other modules</span>
   </div>
 ) : (
   <>
     <ModulesPicker
                value={orgForm.enabled_modules || modulesFromPortalType(orgForm.portal_type || 'service_portal')}
                onChange={(mods) => setOrgForm({ ...orgForm, enabled_modules: mods })}
                testIdPrefix="org-form-modules"
                isLite={orgForm.account_type === 'lite' || orgForm.subscription_tier === 'lite'}
              />
              <p className="text-[10px] text-zinc-400 mt-1.5">Pick every module the new organisation should have access to.</p>
   </>
 )}
 </div>
 <div>
 <Label className="text-zinc-600 text-xs">Platform</Label>
 <Select
   value={
     (orgForm.account_type === 'pulse_pro' || orgForm.account_type === 'lite') ? 'pulse'
     : (['mod_site','mod_branch','mod_org'].includes(orgForm.account_type)) ? 'mod'
     : 'gymaxis'
   }
   onValueChange={v => {
     // Iter 215eh / 216h109 — Platform is the brand. Pulse / Pulse Fitness / MOD.
     if (v === 'pulse') {
       setOrgForm({ ...orgForm, account_type: 'lite', subscription_tier: 'lite', enabled_modules: ['operations'], is_mod: false, mod_force: '' });
     } else if (v === 'mod') {
       setOrgForm({ ...orgForm, account_type: 'mod_site', subscription_tier: 'mod_site', is_mod: true, mod_force: orgForm.mod_force || 'army', enabled_modules: ['operations'], industry: MOD_FORCE_INDUSTRY[orgForm.mod_force || 'army'] });
     } else {
       setOrgForm({ ...orgForm, account_type: 'full', subscription_tier: 'starter', is_mod: false, mod_force: '' });
     }
   }}
 >
 <SelectTrigger className="mt-1" data-testid="org-form-account-type"><SelectValue /></SelectTrigger>
 <SelectContent className="bg-white border-zinc-200">
 <SelectItem value="gymaxis">Pulse Fitness</SelectItem>
 <SelectItem value="pulse">Pulse Fitness</SelectItem>
 <SelectItem value="mod">MOD (Ministry of Defence)</SelectItem>
 </SelectContent>
 </Select>
 </div>
 <div>
 <Label className="text-zinc-600 text-xs">Plan</Label>
 <Select
   value={
     // Map the form state into the plan-select value space.
     (orgForm.account_type === 'pulse_pro' || orgForm.account_type === 'lite')
       ? (orgForm.account_type === 'pulse_pro' ? 'pro' : 'lite')
       : (['mod_site','mod_branch','mod_org'].includes(orgForm.account_type)
           ? orgForm.account_type
           : (orgForm.subscription_tier || 'starter'))
   }
   onValueChange={v => {
     // Plan changes also rewrite account_type when the platform is
     // Pulse Fitness or MOD so the back-end keeps its existing enums.
     const isPulse = orgForm.account_type === 'pulse_pro' || orgForm.account_type === 'lite';
     const isMod = ['mod_site','mod_branch','mod_org'].includes(orgForm.account_type);
     if (isPulse) {
       const at = v === 'pro' ? 'pulse_pro' : 'lite';
       setOrgForm({ ...orgForm, account_type: at, subscription_tier: at });
     } else if (isMod || ['mod_site','mod_branch','mod_org'].includes(v)) {
       setOrgForm({ ...orgForm, account_type: v, subscription_tier: v, is_mod: true });
     } else {
       setOrgForm({ ...orgForm, subscription_tier: v });
     }
   }}
 >
 <SelectTrigger className="mt-1" data-testid="org-form-tier"><SelectValue /></SelectTrigger>
 <SelectContent className="bg-white border-zinc-200">
 {(orgForm.account_type === 'pulse_pro' || orgForm.account_type === 'lite') ? (
 <>
 <SelectItem value="lite">Lite</SelectItem>
 <SelectItem value="pro">Pro</SelectItem>
 </>
 ) : ['mod_site','mod_branch','mod_org'].includes(orgForm.account_type) ? (
 <>
 <SelectItem value="mod_site">MOD Site</SelectItem>
 <SelectItem value="mod_branch">MOD Branch (Catterick-level)</SelectItem>
 <SelectItem value="mod_org">MOD Head Office (Army / RAF / Navy)</SelectItem>
 </>
 ) : (
 <>
 <SelectItem value="starter">Starter</SelectItem>
 <SelectItem value="professional">Professional</SelectItem>
 <SelectItem value="enterprise">Enterprise</SelectItem>
 </>
 )}
 </SelectContent>
 </Select>
 </div>

 {/* Iter 216h109 — MOD Force selector. Only visible when Platform=MOD. */}
 {['mod_site','mod_branch','mod_org'].includes(orgForm.account_type) && (
   <div>
     <Label className="text-zinc-600 text-xs">MOD service</Label>
     <Select value={orgForm.mod_force || 'army'} onValueChange={v => setOrgForm({ ...orgForm, mod_force: v, industry: MOD_FORCE_INDUSTRY[v] })}>
       <SelectTrigger className="mt-1" data-testid="org-form-mod-force"><SelectValue /></SelectTrigger>
       <SelectContent className="bg-white border-zinc-200">
         <SelectItem value="army">British Army</SelectItem>
         <SelectItem value="raf">Royal Air Force</SelectItem>
         <SelectItem value="navy">Royal Navy</SelectItem>
       </SelectContent>
     </Select>
     <p className="text-[10px] text-zinc-400 mt-1">Sites and branches roll up to the matching Head Office.</p>
   </div>
 )}
 <div>
 <Label className="text-zinc-600 text-xs">Industry</Label>
 {isModAccount(orgForm.account_type) ? (
 <Input value={orgForm.industry || MOD_FORCE_INDUSTRY[orgForm.mod_force || 'army']} disabled className="mt-1 bg-zinc-50 text-zinc-600" data-testid="org-form-industry-mod" />
 ) : (
 <Select value={orgForm.industry || '_none'} onValueChange={v => setOrgForm({ ...orgForm, industry: v === '_none' ? '' : v })}>
 <SelectTrigger className="mt-1"><SelectValue placeholder="Select..." /></SelectTrigger>
 <SelectContent className="bg-white border-zinc-200">
 <SelectItem value="_none">Select...</SelectItem>
 {INDUSTRY_OPTIONS.map(i => <SelectItem key={i} value={i}>{i}</SelectItem>)}
 </SelectContent>
 </Select>
 )}
 </div>
 <div>
 <Label className="text-zinc-600 text-xs">Employees</Label>
 <Select value={orgForm.employee_count || '_none'} onValueChange={v => setOrgForm({ ...orgForm, employee_count: v === '_none' ? '' : v })}>
 <SelectTrigger className="mt-1"><SelectValue placeholder="Select..." /></SelectTrigger>
 <SelectContent className="bg-white border-zinc-200">
 <SelectItem value="_none">Select...</SelectItem>
 {EMPLOYEE_RANGES.map(r => <SelectItem key={r} value={r}>{r}</SelectItem>)}
 </SelectContent>
 </Select>
 </div>
 <div>
 <Label className="text-zinc-600 text-xs">Website</Label>
 <Input value={orgForm.website} onChange={e => setOrgForm({ ...orgForm, website: e.target.value })} placeholder="https://..." className="mt-1" />
 </div>
 <div>
 <Label className="text-zinc-600 text-xs">Phone</Label>
 <Input value={orgForm.phone} onChange={e => setOrgForm({ ...orgForm, phone: e.target.value })} className="mt-1" />
 </div>
 </div>
<p className="text-[10px] uppercase tracking-wider font-bold text-zinc-400 pt-1">Registered address</p>
<AddressFields
  value={orgForm}
  onChange={(addr) => setOrgForm({ ...orgForm, ...addr })}
  testIdPrefix="org-form-address"
  required={false}
/>
 <p className="text-[10px] uppercase tracking-wider font-bold text-zinc-400 pt-1">Primary Contact</p>
 <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
 <div>
 <Label className="text-zinc-600 text-xs">Name</Label>
 <Input value={orgForm.primary_contact_name} onChange={e => setOrgForm({ ...orgForm, primary_contact_name: e.target.value })} className="mt-1" />
 </div>
 <div>
 <Label className="text-zinc-600 text-xs">Email</Label>
 <Input value={orgForm.primary_contact_email} onChange={e => setOrgForm({ ...orgForm, primary_contact_email: e.target.value })} className="mt-1" />
 </div>
 <div>
 <Label className="text-zinc-600 text-xs">Phone</Label>
 <Input value={orgForm.primary_contact_phone} onChange={e => setOrgForm({ ...orgForm, primary_contact_phone: e.target.value })} className="mt-1" />
 </div>
 </div>
 <Button className="w-full" onClick={handleCreateOrg} disabled={creating || !orgForm.name.trim()} data-testid="org-form-submit">
 {creating ? <Loader2 size={14} className="animate-spin mr-1" /> : <Save size={14} className="mr-1" />} Create Organisation
 </Button>
 </div>
 </DialogContent>
 </Dialog>

 {/* Add User to Organisation Dialog */}
 <Dialog open={!!showAddUser} onOpenChange={() => { setShowAddUser(null); setLastInvite(null); }}>
 <DialogContent className="bg-white border-zinc-200 text-zinc-900 max-w-md" data-testid="add-user-dialog">
 <DialogHeader><DialogTitle>{lastInvite ? 'Invite link ready' : 'Add User to Organisation'}</DialogTitle></DialogHeader>
 {lastInvite ? (
 /* Iter 215ev — invite-link panel. Shown after creating a user in
    invite mode (no password set by admin). Admin copies link and
    sends manually until Resend DNS verification is live. */
 <div className="space-y-3 mt-2">
 <p className="text-sm text-zinc-600">
 <strong>{lastInvite.full_name}</strong> ({lastInvite.email}) was added. Send them this secure set-password link:
 </p>
 <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3 space-y-2">
 <div className="flex gap-2">
 <Input readOnly value={lastInvite.invite_url} className="bg-white font-mono text-[11px] flex-1" data-testid="add-user-invite-link" />
 <Button size="sm" variant="outline" className="shrink-0" onClick={async () => {
   try { await navigator.clipboard.writeText(lastInvite.invite_url); notify.success('Copied to clipboard'); } catch { notify.error('Copy failed'); }
 }} data-testid="add-user-invite-copy">Copy</Button>
 </div>
 <p className="text-[10px] text-zinc-500">Expires in 72 hours. Ship it via WhatsApp, SMS, email, Slack — the user will set their own password on first visit.</p>
 </div>
 <div className="flex gap-2 pt-2">
 <Button variant="outline" className="flex-1" onClick={() => { setLastInvite(null); }} data-testid="add-user-add-another">Add another</Button>
 <Button className="flex-1" onClick={() => { setShowAddUser(null); setLastInvite(null); }} data-testid="add-user-done">Done</Button>
 </div>
 </div>
 ) : (
 <div className="space-y-4 mt-2">
 <div>
 <Label className="text-zinc-600 text-xs">Email *</Label>
 <Input value={userForm.email} onChange={e => setUserForm({ ...userForm, email: e.target.value })} placeholder="user@company.com" className="mt-1" data-testid="add-user-email" />
 </div>
 <div>
 <Label className="text-zinc-600 text-xs">Full Name *</Label>
 <Input value={userForm.full_name} onChange={e => setUserForm({ ...userForm, full_name: e.target.value })} placeholder="John Smith" className="mt-1" data-testid="add-user-name" />
 </div>
 <div>
 <Label className="text-zinc-600 text-xs">Role</Label>
 <Select value={userForm.role} onValueChange={v => setUserForm({ ...userForm, role: v })}>
 <SelectTrigger className="mt-1" data-testid="add-user-role"><SelectValue /></SelectTrigger>
 <SelectContent className="bg-white border-zinc-200">
 <SelectItem value="owner">Owner</SelectItem>
 <SelectItem value="manager">Manager</SelectItem>
 <SelectItem value="staff">Staff</SelectItem>
 {/* Iter 236 — internal service engineer. Created in the service-portal
     users collection + auto-provisioned svc_engineers row, which
     unlocks the Engineer App (internal_engineer bypass — no Partner
     plan fee for direct employees). */}
 <SelectItem value="engineer">Engineer</SelectItem>
 {/* Iter 216k — Master Admin role granted from the per-org user
     dialog. Backend `add_user_to_organization` accepts `role`
     and sets is_master_admin=true on the user doc when the role
     is master_admin so the user gets full-platform access. */}
 <SelectItem value="master_admin">{masterAdminRoleLabel}</SelectItem>
 </SelectContent>
 </Select>
 {userForm.role === 'engineer' ? (
   <p className="text-[11px] text-blue-700 mt-1 bg-blue-50 border border-blue-200 rounded px-2 py-1.5 leading-snug" data-testid="add-user-engineer-hint">
     <strong>Engineer:</strong> internal service engineer for this organisation — gets the Engineer App (jobs, check sheets, van stock) automatically. No Partner-plan fee for direct employees.
   </p>
 ) : null}
 {userForm.role === 'master_admin' ? (
   <p className="text-[11px] text-amber-700 mt-1 bg-amber-50 border border-amber-200 rounded px-2 py-1.5 leading-snug" data-testid="add-user-master-admin-warning">
     {isPulseOrg
       ? <><strong>Pulse Master Admin:</strong> gets the Master Admin dashboard + organisation impersonation, scoped to Pulse Fitness data only.</>
       : <><strong>Heads up:</strong> a Master Admin can see and edit every organisation on the platform — only assign this to internal staff.</>}
   </p>
 ) : null}
 </div>
 {/* Iter 280 — Module Permissions at creation time. Mirrors the Edit-User
     drawer exactly so both views match. Owners / Master Admins always get
     every module (no picker). For Manager / Staff / Engineer we show one
     checkbox per org-enabled module; all default ON. Unticking stores
     module_overrides[key]=false which the backend persists on the new user. */}
 {(userForm.role === 'owner' || userForm.role === 'master_admin') ? (
   <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-3" data-testid="add-user-permissions-owner-note">
     <p className="text-xs font-bold uppercase tracking-wider text-amber-700 mb-1">Module Permissions</p>
     <p className="text-[11px] text-amber-800 leading-relaxed">
       {userForm.role === 'owner' ? 'Owners' : 'Master Admins'} always have access to every module the organisation has enabled.
     </p>
   </div>
 ) : (() => {
   const addOrg = (filteredOrgs || []).find(o => o.id === showAddUser);
   const orgModulesCfg = (addOrg?.modules) || {};
   const orgEnabledList = Array.isArray(addOrg?.enabled_modules) ? addOrg.enabled_modules : [];
   const MODULES = [
     { key: 'operations', label: 'Operations', desc: 'Service desk, equipment, faults' },
     { key: 'memberships', label: 'Memberships', desc: 'Members, classes, billing' },
     { key: 'marketing',  label: 'Marketing',   desc: 'Campaigns, segments, image library' },
     { key: 'crm',        label: 'CRM',         desc: 'Leads, deals, business pipeline' },
   ];
   const isOrgEnabled = (k) => {
     const cfg = orgModulesCfg[k];
     if (cfg && typeof cfg === 'object' && 'enabled' in cfg) return !!cfg.enabled;
     if (orgEnabledList.length) return orgEnabledList.includes(k);
     return k === 'operations';
   };
   const overrides = userForm.module_overrides || {};
   const visible = MODULES.filter(m => isOrgEnabled(m.key));
   if (visible.length === 0) {
     return (
       <div className="rounded-lg border border-zinc-200 bg-zinc-50/60 p-3" data-testid="add-user-permissions-empty">
         <p className="text-xs font-bold uppercase tracking-wider text-zinc-500 mb-1">Module Permissions</p>
         <p className="text-[11px] text-zinc-500">This organisation has no modules enabled to delegate.</p>
       </div>
     );
   }
   return (
     <div className="rounded-lg border border-zinc-200 bg-zinc-50/60 p-3 space-y-2" data-testid="add-user-permissions">
       <div>
         <p className="text-xs font-bold uppercase tracking-wider text-zinc-500">Module Permissions</p>
         <p className="text-[10px] text-zinc-400 leading-relaxed">Choose which modules this user can access. All on by default.</p>
       </div>
       <div className="space-y-1.5">
         {visible.map(m => {
           const checked = overrides[m.key] === undefined ? true : !!overrides[m.key];
           return (
             <label
               key={m.key}
               className="flex items-center justify-between gap-3 px-2 py-1.5 rounded-md hover:bg-white cursor-pointer"
               data-testid={`add-user-perm-row-${m.key}`}
             >
               <div className="min-w-0">
                 <p className="text-[12px] font-medium text-zinc-800">{m.label}</p>
                 <p className="text-[10px] text-zinc-400 truncate">{m.desc}</p>
               </div>
               <input
                 type="checkbox"
                 checked={checked}
                 onChange={(e) => {
                   const next = { ...overrides, [m.key]: e.target.checked };
                   setUserForm({ ...userForm, module_overrides: next });
                 }}
                 className="h-4 w-4 rounded border-zinc-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                 data-testid={`add-user-perm-${m.key}`}
               />
             </label>
           );
         })}
       </div>
     </div>
   );
 })()}
 {/* Iter 215ev — password field is now OPTIONAL. Leaving blank issues
     an invite link so the user sets their own password. This is the
     recommended flow (admin never handles plaintext). The admin can
     still override and set one manually if they want to provision
     a service-account-style credential. */}
 <div className="rounded-lg border border-blue-200 bg-blue-50/70 p-3 text-xs text-blue-900 flex gap-2">
 <ShieldCheck size={14} className="shrink-0 mt-0.5" />
 <div>
 <strong>Recommended:</strong> Leave password blank. The user will get a single-use invite link to set their own password — you never see or handle the plaintext.
 </div>
 </div>
 <details className="text-xs text-zinc-500">
 <summary className="cursor-pointer hover:text-zinc-700">Advanced: set a password manually</summary>
 <div className="mt-2">
 <Input type="password" value={userForm.password} onChange={e => setUserForm({ ...userForm, password: e.target.value })} placeholder="Min 12 chars (leave blank for invite link)" className="mt-1" data-testid="add-user-password" />
 </div>
 </details>
 <Button className="w-full" onClick={handleAddUser} disabled={addingUser || !userForm.email || !userForm.full_name} data-testid="add-user-submit">
 {addingUser ? <Loader2 size={14} className="animate-spin mr-1" /> : <UserPlus size={14} className="mr-1" />}
 {userForm.password ? 'Add User' : 'Add User & Generate Invite Link'}
 </Button>
 </div>
 )}
 </DialogContent>
 </Dialog>

 {/* Edit User Dialog */}
 <Dialog open={!!editingUser} onOpenChange={() => { setEditingUser(null); setLastResetTempPw(null); setLastInviteUrl(null); }}>
 <DialogContent className="bg-white border-zinc-200 max-w-md" data-testid="edit-user-dialog">
 <DialogHeader><DialogTitle>Edit User</DialogTitle></DialogHeader>
 {editingUser && (
 <div className="space-y-3">
 <div>
 <Label className="text-zinc-600 text-xs">Full Name</Label>
 <Input value={editingUser.full_name || ''} onChange={e => setEditingUser({ ...editingUser, full_name: e.target.value })} className="mt-1" data-testid="edit-user-name" />
 </div>
 <div>
 <Label className="text-zinc-600 text-xs">Email</Label>
 <Input value={editingUser.email || ''} onChange={e => setEditingUser({ ...editingUser, email: e.target.value })} className="mt-1" data-testid="edit-user-email" />
 </div>
 <div>
 <Label className="text-zinc-600 text-xs">Job Title</Label>
 <Input value={editingUser.job_title || ''} onChange={e => setEditingUser({ ...editingUser, job_title: e.target.value })} className="mt-1" data-testid="edit-user-job-title" />
 </div>
 <div>
 <Label className="text-zinc-600 text-xs">Phone</Label>
 <Input value={editingUser.phone || ''} onChange={e => setEditingUser({ ...editingUser, phone: e.target.value })} className="mt-1" data-testid="edit-user-phone" />
 </div>
 <div>
 <Label className="text-zinc-600 text-xs">Role</Label>
 <Select value={editingUser.role || 'staff'} onValueChange={v => setEditingUser({ ...editingUser, role: v })}>
 <SelectTrigger className="mt-1" data-testid="edit-user-role"><SelectValue /></SelectTrigger>
 <SelectContent className="bg-white border-zinc-200">
 <SelectItem value="owner">Owner</SelectItem>
 <SelectItem value="manager">Manager</SelectItem>
 <SelectItem value="staff">Staff</SelectItem>
 <SelectItem value="engineer">Engineer</SelectItem>
 <SelectItem value="master_admin">{masterAdminRoleLabel}</SelectItem>
 {editingUser.role === 'pulse_master_admin' && <SelectItem value="pulse_master_admin">Master Admin (Pulse)</SelectItem>}
 </SelectContent>
 </Select>
 {editingUser.role === 'engineer' ? (
   <p className="text-[11px] text-blue-700 mt-1 bg-blue-50 border border-blue-200 rounded px-2 py-1.5 leading-snug" data-testid="edit-user-engineer-hint">
     <strong>Engineer:</strong> saving provisions an active engineer record and unlocks the Engineer App for this user. Switching to another role deactivates it.
   </p>
 ) : null}
 {(editingUser.role === 'master_admin' || editingUser.role === 'pulse_master_admin') ? (
   <p className="text-[11px] text-amber-700 mt-1 bg-amber-50 border border-amber-200 rounded px-2 py-1.5 leading-snug">
     {isPulseOrg
       ? <><strong>Pulse Master Admin:</strong> gets the Master Admin dashboard + organisation impersonation, scoped to Pulse Fitness data. They keep their existing password.</>
       : <><strong>Heads up:</strong> save changes to elevate this user to platform-wide Master Admin access.</>}
   </p>
 ) : null}
 </div>

{/* Iter 216h16 — Site allocation (allowed_site_ids) for non-owner roles.
    Owners are exempt (they always see all sites). Master Admins are also
    exempt (platform-wide access). Persisted via the existing
    PATCH /master-admin/users/{id} endpoint which already accepts the
    `allowed_site_ids` field. */}
{(editingUser.role !== 'owner' && !editingUser.is_master_admin && editingUser.role !== 'master_admin') && (
  <div className="rounded-lg border border-zinc-200 bg-zinc-50/60 p-3" data-testid="edit-user-sites-panel">
    <div className="flex items-center justify-between mb-2">
      <p className="text-xs font-bold uppercase tracking-wider text-zinc-700">Site access</p>
      <span className="text-[10px] text-zinc-500">
        {((editingUser.allowed_site_ids || []).length === 0)
          ? 'All sites in org'
          : `${(editingUser.allowed_site_ids || []).length} pinned`}
      </span>
    </div>
    {editUserSitesLoading ? (
      <p className="text-[11px] text-zinc-500">Loading sites…</p>
    ) : editUserSites.length === 0 ? (
      <p className="text-[11px] text-zinc-500 italic">This org has no sites yet.</p>
    ) : (
      <>
        <div className="flex flex-wrap gap-1.5">
          {editUserSites.map((s) => {
            const pinned = (editingUser.allowed_site_ids || []).includes(s.id);
            return (
              <button
                type="button"
                key={s.id}
                onClick={() => {
                  const cur = editingUser.allowed_site_ids || [];
                  const next = pinned ? cur.filter((x) => x !== s.id) : [...cur, s.id];
                  setEditingUser({ ...editingUser, allowed_site_ids: next });
                }}
                className="text-xs px-2.5 py-1 rounded-full border transition-colors"
                style={{
                  borderColor: pinned ? '#0055FF' : '#e4e4e7',
                  background: pinned ? 'rgba(0,85,255,0.08)' : 'transparent',
                  color: pinned ? '#0055FF' : '#27272a',
                  fontWeight: pinned ? 600 : 400,
                }}
                data-testid={`edit-user-site-pick-${s.id}`}
              >
                {s.is_head_office ? '★ ' : ''}{s.name}{pinned ? ' ✓' : ''}
              </button>
            );
          })}
        </div>
        <p className="text-[10px] text-zinc-500 mt-2 leading-snug">
          Leave empty for full org-wide access. Selecting sites locks this teammate to those sites only. Owners + Master Admins always see every site.
        </p>
      </>
    )}
  </div>
)}


{/* Iter 216a — Per-User Feature Editor.
    Lets Master Admins / Site Owners revoke access to specific modules
    on a per-user basis. Owners + master admins are exempt (their access
    can never be limited from this UI; this is enforced server-side in
    utils/module_access.py:resolve_module_access). For Manager/Staff
    rows we show one switch per *org-enabled* module. Default state =
    full access (no override stored). Toggling OFF stores
    `module_overrides[key] = false` which the resolver respects. */}
{(() => {
  if (editingUser.role === 'owner' || editingUser.is_master_admin) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-3" data-testid="edit-user-permissions-owner-note">
        <p className="text-xs font-bold uppercase tracking-wider text-amber-700 mb-1">Permissions</p>
        <p className="text-[11px] text-amber-800 leading-relaxed">
          Owners always have access to every module the organisation has enabled.
          To restrict a teammate, change their role to Manager or Staff first.
        </p>
      </div>
    );
  }
  const orgForUser = (filteredOrgs || []).find(o => o.id === editingUser.organization_id);
  const orgModulesCfg = (orgForUser?.modules) || {};
  const orgEnabledList = Array.isArray(orgForUser?.enabled_modules) ? orgForUser.enabled_modules : [];
  const MODULES = [
    { key: 'operations', label: 'Operations', desc: 'Service desk, equipment, faults' },
    { key: 'memberships', label: 'Memberships', desc: 'Members, classes, billing' },
    { key: 'marketing',  label: 'Marketing',   desc: 'Campaigns, segments, image library' },
    { key: 'crm',        label: 'CRM',         desc: 'Leads, deals, business pipeline' },
  ];
  const isOrgEnabled = (k) => {
    const cfg = orgModulesCfg[k];
    if (cfg && typeof cfg === 'object' && 'enabled' in cfg) return !!cfg.enabled;
    if (orgEnabledList.length) return orgEnabledList.includes(k);
    return k === 'operations';
  };
  const overrides = editingUser.module_overrides || {};
  const visible = MODULES.filter(m => isOrgEnabled(m.key));
  if (visible.length === 0) {
    return (
      <div className="rounded-lg border border-zinc-200 bg-zinc-50/60 p-3" data-testid="edit-user-permissions-empty">
        <p className="text-xs font-bold uppercase tracking-wider text-zinc-500 mb-1">Permissions</p>
        <p className="text-[11px] text-zinc-500">Organisation has no modules enabled to delegate.</p>
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-zinc-200 bg-zinc-50/60 p-3 space-y-2" data-testid="edit-user-permissions">
      <div>
        <p className="text-xs font-bold uppercase tracking-wider text-zinc-500">Module Permissions</p>
        <p className="text-[10px] text-zinc-400 leading-relaxed">Toggle off to revoke this user's access to a module. Org-level access is required first.</p>
      </div>
      <div className="space-y-1.5">
        {visible.map(m => {
          const checked = overrides[m.key] === undefined ? true : !!overrides[m.key];
          return (
            <label
              key={m.key}
              className="flex items-center justify-between gap-3 px-2 py-1.5 rounded-md hover:bg-white cursor-pointer"
              data-testid={`edit-user-perm-row-${m.key}`}
            >
              <div className="min-w-0">
                <p className="text-[12px] font-medium text-zinc-800">{m.label}</p>
                <p className="text-[10px] text-zinc-400 truncate">{m.desc}</p>
              </div>
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) => {
                  const next = { ...overrides, [m.key]: e.target.checked };
                  setEditingUser({ ...editingUser, module_overrides: next });
                }}
                className="h-4 w-4 rounded border-zinc-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                data-testid={`edit-user-perm-${m.key}`}
              />
            </label>
          );
        })}
      </div>
    </div>
  );
})()}


 {/* Iter 215bi — in-dialog credentials panel.
     Replaces the global persistent toast that was blocking the side
     drawer. Reset → fresh temp password lands right here, copyable,
     until the dialog closes.

     Iter 216k — explicitly surface the target email above both
     buttons so the operator never sends a reset to the wrong inbox,
     and rename "Reset Password" → "Reset Link" to make it clear it
     generates a copy-able URL (not a temp password). The legacy
     temp-password flow stays as a fallback under "Generate temp
     password" for emergencies. */}
 <div className="rounded-lg border border-zinc-200 bg-zinc-50/60 p-3 space-y-2" data-testid="edit-user-credentials">
 <div className="flex items-center justify-between">
 <p className="text-xs font-bold uppercase tracking-wider text-zinc-500">Login credentials</p>
 <div className="flex items-center gap-1">
 <Button
 type="button"
 size="sm"
 variant="ghost"
 className="h-6 text-[11px] text-emerald-700 hover:bg-emerald-50"
 onClick={async () => {
   try {
     const tk = localStorage.getItem('token');
     const r = await axios.post(`${API}/master-admin/users/${editingUser.id}/invite-link`, {}, { headers: { Authorization: `Bearer ${tk}` } });
     const url = r.data?.invite_url;
     if (url) {
       setLastInviteUrl(url);
       try { await navigator.clipboard.writeText(url); } catch { /* noop */ }
       notify.success('Reset link ready', `Copied to clipboard · send to ${editingUser.email}`, { ttl: 6000 });
     }
   } catch (err) {
      
     console.error('[invite-link] failed', err?.response?.status, err?.response?.data, err);
     notifyApiError(notify, err, 'Failed to generate reset link');
   }
 }}
 data-testid="edit-user-inline-invite-link"
 >
 <Mail size={12} className="mr-1" /> Reset Link
 </Button>
 <Button
 type="button"
 size="sm"
 variant="ghost"
 className="h-6 text-[11px] text-blue-600 hover:bg-blue-50"
 onClick={async () => {
 try {
 const tk = localStorage.getItem('token');
 const r = await axios.put(`${API}/master-admin/users/${editingUser.id}/reset-password`, {}, { headers: { Authorization: `Bearer ${tk}` } });
 const pw = r.data?.temp_password;
 if (pw) {
 setLastResetTempPw(pw);
 try { await navigator.clipboard.writeText(pw); } catch { /* noop */ }
 notify.success('Temp password ready', `Copied to clipboard · send to ${editingUser.email}`, { ttl: 6000 });
 }
 } catch (err) {
  
 console.error('[reset-password] failed', err?.response?.status, err?.response?.data, err);
 // Fall back to the reset-link path automatically — that's the
 // safer, equivalent flow and works even when temp_password
 // generation is blocked (eg. invite-mode users without a hash).
 try {
   const tk2 = localStorage.getItem('token');
   const r2 = await axios.post(`${API}/master-admin/users/${editingUser.id}/invite-link`, {}, { headers: { Authorization: `Bearer ${tk2}` } });
   if (r2.data?.invite_url) {
     setLastInviteUrl(r2.data.invite_url);
     try { await navigator.clipboard.writeText(r2.data.invite_url); } catch { /* noop */ }
     notify.warning('Used reset link instead', `Temp-password failed; copied a reset link for ${editingUser.email}`, { ttl: 7000 });
     return;
   }
 } catch { /* fall through to error toast */ }
 notifyApiError(notify, err, 'Failed to reset password');
 }
 }}
 data-testid="edit-user-inline-reset-pw"
 >
 <KeyRound size={12} className="mr-1" /> Temp Password
 </Button>
 </div>
 </div>
 <div className="rounded-md border border-blue-200 bg-blue-50/60 px-2.5 py-1.5">
   <p className="text-[10px] uppercase tracking-wider font-bold text-blue-700">Reset destination</p>
   <p className="text-[12px] text-blue-900 break-all">
     <span className="font-mono">{editingUser.email}</span>
   </p>
 </div>
 {lastResetTempPw && (
 <div className="rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-2 flex items-center gap-2" data-testid="edit-user-temp-pw-banner">
 <KeyRound size={12} className="text-emerald-700 shrink-0" />
 <code className="text-[12px] font-mono text-emerald-900 break-all flex-1">{lastResetTempPw}</code>
 <Button
 type="button"
 size="sm"
 variant="ghost"
 className="h-6 px-2 text-[10px] text-emerald-700 hover:bg-emerald-100"
 onClick={async () => { try { await navigator.clipboard.writeText(lastResetTempPw); notify.success('Copied'); } catch { /* noop */ } }}
 data-testid="edit-user-temp-pw-copy"
 >
 Copy
 </Button>
 </div>
 )}
 {lastInviteUrl && (
 <div className="rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-2 flex items-center gap-2" data-testid="edit-user-invite-link-banner">
 <Mail size={12} className="text-emerald-700 shrink-0" />
 <code className="text-[11px] font-mono text-emerald-900 break-all flex-1">{lastInviteUrl}</code>
 <Button
 type="button"
 size="sm"
 variant="ghost"
 className="h-6 px-2 text-[10px] text-emerald-700 hover:bg-emerald-100"
 onClick={async () => { try { await navigator.clipboard.writeText(lastInviteUrl); notify.success('Copied'); } catch { /* noop */ } }}
 data-testid="edit-user-invite-link-copy"
 >
 Copy
 </Button>
 </div>
 )}
 <p className="text-[10px] text-zinc-400">User will be forced to change this on next sign-in.</p>
 </div>

 <Button className="w-full" disabled={savingUser} data-testid="save-user-edit-btn"
 onClick={async () => {
 setSavingUser(true);
 if (onEditUser) await onEditUser(editingUser.id, { full_name: editingUser.full_name, email: editingUser.email, role: editingUser.role, job_title: editingUser.job_title, phone: editingUser.phone, module_overrides: editingUser.module_overrides });
 setSavingUser(false);
 setEditingUser(null);
 setLastResetTempPw(null);
 }}>
 {savingUser ? <Loader2 size={14} className="animate-spin mr-1" /> : <Save size={14} className="mr-1" />} Save Changes
 </Button>
 </div>
 )}
 </DialogContent>
 </Dialog>

 {/* Branded Email Preview dialog */}
 <Dialog open={!!emailPreviewOrg} onOpenChange={(o) => { if (!o) { setEmailPreviewOrg(null); setEmailPreviewTo(''); setEmailPreviewKind('comment'); } }}>
 <DialogContent className="max-w-md" data-testid="email-preview-dialog">
 <DialogHeader>
 <DialogTitle className="flex items-center gap-2">
 <Mail size={16} className="text-indigo-600" />
 Send branded email preview
 </DialogTitle>
 </DialogHeader>
 {emailPreviewOrg && (
 <div className="space-y-4">
 <div className="bg-zinc-50 border border-zinc-200 rounded-lg p-3 text-xs text-zinc-700">
 <p>
 Sends a sample email using <strong className="text-zinc-900">{emailPreviewOrg.name}</strong>'s branding.
 </p>
 <p className="mt-1">
 Platform footer shown: <strong className="text-zinc-900">
 {['pulse_pro', 'lite'].includes(emailPreviewOrg.account_type) ? 'Pulse Fitness' : 'Pulse Fitness AI'}
 </strong>
 </p>
 </div>

 <div>
 <Label className="text-xs text-zinc-700">Template to preview</Label>
 <div className="grid grid-cols-1 gap-2 mt-2">
 {[
 { value: 'comment', label: '2-way conversation', desc: 'New comment posted on a live fault' },
 { value: 'engineer_callout', label: 'Engineer callout', desc: 'Initial email when a fault is escalated to a supplier' },
 { value: 'supplier_welcome', label: 'Supplier welcome', desc: 'Onboarding email sent when a supplier is first added' },
 ].map((t) => {
 const selected = emailPreviewKind === t.value;
 return (
 <button
 key={t.value}
 type="button"
 onClick={() => setEmailPreviewKind(t.value)}
 className={`text-left p-3 rounded-lg border-2 transition-colors ${selected
 ? 'border-indigo-500 bg-indigo-50'
 : 'border-zinc-200 bg-white hover:border-zinc-400'}`}
 data-testid={`email-preview-kind-${t.value}`}
 >
 <div className="flex items-center gap-2">
 <span className={`w-3.5 h-3.5 rounded-full border-2 flex-shrink-0 ${selected
 ? 'border-indigo-600 bg-indigo-600 ring-2 ring-indigo-200'
 : 'border-zinc-400'}`} />
 <p className="text-sm font-semibold text-zinc-900">{t.label}</p>
 </div>
 <p className="text-[11px] text-zinc-600 mt-1 ml-5">{t.desc}</p>
 </button>
 );
 })}
 </div>
 </div>

 <div>
 <Label className="text-xs text-zinc-700">Send preview to</Label>
 <Input
 value={emailPreviewTo}
 onChange={(e) => setEmailPreviewTo(e.target.value)}
 placeholder="your@email.com (leave blank to send to your own admin email)"
 className="mt-1"
 data-testid="email-preview-to-input"
 />
 <p className="text-[11px] text-zinc-500 mt-1">
 Nothing is created on the customer's account — this is a preview only.
 </p>
 </div>

 <div className="flex items-center justify-end gap-2 pt-2">
 <Button
 variant="ghost"
 onClick={() => { setEmailPreviewOrg(null); setEmailPreviewTo(''); setEmailPreviewKind('comment'); }}
 data-testid="email-preview-cancel"
 >Cancel</Button>
 <Button
 className="bg-indigo-600 hover:bg-indigo-700 text-white"
 disabled={sendingPreview}
 onClick={async () => {
 setSendingPreview(true);
 const r = await onSendEmailPreview(emailPreviewOrg.id, emailPreviewTo.trim(), emailPreviewKind);
 setSendingPreview(false);
 if (r) { setEmailPreviewOrg(null); setEmailPreviewTo(''); setEmailPreviewKind('comment'); }
 }}
 data-testid="email-preview-send"
 >
 {sendingPreview ? <Loader2 size={14} className="animate-spin mr-1" /> : <Mail size={14} className="mr-1" />}
 Send preview
 </Button>
 </div>
 </div>
 )}
 </DialogContent>
 </Dialog>

 {/* Hard delete user — type-to-confirm */}
 <HardDeleteUserDialog
 open={!!hardDeleteTarget}
 user={hardDeleteTarget}
 onClose={() => setHardDeleteTarget(null)}
 onConfirm={onHardDeleteUser}
 />
 </div>
 );
};

export { HardDeleteUserDialog };
export default AdminOrganizations;
