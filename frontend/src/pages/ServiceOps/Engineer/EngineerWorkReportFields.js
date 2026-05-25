/**
 * EngineerWorkReportFields — Iter 220
 *
 * Engineer-facing manager for custom Work Report fields. Each definition is
 * a per-machine question that will appear on the Complete tab of any job
 * whose asset matches the scope (e.g. "Drag Factor" on every Concept 2
 * machine). Engineers can also create field defs ad-hoc straight from a
 * job's Complete tab — this page is the central library to manage them
 * after the fact.
 *
 * Backend routes:
 *   GET    /api/svc/work-report-fields
 *   POST   /api/svc/work-report-fields
 *   PATCH  /api/svc/work-report-fields/{id}
 *   DELETE /api/svc/work-report-fields/{id}   (soft archive)
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Plus, Loader2, Archive, Edit3, Save, X,
  Eye, EyeOff,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const SCOPE_OPTIONS = [
  { id: 'global',         label: 'All machines (global)' },
  { id: 'equipment_type', label: 'By equipment type (e.g. Treadmill)' },
  { id: 'manufacturer',   label: 'By manufacturer (e.g. Concept 2)' },
  { id: 'model',          label: 'By model name' },
  { id: 'asset',          label: 'Single machine (asset id)' },
];
const TYPE_OPTIONS = [
  { id: 'text',     label: 'Text' },
  { id: 'number',   label: 'Number' },
  { id: 'dropdown', label: 'Dropdown' },
  { id: 'checkbox', label: 'Checkbox' },
  { id: 'date',     label: 'Date' },
  { id: 'file',     label: 'File upload' },
];

export default function EngineerWorkReportFields() {
  const navigate = useNavigate();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showArchived, setShowArchived] = useState(false);
  const [editing, setEditing] = useState(null); // id under edit
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(
        `${API}/svc/work-report-fields?include_archived=${showArchived ? 'true' : 'false'}`,
        auth(),
      );
      setRows(r.data?.fields || []);
    } catch (e) {
      notify.error('Could not load custom fields', e?.response?.data?.detail || e?.message);
    } finally {
      setLoading(false);
    }
  }, [showArchived]);

  useEffect(() => { load(); }, [load]);

  const visibleRows = useMemo(() => rows, [rows]);

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-work-report-fields">
      <header className="sticky top-0 z-10 bg-white border-b border-slate-200">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center gap-3">
          <button
            onClick={() => navigate('/svc/engineer')}
            className="p-2 -ml-2 rounded-lg hover:bg-slate-100"
            data-testid="wrf-back-btn"
          >
            <ArrowLeft size={18} className="text-slate-700" />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-base font-bold text-slate-900">Custom report fields</h1>
            <p className="text-xs text-slate-500">
              Add machine-specific questions to your work reports.
            </p>
          </div>
          <button
            onClick={() => setCreating(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-sm font-bold hover:bg-blue-700"
            data-testid="wrf-new-btn"
          >
            <Plus size={14} /> New field
          </button>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-5 pb-24 space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-xs text-slate-500">
            {loading ? 'Loading…' : `${visibleRows.length} ${visibleRows.length === 1 ? 'field' : 'fields'}`}
          </p>
          <button
            onClick={() => setShowArchived(s => !s)}
            className="inline-flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-900"
            data-testid="wrf-toggle-archived"
          >
            {showArchived ? <EyeOff size={12} /> : <Eye size={12} />}
            {showArchived ? 'Hide archived' : 'Show archived'}
          </button>
        </div>

        {creating && (
          <FieldEditor
            mode="create"
            onCancel={() => setCreating(false)}
            onSaved={() => { setCreating(false); load(); }}
          />
        )}

        {loading ? (
          <div className="flex items-center justify-center py-12 text-slate-400">
            <Loader2 size={20} className="animate-spin mr-2" />
            Loading custom fields…
          </div>
        ) : visibleRows.length === 0 ? (
          <div
            className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center"
            data-testid="wrf-empty"
          >
            <p className="text-sm font-bold text-slate-900">No custom fields yet</p>
            <p className="text-xs text-slate-500 mt-1">
              Create your first one — e.g. "Current Software" for treadmills,
              or "Drag Factor" on every Concept 2 rower.
            </p>
            <button
              onClick={() => setCreating(true)}
              className="mt-4 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-sm font-bold"
              data-testid="wrf-empty-create-btn"
            >
              <Plus size={14} /> Create first field
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            {visibleRows.map((row) => (
              editing === row.id ? (
                <FieldEditor
                  key={row.id}
                  mode="edit"
                  row={row}
                  onCancel={() => setEditing(null)}
                  onSaved={() => { setEditing(null); load(); }}
                />
              ) : (
                <FieldCard
                  key={row.id}
                  row={row}
                  onEdit={() => setEditing(row.id)}
                  onArchive={async () => {
                    if (!window.confirm(`Archive "${row.name}"? It will stop appearing on new work reports.`)) return;
                    try {
                      await axios.delete(`${API}/svc/work-report-fields/${row.id}`, auth());
                      notify.success('Field archived');
                      load();
                    } catch (e) {
                      notify.error('Could not archive', e?.response?.data?.detail || e?.message);
                    }
                  }}
                  onRestore={async () => {
                    try {
                      await axios.patch(`${API}/svc/work-report-fields/${row.id}`, { archived: false }, auth());
                      notify.success('Field restored');
                      load();
                    } catch (e) {
                      notify.error('Could not restore', e?.response?.data?.detail || e?.message);
                    }
                  }}
                />
              )
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

function scopeLabel(row) {
  const opt = SCOPE_OPTIONS.find(s => s.id === row.scope_kind);
  if (!opt) return row.scope_kind;
  if (row.scope_kind === 'global') return 'All machines';
  return `${opt.label.split(' (')[0]}: ${row.scope_value || '—'}`;
}

function FieldCard({ row, onEdit, onArchive, onRestore }) {
  return (
    <div
      className={`rounded-2xl border bg-white p-4 ${row.archived ? 'border-slate-200 opacity-60' : 'border-slate-200'}`}
      data-testid={`wrf-row-${row.id}`}
    >
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-bold text-slate-900 truncate" data-testid={`wrf-name-${row.id}`}>{row.name}</p>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-slate-100 text-slate-700">
              {row.field_type}
            </span>
            {row.required && (
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-rose-100 text-rose-700">
                Required
              </span>
            )}
            {row.archived && (
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-amber-100 text-amber-700">
                Archived
              </span>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-1 truncate">
            {scopeLabel(row)} · key <code className="text-[10px] bg-slate-100 px-1 py-0.5 rounded">{row.key}</code>
          </p>
          {row.field_type === 'dropdown' && (row.options || []).length ? (
            <p className="text-xs text-slate-500 mt-1 truncate">
              Options: {row.options.join(' · ')}
            </p>
          ) : null}
          {row.help_text ? (
            <p className="text-xs text-slate-400 mt-1 italic truncate">{row.help_text}</p>
          ) : null}
        </div>
        <div className="flex items-center gap-1">
          {row.archived ? (
            <button
              type="button"
              onClick={onRestore}
              className="px-2 py-1 rounded-lg text-xs font-bold text-emerald-700 hover:bg-emerald-50"
              data-testid={`wrf-restore-${row.id}`}
            >
              Restore
            </button>
          ) : (
            <>
              <button
                type="button"
                onClick={onEdit}
                className="p-2 rounded-lg hover:bg-slate-100"
                data-testid={`wrf-edit-${row.id}`}
                aria-label="Edit"
              >
                <Edit3 size={14} className="text-slate-700" />
              </button>
              <button
                type="button"
                onClick={onArchive}
                className="p-2 rounded-lg hover:bg-rose-50"
                data-testid={`wrf-archive-${row.id}`}
                aria-label="Archive"
              >
                <Archive size={14} className="text-rose-600" />
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export function FieldEditor({ mode, row, onCancel, onSaved }) {
  const isEdit = mode === 'edit';
  const [name, setName] = useState(row?.name || '');
  const [fieldType, setFieldType] = useState(row?.field_type || 'text');
  const [scopeKind, setScopeKind] = useState(row?.scope_kind || 'global');
  const [scopeValue, setScopeValue] = useState(row?.scope_value || '');
  const [options, setOptions] = useState((row?.options || []).join('\n'));
  const [required, setRequired] = useState(!!row?.required);
  const [helpText, setHelpText] = useState(row?.help_text || '');
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!name.trim()) { notify.error('Name is required'); return; }
    if (scopeKind !== 'global' && !scopeValue.trim()) {
      notify.error('Scope value is required');
      return;
    }
    const opts = options.split(/\n+/).map(s => s.trim()).filter(Boolean);
    if (fieldType === 'dropdown' && opts.length < 2) {
      notify.error('Dropdown fields need at least 2 options');
      return;
    }
    setBusy(true);
    try {
      if (isEdit) {
        await axios.patch(`${API}/svc/work-report-fields/${row.id}`, {
          name: name.trim(),
          options: opts,
          required,
          help_text: helpText.trim(),
        }, auth());
        notify.success('Field updated');
      } else {
        await axios.post(`${API}/svc/work-report-fields`, {
          name: name.trim(),
          field_type: fieldType,
          scope_kind: scopeKind,
          scope_value: scopeKind === 'global' ? null : scopeValue.trim(),
          options: opts,
          required,
          help_text: helpText.trim(),
        }, auth());
        notify.success('Field created');
      }
      onSaved?.();
    } catch (e) {
      notify.error('Could not save field', e?.response?.data?.detail || e?.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-2xl border border-blue-200 bg-blue-50/40 p-4 space-y-3" data-testid={`wrf-editor-${isEdit ? row.id : 'new'}`}>
      <div className="flex items-center justify-between">
        <p className="text-sm font-bold text-slate-900">
          {isEdit ? `Edit "${row.name}"` : 'New custom field'}
        </p>
        <button
          type="button"
          onClick={onCancel}
          className="p-1 rounded-lg hover:bg-white/60"
          data-testid="wrf-editor-cancel"
        >
          <X size={16} className="text-slate-500" />
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Field name *</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full mt-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white"
            placeholder="e.g. Current Software"
            maxLength={60}
            data-testid="wrf-editor-name"
          />
        </div>
        <div>
          <label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Field type *</label>
          <select
            value={fieldType}
            onChange={(e) => setFieldType(e.target.value)}
            disabled={isEdit}
            className="w-full mt-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white disabled:bg-slate-100"
            data-testid="wrf-editor-type"
          >
            {TYPE_OPTIONS.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
          </select>
          {isEdit && <p className="text-[10px] text-slate-400 mt-1">Type can't be changed after creation.</p>}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Show on</label>
          <select
            value={scopeKind}
            onChange={(e) => setScopeKind(e.target.value)}
            disabled={isEdit}
            className="w-full mt-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white disabled:bg-slate-100"
            data-testid="wrf-editor-scope-kind"
          >
            {SCOPE_OPTIONS.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
          </select>
        </div>
        {scopeKind !== 'global' && (
          <div>
            <label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
              {scopeKind === 'asset' ? 'Asset id *' : 'Match value *'}
            </label>
            <input
              value={scopeValue}
              onChange={(e) => setScopeValue(e.target.value)}
              disabled={isEdit}
              className="w-full mt-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white disabled:bg-slate-100"
              placeholder={
                scopeKind === 'equipment_type' ? 'Treadmill' :
                scopeKind === 'manufacturer' ? 'Concept 2' :
                scopeKind === 'model' ? 'Run Artis' :
                'asset-uuid'
              }
              data-testid="wrf-editor-scope-value"
            />
            {isEdit && <p className="text-[10px] text-slate-400 mt-1">Scope can't be changed after creation.</p>}
          </div>
        )}
      </div>

      {fieldType === 'dropdown' && (
        <div>
          <label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Options (one per line, min 2)</label>
          <textarea
            value={options}
            onChange={(e) => setOptions(e.target.value)}
            rows={4}
            className="w-full mt-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white font-mono"
            placeholder={'Low\nMedium\nHigh'}
            data-testid="wrf-editor-options"
          />
        </div>
      )}

      <div>
        <label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Help text (optional)</label>
        <input
          value={helpText}
          onChange={(e) => setHelpText(e.target.value)}
          className="w-full mt-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white"
          placeholder="Shown to the engineer underneath the field"
          maxLength={200}
          data-testid="wrf-editor-help"
        />
      </div>

      <label className="flex items-center gap-2 text-xs text-slate-700 select-none">
        <input
          type="checkbox"
          checked={required}
          onChange={(e) => setRequired(e.target.checked)}
          data-testid="wrf-editor-required"
        />
        Required on work-report submit
      </label>

      <div className="flex justify-end gap-2 pt-1">
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-bold text-slate-700"
          data-testid="wrf-editor-cancel-btn"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={save}
          disabled={busy}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-bold disabled:opacity-50"
          data-testid="wrf-editor-save-btn"
        >
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
          {isEdit ? 'Save changes' : 'Create field'}
        </button>
      </div>
    </div>
  );
}
