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
import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import {
  User, FileText, ShieldAlert, GraduationCap, Loader2, Plus, Pencil,
  Trash2, X, Check, Search, AlertTriangle,
  ExternalLink, Briefcase, UserPlus,
} from 'lucide-react';
import { RELATIONSHIP_OPTIONS } from '@/utils/crmDropdowns';
import DatePicker, { formatDDMMYYYY } from '@/components/shared/DatePicker';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function AddStaffDialog({ headers, onClose, onCreated }) {
  const { t } = useTranslation();
  const [roles, setRoles] = useState(['manager', 'staff']);
  const [form, setForm] = useState({
    full_name: '', email: '', primary_role: 'staff',
    contract_type: 'part_time', hours_per_week: 0, hourly_cost: 0,
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const { data } = await axios.get(`${API}/staffing/roles`, { headers });
        const list = data.all || data.valid || data.platform_defaults || [];
        if (list.length) setRoles(list);
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
                {['full_time', 'part_time', 'casual', 'contractor'].map((c) => <option key={c}>{c}</option>)}
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

const CONTRACT_TYPES = ['', 'permanent', 'fixed_term', 'casual', 'zero_hours', 'self_employed', 'apprentice'];
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
  return String(role)
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// ─────────────────────── Profile panel ───────────────────────────

function ProfilePanel({ staffId, headers, isManager, onUpdated }) {
  const { t } = useTranslation();
  const [profile, setProfile] = useState(null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [sites, setSites] = useState([]);

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
        'bank_name', 'bank_sort_code', 'bank_account_last4',
        'right_to_work_status', 'notes',
      ];
      const payload = {};
      fields.forEach((k) => { if (form[k] !== undefined && form[k] !== null) payload[k] = form[k]; });
      if (typeof payload.hours_per_week === 'string') {
        payload.hours_per_week = parseFloat(payload.hours_per_week) || null;
      }
      await axios.patch(`${API}/staffing/hr/profile/${staffId}`, payload, { headers });
      const staffPatch = {};
      if (Array.isArray(form.site_ids)) staffPatch.site_ids = form.site_ids;
      if (form.primary_role && form.primary_role !== profile.primary_role) staffPatch.primary_role = form.primary_role;
      if (Object.keys(staffPatch).length > 0) {
        try {
          await axios.patch(`${API}/staffing/staff/${staffId}`, staffPatch, { headers });
        } catch (siteErr) { window.alert(siteErr.response?.data?.detail || t('staffing.hr_role_site_save_failed', 'Role / site allocation save failed')); }
      }
      setEditing(false);
      load();
      onUpdated && onUpdated();
    } catch (e) { window.alert(e.response?.data?.detail || t('staffing.hr_save_failed', 'Save failed')); }
    setSaving(false);
  };

  if (!profile) {
    return <div className="py-6 inline-flex items-center gap-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}><Loader2 size={14} className="animate-spin" /> {t('staffing.hr_loading', 'Loading…')}</div>;
  }

  const Field = ({ label, k, type = 'text', list }) => (
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
            value={form[k] || ''}
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

  return (
    <div className="space-y-4" data-testid="hr-profile-panel">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <p className="text-base font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{profile.full_name}</p>
          <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{humanizeRole(profile.primary_role)} · {profile.email || t('staffing.hr_no_email', 'no email on file')}</p>
        </div>
        {isManager && !editing && (
          <button type="button" onClick={() => setEditing(true)}
            className="h-8 rounded-full px-3 text-xs font-bold inline-flex items-center gap-1.5 border"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid="hr-profile-edit">
            <Pencil size={11} /> {t('staffing.hr_edit', 'Edit')}
          </button>
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
              {CONTRACT_TYPES.map((c) => <option key={c} value={c}>{c || '—'}</option>)}
            </select>
          ) : (
            <span className="text-sm" style={{ color: 'var(--theme-text)' }}>{profile.contract_type || '—'}</span>
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
        <Field label={t('staffing.hr_account_last4', 'Account last 4')} k="bank_account_last4" />

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
      </div>
    </div>
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

  return (
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
                <span key={r} className="text-[11px] px-2 py-1 rounded-full border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>{humanizeRole(r)}</span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}


// ─────────────────────── Hub ─────────────────────────────────────
export default function HRTab({ headers, isManager }) {
  const { t } = useTranslation();
  const [staffList, setStaffList] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [search, setSearch] = useState('');
  const [sub, setSub] = useState(() => localStorage.getItem('staffing.hr.sub') || 'profile');
  const [loading, setLoading] = useState(true);
  const [rolesOpen, setRolesOpen] = useState(false);
  const [showAdd, setShowAdd] = useState(false);

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

  const filtered = useMemo(() => {
    if (!search.trim()) return staffList;
    const q = search.toLowerCase();
    return staffList.filter((s) => (s.full_name || '').toLowerCase().includes(q) || (s.email || '').toLowerCase().includes(q));
  }, [staffList, search]);

  const active = filtered.find((s) => s.id === activeId) || filtered[0];

  return (
    <div className="space-y-3" data-testid="hr-tab">

      {isManager && (
        <div className="flex items-center justify-between">
          <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
            {t('staffing.hr_roles_note', 'Roles set in Master Admin pull through automatically — managers can override them per person below.')}
          </p>
          <button type="button" onClick={() => setRolesOpen(true)}
            className="h-8 px-3 rounded-md text-xs font-bold inline-flex items-center gap-1.5 border shrink-0"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
            data-testid="hr-manage-roles-btn">
            <Briefcase size={13} /> {t('staffing.hr_manage_roles', 'Manage job roles')}
          </button>
        </div>
      )}

      {rolesOpen && (
        <JobRolesModal headers={headers} onClose={() => setRolesOpen(false)} onChanged={load} />
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
                  <p className="text-sm font-bold truncate" style={{ color: 'var(--theme-text)' }}>{s.full_name}</p>
                  <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{humanizeRole(s.primary_role)}</p>
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
              {sub === 'profile'      && <ProfilePanel      staffId={active.id} headers={headers} isManager={isManager} onUpdated={load} />}
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
