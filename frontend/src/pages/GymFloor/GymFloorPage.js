/**
 * Gym Floor — shared-credential login + Handover Diary.
 *
 * Two UIs in one file:
 * • /gym-floor — public shared-credential login page (lives at site-level,
 * one login shared by all gym-floor staff, managed by the Manager).
 * • Post-login: Handover Diary surface where staff pick their name from
 * a managed roster, choose a topic, and log notes. Date auto-fills.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
 ClipboardList, ShieldAlert, Users, Sparkles, LogOut, Send, Trash2, Plus,
 CheckCircle2, AlertTriangle, Calendar, Clock, Wrench, User, Eye, EyeOff,
} from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useInlineBanner } from '@/components/notifications';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const STORAGE_KEY = 'gym_floor_session';

// ─── Login view ─────────────────────────────────────────────────

function GymFloorLogin({ onAuthed }) {
 const [username, setUsername] = useState('');
 const [password, setPassword] = useState('');
 const [busy, setBusy] = useState(false);
 const [showPwd, setShowPwd] = useState(false);
 const { banner, show, clear } = useInlineBanner({ autoDismiss: false });

 const submit = async (e) => {
 e.preventDefault();
 clear();
 setBusy(true);
 try {
 const { data } = await axios.post(`${API}/gym-floor/login`, { username, password });
 const session = { ...data, logged_in_at: new Date().toISOString() };
 localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
 onAuthed(session);
 } catch (err) {
 show({
 tone: 'error',
 title: 'Incorrect credentials',
 detail: 'Ask your manager for the current gym-floor username and password.',
 });
 }
 setBusy(false);
 };

 return (
 <div className="min-h-screen flex items-center justify-center p-4" style={{ background: 'var(--theme-bg)', color: 'var(--theme-text)' }}>
 <form onSubmit={submit} className="w-full max-w-sm space-y-5" data-testid="gym-floor-login-form">
 <div className="text-center">
 <div className="w-12 h-12 rounded-2xl bg-[rgb(var(--rgb-brand-cyan)/0.15)] text-[var(--color-brand-cyan)] grid place-items-center mx-auto mb-3">
 <ClipboardList size={22} />
 </div>
 <h1 className="text-2xl font-bold">Gym Floor</h1>
 <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>Shared staff login · Handover Diary</p>
 </div>
 {banner}
 <div className="space-y-2">
 <Label className="text-xs">Username</Label>
 <Input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus required data-testid="gym-floor-username" />
 </div>
 <div className="space-y-2">
 <Label className="text-xs">Password</Label>
 <div className="relative">
 <Input
 type={showPwd ? 'text' : 'password'}
 value={password}
 onChange={(e) => setPassword(e.target.value)}
 required
 className="pr-10"
 data-testid="gym-floor-password"
 />
 <button
 type="button"
 onClick={() => setShowPwd((v) => !v)}
 className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded hover:bg-black/5 dark:hover:bg-white/10 dark:bg-zinc-900"
 aria-label={showPwd ? 'Hide password' : 'Show password'}
 data-testid="gym-floor-password-toggle"
 >
 {showPwd ? <EyeOff size={14} className="text-zinc-500" /> : <Eye size={14} className="text-zinc-500" />}
 </button>
 </div>
 </div>
 <Button type="submit" disabled={busy} className="w-full bg-[var(--color-brand-cyan)] text-black hover:bg-[rgb(var(--rgb-brand-cyan)/0.9)] rounded-full" data-testid="gym-floor-submit">
 {busy ? 'Signing in…' : 'Sign in'}
 </Button>
 </form>
 </div>
 );
}

// ─── Handover Diary ─────────────────────────────────────────────

const SEVERITY_OPTIONS = [
 { value: 'operational_minor', label: 'Operational — Minor', desc: 'Machine is fully usable; minor fault or annoyance.' },
 { value: 'operational_fault', label: 'Operational — Fault present', desc: 'Works but not as intended; could worsen.' },
 { value: 'non_operational', label: 'Non-operational', desc: 'Machine is out of service.' },
 { value: 'safety_critical', label: 'Safety critical', desc: 'Risk of injury — take out of use immediately.' },
];

function FaultLogger({ session, staff, onLogged }) {
 const [equipment, setEquipment] = useState([]);
 const [form, setForm] = useState({ staff_id: '', equipment_id: '', issue_description: '', severity: 'operational_minor', steps_taken: '' });
 const [busy, setBusy] = useState(false);
 const [lastRef, setLastRef] = useState(null);
 const { banner, show, clear } = useInlineBanner();

 const headers = useMemo(() => ({ 'X-Gym-Floor-Token': session.token }), [session.token]);

 const loadEquipment = useCallback(async () => {
 try {
 const r = await axios.get(`${API}/gym-floor/equipment`, { headers });
 setEquipment(r.data.equipment || []);
 } catch {}
 }, [headers]);
 useEffect(() => { loadEquipment(); }, [loadEquipment]);

 const groups = useMemo(() => {
 const m = {};
 equipment.forEach((eq) => {
 const short = eq.name?.includes(',') ? eq.name.split(',')[0].trim() : (eq.name || '');
 if (!m[short]) m[short] = [];
 m[short].push(eq);
 });
 return m;
 }, [equipment]);
 const groupKeys = Object.keys(groups).sort();
 const selectedEq = equipment.find((e) => e.id === form.equipment_id);
 const selectedGroup = selectedEq ? (selectedEq.name?.includes(',') ? selectedEq.name.split(',')[0].trim() : selectedEq.name) : '';
 const groupItems = groups[selectedGroup] || [];
 const needsSerialPick = groupItems.length > 1;

 const handleGroupChange = (g) => {
 const items = groups[g] || [];
 if (items.length > 0) setForm((f) => ({ ...f, equipment_id: items[0].id }));
 };

 const submit = async (e) => {
 e.preventDefault();
 clear();
 if (!form.staff_id) {
 show({ tone: 'error', title: 'Pick your name first', detail: 'Suppliers need to know who logged the fault — select your name from the list above.' });
 return;
 }
 if (!form.equipment_id) {
 show({ tone: 'error', title: 'Pick the affected machine' });
 return;
 }
 if (!form.issue_description.trim()) {
 show({ tone: 'error', title: 'Add a short description', detail: 'Describe what\'s wrong so engineers know where to start.' });
 return;
 }
 setBusy(true);
 try {
 const { data } = await axios.post(`${API}/gym-floor/fault`, form, { headers });
 setLastRef(data.ref);
 show({
 tone: 'success',
 title: `Fault logged · ${data.ref}`,
 detail: `Reported by ${data.reporter?.name || 'you'} (${data.reporter?.email}). The supplier will reach out on the contact details above.`,
 });
 setForm({ ...form, equipment_id: '', issue_description: '', steps_taken: '' });
 onLogged?.();
 } catch (err) {
 show({ tone: 'error', title: 'Couldn\'t log the fault', detail: err.response?.data?.detail || 'Please try again.' });
 }
 setBusy(false);
 };

 const selectedStaff = staff.find((s) => s.id === form.staff_id);

 return (
 <Card className="p-5 rounded-xl" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} data-testid="gym-floor-fault-card">
 <form onSubmit={submit} className="space-y-4">
 {banner}

 {/* Step 1 — Who's logging? (mandatory, at the very top of the card) */}
 <div className="rounded-lg p-3 border" style={{ background: 'var(--theme-bg)', borderColor: form.staff_id ? 'var(--theme-border)' : 'var(--color-brand-cyan)' }}>
 <Label className="text-xs flex items-center gap-1.5 mb-1.5">
 <User size={12} /> <span className="font-semibold">Who's logging this fault?</span>
 <span className="text-red-500">*</span>
 </Label>
 <select
 value={form.staff_id}
 onChange={(e) => setForm({ ...form, staff_id: e.target.value })}
 className="w-full h-10 px-3 rounded-lg border text-sm"
 style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
 data-testid="gym-floor-fault-staff"
 required
 >
 <option value="">Select your name…</option>
 {staff.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
 </select>
 {selectedStaff && (
 <p className="text-[11px] mt-1.5" style={{ color: 'var(--theme-text-muted)' }} data-testid="gym-floor-fault-contact-preview">
 We'll attach <span className="font-mono">{selectedStaff.name}</span>'s contact details to the supplier ticket so they can reach the right person.
 </p>
 )}
 {!selectedStaff && staff.length === 0 && (
 <p className="text-[11px] mt-1.5 text-amber-600 dark:text-amber-400">
 Your manager hasn't added any staff yet. Ask them to set up the roster from Pulse Pro → Gym Floor → Setup.
 </p>
 )}
 </div>

 {/* Step 2 — Pick the machine */}
 <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
 <div>
 <Label className="text-xs">Machine type *</Label>
 <select
 value={selectedGroup}
 onChange={(e) => handleGroupChange(e.target.value)}
 className="w-full mt-1 h-10 px-3 rounded-lg border text-sm"
 style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
 data-testid="gym-floor-fault-machine-type"
 required
 >
 <option value="">Choose machine type…</option>
 {groupKeys.map((g) => (
 <option key={g} value={g}>{g}{groups[g].length > 1 ? ` (${groups[g].length})` : ''}</option>
 ))}
 </select>
 </div>
 {selectedGroup && needsSerialPick && (
 <div>
 <Label className="text-xs">Serial / location *</Label>
 <select
 value={form.equipment_id}
 onChange={(e) => setForm({ ...form, equipment_id: e.target.value })}
 className="w-full mt-1 h-10 px-3 rounded-lg border text-sm"
 style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
 data-testid="gym-floor-fault-serial"
 >
 {groupItems.map((eq) => (
 <option key={eq.id} value={eq.id}>
 {eq.serial_number || 'No serial'}{eq.location ? ` · ${eq.location}` : ''}
 </option>
 ))}
 </select>
 </div>
 )}
 </div>

 {/* Step 3 — Describe */}
 <div>
 <Label className="text-xs">What's wrong? *</Label>
 <Textarea
 value={form.issue_description}
 onChange={(e) => setForm({ ...form, issue_description: e.target.value })}
 placeholder="Describe the fault as best you can — what's the machine doing, what should it be doing, any noises, smells, error codes?"
 className="mt-1 min-h-[110px]"
 data-testid="gym-floor-fault-description"
 />
 </div>

 {/* Step 4 — Severity */}
 <div>
 <Label className="text-xs">Severity</Label>
 <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-1.5" data-testid="gym-floor-fault-severity">
 {SEVERITY_OPTIONS.map((sev) => {
 const sel = form.severity === sev.value;
 return (
 <button
 key={sev.value}
 type="button"
 onClick={() => setForm({ ...form, severity: sev.value })}
 className="text-left p-3 rounded-lg border-2 transition-all"
 style={{
 borderColor: sel ? 'var(--color-brand-cyan)' : 'var(--theme-border)',
 background: sel ? 'rgba(25,205,255,0.08)' : 'var(--theme-bg)',
 }}
 data-testid={`gym-floor-sev-${sev.value}`}
 >
 <div className="flex items-center justify-between">
 <span className="text-sm font-medium" style={{ color: sel ? 'var(--color-brand-cyan)' : 'var(--theme-text)' }}>{sev.label}</span>
 {sel && <CheckCircle2 size={14} style={{ color: 'var(--color-brand-cyan)' }} />}
 </div>
 <p className="text-[11px] mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>{sev.desc}</p>
 </button>
 );
 })}
 </div>
 </div>

 <div>
 <Label className="text-xs">Anything you've already tried? <span className="opacity-50">(optional)</span></Label>
 <Textarea
 value={form.steps_taken}
 onChange={(e) => setForm({ ...form, steps_taken: e.target.value })}
 placeholder="e.g. restarted the machine, tightened the cable…"
 className="mt-1 min-h-[60px]"
 data-testid="gym-floor-fault-steps"
 />
 </div>

 <Button
 type="submit"
 disabled={busy}
 className="w-full rounded-full bg-[var(--color-brand-cyan)] text-black hover:bg-[rgb(var(--rgb-brand-cyan)/0.9)] font-semibold"
 data-testid="gym-floor-fault-submit"
 >
 {busy ? 'Logging fault…' : <><AlertTriangle size={14} className="mr-1.5" /> Log fault report</>}
 </Button>
 {lastRef && (
 <p className="text-[11px] text-center" style={{ color: 'var(--theme-text-muted)' }}>Last fault reference: <span className="font-mono">{lastRef}</span></p>
 )}
 </form>
 </Card>
 );
}

function HandoverDiary({ session, onSignOut }) {
 const [staff, setStaff] = useState([]);
 const [topics, setTopics] = useState([]);
 const [entries, setEntries] = useState([]);
 const [form, setForm] = useState({ staff_name: '', topic_id: '', notes: '' });
 const [busy, setBusy] = useState(false);
 const [tab, setTab] = useState('diary'); // 'diary' | 'fault'
 const { banner, show, clear } = useInlineBanner();

 const headers = useMemo(() => ({ 'X-Gym-Floor-Token': session.token }), [session.token]);
 const today = new Date();
 const dateLabel = today.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

 const load = useCallback(async () => {
 try {
 const [s, t, e] = await Promise.all([
 axios.get(`${API}/gym-floor/staff`, { headers }),
 axios.get(`${API}/gym-floor/topics`, { headers }),
 axios.get(`${API}/gym-floor/handover`, { headers }),
 ]);
 setStaff(s.data.staff || []);
 setTopics(t.data.topics || []);
 setEntries(e.data.entries || []);
 } catch (err) {
 if (err.response?.status === 401) onSignOut();
 }
 }, [headers, onSignOut]);
 useEffect(() => { load(); }, [load]);

 const submit = async (e) => {
 e.preventDefault();
 clear();
 if (!form.staff_name || !form.topic_id || !form.notes.trim()) {
 show({ tone: 'error', title: 'Missing details', detail: 'Pick your name, a topic, and add a note before saving.' });
 return;
 }
 setBusy(true);
 try {
 const { data } = await axios.post(`${API}/gym-floor/handover`, form, { headers });
 if (data.entry.flagged) {
 show({
 tone: 'warning',
 title: 'Note saved but flagged for review',
 detail: 'This note was flagged by our moderation filter and the Manager has been notified. Please keep diary entries respectful.',
 });
 } else {
 show({ tone: 'success', title: 'Handover logged', detail: 'Thanks for keeping the team in the loop.' });
 }
 setForm({ ...form, notes: '' });
 load();
 } catch (err) {
 show({ tone: 'error', title: 'Couldn\'t save', detail: err.response?.data?.detail || 'Please try again.' });
 }
 setBusy(false);
 };

 const topicLabel = (id) => topics.find((t) => t.id === id)?.label || id;

 return (
 <div className="min-h-screen" style={{ background: 'var(--theme-bg)', color: 'var(--theme-text)' }} data-testid="gym-floor-diary">
 <header className="border-b" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
 <div className="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between">
 <div className="flex items-center gap-2">
 <div className="w-8 h-8 rounded-xl bg-[rgb(var(--rgb-brand-cyan)/0.15)] text-[var(--color-brand-cyan)] grid place-items-center">
 <ClipboardList size={15} />
 </div>
 <div>
 <div className="text-[10px] font-bold tracking-[0.2em] uppercase text-[var(--color-brand-cyan)]">GymAxis</div>
 <h1 className="text-base font-bold">Handover Diary</h1>
 </div>
 </div>
 <Button variant="outline" size="sm" onClick={onSignOut} className="rounded-full" data-testid="gym-floor-signout">
 <LogOut size={13} className="mr-1" /> Sign out
 </Button>
 </div>
 </header>

 <main className="max-w-4xl mx-auto px-4 py-6 space-y-5">
 {/* Tab switcher — Diary | Log a Fault */}
 <div className="flex gap-1 p-1 rounded-lg max-w-md mx-auto" style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }} data-testid="gym-floor-tabs">
 {[
 { id: 'diary', label: 'Handover Diary', icon: ClipboardList },
 { id: 'fault', label: 'Log a Fault', icon: Wrench },
 ].map((t) => {
 const Icon = t.icon;
 const sel = tab === t.id;
 return (
 <button
 key={t.id}
 onClick={() => setTab(t.id)}
 className="flex-1 px-3 py-2 rounded-md text-sm font-semibold transition-colors flex items-center justify-center gap-1.5"
 style={sel ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' } : { color: 'var(--theme-text-muted)' }}
 data-testid={`gym-floor-tab-${t.id}`}
 >
 <Icon size={14} /> {t.label}
 </button>
 );
 })}
 </div>

 {tab === 'fault' && (
 <FaultLogger session={session} staff={staff} />
 )}

 {tab === 'diary' && (<>
 <Card className="p-5 rounded-xl" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
 <form onSubmit={submit} className="space-y-3" data-testid="gym-floor-entry-form">
 {banner}
 <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}>
 <Calendar size={12} /> <span data-testid="gym-floor-auto-date">{dateLabel}</span>
 <span className="mx-1">·</span>
 <Clock size={12} /> {today.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
 </div>
 <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
 <div>
 <Label className="text-xs">Who's on shift?</Label>
 <select
 value={form.staff_name}
 onChange={(e) => setForm({ ...form, staff_name: e.target.value })}
 className="w-full mt-1 h-10 px-3 rounded-lg border text-sm"
 style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
 data-testid="gym-floor-staff-select"
 >
 <option value="">Choose your name…</option>
 {staff.map((s) => <option key={s.id} value={s.name}>{s.name}</option>)}
 </select>
 </div>
 <div>
 <Label className="text-xs">Topic</Label>
 <select
 value={form.topic_id}
 onChange={(e) => setForm({ ...form, topic_id: e.target.value })}
 className="w-full mt-1 h-10 px-3 rounded-lg border text-sm"
 style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
 data-testid="gym-floor-topic-select"
 >
 <option value="">Choose topic…</option>
 {topics.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
 </select>
 </div>
 </div>
 <div>
 <Label className="text-xs">Notes for the next shift</Label>
 <textarea
 value={form.notes}
 onChange={(e) => setForm({ ...form, notes: e.target.value })}
 placeholder="What happened today? What needs attention? Anything the next shift should know?"
 className="w-full mt-1 p-3 rounded-lg border text-sm min-h-[120px] resize-y"
 style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
 data-testid="gym-floor-notes"
 />
 <p className="text-[10px] mt-1" style={{ color: 'var(--theme-text-muted)' }}>
 Keep it professional — notes are reviewed for offensive language automatically.
 </p>
 </div>
 <Button type="submit" disabled={busy} className="w-full md:w-auto rounded-full bg-[var(--color-brand-cyan)] text-black hover:bg-[rgb(var(--rgb-brand-cyan)/0.9)]" data-testid="gym-floor-post">
 <Send size={13} className="mr-1.5" /> {busy ? 'Saving…' : 'Post to diary'}
 </Button>
 </form>
 </Card>

 <div className="space-y-3">
 <h2 className="text-sm font-semibold flex items-center gap-2" style={{ color: 'var(--theme-text-muted)' }}>
 <Users size={13} /> Recent entries · {entries.length}
 </h2>
 {entries.length === 0 ? (
 <div className="p-6 text-center text-sm rounded-xl border" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>
 No handover entries yet. Be the first to post!
 </div>
 ) : entries.map((e) => (
 <Card key={e.id} className="p-5 rounded-xl" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} data-testid={`gym-floor-entry-${e.id}`}>
 <div className="flex items-center justify-between gap-3 mb-1.5">
 <div className="flex items-center gap-2">
 <div className="w-8 h-8 rounded-full bg-[rgb(var(--rgb-brand-cyan)/0.15)] text-[var(--color-brand-cyan)] grid place-items-center text-xs font-bold">
 {(e.staff_name || '?').split(' ').map((p) => p[0]).join('').slice(0, 2).toUpperCase()}
 </div>
 <div>
 <p className="text-sm font-semibold">{e.staff_name}</p>
 <p className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>
 {new Date(e.created_at).toLocaleString()} · {topicLabel(e.topic_id)}
 </p>
 </div>
 </div>
 {e.flagged && (
 <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-amber-500/20 text-amber-700 dark:text-amber-400" title={e.moderation?.reason || 'Flagged by moderation'}>
 <ShieldAlert size={11} /> Flagged
 </span>
 )}
 </div>
 <p className="text-sm whitespace-pre-wrap leading-relaxed" style={{ color: 'var(--theme-text)' }}>{e.notes}</p>
 </Card>
 ))}
 </div>
 </>)}
 </main>
 </div>
 );
}

// ─── Route root ─────────────────────────────────────────────────

export default function GymFloorPage() {
 const [session, setSession] = useState(() => {
 try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null'); } catch { return null; }
 });
 const navigate = useNavigate();

 const onSignOut = () => {
 localStorage.removeItem(STORAGE_KEY);
 setSession(null);
 // Pulse-branded operators land on /pulse where the unified login
 // dialog opens for both staff and gym-floor accounts.
 navigate('/pulse', { replace: true });
 };

 // No separate Gym Floor login page — bounce unauthenticated visitors
 // back to the main login surface. Staff log in there with the same
 // credentials they were given by their manager.
 useEffect(() => {
 if (!session?.token) {
 navigate('/pulse', { replace: true });
 }
 }, [session?.token, navigate]);

 if (!session?.token) {
 return null;
 }
 return <HandoverDiary session={session} onSignOut={onSignOut} />;
}
