import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { X, Wrench, LogOut, HeadphonesIcon, Layers, HardHat, Loader2, Search, Building2, ChevronDown, Boxes } from 'lucide-react';
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
 onLogout, onPulseSwitch, onPulseFitnessSwitch,
 onOrgSwitch, organizations = [],
 isPulseAdmin = false,
}) => {
 const _navigate = useNavigate();
 const [openCases, setOpenCases] = useState(0);
 // Org portal picker — switch into any client org's portal as its owner.
 const [orgPickerOpen, setOrgPickerOpen] = useState(false);
 const [orgPickerArea, setOrgPickerArea] = useState('operator');
 const [orgQuery, setOrgQuery] = useState('');
 const [orgBusyId, setOrgBusyId] = useState('');
 const openOrgPicker = (area) => { setOrgPickerArea(area); setOrgQuery(''); setOrgPickerOpen(true); };
 // Iter 220dh — Pending Review queue total (partner applications + PTW + parts).
 const [pendingReview, setPendingReview] = useState(0);
 // Iter 227 — "View as engineer" picker (Pulse Master Admin training/support).
 const [engPickerOpen, setEngPickerOpen] = useState(false);
 const [engineers, setEngineers] = useState([]);
 const [engLoading, setEngLoading] = useState(false);
 const [engQuery, setEngQuery] = useState('');
 const [engBusyId, setEngBusyId] = useState('');

 const openEngineerPicker = useCallback(async () => {
   setEngPickerOpen(true);
   setEngLoading(true);
   try {
     const API = process.env.REACT_APP_BACKEND_URL;
     const headers = { Authorization: `Bearer ${localStorage.getItem('token')}` };
     const { data } = await axios.get(`${API}/api/master-admin/engineers`, { headers });
     setEngineers(data?.engineers || []);
   } catch (e) {
     toast.error(e?.response?.data?.detail || 'Failed to load engineers');
     setEngineers([]);
   }
   setEngLoading(false);
 }, []);

 const viewAsEngineer = useCallback(async (eng) => {
   setEngBusyId(eng.id);
   try {
     const API = process.env.REACT_APP_BACKEND_URL;
     const headers = { Authorization: `Bearer ${localStorage.getItem('token')}` };
     const { data } = await axios.post(`${API}/api/master-admin/impersonate/${eng.id}`, {}, { headers });
     const url = new URL(`${window.location.origin}/svc/engineer`);
     url.searchParams.set('impersonation_token', data.token);
     window.open(url.toString(), '_blank', 'noopener');
     toast.success(`Opening Engineer App as ${eng.full_name || eng.email}`);
     setEngPickerOpen(false);
   } catch (e) {
     toast.error(e?.response?.data?.detail || 'Could not start engineer session');
   }
   setEngBusyId('');
 }, []);

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
 const fetchPending = async () => {
   try {
     const { data } = await axios.get(`${API}/api/master-admin/pending-review/count`, { headers });
     if (!cancelled) setPendingReview(data?.total || 0);
   } catch { /* ignore — sidebar shouldn't crash on a missed poll */ }
 };
 fetchOpen();
 fetchPending();
 const tid = setInterval(() => { fetchOpen(); fetchPending(); }, 60_000);
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

 // Pulse Master Admins see the same console but with Pulse Fitness-only items
 // (e.g. internal Service Desk membership management) hidden.
 const items = isPulseAdmin
 ? SIDEBAR_ITEMS.filter((i) => !i.gymaxisOnly)
 : SIDEBAR_ITEMS;
 return (
 <aside
 className={`fixed inset-y-0 left-0 z-50 w-72 bg-white border-r border-slate-200 flex flex-col transform transition-transform duration-200 ease-in-out lg:static lg:w-[19rem] lg:translate-x-0 lg:z-auto ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}
 data-testid="admin-sidebar"
 >
 <div className="p-5 border-b border-slate-100 flex items-center justify-between">
 <div className="flex items-center gap-3">
 <div className="w-10 h-10 rounded-xl bg-white flex items-center justify-center overflow-hidden gx-grad-ring shadow-sm" data-testid="admin-sidebar-logo">
            <img src="/brand/pulse-mark.svg" alt="Pulse Fitness" className="w-7 h-7 object-contain" draggable={false} loading="eager" decoding="async" />
          </div>
 <div>
 <p className="font-bold text-slate-900 text-sm tracking-tight">{isPulseAdmin ? 'Pulse Fitness' : 'Pulse Fitness'}</p>
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
 {/* Iter 220dh — Pending-review queue badge on the Overview group. */}
 {item.id === 'overview' && pendingReview > 0 && (
 <span
 className="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full bg-amber-500 text-white text-[10px] font-bold leading-none"
 data-testid="sidebar-pending-review-badge"
 title={`${pendingReview} item${pendingReview === 1 ? '' : 's'} pending master-admin action`}
 >
 {pendingReview > 99 ? '99+' : pendingReview}
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
 onClick={onPulseFitnessSwitch}
 className="w-full flex items-center gap-3 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 rounded-lg border border-slate-200 transition-colors"
 data-testid="portal-switch-global-dashboard"
 >
 <Layers size={16} className="text-violet-500" /> Global Dashboard
 </button>
 )}
 <div className="flex items-center gap-1">
 <button
 onClick={onPulseSwitch}
 className="flex-1 flex items-center gap-3 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 rounded-lg border border-slate-200 transition-colors whitespace-nowrap"
 data-testid="portal-switch-pulse"
 >
 <Wrench size={16} className="text-blue-500" /> Pulse Fitness Portal
 </button>
 {onOrgSwitch && (
 <button
 onClick={() => openOrgPicker('operator')}
 title="Switch into any client portal"
 className="px-2 py-2 text-slate-500 hover:text-slate-800 hover:bg-slate-50 rounded-lg border border-slate-200 transition-colors"
 data-testid="portal-switch-org-picker-btn"
 >
 <ChevronDown size={16} />
 </button>
 )}
 </div>
 {/* Iter 244 — Service Desk is the Sicon case hub for Pulse Fitness;
     visible to Pulse Master Admins as well as Pulse Fitness Master Admin. */}
 <div className="flex items-center gap-1">
 <button
 onClick={() => { window.location.href = '/service-desk'; }}
 className="flex-1 flex items-center gap-3 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 rounded-lg border border-slate-200 transition-colors whitespace-nowrap"
 data-testid="portal-switch-service-desk"
 >
 <HeadphonesIcon size={16} className="text-orange-500" /> Service Desk
 </button>
 {onOrgSwitch && (
 <button
 onClick={() => openOrgPicker('service_desk')}
 title="Open a client's Service Desk"
 className="px-2 py-2 text-slate-500 hover:text-slate-800 hover:bg-slate-50 rounded-lg border border-slate-200 transition-colors"
 data-testid="portal-switch-service-desk-org-picker-btn"
 >
 <ChevronDown size={16} />
 </button>
 )}
 </div>
 {/* Inventory & Distribution — its own module (Sage order → warehouse → dealer → customer → service) */}
 <div className="flex items-center gap-1">
 <button
 onClick={() => { window.location.href = '/inventory'; }}
 className="flex-1 flex items-center gap-3 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 rounded-lg border border-slate-200 transition-colors whitespace-nowrap"
 data-testid="portal-switch-inventory"
 >
 <Boxes size={16} className="text-emerald-500" /> Inventory &amp; Distribution
 </button>
 {onOrgSwitch && (
 <button
 onClick={() => openOrgPicker('inventory')}
 title="Open a client's Inventory & Distribution"
 className="px-2 py-2 text-slate-500 hover:text-slate-800 hover:bg-slate-50 rounded-lg border border-slate-200 transition-colors"
 data-testid="portal-switch-inventory-org-picker-btn"
 >
 <ChevronDown size={16} />
 </button>
 )}
 </div>
 {/* Iter 216h256 — Engineer App switch lets Master Admin demo the
     mobile-first engineer surface to prospective field engineers
     without logging in as an engineer. */}
 {!isPulseAdmin && (
 <button
 onClick={() => { window.location.href = '/svc/engineer'; }}
 className="w-full flex items-center gap-3 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 rounded-lg border border-slate-200 transition-colors"
 data-testid="portal-switch-engineer-app"
 >
 <HardHat size={16} className="text-amber-500" /> Engineer App
 </button>
 )}
 {/* Iter 227 — Pulse Master Admins "view as" a specific engineer for
     training/support, opening the Engineer App in a scoped session. */}
 {isPulseAdmin && (
 <button
 onClick={openEngineerPicker}
 className="w-full flex items-center gap-3 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 rounded-lg border border-slate-200 transition-colors"
 data-testid="portal-switch-engineer-app"
 >
 <HardHat size={16} className="text-amber-500" /> Engineer App
 </button>
 )}
 {/* Iter 216h53 — Service Ops folded into Service Desk (full merge).
     Button removed; users land on the unified hub via "Service Desk" above. */}
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

 {/* Iter 227 — View-as-engineer picker modal */}
 {engPickerOpen && (
 <div
 className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
 onMouseDown={(e) => { if (e.target === e.currentTarget) setEngPickerOpen(false); }}
 data-testid="engineer-view-as-modal"
 >
 <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl flex flex-col max-h-[80vh]">
 <div className="p-5 border-b border-slate-100 flex items-start justify-between gap-3">
 <div>
 <p className="font-bold text-slate-900 text-sm flex items-center gap-2"><HardHat size={16} className="text-amber-500" /> View as engineer</p>
 <p className="text-[11px] text-slate-500 mt-1">Open the Engineer App as one of your engineers for training & support. A secure, time-limited session opens in a new tab.</p>
 </div>
 <button onClick={() => setEngPickerOpen(false)} className="p-1 text-slate-400 hover:text-slate-700" data-testid="engineer-view-as-close"><X size={18} /></button>
 </div>
 <div className="p-3 border-b border-slate-100">
 <div className="relative">
 <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
 <input
 value={engQuery}
 onChange={(e) => setEngQuery(e.target.value)}
 placeholder="Search engineers…"
 className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
 data-testid="engineer-view-as-search"
 />
 </div>
 </div>
 <div className="flex-1 overflow-y-auto p-2">
 {engLoading && (
 <div className="flex items-center justify-center py-10 text-slate-400 text-sm"><Loader2 size={18} className="animate-spin mr-2" /> Loading…</div>
 )}
 {!engLoading && engineers.length === 0 && (
 <div className="py-10 text-center text-sm text-slate-500" data-testid="engineer-view-as-empty">
 No engineers found. Assign the <strong>Engineer</strong> role to a teammate in Account Settings → Team &amp; roles to provision one.
 </div>
 )}
 {!engLoading && engineers
 .filter((e) => {
 const q = engQuery.trim().toLowerCase();
 if (!q) return true;
 return `${e.full_name} ${e.email} ${e.organization_name}`.toLowerCase().includes(q);
 })
 .map((e) => (
 <button
 key={e.id}
 onClick={() => viewAsEngineer(e)}
 disabled={!!engBusyId}
 className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-slate-50 text-left transition-colors disabled:opacity-60"
 data-testid={`engineer-view-as-pick-${e.id}`}
 >
 <div className="w-9 h-9 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center text-xs font-bold flex-shrink-0">
 {(e.full_name || e.email || '?').slice(0, 1).toUpperCase()}
 </div>
 <div className="min-w-0 flex-1">
 <div className="text-sm font-medium text-slate-900 truncate">{e.full_name || e.email}</div>
 <div className="text-[11px] text-slate-500 truncate">{e.organization_name || e.email}</div>
 </div>
 {engBusyId === e.id ? <Loader2 size={16} className="animate-spin text-slate-400" /> : <HardHat size={15} className="text-slate-300" />}
 </button>
 ))}
 </div>
 </div>
 </div>
 )}
 {/* Org portal picker — switch into any client org's operator portal */}
 {orgPickerOpen && (
 <div
 className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
 onMouseDown={(e) => { if (e.target === e.currentTarget) setOrgPickerOpen(false); }}
 data-testid="org-portal-modal"
 >
 <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl flex flex-col max-h-[80vh]">
 <div className="p-5 border-b border-slate-100 flex items-start justify-between gap-3">
 <div>
 <p className="font-bold text-slate-900 text-sm flex items-center gap-2"><Building2 size={16} className="text-blue-500" /> {orgPickerArea === 'service_desk' ? "Open a client's Service Desk" : orgPickerArea === 'inventory' ? "Open a client's Inventory" : 'Switch into a client portal'}</p>
 <p className="text-[11px] text-slate-500 mt-1">Open any organisation's {orgPickerArea === 'service_desk' ? 'Service Desk' : orgPickerArea === 'inventory' ? 'Inventory & Distribution' : 'operator'} portal as its admin. A secure, time-limited impersonation session — every action is logged.</p>
 </div>
 <button onClick={() => setOrgPickerOpen(false)} className="p-1 text-slate-400 hover:text-slate-700" data-testid="org-portal-close"><X size={18} /></button>
 </div>
 <div className="p-3 border-b border-slate-100">
 <div className="relative">
 <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
 <input
 value={orgQuery}
 onChange={(e) => setOrgQuery(e.target.value)}
 placeholder="Search organisations…"
 className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
 data-testid="org-portal-search"
 />
 </div>
 </div>
 <div className="flex-1 overflow-y-auto p-2">
 {(organizations || []).length === 0 && (
 <div className="py-10 text-center text-sm text-slate-500" data-testid="org-portal-empty">No organisations found.</div>
 )}
 {(organizations || [])
 .filter((o) => {
 const q = orgQuery.trim().toLowerCase();
 if (!q) return true;
 return `${o.name} ${o.id}`.toLowerCase().includes(q);
 })
 .slice(0, 100)
 .map((o) => (
 <button
 key={o.id}
 onClick={async () => {
 if (orgBusyId) return;
 setOrgBusyId(o.id);
 try { await onOrgSwitch(o.id, orgPickerArea); }
 catch (e) { toast.error(e?.response?.data?.detail || 'Could not open that portal'); setOrgBusyId(''); }
 }}
 disabled={!!orgBusyId}
 className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-slate-50 text-left transition-colors disabled:opacity-60"
 data-testid={`org-portal-pick-${o.id}`}
 >
 <div className="w-9 h-9 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold flex-shrink-0">
 {(o.name || '?').slice(0, 1).toUpperCase()}
 </div>
 <div className="min-w-0 flex-1">
 <div className="text-sm font-medium text-slate-900 truncate">{o.name || 'Unnamed org'}</div>
 <div className="text-[11px] text-slate-500 truncate">{o.account_type || o.subscription_tier || 'operator'}</div>
 </div>
 {orgBusyId === o.id ? <Loader2 size={16} className="animate-spin text-slate-400" /> : <Wrench size={15} className="text-slate-300" />}
 </button>
 ))}
 </div>
 </div>
 </div>
 )}
 </aside>
);
};

export default AdminSidebar;
