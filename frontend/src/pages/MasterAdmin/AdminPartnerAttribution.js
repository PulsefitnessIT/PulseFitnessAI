/**
 * AdminPartnerAttribution — Iter 220q
 *
 * Master-admin view of the top-of-funnel attribution data captured by
 * iter 220o (Instagram-attributed apply form). Renders the live
 * landings + conversions per UTM source, with conversion rate, mini
 * bar chart, and totals.
 *
 * Data source: GET /api/partners/attribution-summary (master-admin
 * only — already gated server-side).
 *
 * Empty-state copy is explicit: this dashboard counts UTM-tagged
 * landings only (organic traffic lives in your web analytics).
 * Mirrors the comment on the backend track-source endpoint so the
 * UX matches the system rule.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Loader2, BarChart3, TrendingUp, Globe } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

// Iter 220q — small per-source icon hint so the table reads at a glance.
const SOURCE_GLYPHS = {
  instagram: '📷',
  linkedin: '💼',
  facebook: '📘',
  twitter: '🐦',
  tiktok: '🎵',
  email: '📧',
  newsletter: '📬',
  direct: '🔗',
  google: '🔎',
};

export default function AdminPartnerAttribution() {
  const token = useMemo(() => localStorage.getItem('token'), []);
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const [rows, setRows] = useState([]);
  const [totals, setTotals] = useState({ landings: 0, applications_attributed: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchSummary = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const r = await axios.get(`${API}/api/partners/attribution-summary`, { headers });
      setRows(r.data?.rows || []);
      setTotals(r.data?.totals || { landings: 0, applications_attributed: 0 });
    } catch (e) {
      setError(e.response?.data?.detail || 'Could not load attribution summary');
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { fetchSummary(); }, [fetchSummary]);

  // Compute the max-landings so each row's mini bar can be scaled
  // relative to the top source — gives an instant "Instagram is
  // 5x more than LinkedIn" read without a real chart library.
  const maxLandings = useMemo(
    () => rows.reduce((m, r) => Math.max(m, r.landings || 0), 0) || 1,
    [rows],
  );

  // Overall conversion rate across all tagged channels.
  const overallRate = totals.landings
    ? ((totals.applications_attributed / totals.landings) * 100).toFixed(2)
    : '0.00';

  return (
    <section
      className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4"
      data-testid="admin-partner-attribution"
    >
      <header className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <BarChart3 size={14} className="text-purple-500" />
          <h3 className="text-sm font-extrabold uppercase tracking-wider">
            Attribution &amp; conversions
          </h3>
        </div>
        <button
          type="button"
          onClick={fetchSummary}
          className="text-xs font-bold text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 inline-flex items-center gap-1"
          data-testid="admin-attribution-refresh"
        >
          {loading ? <Loader2 size={12} className="animate-spin" /> : 'Refresh'}
        </button>
      </header>

      {/* Top stats — landings, applications, overall conversion rate. */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-4">
        <Stat
          icon={Globe}
          label="UTM landings"
          value={totals.landings.toLocaleString()}
          testId="admin-attr-stat-landings"
        />
        <Stat
          icon={TrendingUp}
          label="Applications attributed"
          value={totals.applications_attributed.toLocaleString()}
          testId="admin-attr-stat-applications"
        />
        <Stat
          icon={BarChart3}
          label="Overall conversion"
          value={`${overallRate}%`}
          testId="admin-attr-stat-conversion"
          accent
        />
      </div>

      {error ? (
        <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2" data-testid="admin-attribution-error">
          {error}
        </div>
      ) : null}

      {loading && !rows.length ? (
        <div className="text-xs text-zinc-500 py-6 text-center">
          <Loader2 size={14} className="animate-spin inline mr-2" />
          Loading attribution data…
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-xl border border-dashed border-zinc-300 dark:border-zinc-700 p-6 text-center" data-testid="admin-attribution-empty">
          <p className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">No tagged traffic yet</p>
          <p className="text-xs text-zinc-500 mt-1 max-w-md mx-auto">
            This panel counts <strong>UTM-tagged</strong> landings only.
            Organic traffic + first-touch SEO stay in your web analytics.
            Tag a campaign URL with{' '}
            <code className="px-1 py-0.5 bg-zinc-100 dark:bg-zinc-800 rounded text-[11px]">
              ?utm_source=instagram
            </code>{' '}
            and refresh to see it appear.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto" data-testid="admin-attribution-table-wrap">
          <table className="w-full text-xs" data-testid="admin-attribution-table">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-wider text-zinc-500 border-b border-zinc-200 dark:border-zinc-800">
                <th className="py-2 pr-3">Source</th>
                <th className="py-2 pr-3">Medium</th>
                <th className="py-2 pr-3">Campaign</th>
                <th className="py-2 pr-3 text-right">Landings</th>
                <th className="py-2 pr-3 w-[140px]">Landings (visual)</th>
                <th className="py-2 pr-3 text-right">Applications</th>
                <th className="py-2 pr-3 text-right">Conversion</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const src = (r.utm_source || '').toLowerCase();
                const glyph = SOURCE_GLYPHS[src] || '🌐';
                const barWidth = `${Math.max(2, (r.landings / maxLandings) * 100)}%`;
                const isHot = r.conversion_rate_pct >= 5;
                return (
                  <tr
                    key={r.key || `${r.utm_source}|${r.utm_medium}|${r.utm_campaign}`}
                    className="border-b border-zinc-100 dark:border-zinc-800/50 hover:bg-zinc-50 dark:hover:bg-zinc-800/30"
                    data-testid={`admin-attribution-row-${r.utm_source || 'unknown'}`}
                  >
                    <td className="py-2 pr-3">
                      <span className="inline-flex items-center gap-1.5 font-semibold">
                        <span aria-hidden>{glyph}</span>
                        <span>{r.utm_source || '—'}</span>
                      </span>
                    </td>
                    <td className="py-2 pr-3 text-zinc-600 dark:text-zinc-400">{r.utm_medium || '—'}</td>
                    <td className="py-2 pr-3 text-zinc-600 dark:text-zinc-400 max-w-[200px] truncate" title={r.utm_campaign || ''}>
                      {r.utm_campaign || '—'}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums font-semibold">
                      {(r.landings || 0).toLocaleString()}
                    </td>
                    <td className="py-2 pr-3">
                      <div className="h-2 rounded-full bg-zinc-100 dark:bg-zinc-800 overflow-hidden">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: barWidth,
                            background: 'linear-gradient(90deg, #2563EB 0%, #9D4CDD 100%)',
                          }}
                          aria-label={`${r.landings} landings`}
                        />
                      </div>
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums font-semibold">
                      {(r.applications || 0).toLocaleString()}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums">
                      <span
                        className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded font-bold ${
                          isHot
                            ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                            : 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300'
                        }`}
                      >
                        {(r.conversion_rate_pct || 0).toFixed(2)}%
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Stat({ icon: Icon, label, value, testId, accent }) {
  return (
    <div
      className={`rounded-xl border p-3 ${
        accent
          ? 'border-transparent text-white'
          : 'border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900'
      }`}
      style={accent ? { background: 'linear-gradient(135deg, #2563EB 0%, #5B5BF5 50%, #9D4CDD 100%)' } : undefined}
      data-testid={testId}
    >
      <div className={`text-[10px] uppercase tracking-wider font-bold inline-flex items-center gap-1 ${accent ? 'text-white/85' : 'text-zinc-500'}`}>
        {Icon ? <Icon size={11} /> : null}
        {label}
      </div>
      <div className={`text-xl font-black mt-1 ${accent ? 'text-white' : ''}`}>{value}</div>
    </div>
  );
}
