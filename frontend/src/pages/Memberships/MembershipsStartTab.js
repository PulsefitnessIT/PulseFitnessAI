/**
 * Memberships Start tab — progressive onboarding checklist (iter 216ah, G1).
 *
 * Data-driven: fetches /memberships/studio/onboarding which computes step
 * completeness from live DB counts, then renders a 5-step checklist.
 *
 * Auto-dismissal: when every step is done (or the operator clicks "Hide
 * this"), the parent (MembershipsConsole) hides the Start tab entirely
 * via the `onAllComplete` callback — see useOnboardingChecklist below.
 */
import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import {
  CheckCircle2, Circle, ArrowRight, EyeOff, Sparkles, Loader2, Zap,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

/** Shared hook — also used by MembershipsConsole to decide whether to
 * render the Start tab button at all. Single source of truth so the tab
 * vanishes the moment the checklist is complete. */
export function useOnboardingChecklist() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/memberships/studio/onboarding`, { headers: authHeaders() });
      setData(r.data);
    } catch {
      setData(null);
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  return { data, loading, reload: load };
}

export default function MembershipsStartTab({ setTab }) {
  const { data, loading, reload } = useOnboardingChecklist();
  const [dismissing, setDismissing] = useState(false);

  if (loading) {
    return (
      <div className="flex items-center gap-2 p-10 text-sm text-[color:var(--theme-text-muted)]" data-testid="mbr-start-loading">
        <Loader2 size={14} className="animate-spin" /> Checking your setup…
      </div>
    );
  }
  if (!data) {
    return (
      <div className="p-10 text-sm text-[color:var(--theme-text-muted)]" data-testid="mbr-start-empty">
        Couldn't load your onboarding checklist. <button onClick={reload} className="underline">Retry</button>
      </div>
    );
  }

  const dismiss = async () => {
    if (!window.confirm('Hide this checklist? You can still complete the remaining steps from each tab.')) return;
    setDismissing(true);
    try {
      await axios.post(`${API}/memberships/studio/onboarding/dismiss`, {}, { headers: authHeaders() });
      notify.success('Checklist hidden. Welcome aboard.');
      await reload();
      window.dispatchEvent(new CustomEvent('memberships-start-dismissed'));
    } catch (e) {
      notifyApiError(notify, e, 'Failed to dismiss');
    }
    setDismissing(false);
  };

  const { steps, completed, total, percent, all_complete: allComplete } = data;

  return (
    <div className="max-w-4xl" data-testid="mbr-start-tab">
      <div className="flex items-start justify-between gap-4 flex-wrap mb-6">
        <div>
          <p className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)] flex items-center gap-1">
            <Sparkles size={11} /> Studio quickstart
          </p>
          <h2 className="text-2xl sm:text-3xl tracking-tight font-semibold pulse-font-heading mt-1" style={{ color: 'var(--theme-text)' }}>
            {allComplete ? "You're fully set up" : "Let's get your studio live"}
          </h2>
          <p className="text-sm mt-1" style={{ color: 'var(--theme-text-muted)' }}>
            {allComplete
              ? 'Every setup step is complete. This panel will disappear on your next visit.'
              : `${completed} of ${total} complete — tackle them in any order, each takes under 2 minutes.`}
          </p>
        </div>
        <button onClick={dismiss} disabled={dismissing}
          className="inline-flex items-center gap-1.5 text-xs font-bold px-3 py-2 rounded-lg border border-[color:var(--theme-border)] hover:bg-white/5"
          data-testid="mbr-start-dismiss">
          {dismissing ? <Loader2 size={12} className="animate-spin" /> : <EyeOff size={12} />}
          Hide this
        </button>
      </div>

      <div className="h-2 rounded-full overflow-hidden mb-6" style={{ background: 'var(--theme-surface-hover)' }} data-testid="mbr-start-progress">
        <div className="h-full transition-all"
          style={{ width: `${percent}%`, background: 'var(--color-brand-cyan)' }} />
      </div>

      <ul className="space-y-2">
        {steps.map((s, idx) => (
          <li key={s.id}
            className="rounded-xl p-4 border transition-colors flex items-start gap-3"
            style={{
              background: s.done ? 'var(--theme-surface-hover)' : 'var(--theme-surface)',
              borderColor: s.done ? 'rgba(16,185,129,0.3)' : 'var(--theme-border)',
              opacity: s.done ? 0.75 : 1,
            }}
            data-testid={`mbr-start-step-${s.id}`}>
            <div className="pt-0.5">
              {s.done
                ? <CheckCircle2 size={18} className="text-emerald-400" />
                : <Circle size={18} className="text-[color:var(--theme-text-muted)]" />}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] font-bold uppercase tracking-wider text-[color:var(--theme-text-muted)]">
                  Step {idx + 1}
                </span>
                {s.done && (
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400">
                    Done{s.count ? ` · ${s.count}` : ''}
                  </span>
                )}
              </div>
              <p className="text-sm font-extrabold mt-0.5" style={{ color: 'var(--theme-text)' }}>
                {s.title}
              </p>
              <p className="text-xs mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
                {s.note}
              </p>
            </div>
            {!s.done && (
              <button onClick={() => setTab(s.cta_tab)}
                className="inline-flex items-center gap-1.5 text-xs font-extrabold px-3 py-2 rounded-lg flex-shrink-0"
                style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
                data-testid={`mbr-start-cta-${s.id}`}>
                {s.cta_label} <ArrowRight size={11} />
              </button>
            )}
          </li>
        ))}
      </ul>

      {allComplete && (
        <div className="mt-6 rounded-xl p-5 border text-center"
          style={{ background: 'var(--theme-surface)', borderColor: 'rgba(16,185,129,0.3)' }}
          data-testid="mbr-start-all-done">
          <Zap size={20} className="mx-auto text-emerald-400 mb-2" />
          <p className="font-extrabold">All set. The Start tab auto-hides on next load.</p>
          <p className="text-xs text-[color:var(--theme-text-muted)] mt-1">
            Head to the Dashboard for your KPI strip, or Studio Brain for AI retention insights.
          </p>
        </div>
      )}
    </div>
  );
}
