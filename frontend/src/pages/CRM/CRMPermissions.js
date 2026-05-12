/**
 * CRMPermissions — iter 215de.
 *
 * Admin/owner-only settings panel for two layered authorisation
 * primitives:
 *   1. Sharing rules (record-level access per role + entity type)
 *   2. Field-level security (which fields each role can NOT see)
 *
 * Backend API: /api/crm/permissions/{sharing-rules,field-perms,effective}.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Shield, EyeOff, Trash2, Plus, Lock } from 'lucide-react';
import Button from '@/components/shared/Button';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('crm_token') || localStorage.getItem('token') || ''}` } });

const ROLES = ['rep', 'sales_rep', 'manager', 'analyst', 'support', 'finance'];
const ACCESS_LABEL = {
  all: 'Full access',
  team: 'Team only (manager hierarchy)',
  owner: 'Own records only',
  none: 'No access',
};

function Section({ title, subtitle, icon: Icon, children, testid }) {
  return (
    <div className="rounded-xl border p-5" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid={testid}>
      <div className="flex items-start gap-3 mb-4">
        <div className="h-9 w-9 rounded-lg flex items-center justify-center" style={{ background: 'var(--color-brand-blue, #1d4ed8)', color: 'white' }}>
          <Icon size={16} />
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-bold tracking-tight" style={{ color: 'var(--theme-text)' }}>{title}</h3>
          {subtitle ? <p className="text-xs mt-0.5 opacity-70">{subtitle}</p> : null}
        </div>
      </div>
      {children}
    </div>
  );
}

function SharingRules({ rules, entityTypes, accessLevels, onChange }) {
  const [draft, setDraft] = useState({ entity_type: 'contact', role: 'sales_rep', access: 'team' });
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    setSaving(true);
    try {
      await axios.put(`${API}/crm/permissions/sharing-rules`, draft, auth());
      toast.success('Rule saved');
      onChange();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Save failed');
    } finally { setSaving(false); }
  };

  const remove = async (r) => {
    if (!window.confirm(`Remove ${r.role} → ${r.entity_type} (${r.access})?`)) return;
    try {
      await axios.delete(`${API}/crm/permissions/sharing-rules?entity_type=${encodeURIComponent(r.entity_type)}&role=${encodeURIComponent(r.role)}`, auth());
      toast.success('Removed');
      onChange();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Remove failed'); }
  };

  return (
    <Section
      title="Sharing rules"
      subtitle="Control which records each role can read. Default for any role without a rule is Team only."
      icon={Shield}
      testid="permissions-sharing-rules"
    >
      <div className="overflow-x-auto -mx-2">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left opacity-60 text-[11px] uppercase tracking-wider">
              <th className="px-2 py-1.5">Role</th>
              <th className="px-2 py-1.5">Entity</th>
              <th className="px-2 py-1.5">Access</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rules.length === 0 ? (
              <tr><td colSpan="4" className="px-2 py-4 opacity-60 text-center">No custom rules — every non-admin defaults to Team-only access.</td></tr>
            ) : null}
            {rules.map((r) => (
              <tr key={`${r.role}-${r.entity_type}`} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`rule-row-${r.role}-${r.entity_type}`}>
                <td className="px-2 py-2 font-semibold">{r.role}</td>
                <td className="px-2 py-2 capitalize">{r.entity_type}</td>
                <td className="px-2 py-2">{ACCESS_LABEL[r.access] || r.access}</td>
                <td className="px-2 py-2 text-right">
                  <Button variant="ghostDestructive" size="iconSm" onClick={() => remove(r)} icon={Trash2} title="Remove" aria-label="Remove" data-testid={`rule-remove-${r.role}-${r.entity_type}`} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 grid grid-cols-1 sm:grid-cols-4 gap-2 items-end">
        <div>
          <label className="text-[10px] font-bold uppercase tracking-wider opacity-60">Role</label>
          <input
            list="roles-list"
            value={draft.role}
            onChange={(e) => setDraft({ ...draft, role: e.target.value })}
            className="mt-1 w-full px-2 py-1.5 rounded-md border bg-transparent text-sm"
            style={{ borderColor: 'var(--theme-border)' }}
            data-testid="rule-role-input"
          />
          <datalist id="roles-list">
            {ROLES.map((r) => <option key={r} value={r} />)}
          </datalist>
        </div>
        <div>
          <label className="text-[10px] font-bold uppercase tracking-wider opacity-60">Entity</label>
          <select value={draft.entity_type} onChange={(e) => setDraft({ ...draft, entity_type: e.target.value })} className="mt-1 w-full px-2 py-1.5 rounded-md border bg-transparent text-sm" style={{ borderColor: 'var(--theme-border)' }} data-testid="rule-entity-select">
            {entityTypes.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <label className="text-[10px] font-bold uppercase tracking-wider opacity-60">Access</label>
          <select value={draft.access} onChange={(e) => setDraft({ ...draft, access: e.target.value })} className="mt-1 w-full px-2 py-1.5 rounded-md border bg-transparent text-sm" style={{ borderColor: 'var(--theme-border)' }} data-testid="rule-access-select">
            {accessLevels.map((a) => <option key={a} value={a}>{ACCESS_LABEL[a] || a}</option>)}
          </select>
        </div>
        <button onClick={submit} disabled={saving} className="px-3 py-2 rounded-md text-sm font-bold text-white inline-flex items-center justify-center gap-1.5" style={{ background: 'var(--color-brand-blue, #1d4ed8)' }} data-testid="rule-save">
          <Plus size={13} /> {saving ? 'Saving…' : 'Save rule'}
        </button>
      </div>
    </Section>
  );
}

function FieldPerms({ perms, entityTypes, onChange }) {
  const [draft, setDraft] = useState({ entity_type: 'contact', role: 'sales_rep', field: '', access: 'hidden' });
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!draft.field.trim()) { toast.error('Enter a field name'); return; }
    setSaving(true);
    try {
      await axios.put(`${API}/crm/permissions/field-perms`, draft, auth());
      toast.success('Field permission saved');
      setDraft({ ...draft, field: '' });
      onChange();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Save failed');
    } finally { setSaving(false); }
  };

  const remove = async (p) => {
    try {
      await axios.delete(`${API}/crm/permissions/field-perms?entity_type=${encodeURIComponent(p.entity_type)}&role=${encodeURIComponent(p.role)}&field=${encodeURIComponent(p.field)}`, auth());
      toast.success('Removed');
      onChange();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Remove failed'); }
  };

  return (
    <Section
      title="Field-level security"
      subtitle="Hide sensitive fields from specific roles (e.g. hide 'notes' from sales_rep). Admins always see everything."
      icon={EyeOff}
      testid="permissions-field-perms"
    >
      <div className="overflow-x-auto -mx-2">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left opacity-60 text-[11px] uppercase tracking-wider">
              <th className="px-2 py-1.5">Role</th>
              <th className="px-2 py-1.5">Entity</th>
              <th className="px-2 py-1.5">Hidden field</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {perms.length === 0 ? (
              <tr><td colSpan="4" className="px-2 py-4 opacity-60 text-center">No field-level rules. All fields visible to every role.</td></tr>
            ) : null}
            {perms.map((p) => (
              <tr key={`${p.role}-${p.entity_type}-${p.field}`} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`field-row-${p.role}-${p.entity_type}-${p.field}`}>
                <td className="px-2 py-2 font-semibold">{p.role}</td>
                <td className="px-2 py-2 capitalize">{p.entity_type}</td>
                <td className="px-2 py-2"><code className="text-xs">{p.field}</code></td>
                <td className="px-2 py-2 text-right">
                  <Button variant="ghostDestructive" size="iconSm" onClick={() => remove(p)} icon={Trash2} title="Remove" aria-label="Remove" data-testid={`field-remove-${p.role}-${p.entity_type}-${p.field}`} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 grid grid-cols-1 sm:grid-cols-4 gap-2 items-end">
        <div>
          <label className="text-[10px] font-bold uppercase tracking-wider opacity-60">Role</label>
          <input
            list="roles-list"
            value={draft.role}
            onChange={(e) => setDraft({ ...draft, role: e.target.value })}
            className="mt-1 w-full px-2 py-1.5 rounded-md border bg-transparent text-sm"
            style={{ borderColor: 'var(--theme-border)' }}
            data-testid="field-role-input"
          />
        </div>
        <div>
          <label className="text-[10px] font-bold uppercase tracking-wider opacity-60">Entity</label>
          <select value={draft.entity_type} onChange={(e) => setDraft({ ...draft, entity_type: e.target.value })} className="mt-1 w-full px-2 py-1.5 rounded-md border bg-transparent text-sm" style={{ borderColor: 'var(--theme-border)' }} data-testid="field-entity-select">
            {entityTypes.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div>
          <label className="text-[10px] font-bold uppercase tracking-wider opacity-60">Field name</label>
          <input value={draft.field} onChange={(e) => setDraft({ ...draft, field: e.target.value })} placeholder="e.g. notes, phone, value" className="mt-1 w-full px-2 py-1.5 rounded-md border bg-transparent text-sm" style={{ borderColor: 'var(--theme-border)' }} data-testid="field-name-input" />
        </div>
        <button onClick={submit} disabled={saving} className="px-3 py-2 rounded-md text-sm font-bold text-white inline-flex items-center justify-center gap-1.5" style={{ background: 'var(--color-brand-blue, #1d4ed8)' }} data-testid="field-save">
          <Plus size={13} /> {saving ? 'Saving…' : 'Hide field'}
        </button>
      </div>
    </Section>
  );
}

export default function CRMPermissions() {
  const [rules, setRules] = useState([]);
  const [perms, setPerms] = useState([]);
  const [meta, setMeta] = useState({ entity_types: [], access_levels: [] });
  const [loading, setLoading] = useState(true);
  const [unauthorised, setUnauthorised] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r1, r2] = await Promise.all([
        axios.get(`${API}/crm/permissions/sharing-rules`, auth()),
        axios.get(`${API}/crm/permissions/field-perms`, auth()),
      ]);
      setRules(r1.data.rules || []);
      setPerms(r2.data.perms || []);
      setMeta({
        entity_types: r1.data.entity_types || [],
        access_levels: r1.data.access_levels || [],
      });
      setUnauthorised(false);
    } catch (e) {
      if (e?.response?.status === 403) setUnauthorised(true);
      else toast.error(e?.response?.data?.detail || 'Failed to load permissions');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const entityTypes = useMemo(() => (meta.entity_types.length ? meta.entity_types : ['contact', 'company', 'opportunity', 'contract']), [meta.entity_types]);
  const accessLevels = useMemo(() => (meta.access_levels.length ? meta.access_levels : ['all', 'team', 'owner', 'none']), [meta.access_levels]);

  if (unauthorised) {
    return (
      <div className="rounded-xl border p-6 text-center" style={{ borderColor: 'var(--theme-border)' }} data-testid="permissions-forbidden">
        <Lock size={20} className="mx-auto mb-2 opacity-50" />
        <p className="text-sm opacity-70">Only admins or owners can manage permissions.</p>
      </div>
    );
  }
  if (loading) {
    return <p className="text-sm opacity-60" data-testid="permissions-loading">Loading permissions…</p>;
  }

  return (
    <div className="space-y-5" data-testid="crm-permissions-page">
      <SharingRules rules={rules} entityTypes={entityTypes} accessLevels={accessLevels} onChange={load} />
      <FieldPerms perms={perms} entityTypes={entityTypes} onChange={load} />
    </div>
  );
}
