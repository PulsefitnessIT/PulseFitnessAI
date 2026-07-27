/**
 * MOD Staff Modal — CRUD for a site's staff roster.
 *
 * Consumed from MODSiteDashboard header + from the fault wizard "Who is
 * reporting this?" step (+ Add new contact inline). MRU sort comes from the
 * backend (last_reported_at DESC).
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { X, UserPlus, Pencil, Trash2, Mail, Phone, Briefcase, Save } from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { useAuth } from '@/App';

export default function MODStaffModal({ onClose, onPicked }) {
  const { API } = useAuth();
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const [staff, setStaff] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // null | 'new' | {id,...}

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/mod/site/staff`, { headers });
      setStaff(data.staff || []);
    } catch (e) {
      notify.error('Failed to load staff');
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, [API]);

  useEffect(() => { load(); }, [load]);

  const onDelete = async (s) => {
    if (!window.confirm(`Remove ${s.name}? Tickets they've logged will be preserved.`)) return;
    try {
      await axios.delete(`${API}/mod/site/staff/${s.id}`, { headers });
      notify.success('Staff removed');
      load();
    } catch {
      notify.error('Failed to remove');
    }
  };

  const isPicker = typeof onPicked === 'function';

  return (
    <div className="fixed inset-0 z-[80] bg-black/80 backdrop-blur-sm grid place-items-center p-4" data-testid="mod-staff-modal" onClick={onClose}>
      <div className="w-full max-w-2xl bg-[var(--color-ink-deep)] border border-white/10 rounded-2xl overflow-hidden max-h-[90vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/10 bg-[var(--color-surface-darker)]">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)]">MOD Portal</div>
            <h2 className="text-white text-lg font-extrabold tracking-tight">{isPicker ? 'Pick who is reporting' : 'Site Staff'}</h2>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-white/5 text-white/60" data-testid="mod-staff-close"><X size={18} /></button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-3">
          {editing ? (
            <StaffForm
              initial={editing === 'new' ? null : editing}
              onCancel={() => setEditing(null)}
              onSaved={() => { setEditing(null); load(); }}
              API={API}
              headers={headers}
            />
          ) : (
            <>
              <button
                onClick={() => setEditing('new')}
                className="w-full flex items-center justify-center gap-2 rounded-xl border border-dashed border-[rgb(var(--rgb-brand-cyan)/0.4)] px-4 py-3 text-[var(--color-brand-cyan)] hover:bg-[rgb(var(--rgb-brand-cyan)/0.05)] text-sm font-bold"
                data-testid="mod-staff-add"
              >
                <UserPlus size={15} /> Add new contact
              </button>

              {loading && <div className="text-center text-white/50 py-6 text-sm">Loading…</div>}
              {!loading && staff.length === 0 && (
                <div className="text-center text-white/50 py-8 text-sm">
                  No staff yet. Add one above to start capturing accountable reporters.
                </div>
              )}

              {staff.map((s) => (
                <div
                  key={s.id}
                  className={`rounded-xl border border-white/10 bg-white/[0.03] p-3.5 flex items-start gap-3 ${isPicker ? 'hover:border-[rgb(var(--rgb-brand-cyan)/0.6)] cursor-pointer' : ''}`}
                  onClick={isPicker ? () => onPicked(s) : undefined}
                  data-testid={`mod-staff-row-${s.id}`}
                >
                  <div className="w-10 h-10 rounded-lg bg-[rgb(var(--rgb-brand-cyan)/0.15)] text-[var(--color-brand-cyan)] grid place-items-center font-extrabold text-sm shrink-0">
                    {initials(s.name)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-bold text-white text-sm truncate">{s.name}</div>
                    {s.role && <div className="text-xs text-white/60 flex items-center gap-1"><Briefcase size={10} /> {s.role}</div>}
                    <div className="text-xs text-white/50 flex items-center gap-1 truncate"><Mail size={10} /> {s.email}</div>
                    <div className="text-xs text-white/50 flex items-center gap-1"><Phone size={10} /> {s.phone}</div>
                    {s.fault_count > 0 && (
                      <div className="text-[10px] font-bold text-amber-300 mt-1">
                        {s.fault_count} fault{s.fault_count > 1 ? 's' : ''} reported
                      </div>
                    )}
                  </div>
                  {!isPicker && (
                    <div className="flex flex-col gap-1.5 shrink-0">
                      <button onClick={() => setEditing(s)} className="p-1.5 rounded hover:bg-white/10 text-white/60 hover:text-white" data-testid={`mod-staff-edit-${s.id}`}>
                        <Pencil size={13} />
                      </button>
                      <button onClick={() => onDelete(s)} className="p-1.5 rounded hover:bg-red-500/20 text-white/60 hover:text-red-300" data-testid={`mod-staff-delete-${s.id}`}>
                        <Trash2 size={13} />
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}


function StaffForm({ initial, onCancel, onSaved, API, headers }) {
  const [form, setForm] = useState({
    name: initial?.name || '',
    role: initial?.role || '',
    email: initial?.email || '',
    phone: initial?.phone || '',
  });
  const [saving, setSaving] = useState(false);

  const patch = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    if (!form.name.trim() || !form.email.trim() || !form.phone.trim()) {
      notify.error('Name, email and phone are required');
      return;
    }
    setSaving(true);
    try {
      if (initial?.id) {
        await axios.patch(`${API}/mod/site/staff/${initial.id}`, form, { headers });
        notify.success('Staff updated');
      } else {
        await axios.post(`${API}/mod/site/staff`, form, { headers });
        notify.success('Staff added');
      }
      onSaved();
    } catch (err) {
      notifyApiError(notify, err, 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="rounded-xl border border-white/10 bg-white/[0.03] p-4 space-y-3" data-testid="mod-staff-form">
      <Input label="Full name" value={form.name} onChange={(v) => patch('name', v)} required testid="mod-staff-field-name" />
      <Input label="Role (e.g. PTI, Duty Manager)" value={form.role} onChange={(v) => patch('role', v)} testid="mod-staff-field-role" />
      <Input label="Email" type="email" value={form.email} onChange={(v) => patch('email', v)} required testid="mod-staff-field-email" />
      <Input label="Phone" value={form.phone} onChange={(v) => patch('phone', v)} required testid="mod-staff-field-phone" />
      <div className="flex gap-2 pt-1">
        <button type="submit" disabled={saving}
          className="flex-1 flex items-center justify-center gap-1.5 rounded-lg px-4 py-2.5 text-sm font-bold"
          style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
          data-testid="mod-staff-save"
        >
          <Save size={14} /> {saving ? 'Saving…' : 'Save'}
        </button>
        <button type="button" onClick={onCancel}
          className="rounded-lg px-4 py-2.5 text-sm font-bold border border-white/15 text-white/80 hover:bg-white/5"
        >Cancel</button>
      </div>
    </form>
  );
}


function Input({ label, value, onChange, type = 'text', required, testid }) {
  return (
    <label className="block">
      <span className="text-[10px] font-bold uppercase tracking-wider text-white/60">{label}{required ? ' *' : ''}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-lg bg-black/40 border border-white/10 px-3 py-2.5 text-sm text-white placeholder-white/30 focus:outline-none focus:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
        required={required}
        data-testid={testid}
      />
    </label>
  );
}


function initials(name = '') {
  return name.trim().split(/\s+/).slice(0, 2).map((s) => s[0]?.toUpperCase()).join('');
}
