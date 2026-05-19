/**
 * OfflineBanner (iter 215d9 → 215da → 216h46)
 *
 * Sticky pill below the Navbar that surfaces two signals:
 *   1. Connectivity state ("offline" / brief "back online") — 215d9.
 *   2. Offline mutation queue depth + a manual "Sync now" button — 215da.
 *
 * When the browser reports `navigator.onLine === false` we show
 * "You're offline — showing cached data." Optionally with an inline
 * pill showing how many edits are queued for sync.
 *
 * Iter 216h46 — auth-gated. The banner now ONLY renders when a user
 * is signed in (any scope — main/crm/member). Lee's iter 216h42 bug
 * reported the offline banner showing "on every screen even when I
 * log out" — even after the false-positive fix, the banner persisted
 * on public/marketing/login surfaces where it's useless and confusing.
 * Gating on `useUnifiedAuth().tokens` makes the banner an
 * authenticated-only concern, matching the rest of the operator
 * chrome (Navbar, GlobalCommandPalette, etc).
 */
import { useEffect, useState } from 'react';
import { WifiOff, CheckCircle2, RefreshCw, CloudOff } from 'lucide-react';
import useOnlineStatus from '../../hooks/useOnlineStatus';
import useOfflineQueue from '../../hooks/useOfflineQueue';
import { useUnifiedAuth } from './UnifiedAuthProvider';

export default function OfflineBanner() {
  const { online } = useOnlineStatus();
  const { count, flushing, flush } = useOfflineQueue();
  const { tokens } = useUnifiedAuth();
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
  const signedIn = !!(tokens.main || tokens.crm || tokens.member);

  // Iter 216h46 — public surfaces (marketing site, /pulse landing,
  // /crm login, member-app login) should NEVER show the offline
  // banner, regardless of network state. Those surfaces have no
  // cached data to fall back to, and the banner just looks broken
  // on a static page.
  if (!signedIn) return null;
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
