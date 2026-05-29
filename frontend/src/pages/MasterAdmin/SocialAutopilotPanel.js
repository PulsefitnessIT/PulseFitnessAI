/**
 * Social Media Autopilot — Master Admin → Growth → Social Autopilot
 * (Iter 220bl).
 *
 * Generates daily draft posts for Instagram / TikTok / LinkedIn with
 * channel-aware tone, brand-coloured imagery, and full hashtag bundles.
 * The operator reviews each draft, taps "Copy caption" / "Download
 * image", and posts manually.
 */
import { useEffect, useMemo, useState, useCallback } from 'react';
import axios from 'axios';
import {
 Share2, Loader2, Sparkles, Instagram, Linkedin, Music2, RefreshCw,
 Copy, Check, Download, Trash2, Archive, PlayCircle, AlertTriangle, Hash,
 ImageIcon, Wand2,
} from 'lucide-react';
import { useAuth } from '@/App';
import { notify } from '@/components/notifications';

const CHANNEL_VISUAL = {
  instagram: { icon: Instagram, accent: 'bg-gradient-to-br from-fuchsia-500 via-pink-500 to-amber-500', label: 'Instagram' },
  tiktok:    { icon: Music2,    accent: 'bg-gradient-to-br from-zinc-900 to-cyan-500', label: 'TikTok' },
  linkedin:  { icon: Linkedin,  accent: 'bg-gradient-to-br from-blue-700 to-sky-500', label: 'LinkedIn' },
};

function auth() {
  return { Authorization: `Bearer ${localStorage.getItem('token')}` };
}

function StatusPill({ status }) {
  const map = {
    draft:    { bg: 'bg-amber-100',  text: 'text-amber-800',  label: 'Draft' },
    approved: { bg: 'bg-emerald-100',text: 'text-emerald-800',label: 'Approved' },
    archived: { bg: 'bg-zinc-200',   text: 'text-zinc-500',   label: 'Archived' },
  };
  const c = map[status] || map.draft;
  return (
    <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${c.bg} ${c.text}`}>
      {c.label}
    </span>
  );
}

function ChannelIcon({ channel, size = 14 }) {
  const v = CHANNEL_VISUAL[channel] || {};
  const Icon = v.icon || Share2;
  return (
    <span className={`shrink-0 w-7 h-7 rounded-lg ${v.accent || 'bg-zinc-200'} text-white flex items-center justify-center`}>
      <Icon size={size} />
    </span>
  );
}

function CopyButton({ value, label = 'Copy', testid }) {
  const [copied, setCopied] = useState(false);
  const onClick = async () => {
    try {
      await navigator.clipboard.writeText(value || '');
      setCopied(true);
      notify.success(`${label} copied`);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      notify.error('Clipboard blocked — paste manually from the textarea');
    }
  };
  return (
    <button
      type="button" onClick={onClick}
      className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-bold border border-zinc-200 hover:border-fuchsia-400 hover:text-fuchsia-700 text-zinc-700"
      data-testid={testid}
    >
      {copied ? <Check size={11}/> : <Copy size={11}/>}
      {copied ? 'Copied' : label}
    </button>
  );
}

function DownloadImage({ dataUrl, filename, testid }) {
  if (!dataUrl) return null;
  return (
    <a
      href={dataUrl} download={filename || 'gymaxis-social-post.png'}
      className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-bold border border-zinc-200 hover:border-fuchsia-400 hover:text-fuchsia-700 text-zinc-700"
      data-testid={testid}
    >
      <Download size={11}/> Image
    </a>
  );
}

function PostCard({ post, API, onChange }) {
  const channel = post.channel;
  const visual = CHANNEL_VISUAL[channel] || {};
  const caption = post.caption || '';
  const hashtagBlock = (post.hashtags || []).join(' ');
  const fullText = hashtagBlock ? `${caption}\n\n${hashtagBlock}` : caption;
  const [busy, setBusy] = useState('');

  const setStatus = async (action) => {
    if (busy) return;
    setBusy(action);
    try {
      if (action === 'delete') {
        await axios.delete(`${API}/api/marketing/social-autopilot/posts/${post.id}`, { headers: auth() });
        notify.success('Post deleted');
      } else if (action === 'archive') {
        await axios.post(`${API}/api/marketing/social-autopilot/posts/${post.id}/archive`, {}, { headers: auth() });
        notify.success('Archived');
      } else if (action === 'approve') {
        await axios.post(`${API}/api/marketing/social-autopilot/posts/${post.id}/approve`, {}, { headers: auth() });
        notify.success('Marked as approved');
      }
      onChange();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Action failed');
    } finally { setBusy(''); }
  };

  return (
    <article
      className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 overflow-hidden shadow-sm"
      data-testid={`social-post-${post.id}`}
    >
      <div className={`px-4 py-2 flex items-center gap-3 ${visual.accent || ''} text-white`}>
        <ChannelIcon channel={channel}/>
        <div className="flex-1 min-w-0">
          <p className="text-[11px] uppercase tracking-wider font-bold opacity-90">
            {visual.label} · {post.topic_kind === 'feature' ? 'Feature' : 'Industry'}
          </p>
          <p className="text-sm font-extrabold truncate">{post.topic_label || '—'}</p>
        </div>
        <StatusPill status={post.status}/>
      </div>

      {post.image_url ? (
        <div className="bg-zinc-100 dark:bg-zinc-900 p-2">
          <img
            src={post.image_url}
            alt={post.card_headline || post.topic_label || 'Social post visual'}
            className="w-full max-h-[420px] object-contain rounded-lg"
            data-testid={`social-post-image-${post.id}`}
          />
          <div className="mt-1 flex items-center justify-between px-1">
            <span className="text-[10px] text-zinc-500 font-mono uppercase">
              {post.image_variant === 'A' ? 'AI image' : 'Brand card'} · {post.image_model || ''}
            </span>
            <DownloadImage
              dataUrl={post.image_url}
              filename={`gymaxis-${channel}-${(post.id || '').slice(0, 8)}.png`}
              testid={`social-post-download-${post.id}`}
            />
          </div>
        </div>
      ) : null}

      <div className="px-4 py-3 space-y-3">
        <div>
          <p className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-1 inline-flex items-center gap-1">
            <ImageIcon size={10}/> Caption
          </p>
          <textarea
            readOnly
            className="w-full text-xs font-mono resize-none border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900 rounded-lg p-2 leading-relaxed"
            rows={Math.min(8, Math.max(3, Math.ceil(caption.length / 60)))}
            value={caption}
            data-testid={`social-post-caption-${post.id}`}
          />
        </div>

        {post.hashtags?.length ? (
          <div>
            <p className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-1 inline-flex items-center gap-1">
              <Hash size={10}/> Hashtags ({post.hashtags.length})
            </p>
            <p className="text-xs font-mono text-blue-700 dark:text-blue-300 break-words" data-testid={`social-post-hashtags-${post.id}`}>
              {hashtagBlock}
            </p>
          </div>
        ) : null}

        {post.video_script ? (
          <div>
            <p className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-1 inline-flex items-center gap-1">
              <PlayCircle size={10}/> Video script
            </p>
            <pre className="text-[11px] whitespace-pre-wrap bg-zinc-900 text-zinc-100 rounded-lg p-2 font-mono leading-relaxed">
              {post.video_script}
            </pre>
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2 pt-1">
          <CopyButton value={fullText} label="Copy post" testid={`social-post-copy-full-${post.id}`}/>
          <CopyButton value={caption} label="Caption only" testid={`social-post-copy-caption-${post.id}`}/>
          {post.hashtags?.length ? (
            <CopyButton value={hashtagBlock} label="Hashtags" testid={`social-post-copy-tags-${post.id}`}/>
          ) : null}
          {post.video_script ? (
            <CopyButton value={post.video_script} label="Script" testid={`social-post-copy-script-${post.id}`}/>
          ) : null}
          <div className="flex-1"/>
          {post.status !== 'approved' && post.status !== 'archived' ? (
            <button
              type="button" onClick={() => setStatus('approve')}
              disabled={busy === 'approve'}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-bold bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
              data-testid={`social-post-approve-${post.id}`}
            >
              {busy === 'approve' ? <Loader2 size={11} className="animate-spin"/> : <Check size={11}/>} Approve
            </button>
          ) : null}
          {post.status !== 'archived' ? (
            <button
              type="button" onClick={() => setStatus('archive')}
              disabled={busy === 'archive'}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-bold border border-zinc-200 hover:border-zinc-400 text-zinc-700 disabled:opacity-50"
              data-testid={`social-post-archive-${post.id}`}
            >
              <Archive size={11}/> Archive
            </button>
          ) : null}
          <button
            type="button" onClick={() => setStatus('delete')}
            disabled={busy === 'delete'}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-bold border border-rose-200 text-rose-700 hover:bg-rose-50 disabled:opacity-50"
            data-testid={`social-post-delete-${post.id}`}
          >
            <Trash2 size={11}/>
          </button>
        </div>
      </div>
    </article>
  );
}

export default function SocialAutopilotPanel() {
  const { API } = useAuth();
  const [status, setStatus] = useState(null);
  const [posts, setPosts] = useState([]);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState('');
  const [channelFilter, setChannelFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');

  const load = useCallback(async () => {
    setErr(null);
    try {
      const [s, p] = await Promise.all([
        axios.get(`${API}/api/marketing/social-autopilot/status`, { headers: auth() }),
        axios.get(`${API}/api/marketing/social-autopilot/posts?limit=60`, { headers: auth() }),
      ]);
      setStatus(s.data);
      setPosts(p.data?.posts || []);
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Could not load Social Autopilot');
    }
  }, [API]);

  useEffect(() => { load(); }, [load]);

  const runDaily = async () => {
    if (busy) return;
    setBusy('run');
    try {
      const r = await axios.post(`${API}/api/marketing/social-autopilot/run-now`, {}, { headers: auth() });
      if (r.data?.ok) {
        notify.success('Daily drafts generated — check the cards below');
      } else {
        notify.info(r.data?.reason || 'Already ran today');
      }
      await load();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Run failed');
    } finally { setBusy(''); }
  };

  const generateOne = async (channel) => {
    setBusy(`gen-${channel}`);
    try {
      await axios.post(`${API}/api/marketing/social-autopilot/generate`,
        { channel }, { headers: auth() });
      notify.success(`${CHANNEL_VISUAL[channel]?.label || channel} draft generated`);
      await load();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Generation failed');
    } finally { setBusy(''); }
  };

  const filtered = useMemo(() => {
    return (posts || []).filter((p) =>
      (channelFilter === 'all' || p.channel === channelFilter) &&
      (statusFilter === 'all' || p.status === statusFilter),
    );
  }, [posts, channelFilter, statusFilter]);

  if (err) {
    return (
      <div className="rounded-2xl border border-rose-200 bg-rose-50 text-rose-700 px-4 py-3 text-sm inline-flex items-center gap-2" data-testid="social-autopilot-error">
        <AlertTriangle size={14}/> {err}
      </div>
    );
  }
  if (!status) {
    return (
      <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 px-4 py-3 text-sm text-zinc-500 inline-flex items-center gap-2">
        <Loader2 size={13} className="animate-spin"/> Loading Social Autopilot…
      </div>
    );
  }

  return (
    <div className="space-y-5" data-testid="social-autopilot-panel">
      {/* Hero */}
      <header
        className="rounded-2xl border border-fuchsia-200 dark:border-fuchsia-900 bg-gradient-to-r from-fuchsia-50 via-white to-blue-50 dark:from-zinc-900 dark:via-zinc-900 dark:to-zinc-900 px-5 py-4"
        data-testid="social-autopilot-hero"
      >
        <div className="flex items-center gap-4 flex-wrap">
          <span className="shrink-0 w-12 h-12 rounded-2xl bg-gradient-to-br from-fuchsia-500 to-blue-600 text-white flex items-center justify-center shadow-[0_8px_20px_-8px_rgba(217,70,239,0.6)]">
            <Share2 size={20}/>
          </span>
          <div className="flex-1 min-w-0">
            <p className="text-[11px] uppercase tracking-[0.18em] font-bold text-fuchsia-700 dark:text-fuchsia-400">Growth · Social Autopilot</p>
            <h2 className="text-xl sm:text-2xl font-extrabold text-zinc-900 dark:text-zinc-50 tracking-tight mt-0.5">Daily IG · TikTok · LinkedIn drafts</h2>
            <p className="text-xs sm:text-sm text-zinc-600 dark:text-zinc-300 mt-1 max-w-2xl">
              Channel-aware tone (fun on IG/TikTok, decision-maker on LinkedIn), brand-coloured imagery, 50% feature promotion / 50% industry insight. Review, approve and copy/download — manual posting keeps you in full control.
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <button
              type="button" onClick={runDaily}
              disabled={busy === 'run' || status.ran_today}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold text-white bg-fuchsia-600 hover:bg-fuchsia-700 disabled:opacity-50"
              data-testid="social-run-now-btn"
              title={status.ran_today ? 'Already ran today — use Generate per channel to add more' : 'Generate today\'s drafts for all 3 channels'}
            >
              {busy === 'run' ? <Loader2 size={11} className="animate-spin"/> : <PlayCircle size={11}/>}
              Run today
            </button>
            <button
              type="button" onClick={load}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold border border-zinc-200 dark:border-zinc-700 text-zinc-700 dark:text-zinc-100 hover:border-fuchsia-400"
              data-testid="social-refresh"
            >
              <RefreshCw size={11}/> Refresh
            </button>
          </div>
        </div>
      </header>

      {/* Channel quick-generators */}
      <section className="grid sm:grid-cols-3 gap-3" data-testid="social-channel-row">
        {(status.channels || []).map((c) => (
          <div
            key={c.id}
            className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 p-3 flex items-center gap-3"
            data-testid={`social-channel-card-${c.id}`}
          >
            <ChannelIcon channel={c.id} size={16}/>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-extrabold leading-tight">{c.label}</p>
              <p className="text-[11px] text-zinc-500 leading-tight truncate">
                {(status.draft_counts?.[c.id] ?? 0)} drafts queued
              </p>
            </div>
            <button
              type="button" onClick={() => generateOne(c.id)}
              disabled={busy === `gen-${c.id}`}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-bold border border-fuchsia-300 text-fuchsia-700 hover:bg-fuchsia-50 disabled:opacity-50"
              data-testid={`social-gen-${c.id}`}
            >
              {busy === `gen-${c.id}` ? <Loader2 size={11} className="animate-spin"/> : <Wand2 size={11}/>}
              Generate
            </button>
          </div>
        ))}
      </section>

      {/* Filters */}
      <div className="flex items-center gap-2 flex-wrap" data-testid="social-filters">
        <span className="text-[11px] uppercase font-bold text-zinc-500 mr-1">Channel</span>
        {['all', 'instagram', 'tiktok', 'linkedin'].map((id) => (
          <button
            key={id} type="button" onClick={() => setChannelFilter(id)}
            className={`text-[11px] font-bold px-2 py-1 rounded-full border ${channelFilter === id ? 'bg-zinc-900 text-white border-zinc-900' : 'border-zinc-200 text-zinc-700 hover:border-zinc-400'}`}
            data-testid={`social-filter-channel-${id}`}
          >
            {id === 'all' ? 'All' : (CHANNEL_VISUAL[id]?.label || id)}
          </button>
        ))}
        <span className="text-[11px] uppercase font-bold text-zinc-500 mx-1 ml-3">Status</span>
        {['all', 'draft', 'approved', 'archived'].map((id) => (
          <button
            key={id} type="button" onClick={() => setStatusFilter(id)}
            className={`text-[11px] font-bold px-2 py-1 rounded-full border ${statusFilter === id ? 'bg-zinc-900 text-white border-zinc-900' : 'border-zinc-200 text-zinc-700 hover:border-zinc-400'}`}
            data-testid={`social-filter-status-${id}`}
          >
            {id === 'all' ? 'All' : id.charAt(0).toUpperCase() + id.slice(1)}
          </button>
        ))}
        <div className="flex-1"/>
        <span className="text-[11px] text-zinc-500" data-testid="social-result-count">
          {filtered.length} post{filtered.length === 1 ? '' : 's'}
        </span>
      </div>

      {/* Posts grid */}
      {filtered.length === 0 ? (
        <div
          className="rounded-2xl border border-dashed border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-950 p-8 text-center text-sm text-zinc-500"
          data-testid="social-empty-state"
        >
          <Sparkles className="mx-auto mb-2" size={18}/>
          No drafts yet. Hit <b>Run today</b> to generate one per channel, or use a channel&apos;s <b>Generate</b> button.
        </div>
      ) : (
        <div className="grid lg:grid-cols-2 xl:grid-cols-3 gap-4" data-testid="social-posts-grid">
          {filtered.map((p) => (
            <PostCard key={p.id} post={p} API={API} onChange={load}/>
          ))}
        </div>
      )}
    </div>
  );
}
