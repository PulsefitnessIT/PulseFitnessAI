import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { Sparkles, X, Send, Loader2, Check, ExternalLink, User, Bot, ThumbsUp, ThumbsDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

const API = process.env.REACT_APP_BACKEND_URL;

/* ----------------------------- Context helpers ----------------------------- */
// Lightweight inference of what the user is looking at (for context pill).
// Fed by data-page and data-entity attributes on the current URL/route.
function resolveEntityFromDOM() {
 const path = window.location.pathname;
 const eqMatch = path.match(/\/equipment\/([a-f0-9-]{36})/i);
 if (eqMatch) return { entity_id: eqMatch[1], entity_type: 'equipment', page: path };
 const faultMatch = path.match(/\/faults?\/([a-f0-9-]{36})/i);
 if (faultMatch) return { entity_id: faultMatch[1], entity_type: 'fault', page: path };
 return { entity_id: null, entity_type: null, page: path };
}

const CONFIRMABLE_TOOLS = new Set(['log_fault_draft', 'message_supplier']);

function ToolConfirmDialog({ open, onClose, action, onConfirmed, apiHdr, sessionId }) {
 const [preview, setPreview] = useState(null);
 const [args, setArgs] = useState({});
 const [submitting, setSubmitting] = useState(false);

 useEffect(() => {
 if (!open || !action) return;
 setArgs(action.args || {});
 axios.get(`${API}/api/support/tools/preview/${action.action}`, apiHdr)
 .then(r => setPreview(r.data))
 .catch(() => setPreview({ title: 'Confirm action?', description: '', confirm_label: 'Confirm', fields: [] }));
 }, [open, action, apiHdr]);

 if (!open || !action) return null;
 const updateArg = (k, v) => setArgs(prev => ({ ...prev, [k]: v }));

 const submit = async () => {
 setSubmitting(true);
 try {
 const res = await axios.post(`${API}/api/support/tool/confirm`,
 { session_id: sessionId, tool: action.action, args }, apiHdr);
 notify.success(res.data.message || 'Action completed');
 onConfirmed(res.data);
 } catch (e) {
 notifyApiError(notify, e, 'Action failed');
 } finally {
 setSubmitting(false);
 }
 };

 return (
 <div
 className="fixed inset-0 bg-black/50 z-[120] flex items-end sm:items-center justify-center p-0 sm:p-4"
 onClick={onClose}
 data-testid="ask-confirm-backdrop"
 >
 <div
 className="bg-white w-full sm:max-w-md rounded-t-2xl sm:rounded-xl shadow-2xl"
 onClick={e => e.stopPropagation()}
 data-testid="ask-confirm-dialog"
 >
 <header className="p-5 border-b border-zinc-200">
 <h3 className="font-bold text-zinc-900">{preview?.title || 'Confirm action?'}</h3>
 <p className="text-sm text-zinc-600 mt-1">{preview?.description || ''}</p>
 </header>
 <div className="p-5 space-y-3 max-h-[50vh] overflow-y-auto">
 {(preview?.fields || []).map(field => (
 <div key={field}>
 <label className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
 {field.replace(/_/g, ' ')}
 </label>
 {field === 'issue_description' || field === 'message' ? (
 <textarea
 rows={3}
 value={args[field] || ''}
 onChange={e => updateArg(field, e.target.value)}
 className="w-full mt-1 text-sm border border-zinc-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[rgb(var(--rgb-brand-blue)/0.3)]"
 data-testid={`ask-confirm-field-${field}`}
 />
 ) : field === 'severity' ? (
 <select
 value={args[field] || 'low'}
 onChange={e => updateArg(field, e.target.value)}
 className="w-full mt-1 text-sm border border-zinc-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[rgb(var(--rgb-brand-blue)/0.3)]"
 data-testid={`ask-confirm-field-${field}`}
 >
 <option value="low">Low</option>
 <option value="medium">Medium</option>
 <option value="high">High</option>
 <option value="out_of_order">Out of order</option>
 </select>
 ) : (
 <input
 type="text"
 value={args[field] || ''}
 onChange={e => updateArg(field, e.target.value)}
 className="w-full mt-1 text-sm border border-zinc-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[rgb(var(--rgb-brand-blue)/0.3)]"
 data-testid={`ask-confirm-field-${field}`}
 />
 )}
 </div>
 ))}
 <p className="text-[11px] text-zinc-500 flex items-start gap-1 pt-2">
 <Check size={11} className="mt-0.5 shrink-0" />
 Review the details above — nothing happens until you confirm.
 </p>
 </div>
 <footer className="p-4 border-t border-zinc-200 flex gap-2 justify-end bg-zinc-50">
 <Button variant="outline" size="sm" onClick={onClose} disabled={submitting}
 data-testid="ask-confirm-cancel">Cancel</Button>
 <Button size="sm" onClick={submit} disabled={submitting}
 className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white" data-testid="ask-confirm-submit">
 {submitting ? <><Loader2 size={12} className="mr-1 animate-spin" /> Working…</> : (preview?.confirm_label || 'Confirm')}
 </Button>
 </footer>
 </div>
 </div>
 );
}

/* -------------------------- Suggested actions map ------------------------- */
const ACTION_LABEL_FALLBACK = {
 log_fault_draft: 'Log a fault',
 open_warranty: 'View warranty',
 message_supplier: 'Message supplier',
 book_engineer: 'Book an engineer',
 open_equipment: 'Open equipment',
 open_fault: 'Open fault',
 open_documents: 'Open documents',
 upgrade_plan: 'Upgrade to Pro',
 escalate_human: 'Contact human support',
};

function SuggestedActionButton({ action, onAction }) {
 const label = action.label || ACTION_LABEL_FALLBACK[action.action] || action.action;
 const handleClick = () => {
 if (action.action === 'navigate_deep_link' && action._deep_link) {
 window.location.href = action._deep_link;
 return;
 }
 onAction(action);
 };
 return (
 <Button
 size="sm"
 variant="outline"
 onClick={handleClick}
 className="text-xs h-8 bg-white hover:bg-[var(--color-brand-blue)] hover:text-white hover:border-[var(--color-brand-blue)] transition-colors"
 data-testid={`ask-action-${action.action}`}
 >
 {label}
 </Button>
 );
}

/* ------------------------------ Message bubbles ---------------------------- */
function UserBubble({ text }) {
 return (
 <div className="flex gap-3 items-start" data-testid="ask-msg-user">
 <div className="shrink-0 h-7 w-7 rounded-full bg-zinc-200 flex items-center justify-center">
 <User size={13} className="text-zinc-600" />
 </div>
 <div className="flex-1 pt-0.5">
 <p className="text-xs font-semibold text-zinc-500 mb-1">You</p>
 <p className="text-sm text-zinc-900 leading-relaxed">{text}</p>
 </div>
 </div>
 );
}

function CsatControl({ msg, onRate }) {
 const [rated, setRated] = useState(msg._csat_rated || null);
 const [showCommentFor, setShowCommentFor] = useState(null);
 const [comment, setComment] = useState('');

 if (msg._is_tool_outcome || msg.blocked) return null;

 const handleClick = (rating) => {
 if (rated) return;
 setRated(rating);
 if (rating === 'down') {
 setShowCommentFor('down');
 onRate({ rating, comment: '' });
 } else {
 onRate({ rating, comment: '' });
 }
 };

 const submitComment = () => {
 onRate({ rating: 'down', comment: comment.trim(), _update: true });
 setShowCommentFor(null);
 };

 return (
 <div className="flex items-center gap-1 mt-3" data-testid="ask-csat">
 <span className="text-[10px] text-zinc-400 mr-1">Was this helpful?</span>
 <button
 type="button"
 disabled={!!rated}
 onClick={() => handleClick('up')}
 className={`h-6 w-6 rounded-md flex items-center justify-center transition-colors ${
 rated === 'up' ? 'bg-emerald-100 text-emerald-700' : 'text-zinc-400 hover:bg-zinc-100 hover:text-emerald-600'
 } ${rated && rated !== 'up' ? 'opacity-30' : ''}`}
 data-testid="ask-csat-up"
 aria-label="Thumbs up"
 >
 <ThumbsUp size={12} />
 </button>
 <button
 type="button"
 disabled={!!rated}
 onClick={() => handleClick('down')}
 className={`h-6 w-6 rounded-md flex items-center justify-center transition-colors ${
 rated === 'down' ? 'bg-red-100 text-red-700' : 'text-zinc-400 hover:bg-zinc-100 hover:text-red-600'
 } ${rated && rated !== 'down' ? 'opacity-30' : ''}`}
 data-testid="ask-csat-down"
 aria-label="Thumbs down"
 >
 <ThumbsDown size={12} />
 </button>
 {showCommentFor === 'down' && (
 <div className="flex items-center gap-1 ml-2 flex-1">
 <input
 type="text"
 value={comment}
 onChange={(e) => setComment(e.target.value)}
 placeholder="What went wrong?"
 className="flex-1 text-[11px] border border-zinc-300 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-red-500/40"
 data-testid="ask-csat-comment"
 />
 <button
 type="button"
 onClick={submitComment}
 className="text-[10px] font-medium text-[var(--color-brand-blue)] hover:underline"
 data-testid="ask-csat-comment-submit"
 >
 Send
 </button>
 </div>
 )}
 </div>
 );
}

function AssistantBubble({ msg, onAction, assistantName, onRate }) {
 const doc_sources = msg.doc_sources || [];
 return (
 <div className="flex gap-3 items-start" data-testid="ask-msg-assistant">
 <div className="shrink-0 h-7 w-7 rounded-full bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center">
 <Bot size={13} className="text-white" />
 </div>
 <div className="flex-1 pt-0.5">
 <p className="text-xs font-semibold text-zinc-500 mb-1">{assistantName}</p>
 <p className="text-sm text-zinc-900 leading-relaxed whitespace-pre-wrap">{msg.text}</p>
 {doc_sources.length > 0 && (
 <div className="flex flex-wrap gap-1 mt-2">
 {doc_sources.slice(0, 3).map((s, i) => (
 <Badge key={i} variant="outline" className="text-[10px] text-zinc-600 bg-zinc-50">
 📄 {s.equipment || s.supplier || s.title || 'Manual'}
 </Badge>
 ))}
 </div>
 )}
 {msg.suggested_actions?.length > 0 && (
 <div className="flex flex-wrap gap-2 mt-3">
 {msg.suggested_actions.map((a, i) => (
 <SuggestedActionButton key={i} action={a} onAction={onAction} />
 ))}
 </div>
 )}
 {msg.needs_human && (
 <button
 type="button"
 className="inline-flex items-center gap-1 mt-3 text-xs font-medium text-[var(--color-brand-blue)] hover:underline"
 onClick={() => onAction({ action: 'escalate_human', label: 'Escalate to human' })}
 data-testid="ask-escalate-human"
 >
 Still need a human? <ExternalLink size={11} />
 </button>
 )}
 {msg.blocked && (
 <Badge variant="outline" className="mt-2 bg-amber-50 text-amber-800 border-amber-300 text-[10px]">
 Request blocked by safety filter
 </Badge>
 )}
 {onRate && <CsatControl msg={msg} onRate={onRate} />}
 </div>
 </div>
 );
}

/* ------------------------------ Skeleton loader ---------------------------- */
function AssistantSkeleton() {
 return (
 <div className="flex gap-3 items-start" data-testid="ask-msg-skeleton">
 <div className="shrink-0 h-7 w-7 rounded-full bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center">
 <Loader2 size={13} className="text-white animate-spin" />
 </div>
 <div className="flex-1 pt-1 space-y-2">
 <div className="h-3 bg-zinc-200 rounded animate-pulse w-[80%]" />
 <div className="h-3 bg-zinc-200 rounded animate-pulse w-[60%]" />
 <div className="h-3 bg-zinc-200 rounded animate-pulse w-[40%]" />
 </div>
 </div>
 );
}

/* --------------------------- Main sheet component -------------------------- */
function AskGymAxisSheet({ onClose }) {
 const [session, setSession] = useState(null);
 const [messages, setMessages] = useState([]);
 const [input, setInput] = useState('');
 const [sending, setSending] = useState(false);
 const [confirmDialog, setConfirmDialog] = useState({ open: false, action: null });
 const bottomRef = useRef(null);
 const ctx = useMemo(() => resolveEntityFromDOM(), []);
 const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
 const hdr = useMemo(() => ({ headers: { Authorization: `Bearer ${token}` } }), [token]);

 // Open session on mount
 useEffect(() => {
 axios.post(`${API}/api/support/session`, ctx, hdr)
 .then(r => setSession(r.data))
 .catch(() => notify.error('Could not start support session'));
 }, [ctx, hdr]);

 // Scroll-to-bottom on new messages
 useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, sending]);

 const sendMessage = async (text) => {
 const trimmed = text.trim();
 if (!trimmed || sending) return;
 setMessages(m => [...m, { role: 'user', text: trimmed }]);
 setInput('');
 setSending(true);
 try {
 const body = { ...ctx, message: trimmed, session_id: session?.session_id };
 const res = await axios.post(`${API}/api/support/ask`, body, hdr);
 setMessages(m => [...m, { role: 'assistant', ...res.data }]);
 } catch (e) {
 const detail = e.response?.data?.detail || 'AI temporarily unavailable';
 setMessages(m => [...m, {
 role: 'assistant',
 text: detail + '. Please try again in a moment.',
 needs_human: true,
 suggested_actions: [],
 }]);
 } finally {
 setSending(false);
 }
 };

 const handleAction = (action) => {
 // Confirmable (mutating) actions open the confirm dialog first
 if (CONFIRMABLE_TOOLS.has(action.action)) {
 setConfirmDialog({ open: true, action });
 return;
 }
 if (action.action === 'open_equipment') { window.location.href = '/pulse?tab=equipment'; return; }
 if (action.action === 'open_fault') { window.location.href = '/pulse?tab=faults'; return; }
 if (action.action === 'open_documents') { window.location.href = '/pulse?tab=documents'; return; }
 if (action.action === 'upgrade_plan') { window.location.href = '/pulse?tab=settings&upgrade=1'; return; }
 if (action.action === 'open_warranty') { window.location.href = '/pulse?tab=equipment&view=warranty'; return; }
 if (action.action === 'book_engineer') { window.location.href = '/pulse?tab=faults&book=1'; return; }
 if (action.action === 'escalate_human') { handleEscalate(action.reason); return; }
 notify.info(`Action "${action.action}" — coming soon`);
 };

 const handleEscalate = async (reason) => {
 if (!session?.session_id) return;
 const lastUserMsg = [...messages].reverse().find(m => m.role === 'user')?.text || '';
 try {
 const res = await axios.post(`${API}/api/support/escalate`, {
 session_id: session.session_id,
 reason: reason || 'User requested human support',
 last_message: lastUserMsg,
 }, hdr);
 const { case_ref, platform_name, email_sent } = res.data;
 notify.success(`Case ${case_ref} opened · ${email_sent ? `${platform_name} support has been emailed` : 'saved for support team'}`);
 setMessages(m => [...m, {
 role: 'assistant',
 text: `A human from ${platform_name} support is on it. Your reference is ${case_ref}. They'll reply to ${res.data.recipient ? 'your email' : 'you soon'}.`,
 _is_tool_outcome: true,
 suggested_actions: [],
 }]);
 } catch (e) {
 notifyApiError(notify, e, 'Could not open a support case');
 }
 };

 const submitFeedback = async (turnIndex, { rating, comment }) => {
 if (!session?.session_id) return;
 try {
 await axios.post(`${API}/api/support/feedback`, {
 session_id: session.session_id,
 turn_id: `turn-${turnIndex}`,
 rating, comment: comment || null,
 }, hdr);
 setMessages(m => m.map((msg, i) => i === turnIndex ? { ...msg, _csat_rated: rating } : msg));
 } catch {
 notify.error('Could not record feedback');
 }
 };

 const handleConfirmed = (result) => {
 setConfirmDialog({ open: false, action: null });
 // Add a "tool executed" bubble to the conversation
 setMessages(m => [...m, {
 role: 'assistant',
 text: result.message || 'Done.',
 suggested_actions: result.deep_link ? [{
 action: 'navigate_deep_link',
 label: 'View it',
 _deep_link: result.deep_link,
 }] : [],
 _is_tool_outcome: true,
 }]);
 };

 return (
 <>
 <div
 className="fixed inset-0 bg-black/30 backdrop-blur-sm z-[110] animate-in fade-in duration-200"
 onClick={onClose}
 data-testid="ask-sheet-backdrop"
 />
 <aside
 className="fixed top-0 right-0 h-full w-full sm:w-[420px] md:w-[480px] z-[111] bg-white shadow-2xl border-l border-zinc-200 flex flex-col animate-in slide-in-from-right duration-300"
 data-theme="light"
 data-testid="ask-sheet"
 >
 {/* Header */}
 <header className="p-4 border-b border-zinc-200 flex items-start gap-3">
 <div className="h-9 w-9 rounded-lg bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center shrink-0">
 <Sparkles size={18} className="text-white" />
 </div>
 <div className="flex-1 min-w-0">
 <h2 className="font-bold text-zinc-900" data-testid="ask-title">
 Ask {session?.assistant_name || 'Support'}
 </h2>
 <p className="text-[11px] text-zinc-500 truncate" data-testid="ask-context-pill">
 {session?.pill || 'Loading context…'}
 {session?.plan_tier === 'lite' && (
 <span className="ml-2 text-amber-700 font-medium">· Lite plan</span>
 )}
 </p>
 </div>
 <button onClick={onClose} className="text-zinc-400 hover:text-zinc-900 transition-colors shrink-0"
 data-testid="ask-close-btn" aria-label="Close">
 <X size={18} />
 </button>
 </header>

 {/* Starter chips */}
 {messages.length === 0 && session && (
 <div className="p-4 border-b border-zinc-100 bg-gradient-to-br from-violet-50/60 to-blue-50/60">
 <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500 mb-2">
 Suggested for you
 </p>
 <div className="space-y-2">
 {(session.suggested_intents || []).map((intent, i) => (
 <button
 key={i}
 type="button"
 onClick={() => sendMessage(intent.label)}
 className="w-full text-left text-sm text-zinc-800 bg-white hover:bg-[var(--color-brand-blue)] hover:text-white border border-zinc-200 rounded-lg px-3 py-2 transition-colors"
 data-testid={`ask-intent-${i}`}
 >
 {intent.label}
 </button>
 ))}
 </div>
 </div>
 )}

 {/* Conversation */}
 <div className="flex-1 overflow-y-auto p-4 space-y-5">
 {messages.length === 0 && !session && (
 <div className="text-center text-zinc-400 text-sm pt-8">Loading…</div>
 )}
 {messages.map((m, i) =>
 m.role === 'user'
 ? <UserBubble key={i} text={m.text} />
 : <AssistantBubble key={i} msg={m} onAction={handleAction} assistantName={session?.assistant_name || 'Support'}
 onRate={(fb) => submitFeedback(i, fb)} />,
 )}
 {sending && <AssistantSkeleton />}
 <div ref={bottomRef} />
 </div>

 {/* Composer */}
 <form
 onSubmit={(e) => { e.preventDefault(); sendMessage(input); }}
 className="p-3 border-t border-zinc-200 bg-zinc-50/50"
 >
 <div className="flex items-end gap-2">
 <textarea
 value={input}
 onChange={(e) => setInput(e.target.value)}
 onKeyDown={(e) => {
 if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(input); }
 }}
 placeholder="Ask about your equipment, faults, or the platform…"
 rows={1}
 className="flex-1 resize-none text-sm bg-white border border-zinc-300 rounded-lg px-3 py-2 min-h-[38px] max-h-[120px] focus:outline-none focus:ring-2 focus:ring-[rgb(var(--rgb-brand-blue)/0.3)] focus:border-[var(--color-brand-blue)] text-zinc-900 placeholder:text-zinc-400"
 data-testid="ask-input"
 disabled={sending}
 />
 <Button
 type="submit"
 size="icon"
 disabled={!input.trim() || sending}
 className="bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white h-[38px] w-[38px]"
 data-testid="ask-send-btn"
 aria-label="Send"
 >
 {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
 </Button>
 </div>
 <p className="text-[10px] text-zinc-400 mt-2 flex items-center gap-1">
 <Check size={10} /> Only your org's data · Answers are AI-assisted — verify before acting
 </p>
 </form>
 </aside>
 <ToolConfirmDialog
 open={confirmDialog.open}
 action={confirmDialog.action}
 apiHdr={hdr}
 sessionId={session?.session_id}
 onClose={() => setConfirmDialog({ open: false, action: null })}
 onConfirmed={handleConfirmed}
 />
 </>
 );
}

/* ----------------------- Floating orb (entry point) ----------------------- */
export default function AskGymAxis() {
 const [open, setOpen] = useState(false);

 // Keyboard shortcut: Ctrl+/ or Cmd+/
 useEffect(() => {
 const handler = (e) => {
 if ((e.ctrlKey || e.metaKey) && e.key === '/') { e.preventDefault(); setOpen(v => !v); }
 if (e.key === 'Escape' && open) setOpen(false);
 };
 window.addEventListener('keydown', handler);
 return () => window.removeEventListener('keydown', handler);
 }, [open]);

 return (
 <>
 <button
 type="button"
 onClick={() => setOpen(true)}
 className="fixed bottom-20 right-5 md:bottom-5 md:right-5 z-50 h-14 w-14 rounded-full bg-gradient-to-br from-violet-500 to-blue-600 shadow-lg hover:shadow-xl hover:scale-105 active:scale-95 transition-all flex items-center justify-center group"
 aria-label="Ask AI support"
 data-testid="ask-orb-btn"
 title="Ask AI support (Ctrl+/)"
 >
 <Sparkles size={22} className="text-white group-hover:rotate-12 transition-transform" />
 <span className="absolute -top-1 -right-1 h-3 w-3 rounded-full bg-emerald-400 border-2 border-white" />
 </button>
 {open && <AskGymAxisSheet onClose={() => setOpen(false)} />}
 </>
 );
}
