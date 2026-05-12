/**
 * Phase S4 — Operations tab (Tasks · Forms · Compliance).
 *
 * One tab with three stacked sub-panels — keeps the parent
 * StaffingConsole tab count sane while still surfacing all three
 * subsystems. A pill-style toggle at the top swaps the active panel
 * (saved to localStorage so the operator stays where they left off).
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  CheckSquare, FileText, ShieldAlert, Plus, X, Loader2, Camera, Trash2,
  Pencil, Calendar as CalIcon, AlertTriangle, Check, ClipboardList,
  ChevronDown, ChevronRight, Upload, Send, RefreshCw,
} from 'lucide-react';
import Button from '@/components/shared/Button';
import RowActions from '@/components/shared/RowActions';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SUB_TABS = [
  { id: 'tasks',      label: 'Tasks & Checklists', icon: CheckSquare },
  { id: 'forms',      label: 'Forms',              icon: FileText },
  { id: 'compliance', label: 'Compliance',         icon: ShieldAlert },
];

const CERT_BANDS = {
  expired:      { label: 'Expired',         tint: '#EF4444', bg: 'rgba(239,68,68,0.15)' },
  expiring_30:  { label: 'Expires < 30d',   tint: '#F59E0B', bg: 'rgba(245,158,11,0.15)' },
  expiring_90:  { label: 'Expires < 90d',   tint: '#EAB308', bg: 'rgba(234,179,8,0.12)' },
  ok:           { label: 'OK',              tint: '#10B981', bg: 'rgba(16,185,129,0.10)' },
  unknown:      { label: 'No expiry',       tint: '#94A3B8', bg: 'rgba(148,163,184,0.10)' },
};

function todayISO() { return new Date().toISOString().slice(0, 10); }

// ─────────────────────────── TASKS ───────────────────────────────

function TaskComposer({ open, onClose, onSubmit, headers, staffList }) {
  const [form, setForm] = useState({
    title: '', description: '', kind: 'one_off',
    recurrence: 'daily', weekdays: [0, 1, 2, 3, 4, 5, 6],
    assigned_staff_id: '', due_at: todayISO() + 'T17:00',
    requires_photo: false,
  });
  if (!open) return null;
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = () => {
    if (!form.title.trim()) { window.alert('Title required'); return; }
    const payload = {
      title: form.title.trim(),
      description: form.description.trim() || null,
      kind: form.kind,
      recurrence: form.kind === 'recurring' ? form.recurrence : null,
      weekdays: form.kind === 'recurring' && form.recurrence === 'weekly' ? form.weekdays : [],
      assigned_staff_id: form.assigned_staff_id || null,
      due_at: form.due_at ? `${form.due_at}:00+00:00` : null,
      requires_photo: form.requires_photo,
    };
    onSubmit(payload);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-end sm:items-center justify-center p-0 sm:p-4" data-testid="task-composer">
      <div className="w-full sm:max-w-lg rounded-t-2xl sm:rounded-2xl p-5 space-y-3 max-h-[90vh] overflow-y-auto"
        style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}>
        <div className="flex items-center justify-between">
          <h4 className="text-base font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>New task</h4>
          <button type="button" onClick={onClose} className="w-7 h-7" style={{ color: 'var(--theme-text-muted)' }}><X size={14} /></button>
        </div>
        <input value={form.title} onChange={(e) => set('title', e.target.value)} placeholder="What needs doing?"
          className="w-full h-9 rounded-md bg-transparent border px-2 text-sm" autoFocus
          style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="task-title" />
        <textarea value={form.description} onChange={(e) => set('description', e.target.value)} rows={2} placeholder="Notes (optional)"
          className="w-full rounded-md bg-transparent border px-2 py-1.5 text-sm resize-none"
          style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="task-desc" />
        <div className="flex gap-1.5 flex-wrap">
          {['one_off', 'opening', 'closing', 'recurring'].map((k) => (
            <button key={k} type="button" onClick={() => set('kind', k)}
              className="h-8 px-3 rounded-full text-xs font-bold border"
              style={{
                background: form.kind === k ? 'var(--color-brand-cyan)' : 'transparent',
                color: form.kind === k ? '#001219' : 'var(--theme-text-muted)',
                borderColor: 'var(--theme-border)',
              }}
              data-testid={`task-kind-${k}`}>{k.replace('_', ' ')}</button>
          ))}
        </div>
        {form.kind === 'recurring' && (
          <div className="space-y-2">
            <select value={form.recurrence} onChange={(e) => set('recurrence', e.target.value)}
              className="h-9 rounded-md bg-transparent border px-2 text-xs"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
            </select>
            {form.recurrence === 'weekly' && (
              <div className="flex flex-wrap gap-1">
                {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d, i) => {
                  const on = form.weekdays.includes(i);
                  return (
                    <button key={d} type="button"
                      onClick={() => set('weekdays', on ? form.weekdays.filter((x) => x !== i) : [...form.weekdays, i])}
                      className="h-7 px-2 rounded-full text-[10px] font-bold uppercase tracking-wider border"
                      style={{
                        background: on ? 'var(--color-brand-cyan)' : 'transparent',
                        color: on ? '#001219' : 'var(--theme-text-muted)',
                        borderColor: 'var(--theme-border)',
                      }}>{d}</button>
                  );
                })}
              </div>
            )}
          </div>
        )}
        <div className="grid grid-cols-2 gap-2">
          <select value={form.assigned_staff_id} onChange={(e) => set('assigned_staff_id', e.target.value)}
            className="h-9 rounded-md bg-transparent border px-2 text-xs"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="task-staff">
            <option value="">Unassigned (open)</option>
            {staffList.map((s) => <option key={s.id} value={s.id}>{s.full_name}</option>)}
          </select>
          {form.kind !== 'recurring' && (
            <input type="datetime-local" value={form.due_at} onChange={(e) => set('due_at', e.target.value)}
              className="h-9 rounded-md bg-transparent border px-2 text-xs"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="task-due" />
          )}
        </div>
        <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}>
          <input type="checkbox" checked={form.requires_photo} onChange={(e) => set('requires_photo', e.target.checked)} data-testid="task-photo-req" />
          Require photo to complete
        </label>
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onClose} className="h-9 rounded-full border px-4 text-xs font-bold"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>Cancel</button>
          <button type="button" onClick={submit}
            className="h-9 rounded-full px-4 text-xs font-bold inline-flex items-center gap-1.5"
            style={{ background: 'var(--color-brand-cyan)', color: '#001219' }} data-testid="task-submit">
            <Plus size={12} /> Create
          </button>
        </div>
      </div>
    </div>
  );
}

function TaskRow({ task, isManager, staffList, onComplete, onUncomplete, onDelete }) {
  const completed = task.status === 'completed';
  const owner = staffList.find((s) => s.id === task.assigned_staff_id);
  const tint = task.kind === 'opening' ? '#10B981'
    : task.kind === 'closing' ? '#F59E0B'
    : task.kind === 'recurring' ? '#19CDFF'
    : '#94A3B8';
  return (
    <div className="rounded-lg border p-3 flex items-start gap-3" style={{
      borderColor: 'var(--theme-border)',
      background: completed ? 'rgba(16,185,129,0.05)' : 'transparent',
      opacity: completed ? 0.7 : 1,
    }} data-testid={`task-row-${task.id}`}>
      <button type="button"
        onClick={() => completed ? onUncomplete(task) : onComplete(task)}
        className="w-5 h-5 rounded-md shrink-0 mt-0.5 inline-flex items-center justify-center border transition-colors"
        style={{
          background: completed ? '#10B981' : 'transparent',
          borderColor: completed ? '#10B981' : 'var(--theme-border)',
          color: '#001219',
        }}
        data-testid={`task-toggle-${task.id}`}>
        {completed && <Check size={12} />}
      </button>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-bold" style={{
          color: 'var(--theme-text)',
          textDecoration: completed ? 'line-through' : 'none',
        }}>{task.title}</p>
        {task.description && (
          <p className="text-[11px] mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>{task.description}</p>
        )}
        <div className="flex flex-wrap gap-2 mt-1.5 text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>
          <span className="px-1.5 py-0.5 rounded uppercase font-bold tracking-wider" style={{ background: tint + '22', color: tint }}>{task.kind.replace('_', ' ')}</span>
          {task.due_at && <span className="inline-flex items-center gap-0.5"><CalIcon size={9} /> {task.due_at.slice(0, 16).replace('T', ' ')}</span>}
          {owner && <span>· {owner.full_name}</span>}
          {task.requires_photo && <span className="inline-flex items-center gap-0.5"><Camera size={9} /> Photo</span>}
          {completed && task.completed_by && <span>· done by {task.completed_by.slice(0, 8)}</span>}
        </div>
      </div>
      {isManager && (
        <RowActions>
          <Button variant="ghostDestructive" size="iconSm" onClick={() => onDelete(task)} icon={Trash2} title="Delete task" data-testid={`task-delete-${task.id}`} />
        </RowActions>
      )}
    </div>
  );
}

function TasksPanel({ headers, isManager, staffList }) {
  const [date, setDate] = useState(todayISO());
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [composing, setComposing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/staffing/tasks`, { headers, params: { date } });
      setTasks(data.tasks || []);
    } catch { /* noop */ }
    setLoading(false);
  }, [headers, date]);

  useEffect(() => { load(); }, [load]);

  const create = async (payload) => {
    try {
      await axios.post(`${API}/staffing/tasks`, payload, { headers });
      setComposing(false);
      load();
    } catch (e) { window.alert(e.response?.data?.detail || 'Create failed'); }
  };
  const complete = async (task) => {
    if (task.requires_photo) {
      const url = window.prompt('Paste photo URL (Phase S4 MVP — full upload pipeline lands later):');
      if (!url) return;
      try { await axios.post(`${API}/staffing/tasks/${task.id}/complete`, { photo_url: url }, { headers }); load(); }
      catch (e) { window.alert(e.response?.data?.detail || 'Complete failed'); }
      return;
    }
    try { await axios.post(`${API}/staffing/tasks/${task.id}/complete`, {}, { headers }); load(); }
    catch (e) { window.alert(e.response?.data?.detail || 'Complete failed'); }
  };
  const uncomplete = async (task) => {
    try { await axios.post(`${API}/staffing/tasks/${task.id}/uncomplete`, {}, { headers }); load(); }
    catch (e) { window.alert(e.response?.data?.detail || 'Undo failed'); }
  };
  const remove = async (task) => {
    if (!window.confirm(`Delete "${task.title}"?`)) return;
    try { await axios.delete(`${API}/staffing/tasks/${task.id}`, { headers }); load(); }
    catch (e) { window.alert(e.response?.data?.detail || 'Delete failed'); }
  };
  const materialise = async () => {
    try {
      const { data } = await axios.post(`${API}/staffing/tasks/materialise`, { date }, { headers });
      window.alert(`Created ${data.created} recurring instances · skipped ${data.skipped}.`);
      load();
    } catch (e) { window.alert(e.response?.data?.detail || 'Failed'); }
  };

  const open = tasks.filter((t) => t.status !== 'completed');
  const done = tasks.filter((t) => t.status === 'completed');

  return (
    <div className="space-y-3" data-testid="tasks-panel">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
            className="h-8 rounded-md bg-transparent border px-2 text-xs"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="tasks-date" />
          <span className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{open.length} open · {done.length} done</span>
        </div>
        {isManager && (
          <div className="flex gap-2">
            <button type="button" onClick={materialise}
              className="h-8 inline-flex items-center gap-1.5 rounded-full border px-3 text-xs font-bold"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid="tasks-materialise">
              <RefreshCw size={11} /> Generate recurring
            </button>
            <button type="button" onClick={() => setComposing(true)}
              className="h-8 rounded-full px-3 text-xs font-bold inline-flex items-center gap-1.5"
              style={{ background: 'var(--color-brand-cyan)', color: '#001219' }} data-testid="tasks-new">
              <Plus size={11} /> New task
            </button>
          </div>
        )}
      </div>
      {loading ? (
        <div className="py-6 inline-flex items-center gap-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}>
          <Loader2 size={14} className="animate-spin" /> Loading…
        </div>
      ) : (
        <>
          <div className="space-y-2 group">
            {open.length === 0 && (
              <p className="text-xs py-3" style={{ color: 'var(--theme-text-muted)' }}>No open tasks for this date.</p>
            )}
            {open.map((t) => (
              <TaskRow key={t.id} task={t} isManager={isManager} staffList={staffList}
                onComplete={complete} onUncomplete={uncomplete} onDelete={remove} />
            ))}
          </div>
          {done.length > 0 && (
            <details className="space-y-2">
              <summary className="text-[11px] font-bold uppercase tracking-wider cursor-pointer" style={{ color: 'var(--theme-text-muted)' }}>
                {done.length} completed
              </summary>
              <div className="space-y-2 mt-2">
                {done.map((t) => (
                  <TaskRow key={t.id} task={t} isManager={isManager} staffList={staffList}
                    onComplete={complete} onUncomplete={uncomplete} onDelete={remove} />
                ))}
              </div>
            </details>
          )}
        </>
      )}
      <TaskComposer open={composing} onClose={() => setComposing(false)} onSubmit={create} headers={headers} staffList={staffList} />
    </div>
  );
}

// ─────────────────────────── FORMS ───────────────────────────────

function FormFieldEditor({ field, onChange, onRemove }) {
  return (
    <div className="rounded-md border p-2 space-y-1.5" style={{ borderColor: 'var(--theme-border)' }} data-testid={`field-edit-${field.id || 'new'}`}>
      <div className="flex items-center gap-2">
        <select value={field.kind} onChange={(e) => onChange({ ...field, kind: e.target.value })}
          className="h-8 rounded-md bg-transparent border px-2 text-xs"
          style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}>
          {['text', 'long_text', 'number', 'select', 'checkbox', 'date', 'signature', 'photo'].map((k) =>
            <option key={k} value={k}>{k}</option>
          )}
        </select>
        <input value={field.label} onChange={(e) => onChange({ ...field, label: e.target.value })}
          placeholder="Question"
          className="flex-1 h-8 rounded-md bg-transparent border px-2 text-xs"
          style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} />
        <label className="text-[10px] inline-flex items-center gap-1" style={{ color: 'var(--theme-text-muted)' }}>
          <input type="checkbox" checked={field.required} onChange={(e) => onChange({ ...field, required: e.target.checked })} />
          Req
        </label>
        <button type="button" onClick={onRemove} className="w-6 h-6 inline-flex items-center justify-center" style={{ color: 'var(--theme-text-muted)' }}><X size={11} /></button>
      </div>
      {field.kind === 'select' && (
        <input value={(field.options || []).join(', ')} onChange={(e) => onChange({ ...field, options: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
          placeholder="Options, comma-separated"
          className="w-full h-7 rounded-md bg-transparent border px-2 text-xs"
          style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} />
      )}
    </div>
  );
}

function FormBuilder({ open, onClose, onSubmit, initial }) {
  const [name, setName] = useState(initial?.name || '');
  const [description, setDescription] = useState(initial?.description || '');
  const [fields, setFields] = useState(initial?.fields || []);
  if (!open) return null;
  const addField = () => setFields((fs) => [...fs, { id: null, kind: 'text', label: '', required: false }]);
  const updateField = (i, f) => setFields((fs) => fs.map((x, idx) => idx === i ? f : x));
  const removeField = (i) => setFields((fs) => fs.filter((_, idx) => idx !== i));
  const submit = () => {
    if (!name.trim()) { window.alert('Name required'); return; }
    if (fields.some((f) => !f.label.trim())) { window.alert('All fields need a label'); return; }
    onSubmit({ name: name.trim(), description: description.trim() || null, fields });
  };
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-end sm:items-center justify-center p-0 sm:p-4" data-testid="form-builder">
      <div className="w-full sm:max-w-2xl rounded-t-2xl sm:rounded-2xl p-5 space-y-3 max-h-[90vh] overflow-y-auto"
        style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}>
        <div className="flex items-center justify-between">
          <h4 className="text-base font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{initial?.id ? 'Edit form' : 'New form'}</h4>
          <button type="button" onClick={onClose} className="w-7 h-7" style={{ color: 'var(--theme-text-muted)' }}><X size={14} /></button>
        </div>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Form name"
          className="w-full h-9 rounded-md bg-transparent border px-2 text-sm"
          style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="form-name" />
        <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description (optional)"
          className="w-full h-9 rounded-md bg-transparent border px-2 text-sm"
          style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} />
        <div className="space-y-2" data-testid="form-fields">
          {fields.length === 0 && <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>No fields yet — add one below.</p>}
          {fields.map((f, i) => (
            <FormFieldEditor key={i} field={f} onChange={(nf) => updateField(i, nf)} onRemove={() => removeField(i)} />
          ))}
        </div>
        <button type="button" onClick={addField}
          className="h-8 rounded-full border px-3 text-xs font-bold inline-flex items-center gap-1"
          style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid="form-add-field">
          <Plus size={11} /> Add field
        </button>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="h-9 rounded-full border px-4 text-xs font-bold"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>Cancel</button>
          <button type="button" onClick={submit}
            className="h-9 rounded-full px-4 text-xs font-bold inline-flex items-center gap-1.5"
            style={{ background: 'var(--color-brand-cyan)', color: '#001219' }} data-testid="form-save">
            <Check size={11} /> Save form
          </button>
        </div>
      </div>
    </div>
  );
}

function FormSubmitDialog({ open, template, onClose, onSubmit }) {
  const [values, setValues] = useState({});
  if (!open || !template) return null;
  const set = (id, v) => setValues((s) => ({ ...s, [id]: v }));
  const submit = () => onSubmit(values);
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-end sm:items-center justify-center p-0 sm:p-4" data-testid="form-submit-dialog">
      <div className="w-full sm:max-w-lg rounded-t-2xl sm:rounded-2xl p-5 space-y-3 max-h-[90vh] overflow-y-auto"
        style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: 'var(--color-brand-cyan)' }}>Submit</p>
            <h4 className="text-base font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{template.name}</h4>
          </div>
          <button type="button" onClick={onClose} className="w-7 h-7" style={{ color: 'var(--theme-text-muted)' }}><X size={14} /></button>
        </div>
        {template.description && <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{template.description}</p>}
        {template.fields.map((f) => (
          <div key={f.id} className="space-y-1">
            <label className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>
              {f.label} {f.required && <span style={{ color: '#EF4444' }}>*</span>}
            </label>
            {f.kind === 'long_text' ? (
              <textarea value={values[f.id] || ''} onChange={(e) => set(f.id, e.target.value)} rows={3}
                className="w-full rounded-md bg-transparent border px-2 py-1.5 text-sm"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid={`form-input-${f.id}`} />
            ) : f.kind === 'select' ? (
              <select value={values[f.id] || ''} onChange={(e) => set(f.id, e.target.value)}
                className="w-full h-9 rounded-md bg-transparent border px-2 text-sm"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid={`form-input-${f.id}`}>
                <option value="">— pick —</option>
                {(f.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            ) : f.kind === 'checkbox' ? (
              <input type="checkbox" checked={!!values[f.id]} onChange={(e) => set(f.id, e.target.checked)} data-testid={`form-input-${f.id}`} />
            ) : (
              <input type={f.kind === 'date' ? 'date' : f.kind === 'number' ? 'number' : 'text'}
                value={values[f.id] || ''} onChange={(e) => set(f.id, e.target.value)}
                className="w-full h-9 rounded-md bg-transparent border px-2 text-sm"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid={`form-input-${f.id}`} />
            )}
          </div>
        ))}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="h-9 rounded-full border px-4 text-xs font-bold"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>Cancel</button>
          <button type="button" onClick={submit}
            className="h-9 rounded-full px-4 text-xs font-bold inline-flex items-center gap-1.5"
            style={{ background: 'var(--color-brand-cyan)', color: '#001219' }} data-testid="form-submit-btn">
            <Send size={11} /> Submit
          </button>
        </div>
      </div>
    </div>
  );
}

function FormsPanel({ headers, isManager }) {
  const [templates, setTemplates] = useState([]);
  const [submissions, setSubmissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [building, setBuilding] = useState(null); // null | {} (new) | template (edit)
  const [submitting, setSubmitting] = useState(null); // template
  const [showSubs, setShowSubs] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [t, s] = await Promise.all([
        axios.get(`${API}/staffing/forms/templates`, { headers }),
        axios.get(`${API}/staffing/forms/submissions`, { headers }),
      ]);
      setTemplates(t.data.templates || []);
      setSubmissions(s.data.submissions || []);
    } catch { /* noop */ }
    setLoading(false);
  }, [headers]);
  useEffect(() => { load(); }, [load]);

  const saveTemplate = async (payload) => {
    try {
      if (building?.id) {
        await axios.patch(`${API}/staffing/forms/templates/${building.id}`, payload, { headers });
      } else {
        await axios.post(`${API}/staffing/forms/templates`, payload, { headers });
      }
      setBuilding(null); load();
    } catch (e) { window.alert(e.response?.data?.detail || 'Save failed'); }
  };
  const remove = async (t) => {
    if (!window.confirm(`Delete form "${t.name}"?`)) return;
    try { await axios.delete(`${API}/staffing/forms/templates/${t.id}`, { headers }); load(); }
    catch (e) { window.alert(e.response?.data?.detail || 'Delete failed'); }
  };
  const submitForm = async (values) => {
    try {
      await axios.post(`${API}/staffing/forms/templates/${submitting.id}/submit`, { values }, { headers });
      setSubmitting(null);
      window.alert('Submitted!');
      load();
    } catch (e) { window.alert(e.response?.data?.detail || 'Submit failed'); }
  };

  return (
    <div className="space-y-3" data-testid="forms-panel">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{templates.length} templates · {submissions.length} submissions</p>
        <div className="flex gap-2">
          <button type="button" onClick={() => setShowSubs((v) => !v)}
            className="h-8 rounded-full border px-3 text-xs font-bold"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid="forms-toggle-subs">
            {showSubs ? 'Hide' : 'Show'} submissions
          </button>
          {isManager && (
            <button type="button" onClick={() => setBuilding({})}
              className="h-8 rounded-full px-3 text-xs font-bold inline-flex items-center gap-1.5"
              style={{ background: 'var(--color-brand-cyan)', color: '#001219' }} data-testid="forms-new">
              <Plus size={11} /> New form
            </button>
          )}
        </div>
      </div>
      {loading ? (
        <div className="py-6 inline-flex items-center gap-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}>
          <Loader2 size={14} className="animate-spin" /> Loading…
        </div>
      ) : showSubs ? (
        <div className="space-y-2">
          {submissions.length === 0 && <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>No submissions yet.</p>}
          {submissions.map((s) => (
            <details key={s.id} className="rounded-lg border p-3" style={{ borderColor: 'var(--theme-border)' }} data-testid={`submission-${s.id}`}>
              <summary className="cursor-pointer flex items-center justify-between text-xs">
                <span><strong style={{ color: 'var(--theme-text)' }}>{s.template_name_snapshot}</strong> · {s.submitted_by}</span>
                <span style={{ color: 'var(--theme-text-muted)' }}>{(s.submitted_at || '').slice(0, 16).replace('T', ' ')}</span>
              </summary>
              <pre className="text-[11px] mt-2 whitespace-pre-wrap break-words" style={{ color: 'var(--theme-text-muted)' }}>{JSON.stringify(s.values, null, 2)}</pre>
            </details>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {templates.length === 0 && (
            <p className="col-span-full text-xs" style={{ color: 'var(--theme-text-muted)' }}>
              No forms yet — {isManager ? 'create one to get started.' : 'check back later.'}
            </p>
          )}
          {templates.map((t) => (
            <div key={t.id} className="rounded-xl border p-3 flex flex-col gap-2"
              style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid={`form-template-${t.id}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-bold truncate" style={{ color: 'var(--theme-text)' }}>{t.name}</p>
                  <p className="text-[10px] mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
                    {t.fields.length} field{t.fields.length === 1 ? '' : 's'}
                  </p>
                </div>
                <FileText size={14} style={{ color: 'var(--color-brand-cyan)' }} />
              </div>
              {t.description && <p className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>{t.description}</p>}
              <div className="flex gap-1.5 mt-auto pt-1">
                <button type="button" onClick={() => setSubmitting(t)}
                  className="flex-1 h-8 rounded-full text-[11px] font-bold inline-flex items-center justify-center gap-1"
                  style={{ background: 'var(--color-brand-cyan)', color: '#001219' }} data-testid={`form-submit-${t.id}`}>
                  <Send size={11} /> Fill in
                </button>
                {isManager && (
                  <>
                    <button type="button" onClick={() => setBuilding(t)}
                      className="h-8 w-8 rounded-full border inline-flex items-center justify-center"
                      style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid={`form-edit-${t.id}`}>
                      <Pencil size={11} />
                    </button>
                    <button type="button" onClick={() => remove(t)}
                      className="h-8 w-8 rounded-full border inline-flex items-center justify-center"
                      style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid={`form-delete-${t.id}`}>
                      <Trash2 size={11} />
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      <FormBuilder open={!!building} initial={building?.id ? building : null} onClose={() => setBuilding(null)} onSubmit={saveTemplate} />
      <FormSubmitDialog open={!!submitting} template={submitting} onClose={() => setSubmitting(null)} onSubmit={submitForm} />
    </div>
  );
}

// ─────────────────────────── COMPLIANCE ───────────────────────────

function CertEditor({ open, onClose, onSubmit, staffList, initial }) {
  const [form, setForm] = useState(initial || {
    staff_id: staffList[0]?.id || '',
    cert_type: 'dbs',
    cert_number: '',
    expires_at: '',
    notes: '',
  });
  if (!open) return null;
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-end sm:items-center justify-center p-0 sm:p-4" data-testid="cert-editor">
      <div className="w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl p-5 space-y-3"
        style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}>
        <div className="flex items-center justify-between">
          <h4 className="text-base font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{initial ? 'Edit cert' : 'Add cert'}</h4>
          <button type="button" onClick={onClose} className="w-7 h-7" style={{ color: 'var(--theme-text-muted)' }}><X size={14} /></button>
        </div>
        {!initial && (
          <select value={form.staff_id} onChange={(e) => set('staff_id', e.target.value)}
            className="w-full h-9 rounded-md bg-transparent border px-2 text-sm"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="cert-staff">
            {staffList.map((s) => <option key={s.id} value={s.id}>{s.full_name}</option>)}
          </select>
        )}
        <input value={form.cert_type} onChange={(e) => set('cert_type', e.target.value)} placeholder="Cert type (e.g. dbs, first_aid)"
          className="w-full h-9 rounded-md bg-transparent border px-2 text-sm"
          style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="cert-type" />
        <input value={form.cert_number || ''} onChange={(e) => set('cert_number', e.target.value)} placeholder="Cert number (optional)"
          className="w-full h-9 rounded-md bg-transparent border px-2 text-sm"
          style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="cert-number" />
        <label className="block">
          <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>Expires</span>
          <input type="date" value={form.expires_at || ''} onChange={(e) => set('expires_at', e.target.value)}
            className="mt-1 w-full h-9 rounded-md bg-transparent border px-2 text-sm"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="cert-expires" />
        </label>
        <textarea value={form.notes || ''} onChange={(e) => set('notes', e.target.value)} placeholder="Notes" rows={2}
          className="w-full rounded-md bg-transparent border px-2 py-1.5 text-sm"
          style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} />
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onClose} className="h-9 rounded-full border px-4 text-xs font-bold"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>Cancel</button>
          <button type="button" onClick={() => onSubmit(form)}
            className="h-9 rounded-full px-4 text-xs font-bold inline-flex items-center gap-1.5"
            style={{ background: 'var(--color-brand-cyan)', color: '#001219' }} data-testid="cert-save">
            <Check size={11} /> Save
          </button>
        </div>
      </div>
    </div>
  );
}

function CompliancePanel({ headers, isManager, staffList }) {
  const [tracker, setTracker] = useState(null);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (isManager) {
        const { data } = await axios.get(`${API}/staffing/compliance/tracker`, { headers });
        setTracker(data);
      } else {
        const { data } = await axios.get(`${API}/staffing/compliance/certs`, { headers });
        setTracker({ buckets: { ok: data.certs }, summary: { ok: data.certs.length }, missing_staff: [], missing_count: 0 });
      }
    } catch { /* noop */ }
    setLoading(false);
  }, [headers, isManager]);
  useEffect(() => { load(); }, [load]);

  const create = async (form) => {
    try {
      await axios.post(`${API}/staffing/compliance/certs`, form, { headers });
      setAdding(false); load();
    } catch (e) { window.alert(e.response?.data?.detail || 'Save failed'); }
  };
  const update = async (form) => {
    try {
      await axios.patch(`${API}/staffing/compliance/certs/${form.id}`, {
        cert_number: form.cert_number, expires_at: form.expires_at, notes: form.notes,
      }, { headers });
      setEditing(null); load();
    } catch (e) { window.alert(e.response?.data?.detail || 'Save failed'); }
  };
  const remove = async (cert) => {
    if (!window.confirm(`Delete ${cert.cert_type} cert for ${cert.staff_name || ''}?`)) return;
    try { await axios.delete(`${API}/staffing/compliance/certs/${cert.id}`, { headers }); load(); }
    catch (e) { window.alert(e.response?.data?.detail || 'Delete failed'); }
  };

  if (loading) {
    return <div className="py-6 inline-flex items-center gap-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}><Loader2 size={14} className="animate-spin" /> Loading…</div>;
  }
  if (!tracker) return null;

  const renderBucket = (key) => {
    const meta = CERT_BANDS[key];
    const items = tracker.buckets?.[key] || [];
    if (items.length === 0) return null;
    return (
      <div key={key} className="space-y-1.5" data-testid={`bucket-${key}`}>
        <p className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: meta.tint }}>{meta.label} · {items.length}</p>
        <div className="space-y-1">
          {items.map((c) => (
            <div key={c.id} className="rounded-lg border p-2 flex items-center justify-between gap-2"
              style={{ borderColor: 'var(--theme-border)', background: meta.bg }}
              data-testid={`cert-${c.id}`}>
              <div className="min-w-0">
                <p className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>
                  {c.staff_name || c.staff_id?.slice(0, 8)} · <span className="opacity-80">{c.cert_type}</span>
                </p>
                <p className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>
                  {c.expires_at ? `Expires ${c.expires_at}` : 'No expiry set'}
                  {c.cert_number ? ` · #${c.cert_number}` : ''}
                </p>
              </div>
              {isManager && (
                <div className="flex gap-1">
                  <button type="button" onClick={() => setEditing(c)} className="w-7 h-7 rounded-full border inline-flex items-center justify-center"
                    style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid={`cert-edit-${c.id}`}>
                    <Pencil size={10} />
                  </button>
                  <button type="button" onClick={() => remove(c)} className="w-7 h-7 rounded-full border inline-flex items-center justify-center"
                    style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid={`cert-delete-${c.id}`}>
                    <Trash2 size={10} />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4" data-testid="compliance-panel">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-3 flex-wrap text-xs" style={{ color: 'var(--theme-text-muted)' }}>
          {Object.entries(CERT_BANDS).map(([k, meta]) => (
            <span key={k} className="inline-flex items-center gap-1" data-testid={`cert-summary-${k}`}>
              <span className="w-2 h-2 rounded-full" style={{ background: meta.tint }} />
              {tracker.summary?.[k] || 0} {meta.label.toLowerCase()}
            </span>
          ))}
        </div>
        {isManager && (
          <button type="button" onClick={() => setAdding(true)}
            className="h-8 rounded-full px-3 text-xs font-bold inline-flex items-center gap-1.5"
            style={{ background: 'var(--color-brand-cyan)', color: '#001219' }} data-testid="cert-new">
            <Plus size={11} /> Add cert
          </button>
        )}
      </div>
      <div className="space-y-3">
        {['expired', 'expiring_30', 'expiring_90', 'unknown', 'ok'].map((k) => renderBucket(k))}
        {(tracker.summary?.expired || 0) === 0 &&
         (tracker.summary?.expiring_30 || 0) === 0 &&
         (tracker.summary?.expiring_90 || 0) === 0 &&
         (tracker.summary?.ok || 0) === 0 && (
          <p className="text-xs py-3 text-center" style={{ color: 'var(--theme-text-muted)' }}>
            No certs tracked yet. Add the first one with the button above.
          </p>
        )}
      </div>
      {isManager && tracker.missing_count > 0 && (
        <div className="rounded-lg border p-3" style={{ borderColor: 'var(--theme-border)', background: 'rgba(245,158,11,0.05)' }} data-testid="missing-staff">
          <p className="text-[10px] uppercase tracking-[0.14em] font-bold inline-flex items-center gap-1" style={{ color: '#F59E0B' }}>
            <AlertTriangle size={11} /> {tracker.missing_count} staff have no certs on file
          </p>
          <p className="text-[11px] mt-1" style={{ color: 'var(--theme-text-muted)' }}>
            {(tracker.missing_staff || []).map((m) => m.staff_name).filter(Boolean).slice(0, 6).join(', ')}
            {tracker.missing_count > 6 && ' …'}
          </p>
        </div>
      )}
      <CertEditor open={adding} onClose={() => setAdding(false)} onSubmit={create} staffList={staffList} />
      <CertEditor open={!!editing} initial={editing || undefined} onClose={() => setEditing(null)} onSubmit={update} staffList={staffList} />
    </div>
  );
}

// ─────────────────────────── HUB ───────────────────────────────

export default function OperationsTab({ headers, isManager }) {
  const [sub, setSub] = useState(() => localStorage.getItem('staffing.ops.sub') || 'tasks');
  const [staffList, setStaffList] = useState([]);

  useEffect(() => { localStorage.setItem('staffing.ops.sub', sub); }, [sub]);

  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/staffing/staff`, { headers })
      .then((r) => { if (!cancelled) setStaffList(r.data.staff || []); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [headers]);

  return (
    <div className="space-y-4" data-testid="operations-tab">
      <div className="flex items-center gap-2 flex-wrap">
        <ClipboardList size={14} style={{ color: 'var(--color-brand-cyan)' }} />
        <p className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: 'var(--color-brand-cyan)' }}>Phase S4 · Tasks · Forms · Compliance</p>
      </div>
      <div className="inline-flex rounded-full border overflow-hidden" style={{ borderColor: 'var(--theme-border)' }}>
        {SUB_TABS.map((s) => {
          const Icon = s.icon;
          const on = sub === s.id;
          return (
            <button key={s.id} type="button" onClick={() => setSub(s.id)}
              className="h-8 px-3 text-xs font-bold inline-flex items-center gap-1.5 transition-colors"
              style={{
                background: on ? 'var(--color-brand-cyan)' : 'transparent',
                color: on ? '#001219' : 'var(--theme-text-muted)',
                borderLeft: s.id !== SUB_TABS[0].id ? '1px solid var(--theme-border)' : 'none',
              }}
              data-testid={`ops-sub-${s.id}`}>
              <Icon size={11} /> {s.label}
            </button>
          );
        })}
      </div>
      {sub === 'tasks'      && <TasksPanel headers={headers} isManager={isManager} staffList={staffList} />}
      {sub === 'forms'      && <FormsPanel headers={headers} isManager={isManager} />}
      {sub === 'compliance' && <CompliancePanel headers={headers} isManager={isManager} staffList={staffList} />}
    </div>
  );
}
