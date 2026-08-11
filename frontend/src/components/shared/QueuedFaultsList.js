import { useCallback, useEffect, useRef, useState } from 'react';
import { CloudOff, CloudUpload, Loader2, Clock } from 'lucide-react';
import { listPending, flushQueue, readCachedSnapshot } from '@/utils/offlineFaultQueue';
import { notify } from '@/components/notifications';

const API = (process.env.REACT_APP_BACKEND_URL || '') + '/api';

/**
 * Surfaces faults that were logged with no signal (queued in IndexedDB by
 * the MOD Fault Wizard) so gym-floor staff can SEE they were captured and
 * will sync — even though they aren't on the server yet. Auto-refreshes,
 * clears itself once everything syncs, and calls onSynced() so the parent
 * can reload the live list.
 */
export default function QueuedFaultsList({ onSynced }) {
  const [items, setItems] = useState([]);
  const [online, setOnline] = useState(typeof navigator !== 'undefined' ? navigator.onLine : true);
  const [flushing, setFlushing] = useState(false);
  const prevCount = useRef(0);

  const refresh = useCallback(async () => {
    const list = await listPending();
    setItems(list);
    if (prevCount.current > 0 && list.length === 0) onSynced?.();
    prevCount.current = list.length;
  }, [onSynced]);

  useEffect(() => {
    refresh();
    const onUp = () => { setOnline(true); refresh(); };
    const onDown = () => setOnline(false);
    window.addEventListener('online', onUp);
    window.addEventListener('offline', onDown);
    const iv = setInterval(refresh, 5000);
    return () => {
      window.removeEventListener('online', onUp);
      window.removeEventListener('offline', onDown);
      clearInterval(iv);
    };
  }, [refresh]);

  const syncNow = async () => {
    if (!online || flushing || items.length === 0) return;
    setFlushing(true);
    try {
      const r = await flushQueue(API);
      await refresh();
      if (r.synced > 0) notify.success(`${r.synced} fault${r.synced > 1 ? 's' : ''} synced`);
      if (r.failed > 0) notify.error(`${r.failed} still pending — check your connection`);
    } finally {
      setFlushing(false);
    }
  };

  if (items.length === 0) return null;

  const snap = readCachedSnapshot();
  const nameFor = (id) => {
    const eq = (snap.equipment || []).find((e) => e.id === id);
    return eq?.name || eq?.serial_number || 'Machine';
  };

  return (
    <div className="rounded-xl border border-amber-500/40 bg-amber-500/[0.08] p-4 space-y-3" data-testid="queued-faults-banner">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 min-w-0">
          {online
            ? <CloudUpload size={16} className={`text-amber-500 dark:text-amber-300 shrink-0 ${flushing ? 'animate-pulse' : ''}`} />
            : <CloudOff size={16} className="text-amber-500 dark:text-amber-300 shrink-0" />}
          <div className="min-w-0">
            <p className="text-sm font-extrabold text-amber-700 dark:text-amber-200" data-testid="queued-faults-title">
              {items.length} fault{items.length > 1 ? 's' : ''} queued — will sync
            </p>
            <p className="text-xs text-amber-700/80 dark:text-amber-200/70">
              {online
                ? 'Saved on this device — uploading automatically.'
                : "You're offline. These are safe and will upload the moment you reconnect."}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={syncNow}
          disabled={!online || flushing}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold border border-amber-500/50 text-amber-700 dark:text-amber-200 disabled:opacity-50 hover:bg-amber-500/10 transition-colors"
          data-testid="queued-faults-sync"
          title={online ? 'Retry sync now' : 'Reconnect to sync'}
        >
          {flushing ? <Loader2 size={13} className="animate-spin" /> : <CloudUpload size={13} />}
          {flushing ? 'Syncing…' : 'Sync now'}
        </button>
      </div>
      <div className="space-y-1.5">
        {items.map((it) => (
          <div
            key={it.id}
            className="flex items-center justify-between gap-2 rounded-lg bg-white/50 dark:bg-black/20 border border-amber-500/20 px-3 py-2"
            data-testid={`queued-fault-${it.id}`}
          >
            <div className="min-w-0">
              <p className="text-sm font-bold text-amber-900 dark:text-amber-100 truncate">{nameFor(it.form?.equipment_id)}</p>
              <p className="text-xs text-amber-800/70 dark:text-amber-200/60 truncate">{it.form?.description || it.form?.fault_type || 'Fault report'}</p>
            </div>
            <span className="inline-flex items-center gap-1 text-[10px] font-extrabold uppercase tracking-wider px-2 py-1 rounded-full bg-amber-500/20 text-amber-700 dark:text-amber-200 shrink-0">
              <Clock size={10} /> Queued
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
