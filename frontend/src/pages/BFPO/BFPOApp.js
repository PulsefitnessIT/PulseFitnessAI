import React, { useEffect, useState, useCallback } from 'react';
import { bfpo, bfpoToken } from './bfpoApi';
import BFPOLogin from './BFPOLogin';
import { Spinner } from './ui';
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
  const [me, setMe] = useState(undefined); // undefined=loading, null=logged out
  const [view, setView] = useState('home');
  const [jobId, setJobId] = useState(null);
  const [jobFilter, setJobFilter] = useState('all_open');
  const [staffFilter, setStaffFilter] = useState({});
  const [online, setOnline] = useState(typeof navigator === 'undefined' ? true : navigator.onLine);

  const loadMe = useCallback(async () => {
    if (!bfpoToken.get()) { setMe(null); return; }
    try { const r = await bfpo.get('/me'); setMe(r.data); setView(r.data.user.role === 'staff' ? 'dashboard' : 'home'); }
    catch { bfpoToken.clear(); setMe(null); }
  }, []);
  useEffect(() => { loadMe(); }, [loadMe]);

  useEffect(() => {
    const on = () => setOnline(true); const off = () => setOnline(false);
    window.addEventListener('online', on); window.addEventListener('offline', off);
    return () => { window.removeEventListener('online', on); window.removeEventListener('offline', off); };
  }, []);

  if (me === undefined) return <div className="min-h-screen bg-slate-50"><Spinner label="Loading portal…" /></div>;
  if (me === null) return <BFPOLogin onLoggedIn={() => loadMe()} />;

  const role = me.user.role;
  const logout = () => { bfpoToken.clear(); setMe(null); };
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
      <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-cyan-600 flex items-center justify-center"><Globe2 className="w-4 h-4" /></div>
          <div className="leading-tight">
            <p className="font-bold text-sm">Pulse Fitness</p>
            <p className="text-[10px] text-cyan-400 font-semibold uppercase tracking-wide">MOD / BFPO {role === 'staff' ? 'Operations' : 'Engineer'}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className={`flex items-center gap-1 text-xs ${online ? 'text-emerald-400' : 'text-amber-400'}`} data-testid="bfpo-online">
            {online ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}{online ? 'Synced' : 'Offline'}
          </span>
          <button onClick={logout} className="flex items-center gap-1 text-xs text-slate-300 hover:text-white" data-testid="bfpo-logout"><LogOut className="w-4 h-4" /> Sign out</button>
        </div>
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
    <div className="min-h-screen bg-slate-50 pb-16">
      {Header}
      <main>
        {role === 'staff' ? (
          <>
            {view === 'dashboard' && <StaffDashboard onOpenJobs={(f) => { setStaffFilter(f); setView('jobs'); }} onOpenJob={openStaffJob} />}
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
