/**
 * SocialMediaLibraryPanel
 *
 * Master-admin curated library of ready-to-publish social media posts
 * (image + caption + hashtags + channel + posting notes). Cards offer
 * one-tap Download Image, Copy Caption, Copy Hashtags so the operator
 * can drop straight into Instagram / LinkedIn / etc.
 */
import { useEffect, useState, useCallback, useMemo } from 'react';
import axios from 'axios';
import { useAuth } from '@/App';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import {
  Megaphone, Plus, Trash2, Loader2, RefreshCw, Image as ImageIcon,
  Download, Copy, Hash, Instagram, Linkedin, Facebook, Twitter,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { SkeletonCard, SkeletonLine } from '@/components/shared/Skeleton';

const CHANNELS = [
  { id: 'instagram', label: 'Instagram', Icon: Instagram, color: 'from-fuchsia-500 to-rose-500' },
  { id: 'linkedin',  label: 'LinkedIn',  Icon: Linkedin,  color: 'from-sky-500 to-blue-600' },
  { id: 'facebook',  label: 'Facebook',  Icon: Facebook,  color: 'from-blue-500 to-indigo-600' },
  { id: 'twitter',   label: 'X / Twitter', Icon: Twitter, color: 'from-zinc-700 to-zinc-900' },
  { id: 'tiktok',    label: 'TikTok',    Icon: Megaphone, color: 'from-rose-500 to-cyan-500' },
  { id: 'all',       label: 'Cross-channel', Icon: Megaphone, color: 'from-emerald-500 to-teal-600' },
];

const channelMeta = (id) => CHANNELS.find((c) => c.id === id) || CHANNELS[0];

const SocialMediaLibraryPanel = () => {
  const { API } = useAuth();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [filter, setFilter] = useState('all');
  const [draft, setDraft] = useState({
    label: '',
    image_url: '',
    channel: 'instagram',
    campaign: 'general',
    caption: '',
    hashtags: '',
    notes: '',
    post_order: 0,
  });

  const headers = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/master-admin/social-media-library`, { headers: headers() });
      setRows(r.data?.rows || []);
      if (r.data?.seeded > 0) {
        notify.success('Library seeded', `${r.data.seeded} posts pre-loaded for you.`);
      }
    } catch (e) {
      notify.error('Could not load library', e.response?.data?.detail);
    }
    setLoading(false);
  }, [API]);

  useEffect(() => { load(); }, [load]);

  const handleAdd = async () => {
    if (!draft.label.trim() || !draft.image_url.trim()) {
      notify.error('Missing fields', 'Label and image URL are required.');
      return;
    }
    setAdding(true);
    try {
      await axios.post(
        `${API}/master-admin/social-media-library`,
        {
          ...draft,
          hashtags: draft.hashtags.split(',').map((t) => t.trim()).filter(Boolean),
        },
        { headers: headers() },
      );
      notify.success('Added to social library', draft.label);
      setDraft({
        label: '', image_url: '', channel: 'instagram', campaign: 'general',
        caption: '', hashtags: '', notes: '', post_order: 0,
      });
      await load();
    } catch (e) {
      notify.error('Add failed', e.response?.data?.detail);
    }
    setAdding(false);
  };

  const handleDelete = async (row) => {
    if (!window.confirm(`Remove "${row.label}" from the social library?`)) return;
    try {
      await axios.delete(`${API}/master-admin/social-media-library/${row.id}`, { headers: headers() });
      notify.success('Removed', row.label);
      await load();
    } catch (e) {
      notify.error('Delete failed', e.response?.data?.detail);
    }
  };

  const downloadImage = async (row) => {
    // Mobile-friendly download. Browsers (iOS Safari especially) ignore
    // the <a download> blob trick. Strategy:
    //   1. Web Share API with files  -> native share sheet, "Save to Photos"
    //   2. <a download> blob          -> desktop browsers
    //   3. window.open                -> fallback so user can long-press save
    try {
      const res = await fetch(row.image_url, { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const ext = (row.image_url.split('.').pop() || 'png').split('?')[0].slice(0, 5) || 'png';
      const safe = row.label.replace(/[^a-z0-9]+/gi, '_').replace(/_+/g, '_').toLowerCase();
      const filename = `${safe}.${ext}`;

      const file = new File([blob], filename, { type: blob.type || 'image/png' });

      // 1) Try Web Share API (works on iOS Safari 15+ and modern Android Chrome).
      if (
        typeof navigator !== 'undefined' &&
        typeof navigator.canShare === 'function' &&
        navigator.canShare({ files: [file] }) &&
        typeof navigator.share === 'function'
      ) {
        try {
          await navigator.share({
            files: [file],
            title: row.label,
            text: 'Social media post',
          });
          notify.success('Ready to save', 'Tap "Save to Photos" or "Save to Files" in the share sheet.');
          return;
        } catch (shareErr) {
          if (shareErr?.name === 'AbortError') return; // user cancelled the share sheet
          // otherwise fall through to download fallback below
        }
      }

      // 2) Desktop: classic blob + <a download>.
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      const safe2 = row.label.replace(/[^a-z0-9]+/gi, '_').replace(/_+/g, '_').toLowerCase();
      const ext2 = (row.image_url.split('.').pop() || 'png').split('?')[0].slice(0, 5) || 'png';
      a.href = blobUrl;
      a.download = `${safe2}.${ext2}`;
      a.rel = 'noopener';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(blobUrl);
      notify.success('Downloaded', `${safe2}.${ext2}`);
    } catch (e) {
      // 3) Last-resort fallback: open image so the user can long-press.
      try {
        window.open(row.image_url, '_blank', 'noopener');
        notify.success('Opened in new tab', 'Long-press the image and choose "Save Image".');
      } catch (openErr) {
        notify.error('Download failed', e.message || 'Could not save image.');
      }
    }
  };

  const copyText = async (text, friendly) => {
    try {
      await navigator.clipboard.writeText(text);
      notify.success('Copied', friendly);
    } catch (e) {
      notify.error('Copy failed', e.message);
    }
  };

  const grouped = useMemo(() => {
    const filtered = filter === 'all' ? rows : rows.filter((r) => r.channel === filter);
    const byCampaign = {};
    filtered.forEach((r) => {
      const k = r.campaign || 'general';
      if (!byCampaign[k]) byCampaign[k] = [];
      byCampaign[k].push(r);
    });
    Object.values(byCampaign).forEach((arr) =>
      arr.sort((a, b) => (a.post_order ?? 0) - (b.post_order ?? 0)),
    );
    const order = ['mosaic_9up', 'switch_thread', 'evergreen', 'general'];
    return Object.keys(byCampaign)
      .sort((a, b) => {
        const ai = order.indexOf(a); const bi = order.indexOf(b);
        return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi);
      })
      .map((k) => ({ campaign: k, rows: byCampaign[k] }));
  }, [rows, filter]);

  const channelCount = (id) => rows.filter((r) => r.channel === id).length;

  return (
    <div className="space-y-4" data-testid="social-media-library-panel">
      <Card className="p-5 border-zinc-200">
        <div className="flex items-start justify-between mb-4 flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <Megaphone size={20} className="text-fuchsia-600" />
            <div>
              <h3 className="text-base font-semibold text-zinc-900">Social media post library</h3>
              <p className="text-xs text-zinc-500 mt-0.5">
                Ready-to-publish posts: image + caption + hashtags. Tap{' '}
                <span className="font-semibold">Download</span> to save the image,{' '}
                <span className="font-semibold">Copy caption</span>, then paste straight into Instagram /
                LinkedIn / etc. <strong>{rows.length}</strong> posts available.
              </p>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={load} data-testid="social-library-refresh">
            <RefreshCw size={13} className="mr-1" /> Refresh
          </Button>
        </div>

        {/* Add form */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-2 p-3 bg-zinc-50 rounded-lg border border-dashed border-zinc-200" data-testid="social-add-row">
          <Input
            value={draft.label}
            onChange={(e) => setDraft({ ...draft, label: e.target.value })}
            placeholder="Label (e.g. Mosaic · Tile 05 · GA hero)"
            className="md:col-span-3 h-9"
            data-testid="social-add-label"
          />
          <Input
            value={draft.image_url}
            onChange={(e) => setDraft({ ...draft, image_url: e.target.value })}
            placeholder="Image URL (https://… or /marketing/…)"
            className="md:col-span-4 h-9"
            data-testid="social-add-url"
          />
          <select
            value={draft.channel}
            onChange={(e) => setDraft({ ...draft, channel: e.target.value })}
            className="md:col-span-2 h-9 rounded-md border border-zinc-200 bg-white px-2 text-sm"
            data-testid="social-add-channel"
          >
            {CHANNELS.map((c) => (
              <option key={c.id} value={c.id}>{c.label}</option>
            ))}
          </select>
          <Input
            value={draft.campaign}
            onChange={(e) => setDraft({ ...draft, campaign: e.target.value })}
            placeholder="Campaign tag"
            className="md:col-span-2 h-9"
            data-testid="social-add-campaign"
          />
          <Button
            onClick={handleAdd}
            disabled={adding}
            className="md:col-span-1 h-9 bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white"
            data-testid="social-add-btn"
          >
            {adding ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
          </Button>
          <Textarea
            value={draft.caption}
            onChange={(e) => setDraft({ ...draft, caption: e.target.value })}
            placeholder="Caption / post copy"
            className="md:col-span-8 min-h-[68px] text-sm"
            data-testid="social-add-caption"
          />
          <Input
            value={draft.hashtags}
            onChange={(e) => setDraft({ ...draft, hashtags: e.target.value })}
            placeholder="hashtags, comma, separated"
            className="md:col-span-4 h-9"
            data-testid="social-add-hashtags"
          />
        </div>
      </Card>

      {/* Channel filter */}
      <div className="flex items-center gap-2 flex-wrap">
        <button
          type="button"
          onClick={() => setFilter('all')}
          className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${filter === 'all' ? 'bg-zinc-900 text-white' : 'bg-zinc-100 text-zinc-700 hover:bg-zinc-200'}`}
          data-testid="social-filter-all"
        >
          All ({rows.length})
        </button>
        {CHANNELS.map((c) => {
          const count = channelCount(c.id);
          if (!count) return null;
          const Icon = c.Icon;
          return (
            <button
              key={c.id}
              type="button"
              onClick={() => setFilter(c.id)}
              className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors flex items-center gap-1.5 ${filter === c.id ? 'bg-zinc-900 text-white' : 'bg-zinc-100 text-zinc-700 hover:bg-zinc-200'}`}
              data-testid={`social-filter-${c.id}`}
            >
              <Icon size={12} /> {c.label} ({count})
            </button>
          );
        })}
      </div>

      {/* Body */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3" data-testid="social-loading">
          {[0,1,2,3,4,5].map((i) => (
            <SkeletonCard key={i} className="overflow-hidden">
              <div className="h-44 -mx-4 -mt-4 mb-3 bg-zinc-200/70 dark:bg-white/[0.07] animate-pulse" />
              <SkeletonLine className="mb-2" width="65%" />
              <SkeletonLine width="90%" />
            </SkeletonCard>
          ))}
        </div>
      ) : rows.length === 0 ? (
        <Card className="p-10 text-center border-zinc-200">
          <ImageIcon size={32} className="text-zinc-300 mx-auto mb-3" />
          <p className="text-sm text-zinc-500">No posts yet. Add one above.</p>
        </Card>
      ) : (
        <div className="space-y-6">
          {grouped.map(({ campaign, rows: items }) => (
            <div key={campaign} data-testid={`social-campaign-${campaign}`}>
              <div className="flex items-center gap-2 mb-3">
                <h4 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
                  {campaign === 'mosaic_9up' ? '🟦 Mosaic — 9-tile Instagram grid'
                    : campaign === 'switch_thread' ? '🧵 9 Reasons They Switch — carousel'
                    : campaign}
                </h4>
                <Badge className="bg-zinc-100 text-zinc-600 border border-zinc-200 text-[10px]">
                  {items.length} posts
                </Badge>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                {items.map((row) => {
                  const meta = channelMeta(row.channel);
                  const ChannelIcon = meta.Icon;
                  return (
                    <Card
                      key={row.id}
                      className="overflow-hidden border-zinc-200 group flex flex-col"
                      data-testid={`social-card-${row.id}`}
                    >
                      <div className="aspect-square bg-zinc-50 relative">
                        <img
                          src={row.image_url}
                          alt={row.label}
                          loading="lazy"
                          className="w-full h-full object-cover"
                          onError={(e) => { e.target.style.opacity = 0.2; }}
                        />
                        <div className={`absolute top-2 left-2 flex items-center gap-1.5 px-2 py-1 rounded-full bg-gradient-to-r ${meta.color} text-white text-[10px] font-semibold`}>
                          <ChannelIcon size={10} /> {meta.label}
                        </div>
                        {row.post_order > 0 && (
                          <div className="absolute top-2 right-2 px-2 py-1 rounded-full bg-black/70 text-white text-[10px] font-semibold">
                            #{row.post_order}
                          </div>
                        )}
                        <button
                          type="button"
                          onClick={() => handleDelete(row)}
                          className="absolute bottom-2 right-2 p-1.5 rounded-md bg-white/90 backdrop-blur text-rose-600 opacity-0 group-hover:opacity-100 transition-opacity hover:bg-white"
                          data-testid={`social-delete-${row.id}`}
                          title="Remove from library"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                      <div className="p-3 flex flex-col gap-2 flex-1">
                        <div>
                          <p className="text-sm font-semibold text-zinc-900 leading-snug">{row.label}</p>
                          {row.notes && (
                            <p className="text-[11px] text-zinc-500 mt-0.5 italic">{row.notes}</p>
                          )}
                        </div>
                        {row.caption && (
                          <p className="text-[12px] text-zinc-700 whitespace-pre-line line-clamp-4 leading-snug">
                            {row.caption}
                          </p>
                        )}
                        {row.hashtags?.length > 0 && (
                          <div className="flex items-center gap-1 flex-wrap">
                            {row.hashtags.slice(0, 6).map((h) => (
                              <span
                                key={h}
                                className="text-[10px] text-blue-700 bg-blue-50 border border-blue-100 px-1.5 py-0.5 rounded"
                              >
                                #{h}
                              </span>
                            ))}
                            {row.hashtags.length > 6 && (
                              <span className="text-[10px] text-zinc-400">+{row.hashtags.length - 6}</span>
                            )}
                          </div>
                        )}
                        <div className="flex items-center gap-1.5 mt-auto pt-2 border-t border-zinc-100">
                          <Button
                            size="sm"
                            onClick={() => downloadImage(row)}
                            className="flex-1 h-8 bg-[var(--color-brand-blue)] hover:bg-[var(--color-brand-blue-hover)] text-white text-xs"
                            data-testid={`social-download-${row.id}`}
                            title="Save image (uses your phone's share sheet on mobile)"
                          >
                            <Download size={12} className="mr-1" /> Save
                          </Button>
                          <a
                            href={row.image_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="h-8 px-2 inline-flex items-center justify-center rounded-md border border-zinc-200 text-zinc-700 hover:bg-zinc-50 text-xs"
                            data-testid={`social-open-${row.id}`}
                            title="Open image (long-press on mobile to save to Photos)"
                          >
                            <ImageIcon size={12} />
                          </a>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => copyText(row.caption, 'Caption copied to clipboard')}
                            className="flex-1 h-8 text-xs"
                            disabled={!row.caption}
                            data-testid={`social-copy-caption-${row.id}`}
                          >
                            <Copy size={12} className="mr-1" /> Caption
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => copyText(row.hashtags.map((h) => `#${h}`).join(' '), 'Hashtags copied')}
                            className="h-8 text-xs px-2"
                            disabled={!row.hashtags?.length}
                            data-testid={`social-copy-tags-${row.id}`}
                            title="Copy hashtags"
                          >
                            <Hash size={12} />
                          </Button>
                        </div>
                      </div>
                    </Card>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default SocialMediaLibraryPanel;
