/**
 * EngineerRatings — iter 220l.
 *
 * Engineer's own view of their customer feedback. Sits at
 * /svc/engineer/ratings, linked from the Engineer Account Settings
 * drawer. Shows:
 *  • Big avg (★ 4.7) + total count
 *  • Last-30-day trend stat
 *  • Star distribution histogram bars
 *  • Reverse-chronological list of every rating with the comment +
 *    the case it came from (deep-linked to the case detail).
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Star, Loader2, MessageSquare, TrendingUp } from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

function _fmtDate(iso) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }); }
  catch { return ''; }
}

function Stars({ value, size = 14 }) {
  const v = Math.max(0, Math.min(5, Number(value) || 0));
  return (
    <span className="inline-flex items-center gap-0.5" aria-label={`${v} out of 5`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <Star
          key={i}
          size={size}
          className={i <= v ? 'fill-amber-400 text-amber-400' : 'fill-slate-200 text-slate-300'}
        />
      ))}
    </span>
  );
}

export default function EngineerRatings() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/engineer/me/ratings?limit=200`, auth());
      setData(r.data);
    } catch (e) {
      notify.error('Could not load ratings', e?.response?.data?.detail || e?.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const summary = data?.summary || {};
  const ratings = data?.ratings || [];
  const maxBar = useMemo(() => {
    const dist = summary.distribution || {};
    return Math.max(1, ...Object.values(dist));
  }, [summary]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50" data-testid="ratings-loading">
        <Loader2 size={20} className="animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-ratings-page">
      <header className="sticky top-0 z-10 bg-white border-b border-slate-200">
        <div className="max-w-2xl mx-auto px-4 py-3 flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/svc/engineer')}
            className="p-2 -ml-2 rounded-lg hover:bg-slate-100"
            data-testid="ratings-back"
          >
            <ArrowLeft size={18} className="text-slate-700" />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-base font-extrabold text-slate-900">My ratings</h1>
            <p className="text-xs text-slate-500">What customers say about your work.</p>
          </div>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-4 pb-24 space-y-5">
        {/* Summary card */}
        <section className="rounded-2xl border border-slate-200 bg-white p-5" data-testid="ratings-summary">
          {summary.count === 0 ? (
            <div className="text-center py-6">
              <Star size={32} className="mx-auto text-slate-300" />
              <p className="text-sm font-bold text-slate-700 mt-2">No ratings yet</p>
              <p className="text-xs text-slate-500 mt-1">
                Once a customer rates a closed job, it'll appear here.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-end gap-3">
                <div>
                  <p className="text-4xl font-black text-slate-900 leading-none" data-testid="ratings-avg">
                    {(summary.avg ?? 0).toFixed(1)}
                  </p>
                  <Stars value={summary.avg} size={16} />
                </div>
                <div className="ml-auto text-right">
                  <p className="text-xs text-slate-500">from</p>
                  <p className="text-lg font-extrabold text-slate-900" data-testid="ratings-count">
                    {summary.count} reviews
                  </p>
                </div>
              </div>

              {summary.last_30d_count > 0 && (
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-50 border border-emerald-200">
                  <TrendingUp size={14} className="text-emerald-600" />
                  <p className="text-xs text-emerald-900">
                    Last 30 days: <b>{(summary.last_30d_avg ?? 0).toFixed(1)}</b> avg
                    {' '}<span className="text-emerald-700">({summary.last_30d_count})</span>
                  </p>
                </div>
              )}

              <div className="space-y-1.5" data-testid="ratings-histogram">
                {[5, 4, 3, 2, 1].map((stars) => {
                  const n = (summary.distribution || {})[String(stars)] || 0;
                  const pct = (n / maxBar) * 100;
                  return (
                    <div key={stars} className="flex items-center gap-2 text-xs">
                      <span className="w-4 text-right font-bold text-slate-600">{stars}</span>
                      <Star size={10} className="fill-amber-400 text-amber-400" />
                      <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-amber-400 transition-all"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="w-8 text-right font-mono text-slate-500">{n}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </section>

        {/* Reviews list */}
        {ratings.length > 0 && (
          <section data-testid="ratings-list">
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 mb-2">
              Recent reviews
            </p>
            <div className="space-y-2">
              {ratings.map((r) => (
                <button
                  key={r.case_id}
                  type="button"
                  onClick={() => navigate(`/svc/engineer/jobs/${r.case_id}`)}
                  className="w-full text-left rounded-xl border border-slate-200 bg-white hover:bg-slate-50 transition-colors p-3"
                  data-testid={`rating-${r.case_id}`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Stars value={r.rating} size={12} />
                    <span className="text-[11px] font-bold text-slate-700">
                      {r.customer_name || 'Customer'}
                    </span>
                    <span className="ml-auto text-[10px] text-slate-400">
                      {_fmtDate(r.rated_at || r.closed_at)}
                    </span>
                  </div>
                  {r.comment ? (
                    <div className="flex items-start gap-1.5 mt-1.5">
                      <MessageSquare size={11} className="text-slate-400 mt-0.5 flex-shrink-0" />
                      <p className="text-xs text-slate-600 leading-snug">{r.comment}</p>
                    </div>
                  ) : null}
                  <p className="text-[10px] text-slate-400 mt-2">
                    {r.reference ? `${r.reference} · ` : ''}{r.title || 'Job'}
                  </p>
                </button>
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
