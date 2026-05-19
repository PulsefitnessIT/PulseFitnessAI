import { useEffect, useState } from 'react';
import axios from 'axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import {
 Sparkles, Users, Mail, Gauge, ThumbsUp, ThumbsDown,
 MessageSquare, RotateCcw, CheckCircle2,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;
const hdr = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } });

const STATUS_COLOURS = {
 open: 'bg-red-100 text-red-700 border-red-200',
 in_progress: 'bg-amber-100 text-amber-700 border-amber-200',
 resolved: 'bg-emerald-100 text-emerald-700 border-emerald-200',
 closed: 'bg-zinc-100 text-zinc-700 border-zinc-200',
};

function MetricCard({ label, value, hint, icon: Icon, tone = 'neutral' }) {
 const toneClass = {
 neutral: 'text-zinc-900',
 good: 'text-emerald-700',
 warn: 'text-amber-700',
 bad: 'text-red-700',
 }[tone];
 return (
 <Card className="bg-white border-zinc-200 shadow-sm p-5" data-testid={`ask-metric-${label.toLowerCase().replace(/\s/g, '-')}`}>
 <div className="flex items-start justify-between">
 <div>
 <p className="text-[11px] text-zinc-500 uppercase tracking-wide">{label}</p>
 <p className={`text-2xl font-semibold mt-1 ${toneClass}`}>{value}</p>
 {hint && <p className="text-[11px] text-zinc-400 mt-1">{hint}</p>}
 </div>
 {Icon && <Icon size={18} className="text-zinc-400" />}
 </div>
 </Card>
 );
}

function AnalyticsStrip({ analytics }) {
 if (!analytics) return null;
 const { volume, deflection_pct, avg_latency_ms, csat, cases_by_status } = analytics;
 const csatTone = csat?.score_pct == null ? 'neutral'
 : csat.score_pct >= 80 ? 'good'
 : csat.score_pct >= 60 ? 'warn'
 : 'bad';
 return (
 <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
 <MetricCard label="Asks / 30d" value={volume?.asks ?? 0}
 hint={`${volume?.blocked ?? 0} blocked by safety`} icon={Sparkles} />
 <MetricCard label="Deflection" value={`${deflection_pct ?? 0}%`}
 hint={`${volume?.escalated ?? 0} escalated to humans`}
 tone={(deflection_pct ?? 0) >= 80 ? 'good' : 'warn'} icon={Gauge} />
 <MetricCard label="CSAT"
 value={csat?.score_pct == null ? '—' : `${csat.score_pct}%`}
 hint={`${csat?.thumbs_up ?? 0} up · ${csat?.thumbs_down ?? 0} down`}
 tone={csatTone}
 icon={ThumbsUp} />
 <MetricCard label="Avg response" value={`${Math.round((avg_latency_ms ?? 0) / 1000 * 10) / 10}s`}
 hint={`${cases_by_status?.open ?? 0} open cases`}
 icon={Mail} />
 </div>
 );
}

function CaseRow({ c, onOpen }) {
 const csClass = STATUS_COLOURS[c.status] || STATUS_COLOURS.open;
 const when = (c.created_at || '').slice(0, 16).replace('T', ' ');
 return (
 <button
 type="button"
 onClick={() => onOpen(c)}
 className="w-full text-left p-4 bg-white border border-zinc-200 rounded-lg hover:border-[rgb(var(--rgb-brand-blue)/0.3)] hover:shadow-sm transition-all"
 data-testid={`ask-case-row-${c.id}`}
 >
 <div className="flex items-start justify-between gap-3">
 <div className="min-w-0 flex-1">
 <div className="flex items-center gap-2 flex-wrap">
 <span className="font-mono text-xs text-[var(--color-brand-blue)] font-semibold">{c.ref}</span>
 <Badge variant="outline" className={`text-[10px] ${csClass}`}>{c.status}</Badge>
 <span className="text-[11px] text-zinc-400">{when}</span>
 {c.email_sent && (
 <span className="text-[10px] text-emerald-600 inline-flex items-center gap-0.5">
 <Mail size={10} /> emailed
 </span>
 )}
 </div>
 <p className="text-sm text-zinc-900 mt-1 font-medium truncate">{c.org_name || 'Unknown org'}</p>
 <p className="text-xs text-zinc-500 mt-0.5 truncate">{c.user_email} · {c.user_name}</p>
 {c.reason && <p className="text-xs text-zinc-600 mt-1.5 line-clamp-2">{c.reason}</p>}
 </div>
 </div>
 </button>
 );
}

function CaseDetail({ caseDoc, onClose, onUpdated }) {
 const [status, setStatus] = useState(caseDoc.status);
 const [resolution, setResolution] = useState(caseDoc.resolution || '');
 const [saving, setSaving] = useState(false);

 const save = async () => {
 setSaving(true);
 try {
 const res = await axios.patch(`${API}/api/master-admin/support/cases/${caseDoc.id}`,
 { status, resolution }, hdr());
 notify.success(`Case ${caseDoc.ref} updated`);
 onUpdated(res.data);
 } catch (e) {
 notifyApiError(notify, e, 'Update failed');
 } finally {
 setSaving(false);
 }
 };

 return (
 <div className="fixed inset-0 bg-black/50 z-[110] flex items-center justify-center p-4"
 onClick={onClose} data-testid="ask-case-detail">
 <div className="bg-white w-full max-w-2xl max-h-[85vh] rounded-xl shadow-2xl flex flex-col"
 onClick={e => e.stopPropagation()}>
 <header className="p-5 border-b border-zinc-200 flex items-start justify-between">
 <div>
 <p className="text-[11px] text-zinc-500 uppercase tracking-wide">Support case</p>
 <h2 className="font-bold text-lg text-zinc-900 font-mono">{caseDoc.ref}</h2>
 <p className="text-xs text-zinc-500 mt-1">{caseDoc.org_name} · {caseDoc.user_email}</p>
 </div>
 <button onClick={onClose} className="text-zinc-400 hover:text-zinc-900" data-testid="ask-case-close">✕</button>
 </header>

 <div className="flex-1 overflow-y-auto p-5 space-y-4">
 {caseDoc.reason && (
 <Card className="bg-amber-50 border-amber-200 p-5">
 <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-800">Reason</p>
 <p className="text-sm text-amber-900 mt-1">{caseDoc.reason}</p>
 </Card>
 )}

 <div>
 <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500 mb-2">
 Transcript ({caseDoc.transcript?.length || 0} turns)
 </p>
 <div className="space-y-2">
 {(caseDoc.transcript || []).map((t, i) => (
 <div key={i} className={`p-3 rounded-lg ${t.role === 'assistant' ? 'bg-blue-50' : 'bg-zinc-50'}`}>
 <p className="text-[10px] uppercase tracking-wide text-zinc-500 mb-0.5">
 {t.role} · {(t.created_at || '').slice(0, 16).replace('T', ' ')}
 </p>
 <p className="text-sm text-zinc-900 whitespace-pre-wrap">{t.text}</p>
 </div>
 ))}
 {(caseDoc.transcript?.length || 0) === 0 && (
 <p className="text-xs text-zinc-400 italic">No transcript captured.</p>
 )}
 </div>
 </div>

 <div className="grid grid-cols-2 gap-3">
 <div>
 <label className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Status</label>
 <select
 value={status}
 onChange={e => setStatus(e.target.value)}
 className="w-full mt-1 text-sm border border-zinc-300 rounded px-3 py-2"
 data-testid="ask-case-status-select"
 >
 <option value="open">Open</option>
 <option value="in_progress">In progress</option>
 <option value="resolved">Resolved</option>
 <option value="closed">Closed</option>
 </select>
 </div>
 <div>
 <label className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Routed to</label>
 <p className="mt-2 text-sm text-zinc-900">{caseDoc.recipient_email || '—'}</p>
 </div>
 </div>
 <div>
 <label className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Resolution notes</label>
 <Textarea
 value={resolution}
 onChange={e => setResolution(e.target.value)}
 rows={3}
 placeholder="What did you do? Did the customer agree?"
 className="mt-1 text-sm"
 data-testid="ask-case-resolution"
 />
 </div>
 </div>

 <footer className="p-4 border-t border-zinc-200 flex justify-end gap-2 bg-zinc-50">
 <Button variant="outline" size="sm" onClick={onClose} data-testid="ask-case-cancel">Cancel</Button>
 <Button size="sm" onClick={save} disabled={saving}
 className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white"
 data-testid="ask-case-save">
 {saving ? 'Saving…' : 'Save changes'}
 </Button>
 </footer>
 </div>
 </div>
 );
}

function ClassifierBreakdown({ rows }) {
 if (!rows?.length) return null;
 const total = rows.reduce((a, r) => a + r.count, 0) || 1;
 return (
 <Card className="bg-white border-zinc-200 shadow-sm p-5" data-testid="ask-classifier-breakdown">
 <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500 mb-3">Classifier breakdown (30d)</p>
 <div className="space-y-1.5">
 {rows.map(r => (
 <div key={r.label} className="flex items-center gap-3">
 <span className="text-xs text-zinc-700 w-28 capitalize">{r.label.replace('_', ' ')}</span>
 <div className="flex-1 h-2 bg-zinc-100 rounded-full overflow-hidden">
 <div className="h-full bg-[var(--color-brand-blue)]"
 style={{ width: `${Math.round(r.count * 100 / total)}%` }} />
 </div>
 <span className="text-xs text-zinc-500 w-8 text-right">{r.count}</span>
 </div>
 ))}
 </div>
 </Card>
 );
}

export default function AskSupportDesk() {
 const [cases, setCases] = useState([]);
 const [analytics, setAnalytics] = useState(null);
 const [loading, setLoading] = useState(true);
 const [statusFilter, setStatusFilter] = useState('all');
 const [openCase, setOpenCase] = useState(null);

 const load = async () => {
 setLoading(true);
 try {
 const q = statusFilter === 'all' ? '' : `?status=${statusFilter}`;
 const [casesR, analyticsR] = await Promise.all([
 axios.get(`${API}/api/master-admin/support/cases${q}`, hdr()),
 axios.get(`${API}/api/master-admin/support/analytics?days=30`, hdr()),
 ]);
 setCases(casesR.data.cases || []);
 setAnalytics(analyticsR.data);
 } catch (e) {
 notifyApiError(notify, e, 'Failed to load support desk');
 } finally {
 setLoading(false);
 }
 };
 // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: the loader closure(s) re-read live state on every call; the effect re-fires on the listed trigger deps, so adding the function identity would just thrash without changing behaviour.
 useEffect(() => { load();   }, [statusFilter]);

 const handleUpdated = (updated) => {
 setOpenCase(updated);
 setCases(cs => cs.map(c => c.id === updated.id ? { ...c, ...updated } : c));
 };

 const filters = [
 { id: 'all', label: 'All' },
 { id: 'open', label: 'Open' },
 { id: 'in_progress', label: 'In progress' },
 { id: 'resolved', label: 'Resolved' },
 { id: 'closed', label: 'Closed' },
 ];

 return (
 <div className="space-y-6" data-testid="ask-support-desk">
 <AnalyticsStrip analytics={analytics} />

 <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
 <div className="md:col-span-2 space-y-3">
 <div className="flex items-center justify-between">
 <h3 className="font-medium text-zinc-900">Human-escalated cases</h3>
 <Button variant="outline" size="sm" onClick={load} disabled={loading}
 data-testid="ask-refresh-btn">
 <RotateCcw size={13} className="mr-1.5" /> Refresh
 </Button>
 </div>

 <div className="flex gap-1 flex-wrap">
 {filters.map(f => (
 <button
 key={f.id}
 onClick={() => setStatusFilter(f.id)}
 className={`px-3 py-1 text-xs rounded-full border transition-colors ${
 statusFilter === f.id
 ? 'bg-[var(--color-brand-blue)] border-[var(--color-brand-blue)] text-white'
 : 'bg-white border-zinc-200 text-zinc-700 hover:border-zinc-300'
 }`}
 data-testid={`ask-filter-${f.id}`}
 >
 {f.label}
 </button>
 ))}
 </div>

 <div className="space-y-2">
 {loading && <p className="text-sm text-zinc-400 p-4">Loading…</p>}
 {!loading && cases.length === 0 && (
 <Card className="bg-white border-zinc-200 p-6 text-center">
 <CheckCircle2 size={28} className="text-emerald-500 mx-auto mb-2" />
 <p className="text-sm font-medium text-zinc-900">No escalated cases</p>
 <p className="text-xs text-zinc-500 mt-1">
 The AI assistant is handling everything on its own right now.
 </p>
 </Card>
 )}
 {!loading && cases.map(c => <CaseRow key={c.id} c={c} onOpen={setOpenCase} />)}
 </div>
 </div>

 <div className="space-y-4">
 <ClassifierBreakdown rows={analytics?.classifier_breakdown || []} />
 <Card className="bg-white border-zinc-200 shadow-sm p-5" data-testid="ask-csat-summary">
 <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500 mb-3">CSAT (30d)</p>
 <div className="flex items-center gap-4">
 <div className="flex items-center gap-1.5 text-emerald-700">
 <ThumbsUp size={14} /> <span className="text-lg font-semibold">{analytics?.csat?.thumbs_up ?? 0}</span>
 </div>
 <div className="flex items-center gap-1.5 text-red-700">
 <ThumbsDown size={14} /> <span className="text-lg font-semibold">{analytics?.csat?.thumbs_down ?? 0}</span>
 </div>
 </div>
 {analytics?.csat?.score_pct != null && (
 <p className="text-xs text-zinc-500 mt-2">
 Overall {analytics.csat.score_pct}% satisfaction across {analytics.csat.total} ratings.
 </p>
 )}
 </Card>
 <Card className="bg-white border-zinc-200 shadow-sm p-5" data-testid="ask-cases-summary">
 <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500 mb-3">Case status</p>
 <div className="grid grid-cols-2 gap-2 text-sm">
 {Object.entries(analytics?.cases_by_status || {}).map(([s, n]) => (
 <div key={s} className="flex justify-between">
 <span className="capitalize text-zinc-600">{s.replace('_', ' ')}</span>
 <span className="font-semibold text-zinc-900">{n}</span>
 </div>
 ))}
 </div>
 </Card>
 <Card className="bg-white border-zinc-200 shadow-sm p-5">
 <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500 mb-2">Where escalations go</p>
 <div className="space-y-1.5 text-xs text-zinc-600">
 <div className="flex items-start gap-2"><Users size={12} className="mt-0.5 text-[var(--color-brand-blue)]" />
 <span>Pulse Lite / Pulse Pro → <span className="font-mono">service.dept@pulsefitness.com</span></span>
 </div>
 <div className="flex items-start gap-2"><MessageSquare size={12} className="mt-0.5 text-[var(--color-brand-blue)]" />
 <span>GymAxis customers → same inbox (configurable via env)</span>
 </div>
 </div>
 </Card>
 </div>
 </div>

 {openCase && <CaseDetail caseDoc={openCase} onClose={() => setOpenCase(null)} onUpdated={handleUpdated} />}
 </div>
 );
}
