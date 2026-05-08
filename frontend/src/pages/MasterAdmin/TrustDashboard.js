import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { notify, useConfirm } from '@/components/notifications';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import {
 ShieldCheck, ShieldAlert, Activity, CheckCircle2, XCircle,
 Clock, RefreshCw, Zap, TrendingDown, TrendingUp, Wand2, ChevronRight,
 Sparkles, Loader2, AlertOctagon, History, ArrowRight, Undo2,
} from 'lucide-react';
import SecurityChecksPanel from './SecurityChecksPanel';

const API = process.env.REACT_APP_BACKEND_URL;

const SEVERITY_STYLES = {
 critical: { bg: 'bg-red-600', text: 'text-white', ring: 'ring-red-300' },
 high: { bg: 'bg-red-500', text: 'text-white', ring: 'ring-red-200' },
 med: { bg: 'bg-amber-500', text: 'text-white', ring: 'ring-amber-200' },
 low: { bg: 'bg-yellow-400', text: 'text-black', ring: 'ring-yellow-200' },
 info: { bg: 'bg-zinc-300', text: 'text-black', ring: 'ring-zinc-200' },
};

const INTEGRATION_STATE_COLOR = {
 live: 'bg-emerald-50 text-emerald-700 border-emerald-300 hover:bg-emerald-100',
 degraded: 'bg-amber-50 text-amber-800 border-amber-300 hover:bg-amber-100',
 down: 'bg-red-50 text-red-800 border-red-300 hover:bg-red-100',
};

const SummaryTile = ({ label, value, hint, icon: Icon, tone }) => (
 <Card className={`p-5 ${tone || ''}`} data-testid={`trust-tile-${label.toLowerCase().replace(/\s+/g, '-')}`}>
 <div className="flex items-start justify-between">
 <div>
 <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{label}</p>
 <p className="mt-2 text-3xl font-bold text-zinc-900">{value}</p>
 {hint && <p className="mt-1 text-xs text-zinc-500">{hint}</p>}
 </div>
 {Icon && <Icon size={28} className="text-zinc-400" />}
 </div>
 </Card>
);

const EventRow = ({ ev, onAck, onResolve, busy, onOpen }) => {
 const s = SEVERITY_STYLES[ev.severity] || SEVERITY_STYLES.info;
 return (
 <div className="flex items-start gap-4 rounded-xl border border-zinc-200 bg-white p-4 hover:border-zinc-300 transition-colors"
 data-testid={`trust-event-${ev.id}`}>
 <div className={`mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${s.bg} ${s.text} ring-2 ${s.ring}`}>
 <ShieldAlert size={14} />
 </div>
 <button type="button" onClick={() => onOpen(ev)}
 className="flex-1 min-w-0 text-left" data-testid={`trust-event-open-${ev.id}`}>
 <div className="flex items-center gap-2 flex-wrap">
 <Badge className={`${s.bg} ${s.text} border-0 text-[10px] uppercase tracking-wide`}>{ev.severity}</Badge>
 <code className="text-[11px] text-zinc-500 font-mono">{ev.type}</code>
 {ev.occurrences > 1 && (
 <Badge variant="outline" className="text-[10px] text-zinc-600">×{ev.occurrences}</Badge>
 )}
 {ev.state === 'acknowledged' && (
 <Badge className="bg-blue-100 text-blue-800 border-0 text-[10px]">Acknowledged</Badge>
 )}
 </div>
 <p className="mt-1 text-sm font-medium text-zinc-900 break-words">{ev.summary || ev.type}</p>
 <div className="mt-1 flex items-center gap-3 text-[11px] text-zinc-500">
 <span><Clock size={10} className="inline mr-1" />{new Date(ev.last_seen_at || ev.created_at).toLocaleString('en-GB')}</span>
 {ev.org_id && <span>org · {ev.org_id.slice(0, 8)}</span>}
 <span className="text-[var(--color-brand-blue)] font-medium">View details →</span>
 </div>
 </button>
 <div className="flex flex-col gap-2 shrink-0">
 {ev.state === 'open' && (
 <Button size="sm" variant="outline" disabled={busy} onClick={() => onAck(ev.id)}
 className="text-xs" data-testid={`trust-ack-${ev.id}`}>
 Acknowledge
 </Button>
 )}
 <Button size="sm" disabled={busy} onClick={() => onResolve(ev.id)}
 className="bg-emerald-600 hover:bg-emerald-700 text-white text-xs"
 data-testid={`trust-resolve-${ev.id}`}>
 <CheckCircle2 size={12} className="mr-1" /> Resolve
 </Button>
 </div>
 </div>
 );
};

const IntegrationPill = ({ row, onClick }) => {
 const cls = INTEGRATION_STATE_COLOR[row.state] || INTEGRATION_STATE_COLOR.live;
 return (
 <button type="button" onClick={() => onClick(row)}
 className={`flex items-center justify-between rounded-lg border px-3 py-2.5 transition-colors text-left w-full ${cls}`}
 data-testid={`trust-integration-${row.prefix}`}>
 <div className="flex-1 min-w-0">
 <p className="text-sm font-semibold">{row.label}</p>
 {row.latest?.summary ? (
 <p className="text-[11px] mt-0.5 opacity-80 truncate">{row.latest.summary}</p>
 ) : (
 <p className="text-[11px] mt-0.5 opacity-60">No active issues</p>
 )}
 </div>
 <div className="flex items-center gap-1.5 shrink-0 ml-2">
 <Badge className={`capitalize ${row.state === 'live' ? 'bg-emerald-600' : 'bg-amber-600'} text-white border-0`}>
 {row.state}
 </Badge>
 <ChevronRight size={14} className="opacity-50" />
 </div>
 </button>
 );
};

const SelfHealRow = ({ ev }) => (
 <div className="flex items-center gap-3 rounded-md border border-emerald-100 bg-emerald-50 px-3 py-2"
 data-testid={`trust-self-heal-${ev.id}`}>
 <Wand2 size={14} className="text-emerald-600 shrink-0" />
 <div className="flex-1 min-w-0">
 <p className="text-[13px] text-emerald-900 truncate">{ev.summary || ev.type}</p>
 <p className="text-[11px] text-emerald-700/80">{ev.resolution_note || 'Auto-resolved'} · {new Date(ev.resolved_at).toLocaleTimeString('en-GB')}</p>
 </div>
 <Badge className="bg-emerald-600 text-white border-0 text-[10px]">auto</Badge>
 </div>
);

const AiBadge = ({ confidence }) => {
 const tone =
 confidence === 'high' ? 'bg-emerald-100 text-emerald-800 border-emerald-300'
 : confidence === 'medium' ? 'bg-amber-100 text-amber-800 border-amber-300'
 : 'bg-zinc-100 text-zinc-700 border-zinc-300';
 return <Badge variant="outline" className={`${tone} text-[10px] uppercase`}>{confidence} conf</Badge>;
};

const EventDetailDialog = ({ open, onClose, event, onEventUpdated }) => {
 const [diagnosing, setDiagnosing] = useState(false);
 const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
 const hdr = React.useMemo(() => ({ headers: { Authorization: `Bearer ${token}` } }), [token]);

 if (!event) return null;
 const s = SEVERITY_STYLES[event.severity] || SEVERITY_STYLES.info;
 const ai = event.ai;

 const handleDiagnose = async () => {
 setDiagnosing(true);
 try {
 const res = await axios.post(`${API}/api/master-admin/trust/events/${event.id}/diagnose`, {}, hdr);
 notify.success('AI diagnosis complete');
 if (onEventUpdated && res.data.event) onEventUpdated(res.data.event);
 } catch (e) {
 const detail = e.response?.data?.detail || 'AI diagnosis failed';
 notify.error(detail);
 } finally {
 setDiagnosing(false);
 }
 };

 return (
 <Dialog open={open} onOpenChange={v => !v && onClose()}>
 <DialogContent className="max-w-2xl !bg-white text-zinc-900 border border-zinc-200" data-theme="light" data-testid="trust-event-detail">
 <DialogHeader>
 <DialogTitle className="flex items-center gap-2">
 <Badge className={`${s.bg} ${s.text} border-0 text-[10px] uppercase`}>{event.severity}</Badge>
 <code className="text-xs font-mono text-zinc-500">{event.type}</code>
 </DialogTitle>
 <DialogDescription className="text-zinc-700 text-sm mt-1">{event.summary || '—'}</DialogDescription>
 </DialogHeader>
 <div className="space-y-4">
 <div className="grid grid-cols-2 gap-3 text-sm">
 <div><span className="text-zinc-500 text-xs uppercase tracking-wide">State</span>
 <p className="font-medium capitalize">{event.state}</p></div>
 <div><span className="text-zinc-500 text-xs uppercase tracking-wide">Occurrences</span>
 <p className="font-medium">{event.occurrences ?? 1}</p></div>
 <div><span className="text-zinc-500 text-xs uppercase tracking-wide">First Seen</span>
 <p className="font-medium">{new Date(event.created_at).toLocaleString('en-GB')}</p></div>
 <div><span className="text-zinc-500 text-xs uppercase tracking-wide">Last Seen</span>
 <p className="font-medium">{new Date(event.last_seen_at || event.created_at).toLocaleString('en-GB')}</p></div>
 {event.acknowledged_by && (
 <div><span className="text-zinc-500 text-xs uppercase tracking-wide">Acknowledged by</span>
 <p className="font-medium">{event.acknowledged_by}</p></div>
 )}
 {event.org_id && (
 <div><span className="text-zinc-500 text-xs uppercase tracking-wide">Org</span>
 <code className="text-xs font-mono">{event.org_id}</code></div>
 )}
 </div>
 {event.payload && Object.keys(event.payload).length > 0 && (
 <div>
 <span className="text-zinc-500 text-xs uppercase tracking-wide">Payload</span>
 <pre className="mt-1 bg-zinc-50 border border-zinc-200 rounded p-3 text-[12px] overflow-x-auto">
 {JSON.stringify(event.payload, null, 2)}
 </pre>
 </div>
 )}

 {/* AI diagnosis panel */}
 <div className="rounded-lg bg-gradient-to-br from-violet-50 to-blue-50 border border-violet-200 p-4">
 <div className="flex items-center justify-between mb-2">
 <div className="flex items-center gap-2">
 <Sparkles size={14} className="text-violet-600" />
 <span className="text-xs font-bold uppercase tracking-wide text-violet-900">AI diagnosis</span>
 {ai?.confidence && <AiBadge confidence={ai.confidence} />}
 </div>
 <Button
 size="sm"
 onClick={handleDiagnose}
 disabled={diagnosing}
 className="bg-violet-600 hover:bg-violet-700 text-white text-xs"
 data-testid="trust-diagnose-btn"
 >
 {diagnosing ? (<><Loader2 size={12} className="mr-1 animate-spin" /> Diagnosing…</>)
 : (<><Sparkles size={12} className="mr-1" /> {ai ? 'Re-diagnose' : 'Diagnose with AI'}</>)}
 </Button>
 </div>
 {ai ? (
 <div className="space-y-2 text-sm" data-testid="trust-diagnose-result">
 <div>
 <p className="text-[10px] uppercase font-semibold tracking-wide text-violet-800/80">Probable cause</p>
 <p className="text-[13px] text-zinc-900 leading-relaxed">{ai.probable_cause || '—'}</p>
 </div>
 <div>
 <p className="text-[10px] uppercase font-semibold tracking-wide text-violet-800/80">Recommended action</p>
 <p className="text-[13px] text-zinc-900 leading-relaxed whitespace-pre-wrap">{ai.recommended_action || '—'}</p>
 </div>
 {ai.customer_safe_message && (
 <div>
 <p className="text-[10px] uppercase font-semibold tracking-wide text-violet-800/80">Customer-safe message</p>
 <p className="text-[13px] text-zinc-900 italic leading-relaxed">"{ai.customer_safe_message}"</p>
 </div>
 )}
 <p className="text-[10px] text-zinc-500 pt-1 border-t border-violet-200/50">
 {ai.diagnosed_model} · {ai.diagnosed_at && new Date(ai.diagnosed_at).toLocaleString('en-GB')}
 {ai.diagnosed_by && ` · by ${ai.diagnosed_by}`}
 </p>
 </div>
 ) : (
 <p className="text-[13px] text-zinc-700 leading-relaxed">
 Ask GPT-5.2 to analyse this event plus up to 20 related events from the last 7 days and return a probable cause, recommended action, and confidence rating. No remediation is taken automatically — output is advisory only.
 </p>
 )}
 </div>

 <div className="rounded-lg bg-blue-50 border border-blue-200 p-3 text-sm text-blue-900">
 <p className="font-semibold text-xs uppercase tracking-wide mb-1">What happens next?</p>
 <p className="text-[13px] leading-relaxed">
 Events with a <code className="bg-white px-1 rounded">dedupe_key</code> auto-resolve as soon as the underlying
 condition clears (e.g. Sicon queue drops below the threshold). Otherwise, Acknowledge to silence it while
 you investigate, then Resolve when fixed. Full YAML-driven self-healing playbooks ship in P5.
 </p>
 </div>
 </div>
 </DialogContent>
 </Dialog>
 );
};

const IntegrationDetailDialog = ({ open, onClose, row, apiHdr }) => {
 const [events, setEvents] = useState([]);
 const [loading, setLoading] = useState(false);

 useEffect(() => {
 if (!open || !row) return;
 setLoading(true);
 axios.get(`${API}/api/master-admin/trust/events?type=${row.prefix}.&limit=30`, apiHdr)
 .then(r => setEvents(r.data.events || []))
 .catch(() => setEvents([]))
 .finally(() => setLoading(false));
 // eslint-disable-next-line react-hooks/exhaustive-deps
 }, [open, row]);

 if (!row) return null;
 return (
 <Dialog open={open} onOpenChange={v => !v && onClose()}>
 <DialogContent className="max-w-2xl !bg-white text-zinc-900 border border-zinc-200" data-theme="light" data-testid="trust-integration-detail">
 <DialogHeader>
 <DialogTitle className="flex items-center gap-2">
 {row.label}
 <Badge className={`capitalize ${row.state === 'live' ? 'bg-emerald-600' : 'bg-amber-600'} text-white border-0`}>
 {row.state}
 </Badge>
 </DialogTitle>
 <DialogDescription>Trust events tagged <code className="bg-zinc-100 px-1 rounded">{row.prefix}.*</code> (last 30)</DialogDescription>
 </DialogHeader>
 {loading ? (
 <p className="text-center text-zinc-500 py-8 text-sm">Loading…</p>
 ) : events.length === 0 ? (
 <p className="text-center text-zinc-500 py-8 text-sm">
 <CheckCircle2 size={32} className="mx-auto mb-2 text-emerald-500" />
 No events recorded for this integration yet.
 </p>
 ) : (
 <div className="space-y-2 max-h-96 overflow-y-auto">
 {events.map(ev => {
 const s = SEVERITY_STYLES[ev.severity] || SEVERITY_STYLES.info;
 return (
 <div key={ev.id} className="border border-zinc-200 rounded-md p-3 text-sm" data-testid={`trust-int-ev-${ev.id}`}>
 <div className="flex items-center gap-2 mb-1">
 <Badge className={`${s.bg} ${s.text} border-0 text-[10px] uppercase`}>{ev.severity}</Badge>
 <Badge variant="outline" className="text-[10px] capitalize">{ev.state}</Badge>
 <code className="text-[11px] text-zinc-500">{ev.type}</code>
 </div>
 <p className="text-[13px] text-zinc-900">{ev.summary || '—'}</p>
 <p className="text-[11px] text-zinc-500 mt-1">{new Date(ev.last_seen_at || ev.created_at).toLocaleString('en-GB')}</p>
 </div>
 );
 })}
 </div>
 )}
 </DialogContent>
 </Dialog>
 );
};

export default function TrustDashboard({ refreshTick = 0 }) {
 const [data, setData] = useState(null);
 const [loading, setLoading] = useState(true);
 const [busyId, setBusyId] = useState(null);
 const [eventDialog, setEventDialog] = useState({ open: false, event: null });
 const [integrationDialog, setIntegrationDialog] = useState({ open: false, row: null });
 // Sub-tab inside Trust & Reliability — "live" (default) shows the
 // existing platform-health view; "security" shows the curated
 // hardening timeline + audit feed.
 const [view, setView] = useState('live');

 const token = localStorage.getItem('token');
 const hdr = React.useMemo(() => ({ headers: { Authorization: `Bearer ${token}` } }), [token]);

 const load = useCallback(async (showToast = false) => {
 try {
 const res = await axios.get(`${API}/api/master-admin/trust/overview`, hdr);
 setData(res.data);
 if (showToast) notify.success('Trust overview refreshed');
 } catch (e) {
 if (showToast) notify.error('Failed to refresh trust overview');
 else notify.error('Failed to load trust overview');
 } finally {
 setLoading(false);
 }
 }, [hdr]);

 useEffect(() => {
 load();
 const t = setInterval(() => load(false), 30000); // silent auto-refresh every 30s
 return () => clearInterval(t);
 }, [load]);

 // When the parent page's global Refresh is clicked, refreshTick bumps → re-fetch
 useEffect(() => {
 if (refreshTick > 0) load(false);
 // eslint-disable-next-line react-hooks/exhaustive-deps
 }, [refreshTick]);

 const handleAck = async (id) => {
 setBusyId(id);
 try {
 await axios.post(`${API}/api/master-admin/trust/events/${id}/ack`, {}, hdr);
 notify.success('Event acknowledged');
 await load();
 } catch (e) {
 notify.error('Failed to acknowledge');
 } finally {
 setBusyId(null);
 }
 };

 const handleResolve = async (id) => {
 setBusyId(id);
 try {
 await axios.post(`${API}/api/master-admin/trust/events/${id}/resolve`, { note: 'Resolved by admin' }, hdr);
 notify.success('Event resolved');
 await load();
 } catch (e) {
 notify.error('Failed to resolve');
 } finally {
 setBusyId(null);
 }
 };

 const handleSeedDemo = async () => {
 try {
 await axios.post(`${API}/api/master-admin/trust/events/seed-demo`, {}, hdr);
 notify.success('Demo events seeded');
 await load();
 } catch (e) {
 notify.error('Failed to seed');
 }
 };

 if (loading) {
 return <div className="p-8 text-center text-zinc-500" data-testid="trust-loading">Loading trust overview…</div>;
 }
 if (!data) return null;

 const { summary, reliability, integrations, open_events, self_heal_log } = data;
 const reliabilityTone = reliability.reliability_pct >= 99
 ? 'border-l-4 border-emerald-500'
 : reliability.reliability_pct >= 95
 ? 'border-l-4 border-amber-500'
 : 'border-l-4 border-red-500';

 return (
 <div className="space-y-6" data-theme="light" data-testid="trust-dashboard">
   {/* Top tab strip — Live Health vs Security Checks */}
   <div className="flex items-center gap-2 border-b border-zinc-200 pb-2" data-testid="trust-subtabs">
     <button
       type="button"
       onClick={() => setView('live')}
       className={`px-4 py-2 text-sm font-bold rounded-t-lg transition ${view === 'live' ? 'bg-[var(--color-brand-blue)] text-white' : 'text-zinc-600 hover:text-[var(--color-brand-blue)]'}`}
       data-testid="trust-subtab-live"
     >
       <Activity size={14} className="inline mr-1.5" /> Live platform health
     </button>
     <button
       type="button"
       onClick={() => setView('security')}
       className={`px-4 py-2 text-sm font-bold rounded-t-lg transition ${view === 'security' ? 'bg-[var(--color-brand-blue)] text-white' : 'text-zinc-600 hover:text-[var(--color-brand-blue)]'}`}
       data-testid="trust-subtab-security"
     >
       <ShieldCheck size={14} className="inline mr-1.5" /> Security checks
     </button>
   </div>

   {view === 'security' ? (
     <SecurityChecksPanel />
   ) : (
   <>
 <div className="flex items-center justify-between">
 <div className="flex items-center gap-3">
 <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[rgb(var(--rgb-brand-blue)/0.1)]">
 <ShieldCheck size={22} className="text-[var(--color-brand-blue)]" />
 </div>
 <div>
 <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Trust & Reliability Engine</p>
 <p className="text-xl font-bold text-zinc-900">Live platform health</p>
 </div>
 </div>
 <div className="flex items-center gap-2">
 <Button size="sm" variant="outline" onClick={() => load(true)} data-testid="trust-refresh">
 <RefreshCw size={14} className="mr-1" /> Refresh
 </Button>
 <Button size="sm" variant="outline" onClick={handleSeedDemo} data-testid="trust-seed-demo">
 <Zap size={14} className="mr-1" /> Seed demo
 </Button>
 </div>
 </div>

 <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
 <SummaryTile label="Reliability (24h)" value={`${reliability.reliability_pct}%`}
 hint={`${reliability.events_24h} events · ${reliability.bad_events_24h} high/critical`}
 icon={reliability.reliability_pct >= 99 ? TrendingUp : TrendingDown}
 tone={reliabilityTone} />
 <SummaryTile label="Open Events" value={summary.open} icon={ShieldAlert}
 hint={`${summary.acknowledged} acknowledged`} />
 <SummaryTile label="Critical" value={summary.critical_open} icon={XCircle}
 tone={summary.critical_open > 0 ? 'border-l-4 border-red-600' : ''} />
 <SummaryTile label="High" value={summary.high_open} icon={ShieldAlert}
 tone={summary.high_open > 0 ? 'border-l-4 border-red-400' : ''} />
 <SummaryTile label="Resolved (24h)" value={summary.resolved_24h} icon={CheckCircle2}
 tone="border-l-4 border-emerald-500" />
 </div>

 <Card className="p-5">
 <div className="flex items-center gap-2 mb-3">
 <Activity size={16} className="text-zinc-600" />
 <h3 className="text-sm font-bold uppercase tracking-wide text-zinc-700">Integration health</h3>
 <span className="text-[11px] text-zinc-400 ml-2">click any pill for details</span>
 </div>
 <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
 {integrations.map(row => (
 <IntegrationPill key={row.prefix} row={row}
 onClick={r => setIntegrationDialog({ open: true, row: r })} />
 ))}
 </div>
 </Card>

 <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
 <Card className="p-5 lg:col-span-2" data-testid="trust-open-events">
 <div className="flex items-center justify-between mb-3">
 <h3 className="text-sm font-bold uppercase tracking-wide text-zinc-700">Open trust events</h3>
 <Badge variant="outline" className="text-xs text-zinc-600">{open_events.length}</Badge>
 </div>
 {open_events.length === 0 ? (
 <div className="py-10 text-center text-zinc-500">
 <CheckCircle2 size={32} className="mx-auto mb-2 text-emerald-500" />
 <p className="text-sm">All clear — no active events.</p>
 </div>
 ) : (
 <div className="space-y-3">
 {open_events.map(ev => (
 <EventRow key={ev.id} ev={ev} busy={busyId === ev.id}
 onAck={handleAck} onResolve={handleResolve}
 onOpen={e => setEventDialog({ open: true, event: e })} />
 ))}
 </div>
 )}
 </Card>

 <Card className="p-5" data-testid="trust-self-heal">
 <div className="flex items-center gap-2 mb-3">
 <Wand2 size={14} className="text-emerald-600" />
 <h3 className="text-sm font-bold uppercase tracking-wide text-zinc-700">Self-heal log (24h)</h3>
 </div>
 {self_heal_log.length === 0 ? (
 <p className="py-6 text-center text-xs text-zinc-500">No auto-resolved events yet</p>
 ) : (
 <div className="space-y-2">
 {self_heal_log.map(ev => <SelfHealRow key={ev.id} ev={ev} />)}
 </div>
 )}
 </Card>
 </div>

 <UIErrorsCard apiHdr={hdr} />

 <AIActionLogCard apiHdr={hdr} />

 <p className="text-[11px] text-zinc-400 text-right">Generated {new Date(data.generated_at).toLocaleString('en-GB')} · auto-refresh 30s</p>

 <EventDetailDialog open={eventDialog.open} event={eventDialog.event}
 onClose={() => setEventDialog({ open: false, event: null })}
 onEventUpdated={(ev) => setEventDialog({ open: true, event: ev })} />
 <IntegrationDetailDialog open={integrationDialog.open} row={integrationDialog.row} apiHdr={hdr}
 onClose={() => setIntegrationDialog({ open: false, row: null })} />
   </>
   )}
 </div>
 );
}

/* ═══════════════════════════ UI Error Telemetry ═══════════════════════════ */

function UIErrorsCard({ apiHdr }) {
 const [data, setData] = useState(null);
 const [days, setDays] = useState(7);
 const [loading, setLoading] = useState(false);

 const load = useCallback(async () => {
 setLoading(true);
 try {
 const { data } = await axios.get(`${API}/api/ui-errors/summary?days=${days}`, apiHdr);
 setData(data);
 } catch (e) {
 notify.error('Failed to load UI errors', e.response?.data?.detail || 'Try refreshing');
 }
 setLoading(false);
 }, [apiHdr, days]);

 useEffect(() => { load(); }, [load]);

 return (
 <Card className="p-5" data-testid="trust-ui-errors">
 <div className="flex items-center justify-between mb-3">
 <div className="flex items-center gap-2">
 <AlertOctagon size={16} className="text-zinc-600" />
 <h3 className="text-sm font-bold uppercase tracking-wide text-zinc-700">
 User-facing errors · last {days}d
 </h3>
 {data && (
 <span className="text-xs text-zinc-500">
 {data.total_events} events · {data.unique_users_affected} users affected
 </span>
 )}
 </div>
 <div className="flex items-center gap-2">
 <div className="flex rounded-md border border-zinc-200 overflow-hidden text-xs">
 {[1, 7, 30].map((d) => (
 <button
 key={d}
 onClick={() => setDays(d)}
 className={`px-2.5 py-1 ${days === d ? 'bg-[var(--color-brand-blue)] text-white' : 'bg-white text-zinc-600 hover:bg-zinc-50'}`}
 data-testid={`ui-errors-window-${d}`}
 >
 {d}d
 </button>
 ))}
 </div>
 <Button size="sm" variant="outline" onClick={load} disabled={loading} data-testid="ui-errors-refresh">
 <RefreshCw size={12} className={`mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
 </Button>
 </div>
 </div>
 {!data || data.top.length === 0 ? (
 <div className="py-8 text-center text-zinc-500">
 <CheckCircle2 size={28} className="mx-auto mb-2 text-emerald-500" />
 <p className="text-xs">No user-facing errors in the window. Nice.</p>
 </div>
 ) : (
 <div className="space-y-1.5">
 {data.top.slice(0, 15).map((row) => (
 <div
 key={row.fingerprint}
 className="flex items-start gap-3 p-2.5 rounded-md border border-zinc-100 hover:border-zinc-200 hover:bg-zinc-50 transition-colors"
 data-testid={`ui-error-row-${row.fingerprint}`}
 >
 <Badge variant="outline" className="text-[11px] font-bold mt-0.5 shrink-0">
 {row.count}×
 </Badge>
 <div className="flex-1 min-w-0">
 <p className="text-sm font-medium text-zinc-800 truncate">{row.title}</p>
 {row.detail && (
 <p className="text-[11px] text-zinc-500 truncate">{row.detail}</p>
 )}
 <div className="flex items-center gap-2 mt-0.5 text-[10px] text-zinc-400">
 <span>{row.affected_users} user{row.affected_users === 1 ? '' : 's'}</span>
 {row.paths?.length > 0 && (
 <>
 <span>·</span>
 <span className="truncate">{row.paths.slice(0, 2).join(', ')}</span>
 </>
 )}
 {row.last_seen && (
 <>
 <span>·</span>
 <span>last {new Date(row.last_seen).toLocaleString('en-GB')}</span>
 </>
 )}
 </div>
 </div>
 </div>
 ))}
 </div>
 )}
 </Card>
 );
}


/* ═══════════════════════════ AI Action Log ═══════════════════════════ */

const ACTION_TYPE_LABEL = {
 resolve_issue: {
 label: 'Resolved fault',
 color: 'bg-amber-100 text-amber-800 border-amber-300',
 icon: Zap,
 },
 freeze_membership: {
 label: 'Froze membership',
 color: 'bg-sky-100 text-sky-800 border-sky-300',
 icon: Clock,
 },
 cancel_membership: {
 label: 'Cancelled membership',
 color: 'bg-red-100 text-red-800 border-red-300',
 icon: XCircle,
 },
};

function AIActionLogCard({ apiHdr }) {
 const [data, setData] = useState(null);
 const [days, setDays] = useState(7);
 const [filterType, setFilterType] = useState('');
 const [loading, setLoading] = useState(false);
 const [undoingId, setUndoingId] = useState(null);
 const [, setTick] = useState(0);
 const confirm = useConfirm();

 const load = useCallback(async () => {
 setLoading(true);
 try {
 const url = `${API}/api/master-admin/assistant-actions?days=${days}${filterType ? `&action_type=${filterType}` : ''}`;
 const { data } = await axios.get(url, apiHdr);
 setData(data);
 } catch (e) {
 notify.error('Failed to load AI action log', e.response?.data?.detail || 'Try refreshing');
 }
 setLoading(false);
 }, [apiHdr, days, filterType]);

 useEffect(() => { load(); }, [load]);

 // Re-render every 5s while any row still has time on its undo clock so the
 // countdown stays accurate without spamming the server.
 useEffect(() => {
 const t = setInterval(() => setTick((n) => n + 1), 5000);
 return () => clearInterval(t);
 }, []);

 const undoWindowSec = data?.undo_window_seconds || 300;

 const handleUndo = async (row) => {
 const ok = await confirm({
 title: 'Undo this AI action?',
 detail: `This will reverse the "${ACTION_TYPE_LABEL[row.action_type]?.label || row.action_type}" on "${row.target_label}". The original operator (${row.user_name}) will see the change reverted in their next refresh.`,
 tone: 'warning',
 confirmLabel: 'Undo action',
 cancelLabel: 'Keep change',
 });
 if (!ok) return;
 setUndoingId(row.id);
 try {
 await axios.post(`${API}/api/master-admin/assistant-actions/${row.id}/undo`, {}, apiHdr);
 notify.success('Action reversed', `"${row.target_label}" rolled back to ${row.before_status || 'previous state'}.`);
 load();
 } catch (e) {
 notify.error('Undo failed', e.response?.data?.detail || 'Please refresh and try again.');
 } finally {
 setUndoingId(null);
 }
 };

 const totals = data?.totals || { events: 0, by_type: {}, distinct_users: 0, distinct_orgs: 0 };

 return (
 <Card className="p-5" data-testid="trust-ai-actions">
 <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
 <div className="flex items-center gap-2">
 <Sparkles size={16} className="text-cyan-500" />
 <h3 className="text-sm font-bold uppercase tracking-wide text-zinc-700">
 AI Action Log · last {days}d
 </h3>
 {data && (
 <span className="text-xs text-zinc-500">
 {totals.events} mutation{totals.events === 1 ? '' : 's'} · {totals.distinct_users} user{totals.distinct_users === 1 ? '' : 's'} · {totals.distinct_orgs} org{totals.distinct_orgs === 1 ? '' : 's'}
 {data.scoped && <Badge variant="outline" className="ml-2 text-[10px]">Pulse-scoped</Badge>}
 </span>
 )}
 </div>
 <div className="flex items-center gap-2">
 <select
 value={filterType}
 onChange={(e) => setFilterType(e.target.value)}
 className="text-xs px-2 py-1 rounded-md border border-zinc-200 bg-white text-zinc-700"
 data-testid="ai-actions-filter-type"
 >
 <option value="">All types</option>
 <option value="resolve_issue">Resolve fault</option>
 <option value="freeze_membership">Freeze membership</option>
 <option value="cancel_membership">Cancel membership</option>
 </select>
 <div className="flex rounded-md border border-zinc-200 overflow-hidden text-xs">
 {[1, 7, 30].map((d) => (
 <button
 key={d}
 onClick={() => setDays(d)}
 className={`px-2.5 py-1 ${days === d ? 'bg-[var(--color-brand-blue)] text-white' : 'bg-white text-zinc-600 hover:bg-zinc-50'}`}
 data-testid={`ai-actions-window-${d}`}
 >
 {d}d
 </button>
 ))}
 </div>
 <Button size="sm" variant="outline" onClick={load} disabled={loading} data-testid="ai-actions-refresh">
 <RefreshCw size={12} className={`mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
 </Button>
 </div>
 </div>

 {/* Per-type rollup chips */}
 {data && totals.events > 0 && (
 <div className="flex items-center gap-2 mb-3 flex-wrap" data-testid="ai-actions-rollup">
 {Object.entries(totals.by_type).map(([type, count]) => {
 const meta = ACTION_TYPE_LABEL[type] || { label: type, color: 'bg-zinc-100 text-zinc-700 border-zinc-300', icon: Sparkles };
 const Icon = meta.icon;
 return (
 <span key={type} className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold border ${meta.color}`}>
 <Icon size={11} /> {meta.label} <span className="opacity-70">·</span> {count}
 </span>
 );
 })}
 </div>
 )}

 {!data || data.rows.length === 0 ? (
 <div className="py-8 text-center text-zinc-500" data-testid="ai-actions-empty">
 <History size={28} className="mx-auto mb-2 opacity-40" />
 <p className="text-xs">No AI mutations in this window. The assistant is in advisory mode.</p>
 </div>
 ) : (
 <div className="space-y-1.5" data-testid="ai-actions-list">
 {data.rows.map((row) => {
 const meta = ACTION_TYPE_LABEL[row.action_type] || { label: row.action_type, color: 'bg-zinc-100 text-zinc-700 border-zinc-300', icon: Sparkles };
 const Icon = meta.icon;
 const ageSec = (Date.now() - new Date(row.executed_at).getTime()) / 1000;
 const remaining = Math.max(0, undoWindowSec - ageSec);
 const undoable = !row.undone_at && !row.already_done && remaining > 0;
 return (
 <div
 key={row.id}
 className={`flex items-start gap-3 p-2.5 rounded-md border ${row.undone_at ? 'border-zinc-200 opacity-60' : 'border-zinc-100 hover:border-zinc-200 hover:bg-zinc-50'} transition-colors`}
 data-testid={`ai-action-row-${row.id}`}
 >
 <div className={`mt-0.5 inline-flex items-center justify-center w-7 h-7 rounded-full border ${meta.color} shrink-0`}>
 <Icon size={13} />
 </div>
 <div className="flex-1 min-w-0">
 <div className="flex items-center gap-2 flex-wrap">
 <p className="text-sm font-medium text-zinc-800">
 {meta.label} · <span className="text-zinc-600">{row.target_label || row.target_id?.slice(0, 8)}</span>
 </p>
 {row.already_done && (
 <Badge variant="outline" className="text-[10px] text-amber-700 border-amber-300">already done</Badge>
 )}
 {row.undone_at && (
 <Badge variant="outline" className="text-[10px] text-zinc-700 border-zinc-400">UNDONE by {row.undone_by_user_name || 'admin'}</Badge>
 )}
 {row.before_status && row.after_status && (
 <span className="inline-flex items-center gap-1 text-[10px] text-zinc-500">
 <code className="px-1.5 py-0.5 rounded bg-zinc-100">{row.before_status}</code>
 <ArrowRight size={10} />
 <code className={`px-1.5 py-0.5 rounded ${row.undone_at ? 'bg-zinc-100 line-through' : 'bg-emerald-50 text-emerald-700'}`}>{row.after_status}</code>
 </span>
 )}
 </div>
 <div className="flex items-center gap-2 mt-0.5 text-[11px] text-zinc-500 flex-wrap">
 <span><strong>{row.user_name || 'Unknown'}</strong></span>
 <span>·</span>
 <span>{row.organization_name || row.organization_id?.slice(0, 8) || 'unknown org'}</span>
 <span>·</span>
 <span>{new Date(row.executed_at).toLocaleString('en-GB')}</span>
 {row.params?.days && (<><span>·</span><span>{row.params.days} days</span></>)}
 {row.params?.immediate && (<><span>·</span><Badge variant="outline" className="text-[10px] text-red-700 border-red-300">immediate</Badge></>)}
 {row.result_summary && (<><span>·</span><span>effective {String(row.result_summary).slice(0, 10)}</span></>)}
 </div>
 </div>
 {undoable && (
 <Button
 size="sm"
 variant="outline"
 onClick={() => handleUndo(row)}
 disabled={undoingId === row.id}
 className="shrink-0 self-center text-[11px] h-7 px-2.5 border-amber-400 text-amber-700 bg-amber-50 hover:bg-amber-100"
 data-testid={`ai-action-undo-${row.id}`}
 title={`${Math.ceil(remaining)}s left to undo`}
 >
 {undoingId === row.id ? (
 <><Loader2 size={11} className="mr-1 animate-spin" /> Undoing</>
 ) : (
 <><Undo2 size={11} className="mr-1" /> Undo · {Math.ceil(remaining)}s</>
 )}
 </Button>
 )}
 </div>
 );
 })}
 </div>
 )}
 </Card>
 );
}
