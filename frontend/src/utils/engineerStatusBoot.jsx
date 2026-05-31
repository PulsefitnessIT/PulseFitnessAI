/**
 * Iter 220e6 — Outbox status pill + window error reporter.
 *
 * Combined into one tiny module so a single import in
 * EngineerHomeV2 wires up both observability gaps from the
 * release-readiness audit:
 *   • #2 — visible "X items queued offline" badge
 *   • #4 — global window.onerror / unhandledrejection POSTed to
 *          /client-errors so silent crashes surface in master-admin
 *
 * Both are lazy and side-effect free until first import on the
 * Engineer App entry route.
 */
import { useEffect, useState } from 'react';
import { onOutboxChange, outboxStatus, drainOutbox } from './engineerOutbox';
import { CloudOff, RefreshCw, CheckCircle } from 'lucide-react';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';

// ── Window error reporter (#4) ───────────────────────────────
//
// Guarded so we only register handlers once even if the module is
// re-imported on hot-reload.
let _installedReporters = false;
export function installEngineerErrorReporters() {
  if (_installedReporters || typeof window === 'undefined') return;
  _installedReporters = true;

  const report = (kind, payload) => {
    try {
      const auth = localStorage.getItem('token') || '';
      axios.post(`${API}/client-errors`, {
        kind, ...payload,
        path: window.location.pathname,
        user_agent: navigator.userAgent,
        surface: 'engineer_app',
      }, auth ? { headers: { Authorization: `Bearer ${auth}` } } : {}).catch(() => {});
    } catch (_) { /* swallow */ }
  };

  window.addEventListener('error', (ev) => {
    report('window_error', {
      message: String(ev?.message || ''),
      source: String(ev?.filename || ''),
      lineno: ev?.lineno, colno: ev?.colno,
      stack: String(ev?.error?.stack || ''),
    });
  });

  window.addEventListener('unhandledrejection', (ev) => {
    const reason = ev?.reason;
    report('unhandled_promise', {
      message: String(reason?.message || reason || ''),
      stack: String(reason?.stack || ''),
    });
  });
}

// ── Outbox pill (#2) ─────────────────────────────────────────
export function OutboxStatusPill({ className = '' }) {
  const [state, setState] = useState({ pending: 0, online: true });
  const [draining, setDraining] = useState(false);

  useEffect(() => {
    let alive = true;
    const refresh = async () => {
      const s = await outboxStatus();
      if (alive) setState(s);
    };
    refresh();
    const off = onOutboxChange(refresh);
    const onOnline = () => refresh();
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOnline);
    return () => {
      alive = false;
      off();
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOnline);
    };
  }, []);

  const sync = async () => {
    setDraining(true);
    try { await drainOutbox(); } finally { setDraining(false); }
  };

  if (state.pending === 0 && state.online) return null; // nothing to show
  const tone = !state.online
    ? { bg: 'var(--color-danger)15', fg: 'var(--color-danger)', label: 'Offline' }
    : state.pending > 0
      ? { bg: 'var(--color-accent-amber)15', fg: 'var(--color-accent-amber)', label: `${state.pending} queued` }
      : { bg: 'var(--color-success-alt)15', fg: 'var(--color-success-alt)', label: 'Synced' };
  return (
    <button onClick={sync} disabled={draining}
            data-testid="outbox-status-pill"
            data-pending={state.pending}
            data-online={state.online ? 'yes' : 'no'}
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${className}`}
            style={{ background: tone.bg, color: tone.fg }}>
      {!state.online ? <CloudOff size={10} /> : state.pending > 0 ? <RefreshCw size={10} className={draining ? 'animate-spin' : ''} /> : <CheckCircle size={10} />}
      {tone.label}
    </button>
  );
}
OutboxStatusPill.displayName = 'OutboxStatusPill';
