/**
 * useOfflineQueue (iter 215da) — React hook exposing the pending
 * mutation count + a `flush()` method that manually triggers a drain.
 *
 * Keeps the UI live by subscribing to the queue's pub/sub notifier and
 * re-reading `listPending()` on each change.
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import useOnlineStatus from './useOnlineStatus';
import { drainQueue, listPending, subscribe } from '../utils/offlineQueue';

export default function useOfflineQueue() {
  const [pending, setPending] = useState([]);
  const [flushing, setFlushing] = useState(false);
  const { online } = useOnlineStatus();
  const refreshRef = useRef(null);

  const refresh = useCallback(async () => {
    const items = await listPending();
    setPending(items);
  }, []);
  refreshRef.current = refresh;

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => subscribe(() => refreshRef.current && refreshRef.current()), []);

  const flush = useCallback(async () => {
    if (flushing) return { sent: 0, failed: 0 };
    setFlushing(true);
    try {
      const result = await drainQueue();
      await refresh();
      return result;
    } finally {
      setFlushing(false);
    }
  }, [flushing, refresh]);

  // Iter 215da — auto-drain on reconnect. Single effect, fires when
  // the browser flips from offline → online AND there is pending work.
  const lastOnline = useRef(online);
  useEffect(() => {
    if (!lastOnline.current && online && pending.length > 0) {
      flush();
    }
    lastOnline.current = online;
  }, [online, pending.length, flush]);

  return { pending, count: pending.length, flushing, flush, online };
}
