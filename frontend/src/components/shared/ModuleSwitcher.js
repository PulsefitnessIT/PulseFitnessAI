/**
 * GymAxis Module Switcher
 *
 * A compact pill-shaped tab bar surfaced on every module's top bar so
 * operators with multi-module access can jump between:
 * • Operations — /pulse (Pulse Pro site operations / service desk)
 * • Memberships — /memberships (Studio / classes / revenue)
 * • Marketing — /marketing (Marketing Suite — campaigns, journeys, AI)
 * • CRM — /crm (Sales + contract pipeline)
 *
 * Renders only if the user has access to 2+ modules. Position and sizing
 * are identical across all modules so switching is visually stable — the
 * active pill slides to its slot via a smooth background transition.
 */
import React from 'react';
import axios from 'axios';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Activity, Calendar, Briefcase, Rocket } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';

const MODULES = [
 { id: 'operations', path: '/pulse', label: 'Operations', icon: Activity, accessKey: 'operations' },
 { id: 'memberships', path: '/memberships', label: 'Memberships', icon: Calendar, accessKey: 'memberships' },
 { id: 'crm', path: '/crm', label: 'CRM', icon: Briefcase, accessKey: 'crm' },
 { id: 'marketing', path: '/marketing', label: 'Marketing', icon: Rocket, accessKey: 'marketing' },
];

// Iter 215d5 — Operations module resolves to two different surfaces depending
// on which brand context the user is currently in:
//
//   • `/pulse`     — Pulse Fitness Pro self-service dashboard (cyan brand).
//   • `/dashboard` — GymAxis operator / master-admin dashboard (blue brand).
//
// Previously the switcher always routed to `/pulse`, which dumped GymAxis-
// branded users (master admin, GymAxis operators) onto a Pulse Fitness screen
// when they clicked Operations. This helper picks the right path.
function resolveOperationsPath(user, pathname) {
  // Explicit Pulse tenancy wins — they belong on `/pulse`.
  const accountType = user?.account_type;
  if (accountType === 'pulse_pro' || accountType === 'lite') return '/pulse';
  // Already browsing the Pulse self-service surface — keep them there.
  if (pathname && pathname.startsWith('/pulse')) return '/pulse';
  // Master admins hitting `/dashboard` get auto-redirected to `/master-admin`
  // unless the `?as=operator` flag is set. Preserve that flag so Operations
  // shows the GymAxis operator preview (the 9-tab surface) instead of the
  // Master Admin console, mirroring how the Pulse module works for them.
  const isMaster = user?.is_master_admin === true || user?.role === 'master_admin' || user?.role === 'master';
  if (isMaster) return '/dashboard?as=operator';
  // Everything else (GymAxis `full` orgs, MOD) → GymAxis portal.
  return '/dashboard';
}

function hasAccess(user, accessKey) {
 if (!user) return false;
 const isMaster = user.is_master_admin === true || user.role === 'master_admin' || user.role === 'master';
 if (isMaster) return true;
 const at = user.account_type;
 const isMod = at === 'mod_site' || at === 'mod_branch' || at === 'mod_org';

 const ma = user.moduleAccess || user.module_access;
 const hasExplicitFlag = ma && typeof ma === 'object' && accessKey in ma;

 // Iter 216c — respect explicit master-admin toggles FIRST.
 // Previous Iter 215dj guard hardcoded "Pulse Pro / Lite never get CRM"
 // which overrode the Master Admin Feature Control Panel even when the
 // operator had explicitly turned CRM on for that org. Now we trust the
 // explicit `module_access.<key>` flag (set by master admin in
 // FeatureControlPanel → saved to org.modules.<key>.enabled → resolved
 // by backend resolve_module_access on /auth/me).
 if (hasExplicitFlag) return !!ma[accessKey];

 // No explicit flag — fall back to historical defaults.
 if (isMod) return false;
 if (accessKey === 'crm') {
   // CRM not in module_access dict → only GymAxis-internal `full` orgs get
   // it by default. Pulse customers must have it explicitly toggled on.
   return at === 'full';
 }
 if (accessKey === 'operations') return at === 'pulse_pro' || at === 'full' || at === 'lite';
 if (accessKey === 'memberships') return at === 'pulse_pro' || at === 'full';
 if (accessKey === 'marketing') return at === 'pulse_pro' || at === 'full';
 return false;
}

export default function ModuleSwitcher({ user, current }) {
 const location = useLocation();
 const navigate = useNavigate();
 const { t } = useTranslation();
 const wrapRef = React.useRef(null);
 const [scrollable, setScrollable] = React.useState(false);
 // Iter 215d5 — rewrite module paths per brand context so Operations
 // takes GymAxis users to `/dashboard` and Pulse users to `/pulse`.
 const operationsPath = resolveOperationsPath(user, location.pathname);
 const available = MODULES
   .filter((m) => hasAccess(user, m.accessKey))
   .map((m) => (m.id === 'operations' ? { ...m, path: operationsPath } : m));

 // Toggle scrollable state on mount + resize so the edge-fade + chevrons
 // (future) only render when the track actually overflows.
 React.useEffect(() => {
 const el = wrapRef.current;
 if (!el) return;
 const check = () => setScrollable(el.scrollWidth > el.clientWidth + 1);
 check();
 const ro = new ResizeObserver(check);
 ro.observe(el);
 return () => ro.disconnect();
 }, [available.length]);

 if (available.length < 2) return null;

 // SSO bridge: when the user clicks "CRM" from any other module, exchange
 // their main JWT for a CRM-scoped token via /crm/auth/cross-login, store
 // it in localStorage, THEN navigate. Without this the CRM app has no
 // `crm_token` and bounces the user to CRMLogin.
 const handleClick = async (e, m) => {
 if (m.id !== 'crm') return; // standard <Link> behaviour for everything else
 if (location.pathname.startsWith('/crm')) return;
 e.preventDefault();
 const mainToken = localStorage.getItem('token');
 if (mainToken) {
 try {
 const res = await axios.post(`${API}/crm/auth/cross-login`, {}, {
 headers: { Authorization: `Bearer ${mainToken}` },
 });
 if (res.data?.token) {
 localStorage.setItem('crm_token', res.data.token);
 sessionStorage.setItem('crm_active_session', '1');
 }
 } catch { /* fall through — CRMApp will redirect to login if needed */ }
 }
 navigate('/crm');
 };

 // Auto-derive current when not given via prop.
 let active = current;
 if (!active) {
   // Iter 215d5 — both `/dashboard` and `/pulse` map to the Operations
   // module, so check those two prefixes first before falling back to
   // the generic pathname-startswith match for the other modules.
   const p = location.pathname || '';
   if (p.startsWith('/dashboard') || p.startsWith('/pulse')) {
     active = 'operations';
   } else {
     const match = MODULES.find((m) => m.id !== 'operations' && p.startsWith(m.path));
     active = match?.id;
   }
 }
 // Back-compat — accept legacy prop values "pulse" / "mod".
 if (active === 'pulse') active = 'operations';

 return (
 <div
 ref={wrapRef}
 className="gx-module-switcher-wrap max-w-full overflow-x-auto overflow-y-hidden -mx-1 px-1 scroll-smooth scrollbar-hide"
 style={{
 WebkitOverflowScrolling: 'touch',
 // Iter 215c5 → c6: conditional fade. Only apply the mask when the
 // track overflows (measured by the ResizeObserver above) so desktop
 // users with all 4 pills fitting don't see a subtle fade for no
 // reason. Matches the PillTabBar behaviour used in every module.
 maskImage: scrollable
 ? 'linear-gradient(to right, transparent 0, black 14px, black calc(100% - 14px), transparent 100%)'
 : undefined,
 WebkitMaskImage: scrollable
 ? 'linear-gradient(to right, transparent 0, black 14px, black calc(100% - 14px), transparent 100%)'
 : undefined,
 }}
 data-scrollable={scrollable ? 'true' : 'false'}
 >
 <nav
 aria-label="Module switcher"
 data-testid="module-switcher"
 className="inline-flex items-center gap-1 p-1 rounded-full border shadow-sm whitespace-nowrap"
 style={{
 background: 'var(--theme-surface, rgba(255,255,255,0.05))',
 borderColor: 'var(--theme-border, rgba(255,255,255,0.1))',
 }}
 >
 {available.map((m) => {
 const Icon = m.icon;
 const on = active === m.id;
 return (
 <Link
 key={m.id}
 to={m.path}
 onClick={(e) => handleClick(e, m)}
 data-testid={`module-switcher-${m.id}`}
 aria-current={on ? 'page' : undefined}
 className={`flex-shrink-0 flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-[11px] font-extrabold uppercase tracking-wider transition-all duration-300 ease-out ${
 on
 ? 'bg-[var(--color-brand-cyan)] text-[var(--color-surface-darker)] shadow-md scale-[1.02]'
 : 'text-[color:var(--theme-text-muted,rgba(255,255,255,0.6))] hover:text-[color:var(--theme-text,#fff)] hover:bg-black/5 dark:hover:bg-white/5'
 }`}
 >
 <Icon size={12} />
 {t(`modules.${m.id}`, m.label)}
 </Link>
 );
 })}
 </nav>
 </div>
 );
}
