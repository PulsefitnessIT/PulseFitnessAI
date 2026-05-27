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
  ListChecks, AlertTriangle, Eye, Send, Search, FileText, X,
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
  };
  const c = map[status] || { bg: 'bg-zinc-100', text: 'text-zinc-700', label: status || '—' };
  return (
    <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${c.bg} ${c.text}`}>
      {c.label}
    </span>
  );
}

// ── Dashboard ────────────────────────────────────────────────────

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
    { label: 'Keywords used',     value: data.keywords.published,icon: ListChecks, hint: 'covered by an article' },
  ];

  return (
    <div className="space-y-5" data-testid="seo-dashboard">
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

  return (
    <div className="space-y-5" data-testid="seo-articles">
      <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 overflow-hidden">
        <div className="px-5 py-3 border-b border-zinc-100 dark:border-zinc-800 flex items-center justify-between">
          <p className="text-sm font-bold">Articles</p>
          <button onClick={load} className="text-[11px] inline-flex items-center gap-1 text-zinc-500 hover:text-zinc-900">
            <RefreshCw size={11}/> Refresh
          </button>
        </div>
        {error ? <p className="px-5 py-3 text-sm text-rose-600" data-testid="seo-articles-error">{error}</p> : null}
        {list.length === 0 ? (
          <p className="px-5 py-10 text-sm text-zinc-500 text-center">
            No articles yet. Generate one from the Keywords tab.
          </p>
        ) : (
          <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {list.map((a) => (
              <div key={a.id} className="px-5 py-3 flex items-center gap-3" data-testid={`seo-article-${a.id}`}>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-bold truncate">{a.title}</p>
                    <StatusPill status={a.status} />
                  </div>
                  <p className="text-[11px] text-zinc-500 mt-0.5">
                    /{a.slug} · {a.read_time_min} min · {a.metrics?.views || 0} views · {a.word_count} words
                  </p>
                </div>
                {a.status === 'published' ? (
                  <a href={`/blog/${a.slug}`} target="_blank" rel="noreferrer noopener"
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-bold border border-zinc-200 hover:border-fuchsia-400"
                    data-testid={`seo-article-view-${a.id}`}
                  >
                    <Eye size={11}/> View
                  </a>
                ) : null}
                <button onClick={() => open(a)}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-bold bg-fuchsia-600 text-white hover:bg-fuchsia-700"
                  data-testid={`seo-article-edit-${a.id}`}
                >
                  Edit
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
      {editing ? <ArticleEditor article={editing} onClose={() => setEditing(null)} onSaved={() => load()} /> : null}
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
