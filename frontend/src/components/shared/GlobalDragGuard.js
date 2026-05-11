/**
 * GlobalDragGuard — Iter 216h33
 *
 * Prevents the browser's default "open dropped file" behaviour anywhere
 * outside an explicit dropzone. Without this, a user dragging a PDF onto
 * the page who misses the dropzone by even a few pixels lands the file
 * on the document body — at which point the browser opens the file
 * directly (or, when many files are dropped at once, opens dozens of
 * new tabs and crashes Chrome).
 *
 * Lee reported the exact symptom on Master Admin → Spec Sheets: every
 * dropped PDF opened as a tab, taking the browser down. Root cause was
 * the lack of a window-level guard; the Card dropzone itself called
 * `preventDefault` correctly, but drops that didn't land on the Card
 * (or even drops that started outside it) hit the document's default
 * handler.
 *
 * How it works:
 *   • Two window-level listeners: `dragover` and `drop`.
 *   • Both call `preventDefault()` so the browser never opens dropped
 *     files at the document level.
 *   • Dropzones that DO handle files still receive the event first
 *     (event bubbles target → window). Their `onDrop` runs the upload
 *     and calls `preventDefault` of its own; the bubble-up to window
 *     is then a no-op.
 *   • This is the same pattern react-dropzone uses internally.
 *
 * Renders nothing.
 */
import { useEffect } from 'react';

const GlobalDragGuard = () => {
  useEffect(() => {
    // Only guard against actual FILE drags — leaves intra-app drag-and-
    // drop (Kanban cards, scheduler slots, staffing roster, mobile-app
    // builder cards) untouched. Files arriving from outside the browser
    // carry a `Files` entry in `dataTransfer.types`; in-app drags carry
    // text/uri-list, text/html, or a custom mime, never `Files`.
    const isFileDrag = (e) => {
      const types = e.dataTransfer && e.dataTransfer.types;
      if (!types) return false;
      // DataTransferItemList has a contains-like API via includes / indexOf.
      if (typeof types.includes === 'function') return types.includes('Files');
      for (let i = 0; i < types.length; i += 1) {
        if (types[i] === 'Files') return true;
      }
      return false;
    };

    const guard = (e) => {
      if (isFileDrag(e)) {
        e.preventDefault();
      }
    };

    window.addEventListener('dragover', guard);
    window.addEventListener('drop', guard);
    return () => {
      window.removeEventListener('dragover', guard);
      window.removeEventListener('drop', guard);
    };
  }, []);

  return null;
};

export default GlobalDragGuard;
