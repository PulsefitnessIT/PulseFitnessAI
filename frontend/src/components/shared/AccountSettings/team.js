import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Check, Copy, Loader2, Plus, Trash2 } from 'lucide-react';
import { API, useAuthHeaders, FieldRow } from './shared';


export default function TeamSection({ profile, inviteCode }) {
  const headers = useAuthHeaders();
  const [members, setMembers] = useState([]);
  const [sitesList, setSitesList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [showInvite, setShowInvite] = useState(false);
  const [form, setForm] = useState({
    email: '', full_name: '', role: 'staff',
    delivery: 'reset_link',          // Iter 216h15 — default to email reset link
    allowed_site_ids: [],
  });
  const [tempPwd, setTempPwd] = useState('');
  const [inviteUrl, setInviteUrl] = useState('');
  const [urlCopied, setUrlCopied] = useState(false);
  const [codeCopied, setCodeCopied] = useState(false);
  const [editingSitesFor, setEditingSitesFor] = useState(null);  // user id whose site picker is open
  const [pendingSites, setPendingSites] = useState([]);

  const isOwner = (profile?.role || '').toLowerCase() === 'owner';
  const isManager = (profile?.role || '').toLowerCase() === 'manager';
  const canManage = isOwner || isManager;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [teamRes, sitesRes] = await Promise.all([
        axios.get(`${API}/account/team`, { headers: headers() }),
        axios.get(`${API}/sites`, { headers: headers() }).catch(() => ({ data: { sites: [] } })),
      ]);
      setMembers(teamRes.data.members || []);
      setSitesList(sitesRes.data.sites || []);
    } catch {
      setMembers([]); setSitesList([]);
    }
    setLoading(false);
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const invite = async () => {
    setBusy(true);
    setTempPwd(''); setInviteUrl('');
    try {
      const { data } = await axios.post(`${API}/account/team/invite`, form, { headers: headers() });
      if (data.delivery === 'reset_link') {
        setInviteUrl(data.invite_url || '');
        toast.success('Reset link issued — copy it or it will also be emailed when Resend is wired.');
      } else {
        setTempPwd(data.temp_password || '');
        toast.success('Invite created');
      }
      setForm({ email: '', full_name: '', role: 'staff', delivery: 'reset_link', allowed_site_ids: [] });
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Invite failed');
    }
    setBusy(false);
  };

  const updateRole = async (id, role) => {
    try {
      await axios.patch(`${API}/account/team/${id}`, { role }, { headers: headers() });
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Update failed');
    }
  };

  const remove = async (id) => {
    if (!window.confirm('Remove this teammate? They will lose access immediately.')) return;
    try {
      await axios.delete(`${API}/account/team/${id}`, { headers: headers() });
      await load();
      toast.success('Teammate removed');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Remove failed');
    }
  };

  /** Iter 216h15 — open per-user sites multi-select. */
  const openSitesEditor = (member) => {
    setEditingSitesFor(member.id);
    setPendingSites(Array.isArray(member.allowed_site_ids) ? [...member.allowed_site_ids] : []);
  };

  const togglePendingSite = (siteId) => {
    setPendingSites((prev) => (
      prev.includes(siteId) ? prev.filter((s) => s !== siteId) : [...prev, siteId]
    ));
  };

  const saveSiteAccess = async (memberId) => {
    try {
      await axios.patch(
        `${API}/account/team/${memberId}/site-access`,
        { allowed_site_ids: pendingSites },
        { headers: headers() },
      );
      toast.success(pendingSites.length === 0 ? 'Site access cleared (full access)' : `Pinned to ${pendingSites.length} site(s)`);
      setEditingSitesFor(null);
      setPendingSites([]);
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Site allocation failed');
    }
  };

  /** Iter 216h15 — send a fresh reset link to an existing teammate. */
  const sendResetLink = async (member) => {
    if (!window.confirm(`Send a password reset link to ${member.email}? This invalidates any previous reset link for this user.`)) return;
    try {
      const { data } = await axios.post(
        `${API}/account/team/${member.id}/send-reset-link`, {}, { headers: headers() },
      );
      if (data.invite_url) {
        try { await navigator.clipboard.writeText(data.invite_url); } catch { /* ignore */ }
        toast.success('Reset link copied to clipboard (expires in 72 h).');
      } else {
        toast.success('Reset link issued.');
      }
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not send reset link');
    }
  };

  return (
    <div className="space-y-4" data-testid="account-section-team">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="account-section-title">Team & roles</h3>
          <p className="account-section-sub">{members.length} teammate{members.length === 1 ? '' : 's'} in this organisation.</p>
        </div>
        {canManage && (
          <button
            type="button"
            onClick={() => { setShowInvite((v) => !v); setTempPwd(''); }}
            className="account-btn-primary"
            data-testid="account-team-invite-toggle"
          >
            <Plus size={14} /> Invite
          </button>
        )}
      </div>

      {showInvite && canManage && (
        <div
          className="rounded-xl p-5 space-y-3"
          style={{
            border: '1px solid color-mix(in srgb, var(--brand-color, #0055FF) 25%, transparent)',
            background: 'color-mix(in srgb, var(--brand-color, #0055FF) 5%, transparent)',
          }}
          data-testid="account-team-invite-form"
        >
          {inviteCode && (
            <div className="rounded-md p-3" style={{ background: 'var(--theme-bg)', border: '1px solid var(--theme-border)' }}>
              <div className="text-[10px] uppercase tracking-wider font-semibold mb-1" style={{ color: 'var(--theme-text-muted)' }}>Self-join invite code</div>
              <div className="flex items-center gap-2">
                <code className="text-base font-mono" style={{ color: 'var(--brand-color, var(--color-brand-blue))' }} data-testid="account-team-invite-code">{inviteCode}</code>
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(inviteCode);
                    setCodeCopied(true);
                    setTimeout(() => setCodeCopied(false), 1500);
                  }}
                  className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border"
                  style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}
                  data-testid="account-team-invite-code-copy"
                >
                  {codeCopied ? <Check size={12} /> : <Copy size={12} />} {codeCopied ? 'Copied' : 'Copy'}
                </button>
              </div>
              <p className="text-[11px] mt-1" style={{ color: 'var(--theme-text-muted)' }}>
                Share this code so a new teammate can self-join your organisation, or fill in the form below to send a direct invite.
              </p>
            </div>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <FieldRow label="Full name">
              <input
                type="text"
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                className="account-input"
                data-testid="account-team-invite-name"
              />
            </FieldRow>
            <FieldRow label="Email">
              <input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="account-input"
                data-testid="account-team-invite-email"
              />
            </FieldRow>
            <FieldRow label="Role">
              <select
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
                className="account-input"
                data-testid="account-team-invite-role"
              >
                <option value="staff">Staff</option>
                {isOwner && <option value="manager">Manager</option>}
                {isOwner && <option value="engineer">Engineer</option>}
              </select>
            </FieldRow>
            <FieldRow label="Delivery">
              <select
                value={form.delivery}
                onChange={(e) => setForm({ ...form, delivery: e.target.value })}
                className="account-input"
                data-testid="account-team-invite-delivery"
              >
                <option value="reset_link">Email password reset link (recommended)</option>
                <option value="temp_password">Show temporary password inline</option>
              </select>
            </FieldRow>
          </div>
          {/* Iter 216h15 — owner can pin the new teammate to specific
              sites at invite time. Empty = full access. Head Office +
              all other org sites are listed. */}
          {sitesList.length >= 2 && (
            <div className="rounded-md p-3 mt-2" style={{ background: 'var(--theme-bg)', border: '1px solid var(--theme-border)' }} data-testid="account-team-invite-sites">
              <div className="text-[11px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'var(--theme-text-muted)' }}>
                Pin to sites (optional)
              </div>
              <div className="flex flex-wrap gap-1.5">
                {sitesList.map((s) => {
                  const checked = form.allowed_site_ids.includes(s.id);
                  return (
                    <button
                      type="button"
                      key={s.id}
                      onClick={() => setForm((f) => ({
                        ...f,
                        allowed_site_ids: checked
                          ? f.allowed_site_ids.filter((x) => x !== s.id)
                          : [...f.allowed_site_ids, s.id],
                      }))}
                      className="text-xs px-2.5 py-1 rounded-full border transition-colors"
                      style={{
                        borderColor: checked ? 'var(--brand-color, var(--color-brand-blue))' : 'var(--theme-border)',
                        background: checked ? 'color-mix(in srgb, var(--brand-color, #0055FF) 12%, transparent)' : 'transparent',
                        color: checked ? 'var(--brand-color, var(--color-brand-blue))' : 'var(--theme-text)',
                        fontWeight: checked ? 600 : 400,
                      }}
                      data-testid={`account-team-invite-site-${s.id}`}
                    >
                      {s.is_head_office ? '★ ' : ''}{s.name}{checked ? ' ✓' : ''}
                    </button>
                  );
                })}
              </div>
              <p className="text-[10px] mt-2" style={{ color: 'var(--theme-text-muted)' }}>
                Leave empty for full org-wide access. Selecting sites locks the teammate to those sites only.
              </p>
            </div>
          )}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setShowInvite(false)} className="account-btn-secondary">Cancel</button>
            <button
              type="button"
              onClick={invite}
              disabled={busy || !form.email || !form.full_name}
              className="account-btn-primary"
              data-testid="account-team-invite-submit"
            >
              {busy ? <Loader2 size={14} className="animate-spin" /> : null}
              Send invite
            </button>
          </div>
          {tempPwd && (
            <div className="rounded border border-amber-400/40 bg-amber-400/10 p-3 text-xs" style={{ color: 'var(--theme-text)' }} data-testid="account-team-invite-temp-pwd">
              Temporary password: <code className="font-mono">{tempPwd}</code> — share this with the new teammate.
            </div>
          )}
          {inviteUrl && (
            <div className="rounded border border-emerald-400/40 bg-emerald-400/10 p-3 text-xs space-y-1.5" style={{ color: 'var(--theme-text)' }} data-testid="account-team-invite-url">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-semibold mb-0.5">Password reset link issued · expires in 72 h</div>
                  <code className="font-mono text-[10px] break-all" style={{ color: 'var(--theme-text-muted)' }}>{inviteUrl}</code>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(inviteUrl);
                    setUrlCopied(true);
                    setTimeout(() => setUrlCopied(false), 1500);
                  }}
                  className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border flex-shrink-0"
                  style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}
                  data-testid="account-team-invite-url-copy"
                >
                  {urlCopied ? <Check size={12} /> : <Copy size={12} />} {urlCopied ? 'Copied' : 'Copy'}
                </button>
              </div>
              <p style={{ color: 'var(--theme-text-muted)' }}>
                Share this with the new teammate. They&apos;ll set their own password — you never see it.
              </p>
            </div>
          )}
        </div>
      )}

      <div className="account-card rounded-xl divide-y" style={{ borderColor: 'var(--theme-border)' }}>
        {loading && <div className="px-4 py-6 text-sm text-center" style={{ color: 'var(--theme-text-muted)' }}>Loading…</div>}
        {!loading && members.map((m) => {
          const me = m.id === profile?.id;
          const editable = canManage && !me && m.role !== 'owner';
          const pinnedSites = Array.isArray(m.allowed_site_ids) ? m.allowed_site_ids : [];
          const siteNamesById = Object.fromEntries(sitesList.map((s) => [s.id, s.name]));
          const pinnedNames = pinnedSites.map((id) => siteNamesById[id]).filter(Boolean);
          const editingSites = editingSitesFor === m.id;
          return (
            <div key={m.id} className="px-4 py-3 flex flex-col gap-2" data-testid={`account-team-member-${m.id}`}>
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                  {m.avatar_url ? (
                    <img src={m.avatar_url} alt="" className="w-8 h-8 rounded-full object-cover" />
                  ) : (
                    <div className="account-avatar-placeholder w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold">
                      {(m.full_name || m.email || '?').slice(0, 1).toUpperCase()}
                    </div>
                  )}
                  <div className="min-w-0">
                    <div className="text-sm font-medium truncate" style={{ color: 'var(--theme-text)' }}>{m.full_name || '—'} {me && <span className="text-[10px] font-normal ml-1" style={{ color: 'var(--theme-text-muted)' }}>(you)</span>}</div>
                    <div className="text-[11px] truncate" style={{ color: 'var(--theme-text-muted)' }}>{m.email}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {editable ? (
                    <select
                      value={m.role}
                      onChange={(e) => updateRole(m.id, e.target.value)}
                      className="account-input account-input-sm"
                      data-testid={`account-team-role-${m.id}`}
                    >
                      <option value="staff">Staff</option>
                      {isOwner && <option value="manager">Manager</option>}
                      {(isOwner || m.role === 'engineer') && <option value="engineer">Engineer</option>}
                    </select>
                  ) : (
                    <span className="text-[11px] uppercase tracking-wider px-2 py-1 rounded border capitalize" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>{m.role}</span>
                  )}
                  {/* Iter 216h15 — Send reset link to this teammate */}
                  {editable && (
                    <button
                      type="button"
                      onClick={() => sendResetLink(m)}
                      className="text-[11px] px-2 py-1 rounded border hover:bg-[var(--theme-hover-bg)] transition-colors"
                      style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                      title="Issue a 72 h password reset link"
                      data-testid={`account-team-reset-${m.id}`}
                    >
                      Send reset link
                    </button>
                  )}
                  {editable && (
                    <button
                      type="button"
                      onClick={() => remove(m.id)}
                      className="hover:text-red-400 transition"
                      style={{ color: 'var(--theme-text-muted)' }}
                      title="Remove teammate"
                      data-testid={`account-team-remove-${m.id}`}
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              </div>
              {/* Iter 216h15 — Site allocation row */}
              {canManage && m.role !== 'owner' && sitesList.length >= 1 && (
                <div className="pl-11">
                  {!editingSites ? (
                    <div className="flex items-center gap-2 text-[11px]" style={{ color: 'var(--theme-text-muted)' }} data-testid={`account-team-sites-summary-${m.id}`}>
                      <span className="font-semibold uppercase tracking-wider">Sites:</span>
                      <span>
                        {pinnedNames.length === 0
                          ? <em>All sites in org</em>
                          : pinnedNames.join(' · ')}
                      </span>
                      <button
                        type="button"
                        onClick={() => openSitesEditor(m)}
                        className="ml-auto text-[10px] underline hover:text-[var(--brand-color)]"
                        data-testid={`account-team-sites-edit-${m.id}`}
                      >
                        Edit sites
                      </button>
                    </div>
                  ) : (
                    <div className="rounded-md p-3" style={{ background: 'var(--theme-bg)', border: '1px solid var(--theme-border)' }} data-testid={`account-team-sites-editor-${m.id}`}>
                      <div className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'var(--theme-text-muted)' }}>
                        Pin {m.full_name || m.email} to sites
                      </div>
                      <div className="flex flex-wrap gap-1.5 mb-2">
                        {sitesList.map((s) => {
                          const checked = pendingSites.includes(s.id);
                          return (
                            <button
                              type="button"
                              key={s.id}
                              onClick={() => togglePendingSite(s.id)}
                              className="text-xs px-2.5 py-1 rounded-full border transition-colors"
                              style={{
                                borderColor: checked ? 'var(--brand-color, var(--color-brand-blue))' : 'var(--theme-border)',
                                background: checked ? 'color-mix(in srgb, var(--brand-color, #0055FF) 12%, transparent)' : 'transparent',
                                color: checked ? 'var(--brand-color, var(--color-brand-blue))' : 'var(--theme-text)',
                                fontWeight: checked ? 600 : 400,
                              }}
                              data-testid={`account-team-sites-pick-${m.id}-${s.id}`}
                            >
                              {s.is_head_office ? '★ ' : ''}{s.name}{checked ? ' ✓' : ''}
                            </button>
                          );
                        })}
                      </div>
                      <div className="flex justify-end gap-2">
                        <button type="button" onClick={() => { setEditingSitesFor(null); setPendingSites([]); }} className="text-xs px-2.5 py-1 rounded border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>Cancel</button>
                        <button
                          type="button"
                          onClick={() => saveSiteAccess(m.id)}
                          className="text-xs px-2.5 py-1 rounded font-semibold"
                          style={{ background: 'var(--brand-color, var(--color-brand-blue))', color: 'white' }}
                          data-testid={`account-team-sites-save-${m.id}`}
                        >
                          Save site access
                        </button>
                      </div>
                    </div>
                  )}
                  {/* Iter 216h15 — audit trail of the last reset link */}
                  {m.password_reset_sent_at && (
                    <div className="text-[10px] mt-1" style={{ color: 'var(--theme-text-muted)' }} data-testid={`account-team-reset-audit-${m.id}`}>
                      Last reset link sent {new Date(m.password_reset_sent_at).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                      {m.password_reset_sent_by ? ` by ${m.password_reset_sent_by}` : ''}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
        {!loading && members.length === 0 && (
          <div className="px-4 py-6 text-sm text-center" style={{ color: 'var(--theme-text-muted)' }}>No teammates yet.</div>
        )}
      </div>
    </div>
  );
}

