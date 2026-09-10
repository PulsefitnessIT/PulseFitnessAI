/**
 * Phase S5 — HR 2.0 tab.
 *
 * Master/detail view: pick a staff member on the left, see their
 * full HR profile + documents + disciplinary + training on the
 * right. The drawer collapses to a single column on mobile.
 *
 * Surface is split into 4 sub-panels stitched together:
 *   • Profile     — emergency contact, address, contract, bank
 *   • Documents   — contracts, IDs, onboarding paperwork (URL-based)
 *   • Disciplinary— incidents + warnings (manager-only writes)
 *   • Training    — learning history (alongside Phase S4 certs)
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import {
  User, FileText, ShieldAlert, GraduationCap, Loader2, Plus, Pencil,
  Trash2, X, Check, Search, AlertTriangle,
  ExternalLink, Briefcase, UserPlus, KeyRound, Copy, LogOut, ClipboardCheck,
  FileSpreadsheet,
} from 'lucide-react';
import { RELATIONSHIP_OPTIONS } from '@/utils/crmDropdowns';
import DatePicker, { formatDDMMYYYY } from '@/components/shared/DatePicker';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const hrPhotoSrc = (u) => (u ? (u.startsWith('/api') ? `${process.env.REACT_APP_BACKEND_URL}${u}` : u) : '');
const maskAccount = (full, last4) => {
  const l4 = last4 || String(full || '').replace(/\s+/g, '').slice(-4);
  return l4 ? `•••• ${l4}` : '••••';
};

async function downloadHrFile(url, headers, fallbackName) {
  try {
    const res = await fetch(url, { headers: { Authorization: headers?.Authorization || '' } });
    if (!res.ok) {
      let msg = 'Download failed';
      try { const j = await res.json(); msg = j.detail || msg; } catch { /* non-JSON */ }
      window.alert(msg); return;
    }
    const cd = res.headers.get('Content-Disposition') || '';
    const m = cd.match(/filename="?([^"]+)"?/);
    const blob = await res.blob();
    const objUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = objUrl; a.download = m ? m[1] : fallbackName; a.click();
    URL.revokeObjectURL(objUrl);
  } catch { window.alert('Download failed'); }
}

function AddStaffDialog({ headers, onClose, onCreated }) {
  const { t } = useTranslation();
  const [roles, setRoles] = useState(['manager']);
  const [form, setForm] = useState({
    full_name: '', email: '', primary_role: 'manager',
    contract_type: 'part_time', hours_per_week: 0, hourly_cost: 0,
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const { data } = await axios.get(`${API}/staffing/roles`, { headers });
        const list = data.all || data.valid || data.platform_defaults || [];
        if (list.length) {
          setRoles(list);
          // Keep the selected role valid — the <select> otherwise *displays* the
          // first option while state holds an invalid value (e.g. "staff"),
          // which the backend then rejects.
          setForm((f) => (list.includes(f.primary_role) ? f : { ...f, primary_role: list[0] }));
        }
      } catch { /* keep defaults */ }
    })();
  }, [headers]);

  const submit = async () => {
    if (!form.full_name.trim()) { setErr(t('staffing.hr_name_required', 'Name is required')); return; }
    setSaving(true); setErr('');
    try {
      const { data } = await axios.post(`${API}/staffing/staff`, form, { headers });
      onCreated(data?.id || data?.staff?.id || null);
      onClose();
    } catch (e) {
      setErr(e?.response?.data?.detail || t('staffing.hr_could_not_add', 'Could not add staff'));
    } finally { setSaving(false); }
  };

  return createPortal((
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[70] p-4"
      onClick={onClose} data-testid="hr-add-staff-backdrop">
      <div className="rounded-2xl border p-5 w-full max-w-md" onClick={(e) => e.stopPropagation()}
        style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
        data-testid="hr-add-staff-dialog">
        <div className="flex items-center justify-between mb-3">
          <div className="text-sm font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{t('staffing.hr_add_staff', 'Add staff')}</div>
          <button type="button" onClick={onClose} data-testid="hr-add-staff-close"><X size={16} style={{ color: 'var(--theme-text-muted)' }} /></button>
        </div>
        <div className="space-y-2">
          <div>
            <label className="block text-[10px] uppercase tracking-wider font-bold mb-1" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_full_name', 'Full name')}</label>
            <input placeholder={t('staffing.hr_name_ph', 'e.g. Jane Doe')} value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              className="w-full rounded-lg px-3 py-2 text-sm border"
              style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
              data-testid="hr-add-staff-name" />
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-wider font-bold mb-1" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_email', 'Email')} <span className="opacity-60 normal-case font-normal">{t('staffing.hr_email_hint', '(optional — links to existing user)')}</span></label>
            <input placeholder="jane@example.com" value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              className="w-full rounded-lg px-3 py-2 text-sm border"
              style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
              data-testid="hr-add-staff-email" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-[10px] uppercase tracking-wider font-bold mb-1" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_job_role', 'Job role')}</label>
              <select value={form.primary_role} onChange={(e) => setForm({ ...form, primary_role: e.target.value })}
                className="w-full rounded-lg px-3 py-2 text-sm border"
                style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                data-testid="hr-add-staff-role">
                {roles.map((r) => <option key={r} value={r}>{humanizeRole(r)}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-wider font-bold mb-1" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_contract_type', 'Contract type')}</label>
              <select value={form.contract_type} onChange={(e) => setForm({ ...form, contract_type: e.target.value })}
                className="w-full rounded-lg px-3 py-2 text-sm border"
                style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                data-testid="hr-add-staff-contract">
                {['full_time', 'part_time', 'permanent', 'fixed_term', 'casual', 'zero_hours', 'contractor', 'self_employed', 'apprentice'].map((c) => <option key={c} value={c}>{contractLabel(c)}</option>)}
              </select>
            </div>
          </div>
          {err && <p className="text-xs text-red-500" data-testid="hr-add-staff-error">{err}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={onClose} className="px-3 py-2 rounded-lg text-xs font-bold border"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid="hr-add-staff-cancel">{t('staffing.hr_cancel', 'Cancel')}</button>
            <button type="button" onClick={submit} disabled={saving}
              className="px-3 py-2 rounded-lg text-xs font-bold inline-flex items-center gap-1.5 disabled:opacity-50"
              style={{ background: 'var(--color-brand-cyan)', color: '#001219' }} data-testid="hr-add-staff-save">
              {saving ? <Loader2 size={12} className="animate-spin" /> : <UserPlus size={12} />} {t('staffing.hr_add_staff', 'Add staff')}
            </button>
          </div>
        </div>
      </div>
    </div>
  ), document.body);
}


const SUB_TABS = [
  { id: 'profile',      labelKey: 'staffing.hr_tab_profile',      labelDefault: 'Profile',      icon: User },
  { id: 'documents',    labelKey: 'staffing.hr_tab_documents',    labelDefault: 'Documents',    icon: FileText },
  { id: 'disciplinary', labelKey: 'staffing.hr_tab_disciplinary', labelDefault: 'Disciplinary', icon: ShieldAlert },
  { id: 'training',     labelKey: 'staffing.hr_tab_training',     labelDefault: 'Training',     icon: GraduationCap },
];

// Unified contract types — must be a superset so a value chosen anywhere
// (Add-staff dialog or profile) always has a matching <option>; otherwise the
// select silently renders "—" and looks unsaved.
const CONTRACT_TYPES = ['', 'full_time', 'part_time', 'permanent', 'fixed_term', 'casual', 'zero_hours', 'contractor', 'self_employed', 'apprentice'];
const contractLabel = (c) => (c ? c.replace(/_/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase()) : '—');

// Stable, module-level HR profile field (context-fed) so typing never remounts
// the input — defining it inside ProfilePanel dropped focus after each keystroke.
const ProfileFieldCtx = createContext(null);
function Field({ label, k, type = 'text', list }) {
  const { form, set, editing, profile } = useContext(ProfileFieldCtx);
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{label}</span>
      {editing ? (
        type === 'date' ? (
          <DatePicker
            value={form[k] || ''}
            onChange={(iso) => set(k, iso || null)}
            placeholder="DD/MM/YYYY"
            inputClassName="h-8 px-1"
            testid={`hr-field-${k}`}
          />
        ) : (
          <input type={type}
            value={form[k] ?? ''}
            onChange={(e) => set(k, e.target.value)}
            list={list}
            className="h-8 rounded-md bg-transparent border px-2 text-sm"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
            data-testid={`hr-field-${k}`} />
        )
      ) : (
        <span className="text-sm" style={{ color: 'var(--theme-text)' }}>
          {type === 'date' ? (formatDDMMYYYY(profile[k]) || '—') : (profile[k] || '—')}
        </span>
      )}
    </div>
  );
}
const RTW_STATUSES = ['', 'verified', 'pending', 'expired'];
const DOC_KINDS = ['contract', 'id', 'onboarding', 'training', 'policy', 'other'];
const SEVERITIES = ['informal', 'verbal', 'written', 'final', 'suspension', 'dismissal'];
const SEVERITY_TINT = {
  informal: '#94A3B8',
  verbal: '#10B981',
  written: '#F59E0B',
  final: '#EF4444',
  suspension: '#B91C1C',
  dismissal: '#7F1D1D',
};

function fmtDate(iso) { return iso ? iso.slice(0, 10) : '—'; }

function humanizeRole(role) {
  if (!role) return '—';
  const ACRONYMS = { hr: 'HR', it: 'IT', crm: 'CRM' };
  if (ACRONYMS[String(role).toLowerCase()]) return ACRONYMS[String(role).toLowerCase()];
  return String(role)
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// One-shot copyable field for the portal-credentials dialog.
function CopyableField({ value, mono, testid }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(value || ''); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard blocked */ }
  };
  return (
    <div className="flex items-center gap-2 rounded-md border px-2 py-1.5" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-bg)' }}>
      <span className={`flex-1 text-sm truncate ${mono ? 'font-mono' : ''}`} style={{ color: 'var(--theme-text)' }} data-testid={testid}>{value || '—'}</span>
      <button type="button" onClick={copy} className="text-[11px] font-semibold inline-flex items-center gap-1 shrink-0" style={{ color: 'var(--color-brand-cyan)' }} data-testid={`${testid}-copy`}>
        {copied ? <Check size={12} /> : <Copy size={12} />} {copied ? t('staffing.hr_copied', 'Copied') : t('staffing.hr_copy', 'Copy')}
      </button>
    </div>
  );
}

// Portal-credentials result dialog (invite link OR temp password).
function CredsDialog({ creds, onClose }) {
  const { t } = useTranslation();
  return createPortal((
    <div className="fixed inset-0 z-[80] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4" data-testid="staff-creds-dialog">
      <div className="w-full max-w-md rounded-2xl p-5 shadow-2xl" style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}>
        <div className="flex items-start justify-between mb-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.14em]" style={{ color: 'var(--color-brand-cyan)' }}>{t('staffing.hr_portal_creds', 'Portal credentials')}</p>
            <h4 className="text-base font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{creds.staffName}</h4>
          </div>
          <button type="button" onClick={onClose} className="opacity-60 hover:opacity-100" data-testid="staff-creds-close" aria-label="Close"><X size={16} /></button>
        </div>
        <p className="text-xs mb-3" style={{ color: 'var(--theme-text-muted)' }}>
          {creds.invite_url
            ? t('staffing.hr_creds_msg_link', 'Share this “set your password” link with the staff member so they can activate their platform login.')
            : creds.email_sent
              ? t('staffing.hr_creds_msg_sent', 'We\u2019ve emailed the temporary password to the staff member. You can also share it below.')
              : t('staffing.hr_creds_msg_share', 'Share the temporary password below with the staff member.')}
          {' '}{t('staffing.hr_creds_msg_change', "They'll be asked to change it on first login.")}
        </p>
        <div className="space-y-2">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_login_email', 'Login email')}</p>
            <CopyableField value={creds.email} testid="staff-creds-email" />
          </div>
          {creds.role && (
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_platform_role', 'Platform role')}</p>
              <p className="text-sm font-semibold capitalize" style={{ color: 'var(--theme-text)' }} data-testid="staff-creds-role">{creds.role}</p>
            </div>
          )}
          {creds.invite_url ? (
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_set_pw_link', 'Set-password link')}</p>
              <CopyableField value={creds.invite_url} testid="staff-creds-invite-url" />
            </div>
          ) : (
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_temp_password', 'Temporary password')}</p>
              <CopyableField value={creds.temp_password} mono testid="staff-creds-temp-password" />
            </div>
          )}
        </div>
        <div className="flex justify-end mt-4">
          <button type="button" onClick={onClose} className="text-xs font-semibold px-3 py-1.5 rounded-full" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="staff-creds-done">
            <Check size={11} className="inline-block mr-1" /> {t('staffing.hr_done', 'Done')}
          </button>
        </div>
      </div>
    </div>
  ), document.body);
}

// ─────────────────────── Profile panel ───────────────────────────

function OffboardingSection({ staffId, headers, staffName, onUpdated }) {
  const [c, setC] = useState(null);
  const [busy, setBusy] = useState(false);
  const [start, setStart] = useState({ last_working_day: '', reason: '' });
  const load = useCallback(() => {
    axios.get(`${API}/staffing/offboarding/${staffId}`, { headers })
      .then((r) => setC(r.data)).catch(() => setC({ exists: false }));
  }, [staffId, headers]);
  useEffect(() => { load(); }, [load]);
  if (!c) return null;
  const kase = c.case;
  const th = { borderColor: 'var(--theme-border)', color: 'var(--theme-text)' };

  const begin = async () => {
    setBusy(true);
    try { await axios.post(`${API}/staffing/offboarding/${staffId}/start`, start, { headers }); load(); }
    finally { setBusy(false); }
  };
  const toggle = async (key, val) => {
    await axios.patch(`${API}/staffing/offboarding/${staffId}`, { checklist: { [key]: val } }, { headers }); load();
  };
  const setField = async (patch) => {
    await axios.patch(`${API}/staffing/offboarding/${staffId}`, patch, { headers }); load();
  };
  const complete = async () => {
    if (!window.confirm(`Complete offboarding for ${staffName}?\n\nThis archives them and revokes their portal + platform login. It cannot be undone from here.`)) return;
    setBusy(true);
    try { await axios.post(`${API}/staffing/offboarding/${staffId}/complete`, {}, { headers }); load(); onUpdated && onUpdated(); }
    catch (e) { window.alert(e.response?.data?.detail || 'Could not complete offboarding'); }
    finally { setBusy(false); }
  };

  const wrap = (children) => (
    <div className="rounded-xl border p-4 mt-2" style={{ borderColor: 'var(--theme-border)' }} data-testid="offboarding-section">
      <div className="flex items-center gap-2 mb-3">
        <LogOut size={15} className="text-rose-500" />
        <p className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>Offboarding / Leaver</p>
      </div>
      {children}
    </div>
  );

  if (kase && kase.status === 'complete') {
    return wrap(
      <div className="flex items-center gap-2 flex-wrap text-sm" data-testid="offboarding-complete">
        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">Left the company</span>
        <span style={{ color: 'var(--theme-text-muted)' }}>Last working day: <b style={{ color: 'var(--theme-text)' }}>{kase.last_working_day || '—'}</b></span>
        {kase.reason && <span style={{ color: 'var(--theme-text-muted)' }}>· {kase.reason}</span>}
        {kase.access_revoked && <span className="text-xs text-emerald-600 font-semibold">· Login revoked ✓</span>}
      </div>,
    );
  }

  if (!kase) {
    return wrap(
      <div className="space-y-3" data-testid="offboarding-start">
        <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>Start the leaver process — record the last working day and reason, then work through the checklist.</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <label className="block"><span className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--theme-text-muted)' }}>Last working day</span>
            <input type="date" value={start.last_working_day} onChange={(e) => setStart((p) => ({ ...p, last_working_day: e.target.value }))}
              className="mt-1 w-full h-8 rounded-md bg-transparent border px-2 text-xs" style={th} data-testid="offboarding-lwd" /></label>
          <label className="block"><span className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--theme-text-muted)' }}>Reason</span>
            <input value={start.reason} onChange={(e) => setStart((p) => ({ ...p, reason: e.target.value }))} placeholder="e.g. Resignation"
              className="mt-1 w-full h-8 rounded-md bg-transparent border px-2 text-xs" style={th} data-testid="offboarding-reason" /></label>
        </div>
        <button type="button" onClick={begin} disabled={busy} data-testid="offboarding-start-btn"
          className="h-8 px-3 rounded-md text-xs font-bold inline-flex items-center gap-1.5 border disabled:opacity-50"
          style={{ borderColor: 'rgba(239,68,68,0.4)', color: '#EF4444' }}>
          {busy ? <Loader2 size={12} className="animate-spin" /> : <LogOut size={12} />} Begin offboarding
        </button>
      </div>,
    );
  }

  const items = kase.checklist || [];
  const doneCount = items.filter((i) => i.done).length;
  return wrap(
    <div className="space-y-3" data-testid="offboarding-inprogress">
      <div className="flex items-center gap-2 flex-wrap text-sm">
        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">In progress · {doneCount}/{items.length} done</span>
        <span style={{ color: 'var(--theme-text-muted)' }}>Last day:</span>
        <input type="date" defaultValue={kase.last_working_day || ''} onBlur={(e) => setField({ last_working_day: e.target.value })}
          className="h-7 rounded-md bg-transparent border px-2 text-xs" style={th} data-testid="offboarding-lwd-edit" />
        <input defaultValue={kase.reason || ''} onBlur={(e) => setField({ reason: e.target.value })} placeholder="Reason"
          className="h-7 rounded-md bg-transparent border px-2 text-xs" style={th} data-testid="offboarding-reason-edit" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
        {items.map((it) => (
          <label key={it.key} className="flex items-center gap-2 text-sm cursor-pointer rounded-md border px-3 py-2" style={{ borderColor: 'var(--theme-border)' }} data-testid={`offboarding-item-${it.key}`}>
            <input type="checkbox" checked={!!it.done} onChange={(e) => toggle(it.key, e.target.checked)} data-testid={`offboarding-check-${it.key}`} />
            <span style={{ color: it.done ? 'var(--theme-text-muted)' : 'var(--theme-text)', textDecoration: it.done ? 'line-through' : 'none' }}>{it.label}</span>
          </label>
        ))}
      </div>
      <button type="button" onClick={complete} disabled={busy} data-testid="offboarding-complete-btn"
        className="h-9 px-4 rounded-md text-sm font-bold inline-flex items-center gap-1.5 disabled:opacity-50"
        style={{ background: '#EF4444', color: '#fff' }}>
        {busy ? <Loader2 size={14} className="animate-spin" /> : <ClipboardCheck size={14} />} Complete offboarding & revoke access
      </button>
      <p className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>Completing archives the record, sets their leaving date and revokes their login. The checklist is a guide — you can complete before every box is ticked.</p>
    </div>,
  );
}

function ProfilePanel({ staffId, headers, isManager, onUpdated, onInvite, inviteBusy, onDelete, departments = [], photoUrl }) {
  const { t } = useTranslation();
  const [profile, setProfile] = useState(null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [sites, setSites] = useState([]);
  const [revealAcct, setRevealAcct] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/staffing/hr/profile/${staffId}`, { headers });
      setProfile(data);
      setForm(data);
    } catch { /* noop */ }
  }, [staffId, headers]);
  useEffect(() => { load(); }, [load]);

  const DEFAULT_ROLES = useMemo(() => ['manager','engineer','technician','sales_manager','administrator','receptionist','supervisor','director','other'], []);
  const [roleOptions, setRoleOptions] = useState(DEFAULT_ROLES);
  const [addingRole, setAddingRole] = useState(false);
  const [newRoleName, setNewRoleName] = useState('');
  const loadRoles = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/staffing/roles`, { headers });
      if (Array.isArray(data?.all) && data.all.length) setRoleOptions(data.all);
    } catch { /* best-effort */ }
  }, [headers]);
  useEffect(() => { loadRoles(); }, [loadRoles]);
  const submitNewRole = async () => {
    const name = (newRoleName || '').trim();
    if (!name) { setAddingRole(false); return; }
    try {
      await axios.post(`${API}/staffing/roles`, { role: name }, { headers });
      setNewRoleName('');
      setAddingRole(false);
      await loadRoles();
      set('primary_role', name);
    } catch (err) {
      window.alert(err.response?.data?.detail || t('staffing.hr_could_not_add_role', 'Could not add role'));
    }
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await axios.get(`${API}/sites`, { headers });
        if (!cancelled) setSites(data?.sites || []);
      } catch { /* manager has no /sites access? leave panel empty */ }
    })();
    return () => { cancelled = true; };
  }, [headers]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const toggleSite = (sid) => {
    setForm((f) => {
      const cur = Array.isArray(f.site_ids) ? f.site_ids : [];
      const next = cur.includes(sid) ? cur.filter((x) => x !== sid) : [...cur, sid];
      return { ...f, site_ids: next };
    });
  };

  const save = async () => {
    setSaving(true);
    try {
      const fields = [
        'address_line1', 'address_line2', 'city', 'postcode', 'country',
        'date_of_birth', 'ni_number', 'contract_type', 'hours_per_week',
        'hire_date', 'termination_date', 'termination_reason',
        'emergency_contact_name', 'emergency_contact_phone', 'emergency_contact_relationship',
        'bank_name', 'bank_sort_code', 'bank_account',
        'right_to_work_status', 'notes',
      ];
      const payload = {};
      fields.forEach((k) => { if (form[k] !== undefined && form[k] !== null) payload[k] = form[k]; });
      if (typeof payload.hours_per_week === 'string') {
        payload.hours_per_week = parseFloat(payload.hours_per_week) || null;
      }
      // HR-profile save is best-effort — a failure here must NOT skip the
      // staff-record save (role / email / department), which is what feeds
      // the sidebar list and filters.
      try {
        await axios.patch(`${API}/staffing/hr/profile/${staffId}`, payload, { headers });
      } catch (profErr) { window.alert(profErr.response?.data?.detail || t('staffing.hr_profile_save_failed', 'Profile details save failed')); }
      const staffPatch = {};
      if (Array.isArray(form.site_ids)) staffPatch.site_ids = form.site_ids;
      if ((form.full_name || '').trim() && (form.full_name || '').trim() !== (profile.full_name || '')) staffPatch.full_name = (form.full_name || '').trim();
      if (form.primary_role && form.primary_role !== profile.primary_role) staffPatch.primary_role = form.primary_role;
      if ((form.email || '') !== (profile.email || '')) staffPatch.email = (form.email || '').trim();
      if ((form.department || '') !== (profile.department || '')) staffPatch.department = form.department || '';
      if (Object.keys(staffPatch).length > 0) {
        await axios.patch(`${API}/staffing/staff/${staffId}`, staffPatch, { headers });
      }
      setEditing(false);
      await load();
      if (onUpdated) await onUpdated();
    } catch (e) { window.alert(e.response?.data?.detail || t('staffing.hr_save_failed', 'Save failed')); }
    setSaving(false);
  };

  if (!profile) {
    return <div className="py-6 inline-flex items-center gap-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}><Loader2 size={14} className="animate-spin" /> {t('staffing.hr_loading', 'Loading…')}</div>;
  }

  return (
    <ProfileFieldCtx.Provider value={{ form, set, editing, profile }}>
    <div className="space-y-4" data-testid="hr-profile-panel">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="h-12 w-12 rounded-full overflow-hidden shrink-0 flex items-center justify-center border" style={{ borderColor: 'var(--theme-border)', background: 'rgba(25,205,255,0.12)' }}>
            {(photoUrl || profile.photo_url)
              ? <img src={hrPhotoSrc(photoUrl || profile.photo_url)} alt="" className="h-full w-full object-cover" data-testid="hr-profile-avatar" />
              : <span className="text-sm font-bold" style={{ color: 'var(--color-brand-cyan)' }}>{(profile.full_name || '?').split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase()}</span>}
          </div>
          <div>
            <p className="text-base font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{profile.full_name}</p>
            <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{humanizeRole(profile.primary_role)} · {profile.email || t('staffing.hr_no_email', 'no email on file')}</p>
          </div>
        </div>
        {isManager && !editing && (
          <div className="flex gap-2">
            <button type="button"
              onClick={() => onInvite && onInvite({ id: staffId, full_name: profile.full_name, email: profile.email, primary_role: profile.primary_role, portal_credentials_issued_at: profile.portal_credentials_issued_at })}
              disabled={!!inviteBusy}
              className="h-8 rounded-full px-3 text-xs font-bold inline-flex items-center gap-1.5 border disabled:opacity-50"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)', background: 'var(--theme-surface)' }}
              data-testid="staff-issue-creds-btn"
              title={(profile.has_login || profile.portal_credentials_issued_at) ? t('staffing.hr_reissue_login', 'Re-issue platform login') : t('staffing.hr_invite_platform', 'Invite this person to the platform login')}>
              {inviteBusy ? <Loader2 size={11} className="animate-spin" /> : <KeyRound size={11} />}
              {(profile.has_login || profile.portal_credentials_issued_at) ? t('staffing.hr_reissue_login_short', 'Re-issue login') : t('staffing.hr_invite_platform_short', 'Invite to platform')}
            </button>
            <button type="button" onClick={() => setEditing(true)}
              className="h-8 rounded-full px-3 text-xs font-bold inline-flex items-center gap-1.5 border"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid="hr-profile-edit">
              <Pencil size={11} /> {t('staffing.hr_edit', 'Edit')}
            </button>
            <button type="button"
              onClick={() => downloadHrFile(`${API}/staffing/staff/${staffId}/employee-file?format=pdf`, headers, `employee-file-${staffId}.pdf`)}
              className="h-8 rounded-full px-3 text-xs font-bold inline-flex items-center gap-1.5 border"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="employee-file-pdf"
              title="Full employee file (PDF) — for audits / SARs">
              <FileText size={11} /> File PDF
            </button>
            <button type="button"
              onClick={() => downloadHrFile(`${API}/staffing/staff/${staffId}/employee-file?format=xlsx`, headers, `employee-file-${staffId}.xlsx`)}
              className="h-8 rounded-full px-3 text-xs font-bold inline-flex items-center gap-1.5 border"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="employee-file-xlsx"
              title="Full employee file (Excel)">
              <FileSpreadsheet size={11} /> File Excel
            </button>
          </div>
        )}
        {editing && (
          <div className="flex gap-2">
            <button type="button" onClick={() => { setEditing(false); setForm(profile); }}
              className="h-8 rounded-full border px-3 text-xs font-bold"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid="hr-profile-cancel">{t('staffing.hr_cancel', 'Cancel')}</button>
            <button type="button" onClick={save} disabled={saving}
              className="h-8 rounded-full px-3 text-xs font-bold inline-flex items-center gap-1.5 disabled:opacity-60"
              style={{ background: 'var(--color-brand-cyan)', color: '#001219' }} data-testid="hr-profile-save">
              {saving ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />} {t('staffing.hr_save', 'Save')}
            </button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3 rounded-xl border p-4"
        style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
        <p className="md:col-span-2 text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: 'var(--color-brand-cyan)' }}>{t('staffing.hr_contact', 'Contact')}</p>
        <div className="flex flex-col gap-1 md:col-span-2">
          <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_full_name', 'Full name')}</span>
          {editing ? (
            <input type="text" value={form.full_name || ''} onChange={(e) => set('full_name', e.target.value)}
              placeholder={t('staffing.hr_name_ph', 'e.g. Jane Doe')}
              className="h-8 rounded-md bg-transparent border px-2 text-sm"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
              data-testid="hr-field-full_name" />
          ) : (
            <span className="text-sm" style={{ color: 'var(--theme-text)' }}>{profile.full_name || '—'}</span>
          )}
          {editing && profile.user_id && (
            <span className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_name_login_note', 'This also updates their platform login display name.')}</span>
          )}
        </div>
        <div className="flex flex-col gap-1 md:col-span-2">
          <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_email', 'Email')}</span>
          {editing ? (
            <input type="email" value={form.email || ''} onChange={(e) => set('email', e.target.value)}
              placeholder="name@example.com"
              className="h-8 rounded-md bg-transparent border px-2 text-sm"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
              data-testid="hr-field-email" />
          ) : (
            <span className="text-sm" style={{ color: 'var(--theme-text)' }}>{profile.email || '—'}</span>
          )}
          {editing && profile.user_id && (
            <span className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_email_login_note', 'This also updates their platform login email.')}</span>
          )}
        </div>
        <Field label={t('staffing.hr_address1', 'Address line 1')} k="address_line1" />
        <Field label={t('staffing.hr_address2', 'Address line 2')} k="address_line2" />
        <Field label={t('staffing.hr_city', 'City')} k="city" />
        <Field label={t('staffing.hr_postcode', 'Postcode')} k="postcode" />
        <Field label={t('staffing.hr_dob', 'Date of birth')} k="date_of_birth" type="date" />

        <p className="md:col-span-2 text-[10px] uppercase tracking-[0.14em] font-bold mt-2" style={{ color: 'var(--color-brand-cyan)' }}>{t('staffing.hr_emergency', 'Emergency contact')}</p>
        <Field label={t('staffing.hr_name', 'Name')}        k="emergency_contact_name" />
        <Field label={t('staffing.hr_phone', 'Phone')}       k="emergency_contact_phone" type="tel" />
        <Field label={t('staffing.hr_relationship', 'Relationship')} k="emergency_contact_relationship" list="hr-relationship-list" />
        <datalist id="hr-relationship-list">
          {RELATIONSHIP_OPTIONS.map((r) => <option key={r} value={r} />)}
        </datalist>

        <p className="md:col-span-2 text-[10px] uppercase tracking-[0.14em] font-bold mt-2" style={{ color: 'var(--color-brand-cyan)' }}>{t('staffing.hr_employment', 'Employment')}</p>
        <div className="flex flex-col gap-1" data-testid="hr-primary-role-field">
          <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_primary_role', 'Primary role')}</span>
          {editing ? (addingRole ? (
            <div className="flex gap-1">
              <input
                autoFocus
                type="text"
                maxLength={60}
                value={newRoleName}
                onChange={(e) => setNewRoleName(e.target.value)}
                placeholder={t('staffing.hr_role_ph', 'e.g. Swim coach')}
                className="flex-1 h-8 rounded-md bg-transparent border px-2 text-sm"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                onKeyDown={(e) => { if (e.key === 'Enter') submitNewRole(); if (e.key === 'Escape') { setAddingRole(false); setNewRoleName(''); } }}
                data-testid="hr-primary-role-new-input"
              />
              <button type="button" onClick={submitNewRole} className="text-xs font-semibold px-2 rounded-md" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="hr-primary-role-new-save">{t('staffing.hr_add', 'Add')}</button>
              <button type="button" onClick={() => { setAddingRole(false); setNewRoleName(''); }} className="text-xs px-2 rounded-md border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid="hr-primary-role-new-cancel">×</button>
            </div>
          ) : (
            <select
              value={form.primary_role || ''}
              onChange={(e) => {
                if (e.target.value === '__add_new__') { setAddingRole(true); return; }
                set('primary_role', e.target.value);
              }}
              className="h-8 rounded-md bg-transparent border px-2 text-sm"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
              data-testid="hr-primary-role"
            >
              {(roleOptions.includes(form.primary_role) || !form.primary_role
                ? roleOptions
                : [form.primary_role, ...roleOptions]
              ).map((r) => <option key={r} value={r}>{humanizeRole(r)}</option>)}
              <option value="__add_new__">{t('staffing.hr_add_new_role', '+ Add new role…')}</option>
            </select>
          )) : (
            <span className="text-sm" style={{ color: 'var(--theme-text)' }}>{humanizeRole(profile.primary_role) || '—'}</span>
          )}
        </div>

        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_contract_type', 'Contract type')}</span>
          {editing ? (
            <select value={form.contract_type || ''} onChange={(e) => set('contract_type', e.target.value || null)}
              className="h-8 rounded-md bg-transparent border px-2 text-sm"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="hr-field-contract_type">
              {(form.contract_type && !CONTRACT_TYPES.includes(form.contract_type)
                ? [...CONTRACT_TYPES, form.contract_type]
                : CONTRACT_TYPES)
                .map((c) => <option key={c || 'none'} value={c || ''}>{contractLabel(c)}</option>)}
            </select>
          ) : (
            <span className="text-sm" style={{ color: 'var(--theme-text)' }}>{profile.contract_type || '—'}</span>
          )}
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_department', 'Department')}</span>
          {editing ? (
            <select value={form.department || ''} onChange={(e) => set('department', e.target.value || null)}
              className="h-8 rounded-md bg-transparent border px-2 text-sm"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="hr-field-department">
              <option value="">{t('staffing.hr_no_department', '— None —')}</option>
              {departments.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          ) : (
            <span className="text-sm" style={{ color: 'var(--theme-text)' }}>{profile.department || '—'}</span>
          )}
        </div>
        <Field label={t('staffing.hr_hours_week', 'Hours / week')} k="hours_per_week" type="number" />
        <Field label={t('staffing.hr_hire_date', 'Hire date')} k="hire_date" type="date" />
        <Field label={t('staffing.hr_term_date', 'Termination date')} k="termination_date" type="date" />

        {sites.length > 1 && (
          <div className="md:col-span-2 mt-2" data-testid="hr-site-allocation-panel">
            <p className="text-[10px] uppercase tracking-[0.14em] font-bold mb-2" style={{ color: 'var(--color-brand-cyan)' }}>{t('staffing.hr_site_alloc', 'Site allocation')}</p>
            {editing ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 rounded-md border p-3" style={{ borderColor: 'var(--theme-border)' }}>
                {sites.map((s) => {
                  const checked = Array.isArray(form.site_ids) && form.site_ids.includes(s.id);
                  return (
                    <label key={s.id} className="inline-flex items-start gap-2 text-sm cursor-pointer" style={{ color: 'var(--theme-text)' }}>
                      <input
                        type="checkbox"
                        checked={!!checked}
                        onChange={() => toggleSite(s.id)}
                        className="mt-0.5 accent-[var(--color-brand-cyan)]"
                        data-testid={`hr-site-allocation-toggle-${s.id}`}
                      />
                      <span className="min-w-0">
                        <span className="block truncate">{s.name || t('staffing.hr_unnamed_site', 'Unnamed site')}</span>
                        <span className="block text-[10px] opacity-60 truncate">{s.address || s.postcode || '—'}</span>
                      </span>
                    </label>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm" style={{ color: 'var(--theme-text)' }} data-testid="hr-site-allocation-readout">
                {(() => {
                  const ids = Array.isArray(profile.site_ids) ? profile.site_ids : [];
                  if (ids.length === 0) return t('staffing.hr_all_sites', 'All sites (no restriction)');
                  return sites.filter((s) => ids.includes(s.id)).map((s) => s.name).filter(Boolean).join(', ') || '—';
                })()}
              </p>
            )}
          </div>
        )}

        <p className="md:col-span-2 text-[10px] uppercase tracking-[0.14em] font-bold mt-2" style={{ color: 'var(--color-brand-cyan)' }}>{t('staffing.hr_rtw', 'Right to work')}</p>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_status', 'Status')}</span>
          {editing ? (
            <select value={form.right_to_work_status || ''} onChange={(e) => set('right_to_work_status', e.target.value || null)}
              className="h-8 rounded-md bg-transparent border px-2 text-sm"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="hr-field-rtw">
              {RTW_STATUSES.map((c) => <option key={c} value={c}>{c || '—'}</option>)}
            </select>
          ) : (
            <span className="text-sm" style={{ color: 'var(--theme-text)' }}>{profile.right_to_work_status || '—'}</span>
          )}
        </div>
        <Field label={t('staffing.hr_ni_number', 'NI number')} k="ni_number" />

        <p className="md:col-span-2 text-[10px] uppercase tracking-[0.14em] font-bold mt-2" style={{ color: 'var(--color-brand-cyan)' }}>{t('staffing.hr_bank', 'Bank (payroll)')}</p>
        <Field label={t('staffing.hr_bank_name', 'Bank name')} k="bank_name" />
        <Field label={t('staffing.hr_sort_code', 'Sort code')} k="bank_sort_code" />
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_account_number', 'Account number')}</span>
          {editing ? (
            <input type="text" inputMode="numeric" value={form.bank_account || ''}
              onChange={(e) => set('bank_account', e.target.value)}
              placeholder={t('staffing.hr_account_ph', 'e.g. 12345678')}
              className="h-8 rounded-md bg-transparent border px-2 text-sm"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
              data-testid="hr-field-bank_account" />
          ) : (
            <span className="text-sm inline-flex items-center gap-2" style={{ color: 'var(--theme-text)' }}>
              <span data-testid="hr-bank-account-value">
                {(profile.bank_account || profile.bank_account_last4)
                  ? (revealAcct && profile.bank_account ? profile.bank_account : maskAccount(profile.bank_account, profile.bank_account_last4))
                  : '—'}
              </span>
              {profile.bank_account && (
                <button type="button" onClick={() => setRevealAcct((v) => !v)} data-testid="hr-bank-account-reveal"
                  className="text-[10px] font-semibold" style={{ color: 'var(--color-brand-cyan)' }}>
                  {revealAcct ? t('staffing.hr_hide', 'Hide') : t('staffing.hr_reveal', 'Reveal')}
                </button>
              )}
            </span>
          )}
        </div>

        <div className="md:col-span-2 mt-2">
          <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_notes', 'Notes')}</span>
          {editing ? (
            <textarea value={form.notes || ''} onChange={(e) => set('notes', e.target.value)} rows={3}
              className="mt-1 w-full rounded-md bg-transparent border px-2 py-1.5 text-sm resize-none"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="hr-field-notes" />
          ) : (
            <p className="text-sm whitespace-pre-wrap" style={{ color: 'var(--theme-text)' }}>{profile.notes || '—'}</p>
          )}
        </div>

        {editing && isManager && onDelete && (
          <div className="md:col-span-2 mt-3 pt-3 border-t flex items-center justify-between gap-3 flex-wrap"
            style={{ borderColor: 'var(--theme-border)' }}>
            <span className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>
              {t('staffing.hr_remove_hint', 'Removes them from the active staff list, rota and payroll. Records are kept.')}
            </span>
            <button type="button" onClick={onDelete}
              className="h-8 rounded-full px-3 text-xs font-bold inline-flex items-center gap-1.5 border shrink-0"
              style={{ borderColor: 'rgba(239,68,68,0.4)', color: '#EF4444' }} data-testid="hr-profile-delete"
              title={t('staffing.hr_remove_staff', 'Remove this person from staff')}>
              <Trash2 size={11} /> {t('staffing.hr_remove', 'Remove staff member')}
            </button>
          </div>
        )}
      </div>
      {isManager && <OffboardingSection staffId={staffId} headers={headers} staffName={profile.full_name} onUpdated={onUpdated} />}
    </div>
    </ProfileFieldCtx.Provider>
  );
}

// ─────────────────────── Generic CRUD list ───────────────────────

function CrudList({ title, items, columns, onAdd, onEdit, onDelete, isManager, emptyText, testId }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-3" data-testid={testId}>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <p className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: 'var(--color-brand-cyan)' }}>{title}</p>
        {isManager && (
          <button type="button" onClick={onAdd}
            className="h-8 rounded-full px-3 text-xs font-bold inline-flex items-center gap-1.5"
            style={{ background: 'var(--color-brand-cyan)', color: '#001219' }}
            data-testid={`${testId}-add`}>
            <Plus size={11} /> {t('staffing.hr_add', 'Add')}
          </button>
        )}
      </div>
      {items.length === 0 ? (
        <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{emptyText}</p>
      ) : (
        <div className="space-y-2">
          {items.map((it) => (
            <div key={it.id} className="rounded-lg border p-3 flex items-start gap-3" style={{ borderColor: 'var(--theme-border)' }} data-testid={`${testId}-row-${it.id}`}>
              <div className="flex-1 min-w-0">
                {columns(it)}
              </div>
              {isManager && (
                <div className="flex gap-1 shrink-0">
                  <button type="button" onClick={() => onEdit(it)} className="w-7 h-7 rounded-full border inline-flex items-center justify-center"
                    style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid={`${testId}-edit-${it.id}`}>
                    <Pencil size={11} />
                  </button>
                  <button type="button" onClick={() => onDelete(it)} className="w-7 h-7 rounded-full border inline-flex items-center justify-center"
                    style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid={`${testId}-delete-${it.id}`}>
                    <Trash2 size={11} />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function MiniDialog({ open, title, fields, initial, onClose, onSubmit, testId }) {
  const { t } = useTranslation();
  const [form, setForm] = useState({});
  useEffect(() => { setForm(initial || {}); }, [initial, open]);
  if (!open) return null;
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const submit = () => {
    for (const f of fields) {
      if (f.required && !form[f.id]) { window.alert(`${f.label} ${t('staffing.hr_is_required', 'is required')}`); return; }
    }
    onSubmit(form);
  };
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-end sm:items-center justify-center p-0 sm:p-4" data-testid={testId}>
      <div className="w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl p-5 space-y-3 max-h-[90vh] overflow-y-auto"
        style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}>
        <div className="flex items-center justify-between">
          <h4 className="text-base font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{title}</h4>
          <button type="button" onClick={onClose} className="w-7 h-7" style={{ color: 'var(--theme-text-muted)' }}><X size={14} /></button>
        </div>
        {fields.map((f) => (
          <div key={f.id} className="space-y-1">
            <label className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>
              {f.label} {f.required && <span style={{ color: '#EF4444' }}>*</span>}
            </label>
            {f.kind === 'select' ? (
              <select value={form[f.id] || ''} onChange={(e) => set(f.id, e.target.value)}
                className="w-full h-9 rounded-md bg-transparent border px-2 text-sm"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid={`${testId}-${f.id}`}>
                {f.options.map((o) => <option key={o} value={o}>{o || '—'}</option>)}
              </select>
            ) : f.kind === 'textarea' ? (
              <textarea value={form[f.id] || ''} onChange={(e) => set(f.id, e.target.value)} rows={3}
                className="w-full rounded-md bg-transparent border px-2 py-1.5 text-sm resize-none"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid={`${testId}-${f.id}`} />
            ) : (
              <input type={f.kind || 'text'} value={form[f.id] || ''} onChange={(e) => set(f.id, e.target.value)}
                className="w-full h-9 rounded-md bg-transparent border px-2 text-sm"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid={`${testId}-${f.id}`} />
            )}
          </div>
        ))}
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onClose} className="h-9 rounded-full border px-4 text-xs font-bold"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>{t('staffing.hr_cancel', 'Cancel')}</button>
          <button type="button" onClick={submit}
            className="h-9 rounded-full px-4 text-xs font-bold inline-flex items-center gap-1.5"
            style={{ background: 'var(--color-brand-cyan)', color: '#001219' }} data-testid={`${testId}-save`}>
            <Check size={11} /> {t('staffing.hr_save', 'Save')}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────── Documents / Disciplinary / Training ────

function DocumentsPanel({ staffId, headers, isManager }) {
  const { t } = useTranslation();
  const [items, setItems] = useState([]);
  const [editing, setEditing] = useState(null);
  const [adding, setAdding] = useState(false);
  const load = useCallback(async () => {
    const { data } = await axios.get(`${API}/staffing/hr/documents`, { headers, params: { staff_id: staffId } });
    setItems(data.documents || []);
  }, [headers, staffId]);
  useEffect(() => { load(); }, [load]);

  const fields = [
    { id: 'name', label: t('staffing.hr_name', 'Name'), required: true },
    { id: 'kind', label: t('staffing.hr_kind', 'Kind'), kind: 'select', options: DOC_KINDS, required: true },
    { id: 'url',  label: t('staffing.hr_url', 'URL'),  required: true },
    { id: 'expires_at', label: t('staffing.hr_expires', 'Expires'), kind: 'date' },
    { id: 'notes', label: t('staffing.hr_notes', 'Notes'), kind: 'textarea' },
  ];
  const create = async (form) => {
    try {
      await axios.post(`${API}/staffing/hr/documents`, { ...form, staff_id: staffId, kind: form.kind || 'contract' }, { headers });
      setAdding(false); load();
    } catch (e) { window.alert(e.response?.data?.detail || t('staffing.hr_save_failed', 'Save failed')); }
  };
  const update = async (form) => {
    try {
      await axios.patch(`${API}/staffing/hr/documents/${form.id}`, form, { headers });
      setEditing(null); load();
    } catch (e) { window.alert(e.response?.data?.detail || t('staffing.hr_save_failed', 'Save failed')); }
  };
  const remove = async (it) => {
    if (!window.confirm(`${t('staffing.hr_delete', 'Delete')} "${it.name}"?`)) return;
    try { await axios.delete(`${API}/staffing/hr/documents/${it.id}`, { headers }); load(); }
    catch (e) { window.alert(e.response?.data?.detail || t('staffing.hr_delete_failed', 'Delete failed')); }
  };

  return (
    <>
      <CrudList title={t('staffing.hr_documents', 'Documents')} items={items} testId="hr-docs"
        emptyText={t('staffing.hr_no_docs', 'No documents on file.')}
        onAdd={() => setAdding(true)} onEdit={setEditing} onDelete={remove} isManager={isManager}
        columns={(it) => (
          <>
            <p className="text-sm font-bold inline-flex items-center gap-1.5" style={{ color: 'var(--theme-text)' }}>
              <FileText size={12} /> {it.name}
              <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ml-1" style={{ background: 'rgba(25,205,255,0.12)', color: 'var(--color-brand-cyan)' }}>{it.kind}</span>
            </p>
            <p className="text-[11px] mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
              {it.expires_at ? `${t('staffing.hr_expires_word', 'Expires')} ${fmtDate(it.expires_at)}` : t('staffing.hr_no_expiry', 'No expiry')}
              {it.url && <a href={it.url} target="_blank" rel="noreferrer" className="ml-2 inline-flex items-center gap-1 underline" data-testid={`hr-docs-link-${it.id}`}><ExternalLink size={10} /> {t('staffing.hr_open', 'open')}</a>}
            </p>
          </>
        )} />
      <MiniDialog open={adding}  title={t('staffing.hr_add_doc', 'Add document')} fields={fields} initial={{ kind: 'contract' }} onClose={() => setAdding(false)}  onSubmit={create} testId="hr-docs-dialog" />
      <MiniDialog open={!!editing} title={t('staffing.hr_edit_doc', 'Edit document')} fields={fields} initial={editing}     onClose={() => setEditing(null)}    onSubmit={update} testId="hr-docs-dialog-edit" />
    </>
  );
}

function DisciplinaryPanel({ staffId, headers, isManager }) {
  const { t } = useTranslation();
  const [items, setItems] = useState([]);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(null);
  const load = useCallback(async () => {
    const { data } = await axios.get(`${API}/staffing/hr/disciplinary`, { headers, params: { staff_id: staffId } });
    setItems(data.records || []);
  }, [headers, staffId]);
  useEffect(() => { load(); }, [load]);

  const fields = [
    { id: 'occurred_at', label: t('staffing.hr_date', 'Date'), kind: 'date', required: true },
    { id: 'severity',    label: t('staffing.hr_severity', 'Severity'), kind: 'select', options: SEVERITIES, required: true },
    { id: 'summary',     label: t('staffing.hr_summary', 'Summary'), kind: 'textarea', required: true },
    { id: 'actions_agreed', label: t('staffing.hr_actions_agreed', 'Actions agreed'), kind: 'textarea' },
    { id: 'follow_up_at', label: t('staffing.hr_follow_up', 'Follow-up date'), kind: 'date' },
    { id: 'manager_note', label: t('staffing.hr_manager_note', 'Manager note (private)'), kind: 'textarea' },
  ];
  const create = async (form) => {
    try {
      await axios.post(`${API}/staffing/hr/disciplinary`, {
        ...form, staff_id: staffId, severity: form.severity || 'verbal',
        confidential: true,
      }, { headers });
      setAdding(false); load();
    } catch (e) { window.alert(e.response?.data?.detail || t('staffing.hr_save_failed', 'Save failed')); }
  };
  const update = async (form) => {
    try { await axios.patch(`${API}/staffing/hr/disciplinary/${form.id}`, form, { headers }); setEditing(null); load(); }
    catch (e) { window.alert(e.response?.data?.detail || t('staffing.hr_save_failed', 'Save failed')); }
  };
  const remove = async (it) => {
    if (!window.confirm(t('staffing.hr_delete_record', 'Delete this record?'))) return;
    try { await axios.delete(`${API}/staffing/hr/disciplinary/${it.id}`, { headers }); load(); }
    catch (e) { window.alert(e.response?.data?.detail || t('staffing.hr_delete_failed', 'Delete failed')); }
  };

  return (
    <>
      <CrudList title={t('staffing.hr_disc_records', 'Disciplinary records')} items={items} testId="hr-disc"
        emptyText={t('staffing.hr_no_disc', 'No disciplinary history — clean slate.')}
        onAdd={() => setAdding(true)} onEdit={setEditing} onDelete={remove} isManager={isManager}
        columns={(it) => {
          const tint = SEVERITY_TINT[it.severity] || '#94A3B8';
          return (
            <>
              <p className="text-sm font-bold inline-flex items-center gap-1.5" style={{ color: 'var(--theme-text)' }}>
                <AlertTriangle size={12} style={{ color: tint }} /> {it.severity?.replace('_', ' ')}
                <span className="text-[10px] ml-1" style={{ color: 'var(--theme-text-muted)' }}>· {fmtDate(it.occurred_at)}</span>
              </p>
              <p className="text-[12px] mt-0.5 whitespace-pre-wrap" style={{ color: 'var(--theme-text)' }}>{it.summary}</p>
              {it.actions_agreed && (
                <p className="text-[11px] mt-1" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_action', 'Action')}: {it.actions_agreed}</p>
              )}
              {it.follow_up_at && <p className="text-[10px] mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_follow_up_label', 'Follow-up')}: {fmtDate(it.follow_up_at)}</p>}
            </>
          );
        }} />
      <MiniDialog open={adding}    title={t('staffing.hr_add_disc', 'Add disciplinary record')} fields={fields} initial={{ severity: 'verbal' }} onClose={() => setAdding(false)} onSubmit={create} testId="hr-disc-dialog" />
      <MiniDialog open={!!editing} title={t('staffing.hr_edit_disc', 'Edit disciplinary record')} fields={fields} initial={editing}                 onClose={() => setEditing(null)}    onSubmit={update} testId="hr-disc-dialog-edit" />
    </>
  );
}

function TrainingPanel({ staffId, headers, isManager }) {
  const { t } = useTranslation();
  const [items, setItems] = useState([]);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(null);
  const load = useCallback(async () => {
    const { data } = await axios.get(`${API}/staffing/hr/training`, { headers, params: { staff_id: staffId } });
    setItems(data.records || []);
  }, [headers, staffId]);
  useEffect(() => { load(); }, [load]);
  const fields = [
    { id: 'course_name', label: t('staffing.hr_course', 'Course'), required: true },
    { id: 'provider',    label: t('staffing.hr_provider', 'Provider') },
    { id: 'completed_at', label: t('staffing.hr_completed', 'Completed'), kind: 'date' },
    { id: 'expires_at',  label: t('staffing.hr_expires', 'Expires'),   kind: 'date' },
    { id: 'score',       label: t('staffing.hr_score', 'Score'),     kind: 'number' },
    { id: 'notes',       label: t('staffing.hr_notes', 'Notes'),     kind: 'textarea' },
  ];
  const create = async (form) => {
    try { await axios.post(`${API}/staffing/hr/training`, { ...form, staff_id: staffId, score: form.score ? parseFloat(form.score) : null }, { headers }); setAdding(false); load(); }
    catch (e) { window.alert(e.response?.data?.detail || t('staffing.hr_save_failed', 'Save failed')); }
  };
  const update = async (form) => {
    try { await axios.patch(`${API}/staffing/hr/training/${form.id}`, { ...form, score: form.score ? parseFloat(form.score) : null }, { headers }); setEditing(null); load(); }
    catch (e) { window.alert(e.response?.data?.detail || t('staffing.hr_save_failed', 'Save failed')); }
  };
  const remove = async (it) => {
    if (!window.confirm(`${t('staffing.hr_delete', 'Delete')} "${it.course_name}"?`)) return;
    try { await axios.delete(`${API}/staffing/hr/training/${it.id}`, { headers }); load(); }
    catch (e) { window.alert(e.response?.data?.detail || t('staffing.hr_delete_failed', 'Delete failed')); }
  };

  return (
    <>
      <CrudList title={t('staffing.hr_training_history', 'Training history')} items={items} testId="hr-training"
        emptyText={t('staffing.hr_no_training', 'No training recorded.')}
        onAdd={() => setAdding(true)} onEdit={setEditing} onDelete={remove} isManager={isManager}
        columns={(it) => (
          <>
            <p className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>{it.course_name}</p>
            <p className="text-[11px] mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
              {it.provider ? `${it.provider} · ` : ''}
              {it.completed_at ? `${t('staffing.hr_done', 'Done')} ${fmtDate(it.completed_at)}` : t('staffing.hr_not_completed', 'Not yet completed')}
              {it.expires_at  ? ` · ${t('staffing.hr_expires_lc', 'expires')} ${fmtDate(it.expires_at)}` : ''}
              {typeof it.score === 'number' ? ` · ${t('staffing.hr_score_lc', 'score')} ${it.score}` : ''}
            </p>
          </>
        )} />
      <MiniDialog open={adding}    title={t('staffing.hr_add_training', 'Add training')} fields={fields} initial={{}}      onClose={() => setAdding(false)} onSubmit={create} testId="hr-training-dialog" />
      <MiniDialog open={!!editing} title={t('staffing.hr_edit_training', 'Edit training')} fields={fields} initial={editing} onClose={() => setEditing(null)}  onSubmit={update} testId="hr-training-dialog-edit" />
    </>
  );
}

// ─────────────────────── Job Roles manager ───────────────────────
function JobRolesModal({ headers, onClose, onChanged }) {
  const { t } = useTranslation();
  const [defaults, setDefaults] = useState([]);
  const [custom, setCustom] = useState([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState('');
  const [editing, setEditing] = useState(null); // { role, value }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/staffing/roles`, { headers });
      setDefaults(data?.platform_defaults || []);
      setCustom(data?.custom || []);
    } catch { /* noop */ }
    setLoading(false);
  }, [headers]);
  useEffect(() => { load(); }, [load]);

  const refresh = async () => { await load(); onChanged?.(); };

  const addRole = async () => {
    const name = adding.trim();
    if (!name) return;
    setBusy(true); setError('');
    try {
      await axios.post(`${API}/staffing/roles`, { role: name }, { headers });
      setAdding('');
      await refresh();
    } catch (err) { setError(err.response?.data?.detail || t('staffing.hr_could_not_add_role', 'Could not add role')); }
    setBusy(false);
  };

  const saveRename = async () => {
    if (!editing) return;
    const next = (editing.value || '').trim();
    if (!next || next === editing.role) { setEditing(null); return; }
    setBusy(true); setError('');
    try {
      await axios.put(`${API}/staffing/roles/${encodeURIComponent(editing.role)}`, { new_name: next }, { headers });
      setEditing(null);
      await refresh();
    } catch (err) { setError(err.response?.data?.detail || t('staffing.hr_could_not_rename', 'Could not rename role')); }
    setBusy(false);
  };

  const removeRole = async (role) => {
    if (!window.confirm(`${t('staffing.hr_delete_role_q', 'Delete the')} "${humanizeRole(role)}" ${t('staffing.hr_delete_role_q2', 'role? Staff already assigned to it keep the label.')}`)) return;
    setBusy(true); setError('');
    try {
      await axios.delete(`${API}/staffing/roles/${encodeURIComponent(role)}`, { headers });
      await refresh();
    } catch (err) { setError(err.response?.data?.detail || t('staffing.hr_could_not_delete_role', 'Could not delete role')); }
    setBusy(false);
  };

  return createPortal((
    <div className="fixed inset-0 z-[300] flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.45)' }} data-testid="job-roles-modal">
      <div className="w-full max-w-md rounded-2xl border shadow-xl flex flex-col max-h-[85vh]"
        style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
        <div className="flex items-center justify-between p-4 border-b" style={{ borderColor: 'var(--theme-border)' }}>
          <div className="inline-flex items-center gap-2">
            <Briefcase size={16} style={{ color: 'var(--color-brand-cyan)' }} />
            <h3 className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>{t('staffing.hr_job_roles', 'Job roles')}</h3>
          </div>
          <button type="button" onClick={onClose} data-testid="job-roles-close" style={{ color: 'var(--theme-text-muted)' }}><X size={16} /></button>
        </div>

        <div className="p-4 space-y-4 overflow-y-auto">
          {error && (
            <p className="text-xs px-2 py-1 rounded-md" style={{ background: 'rgba(239,68,68,0.12)', color: '#EF4444' }} data-testid="job-roles-error">{error}</p>
          )}

          <div className="flex flex-col gap-1">
            <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_add_a_role', 'Add a role')}</span>
            <div className="flex gap-1.5">
              <input
                value={adding}
                onChange={(e) => setAdding(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') addRole(); }}
                placeholder={t('staffing.hr_role_pm_ph', 'e.g. Project Manager')}
                maxLength={60}
                className="flex-1 h-9 rounded-md bg-transparent border px-2 text-sm"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                data-testid="job-roles-add-input"
              />
              <button type="button" onClick={addRole} disabled={busy || !adding.trim()}
                className="h-9 px-3 rounded-md text-xs font-bold inline-flex items-center gap-1 disabled:opacity-50"
                style={{ background: 'var(--color-brand-cyan)', color: '#001219' }} data-testid="job-roles-add-btn">
                <Plus size={13} /> {t('staffing.hr_add', 'Add')}
              </button>
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_custom_roles', 'Your custom roles')}</span>
            {loading ? (
              <p className="text-xs inline-flex items-center gap-1.5" style={{ color: 'var(--theme-text-muted)' }}><Loader2 size={12} className="animate-spin" /> {t('staffing.hr_loading', 'Loading…')}</p>
            ) : custom.length === 0 ? (
              <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_no_custom_roles', 'No custom roles yet. The defaults below cover most companies.')}</p>
            ) : (
              <div className="rounded-lg border divide-y" style={{ borderColor: 'var(--theme-border)' }}>
                {custom.map((r) => (
                  <div key={r} className="flex items-center gap-2 px-2.5 py-2" data-testid={`job-roles-custom-${r}`}>
                    {editing?.role === r ? (
                      <>
                        <input autoFocus value={editing.value} maxLength={60}
                          onChange={(e) => setEditing({ role: r, value: e.target.value })}
                          onKeyDown={(e) => { if (e.key === 'Enter') saveRename(); if (e.key === 'Escape') setEditing(null); }}
                          className="flex-1 h-8 rounded-md bg-transparent border px-2 text-sm"
                          style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                          data-testid="job-roles-rename-input" />
                        <button type="button" onClick={saveRename} disabled={busy} style={{ color: 'var(--color-brand-cyan)' }} data-testid="job-roles-rename-save"><Check size={15} /></button>
                        <button type="button" onClick={() => setEditing(null)} style={{ color: 'var(--theme-text-muted)' }}><X size={15} /></button>
                      </>
                    ) : (
                      <>
                        <span className="flex-1 text-sm" style={{ color: 'var(--theme-text)' }}>{humanizeRole(r)}</span>
                        <button type="button" onClick={() => setEditing({ role: r, value: r })} title={t('staffing.hr_rename', 'Rename')} style={{ color: 'var(--theme-text-muted)' }} data-testid={`job-roles-rename-${r}`}><Pencil size={14} /></button>
                        <button type="button" onClick={() => removeRole(r)} title={t('staffing.hr_delete', 'Delete')} style={{ color: '#EF4444' }} data-testid={`job-roles-delete-${r}`}><Trash2 size={14} /></button>
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex flex-col gap-1">
            <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_builtin_roles', 'Built-in roles')}</span>
            <div className="flex flex-wrap gap-1.5">
              {defaults.map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setAdding(humanizeRole(r))}
                  title={t('staffing.hr_use_role_tip', 'Click to use this role name')}
                  className="text-[11px] px-2 py-1 rounded-full border transition-colors cursor-pointer hover:border-[var(--color-brand-cyan)] hover:text-[var(--color-brand-cyan)]"
                  style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}
                  data-testid={`job-roles-builtin-${r}`}
                >{humanizeRole(r)}</button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  ), document.body);
}


// ─────────────────────── Hub ─────────────────────────────────────
function DetailChangeRequestsPanel({ headers, isManager }) {
  const [reqs, setReqs] = useState([]);
  const [busy, setBusy] = useState(null);
  const load = useCallback(() => {
    axios.get(`${API}/staffing/detail-change-requests?status=pending`, { headers })
      .then((r) => setReqs(r.data?.requests || [])).catch(() => setReqs([]));
  }, [headers]);
  useEffect(() => { load(); }, [load]);
  if (!isManager || reqs.length === 0) return null;

  const act = async (id, action) => {
    let body = {};
    if (action === 'reject') {
      const reason = window.prompt('Reason for rejecting this change request (optional):', '');
      if (reason === null) return;
      body = { reason };
    }
    setBusy(id);
    try {
      await axios.post(`${API}/staffing/detail-change-requests/${id}/${action}`, body, { headers });
      load();
    } catch (e) {
      window.alert(e.response?.data?.detail || 'Could not update request');
    } finally { setBusy(null); }
  };

  return (
    <div className="rounded-xl border p-4" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="detail-change-requests-panel">
      <div className="flex items-center gap-2 mb-3">
        <AlertTriangle size={15} className="text-amber-500" />
        <p className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>Staff detail change requests</p>
        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700" data-testid="detail-requests-count">{reqs.length} pending</span>
      </div>
      <div className="space-y-2">
        {reqs.map((r) => (
          <div key={r.id} className="rounded-lg border p-3" style={{ borderColor: 'var(--theme-border)' }} data-testid={`detail-request-${r.id}`}>
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <p className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>{r.person?.full_name || 'Staff member'}</p>
                <p className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>{r.person?.email}</p>
              </div>
              <div className="flex gap-2 shrink-0">
                <button type="button" disabled={busy === r.id} onClick={() => act(r.id, 'approve')}
                  className="h-8 px-3 rounded-md text-xs font-bold inline-flex items-center gap-1.5 disabled:opacity-50"
                  style={{ background: '#10B981', color: '#00121a' }} data-testid={`detail-approve-${r.id}`}>
                  {busy === r.id ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />} Approve & update
                </button>
                <button type="button" disabled={busy === r.id} onClick={() => act(r.id, 'reject')}
                  className="h-8 px-3 rounded-md text-xs font-bold inline-flex items-center gap-1.5 border disabled:opacity-50"
                  style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid={`detail-reject-${r.id}`}>
                  <X size={12} /> Reject
                </button>
              </div>
            </div>
            <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-2">
              {Object.entries(r.changes || {}).map(([k, c]) => (
                <div key={k} className="rounded-md bg-slate-50 border border-slate-200 px-3 py-2 text-xs">
                  <div className="text-[10px] uppercase tracking-wide text-slate-400">{c.label}</div>
                  <div className="text-slate-500 line-through">{c.old || '—'}</div>
                  <div className="text-slate-800 font-semibold">{c.new}</div>
                </div>
              ))}
            </div>
            {r.note && <p className="mt-2 text-xs italic" style={{ color: 'var(--theme-text-muted)' }}>“{r.note}”</p>}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function HRTab({ headers, isManager }) {
  const { t } = useTranslation();
  const [staffList, setStaffList] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [search, setSearch] = useState('');
  const [sub, setSub] = useState(() => localStorage.getItem('staffing.hr.sub') || 'profile');
  const [loading, setLoading] = useState(true);
  const [rolesOpen, setRolesOpen] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [credsDialog, setCredsDialog] = useState(null);
  const [credsBusy, setCredsBusy] = useState(null);
  const [reconciling, setReconciling] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/staffing/staff`, { headers });
      const list = data.staff || [];
      setStaffList(list);
      if (!activeId && list.length > 0) setActiveId(list[0].id);
    } catch { /* noop */ }
    setLoading(false);
  }, [headers, activeId]);
  useEffect(() => { load(); }, [load]);

  useEffect(() => { localStorage.setItem('staffing.hr.sub', sub); }, [sub]);

  const [departments, setDepartments] = useState([]);
  const [deptFilter, setDeptFilter] = useState('');
  useEffect(() => {
    axios.get(`${API}/staffing/departments`, { headers })
      .then((r) => setDepartments(r.data.departments || [])).catch(() => {});
  }, [headers]);

  // Invite a staff member to the platform login (issues an invite link if they
  // have an email, otherwise a one-shot temp password). Their Staffing job role
  // is cross-synced to the platform login role by the backend.
  const issueCredentials = useCallback(async (s) => {
    if (!s) return;
    if (!window.confirm(t('staffing.hr_invite_confirm', `Invite ${s.full_name} to the platform as "${humanizeRole(s.primary_role || 'staff')}"?`))) return;
    const useLink = s.email
      ? window.confirm(t('staffing.hr_invite_link_q', `Send a "set your password" link to ${s.email}?\n\nOK = email a set-password link\nCancel = generate a temporary password instead`))
      : false;
    setCredsBusy(s.id);
    try {
      const { data } = await axios.post(`${API}/staffing/staff/${s.id}/issue-credentials`,
        { delivery: useLink ? 'reset_link' : 'temp_password' }, { headers });
      setCredsDialog({ ...data, staffName: s.full_name });
      load();
    } catch (err) {
      window.alert(err.response?.data?.detail || t('staffing.hr_creds_failed', 'Could not issue credentials'));
    } finally {
      setCredsBusy(null);
    }
  }, [headers, load, t]);

  const reconcileRoles = useCallback(async () => {
    if (!window.confirm(t('staffing.hr_reconcile_confirm', 'Align every staff login role with their Staffing job role? This fixes mismatches (e.g. an Engineer showing as a sales rep in Master Admin).'))) return;
    setReconciling(true);
    try {
      const { data } = await axios.post(`${API}/staffing/reconcile-roles`, {}, { headers });
      window.alert(t('staffing.hr_reconcile_done', `Done — ${data.updated} of ${data.checked} logins updated to match their job role.`));
      load();
    } catch (e) {
      window.alert(e.response?.data?.detail || t('staffing.hr_reconcile_failed', 'Reconcile failed'));
    } finally {
      setReconciling(false);
    }
  }, [headers, load, t]);

  const removeStaff = useCallback(async (s) => {
    if (!s) return;
    if (!window.confirm(t('staffing.hr_remove_confirm',
      `Remove ${s.full_name} from staff?\n\nThey'll be taken off the active staff list, rota and payroll. Their historical records are kept and this can be reversed by re-adding them.`))) return;
    try {
      await axios.delete(`${API}/staffing/staff/${s.id}`, { headers });
      setActiveId(null);
      await load();
    } catch (e) {
      window.alert(e.response?.data?.detail || t('staffing.hr_remove_failed', 'Could not remove staff member'));
    }
  }, [headers, load, t]);

  const filtered = useMemo(() => {
    let list = staffList;
    if (deptFilter) list = list.filter((s) => (s.department || '') === deptFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter((s) => (s.full_name || '').toLowerCase().includes(q) || (s.email || '').toLowerCase().includes(q));
    }
    return list;
  }, [staffList, search, deptFilter]);

  const active = filtered.find((s) => s.id === activeId) || filtered[0];

  return (
    <div className="space-y-3" data-testid="hr-tab">

      <DetailChangeRequestsPanel headers={headers} isManager={isManager} />

      {isManager && (
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
            {t('staffing.hr_roles_note', 'Roles set in Master Admin pull through automatically — managers can override them per person below.')}
          </p>
          <div className="flex items-center gap-2 shrink-0">
            <button type="button" onClick={reconcileRoles} disabled={reconciling}
              className="h-8 px-3 rounded-md text-xs font-bold inline-flex items-center gap-1.5 border disabled:opacity-50"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
              data-testid="staff-reconcile-roles-btn"
              title={t('staffing.hr_reconcile_title', 'Align every staff login role with their Staffing job role')}>
              {reconciling ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
              {reconciling ? t('staffing.hr_fixing', 'Fixing…') : t('staffing.hr_fix_login_roles', 'Fix login roles')}
            </button>
            <button type="button" onClick={() => setRolesOpen(true)}
              className="h-8 px-3 rounded-md text-xs font-bold inline-flex items-center gap-1.5 border shrink-0"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
              data-testid="hr-manage-roles-btn">
              <Briefcase size={13} /> {t('staffing.hr_manage_roles', 'Manage job roles')}
            </button>
          </div>
        </div>
      )}

      {rolesOpen && (
        <JobRolesModal headers={headers} onClose={() => setRolesOpen(false)} onChanged={load} />
      )}

      {credsDialog && (
        <CredsDialog creds={credsDialog} onClose={() => setCredsDialog(null)} />
      )}

      {showAdd && (
        <AddStaffDialog
          headers={headers}
          onClose={() => setShowAdd(false)}
          onCreated={async (newId) => { await load(); if (newId) setActiveId(newId); }}
        />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-3 rounded-xl border overflow-hidden"
        style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)', minHeight: '600px' }}>
        {/* Staff list */}
        <div className="border-r flex flex-col" style={{ borderColor: 'var(--theme-border)' }}>
          <div className="p-2 border-b flex items-center gap-2" style={{ borderColor: 'var(--theme-border)' }}>
            <div className="relative flex-1">
              <Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 opacity-50" />
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('staffing.hr_search_staff', 'Search staff…')}
                className="w-full h-8 rounded-md bg-transparent border pl-6 pr-2 text-xs"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                data-testid="hr-search" />
            </div>
            {isManager && (
              <button type="button" onClick={() => setShowAdd(true)}
                className="h-8 px-2.5 rounded-md text-xs font-bold inline-flex items-center gap-1 shrink-0"
                style={{ background: 'var(--color-brand-cyan)', color: '#001219' }}
                data-testid="hr-add-staff-btn" title={t('staffing.hr_add_staff', 'Add staff')}>
                <UserPlus size={13} /> {t('staffing.hr_add', 'Add')}
              </button>
            )}
          </div>
          <div className="px-2 pb-2 border-b" style={{ borderColor: 'var(--theme-border)' }}>
            <select value={deptFilter} onChange={(e) => setDeptFilter(e.target.value)}
              className="w-full h-8 rounded-md bg-transparent border px-2 text-xs"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
              data-testid="hr-dept-filter">
              <option value="">{t('staffing.hr_all_departments', 'All departments')}</option>
              {departments.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>
          <div className="flex-1 overflow-y-auto" data-testid="hr-staff-list">
            {loading && (
              <div className="p-3 inline-flex items-center gap-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}>
                <Loader2 size={12} className="animate-spin" /> {t('staffing.hr_loading', 'Loading…')}
              </div>
            )}
            {!loading && filtered.length === 0 && (
              <p className="p-4 text-center text-xs" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_no_staff_match', 'No staff match.')}</p>
            )}
            {filtered.map((s) => {
              const on = s.id === active?.id;
              return (
                <button key={s.id} type="button" onClick={() => setActiveId(s.id)}
                  className="w-full text-left px-3 py-2 border-b transition-colors"
                  style={{
                    background: on ? 'rgba(25,205,255,0.10)' : 'transparent',
                    borderColor: 'var(--theme-border)',
                  }}
                  data-testid={`hr-staff-row-${s.id}`}>
                  <div className="flex items-center gap-2.5">
                    <div className="h-8 w-8 rounded-full overflow-hidden shrink-0 flex items-center justify-center border" style={{ borderColor: 'var(--theme-border)', background: 'rgba(25,205,255,0.12)' }}>
                      {s.photo_url
                        ? <img src={hrPhotoSrc(s.photo_url)} alt="" className="h-full w-full object-cover" data-testid={`hr-staff-avatar-${s.id}`} />
                        : <span className="text-[10px] font-bold" style={{ color: 'var(--color-brand-cyan)' }}>{(s.full_name || '?').split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase()}</span>}
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-bold truncate" style={{ color: 'var(--theme-text)' }}>{s.full_name}</p>
                      <p className="text-[10px] uppercase tracking-wider flex items-center gap-1.5 flex-wrap" style={{ color: 'var(--theme-text-muted)' }}>
                        {humanizeRole(s.primary_role)}
                        {s.department && <span className="normal-case text-[9px] px-1 rounded" style={{ background: 'rgba(25,205,255,0.15)', color: 'var(--color-brand-cyan)' }}>{s.department}</span>}
                      </p>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Detail */}
        <div className="p-4 space-y-3">
          {!active ? (
            <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.hr_pick_staff', 'Pick a staff member.')}</p>
          ) : (
            <>
              <div className="inline-flex rounded-full border overflow-hidden" style={{ borderColor: 'var(--theme-border)' }}>
                {SUB_TABS.map((st) => {
                  const Icon = st.icon;
                  const on = sub === st.id;
                  return (
                    <button key={st.id} type="button" onClick={() => setSub(st.id)}
                      className="h-8 px-3 text-xs font-bold inline-flex items-center gap-1.5"
                      style={{
                        background: on ? 'var(--color-brand-cyan)' : 'transparent',
                        color: on ? '#001219' : 'var(--theme-text-muted)',
                        borderLeft: st.id !== SUB_TABS[0].id ? '1px solid var(--theme-border)' : 'none',
                      }}
                      data-testid={`hr-sub-${st.id}`}>
                      <Icon size={11} /> {t(st.labelKey, st.labelDefault)}
                    </button>
                  );
                })}
              </div>
              {sub === 'profile'      && <ProfilePanel      staffId={active.id} headers={headers} isManager={isManager} onUpdated={load} onInvite={issueCredentials} inviteBusy={credsBusy === active.id} onDelete={() => removeStaff(active)} departments={departments} photoUrl={active.photo_url} />}
              {sub === 'documents'    && <DocumentsPanel    staffId={active.id} headers={headers} isManager={isManager} />}
              {sub === 'disciplinary' && <DisciplinaryPanel staffId={active.id} headers={headers} isManager={isManager} />}
              {sub === 'training'     && <TrainingPanel     staffId={active.id} headers={headers} isManager={isManager} />}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
