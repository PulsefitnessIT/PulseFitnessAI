/**
 * AccountSettingsModal — Emergent-style fixed-size settings popover for
 * Owner / Manager / Staff. Master Admins use the dedicated /master-admin
 * console and skip this modal entirely.
 *
 * Six sections in a left rail:
 *   Profile · Security · Preferences · Plan & Billing · Organisation · Team & Roles
 *
 * Forced dark theme — never inherits the in-app light/dark toggle.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import {
  X, User, ShieldCheck, Sliders, CreditCard, Building2, Users,
  Camera, Trash2, Loader2, Check, Copy, Plus, ArrowUpRight,
} from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/App';
import MFASetupCard from './MFASetupCard';
import DigestPreferencesCard from './DigestPreferencesCard';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const SECTIONS = [
  { id: 'profile', label: 'Profile', icon: User },
  { id: 'security', label: 'Security', icon: ShieldCheck },
  { id: 'preferences', label: 'Preferences', icon: Sliders },
  { id: 'billing', label: 'Plan & Billing', icon: CreditCard },
  { id: 'organisation', label: 'Organisation', icon: Building2 },
  { id: 'team', label: 'Team & Roles', icon: Users },
];

const useAuthHeaders = () =>
  useCallback(() => ({ Authorization: `Bearer ${localStorage.getItem('token')}` }), []);

// ─── Profile ──────────────────────────────────────────────────────
function ProfileSection({ profile, onProfileUpdate }) {
  const headers = useAuthHeaders();
  const [fullName, setFullName] = useState(profile?.full_name || '');
  const [phone, setPhone] = useState(profile?.phone || '');
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  useEffect(() => {
    setFullName(profile?.full_name || '');
    setPhone(profile?.phone || '');
  }, [profile?.full_name, profile?.phone]);

  const initials = (fullName || profile?.email || '?').slice(0, 1).toUpperCase();

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await axios.patch(`${API}/account/profile`,
        { full_name: fullName, phone }, { headers: headers() });
      onProfileUpdate(data);
      toast.success('Profile updated');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not update profile');
    }
    setSaving(false);
  };

  const onFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', f);
      const { data } = await axios.post(`${API}/account/avatar`, fd, {
        headers: { ...headers(), 'Content-Type': 'multipart/form-data' },
      });
      onProfileUpdate({ ...profile, avatar_url: data.avatar_url });
      toast.success('Avatar updated');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload failed');
    }
    setUploading(false);
    if (fileRef.current) fileRef.current.value = '';
  };

  const removeAvatar = async () => {
    setUploading(true);
    try {
      await axios.delete(`${API}/account/avatar`, { headers: headers() });
      onProfileUpdate({ ...profile, avatar_url: null });
      toast.success('Avatar removed');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Remove failed');
    }
    setUploading(false);
  };

  return (
    <div className="space-y-6" data-testid="account-section-profile">
      <div className="flex items-center gap-5">
        <div className="relative">
          {profile?.avatar_url ? (
            <img
              src={profile.avatar_url}
              alt="avatar"
              className="w-20 h-20 rounded-full object-cover"
              style={{ border: '1px solid var(--theme-border)' }}
              data-testid="account-avatar-img"
            />
          ) : (
            <div className="account-avatar-placeholder w-20 h-20 rounded-full flex items-center justify-center text-2xl font-bold">
              {initials}
            </div>
          )}
          {uploading && (
            <div className="absolute inset-0 rounded-full bg-black/60 flex items-center justify-center">
              <Loader2 size={20} className="animate-spin text-white" />
            </div>
          )}
        </div>
        <div className="flex flex-col gap-2">
          <input ref={fileRef} type="file" accept="image/*"
            onChange={onFile} className="hidden" data-testid="account-avatar-input" />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider px-3 py-1.5 border rounded-md transition disabled:opacity-50"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
            data-testid="account-avatar-upload-btn"
          >
            <Camera size={13} /> Upload photo
          </button>
          {profile?.avatar_url && (
            <button
              type="button"
              onClick={removeAvatar}
              disabled={uploading}
              className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider px-3 py-1.5 hover:text-red-400 transition disabled:opacity-50"
              style={{ color: 'var(--theme-text-muted)' }}
              data-testid="account-avatar-remove-btn"
            >
              <Trash2 size={13} /> Remove
            </button>
          )}
          <p className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>
            JPG / PNG. Auto-cropped to a 256×256 thumbnail.
          </p>
        </div>
      </div>

      <FieldRow label="Full name">
        <input
          type="text"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          className="account-input"
          data-testid="account-full-name-input"
        />
      </FieldRow>
      <FieldRow label="Email">
        <input
          type="email"
          value={profile?.email || ''}
          readOnly
          disabled
          className="account-input opacity-60 cursor-not-allowed"
          data-testid="account-email-input"
        />
        <p className="text-[10px] mt-1" style={{ color: 'var(--theme-text-muted)' }}>
          Contact your team admin or support to change this.
        </p>
      </FieldRow>
      <FieldRow label="Phone">
        <input
          type="tel"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="+44 7700 900123"
          className="account-input"
          data-testid="account-phone-input"
        />
      </FieldRow>

      <div className="flex justify-end">
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="account-btn-primary"
          data-testid="account-profile-save-btn"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : null}
          Save changes
        </button>
      </div>
    </div>
  );
}

// ─── Security ─────────────────────────────────────────────────────
function SecuritySection() {
  const headers = useAuthHeaders();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (next !== confirm) {
      toast.error('New passwords do not match');
      return;
    }
    setBusy(true);
    try {
      await axios.post(`${API}/account/change-password`,
        { current_password: current, new_password: next },
        { headers: headers() });
      toast.success('Password updated');
      setCurrent(''); setNext(''); setConfirm('');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not change password');
    }
    setBusy(false);
  };

  return (
    <div className="space-y-8" data-testid="account-section-security">
      <div>
        <h3 className="account-section-title">Two-factor authentication</h3>
        <p className="account-section-sub">Protect your account with a 6-digit code on every sign-in.</p>
        <div className="mt-3">
          <MFASetupCard />
        </div>
      </div>

      <div>
        <h3 className="account-section-title">Reset password</h3>
        <p className="account-section-sub">Change your password without leaving the app.</p>
        <div className="mt-3 space-y-3">
          <FieldRow label="Current password">
            <input
              type="password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              className="account-input"
              data-testid="account-current-password-input"
            />
          </FieldRow>
          <FieldRow label="New password">
            <input
              type="password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              className="account-input"
              data-testid="account-new-password-input"
            />
            <p className="text-[10px] mt-1" style={{ color: 'var(--theme-text-muted)' }}>
              At least 8 characters. Use a mix of letters, numbers, and symbols.
            </p>
          </FieldRow>
          <FieldRow label="Confirm new password">
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="account-input"
              data-testid="account-confirm-password-input"
            />
          </FieldRow>
          <div className="flex justify-end">
            <button
              type="button"
              onClick={submit}
              disabled={busy || !current || next.length < 8}
              className="account-btn-primary"
              data-testid="account-password-save-btn"
            >
              {busy ? <Loader2 size={14} className="animate-spin" /> : null}
              Update password
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Preferences ──────────────────────────────────────────────────
function PreferencesSection() {
  const { theme, toggleTheme } = useAuth();
  return (
    <div className="space-y-6" data-testid="account-section-preferences">
      <div>
        <h3 className="account-section-title">App theme</h3>
        <p className="account-section-sub">
          Currently <span className="font-semibold" style={{ color: 'var(--theme-text)' }}>{theme === 'dark' ? 'Dark' : 'Light'}</span>. Affects in-app surfaces only — toggle to switch the whole experience including this panel.
        </p>
        <button
          type="button"
          onClick={toggleTheme}
          className="account-btn-secondary mt-3"
          data-testid="account-theme-toggle"
        >
          Switch to {theme === 'dark' ? 'Light' : 'Dark'}
        </button>
      </div>
      <div>
        <h3 className="account-section-title">Email digest</h3>
        <p className="account-section-sub">Choose which weekly and daily roll-ups land in your inbox.</p>
        <div className="mt-3">
          <DigestPreferencesCard />
        </div>
      </div>
    </div>
  );
}

// ─── Plan & Billing ───────────────────────────────────────────────
function BillingSection({ billing, onClose }) {
  if (!billing) {
    return <div className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>Loading billing…</div>;
  }
  return (
    <div className="space-y-6" data-testid="account-section-billing">
      <div className="account-card rounded-xl p-5">
        <div className="text-[10px] uppercase tracking-wider font-semibold mb-2" style={{ color: 'var(--theme-text-muted)' }}>Current plan</div>
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xl font-extrabold" style={{ color: 'var(--theme-text)' }}>{billing.plan_name}</div>
            <div className="text-sm mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
              {billing.plan_price > 0 ? `£${billing.plan_price}/month` : 'No active subscription'}
            </div>
          </div>
          <Link to="/pricing" onClick={onClose}>
            <button type="button" className="account-btn-primary" data-testid="account-billing-upgrade-btn">
              {billing.current_plan === 'none' ? 'Subscribe' : 'Change plan'}
              <ArrowUpRight size={14} />
            </button>
          </Link>
        </div>
      </div>

      <div>
        <h3 className="account-section-title">Payment history</h3>
        <p className="account-section-sub">Last 50 transactions on this account.</p>
        <div className="mt-3 account-card rounded-xl divide-y max-h-72 overflow-y-auto" style={{ borderColor: 'var(--theme-border)' }}>
          {(billing.payment_history || []).length === 0 && (
            <div className="px-4 py-6 text-sm text-center" style={{ color: 'var(--theme-text-muted)' }}>No payments yet.</div>
          )}
          {(billing.payment_history || []).map((p, idx) => (
            <div key={idx} className="px-4 py-3 flex items-center justify-between text-sm" data-testid={`account-payment-${idx}`}>
              <div>
                <div className="font-medium" style={{ color: 'var(--theme-text)' }}>{p.package_id ? p.package_id.charAt(0).toUpperCase() + p.package_id.slice(1) : 'Charge'}</div>
                <div className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>{p.created_at ? new Date(p.created_at).toLocaleDateString() : ''}</div>
              </div>
              <div className="text-right">
                <div className="font-semibold" style={{ color: 'var(--theme-text)' }}>£{Number(p.amount || 0).toFixed(2)}</div>
                <div className={`text-[11px] uppercase tracking-wider font-bold ${p.payment_status === 'paid' ? 'text-emerald-500' : 'text-amber-500'}`}>
                  {p.payment_status || 'pending'}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Organisation ────────────────────────────────────────────────
function OrganisationSection({ billing, profile }) {
  const [copied, setCopied] = useState(false);
  if (!billing?.organization) {
    return <div className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>No organisation linked to this account.</div>;
  }
  const code = billing.organization_code;
  const copy = () => {
    navigator.clipboard.writeText(code || '');
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="space-y-5" data-testid="account-section-organisation">
      <div className="account-card rounded-xl p-5">
        <div className="text-[10px] uppercase tracking-wider font-semibold mb-2" style={{ color: 'var(--theme-text-muted)' }}>Organisation</div>
        <div className="text-xl font-extrabold" style={{ color: 'var(--theme-text)' }} data-testid="account-org-name">{billing.organization}</div>
        <div className="text-sm mt-1" style={{ color: 'var(--theme-text-muted)' }}>Joined {billing.member_since ? new Date(billing.member_since).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) : '—'}</div>
      </div>

      {code && (
        <div className="account-card rounded-xl p-5">
          <div className="text-[10px] uppercase tracking-wider font-semibold mb-2" style={{ color: 'var(--theme-text-muted)' }}>Invite code</div>
          <div className="flex items-center gap-2">
            <code className="text-lg font-mono" style={{ color: 'var(--brand-color, var(--color-brand-blue))' }} data-testid="account-org-code">{code}</code>
            <button
              type="button"
              onClick={copy}
              className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}
              data-testid="account-org-code-copy"
            >
              {copied ? <Check size={12} /> : <Copy size={12} />} {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
          <p className="text-[11px] mt-2" style={{ color: 'var(--theme-text-muted)' }}>Share this code with new teammates so they join the right org.</p>
        </div>
      )}

      <div className="account-card rounded-xl p-5">
        <div className="text-[10px] uppercase tracking-wider font-semibold mb-2" style={{ color: 'var(--theme-text-muted)' }}>Your role</div>
        <div className="text-base capitalize" style={{ color: 'var(--theme-text)' }} data-testid="account-org-role">{profile?.role || 'staff'}</div>
        <p className="text-[11px] mt-1" style={{ color: 'var(--theme-text-muted)' }}>Roles control which workspaces and actions you can access.</p>
      </div>
    </div>
  );
}

// ─── Team & Roles ─────────────────────────────────────────────────
function TeamSection({ profile }) {
  const headers = useAuthHeaders();
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [showInvite, setShowInvite] = useState(false);
  const [form, setForm] = useState({ email: '', full_name: '', role: 'staff' });
  const [tempPwd, setTempPwd] = useState('');

  const isOwner = (profile?.role || '').toLowerCase() === 'owner';
  const isManager = (profile?.role || '').toLowerCase() === 'manager';
  const canManage = isOwner || isManager;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/account/team`, { headers: headers() });
      setMembers(data.members || []);
    } catch {
      setMembers([]);
    }
    setLoading(false);
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const invite = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/account/team/invite`, form, { headers: headers() });
      setTempPwd(data.temp_password);
      setForm({ email: '', full_name: '', role: 'staff' });
      await load();
      toast.success('Invite created');
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
              </select>
            </FieldRow>
          </div>
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
        </div>
      )}

      <div className="account-card rounded-xl divide-y" style={{ borderColor: 'var(--theme-border)' }}>
        {loading && <div className="px-4 py-6 text-sm text-center" style={{ color: 'var(--theme-text-muted)' }}>Loading…</div>}
        {!loading && members.map((m) => {
          const me = m.id === profile?.id;
          const editable = canManage && !me && m.role !== 'owner';
          return (
            <div key={m.id} className="px-4 py-3 flex items-center justify-between gap-3" data-testid={`account-team-member-${m.id}`}>
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
                  </select>
                ) : (
                  <span className="text-[11px] uppercase tracking-wider px-2 py-1 rounded border capitalize" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>{m.role}</span>
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
          );
        })}
        {!loading && members.length === 0 && (
          <div className="px-4 py-6 text-sm text-center" style={{ color: 'var(--theme-text-muted)' }}>No teammates yet.</div>
        )}
      </div>
    </div>
  );
}

// ─── Shared subcomponents ─────────────────────────────────────────
function FieldRow({ label, children }) {
  return (
    <label className="block">
      <div className="text-[11px] font-semibold uppercase tracking-wide mb-1.5" style={{ color: 'var(--theme-text-muted)' }}>{label}</div>
      {children}
    </label>
  );
}

// ─── Modal shell ──────────────────────────────────────────────────
export default function AccountSettingsModal({ open, onClose }) {
  const { user, API: ctxAPI } = useAuth();
  const headers = useAuthHeaders();
  const [section, setSection] = useState('profile');
  const [profile, setProfile] = useState(null);
  const [billing, setBilling] = useState(null);

  const sections = useMemo(() => SECTIONS, []);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    const url = ctxAPI || API;
    axios.get(`${url}/account/billing`, { headers: headers() })
      .then((r) => {
        setBilling(r.data);
        setProfile((p) => p || ({
          id: user?.id, email: r.data.email, full_name: r.data.full_name,
          role: r.data.role, avatar_url: user?.avatar_url, phone: user?.phone,
        }));
      })
      .catch(() => setBilling(null));
  }, [open, ctxAPI, headers, user]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[120] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={onClose}
      data-testid="account-settings-overlay"
    >
      <style>{`
        .account-input {
          width: 100%; height: 40px; padding: 0 12px;
          background: var(--theme-input-bg);
          border: 1px solid var(--theme-input-border, var(--theme-border));
          color: var(--theme-text); border-radius: 8px; font-size: 14px;
          transition: border-color 0.15s;
        }
        .account-input.account-input-sm { height: 30px; font-size: 12px; padding: 0 8px; }
        .account-input:focus { outline: none; border-color: var(--brand-color, var(--color-brand-blue)); }
        .account-input::placeholder { color: var(--theme-text-muted); opacity: 0.7; }
        .account-section-title {
          font-size: 14px; font-weight: 700; color: var(--theme-text); letter-spacing: -0.01em;
        }
        .account-section-sub {
          font-size: 12px; color: var(--theme-text-muted); margin-top: 2px;
        }
        .account-btn-primary {
          display: inline-flex; align-items: center; gap: 6px;
          height: 36px; padding: 0 16px; font-size: 13px; font-weight: 600;
          background: var(--brand-color, var(--color-brand-blue)); color: #FFFFFF; border-radius: 8px;
          transition: opacity 0.15s; border: none;
        }
        .account-btn-primary:hover { opacity: 0.9; }
        .account-btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
        .account-btn-secondary {
          display: inline-flex; align-items: center; gap: 6px;
          height: 36px; padding: 0 14px; font-size: 13px; font-weight: 500;
          background: transparent; color: var(--theme-text);
          border: 1px solid var(--theme-border); border-radius: 8px;
          transition: background 0.15s;
        }
        .account-btn-secondary:hover { background: var(--theme-border-soft); }
        .account-modal-shell {
          background: var(--theme-bg);
          border: 1px solid var(--theme-border);
          color: var(--theme-text);
        }
        .account-modal-divider { border-color: var(--theme-border); }
        .account-sidebar { background: var(--theme-border-soft); }
        .account-nav-active {
          background: color-mix(in srgb, var(--brand-color, #0055FF) 15%, transparent);
          color: var(--brand-color, var(--color-brand-blue));
        }
        .account-nav-idle {
          color: var(--theme-text-muted);
        }
        .account-nav-idle:hover {
          background: var(--theme-border-soft);
          color: var(--theme-text);
        }
        .account-card {
          border: 1px solid var(--theme-border);
          background: var(--theme-border-soft);
        }
        .account-avatar-placeholder {
          background: color-mix(in srgb, var(--brand-color, #0055FF) 15%, transparent);
          border: 1px solid color-mix(in srgb, var(--brand-color, #0055FF) 30%, transparent);
          color: var(--brand-color, var(--color-brand-blue));
        }
      `}</style>
      <div
        onClick={(e) => e.stopPropagation()}
        className="account-modal-shell relative w-[920px] max-w-full h-[640px] max-h-[92vh] rounded-2xl shadow-2xl overflow-hidden flex flex-col"
        data-testid="account-settings-modal"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b account-modal-divider">
          <div>
            <h2 className="text-base font-bold" style={{ color: 'var(--theme-text)' }}>Account settings</h2>
            <p className="text-[11px] mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>Manage your profile, security, plan and team.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-md transition"
            style={{ color: 'var(--theme-text-muted)' }}
            data-testid="account-settings-close"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex-1 grid grid-cols-[200px_1fr] min-h-0">
          <nav className="account-sidebar border-r account-modal-divider p-3 flex flex-col gap-1 overflow-y-auto">
            {sections.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                onClick={() => setSection(id)}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-left font-medium transition ${
                  section === id ? 'account-nav-active' : 'account-nav-idle'
                }`}
                data-testid={`account-nav-${id}`}
              >
                <Icon size={15} />
                {label}
              </button>
            ))}
          </nav>

          <div className="overflow-y-auto p-6">
            {section === 'profile' && (
              <ProfileSection profile={profile} onProfileUpdate={(p) => setProfile((prev) => ({ ...(prev || {}), ...p }))} />
            )}
            {section === 'security' && <SecuritySection />}
            {section === 'preferences' && <PreferencesSection />}
            {section === 'billing' && <BillingSection billing={billing} onClose={onClose} />}
            {section === 'organisation' && <OrganisationSection billing={billing} profile={profile} />}
            {section === 'team' && <TeamSection profile={profile} />}
          </div>
        </div>
      </div>
    </div>
  );
}
