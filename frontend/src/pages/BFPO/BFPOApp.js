import React, { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '@/App';
import { bfpo } from './bfpoApi';
import { Spinner, Btn, PULSE_LOGO } from './ui';
import AccountMenu from './AccountMenu';
import EngineerHome from './engineer/EngineerHome';
import JobList from './engineer/JobList';
import JobDetail from './engineer/JobDetail';
import Sites from './engineer/Sites';
import Equipment from './engineer/Equipment';
import History from './engineer/History';
import StaffDashboard from './staff/StaffDashboard';
import StaffSites from './staff/StaffSites';
import StaffJobs from './staff/StaffJobs';
import StaffJobDetail from './staff/StaffJobDetail';
import StaffVisiting from './staff/StaffVisiting';
import {
  Home, ClipboardList, MapPin, Package, History as HistoryIcon, Globe2,
  LayoutGrid, KeyRound, LogOut, Wifi, WifiOff,
} from 'lucide-react';

export default function BFPOApp() {
  const { user, loading: authLoading, logout: platformLogout } = useAuth();
  const role = user?.bfpo_role || '';
  const [view, setView] = useState('home');
  const [jobId, setJobId] = useState(null);
  const [jobFilter, setJobFilter] = useState('all_open');
  const [staffFilter, setStaffFilter] = useState({});
  const [online, setOnline] = useState(typeof navigator === 'undefined' ? true : navigator.onLine);

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

  const logout = () => { if (platformLogout) platformLogout(); };
  const openJob = (id) => { setJobId(id); setView('job'); };
  const openStaffJob = (id) => { setJobId(id); setView('staffjob'); };

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
    { key: 'visiting', label: 'Visiting Access', icon: KeyRound },
  ];

  const Header = (
    <header className="bg-slate-900 text-white sticky top-0 z-30">
      <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="bg-white rounded-lg px-2.5 py-1.5 flex items-center" data-testid="bfpo-logo-chip">
            <img src={PULSE_LOGO} alt="Pulse Fitness" className="h-6 w-auto object-contain" data-testid="bfpo-logo" />
          </div>
        </div>
        <AccountMenu user={user} role={role} online={online} onLogout={logout} />
      </div>
      {role === 'staff' && (
        <div className="max-w-6xl mx-auto px-4 flex gap-1 overflow-x-auto">
          {staffNav.map((n) => (
            <button key={n.key} onClick={() => setView(n.key)} data-testid={`staff-nav-${n.key}`}
              className={`flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium border-b-2 whitespace-nowrap transition-colors ${view === n.key ? 'border-cyan-400 text-white' : 'border-transparent text-slate-400 hover:text-white'}`}>
              <n.icon className="w-4 h-4" /> {n.label}
            </button>
          ))}
        </div>
      )}
    </header>
  );

  return (
    <div className="min-h-screen bg-[#F8F9FA] pb-16">
      {Header}
      <main>
        {role === 'staff' ? (
          <>
            {view === 'dashboard' && <StaffDashboard userName={user.full_name} role={role} onOpenJobs={(f) => { setStaffFilter(f); setView('jobs'); }} onOpenJob={openStaffJob} />}
            {view === 'sites' && <StaffSites onOpenJobs={(f) => { setStaffFilter(f); setView('jobs'); }} />}
            {view === 'jobs' && <StaffJobs initialFilter={staffFilter} onOpenJob={openStaffJob} />}
            {view === 'visiting' && <StaffVisiting />}
            {view === 'staffjob' && <StaffJobDetail jobId={jobId} onBack={() => setView('jobs')} />}
          </>
        ) : (
          <>
            {view === 'home' && <EngineerHome onOpenJobs={(f) => { setJobFilter(f); setView('jobs'); }} onOpenJob={openJob} />}
            {view === 'jobs' && <JobList initialFilter={jobFilter} onOpenJob={openJob} />}
            {view === 'sites' && <Sites />}
            {view === 'equipment' && <Equipment />}
            {view === 'history' && <History onOpenJob={openJob} />}
            {view === 'job' && <JobDetail jobId={jobId} onBack={() => setView('jobs')} onOpenJob={openJob} />}
          </>
        )}
      </main>

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
