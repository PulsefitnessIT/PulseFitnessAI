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
  UserCircle, Loader2, ArrowRight,
} from 'lucide-react';
import { useAuth } from '@/App';
import { hasModuleAccess } from '@/components/shared/ModuleSwitcher';
import { moduleHomePath } from '@/utils/moduleHome';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function LauncherPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [access, setAccess] = useState(null); // {has_staff_portal, full_name}

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
    return <div className="min-h-screen flex items-center justify-center bg-slate-50"><Loader2 className="animate-spin text-cyan-500" size={30} /></div>;
  }
  if (destinations.length === 0) return <Navigate to={moduleHomePath(user) || '/dashboard'} replace />;
  if (destinations.length === 1) return <Navigate to={destinations[0].path} replace />;

  const first = (user.full_name || user.name || '').split(' ')[0] || 'there';
  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center px-4 py-12" data-testid="launcher-page">
      <div className="w-full max-w-3xl">
        <div className="mb-8">
          <div className="text-sm font-semibold uppercase tracking-[0.18em] text-cyan-600">Pulse Fitness</div>
          <h1 className="mt-1 text-3xl font-bold text-slate-900">Welcome back, {first}</h1>
          <p className="text-slate-500 mt-1">Where would you like to go today?</p>
        </div>
        <div className="grid sm:grid-cols-2 gap-4">
          {destinations.map((d) => {
            const Icon = d.icon;
            return (
              <button key={d.key} onClick={() => go(d)} data-testid={`launch-${d.key}`}
                className="group text-left rounded-2xl bg-white border border-slate-200 p-5 shadow-sm hover:shadow-md hover:border-cyan-300 transition-all active:scale-[0.99]">
                <div className="flex items-start justify-between">
                  <div className="w-11 h-11 rounded-xl flex items-center justify-center"
                    style={{ background: `${d.accent || '#0f172a'}12`, color: d.accent || '#0f172a' }}>
                    <Icon size={22} />
                  </div>
                  <ArrowRight size={18} className="text-slate-300 group-hover:text-cyan-500 group-hover:translate-x-0.5 transition-all" />
                </div>
                <div className="mt-3 text-lg font-bold text-slate-900">{d.label}</div>
                <div className="text-sm text-slate-500">{d.desc}</div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
