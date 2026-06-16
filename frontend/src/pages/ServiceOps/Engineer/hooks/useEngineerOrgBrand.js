/**
 * useEngineerOrgBrand — Iter 261.
 *
 * Resolves the Engineer App header brand: the name of the organisation
 * the engineer is associated with (instead of the generic "Pulse Fitness ·
 * Engineer"), plus the internal/partner split used to hide the legacy
 * report self-upload for internal engineers (their Service Desk imports
 * history via Settings instead).
 *
 * One GET /svc/engineer/me per session — cached at module level and in
 * sessionStorage so every Engineer App page header renders instantly.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const CACHE_KEY = 'gx_engineer_org_brand_v1';

let memCache = null;
let inflight = null;

const readSession = () => {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
};

export default function useEngineerOrgBrand() {
  const [brand, setBrand] = useState(() => memCache || readSession());

  useEffect(() => {
    if (memCache) return undefined;
    let alive = true;
    if (!inflight) {
      inflight = axios
        .get(`${API}/svc/engineer/me`, {
          headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
        })
        .then((r) => {
          const next = {
            orgName: r.data?.organization_name || null,
            internal: r.data?.internal_engineer === true,
          };
          memCache = next;
          try { sessionStorage.setItem(CACHE_KEY, JSON.stringify(next)); } catch { /* ignore */ }
          return next;
        })
        .catch(() => null)
        .finally(() => { inflight = null; });
    }
    inflight.then((next) => { if (alive && next) setBrand(next); });
    return () => { alive = false; };
  }, []);

  const orgName = brand?.orgName || null;
  return {
    orgName,
    internal: brand?.internal === true,
    label: orgName ? `${orgName} · Engineer` : 'Pulse Fitness · Engineer',
  };
}
