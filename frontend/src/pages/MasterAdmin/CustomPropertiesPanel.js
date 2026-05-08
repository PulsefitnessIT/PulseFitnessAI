/**
 * Custom Properties panel (Iter 232) — Master Admin tab.
 *
 * Lets master admins (and operators via the same backend, but reached
 * here from the admin shell) define custom fields on contacts/companies/
 * deals. Once defined, they auto-show up in:
 *   • Audiences rule builder
 *   • Dynamic Lists rule builder
 *   • Form builder (CRM property mapping)
 *
 * Field types: text, number, date, boolean, url, email, select, multi_select.
 * Soft-delete preserves historical data on records.
 */
import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import {
  ListPlus, Plus, Trash2, Pencil, Save, X, Loader2,
  Users, Building2, Briefcase, Database,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

const ENTITY_TABS = [
  { id: 'contact', label: 'Contacts', icon: Users },
  { id: 'company', label: 'Companies', icon: Building2 },
  { id: 'deal',    label: 'Deals',     icon: Briefcase },
];

const FIELD_TYPES = [
  { id: 'text',         label: 'Text' },
  { id: 'number',       label: 'Number' },
  { id: 'date',         label: 'Date' },
  { id: 'boolean',      label: 'Yes / No' },
  { id: 'url',          label: 'URL' },
  { id: 'email',        label: 'Email' },
  { id: 'select',       label: 'Single select' },
  { id: 'multi_select', label: 'Multi-select' },
];

const slugifyKey = (label) =>
  label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 40);

export default function CustomPropertiesPanel() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const headers = React.useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  const [entityType, setEntityType] = useState('contact');
  const [props, setProps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // null | 'new' | row
  const [saving, setSaving] = useState(false);
  const [usage, setUsage] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/api/custom-properties?entity_type=${entityType}`, { headers });
      setProps(r.data.properties || []);
    } finally {
      setLoading(false);
    }
  }, [entityType, headers]);

  useEffect(() => { load(); }, [load]);

  const fetchUsage = async (id) => {
    try {
      const r = await axios.get(`${API}/api/custom-properties/${id}/usage`, { headers });
      setUsage((prev) => ({ ...prev, [id]: r.data.usage }));
    } catch { /* noop */ }
  };

  const archive = async (row) => {
    await fetchUsage(row.id);
    const recs = usage[row.id] ?? '?';
    if (!window.confirm(`Archive "${row.label}"? Used by ${recs} records — historical data is preserved.`)) return;
    try {
      await axios.delete(`${API}/api/custom-properties/${row.id}`, { headers });
      load();
    } catch (e) {
      window.alert(e.response?.data?.detail || 'Archive failed');
    }
  };

  return (
    <div className="space-y-5" data-testid="custom-properties-panel">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-xl font-bold tracking-tight inline-flex items-center gap-2 text-zinc-900">
            <Database size={20} className="text-fuchsia-500" /> Custom Properties
          </h2>
          <p className="text-xs mt-1 text-zinc-500">
            Add custom fields to contacts, companies and deals. Properties show up automatically in audiences, dynamic lists and forms.
          </p>
        </div>
        <button
          onClick={() => setEditing('new')}
          className="px-3 py-2 rounded-md bg-[var(--color-brand-blue)] text-white text-sm font-semibold inline-flex items-center gap-1.5"
          data-testid="custom-prop-new-btn"
        >
          <Plus size={13} /> New property
        </button>
      </div>

      {/* Entity type pill bar */}
      <div className="inline-flex items-center gap-1 rounded-full p-1 bg-zinc-100 border border-zinc-200">
        {ENTITY_TABS.map((t) => {
          const on = entityType === t.id;
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              onClick={() => setEntityType(t.id)}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold inline-flex items-center gap-1.5 ${
                on ? 'bg-white shadow-sm text-zinc-900' : 'text-zinc-500 hover:text-zinc-800'
              }`}
              data-testid={`custom-prop-entity-${t.id}`}
            >
              <Icon size={12} /> {t.label}
            </button>
          );
        })}
      </div>

      {/* List */}
      {loading ? (
        <div className="text-center py-12">
          <Loader2 size={32} className="animate-spin text-[var(--color-brand-blue)] mx-auto" />
        </div>
      ) : props.length === 0 ? (
        <div className="rounded-xl border border-zinc-200 bg-white p-10 text-center" data-testid="custom-prop-empty">
          <ListPlus size={36} className="mx-auto text-zinc-300 mb-3" />
          <p className="text-sm font-medium text-zinc-700">
            No custom properties for {entityType}s yet
          </p>
          <p className="text-xs text-zinc-500 mt-1">Click "New property" to add your first one.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-zinc-200 bg-white overflow-x-auto" data-testid="custom-prop-list">
          <table className="w-full text-sm min-w-[560px]">
            <thead className="text-[10px] uppercase tracking-wider text-zinc-500 border-b border-zinc-200">
              <tr>
                <th className="text-left py-2.5 px-4 font-semibold">Label</th>
                <th className="text-left font-semibold">Key</th>
                <th className="text-left font-semibold">Type</th>
                <th className="text-left font-semibold">Group</th>
                <th className="text-right font-semibold pr-4">&nbsp;</th>
              </tr>
            </thead>
            <tbody>
              {props.map((p) => (
                <tr key={p.id} className="border-b border-zinc-50 last:border-b-0" data-testid={`custom-prop-row-${p.id}`}>
                  <td className="py-2.5 px-4">
                    <p className="font-medium text-zinc-900">{p.label}</p>
                    {p.required && <span className="text-[9px] uppercase tracking-wider text-amber-600 font-bold">Required</span>}
                  </td>
                  <td className="font-mono text-xs text-zinc-500">{p.key}</td>
                  <td className="text-xs text-zinc-700">
                    {FIELD_TYPES.find((t) => t.id === p.field_type)?.label || p.field_type}
                    {(p.field_type === 'select' || p.field_type === 'multi_select') && (
                      <span className="text-[10px] text-zinc-400 ml-1">({(p.options || []).length})</span>
                    )}
                  </td>
                  <td className="text-xs text-zinc-500">{p.group || '—'}</td>
                  <td className="text-right pr-4">
                    <button onClick={() => setEditing(p)} className="p-1 text-zinc-500 hover:bg-zinc-100 rounded" data-testid={`custom-prop-edit-${p.id}`}>
                      <Pencil size={12} />
                    </button>
                    <button onClick={() => archive(p)} className="p-1 text-rose-500 hover:bg-rose-50 rounded ml-1" data-testid={`custom-prop-archive-${p.id}`}>
                      <Trash2 size={12} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing && (
        <PropertyEditor
          headers={headers}
          entityType={entityType}
          row={editing === 'new' ? null : editing}
          onClose={(refresh) => {
            setEditing(null);
            if (refresh) load();
          }}
          saving={saving}
          setSaving={setSaving}
        />
      )}
    </div>
  );
}


function PropertyEditor({ headers, entityType, row, onClose, saving, setSaving }) {
  const isNew = !row;
  const [form, setForm] = useState(() => row || {
    entity_type: entityType, key: '', label: '', field_type: 'text',
    options: [], required: false, group: '', description: '',
  });
  const [error, setError] = useState(null);

  const updateLabel = (label) => {
    if (isNew && !form.key) {
      setForm({ ...form, label, key: slugifyKey(label) });
    } else {
      setForm({ ...form, label });
    }
  };

  const updateOption = (i, key, val) => setForm({
    ...form,
    options: form.options.map((o, idx) => idx === i ? { ...o, [key]: val } : o),
  });
  const addOption = () => setForm({
    ...form,
    options: [...(form.options || []), { value: '', label: '' }],
  });
  const removeOption = (i) => setForm({
    ...form,
    options: form.options.filter((_, idx) => idx !== i),
  });

  const save = async () => {
    setError(null);
    setSaving(true);
    try {
      if (isNew) {
        await axios.post(`${API}/api/custom-properties`, form, { headers });
      } else {
        const update = {
          label: form.label,
          options: form.options,
          required: form.required,
          group: form.group,
          description: form.description,
        };
        await axios.put(`${API}/api/custom-properties/${row.id}`, update, { headers });
      }
      onClose(true);
    } catch (e) {
      setError(e.response?.data?.detail || 'Save failed');
    } finally { setSaving(false); }
  };

  const needsOptions = form.field_type === 'select' || form.field_type === 'multi_select';

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={() => onClose(false)} data-testid="custom-prop-editor">
      <div onClick={(e) => e.stopPropagation()} className="bg-white rounded-xl shadow-2xl border border-zinc-200 max-w-md w-full p-5 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-zinc-900 inline-flex items-center gap-2">
            <Database size={16} className="text-fuchsia-500" />
            {isNew ? 'New custom property' : 'Edit property'}
          </h3>
          <button onClick={() => onClose(false)} className="text-zinc-400 hover:text-zinc-700" data-testid="custom-prop-editor-close">
            <X size={16} />
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-[10px] uppercase tracking-wider font-semibold text-zinc-500">Label</label>
            <input
              value={form.label}
              onChange={(e) => updateLabel(e.target.value)}
              placeholder="Favourite Class"
              className="w-full mt-1 px-3 py-2 border border-zinc-200 rounded-md text-sm bg-white text-zinc-900"
              data-testid="custom-prop-label"
            />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider font-semibold text-zinc-500">Key (immutable after create)</label>
            <input
              value={form.key}
              onChange={(e) => setForm({ ...form, key: slugifyKey(e.target.value) })}
              disabled={!isNew}
              placeholder="favourite_class"
              className="w-full mt-1 px-3 py-2 border border-zinc-200 rounded-md text-sm font-mono bg-white text-zinc-900 disabled:bg-zinc-100 disabled:text-zinc-500"
              data-testid="custom-prop-key"
            />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider font-semibold text-zinc-500">Field type {!isNew && '(immutable)'}</label>
            <select
              value={form.field_type}
              onChange={(e) => setForm({ ...form, field_type: e.target.value })}
              disabled={!isNew}
              className="w-full mt-1 px-3 py-2 border border-zinc-200 rounded-md text-sm bg-white text-zinc-900 disabled:bg-zinc-100 disabled:text-zinc-500"
              data-testid="custom-prop-field-type"
            >
              {FIELD_TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider font-semibold text-zinc-500">Group (optional)</label>
            <input
              value={form.group || ''}
              onChange={(e) => setForm({ ...form, group: e.target.value })}
              placeholder="Preferences"
              className="w-full mt-1 px-3 py-2 border border-zinc-200 rounded-md text-sm bg-white text-zinc-900"
              data-testid="custom-prop-group"
            />
          </div>
          <label className="flex items-center gap-2 text-xs text-zinc-700">
            <input
              type="checkbox"
              checked={form.required || false}
              onChange={(e) => setForm({ ...form, required: e.target.checked })}
              data-testid="custom-prop-required"
            />
            Required when set on a record
          </label>

          {needsOptions && (
            <div>
              <label className="text-[10px] uppercase tracking-wider font-semibold text-zinc-500">Options</label>
              <div className="space-y-1.5 mt-1">
                {(form.options || []).map((o, i) => (
                  <div key={i} className="flex items-center gap-2" data-testid={`custom-prop-option-${i}`}>
                    <input
                      value={o.label || ''}
                      onChange={(e) => updateOption(i, 'label', e.target.value)}
                      placeholder="Display label"
                      className="flex-1 px-2 py-1.5 border border-zinc-200 rounded text-xs bg-white text-zinc-900"
                    />
                    <input
                      value={o.value || ''}
                      onChange={(e) => updateOption(i, 'value', e.target.value)}
                      placeholder="value"
                      className="flex-1 px-2 py-1.5 border border-zinc-200 rounded text-xs font-mono bg-white text-zinc-900"
                    />
                    <button onClick={() => removeOption(i)} className="p-1 text-zinc-400 hover:text-rose-500"><Trash2 size={11}/></button>
                  </div>
                ))}
                <button onClick={addOption} className="inline-flex items-center gap-1 text-xs text-[var(--color-brand-blue)] font-semibold mt-1" data-testid="custom-prop-add-option">
                  <Plus size={11} /> Add option
                </button>
              </div>
            </div>
          )}

          {error && (
            <div className="rounded-md bg-rose-50 border border-rose-200 text-rose-700 text-xs p-2" data-testid="custom-prop-error">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 mt-5 pt-4 border-t border-zinc-200">
          <button onClick={() => onClose(false)} className="px-3 py-2 text-xs font-semibold text-zinc-600">
            Cancel
          </button>
          <button
            onClick={save}
            disabled={saving || !form.label.trim() || !form.key}
            className="px-3 py-2 rounded-md bg-[var(--color-brand-blue)] text-white text-xs font-semibold disabled:opacity-50 inline-flex items-center gap-1.5"
            data-testid="custom-prop-save"
          >
            {saving ? <Loader2 size={11} className="animate-spin"/> : <Save size={11}/>}
            {isNew ? 'Create' : 'Save changes'}
          </button>
        </div>
      </div>
    </div>
  );
}
