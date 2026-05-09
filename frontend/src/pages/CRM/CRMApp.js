import React, { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useAuth } from '@/App';
import Navbar from '@/components/shared/Navbar';
import ModuleSwitcher from '@/components/shared/ModuleSwitcher';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import CRMLogin from './CRMLogin';
import CRMDashboard from './CRMDashboard';
import CRMStartTab from './CRMStartTab';
import CRMContacts from './CRMContacts';
import { useUserPref } from '@/utils/userPrefs';
import CRMCompanies from './CRMCompanies';
import CRMPipeline from './CRMPipeline';
import CRMAITools from './CRMAITools';
import CRMInbox from './CRMInbox';
import CRMSettings from './CRMSettings';
import CRMWorkflows from './CRMWorkflows';
import CRMCPQ from './CRMCPQ';
import CRMDocuments from './CRMDocuments';
import CRMDemoTour from './CRMDemoTour';
import CRMTenders from './CRMTenders';
import CRMCalendar from './CRMCalendar';
import CRMTerritories from './CRMTerritories';
import CRMContracts from './CRMContracts';
import CRMForecast from './CRMForecast';
import CRMPermissions from './CRMPermissions';
import CRMModeSwitcher from './CRMModeSwitcher';
import CRMUpgradeScreen from './CRMUpgradeScreen';
import { useCRMModes, getStoredCrmMode, setStoredCrmMode } from './useCRMModes';
import PillTabBar from '@/components/shared/PillTabBar';
import ProductTour from '@/components/shared/ProductTour';
import { LayoutDashboard, Users, Building2, GitBranch, Sparkles, Settings, LogOut, Search, ChevronLeft, ChevronRight, Inbox, Zap, FileText, FolderOpen, Menu, X, Sun, Moon, Globe, Target, AlertTriangle, Command, Plus, Bell, User, CheckSquare, Award, CalendarDays, Activity, Shield, UsersRound, MapPin, TrendingUp, EyeOff } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const CRMContext = createContext();
export const useCRM = () => useContext(CRMContext);

/**
 * CRM nav (Iter 215e — IA collapse).
 *
 * Goal: compact, daily-use tab bar. Anything used <weekly is reachable
 * via contextual entry points (contact/company drawers, settings, the
 * AI toolbar button) instead of cluttering the pill bar.
 *
 * Visible to all CRM users: 8 tabs (dashboard … quotes).
 * Internal-only (`is_pulse_internal=true`) adds: contracts, tenders.
 *
 * Removed from the main pill bar (still routable via direct URL):
 *   • start      — onboarding tour, hidden once dismissed
 *   • documents  — surfaced inside contact / company drawers + Quotes
 *   • ai-tools   — surfaced as a Sparkles button in the toolbar
 */
const NAV_ITEMS = [
  { id: 'start', labelKey: 'crm.start', icon: Sparkles, hideFromBar: true },
  { id: 'dashboard', labelKey: 'crm.dashboard', icon: LayoutDashboard },
  { id: 'contacts', labelKey: 'crm.contacts', icon: Users },
  { id: 'companies', labelKey: 'crm.companies', icon: Building2 },
  { id: 'pipeline', labelKey: 'crm.pipeline', icon: GitBranch },
  { id: 'inbox', labelKey: 'crm.activity_feed', icon: Activity },
  { id: 'calendar', labelKey: 'crm.calendar', icon: CalendarDays },
  { id: 'workflows', labelKey: 'crm.workflows', icon: Zap },
  { id: 'quotes', labelKey: 'crm.quotes', icon: FileText },
  // Iter 215dc — enterprise territory & coverage management. Admins + managers only.
  { id: 'territories', labelKey: 'crm.territories', icon: MapPin, adminOnly: true },
  // Iter 215de — enterprise forecasting + quota management.
  { id: 'forecast', labelKey: 'crm.forecast', icon: TrendingUp },
  // Iter 215de — record-level + field-level permissions (admin only).
  { id: 'permissions', labelKey: 'crm.permissions', icon: EyeOff, adminOnly: true, hideFromBar: true },
  // Internal-only — Pulse Fitness HQ staff. Filtered by `internalOnly` below.
  { id: 'contracts', labelKey: 'crm.contracts', icon: Shield, internalOnly: true },
  { id: 'tenders', labelKey: 'crm.tenders', icon: Award, internalOnly: true },
  // Hidden from the bar but still routable via contextual entry points.
  { id: 'documents', labelKey: 'crm.documents', icon: FolderOpen, hideFromBar: true },
  { id: 'ai-tools', labelKey: 'crm.ai_tools', icon: Sparkles, hideFromBar: true },
  // Settings stays out of the bar — it's the gear icon in the toolbar.
];

const LANGS = [
  { code: 'en', label: 'English' },
  { code: 'fr', label: 'Français' },
  { code: 'de', label: 'Deutsch' },
];

const SEARCH_TYPE_ICONS = { company: Building2, contact: Users, opportunity: Target, case: AlertTriangle };
const SEARCH_TYPE_COLORS = { company: 'var(--color-accent-magenta)', contact: 'var(--color-accent-indigo)', opportunity: 'var(--color-info-ios)', case: 'var(--color-accent-amber)' };

const QUICK_CREATE_ITEMS = [
  { id: 'contact', label: 'Contact', icon: Users, color: 'var(--color-accent-indigo)' },
  { id: 'deal', label: 'Deal', icon: Target, color: 'var(--color-info-ios)' },
  { id: 'case', label: 'Case', icon: AlertTriangle, color: 'var(--color-accent-amber)' },
  { id: 'task', label: 'Task', icon: CheckSquare, color: 'var(--color-success-alt)' },
];

/* ═══ QUICK CREATE BUTTON ═══ */
function QuickCreateButton({ API, headers, c, isDark, onCreated }) {
  const [open, setOpen] = useState(false);
  const [activeType, setActiveType] = useState(null);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const wrapperRef = useRef(null);

  useEffect(() => {
    const handler = (e) => { if (wrapperRef.current && !wrapperRef.current.contains(e.target)) { setOpen(false); setActiveType(null); } };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleSubmit = async () => {
    setSaving(true);
    try {
      const payload = { entity_type: activeType, ...form };
      await axios.post(`${API}/crm/v2/quick-create`, payload, { headers: headers() });
      setOpen(false); setActiveType(null); setForm({});
      if (onCreated) onCreated(activeType);
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  const inputStyle = { background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${isDark ? 'var(--color-surface-dark-3)' : 'var(--color-border-alt)'}`, color: c.text };

  return (
    <div className="relative" ref={wrapperRef}>
      <button onClick={() => setOpen(!open)}
        className="w-8 h-8 rounded-md flex items-center justify-center transition-all hover:scale-105"
        style={{ background: 'var(--color-info-ios)', color: '#fff' }}
        data-testid="quick-create-btn">
        <Plus size={16} />
      </button>
      {open && !activeType && (
        <div className="absolute top-full right-0 mt-2 w-48 rounded-lg shadow-xl z-50 py-1"
          style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }}
          data-testid="quick-create-menu">
          {QUICK_CREATE_ITEMS.map(item => {
            const Icon = item.icon;
            return (
              <button key={item.id} onClick={() => { setActiveType(item.id); setForm({}); }}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors hover:bg-[rgb(var(--rgb-info-ios)/0.05)]"
                style={{ color: c.text }}
                data-testid={`quick-create-${item.id}`}>
                <Icon size={15} style={{ color: item.color }} />
                <span>New {item.label}</span>
              </button>
            );
          })}
        </div>
      )}
      {open && activeType && (
        <div className="absolute top-full right-0 mt-2 w-80 rounded-lg shadow-xl z-50 p-4"
          style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }}
          data-testid="quick-create-form">
          <h3 className="text-sm font-semibold mb-3" style={{ color: c.text }}>
            New {QUICK_CREATE_ITEMS.find(i => i.id === activeType)?.label}
          </h3>
          <div className="space-y-2">
            {activeType === 'contact' && <>
              <input value={form.first_name || ''} onChange={e => setForm({ ...form, first_name: e.target.value })} placeholder="First name *" className="w-full px-3 py-1.5 text-sm rounded-md" style={inputStyle} />
              <input value={form.last_name || ''} onChange={e => setForm({ ...form, last_name: e.target.value })} placeholder="Last name" className="w-full px-3 py-1.5 text-sm rounded-md" style={inputStyle} />
              <input value={form.email || ''} onChange={e => setForm({ ...form, email: e.target.value })} placeholder="Email" className="w-full px-3 py-1.5 text-sm rounded-md" style={inputStyle} />
            </>}
            {activeType === 'deal' && <>
              <input value={form.title || ''} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="Deal title *" className="w-full px-3 py-1.5 text-sm rounded-md" style={inputStyle} />
              <input type="number" value={form.value || ''} onChange={e => setForm({ ...form, value: e.target.value })} placeholder="Value (£)" className="w-full px-3 py-1.5 text-sm rounded-md" style={inputStyle} />
            </>}
            {activeType === 'case' && <>
              <input value={form.subject || ''} onChange={e => setForm({ ...form, subject: e.target.value })} placeholder="Case subject *" className="w-full px-3 py-1.5 text-sm rounded-md" style={inputStyle} />
              <select value={form.severity || 'medium'} onChange={e => setForm({ ...form, severity: e.target.value })} className="w-full px-3 py-1.5 text-sm rounded-md" style={inputStyle}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </>}
            {activeType === 'task' && <>
              <input value={form.subject || ''} onChange={e => setForm({ ...form, subject: e.target.value })} placeholder="Task subject *" className="w-full px-3 py-1.5 text-sm rounded-md" style={inputStyle} />
              <input type="date" value={form.due_date || ''} onChange={e => setForm({ ...form, due_date: e.target.value })} className="w-full px-3 py-1.5 text-sm rounded-md" style={inputStyle} />
            </>}
          </div>
          <div className="flex gap-2 mt-3 justify-end">
            <button onClick={() => { setActiveType(null); setForm({}); }} className="px-3 py-1.5 text-xs" style={{ color: c.textMuted }}>Back</button>
            <button onClick={handleSubmit} disabled={saving} className="px-3 py-1.5 bg-[var(--color-info-ios)] text-white text-xs font-medium rounded-md disabled:opacity-50">
              {saving ? 'Creating...' : 'Create'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ═══ STAFF FILTER (toolbar) ═══ */
function StaffFilterDropdown({ API, headers, c, isDark, value, onChange, brandAccent }) {
  const [members, setMembers] = useState([]);
  useEffect(() => {
    let alive = true;
    axios.get(`${API}/crm/users`, { headers: headers() })
      .then(res => { if (alive) setMembers(res.data.users || []); })
      .catch(() => {});
    return () => { alive = false; };
  }, [API, headers]);

  return (
    <div className="flex items-center gap-1.5" data-testid="crm-toolbar-staff-filter">
      <UsersRound size={13} style={{ color: c.textDim }} />
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 px-2 text-xs rounded-md focus:outline-none focus:ring-1"
        style={{
          background: isDark ? 'var(--color-surface-dark-1)' : '#fff',
          border: `1px solid ${c.border}`,
          color: c.text,
          minWidth: 130,
        }}
        data-testid="crm-toolbar-staff-select"
      >
        <option value="all">All Staff</option>
        <option value="mine">My Dashboard</option>
        {members.map(m => (
          <option key={m.id} value={m.id}>{m.full_name}</option>
        ))}
      </select>
    </div>
  );
}

/* ═══ NOTIFICATIONS BELL ═══ */
function NotificationsBell({ API, headers, c, isDark }) {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unread, setUnread] = useState(0);
  const wrapperRef = useRef(null);

  useEffect(() => {
    const handler = (e) => { if (wrapperRef.current && !wrapperRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const load = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/crm/v2/notifications?limit=10`, { headers: headers() });
      setNotifications(res.data.notifications || []);
      setUnread(res.data.unread || 0);
    } catch (e) { /* silent */ }
  }, [API, headers]);

  useEffect(() => { load(); const iv = setInterval(load, 30000); return () => clearInterval(iv); }, [load]);

  const markAllRead = async () => {
    try {
      await axios.post(`${API}/crm/v2/notifications/mark-read`, {}, { headers: headers() });
      load();
    } catch (e) { /* silent */ }
  };

  return (
    <div className="relative" ref={wrapperRef}>
      <button onClick={() => { setOpen(!open); if (!open) load(); }}
        className="w-8 h-8 rounded-md flex items-center justify-center relative transition-all"
        style={{ color: c.textMuted }}
        data-testid="notifications-btn">
        <Bell size={17} />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-[var(--color-danger-alt)] text-white text-[9px] font-bold flex items-center justify-center">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute top-full right-0 mt-2 w-80 rounded-lg shadow-xl z-50 max-h-[400px] overflow-y-auto"
          style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }}
          data-testid="notifications-panel">
          <div className="px-4 py-3 flex items-center justify-between" style={{ borderBottom: `1px solid ${c.border}` }}>
            <span className="text-sm font-semibold" style={{ color: c.text }}>Notifications</span>
            {unread > 0 && <button onClick={markAllRead} className="text-[10px] text-[var(--color-info-ios)] hover:underline">Mark all read</button>}
          </div>
          {notifications.length === 0 ? (
            <div className="px-4 py-8 text-center">
              <Bell size={24} className="mx-auto mb-2" style={{ color: c.textDim }} />
              <p className="text-xs" style={{ color: c.textDim }}>No notifications</p>
            </div>
          ) : (
            notifications.map(n => (
              <div key={n.id} className="px-4 py-3 transition-colors" style={{ borderBottom: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-neutral-100)'}`, background: !n.read ? (isDark ? 'var(--color-info-ios)08' : 'var(--color-info-bg)') : 'transparent' }}>
                <div className="flex items-start gap-2">
                  <Zap size={12} className="mt-0.5 shrink-0" style={{ color: 'var(--color-info-ios)' }} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium" style={{ color: c.text }}>{n.message}</p>
                    {n.entity_name && <p className="text-[10px] mt-0.5" style={{ color: 'var(--color-info-ios)' }}>{n.entity_type}: {n.entity_name}</p>}
                    <p className="text-[10px] mt-0.5" style={{ color: c.textDim }}>
                      {(() => { const d = Date.now() - new Date(n.created_at).getTime(); const m = Math.floor(d/60000); if(m<60) return `${m}m ago`; const h=Math.floor(m/60); if(h<24) return `${h}h ago`; return `${Math.floor(h/24)}d ago`; })()}
                    </p>
                  </div>
                  {!n.read && <div className="w-2 h-2 rounded-full bg-[var(--color-info-ios)] shrink-0 mt-1" />}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

function GlobalSearchBar({ API, headers, c, isDark, t, onNavigate }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef(null);
  const wrapperRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const doSearch = useCallback(async (q) => {
    if (!q || q.length < 2) { setResults([]); setOpen(false); return; }
    setLoading(true);
    try {
      const res = await axios.get(`${API}/crm/v2/search?q=${encodeURIComponent(q)}`, { headers: headers() });
      setResults(res.data.results || []);
      setOpen(true);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [API, headers]);

  const handleChange = (e) => {
    const val = e.target.value;
    setQuery(val);
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => doSearch(val), 300);
  };

  const handleSelect = (result) => {
    setOpen(false);
    setQuery('');
    onNavigate(result.type, result.id);
  };

  return (
    <div className="relative flex-1 max-w-[200px] sm:max-w-xs md:max-w-sm" ref={wrapperRef}>
      <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: c.textDim }} />
      <input
        type="text"
        placeholder={t('crm.search')}
        value={query}
        onChange={handleChange}
        onFocus={() => { if (results.length > 0) setOpen(true); }}
        className="w-full pl-8 pr-8 py-1.5 text-sm rounded-sm focus:outline-none focus:ring-1 focus:ring-[var(--color-info-ios)]"
        style={{ background: c.inputBg || (isDark ? 'var(--color-neutral-900)' : '#fff'), border: `1px solid ${c.border}`, color: c.text }}
        data-testid="crm-global-search"
      />
      <Command size={12} className="absolute right-2.5 top-1/2 -translate-y-1/2" style={{ color: c.textDim }} />
      {open && results.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-1 rounded-md shadow-xl z-50 max-h-80 overflow-y-auto"
          style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }}
          data-testid="global-search-results">
          {results.map((r, i) => {
            const Icon = SEARCH_TYPE_ICONS[r.type] || Search;
            const color = SEARCH_TYPE_COLORS[r.type] || 'var(--color-text-faint-alt)';
            return (
              <button key={`${r.type}-${r.id}-${i}`} onClick={() => handleSelect(r)}
                className="w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-[rgb(var(--rgb-info-ios)/0.05)]"
                style={{ borderBottom: `1px solid ${isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-neutral-100)'}` }}
                data-testid={`search-result-${r.type}-${i}`}>
                <div className="w-7 h-7 rounded-md flex items-center justify-center shrink-0" style={{ background: `${color}15` }}>
                  <Icon size={13} style={{ color }} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm truncate" style={{ color: c.text }}>{r.label}</p>
                  <p className="text-[10px] uppercase" style={{ color: c.textDim }}>{r.type}</p>
                </div>
                {r.value > 0 && <span className="text-xs font-medium" style={{ color: 'var(--color-success-alt)' }}>£{r.value.toLocaleString()}</span>}
              </button>
            );
          })}
        </div>
      )}
      {open && results.length === 0 && query.length >= 2 && !loading && (
        <div className="absolute top-full left-0 right-0 mt-1 rounded-md shadow-xl z-50 px-4 py-6 text-center"
          style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff', border: `1px solid ${c.border}` }}>
          <p className="text-sm" style={{ color: c.textDim }}>No results for "{query}"</p>
        </div>
      )}
    </div>
  );
}

export default function CRMApp() {
  const { t, i18n } = useTranslation();
  // The CRM app runs alongside the main platform auth context, so we can
  // borrow the operator's main user (and the platform Navbar / module
  // switcher) to keep look-and-feel consistent with Operations,
  // Memberships and Marketing.
  const mainAuth = useAuth();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('start');
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark');
  const [showLangMenu, setShowLangMenu] = useState(false);
  const [showTour, setShowTour] = useState(false);
  // Staff filter is hoisted to the top-level toolbar so it sits next to
  // Settings, above the tab bar. CRMDashboard reads `staffFilter` from
  // context so it can scope its data to the chosen team member.
  const [staffFilter, setStaffFilter] = useState('mine');

  // ── CRM modes (Iter 215c) ─────────────────────────────────────────
  const crmModesData = useCRMModes();
  const [activeMode, setActiveMode] = useState(() => getStoredCrmMode());
  // When entitlements load, reconcile: if the stored mode isn't enabled,
  // pick the first one that IS enabled.
  useEffect(() => {
    if (crmModesData.loading) return;
    const m = crmModesData.modes || {};
    if (activeMode === 'leisure' && !m.leisure && m.business) setActiveMode('business');
    else if (activeMode === 'business' && !m.business && m.leisure) setActiveMode('leisure');
  }, [crmModesData.loading, crmModesData.modes, activeMode]);
  const handleModeChange = (mode) => {
    setActiveMode(mode);
    setStoredCrmMode(mode);
  };

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => setTheme(prev => prev === 'dark' ? 'light' : 'dark');
  const isDark = theme === 'dark';

  // Theme-aware colour helpers
  const c = {
    bg: isDark ? 'var(--color-ink-alt)' : 'var(--theme-bg)',
    surface: isDark ? 'var(--color-neutral-900)' : 'var(--theme-surface)',
    surfaceHover: isDark ? 'var(--color-surface-dark-3)' : 'var(--theme-surface-hover)',
    border: isDark ? 'var(--color-surface-dark-3)' : 'var(--theme-border)',
    text: isDark ? 'var(--color-neutral-50)' : 'var(--theme-text)',
    textMuted: isDark ? 'var(--color-neutral-400)' : 'var(--theme-text-muted)',
    textDim: isDark ? 'var(--color-neutral-600)' : 'var(--theme-text-muted)',
    inputBg: isDark ? 'var(--color-neutral-900)' : 'var(--theme-input-bg)',
  };

  const headers = useCallback(() => {
    const token = localStorage.getItem('crm_token');
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, []);

  // ── Brand resolver ──────────────────────────────────────────────────
  // Pulse Pro customers (Tottenham etc.) and Pulse Fitness internal staff
  // get the Pulse-blue branding throughout CRM, including the sidebar
  // header. End-customer accounts NEVER see "GymAxis" branding.
  // Iter 215ax (Phase 3) — for GymAxis-branded CRM users, the active-tab
  // accent is the brand gradient (navy → purple); Pulse-branded users
  // keep the legacy cyan to preserve their visual identity.
  const isPulseBrandedCRM = user?.crm_brand === 'pulse';
  const brandCfg = useMemo(() => {
    if (isPulseBrandedCRM) {
      return { label: 'Pulse Fitness CRM', initial: 'P', accent: 'var(--color-brand-cyan)' };
    }
    return { label: t('crm.title'), initial: 'G', accent: 'var(--gx-brand-from)' };
  }, [isPulseBrandedCRM, t]);

  // ── Internal-only nav filter ────────────────────────────────────────
  // Tender Engine + Contracts are Pulse-Fitness-only modules. Hide them
  // unless the user is an internal Pulse staff member or master admin.
  // The "Start" pill is also hidden when the user has dismissed the
  // guided-experience layer via their preferences (set from the Start
  // tab itself, so the choice is self-service and reversible from
  // Settings later).
  const [hideStart] = useUserPref('hideStartTabs', false);
  useEffect(() => { if (hideStart && activeTab === 'start') setActiveTab('dashboard'); }, [hideStart, activeTab]);
  const visibleNavItems = useMemo(() => {
    const isInternal = !!user?.is_pulse_internal;
    // Iter 215bi — Members mode (leisure) hides the Quotes/CPQ tab. Leisure
    // centres / gyms work off membership packages, not formal sales quotes.
    const isMembersMode = activeMode === 'leisure';
    const isAdmin = user?.role === 'admin' || user?.role === 'owner' || user?.role === 'manager' || user?.is_master_admin;
    return NAV_ITEMS
      .filter(it => !it.internalOnly || isInternal)
      .filter(it => !it.adminOnly || isAdmin)
      .filter(it => !it.hideFromBar)
      .filter(it => !(isMembersMode && it.id === 'quotes'))
      .filter(it => !(hideStart && it.id === 'start'));
  }, [user?.is_pulse_internal, hideStart, activeMode]);

  // ── Sync logout: when the user signs out from the platform Navbar
  // (which clears `mainAuth.user`), the CRM module must follow suit.
  // Without this, the platform JWT is gone but the local CRM token
  // sticks around — the page keeps rendering CRM content with the
  // GymAxis fallback brand because `platformUser` falls back to the
  // CRM-only user record.
  const mainUserId = mainAuth?.user?.id ?? null;
  const wasLoggedInRef = useRef(false);
  useEffect(() => {
    if (mainUserId) {
      wasLoggedInRef.current = true;
      return;
    }
    if (wasLoggedInRef.current) {
      wasLoggedInRef.current = false;
      localStorage.removeItem('crm_token');
      sessionStorage.removeItem('crm_active_session');
      setUser(null);
    }
  }, [mainUserId]);

  useEffect(() => {
    // Check for explicit logout via URL param
    const params = new URLSearchParams(window.location.search);
    if (params.get('logout') === '1') {
      localStorage.removeItem('crm_token');
      localStorage.removeItem('crm_tour_seen');
      window.history.replaceState({}, '', '/crm');
      setLoading(false);
      return;
    }

    const token = localStorage.getItem('crm_token');
    // Auto-login if token exists:
    // - In PWA standalone mode, always try (sessionStorage is lost between launches)
    // - In browser, require sessionStorage flag (prevents stale cross-tab logins)
    const hasSession = sessionStorage.getItem('crm_active_session');
    const isPWA = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
    if (token && (hasSession || isPWA)) {
      axios.get(`${API}/crm/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
        .then(res => {
          if (res.data && res.data.email) {
            setUser(res.data);
            sessionStorage.setItem('crm_active_session', '1');
          } else {
            localStorage.removeItem('crm_token');
            sessionStorage.removeItem('crm_active_session');
          }
          setLoading(false);
        })
        .catch(() => {
          localStorage.removeItem('crm_token');
          sessionStorage.removeItem('crm_active_session');
          setLoading(false);
        });
    } else {
      // No active session — clear any stale token and show login
      if (token && !hasSession && !isPWA) {
        localStorage.removeItem('crm_token');
      }
      setLoading(false);
    }
  }, []);

  const login = (token, userData) => {
    localStorage.setItem('crm_token', token);
    sessionStorage.setItem('crm_active_session', '1');
    setUser(userData);
    // Show tour for new users
    if (!localStorage.getItem('crm_tour_seen')) {
      setShowTour(true);
      localStorage.setItem('crm_tour_seen', '1');
    }
    window.dispatchEvent(new Event('pwa-check-install'));
  };
  const logout = () => {
    localStorage.removeItem('crm_token');
    sessionStorage.removeItem('crm_active_session');
    setUser(null);
  };
  const [navTarget, setNavTarget] = useState(null); // {type: 'company', id: '...'}

  const navigateTo = useCallback((entityType, entityId) => {
    const tabMap = { company: 'companies', contact: 'contacts', opportunity: 'pipeline', deal: 'pipeline', case: 'dashboard', task: 'inbox', quote: 'quotes', contract: 'contracts' };
    const tab = tabMap[entityType] || 'dashboard';
    setNavTarget({ type: entityType, id: entityId });
    setActiveTab(tab);
  }, []);

  const handleNav = (id) => { setActiveTab(id); setNavTarget(null); setMobileOpen(false); };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: c.bg }}>
        <div className="w-6 h-6 border-2 border-[var(--color-info-ios)] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!user) return <CRMLogin onLogin={login} />;

  // Iter 215c — entitlement gate. If the org has neither leisure nor
  // business CRM enabled, render the upgrade screen instead of the
  // CRM workspace. Master admins are exempt (always have both).
  // Fails open when the modes API can't be called (e.g. CRM-only auth
  // without a platform JWT) so we don't accidentally block legacy users.
  const isMasterAdmin = !!(mainAuth?.user?.is_master_admin || user?.is_master_admin);
  const modesResolved = !crmModesData.loading && !crmModesData.error;
  if (modesResolved && !crmModesData.any_enabled && !isMasterAdmin) {
    return (
      <CRMContext.Provider value={{ user, API, headers, logout, activeTab, setActiveTab, navigateTo: () => {}, navTarget: null, setNavTarget: () => {}, theme, isDark, c, t, staffFilter, setStaffFilter, activeMode, modes: crmModesData.modes }}>
        <div className="min-h-screen overflow-x-hidden pulse-font-body" style={{ background: c.bg }}>
          <Navbar user={mainAuth?.user || user} logout={() => { (mainAuth?.logout || logout)(); }} theme={theme} toggleTheme={toggleTheme} />
          <div className="pt-24">
            <CRMUpgradeScreen
              modes={crmModesData.modes}
              accountType={crmModesData.account_type}
              membershipsEnabled={crmModesData.memberships_enabled}
              onUpgraded={crmModesData.reload}
            />
          </div>
        </div>
      </CRMContext.Provider>
    );
  }

  const renderContent = () => {
    switch (activeTab) {
      case 'start': return <CRMStartTab setActiveTab={setActiveTab} />;
      case 'dashboard': return <CRMDashboard />;
      case 'contacts': return <CRMContacts />;
      case 'companies': return <CRMCompanies />;
      case 'pipeline': return <CRMPipeline />;
      case 'inbox': return <CRMInbox />;
      case 'calendar': return <CRMCalendar />;
      case 'workflows': return <CRMWorkflows />;
      case 'quotes': return <CRMCPQ />;
      case 'contracts': return <CRMContracts />;
      case 'documents': return <CRMDocuments />;
      case 'tenders': return <CRMTenders />;
      case 'ai-tools': return <CRMAITools />;
      case 'territories': return <CRMTerritories />;
      case 'forecast': return <CRMForecast />;
      case 'permissions': return <CRMPermissions />;
      case 'settings': return <CRMSettings />;
      default: return <CRMDashboard />;
    }
  };

  const showLabels = !collapsed || mobileOpen;

  // ── Platform shell wrapper ─────────────────────────────────────────
  // Renders the platform Navbar + module switcher at the top so the CRM
  // visually matches Operations / Memberships / Marketing. Falls back to
  // the CRM's own auth context if no main session is available (e.g.
  // direct CRM login without SSO).
  const platformUser = mainAuth?.user || user;
  const platformLogout = () => {
    if (mainAuth?.logout) mainAuth.logout();
    else logout();
  };
  const showShell = !!platformUser;

  return (
    <CRMContext.Provider value={{ user, API, headers, logout, activeTab, setActiveTab, navigateTo, navTarget, setNavTarget, theme, isDark, c, t, staffFilter, setStaffFilter, activeMode, modes: crmModesData.modes }}>
      <div
        className={`min-h-screen overflow-x-hidden pulse-font-body module-fade-in ${!isPulseBrandedCRM && !isDark ? 'theme-gymaxis' : ''}`}
        style={{ background: c.bg }}
      >

        {/* Platform Navbar — shared across modules */}
        {showShell && (
          <Navbar
            user={platformUser}
            logout={platformLogout}
            theme={theme}
            toggleTheme={toggleTheme}
          />
        )}
        {showShell && <ProductTour variant="crm" />}

        {/* Pulse / GymAxis branded module header — byte-for-byte parity
            with Marketing / Memberships so the user gets the same
            typography (text-3xl..4xl + pulse-font-heading) and the
            "Welcome back, …" line sits ABOVE the module switcher. */}
        {showShell && (
          <div className="pt-24 pb-3 px-4 md:px-8 max-w-7xl mx-auto" data-testid="crm-app-header">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <h1
                  className="text-3xl sm:text-4xl tracking-tight font-bold mb-1 pulse-font-heading leading-tight"
                  style={{ color: 'var(--theme-text)' }}
                >
                  {isPulseBrandedCRM ? (
                    brandCfg.label.replace(' CRM', '')
                  ) : (
                    <span className="gx-grad-text">{brandCfg.label.replace(' CRM', '')}</span>
                  )}{' '}
                  {(platformUser?.account_type === 'pulse_pro' || platformUser?.account_type === 'full' || platformUser?.is_master_admin) && (
                    <span style={{ color: isPulseBrandedCRM ? 'var(--color-brand-cyan-hover)' : 'var(--gx-brand-to)' }}>Pro</span>
                  )}
                  {platformUser?.company_name && (
                    <span className="text-base sm:text-lg font-normal ml-2 pulse-font-body" style={{ color: 'var(--theme-text-muted)' }}>
                      · {platformUser.company_name}
                    </span>
                  )}
                </h1>
                <p className="pulse-font-body mb-3" style={{ color: 'var(--theme-text-muted)' }}>
                  Welcome back, {platformUser?.full_name || user?.full_name}
                </p>
              </div>
              <div className="text-sm pulse-font-body shrink-0 mt-1.5" style={{ color: 'var(--theme-text-muted)' }} data-testid="module-today-date">
                {new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
              </div>
            </div>

            {/* Toolbar row — module switcher + search + quick actions
                + staff filter + settings, all level with each other. */}
            <div className="flex items-center gap-3 flex-wrap" data-testid="crm-toolbar">
              <ModuleSwitcher user={platformUser} current="crm" />
              <CRMModeSwitcher
                modes={crmModesData.modes}
                activeMode={activeMode}
                onChange={handleModeChange}
                brandAccent={brandCfg.accent}
              />
              <div className="hidden md:block flex-1 min-w-[160px] max-w-sm">
                <GlobalSearchBar API={API} headers={headers} c={c} isDark={isDark} t={t} onNavigate={(type, id) => navigateTo(type, id)} />
              </div>
              <div className="flex items-center gap-2 ml-auto">
                <QuickCreateButton API={API} headers={headers} c={c} isDark={isDark} onCreated={(type) => {
                  if (type === 'contact') setActiveTab('contacts');
                  else if (type === 'deal') setActiveTab('pipeline');
                  else if (type === 'case') setActiveTab('dashboard');
                  else if (type === 'task') setActiveTab('inbox');
                }} />
                <NotificationsBell API={API} headers={headers} c={c} isDark={isDark} />
                {(['admin', 'owner', 'manager', 'director'].includes(user?.role)) && (
                  <StaffFilterDropdown
                    API={API}
                    headers={headers}
                    c={c}
                    isDark={isDark}
                    value={staffFilter}
                    onChange={setStaffFilter}
                    brandAccent={brandCfg.accent}
                  />
                )}
                <button
                  onClick={() => setActiveTab('ai-tools')}
                  className="w-9 h-9 inline-flex items-center justify-center rounded-md border transition-colors hover:bg-black/5 dark:hover:bg-white/10 dark:bg-zinc-900"
                  style={{
                    color: activeTab === 'ai-tools' ? brandCfg.accent : c.textMuted,
                    borderColor: c.border,
                  }}
                  aria-label="AI Tools"
                  title="AI Tools — drafts, summaries, automation suggestions"
                  data-testid="crm-toolbar-ai"
                >
                  <Sparkles size={16} />
                </button>
                <button
                  onClick={() => setActiveTab('settings')}
                  className="w-9 h-9 inline-flex items-center justify-center rounded-md border transition-colors hover:bg-black/5 dark:hover:bg-white/10 dark:bg-zinc-900"
                  style={{
                    color: activeTab === 'settings' ? brandCfg.accent : c.textMuted,
                    borderColor: c.border,
                  }}
                  aria-label={t('crm.settings')}
                  title={t('crm.settings')}
                  data-testid="crm-toolbar-settings"
                >
                  <Settings size={16} />
                </button>
              </div>
            </div>

            {/* Mobile-only search row (so the toolbar above stays
                tidy on narrow screens). */}
            <div className="mt-3 md:hidden">
              <GlobalSearchBar API={API} headers={headers} c={c} isDark={isDark} t={t} onNavigate={(type, id) => navigateTo(type, id)} />
            </div>
          </div>
        )}

        {/* Horizontal CRM tab bar — canonical PillTabBar so overflow
            auto-scrolls the active tab into view and fades edges. */}
        {showShell && (
          <div
            className="max-w-7xl mx-auto px-4 md:px-8 mb-6 mt-4"
            data-testid="crm-tabs-bar"
          >
            <PillTabBar
              className="hidden md:block pulse-font-body"
              activeId={activeTab}
              testId="crm-tabs-desktop"
              ariaLabel="CRM sections"
            >
              {visibleNavItems.map((item) => {
                const Icon = item.icon;
                const active = activeTab === item.id;
                const activeStyle = isPulseBrandedCRM
                  ? { background: brandCfg.accent, color: 'var(--color-ink)' }
                  : { backgroundImage: 'linear-gradient(135deg, var(--gx-brand-from) 0%, var(--gx-brand-to) 100%)', color: '#FFFFFF', boxShadow: '0 6px 16px -6px rgba(37,99,235,0.35)' };
                return (
                  <button
                    key={item.id}
                    data-pill-id={item.id}
                    onClick={() => handleNav(item.id)}
                    className="flex-shrink-0 inline-flex items-center gap-2 px-4 py-2.5 rounded-full text-sm font-semibold transition-all whitespace-nowrap"
                    style={
                      active
                        ? activeStyle
                        : { color: 'var(--theme-text-muted)', background: 'transparent' }
                    }
                    data-testid={`crm-nav-${item.id}`}
                  >
                    <Icon size={14} className="shrink-0" />
                    <span>{t(item.labelKey)}</span>
                  </button>
                );
              })}
            </PillTabBar>

            {/* Mobile horizontal scroller — same pill style, tighter padding. */}
            <nav
              aria-label="CRM sections (mobile)"
              className="md:hidden flex gap-2 overflow-x-auto scrollbar-hide pb-1 -mx-1 px-1 pulse-font-body"
              style={{ WebkitOverflowScrolling: 'touch' }}
            >
              {visibleNavItems.map((item) => {
                const Icon = item.icon;
                const active = activeTab === item.id;
                const activeStyleMobile = isPulseBrandedCRM
                  ? { background: brandCfg.accent, color: 'var(--color-ink)' }
                  : { backgroundImage: 'linear-gradient(135deg, var(--gx-brand-from) 0%, var(--gx-brand-to) 100%)', color: '#FFFFFF' };
                return (
                  <button
                    key={item.id}
                    onClick={() => handleNav(item.id)}
                    className="flex-shrink-0 inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-xs font-semibold whitespace-nowrap transition-colors"
                    style={
                      active
                        ? activeStyleMobile
                        : { color: 'var(--theme-text-muted)', background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }
                    }
                    data-testid={`crm-nav-mobile-${item.id}`}
                  >
                    <Icon size={12} className="shrink-0" />
                    <span>{t(item.labelKey)}</span>
                  </button>
                );
              })}
            </nav>
          </div>
        )}

        {/* Mobile overlay (kept for legacy slide-out / global search) */}
        {mobileOpen && (
          <div className="fixed inset-0 z-[60] md:hidden" style={{ background: isDark ? 'rgba(0,0,0,0.6)' : 'rgba(0,0,0,0.3)' }} onClick={() => setMobileOpen(false)} data-testid="crm-mobile-overlay" />
        )}

        {/* Main area — content starts directly under the tabs bar */}
        <div className="min-h-screen">
          <div className="max-w-7xl mx-auto p-3 sm:p-4 md:p-8 overflow-x-hidden">
            {renderContent()}
          </div>
        </div>

        {/* Demo Tour */}
        {showTour && <CRMDemoTour onClose={() => setShowTour(false)} onNavigate={handleNav} />}
      </div>
    </CRMContext.Provider>
  );
}
