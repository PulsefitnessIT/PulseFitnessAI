/**
 * Offline status pill — shows online/offline state plus pending-sync
 * count for the MOD surfaces. Sits inside the classification banner
 * region so PTIs always see whether their last action made it to the
 * server.
 *
 * Iter 216h117 — P1 #4 (offline-first field mode UX).
 */
import React, { useEffect, useState } from 'react';
import { Wifi, WifiOff, CloudUpload, Check } from 'lucide-react';
import { countPending, flushQueue, installAutoFlush } from '@/utils/offlineFaultQueue';

const API = (process.env.REACT_APP_BACKEND_URL || '') + '/api';

export default function OfflineStatusPill() {
  const [online, setOnline] = useState(typeof navigator !== 'undefined' ? navigator.onLine : true);
  const [pending, setPending] = useState(0);
  const [flushing, setFlushing] = useState(false);
  const [justSynced, setJustSynced] = useState(false);

  useEffect(() => {
    const refresh = async () => setPending(await countPending());
    refresh();
    const onUp = () => setOnline(true);
    const onDown = () => setOnline(false);
    window.addEventListener('online', onUp);
    window.addEventListener('offline', onDown);
    const cleanup = installAutoFlush(API, () => {
      refresh();
      setJustSynced(true);
      setTimeout(() => setJustSynced(false), 2500);
    });
    const interval = setInterval(refresh, 8000);
    return () => {
      window.removeEventListener('online', onUp);
      window.removeEventListener('offline', onDown);
      if (cleanup) cleanup();
      clearInterval(interval);
    };
  }, []);

  const manualFlush = async () => {
    setFlushing(true);
    try {
      await flushQueue(API);
      setPending(await countPending());
      setJustSynced(true);
      setTimeout(() => setJustSynced(false), 2500);
    } finally {
      setFlushing(false);
    }
  };

  if (online && pending === 0 && !justSynced) return null;

  const tone = !online ? 'amber' : (pending > 0 ? 'cyan' : 'emerald');
  const bg = tone === 'amber' ? 'rgba(245,158,11,0.12)' : tone === 'cyan' ? 'rgba(25,205,255,0.12)' : 'rgba(16,185,129,0.12)';
  const fg = tone === 'amber' ? '#f59e0b' : tone === 'cyan' ? '#19CDFF' : '#10b981';

  return (
    <button
      type="button"
      onClick={!online ? undefined : manualFlush}
      disabled={!online || flushing || pending === 0}
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-extrabold uppercase tracking-wider border"
      style={{ background: bg, borderColor: fg, color: fg, cursor: !online || pending === 0 ? 'default' : 'pointer' }}
      data-testid="mod-offline-pill"
      data-status={!online ? 'offline' : (pending > 0 ? 'queued' : 'synced')}
      title={!online
        ? 'You are offline — submissions will queue and sync automatically when you reconnect.'
        : pending > 0
          ? `${pending} item${pending === 1 ? '' : 's'} waiting to sync. Tap to retry now.`
          : 'All caught up.'}
    >
      {!online ? <WifiOff size={11} /> : pending > 0 ? <CloudUpload size={11} className={flushing ? 'animate-pulse' : ''} /> : <Check size={11} />}
      {!online
        ? `Offline · ${pending} queued`
        : pending > 0
          ? `${pending} pending sync${flushing ? '…' : ''}`
          : 'Synced'}
      {online && pending === 0 && <Wifi size={11} aria-hidden="true" style={{ display: 'none' }} />}
    </button>
  );
}
