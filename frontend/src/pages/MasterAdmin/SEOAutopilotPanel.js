/**
 * SEOAutopilotPanel — Master Admin → Growth → SEO Autopilot (Iter 220ad).
 *
 * Soro-style SEO autopilot for promoting GymAxis itself. Three sub-tabs:
 *
 *   1. Dashboard  — KPIs + recent articles
 *   2. Keywords   — research seeds, queued list, promote-to-article
 *   3. Articles   — drafts, scheduled, published, archived
 *
 * Everything is master-admin-only on the backend; the panel itself is
 * already shielded inside MasterAdmin chrome so we just expose the UI.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import {
  Sparkles, Rocket, BookOpen, Loader2, Plus, RefreshCw,
  AlertTriangle, Eye, Send, Search, FileText, X,
  Share2, Copy, Check, Linkedin, MessageSquare, Clock, ExternalLink,
  PlayCircle, Settings2, TrendingUp, Archive, Trash2,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL;
const auth = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

const SUB_TABS = [
  { id: 'dashboard', label: 'Dashboard',  icon: Rocket },
  { id: 'keywords',  label: 'Keywords',   icon: Search },
  { id: 'articles',  label: 'Articles',   icon: BookOpen },
];

function StatusPill({ status }) {
  const map = {
    queued:    { bg: 'bg-slate-100', text: 'text-slate-700', label: 'Queued' },
    in_use:    { bg: 'bg-blue-100',  text: 'text-blue-800',  label: 'In use' },
    published: { bg: 'bg-green-100', text: 'text-green-800', label: 'Published' },
    ignored:   { bg: 'bg-zinc-100',  text: 'text-zinc-500',  label: 'Ignored' },
    draft:     { bg: 'bg-amber-100', text: 'text-amber-800', label: 'Draft' },
    scheduled: { bg: 'bg-indigo-100',text: 'text-indigo-800',label: 'Scheduled' },
    archived:  { bg: 'bg-rose-100',  text: 'text-rose-700',  label: 'Archived' },
    needs_review: { bg: 'bg-yellow-100', text: 'text-yellow-800', label: 'Needs review' },
  };
  const c = map[status] || { bg: 'bg-zinc-100', text: 'text-zinc-700', label: status || '—' };
  return (
    <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${c.bg} ${c.text}`}>
      {c.label}
    </span>
  );
}

// ── Dashboard ────────────────────────────────────────────────────

function AutopilotStatusCard() {
  const [s, setS] = useState(null);
  const [err, setErr] = useState(null);
  const [running, setRunning] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({
    enabled: true, hour_uk: 9,
    auto_discovery_enabled: true,
    queue_min_threshold: 3,
    queue_target_size: 8,
  });
  const [saving, setSaving] = useState(false);
  const [discovering, setDiscovering] = useState(false);

  const load = async () => {
    try {
      const r = await axios.get(`${API}/api/marketing/seo/autopilot/status`, { headers: auth() });
      setS(r.data);
      setDraft({
        enabled: !!r.data.enabled,
        hour_uk: Number(r.data.hour_uk ?? 9),
        auto_discovery_enabled: r.data.auto_discovery_enabled !== false,
        queue_min_threshold: Number(r.data.queue_min_threshold ?? 3),
        queue_target_size: Number(r.data.queue_target_size ?? 8),
      });
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Could not load autopilot status');
    }
  };
  useEffect(() => { load(); }, []);

  const runNow = async () => {
    if (running) return;
    setRunning(true);
    try {
      const r = await axios.post(`${API}/api/marketing/seo/autopilot/run-now`, {}, { headers: auth() });
      if (r.data?.ok) {
        notify.success('Autopilot run started — fresh article will appear in Articles tab.');
      } else {
        notify.info(r.data?.reason || 'Autopilot already ran today');
      }
      await load();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Run-now failed');
    } finally { setRunning(false); }
  };

  const saveConfig = async () => {
    setSaving(true);
    try {
      await axios.put(`${API}/api/marketing/seo/autopilot/config`,
        {
          enabled: !!draft.enabled,
          hour_uk: Number(draft.hour_uk) || 9,
          auto_discovery_enabled: !!draft.auto_discovery_enabled,
          queue_min_threshold: Number(draft.queue_min_threshold) || 3,
          queue_target_size: Number(draft.queue_target_size) || 8,
        },
        { headers: auth() });
      notify.success('Schedule saved — loop picks it up within 15 minutes.');
      setEditing(false);
      await load();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Save failed');
    } finally { setSaving(false); }
  };

  const discoverNow = async () => {
    if (discovering) return;
    setDiscovering(true);
    try {
      const r = await axios.post(`${API}/api/marketing/seo/keywords/auto-discover`, {}, { headers: auth() });
      if (r.data?.skipped) {
        notify.info(r.data?.reason || 'Queue already topped up');
      } else {
        notify.success(`Added ${r.data?.added_count || 0} keywords (GDPR-safe aggregates)`);
      }
      await load();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Auto-discovery failed');
    } finally { setDiscovering(false); }
  };

  if (err) {
    return (
      <div className="rounded-2xl border border-rose-200 bg-rose-50 text-rose-700 px-4 py-3 text-sm" data-testid="seo-autopilot-status-error">
        {err}
      </div>
    );
  }
  if (!s) {
    return (
      <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 px-4 py-3 text-sm text-zinc-500 inline-flex items-center gap-2">
        <Loader2 size={13} className="animate-spin"/> Loading autopilot status…
      </div>
    );
  }
  const lastDate = s.last_run?.date || '—';
  return (
    <div
      className="rounded-2xl border border-fuchsia-200 dark:border-fuchsia-900 bg-gradient-to-r from-fuchsia-50 via-white to-blue-50 dark:from-zinc-900 dark:via-zinc-900 dark:to-zinc-900 px-5 py-4"
      data-testid="seo-autopilot-status"
    >
      <div className="flex items-center gap-4 flex-wrap">
        <span className="shrink-0 w-10 h-10 rounded-xl bg-gradient-to-br from-amber-400 to-fuchsia-600 text-white flex items-center justify-center">
          <Clock size={16}/>
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-[11px] uppercase tracking-wider font-bold text-fuchsia-700 dark:text-fuchsia-400">
            Daily Autopilot
          </p>
          <p className="text-sm font-bold mt-0.5" data-testid="seo-autopilot-status-headline">
            {s.enabled ? (
              <>Fires daily at <span className="tabular-nums">{String(s.hour_uk).padStart(2, '0')}:00</span> Europe/London</>
            ) : (
              <>Autopilot is paused</>
            )}
          </p>
          <p className="text-[11px] text-zinc-500 mt-0.5">
            {s.ran_today
              ? <>Already fired today ({lastDate}){s.last_run?.manual ? ' · manual run' : ''} — next run tomorrow</>
              : <>Last run: {lastDate}{s.enabled ? ` · Next: today @ ${String(s.hour_uk).padStart(2, '0')}:00` : ''}</>
            }
          </p>
        </div>
        <span
          className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${
            s.ran_today
              ? 'bg-green-100 text-green-800'
              : s.enabled
                ? 'bg-amber-100 text-amber-800'
                : 'bg-zinc-100 text-zinc-600'
          }`}
          data-testid="seo-autopilot-status-pill"
        >
          {s.ran_today ? 'Fired today' : s.enabled ? 'Standby' : 'Off'}
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button" onClick={runNow}
            disabled={running || s.ran_today}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold text-white bg-fuchsia-600 hover:bg-fuchsia-700 disabled:opacity-50 disabled:cursor-not-allowed"
            data-testid="seo-autopilot-run-now"
            title={s.ran_today ? 'Already fired today' : 'Generate today\'s article now'}
          >
            {running ? <Loader2 size={11} className="animate-spin"/> : <PlayCircle size={11}/>}
            Run now
          </button>
          <button
            type="button" onClick={discoverNow}
            disabled={discovering}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold border border-blue-300 text-blue-700 hover:bg-blue-50 disabled:opacity-50"
            data-testid="seo-autopilot-discover-now"
            title="Auto-discover keywords from platform signals + pillars (GDPR-safe, k=5)"
          >
            {discovering ? <Loader2 size={11} className="animate-spin"/> : <Sparkles size={11}/>}
            Discover keywords
          </button>
          <button
            type="button" onClick={() => setEditing((v) => !v)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold border border-zinc-200 dark:border-zinc-700 text-zinc-700 dark:text-zinc-100 hover:border-fuchsia-400"
            data-testid="seo-autopilot-edit-schedule"
          >
            <Settings2 size={11}/> {editing ? 'Close' : 'Schedule'}
          </button>
        </div>
      </div>
      {editing ? (
        <div className="mt-4 pt-4 border-t border-fuchsia-200 dark:border-fuchsia-900 space-y-4" data-testid="seo-autopilot-schedule-editor">
          <div className="grid sm:grid-cols-[auto_auto_1fr] gap-3 items-end">
            <label className="flex items-center gap-2 text-xs font-bold text-zinc-700 dark:text-zinc-200 cursor-pointer">
              <input
                type="checkbox" checked={!!draft.enabled}
                onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
                data-testid="seo-autopilot-enabled-toggle"
              />
              Enabled
            </label>
            <label className="flex items-center gap-2 text-xs font-bold text-zinc-700 dark:text-zinc-200">
              Fire at
              <select
                value={Number(draft.hour_uk)} onChange={(e) => setDraft({ ...draft, hour_uk: Number(e.target.value) })}
                className="text-sm rounded-md border border-zinc-300 px-2 py-1.5"
                data-testid="seo-autopilot-hour-select"
              >
                {Array.from({ length: 24 }).map((_, h) => (
                  <option key={h} value={h}>{String(h).padStart(2, '0')}:00</option>
                ))}
              </select>
              <span className="text-[11px] font-normal text-zinc-500">Europe/London</span>
            </label>
            <div />
          </div>

          <div className="rounded-lg bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-900 p-3" data-testid="seo-autopilot-discovery-config">
            <div className="flex items-start gap-2 mb-3">
              <Sparkles size={14} className="text-blue-700 mt-0.5"/>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-bold text-blue-900 dark:text-blue-200">Auto keyword discovery</p>
                <p className="text-[11px] text-blue-800/80 dark:text-blue-200/70 mt-0.5">
                  Claude chooses meaningful, industry-relevant keywords for you using fitness-industry pillars, your own platform's anonymised aggregate signals (k-anonymity 5, no PII), and content-gap analysis. Tops up the queue automatically when it dips below the threshold.
                </p>
              </div>
            </div>
            <div className="grid sm:grid-cols-3 gap-3">
              <label className="flex items-center gap-2 text-xs font-bold text-blue-900 dark:text-blue-200 cursor-pointer">
                <input
                  type="checkbox" checked={!!draft.auto_discovery_enabled}
                  onChange={(e) => setDraft({ ...draft, auto_discovery_enabled: e.target.checked })}
                  data-testid="seo-auto-discovery-toggle"
                />
                Enable auto-discovery
              </label>
              <label className="flex items-center gap-2 text-xs font-bold text-blue-900 dark:text-blue-200">
                Refill when below
                <input
                  type="number" min={0} max={20}
                  value={draft.queue_min_threshold}
                  onChange={(e) => setDraft({ ...draft, queue_min_threshold: Number(e.target.value) })}
                  className="w-16 text-sm rounded-md border border-blue-300 px-2 py-1"
                  data-testid="seo-auto-min-threshold"
                />
              </label>
              <label className="flex items-center gap-2 text-xs font-bold text-blue-900 dark:text-blue-200">
                Top up to
                <input
                  type="number" min={1} max={30}
                  value={draft.queue_target_size}
                  onChange={(e) => setDraft({ ...draft, queue_target_size: Number(e.target.value) })}
                  className="w-16 text-sm rounded-md border border-blue-300 px-2 py-1"
                  data-testid="seo-auto-target-size"
                />
              </label>
            </div>
          </div>

          <div className="flex justify-end">
            <button
              type="button" onClick={saveConfig} disabled={saving}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold text-white bg-green-600 hover:bg-green-700 disabled:opacity-50"
              data-testid="seo-autopilot-save-config"
            >
              {saving ? <Loader2 size={11} className="animate-spin"/> : <Check size={11}/>}
              Save settings
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

// Key public marketing pages to (re)submit when pinging IndexNow.
const INDEXNOW_KEY_PAGES = [
  '/', '/pricing', '/features', '/blog', '/compare', '/contact', '/security',
  '/platform/crm', '/platform/memberships', '/platform/service',
  '/platform/marketing', '/platform/staffing', '/platform/reporting',
  '/solutions', '/maintenance', '/equipment',
];

function IndexNowCard() {
  const [pinging, setPinging] = useState(false);
  const [result, setResult] = useState(null);

  const ping = async () => {
    if (pinging) return;
    setPinging(true);
    setResult(null);
    try {
      const r = await axios.post(
        `${API}/api/seo/indexnow/ping`,
        { urls: INDEXNOW_KEY_PAGES },
        { headers: auth() },
      );
      setResult(r.data);
      if (r.data?.ok) {
        notify.success(`Pinged ${r.data.submitted} URLs to IndexNow (Bing, Yandex & more).`);
      } else {
        notify.error(`IndexNow ping failed${r.data?.reason ? `: ${r.data.reason}` : ` (status ${r.data?.status || '—'})`}.`);
      }
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not ping search engines');
    } finally {
      setPinging(false);
    }
  };

  return (
    <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 p-4" data-testid="seo-indexnow-card">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Send size={15} className="text-indigo-600" />
            <h3 className="text-sm font-bold">Ping search engines</h3>
          </div>
          <p className="text-xs text-zinc-500 mt-1 max-w-xl">
            Instantly notify Bing, Yandex and other IndexNow engines that your key
            marketing pages changed, so they recrawl sooner. Google doesn't consume
            IndexNow directly but picks the URLs up faster via your live sitemap.
          </p>
          {result && (
            <p className={`text-[11px] mt-2 font-semibold ${result.ok ? 'text-emerald-600' : 'text-rose-600'}`} data-testid="seo-indexnow-result">
              {result.ok
                ? `✓ Submitted ${result.submitted} URLs (status ${result.status}).`
                : `Failed${result.reason ? `: ${result.reason}` : ` (status ${result.status || '—'})`}.`}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={ping}
          disabled={pinging}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-semibold whitespace-nowrap"
          data-testid="seo-indexnow-ping-btn"
        >
          {pinging ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
          {pinging ? 'Pinging…' : 'Ping search engines'}
        </button>
      </div>
    </div>
  );
}

function DashboardTab() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      const r = await axios.get(`${API}/api/marketing/seo/dashboard`, { headers: auth() });
      setData(r.data);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not load dashboard');
    }
  };
  useEffect(() => { load(); }, []);
  if (error) return <div className="text-rose-600 text-sm" data-testid="seo-dashboard-error">{error}</div>;
  if (!data) return <div className="text-zinc-500 text-sm flex items-center gap-2"><Loader2 size={14} className="animate-spin"/> Loading…</div>;

  const tiles = [
    { label: 'Keywords queued',  value: data.keywords.queued,   icon: Search,     hint: `${data.keywords.total} total` },
    { label: 'Articles published', value: data.articles.published, icon: BookOpen, hint: `${data.articles.draft} drafts` },
    { label: 'Articles total',    value: data.articles.total,    icon: FileText,   hint: 'incl. drafts' },
    { label: 'Total blog views',  value: (data.performance?.total_views || 0).toLocaleString(), icon: Eye, hint: 'across all published articles' },
  ];
  const topPerformers = data.performance?.top || [];

  return (
    <div className="space-y-5" data-testid="seo-dashboard">
      <AutopilotStatusCard />
      <IndexNowCard />
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {tiles.map((t) => (
          <div key={t.label} className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 p-4">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">{t.label}</p>
              <t.icon size={14} className="text-zinc-400" />
            </div>
            <p className="text-3xl font-extrabold mt-2 tabular-nums">{t.value ?? 0}</p>
            <p className="text-[11px] text-zinc-500 mt-1">{t.hint}</p>
          </div>
        ))}
      </div>

      {/* Iter 220ai — Top-performing published articles, sorted by
          metrics.views. Empty until the public blog has accumulated
          traffic. */}
      <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 overflow-hidden" data-testid="seo-top-performers">
        <div className="px-5 py-3 border-b border-zinc-100 dark:border-zinc-800 flex items-center gap-2">
          <TrendingUp size={14} className="text-emerald-600" />
          <p className="text-sm font-bold">Top performers</p>
          <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-400">
            Most-viewed published articles
          </span>
        </div>
        <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {topPerformers.length === 0 ? (
            <p className="px-5 py-6 text-sm text-zinc-500" data-testid="seo-top-performers-empty">
              No traffic yet — once the public blog starts getting views, the most-read articles surface here.
            </p>
          ) : topPerformers.map((a, idx) => {
            const trend = a.trend || {};
            const pct = trend.delta_pct;
            const isNew = !!trend.is_new;
            const isUp = (trend.delta_abs || 0) > 0;
            const isDown = (trend.delta_abs || 0) < 0;
            const trendStyle = isNew
              ? 'bg-fuchsia-100 text-fuchsia-700'
              : isUp
                ? 'bg-emerald-100 text-emerald-700'
                : isDown
                  ? 'bg-rose-100 text-rose-700'
                  : 'bg-zinc-100 text-zinc-600';
            const trendLabel = isNew
              ? `+${trend.delta_abs || 0} new`
              : pct === null
                ? `${isUp ? '+' : ''}${trend.delta_abs}`
                : `${pct > 0 ? '+' : ''}${pct}% wk`;
            return (
              <div key={a.id} className="px-5 py-3 flex items-center gap-3" data-testid={`seo-top-${idx}`}>
                <span className="shrink-0 w-7 h-7 rounded-full bg-fuchsia-100 dark:bg-fuchsia-950 text-fuchsia-700 dark:text-fuchsia-300 text-xs font-extrabold inline-flex items-center justify-center">
                  {idx + 1}
                </span>
                <div className="flex-1 min-w-0">
                  <a href={`/blog/${a.slug}`} target="_blank" rel="noreferrer noopener"
                    className="text-sm font-bold truncate hover:underline block"
                  >
                    {a.title}
                  </a>
                  <p className="text-[11px] text-zinc-500 mt-0.5">
                    /{a.slug} · {a.read_time_min} min read · {a.primary_keyword || '—'}
                  </p>
                </div>
                <span
                  className={`shrink-0 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${trendStyle}`}
                  data-testid={`seo-top-${idx}-trend`}
                  title={isNew ? 'Published in the last 7 days' : `${trend.views_7d_ago || 0} views 7 days ago`}
                >
                  {trendLabel}
                </span>
                <div className="text-right">
                  <p className="text-base font-extrabold tabular-nums">{(a.metrics?.views || 0).toLocaleString()}</p>
                  <p className="text-[10px] uppercase tracking-wider font-bold text-zinc-400">views</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 overflow-hidden">
        <div className="px-5 py-3 border-b border-zinc-100 dark:border-zinc-800 flex items-center gap-2">
          <BookOpen size={14} className="text-fuchsia-600" />
          <p className="text-sm font-bold">Recent activity</p>
        </div>
        <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {data.recent.length === 0 ? (
            <p className="px-5 py-6 text-sm text-zinc-500">
              No articles yet. Generate your first one from the Keywords tab.
            </p>
          ) : data.recent.map((a) => (
            <div key={a.id} className="px-5 py-3 flex items-center gap-3" data-testid={`seo-recent-${a.id}`}>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-bold truncate">{a.title}</p>
                <p className="text-[11px] text-zinc-500 mt-0.5">
                  /{a.slug} · {a.read_time_min} min read · {a.metrics?.views || 0} views
                </p>
              </div>
              <StatusPill status={a.status} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Keywords ─────────────────────────────────────────────────────

function KeywordsTab({ onArticleGenerated }) {
  const [list, setList] = useState([]);
  const [seed, setSeed] = useState('');
  const [audience, setAudience] = useState('Gym owners and multi-site operators');
  const [count, setCount] = useState(10);
  const [researching, setResearching] = useState(false);
  const [generatingKw, setGeneratingKw] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      const r = await axios.get(`${API}/api/marketing/seo/keywords`, { headers: auth() });
      setList(r.data.keywords || []);
    } catch (e) { setError(e?.response?.data?.detail || 'Load failed'); }
  };
  useEffect(() => { load(); }, []);

  const research = async (e) => {
    e?.preventDefault?.();
    if (!seed.trim()) return;
    setResearching(true); setError(null);
    try {
      const r = await axios.post(
        `${API}/api/marketing/seo/keywords/research`,
        { seed_topic: seed, audience, count: Number(count) || 10 },
        { headers: auth() },
      );
      notify.success(`Added ${r.data.count} keywords`);
      setSeed('');
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail || 'Research failed');
    } finally { setResearching(false); }
  };

  const generate = async (kw) => {
    setGeneratingKw(kw.id);
    try {
      const r = await axios.post(
        `${API}/api/marketing/seo/articles/generate`,
        { primary_keyword: kw.term, angle: kw.rationale, publish_now: false, generate_hero_image: true },
        { headers: auth() },
      );
      // Mark keyword in_use
      await axios.patch(
        `${API}/api/marketing/seo/keywords/${kw.id}`,
        { status: 'in_use' }, { headers: auth() },
      );
      notify.success('Article drafted');
      onArticleGenerated?.(r.data);
      await load();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Generation failed');
    } finally { setGeneratingKw(null); }
  };

  return (
    <div className="space-y-5" data-testid="seo-keywords">
      <form
        onSubmit={research}
        className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-gradient-to-br from-fuchsia-50 via-white to-blue-50 dark:from-zinc-900 dark:via-zinc-900 dark:to-zinc-900 p-5 space-y-3"
        data-testid="seo-research-form"
      >
        <div className="flex items-center gap-2">
          <Sparkles size={16} className="text-fuchsia-600" />
          <h3 className="text-base font-bold">Research SEO keywords with Claude</h3>
        </div>
        <p className="text-xs text-zinc-500">
          Drop a seed topic, get long-tail keyword ideas with intent + difficulty.
          Promote any one to a full draft article in a single click.
        </p>
        <div className="grid sm:grid-cols-[2fr_1fr_auto] gap-2">
          <input
            type="text" value={seed} onChange={(e) => setSeed(e.target.value)}
            placeholder="Seed topic — e.g. 'gym equipment downtime'"
            className="text-sm rounded-md border border-zinc-300 px-3 py-2 focus:border-fuchsia-500 focus:ring-1 focus:ring-fuchsia-500 outline-none"
            data-testid="seo-research-seed"
            required
          />
          <input
            type="number" value={count} onChange={(e) => setCount(e.target.value)}
            min={3} max={30}
            className="text-sm rounded-md border border-zinc-300 px-3 py-2 outline-none"
            data-testid="seo-research-count"
          />
          <button
            type="submit" disabled={researching}
            className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-md text-sm font-bold text-white bg-fuchsia-600 hover:bg-fuchsia-700 disabled:opacity-50"
            data-testid="seo-research-btn"
          >
            {researching ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
            Research
          </button>
        </div>
        <input
          type="text" value={audience} onChange={(e) => setAudience(e.target.value)}
          className="w-full text-sm rounded-md border border-zinc-300 px-3 py-2 outline-none"
          placeholder="Audience"
          data-testid="seo-research-audience"
        />
      </form>

      {error ? (
        <div className="rounded-md border border-rose-200 bg-rose-50 text-rose-700 px-3 py-2 text-sm inline-flex items-center gap-2" data-testid="seo-keywords-error">
          <AlertTriangle size={14}/> {error}
        </div>
      ) : null}

      <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 overflow-hidden">
        <div className="px-5 py-3 border-b border-zinc-100 dark:border-zinc-800 flex items-center justify-between">
          <p className="text-sm font-bold">Keyword library</p>
          <button onClick={load} className="text-[11px] inline-flex items-center gap-1 text-zinc-500 hover:text-zinc-900" data-testid="seo-keywords-refresh">
            <RefreshCw size={11}/> Refresh
          </button>
        </div>
        {list.length === 0 ? (
          <p className="px-5 py-10 text-sm text-zinc-500 text-center">
            No keywords yet. Research a seed topic above to get started.
          </p>
        ) : (
          <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {list.map((kw) => (
              <div key={kw.id} className="px-5 py-3 flex items-center gap-3" data-testid={`seo-kw-${kw.id}`}>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-bold truncate">{kw.term}</p>
                    <StatusPill status={kw.status} />
                    <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">
                      {kw.intent} · {kw.difficulty} · {kw.volume_estimate}
                    </span>
                  </div>
                  {kw.rationale ? (
                    <p className="text-[12px] text-zinc-500 mt-1">{kw.rationale}</p>
                  ) : null}
                </div>
                {kw.status === 'queued' ? (
                  <button
                    onClick={() => generate(kw)} disabled={generatingKw === kw.id}
                    className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md text-xs font-bold text-white bg-fuchsia-600 hover:bg-fuchsia-700 disabled:opacity-50"
                    data-testid={`seo-kw-generate-${kw.id}`}
                  >
                    {generatingKw === kw.id ? <Loader2 size={11} className="animate-spin"/> : <Plus size={11}/>}
                    Generate article
                  </button>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Articles ─────────────────────────────────────────────────────

// CopyableBlock — reused for every distribution snippet.
function CopyableBlock({ value, label, testIdBase, hint, postedAt }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      notify.success(`${label} copied`);
      setTimeout(() => setCopied(false), 2200);
    } catch (_e) {
      notify.error('Could not copy — select manually');
    }
  };
  return (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900 p-3 relative">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[10px] uppercase tracking-wider font-bold text-zinc-500">{label}</span>
        <div className="flex items-center gap-2">
          {postedAt ? (
            <span
              className="text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-full bg-green-100 text-green-800 inline-flex items-center gap-1"
              data-testid={`${testIdBase}-posted-pill`}
              title={`Opened share window at ${postedAt}`}
            >
              <Check size={9}/> Posted
            </span>
          ) : null}
          {hint ? <span className="text-[10px] text-zinc-400">{hint}</span> : null}
        </div>
      </div>
      <pre
        className="text-[12px] text-zinc-800 dark:text-zinc-200 whitespace-pre-wrap break-words font-sans leading-relaxed pr-10"
        data-testid={`${testIdBase}-text`}
      >{value}</pre>
      <button
        type="button" onClick={copy}
        className="absolute top-2 right-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 hover:opacity-90"
        data-testid={`${testIdBase}-copy`}
      >
        {copied ? <Check size={9} /> : <Copy size={9} />}
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  );
}

// PublishButton — Iter 220af. 1-click open of the platform-native share
// intent URL. The backend also stamps a "posted" record so the UI can
// show the green "Posted" pill on subsequent loads.
function PublishButton({ articleId, channel, index, onPosted, label }) {
  const [busy, setBusy] = useState(false);
  const publish = async () => {
    setBusy(true);
    try {
      const r = await axios.post(
        `${API}/api/marketing/seo/articles/${articleId}/publish-share`,
        { channel, index },
        { headers: auth() },
      );
      const url = r.data?.share_url;
      if (url) {
        window.open(url, '_blank', 'noopener,noreferrer');
        notify.success(`Opening ${label} composer — tap "Post" there to finish.`);
        onPosted?.();
      } else {
        notify.error('No share URL returned');
      }
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Publish failed');
    } finally { setBusy(false); }
  };
  const isLinkedIn = channel === 'linkedin';
  return (
    <button
      type="button" onClick={publish} disabled={busy}
      className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-bold text-white ${isLinkedIn ? '' : 'bg-zinc-900 hover:bg-black'} disabled:opacity-50`}
      style={isLinkedIn ? { backgroundColor: 'var(--color-brand-linkedin)' } : undefined}
      onMouseEnter={isLinkedIn ? (e) => { e.currentTarget.style.backgroundColor = 'var(--color-brand-linkedin-deep)'; } : undefined}
      onMouseLeave={isLinkedIn ? (e) => { e.currentTarget.style.backgroundColor = 'var(--color-brand-linkedin)'; } : undefined}
      data-testid={`seo-publish-${channel}-${index}`}
      title={`Open ${label} composer with this post pre-filled`}
    >
      {busy ? <Loader2 size={10} className="animate-spin"/> : <ExternalLink size={10}/>}
      Post to {label}
    </button>
  );
}

// DistributionDrawer — Iter 220ae. Spins one article into 5 LinkedIn
// posts + 1 X thread + 1 Reddit summary using Claude on the server.
function DistributionDrawer({ article, onClose }) {
  const [dist, setDist] = useState(null);
  const [loading, setLoading] = useState(true);
  const [spinning, setSpinning] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(
        `${API}/api/marketing/seo/articles/${article.id}/distributions`,
        { headers: auth() },
      );
      setDist(r.data?.distribution || null);
    } catch (_e) {
      setDist(null);
    } finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load();   }, [article.id]);

  const spin = async () => {
    setSpinning(true);
    try {
      const r = await axios.post(
        `${API}/api/marketing/seo/articles/${article.id}/distribute`,
        { channels: ['linkedin', 'x_thread', 'reddit'] },
        { headers: auth() },
      );
      setDist(r.data);
      notify.success('Spun into LinkedIn + X + Reddit');
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Spin failed');
    } finally { setSpinning(false); }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex justify-end"
      data-testid="seo-distribution-drawer"
      onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}
    >
      <div className="bg-white dark:bg-zinc-950 w-full max-w-2xl h-full flex flex-col">
        <header className="px-5 py-3 border-b border-zinc-100 dark:border-zinc-800 flex items-center gap-3">
          <Share2 size={16} className="text-fuchsia-600"/>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-bold truncate">Distribute · {article.title}</p>
            <p className="text-[11px] text-zinc-500">5 LinkedIn posts · 1 X thread · 1 Reddit summary</p>
          </div>
          <button
            onClick={spin} disabled={spinning}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md text-xs font-bold text-white bg-fuchsia-600 hover:bg-fuchsia-700 disabled:opacity-50"
            data-testid="seo-distribution-spin-btn"
          >
            {spinning ? <Loader2 size={11} className="animate-spin"/> : <Sparkles size={11}/>}
            {dist ? 'Re-spin' : 'Spin posts'}
          </button>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-900" aria-label="Close">
            <X size={16}/>
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {loading ? (
            <div className="text-zinc-500 text-sm inline-flex items-center gap-2">
              <Loader2 size={14} className="animate-spin"/> Loading…
            </div>
          ) : !dist ? (
            <div className="rounded-xl border border-dashed border-zinc-300 dark:border-zinc-700 p-6 text-center">
              <Share2 size={20} className="text-zinc-300 mx-auto mb-1"/>
              <p className="text-sm font-bold">No distribution yet</p>
              <p className="text-[12px] text-zinc-500 mt-1 mb-3">
                Click "Spin posts" to generate channel-native content from this article.
              </p>
              <button
                onClick={spin} disabled={spinning}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md text-xs font-bold text-white bg-fuchsia-600 hover:bg-fuchsia-700 disabled:opacity-50"
                data-testid="seo-distribution-first-spin-btn"
              >
                {spinning ? <Loader2 size={11} className="animate-spin"/> : <Sparkles size={11}/>}
                Spin posts
              </button>
            </div>
          ) : (
            <>
              {dist.content?.linkedin?.length ? (
                <section data-testid="seo-distribution-linkedin">
                  <div className="flex items-center gap-2 mb-3">
                    <Linkedin size={14} style={{ color: 'var(--color-brand-linkedin)' }}/>
                    <h3 className="text-sm font-bold">LinkedIn · 5 angles</h3>
                  </div>
                  <div className="space-y-3">
                    {dist.content.linkedin.map((post, i) => (
                      <div key={i} className="space-y-1.5">
                        <CopyableBlock
                          value={post}
                          label={`Post ${i + 1}`}
                          hint={`${post.length} chars`}
                          testIdBase={`seo-distribution-linkedin-${i}`}
                          postedAt={dist.published?.linkedin?.[i]?.posted_at}
                        />
                        <div className="flex justify-end">
                          <PublishButton
                            articleId={article.id}
                            channel="linkedin"
                            index={i}
                            label="LinkedIn"
                            onPosted={load}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              ) : null}

              {dist.content?.x_thread?.length ? (
                <section data-testid="seo-distribution-x-thread">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <MessageSquare size={14} className="text-zinc-900 dark:text-zinc-100"/>
                      <h3 className="text-sm font-bold">X · {dist.content.x_thread.length}-tweet thread</h3>
                    </div>
                    <PublishButton
                      articleId={article.id}
                      channel="x"
                      index={0}
                      label="X"
                      onPosted={load}
                    />
                  </div>
                  <CopyableBlock
                    value={dist.content.x_thread.map((t, i) => `${i + 1}/ ${t}`).join('\n\n')}
                    label="Full thread"
                    hint="Paste each tweet separately on X"
                    testIdBase="seo-distribution-x-full"
                    postedAt={dist.published?.x?.['0']?.posted_at}
                  />
                  <div className="mt-2 space-y-2">
                    {dist.content.x_thread.map((tweet, i) => (
                      <CopyableBlock
                        key={i} value={tweet}
                        label={`Tweet ${i + 1}/${dist.content.x_thread.length}`}
                        hint={`${tweet.length} chars`}
                        testIdBase={`seo-distribution-x-${i}`}
                      />
                    ))}
                  </div>
                </section>
              ) : null}

              {dist.content?.reddit ? (
                <section data-testid="seo-distribution-reddit">
                  <div className="flex items-center gap-2 mb-3">
                    <MessageSquare size={14} className="text-orange-600"/>
                    <h3 className="text-sm font-bold">Reddit · long-form summary</h3>
                  </div>
                  <div className="space-y-3">
                    <CopyableBlock
                      value={dist.content.reddit.title}
                      label="Title"
                      testIdBase="seo-distribution-reddit-title"
                    />
                    <CopyableBlock
                      value={dist.content.reddit.body}
                      label="Body (Markdown)"
                      testIdBase="seo-distribution-reddit-body"
                    />
                    {dist.content.reddit.subreddits?.length ? (
                      <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 p-3">
                        <p className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-2">
                          Suggested subreddits
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                          {dist.content.reddit.subreddits.map((s) => (
                            <a
                              key={s}
                              href={`https://www.reddit.com/r/${s}`}
                              target="_blank" rel="noreferrer noopener"
                              className="text-[11px] font-bold px-2 py-1 rounded-md bg-orange-50 text-orange-700 hover:bg-orange-100"
                            >
                              r/{s}
                            </a>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </div>
                </section>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function ArticleEditor({ article, onClose, onSaved }) {
  const [doc, setDoc] = useState(article);
  const [saving, setSaving] = useState(false);

  const set = (k) => (e) => setDoc({ ...doc, [k]: e.target?.value ?? e });

  const save = async (status) => {
    setSaving(true);
    try {
      const r = await axios.patch(
        `${API}/api/marketing/seo/articles/${article.id}`,
        { title: doc.title, excerpt: doc.excerpt, body_md: doc.body_md, status },
        { headers: auth() },
      );
      notify.success(status === 'published' ? 'Published' : 'Saved');
      onSaved?.(r.data);
      onClose?.();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Save failed');
    } finally { setSaving(false); }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-stretch justify-center p-4 overflow-y-auto"
      data-testid="seo-article-editor"
      onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}
    >
      <div className="bg-white dark:bg-zinc-950 rounded-2xl w-full max-w-4xl my-auto flex flex-col max-h-[92vh]">
        <header className="px-5 py-3 border-b border-zinc-100 dark:border-zinc-800 flex items-center gap-3">
          <p className="flex-1 text-sm font-bold truncate">Edit article</p>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-900" data-testid="seo-editor-close" aria-label="Close">
            <X size={16}/>
          </button>
        </header>
        <div className="flex-1 overflow-y-auto p-5 space-y-3">
          <input
            type="text" value={doc.title || ''} onChange={set('title')}
            className="w-full text-lg font-bold rounded-md border border-zinc-300 px-3 py-2"
            data-testid="seo-editor-title"
            placeholder="Article title"
          />
          <textarea
            rows={2} value={doc.excerpt || ''} onChange={set('excerpt')}
            className="w-full text-sm rounded-md border border-zinc-300 px-3 py-2 resize-none"
            placeholder="Excerpt"
            data-testid="seo-editor-excerpt"
          />
          {doc.hero_image_url ? (
            <img src={doc.hero_image_url} alt="" className="w-full max-h-64 object-cover rounded-md border border-zinc-200" />
          ) : null}
          <textarea
            rows={20} value={doc.body_md || ''} onChange={set('body_md')}
            className="w-full text-sm rounded-md border border-zinc-300 px-3 py-2 font-mono leading-relaxed"
            placeholder="# Article body (Markdown)"
            data-testid="seo-editor-body"
          />
        </div>
        <footer className="px-5 py-3 border-t border-zinc-100 dark:border-zinc-800 flex items-center justify-end gap-2">
          <span className="text-[11px] text-zinc-500 mr-auto">{(doc.body_md || '').split(/\s+/).filter(Boolean).length} words</span>
          <button onClick={() => save('draft')} disabled={saving}
            className="px-3 py-1.5 rounded-md text-xs font-bold border border-zinc-300 hover:border-zinc-500"
            data-testid="seo-editor-save-draft">
            Save draft
          </button>
          <button onClick={() => save('published')} disabled={saving}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md text-xs font-bold text-white bg-green-600 hover:bg-green-700 disabled:opacity-50"
            data-testid="seo-editor-publish">
            {saving ? <Loader2 size={11} className="animate-spin"/> : <Send size={11}/>}
            Publish
          </button>
        </footer>
      </div>
    </div>
  );
}

function ArticlesTab() {
  const [list, setList] = useState([]);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null);
  const [distributing, setDistributing] = useState(null);
  // Iter 220ai — view-sortable list. Default to "recent" so the
  // operator sees just-published work first; toggle to "views" to
  // surface the most-trafficked articles.
  const [sortBy, setSortBy] = useState('recent');
  // Iter 220bj — duplicate-content audit panel state.
  const [dupes, setDupes] = useState(null);
  const [dupesLoading, setDupesLoading] = useState(false);
  const [archivingId, setArchivingId] = useState(null);

  const load = async () => {
    try {
      const r = await axios.get(`${API}/api/marketing/seo/articles`, { headers: auth() });
      setList(r.data.articles || []);
    } catch (e) { setError(e?.response?.data?.detail || 'Load failed'); }
  };
  useEffect(() => { load(); }, []);

  const open = async (a) => {
    try {
      const r = await axios.get(`${API}/api/marketing/seo/articles/${a.id}`, { headers: auth() });
      setEditing(r.data);
    } catch (e) {
      notify.error('Could not open article');
    }
  };

  const findDuplicates = async () => {
    setDupesLoading(true);
    try {
      const r = await axios.get(`${API}/api/marketing/seo/articles/duplicates?threshold=0.55`, { headers: auth() });
      setDupes(r.data);
      if (!r.data.pairs?.length) {
        notify.success('No duplicates detected at this threshold');
      }
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Duplicate scan failed');
    } finally {
      setDupesLoading(false);
    }
  };

  const archive = async (id) => {
    if (!window.confirm('Archive this article? It will disappear from the public blog immediately.')) return;
    setArchivingId(id);
    try {
      await axios.post(`${API}/api/marketing/seo/articles/${id}/archive`, {}, { headers: auth() });
      notify.success('Article archived');
      await load();
      // Refresh the duplicate panel too — the archived one will drop out.
      if (dupes) {
        setDupes({
          ...dupes,
          pairs: dupes.pairs.filter((p) => p.a.id !== id && p.b.id !== id),
        });
      }
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Archive failed');
    } finally {
      setArchivingId(null);
    }
  };

  const sorted = [...list].sort((a, b) => {
    if (sortBy === 'views') {
      return (b.metrics?.views || 0) - (a.metrics?.views || 0);
    }
    return new Date(b.updated_at || 0) - new Date(a.updated_at || 0);
  });

  return (
    <div className="space-y-5" data-testid="seo-articles">
      {/* Iter 220bj — duplicate-content audit panel */}
      <div className="rounded-2xl border border-amber-200 bg-amber-50/50 dark:bg-amber-950/20 dark:border-amber-900/40 p-4" data-testid="seo-dup-audit">
        <div className="flex items-start gap-3 flex-wrap">
          <div className="shrink-0 w-9 h-9 rounded-xl bg-amber-100 text-amber-700 flex items-center justify-center">
            <AlertTriangle size={16}/>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-extrabold text-amber-900 dark:text-amber-200">Blog freshness check</p>
            <p className="text-[12px] text-amber-800/80 dark:text-amber-200/70 mt-0.5">
              Scan every published article for near-identical title + opener pairs. Useful for sweeping old duplicates that pre-dated the new freshness gate.
            </p>
          </div>
          <button
            type="button"
            onClick={findDuplicates}
            disabled={dupesLoading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-60"
            data-testid="seo-find-duplicates-btn"
          >
            {dupesLoading ? <Loader2 size={12} className="animate-spin"/> : <Search size={12}/>}
            {dupesLoading ? 'Scanning…' : 'Find duplicates'}
          </button>
        </div>
        {dupes && dupes.pairs?.length > 0 ? (
          <div className="mt-3 space-y-2" data-testid="seo-dup-pairs">
            {dupes.pairs.map((p, i) => (
              <div key={i} className="rounded-lg bg-white dark:bg-zinc-950 border border-amber-200 dark:border-amber-900/40 p-3 text-[12px]" data-testid={`seo-dup-pair-${i}`}>
                <p className="font-bold text-amber-700 mb-1.5">Similarity {Math.round(p.score * 100)}%</p>
                {[p.a, p.b].map((side, idx) => (
                  <div key={side.id} className="flex items-center justify-between gap-2 py-1 border-t border-amber-100 first:border-t-0">
                    <div className="min-w-0">
                      <p className="font-semibold truncate">{side.title}</p>
                      <p className="text-[10px] text-zinc-500">/{side.slug} · published {side.published_at?.slice(0, 10) || '—'}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => archive(side.id)}
                      disabled={archivingId === side.id}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-bold border border-rose-300 text-rose-700 hover:bg-rose-50 disabled:opacity-60 shrink-0"
                      data-testid={`seo-dup-archive-${i}-${idx}`}
                    >
                      {archivingId === side.id ? <Loader2 size={11} className="animate-spin"/> : <Archive size={11}/>}
                      Archive
                    </button>
                  </div>
                ))}
              </div>
            ))}
          </div>
        ) : dupes && dupes.pairs?.length === 0 ? (
          <p className="mt-3 text-[12px] text-emerald-700 font-bold" data-testid="seo-dup-empty">
            <Check size={12} className="inline mr-1"/> No duplicate pairs found at the current threshold.
          </p>
        ) : null}
      </div>

      <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 overflow-hidden">
        <div className="px-5 py-3 border-b border-zinc-100 dark:border-zinc-800 flex items-center justify-between gap-3 flex-wrap">
          <p className="text-sm font-bold">Articles</p>
          <div className="flex items-center gap-2">
            <div className="inline-flex rounded-md border border-zinc-200 dark:border-zinc-800 overflow-hidden" data-testid="seo-articles-sort">
              <button
                type="button" onClick={() => setSortBy('recent')}
                className={`px-2.5 py-1 text-[11px] font-bold ${sortBy === 'recent' ? 'bg-fuchsia-600 text-white' : 'text-zinc-600 hover:text-zinc-900'}`}
                data-testid="seo-articles-sort-recent"
              >
                Recent
              </button>
              <button
                type="button" onClick={() => setSortBy('views')}
                className={`px-2.5 py-1 text-[11px] font-bold inline-flex items-center gap-1 ${sortBy === 'views' ? 'bg-fuchsia-600 text-white' : 'text-zinc-600 hover:text-zinc-900'}`}
                data-testid="seo-articles-sort-views"
              >
                <Eye size={10}/> Views
              </button>
            </div>
            <button onClick={load} className="text-[11px] inline-flex items-center gap-1 text-zinc-500 hover:text-zinc-900">
              <RefreshCw size={11}/> Refresh
            </button>
          </div>
        </div>
        {error ? <p className="px-5 py-3 text-sm text-rose-600" data-testid="seo-articles-error">{error}</p> : null}
        {sorted.length === 0 ? (
          <p className="px-5 py-10 text-sm text-zinc-500 text-center">
            No articles yet. Generate one from the Keywords tab.
          </p>
        ) : (
          <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {sorted.map((a) => (
              <div key={a.id} className="px-5 py-3 flex items-center gap-3" data-testid={`seo-article-${a.id}`}>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-bold truncate">{a.title}</p>
                    <StatusPill status={a.status} />
                  </div>
                  <p className="text-[11px] text-zinc-500 mt-0.5">
                    /{a.slug} · {a.read_time_min} min · {a.word_count} words
                  </p>
                </div>
                {/* Iter 220ai — per-article view tally as a sortable column */}
                <div className="text-right shrink-0 min-w-[58px]" data-testid={`seo-article-views-${a.id}`}>
                  <p className="text-sm font-extrabold tabular-nums">{(a.metrics?.views || 0).toLocaleString()}</p>
                  <p className="text-[9px] uppercase tracking-wider font-bold text-zinc-400">views</p>
                </div>
                {a.status === 'published' ? (
                  <a href={`/blog/${a.slug}`} target="_blank" rel="noreferrer noopener"
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-bold border border-zinc-200 hover:border-fuchsia-400"
                    data-testid={`seo-article-view-${a.id}`}
                  >
                    <Eye size={11}/> View
                  </a>
                ) : null}
                {/* Iter 220ae — distribution drawer launcher */}
                <button onClick={() => setDistributing(a)}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-bold border border-fuchsia-200 text-fuchsia-700 hover:bg-fuchsia-50"
                  data-testid={`seo-article-distribute-${a.id}`}
                  title="Spin into LinkedIn / X / Reddit posts"
                >
                  <Share2 size={11}/> Distribute
                </button>
                <button onClick={() => open(a)}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-bold bg-fuchsia-600 text-white hover:bg-fuchsia-700"
                  data-testid={`seo-article-edit-${a.id}`}
                >
                  Edit
                </button>
                {a.status !== 'archived' ? (
                  <button onClick={() => archive(a.id)}
                    disabled={archivingId === a.id}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-bold border border-rose-200 text-rose-700 hover:bg-rose-50 disabled:opacity-60"
                    data-testid={`seo-article-archive-${a.id}`}
                    title="Archive this article (removes it from the public blog)"
                  >
                    {archivingId === a.id ? <Loader2 size={11} className="animate-spin"/> : <Trash2 size={11}/>}
                  </button>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </div>
      {editing ? <ArticleEditor article={editing} onClose={() => setEditing(null)} onSaved={() => load()} /> : null}
      {distributing ? <DistributionDrawer article={distributing} onClose={() => setDistributing(null)} /> : null}
    </div>
  );
}

// ── Shell ────────────────────────────────────────────────────────

export default function SEOAutopilotPanel() {
  const [tab, setTab] = useState('dashboard');
  const [bump, setBump] = useState(0);

  return (
    <div className="space-y-5" data-testid="seo-autopilot">
      <header className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-gradient-to-r from-fuchsia-50 via-white to-blue-50 dark:from-zinc-900 dark:via-zinc-900 dark:to-zinc-900 px-5 py-4 flex items-center gap-4">
        <span className="shrink-0 w-12 h-12 rounded-2xl bg-gradient-to-br from-amber-400 to-fuchsia-600 text-white flex items-center justify-center shadow-[0_8px_20px_-8px_rgba(217,70,239,0.6)]">
          <Sparkles size={20} />
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-[11px] uppercase tracking-[0.18em] font-bold text-fuchsia-700 dark:text-fuchsia-400">
            Growth · SEO Autopilot
          </p>
          <h2 className="text-xl sm:text-2xl font-extrabold text-zinc-900 dark:text-zinc-50 tracking-tight mt-0.5">
            Rank GymAxis on Google &amp; ChatGPT
          </h2>
          <p className="text-xs sm:text-sm text-zinc-600 dark:text-zinc-300 mt-1 max-w-2xl">
            Research keywords · generate 1500-word articles with on-brand voice
            · auto-publish to the blog · get cited by AI overviews.
            Saves £2k+/mo vs. agency / Soro.
          </p>
        </div>
      </header>

      <div className="flex items-center gap-1 border-b border-zinc-200 dark:border-zinc-800">
        {SUB_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-bold inline-flex items-center gap-1.5 border-b-2 transition-colors ${
              tab === t.id
                ? 'border-fuchsia-600 text-fuchsia-700'
                : 'border-transparent text-zinc-500 hover:text-zinc-900'
            }`}
            data-testid={`seo-tab-${t.id}`}
          >
            <t.icon size={13}/> {t.label}
          </button>
        ))}
      </div>

      {tab === 'dashboard' && <DashboardTab key={`d-${bump}`} />}
      {tab === 'keywords'  && <KeywordsTab onArticleGenerated={() => setBump((n) => n + 1)} />}
      {tab === 'articles'  && <ArticlesTab key={`a-${bump}`} />}
    </div>
  );
}
