import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  Megaphone, PlayCircle, PauseCircle, Trash2, Plus, RefreshCw, Loader2,
  TrendingUp, ExternalLink, AlertTriangle, Sparkles,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL;
const auth = () => ({
  Authorization: `Bearer ${localStorage.getItem('token') || ''}`,
});

/**
 * <CampaignsSection/> — Iter 220bw — Launch campaign manager for the
 * Social Autopilot panel. Allows the master admin to create a Launch
 * campaign with keywords + a blend ratio, activate / pause it, and
 * see the archetypes the generator will cycle through.
 */
export function CampaignsSection() {
  const [campaigns, setCampaigns] = useState([]);
  const [archetypes, setArchetypes] = useState([]);
  const [busy, setBusy] = useState('');
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    name: 'GymAxis Launch Week',
    type: 'launch',
    keywords: 'early access, ops-first, feature reveal, built by ops',
    blend_ratio: 0.7,
  });

  const load = useCallback(async () => {
    try {
      const r = await axios.get(
        `${API}/api/marketing/social-autopilot/campaigns`,
        { headers: auth() },
      );
      setCampaigns(r.data?.campaigns || []);
      setArchetypes(r.data?.archetypes || []);
    } catch (e) {
      // 401 means the token expired — surface a friendly toast.
      notify.error('Could not load campaigns', e?.response?.data?.detail || e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const createCampaign = async () => {
    setBusy('create');
    try {
      const payload = {
        ...form,
        blend_ratio: parseFloat(form.blend_ratio) || 0.7,
        keywords: form.keywords.split(',').map((k) => k.trim()).filter(Boolean),
      };
      await axios.post(
        `${API}/api/marketing/social-autopilot/campaigns`, payload,
        { headers: auth() },
      );
      notify.success('Campaign created', `"${form.name}" saved as paused — hit Activate to start blending.`);
      setCreating(false);
      load();
    } catch (e) {
      notify.error('Create failed', e?.response?.data?.detail || e.message);
    }
    setBusy('');
  };

  const activate = async (id) => {
    setBusy(`act:${id}`);
    try {
      await axios.post(
        `${API}/api/marketing/social-autopilot/campaigns/${id}/activate`, {},
        { headers: auth() },
      );
      notify.success('Campaign active', 'New posts will now blend 70 / 30 with launch tone.');
      load();
    } catch (e) {
      notify.error('Activate failed', e?.response?.data?.detail || e.message);
    }
    setBusy('');
  };

  const pause = async (id) => {
    setBusy(`pause:${id}`);
    try {
      await axios.post(
        `${API}/api/marketing/social-autopilot/campaigns/${id}/pause`, {},
        { headers: auth() },
      );
      load();
    } catch (e) {
      notify.error('Pause failed', e?.response?.data?.detail || e.message);
    }
    setBusy('');
  };

  const remove = async (id) => {
    if (!window.confirm('Delete this campaign? Its tagged posts will still exist.')) return;
    setBusy(`del:${id}`);
    try {
      await axios.delete(
        `${API}/api/marketing/social-autopilot/campaigns/${id}`,
        { headers: auth() },
      );
      load();
    } catch (e) {
      notify.error('Delete failed', e?.response?.data?.detail || e.message);
    }
    setBusy('');
  };

  return (
    <section className="space-y-3" data-testid="campaigns-section">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold flex items-center gap-2">
          <Megaphone size={16} className="text-violet-500"/>
          Launch campaigns
          <span className="text-xs font-normal text-zinc-500">
            ({campaigns.filter((c) => c.status === 'active').length} active)
          </span>
        </h2>
        <button
          type="button"
          className="text-xs px-2.5 py-1 rounded-md border bg-violet-600 text-white border-violet-700 flex items-center gap-1"
          onClick={() => setCreating((v) => !v)}
          data-testid="campaigns-toggle-create"
        >
          <Plus size={12}/>{creating ? 'Cancel' : 'New campaign'}
        </button>
      </div>

      {creating && (
        <div className="rounded-xl border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-950 p-4 space-y-3" data-testid="campaign-create-form">
          <div className="grid sm:grid-cols-2 gap-3">
            <label className="text-xs">
              <span className="text-zinc-500">Campaign name</span>
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="mt-1 w-full text-sm px-2 py-1 rounded border bg-transparent"
                data-testid="campaign-form-name"
              />
            </label>
            <label className="text-xs">
              <span className="text-zinc-500">Type</span>
              <select
                value={form.type}
                onChange={(e) => setForm({ ...form, type: e.target.value })}
                className="mt-1 w-full text-sm px-2 py-1 rounded border bg-transparent"
                data-testid="campaign-form-type"
              >
                <option value="launch">Launch (brand-new platform tone)</option>
                <option value="feature">Feature (post-launch reveal)</option>
                <option value="seasonal">Seasonal</option>
              </select>
            </label>
          </div>
          <label className="text-xs block">
            <span className="text-zinc-500">Keywords (comma-separated — the AI will weave 2-3 into each post)</span>
            <input
              value={form.keywords}
              onChange={(e) => setForm({ ...form, keywords: e.target.value })}
              className="mt-1 w-full text-sm px-2 py-1 rounded border bg-transparent"
              data-testid="campaign-form-keywords"
            />
          </label>
          <label className="text-xs block">
            <span className="text-zinc-500">
              Blend ratio — fraction of posts that use the launch tone (default 0.7 = 70/30 split)
            </span>
            <input
              type="number"
              min={0} max={1} step={0.1}
              value={form.blend_ratio}
              onChange={(e) => setForm({ ...form, blend_ratio: e.target.value })}
              className="mt-1 w-32 text-sm px-2 py-1 rounded border bg-transparent"
              data-testid="campaign-form-blend"
            />
          </label>
          <button
            type="button"
            disabled={busy === 'create'}
            onClick={createCampaign}
            className="text-xs px-3 py-1.5 rounded-md bg-emerald-600 text-white disabled:opacity-60 flex items-center gap-1"
            data-testid="campaign-form-save"
          >
            {busy === 'create' ? <Loader2 size={12} className="animate-spin"/> : <Sparkles size={12}/>}
            Save campaign
          </button>
        </div>
      )}

      {campaigns.length === 0 ? (
        <p className="text-xs text-zinc-500 italic" data-testid="campaigns-empty">
          No campaigns yet — create a "Launch Week" campaign to switch the AI from established voice to brand-new-platform tone.
        </p>
      ) : (
        <div className="space-y-2">
          {campaigns.map((c) => (
            <div
              key={c.id}
              className={`rounded-xl border p-3 flex items-center justify-between gap-2 ${
                c.status === 'active'
                  ? 'border-emerald-400 bg-emerald-50/40 dark:bg-emerald-950/20'
                  : 'border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-950'
              }`}
              data-testid={`campaign-row-${c.id}`}
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="text-sm font-semibold truncate">{c.name}</p>
                  <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${
                    c.status === 'active'
                      ? 'bg-emerald-200 text-emerald-900'
                      : 'bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'
                  }`}>{c.status}</span>
                  <span className="text-[10px] uppercase px-1.5 py-0.5 rounded bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-300">
                    {c.type}
                  </span>
                  <span className="text-[10px] text-zinc-500">
                    blend {Math.round((c.blend_ratio ?? 0.7) * 100)}%
                  </span>
                </div>
                {c.keywords?.length > 0 && (
                  <p className="text-[11px] text-zinc-500 mt-1 truncate">
                    keywords: {c.keywords.join(', ')}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                {c.status === 'active' ? (
                  <button
                    type="button"
                    onClick={() => pause(c.id)}
                    disabled={busy === `pause:${c.id}`}
                    className="text-xs px-2 py-1 rounded border bg-zinc-100 dark:bg-zinc-800 flex items-center gap-1"
                    data-testid={`campaign-pause-${c.id}`}
                  >
                    {busy === `pause:${c.id}` ? <Loader2 size={11} className="animate-spin"/> : <PauseCircle size={11}/>}
                    Pause
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => activate(c.id)}
                    disabled={busy === `act:${c.id}`}
                    className="text-xs px-2 py-1 rounded bg-emerald-600 text-white flex items-center gap-1"
                    data-testid={`campaign-activate-${c.id}`}
                  >
                    {busy === `act:${c.id}` ? <Loader2 size={11} className="animate-spin"/> : <PlayCircle size={11}/>}
                    Activate
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => remove(c.id)}
                  className="text-xs px-2 py-1 rounded text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40"
                  data-testid={`campaign-delete-${c.id}`}
                >
                  <Trash2 size={11}/>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {archetypes.length > 0 && (
        <details className="text-xs text-zinc-500" data-testid="campaigns-archetypes">
          <summary className="cursor-pointer">Launch archetypes the AI cycles through ({archetypes.length})</summary>
          <ul className="mt-2 space-y-1 list-disc list-inside">
            {archetypes.map((a) => (
              <li key={a.id}><b>{a.id.replace(/_/g, ' ')}</b> — {a.card_headline_hint}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}


/**
 * <TrackedPostsSection/> — Iter 220bw — Tracks public-post engagement
 * (likes / comments / caption) by daily crawl. First use-case: the
 * launch teaser at instagram.com/p/DYfu35JNbkJ/. Same surface accepts
 * the TikTok / LinkedIn URLs once they're posted.
 */
export function TrackedPostsSection() {
  const [rows, setRows] = useState([]);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState('');
  const [form, setForm] = useState({ url: 'https://www.instagram.com/p/DYfu35JNbkJ/', label: 'Launch teaser' });

  const load = useCallback(async () => {
    try {
      const r = await axios.get(
        `${API}/api/marketing/social-autopilot/tracked-posts`,
        { headers: auth() },
      );
      setRows(r.data?.tracked_posts || []);
    } catch (e) {
      notify.error('Could not load tracked posts', e?.response?.data?.detail || e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const add = async () => {
    setBusy('add');
    try {
      await axios.post(
        `${API}/api/marketing/social-autopilot/tracked-posts`, form,
        { headers: auth() },
      );
      notify.success('Tracking added', 'First crawl will run within 24 h. Use Refresh to get a reading now.');
      setAdding(false);
      load();
    } catch (e) {
      notify.error('Add failed', e?.response?.data?.detail || e.message);
    }
    setBusy('');
  };

  const refresh = async (id) => {
    setBusy(`r:${id}`);
    try {
      const r = await axios.post(
        `${API}/api/marketing/social-autopilot/tracked-posts/${id}/refresh`, {},
        { headers: auth() },
      );
      if (r.data?.status === 'blocked') {
        notify.error('IG blocked the crawl', 'Login wall detected. We will silently retry tomorrow.');
      } else if (r.data?.status === 'ok') {
        notify.success('Refreshed', `Latest reading captured at ${new Date(r.data.fetched_at).toLocaleTimeString()}.`);
      } else {
        notify.error('Refresh failed', `HTTP ${r.data?.http_status || 'n/a'}`);
      }
      load();
    } catch (e) {
      notify.error('Refresh failed', e?.response?.data?.detail || e.message);
    }
    setBusy('');
  };

  const remove = async (id) => {
    if (!window.confirm('Stop tracking this post?')) return;
    setBusy(`d:${id}`);
    try {
      await axios.delete(
        `${API}/api/marketing/social-autopilot/tracked-posts/${id}`,
        { headers: auth() },
      );
      load();
    } catch (e) {
      notify.error('Delete failed', e?.response?.data?.detail || e.message);
    }
    setBusy('');
  };

  return (
    <section className="space-y-3" data-testid="tracked-posts-section">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold flex items-center gap-2">
          <TrendingUp size={16} className="text-cyan-500"/>
          Tracked posts
          <span className="text-xs font-normal text-zinc-500">
            ({rows.filter((r) => r.active).length} active)
          </span>
        </h2>
        <button
          type="button"
          className="text-xs px-2.5 py-1 rounded-md border bg-cyan-600 text-white border-cyan-700 flex items-center gap-1"
          onClick={() => setAdding((v) => !v)}
          data-testid="tracked-toggle-add"
        >
          <Plus size={12}/>{adding ? 'Cancel' : 'Track URL'}
        </button>
      </div>

      {adding && (
        <div className="rounded-xl border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-950 p-3 space-y-2" data-testid="tracked-add-form">
          <label className="text-xs block">
            <span className="text-zinc-500">Post URL (Instagram / TikTok / LinkedIn)</span>
            <input
              value={form.url}
              onChange={(e) => setForm({ ...form, url: e.target.value })}
              className="mt-1 w-full text-sm px-2 py-1 rounded border bg-transparent"
              placeholder="https://www.instagram.com/p/..."
              data-testid="tracked-form-url"
            />
          </label>
          <label className="text-xs block">
            <span className="text-zinc-500">Label (optional)</span>
            <input
              value={form.label}
              onChange={(e) => setForm({ ...form, label: e.target.value })}
              className="mt-1 w-full text-sm px-2 py-1 rounded border bg-transparent"
              data-testid="tracked-form-label"
            />
          </label>
          <button
            type="button"
            disabled={busy === 'add' || !form.url}
            onClick={add}
            className="text-xs px-3 py-1.5 rounded bg-cyan-600 text-white disabled:opacity-60 flex items-center gap-1"
            data-testid="tracked-form-save"
          >
            {busy === 'add' ? <Loader2 size={12} className="animate-spin"/> : <Plus size={12}/>}
            Start tracking
          </button>
        </div>
      )}

      {rows.length === 0 ? (
        <p className="text-xs text-zinc-500 italic" data-testid="tracked-posts-empty">
          No tracked posts yet — add the launch teaser at <code>instagram.com/p/DYfu35JNbkJ/</code> to start the daily reading.
        </p>
      ) : (
        <div className="space-y-2">
          {rows.map((r) => {
            const eng = r.last_engagement || {};
            const stale = r.last_crawl_status === 'blocked';
            return (
              <div
                key={r.id}
                className="rounded-xl border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-950 p-3 flex items-center justify-between gap-3"
                data-testid={`tracked-row-${r.id}`}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-zinc-200 dark:bg-zinc-800">
                      {r.platform}
                    </span>
                    {r.label && <span className="text-sm font-medium truncate">{r.label}</span>}
                    {stale && (
                      <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-amber-200 text-amber-900 flex items-center gap-0.5">
                        <AlertTriangle size={9}/> blocked
                      </span>
                    )}
                  </div>
                  <a
                    href={r.url} target="_blank" rel="noreferrer"
                    className="text-[11px] text-zinc-500 truncate inline-flex items-center gap-1 hover:underline"
                    data-testid={`tracked-row-link-${r.id}`}
                  >
                    {r.url} <ExternalLink size={9}/>
                  </a>
                  {(eng.likes !== undefined || eng.comments !== undefined) && (
                    <div className="mt-1 flex items-center gap-3 text-xs">
                      {eng.likes !== undefined && (
                        <span><b>{eng.likes.toLocaleString()}</b> likes</span>
                      )}
                      {eng.comments !== undefined && (
                        <span><b>{eng.comments.toLocaleString()}</b> comments</span>
                      )}
                      {eng.views !== undefined && (
                        <span><b>{eng.views.toLocaleString()}</b> views</span>
                      )}
                      <span className="text-zinc-500 italic truncate max-w-[16rem]">
                        {eng.caption_snippet || ''}
                      </span>
                    </div>
                  )}
                  {r.last_crawled_at && (
                    <p className="text-[10px] text-zinc-500 mt-1">
                      Last crawl: {new Date(r.last_crawled_at).toLocaleString()} · {r.last_crawl_status}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    type="button"
                    disabled={busy === `r:${r.id}`}
                    onClick={() => refresh(r.id)}
                    className="text-xs px-2 py-1 rounded border bg-zinc-100 dark:bg-zinc-800 flex items-center gap-1"
                    data-testid={`tracked-refresh-${r.id}`}
                  >
                    {busy === `r:${r.id}` ? <Loader2 size={11} className="animate-spin"/> : <RefreshCw size={11}/>}
                    Refresh
                  </button>
                  <button
                    type="button"
                    onClick={() => remove(r.id)}
                    className="text-xs px-2 py-1 rounded text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40"
                    data-testid={`tracked-delete-${r.id}`}
                  >
                    <Trash2 size={11}/>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

export default CampaignsSection;
