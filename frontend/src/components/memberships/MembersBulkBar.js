/**
 * Sprint C — Bulk Actions Bar.
 *
 * Docked bar that appears above the member table whenever the operator
 * has selected one or more rows. Offers:
 *   • Invite to portal — fires magic-link emails to the selection
 *   • Send reminder    — compose a short email (subject + message)
 *                        sent to every selected member with an email
 *   • Add tag          — bulk-tag for future filtering / saved views
 *
 * Each action fans out via POST /memberships/members/bulk-action, which
 * returns per-member ok/error so we can show a "Invited 18 of 20, 2
 * skipped" toast. Clears the selection on success.
 */
import { useState } from 'react';
import axios from 'axios';
import { Mail, MessageSquare, Tag as TagIcon, X, Loader2, CheckCircle2 } from 'lucide-react';
import { notify } from '@/components/notifications';

const ACTIONS = [
  { id: 'invite_portal', label: 'Invite to portal', icon: Mail },
  { id: 'send_reminder', label: 'Send reminder',   icon: MessageSquare },
  { id: 'add_tag',       label: 'Add tag',         icon: TagIcon },
];

export default function MembersBulkBar({ API, headers, selectedIds, onClearSelection, onRefresh }) {
  const [open, setOpen] = useState(null); // 'invite_portal' | 'send_reminder' | 'add_tag' | null
  const [busy, setBusy] = useState(false);
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [tag, setTag] = useState('');

  const count = selectedIds.length;
  if (count === 0) return null;

  const run = async (action, payload = {}) => {
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/memberships/members/bulk-action`, {
        action,
        member_ids: selectedIds,
        payload,
      }, { headers });
      const ok = data.succeeded || 0;
      const fail = data.failed || 0;
      if (fail === 0) {
        notify.success(`${ok} member${ok === 1 ? '' : 's'} processed`, 'All done.');
      } else {
        // Surface the first few error reasons so operators can fix bad data.
        const sample = (data.results || [])
          .filter((r) => !r.ok).slice(0, 3)
          .map((r) => r.error).filter(Boolean).join(' · ');
        notify.warning(`${ok} succeeded, ${fail} failed`, sample || 'Open a row to see details.');
      }
      setOpen(null);
      setSubject(''); setMessage(''); setTag('');
      onClearSelection();
      onRefresh && onRefresh();
    } catch (e) {
      notify.error('Bulk action failed', e.response?.data?.detail || 'Try again.');
    } finally {
      setBusy(false);
    }
  };

  const submit = () => {
    if (open === 'invite_portal') {
      run('invite_portal');
    } else if (open === 'send_reminder') {
      if (!subject.trim() || !message.trim()) {
        notify.error('Subject + message required');
        return;
      }
      run('send_reminder', { subject: subject.trim(), message: message.trim() });
    } else if (open === 'add_tag') {
      if (!tag.trim()) { notify.error('Enter a tag'); return; }
      run('add_tag', { tag: tag.trim() });
    }
  };

  return (
    <div
      className="sticky top-0 z-20 mt-4 rounded-xl border border-[color:var(--color-brand-cyan)]/40 bg-[color:var(--color-brand-cyan)]/10 backdrop-blur px-4 py-3"
      data-testid="mbr-bulk-bar"
    >
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-sm">
          <CheckCircle2 size={15} className="text-[color:var(--color-brand-cyan)]" />
          <span className="font-bold text-[color:var(--theme-text)]">
            {count} selected
          </span>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {ACTIONS.map((a) => {
            const Icon = a.icon;
            return (
              <button
                key={a.id}
                type="button"
                onClick={() => setOpen(a.id)}
                className="h-8 inline-flex items-center gap-1.5 rounded-full bg-[color:var(--theme-surface)] border border-[color:var(--theme-border)] px-3 text-xs font-bold hover:border-[color:var(--color-brand-cyan)]/60 transition-colors"
                data-testid={`mbr-bulk-${a.id}`}
              >
                <Icon size={12} /> {a.label}
              </button>
            );
          })}
          <button
            type="button"
            onClick={onClearSelection}
            className="h-8 px-3 rounded-full text-xs font-bold text-[color:var(--theme-text-muted)] hover:text-[color:var(--theme-text)] inline-flex items-center gap-1"
            data-testid="mbr-bulk-clear"
          >
            <X size={12} /> Clear
          </button>
        </div>
      </div>

      {open === 'invite_portal' && (
        <div className="mt-3 border-t border-[color:var(--color-brand-cyan)]/30 pt-3" data-testid="mbr-bulk-invite-form">
          <p className="text-xs text-[color:var(--theme-text-muted)] mb-2">
            Each selected member with an email will get a magic-link invite. Already-invited members will
            receive a fresh link (old tokens die). This action is safe to repeat.
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={submit}
              className="h-8 rounded-full bg-[color:var(--color-brand-cyan)] text-white text-xs font-bold px-4 disabled:opacity-60 inline-flex items-center gap-1.5"
              data-testid="mbr-bulk-invite-confirm"
            >
              {busy ? <Loader2 size={12} className="animate-spin" /> : <Mail size={12} />}
              {busy ? 'Inviting…' : `Invite ${count} member${count === 1 ? '' : 's'}`}
            </button>
            <button
              type="button"
              onClick={() => setOpen(null)}
              className="h-8 rounded-full border border-[color:var(--theme-border)] text-xs font-bold px-4 text-[color:var(--theme-text-muted)]"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {open === 'send_reminder' && (
        <div className="mt-3 border-t border-[color:var(--color-brand-cyan)]/30 pt-3 space-y-2" data-testid="mbr-bulk-reminder-form">
          <input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            maxLength={120}
            placeholder="Email subject"
            className="w-full h-9 rounded-md bg-[color:var(--theme-surface)] border border-[color:var(--theme-border)] px-3 text-sm"
            data-testid="mbr-bulk-reminder-subject"
          />
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            maxLength={2000}
            rows={4}
            placeholder="Your message (will be addressed to each member by first name automatically)"
            className="w-full rounded-md bg-[color:var(--theme-surface)] border border-[color:var(--theme-border)] px-3 py-2 text-sm"
            data-testid="mbr-bulk-reminder-message"
          />
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={submit}
              className="h-8 rounded-full bg-[color:var(--color-brand-cyan)] text-white text-xs font-bold px-4 disabled:opacity-60 inline-flex items-center gap-1.5"
              data-testid="mbr-bulk-reminder-confirm"
            >
              {busy ? <Loader2 size={12} className="animate-spin" /> : <MessageSquare size={12} />}
              {busy ? 'Sending…' : `Send to ${count} member${count === 1 ? '' : 's'}`}
            </button>
            <button
              type="button"
              onClick={() => setOpen(null)}
              className="h-8 rounded-full border border-[color:var(--theme-border)] text-xs font-bold px-4 text-[color:var(--theme-text-muted)]"
            >
              Cancel
            </button>
          </div>
          <p className="text-[10px] text-[color:var(--theme-text-muted)]">
            Members without an email on file are skipped.
          </p>
        </div>
      )}

      {open === 'add_tag' && (
        <div className="mt-3 border-t border-[color:var(--color-brand-cyan)]/30 pt-3 space-y-2" data-testid="mbr-bulk-tag-form">
          <input
            value={tag}
            onChange={(e) => setTag(e.target.value)}
            maxLength={40}
            placeholder="e.g. vip, renewal_due, lapsed"
            className="w-full h-9 rounded-md bg-[color:var(--theme-surface)] border border-[color:var(--theme-border)] px-3 text-sm"
            data-testid="mbr-bulk-tag-input"
          />
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={submit}
              className="h-8 rounded-full bg-[color:var(--color-brand-cyan)] text-white text-xs font-bold px-4 disabled:opacity-60 inline-flex items-center gap-1.5"
              data-testid="mbr-bulk-tag-confirm"
            >
              {busy ? <Loader2 size={12} className="animate-spin" /> : <TagIcon size={12} />}
              {busy ? 'Tagging…' : `Tag ${count} member${count === 1 ? '' : 's'}`}
            </button>
            <button
              type="button"
              onClick={() => setOpen(null)}
              className="h-8 rounded-full border border-[color:var(--theme-border)] text-xs font-bold px-4 text-[color:var(--theme-text-muted)]"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
