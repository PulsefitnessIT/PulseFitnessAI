import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * Iter 215c — CRM mode entitlements.
 *
 * Returns the {leisure, business} modes the signed-in user has access
 * to. Leisure is auto-bundled with the Memberships module; Business is
 * a paid add-on (Master Admin grant or Stripe self-serve).
 *
 * Uses the main platform JWT (localStorage `token`) — NOT the CRM-only
 * token — because /api/me/crm-modes is on the platform auth surface.
 */
export const useCRMModes = () => {
  const [data, setData] = useState({
    modes: { leisure: false, business: false },
    any_enabled: false,
    memberships_enabled: false,
    account_type: null,
    loading: true,
    error: null,
  });

  const reload = useCallback(async () => {
    const token = localStorage.getItem('token');
    if (!token) {
      setData((d) => ({ ...d, loading: false, error: 'no_token' }));
      return;
    }
    try {
      const res = await axios.get(`${API}/me/crm-modes`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setData({ ...res.data, loading: false, error: null });
    } catch (e) {
      setData((d) => ({ ...d, loading: false, error: e?.response?.status || 'error' }));
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  return { ...data, reload };
};

/**
 * Per-user CRM mode preference (when both modes are enabled). Default
 * is leisure for Pulse Pro accounts (they joined for memberships) and
 * business otherwise.
 */
export const getStoredCrmMode = (defaultMode = 'leisure') => {
  return localStorage.getItem('crm_active_mode') || defaultMode;
};

export const setStoredCrmMode = (mode) => {
  if (mode === 'leisure' || mode === 'business') {
    localStorage.setItem('crm_active_mode', mode);
  }
};
