import React, { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '@/App';
import { bfpo } from './bfpoApi';
import { Spinner, Btn, PULSE_LOGO } from './ui';
import Navbar from '@/components/shared/Navbar';
import PillTabBar from '@/components/shared/PillTabBar';
import AccountMenu from './AccountMenu';
import Footer from './Footer';
import EngineerHome from './engineer/EngineerHome';
import JobList from './engineer/JobList';
import JobDetail from './engineer/JobDetail';
import Sites from './engineer/Sites';
import Equipment from './engineer/Equipment';
import History from './engineer/History';
import WelcomeKit from './engineer/WelcomeKit';
import StaffDashboard from './staff/StaffDashboard';
import StaffSites from './staff/StaffSites';
import StaffJobs from './staff/StaffJobs';
import StaffJobDetail from './staff/StaffJobDetail';
import StaffVisiting from './staff/StaffVisiting';
import StaffEngineers from './staff/StaffEngineers';
import PPMEngineerList from './ppm/PPMEngineerList';
import PPMServiceDetail from './ppm/PPMServiceDetail';
import PPMStaff from './ppm/PPMStaff';
import PPMReports from './ppm/PPMReports';
import {
  Home, ClipboardList, MapPin, Package, History as HistoryIcon, Globe2,
  LayoutGrid, LogOut, Wifi, WifiOff, ClipboardCheck, BarChart3, Users,
} from 'lucide-react';

export default function BFPOApp() {
  const { user, loading: authLoading, logout: platformLogout } = useAuth();
  // A Pulse Fitness staffer granted the MOD Operations module (platform admins
  // always qualify) gets the staff operations view even without a bfpo_role.
  const hasModOps = !!(user && (user.is_master_admin || user.is_pulse_admin
    || (user.module_overrides && user.module_overrides.mod_operations === true)));
  const rawRole = (user?.bfpo_role || '').toLowerCase();
  const role = ['engineer', 'lead', 'staff'].includes(rawRole) ? rawRole : (hasModOps ? 'staff' : '');
  const [view, setView] = useState('home');
  const [jobId, setJobId] = useState(null);
  const [jobFilter, setJobFilter] = useState('all_open');
  const [staffFilter, setStaffFilter] = useState({});
  const [ppmId, setPpmId] = useState(null);
  const [online, setOnline] = useState(typeof navigator === 'undefined' ? true : navigator.onLine);
  const [welcome, setWelcome] = useState(null);

  useEffect(() => {
    let alive = true;
    if (user && (role === 'engineer' || role === 'lead')) {
      bfpo.get('/me/welcome').then((r) => { if (alive && r.data.show) setWelcome(r.data); }).catch(() => {});
    }
    return () => { alive = false; };
  }, [user, role]);

  const dismissWelcome = async () => {
    try { await bfpo.post('/me/welcome/dismiss'); } catch { /* ignore */ }
    setWelcome(null);
  };

  useEffect(() => { setView(role === 'staff' ? 'dashboard' : 'home'); }, [role]);

  useEffect(() => {
    const on = () => setOnline(true); const off = () => setOnline(false);
    window.addEventListener('online', on); window.addEventListener('offline', off);
    return () => { window.removeEventListener('online', on); window.removeEventListener('offline', off); };
  }, []);

  if (authLoading) return <div className="min-h-screen bg-[#F8F9FA]"><Spinner label="Loading portal…" /></div>;
  // Not signed in → send to the standard MOD service login screen.
  if (!user) return <Navigate to="/MODService" replace />;
  // Signed in but not a MOD/BFPO account → friendly no-access card.
  if (!['engineer', 'lead', 'staff'].includes(role)) {
    return (
      <div className="min-h-screen bg-[#F8F9FA] flex items-center justify-center p-6" data-testid="bfpo-no-access">
        <div className="text-center max-w-sm">
          <p className="text-lg font-bold text-[#212721]">This area is for MOD/BFPO personnel</p>
          <p className="text-sm text-[#505759] mt-1">Your account doesn't have access to the BFPO Engineer Portal.</p>
          <a href="/dashboard" className="inline-block mt-4"><Btn variant="primary">Go to your dashboard</Btn></a>
        </div>
      </div>
    );
  }
  // MOD Operations overview dashboard is module-gated to select Pulse staff.
  if (role === 'staff' && !hasModOps) {
    return (
      <div className="min-h-screen bg-[#F8F9FA] flex items-center justify-center p-6" data-testid="bfpo-no-modops">
        <div className="text-center max-w-sm">
          <p className="text-lg font-bold text-[#212721]">Pulse Fitness MOD Operations</p>
          <p className="text-sm text-[#505759] mt-1">Your account isn't enabled for the MOD Operations overview dashboard. Ask a Master Admin to grant you the <span className="font-semibold">Pulse Fitness MOD Operations</span> module.</p>
          <a href="/dashboard" className="inline-block mt-4"><Btn variant="primary">Go to your dashboard</Btn></a>
        </div>
      </div>
    );
  }

  const logout = () => { if (platformLogout) platformLogout(); };
  const openJob = (id) => { setJobId(id); setView('job'); };
  const openStaffJob = (id) => { setJobId(id); setView('staffjob'); };
  const openPpm = (id) => { setPpmId(id); setView('ppmdetail'); };

  const engNav = [
    { key: 'home', label: 'Home', icon: Home },
    { key: 'jobs', label: 'Jobs', icon: ClipboardList },
    { key: 'sites', label: 'Sites', icon: MapPin },
    { key: 'equipment', label: 'Kit', icon: Package },
    { key: 'history', label: 'History', icon: HistoryIcon },
  ];
  const staffNav = [
    { key: 'dashboard', label: 'Dashboard', icon: LayoutGrid },
    { key: 'sites', label: 'Sites', icon: Globe2 },
    { key: 'jobs', label: 'Jobs', icon: ClipboardList },
    { key: 'servicing', label: 'Servicing', icon: ClipboardCheck },
    { key: 'reports', label: 'Reports', icon: BarChart3 },
    { key: 'engineers', label: 'Engineers', icon: Users },
  ];

  const Header = role === 'staff' ? (
    <>
      <Navbar />
      <div className="pt-24 pulse-font" style={{ background: 'var(--theme-bg)' }}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <h1 className="text-2xl sm:text-4xl tracking-tight font-semibold pulse-font-heading leading-tight" style={{ color: 'var(--theme-text)' }}>MOD Operations</h1>
          <p className="mt-1 text-sm pulse-font-body" style={{ color: 'var(--theme-text-muted)' }} data-testid="staff-welcome">
            Welcome back, <span className="font-medium" style={{ color: 'var(--theme-text)' }}>{user.full_name || 'Operations'}</span> · Global oversight
          </p>
          <PillTabBar className="mt-6 mb-2 w-full" activeId={view} testId="staff-nav-tabs" ariaLabel="MOD Operations sections">
            {staffNav.map((n) => {
              const isActive = view === n.key;
              return (
                <button key={n.key} data-pill-id={n.key} onClick={() => setView(n.key)} data-testid={`staff-nav-${n.key}`}
                  className="flex-shrink-0 inline-flex items-center gap-2 px-4 py-2.5 rounded-full text-sm font-semibold transition-colors whitespace-nowrap"
                  style={isActive
                    ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
                    : { color: 'var(--theme-text-muted)', background: 'transparent' }}>
                  <n.icon size={14} /> {n.label}
                </button>
              );
            })}
          </PillTabBar>
        </div>
      </div>
    </>
  ) : (
    <header className="sticky top-0 z-30" style={{ fontFamily: "'Proxima Nova', 'Inter', system-ui, sans-serif" }}>
      <div className="on-dark text-white border-b border-white/10" style={{ backgroundColor: '#000000' }}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-20 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <img src={PULSE_LOGO} alt="Pulse Fitness" className="h-10 rounded-md object-cover"
              style={{ objectPosition: 'center', aspectRatio: '3.8/1', clipPath: 'inset(12% 3% 12% 3% round 6px)' }}
              data-testid="bfpo-logo" />
          </div>
          <AccountMenu user={user} role={role} online={online} onLogout={logout} showSync />
        </div>
      </div>
    </header>
  );

  return (
    <div className={`min-h-screen flex flex-col ${role === 'staff' ? 'pulse-font overflow-x-hidden' : 'bg-[#F8F9FA]'}`} style={role === 'staff' ? { background: 'var(--theme-bg)' } : undefined}>
      {welcome && <WelcomeKit data={welcome} onStart={dismissWelcome} onViewJobs={() => { dismissWelcome(); setJobFilter('all_open'); setView('jobs'); }} />}
      {Header}
      <main className="flex-1">
        {role === 'staff' ? (
          <>
            {view === 'dashboard' && <StaffDashboard userName={user.full_name} role={role} onOpenJobs={(f) => { setStaffFilter(f); setView('jobs'); }} onOpenJob={openStaffJob} />}
            {view === 'sites' && <StaffSites onOpenJobs={(f) => { setStaffFilter(f); setView('jobs'); }} />}
            {view === 'jobs' && <StaffJobs initialFilter={staffFilter} onOpenJob={openStaffJob} />}
            {view === 'visiting' && <StaffVisiting />}
            {view === 'engineers' && <StaffEngineers />}
            {view === 'servicing' && <PPMStaff onOpen={openPpm} />}
            {view === 'reports' && <PPMReports />}
            {view === 'staffjob' && <StaffJobDetail jobId={jobId} onBack={() => setView('jobs')} />}
            {view === 'ppmdetail' && <PPMServiceDetail serviceId={ppmId} onBack={() => setView('servicing')} />}
          </>
        ) : (
          <>
            {view === 'home' && <EngineerHome onOpenJobs={(f) => { setJobFilter(f); setView('jobs'); }} onOpenJob={openJob} onOpenServices={() => setView('ppm')} />}
            {view === 'jobs' && <JobList initialFilter={jobFilter} onOpenJob={openJob} />}
            {view === 'sites' && <Sites />}
            {view === 'equipment' && <Equipment />}
            {view === 'history' && <History onOpenJob={openJob} />}
            {view === 'job' && <JobDetail jobId={jobId} onBack={() => setView('jobs')} onOpenJob={openJob} />}
            {view === 'ppm' && <PPMEngineerList onOpen={openPpm} onBack={() => setView('home')} />}
            {view === 'ppmdetail' && <PPMServiceDetail serviceId={ppmId} onBack={() => setView('ppm')} />}
          </>
        )}
      </main>

      <div className={role !== 'staff' ? 'pb-16' : ''}><Footer /></div>

      {/* Engineer bottom nav */}
      {role !== 'staff' && (
        <nav className="fixed bottom-0 left-0 right-0 bg-white border-t border-slate-200 z-30" data-testid="engineer-bottom-nav">
          <div className="max-w-2xl mx-auto grid grid-cols-5">
            {engNav.map((n) => {
              const active = view === n.key || (view === 'job' && n.key === 'jobs');
              return (
                <button key={n.key} onClick={() => setView(n.key)} data-testid={`eng-nav-${n.key}`}
                  className={`flex flex-col items-center gap-0.5 py-2.5 text-[11px] font-medium ${active ? 'text-cyan-600' : 'text-slate-400'}`}>
                  <n.icon className="w-5 h-5" /> {n.label}
                </button>
              );
            })}
          </div>
        </nav>
      )}
    </div>
  );
}
