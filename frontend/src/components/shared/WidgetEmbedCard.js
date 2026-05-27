/**
 * WidgetEmbedCard — Iter 220aa.
 *
 * Snippet-builder card. Lists existing embeds with submission counts,
 * generates new ones, copies the `<iframe>` HTML to the clipboard, and
 * revokes tokens.
 *
 * Renders for BOTH owner types — engineer or organization — via the
 * unified `/api/widget/my-embeds` endpoint, which picks the right
 * inbox under the hood.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import {
  Code, Copy, Check, ExternalLink, Plus, Trash2, AlertCircle,
  Loader2, Inbox,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL;
const FRONTEND_BASE = (typeof window !== 'undefined' ? window.location.origin : '');

const snippetFor = (token) => (
  `<iframe src="${FRONTEND_BASE}/embed/log-fault/${token}"
    width="100%" height="640" style="border:0; max-width:480px"
    title="Log a fault"></iframe>`
);

export default function WidgetEmbedCard({ ownerType = 'partner_engineer' }) {
  const [embeds, setEmbeds] = useState(null);
  const [creating, setCreating] = useState(false);
  const [copied, setCopied] = useState(null);
  const [error, setError] = useState(null);

  const auth = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

  const load = async () => {
    try {
      const r = await axios.get(`${API}/api/widget/my-embeds`, { headers: auth() });
      setEmbeds(r.data.embeds || []);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not load widget embeds');
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const create = async () => {
    setCreating(true); setError(null);
    try {
      await axios.post(
        `${API}/api/widget/embeds`,
        {
          owner_type: ownerType,
          label: ownerType === 'partner_engineer' ? 'Log a fault' : 'Get a quote',
          show_reviews_badge: true,
        },
        { headers: auth() },
      );
      await load();
      notify.success('Widget created');
    } catch (e) {
      const d = e?.response?.data?.detail;
      setError(typeof d === 'string' ? d : 'Could not create widget');
    } finally {
      setCreating(false);
    }
  };

  const copy = async (token) => {
    try {
      await navigator.clipboard.writeText(snippetFor(token));
      setCopied(token);
      notify.success('Snippet copied');
      setTimeout(() => setCopied(null), 2500);
    } catch (_e) {
      notify.error('Could not copy — select the snippet manually');
    }
  };

  const revoke = async (id) => {
    if (!window.confirm('Revoke this widget? Submissions will stop landing in your inbox.')) {
      return;
    }
    try {
      await axios.delete(`${API}/api/widget/embeds/${id}`, { headers: auth() });
      await load();
      notify.success('Widget revoked');
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not revoke');
    }
  };

  if (embeds === null && !error) {
    return (
      <div className="rounded-2xl border border-zinc-200 bg-white p-6 flex items-center justify-center">
        <Loader2 className="animate-spin text-blue-600" size={20} />
      </div>
    );
  }

  return (
    <div
      className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 overflow-hidden"
      data-testid="widget-embed-card"
    >
      <div className="px-5 py-4 flex items-center gap-3 border-b border-zinc-100 dark:border-zinc-800">
        <span className="w-9 h-9 rounded-xl bg-violet-600 text-white flex items-center justify-center">
          <Code size={16} />
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold text-zinc-900 dark:text-zinc-50">
            Embed on your own website
          </p>
          <p className="text-[11px] text-zinc-500 dark:text-zinc-400">
            {ownerType === 'partner_engineer'
              ? 'Drop a "Log a Fault" form on your site — submissions land in your engineer inbox.'
              : 'Drop a "Get a Quote" form on your site — submissions land as CRM leads.'}
          </p>
        </div>
        <button
          type="button"
          onClick={create}
          disabled={creating}
          className="shrink-0 inline-flex items-center gap-1 px-3 py-1.5 rounded-md text-xs font-bold text-white bg-violet-600 hover:bg-violet-700 disabled:opacity-50 transition-colors"
          data-testid="widget-embed-create-btn"
        >
          {creating ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
          New embed
        </button>
      </div>

      <div className="p-5 space-y-3">
        {error ? (
          <div
            className="rounded-md border border-rose-200 bg-rose-50 text-rose-700 text-sm px-3 py-2 inline-flex items-center gap-2"
            data-testid="widget-embed-error"
          >
            <AlertCircle size={14} /> {error}
          </div>
        ) : null}

        {(embeds || []).length === 0 ? (
          <div
            className="rounded-xl border border-dashed border-zinc-300 dark:border-zinc-700 p-6 text-center"
            data-testid="widget-embed-empty"
          >
            <Inbox size={24} className="text-zinc-300 dark:text-zinc-600 mx-auto mb-1" />
            <p className="text-sm text-zinc-600 dark:text-zinc-300 font-medium">
              No embeds yet
            </p>
            <p className="text-[11px] text-zinc-500 mt-1">
              Click "New embed" to generate your first iframe snippet.
            </p>
          </div>
        ) : null}

        {(embeds || []).map((e) => {
          const url = `${FRONTEND_BASE}/embed/log-fault/${e.token}`;
          const snippet = snippetFor(e.token);
          return (
            <div
              key={e.id}
              className="rounded-xl border border-zinc-200 dark:border-zinc-700 p-4"
              data-testid={`widget-embed-row-${e.id}`}
            >
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-bold text-zinc-900 dark:text-zinc-50">
                    {e.label || (ownerType === 'partner_engineer' ? 'Log a fault' : 'Get a quote')}
                  </p>
                  <p className="text-[11px] text-zinc-500 dark:text-zinc-400 mt-0.5">
                    {(e.submission_count || 0)} submission{(e.submission_count || 0) === 1 ? '' : 's'}
                    {e.last_submission_at ? ` · last ${new Date(e.last_submission_at).toLocaleDateString()}` : ''}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <a
                    href={url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-bold bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 text-zinc-700 dark:text-zinc-100 hover:border-violet-400 transition-colors"
                    data-testid={`widget-embed-preview-${e.id}`}
                  >
                    <ExternalLink size={11} /> Preview
                  </a>
                  <button
                    type="button"
                    onClick={() => revoke(e.id)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-bold bg-rose-50 border border-rose-100 text-rose-700 hover:bg-rose-100 transition-colors"
                    data-testid={`widget-embed-revoke-${e.id}`}
                    aria-label="Revoke widget"
                  >
                    <Trash2 size={11} /> Revoke
                  </button>
                </div>
              </div>
              <div className="mt-3 rounded-md bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 p-2.5 relative">
                <pre
                  className="text-[11px] text-zinc-700 dark:text-zinc-300 overflow-x-auto whitespace-pre-wrap break-all font-mono leading-relaxed pr-12"
                  data-testid={`widget-embed-snippet-${e.id}`}
                >{snippet}</pre>
                <button
                  type="button"
                  onClick={() => copy(e.token)}
                  className="absolute top-2 right-2 inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-bold bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 hover:opacity-90 transition-opacity"
                  data-testid={`widget-embed-copy-${e.id}`}
                >
                  {copied === e.token ? <Check size={10} /> : <Copy size={10} />}
                  {copied === e.token ? 'Copied' : 'Copy'}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
