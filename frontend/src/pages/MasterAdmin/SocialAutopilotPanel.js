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
 ImageIcon, Wand2, Film, Clock, ChevronDown, ChevronUp,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { CampaignsSection, TrackedPostsSection } from './SocialAutopilotCampaignsAndTracker';

// Match SEOAutopilotPanel convention — REACT_APP_BACKEND_URL is the
// host root WITHOUT a trailing /api, every fetch URL prefixes the
// /api/ segment itself. See test_iter_220bo for the regression guard.
const API = process.env.REACT_APP_BACKEND_URL;

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

function VideoSection({ post, onChange }) {
  const status = post.video_status || (post.video_url ? 'ready' : 'idle');
  const [busy, setBusy] = useState(false);
  // Auto-poll while a video is generating so the operator doesn't
  // have to keep refreshing manually.
  useEffect(() => {
    if (status !== 'generating' && status !== 'queued') return undefined;
    const id = setInterval(() => onChange(), 8000);
    return () => clearInterval(id);
  }, [status, onChange]);

  const triggerGenerate = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await axios.post(`${API}/api/marketing/social-autopilot/posts/${post.id}/generate-video`,
        { model: 'sora-2', duration: 8 }, { headers: auth() });
      notify.success('Sora 2 render queued — typically 2-5 minutes');
      onChange();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Video generation failed');
    } finally { setBusy(false); }
  };

  if (status === 'ready' && post.video_url) {
    const videoSrc = `${API}${post.video_url}`;
    return (
      <div className="px-3 pt-2" data-testid={`social-post-video-${post.id}`}>
        <p className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 mb-1 inline-flex items-center gap-1">
          <Film size={10}/> Sora 2 video clip
        </p>
        <video
          src={`${videoSrc}?t=${encodeURIComponent(localStorage.getItem('token') || '')}`}
          controls
          className="w-full rounded-lg bg-black max-h-[420px]"
          data-testid={`social-post-video-player-${post.id}`}
          // Pass auth via header by fetching as a blob — fallback for
          // browsers that don't allow Authorization header on video.
          onError={async (e) => {
            try {
              const r = await axios.get(videoSrc, {
                headers: auth(), responseType: 'blob',
              });
              e.target.src = URL.createObjectURL(r.data);
            } catch { /* keep error state */ }
          }}
        />
        <div className="mt-1 flex items-center justify-between px-1">
          <span className="text-[10px] text-zinc-500 font-mono uppercase">
            {post.video_model || 'sora-2'} · {post.video_duration || 8}s · {Math.round((post.video_size_bytes || 0) / 1024)} KB
          </span>
          <button
            type="button" onClick={async () => {
              try {
                const r = await axios.get(videoSrc, { headers: auth(), responseType: 'blob' });
                const url = URL.createObjectURL(r.data);
                const a = document.createElement('a');
                a.href = url; a.download = `gymaxis-tiktok-${post.id.slice(0, 8)}.mp4`;
                a.click(); URL.revokeObjectURL(url);
              } catch (err) {
                notify.error('Download failed');
              }
            }}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-bold border border-zinc-200 hover:border-fuchsia-400 hover:text-fuchsia-700 text-zinc-700"
            data-testid={`social-post-download-video-${post.id}`}
          >
            <Download size={11}/> Video
          </button>
        </div>
      </div>
    );
  }

  if (status === 'generating' || status === 'queued') {
    return (
      <div className="px-3 pt-2" data-testid={`social-post-video-pending-${post.id}`}>
        <div className="rounded-lg bg-fuchsia-50 dark:bg-fuchsia-950/30 border border-fuchsia-200 dark:border-fuchsia-900 p-3 flex items-center gap-2 text-xs text-fuchsia-800 dark:text-fuchsia-200">
          <Loader2 size={13} className="animate-spin shrink-0"/>
          <div className="flex-1 min-w-0">
            <p className="font-bold">Sora 2 rendering your clip…</p>
            <p className="text-[11px] opacity-80 flex items-center gap-1">
              <Clock size={10}/> Typically 2-5 minutes. This page auto-refreshes.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (status === 'failed') {
    return (
      <div className="px-3 pt-2">
        <div className="rounded-lg bg-rose-50 border border-rose-200 p-2 text-[11px] text-rose-700 flex items-start gap-2">
          <AlertTriangle size={12} className="shrink-0 mt-0.5"/>
          <div className="flex-1">
            <p className="font-bold">Video generation failed</p>
            <p className="opacity-80 break-words">{post.video_error || 'Sora 2 returned no bytes.'}</p>
          </div>
          <button
            type="button" onClick={triggerGenerate} disabled={busy}
            className="text-[11px] font-bold underline hover:no-underline shrink-0"
            data-testid={`social-post-video-retry-${post.id}`}
          >Retry</button>
        </div>
      </div>
    );
  }

  // Idle — show the "Generate video" button.
  return (
    <div className="px-3 pt-2">
      <button
        type="button" onClick={triggerGenerate} disabled={busy}
        className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-bold bg-gradient-to-r from-zinc-900 to-cyan-600 text-white hover:opacity-95 disabled:opacity-50"
        data-testid={`social-post-video-generate-${post.id}`}
        title="Render a ~8 second 9:16 vertical clip via Sora 2 (typically 2-5 minutes)"
      >
        {busy ? <Loader2 size={11} className="animate-spin"/> : <Film size={11}/>}
        Generate Sora 2 clip
      </button>
    </div>
  );
}

function ToneCheckBanner({ post, onRecheck }) {
  const tc = post.tone_check;
  const [busy, setBusy] = useState(false);
  const recheck = async (deep = false) => {
    setBusy(true);
    try {
      const r = await axios.post(
        `${API}/api/marketing/social-autopilot/posts/${post.id}/recheck-tone?deep=${deep}`,
        {},
        { headers: auth() },
      );
      const newStatus = r.data?.status;
      if (newStatus === 'ok') notify.success('Tone check passed', 'All clear.');
      else notify.error(
        newStatus === 'failed' ? 'Launch-tone violations found' : 'Tone warnings',
        `${r.data?.findings?.length || 0} finding(s) — see the post card.`,
      );
      onRecheck && onRecheck();
    } catch (e) {
      notify.error('Recheck failed', e?.response?.data?.detail || e.message);
    }
    setBusy(false);
  };

  if (!tc || tc.status === 'ok') {
    // Render a slim "passed" stripe only when we ran a check (so a
    // legacy doc with no tone_check field shows nothing).
    if (!tc) return null;
    return (
      <div
        className="px-4 py-1.5 text-[11px] flex items-center justify-between gap-2 border-b border-emerald-100 bg-emerald-50/60 dark:bg-emerald-950/30 dark:border-emerald-900"
        data-testid={`tone-check-ok-${post.id}`}
      >
        <span className="text-emerald-700 dark:text-emerald-300 flex items-center gap-1">
          <Check size={11}/> Launch tone OK
        </span>
        <button
          type="button" onClick={() => recheck(false)} disabled={busy}
          className="text-emerald-700 dark:text-emerald-300 hover:underline"
          data-testid={`tone-check-recheck-${post.id}`}
        >
          {busy ? 'Checking…' : 'Recheck'}
        </button>
      </div>
    );
  }

  const isFail = tc.status === 'failed';
  const tone = isFail
    ? 'border-rose-200 bg-rose-50/70 dark:bg-rose-950/40 dark:border-rose-900'
    : 'border-amber-200 bg-amber-50/70 dark:bg-amber-950/40 dark:border-amber-900';
  const textTone = isFail ? 'text-rose-800 dark:text-rose-200' : 'text-amber-800 dark:text-amber-200';
  return (
    <div
      className={`px-4 py-2 text-[12px] border-b ${tone}`}
      data-testid={`tone-check-${tc.status}-${post.id}`}
    >
      <div className={`flex items-center justify-between gap-2 ${textTone}`}>
        <span className="font-semibold flex items-center gap-1">
          <AlertTriangle size={12}/>
          {isFail ? 'Launch-tone violations' : 'Launch-tone warnings'} — {tc.findings.length} item{tc.findings.length === 1 ? '' : 's'}
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button" onClick={() => recheck(false)} disabled={busy}
            className="hover:underline"
            data-testid={`tone-check-recheck-${post.id}`}
          >
            {busy ? 'Checking…' : 'Recheck'}
          </button>
          <button
            type="button" onClick={() => recheck(true)} disabled={busy}
            className="hover:underline opacity-80"
            data-testid={`tone-check-deep-${post.id}`}
          >
            Deep recheck (LLM)
          </button>
        </div>
      </div>
      <ul className="mt-1.5 space-y-1 list-disc list-inside" data-testid={`tone-check-findings-${post.id}`}>
        {tc.findings.slice(0, 4).map((f, i) => (
          <li key={i} className={`${textTone} opacity-90`}>
            <span className="font-mono text-[11px] bg-white/40 dark:bg-black/30 rounded px-1">
              {f.matched || f.snippet?.slice(0, 40)}
            </span>
            <span className="ml-1">— {f.suggestion}</span>
          </li>
        ))}
        {tc.findings.length > 4 && (
          <li className={`${textTone} opacity-70 italic`}>+ {tc.findings.length - 4} more</li>
        )}
      </ul>
    </div>
  );
}

function PostCard({ post, onChange }) {
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

      <ToneCheckBanner post={post} onRecheck={onChange}/>

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

      {channel === 'tiktok' ? <VideoSection post={post} onChange={onChange}/> : null}

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

function LegacyLibrarySection() {
  const [rows, setRows] = useState(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState('');
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const r = await axios.get(`${API}/api/marketing/social-autopilot/legacy-library`, { headers: auth() });
      setRows(r.data?.rows || []);
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Could not load legacy library');
      setRows([]);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const remove = async (id) => {
    if (!window.confirm('Delete this legacy library post? This cannot be undone.')) return;
    setBusy(id);
    try {
      await axios.delete(`${API}/api/marketing/social-autopilot/legacy-library/${id}`, { headers: auth() });
      notify.success('Deleted');
      setRows((cur) => (cur || []).filter((r) => r.id !== id));
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Delete failed');
    } finally { setBusy(''); }
  };

  if (rows === null) return null;
  if (!rows.length && !err) return null;  // nothing to clean up, hide

  return (
    <section
      className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 overflow-hidden"
      data-testid="social-legacy-library"
    >
      <button
        type="button" onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-zinc-50 dark:hover:bg-zinc-900"
        data-testid="social-legacy-toggle"
      >
        <span className="shrink-0 w-9 h-9 rounded-xl bg-amber-100 text-amber-700 flex items-center justify-center">
          <Archive size={14}/>
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-extrabold">Legacy social library</p>
          <p className="text-[11px] text-zinc-500">
            {rows.length} post{rows.length === 1 ? '' : 's'} from the old Catalogue → Social Media tab. Delete-only — no new posts can be added here.
          </p>
        </div>
        {open ? <ChevronUp size={14}/> : <ChevronDown size={14}/>}
      </button>
      {open ? (
        <div className="border-t border-zinc-100 dark:border-zinc-800 divide-y divide-zinc-100 dark:divide-zinc-800" data-testid="social-legacy-rows">
          {err ? (
            <p className="px-4 py-3 text-xs text-rose-600">{err}</p>
          ) : null}
          {rows.map((row) => (
            <div key={row.id} className="flex items-center gap-3 px-4 py-2 text-sm" data-testid={`social-legacy-row-${row.id}`}>
              {row.image_url ? (
                <img src={row.image_url} alt={row.label || 'legacy post'}
                  className="w-10 h-10 rounded-md object-cover bg-zinc-100"/>
              ) : (
                <div className="w-10 h-10 rounded-md bg-zinc-100 flex items-center justify-center text-zinc-400">
                  <ImageIcon size={14}/>
                </div>
              )}
              <div className="flex-1 min-w-0">
                <p className="font-bold truncate">{row.label || 'Untitled'}</p>
                <p className="text-[11px] text-zinc-500 truncate">
                  {row.channel || 'unknown'} · {row.campaign || 'general'} · {row.created_at?.slice(0, 10) || ''}
                </p>
              </div>
              <button
                type="button" onClick={() => remove(row.id)}
                disabled={busy === row.id}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-bold border border-rose-200 text-rose-700 hover:bg-rose-50 disabled:opacity-50"
                data-testid={`social-legacy-delete-${row.id}`}
              >
                {busy === row.id ? <Loader2 size={11} className="animate-spin"/> : <Trash2 size={11}/>}
                Delete
              </button>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

export default function SocialAutopilotPanel() {
  const [status, setStatus] = useState(null);
  const [posts, setPosts] = useState([]);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState('');
  const [channelFilter, setChannelFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');

  const load = useCallback(async (opts) => {
    setErr(null);
    if (opts && opts.silent !== true) setBusy('refresh');
    try {
      const [s, p] = await Promise.all([
        axios.get(`${API}/api/marketing/social-autopilot/status`, { headers: auth() }),
        axios.get(`${API}/api/marketing/social-autopilot/posts?limit=60`, { headers: auth() }),
      ]);
      setStatus(s.data);
      setPosts(p.data?.posts || []);
      if (opts && opts.silent !== true && opts !== undefined) {
        notify.success(`Refreshed · ${p.data?.posts?.length || 0} posts loaded`);
      }
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Could not load Social Autopilot');
    } finally {
      if (opts && opts.silent !== true) setBusy('');
    }
  }, []);

  useEffect(() => { load({ silent: true }); }, [load]);

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
      await load({ silent: true });
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
      await load({ silent: true });
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
        className="rounded-2xl border border-fuchsia-200 dark:border-fuchsia-900 bg-gradient-to-r from-fuchsia-50 via-white to-blue-50 dark:from-zinc-900 dark:via-zinc-900 dark:to-zinc-900 px-4 sm:px-5 py-4"
        data-testid="social-autopilot-hero"
      >
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4">
          <div className="flex items-start gap-3 sm:contents">
            <span className="shrink-0 w-10 h-10 sm:w-12 sm:h-12 rounded-2xl bg-gradient-to-br from-fuchsia-500 to-blue-600 text-white flex items-center justify-center shadow-[0_8px_20px_-8px_rgba(217,70,239,0.6)]">
              <Share2 size={18}/>
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-[10px] sm:text-[11px] uppercase tracking-[0.18em] font-bold text-fuchsia-700 dark:text-fuchsia-400">Growth · Social Autopilot</p>
              <h2 className="text-lg sm:text-2xl font-extrabold text-zinc-900 dark:text-zinc-50 tracking-tight mt-0.5 leading-tight">Daily IG · TikTok · LinkedIn drafts</h2>
              <p className="hidden sm:block text-xs sm:text-sm text-zinc-600 dark:text-zinc-300 mt-1 max-w-2xl">
                Channel-aware tone (fun on IG/TikTok, decision-maker on LinkedIn), brand-coloured imagery, 50% feature promotion / 50% industry insight. Review, approve and copy/download — manual posting keeps you in full control.
              </p>
              <p className="sm:hidden text-xs text-zinc-600 dark:text-zinc-300 mt-1 leading-snug">
                Channel-aware tone · brand imagery · 50/50 feature/insight. Review &amp; approve from here.
              </p>
              <p className="text-[11px] text-zinc-500 dark:text-zinc-400 mt-1.5 inline-flex items-center gap-1.5" data-testid="social-schedule-strip">
                <Clock size={10}/>
                {status.enabled ? (
                  <>Fires daily at <b className="tabular-nums">{String(status.hour_uk ?? 9).padStart(2, '0')}:00</b> · {status.ran_today ? 'fired today' : 'next run today'}</>
                ) : (
                  <>Daily loop is paused</>
                )}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 w-full sm:w-auto sm:shrink-0">
            <button
              type="button" onClick={runDaily}
              disabled={busy === 'run' || status.ran_today}
              className="flex-1 sm:flex-initial inline-flex items-center justify-center gap-1.5 px-3 py-2 sm:py-1.5 rounded-md text-xs font-bold text-white bg-fuchsia-600 hover:bg-fuchsia-700 disabled:opacity-50"
              data-testid="social-run-now-btn"
              title={status.ran_today ? 'Already ran today — use Generate per channel to add more' : 'Generate today\'s drafts for all 3 channels'}
            >
              {busy === 'run' ? <Loader2 size={11} className="animate-spin"/> : <PlayCircle size={11}/>}
              Run today
            </button>
            <button
              type="button" onClick={() => load({ silent: false })}
              disabled={busy === 'refresh'}
              className="flex-1 sm:flex-initial inline-flex items-center justify-center gap-1.5 px-3 py-2 sm:py-1.5 rounded-md text-xs font-bold border border-zinc-200 dark:border-zinc-700 text-zinc-700 dark:text-zinc-100 hover:border-fuchsia-400 bg-white dark:bg-zinc-950 disabled:opacity-60"
              data-testid="social-refresh"
            >
              {busy === 'refresh' ? <Loader2 size={11} className="animate-spin"/> : <RefreshCw size={11}/>}
              {busy === 'refresh' ? 'Refreshing…' : 'Refresh'}
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
      <div className="flex items-center gap-x-2 gap-y-2 flex-wrap" data-testid="social-filters">
        <span className="text-[11px] uppercase font-bold text-zinc-500 mr-1 shrink-0">Channel</span>
        {['all', 'instagram', 'tiktok', 'linkedin'].map((id) => (
          <button
            key={id} type="button" onClick={() => setChannelFilter(id)}
            className={`text-[11px] font-bold px-2.5 py-1 rounded-full border ${channelFilter === id ? 'bg-zinc-900 text-white border-zinc-900' : 'border-zinc-200 text-zinc-700 hover:border-zinc-400'}`}
            data-testid={`social-filter-channel-${id}`}
          >
            {id === 'all' ? 'All' : (CHANNEL_VISUAL[id]?.label || id)}
          </button>
        ))}
        <span className="text-[11px] uppercase font-bold text-zinc-500 mx-1 sm:ml-3 shrink-0">Status</span>
        {['all', 'draft', 'approved', 'archived'].map((id) => (
          <button
            key={id} type="button" onClick={() => setStatusFilter(id)}
            className={`text-[11px] font-bold px-2.5 py-1 rounded-full border ${statusFilter === id ? 'bg-zinc-900 text-white border-zinc-900' : 'border-zinc-200 text-zinc-700 hover:border-zinc-400'}`}
            data-testid={`social-filter-status-${id}`}
          >
            {id === 'all' ? 'All' : id.charAt(0).toUpperCase() + id.slice(1)}
          </button>
        ))}
        <div className="hidden sm:block flex-1"/>
        <span className="text-[11px] text-zinc-500 ml-auto sm:ml-0" data-testid="social-result-count">
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
            <PostCard key={p.id} post={p} onChange={load}/>
          ))}
        </div>
      )}

      {/* Iter 220bw — Launch campaigns + tracked-post crawler */}
      <CampaignsSection/>
      <TrackedPostsSection/>

      {/* Legacy library cleanup section — only renders if there are
          orphaned rows in the old social_media_library collection. */}
      <LegacyLibrarySection/>
    </div>
  );
}
