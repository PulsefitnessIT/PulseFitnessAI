/**
 * useEngineerAttention — iter 220j.
 *
 * Polls /api/svc/engineer/attention so the hamburger menu can pulse
 * amber/red when something needs the engineer's eye (compliance
 * expiring, subscription past_due, missing Stripe Connect, etc).
 *
 * The Engineer Home polls every 90 s; the drawer re-reads on each
 * open so the inline notice never goes stale.
 *
 * Returns `{loading, data, severity, count, items, refresh}`.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const EMPTY = { count: 0, severity: 'green', items: [] };

export default function useEngineerAttention({ poll = false, intervalMs = 90000 } = {}) {
  const [data, setData] = useState(EMPTY);
  const [loading, setLoading] = useState(true);
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/svc/engineer/attention`, auth());
      if (!alive.current) return;
      setData(r.data || EMPTY);
    } catch (_err) {
      // 401 / 403 / network — silently fall back to clean state so
      // the menu never shows a spurious dot when the API is down.
      if (alive.current) setData(EMPTY);
    } finally {
      if (alive.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    refresh();
    let id;
    if (poll) {
      id = setInterval(refresh, intervalMs);
    }
    return () => {
      alive.current = false;
      if (id) clearInterval(id);
    };
  }, [refresh, poll, intervalMs]);

  return {
    loading,
    data,
    severity: data.severity || 'green',
    count: data.count || 0,
    items: data.items || [],
    refresh,
  };
}
