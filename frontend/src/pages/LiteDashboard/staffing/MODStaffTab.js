/**
 * MOD Staff tab — site-scoped staff CRUD for MOD tenants.
 * (Iter 216h113h).
 *
 * Backs onto /api/mod/site/staff which stores records in the
 * `mod_site_staff` collection (separate from `staffing_staff` used
 * by commercial Pulse tenants — MOD records carry a Rank field).
 *
 * Fields per staff member: Rank · Name · Role · Email · Phone.
 */
import { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Plus, Pencil, Trash2, Loader2, Mail, Phone, Users, X, KeyRound, Copy } from 'lucide-react';
import { useAuth } from '@/App';
import { can } from '@/utils/capabilities';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const BLANK = { rank: '', name: '', role: 'PT Instructor', date_of_birth: '', email: '', phone: '' };
const BLANK_HANDOVER = { successor_name: '', successor_email: '', mode: 'password' };

export default function MODStaffTab({ headers }) {
  const { user } = useAuth();
  const isOwner = can(user, 'transfer_ownership');
  const [staff, setStaff] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);  // null | {} (new) | record (edit)
  const [form, setForm] = useState(BLANK);
  const [submitting, setSubmitting] = useState(false);
  const [handoverOpen, setHandoverOpen] = useState(false);
  const [handover, setHandover] = useState(BLANK_HANDOVER);
  const [handoverBusy, setHandoverBusy] = useState(false);
  const [handoverResult, setHandoverResult] = useState(null);

  const submitHandover = async (e) => {
    e?.preventDefault?.();
    if (!handover.successor_name.trim() || !handover.successor_email.trim()) {
      toast.error('New owner name and email are required');
      return;
    }
    setHandoverBusy(true);
    try {
      const r = await axios.post(`${API}/mod/site/transfer-owner`, {
        successor_name: handover.successor_name.trim(),
        successor_email: handover.successor_email.trim(),
        mode: handover.mode,
      }, { headers });
      setHandoverResult(r.data?.new_owner || null);
      toast.success('Ownership transferred');
    } catch (err) {
      const msg = err?.response?.data?.detail || 'Transfer failed';
      toast.error(typeof msg === 'string' ? msg : 'Transfer failed');
    } finally {
      setHandoverBusy(false);
    }
  };
  const closeHandover = () => { setHandoverOpen(false); setHandover(BLANK_HANDOVER); setHandoverResult(null); };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/mod/site/staff`, { headers });
      setStaff(r.data?.staff || []);
    } catch (e) {
      const msg = e?.response?.data?.detail || 'Could not load staff';
      toast.error(typeof msg === 'string' ? msg : 'Could not load staff');
    } finally {
      setLoading(false);
    }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  const openNew = () => { setEditing({}); setForm(BLANK); };
  const openEdit = (s) => {
    setEditing(s);
    setForm({
      rank: s.rank || '',
      name: s.name || '',
      role: s.role || 'PT Instructor',
      date_of_birth: s.date_of_birth || '',
      email: s.email || '',
      phone: s.phone || '',
    });
  };
  const close = () => { setEditing(null); setForm(BLANK); };

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!form.name?.trim() || !form.email?.trim() || !form.phone?.trim()) {
      toast.error('Name, email and phone are required');
      return;
    }
    if (!form.date_of_birth) {
      toast.error('Date of birth is required');
      return;
    }
    setSubmitting(true);
    try {
      const body = {
        name: form.name.trim(),
        rank: form.rank.trim() || undefined,
        role: form.role.trim() || undefined,
        date_of_birth: form.date_of_birth,
        email: form.email.trim(),
        phone: form.phone.trim(),
      };
      if (editing && editing.id) {
        await axios.patch(`${API}/mod/site/staff/${editing.id}`, body, { headers });
        toast.success('Staff updated');
      } else {
        await axios.post(`${API}/mod/site/staff`, body, { headers });
        toast.success('Staff added');
      }
      close();
      load();
    } catch (e) {
      const msg = e?.response?.data?.detail || 'Save failed';
      toast.error(typeof msg === 'string' ? msg : 'Save failed');
    } finally {
      setSubmitting(false);
    }
  };

  const remove = async (s) => {
    if (!window.confirm(`Remove ${s.name} from this site?`)) return;
    try {
      await axios.delete(`${API}/mod/site/staff/${s.id}`, { headers });
      toast.success('Staff removed');
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not remove');
    }
  };

  return (
    <div className="space-y-5" data-testid="mod-staff-tab">
      <div className="rounded-2xl border p-5 flex items-start gap-3" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border, #E4E4E7)' }}>
        <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0" style={{ background: 'rgba(102,204,255,0.10)' }}>
          <Users size={18} style={{ color: '#33B8FF' }} />
        </div>
        <div className="flex-1">
          <h3 className="text-base font-bold" style={{ color: 'var(--theme-text)' }}>Staff at this site</h3>
          <p className="text-sm mt-1" style={{ color: 'var(--theme-text-muted)' }}>
            Service Personnel assigned to this site. Use Transfers to move
            someone in or out of this gym.
          </p>
        </div>
        <button
          type="button"
          onClick={openNew}
          className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-bold"
          style={{ background: '#66CCFF', color: '#212721' }}
          data-testid="mod-staff-add"
        >
          <Plus size={14} /> Add staff
        </button>
        {isOwner && (
          <button
            type="button"
            onClick={() => { setHandoverResult(null); setHandover(BLANK_HANDOVER); setHandoverOpen(true); }}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-bold border"
            style={{ borderColor: 'var(--theme-border, #E4E4E7)', color: 'var(--theme-text)' }}
            data-testid="mod-owner-transfer-open"
          >
            <KeyRound size={14} /> Transfer ownership
          </button>
        )}
      </div>

      {/* List */}
      <div className="rounded-2xl border overflow-hidden" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border, #E4E4E7)' }}>
        {loading ? (
          <div className="p-8 text-center text-sm" style={{ color: 'var(--theme-text-muted)' }}>
            <Loader2 size={16} className="animate-spin inline mr-2" /> Loading staff…
          </div>
        ) : staff.length === 0 ? (
          <div className="p-8 text-center text-sm" style={{ color: 'var(--theme-text-muted)' }} data-testid="mod-staff-empty">
            No staff added yet. Click <strong>Add staff</strong> above.
          </div>
        ) : (
          <ul className="divide-y" style={{ borderColor: 'var(--theme-border, #E4E4E7)' }}>
            {staff.map((s) => (
              <li key={s.id} className="px-4 sm:px-5 py-3.5 flex items-start gap-3" data-testid={`mod-staff-row-${s.id}`}>
                <div className="w-10 h-10 rounded-lg flex items-center justify-center text-xs font-bold shrink-0" style={{ background: 'rgba(102,204,255,0.10)', color: '#33B8FF' }}>
                  {(s.name || '?').split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    {s.rank && (
                      <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded" style={{ background: 'rgba(102,204,255,0.12)', color: '#33B8FF' }}>
                        {s.rank}
                      </span>
                    )}
                    <span className="font-semibold text-sm" style={{ color: 'var(--theme-text)' }}>{s.name}</span>
                  </div>
                  <div className="text-xs mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
                    {s.role || '—'}
                  </div>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs mt-1.5" style={{ color: 'var(--theme-text-muted)' }}>
                    {s.email && <span className="inline-flex items-center gap-1"><Mail size={11} /> {s.email}</span>}
                    {s.phone && <span className="inline-flex items-center gap-1"><Phone size={11} /> {s.phone}</span>}
                  </div>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <button type="button" onClick={() => openEdit(s)} className="p-1.5 rounded-md" style={{ color: 'var(--theme-text-muted)' }} data-testid={`mod-staff-edit-${s.id}`} aria-label="Edit">
                    <Pencil size={14} />
                  </button>
                  <button type="button" onClick={() => remove(s)} className="p-1.5 rounded-md" style={{ color: '#DC2626' }} data-testid={`mod-staff-delete-${s.id}`} aria-label="Remove">
                    <Trash2 size={14} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Edit / add modal — portalled to <body> so `fixed inset-0` covers the
          true viewport (the Lite dashboard has transformed ancestors that
          would otherwise trap the overlay inside the tab content area). */}
      {editing !== null && createPortal((
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(4px)' }} data-testid="mod-staff-modal">
          <form onSubmit={submit} className="rounded-2xl w-full max-w-lg p-6 relative" style={{ background: 'var(--theme-surface)' }}>
            <button type="button" onClick={close} className="absolute right-4 top-4 p-1.5 rounded-full" aria-label="Close" data-testid="mod-staff-close">
              <X size={16} />
            </button>
            <h4 className="text-base font-bold mb-4" style={{ color: 'var(--theme-text)' }}>
              {editing.id ? `Edit ${editing.name}` : 'Add staff'}
            </h4>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <Field label="Rank" testid="mod-staff-field-rank">
                <input
                  type="text"
                  value={form.rank}
                  onChange={(e) => setForm({ ...form, rank: e.target.value })}
                  placeholder="Sgt"
                  maxLength={40}
                  className="w-full px-3 py-2 rounded-lg text-sm border focus:outline-none focus:border-cyan-400"
                  style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border, #E4E4E7)', color: 'var(--theme-text)' }}
                />
              </Field>
              <Field label="Full name" testid="mod-staff-field-name" className="sm:col-span-2" required>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Sgt Jane Smith"
                  required
                  data-testid="mod-staff-field-fullname"
                  className="w-full px-3 py-2 rounded-lg text-sm border focus:outline-none focus:border-cyan-400"
                  style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border, #E4E4E7)', color: 'var(--theme-text)' }}
                />
              </Field>
            </div>

            <Field label="Role" testid="mod-staff-field-role" className="mt-3">
              <input
                type="text"
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
                placeholder="PT Instructor"
                className="w-full px-3 py-2 rounded-lg text-sm border focus:outline-none focus:border-cyan-400"
                style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border, #E4E4E7)', color: 'var(--theme-text)' }}
              />
            </Field>

            <Field label="Date of birth" testid="mod-staff-field-dob" className="mt-3" required>
              <input
                type="date"
                value={form.date_of_birth}
                onChange={(e) => setForm({ ...form, date_of_birth: e.target.value })}
                max={new Date().toISOString().slice(0, 10)}
                required
                className="w-full px-3 py-2 rounded-lg text-sm border focus:outline-none focus:border-cyan-400"
                style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border, #E4E4E7)', color: 'var(--theme-text)' }}
              />
              <span className="text-[10.5px] mt-1 block" style={{ color: 'var(--theme-text-muted)' }}>
                Used to confirm identity when transferring this person between sites.
              </span>
            </Field>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
              <Field label="Email" testid="mod-staff-field-email" required>
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  required
                  className="w-full px-3 py-2 rounded-lg text-sm border focus:outline-none focus:border-cyan-400"
                  style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border, #E4E4E7)', color: 'var(--theme-text)' }}
                />
              </Field>
              <Field label="Phone" testid="mod-staff-field-phone" required>
                <input
                  type="tel"
                  value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                  required
                  className="w-full px-3 py-2 rounded-lg text-sm border focus:outline-none focus:border-cyan-400"
                  style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border, #E4E4E7)', color: 'var(--theme-text)' }}
                />
              </Field>
            </div>

            <div className="mt-5 flex items-center justify-end gap-2">
              <button type="button" onClick={close} className="px-4 py-2 rounded-lg text-sm font-semibold" style={{ color: 'var(--theme-text-muted)' }} data-testid="mod-staff-cancel">
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="px-4 py-2 rounded-lg text-sm font-bold inline-flex items-center gap-2 disabled:opacity-50"
                style={{ background: '#66CCFF', color: '#212721' }}
                data-testid="mod-staff-save"
              >
                {submitting ? <Loader2 size={14} className="animate-spin" /> : null}
                {editing.id ? 'Save changes' : 'Add staff'}
              </button>
            </div>
          </form>
        </div>
      ), document.body)}

      {/* Owner handover modal (owner-only) */}
      {handoverOpen && createPortal((
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(4px)' }} data-testid="mod-owner-transfer-modal">
          <div className="rounded-2xl w-full max-w-lg p-6 relative" style={{ background: 'var(--theme-surface)' }}>
            <button type="button" onClick={closeHandover} className="absolute right-4 top-4 p-1.5 rounded-full" aria-label="Close" data-testid="mod-owner-transfer-close">
              <X size={16} />
            </button>
            <h4 className="text-base font-bold mb-1 flex items-center gap-2" style={{ color: 'var(--theme-text)' }}>
              <KeyRound size={16} style={{ color: '#33B8FF' }} /> Transfer site ownership
            </h4>

            {handoverResult ? (
              <div className="mt-3" data-testid="mod-owner-transfer-result">
                <p className="text-sm mb-3" style={{ color: 'var(--theme-text-muted)' }}>
                  Ownership handed over. Your own login has been stepped down — share these with the new owner:
                </p>
                {handoverResult.mode === 'password' ? (
                  <div className="rounded-lg border p-3 text-sm space-y-1.5" style={{ borderColor: 'var(--theme-border, #E4E4E7)' }}>
                    <div className="flex items-center gap-2"><span style={{ color: 'var(--theme-text-muted)' }}>Login</span> <code className="font-mono px-1.5 py-0.5 rounded" style={{ background: 'rgba(102,204,255,0.12)' }} data-testid="mod-owner-new-email">{handoverResult.email}</code></div>
                    <div className="flex items-center gap-2">
                      <span style={{ color: 'var(--theme-text-muted)' }}>Password</span>
                      <code className="font-mono px-1.5 py-0.5 rounded" style={{ background: 'rgba(102,204,255,0.12)' }} data-testid="mod-owner-new-password">{handoverResult.temporary_password}</code>
                      <button type="button" onClick={() => { navigator.clipboard?.writeText(handoverResult.temporary_password); toast.success('Password copied'); }} className="p-1 rounded" aria-label="Copy password"><Copy size={12} /></button>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-lg border p-3 text-sm break-all" style={{ borderColor: 'var(--theme-border, #E4E4E7)' }} data-testid="mod-owner-new-invite">
                    Invite link sent to <strong>{handoverResult.email}</strong>:<br />{handoverResult.invite_url}
                  </div>
                )}
                <div className="mt-5 flex justify-end">
                  <button type="button" onClick={closeHandover} className="px-4 py-2 rounded-lg text-sm font-bold" style={{ background: '#66CCFF', color: '#212721' }} data-testid="mod-owner-transfer-done">Done</button>
                </div>
              </div>
            ) : (
              <form onSubmit={submitHandover} className="mt-3">
                <p className="text-sm mb-4" style={{ color: 'var(--theme-text-muted)' }}>
                  Hand the <strong>owner</strong> role to a new person (e.g. when you post out). They get their own individual login with full visibility; your login is stepped down to the shared level.
                </p>
                <Field label="New owner full name" testid="mod-owner-field-name" required>
                  <input type="text" value={handover.successor_name} onChange={(e) => setHandover({ ...handover, successor_name: e.target.value })} required data-testid="mod-owner-input-name"
                    className="w-full px-3 py-2 rounded-lg text-sm border focus:outline-none focus:border-cyan-400"
                    style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border, #E4E4E7)', color: 'var(--theme-text)' }} />
                </Field>
                <Field label="New owner email" testid="mod-owner-field-email" className="mt-3" required>
                  <input type="email" value={handover.successor_email} onChange={(e) => setHandover({ ...handover, successor_email: e.target.value })} required data-testid="mod-owner-input-email"
                    placeholder="new.owner@example.com"
                    className="w-full px-3 py-2 rounded-lg text-sm border focus:outline-none focus:border-cyan-400"
                    style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border, #E4E4E7)', color: 'var(--theme-text)' }} />
                </Field>
                <Field label="Credential" testid="mod-owner-field-mode" className="mt-3">
                  <select value={handover.mode} onChange={(e) => setHandover({ ...handover, mode: e.target.value })} data-testid="mod-owner-input-mode"
                    className="w-full px-3 py-2 rounded-lg text-sm border focus:outline-none focus:border-cyan-400"
                    style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border, #E4E4E7)', color: 'var(--theme-text)' }}>
                    <option value="password">Generate a temporary password</option>
                    <option value="invite">Send an invite link</option>
                  </select>
                </Field>
                <div className="mt-5 flex items-center justify-end gap-2">
                  <button type="button" onClick={closeHandover} className="px-4 py-2 rounded-lg text-sm font-semibold" style={{ color: 'var(--theme-text-muted)' }} data-testid="mod-owner-transfer-cancel">Cancel</button>
                  <button type="submit" disabled={handoverBusy} className="px-4 py-2 rounded-lg text-sm font-bold inline-flex items-center gap-2 disabled:opacity-50" style={{ background: '#66CCFF', color: '#212721' }} data-testid="mod-owner-transfer-submit">
                    {handoverBusy ? <Loader2 size={14} className="animate-spin" /> : null}
                    Transfer ownership
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      ), document.body)}
    </div>
  );
}

function Field({ label, testid, children, className = '', required = false }) {
  return (
    <label className={`block ${className}`} data-testid={testid}>
      <span className="text-[10.5px] uppercase font-bold" style={{ color: 'var(--theme-text-muted)', letterSpacing: '0.18em' }}>
        {label}{required && ' *'}
      </span>
      <div className="mt-1.5">{children}</div>
    </label>
  );
}
