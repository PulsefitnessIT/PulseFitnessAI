/**
 * Iter 220ea·6 — Router-agnostic "is engineer route?" hook.
 *
 * Some global components (`AskPulseFitness`, `CookieConsent`, etc.) are
 * mounted OUTSIDE the `<BrowserRouter>` and therefore cannot call
 * `useLocation()`. This hook gives them the same reactivity by
 * listening to `popstate` plus a self-dispatched
 * `gx:route-changed` event we fire on every `history.pushState` /
 * `replaceState` (which is what React Router uses internally).
 *
 * Patching `history.pushState/replaceState` here is a one-shot
 * idempotent install; calling the hook from multiple components
 * does NOT re-patch (we stamp a flag on the function).
 *
 * Returns the current `pathname` as a reactive string. Components
 * can derive whatever they need from it.
 */
import { useEffect, useState } from 'react';

const PATCH_FLAG = '__gxHistoryPatched';

function installHistoryPatch() {
  if (typeof window === 'undefined') return;
  if (window.history[PATCH_FLAG]) return;
  const fire = () => window.dispatchEvent(new Event('gx:route-changed'));
  const wrap = (method) => {
    const original = window.history[method];
    window.history[method] = function patched(...args) {
      const result = original.apply(this, args);
      fire();
      return result;
    };
  };
  wrap('pushState');
  wrap('replaceState');
  window.history[PATCH_FLAG] = true;
}

export function useRouterAgnosticPathname() {
  const initial = typeof window !== 'undefined' ? window.location.pathname : '/';
  const [pathname, setPathname] = useState(initial);

  useEffect(() => {
    installHistoryPatch();
    const sync = () => setPathname(window.location.pathname);
    window.addEventListener('popstate', sync);
    window.addEventListener('gx:route-changed', sync);
    return () => {
      window.removeEventListener('popstate', sync);
      window.removeEventListener('gx:route-changed', sync);
    };
  }, []);

  return pathname;
}

export function useIsEngineerRoute() {
  const pathname = useRouterAgnosticPathname();
  return /^\/svc\/engineer/.test(pathname);
}
