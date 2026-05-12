/**
 * useOnlineStatus — verified online detection (iter 216h42).
 *
 * Original (iter 215d9) trusted `navigator.onLine` directly. That API
 * is notoriously unreliable on Chrome Android — Lee's production
 * device repeatedly showed "You're offline" while genuinely on 5G.
 * Common false-positives:
 *   • Chrome on Android backgrounded then resumed.
 *   • Mobile data-savers / corporate VPNs / split tunnels.
 *   • Service-worker takeover momentarily detached from the network
 *     stack on certain builds.
 *
 * Fix: VERIFY before trusting offline. When `navigator.onLine` flips
 * false (or when we boot in an alleged offline state) we run a tiny
 * `fetch(REACT_APP_BACKEND_URL/api/health, { cache: 'no-store' })`
 * probe with a 4 s timeout. Only after the probe genuinely fails do
 * we surface the offline banner. When `online` flips true via the
 * browser event we trust it instantly (false-positives in that
 * direction are harmless — we just retry network calls).
 *
 * The probe re-runs every 20 s while the offline state is sticky,
 * so if connectivity recovers behind the browser's back the banner
 * dismisses on its own without waiting for a user action.
 *
 *   const { online } = useOnlineStatus();
 *   if (!online) toast.info("You're offline — showing cached data.");
 */
import { useEffect, useRef, useState } from 'react';

const PROBE_TIMEOUT_MS = 4000;
const PROBE_INTERVAL_MS = 20000;

const buildProbeUrl = () => {
  // REACT_APP_BACKEND_URL is the canonical external API base. Fall
  // back to a relative `/api/health` (same origin) if the env var is
  // missing — same-origin probe still works because the service
  // worker proxies it to the FastAPI pod.
  const base = (typeof process !== 'undefined' && process.env && process.env.REACT_APP_BACKEND_URL) || '';
  return `${base}/api/health`;
};

const probe = async () => {
  if (typeof fetch === 'undefined') return false;
  const url = buildProbeUrl();
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
    // Cache-buster query string so any service-worker cache layer is
    // forced to attempt the network — defeating an aggressive SW
    // that would otherwise serve a stale 200 forever.
    const res = await fetch(`${url}?t=${Date.now()}`, {
      method: 'GET',
      cache: 'no-store',
      credentials: 'omit',
      signal: controller.signal,
    });
    clearTimeout(timer);
    return res.ok;
  } catch {
    return false;
  }
};

export default function useOnlineStatus() {
  const [online, setOnline] = useState(
    typeof navigator === 'undefined' ? true : navigator.onLine
  );
  const [lastOfflineAt, setLastOfflineAt] = useState(null);
  const probeTimerRef = useRef(null);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;

    const goOnline = () => setOnline(true);

    // The browser SAYS we're offline — but verify with a real probe
    // before we trust it. Chrome Android lies frequently here.
    const verifyOffline = async () => {
      const reachable = await probe();
      if (reachable) {
        // False alarm — stay online.
        setOnline(true);
      } else {
        setOnline(false);
        setLastOfflineAt(new Date());
      }
    };

    const handleOnline = () => goOnline();
    const handleOffline = () => { verifyOffline(); };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    // On mount, if navigator says we're offline, ALSO probe — covers
    // the page-load-while-offline path (otherwise we'd render the
    // banner immediately based on a possibly-stale flag).
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      verifyOffline();
    }

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  // While we believe we're offline, re-probe every PROBE_INTERVAL_MS
  // so the banner dismisses itself if connectivity has actually
  // recovered behind the browser's back.
  useEffect(() => {
    if (online) {
      if (probeTimerRef.current) { clearInterval(probeTimerRef.current); probeTimerRef.current = null; }
      return undefined;
    }
    probeTimerRef.current = setInterval(async () => {
      const reachable = await probe();
      if (reachable) setOnline(true);
    }, PROBE_INTERVAL_MS);
    return () => { if (probeTimerRef.current) { clearInterval(probeTimerRef.current); probeTimerRef.current = null; } };
  }, [online]);

  return { online, lastOfflineAt };
}
