/**
 * useStudioMode — React hook for the Studio Mode flag + quickstart state.
 *
 * Iter 215p. Studio Mode is a per-org UI toggle that simplifies the
 * Memberships console for 1-3 person teams (yoga studios, dance schools,
 * pilates, wellness coaches). Backend endpoints:
 *   GET  /api/memberships/studio/settings
 *   POST /api/memberships/studio/settings
 *   POST /api/memberships/studio/quickstart
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';

export default function useStudioMode() {
  const { API } = useAuth();
  const [studioMode, setStudioMode] = useState(false);
  const [quickstartCompleted, setQuickstartCompleted] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const headers = () => ({
    Authorization: `Bearer ${typeof window !== 'undefined' ? localStorage.getItem('token') : ''}`,
  });

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/memberships/studio/settings`, { headers: headers() });
      setStudioMode(!!data.studio_mode);
      setQuickstartCompleted(!!data.quickstart_completed);
    } catch {
      // ignore — 403 for non-operators is expected, just default to off
      setStudioMode(false);
    } finally {
      setLoading(false);
    }
  }, [API]);

  useEffect(() => { refresh(); }, [refresh]);

  const toggle = useCallback(async (next) => {
    setSaving(true);
    try {
      const { data } = await axios.post(
        `${API}/memberships/studio/settings`,
        { studio_mode: !!next },
        { headers: headers() },
      );
      setStudioMode(!!data.studio_mode);
      return { ok: true };
    } catch (e) {
      return { ok: false, error: e?.response?.data?.detail || 'Failed to toggle Studio Mode' };
    } finally {
      setSaving(false);
    }
  }, [API]);

  const runQuickstart = useCallback(async (payload = {}) => {
    setSaving(true);
    try {
      const { data } = await axios.post(
        `${API}/memberships/studio/quickstart`,
        payload,
        { headers: headers() },
      );
      setStudioMode(true);
      setQuickstartCompleted(true);
      return { ok: true, ...data };
    } catch (e) {
      return { ok: false, error: e?.response?.data?.detail || 'Quickstart failed' };
    } finally {
      setSaving(false);
    }
  }, [API]);

  return { studioMode, quickstartCompleted, loading, saving, toggle, runQuickstart, refresh };
}
