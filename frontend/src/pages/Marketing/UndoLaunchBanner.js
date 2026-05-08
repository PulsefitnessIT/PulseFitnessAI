/**
 * UndoLaunchBanner — 30-second "oh no, wrong button" safety net.
 *
 * Shown the moment a wizard-launched campaign ships. Gives the launcher a
 * 30-second window to cancel (DELETEs the draft / pauses the send via the
 * existing campaigns endpoint). After the window expires, the banner fades
 * away and the send is locked in.
 *
 * Usage:
 *   <UndoLaunchBanner campaignId={id} onUndone={...} onExpire={...} />
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Rocket, Undo2, CheckCircle2 } from 'lucide-react';

export default function UndoLaunchBanner({ campaignId, API, headers, onUndone, onExpire }) {
  const WINDOW_SEC = 30;
  const [remaining, setRemaining] = useState(WINDOW_SEC);
  const [state, setState] = useState('armed'); // armed | undoing | undone | expired

  useEffect(() => {
    if (state !== 'armed') return;
    const t = setInterval(() => {
      setRemaining((r) => {
        if (r <= 1) {
          clearInterval(t);
          setState('expired');
          onExpire?.();
          return 0;
        }
        return r - 1;
      });
    }, 1000);
    return () => clearInterval(t);
  }, [state, onExpire]);

  const doUndo = async () => {
    setState('undoing');
    try {
      await axios.delete(`${API}/api/marketing/campaigns/${campaignId}`, { headers });
      setState('undone');
      onUndone?.();
    } catch (e) {
      // Best-effort — the campaign may already be mid-flight. Let the
      // timer expire naturally and the user can intervene from Campaigns.
      setState('expired');
    }
  };

  if (state === 'expired' || state === 'undone') return null;

  const pct = (remaining / WINDOW_SEC) * 100;

  return (
    <div
      className="fixed left-1/2 -translate-x-1/2 bottom-6 z-[300] rounded-2xl border shadow-2xl pulse-font-body overflow-hidden"
      style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', minWidth: 380, maxWidth: '92vw' }}
      data-testid="undo-launch-banner"
    >
      {/* Progress countdown bar */}
      <div className="h-1" style={{ background: 'var(--theme-border)' }}>
        <div className="h-full transition-all" style={{ width: `${pct}%`, background: 'var(--color-brand-cyan)' }} />
      </div>
      <div className="p-4 flex items-center gap-4">
        <div className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>
          <Rocket size={15} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>
            Campaign launched
          </div>
          <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
            You have <span style={{ color: 'var(--color-brand-cyan)' }} className="font-semibold">{remaining}s</span> to undo the send.
          </div>
        </div>
        <button
          type="button"
          onClick={doUndo}
          disabled={state === 'undoing'}
          className="btn-secondary btn-sm"
          data-testid="undo-launch-btn"
        >
          {state === 'undoing' ? <CheckCircle2 size={13} /> : <Undo2 size={13} />}
          {state === 'undoing' ? 'Cancelling…' : 'Undo'}
        </button>
      </div>
    </div>
  );
}
