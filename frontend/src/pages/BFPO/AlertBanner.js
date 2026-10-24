import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, X, CloudOff, RefreshCw } from 'lucide-react';
import { bfpo, outboxCount, onOutboxChange, flushOutbox, outboxError } from './bfpoApi';

// Red banner for open P1 / safety-critical MOD jobs the user hasn't acknowledged.
export function UrgentAlertBanner({ online, onOpen }) {
  const [alerts, setAlerts] = useState([]);
  const load = useCallback(async () => {
    if (!navigator.onLine) return;
    try { const r = await bfpo.get('/alerts'); setAlerts(r.data.alerts || []); } catch { /* keep last */ }
  }, []);
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, [load, online]);
  const ack = async (id) => {
    setAlerts((a) => a.filter((x) => x.id !== id));
    try { await bfpo.post(`/alerts/${id}/ack`); } catch { /* re-shows next poll */ }
  };
  if (!alerts.length) return null;
  const a = alerts[0];
  return (
    <div className="bg-red-600 text-white" role="alert" data-testid="urgent-alert-banner">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-2.5 flex items-center gap-3 flex-wrap">
        <AlertTriangle className="w-5 h-5 shrink-0 animate-pulse" />
        <p className="text-sm flex-1 min-w-0" data-testid="urgent-alert-text">
          <span className="font-bold">{a.safety_critical ? 'Safety-critical fault' : 'Urgent fault'}</span>
          {' · '}{a.site_name}{' · '}{a.title}
          {alerts.length > 1 && <span className="ml-2 text-red-100">+{alerts.length - 1} more</span>}
        </p>
        <button onClick={() => { onOpen(a.id); ack(a.id); }} className="px-3 py-1.5 rounded-full bg-white text-red-700 text-xs font-bold" data-testid="urgent-alert-open">View job</button>
        <button onClick={() => ack(a.id)} className="p-1.5 rounded-full hover:bg-white/15" aria-label="Acknowledge" data-testid="urgent-alert-ack"><X className="w-4 h-4" /></button>
      </div>
    </div>
  );
}

// Amber strip while offline / while saved updates are waiting to send.
export function OfflineSyncBar({ online }) {
  const [pending, setPending] = useState(outboxCount());
  const [busy, setBusy] = useState(false);
  const [, setTick] = useState(0);
  useEffect(() => onOutboxChange((n) => { setPending(n); setTick((t) => t + 1); }), []);
  if (online && !pending) {
    const msg = outboxError();
    return msg ? <div className="bg-amber-100 text-amber-900 border-b border-amber-200 px-4 py-2 text-sm" data-testid="offline-sync-error">{msg}</div> : null;
  }
  const sync = async () => { setBusy(true); try { await flushOutbox(); } finally { setBusy(false); setPending(outboxCount()); } };
  return (
    <div className="bg-amber-100 text-amber-900 border-b border-amber-200" data-testid="offline-sync-bar">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-2 flex items-center gap-2 text-sm">
        <CloudOff className="w-4 h-4 shrink-0" />
        <span className="flex-1" data-testid="offline-sync-text">
          {online ? `${pending} saved update${pending === 1 ? '' : 's'} waiting to send${outboxError() ? ` — ${outboxError()}` : ''}` : `No signal — you can keep working${pending ? ` · ${pending} update${pending === 1 ? '' : 's'} saved on this phone` : ''}`}
        </span>
        {online && pending > 0 && (
          <button onClick={sync} disabled={busy} className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-amber-600 text-white text-xs font-bold" data-testid="offline-sync-now">
            <RefreshCw className={`w-3.5 h-3.5 ${busy ? 'animate-spin' : ''}`} /> Send now
          </button>
        )}
      </div>
    </div>
  );
}
