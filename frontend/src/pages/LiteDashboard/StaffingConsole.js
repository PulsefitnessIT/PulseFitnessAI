/**
 * StaffingConsole — workforce intelligence dashboard.
 *
 * Role-gated: managers/owners see every tab (Rota, Staff, Leave, Market,
 * Performance, Payroll, Live Floor, Rules, Announcements, AI). Staff
 * see a reduced set (My Shifts, My Leave, Open Shifts, Swap Requests,
 * Announcements read-only, Live Floor).
 *
 * Two mount points:
 *   - Operations → 'Staffing' tab for managers/owners (full view)
 *   - Operations → 'Gym Floor' tab for staff (same component, role-gated)
 *
 * All data fetched from /api/staffing/* — role filtering is enforced
 * server-side; the frontend just hides UI the user can't use.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import {
  Users, Calendar, UserPlus, Plane, ShoppingBag, BarChart3, PoundSterling,
  Eye, Shield, Megaphone, Sparkles, Trash2,
  ChevronLeft, ChevronRight, Clock, AlertTriangle, Download, RefreshCw,
  LayoutDashboard, Layers, Activity, Timer, MessageSquare, ClipboardList,
  IdCard, Wand2, ArrowRightLeft, Wallet, Network,
  // Iter 216h264 — staff portal preview + credentials issuance
  ExternalLink, KeyRound, Loader2, Copy, Check, X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/App';
import PillTabBar from '@/components/shared/PillTabBar';
import PageHeader from '@/components/shared/PageHeader';
import WorkforceDashboardTab from '@/pages/LiteDashboard/staffing/WorkforceDashboardTab';
import ShiftTemplatesTab from '@/pages/LiteDashboard/staffing/ShiftTemplatesTab';
import TimeClockTab from '@/pages/LiteDashboard/staffing/TimeClockTab';
import MyClockTab from '@/pages/LiteDashboard/staffing/MyClockTab';
import CommsTab from '@/pages/LiteDashboard/staffing/CommsTab';
import OperationsTab from '@/pages/LiteDashboard/staffing/OperationsTab';
import HRTab from '@/pages/LiteDashboard/staffing/HRTab';
import StaffOnboarding from '@/pages/LiteDashboard/staffing/StaffOnboarding';
import TeamAccessTab from '@/pages/LiteDashboard/staffing/TeamAccessTab';
import OrgChartTab from '@/pages/LiteDashboard/staffing/orgchart/OrgChartTab';
import AIWorkforceTab from '@/pages/LiteDashboard/staffing/AIWorkforceTab';
import MODStaffTransferTab from '@/pages/LiteDashboard/staffing/MODStaffTransferTab';
import MODStaffTab from '@/pages/LiteDashboard/staffing/MODStaffTab';
import SiteStaffManager from '@/pages/LiteDashboard/staffing/SiteStaffManager';
import DeskExpenses from '@/pages/ServiceDesk/DeskExpenses';
import ProductTour from '@/components/shared/ProductTour';
import { useLocalization, formatMoneySync, getCachedLocalization } from '@/utils/localization';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Iter 279c — job roles are stored as lower_snake tokens; show them as
// proper Title Case ("sales_manager" → "Sales Manager").
function humanizeRole(role) {
  if (!role) return '—';
  return String(role).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

// Iter 279d — Staffing nav condensed into logical GROUPS with nested
// sub-tabs (was a flat 18-pill strip). Nothing is removed — features
// are regrouped so the bar is shorter and reads top-to-bottom in a
// natural workflow order. Each leaf keeps its original id (so deep
// state / data-testids stay stable) and its own role gate.
const MGR = ['owner', 'manager', 'master_admin'];
const ALL = ['owner', 'manager', 'master_admin', 'staff'];

const GROUPS_ALL = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, leaf: 'dashboard', roles: MGR },
  // People = Staff roster + HR records combined. Per user, the old standalone
  // "Staff" tab was merged into HR (HRTab now has Add-staff); the other People
  // options are unchanged.
  { id: 'people', label: 'People', icon: Users, children: [
    { id: 'hr',       label: 'HR',        icon: IdCard,  roles: MGR },
    { id: 'onboarding', label: 'Staff Onboarding', icon: UserPlus, roles: MGR },
    { id: 'orgchart', label: 'Org Chart', icon: Network, roles: MGR },
    { id: 'team-access', label: 'Team Access', icon: KeyRound, roles: MGR },
    { id: 'site-access', label: 'Site Login', icon: KeyRound, roles: MGR },
  ] },
  // Rota = everything schedule-related.
  { id: 'rota', label: 'Rota', icon: Calendar, children: [
    { id: 'rota',      label: 'Schedule',     icon: Calendar,    roles: MGR },
    { id: 'templates', label: 'Templates',    icon: Layers,      roles: MGR },
    { id: 'leave',     label: 'Time Off',     icon: Plane,       roles: ALL },
    { id: 'market',    label: 'Shift Market', icon: ShoppingBag, roles: ALL },
    { id: 'live',      label: 'Live Floor',   icon: Eye,         roles: ALL },
    { id: 'ai-rota',   label: 'AI Rota',      icon: Wand2,       roles: MGR },
  ] },
  // Time Clock = manager team clock + the staff member's own clock.
  { id: 'timeclock', label: 'Time Clock', icon: Activity, children: [
    { id: 'timeclock', label: 'Team Clock', icon: Activity, roles: MGR },
    { id: 'myclock',   label: 'My Clock',   icon: Timer,    roles: ['staff'] },
  ] },
  // Performance = overview metrics + AI insights (combined per request).
  { id: 'performance', label: 'Performance', icon: BarChart3, children: [
    { id: 'performance', label: 'Overview',    icon: BarChart3, roles: MGR },
    { id: 'ai',          label: 'AI Insights', icon: Sparkles,  roles: MGR },
  ] },
  { id: 'payroll',  label: 'Payroll',  icon: PoundSterling, leaf: 'payroll',  roles: MGR },
  // Expenses moved in from the Operations bar, right after Payroll.
  { id: 'expenses', label: 'Expenses', icon: Wallet,        leaf: 'expenses', roles: MGR },
  // Comms = Announcements + Handover Diary (combined per request).
  { id: 'comms', label: 'Comms', icon: MessageSquare, children: [
    { id: 'announce', label: 'Announcements',  icon: Megaphone,     roles: ALL },
    { id: 'comms',    label: 'Handover Diary', icon: MessageSquare, roles: ALL },
  ] },
  { id: 'operations', label: 'Ops · Forms', icon: ClipboardList, leaf: 'operations', roles: ALL },
  { id: 'rules',      label: 'Rules',       icon: Shield,        leaf: 'rules',      roles: MGR },
];


export default function StaffingConsole() {
  const { t } = useTranslation();
  const { user } = useAuth();
  useLocalization();  // warm currency cache
  // Translate a nav label by a slug derived from its English text.
  const trLabel = useCallback((s) => t(
    `staffing.nav_${String(s).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')}`,
    s,
  ), [t]);
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  // Iter 216h264 — when a manager opens this console with ?as=staff
  // we want to render the exact tab set a staff member would see
  // (no payroll, no HR, etc.). The actual user object is untouched
  // so API calls still authenticate as the manager — the preview is
  // purely a frontend role-gate filter.
  const previewAsStaff = typeof window !== 'undefined'
    && new URLSearchParams(window.location.search).get('as') === 'staff';
  const role = useMemo(() => {
    if (previewAsStaff) return 'staff';
    if (user?.is_master_admin || user?.is_pulse_admin) return 'master_admin';
    const r = (user?.role || '').toLowerCase();
    return ['owner','manager','staff','gym_floor'].includes(r) ? r : 'staff';
  }, [user, previewAsStaff]);
  const isManager = !previewAsStaff && (role === 'owner' || role === 'manager' || role === 'master_admin');
  const isMOD = ['mod_site', 'mod_branch', 'mod_org'].includes(user?.account_type);

  // Build the visible group tree for this role. MOD tenants only get a
  // Staff roster + Transfers (everything else is managed out-of-band).
  const groups = useMemo(() => {
    if (isMOD) {
      return [
        { id: 'staff', label: trLabel('Staff'), icon: Users, leaf: 'staff' },
        { id: 'mod-transfer', label: trLabel('Transfers'), icon: ArrowRightLeft, leaf: 'mod-transfer' },
        { id: 'comms', label: trLabel('Handover Diary'), icon: MessageSquare, leaf: 'comms' },
      ];
    }
    const childOK = (c) => c.roles.includes(role);
    const list = GROUPS_ALL
      .map((g) => {
        if (g.children) {
          const kids = g.children.filter(childOK).map((c) => ({ ...c, label: trLabel(c.label) }));
          return kids.length ? { ...g, label: trLabel(g.label), children: kids } : null;
        }
        return g.roles.includes(role) ? { ...g, label: trLabel(g.label) } : null;
      })
      .filter(Boolean);
    // Staff use Comms (handover diary) at shift change-over, so surface it first.
    if (role === 'staff') {
      const idx = list.findIndex((g) => g.id === 'comms');
      if (idx > 0) { const [c] = list.splice(idx, 1); list.unshift(c); }
    }
    return list;
  }, [role, isMOD, trLabel]);

  // Flatten to leaf ids so we can map a leaf → its parent group.
  const leafToGroup = useMemo(() => {
    const m = {};
    groups.forEach((g) => {
      if (g.children) g.children.forEach((c) => { m[c.id] = g.id; });
      else m[g.leaf] = g.id;
    });
    return m;
  }, [groups]);

  const firstLeaf = (g) => (g?.children ? g.children[0]?.id : g?.leaf);
  // Iter 279e — remember the manager's last Staffing tab across reloads
  // (per user, so shared browsers don't collide).
  const storageKey = `staffing.activeLeaf:${user?.id || 'anon'}`;
  const [tab, setTab] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem(storageKey);
      if (saved === 'staff' && !isMOD) return 'hr';  // merged Staff → HR (gym tenants only)
      if (saved) return saved;
    }
    return firstLeaf(groups[0]) || 'leave';
  });

  // Keep `tab` valid when the role-filtered tree changes.
  useEffect(() => {
    // Gym tenants merged the old "Staff" leaf into "HR"; MOD tenants keep a
    // real "staff" leaf, so only migrate when `staff` isn't a valid leaf
    // (otherwise staff↔hr ping-pong remounts the tab forever).
    if (tab === 'staff' && !leafToGroup.staff) { setTab('hr'); return; }
    if (!leafToGroup[tab]) setTab(firstLeaf(groups[0]) || 'leave');
  }, [groups, leafToGroup, tab]);

  // Persist the active leaf whenever it's valid for this role.
  useEffect(() => {
    if (leafToGroup[tab] && typeof window !== 'undefined') {
      localStorage.setItem(storageKey, tab);
    }
  }, [tab, leafToGroup, storageKey]);

  const activeGroup = groups.find((g) => g.id === leafToGroup[tab]) || groups[0];
  const subTabs = activeGroup?.children || [];

  const selectGroup = (g) => {
    // Jump to the group's first leaf unless the active leaf already lives
    // inside it (so re-clicking the parent doesn't lose your sub-tab).
    if (leafToGroup[tab] === g.id) return;
    setTab(firstLeaf(g));
  };

  return (
    <div className="space-y-5 pulse-font-body" data-testid="staffing-console">
      <ProductTour variant="staffing" />
      {previewAsStaff && (
        <div
          className="rounded-xl border px-4 py-2 flex items-center justify-between gap-3 text-xs"
          style={{ borderColor: 'var(--color-brand-cyan)', background: 'rgba(25,205,255,0.08)', color: 'var(--color-brand-cyan)' }}
          data-testid="staff-portal-preview-banner"
        >
          <span className="font-semibold inline-flex items-center gap-1.5">
            <Eye size={12} /> {t('staffing.sc_preview_banner', "Previewing the staff portal — managers' tabs are hidden.")}
          </span>
          <a
            href="?"
            className="font-semibold underline"
            onClick={(e) => {
              e.preventDefault();
              const u = new URL(window.location.href);
              u.searchParams.delete('as');
              window.location.href = u.toString();
            }}
          >{t('staffing.sc_exit_preview', 'Exit preview')}</a>
        </div>
      )}
      <PageHeader
        title={isManager ? t('staffing.sc_title_mgr', 'Staffing') : t('staffing.sc_title_staff', 'My shifts')}
        subtitle={isManager
          ? t('staffing.sc_subtitle_mgr', 'Rota, performance, payroll, and AI workforce optimisation.')
          : t('staffing.sc_subtitle_staff', 'Your shifts, time off, and open shifts you can claim.')}
        icon={Users}
        helpId={isManager ? 'staffing-overview' : 'staffing-marketplace'}
        testId="staffing-header"
        actions={!isManager ? (
          <div className="text-[10px] font-semibold uppercase tracking-[0.18em] px-3 py-1 rounded-full" style={{ background: 'rgba(25,205,255,0.1)', color: 'var(--color-brand-cyan)' }} data-testid="staffing-staff-badge">
            {t('staffing.sc_staff_view', 'Staff view')}
          </div>
        ) : null}
      />

      {/* Primary group bar */}
      <PillTabBar
        activeId={activeGroup?.id}
        testId="staffing-tabs"
        ariaLabel={t('staffing.sc_sections_aria', 'Staffing sections')}
      >
        {groups.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            data-pill-id={id}
            onClick={() => selectGroup(groups.find((g) => g.id === id))}
            className="flex-shrink-0 inline-flex items-center gap-2 px-4 py-2.5 rounded-full text-sm font-semibold transition-colors whitespace-nowrap"
            style={activeGroup?.id === id
              ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
              : { color: 'var(--theme-text-muted)', background: 'transparent' }}
            data-testid={`staffing-tab-${id}`}
          >
            <Icon size={14} /> {label}
          </button>
        ))}
      </PillTabBar>

      {/* Secondary sub-tab bar (only when the active group has children) */}
      {subTabs.length > 0 && (
        <div
          className="flex items-center gap-1.5 flex-wrap -mt-2"
          data-testid="staffing-subtabs"
        >
          {subTabs.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors whitespace-nowrap border"
              style={tab === id
                ? { background: 'rgba(25,205,255,0.12)', color: 'var(--color-brand-cyan)', borderColor: 'var(--color-brand-cyan)' }
                : { color: 'var(--theme-text-muted)', background: 'transparent', borderColor: 'var(--theme-border)' }}
              data-testid={`staffing-subtab-${id}`}
            >
              <Icon size={12} /> {label}
            </button>
          ))}
        </div>
      )}

      <div>
        {tab === 'dashboard'   && <WorkforceDashboardTab headers={headers} />}
        {tab === 'rota'        && <RotaTab        headers={headers} isManager={isManager} />}
        {tab === 'templates'   && <ShiftTemplatesTab  headers={headers} isManager={isManager} />}
        {tab === 'timeclock'   && <TimeClockTab   headers={headers} />}
        {tab === 'myclock'     && <MyClockTab     headers={headers} />}
        {tab === 'staff'       && (isMOD ? <MODStaffTab headers={headers} /> : <StaffTab headers={headers} />)}
        {tab === 'site-access' && <SiteStaffManager headers={headers} />}
        {tab === 'leave'       && <LeaveTab       headers={headers} isManager={isManager} />}
        {tab === 'market'      && <MarketTab      headers={headers} isManager={isManager} />}
        {tab === 'performance' && <PerformanceTab headers={headers} />}
        {tab === 'payroll'     && <PayrollTab     headers={headers} />}
        {tab === 'expenses'    && <DeskExpenses />}
        {tab === 'live'        && <LiveFloorTab   headers={headers} />}
        {tab === 'rules'       && <RulesTab       headers={headers} />}
        {tab === 'announce'    && <AnnouncementsTab headers={headers} isManager={isManager} />}
        {tab === 'comms'       && <CommsTab        headers={headers} isManager={isManager} />}
        {tab === 'operations'  && <OperationsTab   headers={headers} isManager={isManager} />}
        {tab === 'hr'          && <HRTab           headers={headers} isManager={isManager} />}
        {tab === 'onboarding'  && <StaffOnboarding headers={headers} />}
        {tab === 'team-access' && <TeamAccessTab   headers={headers} />}
        {tab === 'orgchart'    && <OrgChartTab />}
        {tab === 'ai-rota'     && <AIWorkforceTab  headers={headers} />}
        {tab === 'ai'          && <AIInsightsTab  headers={headers} />}
        {tab === 'mod-transfer' && <MODStaffTransferTab headers={headers} />}
      </div>
    </div>
  );
}

// ───────────────────────────── Tabs ─────────────────────────────

function Card({ children, testId }) {
  return (
    <div
      className="rounded-2xl p-4 border"
      style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
      data-testid={testId}
    >{children}</div>
  );
}

function EmptyState({ icon: Icon, title, hint, testId }) {
  return (
    <div className="rounded-2xl p-10 border text-center" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} data-testid={testId}>
      <Icon size={22} style={{ color: 'var(--theme-text-muted)' }} className="mx-auto mb-2" />
      <div className="text-sm font-semibold pulse-font-heading mb-1" style={{ color: 'var(--theme-text)' }}>{title}</div>
      {hint && <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{hint}</div>}
    </div>
  );
}

// ─── Rota (drag-and-drop week view, manager only) ───
function RotaTab({ headers, isManager }) {
  const { t } = useTranslation();
  const [weekStart, setWeekStart] = useState(() => {
    const d = new Date(); d.setHours(0, 0, 0, 0);
    d.setDate(d.getDate() - d.getDay() + 1); // Monday
    return d.toISOString().slice(0, 10);
  });
  const [shifts, setShifts] = useState([]);
  const [staff, setStaff] = useState([]);
  const [conflicts, setConflicts] = useState([]); // [{shift_id, reason, severity}]
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState(null); // { staff_id, date }
  // Phase S1 — drag/drop state
  const [dragging, setDragging] = useState(null);   // shift_id
  const [dropTarget, setDropTarget] = useState(null); // `${staff_id}|${date}`

  const days = useMemo(() => {
    const start = new Date(weekStart);
    return Array.from({ length: 7 }).map((_, i) => {
      const d = new Date(start); d.setDate(start.getDate() + i);
      return d.toISOString().slice(0, 10);
    });
  }, [weekStart]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [sh, st, cf] = await Promise.all([
        axios.get(`${API}/staffing/shifts`, { headers, params: { date_from: days[0], date_to: days[6] } }),
        axios.get(`${API}/staffing/staff`, { headers }),
        isManager
          ? axios.get(`${API}/staffing/conflicts`, { headers, params: { start_date: days[0], end_date: days[6] } })
          : Promise.resolve({ data: { conflicts: [] } }),
      ]);
      setShifts(sh.data.shifts || []);
      setStaff(st.data.staff || []);
      setConflicts(cf.data?.conflicts || []);
    } catch { /* noop */ }
    setLoading(false);
  }, [headers, days, isManager]);

  useEffect(() => { load(); }, [load]);

  // Build a quick lookup for conflict lines per shift
  const conflictsByShift = useMemo(() => {
    const m = {};
    conflicts.forEach((c) => {
      if (!m[c.shift_id]) m[c.shift_id] = [];
      m[c.shift_id].push(c);
    });
    return m;
  }, [conflicts]);

  const weekCost = shifts.reduce((s, x) => s + (x.labour_cost || 0), 0);
  const weekHours = shifts.reduce((s, x) => s + (x.hours || 0), 0);

  // Per-day totals for the bottom row
  const dayTotals = useMemo(() => {
    const out = {};
    days.forEach((d) => { out[d] = { hours: 0, cost: 0 }; });
    shifts.forEach((s) => {
      if (!out[s.date]) return;
      out[s.date].hours += (s.hours || 0);
      out[s.date].cost += (s.labour_cost || 0);
    });
    return out;
  }, [shifts, days]);

  const addShift = async ({ staff_id, date, start_time, end_time, role }) => {
    try {
      await axios.post(`${API}/staffing/shifts`, { staff_id, date, start_time, end_time, role: role || 'reception', status: 'scheduled' }, { headers });
      setAdding(null);
      load();
    } catch (err) { alert(err.response?.data?.detail || 'Failed'); }
  };

  const deleteShift = async (id) => {
    if (!window.confirm(t('staffing.sc_rota_delete_confirm', 'Delete this shift?'))) return;
    try { await axios.delete(`${API}/staffing/shifts/${id}`, { headers }); load(); }
    catch { /* noop */ }
  };

  const copyWeek = async () => {
    const target = new Date(weekStart); target.setDate(target.getDate() + 7);
    try {
      await axios.post(`${API}/staffing/shifts/bulk`, { source_start: weekStart, target_start: target.toISOString().slice(0, 10) }, { headers });
      setWeekStart(target.toISOString().slice(0, 10));
      load();
    } catch (err) { alert(err.response?.data?.detail || 'Failed'); }
  };

  // Phase S1 — drag/drop handlers (HTML5 native; no extra lib)
  const onDragStart = (e, shiftId) => {
    if (!isManager) return;
    setDragging(shiftId);
    try { e.dataTransfer.setData('text/plain', shiftId); } catch { /* firefox quirk */ }
    e.dataTransfer.effectAllowed = 'move';
  };
  const onDragEnd = () => { setDragging(null); setDropTarget(null); };
  const onDragOver = (e, staff_id, date) => {
    if (!dragging) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    const key = `${staff_id}|${date}`;
    if (dropTarget !== key) setDropTarget(key);
  };
  const onDrop = async (e, staff_id, date) => {
    e.preventDefault();
    const id = dragging || e.dataTransfer.getData('text/plain');
    setDropTarget(null);
    setDragging(null);
    if (!id) return;
    // No-op if dropped in original cell
    const cur = shifts.find((s) => s.id === id);
    if (cur && cur.staff_id === staff_id && cur.date === date) return;
    // Optimistic update
    setShifts((prev) => prev.map((s) => s.id === id ? { ...s, staff_id, date } : s));
    try {
      await axios.post(`${API}/staffing/shifts/${id}/move`, { staff_id, date }, { headers });
      load();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to move shift');
      load(); // revert optimistic
    }
  };

  const shiftsFor = (staffId, date) => shifts.filter((s) => s.staff_id === staffId && s.date === date);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="inline-flex items-center gap-1 rounded-full border" style={{ borderColor: 'var(--theme-border)' }}>
          <button type="button" onClick={() => { const d = new Date(weekStart); d.setDate(d.getDate() - 7); setWeekStart(d.toISOString().slice(0,10)); }} className="w-8 h-8 inline-flex items-center justify-center" data-testid="rota-prev-week"><ChevronLeft size={14} /></button>
          <div className="text-xs font-semibold px-2" data-testid="rota-week-label">{t('staffing.sc_rota_week_of', 'Week of')} {weekStart}</div>
          <button type="button" onClick={() => { const d = new Date(weekStart); d.setDate(d.getDate() + 7); setWeekStart(d.toISOString().slice(0,10)); }} className="w-8 h-8 inline-flex items-center justify-center" data-testid="rota-next-week"><ChevronRight size={14} /></button>
        </div>
        <div className="flex items-center gap-2 text-xs flex-wrap" style={{ color: 'var(--theme-text-muted)' }}>
          <span data-testid="rota-week-hours">{weekHours.toFixed(1)}h</span>
          <span>·</span>
          <span data-testid="rota-week-cost">{formatMoneySync(weekCost)} {t('staffing.sc_rota_labour', 'labour')}</span>
          {isManager && conflicts.length > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold" style={{ background: 'rgba(239,68,68,0.15)', color: '#EF4444' }} data-testid="rota-conflicts-badge">
              <AlertTriangle size={10} /> {conflicts.length} {conflicts.length === 1 ? t('staffing.sc_rota_conflict', 'conflict') : t('staffing.sc_rota_conflicts', 'conflicts')}
            </span>
          )}
        </div>
        {isManager && (
          <button type="button" onClick={copyWeek} className="text-xs font-semibold inline-flex items-center gap-1 rounded-full px-3 py-1.5" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="rota-copy-week">
            <RefreshCw size={12} /> {t('staffing.sc_rota_copy_next', 'Copy to next week')}
          </button>
        )}
      </div>

      <Card testId="rota-grid">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr style={{ color: 'var(--theme-text-muted)' }}>
                <th className="text-left py-2 font-semibold px-2">{t('staffing.sc_rota_staff', 'Staff')}</th>
                {days.map((d) => (
                  <th key={d} className="text-left py-2 font-semibold px-2 whitespace-nowrap">{d.slice(5)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {staff.length === 0 ? (
                <tr><td colSpan={8} className="py-8 text-center" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_rota_no_staff', 'No staff yet — add staff in the Staff tab.')}</td></tr>
              ) : staff.map((s) => (
                <tr key={s.id} className="border-t" style={{ borderColor: 'var(--theme-border)' }}>
                  <td className="py-2 px-2" data-testid={`rota-row-${s.id}`}>
                    <div className="text-sm font-semibold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{s.full_name}</div>
                    <div className="text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--theme-text-muted)' }}>{humanizeRole(s.primary_role)}</div>
                  </td>
                  {days.map((d) => {
                    const cellKey = `${s.id}|${d}`;
                    const isDropTarget = dropTarget === cellKey && dragging;
                    return (
                    <td
                      key={d}
                      className="py-2 px-1 align-top"
                      onDragOver={(e) => isManager && onDragOver(e, s.id, d)}
                      onDrop={(e) => isManager && onDrop(e, s.id, d)}
                      style={isDropTarget ? { background: 'rgba(25,205,255,0.12)', outline: '1px dashed var(--color-brand-cyan)' } : {}}
                      data-testid={`rota-cell-${s.id}-${d}`}
                    >
                      <div className="space-y-1">
                        {shiftsFor(s.id, d).map((sh) => {
                          const myConflicts = conflictsByShift[sh.id] || [];
                          const hasError = myConflicts.some((c) => c.severity === 'error');
                          const hasWarn = myConflicts.length > 0 && !hasError;
                          return (
                          <div
                            key={sh.id}
                            draggable={isManager}
                            onDragStart={(e) => onDragStart(e, sh.id)}
                            onDragEnd={onDragEnd}
                            className="rounded-lg px-2 py-1 text-[11px] flex items-center gap-1 group cursor-grab active:cursor-grabbing"
                            style={{
                              background: hasError ? 'rgba(239,68,68,0.15)'
                                : hasWarn ? 'rgba(245,158,11,0.15)'
                                : 'rgba(25,205,255,0.12)',
                              color: 'var(--theme-text)',
                              outline: hasError ? '1px solid rgba(239,68,68,0.4)'
                                : hasWarn ? '1px solid rgba(245,158,11,0.4)'
                                : 'none',
                              opacity: dragging === sh.id ? 0.4 : 1,
                            }}
                            title={myConflicts.map((c) => c.reason).join('\n') || `${sh.start_time}–${sh.end_time}`}
                            data-testid={`rota-shift-${sh.id}`}>
                            {(hasError || hasWarn) && <AlertTriangle size={10} style={{ color: hasError ? '#EF4444' : '#F59E0B' }} />}
                            {!hasError && !hasWarn && <Clock size={10} />}
                            <span className="flex-1">{sh.start_time}–{sh.end_time}</span>
                            {isManager && <button type="button" onClick={() => deleteShift(sh.id)} className="opacity-0 group-hover:opacity-100 transition-opacity" data-testid={`rota-delete-${sh.id}`}><Trash2 size={10} /></button>}
                          </div>
                        ); })}
                        {isManager && (
                          <button type="button" onClick={() => setAdding({ staff_id: s.id, date: d })} className="w-full rounded-lg px-2 py-1 text-[11px] opacity-40 hover:opacity-100 border border-dashed" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid={`rota-add-${s.id}-${d}`}>+</button>
                        )}
                      </div>
                    </td>
                  ); })}
                </tr>
              ))}
              {/* Day totals */}
              {staff.length > 0 && (
                <tr className="border-t" style={{ borderColor: 'var(--theme-border)' }}>
                  <td className="py-2 px-2 text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_rota_day_totals', 'Day totals')}</td>
                  {days.map((d) => {
                    const dt = dayTotals[d];
                    return (
                      <td key={d} className="py-2 px-2" data-testid={`rota-day-total-${d}`}>
                        <div className="text-[11px] font-bold tabular-nums" style={{ color: 'var(--theme-text)' }}>{dt.hours.toFixed(1)}h</div>
                        {isManager && <div className="text-[10px] tabular-nums" style={{ color: 'var(--theme-text-muted)' }}>{formatMoneySync(dt.cost)}</div>}
                      </td>
                    );
                  })}
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {loading && <div className="text-xs mt-2" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_loading', 'Loading…')}</div>}
        {isManager && <p className="text-[10px] mt-2" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_rota_tip', 'Tip: drag any shift tile onto another cell to reassign it.')}</p>}
      </Card>

      {adding && (
        <AddShiftDialog
          initial={adding}
          onCancel={() => setAdding(null)}
          onSubmit={addShift}
        />
      )}
    </div>
  );
}

function AddShiftDialog({ initial, onCancel, onSubmit }) {
  const { t } = useTranslation();
  const [start_time, setStart] = useState('09:00');
  const [end_time, setEnd]     = useState('17:00');
  const [role, setRole]        = useState('manager');
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[70] p-4" data-testid="add-shift-dialog" onClick={onCancel}>
      <div className="rounded-2xl border p-5 w-full max-w-sm" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} onClick={(e) => e.stopPropagation()}>
        <div className="text-sm font-semibold pulse-font-heading mb-3" style={{ color: 'var(--theme-text)' }}>{t('staffing.sc_add_shift', 'Add shift')} · {initial.date}</div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_start', 'Start')}</label>
            <input type="time" value={start_time} onChange={(e) => setStart(e.target.value)} className="w-full rounded-lg px-2 py-1.5 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="add-shift-start" />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_end', 'End')}</label>
            <input type="time" value={end_time} onChange={(e) => setEnd(e.target.value)} className="w-full rounded-lg px-2 py-1.5 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="add-shift-end" />
          </div>
          <div className="col-span-2">
            <label className="text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_role', 'Role')}</label>
            <select value={role} onChange={(e) => setRole(e.target.value)} className="w-full rounded-lg px-2 py-1.5 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="add-shift-role">
              {['manager','engineer','technician','sales_manager','administrator','receptionist','supervisor','director','other'].map((r) => <option key={r} value={r}>{humanizeRole(r)}</option>)}
            </select>
          </div>
        </div>
        <div className="flex items-center gap-2 justify-end mt-4">
          <button type="button" onClick={onCancel} className="text-xs px-3 py-1.5 rounded-full border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid="add-shift-cancel">{t('staffing.sc_cancel', 'Cancel')}</button>
          <button type="button" onClick={() => onSubmit({ ...initial, start_time, end_time, role })} className="text-xs font-semibold px-3 py-1.5 rounded-full" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="add-shift-save">{t('staffing.sc_save', 'Save')}</button>
        </div>
      </div>
    </div>
  );
}

// ─── Staff directory (manager only) ───
function StaffTab({ headers }) {
  const { t } = useTranslation();
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ full_name: '', email: '', primary_role: 'manager', hourly_cost: 0, hours_per_week: 0, contract_type: 'part_time' });
  const [showAdd, setShowAdd] = useState(false);
  // Iter 216h243 — dynamic role list. Platform defaults + custom roles
  // come from `GET /staffing/roles` so operators can manage org-specific
  // roles (e.g. "swim coach", "spa therapist") without redeploys.
  const DEFAULT_ROLES = useMemo(() => ['manager','engineer','technician','sales_manager','administrator','receptionist','supervisor','director','other'], []);
  const [roleOptions, setRoleOptions] = useState(DEFAULT_ROLES);
  const [addingRole, setAddingRole] = useState(false);
  const [newRoleName, setNewRoleName] = useState('');
  const loadRoles = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/staffing/roles`, { headers });
      if (Array.isArray(data?.all) && data.all.length) setRoleOptions(data.all);
    } catch { /* best-effort — fall back to defaults */ }
  }, [headers]);
  const load = useCallback(async () => {
    const r = await axios.get(`${API}/staffing/staff`, { headers });
    setRows(r.data.staff || []);
  }, [headers]);
  useEffect(() => { load(); loadRoles(); }, [load, loadRoles]);
  const save = async () => {
    try { await axios.post(`${API}/staffing/staff`, form, { headers }); setShowAdd(false); setForm({ full_name: '', email: '', primary_role: 'manager', hourly_cost: 0, hours_per_week: 0, contract_type: 'part_time' }); load(); }
    catch (err) { alert(err.response?.data?.detail || 'Failed'); }
  };
  const submitNewRole = async () => {
    const name = (newRoleName || '').trim();
    if (!name) { setAddingRole(false); return; }
    try {
      await axios.post(`${API}/staffing/roles`, { role: name }, { headers });
      setNewRoleName('');
      setAddingRole(false);
      await loadRoles();
      setForm((f) => ({ ...f, primary_role: name }));
    } catch (err) {
      window.alert(err.response?.data?.detail || 'Could not add role');
    }
  };
  const archive = async (id) => { if (!window.confirm(t('staffing.sc_archive_confirm', 'Archive staff?'))) return; await axios.delete(`${API}/staffing/staff/${id}`, { headers }); load(); };

  // Iter 216h264 — issue or reset a staff member's portal credentials.
  // Backend creates / refreshes the matching users doc, returns a one-
  // shot temp password the manager can hand over (and best-effort
  // emails it to the staff member).
  const [credsBusy, setCredsBusy] = useState(null);
  const [credsDialog, setCredsDialog] = useState(null);
  const issueCredentials = async (s) => {
    const ok = window.confirm(
      `Issue portal login for ${s.full_name}? A temporary password will be ${s.email ? 'emailed to them and ' : ''}shown to you once.`,
    );
    if (!ok) return;
    setCredsBusy(s.id);
    try {
      const r = await axios.post(`${API}/staffing/staff/${s.id}/issue-credentials`, {}, { headers });
      setCredsDialog({ ...r.data, staffName: s.full_name });
    } catch (err) {
      window.alert(err.response?.data?.detail || 'Could not issue credentials');
    } finally {
      setCredsBusy(null);
    }
  };

  // Iter 216h264 — let managers preview what the staff portal looks
  // like by opening the Staffing console in a fresh tab with
  // `?as=staff`. The console hides manager-only tabs when this flag
  // is on (see useStaffPreviewRole below).
  const openStaffPreview = () => {
    const u = new URL(window.location.href);
    u.searchParams.set('as', 'staff');
    window.open(u.toString(), '_blank', 'noopener');
  };

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center flex-wrap gap-2">
        <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{rows.length} active staff</div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={openStaffPreview}
            className="text-xs font-semibold inline-flex items-center gap-1 rounded-full px-3 py-1.5 border"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)', background: 'var(--theme-surface)' }}
            data-testid="staff-preview-portal-btn"
            title={t('staffing.sc_preview_portal_title', 'Open the staff portal in a new tab as if you were a staff member')}
          >
            <ExternalLink size={12} /> {t('staffing.sc_preview_portal', 'Preview staff portal')}
          </button>
          <button type="button" onClick={() => setShowAdd(true)} className="text-xs font-semibold inline-flex items-center gap-1 rounded-full px-3 py-1.5" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="staff-add-btn">
            <UserPlus size={12} /> {t('staffing.sc_add_staff', 'Add staff')}
          </button>
        </div>
      </div>

      {rows.length === 0 ? <EmptyState icon={Users} title={t('staffing.sc_no_staff_title', 'No staff yet')} hint={t('staffing.sc_no_staff_hint', "Click 'Add staff' to build your roster.")} testId="staff-empty" /> : (
        <Card testId="staff-list">
          {/* Iter 215dj — wrap in overflow-x-auto so columns don't get
              clipped on mobile (was hiding the Hourly column on phones). */}
          <div className="overflow-x-auto -mx-2 sm:mx-0">
          <table className="w-full text-sm min-w-[34rem]">
            <thead>
              <tr className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
                <th className="text-left py-2 px-2 font-semibold">{t('staffing.sc_col_name', 'Name')}</th>
                <th className="text-left py-2 px-2 font-semibold">{t('staffing.sc_col_role', 'Role')}</th>
                <th className="text-left py-2 px-2 font-semibold">{t('staffing.sc_col_contract', 'Contract')}</th>
                {/* Iter 216h241 — surface both contracted hours and hourly
                    rate so operators can spot at a glance which is which.
                    Previously a row showing "£39.00" under "Hourly" was
                    mistaken for hours/week because the column header was
                    ambiguous. */}
                <th className="text-right py-2 px-2 font-semibold">{t('staffing.sc_col_hrs_wk', 'Hrs/wk')}</th>
                <th className="text-right py-2 px-2 font-semibold">{t('staffing.sc_col_hourly_rate', 'Hourly rate')}</th>
                <th className="text-right py-2 px-2 font-semibold">{t('staffing.sc_col_login', 'Login')}</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`staff-row-${s.id}`}>
                  <td className="py-2 px-2 font-medium" style={{ color: 'var(--theme-text)' }}>{s.full_name}</td>
                  <td className="py-2 px-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}>{humanizeRole(s.primary_role)}</td>
                  <td className="py-2 px-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}>{s.contract_type || '—'}</td>
                  <td className="py-2 px-2 text-right text-xs" style={{ color: 'var(--theme-text)' }} data-testid={`staff-row-${s.id}-hrs`}>{s.hours_per_week ? `${s.hours_per_week}h` : '—'}</td>
                  <td className="py-2 px-2 text-right text-xs" style={{ color: 'var(--theme-text)' }} data-testid={`staff-row-${s.id}-hourly`}>{formatMoneySync(s.hourly_cost || 0)}</td>
                  <td className="py-2 px-2 text-right">
                    <button
                      type="button"
                      onClick={() => issueCredentials(s)}
                      disabled={credsBusy === s.id}
                      className="inline-flex items-center gap-1 text-[11px] font-semibold rounded-md px-2 py-1 border disabled:opacity-50"
                      style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)', background: 'var(--theme-surface)' }}
                      data-testid={`staff-issue-creds-${s.id}`}
                      title={s.portal_credentials_issued_at ? t('staffing.sc_reissue_pw_title', 'Re-issue portal password') : t('staffing.sc_send_login_title', 'Send portal login')}
                    >
                      {credsBusy === s.id
                        ? <Loader2 size={11} className="animate-spin" />
                        : <KeyRound size={11} />}
                      {s.portal_credentials_issued_at ? t('staffing.sc_reissue', 'Re-issue') : t('staffing.sc_send_login', 'Send login')}
                    </button>
                  </td>
                  <td className="py-2 px-2 text-right"><button type="button" onClick={() => archive(s.id)} className="opacity-60 hover:opacity-100" data-testid={`staff-archive-${s.id}`}><Trash2 size={12} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </Card>
      )}

      {showAdd && createPortal((
        // Iter 216h242 — portal to document.body so the fixed inset-0
        // overlay covers the full viewport. Previously the modal was
        // rendered inside a parent with `transform`, which creates a
        // new containing block for position:fixed — the result was a
        // 1/3-of-screen un-dimmed white area below the page content.
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[70] p-4" onClick={() => setShowAdd(false)} data-testid="staff-add-backdrop">
          <div className="rounded-2xl border p-5 w-full max-w-md" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} onClick={(e) => e.stopPropagation()} data-testid="staff-add-dialog">
            <div className="text-sm font-semibold mb-3 pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{t('staffing.sc_add_staff', 'Add staff')}</div>
            <div className="space-y-2">
              <div>
                <label className="block text-[10px] uppercase tracking-wider font-bold mb-1" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_full_name', 'Full name')}</label>
                <input placeholder={t('staffing.sc_full_name_ph', 'e.g. Jane Doe')} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} className="w-full rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="staff-add-name" />
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-wider font-bold mb-1" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_email', 'Email')} <span className="opacity-60 normal-case font-normal">{t('staffing.sc_email_hint', '(optional — links to existing user)')}</span></label>
                <input placeholder="jane@example.com" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="w-full rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="staff-add-email" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[10px] uppercase tracking-wider font-bold mb-1" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_primary_role', 'Primary role')}</label>
                  {addingRole ? (
                    <div className="flex gap-1" data-testid="staff-add-role-new">
                      <input
                        autoFocus
                        type="text"
                        maxLength={60}
                        value={newRoleName}
                        onChange={(e) => setNewRoleName(e.target.value)}
                        placeholder={t('staffing.sc_new_role_ph', 'e.g. Swim coach')}
                        className="flex-1 rounded-lg px-3 py-2 text-sm border"
                        style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                        onKeyDown={(e) => { if (e.key === 'Enter') submitNewRole(); if (e.key === 'Escape') { setAddingRole(false); setNewRoleName(''); } }}
                        data-testid="staff-add-role-new-input"
                      />
                      <button type="button" onClick={submitNewRole} className="text-xs font-semibold px-3 py-1 rounded-full" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="staff-add-role-new-save">Add</button>
                      <button type="button" onClick={() => { setAddingRole(false); setNewRoleName(''); }} className="text-xs px-2 py-1 rounded-full border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid="staff-add-role-new-cancel">×</button>
                    </div>
                  ) : (
                    <select
                      value={form.primary_role}
                      onChange={(e) => {
                        if (e.target.value === '__add_new__') { setAddingRole(true); return; }
                        setForm({ ...form, primary_role: e.target.value });
                      }}
                      className="w-full rounded-lg px-3 py-2 text-sm border"
                      style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                      data-testid="staff-add-role"
                    >
                      {roleOptions.map((r) => <option key={r} value={r}>{humanizeRole(r)}</option>)}
                      <option value="__add_new__">{t('staffing.sc_add_new_role', '+ Add new role…')}</option>
                    </select>
                  )}
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-wider font-bold mb-1" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_contract_type', 'Contract type')}</label>
                  <select value={form.contract_type} onChange={(e) => setForm({ ...form, contract_type: e.target.value })} className="w-full rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="staff-add-contract">
                    {['full_time','part_time','casual','contractor'].map((c) => <option key={c}>{c}</option>)}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  {/* Iter 216h242 — labels above each number input. Without
                      these the two zeros looked identical and operators
                      had no way to tell which was £/hr vs hours/week. */}
                  <label className="block text-[10px] uppercase tracking-wider font-bold mb-1" style={{ color: 'var(--theme-text-muted)' }}>Hourly rate ({getCachedLocalization().currency_symbol}/hr)</label>
                  <input type="number" step="0.5" min="0" value={form.hourly_cost} onChange={(e) => setForm({ ...form, hourly_cost: parseFloat(e.target.value) || 0 })} className="w-full rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="staff-add-hourly" />
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-wider font-bold mb-1" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_contracted_hours', 'Contracted hours / week')}</label>
                  <input type="number" step="0.5" min="0" max="80" value={form.hours_per_week} onChange={(e) => setForm({ ...form, hours_per_week: parseFloat(e.target.value) || 0 })} className="w-full rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="staff-add-hours-per-week" />
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button type="button" onClick={() => setShowAdd(false)} className="text-xs px-3 py-1.5 rounded-full border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>{t('staffing.sc_cancel', 'Cancel')}</button>
              <button type="button" onClick={save} className="text-xs font-semibold px-3 py-1.5 rounded-full" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="staff-add-save">{t('staffing.sc_add', 'Add')}</button>
            </div>
          </div>
        </div>
      ), document.body)}

      {credsDialog && createPortal((
        <div className="fixed inset-0 z-[60] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4" data-testid="staff-creds-dialog">
          <div className="w-full max-w-md rounded-2xl p-5 shadow-2xl" style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}>
            <div className="flex items-start justify-between mb-3">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.14em]" style={{ color: 'var(--color-brand-cyan)' }}>{t('staffing.sc_portal_creds', 'Portal credentials')}</p>
                <h4 className="text-base font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{credsDialog.staffName}</h4>
              </div>
              <button type="button" onClick={() => setCredsDialog(null)} className="opacity-60 hover:opacity-100" data-testid="staff-creds-close" aria-label="Close"><X size={16} /></button>
            </div>
            <p className="text-xs mb-3" style={{ color: 'var(--theme-text-muted)' }}>
              {credsDialog.email_sent
                ? t('staffing.sc_creds_msg_sent', 'We\u2019ve emailed the temporary password to the staff member. You can also share it below.')
                : credsDialog.email
                  ? t('staffing.sc_creds_msg_failed', 'Email delivery failed — please copy the temporary password below and share it with the staff member.')
                  : t('staffing.sc_creds_msg_share', 'Share the temporary password below with the staff member.')}
              {' '}{t('staffing.sc_creds_msg_change', "They'll be asked to change it on first login.")}
            </p>
            <div className="space-y-2">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_login_email', 'Login email')}</p>
                <CopyableField value={credsDialog.email} testid="staff-creds-email" />
              </div>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_temp_password', 'Temporary password')}</p>
                <CopyableField value={credsDialog.temp_password} mono testid="staff-creds-temp-password" />
              </div>
            </div>
            <div className="flex justify-end mt-4">
              <button type="button" onClick={() => setCredsDialog(null)} className="text-xs font-semibold px-3 py-1.5 rounded-full" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="staff-creds-done">
                <Check size={11} className="inline-block mr-1" /> {t('staffing.sc_done', 'Done')}
              </button>
            </div>
          </div>
        </div>
      ), document.body)}
    </div>
  );
}

function CopyableField({ value, mono, testid }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value || '');
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard blocked */ }
  };
  return (
    <div className="mt-1 flex items-stretch gap-1.5">
      <input
        readOnly
        value={value || ''}
        className={`flex-1 min-w-0 h-9 rounded-md border px-2 text-sm ${mono ? 'font-mono tracking-wide' : ''}`}
        style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
        onFocus={(e) => e.target.select()}
        data-testid={`${testid}-input`}
      />
      <button type="button" onClick={copy} className="h-9 px-2 rounded-md border inline-flex items-center gap-1 text-[11px] font-semibold" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)', background: 'var(--theme-surface)' }} data-testid={`${testid}-copy`}>
        {copied ? <><Check size={11} /> {t('staffing.sc_copied', 'Copied')}</> : <><Copy size={11} /> {t('staffing.sc_copy', 'Copy')}</>}
      </button>

    </div>
  );
}

// ─── Leave ───
function LeaveTab({ headers, isManager }) {
  const { t } = useTranslation();
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ start_date: '', end_date: '', leave_type: 'holiday', reason: '' });
  const load = useCallback(async () => { const r = await axios.get(`${API}/staffing/leave`, { headers }); setRows(r.data.leave || []); }, [headers]);
  useEffect(() => { load(); }, [load]);
  const submit = async () => { try { await axios.post(`${API}/staffing/leave`, form, { headers }); setForm({ start_date: '', end_date: '', leave_type: 'holiday', reason: '' }); load(); } catch (err) { alert(err.response?.data?.detail || 'Failed'); } };
  const decide = async (id, status) => { await axios.patch(`${API}/staffing/leave/${id}`, { status }, { headers }); load(); };

  return (
    <div className="space-y-3">
      <Card testId="leave-form">
        <div className="text-xs font-semibold uppercase tracking-[0.14em] mb-2" style={{ color: 'var(--color-brand-cyan)' }}>{t('staffing.sc_request_time_off', 'Request time off')}</div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
          <input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} className="rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="leave-start" />
          <input type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} className="rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="leave-end" />
          <select value={form.leave_type} onChange={(e) => setForm({ ...form, leave_type: e.target.value })} className="rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="leave-type">
            {['holiday','sick','unpaid','training','other'].map((lt) => <option key={lt} value={lt}>{t(`staffing.sc_leave_type_${lt}`, lt)}</option>)}
          </select>
          <button type="button" onClick={submit} className="text-xs font-semibold rounded-full" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="leave-submit">{t('staffing.sc_submit', 'Submit')}</button>
        </div>
        <input placeholder={t('staffing.sc_reason_ph', 'Reason (optional)')} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} className="mt-2 w-full rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} />
      </Card>

      {rows.length === 0 ? <EmptyState icon={Plane} title={t('staffing.sc_no_leave', 'No leave requests yet')} testId="leave-empty" /> : (
        <Card testId="leave-list">
          <table className="w-full text-sm">
            <thead><tr className="text-xs" style={{ color: 'var(--theme-text-muted)' }}><th className="text-left py-2 px-2">{t('staffing.sc_dates', 'Dates')}</th><th className="text-left py-2 px-2">{t('staffing.sc_type', 'Type')}</th><th className="text-left py-2 px-2">{t('staffing.sc_status', 'Status')}</th>{isManager && <th className="w-32" />}</tr></thead>
            <tbody>
              {rows.map((l) => (
                <tr key={l.id} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`leave-row-${l.id}`}>
                  <td className="py-2 px-2 text-xs">{l.start_date} → {l.end_date}</td>
                  <td className="py-2 px-2 text-xs uppercase tracking-[0.14em]" style={{ color: 'var(--theme-text-muted)' }}>{l.leave_type}</td>
                  <td className="py-2 px-2 text-xs"><StatusBadge status={l.status} /></td>
                  {isManager && l.status === 'pending' && (
                    <td className="py-2 px-2 text-right space-x-1">
                      <button type="button" onClick={() => decide(l.id, 'approved')} className="text-[10px] font-semibold rounded-full px-2 py-1" style={{ background: 'var(--color-success)', color: 'var(--color-emerald-dark)' }} data-testid={`leave-approve-${l.id}`}>{t('staffing.sc_approve', 'Approve')}</button>
                      <button type="button" onClick={() => decide(l.id, 'rejected')} className="text-[10px] font-semibold rounded-full px-2 py-1 border" style={{ borderColor: 'var(--theme-border)' }} data-testid={`leave-reject-${l.id}`}>{t('staffing.sc_reject', 'Reject')}</button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

function StatusBadge({ status }) {
  const colour = status === 'approved' ? 'var(--color-success)' : status === 'rejected' ? 'var(--color-danger)' : status === 'pending' ? 'var(--color-warning)' : 'var(--color-text-faint-alt)';
  return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-[0.14em]" style={{ background: `${colour}22`, color: colour }}>{status}</span>;
}

// ─── Shift Marketplace ───
function MarketTab({ headers, isManager }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState([]);
  const [reqs, setReqs] = useState([]);
  const load = useCallback(async () => {
    const [o, r] = await Promise.all([
      axios.get(`${API}/staffing/marketplace/open`, { headers }),
      axios.get(`${API}/staffing/marketplace/requests`, { headers }),
    ]);
    setOpen(o.data.open_shifts || []);
    setReqs(r.data.requests || []);
  }, [headers]);
  useEffect(() => { load(); }, [load]);
  const claim = async (id) => { try { await axios.post(`${API}/staffing/marketplace/open/${id}/claim`, {}, { headers }); load(); } catch (err) { alert(err.response?.data?.detail || 'Failed'); } };
  const decide = async (id, status) => { await axios.patch(`${API}/staffing/marketplace/requests/${id}`, { status }, { headers }); load(); };
  return (
    <div className="space-y-3">
      <Card testId="market-open">
        <div className="text-xs font-semibold uppercase tracking-[0.14em] mb-2" style={{ color: 'var(--color-brand-cyan)' }}>{t('staffing.sc_open_shifts', 'Open shifts')} · {open.length}</div>
        {open.length === 0 ? <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_no_open_shifts', 'No open shifts right now.')}</div> : (
          <div className="space-y-2">
            {open.map((s) => (
              <div key={s.id} className="flex items-center gap-3 rounded-lg border px-3 py-2" style={{ borderColor: 'var(--theme-border)' }} data-testid={`market-open-${s.id}`}>
                <Clock size={14} style={{ color: 'var(--color-brand-cyan)' }} />
                <div className="flex-1 text-sm">{s.date} · {s.start_time}–{s.end_time}<span className="ml-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}>{humanizeRole(s.role)}</span></div>
                <button type="button" onClick={() => claim(s.id)} className="text-xs font-semibold rounded-full px-3 py-1" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid={`market-claim-${s.id}`}>{t('staffing.sc_claim', 'Claim')}</button>
              </div>
            ))}
          </div>
        )}
      </Card>
      <Card testId="market-requests">
        <div className="text-xs font-semibold uppercase tracking-[0.14em] mb-2" style={{ color: 'var(--color-brand-cyan)' }}>{t('staffing.sc_requests', 'Requests')} · {reqs.length}</div>
        {reqs.length === 0 ? <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_nothing_pending', 'Nothing pending.')}</div> : (
          <ul className="space-y-2">
            {reqs.map((r) => (
              <li key={r.id} className="rounded-lg border px-3 py-2 flex items-center gap-3" style={{ borderColor: 'var(--theme-border)' }} data-testid={`market-req-${r.id}`}>
                <div className="text-xs flex-1">
                  <span className="uppercase tracking-[0.14em] mr-2" style={{ color: 'var(--theme-text-muted)' }}>{r.kind}</span>
                  <span>{r.offered_shift_id.slice(0, 8)}…</span>
                </div>
                <StatusBadge status={r.status} />
                {isManager && r.status === 'pending' && (
                  <>
                    <button type="button" onClick={() => decide(r.id, 'approved')} className="text-[10px] font-semibold rounded-full px-2 py-1" style={{ background: 'var(--color-success)', color: 'var(--color-emerald-dark)' }}>{t('staffing.sc_approve', 'Approve')}</button>
                    <button type="button" onClick={() => decide(r.id, 'rejected')} className="text-[10px] font-semibold rounded-full px-2 py-1 border" style={{ borderColor: 'var(--theme-border)' }}>{t('staffing.sc_reject', 'Reject')}</button>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

// ─── Performance ───
function PerformanceTab({ headers }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  useEffect(() => {
    axios.get(`${API}/staffing/performance`, { headers }).then((r) => setData(r.data)).catch(() => setData({ staff: [] }));
  }, [headers]);
  if (!data) return <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_loading', 'Loading…')}</div>;
  if (!data.staff || data.staff.length === 0) return <EmptyState icon={BarChart3} title={t('staffing.sc_no_perf', 'No performance data yet')} hint={t('staffing.sc_no_perf_hint', 'Add staff and shifts to see breakdowns.')} testId="perf-empty" />;
  return (
    <Card testId="perf-list">
      {/* Iter 215dj — wrap in overflow-x-auto + min-width so labour £ /
          classes / attendees columns don't clip on mobile. */}
      <div className="overflow-x-auto -mx-2 sm:mx-0">
      <table className="w-full text-sm min-w-[36rem]">
        <thead><tr className="text-xs" style={{ color: 'var(--theme-text-muted)' }}><th className="text-left py-2 px-2 whitespace-nowrap">{t('staffing.sc_perf_staff', 'Staff')}</th><th className="text-right py-2 px-2 whitespace-nowrap">{t('staffing.sc_perf_hours', 'Hours')}</th><th className="text-right py-2 px-2 whitespace-nowrap">{t('staffing.sc_perf_labour', 'Labour')} {getCachedLocalization().currency_symbol}</th><th className="text-right py-2 px-2 whitespace-nowrap">{t('staffing.sc_perf_classes', 'Classes')}</th><th className="text-right py-2 px-2 whitespace-nowrap">{t('staffing.sc_perf_attendees', 'Attendees')}</th></tr></thead>
        <tbody>
          {data.staff.map((s) => (
            <tr key={s.staff_id} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`perf-row-${s.staff_id}`}>
              <td className="py-2 px-2"><div className="font-medium" style={{ color: 'var(--theme-text)' }}>{s.full_name}</div><div className="text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--theme-text-muted)' }}>{humanizeRole(s.primary_role)}</div></td>
              <td className="py-2 px-2 text-right tabular-nums">{s.hours_scheduled}</td>
              <td className="py-2 px-2 text-right tabular-nums">{formatMoneySync(s.labour_cost)}</td>
              <td className="py-2 px-2 text-right tabular-nums">{s.classes_delivered}</td>
              <td className="py-2 px-2 text-right tabular-nums">{s.attendees}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </Card>
  );
}

// ─── Payroll (export only) ───
function PayrollTab({ headers }) {
  const { t } = useTranslation();
  const [from, setFrom] = useState(() => { const d = new Date(); d.setDate(1); return d.toISOString().slice(0,10); });
  const [to, setTo] = useState(() => new Date().toISOString().slice(0,10));
  const download = async () => {
    const token = headers.Authorization?.split(' ')[1];
    const r = await fetch(`${API}/staffing/payroll/export?date_from=${from}&date_to=${to}`, { headers: { Authorization: `Bearer ${token}` } });
    const blob = await r.blob();
    const url = URL.createObjectURL(blob); const a = document.createElement('a');
    a.href = url; a.download = `payroll-${from}-to-${to}.csv`; a.click(); URL.revokeObjectURL(url);
  };
  return (
    <Card testId="payroll-card">
      <div className="text-xs font-semibold uppercase tracking-[0.14em] mb-3" style={{ color: 'var(--color-brand-cyan)' }}>{t('staffing.sc_export_payroll', 'Export payroll CSV')}</div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="payroll-from" />
        <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="payroll-to" />
        <button type="button" onClick={download} className="text-xs font-semibold rounded-full inline-flex items-center gap-1 justify-center" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="payroll-download"><Download size={12} /> {t('staffing.sc_download_csv', 'Download CSV')}</button>
      </div>
      <p className="text-[11px] mt-3" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_payroll_note', "Non-cancelled shifts only. Hours multiply by each staff's hourly cost.")}</p>
    </Card>
  );
}

// ─── Live Floor ───
function LiveFloorTab({ headers }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const load = useCallback(async () => { try { const r = await axios.get(`${API}/staffing/live-floor`, { headers }); setData(r.data); } catch { /* noop */ } }, [headers]);
  useEffect(() => { load(); const iv = setInterval(load, 60000); return () => clearInterval(iv); }, [load]);
  if (!data) return <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_loading', 'Loading…')}</div>;
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 text-xs" style={{ color: 'var(--theme-text-muted)' }}>
        <span className="inline-flex items-center gap-1"><div className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--color-success)' }} />{t('staffing.sc_live', 'Live')} · {new Date(data.as_of).toLocaleTimeString()}</span>
        <span>{data.coverage.on_now} {t('staffing.sc_on_now', 'on now')}</span>
        <span>{data.coverage.open_shifts_today} {t('staffing.sc_open_today', 'open today')}</span>
      </div>
      <Card testId="live-now">
        <div className="text-xs font-semibold uppercase tracking-[0.14em] mb-2" style={{ color: 'var(--color-success)' }}>{t('staffing.sc_on_floor_now', 'On the floor now')}</div>
        {data.on_now.length === 0 ? <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_nobody_now', 'Nobody scheduled right now.')}</div> : (
          <ul className="space-y-1">
            {data.on_now.map((s) => (
              <li key={s.id} className="flex items-center gap-2 text-sm" data-testid={`live-now-${s.id}`}>
                <div className="w-7 h-7 rounded-full flex items-center justify-center" style={{ background: 'var(--color-success)22', color: 'var(--color-success)' }}>{(s.staff_name || '?').charAt(0).toUpperCase()}</div>
                <div className="flex-1">{s.staff_name}</div>
                <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{humanizeRole(s.role)} · {t('staffing.sc_until', 'until')} {s.end_time}</div>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card testId="live-upcoming">
        <div className="text-xs font-semibold uppercase tracking-[0.14em] mb-2" style={{ color: 'var(--color-brand-cyan)' }}>{t('staffing.sc_up_next', 'Up next today')}</div>
        {data.upcoming.length === 0 ? <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_nothing_else', 'Nothing else scheduled today.')}</div> : (
          <ul className="space-y-1">
            {data.upcoming.map((s) => (
              <li key={s.id} className="flex items-center gap-2 text-sm" data-testid={`live-up-${s.id}`}>
                <Clock size={13} />
                <div className="flex-1">{s.staff_name}</div>
                <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{s.start_time}–{s.end_time} · {humanizeRole(s.role)}</div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

// ─── Rules (compliance) ───
function RulesTab({ headers }) {
  const { t } = useTranslation();
  const [rules, setRules] = useState(null);
  useEffect(() => { axios.get(`${API}/staffing/rules`, { headers }).then((r) => setRules(r.data)); }, [headers]);
  const save = async () => { await axios.put(`${API}/staffing/rules`, rules, { headers }); alert(t('staffing.sc_rules_saved', 'Rules saved')); };
  if (!rules) return <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_loading', 'Loading…')}</div>;
  const F = ({ k, label, step = '0.5' }) => (
    <div>
      <label className="text-[11px] uppercase tracking-[0.14em]" style={{ color: 'var(--theme-text-muted)' }}>{label}</label>
      <input type="number" step={step} value={rules[k] ?? 0} onChange={(e) => setRules({ ...rules, [k]: parseFloat(e.target.value) || 0 })} className="w-full rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid={`rules-${k}`} />
    </div>
  );
  return (
    <Card testId="rules-card">
      <div className="text-xs font-semibold uppercase tracking-[0.14em] mb-3" style={{ color: 'var(--color-brand-cyan)' }}>{t('staffing.sc_compliance_rules', 'Compliance rules')}</div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <F k="max_hours_per_week" label={t('staffing.sc_rule_max_hours', 'Max hours per week')} />
        <F k="min_rest_hours_between_shifts" label={t('staffing.sc_rule_min_rest', 'Min rest between shifts (h)')} />
        <F k="min_break_minutes_per_shift" label={t('staffing.sc_rule_min_break', 'Min break per shift (min)')} step="1" />
        <F k="max_days_consecutive" label={t('staffing.sc_rule_max_days', 'Max consecutive days')} step="1" />
      </div>
      <button type="button" onClick={save} className="mt-4 text-xs font-semibold rounded-full px-4 py-2" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="rules-save">{t('staffing.sc_save_rules', 'Save rules')}</button>
    </Card>
  );
}

// ─── Announcements ───
function AnnouncementsTab({ headers, isManager }) {
  const { t } = useTranslation();
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ title: '', body: '' });
  const load = useCallback(async () => { const r = await axios.get(`${API}/staffing/announcements`, { headers }); setRows(r.data.announcements || []); }, [headers]);
  useEffect(() => { load(); }, [load]);
  const submit = async () => { await axios.post(`${API}/staffing/announcements`, { ...form, audience: 'all' }, { headers }); setForm({ title: '', body: '' }); load(); };
  const remove = async (id) => { if (!window.confirm(t('staffing.sc_delete_q', 'Delete?'))) return; await axios.delete(`${API}/staffing/announcements/${id}`, { headers }); load(); };
  return (
    <div className="space-y-3">
      {isManager && (
        <Card testId="announce-form">
          <div className="text-xs font-semibold uppercase tracking-[0.14em] mb-2" style={{ color: 'var(--color-brand-cyan)' }}>{t('staffing.sc_post_announcement', 'Post an announcement')}</div>
          <input placeholder={t('staffing.sc_title', 'Title')} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="w-full rounded-lg px-3 py-2 text-sm border mb-2" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="announce-title" />
          <textarea placeholder={t('staffing.sc_message_ph', 'Message to staff…')} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} rows={3} className="w-full rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="announce-body" />
          <button type="button" onClick={submit} disabled={!form.title || !form.body} className="mt-2 text-xs font-semibold rounded-full px-4 py-2 disabled:opacity-40" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="announce-post">{t('staffing.sc_post', 'Post')}</button>
        </Card>
      )}
      {rows.length === 0 ? <EmptyState icon={Megaphone} title={t('staffing.sc_no_announcements', 'No announcements yet')} testId="announce-empty" /> : (
        <div className="space-y-2">
          {rows.map((a) => (
            <Card key={a.id} testId={`announce-${a.id}`}>
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0" style={{ background: 'var(--color-brand-cyan)22', color: 'var(--color-brand-cyan)' }}><Megaphone size={14} /></div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{a.title}</div>
                  <div className="text-sm mt-1" style={{ color: 'var(--theme-text-muted)' }}>{a.body}</div>
                  <div className="text-[10px] uppercase tracking-[0.14em] mt-2" style={{ color: 'var(--theme-text-muted)' }}>{a.author_name} · {a.created_at?.slice(0, 10)}</div>
                </div>
                {isManager && <button type="button" onClick={() => remove(a.id)} className="opacity-60 hover:opacity-100" data-testid={`announce-del-${a.id}`}><Trash2 size={12} /></button>}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── AI Insights ───
function AIInsightsTab({ headers }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  useEffect(() => { axios.get(`${API}/staffing/ai/insights`, { headers }).then((r) => setData(r.data)).catch(() => setData({ flags: [], narrative: 'No data yet.' })); }, [headers]);
  if (!data) return <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_analysing', 'Analysing last 30 days…')}</div>;
  const DAYS = [t('staffing.sc_day_mon', 'Mon'), t('staffing.sc_day_tue', 'Tue'), t('staffing.sc_day_wed', 'Wed'), t('staffing.sc_day_thu', 'Thu'), t('staffing.sc_day_fri', 'Fri'), t('staffing.sc_day_sat', 'Sat'), t('staffing.sc_day_sun', 'Sun')];
  return (
    <div className="space-y-3">
      <Card testId="ai-narrative">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}><Sparkles size={14} /></div>
          <div className="flex-1 text-sm" style={{ color: 'var(--theme-text)' }}>{data.narrative}</div>
        </div>
      </Card>
      <Card testId="ai-flags">
        <div className="text-xs font-semibold uppercase tracking-[0.14em] mb-2" style={{ color: 'var(--color-brand-cyan)' }}>{t('staffing.sc_flagged_slots', 'Flagged slots')} · {data.flags.length}</div>
        {data.flags.length === 0 ? <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_no_anomalies', 'No anomalies in the last 30 days. Nice.')}</div> : (
          <ul className="space-y-1">
            {data.flags.map((f, i) => (
              <li key={i} className="flex items-center gap-2 text-sm" data-testid={`ai-flag-${i}`}>
                <AlertTriangle size={13} style={{ color: f.kind === 'understaffed' ? 'var(--color-danger)' : 'var(--color-warning)' }} />
                <span className="flex-1">{DAYS[f.weekday]} {t('staffing.sc_at', 'at')} {String(f.hour).padStart(2, '0')}:00 · {t(`staffing.sc_kind_${f.kind}`, f.kind)}</span>
                <span className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.sc_demand', 'demand')} {f.demand} / {t('staffing.sc_supply', 'supply')} {f.supply}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}


