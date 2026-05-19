/**
 * Territory editor modal — split into its own file so Babel's
 * traversal visitor doesn't overflow on a deep JSX tree.
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { X, Save } from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('crm_token') || localStorage.getItem('token') || ''}` } });

const Field = ({ label, children }) => (
  <div>
    <label className="block text-[10px] font-bold uppercase tracking-[0.18em] text-[color:var(--theme-text-muted)] mb-1.5">{label}</label>
    {children}
  </div>
);

function RepOption({ user, checked, onToggle }) {
  return (
    <label className="flex items-center gap-2 px-2 py-1.5 rounded text-sm cursor-pointer hover:bg-[color:var(--theme-surface-hover)]">
      <input type="checkbox" checked={checked} onChange={onToggle} />
      <span style={{ color: 'var(--theme-text)' }}>{user.full_name || user.email}</span>
      <span className="ml-auto text-[11px] uppercase tracking-wider text-[color:var(--theme-text-muted)]">{user.role}</span>
    </label>
  );
}

export default function TerritoryEditor({ open, initial, reps, onClose, onSaved }) {
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    const base = {
      name: '', description: '', parent_id: '',
      postcode_prefixes: [], counties: [], regions: [], countries: ['UK'],
      assigned_rep_ids: [], priority: 0,
    };
    setForm({ ...base, ...(initial || {}) });
  }, [open, initial]);

  if (!open || !form) return null;
  const isNew = !initial?.id;

  const save = async () => {
    if (!form.name.trim()) { toast.error('Name required'); return; }
    setSaving(true);
    try {
      const body = { ...form, priority: Number(form.priority) || 0 };
      if (isNew) await axios.post(`${API}/crm/territories`, body, auth());
      else await axios.put(`${API}/crm/territories/${initial.id}`, body, auth());
      toast.success(isNew ? 'Territory created' : 'Territory updated');
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Save failed');
    } finally { setSaving(false); }
  };

  const setListField = (field) => (e) => {
    const raw = e.target.value;
    setForm({ ...form, [field]: raw.split(',').map((s) => s.trim()).filter(Boolean) });
  };

  const toggleRep = (uid) => {
    const has = form.assigned_rep_ids.includes(uid);
    setForm({
      ...form,
      assigned_rep_ids: has
        ? form.assigned_rep_ids.filter((x) => x !== uid)
        : [...form.assigned_rep_ids, uid],
    });
  };

  const header = (
    <header className="flex-shrink-0 px-5 py-4 border-b border-[color:var(--theme-border)] flex items-start justify-between gap-3">
      <div>
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)]">Territory</p>
        <h2 className="text-lg font-extrabold" style={{ color: 'var(--theme-text)' }}>{isNew ? 'New territory' : form.name}</h2>
      </div>
      <button onClick={onClose} className="h-9 w-9 rounded-full border border-[color:var(--theme-border)] flex items-center justify-center" aria-label="Close" data-testid="territory-editor-close" type="button">
        <X size={18} />
      </button>
    </header>
  );

  const footer = (
    <div className="flex-shrink-0 px-5 py-3 border-t border-[color:var(--theme-border)] flex justify-end gap-2">
      <button onClick={onClose} className="px-3 py-2 rounded-lg text-sm font-bold text-[color:var(--theme-text-muted)]" type="button">Cancel</button>
      <button onClick={save} disabled={saving} className="px-4 py-2 rounded-lg text-sm font-extrabold text-white" style={{ background: 'var(--color-brand-blue)' }} data-testid="territory-save" type="button">
        {saving ? 'Saving…' : <span><Save size={13} className="inline mr-1" /> Save</span>}
      </button>
    </div>
  );

  return (
    <div className="fixed inset-0 z-[100] bg-black/40" onClick={onClose} data-testid="territory-editor">
      <div className="absolute inset-x-0 top-16 bottom-16 sm:inset-0 flex items-stretch sm:items-center justify-center p-3 sm:p-4">
        <div className="relative w-full max-w-lg h-full sm:h-auto sm:max-h-[calc(100vh-6rem)] bg-[color:var(--theme-surface)] border border-[color:var(--theme-border)] rounded-2xl shadow-xl flex flex-col overflow-hidden" onClick={(e) => e.stopPropagation()}>
          {header}
          <div className="flex-1 overflow-y-auto p-5 space-y-4 text-sm">
            <Field label="Name">
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[color:var(--theme-border)] bg-transparent" data-testid="territory-name" />
            </Field>
            <Field label="Description (optional)">
              <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[color:var(--theme-border)] bg-transparent" />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Postcode prefixes">
                <input value={form.postcode_prefixes.join(', ')} onChange={setListField('postcode_prefixes')} placeholder="SW, SE, E1" className="w-full px-3 py-2 rounded-lg border border-[color:var(--theme-border)] bg-transparent" data-testid="territory-postcodes" />
              </Field>
              <Field label="Priority">
                <input type="number" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} className="w-full px-3 py-2 rounded-lg border border-[color:var(--theme-border)] bg-transparent" data-testid="territory-priority" />
              </Field>
            </div>
            <Field label="Counties">
              <input value={form.counties.join(', ')} onChange={setListField('counties')} placeholder="Greater London, Surrey" className="w-full px-3 py-2 rounded-lg border border-[color:var(--theme-border)] bg-transparent" />
            </Field>
            <Field label="Regions">
              <input value={form.regions.join(', ')} onChange={setListField('regions')} placeholder="South East, South West" className="w-full px-3 py-2 rounded-lg border border-[color:var(--theme-border)] bg-transparent" />
            </Field>
            <Field label="Countries">
              <input value={form.countries.join(', ')} onChange={setListField('countries')} placeholder="UK, IE" className="w-full px-3 py-2 rounded-lg border border-[color:var(--theme-border)] bg-transparent" />
            </Field>
            <Field label="Assigned reps (round-robin)">
              <div className="space-y-1 max-h-48 overflow-y-auto rounded-lg border border-[color:var(--theme-border)] p-2">
                {reps.length === 0 ? <p className="text-xs text-[color:var(--theme-text-muted)] px-1">No reps yet.</p> : null}
                {reps.map((u) => (
                  <RepOption key={u.id} user={u} checked={form.assigned_rep_ids.includes(u.id)} onToggle={() => toggleRep(u.id)} />
                ))}
              </div>
            </Field>
          </div>
          {footer}
        </div>
      </div>
    </div>
  );
}
