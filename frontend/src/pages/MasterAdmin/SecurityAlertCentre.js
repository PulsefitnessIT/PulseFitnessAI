import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  ShieldAlert, RefreshCcw, Download, Search, AlertTriangle,
  Ban, ShieldCheck, Activity, Loader2,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });
const BASE = `${API}/master-admin/security-centre`;

const CATEGORY_LABELS = {
  access_denied: 'Access denied',
  workflow: 'Skip-approval / workflow',
  mass_assignment: 'Mass assignment',
  step_up: 'Step-up',
  financial: 'Invoices',
  stock: 'Stock',
  privileged: 'Privileged',
  abuse: 'Abuse / auto-response',
};

const SEVERITY_STYLE = {
  critical: { bg: 'bg-red-500/15', text: 'text-red-400', dot: 'bg-red-500' },
  warning: { bg: 'bg-amber-500/15', text: 'text-amber-400', dot: 'bg-amber-500' },
  info: { bg: 'bg-sky-500/15', text: 'text-sky-400', dot: 'bg-sky-500' },
};

function fmtTime(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit' }); }
  catch { return iso; }
}
function prettyType(t) { return (t || '').replace(/_/g, ' '); }

export default function SecurityAlertCentre() {
  const [summary, setSummary] = useState(null);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sinceDays, setSinceDays] = useState(7);
  const [category, setCategory] = useState('');
  const [severity, setSeverity] = useState('');
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [live, setLive] = useState(true);
  const [lastRefresh, setLastRefresh] = useState(null);

  // Debounce the search box into debouncedSearch (avoids stale-closure refetch).
  useEffect(() => {
    const id = setTimeout(() => setDebouncedSearch(search.trim()), 400);
    return () => clearTimeout(id);
  }, [search]);

  const load = useCallback(async () => {
    try {
      const params = { since_days: sinceDays, limit: 300 };
      if (category) params.category = category;
      if (severity) params.severity = severity;
      if (debouncedSearch) params.search = debouncedSearch;
      const [sRes, eRes] = await Promise.all([
        axios.get(`${BASE}/summary`, { ...auth(), params: { since_days: sinceDays } }),
        axios.get(`${BASE}/events`, { ...auth(), params }),
      ]);
      setSummary(sRes.data);
      setEvents(eRes.data.events || []);
      setLastRefresh(new Date());
    } catch (e) {
      console.error('security-centre load failed', e);
    } finally {
      setLoading(false);
    }
  }, [sinceDays, category, severity, debouncedSearch]);

  useEffect(() => { load(); }, [load]);

  // Live auto-refresh every 15s.
  useEffect(() => {
    if (!live) return undefined;
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [live, load]);

  const onSearchChange = (v) => setSearch(v);

  const exportCsv = async () => {
    try {
      const params = { since_days: Math.max(sinceDays, 30) };
      if (category) params.category = category;
      if (severity) params.severity = severity;
      if (debouncedSearch) params.search = debouncedSearch;
      const r = await axios.get(`${BASE}/export.csv`, { ...auth(), params, responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement('a');
      a.href = url; a.download = `pulse-security-events.csv`;
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) { console.error('export failed', e); }
  };

  const tiles = useMemo(() => {
    const s = summary || {};
    const sev = s.by_severity || {};
    return [
      { key: 'total', label: 'Events', value: s.total || 0, icon: Activity, tone: 'text-sky-400' },
      { key: 'critical', label: 'Critical', value: sev.critical || 0, icon: AlertTriangle, tone: 'text-red-400' },
      { key: 'warning', label: 'Warnings', value: sev.warning || 0, icon: ShieldAlert, tone: 'text-amber-400' },
      { key: 'denials', label: 'Access denials', value: s.access_denials || 0, icon: Ban, tone: 'text-red-400' },
    ];
  }, [summary]);

  return (
    <div className="space-y-6" data-testid="security-alert-centre">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-red-500/15">
            <ShieldAlert className="h-6 w-6 text-red-400" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-white">Security Alert Centre</h1>
            <p className="text-sm text-white/50">
              Live Zero-Trust telemetry · access denials, cross-tenant/site attempts, skip-approval blocks, step-up & financial events
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setLive((v) => !v)}
            className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium transition-colors ${live ? 'bg-emerald-500/15 text-emerald-400' : 'bg-white/5 text-white/50'}`}
            data-testid="security-live-toggle"
          >
            <span className={`h-2 w-2 rounded-full ${live ? 'bg-emerald-400 animate-pulse' : 'bg-white/30'}`} />
            {live ? 'Live' : 'Paused'}
          </button>
          <button onClick={load} className="inline-flex items-center gap-2 rounded-lg bg-white/5 px-3 py-2 text-xs font-medium text-white/70 hover:bg-white/10" data-testid="security-refresh-btn">
            <RefreshCcw className="h-4 w-4" /> Refresh
          </button>
          <button onClick={exportCsv} className="inline-flex items-center gap-2 rounded-lg bg-white/5 px-3 py-2 text-xs font-medium text-white/70 hover:bg-white/10" data-testid="security-export-btn">
            <Download className="h-4 w-4" /> Export CSV
          </button>
        </div>
      </div>

      {/* KPI tiles */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {tiles.map((t) => (
          <div key={t.key} className="rounded-xl border border-white/10 bg-white/[0.03] p-4" data-testid={`security-tile-${t.key}`}>
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase tracking-wide text-white/40">{t.label}</span>
              <t.icon className={`h-4 w-4 ${t.tone}`} />
            </div>
            <div className={`mt-2 text-2xl font-semibold ${t.tone}`}>{t.value}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <select value={sinceDays} onChange={(e) => setSinceDays(Number(e.target.value))} className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white/80" data-testid="security-since-select">
          <option value={1}>Last 24h</option>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
        <select value={severity} onChange={(e) => setSeverity(e.target.value)} className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white/80" data-testid="security-severity-select">
          <option value="">All severities</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
        </select>
        <div className="flex flex-wrap gap-1.5">
          <button onClick={() => setCategory('')} className={`rounded-full px-3 py-1.5 text-xs ${!category ? 'bg-sky-500/20 text-sky-300' : 'bg-white/5 text-white/50 hover:bg-white/10'}`} data-testid="security-cat-all">All</button>
          {Object.entries(CATEGORY_LABELS).map(([k, label]) => (
            <button key={k} onClick={() => setCategory(k)} className={`rounded-full px-3 py-1.5 text-xs ${category === k ? 'bg-sky-500/20 text-sky-300' : 'bg-white/5 text-white/50 hover:bg-white/10'}`} data-testid={`security-cat-${k}`}>
              {label}{summary?.by_category?.[k] ? ` (${summary.by_category[k]})` : ''}
            </button>
          ))}
        </div>
        <div className="relative ml-auto">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-white/30" />
          <input value={search} onChange={(e) => onSearchChange(e.target.value)} placeholder="Search detail, path, IP, resource…" className="w-64 rounded-lg border border-white/10 bg-black/30 py-2 pl-9 pr-3 text-sm text-white/80 outline-none focus:border-sky-500" data-testid="security-search-input" />
        </div>
      </div>

      {/* Events table */}
      <div className="overflow-hidden rounded-xl border border-white/10">
        <div className="flex items-center justify-between border-b border-white/10 bg-white/[0.02] px-4 py-2 text-xs text-white/40">
          <span>{events.length} event{events.length === 1 ? '' : 's'}</span>
          {lastRefresh && <span>Updated {lastRefresh.toLocaleTimeString('en-GB')}</span>}
        </div>
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-16 text-white/40"><Loader2 className="h-5 w-5 animate-spin" /> Loading…</div>
        ) : events.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-16 text-white/40" data-testid="security-empty">
            <ShieldCheck className="h-8 w-8 text-emerald-400/60" />
            <p className="text-sm">No security events for this filter — all clear.</p>
          </div>
        ) : (
          <div className="max-h-[560px] overflow-auto">
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 bg-[#0f1218] text-xs uppercase tracking-wide text-white/40">
                <tr>
                  <th className="px-4 py-2 font-medium">Time</th>
                  <th className="px-4 py-2 font-medium">Event</th>
                  <th className="px-4 py-2 font-medium">Actor</th>
                  <th className="px-4 py-2 font-medium">Resource</th>
                  <th className="px-4 py-2 font-medium">Detail</th>
                  <th className="px-4 py-2 font-medium">IP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5" data-testid="security-events-table">
                {events.map((e) => {
                  const st = SEVERITY_STYLE[e.severity] || SEVERITY_STYLE.info;
                  return (
                    <tr key={e.id} className="hover:bg-white/[0.02]">
                      <td className="whitespace-nowrap px-4 py-2.5 text-xs text-white/50">{fmtTime(e.created_at)}</td>
                      <td className="px-4 py-2.5">
                        <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${st.bg} ${st.text}`}>
                          <span className={`h-1.5 w-1.5 rounded-full ${st.dot}`} />
                          {prettyType(e.event_type)}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-xs text-white/70">
                        {e.actor_email || e.actor_id || <span className="text-white/30">system</span>}
                        {e.is_master_admin && <span className="ml-1 rounded bg-purple-500/20 px-1 text-[10px] text-purple-300">admin</span>}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-white/50">
                        {e.resource_type ? `${e.resource_type}${e.resource_id ? ` · ${String(e.resource_id).slice(0, 10)}` : ''}` : '—'}
                        {e.action && <div className="text-white/30">{e.action}</div>}
                      </td>
                      <td className="max-w-[260px] truncate px-4 py-2.5 text-xs text-white/60" title={e.detail || ''}>{e.detail || '—'}</td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-xs text-white/40">{e.ip || '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Top actors / IPs */}
      {summary && (summary.top_actors?.length > 0 || summary.top_ips?.length > 0) && (
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <h3 className="mb-3 text-xs font-medium uppercase tracking-wide text-white/40">Most active actors</h3>
            <div className="space-y-1.5">
              {(summary.top_actors || []).map((a) => (
                <div key={a.actor} className="flex items-center justify-between text-sm">
                  <span className="truncate text-white/70">{a.actor}</span>
                  <span className="text-white/40">{a.count}</span>
                </div>
              ))}
              {(summary.top_actors || []).length === 0 && <p className="text-sm text-white/30">None</p>}
            </div>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <h3 className="mb-3 text-xs font-medium uppercase tracking-wide text-white/40">Top source IPs</h3>
            <div className="space-y-1.5">
              {(summary.top_ips || []).map((i) => (
                <div key={i.ip} className="flex items-center justify-between text-sm">
                  <span className="truncate text-white/70">{i.ip}</span>
                  <span className="text-white/40">{i.count}</span>
                </div>
              ))}
              {(summary.top_ips || []).length === 0 && <p className="text-sm text-white/30">None</p>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
