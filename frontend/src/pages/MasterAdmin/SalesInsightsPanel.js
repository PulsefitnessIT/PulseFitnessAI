/**
 * Sales Insights — Iter 216bb.
 *
 * Master Admin → Growth → Sales Insights. Surfaces the top sales
 * objections / common prospect questions sourced from the public
 * marketing chat widget. Feeds homepage / pricing-page improvement
 * decisions with real-world data.
 */
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  Sparkles, Loader2, MessageSquare, TrendingUp, Hash, Compass,
  Lightbulb, RefreshCw, Calendar,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function SalesInsightsPanel() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const r = await axios.get(`${API}/api/master-admin/marketing/sales-insights`, {
        headers: { Authorization: `Bearer ${token}` },
        params: { days },
        timeout: 60000,
      });
      setData(r.data);
    } catch (e) {
      setErr(e.response?.data?.detail || e.message || 'Failed to load');
    }
    setLoading(false);
  }, [days, token]);
  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="p-8 text-center" data-testid="sales-insights-loading"><Loader2 size={24} className="animate-spin inline" /></div>;
  if (err) return <div className="p-8 text-center text-rose-500 text-sm" data-testid="sales-insights-error">{err}</div>;
  if (!data) return null;

  return (
    <div className="space-y-6" data-testid="sales-insights">
      {/* Header */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-zinc-700 dark:text-zinc-300">
          <Compass size={16} />
          <span className="text-sm font-bold">Last {days} days · {data.message_count} messages · {data.session_count} sessions</span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <select value={days} onChange={(e) => setDays(parseInt(e.target.value, 10))}
            className="h-8 rounded-md border border-zinc-200 dark:border-zinc-800 bg-transparent text-xs px-2"
            data-testid="sales-insights-days">
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
          <button type="button" onClick={load}
            className="h-8 px-3 rounded-md bg-zinc-100 dark:bg-zinc-800 text-xs font-bold inline-flex items-center gap-1.5"
            data-testid="sales-insights-refresh">
            <RefreshCw size={12} /> Refresh
          </button>
        </div>
      </div>

      {/* Empty-state hint */}
      {data.message_count === 0 && (
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900 p-6 text-center" data-testid="sales-insights-empty">
          <MessageSquare size={20} className="mx-auto text-zinc-400 mb-2" />
          <p className="text-sm font-bold text-zinc-900 dark:text-zinc-100">No prospect chats yet</p>
          <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">As soon as visitors use the marketing AI chat widget, themes and objections will surface here.</p>
        </div>
      )}

      {/* AI themes (when present) */}
      {data.ai_topics?.themes?.length > 0 && (
        <div className="rounded-xl border border-violet-200 dark:border-violet-800/50 bg-gradient-to-br from-violet-50 to-fuchsia-50 dark:from-violet-950/30 dark:to-fuchsia-950/30 p-5" data-testid="sales-insights-ai-themes">
          <p className="text-sm font-bold text-violet-900 dark:text-violet-200 inline-flex items-center gap-2">
            <Sparkles size={14} /> AI-spotted themes (Claude)
          </p>
          <div className="mt-3 grid md:grid-cols-2 gap-3">
            {data.ai_topics.themes.map((t, i) => (
              <div key={i} className="rounded-lg bg-white dark:bg-zinc-900 border border-violet-200/60 dark:border-violet-800/40 p-3" data-testid={`ai-theme-${i}`}>
                <p className="text-sm font-bold text-zinc-900 dark:text-zinc-100">{t.title}</p>
                <p className="text-xs text-zinc-600 dark:text-zinc-400 mt-1">{t.summary}</p>
                <div className="mt-2 flex items-start gap-1.5 text-[11px] text-amber-800 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/30 p-2 rounded">
                  <Lightbulb size={11} className="shrink-0 mt-0.5" />
                  <span>{t.action}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Top questions */}
      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4">
        <p className="text-sm font-bold text-zinc-900 dark:text-zinc-100 mb-3 inline-flex items-center gap-2">
          <MessageSquare size={14} /> Most-asked questions
        </p>
        {data.top_questions.length === 0 ? (
          <p className="text-xs text-zinc-500 dark:text-zinc-400">None yet.</p>
        ) : (
          <ul className="space-y-2 max-h-[420px] overflow-y-auto">
            {data.top_questions.map((q, i) => (
              <li key={i} className="border-b border-zinc-100 dark:border-zinc-800/50 pb-2" data-testid={`sales-q-${i}`}>
                <p className="text-sm text-zinc-900 dark:text-zinc-100 font-semibold leading-snug">"{q.message}"</p>
                <p className="text-[11px] text-zinc-500 dark:text-zinc-400 mt-0.5">From {q.context_path} · {new Date(q.at).toLocaleString()}</p>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Two-column secondary */}
      <div className="grid md:grid-cols-2 gap-4">
        {/* Keywords */}
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4">
          <p className="text-sm font-bold text-zinc-900 dark:text-zinc-100 mb-3 inline-flex items-center gap-2">
            <Hash size={14} /> Top keywords
          </p>
          {data.top_keywords.length === 0 ? (
            <p className="text-xs text-zinc-500 dark:text-zinc-400">No recurring keywords yet.</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {data.top_keywords.map((k) => (
                <span key={k.term}
                  className="text-xs rounded-full bg-zinc-100 dark:bg-zinc-800 px-2.5 py-1 inline-flex items-center gap-1"
                  data-testid={`sales-kw-${k.term}`}>
                  {k.term} <span className="text-zinc-500 tabular-nums">{k.count}</span>
                </span>
              ))}
            </div>
          )}
        </div>

        {/* By path */}
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4">
          <p className="text-sm font-bold text-zinc-900 dark:text-zinc-100 mb-3 inline-flex items-center gap-2">
            <TrendingUp size={14} /> Where chats start
          </p>
          {data.by_path.length === 0 ? (
            <p className="text-xs text-zinc-500 dark:text-zinc-400">No chats yet.</p>
          ) : (
            <ul className="space-y-1.5">
              {data.by_path.map((p) => (
                <li key={p.path} className="flex items-center gap-3 text-xs" data-testid={`sales-path-${p.path}`}>
                  <span className="text-zinc-700 dark:text-zinc-300 truncate flex-1">{p.path || '/'}</span>
                  <span className="font-bold text-zinc-900 dark:text-zinc-100 tabular-nums">{p.count}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Daily volume sparkline-ish */}
      {data.daily_volume.length > 0 && (
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4">
          <p className="text-sm font-bold text-zinc-900 dark:text-zinc-100 mb-3 inline-flex items-center gap-2">
            <Calendar size={14} /> Daily message volume
          </p>
          <DailyBar data={data.daily_volume} />
        </div>
      )}
    </div>
  );
}

function DailyBar({ data }) {
  const max = Math.max(1, ...data.map((d) => d.count));
  return (
    <div className="flex items-end gap-1 h-24" data-testid="sales-daily-volume">
      {data.map((d) => (
        <div key={d.day} title={`${d.day}: ${d.count}`} className="flex-1 min-w-[6px] flex flex-col items-stretch justify-end">
          <div
            className="rounded-t bg-gradient-to-t from-violet-500 to-fuchsia-400"
            style={{ height: `${(d.count / max) * 100}%` }}
          />
          <div className="text-[8px] text-zinc-400 mt-1 truncate text-center">{d.day.slice(5)}</div>
        </div>
      ))}
    </div>
  );
}
