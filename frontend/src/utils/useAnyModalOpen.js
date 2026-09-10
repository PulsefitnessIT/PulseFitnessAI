/**
 * useAnyModalOpen — global signal that is true whenever a modal/dialog is on
 * screen anywhere in the app. Bottom-docked banners (cookie consent, PWA
 * install) subscribe to it and hide themselves while a modal is open, so they
 * can never sit over a dialog's action buttons — regardless of the modal's
 * z-index or ancestor stacking context (the root cause of the old overlap).
 *
 * Detection is DOM-based (not per-modal wiring): any rendered full-screen
 * overlay (`fixed inset-0`, the convention used by every dialog in this
 * codebase) or ARIA dialog (`role="dialog"` / `aria-modal="true"`, e.g. Radix
 * shadcn dialogs). Bottom banners tag themselves `data-bottom-banner` so they
 * are excluded from detection.
 */
import { useEffect, useState } from 'react';

let observer = null;
let current = false;
let raf = 0;
const subs = new Set();

function isRendered(el) {
  if (!el) return false;
  const rects = el.getClientRects();
  return !!(rects && rects.length);
}

function computeOpen() {
  if (typeof document === 'undefined') return false;
  const nodes = document.querySelectorAll(
    '[class~="fixed"][class~="inset-0"], [role="dialog"], [aria-modal="true"]',
  );
  for (let i = 0; i < nodes.length; i += 1) {
    const el = nodes[i];
    if (el.closest('[data-bottom-banner]')) continue; // banners aren't modals
    if (isRendered(el)) return true;
  }
  return false;
}

function recompute() {
  const next = computeOpen();
  if (next === current) return;
  current = next;
  try { document.body.dataset.modalOpen = next ? '1' : ''; } catch { /* noop */ }
  subs.forEach((fn) => fn(next));
}

function schedule() {
  if (raf) return;
  raf = requestAnimationFrame(() => { raf = 0; recompute(); });
}

function ensureObserver() {
  if (observer || typeof document === 'undefined') return;
  observer = new MutationObserver(schedule);
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['class', 'style', 'role', 'aria-modal', 'hidden'],
  });
}

export function useAnyModalOpen() {
  const [open, setOpen] = useState(current);
  useEffect(() => {
    ensureObserver();
    subs.add(setOpen);
    schedule();
    return () => { subs.delete(setOpen); };
  }, []);
  return open;
}
