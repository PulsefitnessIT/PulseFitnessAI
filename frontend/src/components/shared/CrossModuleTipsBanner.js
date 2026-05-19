/**
 * CrossModuleTipsBanner — Iter 231
 *
 * Surfaces tasteful, dismissable tips on each module's main page when the
 * user has the source module enabled but lacks a complementary one
 * (e.g. has Marketing, missing CRM ⇒ "Turn campaign leads into closed deals").
 *
 * Behaviour:
 *   • Auto-rotates through applicable tips (one at a time)
 *   • "Learn more" opens a dialog with value props + "Request enable" CTA
 *   • Dismiss persists per-user via /notifications/cross-module-tips/{id}/dismiss
 *
 * Mounting:
 *   <CrossModuleTipsBanner mode="marketing" />  // pass current module
 */
import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { X, Sparkles, ChevronRight, Activity, Calendar, Briefcase, Rocket, CheckCircle2, Loader2 } from 'lucide-react';  
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const ICONS = {
  Activity, Calendar, Briefcase, Rocket,
};

const CrossModuleTipsBanner = ({ mode }) => {
  const API = process.env.REACT_APP_BACKEND_URL;
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const [tips, setTips] = useState([]);
  const [activeIdx, setActiveIdx] = useState(0);
  const [dialogTip, setDialogTip] = useState(null);
  const [requesting, setRequesting] = useState(false);

  const headers = React.useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      const { data } = await axios.get(`${API}/api/notifications/cross-module-tips`, { headers });
      // Filter to tips where current `mode` is the SOURCE — keeps each
      // module's banner contextually relevant. Master admins skip this
      // filter so they preview everything.
      const filtered = (data.tips || []).filter((t) => data.is_master_admin || !mode || t.source === mode);
      setTips(filtered);
    } catch { /* noop — banner just hides */ }
  }, [API, headers, mode, token]);

  useEffect(() => { load(); }, [load]);

  // Rotate every 12s if multiple tips
  useEffect(() => {
    if (tips.length < 2) return;
    const id = setInterval(() => setActiveIdx((i) => (i + 1) % tips.length), 12_000);
    return () => clearInterval(id);
  }, [tips.length]);

  const dismiss = async (tip) => {
    try {
      await axios.post(`${API}/api/notifications/cross-module-tips/${tip.id}/dismiss`, {}, { headers });
      setTips((prev) => prev.filter((t) => t.id !== tip.id));
      setActiveIdx(0);
    } catch {
      notify.error('Could not dismiss');
    }
  };

  const requestEnable = async (tip) => {
    setRequesting(true);
    try {
      await axios.post(`${API}/api/notifications/cross-module-tips/${tip.id}/request-enable`, {}, { headers });
      notify.success('Request sent', 'Your administrator will get back to you shortly.');
      setDialogTip(null);
    } catch (e) {
      notifyApiError(notify, e, 'Request failed');
    } finally {
      setRequesting(false);
    }
  };

  if (!tips.length) return null;
  const tip = tips[activeIdx % tips.length];
  const Icon = ICONS[tip.icon] || Sparkles;

  return (
    <>
      <div
        className="rounded-xl border border-fuchsia-200 dark:border-fuchsia-800/60 bg-gradient-to-r from-fuchsia-50 via-white to-blue-50 dark:from-fuchsia-950/30 dark:via-zinc-900 dark:to-blue-950/30 p-4 mb-5 flex items-start gap-3"
        data-testid={`cross-module-tip-${tip.id}`}
      >
        <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-fuchsia-500 to-blue-500 flex items-center justify-center text-white shrink-0">
          <Icon size={16} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[9px] font-bold uppercase tracking-[0.18em] text-fuchsia-600 dark:text-fuchsia-300">Tip</span>
            <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{tip.headline}</p>
          </div>
          <p className="text-xs text-zinc-600 dark:text-zinc-300 mt-0.5">{tip.body}</p>
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            <button
              onClick={() => setDialogTip(tip)}
              className="text-xs font-semibold text-fuchsia-700 dark:text-fuchsia-300 hover:underline inline-flex items-center gap-1"
              data-testid={`cross-module-tip-cta-${tip.id}`}
            >
              {tip.cta} <ChevronRight size={12} />
            </button>
            {tips.length > 1 && (
              <span className="text-[10px] text-zinc-400 dark:text-zinc-500">
                {activeIdx + 1} of {tips.length}
              </span>
            )}
          </div>
        </div>
        <button
          onClick={() => dismiss(tip)}
          className="p-1 text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 shrink-0"
          aria-label="Dismiss"
          data-testid={`cross-module-tip-dismiss-${tip.id}`}
        >
          <X size={14} />
        </button>
      </div>

      {dialogTip && (
        <div
          className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
          onClick={() => setDialogTip(null)}
          data-testid="cross-module-tip-dialog"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="bg-white dark:bg-zinc-900 rounded-xl shadow-2xl border border-zinc-200 dark:border-zinc-800 max-w-md w-full p-6"
          >
            <div className="flex items-start gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-fuchsia-500 to-blue-500 flex items-center justify-center text-white shrink-0">
                {React.createElement(ICONS[dialogTip.icon] || Sparkles, { size: 18 })}
              </div>
              <div className="flex-1">
                <h3 className="text-base font-bold text-zinc-900 dark:text-zinc-100 pulse-font-heading">{dialogTip.title}</h3>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">{dialogTip.headline}</p>
              </div>
              <button onClick={() => setDialogTip(null)} className="text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200" aria-label="Close" data-testid="cross-module-tip-dialog-close">
                <X size={16} />
              </button>
            </div>
            <p className="text-sm text-zinc-700 dark:text-zinc-300 mb-3">{dialogTip.body}</p>
            <ul className="space-y-1.5 mb-4">
              {(dialogTip.value_props || []).map((vp, i) => (
                <li key={i} className="text-xs text-zinc-700 dark:text-zinc-200 flex items-start gap-1.5" data-testid={`cross-module-tip-vp-${i}`}>
                  <CheckCircle2 size={12} className="text-emerald-500 mt-0.5 shrink-0" />
                  <span>{vp}</span>
                </li>
              ))}
            </ul>
            <div className="flex items-center justify-end gap-2">
              <button onClick={() => setDialogTip(null)} className="px-3 py-2 text-xs font-semibold text-zinc-600 dark:text-zinc-300 hover:text-zinc-900 dark:hover:text-zinc-100">
                Maybe later
              </button>
              <button
                onClick={() => requestEnable(dialogTip)}
                disabled={requesting}
                className="px-3 py-2 rounded-md bg-gradient-to-r from-fuchsia-600 to-blue-600 text-white text-xs font-semibold disabled:opacity-50 inline-flex items-center gap-1.5"
                data-testid="cross-module-tip-request-btn"
              >
                {requesting ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />} Request enable
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default CrossModuleTipsBanner;
