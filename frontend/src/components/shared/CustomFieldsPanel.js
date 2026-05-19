/**
 * CustomFieldsPanel — Iter 235
 *
 * Renders the current org's custom contact (or company / deal) properties
 * as type-aware viewers/editors directly on the entity's detail page.
 *
 * Usage:
 *   <CustomFieldsPanel
 *     entityType="contact"
 *     entityId={contactId}
 *     values={contact.custom_fields || {}}
 *     onSave={(patch) => putContact({ custom_fields: { ...current, ...patch } })}
 *   />
 *
 * Why a single component:
 *   • Same renderer is used in CRM v2 contact detail, the future
 *     contact-detail drawer in Memberships, and (later) company/deal
 *     pages — single rule-builder vocabulary, single editor.
 *   • Groups properties by their `group` field to mirror the editor
 *     UI in Master Admin.
 *   • Save-on-blur — no big "Save" button required for a single field
 *     tweak. Toast on failure via formatApiError.
 *
 * Permissions: read for any authenticated user; write requires the
 * caller to provide a working onSave (we don't gate write here).
 */
import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { Database, Loader2, CheckCircle2, X } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

// Type → editor element. We keep this lean — anything fancier should be
// a separate component file, not inlined here.
const renderField = (prop, value, onChange, isDark) => {
  const baseCls = 'w-full px-2 py-1.5 border rounded-md text-sm';
  const style = {
    background: isDark ? 'var(--color-neutral-950)' : '#fff',
    borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)',
    color: isDark ? 'var(--color-paper-alt)' : 'var(--color-neutral-950-alt)',
  };
  switch (prop.field_type) {
    case 'number':
      return <input type="number" value={value ?? ''} onChange={(e) => onChange(e.target.value === '' ? null : parseFloat(e.target.value))} className={baseCls} style={style} data-testid={`custom-field-${prop.key}`} />;
    case 'date':
      return <input type="date" value={value ?? ''} onChange={(e) => onChange(e.target.value)} className={baseCls} style={style} data-testid={`custom-field-${prop.key}`} />;
    case 'boolean':
      return (
        <label className="inline-flex items-center gap-2 text-xs cursor-pointer">
          <input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} data-testid={`custom-field-${prop.key}`} />
          <span style={{ color: style.color }}>{value ? 'Yes' : 'No'}</span>
        </label>
      );
    case 'url':
      return <input type="url" value={value ?? ''} onChange={(e) => onChange(e.target.value)} placeholder="https://…" className={baseCls} style={style} data-testid={`custom-field-${prop.key}`} />;
    case 'email':
      return <input type="email" value={value ?? ''} onChange={(e) => onChange(e.target.value)} placeholder="name@example.com" className={baseCls} style={style} data-testid={`custom-field-${prop.key}`} />;
    case 'select':
      return (
        <select value={value ?? ''} onChange={(e) => onChange(e.target.value || null)} className={baseCls} style={style} data-testid={`custom-field-${prop.key}`}>
          <option value="">—</option>
          {(prop.options || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      );
    case 'multi_select':
      return (
        <div className="space-y-1" data-testid={`custom-field-${prop.key}`}>
          {(prop.options || []).map((o) => {
            const arr = Array.isArray(value) ? value : [];
            const checked = arr.includes(o.value);
            return (
              <label key={o.value} className="inline-flex items-center gap-2 text-xs mr-3 cursor-pointer" style={{ color: style.color }}>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(e) => {
                    const next = e.target.checked
                      ? [...arr, o.value]
                      : arr.filter((x) => x !== o.value);
                    onChange(next);
                  }}
                />
                {o.label}
              </label>
            );
          })}
        </div>
      );
    case 'text':
    default:
      return <input type="text" value={value ?? ''} onChange={(e) => onChange(e.target.value)} className={baseCls} style={style} data-testid={`custom-field-${prop.key}`} />;
  }
};


export default function CustomFieldsPanel({
  entityType, entityId, values, onSave, isDark = false, headers,
}) {
  const auth = headers || ((typeof window !== 'undefined') ? { Authorization: `Bearer ${localStorage.getItem('token')}` } : {});
  const [props, setProps] = useState(null);
  const [pending, setPending] = useState({}); // {key: value} — local edits not yet flushed
  const [saving, setSaving] = useState(null); // current key being saved
  const [savedAt, setSavedAt] = useState({}); // {key: timestamp} for the green tick
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/api/custom-properties?entity_type=${entityType}`, { headers: auth });
      setProps(r.data.properties || []);
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to load custom properties');
      setProps([]);
    }
  }, [API, entityType, auth]);

  useEffect(() => { load(); }, [load]);

  const flush = async (key, value) => {
    setSaving(key);
    try {
      await onSave({ [key]: value });
      setSavedAt((prev) => ({ ...prev, [key]: Date.now() }));
      setPending((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
      setTimeout(() => {
        setSavedAt((prev) => {
          const n = { ...prev };
          delete n[key];
          return n;
        });
      }, 2500);
    } catch (e) {
      setError(e.response?.data?.detail || 'Save failed');
    } finally {
      setSaving(null);
    }
  };

  if (props === null) {
    return (
      <div className="flex items-center gap-2 text-xs text-zinc-500 py-3" data-testid={`custom-fields-${entityType}-loading`}>
        <Loader2 size={12} className="animate-spin" /> Loading custom fields…
      </div>
    );
  }
  if (props.length === 0) {
    return (
      <div className="rounded-md border-dashed border p-4 text-center" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }} data-testid={`custom-fields-${entityType}-empty`}>
        <Database size={16} className="mx-auto mb-1" style={{ color: isDark ? 'var(--color-text-faint)' : 'var(--color-text-faint)' }} />
        <p className="text-xs" style={{ color: isDark ? 'var(--color-text-muted)' : 'var(--color-text-faint)' }}>
          No custom properties defined for {entityType}s yet.{' '}
          <a href="/master-admin" className="text-[var(--color-brand-blue)] underline">Add some →</a>
        </p>
      </div>
    );
  }

  // Group by their `group` field, preserving Master Admin's ordering.
  const grouped = {};
  for (const p of props) {
    const g = p.group || 'Custom';
    if (!grouped[g]) grouped[g] = [];
    grouped[g].push(p);
  }

  const currentValue = (key) => (key in pending ? pending[key] : (values?.[key] ?? ''));

  return (
    <div className="space-y-4" data-testid={`custom-fields-${entityType}`}>
      {error && (
        <div className="rounded-md border border-rose-300 bg-rose-50 p-2 text-xs text-rose-700 inline-flex items-center gap-1.5" data-testid="custom-fields-error">
          <X size={11} /> {error}
        </div>
      )}
      {Object.entries(grouped).map(([groupName, groupProps]) => (
        <div key={groupName} className="space-y-2" data-testid={`custom-fields-group-${groupName}`}>
          <p className="text-[10px] uppercase tracking-wider font-bold" style={{ color: isDark ? 'var(--color-text-faint)' : 'var(--color-text-muted)' }}>
            {groupName}
          </p>
          {groupProps.map((p) => {
            const val = currentValue(p.key);
            return (
              <div key={p.key} className="flex items-start gap-3" data-testid={`custom-field-row-${p.key}`}>
                <label className="text-xs font-medium pt-2 w-32 shrink-0" style={{ color: isDark ? 'var(--color-text-muted)' : 'var(--color-ink-muted)' }}>
                  {p.label}
                  {p.required && <span className="text-rose-500 ml-0.5">*</span>}
                </label>
                <div className="flex-1 min-w-0">
                  {renderField(p, val, (next) => {
                    setPending((prev) => ({ ...prev, [p.key]: next }));
                  }, isDark)}
                  {p.description && (
                    <p className="text-[10px] mt-0.5" style={{ color: isDark ? 'var(--color-text-faint)' : 'var(--color-text-muted)' }}>{p.description}</p>
                  )}
                </div>
                <div className="pt-2 w-16 shrink-0 text-right">
                  {(p.key in pending) && (
                    <button
                      onClick={() => flush(p.key, pending[p.key])}
                      disabled={saving === p.key}
                      className="text-[11px] font-semibold text-[var(--color-brand-blue)] hover:underline disabled:opacity-50 inline-flex items-center gap-1"
                      data-testid={`custom-field-save-${p.key}`}
                    >
                      {saving === p.key ? <Loader2 size={10} className="animate-spin" /> : null}
                      Save
                    </button>
                  )}
                  {savedAt[p.key] && (
                    <span className="text-[10px] inline-flex items-center gap-1 text-emerald-600" data-testid={`custom-field-saved-${p.key}`}>
                      <CheckCircle2 size={10} /> Saved
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
