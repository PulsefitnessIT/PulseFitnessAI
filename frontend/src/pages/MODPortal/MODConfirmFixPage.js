/**
 * Public MOD Confirm-Fix page.
 *
 * Iter 216h115 — reporter lands here from the email link after their
 * fault has been marked resolved. Captures Y/N + 1–5 rating + free
 * text comment. No auth — the token in the URL is the auth.
 */
import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Star, Check, X, Loader2, AlertTriangle } from 'lucide-react';

const API = (process.env.REACT_APP_BACKEND_URL || '') + '/api';

export default function MODConfirmFixPage() {
  const { token } = useParams();
  const [lookup, setLookup] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [confirmed, setConfirmed] = useState(null);
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    let cancelled = false;
    axios
      .get(`${API}/public/mod-fault-confirm/${token}`)
      .then((r) => { if (!cancelled) setLookup(r.data); })
      .catch((e) => {
        if (!cancelled) setError(e?.response?.data?.detail || 'Link invalid or expired');
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [token]);

  const submit = async () => {
    if (confirmed === null) return;
    setSubmitting(true);
    try {
      const r = await axios.post(
        `${API}/public/mod-fault-confirm/${token}`,
        { confirmed, rating: rating || null, comment: comment.trim() || null },
      );
      setResult(r.data);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not record your response');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="min-h-screen grid place-items-center px-4 py-8"
      style={{ background: '#0A0B10', color: '#fff' }}
      data-testid="mod-confirm-fix-page"
    >
      <div className="w-full max-w-md rounded-2xl overflow-hidden border" style={{ borderColor: 'rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.02)' }}>
        <div className="px-5 py-4 border-b" style={{ borderColor: 'rgba(255,255,255,0.08)', background: 'rgba(25,205,255,0.06)' }}>
          <div className="text-[10px] font-extrabold uppercase tracking-[0.3em]" style={{ color: '#19CDFF' }}>
            Pulse Fitness · MOD Service · Confirm fix
          </div>
          {lookup && (
            <h1 className="text-base font-extrabold mt-1.5" data-testid="mod-confirm-fix-ticket">
              {lookup.ticket_ref} · {lookup.site_name}
            </h1>
          )}
        </div>
        <div className="p-5 space-y-4">
          {loading && (
            <div className="flex items-center gap-2 text-sm text-white/70"><Loader2 size={14} className="animate-spin" /> Loading…</div>
          )}
          {error && !result && (
            <div className="flex items-start gap-2 text-sm text-rose-300" data-testid="mod-confirm-fix-error">
              <AlertTriangle size={16} className="mt-0.5 shrink-0" /> {error}
            </div>
          )}
          {!loading && !error && lookup && !result && (
            <>
              {lookup.acceptance_status && lookup.acceptance_status !== 'pending' && (
                <div className="text-xs text-amber-300/80">
                  This link has already been used. Submitting again will overwrite the previous response.
                </div>
              )}
              <p className="text-sm text-white/80">
                The fault you raised has been marked resolved. Is the machine actually back in service?
              </p>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setConfirmed(true)}
                  className={`flex items-center justify-center gap-2 py-3 rounded-lg font-extrabold text-sm border ${confirmed === true ? 'bg-emerald-500/20 border-emerald-400 text-emerald-200' : 'border-white/10 text-white/70 hover:text-white'}`}
                  data-testid="mod-confirm-fix-yes"
                >
                  <Check size={16} /> Yes — fixed
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmed(false)}
                  className={`flex items-center justify-center gap-2 py-3 rounded-lg font-extrabold text-sm border ${confirmed === false ? 'bg-rose-500/20 border-rose-400 text-rose-200' : 'border-white/10 text-white/70 hover:text-white'}`}
                  data-testid="mod-confirm-fix-no"
                >
                  <X size={16} /> Still broken
                </button>
              </div>

              {confirmed !== null && (
                <>
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-wider text-white/60 mb-1.5">
                      How was the service? (optional)
                    </div>
                    <div className="flex items-center gap-1.5" data-testid="mod-confirm-fix-rating">
                      {[1, 2, 3, 4, 5].map((n) => (
                        <button
                          key={n}
                          type="button"
                          onClick={() => setRating(n)}
                          className={n <= rating ? 'text-amber-300' : 'text-white/30 hover:text-white/60'}
                          data-testid={`mod-confirm-fix-star-${n}`}
                          aria-label={`Rate ${n} of 5`}
                        >
                          <Star size={28} fill={n <= rating ? 'currentColor' : 'none'} />
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-wider text-white/60 mb-1.5">
                      Anything to add? (optional)
                    </div>
                    <textarea
                      value={comment}
                      onChange={(e) => setComment(e.target.value)}
                      rows={3}
                      placeholder="e.g. quick fix · belt still squeaks under load · attended within an hour"
                      className="w-full rounded-md border px-3 py-2 text-sm placeholder-white/30 focus:outline-none"
                      style={{ background: 'rgba(255,255,255,0.04)', borderColor: 'rgba(255,255,255,0.1)', color: '#fff' }}
                      data-testid="mod-confirm-fix-comment"
                    />
                    <div className="text-[10px] text-amber-300/70 mt-1">
                      ◆ OFFICIAL only — do not include classified info.
                    </div>
                  </div>

                  <button
                    type="button"
                    disabled={submitting}
                    onClick={submit}
                    className="w-full py-3 rounded-lg font-extrabold uppercase tracking-wider text-sm text-black disabled:opacity-50"
                    style={{ background: '#19CDFF' }}
                    data-testid="mod-confirm-fix-submit"
                  >
                    {submitting ? <Loader2 size={16} className="animate-spin mx-auto" /> : 'Submit response'}
                  </button>
                </>
              )}
            </>
          )}
          {result && (
            <div className="text-sm text-white/80 space-y-2" data-testid="mod-confirm-fix-done">
              <div className="flex items-center gap-2 text-emerald-300 font-bold">
                <Check size={16} /> Response recorded — thank you.
              </div>
              {result.confirmed
                ? <p>Ticket {result.ticket_ref} is now closed. We'll factor your rating into the supplier scorecard.</p>
                : <p>Ticket {result.ticket_ref} has been auto-reopened — the supplier has been notified.</p>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
