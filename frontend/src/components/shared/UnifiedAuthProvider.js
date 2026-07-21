/**
 * UnifiedAuthProvider — Iter 216h45
 *
 * Single source of truth for the three auth surfaces that previously
 * each owned their own `localStorage` key + bootstrap routine:
 *
 *    main    — Operations / Memberships / Master Admin / portals.
 *              `localStorage.token`. Issued by POST /api/auth/login.
 *    crm     — CRM workspace. `localStorage.crm_token`. Issued by
 *              POST /api/crm/auth/login OR POST /api/crm/auth/cross-login
 *              (exchange a main token for a CRM-scoped token).
 *    member  — Member kiosk / member app. `localStorage.member_token`.
 *
 * Why?
 *   Two recurring "ghost-login" bugs in close succession (iter 216h42
 *   false-offline banner, iter 216h43 stale CRMLogin) traced back to
 *   the same root issue: each module owns its own token + bootstrap
 *   routine, so auth state diverges across modules. CRM used a
 *   sessionStorage gate that wiped a valid token on every new tab.
 *   The fix was per-module; the *class* of bug remained.
 *
 *   This provider lifts auth into one place, watches all three keys
 *   via both `window.storage` (cross-tab) and a custom in-tab event,
 *   and auto-refreshes the CRM token from the main JWT the moment a
 *   main login lands. Once consumers move to `useUnifiedAuth()`, they
 *   neither read nor write localStorage directly — eliminating the
 *   entire class of "I logged in once but X module still says
 *   logged out" bug.
 *
 * Backwards compatibility:
 *   The provider continues to write to the same `token` / `crm_token`
 *   / `member_token` localStorage keys, so every existing direct
 *   `localStorage.getItem('token')` reader keeps working. Migration
 *   to `useUnifiedAuth()` is incremental.
 *
 * API:
 *   const { tokens, identity, login, logout, refresh } = useUnifiedAuth();
 *
 *   tokens   = { main, crm, member }   // strings or null
 *   identity = { main, crm }           // { email, role, ... } | null
 *   login({ scope, token, identity? })  // scope ∈ 'main'|'crm'|'member'
 *   logout(scope?)                      // omit scope to wipe all 3
 *   refresh.crm()                       // re-exchange main → CRM
 *
 * Internal event bus:
 *   The provider dispatches a `gymaxis:auth-changed` CustomEvent on
 *   `window` whenever any token changes. Components that aren't ready
 *   to migrate to `useUnifiedAuth()` yet can still react to logins via:
 *     window.addEventListener('gymaxis:auth-changed', handler)
 */
import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from 'react';
import axios from 'axios';

const AuthCtx = createContext(null);

const API = (typeof process !== 'undefined' && process.env && process.env.REACT_APP_BACKEND_URL)
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';

const KEY = { main: 'token', crm: 'crm_token', member: 'member_token' };

const readToken = (scope) => {
  if (typeof localStorage === 'undefined') return null;
  return localStorage.getItem(KEY[scope]) || null;
};
const writeToken = (scope, token) => {
  if (typeof localStorage === 'undefined') return;
  if (token) localStorage.setItem(KEY[scope], token);
  else localStorage.removeItem(KEY[scope]);
};

const broadcast = () => {
  if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
    window.dispatchEvent(new CustomEvent('gymaxis:auth-changed'));
  }
};

export function UnifiedAuthProvider({ children }) {
  const [tokens, setTokens] = useState(() => ({
    main: readToken('main'),
    crm: readToken('crm'),
    member: readToken('member'),
  }));
  const [identity, setIdentity] = useState({ main: null, crm: null });
  // Iter 216h67 — cross-login retry telemetry surfaced to consumers
  // (e.g. CRMApp uses this to render a "Reconnecting…" state with a
  // manual Try-again button instead of bouncing the user to CRMLogin
  // when their main session is alive but the network blip ate the
  // cross-login response).
  const [crmExchangeStatus, setCrmExchangeStatus] = useState({
    state: 'idle',       // 'idle' | 'pending' | 'failed' | 'unavailable'
    attempts: 0,
    lastError: null,
  });
  const crossLoginInflight = useRef(false);
  const crossLoginAttemptsRef = useRef(0);
  const crossLoginTimerRef = useRef(null);
  // Cap automatic retries at 3 (1s + 2s + 4s = 7s headroom on top of
  // the per-call 6s timeout). After that the consumer surfaces a
  // "Try again" CTA so the user can manually retry.
  const MAX_CROSS_LOGIN_ATTEMPTS = 3;

  // ── Token reads: react to both cross-tab `storage` events and our
  // own in-tab `gymaxis:auth-changed` so consumers stay in sync.
  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const sync = () => {
      setTokens({
        main: readToken('main'),
        crm: readToken('crm'),
        member: readToken('member'),
      });
    };
    window.addEventListener('storage', sync);
    window.addEventListener('gymaxis:auth-changed', sync);
    return () => {
      window.removeEventListener('storage', sync);
      window.removeEventListener('gymaxis:auth-changed', sync);
    };
  }, []);

  // ── Auto-cross-login: when main token exists but CRM token is
  // missing OR invalid, eagerly exchange. This is what kills the
  // "I'm logged in but CRM asks me to log in again" bug class.
  //
  // Iter 216h67 — mobile-network hardening. The original implementation
  // (216h45) had no retry: any timeout / 5xx silently dropped the
  // exchange and CRMApp eventually rendered CRMLogin to a user with
  // a perfectly valid main session. We now retry up to 3× with
  // exponential backoff and expose status to consumers so they can
  // render a "Reconnecting…" state instead of a bogus login screen.
  const attemptCrossLogin = useCallback(async () => {
    const main = readToken('main');
    if (!main) {
      setCrmExchangeStatus({ state: 'idle', attempts: 0, lastError: null });
      return;
    }
    if (crossLoginInflight.current) return;
    crossLoginInflight.current = true;
    const attempt = crossLoginAttemptsRef.current + 1;
    crossLoginAttemptsRef.current = attempt;
    setCrmExchangeStatus({ state: 'pending', attempts: attempt, lastError: null });
    try {
      const res = await axios.post(
        `${API}/crm/auth/cross-login`, {},
        { headers: { Authorization: `Bearer ${main}` }, timeout: 8000 },
      );
      if (res.data?.token) {
        writeToken('crm', res.data.token);
        broadcast();
        crossLoginAttemptsRef.current = 0;
        setCrmExchangeStatus({ state: 'idle', attempts: 0, lastError: null });
      } else {
        // 200 OK but no token in payload — treat as unavailable so we
        // don't hammer the endpoint. Common for orgs without CRM
        // entitlement.
        setCrmExchangeStatus({ state: 'unavailable', attempts: attempt, lastError: 'CRM not available for this account' });
      }
    } catch (err) {
      const status = err?.response?.status;
      // 401/403 = the main token cannot exchange (e.g. account doesn't
      // have CRM access). Don't retry — surface "unavailable".
      if (status === 401 || status === 403) {
        setCrmExchangeStatus({
          state: 'unavailable',
          attempts: attempt,
          lastError: err?.response?.data?.detail || 'CRM access denied for this account',
        });
      } else if (attempt < MAX_CROSS_LOGIN_ATTEMPTS) {
        // Transient network / 5xx — retry with exponential backoff.
        const delayMs = Math.min(4000, 1000 * Math.pow(2, attempt - 1));
        setCrmExchangeStatus({
          state: 'pending',
          attempts: attempt,
          lastError: err?.message || 'Network error',
        });
        crossLoginTimerRef.current = setTimeout(() => {
          crossLoginInflight.current = false;
          attemptCrossLogin();
        }, delayMs);
        return; // don't reset inflight yet — the timer will
      } else {
        setCrmExchangeStatus({
          state: 'failed',
          attempts: attempt,
          lastError: err?.message || 'CRM is unreachable',
        });
      }
    } finally {
      // Reset inflight unless a retry timer is queued.
      if (!crossLoginTimerRef.current) {
        crossLoginInflight.current = false;
      }
    }
  }, []);

  useEffect(() => {
    // Cancel any pending retry when state changes (e.g. logout).
    return () => {
      if (crossLoginTimerRef.current) {
        clearTimeout(crossLoginTimerRef.current);
        crossLoginTimerRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!tokens.main) {
      // No main → nothing to exchange. Reset attempt counter so the
      // next main login starts fresh.
      crossLoginAttemptsRef.current = 0;
      if (crossLoginTimerRef.current) {
        clearTimeout(crossLoginTimerRef.current);
        crossLoginTimerRef.current = null;
      }
      setCrmExchangeStatus({ state: 'idle', attempts: 0, lastError: null });
      return;
    }
    if (tokens.crm) {
      // CRM token landed (either from this exchange or another tab).
      // Stop trying and reset the attempt counter.
      crossLoginAttemptsRef.current = 0;
      if (crossLoginTimerRef.current) {
        clearTimeout(crossLoginTimerRef.current);
        crossLoginTimerRef.current = null;
      }
      setCrmExchangeStatus({ state: 'idle', attempts: 0, lastError: null });
      return;
    }
    // Main present, CRM missing — kick off the exchange chain.
    attemptCrossLogin();
  }, [tokens.main, tokens.crm, attemptCrossLogin]);

  // ── Identity hydration. Lightweight `/auth/me` + `/crm/auth/me`
  // calls so consumers don't each redo the same fetch.
  useEffect(() => {
    let cancelled = false;
    if (!tokens.main) { setIdentity((id) => ({ ...id, main: null })); return undefined; }
    axios.get(`${API}/auth/me`, { headers: { Authorization: `Bearer ${tokens.main}` }, timeout: 6000 })
      .then((res) => { if (!cancelled && res.data?.email) setIdentity((id) => ({ ...id, main: res.data })); })
      .catch(() => { if (!cancelled) setIdentity((id) => ({ ...id, main: null })); });
    return () => { cancelled = true; };
  }, [tokens.main]);

  useEffect(() => {
    let cancelled = false;
    if (!tokens.crm) { setIdentity((id) => ({ ...id, crm: null })); return undefined; }
    axios.get(`${API}/crm/auth/me`, { headers: { Authorization: `Bearer ${tokens.crm}` }, timeout: 6000 })
      .then((res) => { if (!cancelled && res.data?.email) setIdentity((id) => ({ ...id, crm: res.data })); })
      .catch(() => {
        if (cancelled) return;
        // Stale CRM token. Strip and rely on the auto-cross-login
        // effect above to re-mint from the main token.
        writeToken('crm', null);
        broadcast();
        setIdentity((id) => ({ ...id, crm: null }));
      });
    return () => { cancelled = true; };
  }, [tokens.crm]);

  // ── Org-mismatch guard (multi-tenant isolation, CRITICAL). ──────────
  // When a master admin switches org portals / starts an impersonation,
  // the MAIN session rebinds to the new org but the previously-minted
  // `crm_token` for the OLD org lingers in localStorage (it's still a
  // valid token, so the stale-token effect above won't strip it). Result:
  // the CRM keeps reading the PREVIOUS org's data (e.g. Documents) under
  // the new tenant's header. If the two identities disagree on
  // organization_id, the CRM token is stale for THIS session — drop it so
  // the auto-cross-login re-mints one bound to the current org.
  useEffect(() => {
    const mainOrg = identity.main?.organization_id;
    const crmOrg = identity.crm?.organization_id;
    if (mainOrg && crmOrg && mainOrg !== crmOrg) {
      writeToken('crm', null);
      broadcast();
      setIdentity((id) => ({ ...id, crm: null }));
    }
  }, [identity.main, identity.crm]);

  // ── API surface.
  const login = useCallback(({ scope, token, identity: nextIdentity }) => {
    if (!scope || !token) return;
    writeToken(scope, token);
    if (nextIdentity && (scope === 'main' || scope === 'crm')) {
      setIdentity((id) => ({ ...id, [scope]: nextIdentity }));
    }
    broadcast();
  }, []);

  const logout = useCallback((scope) => {
    if (scope) {
      writeToken(scope, null);
    } else {
      writeToken('main', null);
      writeToken('crm', null);
      writeToken('member', null);
      // Iter 216h43 — also wipe the legacy sessionStorage gate so any
      // pre-migrated consumer doesn't try to honour a stale flag.
      if (typeof sessionStorage !== 'undefined') sessionStorage.removeItem('crm_active_session');
    }
    setIdentity({ main: null, crm: null });
    broadcast();
  }, []);

  const refreshCrm = useCallback(async () => {
    const main = readToken('main');
    if (!main) return null;
    // Iter 216h67 — reset the attempt counter so a user-triggered
    // retry always gets a fresh window (3 more attempts).
    crossLoginAttemptsRef.current = 0;
    if (crossLoginTimerRef.current) {
      clearTimeout(crossLoginTimerRef.current);
      crossLoginTimerRef.current = null;
    }
    try {
      const res = await axios.post(
        `${API}/crm/auth/cross-login`, {},
        { headers: { Authorization: `Bearer ${main}` }, timeout: 8000 },
      );
      if (res.data?.token) {
        writeToken('crm', res.data.token);
        broadcast();
        setCrmExchangeStatus({ state: 'idle', attempts: 0, lastError: null });
        return res.data.token;
      }
      setCrmExchangeStatus({ state: 'unavailable', attempts: 1, lastError: 'CRM not available' });
    } catch (err) {
      const status = err?.response?.status;
      if (status === 401 || status === 403) {
        setCrmExchangeStatus({
          state: 'unavailable',
          attempts: 1,
          lastError: err?.response?.data?.detail || 'CRM access denied',
        });
      } else {
        setCrmExchangeStatus({
          state: 'failed',
          attempts: 1,
          lastError: err?.message || 'CRM is unreachable',
        });
      }
    }
    return null;
  }, []);

  const value = useMemo(() => ({
    tokens,
    identity,
    login,
    logout,
    refresh: { crm: refreshCrm },
    // Iter 216h67 — surfaced so consumers (CRMApp) can render
    // "Reconnecting…" + manual retry instead of CRMLogin when a
    // logged-in user hits a CRM-cross-login network blip.
    crmExchangeStatus,
  }), [tokens, identity, login, logout, refreshCrm, crmExchangeStatus]);

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useUnifiedAuth() {
  const v = useContext(AuthCtx);
  if (!v) {
    // Graceful fallback for code paths that mount outside the
    // provider (Storybook, isolated unit tests). Falls back to a
    // read-only snapshot of localStorage.
    return {
      tokens: { main: readToken('main'), crm: readToken('crm'), member: readToken('member') },
      identity: { main: null, crm: null },
      login: ({ scope, token }) => writeToken(scope, token),
      logout: (scope) => {
        if (scope) writeToken(scope, null);
        else { writeToken('main', null); writeToken('crm', null); writeToken('member', null); }
      },
      refresh: { crm: async () => null },
      crmExchangeStatus: { state: 'idle', attempts: 0, lastError: null },
    };
  }
  return v;
}

export default UnifiedAuthProvider;
