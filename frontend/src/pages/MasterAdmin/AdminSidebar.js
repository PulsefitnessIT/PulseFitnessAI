import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { X, Wrench, LogOut, HeadphonesIcon, Layers, Sparkles } from 'lucide-react';
import { SIDEBAR_ITEMS, SECTION_TO_GROUP } from './SidebarConfig';

/**
 * The full left-rail navigation: group headers, section buttons, portal switcher,
 * and log-out action. Mobile off-canvas behaviour is controlled by
 * parent via `sidebarOpen`.
 *
 * Polls `/master-admin/support/cases?status=open` every 60s so the
 * Ask Support Desk item displays a red notification badge with the count
 * of unresolved escalations — guides the admin to the cases that need
 * attention without them having to remember to check.
 */
const AdminSidebar = ({
 section, setSection, setSearch,
 sidebarOpen, setSidebarOpen,
 onLogout, onPulseSwitch, onGymAxisSwitch,
 isPulseAdmin = false,
}) => {
 const navigate = useNavigate();
 const [openCases, setOpenCases] = useState(0);

 useEffect(() => {
 const API = process.env.REACT_APP_BACKEND_URL;
 const headers = { Authorization: `Bearer ${localStorage.getItem('token')}` };
 let cancelled = false;
 const fetchOpen = async () => {
 try {
 const { data } = await axios.get(`${API}/api/master-admin/support/cases`, {
 headers, params: { status: 'open', limit: 200 },
 });
 if (!cancelled) setOpenCases((data.cases || []).length);
 } catch { /* ignore — sidebar shouldn't crash on a missed poll */ }
 };
 fetchOpen();
 const tid = setInterval(fetchOpen, 60_000);
 return () => { cancelled = true; clearInterval(tid); };
 }, []);

 // Iter 215al — lock body scroll while the sidebar drawer is open on
 // mobile. Desktop is unaffected (sidebar is always-visible static at lg+).
 useEffect(() => {
   if (!sidebarOpen) return undefined;
   const prev = document.body.style.overflow;
   document.body.style.overflow = 'hidden';
   return () => { document.body.style.overflow = prev; };
 }, [sidebarOpen]);

 // Pulse Master Admins see the same console but with GymAxis-only items
 // (e.g. internal Service Desk membership management) hidden.
 const items = isPulseAdmin
 ? SIDEBAR_ITEMS.filter((i) => !i.gymaxisOnly)
 : SIDEBAR_ITEMS;
 return (
 <aside
 className={`fixed inset-y-0 left-0 z-50 w-72 bg-white border-r border-slate-200 flex flex-col transform transition-transform duration-200 ease-in-out lg:static lg:w-64 lg:translate-x-0 lg:z-auto ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}
 data-testid="admin-sidebar"
 >
 <div className="p-5 border-b border-slate-100 flex items-center justify-between">
 <div className="flex items-center gap-3">
 <div className="w-10 h-10 rounded-xl bg-white flex items-center justify-center overflow-hidden gx-grad-ring shadow-sm" data-testid="admin-sidebar-logo">
            <img src="/brand/gymaxis-mark-tight.png" alt="GymAxis" className="w-7 h-7 object-contain" draggable={false} />
          </div>
 <div>
 <p className="font-bold text-slate-900 text-sm tracking-tight">{isPulseAdmin ? 'Pulse Fitness' : 'GymAxis'}</p>
 <p className="text-[10px] text-slate-400 uppercase tracking-[0.16em] font-semibold">{isPulseAdmin ? 'Master Admin' : 'Admin Console'}</p>
 </div>
 </div>
 <button
 onClick={() => setSidebarOpen(false)}
 className="lg:hidden p-1 text-zinc-400 hover:text-zinc-700"
 data-testid="sidebar-close-btn"
 >
 <X size={20} />
 </button>
 </div>

 <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto">
 {(() => {
 let lastGroup = '';
 return items.map(item => {
 const showGroupLabel = item.group !== lastGroup;
 lastGroup = item.group;
 return (
 <React.Fragment key={item.id}>
 {showGroupLabel && item.group === 'integrations' && (
 <p className="text-[10px] text-slate-400 uppercase tracking-[0.16em] font-semibold px-3 pt-4 pb-1">Integrations</p>
 )}
 {showGroupLabel && item.group === 'tools' && (
 <p className="text-[10px] text-slate-400 uppercase tracking-[0.16em] font-semibold px-3 pt-4 pb-1">Tools</p>
 )}
 <button
 onClick={() => {
 const target = item.subTabs && item.subTabs.length
 ? (item.subTabs.find((s) => !s.gymaxisOnly || !isPulseAdmin) || item.subTabs[0]).id
 : item.id;
 setSection(target);
 setSearch('');
 setSidebarOpen(false);
 }}
 className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all ${
 (section === item.id || SECTION_TO_GROUP[section] === item.id)
 ? 'bg-gradient-to-r from-[var(--gx-brand-from)]/10 to-[var(--gx-brand-to)]/10 text-[var(--gx-brand-from)] font-semibold ring-1 ring-[var(--gx-brand-from)]/15'
 : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
 }`}
 data-testid={`sidebar-${item.id}`}
 >
 <item.icon size={16} />
 <span className="flex-1 text-left">{item.label}</span>
 {item.id === 'ask-support' && openCases > 0 && (
 <span
 className="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full bg-red-500 text-white text-[10px] font-bold leading-none"
 data-testid="sidebar-ask-support-badge"
 title={`${openCases} open enquir${openCases === 1 ? 'y' : 'ies'} need attention`}
 >
 {openCases > 99 ? '99+' : openCases}
 </span>
 )}
 </button>
 </React.Fragment>
 );
 });
 })()}
 </nav>

 {/* Portal Switcher */}
 <div className="px-3 pb-2">
 <p className="text-[10px] text-slate-400 uppercase tracking-[0.16em] font-semibold px-3 mb-2">Switch Portal</p>
 <div className="space-y-1">
 {!isPulseAdmin && (
 <button
 onClick={onGymAxisSwitch}
 className="w-full flex items-center gap-3 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 rounded-lg border border-slate-200 transition-colors"
 data-testid="portal-switch-gymaxis"
 >
 <Layers size={16} className="text-violet-500" /> GymAxis Portal
 </button>
 )}
 <button
 onClick={onPulseSwitch}
 className="w-full flex items-center gap-3 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 rounded-lg border border-slate-200 transition-colors"
 data-testid="portal-switch-pulse"
 >
 <Wrench size={16} className="text-blue-500" /> Pulse Fitness Portal
 </button>
 {!isPulseAdmin && (
 <button
 onClick={() => { window.location.href = '/service-desk'; }}
 className="w-full flex items-center gap-3 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 rounded-lg border border-slate-200 transition-colors"
 data-testid="portal-switch-service-desk"
 >
 <HeadphonesIcon size={16} className="text-orange-500" /> Service Desk
 </button>
 )}
 {!isPulseAdmin && (
 <button
 onClick={() => { navigate('/service-ops'); setSidebarOpen(false); }}
 className="w-full flex items-center gap-3 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 rounded-lg border border-slate-200 transition-colors"
 data-testid="portal-switch-service-ops"
 title="New: native field-service operations console (replaces Sicon)"
 >
 <Sparkles size={16} className="text-emerald-500" /> Service Ops <span className="ml-auto text-[9px] font-bold uppercase tracking-wider text-emerald-600">New</span>
 </button>
 )}
 </div>
 </div>

 <div className="p-3 border-t border-slate-100">
 <Button
 variant="outline"
 size="sm"
 onClick={onLogout}
 className="w-full border-red-200 text-red-600 hover:bg-red-50 hover:text-red-700"
 data-testid="admin-logout-btn"
 >
 <LogOut size={14} className="mr-2" /> Log out
 </Button>
 </div>
 </aside>
);
};

export default AdminSidebar;
