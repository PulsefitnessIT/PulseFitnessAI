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
import { useState, useEffect } from 'react';
import axios from 'axios';
import { X, Mail, Building, ShieldCheck, KeyRound, Copy, Check, AlertTriangle, ArrowUpRight, Layers, CircleCheck, CircleSlash, Wand2, History } from 'lucide-react';
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

// Iter 278f — Module access diagnostics. Shows, per module, whether the
// ORG has it enabled and whether THIS user effectively gets in, with a
// plain-English reason — so a master admin can self-diagnose lock-outs
// (e.g. the recurring "CRM is not enabled" Pulse Master Admin case).
const ModuleAccessSection = ({ userId, headers }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [fixing, setFixing] = useState(null);
  const [audit, setAudit] = useState([]);

  const fetchData = () => axios
    .get(`${API_BASE}/master-admin/users/${userId}/module-access`, { headers })
    .then(({ data }) => setData(data))
    .catch(() => setError(true));

  const fetchAudit = () => axios
    .get(`${API_BASE}/master-admin/users/${userId}/module-access/audit`, { headers })
    .then(({ data }) => setAudit(data.events || []))
    .catch(() => {});

  useEffect(() => {
    let alive = true;
    setLoading(true); setError(false);
    Promise.all([
      axios.get(`${API_BASE}/master-admin/users/${userId}/module-access`, { headers }).then(({ data }) => { if (alive) setData(data); }),
      axios.get(`${API_BASE}/master-admin/users/${userId}/module-access/audit`, { headers }).then(({ data }) => { if (alive) setAudit(data.events || []); }).catch(() => {}),
    ]).catch(() => { if (alive) setError(true); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [userId]); // eslint-disable-line react-hooks/exhaustive-deps

  const UNDO_SCOPE = { granted_org: 'org', restored_user: 'user', granted_org_and_restored_user: 'both' };

  const undo = async (m, scope) => {
    try {
      const { data } = await axios.post(
        `${API_BASE}/master-admin/users/${userId}/module-access/${m.key}/revoke`,
        { scope }, { headers });
      setData(data); fetchAudit();
      toast.success(`${m.label} access change undone`);
    } catch {
      await Promise.all([fetchData(), fetchAudit()]);
      toast.error('Could not undo — please try again');
    }
  };

  const fix = async (m) => {
    setFixing(m.key);
    try {
      // Access-flag toggles (Service Desk / Inventory) — grant or revoke the
      // flag that drives the user's Switch-area.
      if (m.fix_action === 'grant_flag' || m.fix_action === 'revoke_flag') {
        const isRevoke = m.fix_action === 'revoke_flag';
        const { data } = await axios.post(
          `${API_BASE}/master-admin/users/${userId}/module-access/${m.key}/${isRevoke ? 'revoke' : 'grant'}`,
          {}, { headers });
        setData(data); fetchAudit();
        toast.success(isRevoke ? `${m.label} access removed` : `${m.label} access granted`);
        return;
      }
      const { data } = await axios.post(
        `${API_BASE}/master-admin/users/${userId}/module-access/${m.key}/grant`,
        {}, { headers });
      setData(data); fetchAudit();
      const scope = UNDO_SCOPE[data.result];
      const msg = data.result === 'granted_org'
        ? `${m.label} enabled for the organisation`
        : data.result === 'granted_org_and_restored_user'
          ? `${m.label} enabled for the org and restored for this user`
          : `${m.label} access restored`;
      toast.success(msg, scope ? { action: { label: 'Undo', onClick: () => undo(m, scope) }, duration: 8000 } : undefined);
    } catch {
      await fetchData();
      toast.error('Could not update access — please try again');
    } finally {
      setFixing(null);
    }
  };

  return (
    <div className="rounded-lg border bg-white p-4 space-y-3" style={{ borderColor: '#E4E4E7' }} data-testid="people-drawer-module-access">
      <div className="flex items-center gap-2">
        <Layers size={14} className="text-zinc-600" />
        <h3 className="text-sm font-bold text-zinc-900">Module access</h3>
      </div>
      {loading ? (
        <div className="space-y-2">
          {[0, 1, 2, 3].map((i) => <div key={i} className="h-8 rounded bg-zinc-100 animate-pulse" />)}
        </div>
      ) : error ? (
        <p className="text-[11px] text-zinc-500">Couldn't load module access.</p>
      ) : (
        <>
          {data.is_privileged && (
            <div className="rounded-md bg-blue-50 border border-blue-200 px-2.5 py-1.5 text-[11px] text-blue-800" data-testid="module-access-privileged">
              {data.privilege_label} — full access to every module.
            </div>
          )}
          <div className="grid grid-cols-[10px_1fr] gap-x-2 text-[10px] font-bold uppercase tracking-wider text-zinc-400 px-1">
            <span />
            <div className="grid grid-cols-[1fr_auto_auto] gap-2">
              <span>Module</span>
              <span className="text-center w-12">Org</span>
              <span className="text-center w-12">User</span>
            </div>
          </div>
          <div className="space-y-1.5">
            {data.modules.map((m) => (
              <div key={m.key} className="rounded-md border px-2.5 py-2" style={{ borderColor: '#F4F4F5' }} data-testid={`module-access-row-${m.key}`}>
                <div className="grid grid-cols-[1fr_auto_auto] gap-2 items-center">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-zinc-900 truncate">{m.label}</div>
                    <div className="text-[10px] text-zinc-400 truncate">{m.blurb}</div>
                  </div>
                  <AccessDot on={m.org_enabled} />
                  <AccessDot on={m.user_access} testid={`module-access-user-${m.key}`} />
                </div>
                <div className="flex items-center justify-between gap-2 mt-1">
                  <span className="text-[10px]" style={{ color: m.user_access ? '#16a34a' : (m.org_enabled ? '#d97706' : '#a1a1aa') }}>
                    {m.reason}
                  </span>
                  {m.fix_action && (
                    <button
                      onClick={() => fix(m)}
                      disabled={fixing === m.key}
                      className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-1 rounded-md border transition-colors disabled:opacity-50"
                      style={{ borderColor: '#bfdbfe', color: '#1d4ed8', background: '#eff6ff' }}
                      data-testid={`module-access-fix-${m.key}`}
                    >
                      <Wand2 size={11} />
                      {fixing === m.key
                        ? 'Fixing…'
                        : m.fix_action === 'grant_org' ? `Enable ${m.label} for org`
                          : m.fix_action === 'grant_flag' ? `Enable ${m.label}`
                            : m.fix_action === 'revoke_flag' ? `Remove ${m.label}`
                              : 'Restore access'}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
          <p className="text-[10px] text-zinc-400 leading-snug">
            <strong>Org</strong> = enabled for the organisation. <strong>User</strong> = this person's effective access. A green Org but amber User means access was revoked for this user.
          </p>

          {audit.length > 0 && (
            <div className="pt-2 border-t" style={{ borderColor: '#F4F4F5' }} data-testid="module-access-audit">
              <div className="flex items-center gap-1.5 mb-1.5">
                <History size={12} className="text-zinc-400" />
                <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-400">Recent access changes</span>
              </div>
              <ul className="space-y-1">
                {audit.map((e, i) => (
                  <li key={i} className="text-[11px] text-zinc-600 flex items-start gap-1.5" data-testid={`module-access-audit-row-${i}`}>
                    <span className={`mt-1.5 h-1.5 w-1.5 rounded-full flex-shrink-0 ${e.verb === 'revoked' ? 'bg-red-500' : 'bg-emerald-500'}`} />
                    <span className="min-w-0">
                      <span className="text-zinc-800">{e.details}</span>
                      <span className="text-zinc-400"> · {relativeTime(e.timestamp)} · {e.admin_email}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
};

// Iter 279 — Login-access diagnostics + one-click "Repair login access".
// Surfaces which portal(s) a person can actually sign into and fixes the
// "unknown user" class of bug (CRM-only account missing its `users` row)
// in a single click — mirrors a service-portal row keeping the same
// password. See routes/master_admin_users.py get/repair endpoints.
const LoginAccessSection = ({ userId, headers }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true); setError(false);
    axios.get(`${API_BASE}/master-admin/users/${userId}/login-access`, { headers })
      .then(({ data }) => { if (alive) setData(data); })
      .catch(() => { if (alive) setError(true); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const repair = async () => {
    setBusy(true);
    try {
      const { data: res } = await axios.post(
        `${API_BASE}/master-admin/users/${userId}/repair-login`, {}, { headers },
      );
      setData(res);
      if (res.result === 'mirrored_crm_to_service_portal') {
        toast.success('Login access repaired — this user can now sign in on the standard portal.');
      } else {
        toast.info('No repair needed — standard-portal access already present.');
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not repair login access');
    }
    setBusy(false);
  };

  if (loading || error || !data) return null;

  const Row = ({ label, on }) => (
    <div className="flex items-center justify-between text-xs">
      <span className="text-zinc-600">{label}</span>
      {on
        ? <CircleCheck size={16} className="text-emerald-500" />
        : <CircleSlash size={16} className="text-zinc-300" />}
    </div>
  );

  return (
    <div className="rounded-lg border bg-white p-4 space-y-3" style={{ borderColor: '#E4E4E7' }} data-testid="people-drawer-login-access">
      <div className="flex items-center gap-2">
        <KeyRound size={14} className="text-zinc-600" />
        <h3 className="text-sm font-bold text-zinc-900">Login access</h3>
      </div>
      <div className="space-y-1.5">
        <Row label="Standard portal (/login)" on={data.can_standard_login} />
        <Row label="CRM portal" on={data.can_crm_login} />
      </div>
      <p
        className={`text-[11px] leading-snug ${data.needs_repair ? 'text-amber-700' : 'text-zinc-500'}`}
        data-testid="login-access-reason"
      >
        {data.needs_repair && <AlertTriangle size={12} className="inline mr-1 -mt-0.5" />}
        {data.reason}
      </p>
      {data.needs_repair && (
        <>
          <Button
            variant="primary" size="md" className="w-full" icon={Wand2}
            onClick={repair} loading={busy} disabled={busy}
            data-testid="people-drawer-repair-login"
          >
            {busy ? 'Repairing…' : 'Repair login access'}
          </Button>
          {data.password_placeholder && (
            <p className="text-[10px] text-zinc-500 leading-snug">
              This CRM account may not have a known password. After repairing, also issue a reset link below so the user can set one.
            </p>
          )}
        </>
      )}
    </div>
  );
};

function relativeTime(iso) {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const diff = Date.now() - then;
  const mins = Math.round(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

const AccessDot = ({ on, testid }) => (
  <span className="flex justify-center w-12" data-testid={testid}>
    {on
      ? <CircleCheck size={18} className="text-emerald-500" />
      : <CircleSlash size={18} className="text-zinc-300" />}
  </span>
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

          <ModuleAccessSection userId={user.id} headers={headers} />

          <LoginAccessSection userId={user.id} headers={headers} />

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
