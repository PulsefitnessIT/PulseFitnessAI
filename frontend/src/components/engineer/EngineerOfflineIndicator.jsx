/**
 * EngineerOfflineIndicator — iter 216h143 (Phase 4 / Slice 3).
 *
 * Floating pill that surfaces:
 *   • offline state (red — "Offline · n queued")
 *   • online with pending ops (amber — "Syncing n…")
 *   • online + empty (hidden)
 *
 * Tapping the pill opens the engineer sync panel for a detailed list
 * with manual "Sync now" + per-op error display.
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { WifiOff, RefreshCw, CheckCircle2 } from 'lucide-react';
import { useEngineerOfflineQueue, engineerFlushQueue } from '@/utils/engineerOfflineQueue';

export default function EngineerOfflineIndicator() {
  const navigate = useNavigate();
  const { online, pending } = useEngineerOfflineQueue();

  if (online && pending === 0) return null;

  const onClick = (e) => {
    e.preventDefault();
    if (online && pending > 0) {
      engineerFlushQueue();
    } else {
      navigate('/svc/engineer/sync');
    }
  };

  if (!online) {
    return (
      <button
        type="button"
        onClick={onClick}
        className="fixed bottom-20 left-4 z-30 flex items-center gap-2 bg-red-600 hover:bg-red-700 text-white text-xs font-bold px-3 py-2 rounded-full shadow-lg"
        data-testid="offline-indicator-offline"
        title="Offline — tap to open sync panel"
      >
        <WifiOff size={14} /> Offline
        {pending > 0 ? <span className="bg-white/25 rounded-full px-1.5">{pending}</span> : null}
      </button>
    );
  }
  // Online with pending → amber syncing pill
  return (
    <button
      type="button"
      onClick={onClick}
      className="fixed bottom-20 left-4 z-30 flex items-center gap-2 bg-amber-500 hover:bg-amber-600 text-white text-xs font-bold px-3 py-2 rounded-full shadow-lg"
      data-testid="offline-indicator-syncing"
      title="Tap to sync now"
    >
      <RefreshCw size={14} className="animate-spin" /> Syncing {pending}
    </button>
  );
}

export const QueueCountBadge = () => {
  const { pending } = useEngineerOfflineQueue();
  if (!pending) return null;
  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-700"
      data-testid="queue-count-badge"
    >
      {pending} pending
    </span>
  );
};

export const AllSyncedPill = () => {
  const { online, pending } = useEngineerOfflineQueue();
  if (!online || pending > 0) return null;
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-700">
      <CheckCircle2 size={10} /> All synced
    </span>
  );
};
