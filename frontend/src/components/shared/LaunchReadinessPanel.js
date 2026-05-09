/**
 * Pre-launch readiness panel — Iter 216bc.
 *
 * Single panel under Settings → Launch that lets the operator:
 *   • Set their email-sender friendly name + reply-to (per-org branding)
 *   • Load / clear sample data
 *
 * Surfaces inside MembershipsConsole's Settings tab — embedded, not a
 * full-screen wizard. The trial / live operator can come back to it
 * any time.
 */
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  Mail, Loader2, Save, CheckCircle2, AlertTriangle, Database,
  Trash2, Sparkles, Eye,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function LaunchReadinessPanel() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const headers = { Authorization: `Bearer ${token}` };

  const [sender, setSender] = useState({ friendly_name: '', reply_to: '', preview_from: '' });
  const [savingSender, setSavingSender] = useState(false);
  const [savedSender, setSavedSender] = useState(false);

  const [sampleBusy, setSampleBusy] = useState(false);
  const [sampleResult, setSampleResult] = useState(null);

  const loadSender = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/launch/email-sender`, { headers });
      setSender({
        friendly_name: data.friendly_name || '',
        reply_to: data.reply_to || '',
        preview_from: data.preview_from || '',
      });
    } catch { /* noop */ }
    // eslint-disable-next-line
  }, []);
  useEffect(() => { loadSender(); }, [loadSender]);

  const saveSender = async () => {
    setSavingSender(true); setSavedSender(false);
    try {
      const { data } = await axios.post(`${API}/launch/email-sender`,
        { friendly_name: sender.friendly_name || null, reply_to: sender.reply_to || null },
        { headers });
      setSender((s) => ({ ...s, preview_from: data.preview_from || s.preview_from }));
      setSavedSender(true);
      setTimeout(() => setSavedSender(false), 2500);
    } catch { /* swallow */ }
    setSavingSender(false);
  };

  const loadSample = async () => {
    setSampleBusy(true); setSampleResult(null);
    try {
      const { data } = await axios.post(`${API}/launch/sample-data/load`, {}, { headers });
      setSampleResult({ kind: 'loaded', ...data.created });
    } catch { /* swallow */ }
    setSampleBusy(false);
  };
  const clearSample = async () => {
    if (!window.confirm('Remove all sample data? This only deletes items tagged sample_data_v1.')) return;
    setSampleBusy(true); setSampleResult(null);
    try {
      const { data } = await axios.post(`${API}/launch/sample-data/clear`, {}, { headers });
      setSampleResult({ kind: 'cleared', ...data.removed });
    } catch { /* swallow */ }
    setSampleBusy(false);
  };

  return (
    <div className="space-y-5" data-testid="launch-readiness-panel">
      {/* Email sender */}
      <section className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-5">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center text-blue-600">
            <Mail size={18} />
          </div>
          <div className="flex-1">
            <h3 className="text-base font-bold text-zinc-900 dark:text-zinc-100 pulse-font-heading">Email sender branding</h3>
            <p className="text-xs text-zinc-600 dark:text-zinc-400 mt-1">
              Your members see your studio name when emails arrive — invoices, booking confirmations and campaigns. Replies come back to you, not us.
            </p>
          </div>
        </div>

        <div className="mt-4 grid md:grid-cols-2 gap-3">
          <div>
            <label className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Friendly name shown to recipient</label>
            <input
              type="text" value={sender.friendly_name}
              onChange={(e) => setSender({ ...sender, friendly_name: e.target.value })}
              placeholder="e.g. National Dance Studio"
              className="mt-1 w-full h-9 rounded-md border border-zinc-200 dark:border-zinc-800 bg-transparent px-3 text-sm"
              data-testid="email-sender-friendly-name"
            />
          </div>
          <div>
            <label className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Reply-to email</label>
            <input
              type="email" value={sender.reply_to}
              onChange={(e) => setSender({ ...sender, reply_to: e.target.value })}
              placeholder="hello@yourstudio.com"
              className="mt-1 w-full h-9 rounded-md border border-zinc-200 dark:border-zinc-800 bg-transparent px-3 text-sm"
              data-testid="email-sender-reply-to"
            />
          </div>
        </div>

        <div className="mt-4 rounded-lg bg-zinc-50 dark:bg-zinc-800/40 px-3 py-2 text-xs flex items-center gap-2" data-testid="email-sender-preview">
          <Eye size={12} className="text-zinc-500" />
          <span className="text-zinc-500">Preview:</span>
          <code className="text-zinc-900 dark:text-zinc-100 font-mono text-[11px]">{sender.preview_from || '—'}</code>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <button type="button" onClick={saveSender} disabled={savingSender}
            className="rounded-md bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold px-4 py-2 inline-flex items-center gap-1.5 disabled:opacity-60"
            data-testid="email-sender-save">
            {savingSender ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} Save sender branding
          </button>
          {savedSender && <span className="text-xs text-emerald-600 inline-flex items-center gap-1" data-testid="email-sender-saved"><CheckCircle2 size={12} /> Saved</span>}
        </div>

        <div className="mt-4 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800/50 p-3 text-[11px] text-amber-900 dark:text-amber-200 flex items-start gap-2">
          <AlertTriangle size={14} className="text-amber-600 shrink-0 mt-0.5" />
          <div>
            <strong>Want emails to come from <code>@yourstudio.com</code> directly?</strong> That's the next tier — message us and we'll generate the 3 DNS records you need to verify your subdomain via Resend. Free.
          </div>
        </div>
      </section>

      {/* Sample data */}
      <section className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-5">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-lg bg-violet-100 dark:bg-violet-900/30 flex items-center justify-center text-violet-600">
            <Database size={18} />
          </div>
          <div className="flex-1">
            <h3 className="text-base font-bold text-zinc-900 dark:text-zinc-100 pulse-font-heading">Sample data</h3>
            <p className="text-xs text-zinc-600 dark:text-zinc-400 mt-1">
              Want to play with the platform before importing your real members? Load a small sample (5 members · 3 plans · 3 class templates) tagged so you can clear it in one click.
            </p>
          </div>
        </div>

        <div className="mt-4 flex items-center gap-3 flex-wrap">
          <button type="button" onClick={loadSample} disabled={sampleBusy}
            className="rounded-md bg-violet-600 hover:bg-violet-700 text-white text-xs font-bold px-4 py-2 inline-flex items-center gap-1.5 disabled:opacity-60"
            data-testid="sample-data-load">
            {sampleBusy ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />} Load sample data
          </button>
          <button type="button" onClick={clearSample} disabled={sampleBusy}
            className="rounded-md border border-zinc-200 dark:border-zinc-800 text-xs font-bold px-4 py-2 inline-flex items-center gap-1.5 text-zinc-700 dark:text-zinc-300 disabled:opacity-60"
            data-testid="sample-data-clear">
            <Trash2 size={12} /> Clear sample data
          </button>
          {sampleResult && (
            <span className="text-xs text-emerald-600 inline-flex items-center gap-1" data-testid="sample-data-result">
              <CheckCircle2 size={12} />
              {sampleResult.kind === 'loaded'
                ? `Loaded — ${sampleResult.members} members, ${sampleResult.plans} plans, ${sampleResult.class_templates} classes`
                : `Cleared — removed ${sampleResult.members} members, ${sampleResult.plans} plans, ${sampleResult.class_templates} classes`}
            </span>
          )}
        </div>
      </section>
    </div>
  );
}
