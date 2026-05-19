/**
 * <HelpHint /> — inline contextual help affordance.
 *
 * Iter 215m. Drop one of these next to any section header to give
 * users a one-click route into the matching Help Centre guide WITHOUT
 * leaving the page. Click → slide-over with steps/tips/mistakes plus
 * an "Ask Pulse" button that opens the AI Orb pre-loaded with a
 * question seeded from the current screen.
 *
 * Usage:
 *   <h2>Members <HelpHint guideId="mbr-onboard-first" /></h2>
 *
 * Or with a search query (auto-resolves to the top-ranked guide):
 *   <HelpHint query="how do I freeze a membership" />
 *
 * Always emits a `data-testid` on the trigger so tests can target it.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  HelpCircle, X, Sparkles, ArrowRight, Loader2,
} from 'lucide-react';
import { useAuth } from '@/App';
import { useNavigate } from 'react-router-dom';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function HelpHint({ guideId, query, label, size = 14, className = '', testId }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  // Read token fresh on each render to handle login state changes.
  // Falls back to `crm_token` so HelpHint renders inside the CRM SPA
  // which uses its own JWT under a different localStorage key.
  const token = typeof window !== 'undefined'
    ? (localStorage.getItem('token') || localStorage.getItem('crm_token') || '')
    : '';
  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token}` }),
    [token],
  );

  const [open, setOpen] = useState(false);
  const [guide, setGuide] = useState(null);
  const [loading, setLoading] = useState(false);
  const [resolvedId, setResolvedId] = useState(guideId || null);

  // Resolve the guide id either directly or by search query when the
  // slide-over is opened the first time. We deliberately exclude
  // `loading` and `guide` from the deps array — including them would
  // re-fire the effect mid-fetch (state changes inside the effect),
  // cancel the in-flight request, and never apply the result.
  useEffect(() => {
    if (!open) return undefined;
    if (guide) return undefined; // already loaded once for this open session
    let cancelled = false;
    const fetchOne = async (id) => {
      setLoading(true);
      try {
        const r = await axios.get(`${API}/help/guides/${id}`, { headers });
        if (!cancelled) setGuide(r.data);
      } catch {
        if (!cancelled) setGuide({ error: true });
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    if (resolvedId) {
      fetchOne(resolvedId);
    } else if (query) {
      setLoading(true);
      axios.get(`${API}/help/search`, { headers, params: { q: query } })
        .then((r) => {
          const top = (r.data?.results || [])[0];
          if (cancelled) return;
          if (top?.id) {
            setResolvedId(top.id);
            fetchOne(top.id);
          } else {
            setGuide({ error: true });
            setLoading(false);
          }
        })
        .catch(() => {
          if (!cancelled) { setGuide({ error: true }); setLoading(false); }
        });
    }
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, resolvedId, query]);

  const askPulse = useCallback(() => {
    // Seed the AI orb with the user's "I'm stuck on this section" intent.
    const seed = query || (guide?.title ? `Help me with: ${guide.title}` : 'Help me with this screen');
    try {
      sessionStorage.setItem('assistant_seed_question', seed);
      window.dispatchEvent(new CustomEvent('open-unified-assistant', { detail: { seed } }));
    } catch { /* best effort */ }
    setOpen(false);
  }, [query, guide]);

  const openFullGuide = useCallback(() => {
    if (resolvedId) navigate(`/help/${resolvedId}`);
  }, [resolvedId, navigate]);

  // Iter 215n — render even when useAuth.user is null (e.g. inside the
  // CRM SPA which uses a separate auth context). The presence of a
  // token in localStorage is the only render gate.
  if (!user && !token) return null;

  return (
    <>
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); setOpen(true); }}
        className={`inline-flex items-center justify-center rounded-full text-zinc-400 hover:text-zinc-700 hover:bg-zinc-100 transition-colors ${className}`}
        style={{ width: size + 8, height: size + 8 }}
        aria-label={label || 'Open contextual help'}
        title={label || 'Need help?'}
        data-testid={testId || `help-hint-${resolvedId || query || 'generic'}`}
      >
        <HelpCircle size={size} />
      </button>
      {open && (
        <HelpHintDrawer
          guide={guide}
          loading={loading}
          onClose={() => setOpen(false)}
          onAskPulse={askPulse}
          onOpenFull={openFullGuide}
        />
      )}
    </>
  );
}

function HelpHintDrawer({ guide, loading, onClose, onAskPulse, onOpenFull }) {
  // Close on ESC.
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-[60] flex justify-end" data-testid="help-hint-drawer">
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
        data-testid="help-hint-backdrop"
      />
      <div
        className="relative w-full max-w-md h-full bg-white shadow-2xl flex flex-col"
        role="dialog"
        aria-label="Contextual help"
      >
        <div className="flex items-start justify-between p-4 border-b border-zinc-100">
          <div className="flex items-center gap-2 min-w-0">
            <HelpCircle size={16} className="text-zinc-500 flex-shrink-0" />
            <div className="min-w-0">
              <div className="text-[10px] uppercase tracking-wider font-bold text-zinc-400">Help</div>
              <h3 className="text-sm font-semibold text-zinc-900 truncate">
                {loading ? 'Loading…' : (guide?.title || 'No guide found')}
              </h3>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded hover:bg-zinc-100 text-zinc-500"
            aria-label="Close"
            data-testid="help-hint-close"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {loading && (
            <div className="flex items-center gap-2 text-sm text-zinc-500" data-testid="help-hint-loading">
              <Loader2 size={14} className="animate-spin" /> Loading guide…
            </div>
          )}
          {!loading && guide?.error && (
            <div className="text-sm text-zinc-600" data-testid="help-hint-empty">
              No matching guide found yet — try Ask Pulse below.
            </div>
          )}
          {!loading && guide && !guide.error && (
            <>
              {guide.description && (
                <p className="text-sm text-zinc-700">{guide.description}</p>
              )}
              {Array.isArray(guide.steps) && guide.steps.length > 0 && (
                <section data-testid="help-hint-steps">
                  <div className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-2">Steps</div>
                  <ol className="space-y-2">
                    {guide.steps.slice(0, 5).map((s, i) => (
                      <li key={i} className="text-sm" data-testid={`help-hint-step-${i}`}>
                        <div className="font-semibold text-zinc-900">{i + 1}. {s.title}</div>
                        {s.body && <div className="text-zinc-600 mt-0.5">{s.body}</div>}
                      </li>
                    ))}
                  </ol>
                </section>
              )}
              {Array.isArray(guide.tips) && guide.tips.length > 0 && (
                <section data-testid="help-hint-tips">
                  <div className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-1">Tips</div>
                  <ul className="space-y-1 list-disc list-inside text-sm text-zinc-700">
                    {guide.tips.slice(0, 3).map((t, i) => <li key={i}>{t}</li>)}
                  </ul>
                </section>
              )}
            </>
          )}
        </div>

        <div className="p-3 border-t border-zinc-100 grid grid-cols-2 gap-2 bg-zinc-50">
          <button
            type="button"
            onClick={onAskPulse}
            className="inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-cyan-500 text-zinc-900 text-sm font-semibold hover:bg-cyan-400"
            data-testid="help-hint-ask-pulse"
          >
            <Sparkles size={14} /> Ask Pulse
          </button>
          <button
            type="button"
            onClick={onOpenFull}
            disabled={!guide || guide.error}
            className="inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg border border-zinc-300 text-zinc-700 text-sm font-semibold hover:bg-white disabled:opacity-50"
            data-testid="help-hint-open-full"
          >
            Full guide <ArrowRight size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}
