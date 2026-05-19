/**
 * Pulse Master Admin — Setup Tasks panel.
 *
 * A live checklist surfaced at the top of the Overview for delegated Pulse
 * admins. Each task auto-ticks itself based on backend state (Stripe Connect
 * configured, equipment imported, customers imported, etc.) so the list
 * shrinks as work gets done — no manual maintenance.
 *
 * Tasks bucket into:
 * • integrations — Stripe Connect, Sage, Sicon, Orbit 4
 * • bulk imports — equipment, customer roster
 * • content — onboarding packets, AI image fallback verification
 * • compliance — security baseline, audit log review
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
 CheckCircle2, Circle, ChevronRight, ListChecks, RefreshCw,
 CreditCard, Users, Wrench, FileText, ShieldCheck, ArrowLeftRight,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

const TASK_DEFS = [
 // ── INTEGRATIONS ────────────────────────────────────────────
 {
 id: 'stripe-server-config',
 group: 'integrations',
 icon: CreditCard,
 title: 'Configure Stripe Connect server keys',
 body: 'Set STRIPE_CONNECT_CLIENT_ID, STRIPE_CONNECT_REDIRECT_URI, and STRIPE_CONNECT_WEBHOOK_SECRET in backend/.env, then restart.',
 cta: { label: 'Open Stripe tab', section: 'stripe-connect' },
 isDone: ({ stripe }) => !!stripe?.configured,
 },
 {
 id: 'stripe-connected',
 group: 'integrations',
 icon: CreditCard,
 title: 'Connect Pulse Fitness to Stripe',
 body: 'Run the OAuth wizard so we can issue charges on the connected account and take the platform fee.',
 cta: { label: 'Connect with Stripe', section: 'stripe-connect' },
 isDone: ({ stripe }) => !!stripe?.connected,
 },
 {
 id: 'stripe-charges-enabled',
 group: 'integrations',
 icon: CreditCard,
 title: 'Stripe charges enabled',
 body: 'Stripe verifies the connected account before charges go live. This ticks itself once Stripe flips charges_enabled.',
 cta: { label: 'Check status', section: 'stripe-connect' },
 isDone: ({ stripe }) => !!stripe?.charges_enabled,
 },
 {
 id: 'sicon-integration',
 group: 'integrations',
 icon: ArrowLeftRight,
 title: 'Wire up Sicon Service',
 body: 'Configure Sicon credentials so service jobs and assets sync both ways.',
 cta: { label: 'Open Sicon tab', section: 'sicon-integration' },
 isDone: ({ integrations }) => !!integrations?.sicon_configured,
 },
 {
 id: 'orbit4-integration',
 group: 'integrations',
 icon: ArrowLeftRight,
 title: 'Wire up Orbit 4',
 body: 'Connect Orbit 4 so customer + contract data flows in.',
 cta: { label: 'Open Orbit 4 tab', section: 'orbit4' },
 isDone: ({ integrations }) => !!integrations?.orbit4_configured,
 },

 // ── BULK IMPORTS ────────────────────────────────────────────
 {
 id: 'import-customers',
 group: 'imports',
 icon: Users,
 title: 'Bulk import customers',
 body: 'Upload your CRM customer roster as CSV. Download the template, edit, then upload — duplicates by email are skipped.',
 cta: { label: 'Open Bulk Imports', section: 'onboarding' },
 isDone: ({ counts }) => (counts?.customers || 0) > 0,
 },
 {
 id: 'import-equipment',
 group: 'imports',
 icon: Wrench,
 title: 'Bulk import equipment',
 body: 'Upload your equipment fleet as CSV (or upload supplier invoices for AI-assisted parsing on the Onboard Site flow).',
 cta: { label: 'Open Bulk Imports', section: 'onboarding' },
 isDone: ({ counts }) => (counts?.equipment || 0) > 0,
 },

 // ── CONTENT ─────────────────────────────────────────────────
 {
 id: 'onboarding-packet',
 group: 'content',
 icon: FileText,
 title: 'Send first onboarding packet',
 body: 'Onboarding packets walk new sites through setup with a branded checklist.',
 cta: { label: 'Open packets', section: 'onboarding' },
 isDone: ({ counts }) => (counts?.onboarding_packets_sent || 0) > 0,
 },

 // ── COMPLIANCE ──────────────────────────────────────────────
 {
 id: 'review-trust',
 group: 'compliance',
 icon: ShieldCheck,
 title: 'Review the Trust dashboard',
 body: 'Sign-off security/reliability baselines and acknowledge any open events. Required quarterly.',
 cta: { label: 'Open Trust dashboard', section: 'trust' },
 isDone: ({ trust }) => !!trust?.acknowledged_recently,
 },
];

const GROUP_LABELS = {
 integrations: 'Integrations',
 imports: 'Bulk imports',
 content: 'Content',
 compliance: 'Compliance',
};

const SetupTasksPanel = ({ API, onJumpToSection }) => {
 const token = localStorage.getItem('token');
 const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
 const [snapshot, setSnapshot] = useState(null);
 const [loading, setLoading] = useState(true);
 const [collapsed, setCollapsed] = useState(false);

 const load = useCallback(async () => {
 setLoading(true);
 try {
 const { data } = await axios.get(`${API}/master-admin/setup-tasks`, { headers });
 setSnapshot(data);
 } catch {
 setSnapshot({ stripe: {}, integrations: {}, counts: {}, trust: {} });
 }
 setLoading(false);
 }, [API, headers]);
 useEffect(() => { load(); }, [load]);

 const tasks = useMemo(() => {
 if (!snapshot) return [];
 return TASK_DEFS.map((t) => ({ ...t, done: !!t.isDone(snapshot) }));
 }, [snapshot]);

 const completed = tasks.filter((t) => t.done).length;
 const total = tasks.length;
 const pct = total ? Math.round((completed / total) * 100) : 0;

 // Group + sort: incomplete first (by group), then completed at the bottom.
 const grouped = useMemo(() => {
 const open = tasks.filter((t) => !t.done);
 const done = tasks.filter((t) => t.done);
 const groups = {};
 open.forEach((t) => {
 groups[t.group] = groups[t.group] || [];
 groups[t.group].push(t);
 });
 return { groups, doneList: done };
 }, [tasks]);

 if (loading) return null;

 return (
 <Card className="p-5 rounded-xl border-zinc-200 bg-white" data-testid="setup-tasks-panel">
 <button
 onClick={() => setCollapsed((c) => !c)}
 className="w-full flex items-center justify-between text-left"
 data-testid="setup-tasks-toggle"
 >
 <div className="flex items-center gap-3">
 <div className="w-9 h-9 rounded-lg bg-[rgb(var(--rgb-brand-blue)/0.1)] text-[var(--color-brand-blue)] grid place-items-center">
 <ListChecks size={18} />
 </div>
 <div>
 <h2 className="text-base font-semibold text-zinc-900">Setup tasks</h2>
 <p className="text-xs text-zinc-500">
 {completed === total
 ? 'All caught up — nothing pending.'
 : `${completed} of ${total} done · ${pct}% complete`}
 </p>
 </div>
 </div>
 <div className="flex items-center gap-3">
 <div className="hidden sm:block w-32 h-1.5 rounded-full bg-zinc-100 overflow-hidden">
 <div
 className="h-full bg-emerald-500 transition-all"
 style={{ width: `${pct}%` }}
 data-testid="setup-tasks-progress"
 />
 </div>
 <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); load(); }} className="text-zinc-500 hover:text-zinc-700">
 <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
 </Button>
 <ChevronRight size={16} className={`text-zinc-400 transition-transform ${collapsed ? '' : 'rotate-90'}`} />
 </div>
 </button>

 {!collapsed && (
 <div className="mt-5 space-y-5">
 {Object.keys(grouped.groups).length === 0 && grouped.doneList.length === total ? (
 <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 flex items-center gap-3" data-testid="setup-tasks-all-done">
 <CheckCircle2 size={18} className="text-emerald-700" />
 <p className="text-sm text-emerald-900">Setup complete. Time to onboard your first site.</p>
 </div>
 ) : (
 Object.entries(grouped.groups).map(([gid, items]) => (
 <div key={gid}>
 <p className="text-[10px] uppercase tracking-wider text-zinc-400 font-semibold mb-2">{GROUP_LABELS[gid] || gid}</p>
 <ul className="space-y-2">
 {items.map((t) => (
 <TaskRow key={t.id} task={t} onJump={onJumpToSection} />
 ))}
 </ul>
 </div>
 ))
 )}

 {grouped.doneList.length > 0 && (
 <details className="text-xs" data-testid="setup-tasks-done-collapse">
 <summary className="cursor-pointer text-zinc-500 hover:text-zinc-700 select-none">
 {grouped.doneList.length} completed task{grouped.doneList.length !== 1 ? 's' : ''}
 </summary>
 <ul className="mt-2 space-y-1.5">
 {grouped.doneList.map((t) => (
 <li key={t.id} className="flex items-center gap-2 text-zinc-500" data-testid={`task-row-${t.id}`}>
 <CheckCircle2 size={14} className="text-emerald-500 shrink-0" />
 <span className="line-through">{t.title}</span>
 </li>
 ))}
 </ul>
 </details>
 )}
 </div>
 )}
 </Card>
 );
};

const TaskRow = ({ task, onJump }) => {
 const Icon = task.icon || Circle;
 return (
 <li
 className="rounded-lg border border-zinc-200 hover:border-[rgb(var(--rgb-brand-blue)/0.4)] hover:bg-zinc-50 transition-colors p-3 flex items-start gap-3"
 data-testid={`task-row-${task.id}`}
 >
 <div className="w-8 h-8 rounded-lg bg-zinc-100 grid place-items-center text-zinc-500 shrink-0">
 <Icon size={14} />
 </div>
 <div className="flex-1 min-w-0">
 <p className="text-sm font-medium text-zinc-900">{task.title}</p>
 <p className="text-[12px] text-zinc-500 mt-0.5 leading-relaxed">{task.body}</p>
 </div>
 {task.cta && (
 <Button
 size="sm"
 variant="outline"
 onClick={() => onJump?.(task.cta.section)}
 className="shrink-0 text-[var(--color-brand-blue)] border-[rgb(var(--rgb-brand-blue)/0.3)] hover:bg-[rgb(var(--rgb-brand-blue)/0.05)]"
 data-testid={`task-cta-${task.id}`}
 >
 {task.cta.label} <ChevronRight size={12} className="ml-1" />
 </Button>
 )}
 </li>
 );
};

export default SetupTasksPanel;
