/**
 * OfflineBanner (iter 215d9 → 215da)
 *
 * Sticky pill below the Navbar that surfaces two signals:
 *   1. Connectivity state ("offline" / brief "back online") — 215d9.
 *   2. Offline mutation queue depth + a manual "Sync now" button — 215da.
 *
 * When the browser reports `navigator.onLine === false` we show
 * "You're offline — showing cached data." Optionally with an inline
 * pill showing how many edits are queued for sync.
 *
 * When online but with a non-empty queue (rare — we auto-drain on
 * reconnect, but this shows briefly while flushing or when a drain
 * has stalled), we show "N edits syncing…" with a retry button.
 */
import React, { useEffect, useState } from 'react';
import { WifiOff, CheckCircle2, RefreshCw, CloudOff } from 'lucide-react';
import useOnlineStatus from '../../hooks/useOnlineStatus';
import useOfflineQueue from '../../hooks/useOfflineQueue';

export default function OfflineBanner() {
  const { online } = useOnlineStatus();
  const { count, flushing, flush } = useOfflineQueue();
  const [showBackOnline, setShowBackOnline] = useState(false);
  const [wasOffline, setWasOffline] = useState(false);

  useEffect(() => {
    if (!online) {
      setWasOffline(true);
      setShowBackOnline(false);
      return;
    }
    if (wasOffline) {
      setShowBackOnline(true);
      const t = setTimeout(() => {
        setShowBackOnline(false);
        setWasOffline(false);
      }, 3000);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [online, wasOffline]);

  const offline = !online;
  const syncing = online && (flushing || count > 0);

  if (!offline && !showBackOnline && !syncing) return null;

  let background = '#1F2937';
  let borderColor = '#374151';
  let testid = 'offline-banner';
  let icon = <WifiOff size={14} />;
  let label = "You're offline — showing the last cached data.";

  if (!offline && showBackOnline) {
    background = '#065F46';
    borderColor = '#047857';
    testid = 'back-online-banner';
    icon = <CheckCircle2 size={14} />;
    label = 'Back online.';
  } else if (!offline && syncing) {
    background = '#1E3A8A';
    borderColor = '#1D4ED8';
    testid = 'sync-banner';
    icon = <RefreshCw size={14} className={flushing ? 'animate-spin' : ''} />;
    label = flushing ? `Syncing ${count} edit${count === 1 ? '' : 's'}…` : `${count} edit${count === 1 ? '' : 's'} waiting to sync`;
  }

  return (
    <div
      className="fixed left-1/2 -translate-x-1/2 z-[95] flex items-center gap-2 px-4 py-2 rounded-full shadow-lg border text-sm font-semibold animate-[slideDown_220ms_ease-out]"
      style={{
        top: 'calc(env(safe-area-inset-top, 0px) + 76px)',
        background,
        color: '#FFFFFF',
        borderColor,
      }}
      role="status"
      aria-live="polite"
      data-testid={testid}
    >
      {icon}
      <span data-testid="offline-banner-label">{label}</span>
      {offline && count > 0 && (
        <span className="ml-1 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-extrabold" style={{ background: '#111827', color: '#FDE68A' }} data-testid="offline-queue-pill">
          <CloudOff size={11} /> {count} pending
        </span>
      )}
      {!offline && count > 0 && !flushing && (
        <button
          type="button"
          onClick={flush}
          className="ml-1 text-[11px] font-extrabold px-2 py-0.5 rounded-full border border-white/40 hover:bg-white/10"
          data-testid="offline-retry-btn"
        >
          Retry
        </button>
      )}
    </div>
  );
}
