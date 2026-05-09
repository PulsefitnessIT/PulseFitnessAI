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
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  User, FileText, ShieldAlert, GraduationCap, Loader2, Plus, Pencil,
  Trash2, X, Check, Search, Calendar as CalIcon, Phone, MapPin, AlertTriangle,
  ExternalLink,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SUB_TABS = [
  { id: 'profile',      label: 'Profile',      icon: User },
  { id: 'documents',    label: 'Documents',    icon: FileText },
  { id: 'disciplinary', label: 'Disciplinary', icon: ShieldAlert },
  { id: 'training',     label: 'Training',     icon: GraduationCap },
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

// ─────────────────────── Profile panel ───────────────────────────

function ProfilePanel({ staffId, headers, isManager, onUpdated }) {
  const [profile, setProfile] = useState(null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/staffing/hr/profile/${staffId}`, { headers });
      setProfile(data);
      setForm(data);
    } catch { /* noop */ }
  }, [staffId, headers]);
  useEffect(() => { load(); }, [load]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

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
      setEditing(false);
      load();
      onUpdated && onUpdated();
    } catch (e) { window.alert(e.response?.data?.detail || 'Save failed'); }
    setSaving(false);
  };

  if (!profile) {
    return <div className="py-6 inline-flex items-center gap-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}><Loader2 size={14} className="animate-spin" /> Loading…</div>;
  }

  const Field = ({ label, k, type = 'text' }) => (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{label}</span>
      {editing ? (
        <input type={type}
          value={form[k] || ''}
          onChange={(e) => set(k, e.target.value)}
          className="h-8 rounded-md bg-transparent border px-2 text-sm"
          style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
          data-testid={`hr-field-${k}`} />
      ) : (
        <span className="text-sm" style={{ color: 'var(--theme-text)' }}>{profile[k] || '—'}</span>
      )}
    </div>
  );

  return (
    <div className="space-y-4" data-testid="hr-profile-panel">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <p className="text-base font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{profile.full_name}</p>
          <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{profile.primary_role} · {profile.email || 'no email on file'}</p>
        </div>
        {isManager && !editing && (
          <button type="button" onClick={() => setEditing(true)}
            className="h-8 rounded-full px-3 text-xs font-bold inline-flex items-center gap-1.5 border"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid="hr-profile-edit">
            <Pencil size={11} /> Edit
          </button>
        )}
        {editing && (
          <div className="flex gap-2">
            <button type="button" onClick={() => { setEditing(false); setForm(profile); }}
              className="h-8 rounded-full border px-3 text-xs font-bold"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid="hr-profile-cancel">Cancel</button>
            <button type="button" onClick={save} disabled={saving}
              className="h-8 rounded-full px-3 text-xs font-bold inline-flex items-center gap-1.5 disabled:opacity-60"
              style={{ background: 'var(--color-brand-cyan)', color: '#001219' }} data-testid="hr-profile-save">
              {saving ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />} Save
            </button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3 rounded-xl border p-4"
        style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
        <p className="md:col-span-2 text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: 'var(--color-brand-cyan)' }}>Contact</p>
        <Field label="Address line 1" k="address_line1" />
        <Field label="Address line 2" k="address_line2" />
        <Field label="City" k="city" />
        <Field label="Postcode" k="postcode" />
        <Field label="Date of birth" k="date_of_birth" type="date" />

        <p className="md:col-span-2 text-[10px] uppercase tracking-[0.14em] font-bold mt-2" style={{ color: 'var(--color-brand-cyan)' }}>Emergency contact</p>
        <Field label="Name"        k="emergency_contact_name" />
        <Field label="Phone"       k="emergency_contact_phone" type="tel" />
        <Field label="Relationship" k="emergency_contact_relationship" />

        <p className="md:col-span-2 text-[10px] uppercase tracking-[0.14em] font-bold mt-2" style={{ color: 'var(--color-brand-cyan)' }}>Employment</p>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>Contract type</span>
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
        <Field label="Hours / week" k="hours_per_week" type="number" />
        <Field label="Hire date" k="hire_date" type="date" />
        <Field label="Termination date" k="termination_date" type="date" />

        <p className="md:col-span-2 text-[10px] uppercase tracking-[0.14em] font-bold mt-2" style={{ color: 'var(--color-brand-cyan)' }}>Right to work</p>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>Status</span>
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
        <Field label="NI number" k="ni_number" />

        <p className="md:col-span-2 text-[10px] uppercase tracking-[0.14em] font-bold mt-2" style={{ color: 'var(--color-brand-cyan)' }}>Bank (payroll)</p>
        <Field label="Bank name" k="bank_name" />
        <Field label="Sort code" k="bank_sort_code" />
        <Field label="Account last 4" k="bank_account_last4" />

        <div className="md:col-span-2 mt-2">
          <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>Notes</span>
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
  return (
    <div className="space-y-3" data-testid={testId}>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <p className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: 'var(--color-brand-cyan)' }}>{title}</p>
        {isManager && (
          <button type="button" onClick={onAdd}
            className="h-8 rounded-full px-3 text-xs font-bold inline-flex items-center gap-1.5"
            style={{ background: 'var(--color-brand-cyan)', color: '#001219' }}
            data-testid={`${testId}-add`}>
            <Plus size={11} /> Add
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
  const [form, setForm] = useState({});
  useEffect(() => { setForm(initial || {}); }, [initial, open]);
  if (!open) return null;
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const submit = () => {
    for (const f of fields) {
      if (f.required && !form[f.id]) { window.alert(`${f.label} is required`); return; }
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
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>Cancel</button>
          <button type="button" onClick={submit}
            className="h-9 rounded-full px-4 text-xs font-bold inline-flex items-center gap-1.5"
            style={{ background: 'var(--color-brand-cyan)', color: '#001219' }} data-testid={`${testId}-save`}>
            <Check size={11} /> Save
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────── Documents / Disciplinary / Training ────

function DocumentsPanel({ staffId, headers, isManager }) {
  const [items, setItems] = useState([]);
  const [editing, setEditing] = useState(null);
  const [adding, setAdding] = useState(false);
  const load = useCallback(async () => {
    const { data } = await axios.get(`${API}/staffing/hr/documents`, { headers, params: { staff_id: staffId } });
    setItems(data.documents || []);
  }, [headers, staffId]);
  useEffect(() => { load(); }, [load]);

  const fields = [
    { id: 'name', label: 'Name', required: true },
    { id: 'kind', label: 'Kind', kind: 'select', options: DOC_KINDS, required: true },
    { id: 'url',  label: 'URL',  required: true },
    { id: 'expires_at', label: 'Expires', kind: 'date' },
    { id: 'notes', label: 'Notes', kind: 'textarea' },
  ];
  const create = async (form) => {
    try {
      await axios.post(`${API}/staffing/hr/documents`, { ...form, staff_id: staffId, kind: form.kind || 'contract' }, { headers });
      setAdding(false); load();
    } catch (e) { window.alert(e.response?.data?.detail || 'Save failed'); }
  };
  const update = async (form) => {
    try {
      await axios.patch(`${API}/staffing/hr/documents/${form.id}`, form, { headers });
      setEditing(null); load();
    } catch (e) { window.alert(e.response?.data?.detail || 'Save failed'); }
  };
  const remove = async (it) => {
    if (!window.confirm(`Delete "${it.name}"?`)) return;
    try { await axios.delete(`${API}/staffing/hr/documents/${it.id}`, { headers }); load(); }
    catch (e) { window.alert(e.response?.data?.detail || 'Delete failed'); }
  };

  return (
    <>
      <CrudList title="Documents" items={items} testId="hr-docs"
        emptyText="No documents on file."
        onAdd={() => setAdding(true)} onEdit={setEditing} onDelete={remove} isManager={isManager}
        columns={(it) => (
          <>
            <p className="text-sm font-bold inline-flex items-center gap-1.5" style={{ color: 'var(--theme-text)' }}>
              <FileText size={12} /> {it.name}
              <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ml-1" style={{ background: 'rgba(25,205,255,0.12)', color: 'var(--color-brand-cyan)' }}>{it.kind}</span>
            </p>
            <p className="text-[11px] mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
              {it.expires_at ? `Expires ${fmtDate(it.expires_at)}` : 'No expiry'}
              {it.url && <a href={it.url} target="_blank" rel="noreferrer" className="ml-2 inline-flex items-center gap-1 underline" data-testid={`hr-docs-link-${it.id}`}><ExternalLink size={10} /> open</a>}
            </p>
          </>
        )} />
      <MiniDialog open={adding}  title="Add document" fields={fields} initial={{ kind: 'contract' }} onClose={() => setAdding(false)}  onSubmit={create} testId="hr-docs-dialog" />
      <MiniDialog open={!!editing} title="Edit document" fields={fields} initial={editing}     onClose={() => setEditing(null)}    onSubmit={update} testId="hr-docs-dialog-edit" />
    </>
  );
}

function DisciplinaryPanel({ staffId, headers, isManager }) {
  const [items, setItems] = useState([]);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(null);
  const load = useCallback(async () => {
    const { data } = await axios.get(`${API}/staffing/hr/disciplinary`, { headers, params: { staff_id: staffId } });
    setItems(data.records || []);
  }, [headers, staffId]);
  useEffect(() => { load(); }, [load]);

  const fields = [
    { id: 'occurred_at', label: 'Date', kind: 'date', required: true },
    { id: 'severity',    label: 'Severity', kind: 'select', options: SEVERITIES, required: true },
    { id: 'summary',     label: 'Summary', kind: 'textarea', required: true },
    { id: 'actions_agreed', label: 'Actions agreed', kind: 'textarea' },
    { id: 'follow_up_at', label: 'Follow-up date', kind: 'date' },
    { id: 'manager_note', label: 'Manager note (private)', kind: 'textarea' },
  ];
  const create = async (form) => {
    try {
      await axios.post(`${API}/staffing/hr/disciplinary`, {
        ...form, staff_id: staffId, severity: form.severity || 'verbal',
        confidential: true,
      }, { headers });
      setAdding(false); load();
    } catch (e) { window.alert(e.response?.data?.detail || 'Save failed'); }
  };
  const update = async (form) => {
    try { await axios.patch(`${API}/staffing/hr/disciplinary/${form.id}`, form, { headers }); setEditing(null); load(); }
    catch (e) { window.alert(e.response?.data?.detail || 'Save failed'); }
  };
  const remove = async (it) => {
    if (!window.confirm('Delete this record?')) return;
    try { await axios.delete(`${API}/staffing/hr/disciplinary/${it.id}`, { headers }); load(); }
    catch (e) { window.alert(e.response?.data?.detail || 'Delete failed'); }
  };

  return (
    <>
      <CrudList title="Disciplinary records" items={items} testId="hr-disc"
        emptyText="No disciplinary history — clean slate."
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
                <p className="text-[11px] mt-1" style={{ color: 'var(--theme-text-muted)' }}>Action: {it.actions_agreed}</p>
              )}
              {it.follow_up_at && <p className="text-[10px] mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>Follow-up: {fmtDate(it.follow_up_at)}</p>}
            </>
          );
        }} />
      <MiniDialog open={adding}    title="Add disciplinary record" fields={fields} initial={{ severity: 'verbal' }} onClose={() => setAdding(false)} onSubmit={create} testId="hr-disc-dialog" />
      <MiniDialog open={!!editing} title="Edit disciplinary record" fields={fields} initial={editing}                 onClose={() => setEditing(null)}    onSubmit={update} testId="hr-disc-dialog-edit" />
    </>
  );
}

function TrainingPanel({ staffId, headers, isManager }) {
  const [items, setItems] = useState([]);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(null);
  const load = useCallback(async () => {
    const { data } = await axios.get(`${API}/staffing/hr/training`, { headers, params: { staff_id: staffId } });
    setItems(data.records || []);
  }, [headers, staffId]);
  useEffect(() => { load(); }, [load]);
  const fields = [
    { id: 'course_name', label: 'Course', required: true },
    { id: 'provider',    label: 'Provider' },
    { id: 'completed_at', label: 'Completed', kind: 'date' },
    { id: 'expires_at',  label: 'Expires',   kind: 'date' },
    { id: 'score',       label: 'Score',     kind: 'number' },
    { id: 'notes',       label: 'Notes',     kind: 'textarea' },
  ];
  const create = async (form) => {
    try { await axios.post(`${API}/staffing/hr/training`, { ...form, staff_id: staffId, score: form.score ? parseFloat(form.score) : null }, { headers }); setAdding(false); load(); }
    catch (e) { window.alert(e.response?.data?.detail || 'Save failed'); }
  };
  const update = async (form) => {
    try { await axios.patch(`${API}/staffing/hr/training/${form.id}`, { ...form, score: form.score ? parseFloat(form.score) : null }, { headers }); setEditing(null); load(); }
    catch (e) { window.alert(e.response?.data?.detail || 'Save failed'); }
  };
  const remove = async (it) => {
    if (!window.confirm(`Delete "${it.course_name}"?`)) return;
    try { await axios.delete(`${API}/staffing/hr/training/${it.id}`, { headers }); load(); }
    catch (e) { window.alert(e.response?.data?.detail || 'Delete failed'); }
  };

  return (
    <>
      <CrudList title="Training history" items={items} testId="hr-training"
        emptyText="No training recorded."
        onAdd={() => setAdding(true)} onEdit={setEditing} onDelete={remove} isManager={isManager}
        columns={(it) => (
          <>
            <p className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>{it.course_name}</p>
            <p className="text-[11px] mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
              {it.provider ? `${it.provider} · ` : ''}
              {it.completed_at ? `Done ${fmtDate(it.completed_at)}` : 'Not yet completed'}
              {it.expires_at  ? ` · expires ${fmtDate(it.expires_at)}` : ''}
              {typeof it.score === 'number' ? ` · score ${it.score}` : ''}
            </p>
          </>
        )} />
      <MiniDialog open={adding}    title="Add training" fields={fields} initial={{}}      onClose={() => setAdding(false)} onSubmit={create} testId="hr-training-dialog" />
      <MiniDialog open={!!editing} title="Edit training" fields={fields} initial={editing} onClose={() => setEditing(null)}  onSubmit={update} testId="hr-training-dialog-edit" />
    </>
  );
}

// ─────────────────────── Hub ─────────────────────────────────────

export default function HRTab({ headers, isManager }) {
  const [staffList, setStaffList] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [search, setSearch] = useState('');
  const [sub, setSub] = useState(() => localStorage.getItem('staffing.hr.sub') || 'profile');
  const [loading, setLoading] = useState(true);

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
      <div className="flex items-center gap-2">
        <User size={14} style={{ color: 'var(--color-brand-cyan)' }} />
        <p className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: 'var(--color-brand-cyan)' }}>Phase S5 · HR · Documents · Disciplinary · Training</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-3 rounded-xl border overflow-hidden"
        style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)', minHeight: '600px' }}>
        {/* Staff list */}
        <div className="border-r flex flex-col" style={{ borderColor: 'var(--theme-border)' }}>
          <div className="p-2 border-b" style={{ borderColor: 'var(--theme-border)' }}>
            <div className="relative">
              <Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 opacity-50" />
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search staff…"
                className="w-full h-8 rounded-md bg-transparent border pl-6 pr-2 text-xs"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                data-testid="hr-search" />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto" data-testid="hr-staff-list">
            {loading && (
              <div className="p-3 inline-flex items-center gap-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}>
                <Loader2 size={12} className="animate-spin" /> Loading…
              </div>
            )}
            {!loading && filtered.length === 0 && (
              <p className="p-4 text-center text-xs" style={{ color: 'var(--theme-text-muted)' }}>No staff match.</p>
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
                  <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{s.primary_role}</p>
                </button>
              );
            })}
          </div>
        </div>

        {/* Detail */}
        <div className="p-4 space-y-3">
          {!active ? (
            <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Pick a staff member.</p>
          ) : (
            <>
              <div className="inline-flex rounded-full border overflow-hidden" style={{ borderColor: 'var(--theme-border)' }}>
                {SUB_TABS.map((t) => {
                  const Icon = t.icon;
                  const on = sub === t.id;
                  return (
                    <button key={t.id} type="button" onClick={() => setSub(t.id)}
                      className="h-8 px-3 text-xs font-bold inline-flex items-center gap-1.5"
                      style={{
                        background: on ? 'var(--color-brand-cyan)' : 'transparent',
                        color: on ? '#001219' : 'var(--theme-text-muted)',
                        borderLeft: t.id !== SUB_TABS[0].id ? '1px solid var(--theme-border)' : 'none',
                      }}
                      data-testid={`hr-sub-${t.id}`}>
                      <Icon size={11} /> {t.label}
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
