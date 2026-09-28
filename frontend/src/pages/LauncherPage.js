/**
 * LauncherPage — the post-login chooser (one login → pick a destination).
 *
 * A staff member signs in once at /login, then chooses their Staff Portal or
 * any platform module they can access. If there's only one destination we skip
 * the chooser and go straight there, so this never adds friction for
 * single-purpose accounts.
 */
import { useEffect, useMemo, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import axios from 'axios';
import {
  Activity, Calendar, Briefcase, Rocket, MessagesSquare, Headset, Boxes,
  UserCircle, Loader2, ArrowRight, ShieldAlert,
} from 'lucide-react';
import { useAuth } from '@/App';
import Navbar from '@/components/shared/Navbar';
import { hasModuleAccess } from '@/components/shared/ModuleSwitcher';
import { moduleHomePath } from '@/utils/moduleHome';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
// Per-device "remember my area" — the operator-company staffer's chosen launch
// area. Auto-forwarded to on next login; bypass with /launch?choose=1.
const DEFAULT_AREA_KEY = 'pf_launcher_default_area';

export default function LauncherPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [access, setAccess] = useState(null); // {has_staff_portal, full_name}
  const [remember, setRemember] = useState(true);
  const forceChoose = (() => {
    try { return new URLSearchParams(window.location.search).get('choose') === '1'; }
    catch { return false; }
  })();

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) { setAccess({ has_staff_portal: false }); return; }
    axios.get(`${API}/staffing/me/portal-access`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => setAccess(r.data))
      .catch(() => setAccess({ has_staff_portal: false }));
  }, []);

  const opsPath = (user?.account_type === 'lite' || user?.account_type === 'pulse_pro') ? '/pulse' : '/dashboard';
  const MODS = [
    { key: 'operations', label: 'Operations', path: opsPath, icon: Activity, desc: 'Dashboard, faults, reports and site ops.' },
    { key: 'service_desk', label: 'Service Desk', path: '/service-desk', icon: Headset, desc: 'Cases, engineers and scheduling.' },
    { key: 'inventory', label: 'Inventory', path: '/inventory', icon: Boxes, desc: 'Stock, distribution and installs.' },
    { key: 'memberships', label: 'Memberships', path: '/memberships', icon: Calendar, desc: 'Members, classes and revenue.' },
    { key: 'crm', label: 'CRM', path: '/crm', icon: Briefcase, desc: 'Sales pipeline and contracts.' },
    { key: 'marketing', label: 'Marketing', path: '/marketing', icon: Rocket, desc: 'Campaigns, journeys and AI.' },
    { key: 'comms', label: 'Comms Centre', path: '/comms', icon: MessagesSquare, desc: 'Member + B2B communications.' },
  ];

  const destinations = useMemo(() => {
    if (!user || !access) return null;
    const out = [];
    if (access.has_staff_portal) {
      out.push({ key: 'staff', label: 'Staff Portal', path: '/staff-portal', icon: UserCircle,
        desc: 'Your day, time, holidays and payslip info.', accent: '#0891b2' });
    }
    MODS.filter((m) => hasModuleAccess(user, m.key)).forEach((m) => out.push(m));
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, access]);

  const go = async (dest) => {
    // Remember my area — persist (or clear) the chosen area so next login
    // jumps straight here. Toggle off to keep seeing the chooser.
    try {
      if (remember) localStorage.setItem(DEFAULT_AREA_KEY, dest.key);
      else localStorage.removeItem(DEFAULT_AREA_KEY);
    } catch { /* quota */ }
    if (dest.key === 'crm') {
      const token = localStorage.getItem('token');
      if (token) {
        try {
          const res = await axios.post(`${API}/crm/auth/cross-login`, {}, { headers: { Authorization: `Bearer ${token}` } });
          if (res.data?.token) { localStorage.setItem('crm_token', res.data.token); sessionStorage.setItem('crm_active_session', '1'); }
        } catch { /* CRMApp will redirect if needed */ }
      }
    }
    navigate(dest.path);
  };

  if (!user) return <Navigate to="/login" replace />;

  // Master admin + partner engineer keep their dedicated homes.
  if (user.is_master_admin || user.is_pulse_admin || user.role === 'master_admin') return <Navigate to="/master-admin" replace />;
  if (user.is_partner_engineer || user.account_type === 'partner_engineer' || user.role === 'engineer_partner') return <Navigate to="/partner-engineer" replace />;
  // Service-Desk self-serve providers finish the setup wizard first.
  if (user.is_service_desk && user.service_ops_setup_complete === false) return <Navigate to="/service-desk/setup" replace />;

  if (!destinations) {
    return (
      <div className="min-h-screen flex items-center justify-center pulse-font" style={{ background: 'var(--theme-bg)' }}>
        <Loader2 className="animate-spin text-cyan-500" size={30} />
      </div>
    );
  }
  if (destinations.length === 0) {
    // A bolt-on-only entitlement (e.g. Memberships-only) has a natural home.
    const home = moduleHomePath(user);
    if (home) return <Navigate to={home} replace />;
    // Genuinely no entitled area — show a clear no-access state. We must NEVER
    // bounce to /dashboard here: the Operations guard would send a
    // non-Operations user straight back to /launch, creating a redirect loop.
    return (
      <div className="min-h-screen pulse-font" style={{ background: 'var(--theme-bg)' }} data-testid="launcher-no-access">
        <Navbar />
        <div className="pt-24 pb-12 flex items-center justify-center px-4">
          <div className="w-full max-w-md rounded-2xl p-8 text-center"
            style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', boxShadow: 'var(--theme-card-shadow)' }}>
            <div className="w-12 h-12 rounded-xl mx-auto flex items-center justify-center" style={{ background: '#f59e0b1f', color: '#d97706' }}>
              <ShieldAlert size={24} />
            </div>
            <h1 className="mt-4 text-xl font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>No areas assigned yet</h1>
            <p className="mt-2 text-sm pulse-font-body" style={{ color: 'var(--theme-text-muted)' }}>
              Your account doesn't have access to any modules or the Staff Portal.
              Please ask your manager or administrator to grant you access.
            </p>
          </div>
        </div>
      </div>
    );
  }
  // The area selector is a Pulse Fitness Ltd (operator company) feature. Any
  // other company never sees the chooser — forward them straight to their
  // primary module (a real module, not the Staff Portal), exactly as before.
  if (user.is_operator_company !== true) {
    const primary = destinations.find((d) => d.key !== 'staff') || destinations[0];
    return <Navigate to={primary.path} replace />;
  }
  if (destinations.length === 1) return <Navigate to={destinations[0].path} replace />;

  // Remember my area — jump straight to the saved area next login, unless the
  // user explicitly asked to re-choose (/launch?choose=1). Only ever applies
  // to the operator-company chooser and to an area they still have access to.
  const savedKey = (() => { try { return localStorage.getItem(DEFAULT_AREA_KEY); } catch { return null; } })();
  const savedDest = savedKey ? destinations.find((d) => d.key === savedKey) : null;
  if (!forceChoose && savedDest) return <Navigate to={savedDest.path} replace />;

  const clearDefault = () => { try { localStorage.removeItem(DEFAULT_AREA_KEY); } catch { /* ignore */ } setRemember(false); };

  const first = (user.full_name || user.name || '').split(' ')[0] || 'there';
  return (
    <div className="min-h-screen overflow-x-hidden pulse-font" style={{ background: 'var(--theme-bg)' }} data-testid="launcher-page">
      <Navbar />
      <div className="pt-24 pb-12 module-fade-in">
        <div className="w-full max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="mb-8">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] pulse-font-body" style={{ color: 'var(--color-brand-cyan)' }}>Pulse Fitness</div>
            <h1 className="mt-1 text-2xl sm:text-4xl tracking-tight font-semibold pulse-font-heading leading-tight" style={{ color: 'var(--theme-text)' }}>Welcome back, {first}</h1>
            <p className="mt-1 pulse-font-body" style={{ color: 'var(--theme-text-muted)' }}>Where would you like to go today?</p>
            {savedDest && forceChoose && (
              <p className="mt-2 text-xs pulse-font-body" style={{ color: 'var(--theme-text-muted)' }} data-testid="launcher-current-default">
                Your usual area is <span style={{ color: 'var(--theme-text)', fontWeight: 600 }}>{savedDest.label}</span>.{' '}
                <button onClick={clearDefault} className="underline hover:opacity-80" style={{ color: 'var(--color-brand-cyan)' }} data-testid="launcher-clear-default">
                  Ask me every time
                </button>
              </p>
            )}
          </div>
          <label className="mb-4 flex items-center gap-2 cursor-pointer select-none w-fit" data-testid="launcher-remember-toggle">
            <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)}
              className="h-4 w-4 rounded accent-cyan-500" data-testid="launcher-remember-checkbox" />
            <span className="text-sm pulse-font-body" style={{ color: 'var(--theme-text-muted)' }}>
              Remember my choice and take me straight there next time
            </span>
          </label>
          <div className="grid sm:grid-cols-2 gap-4">
            {destinations.map((d) => {
              const Icon = d.icon;
              const tint = d.accent || '#0891b2';
              return (
                <button key={d.key} onClick={() => go(d)} data-testid={`launch-${d.key}`}
                  className="group text-left rounded-2xl p-5 transition-all active:scale-[0.99] hover:-translate-y-0.5"
                  style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)', boxShadow: 'var(--theme-card-shadow)' }}>
                  <div className="flex items-start justify-between">
                    <div className="w-11 h-11 rounded-xl flex items-center justify-center"
                      style={{ background: `${tint}1f`, color: tint }}>
                      <Icon size={22} />
                    </div>
                    <ArrowRight size={18} style={{ color: 'var(--theme-text-muted)' }}
                      className="group-hover:translate-x-0.5 transition-transform" />
                  </div>
                  <div className="mt-3 text-lg font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{d.label}</div>
                  <div className="text-sm pulse-font-body" style={{ color: 'var(--theme-text-muted)' }}>{d.desc}</div>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
