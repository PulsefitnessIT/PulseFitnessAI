/**
 * Modal — canonical modal/drawer primitive (single source of truth).
 *
 * Guarantees the content can NEVER be cut off behind the action footer:
 * the card is a fixed-height flex column, so the header and footer are
 * `flex-shrink-0` siblings and ONLY the body scrolls. A `sticky` footer
 * inside a scroll container (the old pattern) floats over the last field
 * at max scroll — this primitive makes that impossible by construction.
 *
 *   ┌───────────────┐  ← header  (flex-shrink-0, pinned)
 *   │  scroll body  │  ← children (flex-1 overflow-y-auto)
 *   └───────────────┘  ← footer  (flex-shrink-0, pinned)
 *
 * Usage:
 *   <Modal open={open} onClose={close} title="Add member" eyebrow="New record"
 *          size="lg" footer={<ModalFooter …/>}>
 *     …form fields…
 *   </Modal>
 *
 * Theme-aware via CSS vars (--theme-surface / --theme-border / --theme-text).
 * Renders through a portal so it escapes any transformed ancestor and the
 * fixed backdrop is measured against the viewport (not a tall <main>).
 */
import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

const SIZE = {
  sm: 'max-w-md',
  md: 'max-w-lg',
  lg: 'max-w-2xl',
  xl: 'max-w-3xl',
};

export function Modal({
  open = true,
  onClose,
  title,
  eyebrow,
  footer,
  children,
  size = 'md',
  testId = 'modal',
  closeOnBackdrop = true,
  hideClose = false,
}) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') onClose && onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (!open || typeof document === 'undefined') return undefined;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, [open]);

  if (!open || typeof document === 'undefined') return null;

  return createPortal((
    <div
      className="fixed inset-0 z-[100] bg-black/40"
      onClick={closeOnBackdrop ? onClose : undefined}
      data-testid={testId}
    >
      {/* Inset on mobile so the card sits between the fixed top/bottom navs. */}
      <div className="absolute inset-x-0 top-16 bottom-16 sm:inset-0 flex items-stretch sm:items-center justify-center p-3 sm:p-4">
        <div
          className={`relative w-full ${SIZE[size] || SIZE.md} h-full sm:h-auto sm:max-h-[calc(100vh-6rem)] bg-[color:var(--theme-surface)] border border-[color:var(--theme-border)] rounded-2xl shadow-xl flex flex-col overflow-hidden`}
          onClick={(e) => e.stopPropagation()}
          role="dialog"
          aria-modal="true"
          aria-labelledby={`${testId}-title`}
        >
          {(title || eyebrow || !hideClose) && (
            <div className="flex-shrink-0 px-5 py-4 border-b border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] rounded-t-2xl flex items-start justify-between gap-3">
              <div className="min-w-0">
                {eyebrow && <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)]">{eyebrow}</div>}
                {title && <h3 id={`${testId}-title`} className="font-extrabold text-lg mt-1 truncate" style={{ color: 'var(--theme-text)' }}>{title}</h3>}
              </div>
              {!hideClose && (
                <button
                  type="button"
                  onClick={onClose}
                  className="h-9 w-9 rounded-full flex items-center justify-center border border-[color:var(--theme-border)] bg-[color:var(--theme-bg,transparent)] text-[color:var(--theme-text)] hover:bg-[color:var(--theme-surface-hover)] focus:outline-none focus:ring-2 focus:ring-[color:var(--color-brand-cyan)] focus:ring-offset-1 transition-colors shrink-0"
                  aria-label="Close"
                  data-testid={`${testId}-close`}
                >
                  <X size={18} />
                </button>
              )}
            </div>
          )}

          {/* Scroll body — the ONLY scrolling region. `min-h-0` lets it
              shrink inside the flex column so the footer stays visible. */}
          <div className="flex-1 overflow-y-auto min-h-0 p-5 flex flex-col gap-3">{children}</div>

          {footer && <div className="flex-shrink-0">{footer}</div>}
        </div>
      </div>
    </div>
  ), document.body);
}

/**
 * ModalFooter — standard Save / Cancel action row for the footer slot.
 * Owns its own top border so it hugs the card's bottom edge.
 */
export function ModalFooter({ onCancel, onSave, saving, saveLabel, cancelLabel = 'Cancel', testId, children }) {
  if (children) {
    return (
      <div className="px-5 py-3 bg-[color:var(--theme-surface)] border-t border-[color:var(--theme-border)] rounded-b-2xl flex gap-2">
        {children}
      </div>
    );
  }
  return (
    <div className="px-5 py-3 bg-[color:var(--theme-surface)] border-t border-[color:var(--theme-border)] rounded-b-2xl flex gap-2">
      <button
        onClick={onSave}
        disabled={saving}
        className="flex-1 rounded-lg py-2.5 text-sm font-extrabold disabled:opacity-60"
        style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
        data-testid={testId}
      >
        {saving ? 'Saving…' : (saveLabel || 'Save')}
      </button>
      <button
        onClick={onCancel}
        className="rounded-lg px-4 py-2.5 text-sm font-bold border border-[color:var(--theme-border)] text-[color:var(--theme-text-muted)] hover:bg-black/[0.04] dark:hover:bg-white/5"
      >
        {cancelLabel}
      </button>
    </div>
  );
}

export default Modal;
