/**
 * Pulse Fitness Unified AI Assistant
 *
 * A single floating-orb component that adapts its capabilities based on the
 * current route:
 *
 * • /marketing → Marketing Copilot (campaigns, audiences, journeys)
 * • /pulse → Operations Copilot (faults, equipment, suppliers)
 * • /memberships→ Memberships Copilot (members, plans, classes)
 *
 * Behind every mode the same backend `/api/assistant/chat` endpoint runs
 * Claude Sonnet 4.5 with a tailored system prompt + grounded MongoDB
 * context so answers always reference the user's real numbers.
 *
 * Mounted globally in App.js. Hides itself on:
 * - unauthenticated routes
 * - public landing pages (the legacy AskPulseFitness covers those)
 * - Master Admin / CRM where a different copilot makes sense
 *
 * Action bubbles ("Open Campaigns →", "View Equipment Fleet") run via the
 * shared `gymaxis-jump` CustomEvent — each module listens and reacts.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { useLocation } from 'react-router-dom';
import { Sparkles, X, Loader2, Send, MessageSquare, Zap, CheckCircle2 } from 'lucide-react';
import { notify, useConfirm } from '@/components/notifications';
import { useAuth } from '@/App';

const API_BASE = process.env.REACT_APP_BACKEND_URL;

// Per-mode UI configuration. Backend is single source of truth for what
// actions / context get applied — these are just labels and starter prompts.
const MODES = {
 marketing: {
 label: 'Marketing',
 accent: 'var(--color-brand-cyan)',
 headerLabel: 'Marketing Copilot',
 starters: [
 'How is my last campaign performing?',
 'Which audience should I target next?',
 'Suggest a winback message for inactive members',
 ],
 },
 operations: {
 label: 'Operations',
 accent: '#FF8800',
 headerLabel: 'Operations Copilot',
 starters: [
 'What\'s my fault situation right now?',
 'Which equipment is most likely to break next?',
 'How do I prioritise overdue tickets?',
 ],
 },
 memberships: {
 label: 'Memberships',
 accent: 'var(--color-success)',
 headerLabel: 'Memberships Copilot',
 starters: [
 'How many active members do I have?',
 'Which classes are filling up fastest?',
 'How do I reduce churn on my Premium plan?',
 ],
 },
 // Iter 215q — mount on admin & CRM surfaces so Ask Pulse from every
 // <HelpHint /> actually lands somewhere. These modes reuse the
 // backend 'general' / guide-grounded fallback; no new AI scaffolding.
 admin: {
 label: 'Admin',
 accent: 'var(--color-brand-cyan)',
 headerLabel: 'Admin Copilot',
 starters: [
 'Which integrations are down right now?',
 "How do I reset a user's password?",
 'Explain the bill-to-date balance for this org.',
 ],
 },
 crm: {
 label: 'CRM',
 accent: 'var(--color-brand-cyan)',
 headerLabel: 'CRM Copilot',
 starters: [
 'How do I customise pipeline stages?',
 "What's the difference between Leisure and Business CRM?",
 'Show me the bulk-import CSV steps.',
 ],
 },
};

// Detect the active mode from the route. Returns null when the orb shouldn't render.
function detectMode(pathname) {
 if (pathname.startsWith('/marketing')) return 'marketing';
 if (pathname.startsWith('/pulse') || pathname === '/dashboard') return 'operations';
 if (pathname.startsWith('/memberships')) return 'memberships';
 if (pathname.startsWith('/master-admin')) return 'admin';
 if (pathname.startsWith('/crm')) return 'crm';
 return null;
}

// Render Claude's lightweight markdown (bold + line breaks only).
function renderAnswer(text) {
 if (!text) return '';
 return text
 .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
 .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
 .replace(/\n/g, '<br/>');
}

const UnifiedAssistant = () => {
 const { user } = useAuth();
 const location = useLocation();
 const detected = detectMode(location.pathname);
 // Module entitlement gate — mirror backend's resolved access map.
 const isMaster = user?.is_master_admin === true;
 const moduleAccess = user?.module_access || user?.moduleAccess || {};
 const accessibleMode = (m) => isMaster || moduleAccess[m] !== false;
 const mode = detected && accessibleMode(detected) ? detected : null;
 const cfg = mode ? MODES[mode] : null;
 const confirm = useConfirm();

 // Persist a separate session per mode so each conversation has its own
 // memory and we don't leak campaign context into operations replies.
 const sessionId = useMemo(() => {
 if (!mode) return null;
 const key = `assistant_session_${mode}`;
 const stored = localStorage.getItem(key);
 if (stored) return stored;
 const id = `gx-${mode}-${Math.random().toString(36).slice(2, 11)}`;
 localStorage.setItem(key, id);
 return id;
 }, [mode]);

 // Closed by default — the user opens it deliberately. A 3-second
 // "Can I help you?" bubble peeks out the first time per session per
 // mode so it stays discoverable without being annoying.
 const [open, setOpen] = useState(false);
 const [showHint, setShowHint] = useState(false);
 const [question, setQuestion] = useState('');
 const [turns, setTurns] = useState([]);
 const [busy, setBusy] = useState(false);
 const [executingIdx, setExecutingIdx] = useState(null);
 const scrollRef = useRef(null);

 const headers = useMemo(() => ({
 Authorization: `Bearer ${localStorage.getItem('token')}`,
 }), []);

 // Reset thread when mode flips so the chat reflects the active module.
 useEffect(() => { setTurns([]); }, [mode]);

 // First-touch hint per (mode, day) — slide-out for 3s, then back in.
 useEffect(() => {
 if (!mode || !user) return;
 const key = `assistant_hint_seen_${mode}_${new Date().toDateString()}`;
 if (sessionStorage.getItem(key)) return;
 sessionStorage.setItem(key, '1');
 const showT = setTimeout(() => setShowHint(true), 1200);
 const hideT = setTimeout(() => setShowHint(false), 1200 + 3000);
 return () => { clearTimeout(showT); clearTimeout(hideT); };
 }, [mode, user]);

 // Hydrate prior history for this mode's session.
 useEffect(() => {
 if (!mode || !sessionId || !user) return;
 let cancelled = false;
 (async () => {
 try {
 const { data } = await axios.get(`${API_BASE}/api/assistant/chat/${sessionId}`, { headers });
 if (!cancelled) setTurns(data.turns || []);
 } catch { /* sidebar not critical */ }
 })();
 return () => { cancelled = true; };
 }, [mode, sessionId, user, headers]);

 // Auto-scroll on new turn.
 useEffect(() => {
 if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
 }, [turns, busy]);

 // Iter 215m — Listen for the global "open-unified-assistant" event
 // dispatched by <HelpHint>. Opens the orb and pre-fills the seed
 // question so the user sees what's about to be asked before sending.
 useEffect(() => {
   const onOpen = (e) => {
     const seed = e?.detail?.seed || sessionStorage.getItem('assistant_seed_question') || '';
     setOpen(true);
     if (seed) setQuestion(seed);
     try { sessionStorage.removeItem('assistant_seed_question'); } catch { /* noop */ }
   };
   window.addEventListener('open-unified-assistant', onOpen);
   return () => window.removeEventListener('open-unified-assistant', onOpen);
 }, []);

 const sendMessage = async (msg) => {
 const text = (msg ?? question).trim();
 if (!text || busy || !mode) return;
 setQuestion('');
 setTurns((t) => [...t, { role: 'user', content: text }]);
 setBusy(true);

 // Iter 215l — Page-context awareness. Let the assistant know exactly
 // which screen the user is on so a question like "how do I do this?"
 // resolves to *this* tab, not the whole module. Frontend reads from
 // window location + a sessionStorage breadcrumb each module updates.
 let page_context = null;
 try {
   const params = new URLSearchParams(location.search || '');
   const query = {};
   for (const [k, v] of params.entries()) query[k] = v;
   const breadcrumb = (() => {
     try { return JSON.parse(sessionStorage.getItem('assistant_page_breadcrumb') || '{}'); }
     catch { return {}; }
   })();
   page_context = {
     pathname: location.pathname,
     query,
     tab: query.tab || breadcrumb.tab || null,
     active_section: breadcrumb.active_section || null,
     recent_actions: Array.isArray(breadcrumb.recent_actions) ? breadcrumb.recent_actions.slice(-5) : [],
   };
 } catch { /* breadcrumb is best-effort */ }

 try {
 const { data } = await axios.post(
 `${API_BASE}/api/assistant/chat`,
 { mode, session_id: sessionId, message: text, page_context },
 { headers, timeout: 60_000 },
 );
 setTurns((t) => [...t, { role: 'assistant', content: data.answer, action: data.action }]);
 } catch {
 setTurns((t) => [...t, { role: 'assistant', content: 'Sorry — I had trouble reaching the AI service. Please try again in a moment.' }]);
 } finally {
 setBusy(false);
 }
 };

 const executeAction = async (action, idx) => {
 if (!action || executingIdx !== null) return;

 // Destructive actions require explicit operator confirmation.
 const destructiveCopy = {
 resolve_issue: { title: 'Mark fault as resolved?', detail: 'This will close the fault and stamp it with your name in the timeline.', tone: 'warning', confirmLabel: 'Resolve fault' },
 freeze_membership: { title: 'Freeze this membership?', detail: `Billing pauses for ${action.params?.days || 30} day(s). Member can still attend until the freeze starts.`, tone: 'warning', confirmLabel: 'Freeze' },
 cancel_membership: { title: 'Cancel this membership?', detail: action.params?.immediate ? 'IMMEDIATE cancellation — the member loses access right away.' : 'Cancellation will take effect after the plan\'s notice period.', tone: 'danger', confirmLabel: action.params?.immediate ? 'Cancel now' : 'Cancel at notice' },
 };
 const copy = destructiveCopy[action.type];
 if (copy) {
 const ok = await confirm({ title: copy.title, detail: copy.detail, tone: copy.tone, confirmLabel: copy.confirmLabel, cancelLabel: 'Keep as-is' });
 if (!ok) return;
 }

 setExecutingIdx(idx);
 try {
 const { data } = await axios.post(
 `${API_BASE}/api/assistant/execute-action`,
 { mode, type: action.type, params: action.params },
 { headers },
 );
 setTurns((t) => t.map((turn, i) => i === idx ? { ...turn, done: true } : turn));

 // Side-effects: emit a global jump event each module can opt into.
 if (action.type === 'navigate_tab' && data.navigate_to_tab) {
 window.dispatchEvent(new CustomEvent('gymaxis-jump', {
 detail: { mode, target: data.navigate_to_tab, deep_link: data.deep_link },
 }));
 notify.success(`Switched to ${data.navigate_to_tab.charAt(0).toUpperCase() + data.navigate_to_tab.slice(1)} tab`);
 } else if (action.type === 'navigate' && data.navigate_to) {
 window.dispatchEvent(new CustomEvent('gymaxis-jump', {
 detail: { mode, target: data.navigate_to, deep_link: data.deep_link },
 }));
 notify.success(`Opening ${data.navigate_to}…`);
 } else if (action.type === 'instantiate_template') {
 notify.success('Template ready', `Audience size: ${data.audience_size || 0} · saved as a draft.`);
 window.dispatchEvent(new CustomEvent('gymaxis-jump', { detail: { mode, target: 'campaigns' } }));
 } else if (action.type === 'resolve_issue') {
 notify.success(data.already_done ? 'Fault was already resolved' : 'Fault resolved', 'Operations updated.');
 window.dispatchEvent(new CustomEvent('gymaxis-jump', {
 detail: { mode, target: data.navigate_to_tab, deep_link: data.deep_link },
 }));
 } else if (action.type === 'freeze_membership') {
 notify.success('Membership frozen', `Resumes on ${data.result?.frozen_until?.slice(0,10) || 'the scheduled date'}.`);
 window.dispatchEvent(new CustomEvent('gymaxis-jump', {
 detail: { mode, target: data.navigate_to_tab, deep_link: data.deep_link },
 }));
 } else if (action.type === 'cancel_membership') {
 notify.success('Cancellation logged', data.result?.effective ? `Effective ${data.result.effective.slice(0,10)}.` : 'Saved.');
 window.dispatchEvent(new CustomEvent('gymaxis-jump', {
 detail: { mode, target: data.navigate_to_tab, deep_link: data.deep_link },
 }));
 } else if (data.deep_link) {
 // Deep-link actions (open_fault / open_member / open_plan / open_equipment).
 window.dispatchEvent(new CustomEvent('gymaxis-jump', {
 detail: { mode, target: data.navigate_to_tab, deep_link: data.deep_link },
 }));
 notify.success(`Opening ${data.deep_link.kind} ${data.deep_link.label}`);
 }
 } catch (err) {
 notify.error(err.response?.data?.detail || 'Couldn\'t execute that action');
 } finally {
 setExecutingIdx(null);
 }
 };

 // Iter 215d6.1 — hide the floating assistant while any modal/drawer is
 // open so its sparkle icon never overlaps a Save/Cancel button.
 // Tracks a live count of open `[role=dialog][aria-modal="true"]`
 // elements via a MutationObserver.
 const [modalOpen, setModalOpen] = React.useState(false);
 React.useEffect(() => {
   const check = () => {
     if (typeof document === 'undefined') return;
     const openDialogs = document.querySelectorAll(
       '[role="dialog"][aria-modal="true"], [data-testid$="-drawer"], [data-testid="mbr-add-modal"], [data-testid="mbr-class-editor"], [data-testid="mbr-plan-editor"]'
     );
     setModalOpen(openDialogs.length > 0);
   };
   check();
   const mo = new MutationObserver(check);
   mo.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-state', 'role', 'aria-modal'] });
   return () => mo.disconnect();
 }, []);

 // Don't render on unsupported routes / unauthenticated.
 if (!mode || !user) return null;
 if (modalOpen) return null;

 // On the public member app (`/m/{slug}`) the orb floats on a phone-sized
 // viewport, so shrink it to ~70% of the dashboard size so it doesn't eat
 // up screen real estate.
 const onMemberApp = typeof window !== 'undefined' && window.location.pathname.startsWith('/m/');

 if (!open) {
    return (
      <div
        className={`fixed ${onMemberApp ? 'bottom-4 right-3' : 'bottom-24 md:bottom-5 right-4 md:right-5'} z-30 flex items-center gap-2`}
        data-testid="unified-assistant-toggle-wrapper"
        data-fab-rail
        data-fab-slot="primary"
      >
 {/* "Can I help you?" hint bubble — slides out on first touch */}
 <div
 className={`pointer-events-none transition-all duration-500 ease-out origin-right ${
 showHint
 ? 'opacity-100 translate-x-0 scale-100'
 : 'opacity-0 translate-x-6 scale-90'
 }`}
 aria-hidden={!showHint}
 >
 <div
 className={`${onMemberApp ? 'px-2 py-1 text-[10px]' : 'px-3 py-2 text-sm'} rounded-2xl rounded-br-sm shadow-xl font-bold whitespace-nowrap text-white`}
 style={{ background: `linear-gradient(135deg, var(--color-brand-blue), ${cfg.accent})` }}
 data-testid="unified-assistant-hint"
 >
 Can I help you?
 </div>
 </div>

 <button
 onClick={() => { setOpen(true); setShowHint(false); }}
 className={`${onMemberApp ? 'w-9 h-9' : 'w-12 h-12'} rounded-full text-white shadow-xl flex items-center justify-center hover:scale-105 transition relative`}
 style={{ background: `linear-gradient(135deg, var(--color-brand-blue), ${cfg.accent})` }}
 aria-label={`Open ${cfg.headerLabel}`}
 data-testid="unified-assistant-toggle"
 >
 <Sparkles size={onMemberApp ? 13 : 18} />
 {/* Pulse ring while the hint is visible */}
 {showHint && (
 <span
 className="absolute inset-0 rounded-full animate-ping"
 style={{ background: cfg.accent, opacity: 0.35 }}
 />
 )}
 </button>
 </div>
 );
 }

 return (
 <div
 className="fixed bottom-24 md:bottom-5 right-4 md:right-5 w-96 max-w-[calc(100vw-2rem)] rounded-2xl shadow-2xl overflow-hidden z-30 flex flex-col max-h-[calc(100vh-8rem)]"
 style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', borderWidth: 1 }}
 data-testid="unified-assistant"
 data-assistant-mode={mode}
 >
 <div className="flex items-center justify-between p-3 text-white flex-shrink-0" style={{ background: `linear-gradient(135deg, var(--color-brand-blue), ${cfg.accent})` }}>
 <div className="flex items-center gap-2">
 <Sparkles size={14} />
 <p className="text-sm font-semibold">{cfg.headerLabel} <span className="text-[10px] font-normal opacity-80 ml-1">· Claude</span></p>
 </div>
 <button onClick={() => setOpen(false)} className="text-white/80 hover:text-white" data-testid="unified-assistant-close" aria-label="Close">
 <X size={14} />
 </button>
 </div>

 <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-2.5" data-testid="unified-assistant-thread" style={{ minHeight: 220 }}>
 {turns.length === 0 ? (
 <div className="text-center py-2">
 <MessageSquare className="mx-auto mb-2 opacity-40" size={20} style={{ color: 'var(--theme-text-muted)' }} />
 <p className="text-[11px] font-semibold mb-2" style={{ color: 'var(--theme-text-muted)' }}>Try one of these:</p>
 <div className="space-y-1.5">
 {cfg.starters.map((q, i) => (
 <button
 key={i}
 onClick={() => sendMessage(q)}
 className="w-full text-left text-[11px] px-2.5 py-1.5 rounded-md border hover:bg-[rgb(var(--rgb-brand-blue)/0.05)] transition"
 style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
 data-testid={`unified-starter-${i}`}
 >
 "{q}"
 </button>
 ))}
 </div>
 </div>
 ) : (
 turns.map((turn, i) => (
 <div key={i} className={`flex ${turn.role === 'user' ? 'justify-end' : 'justify-start'}`} data-testid={`unified-turn-${i}`}>
 <div className={`max-w-[85%] flex flex-col gap-2 ${turn.role === 'user' ? 'items-end' : 'items-start'}`}>
 <div
 className={`px-3 py-2 rounded-2xl text-xs leading-relaxed ${turn.role === 'user' ? 'rounded-br-sm' : 'rounded-bl-sm'}`}
 style={turn.role === 'user'
 ? { background: `linear-gradient(135deg, var(--color-brand-blue), ${cfg.accent})`, color: 'white' }
 : { background: 'var(--theme-bg)', color: 'var(--theme-text)', border: '1px solid var(--theme-border)' }}
 dangerouslySetInnerHTML={turn.role === 'assistant' ? { __html: renderAnswer(turn.content) } : undefined}
 >
 {turn.role === 'user' ? turn.content : null}
 </div>
 {turn.role === 'assistant' && turn.action && (
 <button
 onClick={() => !turn.done && executeAction(turn.action, i)}
 disabled={turn.done || executingIdx === i}
 className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-bold shadow-sm transition disabled:opacity-60"
 style={turn.done
 ? { background: 'rgb(16 185 129 / 0.12)', color: 'rgb(16 185 129)', border: '1px solid rgb(16 185 129 / 0.3)' }
 : { background: `linear-gradient(135deg, var(--color-brand-blue), ${cfg.accent})`, color: 'white' }}
 data-testid={`unified-action-${i}`}
 >
 {executingIdx === i ? <Loader2 size={11} className="animate-spin" /> : turn.done ? <CheckCircle2 size={11} /> : <Zap size={11} />}
 {turn.done ? 'Done' : (executingIdx === i ? 'Working…' : turn.action.label)}
 </button>
 )}
 </div>
 </div>
 ))
 )}
 {busy && (
 <div className="flex items-center gap-1.5 text-[11px]" style={{ color: 'var(--theme-text-muted)' }} data-testid="unified-thinking">
 <Loader2 size={11} className="animate-spin" /> Thinking…
 </div>
 )}
 </div>

 <form
 className="p-2.5 flex gap-1.5 border-t flex-shrink-0"
 style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}
 onSubmit={(e) => { e.preventDefault(); sendMessage(); }}
 data-testid="unified-form"
 >
 <input
 value={question}
 onChange={(e) => setQuestion(e.target.value)}
 placeholder={`Ask anything about ${cfg.label.toLowerCase()}…`}
 disabled={busy}
 className="flex-1 px-2.5 py-1.5 text-xs rounded-md disabled:opacity-50"
 style={{ background: 'var(--theme-bg)', color: 'var(--theme-text)', border: '1px solid var(--theme-border)' }}
 data-testid="unified-input"
 />
 <button
 type="submit"
 disabled={!question.trim() || busy}
 className="p-1.5 rounded-md text-white disabled:opacity-40 disabled:cursor-not-allowed"
 style={{ background: cfg.accent }}
 data-testid="unified-send"
 aria-label="Send"
 >
 {busy ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
 </button>
 </form>
 </div>
 );
};

export default UnifiedAssistant;
