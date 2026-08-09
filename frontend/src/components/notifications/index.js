/**
 * Pulse Fitness Notification System — visual, in-context, intuitive.
 *
 * Replaces the previous "sprinkle toast.X everywhere" pattern with a tiered
 * approach that matches the intent of each message:
 *
 * ┌─────────────────────┬────────────────────────────────────────────────┐
 * │ Intent │ Surface │
 * ├─────────────────────┼────────────────────────────────────────────────┤
 * │ Critical / destructive action (delete, cancel) │ <ConfirmDialog />
 * │ Form-scoped success / error confirmation │ useInlineBanner()
 * │ Page-wide success / error (no host form) │ notify.success / .error
 * │ Background info (heads-up / hint) │ notify.info
 * │ Progress (long-running) │ <InlineProgress />
 * │ Micro confirmation (copy-to-clipboard) │ notify.micro()
 * └─────────────────────┴────────────────────────────────────────────────┘
 *
 * USAGE (inline, form-scoped):
 * const { banner, show, clear } = useInlineBanner();
 * show({ tone: 'success', title: 'Uploaded', detail: 'Saved to General tab.' });
 * return <><div>{banner}</div> ... </>;
 *
 * USAGE (global banner — from anywhere, no host needed):
 * import { notify } from '@/components/notifications';
 * notify.error('Something went wrong'); // short form
 * notify.success('Saved', 'Your changes are live'); // with detail
 * notify.info('Heads up', 'Remember to review the plan'); // info tone
 * notify.warning('Approaching limit'); // warning tone
 * notify.micro('Link copied'); // micro toast
 *
 * USAGE (confirm dialog):
 * const confirm = useConfirm();
 * const ok = await confirm({ title: 'Delete fault?', tone: 'danger', confirmLabel: 'Delete' });
 * if (ok) doDelete();
 *
 * MOUNT: wrap your app with <ConfirmProvider /> once — it also hosts the
 * global banner stack used by `notify.*`.
 */
import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import {
 CheckCircle2, AlertTriangle, Info, XCircle, X, Loader2,
} from 'lucide-react';
import {
 Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { toast as sonnerToast } from 'sonner';

/* ═══════════════════════════ InlineBanner ═══════════════════════════ */

const TONE_CONFIG = {
 success: { bg: 'bg-emerald-50 dark:bg-emerald-950/40', border: 'border-emerald-300 dark:border-emerald-700', text: 'text-emerald-900 dark:text-emerald-200', icon: CheckCircle2, iconColor: 'text-emerald-600 dark:text-emerald-400' },
 error: { bg: 'bg-red-50 dark:bg-red-950/40', border: 'border-red-300 dark:border-red-700', text: 'text-red-900 dark:text-red-200', icon: XCircle, iconColor: 'text-red-600 dark:text-red-400' },
 warning: { bg: 'bg-amber-50 dark:bg-amber-950/40', border: 'border-amber-300 dark:border-amber-700', text: 'text-amber-900 dark:text-amber-200', icon: AlertTriangle, iconColor: 'text-amber-600 dark:text-amber-400' },
 info: { bg: 'bg-blue-50 dark:bg-blue-950/40', border: 'border-blue-300 dark:border-blue-700', text: 'text-blue-900 dark:text-blue-200', icon: Info, iconColor: 'text-blue-600 dark:text-blue-400' },
};

export function InlineBanner({ tone = 'info', title, detail, action, onDismiss, compact = false, className = '' }) {
 const cfg = TONE_CONFIG[tone] || TONE_CONFIG.info;
 const Icon = cfg.icon;
 // Defensive: never render a raw object as a child — coerce to string so
 // a stray `notify.success(msg, { duration: ... })` call can't crash the app.
 const safeTitle = (title != null && typeof title !== 'string' && !React.isValidElement(title))
 ? String(title?.message || title?.title || '') : title;
 const safeDetail = (detail != null && typeof detail !== 'string' && !React.isValidElement(detail))
 ? null : detail;
 return (
 <div
 role={tone === 'error' ? 'alert' : 'status'}
 className={`border rounded-md ${cfg.bg} ${cfg.border} ${cfg.text} flex items-start gap-2.5 ${compact ? 'p-2' : 'p-3'} ${className}`}
 data-testid={`inline-banner-${tone}`}
 >
 <Icon size={compact ? 14 : 16} className={`${cfg.iconColor} flex-shrink-0 mt-0.5`} />
 <div className="flex-1 min-w-0">
 {safeTitle && <p className={`text-sm font-medium ${compact ? 'leading-tight' : ''}`}>{safeTitle}</p>}
 {safeDetail && <p className={`text-xs opacity-80 ${safeTitle ? 'mt-0.5' : ''}`}>{safeDetail}</p>}
 {action && (
 <button
 onClick={action.onClick}
 className="text-xs font-semibold underline underline-offset-2 mt-1.5 hover:opacity-80"
 data-testid={`inline-banner-action-${tone}`}
 >
 {action.label} →
 </button>
 )}
 </div>
 {onDismiss && (
 <button onClick={onDismiss} className="opacity-60 hover:opacity-100" aria-label="Dismiss" data-testid={`inline-banner-dismiss-${tone}`}>
 <X size={14} />
 </button>
 )}
 </div>
 );
}

/** Hook: `const { banner, show, clear } = useInlineBanner();`
 * Auto-dismisses success after 4s, errors persist until `clear()`. */
export function useInlineBanner(options = {}) {
 const [state, setState] = useState(null);
 const show = useCallback((b) => {
 setState(b);
 if (b.tone === 'success' && options.autoDismiss !== false) {
 setTimeout(() => setState((cur) => (cur === b ? null : cur)), options.autoDismissMs || 4000);
 }
 }, [options.autoDismiss, options.autoDismissMs]);
 const clear = useCallback(() => setState(null), []);
 const banner = state ? (
 <InlineBanner {...state} onDismiss={state.onDismiss === false ? undefined : clear} />
 ) : null;
 return { banner, show, clear };
}

/* ═══════════════════════════ InlineProgress ═══════════════════════════ */

export function InlineProgress({ title, percent, detail, className = '' }) {
 return (
 <div className={`border border-blue-200 bg-blue-50/60 rounded-md p-3 ${className}`} data-testid="inline-progress">
 <div className="flex items-center gap-2 mb-1.5">
 <Loader2 size={14} className="text-blue-600 animate-spin" />
 <p className="text-sm font-medium text-blue-900 flex-1">{title}</p>
 {percent != null && <span className="text-xs font-semibold text-blue-700">{Math.round(percent)}%</span>}
 </div>
 {detail && <p className="text-xs text-blue-800/70 mb-1.5">{detail}</p>}
 {percent != null && (
 <div className="h-1.5 w-full bg-blue-100 rounded-full overflow-hidden">
 <div className="h-full bg-blue-500 transition-all" style={{ width: `${Math.max(0, Math.min(100, percent))}%` }} />
 </div>
 )}
 </div>
 );
}

/* ═══════════════════════════ Global Banner Host (notify.*) ═══════════════════════════ */

let _globalPush = null;
let _globalDismiss = null;

function GlobalBannerHost() {
 const [items, setItems] = useState([]);
 const counter = useRef(0);

 const push = useCallback((entry) => {
 const id = ++counter.current;
 const ttl = entry.ttl != null ? entry.ttl : (entry.tone === 'error' || entry.tone === 'warning' ? 6500 : 3500);
 setItems((prev) => [...prev.slice(-3), { ...entry, id }]); // keep max 4 stacked
 if (ttl > 0) {
 setTimeout(() => setItems((p) => p.filter((x) => x.id !== id)), ttl);
 }
 return id;
 }, []);

 const dismiss = useCallback((id) => setItems((p) => p.filter((x) => x.id !== id)), []);

 useEffect(() => {
 _globalPush = push;
 _globalDismiss = dismiss;
 return () => { _globalPush = null; _globalDismiss = null; };
 }, [push, dismiss]);

 if (items.length === 0) return null;
 return (
 <div
 className="fixed top-6 left-1/2 -translate-x-1/2 z-[10000] flex flex-col gap-2 w-[calc(100vw-2rem)] max-w-md pointer-events-none items-center"
 data-testid="global-banner-host"
 >
 {items.map((it) => (
 <div key={it.id} className="pointer-events-auto shadow-2xl animate-in fade-in slide-in-from-top-2 duration-200 w-full">
 <InlineBanner
 tone={it.tone}
 title={it.title}
 detail={it.detail}
                                                                action={it.action}
 onDismiss={() => dismiss(it.id)}
 />
 </div>
 ))}
 </div>
 );
}

/* ═══════════════════════════ ConfirmDialog ═══════════════════════════ */

const ConfirmContext = createContext(null);

export function ConfirmProvider({ children }) {
 const [state, setState] = useState(null);
 const confirm = useCallback((opts) => new Promise((resolve) => {
 setState({ ...opts, resolve });
 }), []);
 const close = (result) => { if (state) { state.resolve(result); setState(null); } };
 return (
 <ConfirmContext.Provider value={confirm}>
 {children}
 <GlobalBannerHost />
 <Dialog open={!!state} onOpenChange={(o) => !o && close(false)}>
 <DialogContent className="max-w-md sm:rounded-xl" data-testid="confirm-dialog" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}>
 {state && (
 <>
 <DialogHeader>
 <DialogTitle className="flex items-center gap-2" style={{ color: 'var(--theme-text)' }}>
 {state.tone === 'danger' && <AlertTriangle size={18} className="text-red-500" />}
 {state.tone === 'warning' && <AlertTriangle size={18} className="text-amber-500" />}
 {state.title}
 </DialogTitle>
 </DialogHeader>
 {state.detail && <p className="text-sm leading-relaxed" style={{ color: 'var(--theme-text-muted)' }}>{state.detail}</p>}
 <DialogFooter className="gap-2">
 <Button variant="outline" onClick={() => close(false)} data-testid="confirm-cancel" style={{ borderColor: 'var(--theme-border)', background: 'transparent', color: 'var(--theme-text)' }}>
 {state.cancelLabel || 'Cancel'}
 </Button>
 <Button
 className={state.tone === 'danger' ? 'bg-red-600 hover:bg-red-700 text-white' : 'bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white'}
 onClick={() => close(true)}
 data-testid="confirm-ok"
 >
 {state.confirmLabel || 'Confirm'}
 </Button>
 </DialogFooter>
 </>
 )}
 </DialogContent>
 </Dialog>
 </ConfirmContext.Provider>
 );
}

export function useConfirm() {
 const ctx = useContext(ConfirmContext);
 if (!ctx) throw new Error('useConfirm must be used inside <ConfirmProvider />');
 return ctx;
}

/* ═══════════════════════════ notify API ═══════════════════════════ */

/** Fire-and-forget error telemetry. Never blocks the UI. */
function _logErrorTelemetry(title, detail) {
 try {
 const apiBase = (typeof process !== 'undefined' && process.env && process.env.REACT_APP_BACKEND_URL) || '';
 if (!apiBase) return;
 const token = typeof localStorage !== 'undefined' ? localStorage.getItem('token') : null;
 const path = typeof window !== 'undefined' ? window.location.pathname : null;
 const headers = { 'Content-Type': 'application/json' };
 if (token) headers.Authorization = `Bearer ${token}`;
 // Use keepalive so the request survives a navigation/unload.
 fetch(`${apiBase}/api/ui-errors`, {
 method: 'POST',
 headers,
 keepalive: true,
 body: JSON.stringify({
 title: String(title || '').slice(0, 300),
 detail: detail ? String(detail).slice(0, 1000) : undefined,
 tone: 'error',
 path,
 }),
 }).catch(() => { /* swallow — telemetry is non-critical */ });
 } catch {
 /* swallow */
 }
}

/**
 * Global banner API — works from anywhere (hooks, async handlers, plain JS).
 * notify.success('Saved') // title only
 * notify.success('Saved', 'Your changes are live') // title + detail
 * notify.error(err.message)
 * notify.info('Heads up', 'Remember to review')
 *
 * Falls back to a sonner toast if the <ConfirmProvider /> host isn't mounted
 * yet (e.g. during the very first render).
 */
function _push(tone, title, detail, options = {}) {
 // Be tolerant of the (title, options) call form — many callers pass the
 // options object as the 2nd argument (e.g. `notify.success('Saved',
 // { duration: 7000 })`). Without this guard the object would be set as
 // `detail` and React would crash when rendering it as a child.
 if (detail !== null && typeof detail === 'object' && !Array.isArray(detail)
 && !React.isValidElement(detail) && typeof title !== 'object') {
 options = { ...detail, ...options };
 detail = undefined;
 }
 const msg = typeof title === 'object' && title !== null
 ? { ...title }
 : { title, detail };
 msg.tone = tone;
 // Map common option aliases to the GlobalBannerHost contract.
 if (options.duration != null && options.ttl == null) {
 options.ttl = options.duration;
 }
 // Final defensive guard: never let a non-string detail reach the renderer.
 if (msg.detail != null && typeof msg.detail !== 'string' && !React.isValidElement(msg.detail)) {
 msg.detail = undefined;
 }
 // Fire telemetry for errors — non-blocking.
 if (tone === 'error' && options.silent !== true) {
 _logErrorTelemetry(msg.title, msg.detail);
 }
 if (!_globalPush) {
 // Host not ready — fall back to sonner
 const fn = tone === 'error' ? sonnerToast.error : tone === 'success' ? sonnerToast.success : sonnerToast;
 fn(msg.title || (tone === 'error' ? 'Something went wrong' : ''));
 return null;
 }
 return _globalPush({ ...msg, ...options });
}

export const notify = {
 success: (title, detail, opts) => _push('success', title, detail, opts),
 error: (title, detail, opts) => _push('error', title, detail, opts),
 warning: (title, detail, opts) => _push('warning', title, detail, opts),
 info: (title, detail, opts) => _push('info', title, detail, opts),
 /** Dismiss a previously-pushed banner by id (returned from notify.success/info/etc.) */
 dismiss: (id) => { if (id != null && _globalDismiss) _globalDismiss(id); },
 /** Tiny one-line confirmations only — e.g. "Link copied". */
 micro: (msg) => sonnerToast(msg, { duration: 1400, position: 'top-center', className: '!min-h-0 !py-1.5 !px-2.5 !text-xs' }),
};

/* ═══════════════════════════ Default export convenience ═══════════════════════════ */

export default {
 InlineBanner,
 InlineProgress,
 useInlineBanner,
 ConfirmProvider,
 useConfirm,
 notify,
};
