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
import { Link, useNavigate } from 'react-router-dom';
import {
  X, User, ShieldCheck, Sliders, CreditCard, Building2, Users, ListChecks,
  Camera, Trash2, Loader2, Check, Copy, Plus, ArrowUpRight, FileText,
} from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/App';
import MFASetupCard from './MFASetupCard';
import DigestPreferencesCard from './DigestPreferencesCard';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const SECTIONS = [
  { id: 'profile', label: 'Profile', icon: User },
  { id: 'onboarding', label: 'Onboarding', icon: ListChecks },
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

// ─── Onboarding ───────────────────────────────────────────────────
function OnboardingSection({ onJumpSection, onClose, profile }) {
  const headers = useAuthHeaders();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const { data } = await axios.get(`${API}/account/onboarding`, { headers: headers() });
        if (!cancelled) setData(data);
      } catch {
        if (!cancelled) setData({ steps: [], percent: 0 });
      }
      if (!cancelled) setLoading(false);
    };
    load();
    return () => { cancelled = true; };
  }, [headers]);

  // Iter 216h60 — resolve symbolic onboarding routes to ACTUAL react-
  // router routes for the current user. Previously the backend handed
  // out `/sites` and `/dashboard?tab=equipment` indiscriminately and
  // Pulse/Lite operators bounced to the GymAxis 404 page (Lee's
  // screenshot). Now we map them to the right destination.
  const resolveRoute = (route) => {
    if (!route) return route;
    const isMaster = !!profile?.is_master_admin;
    const at = (profile?.account_type || '').toLowerCase();
    const isPulse = at === 'pulse_pro' || at === 'lite';
    // /sites isn't a real route — direct to the right Sites surface.
    if (route === '/sites' || route.startsWith('/sites?')) {
      if (isMaster) return '/master-admin?section=organizations';
      // Pulse operators manage sites via the Settings dialog (which
      // hosts PulseSettingsTab → "Add Site"). Opening with the
      // ?settings=sites deep-link triggers the dialog on mount.
      if (isPulse) return '/pulse?settings=sites';
      return '/dashboard';
    }
    // Equipment tab: Pulse operators land on /pulse with the equipment tab.
    if (route.startsWith('/dashboard?tab=equipment')) {
      if (isPulse) return '/pulse?tab=equipment';
    }
    if (route === '/dashboard' || route.startsWith('/dashboard?')) {
      if (isMaster) return route.replace('/dashboard', '/master-admin');
      if (isPulse) return route.replace('/dashboard', '/pulse');
    }
    if (route === '/pricing' && isMaster) return '/master-admin?section=integrations-hub';
    return route;
  };

  const handleStep = (step) => {
    if (step.cta_section) {
      onJumpSection(step.cta_section);
    } else if (step.cta_route) {
      navigate(resolveRoute(step.cta_route));
      onClose();
    }
  };

  if (loading) {
    return <div className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>Loading checklist…</div>;
  }
  const pct = data?.percent ?? 0;
  return (
    <div className="space-y-5" data-testid="account-section-onboarding">
      <div>
        <h3 className="account-section-title">Setup checklist</h3>
        <p className="account-section-sub">
          {data?.completed_count ?? 0} of {data?.total ?? 0} steps complete — finish them in any order.
        </p>
      </div>
      <div className="rounded-full overflow-hidden h-2 w-full" style={{ background: 'var(--theme-border-soft)' }}>
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, background: 'var(--brand-color, var(--color-brand-blue))' }}
          data-testid="account-onboarding-progress"
        />
      </div>
      <div className="space-y-2">
        {(data?.steps || []).map((s) => (
          <div
            key={s.id}
            className="account-card rounded-xl p-4 flex items-start gap-3"
            data-testid={`account-onboarding-step-${s.id}`}
            data-completed={s.completed ? 'true' : 'false'}
          >
            <div
              className="mt-0.5 w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0"
              style={{
                background: s.completed
                  ? 'var(--brand-color, var(--color-brand-blue))'
                  : 'transparent',
                border: s.completed
                  ? 'none'
                  : '1.5px solid var(--theme-border)',
              }}
            >
              {s.completed && <Check size={12} color="#FFFFFF" strokeWidth={3} />}
            </div>
            <div className="flex-1 min-w-0">
              <div
                className={`text-sm font-semibold ${s.completed ? 'line-through opacity-60' : ''}`}
                style={{ color: 'var(--theme-text)' }}
              >
                {s.label}
              </div>
              <div className="text-xs mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
                {s.description}
              </div>
            </div>
            <button
              type="button"
              onClick={() => handleStep(s)}
              className="account-btn-secondary flex-shrink-0"
              data-testid={`account-onboarding-cta-${s.id}`}
            >
              {s.completed ? 'Review' : (s.cta_label || 'Open')}
            </button>
          </div>
        ))}
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
  const { user } = useAuth();
  const headers = useAuthHeaders();
  const trial = user?.trial;
  const isTrial = !!trial?.is_trial;
  const [pricing, setPricing] = useState(null);
  const [moduleBusy, setModuleBusy] = useState(null);

  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/payments/pricing`)
      .then((r) => { if (!cancelled) setPricing(r.data); })
      .catch(() => { if (!cancelled) setPricing(null); });
    return () => { cancelled = true; };
  }, []);

  // Modules already enabled on this org (so we can render Active vs Add-this-module)
  const enabledModules = new Set(Object.entries(user?.module_access || {})
    .filter(([, v]) => !!v).map(([k]) => k));

  const startCheckout = async (plan, opts = {}) => {
    setModuleBusy(opts.module_id || plan);
    try {
      const { data } = await axios.post(
        `${API}/payments/checkout/flex`,
        { plan, origin_url: window.location.origin, ...opts },
        { headers: headers() },
      );
      if (data?.url) {
        window.location.href = data.url;
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not open checkout');
      setModuleBusy(null);
    }
  };

  if (!billing) {
    return <div className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>Loading billing…</div>;
  }

  return (
    <div className="space-y-6" data-testid="account-section-billing">
      {/* Trial state — visible when org is in any trial status */}
      {isTrial && (
        <div
          className="rounded-xl p-5"
          style={{
            border: `1px solid ${trial.status === 'expired' || trial.status === 'suspended' ? '#dc2626' : trial.status === 'expiring_soon' ? '#f59e0b' : 'var(--brand-color, #0055FF)'}`,
            background: trial.status === 'expired' || trial.status === 'suspended'
              ? 'color-mix(in srgb, #dc2626 8%, transparent)'
              : trial.status === 'expiring_soon'
                ? 'color-mix(in srgb, #f59e0b 8%, transparent)'
                : 'color-mix(in srgb, var(--brand-color, #0055FF) 5%, transparent)',
          }}
          data-testid="account-billing-trial-card"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-wider font-bold mb-1"
                   style={{ color: trial.status === 'expired' || trial.status === 'suspended' ? '#dc2626' : trial.status === 'expiring_soon' ? '#b45309' : 'var(--brand-color, var(--color-brand-blue))' }}>
                {trial.status === 'suspended' ? 'Trial suspended' :
                 trial.status === 'expired' ? 'Trial expired' :
                 trial.status === 'expiring_soon' ? 'Trial ending soon' :
                 'Free trial active'}
              </div>
              <div className="text-xl font-extrabold" style={{ color: 'var(--theme-text)' }} data-testid="account-billing-trial-countdown">
                {trial.status === 'suspended' ? 'Access has been suspended' :
                 trial.days_left > 0 ? `${trial.days_left} day${trial.days_left === 1 ? '' : 's'} remaining` :
                 trial.hours_left > 0 ? `${trial.hours_left} hour${trial.hours_left === 1 ? '' : 's'} remaining` :
                 'Trial has ended'}
              </div>
              <div className="text-sm mt-1" style={{ color: 'var(--theme-text-muted)' }}>
                Trial ends {trial.trial_ends_at ? new Date(trial.trial_ends_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) : '—'}.
                {trial.status === 'expired' && ' Upgrade to keep your data — it will be permanently deleted after the grace period.'}
                {trial.status === 'expiring_soon' && ' Upgrade now to avoid losing access.'}
                {trial.status === 'active' && ' Add a payment method whenever you’re ready.'}
              </div>
            </div>
            <button
              type="button"
              onClick={() => startCheckout('bundle', { site_count: 1 })}
              disabled={moduleBusy === 'bundle'}
              className="account-btn-primary flex-shrink-0"
              data-testid="account-billing-upgrade-now-btn"
            >
              {moduleBusy === 'bundle' ? <Loader2 size={14} className="animate-spin" /> : null}
              Upgrade Plan <ArrowUpRight size={14} />
            </button>
          </div>
        </div>
      )}

      <div className="account-card rounded-xl p-5">
        <div className="text-[10px] uppercase tracking-wider font-semibold mb-2" style={{ color: 'var(--theme-text-muted)' }}>Current plan</div>
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xl font-extrabold" style={{ color: 'var(--theme-text)' }}>{billing.plan_name}</div>
            <div className="text-sm mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
              {isTrial ? 'On free trial — payment due before trial ends' :
               billing.plan_price > 0 ? `£${billing.plan_price}/month` : 'No active subscription'}
            </div>
          </div>
          <button
            type="button"
            onClick={() => startCheckout('bundle', { site_count: 1 })}
            disabled={moduleBusy === 'bundle'}
            className="account-btn-primary"
            data-testid="account-billing-upgrade-btn"
          >
            {moduleBusy === 'bundle' ? <Loader2 size={14} className="animate-spin" /> : null}
            {billing.current_plan === 'none' || isTrial ? 'Upgrade Plan' : 'Change plan'}
            <ArrowUpRight size={14} />
          </button>
        </div>
      </div>

      {/* Modules — buy individual ones if you don't want the full bundle */}
      {pricing?.modules?.length > 0 && (
        <div data-testid="account-billing-modules">
          <h3 className="account-section-title">Add a module</h3>
          <p className="account-section-sub">
            Pay only for what you need — or upgrade to the {pricing.bundle?.name || 'GymAxis Pro'} bundle for everything at £{pricing.bundle?.monthly}/mo.
          </p>
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
            {pricing.modules.map((m) => {
              const active = enabledModules.has(m.id);
              return (
                <div
                  key={m.id}
                  className="account-card rounded-xl p-4 flex items-center justify-between gap-3"
                  data-testid={`account-billing-module-${m.id}`}
                >
                  <div className="min-w-0">
                    <div className="text-sm font-semibold capitalize" style={{ color: 'var(--theme-text)' }}>{m.name}</div>
                    <div className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>£{m.monthly}/mo · £{m.annual}/yr</div>
                  </div>
                  {active ? (
                    <span className="text-[10px] uppercase tracking-wider px-2 py-1 rounded font-bold" style={{
                      color: 'var(--brand-color, var(--color-brand-blue))',
                      background: 'color-mix(in srgb, var(--brand-color, #0055FF) 12%, transparent)',
                    }}>
                      <Check size={10} className="inline mr-0.5" /> Active
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => startCheckout('module', { module_id: m.id })}
                      disabled={moduleBusy === m.id}
                      className="account-btn-secondary flex-shrink-0"
                      data-testid={`account-billing-add-module-${m.id}`}
                    >
                      {moduleBusy === m.id ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                      Add this module
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div>
        <h3 className="account-section-title">Payment history</h3>
        <p className="account-section-sub">Last 50 transactions on this account.</p>
        <div className="mt-3 account-card rounded-xl divide-y max-h-72 overflow-y-auto" style={{ borderColor: 'var(--theme-border)' }}>
          {(billing.payment_history || []).length === 0 && (
            <div className="px-4 py-6 text-sm text-center" style={{ color: 'var(--theme-text-muted)' }}>No payments yet.</div>
          )}
          {(billing.payment_history || []).map((p, idx) => {
            const invoiceId = p.id || p.session_id;
            const downloadPdf = async () => {
              if (!invoiceId) return;
              const token = localStorage.getItem('token');
              try {
                const resp = await fetch(
                  `${API}/account/billing/${encodeURIComponent(invoiceId)}/invoice.pdf`,
                  { headers: { Authorization: `Bearer ${token}` } },
                );
                if (resp.redirected) {
                  window.open(resp.url, '_blank', 'noopener');
                  return;
                }
                if (!resp.ok) throw new Error('Download failed');
                const blob = await resp.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `invoice-${String(invoiceId).slice(0, 12)}.pdf`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
              } catch (err) {
                toast.error('Could not download invoice');
              }
            };
            return (
              <div key={idx} className="px-4 py-3 flex items-center justify-between gap-3 text-sm" data-testid={`account-payment-${idx}`}>
                <div className="min-w-0">
                  <div className="font-medium truncate" style={{ color: 'var(--theme-text)' }}>{p.package_id ? p.package_id.charAt(0).toUpperCase() + p.package_id.slice(1) : (p.package_name || 'Charge')}</div>
                  <div className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>{p.created_at ? new Date(p.created_at).toLocaleDateString() : ''}</div>
                </div>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <div className="text-right">
                    <div className="font-semibold" style={{ color: 'var(--theme-text)' }}>£{Number(p.amount || 0).toFixed(2)}</div>
                    <div className={`text-[11px] uppercase tracking-wider font-bold ${p.payment_status === 'paid' ? 'text-emerald-500' : 'text-amber-500'}`}>
                      {p.payment_status || 'pending'}
                    </div>
                  </div>
                  {invoiceId && (
                    <button
                      type="button"
                      onClick={downloadPdf}
                      className="inline-flex items-center gap-1 text-xs px-2 py-1.5 rounded border transition"
                      style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}
                      title="Download invoice PDF"
                      data-testid={`account-payment-pdf-${idx}`}
                    >
                      <FileText size={12} /> PDF
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ─── Organisation ────────────────────────────────────────────────
// ─── Organisation ────────────────────────────────────────────────
function OrganisationSection({ billing, profile }) {
  const headers = useAuthHeaders();
  const [org, setOrg] = useState(null);
  const [form, setForm] = useState({
    address_line1: '', address_line2: '', address_line3: '', city: '',
    postcode: '', country: '', phone: '', primary_contact_email: '',
    primary_contact_phone: '', website: '',
  });
  const [saving, setSaving] = useState(false);
  // Iter 216h57 — inline logo upload so the "Upload logo" onboarding
  // step works without navigating away (previously it tried to push
  // to /dashboard?settings=brand which doesn't exist and closed the
  // settings modal).
  const [logoUploading, setLogoUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [applyingColor, setApplyingColor] = useState('');
  const logoFileRef = useRef(null);
  const isOwner = (profile?.role || '').toLowerCase() === 'owner';
  const isManager = (profile?.role || '').toLowerCase() === 'manager';
  const canEditLogo = isOwner || isManager;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await axios.get(`${API}/account/organisation`, { headers: headers() });
        if (cancelled) return;
        setOrg(data);
        setForm({
          address_line1: data.address_line1 || '',
          address_line2: data.address_line2 || '',
          address_line3: data.address_line3 || '',
          city: data.city || '',
          postcode: data.postcode || '',
          country: data.country || '',
          phone: data.phone || '',
          primary_contact_email: data.primary_contact_email || '',
          primary_contact_phone: data.primary_contact_phone || '',
          website: data.website || '',
        });
      } catch {
        if (!cancelled) setOrg(null);
      }
    })();
    return () => { cancelled = true; };
  }, [headers]);

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await axios.patch(`${API}/account/organisation`, form, { headers: headers() });
      setOrg(data);
      toast.success('Organisation details updated');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Update failed');
    }
    setSaving(false);
  };

  if (!org && !billing?.organization) {
    return <div className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>No organisation linked to this account.</div>;
  }

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const onLogoFile = async (e) => {
    const f = e.target?.files?.[0] || e;
    if (!f) return;
    await uploadLogo(f);
    if (logoFileRef.current) logoFileRef.current.value = '';
  };

  const uploadLogo = async (f) => {
    setLogoUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', f);
      const { data } = await axios.post(`${API}/account/logo`, fd, {
        headers: { ...headers(), 'Content-Type': 'multipart/form-data' },
      });
      setOrg((o) => ({ ...(o || {}), logo_url: data.logo_url, brand_palette: data.brand_palette || [] }));
      toast.success(
        data.brand_palette?.length
          ? `Logo uploaded — ${data.brand_palette.length} brand colour${data.brand_palette.length === 1 ? '' : 's'} detected`
          : 'Logo uploaded',
      );
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Logo upload failed');
    }
    setLogoUploading(false);
  };

  // Iter 216h58 — drag-and-drop + extracted brand-colour palette.
  const onLogoDrop = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    if (!canEditLogo) {
      toast.error('Only the Owner or a Manager can change the logo.');
      return;
    }
    const f = e.dataTransfer?.files?.[0];
    if (!f) return;
    if (!/^image\//.test(f.type)) {
      toast.error('Please drop an image file (PNG, JPG, or WebP).');
      return;
    }
    await uploadLogo(f);
  };

  const applyBrandColor = async (hex) => {
    setApplyingColor(hex);
    try {
      await axios.post(`${API}/account/branding/apply`, { primary_color: hex }, { headers: headers() });
      setOrg((o) => ({ ...(o || {}), primary_color: hex }));
      toast.success(`Brand colour set to ${hex}`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not apply brand colour');
    }
    setApplyingColor('');
  };

  const removeLogo = async () => {
    setLogoUploading(true);
    try {
      await axios.delete(`${API}/account/logo`, { headers: headers() });
      setOrg((o) => ({ ...(o || {}), logo_url: null }));
      toast.success('Logo removed');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Remove failed');
    }
    setLogoUploading(false);
  };

  return (
    <div className="space-y-5" data-testid="account-section-organisation">
      <div className="account-card rounded-xl p-5">
        <div className="text-[10px] uppercase tracking-wider font-semibold mb-2" style={{ color: 'var(--theme-text-muted)' }}>Organisation</div>
        <div className="text-xl font-extrabold" style={{ color: 'var(--theme-text)' }} data-testid="account-org-name">
          {org?.name || billing?.organization}
        </div>
        <div className="text-sm mt-1" style={{ color: 'var(--theme-text-muted)' }}>
          Joined {billing?.member_since ? new Date(billing.member_since).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) : '—'}
        </div>
      </div>

      {/* Iter 216h58 — drag-and-drop logo zone with auto-extracted
          brand-colour palette. Replaces the static button-only layout
          shipped in iter 216h57 — operators now drop a PNG/JPG and
          instantly see the dominant colours pulled from the image,
          one-click apply to set the org-wide primary brand colour. */}
      <div data-testid="account-section-logo">
        <h3 className="account-section-title">Organisation logo & brand colour</h3>
        <p className="account-section-sub">Drop a PNG / JPG. Brand colours are auto-extracted — one click applies them across invoices, member emails, and supplier case pages.</p>

        <div
          onDragOver={(e) => { if (canEditLogo) { e.preventDefault(); setDragOver(true); } }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onLogoDrop}
          className={`mt-3 relative rounded-xl border-2 border-dashed transition p-4 flex flex-col sm:flex-row gap-5 items-center ${dragOver ? 'border-[var(--theme-accent)] bg-[var(--theme-accent)]/5' : ''}`}
          style={{ borderColor: dragOver ? undefined : 'var(--theme-border)' }}
          data-testid="account-org-logo-dropzone"
        >
          <div className="relative w-24 h-24 shrink-0 rounded-xl flex items-center justify-center overflow-hidden" style={{ background: 'var(--theme-surface-sunken)', border: '1px solid var(--theme-border)' }}>
            {org?.logo_url ? (
              <img src={org.logo_url} alt={`${org?.name || 'Organisation'} logo`} className="max-w-full max-h-full object-contain" data-testid="account-org-logo-img" />
            ) : (
              <span className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>No logo</span>
            )}
            {logoUploading && (
              <div className="absolute inset-0 bg-black/60 flex items-center justify-center">
                <Loader2 size={20} className="animate-spin text-white" />
              </div>
            )}
          </div>

          <div className="flex-1 flex flex-col gap-2 min-w-0">
            <p className="text-xs font-semibold" style={{ color: 'var(--theme-text)' }}>
              {dragOver ? 'Drop to upload' : 'Drag & drop a logo here, or click the button.'}
            </p>
            <p className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>
              PNG (transparent preferred), JPG or WebP — up to 8 MB. Auto-resized to 512px.
            </p>

            <input
              ref={logoFileRef} type="file" accept="image/png,image/jpeg,image/jpg,image/webp"
              onChange={onLogoFile} className="hidden" data-testid="account-org-logo-input"
            />
            <div className="flex flex-wrap gap-2 mt-1">
              <button
                type="button"
                onClick={() => logoFileRef.current?.click()}
                disabled={!canEditLogo || logoUploading}
                className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider px-3 py-1.5 border rounded-md transition disabled:opacity-50"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                data-testid="account-org-logo-upload-btn"
              >
                <Camera size={13} /> {org?.logo_url ? 'Replace logo' : 'Upload logo'}
              </button>
              {org?.logo_url && canEditLogo && (
                <button
                  type="button"
                  onClick={removeLogo}
                  disabled={logoUploading}
                  className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider px-3 py-1.5 hover:text-red-400 transition disabled:opacity-50"
                  style={{ color: 'var(--theme-text-muted)' }}
                  data-testid="account-org-logo-remove-btn"
                >
                  <Trash2 size={13} /> Remove
                </button>
              )}
              {!canEditLogo && (
                <p className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>Only the Owner or a Manager can change the logo.</p>
              )}
            </div>
          </div>
        </div>

        {/* Extracted palette ─ tap to apply */}
        {(org?.brand_palette?.length || org?.primary_color) ? (
          <div className="mt-4" data-testid="account-org-palette">
            <p className="text-[11px] uppercase tracking-wider font-semibold mb-2" style={{ color: 'var(--theme-text-muted)' }}>
              Extracted brand palette {org?.primary_color ? <span className="ml-2 normal-case text-[10px]" style={{ color: 'var(--theme-text)' }}>· active: <span className="font-mono">{org.primary_color}</span></span> : null}
            </p>
            <div className="flex flex-wrap gap-2">
              {(org.brand_palette || []).map((hex) => {
                const active = (org?.primary_color || '').toUpperCase() === hex.toUpperCase();
                return (
                  <button
                    key={hex}
                    type="button"
                    onClick={() => canEditLogo && applyBrandColor(hex)}
                    disabled={!canEditLogo || applyingColor === hex}
                    className={`group relative w-16 h-16 rounded-lg border-2 transition flex flex-col items-center justify-end overflow-hidden disabled:opacity-50 ${active ? 'ring-2 ring-offset-2 ring-[var(--theme-accent)]' : 'hover:scale-[1.04]'}`}
                    style={{ background: hex, borderColor: active ? 'var(--theme-accent)' : 'var(--theme-border)' }}
                    data-testid={`account-org-palette-swatch-${hex.replace('#','').toLowerCase()}`}
                    title={active ? `${hex} — current brand colour` : `Apply ${hex} as brand colour`}
                  >
                    <span className="w-full bg-black/40 text-white text-[9px] font-mono py-0.5 backdrop-blur-sm">
                      {applyingColor === hex ? '…' : hex}
                    </span>
                  </button>
                );
              })}
              {!org?.brand_palette?.length && org?.primary_color && (
                <div
                  className="w-16 h-16 rounded-lg border flex items-end justify-center overflow-hidden"
                  style={{ background: org.primary_color, borderColor: 'var(--theme-border)' }}
                >
                  <span className="w-full bg-black/40 text-white text-[9px] font-mono py-0.5 text-center">
                    {org.primary_color}
                  </span>
                </div>
              )}
            </div>
            {canEditLogo && org?.brand_palette?.length > 0 && (
              <p className="mt-2 text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>
                Click a swatch to set it as the organisation’s primary brand colour.
              </p>
            )}
          </div>
        ) : null}
      </div>

      <div>
        <h3 className="account-section-title">Registered address</h3>
        <p className="account-section-sub">Used on invoices, official emails, and admin records.</p>
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
          <FieldRow label="Address line 1">
            <input
              type="text" value={form.address_line1}
              onChange={(e) => update('address_line1', e.target.value)}
              disabled={!isOwner}
              className="account-input" data-testid="account-org-address1"
            />
          </FieldRow>
          <FieldRow label="Address line 2">
            <input
              type="text" value={form.address_line2}
              onChange={(e) => update('address_line2', e.target.value)}
              disabled={!isOwner}
              className="account-input" data-testid="account-org-address2"
            />
          </FieldRow>
          <FieldRow label="City">
            <input
              type="text" value={form.city}
              onChange={(e) => update('city', e.target.value)}
              disabled={!isOwner}
              className="account-input" data-testid="account-org-city"
            />
          </FieldRow>
          <FieldRow label="Postcode">
            <input
              type="text" value={form.postcode}
              onChange={(e) => update('postcode', e.target.value)}
              disabled={!isOwner}
              className="account-input" data-testid="account-org-postcode"
            />
          </FieldRow>
          <FieldRow label="Country">
            <input
              type="text" value={form.country}
              onChange={(e) => update('country', e.target.value)}
              disabled={!isOwner}
              className="account-input" data-testid="account-org-country"
            />
          </FieldRow>
          <FieldRow label="Website">
            <input
              type="url" placeholder="https://" value={form.website}
              onChange={(e) => update('website', e.target.value)}
              disabled={!isOwner}
              className="account-input" data-testid="account-org-website"
            />
          </FieldRow>
        </div>
      </div>

      <div>
        <h3 className="account-section-title">Primary contact</h3>
        <p className="account-section-sub">The point person we email about billing, downtime, and account issues.</p>
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
          <FieldRow label="Contact email">
            <input
              type="email" value={form.primary_contact_email}
              onChange={(e) => update('primary_contact_email', e.target.value)}
              disabled={!isOwner}
              className="account-input" data-testid="account-org-contact-email"
            />
          </FieldRow>
          <FieldRow label="Contact phone">
            <input
              type="tel" value={form.primary_contact_phone}
              onChange={(e) => update('primary_contact_phone', e.target.value)}
              disabled={!isOwner}
              className="account-input" data-testid="account-org-contact-phone"
            />
          </FieldRow>
          <FieldRow label="Main switchboard">
            <input
              type="tel" value={form.phone}
              onChange={(e) => update('phone', e.target.value)}
              disabled={!isOwner}
              className="account-input" data-testid="account-org-phone"
            />
          </FieldRow>
        </div>
      </div>

      {isOwner && (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="account-btn-primary"
            data-testid="account-org-save-btn"
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : null}
            Save organisation
          </button>
        </div>
      )}
      {!isOwner && (
        <p className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>
          Only the organisation Owner can edit these details.
        </p>
      )}
    </div>
  );
}

// ─── Team & Roles ─────────────────────────────────────────────────
function TeamSection({ profile, inviteCode }) {
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
            <h2 className="text-base font-bold" style={{ color: 'var(--theme-text)' }}>Account Settings</h2>
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
            {section === 'onboarding' && (
              <OnboardingSection
                onJumpSection={(id) => setSection(id)}
                onClose={onClose}
                profile={profile}
              />
            )}
            {section === 'security' && <SecuritySection />}
            {section === 'preferences' && <PreferencesSection />}
            {section === 'billing' && <BillingSection billing={billing} onClose={onClose} />}
            {section === 'organisation' && <OrganisationSection billing={billing} profile={profile} />}
            {section === 'team' && <TeamSection profile={profile} inviteCode={billing?.organization_code} />}
          </div>
        </div>
      </div>
    </div>
  );
}
