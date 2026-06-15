/** Modals + drawers for the Org Chart: add card, edit card, confirm move. */
import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { X, Trash2, Link2, UserPlus, Loader2 } from 'lucide-react';
import { humanize, NODE_LABELS, VACANCY_STAGES } from './api';

const overlay = {
  position: 'fixed', inset: 0, zIndex: 1000,
  background: 'rgba(2,12,40,0.45)', display: 'flex', justifyContent: 'flex-end',
};
const sheet = {
  width: 'min(420px, 100%)', height: '100%', overflowY: 'auto',
  background: 'var(--theme-surface, #fff)', boxShadow: '-12px 0 40px rgba(2,12,40,0.25)',
};
const center = { ...overlay, alignItems: 'center', justifyContent: 'center' };
const modalBox = {
  width: 'min(440px, 92vw)', borderRadius: 18, padding: 22,
  background: 'var(--theme-surface, #fff)', boxShadow: '0 20px 60px rgba(2,12,40,0.3)',
};

function Field({ label, children }) {
  return (
    <label className="block mb-3">
      <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

const inputCls = 'w-full px-3 py-2 rounded-lg text-sm border outline-none';
const inputStyle = { background: 'var(--theme-bg, #fff)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' };

// ─── Add card ───
export function AddNodeModal({ open, onClose, onCreate, staffOptions, sites, departments }) {
  const [type, setType] = useState('staff');
  const [staffId, setStaffId] = useState('');
  const [form, setForm] = useState({ full_name: '', job_title: '', department: '', site_id: '', employment_type: '' });
  const [saving, setSaving] = useState(false);

  useEffect(() => { if (open) { setType('staff'); setStaffId(''); setForm({ full_name: '', job_title: '', department: '', site_id: '', employment_type: '' }); } }, [open]);
  if (!open) return null;

  const submit = async () => {
    setSaving(true);
    const body = { type, ...form };
    if (type === 'staff' && staffId) body.staff_id = staffId;
    try { await onCreate(body); onClose(); } finally { setSaving(false); }
  };
  const canSave = type === 'staff' ? !!staffId : !!form.full_name.trim();

  return createPortal(
    <div style={center} onMouseDown={onClose}>
      <div style={modalBox} onMouseDown={(e) => e.stopPropagation()} data-testid="orgchart-add-modal">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-bold pulse-font-heading inline-flex items-center gap-2" style={{ color: 'var(--theme-text)' }}><UserPlus size={16} /> Add to chart</h3>
          <button onClick={onClose} data-testid="orgchart-add-close"><X size={18} style={{ color: 'var(--theme-text-muted)' }} /></button>
        </div>
        <Field label="Card type">
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(NODE_LABELS).map(([k, lbl]) => (
              <button key={k} onClick={() => setType(k)}
                className="px-3 py-1.5 rounded-full text-xs font-semibold border"
                style={type === k
                  ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', borderColor: 'var(--color-brand-cyan)' }
                  : { color: 'var(--theme-text-muted)', borderColor: 'var(--theme-border)' }}
                data-testid={`orgchart-add-type-${k}`}>{lbl}</button>
            ))}
          </div>
        </Field>

        {type === 'staff' ? (
          <Field label="Link an existing staff member">
            <select className={inputCls} style={inputStyle} value={staffId} onChange={(e) => setStaffId(e.target.value)} data-testid="orgchart-add-staff-select">
              <option value="">— Select staff —</option>
              {staffOptions.map((s) => (
                <option key={s.id} value={s.id}>{s.full_name} {s.primary_role ? `· ${humanize(s.primary_role)}` : ''}</option>
              ))}
            </select>
            {!staffOptions.length && <p className="text-[11px] mt-1" style={{ color: 'var(--theme-text-muted)' }}>Everyone is already on the chart.</p>}
          </Field>
        ) : (
          <>
            <Field label={type === 'vacancy' ? 'Role title' : 'Name'}>
              <input className={inputCls} style={inputStyle} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} data-testid="orgchart-add-name" placeholder={type === 'vacancy' ? 'e.g. Senior Field Engineer' : 'Full name'} />
            </Field>
            <Field label="Job title"><input className={inputCls} style={inputStyle} value={form.job_title} onChange={(e) => setForm({ ...form, job_title: e.target.value })} data-testid="orgchart-add-title" /></Field>
          </>
        )}

        <Field label="Department">
          <input className={inputCls} style={inputStyle} list="oc-depts" value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} data-testid="orgchart-add-dept" placeholder="e.g. Service & Aftersales" />
          <datalist id="oc-depts">{departments.map((d) => <option key={d} value={d} />)}</datalist>
        </Field>
        {!!sites.length && (
          <Field label="Site">
            <select className={inputCls} style={inputStyle} value={form.site_id} onChange={(e) => setForm({ ...form, site_id: e.target.value })} data-testid="orgchart-add-site">
              <option value="">— None —</option>
              {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Field>
        )}

        <button onClick={submit} disabled={!canSave || saving}
          className="w-full mt-2 py-2.5 rounded-lg text-sm font-bold inline-flex items-center justify-center gap-2 disabled:opacity-50"
          style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="orgchart-add-submit">
          {saving ? <Loader2 size={15} className="animate-spin" /> : <UserPlus size={15} />} Add card
        </button>
      </div>
    </div>, document.body,
  );
}

// ─── Edit drawer ───
export function NodeDrawer({ node, onClose, onSave, onDelete, sites, nodes, departments }) {
  const [form, setForm] = useState(node || {});
  const [saving, setSaving] = useState(false);
  useEffect(() => { setForm(node || {}); }, [node]);
  const managerOptions = useMemo(
    () => nodes.filter((n) => n.id !== node?.id), [nodes, node],
  );
  if (!node) return null;

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const save = async () => {
    setSaving(true);
    try {
      await onSave(node.id, {
        full_name: form.full_name, job_title: form.job_title, department: form.department || '',
        site_id: form.site_id || '', employment_type: form.employment_type, status: form.status,
        email: form.email, phone: form.phone, notes: form.notes,
        recruitment_stage: form.recruitment_stage, salary_band: form.salary_band,
        priority: form.priority, target_start_date: form.target_start_date,
      });
      onClose();
    } finally { setSaving(false); }
  };

  return createPortal(
    <div style={overlay} onMouseDown={onClose}>
      <div style={sheet} onMouseDown={(e) => e.stopPropagation()} className="p-5" data-testid="orgchart-node-drawer">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>Edit card</h3>
          <button onClick={onClose} data-testid="orgchart-drawer-close"><X size={18} style={{ color: 'var(--theme-text-muted)' }} /></button>
        </div>
        {node.staff_id && (
          <div className="mb-3 inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full" style={{ background: 'rgba(25,205,255,0.12)', color: 'var(--color-brand-cyan)' }} data-testid="orgchart-linked-badge">
            <Link2 size={12} /> Linked to staff record
          </div>
        )}
        <Field label="Name"><input className={inputCls} style={inputStyle} value={form.full_name || ''} onChange={(e) => set('full_name', e.target.value)} data-testid="orgchart-edit-name" /></Field>
        <Field label="Job title"><input className={inputCls} style={inputStyle} value={form.job_title || ''} onChange={(e) => set('job_title', e.target.value)} data-testid="orgchart-edit-title" /></Field>
        <Field label="Department">
          <input className={inputCls} style={inputStyle} list="oc-depts-edit" value={form.department || ''} onChange={(e) => set('department', e.target.value)} data-testid="orgchart-edit-dept" />
          <datalist id="oc-depts-edit">{departments.map((d) => <option key={d} value={d} />)}</datalist>
        </Field>
        {!!sites.length && (
          <Field label="Site">
            <select className={inputCls} style={inputStyle} value={form.site_id || ''} onChange={(e) => set('site_id', e.target.value)} data-testid="orgchart-edit-site">
              <option value="">— None —</option>
              {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Field>
        )}
        <Field label="Reports to">
          <select className={inputCls} style={inputStyle} value={form.manager_node_id || ''}
            onChange={(e) => onSave(node.id, { manager_node_id: e.target.value || null }).then(() => set('manager_node_id', e.target.value || null))}
            data-testid="orgchart-edit-manager">
            <option value="">— No manager —</option>
            {managerOptions.map((n) => <option key={n.id} value={n.id}>{n.full_name}</option>)}
          </select>
        </Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Email"><input className={inputCls} style={inputStyle} value={form.email || ''} onChange={(e) => set('email', e.target.value)} /></Field>
          <Field label="Phone"><input className={inputCls} style={inputStyle} value={form.phone || ''} onChange={(e) => set('phone', e.target.value)} /></Field>
        </div>
        {node.type === 'vacancy' && (
          <>
            <Field label="Recruitment stage">
              <select className={inputCls} style={inputStyle} value={form.recruitment_stage || 'Planned'} onChange={(e) => set('recruitment_stage', e.target.value)} data-testid="orgchart-edit-stage">
                {VACANCY_STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Salary band"><input className={inputCls} style={inputStyle} value={form.salary_band || ''} onChange={(e) => set('salary_band', e.target.value)} /></Field>
              <Field label="Target start"><input type="date" className={inputCls} style={inputStyle} value={form.target_start_date || ''} onChange={(e) => set('target_start_date', e.target.value)} /></Field>
            </div>
          </>
        )}
        <Field label="Notes"><textarea rows={3} className={inputCls} style={inputStyle} value={form.notes || ''} onChange={(e) => set('notes', e.target.value)} data-testid="orgchart-edit-notes" /></Field>

        <div className="flex gap-2 mt-2">
          <button onClick={save} disabled={saving} className="flex-1 py-2.5 rounded-lg text-sm font-bold inline-flex items-center justify-center gap-2 disabled:opacity-50" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="orgchart-drawer-save">
            {saving ? <Loader2 size={15} className="animate-spin" /> : null} Save
          </button>
          <button onClick={() => onDelete(node.id)} className="px-3 py-2.5 rounded-lg border" style={{ borderColor: '#fca5a5', color: '#dc2626' }} data-testid="orgchart-drawer-delete"><Trash2 size={15} /></button>
        </div>
      </div>
    </div>, document.body,
  );
}

// ─── Move confirm ───
export function MoveConfirmModal({ data, onChoose, onClose }) {
  if (!data) return null;
  const { childName, managerName, hasStaffLink } = data;
  return createPortal(
    <div style={center} onMouseDown={onClose}>
      <div style={modalBox} onMouseDown={(e) => e.stopPropagation()} data-testid="orgchart-move-modal">
        <h3 className="text-base font-bold pulse-font-heading mb-2" style={{ color: 'var(--theme-text)' }}>Update reporting line?</h3>
        <p className="text-sm mb-5" style={{ color: 'var(--theme-text-muted)' }}>
          You moved <b style={{ color: 'var(--theme-text)' }}>{childName}</b> under <b style={{ color: 'var(--theme-text)' }}>{managerName}</b>.
          {hasStaffLink ? ' Do you want to update their manager in the Staffing record too?' : ''}
        </p>
        <div className="space-y-2">
          {hasStaffLink && (
            <button onClick={() => onChoose('update')} className="w-full py-2.5 rounded-lg text-sm font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="orgchart-move-update">
              Update Staffing record
            </button>
          )}
          <button onClick={() => onChoose('visual')} className="w-full py-2.5 rounded-lg text-sm font-semibold border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="orgchart-move-visual">
            Move on chart only
          </button>
          <button onClick={() => onChoose('cancel')} className="w-full py-2 rounded-lg text-sm font-semibold" style={{ color: 'var(--theme-text-muted)' }} data-testid="orgchart-move-cancel">
            Cancel
          </button>
        </div>
      </div>
    </div>, document.body,
  );
}
