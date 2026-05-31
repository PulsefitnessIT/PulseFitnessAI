/**
 * MachineRowCustomFields — Iter 220i
 *
 * Per-machine custom-field block shown inside an expanded machine row
 * on the WorkVisitMachinesCard. Wraps iter-220's custom-field engine:
 *   • Pulls defs scoped to THIS row's asset type / manufacturer / model.
 *   • Pre-fills with the row's already-saved `custom_fields` dict.
 *   • Persists changes back via PATCH /machines/{row_id} on every edit.
 *   • "+ New field" inline editor lets the engineer self-serve creation
 *     scoped automatically to this row's equipment_type — so the SAME
 *     field auto-loads next time they pick a machine of that type.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Plus, Loader2, Sliders } from 'lucide-react';
import { notify } from '@/components/notifications';
import { FieldEditor } from './EngineerWorkReportFields';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

export default function MachineRowCustomFields({ caseId, row, onPatch }) {
  const [fields, setFields] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [context, setContext] = useState({});

  const load = useCallback(async () => {
    if (!row?.id) { setLoading(false); return; }
    setLoading(true);
    try {
      const r = await axios.get(
        `${API}/svc/work-report-fields/for-machine-row/${row.id}`,
        auth(),
      );
      setFields(r.data?.fields || []);
      setContext(r.data?.context || {});
    } catch (e) {
      console.warn('[machine-row-fields] load failed', e);
      setFields([]);
    } finally {
      setLoading(false);
    }
  }, [row?.id]);

  useEffect(() => { load(); }, [load]);

  const setValue = (key, v) => {
    const next = { ...(row.custom_fields || {}), [key]: v };
    onPatch({ custom_fields: next });
  };

  // Default scope for the inline create — choose the strongest signal
  // the row has. If the row has an asset_type → fields auto-load for
  // every future machine of the same type.
  const suggestedScope = (() => {
    if (context.equipment_type) {
      return { scope_kind: 'equipment_type', scope_value: context.equipment_type };
    }
    if (context.manufacturer) {
      return { scope_kind: 'manufacturer', scope_value: context.manufacturer };
    }
    return { scope_kind: 'global', scope_value: null };
  })();

  if (loading) {
    return (
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs text-slate-400 flex items-center gap-2" data-testid={`mrcf-loading-${row.id}`}>
        <Loader2 size={12} className="animate-spin" /> Loading custom fields…
      </div>
    );
  }

  // Iter 220dz — collapse the panel entirely when there's nothing to
  // show. Previously even a blank "no fields configured" placeholder
  // ate ~80 px under every machine row on the Equipment tab. We only
  // render the panel when:
  //   • At least one resolved field exists (admin pre-configured for
  //     this job-type / equipment scope in Account Settings), OR
  //   • The engineer has already saved a value on this row (so the
  //     panel must stay to keep the value visible/editable), OR
  //   • The engineer has actively opened the create editor.
  // A small "+ Custom field" link rides at the bottom of the existing
  // notes section instead (added below).
  const hasSavedValues = Object.keys(row.custom_fields || {}).length > 0;
  if (fields.length === 0 && !creating && !hasSavedValues) {
    return (
      <div className="text-right" data-testid={`mrcf-collapsed-${row.id}`}>
        <button
          type="button"
          onClick={() => setCreating(true)}
          className="inline-flex items-center gap-1 text-[10px] font-bold text-slate-400 hover:text-blue-700"
          data-testid={`mrcf-new-${row.id}`}
        >
          <Plus size={9} /> Custom field
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-3 space-y-2" data-testid={`mrcf-${row.id}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <Sliders size={11} className="text-blue-600" />
          <p className="text-[10px] font-bold uppercase tracking-wide text-slate-600">
            Machine details {context.equipment_type ? `· ${context.equipment_type}` : ''}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setCreating(true)}
          className="inline-flex items-center gap-1 text-[10px] font-bold text-blue-700 hover:underline"
          data-testid={`mrcf-new-${row.id}`}
        >
          <Plus size={9} /> Custom field
        </button>
      </div>

      {creating && (
        <FieldEditor
          mode="create"
          row={{
            scope_kind: suggestedScope.scope_kind,
            scope_value: suggestedScope.scope_value,
          }}
          onCancel={() => setCreating(false)}
          onSaved={() => { setCreating(false); load(); notify.success('Field saved — will auto-load next time'); }}
        />
      )}

      {fields.length === 0 ? null : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {fields.map((f) => (
            <div key={f.id} data-testid={`mrcf-field-${row.id}-${f.key}`}>
              <label className="text-[9px] font-bold uppercase tracking-wide text-slate-500 flex items-center gap-1">
                {f.name}
                {f.required && <span className="text-rose-500">*</span>}
              </label>
              {f.field_type === 'text' && (
                <input
                  value={(row.custom_fields || {})[f.key] || ''}
                  onChange={(e) => setValue(f.key, e.target.value)}
                  className="w-full mt-0.5 text-xs border border-slate-200 rounded px-2 py-1 bg-white"
                  placeholder={f.help_text || ''}
                  data-testid={`mrcf-input-${row.id}-${f.key}`}
                />
              )}
              {f.field_type === 'number' && (
                <input
                  type="number"
                  value={(row.custom_fields || {})[f.key] ?? ''}
                  onChange={(e) => setValue(f.key, e.target.value)}
                  className="w-full mt-0.5 text-xs border border-slate-200 rounded px-2 py-1 bg-white"
                  placeholder={f.help_text || ''}
                  data-testid={`mrcf-input-${row.id}-${f.key}`}
                />
              )}
              {f.field_type === 'date' && (
                <input
                  type="date"
                  value={(row.custom_fields || {})[f.key] || ''}
                  onChange={(e) => setValue(f.key, e.target.value)}
                  className="w-full mt-0.5 text-xs border border-slate-200 rounded px-2 py-1 bg-white"
                  data-testid={`mrcf-input-${row.id}-${f.key}`}
                />
              )}
              {f.field_type === 'dropdown' && (
                <select
                  value={(row.custom_fields || {})[f.key] || ''}
                  onChange={(e) => setValue(f.key, e.target.value)}
                  className="w-full mt-0.5 text-xs border border-slate-200 rounded px-2 py-1 bg-white"
                  data-testid={`mrcf-input-${row.id}-${f.key}`}
                >
                  <option value="">— select —</option>
                  {(f.options || []).map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              )}
              {f.field_type === 'checkbox' && (
                <label className="flex items-center gap-1.5 mt-0.5 text-xs text-slate-700 select-none">
                  <input
                    type="checkbox"
                    checked={!!(row.custom_fields || {})[f.key]}
                    onChange={(e) => setValue(f.key, e.target.checked)}
                    data-testid={`mrcf-input-${row.id}-${f.key}`}
                  />
                  {f.help_text || 'Yes'}
                </label>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
