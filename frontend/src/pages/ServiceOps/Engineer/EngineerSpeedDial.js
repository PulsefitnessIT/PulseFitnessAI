/**
 * Iter 220ea·5 — Engineer App SpeedDial.
 *
 * Replaces three independently-positioned FABs (voice mic,
 * AskGymAxis sparkle, FeedbackWidget thumbs) with a single
 * thumb-friendly launcher in the bottom-right corner. Tap it once
 * to reveal the three actions as a vertical arc; tap an action to
 * dispatch the corresponding global event the existing modal
 * component already listens for.
 *
 * Why events and not props?
 *   Each of the three target modals lives in its own self-managed
 *   component (`VoiceToJobButton`, `AskGymAxis`, `FeedbackWidget`).
 *   Hoisting their open state into a context just to trigger from
 *   here would force a refactor across three feature flows. A
 *   tiny `gx:open-{voice|ask|feedback}` window-event contract
 *   keeps the SpeedDial decoupled and means non-engineer routes
 *   can keep firing those events from anywhere (e.g. a header
 *   shortcut) in the future.
 *
 * Each event-fired component is expected to ALSO suppress its own
 * launcher on engineer routes via a route check, so the engineer
 * sees exactly one launcher instead of four (3 native + 1 dial).
 *
 * Mounted by `AppRoutes.js` on any `/svc/engineer*` path.
 */
import { useEffect, useRef, useState } from 'react';
import { Plus, Mic, Sparkles, MessageSquarePlus, X } from 'lucide-react';

const ACTIONS = [
  {
    id: 'voice',
    label: 'Voice-to-job',
    icon: Mic,
    bg: 'linear-gradient(135deg, #2563eb 0%, #4338ca 100%)',
    testid: 'engineer-speed-dial-voice',
    event: 'gx:open-voice',
  },
  {
    id: 'ask',
    label: 'Ask GymAxis',
    icon: Sparkles,
    bg: 'linear-gradient(135deg, #2563eb 0%, #7c3aed 100%)',
    testid: 'engineer-speed-dial-ask',
    event: 'gx:open-ask',
  },
  {
    id: 'feedback',
    label: 'Send feedback',
    icon: MessageSquarePlus,
    bg: '#ffffff',
    fg: '#0f172a',
    border: '1px solid #e2e8f0',
    testid: 'engineer-speed-dial-feedback',
    event: 'gx:open-feedback',
  },
];

export default function EngineerSpeedDial() {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  // Close on outside-tap or Escape, so the engineer can dismiss
  // without picking an action.
  useEffect(() => {
    if (!open) return undefined;
    const onClick = (e) => {
      if (!rootRef.current?.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('mousedown', onClick);
    window.addEventListener('touchstart', onClick);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('mousedown', onClick);
      window.removeEventListener('touchstart', onClick);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const fire = (eventName) => {
    setOpen(false);
    window.dispatchEvent(new CustomEvent(eventName));
  };

  return (
    <div
      ref={rootRef}
      className="fixed bottom-6 right-6 z-40 flex flex-col items-end gap-3"
      data-testid="engineer-speed-dial"
    >
      {open && (
        <div className="flex flex-col items-end gap-3 animate-in fade-in slide-in-from-bottom-2 duration-150">
          {ACTIONS.map(({ id, label, icon: Icon, bg, fg, border, testid, event }) => (
            <div key={id} className="flex items-center gap-2">
              <span
                className="text-[11px] font-bold text-white bg-slate-900/85 dark:bg-slate-100/95 dark:text-slate-900 px-2.5 py-1 rounded-md shadow-sm"
                aria-hidden="true"
              >
                {label}
              </span>
              <button
                type="button"
                onClick={() => fire(event)}
                data-testid={testid}
                aria-label={label}
                className="w-11 h-11 rounded-full shadow-lg flex items-center justify-center hover:scale-105 transition-transform"
                style={{ background: bg, color: fg || '#fff', border: border || 'none' }}
              >
                <Icon size={18} />
              </button>
            </div>
          ))}
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        data-testid="engineer-speed-dial-launcher"
        aria-label={open ? 'Close engineer actions' : 'Open engineer actions'}
        aria-expanded={open}
        className="w-14 h-14 rounded-full text-white shadow-xl flex items-center justify-center hover:scale-105 transition-transform"
        style={{ background: 'linear-gradient(135deg, #2563eb 0%, #4338ca 100%)' }}
      >
        {open ? <X size={22} /> : <Plus size={22} />}
      </button>
    </div>
  );
}
