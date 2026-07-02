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
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft, Plus, Loader2, Archive, Edit3, Save, X,
  Eye, EyeOff, Sparkles, Check, ChevronRight,
  Share2, Link2, Copy, Download, Tags,
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

// Iter 220du — Job-type filter chips. Empty selection = all jobs
// (the historic behaviour, fully backwards compatible).
// Iter 220ec — these are now fetched live from the org's configurable
// case types; this constant is only a fallback before the fetch lands.
const JOB_TYPE_OPTIONS = [
  { id: 'repair',     label: 'Repair' },
  { id: 'ppm',        label: 'PPM Service' },
  { id: 'install',    label: 'Installation' },
  { id: 'inspection', label: 'Inspection' },
  { id: 'callout',    label: 'Emergency callout' },
  { id: 'audit',      label: 'Asset audit' },
];

export default function EngineerWorkReportFields() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showArchived, setShowArchived] = useState(false);
  const [editing, setEditing] = useState(null); // id under edit
  const [creating, setCreating] = useState(false);
  // Iter 220ea·14 — Templates modal toggle.
  const [showTemplates, setShowTemplates] = useState(false);
  // Iter 220ea·24 — Share / import modal. `shareToken` deep-links an
  // inbound share (?share=<token>) straight into import-preview.
  const [showShare, setShowShare] = useState(false);
  const [shareToken, setShareToken] = useState('');
  // Iter 220ec — live job-type options from configurable case types.
  const [jobTypeOptions, setJobTypeOptions] = useState(JOB_TYPE_OPTIONS);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/svc/case-types`, auth());
        const opts = (r.data?.case_types || [])
          .filter((t) => t.active !== false)
          .map((t) => ({ id: t.slug, label: t.label }));
        if (!cancelled && opts.length) setJobTypeOptions(opts);
      } catch { /* fall back to defaults */ }
    })();
    return () => { cancelled = true; };
  }, []);

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

  // Iter 220ea·24 — open the import flow when arriving via a share link.
  useEffect(() => {
    const t = searchParams.get('share');
    if (t) {
      setShareToken(t);
      setShowShare(true);
    }
  }, [searchParams]);

  const closeShare = () => {
    setShowShare(false);
    setShareToken('');
    if (searchParams.get('share')) {
      searchParams.delete('share');
      setSearchParams(searchParams, { replace: true });
    }
  };

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
            onClick={() => navigate('/svc/engineer/case-types')}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 text-sm font-bold hover:bg-slate-50"
            data-testid="wrf-case-types-btn"
            title="Manage your case types (Repair / PPM / custom)"
          >
            <Tags size={14} /> Case types
          </button>
          <button
            onClick={() => setShowTemplates(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-teal-200 bg-teal-50 text-teal-700 text-sm font-bold hover:bg-teal-100"
            data-testid="wrf-templates-btn"
            title="Pick a starter template (e.g. Treadmill PPM) to seed common fields in one tap"
          >
            <Sparkles size={14} /> Templates
          </button>
          <button
            onClick={() => { setShareToken(''); setShowShare(true); }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 text-sm font-bold hover:bg-slate-50"
            data-testid="wrf-share-btn"
            title="Share these fields with another organisation, or import a shared set"
          >
            <Share2 size={14} /> Share
          </button>
          <button
            onClick={() => setCreating(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-600 text-white text-sm font-bold hover:bg-cyan-700"
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
            jobTypeOptions={jobTypeOptions}
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
              className="mt-4 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-600 text-white text-sm font-bold"
              data-testid="wrf-empty-create-btn"
            >
              <Plus size={14} /> Create first field
            </button>
            <button
              onClick={() => setShowTemplates(true)}
              className="mt-2 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-teal-200 bg-teal-50 text-teal-700 text-sm font-bold hover:bg-teal-100"
              data-testid="wrf-empty-templates-btn"
            >
              <Sparkles size={14} /> Or pick a starter template
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
                  jobTypeOptions={jobTypeOptions}
                  onCancel={() => setEditing(null)}
                  onSaved={() => { setEditing(null); load(); }}
                />
              ) : (
                <FieldCard
                  key={row.id}
                  row={row}
                  jobTypeOptions={jobTypeOptions}
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

      {showTemplates && (
        <FieldTemplatesModal
          onClose={() => setShowTemplates(false)}
          onApplied={() => { setShowTemplates(false); load(); }}
        />
      )}

      {showShare && (
        <ShareImportModal
          fieldCount={rows.filter((r) => !r.archived).length}
          initialToken={shareToken}
          onClose={closeShare}
          onImported={() => { closeShare(); load(); }}
        />
      )}
    </div>
  );
}

function scopeLabel(row) {
  const opt = SCOPE_OPTIONS.find(s => s.id === row.scope_kind);
  if (!opt) return row.scope_kind;
  if (row.scope_kind === 'global') return 'All machines';
  return `${opt.label.split(' (')[0]}: ${row.scope_value || '—'}`;
}

function FieldCard({ row, onEdit, onArchive, onRestore, jobTypeOptions = JOB_TYPE_OPTIONS }) {
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
          {/* Iter 220du — Job-type chips (empty = all). */}
          {(row.job_types || []).length ? (
            <p
              className="text-[11px] text-teal-700 mt-1 flex flex-wrap gap-1"
              data-testid={`wrf-row-${row.id}-job-types`}
            >
              {row.job_types.map((jt) => (
                <span
                  key={jt}
                  className="inline-flex items-center px-1.5 py-0.5 rounded-full bg-teal-50 border border-teal-200 text-[10px] font-bold uppercase"
                >
                  {jobTypeOptions.find((o) => o.id === jt)?.label || jt}
                </span>
              ))}
            </p>
          ) : null}
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

export function FieldEditor({ mode, row, onCancel, onSaved, jobTypeOptions = JOB_TYPE_OPTIONS }) {
  const isEdit = mode === 'edit';
  const [name, setName] = useState(row?.name || '');
  const [fieldType, setFieldType] = useState(row?.field_type || 'text');
  const [scopeKind, setScopeKind] = useState(row?.scope_kind || 'global');
  const [scopeValue, setScopeValue] = useState(row?.scope_value || '');
  const [options, setOptions] = useState((row?.options || []).join('\n'));
  const [required, setRequired] = useState(!!row?.required);
  const [helpText, setHelpText] = useState(row?.help_text || '');
  // Iter 220du — Job-type filter (Repair / PPM / Install / etc).
  // Empty array = all job types (the historic behaviour, fully
  // backwards compatible).
  const [jobTypes, setJobTypes] = useState(row?.job_types || []);
  const [busy, setBusy] = useState(false);

  const toggleJobType = (slug) => {
    setJobTypes((prev) =>
      prev.includes(slug) ? prev.filter((s) => s !== slug) : [...prev, slug],
    );
  };

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
          job_types: jobTypes,
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
          job_types: jobTypes,
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
    <div className="rounded-2xl border border-cyan-200 bg-cyan-50/40 p-4 space-y-3" data-testid={`wrf-editor-${isEdit ? row.id : 'new'}`}>
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

      {/* Iter 220du — Job-type filter chips. Clicking toggles
          inclusion; an empty set means "show on every job type".
          Drives `fields_for_case` + `fields_for_machine_row`. */}
      <div data-testid="wrf-editor-job-types">
        <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
          Only on these job types{' '}
          <span className="font-normal normal-case text-slate-400">
            (leave empty for all)
          </span>
        </p>
        <div className="flex flex-wrap gap-1.5 mt-1">
          {jobTypeOptions.map((j) => {
            const on = jobTypes.includes(j.id);
            return (
              <button
                key={j.id}
                type="button"
                onClick={() => toggleJobType(j.id)}
                className={`px-2.5 py-1 rounded-full text-[11px] font-bold border ${
                  on
                    ? 'bg-teal-600 text-white border-teal-600'
                    : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
                }`}
                data-testid={`wrf-editor-job-${j.id}`}
              >
                {j.label}
              </button>
            );
          })}
        </div>
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
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-600 text-white text-xs font-bold disabled:opacity-50"
          data-testid="wrf-editor-save-btn"
        >
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
          {isEdit ? 'Save changes' : 'Create field'}
        </button>
      </div>
    </div>
  );
}

// ─── Iter 220ea·14 · FieldTemplatesModal ─────────────────────────
// Bottom-sheet style modal listing the platform's starter
// templates. Each card is one-tap apply: the engineer can tweak
// scope_value (e.g. their own taxonomy "Cardio · Belt") before
// applying. Skips fields with the same name in the same scope so
// it's safe to re-apply without creating duplicates.
function FieldTemplatesModal({ onClose, onApplied }) {
  const [loading, setLoading] = useState(true);
  const [templates, setTemplates] = useState([]);
  const [appliedId, setAppliedId] = useState(null);
  const [busyId, setBusyId] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/svc/work-report-fields/templates`, auth());
        if (!cancelled) setTemplates(r.data?.templates || []);
      } catch (e) {
        if (!cancelled) notify.error('Could not load templates', e?.response?.data?.detail || e?.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const apply = async (t) => {
    if (!window.confirm(
      `Apply "${t.name}"?\n\nThis seeds ${t.field_count} field${t.field_count === 1 ? '' : 's'} `
      + `into your custom-fields library (scope: ${t.scope_kind === 'global'
        ? 'all machines'
        : `${t.scope_kind} = ${t.scope_value}`}).`
      + `\n\nYou can edit or archive any field afterwards.`,
    )) return;
    setBusyId(t.id);
    try {
      const r = await axios.post(`${API}/svc/work-report-fields/apply-template`, {
        template_id: t.id,
      }, auth());
      const created = r.data?.created_count || 0;
      const skipped = r.data?.skipped_count || 0;
      notify.success(
        'Template applied',
        `${created} field${created === 1 ? '' : 's'} created${skipped > 0 ? ` · ${skipped} already existed (skipped)` : ''}.`,
      );
      setAppliedId(t.id);
      onApplied?.();
    } catch (e) {
      notify.error('Could not apply template', e?.response?.data?.detail || e?.message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-end sm:items-center justify-center p-3"
      onClick={onClose}
      data-testid="wrf-templates-modal"
    >
      <div
        className="w-full max-w-2xl max-h-[90vh] overflow-hidden bg-white rounded-2xl shadow-2xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="px-5 py-4 border-b border-slate-200 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-teal-100 flex items-center justify-center">
            <Sparkles size={18} className="text-teal-700" />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-base font-extrabold text-slate-900">
              Starter templates
            </h2>
            <p className="text-xs text-slate-500">
              Tap any template to seed common fields. You can edit, rename, or archive them after.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-full hover:bg-slate-100"
            aria-label="Close"
            data-testid="wrf-templates-close"
          >
            <X size={16} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-3 py-3">
          {loading ? (
            <div className="flex items-center justify-center py-10 text-slate-400">
              <Loader2 size={18} className="animate-spin mr-2" />
              Loading templates…
            </div>
          ) : templates.length === 0 ? (
            <p className="text-sm text-slate-500 text-center py-8">
              No templates available.
            </p>
          ) : (
            <ul className="space-y-2">
              {templates.map((t) => {
                const isApplied = appliedId === t.id;
                const isBusy = busyId === t.id;
                return (
                  <li
                    key={t.id}
                    className={`rounded-xl border bg-white p-3 transition-colors ${
                      isApplied ? 'border-emerald-200 bg-emerald-50' : 'border-slate-200 hover:bg-slate-50'
                    }`}
                    data-testid={`wrf-template-card-${t.id}`}
                  >
                    <div className="flex items-start gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <p className="text-sm font-extrabold text-slate-900">{t.name}</p>
                          <span className="inline-flex items-center text-[10px] font-extrabold uppercase tracking-wider px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
                            {t.field_count} field{t.field_count === 1 ? '' : 's'}
                          </span>
                          {t.scope_kind !== 'global' && t.scope_value && (
                            <span className="inline-flex items-center text-[10px] font-extrabold uppercase tracking-wider px-2 py-0.5 rounded-full bg-teal-50 text-teal-700 border border-teal-200">
                              {t.scope_value}
                            </span>
                          )}
                          {(t.job_types || []).map((jt) => (
                            <span
                              key={jt}
                              className="inline-flex items-center text-[10px] font-extrabold uppercase tracking-wider px-2 py-0.5 rounded-full bg-cyan-50 text-cyan-700 border border-cyan-200"
                            >
                              {jt}
                            </span>
                          ))}
                        </div>
                        <p className="text-xs text-slate-500 mt-1 leading-snug">{t.summary}</p>
                        <details className="mt-2 group">
                          <summary className="text-[11px] text-slate-500 cursor-pointer hover:text-slate-700 inline-flex items-center gap-1">
                            <ChevronRight size={10} className="transition-transform group-open:rotate-90" />
                            Preview {t.field_count} field{t.field_count === 1 ? '' : 's'}
                          </summary>
                          <ul className="mt-1.5 space-y-1 pl-3">
                            {(t.fields || []).map((f, i) => (
                              <li
                                key={i}
                                className="text-[11px] text-slate-700 flex items-center gap-2"
                                data-testid={`wrf-template-${t.id}-field-${i}`}
                              >
                                <span className="font-mono text-slate-400">{i + 1}.</span>
                                <span className="font-bold text-slate-900">{f.name}</span>
                                <span className="text-slate-400">·</span>
                                <span className="uppercase tracking-wide text-[9px] text-slate-500">{f.field_type}</span>
                                {f.required && <span className="text-rose-600 font-extrabold">*</span>}
                              </li>
                            ))}
                          </ul>
                        </details>
                      </div>
                      <button
                        type="button"
                        onClick={() => apply(t)}
                        disabled={isBusy || isApplied}
                        className={`shrink-0 inline-flex items-center gap-1 px-3 py-2 rounded-lg text-xs font-extrabold transition-colors ${
                          isApplied
                            ? 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                            : 'bg-teal-600 text-white hover:bg-teal-700 disabled:opacity-50'
                        }`}
                        data-testid={`wrf-template-apply-${t.id}`}
                      >
                        {isBusy ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : isApplied ? (
                          <Check size={12} />
                        ) : (
                          <Plus size={12} />
                        )}
                        {isApplied ? 'Applied' : isBusy ? 'Applying…' : 'Apply'}
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <footer className="px-5 py-3 border-t border-slate-200 flex items-center justify-between bg-slate-50">
          <p className="text-[10px] text-slate-500">
            Templates are safe to re-apply — duplicates are skipped automatically.
          </p>
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded-lg bg-white border border-slate-200 text-slate-700 text-xs font-bold hover:bg-slate-50"
          >
            Done
          </button>
        </footer>
      </div>
    </div>
  );
}


// ─── Iter 220ea·24 · ShareImportModal ─────────────────────────────
// Two flows in one sheet: (1) "Share" bundles the org's custom fields
// into a token + link to hand to another org; (2) "Import" pastes a
// token/link, previews the shared set, and one-tap imports it (dups
// skipped). A ?share=<token> deep-link opens straight into Import.
function ShareImportModal({ fieldCount, initialToken, onClose, onImported }) {
  const [tab, setTab] = useState(initialToken ? 'import' : 'share');

  // Share state
  const [label, setLabel] = useState('');
  const [generating, setGenerating] = useState(false);
  const [shareResult, setShareResult] = useState(null); // {token, url, field_count}
  const [copied, setCopied] = useState(false);

  // Import state
  const [tokenInput, setTokenInput] = useState(initialToken || '');
  const [previewing, setPreviewing] = useState(false);
  const [preview, setPreview] = useState(null); // {source_org_name, fields, ...}
  const [importing, setImporting] = useState(false);

  const shareUrl = (token) =>
    `${window.location.origin}/svc/engineer/work-report-fields?share=${token}`;

  const extractToken = (raw) => {
    const v = (raw || '').trim();
    if (!v) return '';
    const m = v.match(/[?&]share=([^&\s]+)/);
    if (m) return decodeURIComponent(m[1]);
    // Bare token (strip any trailing slash/url noise).
    return v.split(/[/?#\s]/).pop();
  };

  const generate = async () => {
    setGenerating(true);
    try {
      const r = await axios.post(`${API}/svc/work-report-fields/share`, {
        field_ids: [], label: label.trim() || undefined,
      }, auth());
      const token = r.data?.token;
      setShareResult({ token, url: shareUrl(token), field_count: r.data?.field_count || 0 });
    } catch (e) {
      notify.error('Could not create share link', e?.response?.data?.detail || e?.message);
    } finally {
      setGenerating(false);
    }
  };

  const copyLink = async () => {
    if (!shareResult?.url) return;
    try {
      await navigator.clipboard.writeText(shareResult.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      notify.error('Copy failed — select and copy the link manually');
    }
  };

  const doPreview = useCallback(async (tok) => {
    const token = extractToken(tok);
    if (!token) { notify.error('Paste a share link or token first'); return; }
    setPreviewing(true);
    setPreview(null);
    try {
      const r = await axios.get(`${API}/svc/work-report-fields/shared/${encodeURIComponent(token)}`, auth());
      setPreview({ ...r.data, token });
    } catch (e) {
      notify.error('Could not load shared fields', e?.response?.data?.detail || e?.message);
    } finally {
      setPreviewing(false);
    }
  }, []);

  // Auto-preview when deep-linked via ?share=.
  useEffect(() => {
    if (initialToken) doPreview(initialToken);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialToken]);

  const doImport = async () => {
    if (!preview?.token) return;
    setImporting(true);
    try {
      const r = await axios.post(
        `${API}/svc/work-report-fields/shared/${encodeURIComponent(preview.token)}/import`,
        {}, auth());
      const created = r.data?.created_count || 0;
      const skipped = r.data?.skipped_count || 0;
      notify.success(
        'Fields imported',
        `${created} field${created === 1 ? '' : 's'} added${skipped > 0 ? ` · ${skipped} already existed (skipped)` : ''}.`,
      );
      onImported?.();
    } catch (e) {
      notify.error('Import failed', e?.response?.data?.detail || e?.message);
    } finally {
      setImporting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-end sm:items-center justify-center p-3"
      onClick={onClose}
      data-testid="wrf-share-modal"
    >
      <div
        className="w-full max-w-xl max-h-[90vh] overflow-hidden bg-white rounded-2xl shadow-2xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="px-5 py-4 border-b border-slate-200 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-slate-900 flex items-center justify-center">
            <Share2 size={18} className="text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-base font-extrabold text-slate-900">Share custom fields</h2>
            <p className="text-xs text-slate-500">Copy your field set to another organisation.</p>
          </div>
          <button type="button" onClick={onClose} className="p-2 rounded-full hover:bg-slate-100" aria-label="Close" data-testid="wrf-share-close">
            <X size={16} />
          </button>
        </header>

        <div className="px-3 pt-3 flex gap-1">
          <button
            onClick={() => setTab('share')}
            className={`flex-1 inline-flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-bold border ${tab === 'share' ? 'bg-slate-900 text-white border-slate-900' : 'bg-white text-slate-600 border-slate-200'}`}
            data-testid="wrf-share-tab-share"
          >
            <Link2 size={14} /> Share mine
          </button>
          <button
            onClick={() => setTab('import')}
            className={`flex-1 inline-flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-bold border ${tab === 'import' ? 'bg-slate-900 text-white border-slate-900' : 'bg-white text-slate-600 border-slate-200'}`}
            data-testid="wrf-share-tab-import"
          >
            <Download size={14} /> Import a link
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {tab === 'share' ? (
            <div className="space-y-3" data-testid="wrf-share-pane">
              <p className="text-xs text-slate-500">
                This creates a link sharing all <b>{fieldCount}</b> active custom field{fieldCount === 1 ? '' : 's'}.
                The recipient imports them into their own library — duplicates are skipped.
              </p>
              <div>
                <label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Label (optional)</label>
                <input
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  maxLength={80}
                  placeholder="e.g. Treadmill PPM pack"
                  className="w-full mt-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white"
                  data-testid="wrf-share-label"
                />
              </div>
              {!shareResult ? (
                <button
                  onClick={generate}
                  disabled={generating || fieldCount === 0}
                  className="w-full inline-flex items-center justify-center gap-2 py-2.5 rounded-lg bg-slate-900 text-white text-sm font-bold disabled:opacity-50"
                  data-testid="wrf-share-generate"
                >
                  {generating ? <Loader2 size={14} className="animate-spin" /> : <Link2 size={14} />}
                  {fieldCount === 0 ? 'No fields to share' : 'Generate share link'}
                </button>
              ) : (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 space-y-2" data-testid="wrf-share-result">
                  <p className="text-xs font-bold text-emerald-800">
                    Link ready · {shareResult.field_count} field{shareResult.field_count === 1 ? '' : 's'} · valid 30 days
                  </p>
                  <div className="flex items-center gap-2">
                    <input
                      readOnly
                      value={shareResult.url}
                      className="flex-1 text-xs border border-emerald-200 rounded-lg px-2 py-2 bg-white font-mono text-slate-700"
                      data-testid="wrf-share-url"
                      onFocus={(e) => e.target.select()}
                    />
                    <button
                      onClick={copyLink}
                      className="shrink-0 inline-flex items-center gap-1 px-3 py-2 rounded-lg bg-emerald-600 text-white text-xs font-bold"
                      data-testid="wrf-share-copy"
                    >
                      {copied ? <Check size={13} /> : <Copy size={13} />}
                      {copied ? 'Copied' : 'Copy'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-3" data-testid="wrf-import-pane">
              <p className="text-xs text-slate-500">
                Paste a share link (or token) someone sent you, then preview and import.
              </p>
              <div className="flex items-center gap-2">
                <input
                  value={tokenInput}
                  onChange={(e) => setTokenInput(e.target.value)}
                  placeholder="Paste share link or token…"
                  className="flex-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white"
                  data-testid="wrf-import-token"
                />
                <button
                  onClick={() => doPreview(tokenInput)}
                  disabled={previewing || !tokenInput.trim()}
                  className="shrink-0 inline-flex items-center gap-1 px-3 py-2 rounded-lg bg-slate-900 text-white text-sm font-bold disabled:opacity-50"
                  data-testid="wrf-import-preview"
                >
                  {previewing ? <Loader2 size={13} className="animate-spin" /> : 'Preview'}
                </button>
              </div>

              {preview && (
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 space-y-2" data-testid="wrf-import-preview-result">
                  <p className="text-xs text-slate-600">
                    <b className="text-slate-900">{preview.label || `${preview.field_count} fields`}</b>
                    {preview.source_org_name ? <> · from <b>{preview.source_org_name}</b></> : null}
                    {preview.is_own_org ? <span className="ml-1 text-amber-700">(your own org)</span> : null}
                  </p>
                  <ul className="space-y-1 max-h-48 overflow-y-auto">
                    {(preview.fields || []).map((f, i) => (
                      <li key={i} className="text-[11px] text-slate-700 flex items-center gap-2" data-testid={`wrf-import-field-${i}`}>
                        <span className="font-mono text-slate-400">{i + 1}.</span>
                        <span className="font-bold text-slate-900">{f.name}</span>
                        <span className="text-slate-400">·</span>
                        <span className="uppercase tracking-wide text-[9px] text-slate-500">{f.field_type}</span>
                        {f.required && <span className="text-rose-600 font-extrabold">*</span>}
                      </li>
                    ))}
                  </ul>
                  <button
                    onClick={doImport}
                    disabled={importing}
                    className="w-full inline-flex items-center justify-center gap-2 py-2.5 rounded-lg bg-cyan-600 text-white text-sm font-bold disabled:opacity-50"
                    data-testid="wrf-import-confirm"
                  >
                    {importing ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                    Import {preview.field_count} field{preview.field_count === 1 ? '' : 's'}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
