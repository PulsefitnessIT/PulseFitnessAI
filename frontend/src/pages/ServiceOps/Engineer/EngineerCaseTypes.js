/**
 * EngineerCaseTypes — Iter 220ec (Phase 2)
 *
 * Manage the organisation's case-type taxonomy (Repair / PPM / custom).
 * Owners AND engineers can add types, rename / recolour them, deactivate
 * the ones they don't use, reorder, and delete custom types.
 *
 * case_type drives the "Job type" row on the customer report and which
 * custom report questions an engineer is asked (questions are scoped to
 * case types in "Custom report fields").
 *
 * Backend routes:
 *   GET    /api/svc/case-types
 *   POST   /api/svc/case-types
 *   PATCH  /api/svc/case-types/{id}
 *   DELETE /api/svc/case-types/{id}
 *   POST   /api/svc/case-types/reorder
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Plus, Loader2, Trash2, Edit3, Save, X,
  ChevronUp, ChevronDown, Eye, EyeOff, ListChecks,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const SWATCHES = ['#dc2626', '#ea580c', '#d97706', '#16a34a', '#0891b2', '#2563eb', '#7c3aed', '#db2777', '#475569'];

export default function EngineerCaseTypes() {
  const navigate = useNavigate();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [savingOrder, setSavingOrder] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/case-types`, auth());
      setRows(r.data?.case_types || []);
    } catch (e) {
      notify.error('Could not load case types', e?.response?.data?.detail || e?.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const move = async (idx, dir) => {
    const next = [...rows];
    const swap = idx + dir;
    if (swap < 0 || swap >= next.length) return;
    [next[idx], next[swap]] = [next[swap], next[idx]];
    setRows(next);
    setSavingOrder(true);
    try {
      await axios.post(`${API}/svc/case-types/reorder`, { ordered_ids: next.map(r => r.id) }, auth());
    } catch (e) {
      notify.error('Could not save order', e?.response?.data?.detail || e?.message);
      load();
    } finally {
      setSavingOrder(false);
    }
  };

  const toggleActive = async (row) => {
    try {
      await axios.patch(`${API}/svc/case-types/${row.id}`, { active: !row.active }, auth());
      load();
    } catch (e) {
      notify.error('Could not update', e?.response?.data?.detail || e?.message);
    }
  };

  const remove = async (row) => {
    if (!window.confirm(`Delete "${row.label}"? Jobs already using it keep their type, but it won't be offered on new jobs.`)) return;
    try {
      await axios.delete(`${API}/svc/case-types/${row.id}`, auth());
      notify.success('Case type deleted');
      load();
    } catch (e) {
      notify.error('Could not delete', e?.response?.data?.detail || e?.message);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-case-types">
      <header className="sticky top-0 z-10 bg-white border-b border-slate-200">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center gap-3">
          <button
            onClick={() => navigate('/svc/engineer')}
            className="p-2 -ml-2 rounded-lg hover:bg-slate-100"
            data-testid="case-types-back-btn"
          >
            <ArrowLeft size={18} className="text-slate-700" />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-base font-bold text-slate-900">Case types</h1>
            <p className="text-xs text-slate-500">Repair, PPM, and your own job types.</p>
          </div>
          <button
            onClick={() => navigate('/svc/engineer/work-report-fields')}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 text-sm font-bold hover:bg-slate-50"
            data-testid="case-types-questions-btn"
            title="Add custom report questions for each case type"
          >
            <ListChecks size={14} /> Questions
          </button>
          <button
            onClick={() => setCreating(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-sm font-bold hover:bg-blue-700"
            data-testid="case-types-new-btn"
          >
            <Plus size={14} /> New type
          </button>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-5 pb-24 space-y-3">
        <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-3 text-xs text-indigo-800">
          Each case type can have its own report questions — set them up under
          <button onClick={() => navigate('/svc/engineer/work-report-fields')} className="font-bold underline mx-1">Questions</button>
          and pick the job type(s) a question applies to. A PPM checklist will then differ from a Repair report.
        </div>

        {creating && (
          <CaseTypeEditor
            mode="create"
            onCancel={() => setCreating(false)}
            onSaved={() => { setCreating(false); load(); }}
          />
        )}

        {loading ? (
          <div className="flex items-center justify-center py-12 text-slate-400">
            <Loader2 size={20} className="animate-spin mr-2" /> Loading…
          </div>
        ) : (
          <div className="space-y-2">
            {rows.map((row, idx) => (
              editingId === row.id ? (
                <CaseTypeEditor
                  key={row.id}
                  mode="edit"
                  row={row}
                  onCancel={() => setEditingId(null)}
                  onSaved={() => { setEditingId(null); load(); }}
                />
              ) : (
                <div
                  key={row.id}
                  className={`rounded-2xl border bg-white p-4 ${row.active ? 'border-slate-200' : 'border-slate-200 opacity-60'}`}
                  data-testid={`case-type-row-${row.slug}`}
                >
                  <div className="flex items-center gap-3">
                    <span className="w-3.5 h-3.5 rounded-full shrink-0" style={{ background: row.color || '#475569' }} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="text-sm font-bold text-slate-900 truncate" data-testid={`case-type-label-${row.slug}`}>{row.label}</p>
                        {row.is_builtin && (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-slate-100 text-slate-600">Built-in</span>
                        )}
                        {!row.active && (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-amber-100 text-amber-700">Inactive</span>
                        )}
                      </div>
                      {row.description ? (
                        <p className="text-xs text-slate-500 mt-0.5 truncate">{row.description}</p>
                      ) : null}
                    </div>
                    <div className="flex items-center gap-0.5">
                      <button type="button" onClick={() => move(idx, -1)} disabled={idx === 0 || savingOrder} className="p-1.5 rounded-lg hover:bg-slate-100 disabled:opacity-30" data-testid={`case-type-up-${row.slug}`} aria-label="Move up">
                        <ChevronUp size={14} className="text-slate-600" />
                      </button>
                      <button type="button" onClick={() => move(idx, 1)} disabled={idx === rows.length - 1 || savingOrder} className="p-1.5 rounded-lg hover:bg-slate-100 disabled:opacity-30" data-testid={`case-type-down-${row.slug}`} aria-label="Move down">
                        <ChevronDown size={14} className="text-slate-600" />
                      </button>
                      <button type="button" onClick={() => toggleActive(row)} className="p-2 rounded-lg hover:bg-slate-100" data-testid={`case-type-toggle-${row.slug}`} aria-label={row.active ? 'Deactivate' : 'Activate'}>
                        {row.active ? <Eye size={14} className="text-slate-700" /> : <EyeOff size={14} className="text-amber-600" />}
                      </button>
                      <button type="button" onClick={() => setEditingId(row.id)} className="p-2 rounded-lg hover:bg-slate-100" data-testid={`case-type-edit-${row.slug}`} aria-label="Edit">
                        <Edit3 size={14} className="text-slate-700" />
                      </button>
                      {!row.is_builtin && (
                        <button type="button" onClick={() => remove(row)} className="p-2 rounded-lg hover:bg-rose-50" data-testid={`case-type-delete-${row.slug}`} aria-label="Delete">
                          <Trash2 size={14} className="text-rose-600" />
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              )
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

function CaseTypeEditor({ mode, row, onCancel, onSaved }) {
  const isEdit = mode === 'edit';
  const [label, setLabel] = useState(row?.label || '');
  const [description, setDescription] = useState(row?.description || '');
  const [color, setColor] = useState(row?.color || '#475569');
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!label.trim()) { notify.error('Label is required'); return; }
    setBusy(true);
    try {
      if (isEdit) {
        await axios.patch(`${API}/svc/case-types/${row.id}`, {
          label: label.trim(), description: description.trim(), color,
        }, auth());
        notify.success('Case type updated');
      } else {
        await axios.post(`${API}/svc/case-types`, {
          label: label.trim(), description: description.trim(), color,
        }, auth());
        notify.success('Case type created');
      }
      onSaved?.();
    } catch (e) {
      notify.error('Could not save', e?.response?.data?.detail || e?.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-2xl border border-blue-200 bg-blue-50/40 p-4 space-y-3" data-testid={`case-type-editor-${isEdit ? row.slug : 'new'}`}>
      <div className="flex items-center justify-between">
        <p className="text-sm font-bold text-slate-900">{isEdit ? `Edit "${row.label}"` : 'New case type'}</p>
        <button type="button" onClick={onCancel} className="p-1 rounded-lg hover:bg-white/60" data-testid="case-type-editor-cancel">
          <X size={16} className="text-slate-500" />
        </button>
      </div>
      <div>
        <label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Label *</label>
        <input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          className="w-full mt-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white"
          placeholder="e.g. Deep Clean"
          maxLength={50}
          data-testid="case-type-editor-label"
        />
      </div>
      <div>
        <label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Description (optional)</label>
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="w-full mt-1 text-sm border border-slate-200 rounded-lg px-3 py-2 bg-white"
          placeholder="Shown to the team when picking a job type"
          maxLength={200}
          data-testid="case-type-editor-description"
        />
      </div>
      <div>
        <label className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Colour</label>
        <div className="flex flex-wrap gap-2 mt-1.5">
          {SWATCHES.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setColor(c)}
              className={`w-7 h-7 rounded-full border-2 ${color === c ? 'border-slate-900' : 'border-transparent'}`}
              style={{ background: c }}
              data-testid={`case-type-editor-color-${c.replace('#', '')}`}
              aria-label={`Colour ${c}`}
            />
          ))}
        </div>
      </div>
      <div className="flex justify-end gap-2 pt-1">
        <button type="button" onClick={onCancel} className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-bold text-slate-700" data-testid="case-type-editor-cancel-btn">
          Cancel
        </button>
        <button type="button" onClick={save} disabled={busy} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-bold disabled:opacity-50" data-testid="case-type-editor-save-btn">
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
          {isEdit ? 'Save changes' : 'Create type'}
        </button>
      </div>
    </div>
  );
}
