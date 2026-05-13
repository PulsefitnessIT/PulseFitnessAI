/**
 * Marketing Starter Pack panel — iter 216h71.
 *
 * Sits below the Brand Auto-Discovery panel in Brand Kit. Lets the
 * operator one-click "Generate my starter pack" — Claude Haiku 4.5
 * drafts 3 email templates (welcome / win-back / promo) + 3 social
 * posts (Instagram / Facebook / X) in their tone-of-voice using the
 * audience segments + campaigns extracted by brand discovery.
 *
 * The drafts are persisted server-side so the operator can return to
 * them later. Each draft has a "Copy to clipboard" button so they can
 * paste into their email tool or scheduler.
 */
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  Wand2, Mail, Instagram, Facebook, Twitter, Loader2, Sparkles,
  CheckCircle2, Copy, Trash2,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const EMAIL_META = {
  welcome:  { label: 'Welcome',  hint: 'For new sign-ups',         color: '#10b981' },
  win_back: { label: 'Win-back', hint: 'For lapsed members',       color: '#f59e0b' },
  promo:    { label: 'Promo',    hint: 'Current campaign push',    color: '#6366f1' },
};
const SOCIAL_META = {
  instagram: { label: 'Instagram', Icon: Instagram, color: '#e1306c' },
  facebook:  { label: 'Facebook',  Icon: Facebook,  color: '#1877f2' },
  x:         { label: 'X',         Icon: Twitter,   color: '#0f1419' },
};

export default function StarterPackPanel({ API, headers }) {
  const [doc, setDoc] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/api/marketing/starter-pack`, { headers });
      setDoc(r.data || null);
    } catch {
      /* tolerated */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [API, headers]);

  useEffect(() => { load(); }, [load]);

  const generate = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/api/marketing/starter-pack/generate`, {}, { headers });
      setDoc(r.data);
      notify.success('Starter pack drafted — review & tweak below.');
    } catch (e) {
      notifyApiError(notify, e, 'Could not draft your starter pack');
    } finally {
      setBusy(false);
    }
  };

  const clear = async () => {
    if (!window.confirm('Clear your starter pack drafts?')) return;
    setBusy(true);
    try {
      await axios.delete(`${API}/api/marketing/starter-pack`, { headers });
      setDoc(null);
      notify.success('Starter pack cleared.');
    } catch (e) {
      notifyApiError(notify, e, 'Could not clear');
    } finally {
      setBusy(false);
    }
  };

  const copyToClipboard = async (text, label) => {
    try {
      await navigator.clipboard.writeText(text);
      notify.success(`${label} copied to clipboard`);
    } catch {
      notify.error('Clipboard unavailable in this browser');
    }
  };

  const pack = doc?.pack;

  return (
    <div
      className="rounded-2xl border p-5 mb-5"
      style={{
        background: 'linear-gradient(135deg, rgba(168,85,247,0.05), rgba(236,72,153,0.05))',
        borderColor: 'rgba(168,85,247,0.25)',
      }}
      data-testid="starter-pack-panel"
    >
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <div className="text-[10px] uppercase tracking-wider font-extrabold text-purple-500 flex items-center gap-1.5">
            <Wand2 size={11} /> Marketing starter pack
          </div>
          <h3 className="text-base font-bold mt-1">3 emails + 3 social posts in your tone</h3>
          <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1 max-w-xl">
            We'll use your brand voice, audience segments and current campaigns to draft a
            welcome email, a win-back email, a promo email, and three social posts. Edit
            anything before you send.
          </p>
        </div>
        {pack && (
          <button onClick={clear} disabled={busy}
            className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 hover:text-zinc-700 flex items-center gap-1 disabled:opacity-50"
            data-testid="starter-pack-clear">
            <Trash2 size={10} /> Clear
          </button>
        )}
      </div>

      {!pack && (
        <button
          onClick={generate}
          disabled={busy}
          className="px-5 py-2.5 text-sm font-bold rounded-md bg-purple-600 hover:bg-purple-700 text-white disabled:opacity-50 flex items-center gap-1.5"
          data-testid="starter-pack-generate"
        >
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
          Draft my starter pack
        </button>
      )}

      {pack && (
        <div className="space-y-4" data-testid="starter-pack-drafts">
          {/* Emails */}
          <Section icon={Mail} title="Email templates">
            <div className="space-y-2">
              {(pack.emails || []).map((em) => {
                const meta = EMAIL_META[em.id] || { label: em.id, hint: '', color: '#71717a' };
                return (
                  <details key={em.id} className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 group">
                    <summary className="cursor-pointer p-3 flex items-center gap-2 list-none">
                      <span className="w-1.5 h-6 rounded shrink-0" style={{ background: meta.color }} />
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-bold uppercase tracking-wider" style={{ color: meta.color }}>
                          {meta.label} <span className="text-zinc-400 ml-1 normal-case">· {meta.hint}</span>
                        </div>
                        <div className="text-sm font-semibold mt-0.5 truncate">{em.subject}</div>
                        <div className="text-xs text-zinc-500 dark:text-zinc-400 truncate">{em.preview}</div>
                      </div>
                      <button
                        onClick={(e) => { e.preventDefault(); e.stopPropagation(); copyToClipboard(`Subject: ${em.subject}\nPreview: ${em.preview}\n\n${em.body}`, `${meta.label} email`); }}
                        className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded flex items-center gap-1"
                        data-testid={`starter-pack-copy-email-${em.id}`}>
                        <Copy size={10} /> Copy
                      </button>
                    </summary>
                    <div className="px-4 pb-3 text-xs whitespace-pre-wrap font-mono leading-relaxed text-zinc-700 dark:text-zinc-300 border-t border-zinc-100 dark:border-zinc-800 pt-2 mt-1">
                      {em.body}
                    </div>
                  </details>
                );
              })}
            </div>
          </Section>

          {/* Social */}
          <Section icon={Sparkles} title="Social posts">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              {(pack.social || []).map((sp) => {
                const meta = SOCIAL_META[sp.id] || { label: sp.platform, Icon: Sparkles, color: '#71717a' };
                const Icon = meta.Icon;
                return (
                  <div key={sp.id} className="rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 p-3" data-testid={`starter-pack-social-${sp.id}`}>
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider" style={{ color: meta.color }}>
                        <Icon size={11} /> {meta.label}
                      </div>
                      <button
                        onClick={() => copyToClipboard(sp.body, `${meta.label} post`)}
                        className="px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded flex items-center gap-0.5"
                        data-testid={`starter-pack-copy-social-${sp.id}`}>
                        <Copy size={9} /> Copy
                      </button>
                    </div>
                    <p className="text-xs whitespace-pre-wrap leading-relaxed text-zinc-700 dark:text-zinc-300">{sp.body}</p>
                  </div>
                );
              })}
            </div>
          </Section>

          <div className="rounded-md bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-900 p-2.5 text-xs flex items-start gap-2">
            <CheckCircle2 size={12} className="text-emerald-600 dark:text-emerald-400 mt-0.5 shrink-0" />
            <span className="text-emerald-700 dark:text-emerald-200">
              <strong>Drafts saved.</strong> Copy any one to your email tool / scheduler, or re-generate after a fresh brand refresh.
            </span>
          </div>

          <div className="flex justify-end pt-1">
            <button onClick={generate} disabled={busy}
              className="px-3 py-1.5 text-xs font-medium text-purple-600 dark:text-purple-400 hover:bg-purple-50 dark:hover:bg-purple-900/20 rounded-md flex items-center gap-1.5 disabled:opacity-50"
              data-testid="starter-pack-regenerate">
              {busy ? <Loader2 size={11} className="animate-spin" /> : <Wand2 size={11} />}
              Re-generate
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Section({ icon: Icon, title, children }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 dark:text-zinc-400 flex items-center gap-1.5 mb-2">
        {Icon && <Icon size={11} />} {title}
      </div>
      {children}
    </div>
  );
}
