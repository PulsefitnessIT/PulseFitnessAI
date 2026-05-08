/**
 * useOnlineStatus — compact hook over `navigator.onLine` + `online/offline` events.
 *
 * Iter 215d9 — companion to the service worker's offline API cache.
 * Exposes two pieces of state:
 *   - `online`: true when the browser reports network connectivity.
 *   - `lastOfflineAt`: Date or null — when we last lost connectivity.
 *
 * Consumers typically just branch on `online`:
 *
 *   const { online } = useOnlineStatus();
 *   if (!online) toast.info('You're offline — showing cached data.');
 */
import { useEffect, useState } from 'react';

export default function useOnlineStatus() {
  const [online, setOnline] = useState(
    typeof navigator === 'undefined' ? true : navigator.onLine
  );
  const [lastOfflineAt, setLastOfflineAt] = useState(null);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const handleOnline = () => setOnline(true);
    const handleOffline = () => {
      setOnline(false);
      setLastOfflineAt(new Date());
    };
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  return { online, lastOfflineAt };
}
