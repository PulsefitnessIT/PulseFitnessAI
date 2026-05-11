/**
 * Iter 216h20 — User detail drawer for the People Directory.
 *
 * Right-hand slide-in panel that opens when a directory row is
 * clicked. Surfaces the most-used actions a Master Admin needs
 * during staff onboarding this week:
 *
 *   1. Profile         — name, email, org, role, status, portals.
 *   2. Issue reset link — POST /master-admin/users/{id}/invite-link.
 *                         Copies the URL to clipboard. 72 h expiry.
 *   3. Open in legacy panel — falls back to the GlobalUsersPanel for
 *                             archive / purge / leaver flow.
 *
 * Drawer is INTENTIONALLY lean — full edit lives on the legacy panel
 * for one release. Once operators are happy with the drawer, the
 * legacy panel is retired (P3b).
 */
import React, { useState } from 'react';
import axios from 'axios';
import { X, Mail, Building, ShieldCheck, KeyRound, Copy, Check, AlertTriangle, ArrowUpRight } from 'lucide-react';
import { toast } from 'sonner';
import Button from '@/components/shared/Button';

const API_BASE = `${process.env.REACT_APP_BACKEND_URL}/api`;

const PortalPill = ({ portal }) => {
  const map = {
    service_portal: { bg: 'rgba(16,185,129,0.12)', fg: '#047857', label: 'Service Portal' },
    crm:            { bg: 'rgba(245,158,11,0.14)', fg: '#B45309', label: 'CRM' },
    pulse_platform: { bg: 'rgba(0,85,255,0.12)',   fg: '#0055FF', label: 'Pulse Platform' },
  };
  const tone = map[portal] || { bg: 'rgba(113,113,122,0.12)', fg: '#52525B', label: portal };
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold" style={{ background: tone.bg, color: tone.fg }}>
      {tone.label}
    </span>
  );
};

const Field = ({ label, value, icon: Icon, testId }) => (
  <div className="flex items-start gap-3" data-testid={testId}>
    {Icon && <Icon size={14} className="text-zinc-400 mt-0.5 flex-shrink-0" />}
    <div className="min-w-0 flex-1">
      <div className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">{label}</div>
      <div className="text-sm text-zinc-900 mt-0.5 break-words">{value || <span className="italic text-zinc-400">—</span>}</div>
    </div>
  </div>
);

const UserDetailDrawer = ({ user, onClose, onOpenLegacyEdit, onReload }) => {
  const [linkUrl, setLinkUrl] = useState('');
  const [linkBusy, setLinkBusy] = useState(false);
  const [linkExpiry, setLinkExpiry] = useState('');
  const [copied, setCopied] = useState(false);

  if (!user) return null;

  const token = (typeof window !== 'undefined') ? localStorage.getItem('token') : '';
  const headers = { Authorization: `Bearer ${token}` };

  const sendResetLink = async () => {
    setLinkBusy(true);
    try {
      const { data } = await axios.post(
        `${API_BASE}/master-admin/users/${user.id}/invite-link`,
        {}, { headers },
      );
      const url = data.invite_url || data.reset_url || '';
      setLinkUrl(url);
      setLinkExpiry(data.expires_at || '');
      try { if (url) await navigator.clipboard.writeText(url); } catch { /* ignore */ }
      toast.success('Reset link copied to clipboard · expires in 72 h');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not issue reset link');
    }
    setLinkBusy(false);
  };

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(linkUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* ignore */ }
  };

  const hasMismatch = user.invited_role && user.invited_role !== user.role;
  const portals = Array.isArray(user.portals) ? user.portals : [];

  return (
    <>
      {/* Backdrop */}
      <button
        type="button"
        onClick={onClose}
        className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm"
        aria-label="Close drawer"
        data-testid="people-drawer-backdrop"
      />
      {/* Drawer */}
      <aside
        role="dialog"
        aria-modal="true"
        className="fixed top-0 right-0 z-50 h-full w-full sm:w-[440px] bg-white shadow-2xl flex flex-col"
        style={{ borderLeft: '1px solid #E4E4E7' }}
        data-testid="people-drawer"
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3 p-5 border-b" style={{ borderColor: '#F4F4F5' }}>
          <div className="flex items-start gap-3 min-w-0">
            {user.avatar_url ? (
              <img src={user.avatar_url} alt="" className="w-12 h-12 rounded-full object-cover flex-shrink-0" />
            ) : (
              <div className="w-12 h-12 rounded-full flex-shrink-0 flex items-center justify-center text-lg font-bold" style={{ background: '#F4F4F5', color: '#52525B' }}>
                {(user.full_name || user.email || '?').slice(0, 1).toUpperCase()}
              </div>
            )}
            <div className="min-w-0">
              <h2 className="text-lg font-bold text-zinc-900 truncate" data-testid="people-drawer-name">{user.full_name || user.email}</h2>
              <p className="text-xs text-zinc-500 truncate">{user.email}</p>
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {portals.map((p) => <PortalPill key={p} portal={p} />)}
              </div>
            </div>
          </div>
          <button type="button" onClick={onClose} className="p-1.5 rounded hover:bg-zinc-100 transition-colors" data-testid="people-drawer-close">
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {hasMismatch && (
            <div className="rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-700 flex items-start gap-2" data-testid="people-drawer-mismatch">
              <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
              <div>
                <strong className="font-semibold">Role mismatch:</strong> invited as <code className="font-mono">{user.invited_role}</code>, currently <code className="font-mono">{user.role}</code>.
              </div>
            </div>
          )}

          <div className="space-y-3">
            <Field label="Email" value={user.email} icon={Mail} testId="people-drawer-email" />
            <Field label="Organisation" value={user.organization_name || (user.organization_id ? 'Linked' : 'Unaffiliated')} icon={Building} testId="people-drawer-org" />
            <Field label="Role" value={user.display_role || user.role || 'staff'} icon={ShieldCheck} testId="people-drawer-role" />
            {user.allowed_site_ids && user.allowed_site_ids.length > 0 && (
              <Field label="Pinned to sites" value={`${user.allowed_site_ids.length} site(s)`} testId="people-drawer-sites" />
            )}
            {user.password_reset_sent_at && (
              <Field
                label="Last reset link issued"
                value={`${new Date(user.password_reset_sent_at).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })}${user.password_reset_sent_by ? ` by ${user.password_reset_sent_by}` : ''}`}
                testId="people-drawer-last-reset"
              />
            )}
            {user.last_login && (
              <Field
                label="Last login"
                value={new Date(user.last_login).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                testId="people-drawer-last-login"
              />
            )}
          </div>

          <div className="rounded-lg border bg-zinc-50/60 p-4 space-y-3" style={{ borderColor: '#E4E4E7' }}>
            <div className="flex items-center gap-2">
              <KeyRound size={14} className="text-zinc-600" />
              <h3 className="text-sm font-bold text-zinc-900">Issue password reset link</h3>
            </div>
            <p className="text-[11px] text-zinc-600 leading-snug">
              Generates a one-time 72 h link the user can use to set their own password. Master Admin never sees the plaintext.
            </p>
            {!linkUrl ? (
              <Button
                variant="primary" size="md"
                className="w-full"
                onClick={sendResetLink}
                loading={linkBusy}
                disabled={linkBusy}
                data-testid="people-drawer-issue-reset-link"
              >
                {linkBusy ? 'Issuing...' : 'Issue & copy reset link'}
              </Button>
            ) : (
              <div className="rounded border border-emerald-200 bg-emerald-50 p-2.5 space-y-1.5" data-testid="people-drawer-reset-link-result">
                <code className="block font-mono text-[10px] break-all text-zinc-700">{linkUrl}</code>
                <div className="flex items-center justify-between gap-2">
                  {linkExpiry && (
                    <span className="text-[10px] text-zinc-500">
                      Expires {new Date(linkExpiry).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                    </span>
                  )}
                  <Button
                    variant="secondary" size="sm"
                    icon={copied ? Check : Copy}
                    onClick={copyLink}
                    data-testid="people-drawer-copy-reset-link"
                  >
                    {copied ? 'Copied' : 'Copy again'}
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer actions */}
        <div className="border-t p-4 flex items-center justify-between gap-2" style={{ borderColor: '#F4F4F5' }}>
          <Button
            variant="tertiary" size="md"
            onClick={onClose}
            data-testid="people-drawer-cancel"
          >
            Close
          </Button>
          {onOpenLegacyEdit && (
            <Button
              variant="secondary" size="md"
              iconRight={ArrowUpRight}
              onClick={() => { onOpenLegacyEdit(user); onClose(); if (onReload) onReload(); }}
              data-testid="people-drawer-open-legacy"
            >
              Full edit in legacy panel
            </Button>
          )}
        </div>
      </aside>
    </>
  );
};

export default UserDetailDrawer;
