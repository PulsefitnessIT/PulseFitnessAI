/**
 * FreshTrialsTile — fresh trial signups in the last 24h.
 *
 * Iter 216h220 — slots into AdminOverview next to PlatformIssuesTile.
 * Surfaces the prospect intel captured by the trial signup modal's
 * step 2 (Iter 216h219): industry, team size, referral source, UTM
 * tags. One-click row opens Master Admin → Trials so the team can
 * action the lead.
 *
 * Empty state: friendly "No new signups in the last 24h" so the tile
 * is never noisy when growth is quiet.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Sparkles, RefreshCw, ChevronRight, ExternalLink } from 'lucide-react';
import { useAuth } from '@/App';

// Human time-ago for the "started 23m ago" pill.
function timeAgo(iso) {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const diff = Math.max(0, Date.now() - then);
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function FreshTrialsTile({ onGoTrials }) {
  const { API } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const { data: payload } = await axios.get(
        `${API}/master-admin/trials/recent?hours=24&limit=5`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      setData(payload);
    } catch (_) {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [API]);

  useEffect(() => {
    load();
    const id = setInterval(load, 120_000); // refresh every 2 min
    return () => clearInterval(id);
  }, [load]);

  const items = data?.items || [];

  return (
    <div
      data-testid="fresh-trials-tile"
      className="bg-white border border-slate-200 rounded-2xl shadow-[0_1px_2px_rgba(15,23,42,0.04)] p-5 lg:p-6"
    >
      <div className="flex items-center gap-3 mb-4">
        <div className="w-9 h-9 rounded-xl bg-violet-50 flex items-center justify-center">
          <Sparkles size={16} className="text-violet-700" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-slate-500">
            Fresh trial signups · 24h
          </p>
          <p className="text-xs text-slate-400">
            Industry · team size · attribution at a glance
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="text-slate-400 hover:text-slate-700 transition"
          aria-label="Refresh"
          data-testid="fresh-trials-refresh"
          disabled={loading}
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      <div className="flex items-baseline gap-2 mb-4">
        <span
          className="text-4xl font-extrabold tracking-tight text-slate-900"
          data-testid="fresh-trials-count"
        >
          {data ? items.length : '—'}
        </span>
        <span className="text-xs text-slate-500 font-semibold">
          {items.length === 1 ? 'new prospect' : 'new prospects'}
        </span>
      </div>

      {items.length === 0 && !loading && (
        <p className="text-xs text-slate-400 py-4 text-center" data-testid="fresh-trials-empty">
          No new trial signups in the last 24 hours.
        </p>
      )}

      <ul className="divide-y divide-slate-100 -mx-2">
        {items.map((row) => (
          <li key={row.id}>
            <button
              type="button"
              onClick={() => onGoTrials?.()}
              className="w-full text-left px-2 py-2.5 hover:bg-slate-50 transition rounded group"
              data-testid={`fresh-trial-row-${row.id}`}
              title={`Open in Trials${row.owner_email ? ` — ${row.owner_email}` : ''}`}
            >
              <div className="flex items-center gap-2">
                <span className="flex-1 min-w-0">
                  <span className="block text-sm font-semibold text-slate-900 truncate">
                    {row.name || 'Untitled gym'}
                  </span>
                  <span className="block text-[11px] text-slate-500 truncate">
                    {row.owner_email || 'No owner contact'}
                    {row.industry ? ` · ${row.industry}` : ''}
                    {row.employee_count ? ` · ${row.employee_count}` : ''}
                  </span>
                </span>
                <span className="text-[10px] text-slate-400 whitespace-nowrap" data-testid={`fresh-trial-row-${row.id}-age`}>
                  {timeAgo(row.trial_started_at)}
                </span>
                <ChevronRight size={14} className="text-slate-300 group-hover:text-slate-500 transition" />
              </div>
              {/* Attribution chips — only render if we have something */}
              {(row.utm_source || row.referral_source || row.website) && (
                <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                  {row.utm_source && (
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded-full bg-violet-50 text-violet-700 text-[10px] font-bold uppercase tracking-wider" data-testid={`fresh-trial-row-${row.id}-utm`}>
                      {row.utm_source}{row.utm_campaign ? ` · ${row.utm_campaign}` : ''}
                    </span>
                  )}
                  {!row.utm_source && row.referral_source && (
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[10px] font-bold uppercase tracking-wider" data-testid={`fresh-trial-row-${row.id}-ref`}>
                      {row.referral_source}
                    </span>
                  )}
                  {row.website && (
                    <a
                      href={row.website.startsWith('http') ? row.website : `https://${row.website}`}
                      target="_blank"
                      rel="noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-slate-50 text-slate-600 hover:text-slate-900 text-[10px] font-semibold border border-slate-200"
                      data-testid={`fresh-trial-row-${row.id}-website`}
                    >
                      <ExternalLink size={9} /> Site
                    </a>
                  )}
                </div>
              )}
            </button>
          </li>
        ))}
      </ul>

      {items.length > 0 && (
        <button
          type="button"
          onClick={() => onGoTrials?.()}
          className="mt-3 w-full text-xs font-semibold text-slate-500 hover:text-slate-900 inline-flex items-center justify-center gap-1 py-1.5 rounded-md hover:bg-slate-50 transition"
          data-testid="fresh-trials-view-all"
        >
          View all trials <ChevronRight size={12} />
        </button>
      )}
    </div>
  );
}
