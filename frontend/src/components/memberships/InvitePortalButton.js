/**
 * Sprint B · G5 — Invite to portal button (iter 216ak).
 *
 * Compact icon button shown on each member row. Three states:
 *
 *   never-invited  → "Invite" (primary)
 *   invited         → "Resend" (neutral)
 *   claimed         → Green "Active" pill (click = Revoke menu)
 *
 * Sends POST /memberships/members/{id}/invite-portal. The backend
 * issues a magic-link token the member opens at /m/{slug}/claim?t=…
 * and POSTs to /member-auth/claim-invite to set a password.
 *
 * Clicks `stopPropagation` so the parent row's click-to-open-drawer
 * doesn't fire at the same time.
 */
import { useState } from 'react';
import axios from 'axios';
import { Mail, Check, Copy, RefreshCw, ShieldOff } from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const InvitePortalButton = ({ API, headers, member, onDone }) => {
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  const status = member.portal_claimed_at
    ? 'claimed'
    : member.portal_invited_at
    ? 'invited'
    : 'never';

  const stop = (e) => { e.stopPropagation(); e.preventDefault(); };

  const invite = async (ev) => {
    stop(ev);
    if (!member.email) { notify.error('Add an email first'); return; }
    setBusy(true);
    try {
      const r = await axios.post(
        `${API}/memberships/members/${member.id}/invite-portal`,
        {},
        { headers },
      );
      if (r.data?.email_sent) {
        notify.success('Invite sent', member.email);
      } else {
        notify.success('Invite ready', 'Email unconfigured — copy the link below');
        try { await navigator.clipboard.writeText(r.data.claim_url); } catch { /* */ }
      }
      onDone?.();
    } catch (e) {
      notifyApiError(notify, e, 'Failed to invite');
    }
    setBusy(false);
  };

  const revoke = async (ev) => {
    stop(ev);
    if (!window.confirm(`Revoke portal access for ${member.first_name}?`)) return;
    setBusy(true);
    try {
      await axios.post(`${API}/memberships/members/${member.id}/revoke-portal`, {}, { headers });
      notify.success('Portal access revoked');
      setOpen(false);
      onDone?.();
    } catch (e) {
      notifyApiError(notify, e, 'Failed to revoke');
    }
    setBusy(false);
  };

  const copyLink = async (ev) => {
    stop(ev);
    setBusy(true);
    try {
      const r = await axios.post(
        `${API}/memberships/members/${member.id}/invite-portal`,
        {},
        { headers },
      );
      await navigator.clipboard.writeText(r.data?.claim_url || '');
      notify.success('Invite link copied');
      setOpen(false);
      onDone?.();
    } catch (e) {
      notifyApiError(notify, e, 'Failed to generate link');
    }
    setBusy(false);
  };

  if (status === 'claimed') {
    return (
      <div className="relative inline-block" onClick={stop}>
        <button type="button" onClick={(e) => { stop(e); setOpen((v) => !v); }} disabled={busy}
          className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-extrabold bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25"
          data-testid={`mbr-invite-btn-${member.id}`}
          title="Portal active — click to manage">
          <Check size={10} /> Active
        </button>
        {open && (
          <div className="absolute right-0 top-full mt-1 z-10 rounded-lg border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] shadow-xl min-w-[140px] py-1">
            <button type="button" onClick={revoke} disabled={busy}
              className="w-full text-left px-3 py-1.5 text-[11px] font-bold text-red-300 hover:bg-red-500/10 inline-flex items-center gap-1.5"
              data-testid={`mbr-invite-revoke-${member.id}`}>
              <ShieldOff size={10} /> Revoke access
            </button>
          </div>
        )}
      </div>
    );
  }

  if (status === 'invited') {
    return (
      <div className="relative inline-block" onClick={stop}>
        <button type="button" onClick={invite} disabled={busy}
          className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-extrabold bg-amber-500/15 text-amber-400 hover:bg-amber-500/25"
          data-testid={`mbr-invite-btn-${member.id}`}
          title="Invite sent — click to resend">
          {busy ? <RefreshCw size={10} className="animate-spin" /> : <Mail size={10} />}
          Resend
        </button>
        <button type="button" onClick={copyLink} disabled={busy}
          className="ml-1 inline-flex items-center gap-0.5 px-1.5 py-1 rounded-full text-[10px] font-bold text-[color:var(--theme-text-muted)] hover:bg-white/5"
          title="Copy fresh invite link"
          data-testid={`mbr-invite-copy-${member.id}`}>
          <Copy size={9} />
        </button>
      </div>
    );
  }

  return (
    <button type="button" onClick={invite} disabled={busy}
      className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-extrabold text-[var(--color-surface-darker)]"
      style={{ background: 'var(--color-brand-cyan)' }}
      title="Send a portal invite"
      data-testid={`mbr-invite-btn-${member.id}`}>
      {busy ? <RefreshCw size={10} className="animate-spin" /> : <Mail size={10} />}
      Invite
    </button>
  );
};

export default InvitePortalButton;
