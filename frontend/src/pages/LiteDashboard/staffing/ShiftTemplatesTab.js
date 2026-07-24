/**
 * Phase S1 — Shift Templates tab.
 *
 * CRUD for reusable shift definitions. Each template captures:
 *   name · role · start_time · end_time · break · weekdays · colour
 *   · default_staff_id (optional) · notes
 *
 * From the list view, managers can:
 *   • Create / edit / delete templates
 *   • "Apply" a template across a date range in one click — this
 *     materialises one shift per weekday-matching date via
 *     POST /api/staffing/shift-templates/{id}/apply
 *
 * The "apply" action shows a small drawer with a date-range picker
 * and an optional staff override so operators can stamp the same
 * template for different people without cloning it.
 */
import { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import {
  Plus, Clock, Pencil, Trash2, X, Check, Calendar as CalIcon, Loader2, Layers,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const ROLES = ['instructor', 'pt', 'manager', 'reception', 'cleaner', 'maintenance', 'lifeguard', 'duty_manager', 'other'];
const WEEKDAYS = [
  { i: 0, s: 'Mon' }, { i: 1, s: 'Tue' }, { i: 2, s: 'Wed' },
  { i: 3, s: 'Thu' }, { i: 4, s: 'Fri' }, { i: 5, s: 'Sat' }, { i: 6, s: 'Sun' },
];
const EMPTY = {
  name: '', role: 'reception', start_time: '09:00', end_time: '17:00',
  break_minutes: 30, weekdays: [0, 1, 2, 3, 4], colour: '#19CDFF',
  default_staff_id: null, notes: '',
};

function WeekdayToggles({ value, onChange, testId }) {
  const toggle = (i) => {
    const set = new Set(value);
    if (set.has(i)) set.delete(i); else set.add(i);
    onChange([...set].sort((a, b) => a - b));
  };
  return (
    <div className="inline-flex rounded-full overflow-hidden border" style={{ borderColor: 'var(--theme-border)' }} data-testid={testId}>
      {WEEKDAYS.map(({ i, s }) => {
        const on = value.includes(i);
        return (
          <button
            key={i}
            type="button"
            onClick={() => toggle(i)}
            className="px-2.5 h-8 text-[10px] font-bold uppercase tracking-wider transition-colors"
            style={{
              background: on ? 'var(--color-brand-cyan)' : 'transparent',
              color: on ? '#001219' : 'var(--theme-text-muted)',
              borderLeft: i > 0 ? '1px solid var(--theme-border)' : 'none',
            }}
            data-testid={`${testId}-${s.toLowerCase()}`}
          >
            {s}
          </button>
        );
      })}
    </div>
  );
}

function TemplateEditor({ initial, staff, onSave, onCancel, saving }) {
  const { t } = useTranslation();
  const [form, setForm] = useState({ ...EMPTY, ...(initial || {}) });
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = () => {
    if (!form.name.trim()) { window.alert(t('staffing.tpl_name_required', 'Name is required')); return; }
    if (!form.weekdays?.length) { window.alert(t('staffing.tpl_weekday_required', 'Pick at least one weekday')); return; }
    if (form.start_time >= form.end_time) { window.alert(t('staffing.tpl_time_order', 'End time must be after start time')); return; }
    const payload = { ...form, name: form.name.trim(), break_minutes: Number(form.break_minutes) || 0 };
    onSave(payload);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-4" data-testid="template-editor">
      <div className="w-full sm:max-w-2xl rounded-t-2xl sm:rounded-2xl p-5 space-y-3 max-h-[90vh] overflow-y-auto shadow-2xl"
        style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}>
        <div className="flex items-center justify-between">
          <h4 className="text-base font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>
            {initial?.id ? t('staffing.tpl_edit', 'Edit template') : t('staffing.tpl_new', 'New shift template')}
          </h4>
          <button type="button" onClick={onCancel} className="w-7 h-7 rounded-full inline-flex items-center justify-center" style={{ color: 'var(--theme-text-muted)' }}>
            <X size={14} />
          </button>
        </div>

        <div className="grid grid-cols-1 gap-3">
          <label className="block">
            <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.tpl_name', 'Name')}</span>
            <input
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
              placeholder={t('staffing.tpl_name_ph', 'e.g. Morning Reception')}
              className="mt-1 w-full h-9 rounded-md bg-transparent border px-2 text-sm"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
              data-testid="template-editor-name"
            />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.tpl_role', 'Role')}</span>
              <select
                value={form.role}
                onChange={(e) => set('role', e.target.value)}
                className="mt-1 w-full h-9 rounded-md bg-transparent border px-2 text-sm"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                data-testid="template-editor-role"
              >
                {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.tpl_break', 'Break (min)')}</span>
              <input
                type="number"
                min="0"
                value={form.break_minutes}
                onChange={(e) => set('break_minutes', e.target.value)}
                className="mt-1 w-full h-9 rounded-md bg-transparent border px-2 text-sm"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                data-testid="template-editor-break"
              />
            </label>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.tpl_start', 'Start')}</span>
              <input
                type="time"
                value={form.start_time}
                onChange={(e) => set('start_time', e.target.value)}
                className="mt-1 w-full h-9 rounded-md bg-transparent border px-2 text-sm"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                data-testid="template-editor-start"
              />
            </label>
            <label className="block">
              <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.tpl_end', 'End')}</span>
              <input
                type="time"
                value={form.end_time}
                onChange={(e) => set('end_time', e.target.value)}
                className="mt-1 w-full h-9 rounded-md bg-transparent border px-2 text-sm"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                data-testid="template-editor-end"
              />
            </label>
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.tpl_weekdays', 'Weekdays')}</span>
            <div className="mt-1">
              <WeekdayToggles value={form.weekdays || []} onChange={(wd) => set('weekdays', wd)} testId="template-editor-weekdays" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.tpl_default_staff', 'Default staff')}</span>
              <select
                value={form.default_staff_id || ''}
                onChange={(e) => set('default_staff_id', e.target.value || null)}
                className="mt-1 w-full h-9 rounded-md bg-transparent border px-2 text-sm"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
                data-testid="template-editor-staff"
              >
                <option value="">{t('staffing.tpl_open_shift', '— Open shift —')}</option>
                {staff.map((s) => <option key={s.id} value={s.id}>{s.full_name}</option>)}
              </select>
            </label>
            <label className="block">
              <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.tpl_colour', 'Colour')}</span>
              <input
                type="color"
                value={form.colour || '#19CDFF'}
                onChange={(e) => set('colour', e.target.value)}
                className="mt-1 w-full h-9 rounded-md bg-transparent border px-1 text-sm"
                style={{ borderColor: 'var(--theme-border)' }}
                data-testid="template-editor-colour"
              />
            </label>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 pt-2">
          <button type="button" onClick={onCancel} className="h-9 rounded-full border px-4 text-xs font-bold" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid="template-editor-cancel">
            {t('staffing.tpl_cancel', 'Cancel')}
          </button>
          <button type="button" onClick={submit} disabled={saving} className="h-9 rounded-full px-4 text-xs font-bold inline-flex items-center gap-1.5 disabled:opacity-60"
            style={{ background: 'var(--color-brand-cyan)', color: '#001219' }} data-testid="template-editor-save">
            {saving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
            {saving ? t('staffing.tpl_saving', 'Saving…') : t('staffing.tpl_save', 'Save template')}
          </button>
        </div>
      </div>
    </div>
  );
}

function ApplyDialog({ template, staff, onCancel, onApply, applying }) {
  const { t } = useTranslation();
  const today = new Date();
  const weekMonday = new Date(today);
  weekMonday.setDate(today.getDate() - ((today.getDay() + 6) % 7));
  const nextSunday = new Date(weekMonday);
  nextSunday.setDate(weekMonday.getDate() + 6);
  const [start, setStart] = useState(weekMonday.toISOString().slice(0, 10));
  const [end, setEnd] = useState(nextSunday.toISOString().slice(0, 10));
  const [staffId, setStaffId] = useState(template.default_staff_id || '');
  const [skipExisting, setSkipExisting] = useState(true);

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-end sm:items-center justify-center p-0 sm:p-4" data-testid="apply-dialog">
      <div className="w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl p-5 space-y-3"
        style={{ background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' }}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: 'var(--color-brand-cyan)' }}>{t('staffing.tpl_apply', 'Apply template')}</p>
            <h4 className="text-base font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{template.name}</h4>
          </div>
          <button type="button" onClick={onCancel} className="w-7 h-7 rounded-full inline-flex items-center justify-center" style={{ color: 'var(--theme-text-muted)' }}><X size={14} /></button>
        </div>
        <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
          {t('staffing.tpl_apply_desc', 'Will create one shift per matching weekday (')}
          {(template.weekdays || []).map((d) => WEEKDAYS[d]?.s).join(', ')}
          {t('staffing.tpl_apply_desc2', ') between the dates below.')}
        </p>
        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.tpl_start_date', 'Start date')}</span>
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)}
              className="mt-1 w-full h-9 rounded-md bg-transparent border px-2 text-sm"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="apply-start" />
          </label>
          <label className="block">
            <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.tpl_end_date', 'End date')}</span>
            <input type="date" value={end} onChange={(e) => setEnd(e.target.value)}
              className="mt-1 w-full h-9 rounded-md bg-transparent border px-2 text-sm"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="apply-end" />
          </label>
        </div>
        <label className="block">
          <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{t('staffing.tpl_assign_to', 'Assign to')}</span>
          <select value={staffId} onChange={(e) => setStaffId(e.target.value)}
            className="mt-1 w-full h-9 rounded-md bg-transparent border px-2 text-sm"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="apply-staff">
            <option value="">{t('staffing.tpl_leave_open', '— Leave open —')}</option>
            {staff.map((s) => <option key={s.id} value={s.id}>{s.full_name}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}>
          <input type="checkbox" checked={skipExisting} onChange={(e) => setSkipExisting(e.target.checked)} data-testid="apply-skip" />
          {t('staffing.tpl_skip_existing', 'Skip days where a matching shift already exists')}
        </label>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onCancel} className="h-9 rounded-full border px-4 text-xs font-bold" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid="apply-cancel">
            {t('staffing.tpl_cancel', 'Cancel')}
          </button>
          <button type="button" disabled={applying}
            onClick={() => onApply({ start_date: start, end_date: end, staff_id: staffId || null, skip_existing: skipExisting })}
            className="h-9 rounded-full px-4 text-xs font-bold inline-flex items-center gap-1.5 disabled:opacity-60"
            style={{ background: 'var(--color-brand-cyan)', color: '#001219' }} data-testid="apply-confirm">
            {applying ? <Loader2 size={12} className="animate-spin" /> : <CalIcon size={12} />}
            {applying ? t('staffing.tpl_applying', 'Applying…') : t('staffing.tpl_apply_btn', 'Apply')}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ShiftTemplatesTab({ headers, isManager }) {
  const { t } = useTranslation();
  const [templates, setTemplates] = useState([]);
  const [staff, setStaff] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);     // { ...tpl } or {} for new
  const [applying, setApplying] = useState(null);   // template doc
  const [saving, setSaving] = useState(false);
  const [applyBusy, setApplyBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [tRes, sRes] = await Promise.all([
        axios.get(`${API}/staffing/shift-templates`, { headers }),
        axios.get(`${API}/staffing/staff`, { headers }),
      ]);
      setTemplates(tRes.data.templates || []);
      setStaff(sRes.data.staff || []);
    } catch { /* noop */ }
    setLoading(false);
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const save = async (form) => {
    setSaving(true);
    try {
      if (editing?.id) {
        await axios.patch(`${API}/staffing/shift-templates/${editing.id}`, form, { headers });
      } else {
        await axios.post(`${API}/staffing/shift-templates`, form, { headers });
      }
      setEditing(null);
      load();
    } catch (e) { window.alert(e.response?.data?.detail || t('staffing.tpl_save_failed', 'Failed to save')); }
    setSaving(false);
  };

  const remove = async (tpl) => {
    if (!window.confirm(`${t('staffing.tpl_delete_confirm', 'Delete template')} "${tpl.name}"?`)) return;
    try {
      await axios.delete(`${API}/staffing/shift-templates/${tpl.id}`, { headers });
      load();
    } catch (e) { window.alert(e.response?.data?.detail || t('staffing.tpl_delete_failed', 'Failed to delete')); }
  };

  const apply = async (payload) => {
    setApplyBusy(true);
    try {
      const { data } = await axios.post(`${API}/staffing/shift-templates/${applying.id}/apply`, payload, { headers });
      setApplying(null);
      window.alert(`${t('staffing.tpl_applied', 'Applied')}: ${data.created} ${data.created === 1 ? t('staffing.tpl_shift', 'shift') : t('staffing.tpl_shifts', 'shifts')} ${t('staffing.tpl_created', 'created')} · ${data.skipped} ${t('staffing.tpl_skipped', 'skipped')}.`);
    } catch (e) { window.alert(e.response?.data?.detail || t('staffing.tpl_apply_failed', 'Failed to apply')); }
    setApplyBusy(false);
  };

  return (
    <div className="space-y-4" data-testid="shift-templates-tab">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <p className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: 'var(--color-brand-cyan)' }}>{t('staffing.tpl_reusable', 'Reusable shifts')}</p>
          <h3 className="text-base font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{t('staffing.tpl_title', 'Shift templates')}</h3>
        </div>
        {isManager && (
          <button type="button" onClick={() => setEditing({})}
            className="h-9 rounded-full px-4 text-xs font-bold inline-flex items-center gap-1.5"
            style={{ background: 'var(--color-brand-cyan)', color: '#001219' }}
            data-testid="template-new">
            <Plus size={12} /> {t('staffing.tpl_new_btn', 'New template')}
          </button>
        )}
      </div>

      {loading && (
        <div className="py-6 inline-flex items-center gap-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}>
          <Loader2 size={14} className="animate-spin" /> {t('staffing.tpl_loading', 'Loading…')}
        </div>
      )}

      {!loading && templates.length === 0 && (
        <div className="rounded-xl border p-6 text-center" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="templates-empty">
          <Layers size={20} className="mx-auto mb-2" style={{ color: 'var(--theme-text-muted)' }} />
          <p className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>{t('staffing.tpl_none', 'No templates yet')}</p>
          <p className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>
            {t('staffing.tpl_none_desc', 'Create a template for each repeating shift (e.g. Morning Reception, Saturday Lifeguard) and stamp them across the rota in one click.')}
          </p>
        </div>
      )}

      {!loading && templates.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {templates.map((tpl) => {
            const owner = staff.find((s) => s.id === tpl.default_staff_id);
            return (
              <div key={tpl.id}
                className="rounded-xl border p-4 space-y-2"
                style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}
                data-testid={`template-${tpl.id}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-bold truncate" style={{ color: 'var(--theme-text)' }}>{tpl.name}</p>
                    <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{tpl.role}</p>
                  </div>
                  <span className="w-4 h-4 rounded shrink-0" style={{ background: tpl.colour || '#19CDFF' }} />
                </div>
                <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}>
                  <Clock size={11} /> {tpl.start_time}–{tpl.end_time}
                  {tpl.break_minutes ? <span>· {tpl.break_minutes}{t('staffing.tpl_break_short', 'm break')}</span> : null}
                </div>
                <div className="flex flex-wrap gap-1">
                  {WEEKDAYS.map(({ i, s }) => (
                    <span key={i}
                      className="text-[9px] font-bold px-1.5 py-0.5 rounded"
                      style={{
                        background: (tpl.weekdays || []).includes(i) ? 'rgba(25,205,255,0.15)' : 'transparent',
                        color: (tpl.weekdays || []).includes(i) ? 'var(--color-brand-cyan)' : 'var(--theme-text-muted)',
                        border: '1px solid var(--theme-border)',
                      }}>
                      {s}
                    </span>
                  ))}
                </div>
                <p className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>
                  {owner ? `${t('staffing.tpl_default', 'Default')}: ${owner.full_name}` : t('staffing.tpl_creates_open', 'Creates as open shift')}
                </p>
                {isManager && (
                  <div className="flex gap-1.5 pt-1">
                    <button type="button" onClick={() => setApplying(tpl)}
                      className="flex-1 h-8 rounded-full text-[11px] font-bold inline-flex items-center justify-center gap-1"
                      style={{ background: 'var(--color-brand-cyan)', color: '#001219' }}
                      data-testid={`template-apply-${tpl.id}`}>
                      <CalIcon size={11} /> {t('staffing.tpl_apply_btn', 'Apply')}
                    </button>
                    <button type="button" onClick={() => setEditing(tpl)}
                      className="h-8 w-8 rounded-full border inline-flex items-center justify-center"
                      style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}
                      data-testid={`template-edit-${tpl.id}`} aria-label={t('staffing.tpl_edit_aria', 'Edit')}>
                      <Pencil size={11} />
                    </button>
                    <button type="button" onClick={() => remove(tpl)}
                      className="h-8 w-8 rounded-full border inline-flex items-center justify-center"
                      style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}
                      data-testid={`template-delete-${tpl.id}`} aria-label={t('staffing.tpl_delete_aria', 'Delete')}>
                      <Trash2 size={11} />
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {editing && createPortal((
        // Iter 216h264 — portal to document.body so the fixed inset-0
        // overlay covers the full viewport (parent has `transform` which
        // would otherwise create a new containing block for fixed and
        // leave a white 1/3 strip at the bottom of the screen).
        <TemplateEditor
          initial={editing.id ? editing : null}
          staff={staff}
          saving={saving}
          onSave={save}
          onCancel={() => setEditing(null)}
        />
      ), document.body)}
      {applying && createPortal((
        <ApplyDialog
          template={applying}
          staff={staff}
          applying={applyBusy}
          onApply={apply}
          onCancel={() => setApplying(null)}
        />
      ), document.body)}
    </div>
  );
}
