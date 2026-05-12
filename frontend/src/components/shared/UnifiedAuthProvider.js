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
import React, {
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
  const crossLoginInflight = useRef(false);

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
  // The actual stale-token check happens in the consumer (call
  // `refresh.crm()` from a 401 handler); here we just ensure the
  // CRM token is present whenever the main token is.
  useEffect(() => {
    if (!tokens.main || tokens.crm || crossLoginInflight.current) return;
    crossLoginInflight.current = true;
    axios.post(
      `${API}/crm/auth/cross-login`, {},
      { headers: { Authorization: `Bearer ${tokens.main}` }, timeout: 6000 },
    )
      .then((res) => {
        if (res.data?.token) {
          writeToken('crm', res.data.token);
          broadcast();
        }
      })
      .catch(() => { /* CRM module may be disabled for this org. Silent. */ })
      .finally(() => { crossLoginInflight.current = false; });
  }, [tokens.main, tokens.crm]);

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
    try {
      const res = await axios.post(
        `${API}/crm/auth/cross-login`, {},
        { headers: { Authorization: `Bearer ${main}` }, timeout: 6000 },
      );
      if (res.data?.token) {
        writeToken('crm', res.data.token);
        broadcast();
        return res.data.token;
      }
    } catch {
      /* fallthrough */
    }
    return null;
  }, []);

  const value = useMemo(() => ({
    tokens,
    identity,
    login,
    logout,
    refresh: { crm: refreshCrm },
  }), [tokens, identity, login, logout, refreshCrm]);

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
    };
  }
  return v;
}

export default UnifiedAuthProvider;
