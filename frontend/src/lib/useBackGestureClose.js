import { useEffect } from 'react';

/**
 * Iter 216f — back-gesture close handler for modals / sheets / dialogs.
 *
 * Problem this solves
 * -------------------
 * shadcn `Sheet` and `Dialog` are NOT routes — they're React state. So
 * a browser/mobile back gesture pops the actual route the user is on
 * instead of just closing the modal. Lee's Feb-2026 production report:
 *   "Master admin → org users panel → swipe back → dumped on landing
 *    page (lost all my filters / nav state)."
 *
 * What this hook does
 * -------------------
 * • When `open` flips true, push a phantom history entry tagged with a
 *   marker so we can detect it on cleanup.
 * • On `popstate` while `open`, intercept and call `onClose()` — the
 *   back gesture is "consumed" by closing the modal instead of
 *   navigating away.
 * • If the modal closes through any other path (X button, Escape,
 *   overlay click), pop the phantom entry on unmount so the user's
 *   subsequent back gesture still navigates as expected (no history
 *   trash accumulating per modal-open).
 *
 * Idempotent + side-effect safe — `try/catch` around every history
 * call because Safari throws if you push too rapidly.
 *
 * Usage:
 *   useBackGestureClose(isOpen, () => setIsOpen(false));
 *
 * @param open  Whether the modal/sheet is currently open
 * @param onClose Called when the user tries to back-gesture out of the modal
 * @param key Optional unique tag for this modal (e.g. "org-panel"). Lets
 *            multiple stacked modals not stomp each other's phantom entries.
 */
export function useBackGestureClose(open, onClose, key = 'gymaxis-modal') {
  useEffect(() => {
    if (!open) return undefined;
    try {
      window.history.pushState({ [key]: true }, '', window.location.href);
    } catch { /* noop — Safari rate-limits pushState */ }

    let closedByPopstate = false;
    const handlePopState = () => {
      closedByPopstate = true;
      try { onClose && onClose(); } catch { /* noop */ }
    };
    window.addEventListener('popstate', handlePopState);

    return () => {
      window.removeEventListener('popstate', handlePopState);
      // Clean close (X / Escape / overlay) → pop the phantom entry so
      // the next real back gesture doesn't trip our marker.
      if (!closedByPopstate) {
        try {
          const st = window.history.state;
          if (st && st[key]) window.history.back();
        } catch { /* noop */ }
      }
    };
  }, [open, onClose, key]);
}

export default useBackGestureClose;
