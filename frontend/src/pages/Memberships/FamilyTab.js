/**
 * Member Portal → Family / Sub-profiles tab.
 *
 * Lets a parent member manage who's "on the family plan". Booking flows
 * pick from this list when checking attendees in. Bookings against
 * sub-profiles draw from the parent's credit pool.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import {
  Users, Plus, Trash2, X, Loader2, BadgeCheck, AlertTriangle,
  HeartPulse, Phone,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';

const RELATIONSHIP_OPTIONS = [
  { value: 'child',     label: 'Child' },
  { value: 'partner',   label: 'Partner' },
  { value: 'dependent', label: 'Dependent' },
  { value: 'parent',    label: 'Parent' },
];


export default function FamilyTab({ API, headers }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showEditor, setShowEditor] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/member/sub-profiles`, { headers });
      setRows(data?.sub_profiles || []);
    } catch (e) {
      notifyApiError(notify, e, 'Could not load family');
    }
    setLoading(false);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const remove = async (sp) => {
    if (!window.confirm(`Remove ${sp.first_name} from your family plan? Their booking history stays on record.`)) return;
    try {
      await axios.delete(`${API}/member/sub-profiles/${sp.id}`, { headers });
      notify.success('Removed');
      load();
    } catch (e) {
      notifyApiError(notify, e, 'Failed');
    }
  };

  return (
    <div data-testid="member-family">
      <div className="flex items-end justify-between gap-3 mb-3 flex-wrap">
        <div>
          <h2 className="text-xl font-extrabold tracking-tight" style={{ letterSpacing: '-0.02em' }}>
            Family
          </h2>
          <p className="text-xs text-white/50 mt-1">
            Add kids, partners, or dependents to your plan. They'll share your credits and you can book classes for everyone in one go.
          </p>
        </div>
        <button onClick={() => setShowEditor(true)}
          className="rounded-lg px-3 py-2 text-xs font-extrabold uppercase tracking-wider"
          style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
          data-testid="member-family-add">
          <Plus size={11} className="inline mr-1" /> Add person
        </button>
      </div>

      {loading ? (
        <div className="text-center py-10 text-white/50 text-sm flex items-center justify-center gap-2">
          <Loader2 size={14} className="animate-spin" /> Loading…
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-xl border border-dashed border-white/10 p-10 text-center" data-testid="member-family-empty">
          <Users size={32} className="mx-auto text-white/30 mb-3" />
          <p className="text-sm font-bold text-white/80">No-one on your family plan yet</p>
          <p className="text-xs text-white/50 mt-1">Add kids, your partner, or anyone you regularly book classes for.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {rows.map((sp) => (
            <div key={sp.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-4 flex items-start gap-3"
              data-testid={`member-family-${sp.id}`}>
              <div className="flex-shrink-0 w-10 h-10 rounded-full bg-[rgb(var(--rgb-brand-cyan)/0.2)] flex items-center justify-center">
                <span className="text-[var(--color-brand-cyan)] font-extrabold text-sm">
                  {(sp.first_name || '?').slice(0, 1).toUpperCase()}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-bold text-white truncate">
                  {sp.first_name} {sp.last_name}
                  <span className="ml-2 text-[10px] font-extrabold tracking-wider px-1.5 py-0.5 rounded bg-white/10 text-white/60 uppercase">
                    {sp.relationship}
                  </span>
                </p>
                <div className="text-[11px] text-white/50 mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5">
                  {sp.dob && <span>DOB: {new Date(sp.dob).toLocaleDateString()}</span>}
                  {sp.allergies && <span className="text-amber-300"><HeartPulse size={9} className="inline mr-0.5" /> {sp.allergies}</span>}
                  {sp.emergency_contact_phone && (
                    <span><Phone size={9} className="inline mr-0.5" /> {sp.emergency_contact_phone}</span>
                  )}
                </div>
              </div>
              <button onClick={() => remove(sp)}
                className="p-2 rounded hover:bg-red-500/15 text-red-300/70 hover:text-red-300"
                title="Remove from family plan"
                data-testid={`member-family-remove-${sp.id}`}>
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>
      )}

      {showEditor && (
        <SubProfileEditor API={API} headers={headers}
          onClose={(refresh) => { setShowEditor(false); if (refresh) load(); }} />
      )}
    </div>
  );
}


function SubProfileEditor({ API, headers, onClose }) {
  const [f, setF] = useState({
    first_name: '', last_name: '', dob: '', gender: '',
    relationship: 'child',
    allergies: '', medical_notes: '',
    emergency_contact_name: '', emergency_contact_phone: '',
  });
  const [saving, setSaving] = useState(false);
  const up = (k) => (v) => setF((p) => ({ ...p, [k]: v }));

  const submit = async () => {
    if (!f.first_name.trim()) {
      notify.error('First name is required'); return;
    }
    setSaving(true);
    try {
      await axios.post(`${API}/member/sub-profiles`,
        Object.fromEntries(Object.entries(f).map(([k, v]) => [k, (v || '') || null])),
        { headers });
      notify.success('Added to your family plan');
      onClose(true);
    } catch (e) {
      notifyApiError(notify, e, 'Failed');
    }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-[80] bg-black/80 grid place-items-center p-3 overflow-y-auto" onClick={() => onClose(false)}>
      <div className="w-full max-w-md bg-[color:var(--theme-surface)] dark:bg-zinc-900 border border-white/10 rounded-2xl shadow-2xl overflow-y-auto max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
        data-testid="member-family-editor">
        <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between sticky top-0 bg-[color:var(--theme-surface)] dark:bg-zinc-900 z-10">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--color-brand-cyan)]">Family</p>
            <h2 className="text-lg font-extrabold text-white">Add a person</h2>
          </div>
          <button onClick={() => onClose(false)} className="p-1.5 rounded hover:bg-white/10 text-white/60">
            <X size={14} />
          </button>
        </div>
        <div className="p-5 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="First name *">
              <input value={f.first_name} onChange={(e) => up('first_name')(e.target.value)}
                className="input" data-testid="member-family-first-name" />
            </Field>
            <Field label="Last name">
              <input value={f.last_name} onChange={(e) => up('last_name')(e.target.value)}
                className="input" data-testid="member-family-last-name" />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Relationship">
              <select value={f.relationship} onChange={(e) => up('relationship')(e.target.value)}
                className="input" data-testid="member-family-relationship">
                {RELATIONSHIP_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value} className="bg-zinc-900">{o.label}</option>
                ))}
              </select>
            </Field>
            <Field label="Date of birth">
              <input type="date" value={f.dob} onChange={(e) => up('dob')(e.target.value)}
                className="input" data-testid="member-family-dob" />
            </Field>
          </div>

          <Field label="Allergies (optional)" hint="So instructors and reception are aware">
            <input value={f.allergies} onChange={(e) => up('allergies')(e.target.value)}
              className="input" placeholder="e.g. peanuts" data-testid="member-family-allergies" />
          </Field>

          <Field label="Medical notes (optional)">
            <textarea value={f.medical_notes} onChange={(e) => up('medical_notes')(e.target.value)}
              className="input min-h-[60px]" rows={2}
              placeholder="Anything instructors should know"
              data-testid="member-family-medical" />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Emergency contact name">
              <input value={f.emergency_contact_name} onChange={(e) => up('emergency_contact_name')(e.target.value)}
                className="input" data-testid="member-family-emergency-name" />
            </Field>
            <Field label="Emergency contact phone">
              <input value={f.emergency_contact_phone} onChange={(e) => up('emergency_contact_phone')(e.target.value)}
                className="input" data-testid="member-family-emergency-phone" />
            </Field>
          </div>

          <div className="rounded-lg bg-amber-500/10 border border-amber-500/30 px-3 py-2 mt-3">
            <p className="text-[11px] text-amber-200 flex items-start gap-1.5">
              <AlertTriangle size={11} className="flex-shrink-0 mt-0.5" />
              Your plan covers everyone in your family. Bookings draw from your credit pool.
            </p>
          </div>
        </div>
        <div className="px-5 py-4 border-t border-white/10 flex justify-end gap-2 sticky bottom-0 bg-[color:var(--theme-surface)] dark:bg-zinc-900">
          <button onClick={() => onClose(false)}
            className="px-3 py-2 text-sm font-bold text-white/60 hover:text-white"
            data-testid="member-family-cancel">
            Cancel
          </button>
          <button onClick={submit} disabled={saving}
            className="px-4 py-2 rounded-md text-sm font-extrabold flex items-center gap-1.5 disabled:opacity-60"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
            data-testid="member-family-save">
            {saving ? <><Loader2 size={11} className="animate-spin" /> Saving</> : <><BadgeCheck size={11} /> Add person</>}
          </button>
        </div>
      </div>
      <style>{`
        .input {
          width: 100%; padding: 8px 12px;
          background: rgba(255,255,255,0.04);
          border: 1px solid rgba(255,255,255,0.1);
          border-radius: 8px; color: white;
          font-size: 14px; outline: none;
        }
        .input:focus { border-color: var(--color-brand-cyan); }
      `}</style>
    </div>
  );
}


function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="text-[10px] uppercase tracking-wider font-bold text-white/50">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <p className="text-[10px] text-white/40 mt-1">{hint}</p>}
    </label>
  );
}
