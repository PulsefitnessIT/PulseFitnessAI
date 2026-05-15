import React, { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import axios from 'axios';
import {
 Clock, CheckCircle, AlertCircle, Truck, Search, Plus,
 ArrowRight, Building, Wrench, Package, Timer, Star, Info, ChevronDown
} from 'lucide-react';
import SupplierEquipmentWizard from './SupplierEquipmentWizard';
import PageHeader from '@/components/shared/PageHeader';
import KpiTile from '@/components/shared/KpiTile';

const SupplierDashboardTab = () => {
 const { t } = useTranslation();
 const { API, user, activeSite } = useAuth();
 const [cases, setCases] = useState([]);
 const [metrics, setMetrics] = useState(null);
 const [equipmentSuppliers, setEquipmentSuppliers] = useState([]);
 const [search, setSearch] = useState('');
 const [expandedSupplier, setExpandedSupplier] = useState(null);
 const [showScoreInfo, setShowScoreInfo] = useState(false);
 const [showAdd, setShowAdd] = useState(false);
 const [addForm, setAddForm] = useState({ name: '', email: '', contact_person: '', phone: '' });
 const [adding, setAdding] = useState(false);
 const [wizardSupplier, setWizardSupplier] = useState(null);

 // Supplier CRUD is gated to Pulse Pro and GymAxis Full (Pulse Lite excluded).
 const canAddSuppliers = ['pulse_pro', 'full', undefined, null].includes(user?.account_type);

 // Iter 216h121 — Re-fetch when the active site changes. MOD HQ users
 // toggling between "All Operations Sites" and a single garrison get a
 // fresh supplier league table for the chosen scope.
 useEffect(() => { loadDashboard(); }, [API, activeSite?.id]); // eslint-disable-line react-hooks/exhaustive-deps

 const loadDashboard = async () => {
 const token = localStorage.getItem('token');
 try {
 const siteParam = (activeSite && !activeSite.is_default) ? `?site_id=${activeSite.id}` : '';
 const res = await axios.get(`${API}/supplier-dashboard${siteParam}`, {
 headers: { Authorization: `Bearer ${token}` }
 });
 setCases(res.data.cases || []);
 setMetrics(res.data.metrics || {});
 setEquipmentSuppliers(res.data.equipment_suppliers || []);
 } catch (err) {
 console.error('Failed to load supplier dashboard:', err);
 setCases([]);
 }
 };

 const getSeverityBadge = (severity) => {
 const map = {
 critical: 'bg-red-500/20 text-red-400',
 operational_fault: 'bg-orange-500/20 text-orange-400',
 operational_minor: 'bg-yellow-500/20 text-yellow-400',
 cosmetic: 'bg-green-500/20 text-green-400',
 };
 return map[severity] || 'bg-gray-500/20 text-gray-400';
 };

 const getStatusBadge = (status) => {
 const map = {
 open: { label: 'Open', color: 'bg-red-500/20 text-red-400', icon: AlertCircle },
 in_progress: { label: 'In Progress', color: 'bg-orange-500/20 text-orange-400', icon: Wrench },
 resolved: { label: 'Resolved', color: 'bg-green-500/20 text-green-400', icon: CheckCircle },
 closed: { label: 'Closed', color: 'bg-gray-500/20 text-gray-400', icon: CheckCircle },
 };
 return map[status] || { label: status, color: 'bg-gray-500/20 text-gray-400', icon: Clock };
 };

 const getStatusConfig = (status) => {
 const map = {
 pending: { label: 'Pending', color: 'bg-yellow-500/20 text-yellow-400', icon: Clock },
 acknowledged: { label: 'Acknowledged', color: 'bg-blue-500/20 text-blue-400', icon: CheckCircle },
 engineer_scheduled: { label: 'Engineer Scheduled', color: 'bg-purple-500/20 text-purple-400', icon: Truck },
 in_progress: { label: 'In Progress', color: 'bg-orange-500/20 text-orange-400', icon: Wrench },
 parts_ordered: { label: 'Parts Ordered', color: 'bg-cyan-500/20 text-cyan-400', icon: Package },
 completed: { label: 'Completed', color: 'bg-green-500/20 text-green-400', icon: CheckCircle },
 };
 return map[status] || { label: status, color: 'bg-gray-500/20 text-gray-400', icon: Clock };
 };

 // Group escalated cases by supplier (existing logic for performance scores)
 const supplierCaseGroups = useMemo(() => {
 const groups = {};
 cases.forEach(c => {
 const name = c.supplier_name || 'Unknown';
 if (!groups[name]) {
 groups[name] = { name, email: c.supplier_email, cases: [], totalResponseHours: 0, respondedCount: 0 };
 }
 groups[name].cases.push(c);
 if (c.first_response_at && c.created_at) {
 try {
 const diff = (new Date(c.first_response_at) - new Date(c.created_at)) / 3600000;
 groups[name].totalResponseHours += diff;
 groups[name].respondedCount++;
 } catch { /* skip */ }
 }
 });
 return groups;
 }, [cases]);

 // Calculate supplier performance scores.
//
// Iter 216h121 — The backend now ships an authoritative `score`,
// `grade`, `rank`, `resolution_rate`, `avg_rating`, and
// `avg_response_hours` on each supplier (utility-grade league
// table). When those server-side fields are present we trust them;
// otherwise we fall back to the legacy client-side maths so older
// API versions still render something sensible.
 const scoredSuppliers = useMemo(() => {
 const ranked = equipmentSuppliers.map(supplier => {
 const faults = supplier.faults || [];
 const total = faults.length;
 const resolved = faults.filter(f => f.status === 'resolved' || f.status === 'closed').length;
 const open = supplier.open_faults || 0;
 const caseGroup = supplierCaseGroups[supplier.name];
 const escalatedCases = caseGroup?.cases?.length || 0;
 const responded = caseGroup?.respondedCount || 0;

 if (typeof supplier.score === 'number') {
   // Server-side league table — use it directly. Synthesise a
   // score breakdown for the rainbow bar (40 / 30 / 20 / 10 ratio).
   return {
     ...supplier,
     score: supplier.score,
     scoreBreakdown: {
       resolution: Math.round((supplier.resolution_rate ?? 1) * 40),
       openFault:  Math.max(0, 10 - Math.min(10, open * 2)),
       response:   supplier.avg_response_hours == null
         ? 12
         : supplier.avg_response_hours <= 24 ? 20
         : supplier.avg_response_hours <= 48 ? 10
         : supplier.avg_response_hours <= 96 ? 5 : 0,
     },
   };
 }

 // Legacy fallback — pure client maths.
 const resolutionScore = total > 0 ? Math.round((resolved / total) * 40) : 40;
 const faultRatio = supplier.equipment_count > 0 ? open / supplier.equipment_count : 0;
 const openFaultScore = Math.round(Math.max(0, 30 - (faultRatio * 300)));
 const responseScore = escalatedCases > 0 ? Math.round((responded / escalatedCases) * 30) : 30;
 const score = Math.min(100, resolutionScore + openFaultScore + responseScore);
 return { ...supplier, score, scoreBreakdown: { resolution: resolutionScore, openFault: openFaultScore, response: responseScore } };
 }).sort((a, b) => b.score - a.score);
 // Assign league rank after sorting so the badge is always 1, 2, 3…
 return ranked.map((s, i) => ({ ...s, rank: s.rank ?? (i + 1) }));
 }, [equipmentSuppliers, supplierCaseGroups]);

 const getScoreColor = (score) => {
 if (score >= 80) return 'text-green-400 bg-green-500/20';
 if (score >= 60) return 'text-yellow-400 bg-yellow-500/20';
 if (score >= 40) return 'text-orange-400 bg-orange-500/20';
 return 'text-red-400 bg-red-500/20';
 };

 const getScoreLabel = (score) => {
 if (score >= 80) return 'Excellent';
 if (score >= 60) return 'Good';
 if (score >= 40) return 'Needs Improvement';
 return 'Poor';
 };

 // Filter scored suppliers
 const filteredSuppliers = scoredSuppliers.filter(s =>
 !search || s.name.toLowerCase().includes(search.toLowerCase())
 );

 const handleCreateSupplier = async (e) => {
 e.preventDefault();
 if (!addForm.name.trim()) {
 notify.error('Supplier name required');
 return;
 }
 setAdding(true);
 const token = localStorage.getItem('token');
 try {
 const r = await axios.post(
 `${API}/suppliers`,
 { ...addForm, send_welcome: false },
 { headers: { Authorization: `Bearer ${token}` } },
 );
 notify.success(`${r.data.name} added — now link their machines`);
 setShowAdd(false);
 setAddForm({ name: '', email: '', contact_person: '', phone: '' });
 setWizardSupplier(r.data);
 await loadDashboard();
 } catch (err) {
 notifyApiError(notify, err, 'Failed to add supplier');
 } finally {
 setAdding(false);
 }
 };

 return (
 <div className="space-y-6" data-testid="supplier-dashboard-tab">
 <PageHeader
   title="Suppliers"
   subtitle="Equipment suppliers, performance scores and associated fault cases"
   icon={Building}
   helpId="service-supplier-management"
   testId="suppliers-header"
   actions={
     <>
       {canAddSuppliers && (
         <Button
           size="sm" className="bg-indigo-600 hover:bg-indigo-700 text-white"
           onClick={() => setShowAdd(true)}
           data-testid="supplier-dash-add-btn"
         >
           <Plus size={14} className="mr-1" /> Add supplier
         </Button>
       )}
       <Button size="sm" variant="outline" className="border-[var(--theme-border)] text-[var(--color-text-muted)]" onClick={() => setShowScoreInfo(true)} data-testid="score-info-btn">
         <Info size={14} className="mr-1" /> How scores work
       </Button>
     </>
   }
 />

 {/* Metrics */}
 {metrics && (
 <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="supplier-metrics">
   <KpiTile icon={Building} label="Suppliers"        value={equipmentSuppliers.length}                                                tone="brand"   testId="supplier-kpi-count" />
   <KpiTile icon={Wrench}   label="Total Equipment"  value={equipmentSuppliers.reduce((s, sup) => s + sup.equipment_count, 0)}        tone="cyan"    testId="supplier-kpi-equipment" />
   <KpiTile icon={AlertCircle} label="Open Faults"   value={equipmentSuppliers.reduce((s, sup) => s + (sup.open_faults || 0), 0)}     tone="warning" testId="supplier-kpi-open" />
   <KpiTile icon={CheckCircle} label="Escalated Cases" value={metrics.total_cases}                                                    tone="success" testId="supplier-kpi-escalated" />
 </div>
 )}

 {/* Search */}
 <div className="relative">
 <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" size={18} />
 <Input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search supplier..."
 className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] pl-10" data-testid="supplier-dash-search" />
 </div>

 {/* Equipment Suppliers */}
 <div className="space-y-4">
 {filteredSuppliers.length > 0 ? filteredSuppliers.map(supplier => {
 const isExpanded = expandedSupplier === supplier.name;
 const caseGroup = supplierCaseGroups[supplier.name];
 const faults = supplier.faults || [];
 const openFaults = supplier.open_faults || 0;
 const resolvedFaults = faults.filter(f => f.status === 'resolved' || f.status === 'closed').length;

 return (
 <Card key={supplier.name} className="bg-[var(--theme-surface)] border-[var(--theme-border)] overflow-hidden" data-testid={`supplier-group-${supplier.name}`}>
 {/* Supplier Header */}
 <div className="p-5 cursor-pointer hover:bg-white/5 transition-colors dark:bg-zinc-900" onClick={() => setExpandedSupplier(isExpanded ? null : supplier.name)}>
 <div className="flex items-center justify-between">
 <div className="flex items-center gap-4">
 {/* Iter 216h121 — league rank medal. 1st/2nd/3rd get a podium colour. */}
 <div
   className={`w-10 h-10 rounded-full flex flex-col items-center justify-center flex-shrink-0 font-extrabold ${
     supplier.rank === 1 ? 'bg-amber-400 text-amber-950'
     : supplier.rank === 2 ? 'bg-zinc-300 text-zinc-800'
     : supplier.rank === 3 ? 'bg-orange-300 text-orange-900'
     : 'bg-white/5 text-[var(--color-text-muted)] border border-[var(--theme-border)]'
   }`}
   data-testid={`supplier-rank-${supplier.name}`}
   title={`League rank #${supplier.rank}`}
 >
   <span className="text-[10px] leading-none uppercase opacity-80">#</span>
   <span className="text-base leading-none">{supplier.rank}</span>
 </div>
 <div className="w-12 h-12 rounded-xl bg-[rgb(var(--rgb-brand-blue)/0.1)] flex items-center justify-center flex-shrink-0">
 <Building size={24} className="text-[var(--color-brand-blue)]" />
 </div>
 <div>
 <div className="flex items-center gap-2 flex-wrap">
 <p className="text-white font-bold text-lg">{supplier.name}</p>
 {supplier.grade && (
 <span
   className={`text-[10px] font-extrabold px-1.5 py-0.5 rounded uppercase tracking-wider ${
     supplier.grade === 'A' ? 'bg-emerald-500/20 text-emerald-300'
     : supplier.grade === 'B' ? 'bg-cyan-500/20 text-cyan-300'
     : supplier.grade === 'C' ? 'bg-yellow-500/20 text-yellow-300'
     : supplier.grade === 'D' ? 'bg-orange-500/20 text-orange-300'
     : 'bg-red-500/20 text-red-300'
   }`}
   data-testid={`supplier-grade-${supplier.name}`}
 >
   Grade {supplier.grade}
 </span>
 )}
 </div>
 <div className="flex items-center gap-2 mt-0.5 flex-wrap">
 {supplier.equipment_types.map(t => (
 <Badge key={t} className="bg-white/5 text-[var(--color-text-muted)] border-0 text-[10px]">{t}</Badge>
 ))}
 </div>
 </div>
 </div>
 <div className="flex items-center gap-3">
 {/* Performance Score */}
 <div className="text-center" data-testid={`score-${supplier.name}`}>
 <div className={`w-14 h-14 rounded-full flex flex-col items-center justify-center ${getScoreColor(supplier.score)}`}>
 <span className="text-lg font-bold leading-none">{supplier.score}</span>
 <span className="text-[7px] uppercase tracking-wider opacity-80">/100</span>
 </div>
 <p className={`text-[10px] mt-0.5 font-medium ${getScoreColor(supplier.score).split(' ')[0]}`}>{getScoreLabel(supplier.score)}</p>
 </div>
 <ChevronDown size={20} className={`text-[var(--color-text-muted)] transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
 </div>
 </div>

 {/* Quick stats row */}
 <div className="flex gap-4 mt-3 flex-wrap">
 <span className="text-[var(--color-brand-cyan-hover)] text-sm font-medium">{supplier.equipment_count} machines</span>
 {faults.length > 0 && (
 <>
 <span className="text-amber-400 text-sm">{openFaults} open fault{openFaults !== 1 ? 's' : ''}</span>
 <span className="text-green-400 text-sm">{resolvedFaults} resolved</span>
 </>
 )}
 {faults.length === 0 && (
 <span className="text-emerald-400 text-sm">No faults reported</span>
 )}
 {caseGroup && (
 <span className="text-purple-400 text-sm">{caseGroup.cases.length} escalated case{caseGroup.cases.length !== 1 ? 's' : ''}</span>
 )}
 {/* Iter 216h121 — backend-supplied league stats */}
 {supplier.resolution_rate != null && (
 <span className="text-sm text-[var(--color-text-muted)]">
   · Resolution {Math.round(supplier.resolution_rate * 100)}%
 </span>
 )}
 {supplier.avg_rating != null && (
 <span className="text-sm text-[var(--color-text-muted)] inline-flex items-center gap-1">
   · <Star size={11} className="text-yellow-400" />{supplier.avg_rating.toFixed(1)}
 </span>
 )}
 {supplier.avg_response_hours != null && (
 <span className="text-sm text-[var(--color-text-muted)]">
   · {supplier.avg_response_hours.toFixed(1)}h avg response
 </span>
 )}
 </div>

 {/* Score breakdown bar */}
 <div className="mt-3 flex gap-1 h-2 rounded-full overflow-hidden bg-[var(--theme-surface)]">
 <div className="bg-green-500 rounded-l" style={{ width: `${supplier.scoreBreakdown?.resolution || 0}%` }} title="Resolution Rate" />
 <div className="bg-blue-500" style={{ width: `${supplier.scoreBreakdown?.openFault || 0}%` }} title="Open Fault Ratio" />
 <div className="bg-purple-500 rounded-r" style={{ width: `${supplier.scoreBreakdown?.response || 0}%` }} title="Response Rate" />
 </div>
 <div className="flex gap-4 mt-1 text-[10px] text-[var(--color-text-muted)]">
 <span><span className="inline-block w-2 h-2 rounded bg-green-500 mr-1" />Resolution {supplier.scoreBreakdown?.resolution || 0}/40</span>
 <span><span className="inline-block w-2 h-2 rounded bg-blue-500 mr-1" />Fault Ratio {supplier.scoreBreakdown?.openFault || 0}/30</span>
 <span><span className="inline-block w-2 h-2 rounded bg-purple-500 mr-1" />Response {supplier.scoreBreakdown?.response || 0}/30</span>
 </div>
 </div>

 {/* Expanded: Faults and escalated cases */}
 {isExpanded && (
 <div className="border-t border-[var(--theme-border)] p-4 bg-[rgb(var(--rgb-ink-alt)/0.5)] space-y-4" data-testid={`supplier-detail-${supplier.name}`}>
 {/* Fault Issues */}
 {faults.length > 0 && (
 <div>
 <p className="text-white font-semibold text-sm mb-2">Fault Issues ({faults.length})</p>
 <div className="space-y-2">
 {faults.map(f => {
 const statusCfg = getStatusBadge(f.status);
 const StatusIcon = statusCfg.icon;
 return (
 <div key={f.id} className="p-3 bg-[var(--theme-surface)] rounded-lg border border-white/5">
 <div className="flex items-center justify-between mb-1.5">
 <div className="flex items-center gap-2">
 <Badge className={statusCfg.color}><StatusIcon size={12} className="mr-1" /> {statusCfg.label}</Badge>
 <Badge className={getSeverityBadge(f.severity)}>{(f.severity || '').replace('_', ' ')}</Badge>
 </div>
 <span className="text-[var(--color-text-muted)] text-xs">{f.created_at ? new Date(f.created_at).toLocaleDateString() : ''}</span>
 </div>
 <p className="text-white text-sm">{f.machine_type} | {f.serial_number}</p>
 {f.description && <p className="text-[var(--color-text-muted)] text-xs mt-1">{f.description}</p>}
 </div>
 );
 })}
 </div>
 </div>
 )}

 {/* Escalated Supplier Cases */}
 {caseGroup && caseGroup.cases.length > 0 && (
 <div>
 <p className="text-white font-semibold text-sm mb-2">Escalated Cases ({caseGroup.cases.length})</p>
 <div className="space-y-2">
 {caseGroup.cases.map(c => {
 const cfg = getStatusConfig(c.current_status);
 const CaseIcon = cfg.icon;
 return (
 <div key={c.case_id} className="p-3 bg-[var(--theme-surface)] rounded-lg border border-white/5">
 <div className="flex items-center justify-between mb-1.5">
 <div className="flex items-center gap-2">
 <Badge className={cfg.color}><CaseIcon size={12} className="mr-1" /> {cfg.label}</Badge>
 <Badge className={c.issue?.severity === 'critical' ? 'bg-red-500/20 text-red-400' : c.issue?.severity === 'medium' ? 'bg-yellow-500/20 text-yellow-400' : 'bg-green-500/20 text-green-400'}>
 {c.issue?.severity}
 </Badge>
 </div>
 <span className="text-[var(--color-text-muted)] text-xs">{c.created_at ? new Date(c.created_at).toLocaleDateString() : ''}</span>
 </div>
 <p className="text-white text-sm">{c.issue?.machine_type} | {c.issue?.serial_number}</p>
 <p className="text-[var(--color-text-muted)] text-xs mt-1">{c.issue?.issue_description}</p>
 </div>
 );
 })}
 </div>
 </div>
 )}

 {faults.length === 0 && (!caseGroup || caseGroup.cases.length === 0) && (
 <p className="text-[var(--color-text-muted)] text-sm text-center py-4">No faults or cases for this supplier yet.</p>
 )}
 </div>
 )}
 </Card>
 );
 }) : (
 <Card className="bg-[var(--theme-surface)] border-[var(--theme-border)] p-12 text-center">
 <Building size={48} className="mx-auto mb-4 text-[var(--color-text-muted)]" />
 <p className="text-[var(--color-text-muted)]">
 {equipmentSuppliers.length === 0
 ? 'No suppliers found. Suppliers are derived from equipment manufacturer data.'
 : 'No suppliers match your search'}
 </p>
 </Card>
 )}
 </div>

 {/* Score Info Dialog */}
 <Dialog open={showScoreInfo} onOpenChange={setShowScoreInfo}>
 <DialogContent className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] max-w-lg" data-testid="score-info-dialog">
 <DialogHeader>
 <DialogTitle className="text-white flex items-center gap-2"><Star size={20} className="text-yellow-400" /> How Performance Scores Work</DialogTitle>
 </DialogHeader>
 <div className="space-y-4 text-sm">
 <p className="text-[var(--color-text-muted)]">Each supplier receives a score out of 100, calculated from three metrics:</p>

 <div className="space-y-3">
 <div className="p-3 bg-[var(--theme-surface)] rounded-lg border border-green-500/20">
 <div className="flex items-center justify-between mb-1">
 <span className="text-green-400 font-semibold">Fault Resolution Rate</span>
 <span className="text-green-400 font-bold">40 points</span>
 </div>
 <p className="text-[var(--color-text-muted)] text-xs">Percentage of reported faults that have been resolved. Higher resolution = better score.</p>
 </div>

 <div className="p-3 bg-[var(--theme-surface)] rounded-lg border border-blue-500/20">
 <div className="flex items-center justify-between mb-1">
 <span className="text-blue-400 font-semibold">Open Fault Ratio</span>
 <span className="text-blue-400 font-bold">30 points</span>
 </div>
 <p className="text-[var(--color-text-muted)] text-xs">Fewer open faults relative to total equipment = better score. Measures current fault burden.</p>
 </div>

 <div className="p-3 bg-[var(--theme-surface)] rounded-lg border border-purple-500/20">
 <div className="flex items-center justify-between mb-1">
 <span className="text-purple-400 font-semibold">Response Rate</span>
 <span className="text-purple-400 font-bold">30 points</span>
 </div>
 <p className="text-[var(--color-text-muted)] text-xs">Percentage of escalated cases the supplier has responded to. Full marks if no cases escalated yet.</p>
 </div>
 </div>

 <div className="border-t border-[var(--theme-border)] pt-3">
 <p className="text-white font-medium mb-2">Score Ranges</p>
 <div className="grid grid-cols-2 gap-2">
 <div className="flex items-center gap-2"><Badge className="bg-green-500/20 text-green-400">80-100</Badge><span className="text-[var(--color-text-muted)] text-xs">Excellent</span></div>
 <div className="flex items-center gap-2"><Badge className="bg-yellow-500/20 text-yellow-400">60-79</Badge><span className="text-[var(--color-text-muted)] text-xs">Good</span></div>
 <div className="flex items-center gap-2"><Badge className="bg-orange-500/20 text-orange-400">40-59</Badge><span className="text-[var(--color-text-muted)] text-xs">Needs Improvement</span></div>
 <div className="flex items-center gap-2"><Badge className="bg-red-500/20 text-red-400">0-39</Badge><span className="text-[var(--color-text-muted)] text-xs">Poor</span></div>
 </div>
 </div>
 </div>
 </DialogContent>
 </Dialog>

 {/* Add Supplier dialog (Pulse Pro / Full tiers only) */}
 <Dialog open={showAdd} onOpenChange={setShowAdd}>
 <DialogContent className="max-w-md" data-testid="supplier-dash-add-dialog">
 <DialogHeader>
 <DialogTitle className="text-white">Add new supplier</DialogTitle>
 </DialogHeader>
 <form onSubmit={handleCreateSupplier} className="space-y-3 mt-2">
 <div>
 <label className="text-[var(--color-text-muted)] text-xs">Name *</label>
 <Input
 value={addForm.name}
 onChange={(e) => setAddForm({ ...addForm, name: e.target.value })}
 required
 className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1"
 data-testid="supplier-dash-add-name"
 />
 </div>
 <div>
 <label className="text-[var(--color-text-muted)] text-xs">Email (needed to send welcome)</label>
 <Input
 type="email" value={addForm.email}
 onChange={(e) => setAddForm({ ...addForm, email: e.target.value })}
 className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1"
 data-testid="supplier-dash-add-email"
 />
 </div>
 <div className="grid grid-cols-2 gap-3">
 <div>
 <label className="text-[var(--color-text-muted)] text-xs">Contact person</label>
 <Input
 value={addForm.contact_person}
 onChange={(e) => setAddForm({ ...addForm, contact_person: e.target.value })}
 className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1"
 />
 </div>
 <div>
 <label className="text-[var(--color-text-muted)] text-xs">Phone</label>
 <Input
 value={addForm.phone}
 onChange={(e) => setAddForm({ ...addForm, phone: e.target.value })}
 className="bg-[var(--theme-surface)] border-[var(--theme-border)] text-[var(--theme-text)] mt-1"
 />
 </div>
 </div>
 <div className="text-[11px] text-[var(--color-text-muted)] bg-indigo-500/10 border border-indigo-500/20 rounded p-2">
 After saving, you'll be asked which machines to link. Their welcome email will include a CSV of the machines assigned to them.
 </div>
 <div className="flex justify-end gap-2 pt-1">
 <Button type="button" variant="ghost" onClick={() => setShowAdd(false)}>Cancel</Button>
 <Button
 type="submit" disabled={adding}
 className="bg-indigo-600 hover:bg-indigo-700 text-white"
 data-testid="supplier-dash-add-submit"
 >
 {adding ? 'Saving…' : 'Save & link machines'}
 </Button>
 </div>
 </form>
 </DialogContent>
 </Dialog>

 <SupplierEquipmentWizard
 supplier={wizardSupplier}
 open={!!wizardSupplier}
 onClose={() => setWizardSupplier(null)}
 onComplete={loadDashboard}
 />
 </div>
 );
};

export default SupplierDashboardTab;
