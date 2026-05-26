/**
 * useJobDraft — Iter 220c
 *
 * Persists the Engineer App's job-completion draft so engineers never
 * lose their work when they:
 *   • Switch tabs inside `EngineerJobDetailV2` (component unmounts)
 *   • Hit the back button mid-typing
 *   • Reload the page / kill the app / lose signal
 *
 * Two-tier persistence:
 *   1. localStorage — instant, sync, survives page reload + offline.
 *   2. Backend `/api/svc/engineer/jobs/{id}/draft` — debounced 1 s,
 *      durable, survives device loss.
 *
 * The hook returns `{ draft, setDraft, saving, lastSavedAt, hydrated }`.
 * `setDraft` accepts a partial patch (`{ summary: '...' }`) or an
 * updater fn (`(prev) => ({ ...prev, x: 1 })`).
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});
const storageKey = (caseId) => `gymaxis:engineer:job-draft:${caseId}`;

const DEBOUNCE_MS = 1000;

export function useJobDraft(caseId) {
  const [draft, setDraftState] = useState({});
  const [hydrated, setHydrated] = useState(false);
  const [saving, setSaving] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState(null);
  const [dirty, setDirty] = useState(false);
  const draftRef = useRef(draft);
  const debounceRef = useRef(null);

  // ── Hydration — read localStorage immediately, then reconcile with
  // backend draft on the next tick. Server wins only when its
  // `updated_at` is newer than the local copy.
  useEffect(() => {
    if (!caseId) { setHydrated(true); return; }
    let cancelled = false;

    // 1. localStorage (synchronous)
    try {
      const raw = localStorage.getItem(storageKey(caseId));
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === 'object') {
          draftRef.current = parsed.draft || {};
          setDraftState(parsed.draft || {});
          if (parsed.saved_at) setLastSavedAt(parsed.saved_at);
        }
      }
    } catch (e) {
      console.warn('[job-draft] local hydrate failed', e);
    }

    // 2. Backend (async — picks up the latest from another device)
    (async () => {
      try {
        const r = await axios.get(`${API}/svc/engineer/jobs/${caseId}/draft`, auth());
        if (cancelled) return;
        const remote = r.data?.draft || {};
        const remoteAt = r.data?.updated_at;
        const localAt = lastSavedAt;
        // If remote is newer or local is empty, take remote.
        const localEmpty = !draftRef.current || Object.keys(draftRef.current).length === 0;
        const remoteWins =
          localEmpty ||
          (remoteAt && (!localAt || new Date(remoteAt) > new Date(localAt)));
        if (remoteWins && Object.keys(remote).length) {
          draftRef.current = remote;
          setDraftState(remote);
          setLastSavedAt(remoteAt || null);
          try {
            localStorage.setItem(
              storageKey(caseId),
              JSON.stringify({ draft: remote, saved_at: remoteAt }),
            );
          } catch (e) { /* quota */ }
        }
      } catch (e) {
        // Non-blocking — engineer can still work offline.
        console.warn('[job-draft] remote hydrate failed', e);
      } finally {
        if (!cancelled) setHydrated(true);
      }
    })();

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  // ── Persist on every change. localStorage is sync (no race when the
  // engineer switches tabs immediately after typing). Backend write is
  // debounced to avoid spamming on every keystroke.
  const persistRemote = useCallback(async (next) => {
    if (!caseId) return;
    setSaving(true);
    try {
      const r = await axios.put(
        `${API}/svc/engineer/jobs/${caseId}/draft`,
        { draft: next },
        auth(),
      );
      setLastSavedAt(r.data?.saved_at || new Date().toISOString());
      setDirty(false);
      try {
        localStorage.setItem(
          storageKey(caseId),
          JSON.stringify({ draft: next, saved_at: r.data?.saved_at }),
        );
      } catch (e) { /* quota */ }
    } catch (e) {
      // Stay dirty so the warning still fires; the local copy is safe.
      console.warn('[job-draft] remote save failed', e);
    } finally {
      setSaving(false);
    }
  }, [caseId]);

  const setDraft = useCallback((patchOrFn) => {
    const next = typeof patchOrFn === 'function'
      ? patchOrFn(draftRef.current)
      : { ...draftRef.current, ...patchOrFn };
    draftRef.current = next;
    setDraftState(next);
    setDirty(true);
    if (caseId) {
      // Local first (sync, instant).
      try {
        localStorage.setItem(
          storageKey(caseId),
          JSON.stringify({ draft: next, saved_at: lastSavedAt }),
        );
      } catch (e) { /* quota */ }
      // Debounced backend write.
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => persistRemote(next), DEBOUNCE_MS);
    }
  }, [caseId, lastSavedAt, persistRemote]);

  // Flush + clear used on successful complete.
  const clearDraft = useCallback(async () => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    setDirty(false);
    draftRef.current = {};
    setDraftState({});
    try { localStorage.removeItem(storageKey(caseId)); } catch (e) { /* ignore */ }
    if (caseId) {
      try { await axios.delete(`${API}/svc/engineer/jobs/${caseId}/draft`, auth()); }
      catch (e) { /* ignore */ }
    }
  }, [caseId]);

  // beforeunload guard — only when there are pending unsaved changes.
  useEffect(() => {
    const handler = (e) => {
      if (!dirty) return undefined;
      e.preventDefault();
      e.returnValue = 'You have unsaved work on this job. Leave anyway?';
      return e.returnValue;
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [dirty]);

  return { draft, setDraft, clearDraft, saving, lastSavedAt, hydrated, dirty };
}

export default useJobDraft;
