/**
 * Service Ops · Engineers admin
 * ─────────────────────────────
 * Owner / Manager view to manage engineer profiles: create from existing
 * org users, edit skills / mobile / vehicle reg / working-hours / Sage
 * user id, and soft-deactivate. The data here drives the Phase 2 AI
 * auto-assign helper (skills + active flag).
 *
 * Iter 216v (Phase 3).
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { HardHat, Plus, Loader2, Trash2, Save } from 'lucide-react';
import { toast } from 'sonner';
import ServiceOpsShell from './ServiceOpsShell';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } });

const SKILL_OPTIONS = [
  'cardio', 'strength', 'electrical', 'mechanical', 'hydraulic',
  'plate-loaded', 'cable', 'install', 'commissioning',
];

export default function EngineersAdminPage() {
  const [engineers, setEngineers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [addBusy, setAddBusy] = useState(false);
  const [addForm, setAddForm] = useState({
    email: '', full_name: '', mobile: '', vehicle_reg: '', sage_user_id: '', skills: [],
  });
  const [editingId, setEditingId] = useState(null);
  const [editDraft, setEditDraft] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/svc/engineers`, auth());
      setEngineers(data.engineers || []);
    } catch {
      toast.error('Could not load engineers');
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!addForm.email || !addForm.full_name) {
      toast.error('Email and name are required');
      return;
    }
    setAddBusy(true);
    try {
      await axios.post(`${API}/svc/engineers`, addForm, auth());
      toast.success('Engineer added');
      setShowAdd(false);
      setAddForm({ email: '', full_name: '', mobile: '', vehicle_reg: '', sage_user_id: '', skills: [] });
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not add engineer');
    }
    setAddBusy(false);
  };

  const save = async (id) => {
    try {
      await axios.patch(`${API}/svc/engineers/${id}`, editDraft, auth());
      toast.success('Saved');
      setEditingId(null);
      setEditDraft({});
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Save failed');
    }
  };

  const deactivate = async (id) => {
    if (!window.confirm('Deactivate this engineer? They won’t receive new assignments.')) return;
    try {
      await axios.delete(`${API}/svc/engineers/${id}`, auth());
      toast.success('Deactivated');
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Failed');
    }
  };

  const beginEdit = (eng) => {
    setEditingId(eng.id);
    setEditDraft({
      mobile: eng.mobile || '',
      vehicle_reg: eng.vehicle_reg || '',
      sage_user_id: eng.sage_user_id || '',
      skills: eng.skills || [],
      active: eng.active !== false,
    });
  };

  const toggleSkill = (skill, target) => {
    if (target === 'add') {
      const cur = new Set(addForm.skills);
      cur.has(skill) ? cur.delete(skill) : cur.add(skill);
      setAddForm({ ...addForm, skills: [...cur] });
    } else {
      const cur = new Set(editDraft.skills || []);
      cur.has(skill) ? cur.delete(skill) : cur.add(skill);
      setEditDraft({ ...editDraft, skills: [...cur] });
    }
  };

  const actions = useMemo(() => (
    <button
      type="button"
      onClick={() => setShowAdd((v) => !v)}
      className="svc-btn-primary"
      data-testid="engineers-add-btn"
    >
      <Plus size={14} /> Add engineer
    </button>
  ), []);

  return (
    <ServiceOpsShell
      active="engineers"
      title="Engineers"
      subtitle="Profiles, skills, vehicles & Sage links — drives AI auto-assign."
      icon={HardHat}
      actions={actions}
    >
      {showAdd ? (
        <section
          className="svc-card mb-3"
          style={{ padding: 16, border: '1px solid var(--theme-border)' }}
          data-testid="engineers-add-form"
        >
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <Field label="Email (existing teammate)">
              <input className="svc-input" data-testid="engineers-add-email"
                value={addForm.email}
                onChange={(e) => setAddForm({ ...addForm, email: e.target.value })} />
            </Field>
            <Field label="Full name">
              <input className="svc-input" data-testid="engineers-add-name"
                value={addForm.full_name}
                onChange={(e) => setAddForm({ ...addForm, full_name: e.target.value })} />
            </Field>
            <Field label="Mobile">
              <input className="svc-input" data-testid="engineers-add-mobile"
                value={addForm.mobile}
                onChange={(e) => setAddForm({ ...addForm, mobile: e.target.value })} />
            </Field>
            <Field label="Vehicle reg">
              <input className="svc-input" data-testid="engineers-add-vehicle"
                value={addForm.vehicle_reg}
                onChange={(e) => setAddForm({ ...addForm, vehicle_reg: e.target.value })} />
            </Field>
            <Field label="Sage user ID">
              <input className="svc-input" data-testid="engineers-add-sage"
                value={addForm.sage_user_id}
                onChange={(e) => setAddForm({ ...addForm, sage_user_id: e.target.value })} />
            </Field>
          </div>
          <SkillPicker selected={addForm.skills} onToggle={(s) => toggleSkill(s, 'add')} />
          <div className="flex gap-2 mt-3">
            <button type="button" className="svc-btn-primary" onClick={create} disabled={addBusy} data-testid="engineers-add-submit">
              {addBusy ? <Loader2 size={14} className="animate-spin" /> : null} Add engineer
            </button>
            <button type="button" className="svc-btn-secondary" onClick={() => setShowAdd(false)}>Cancel</button>
          </div>
        </section>
      ) : null}

      <section className="svc-card" style={{ padding: 0, border: '1px solid var(--theme-border)' }}>
        <table className="svc-table" data-testid="engineers-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Mobile</th>
              <th>Vehicle</th>
              <th>Skills</th>
              <th>Sage</th>
              <th style={{ textAlign: 'right' }}>Open jobs</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} style={{ padding: 16, opacity: 0.6 }}>Loading…</td></tr>
            ) : engineers.length === 0 ? (
              <tr><td colSpan={8} style={{ padding: 16, opacity: 0.6 }}>No engineers yet — add one above.</td></tr>
            ) : engineers.map((e) => {
              const editing = editingId === e.id;
              return (
                <tr key={e.id} data-testid={`engineer-row-${e.id}`}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{e.full_name}</div>
                    <div className="text-xs svc-muted">{e.email}</div>
                  </td>
                  <td>
                    {editing ? (
                      <input className="svc-input svc-input-sm" value={editDraft.mobile || ''}
                        onChange={(ev) => setEditDraft({ ...editDraft, mobile: ev.target.value })} />
                    ) : (e.mobile || '—')}
                  </td>
                  <td>
                    {editing ? (
                      <input className="svc-input svc-input-sm" value={editDraft.vehicle_reg || ''}
                        onChange={(ev) => setEditDraft({ ...editDraft, vehicle_reg: ev.target.value })} />
                    ) : (e.vehicle_reg || '—')}
                  </td>
                  <td style={{ maxWidth: 240 }}>
                    {editing ? (
                      <SkillPicker compact selected={editDraft.skills || []} onToggle={(s) => toggleSkill(s, 'edit')} />
                    ) : (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                        {(e.skills || []).length === 0 ? <span className="svc-muted text-xs">—</span> :
                          e.skills.map((s) => <span key={s} className="svc-pill svc-pill-soft">{s}</span>)}
                      </div>
                    )}
                  </td>
                  <td className="text-xs">
                    {editing ? (
                      <input className="svc-input svc-input-sm" value={editDraft.sage_user_id || ''}
                        onChange={(ev) => setEditDraft({ ...editDraft, sage_user_id: ev.target.value })} />
                    ) : (e.sage_user_id || '—')}
                  </td>
                  <td style={{ textAlign: 'right', fontWeight: 700 }}>{e.open_jobs ?? 0}</td>
                  <td>
                    <span className={`svc-pill ${e.active === false ? 'svc-pill-muted' : 'svc-pill-success'}`}>
                      {e.active === false ? 'Inactive' : 'Active'}
                    </span>
                  </td>
                  <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                    {editing ? (
                      <>
                        <button type="button" className="svc-btn-primary svc-btn-sm" onClick={() => save(e.id)} data-testid={`engineer-save-${e.id}`}>
                          <Save size={12} /> Save
                        </button>
                        <button type="button" className="svc-btn-secondary svc-btn-sm" onClick={() => { setEditingId(null); setEditDraft({}); }}>
                          Cancel
                        </button>
                      </>
                    ) : (
                      <>
                        <button type="button" className="svc-btn-secondary svc-btn-sm" onClick={() => beginEdit(e)} data-testid={`engineer-edit-${e.id}`}>
                          Edit
                        </button>
                        {e.active !== false ? (
                          <button type="button" className="svc-btn-secondary svc-btn-sm" onClick={() => deactivate(e.id)} data-testid={`engineer-deactivate-${e.id}`}>
                            <Trash2 size={11} />
                          </button>
                        ) : null}
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </ServiceOpsShell>
  );
}

function Field({ label, children }) {
  return (
    <label style={{ display: 'block' }}>
      <div className="svc-field-label">{label}</div>
      {children}
    </label>
  );
}

function SkillPicker({ selected, onToggle, compact }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: compact ? 4 : 6, marginTop: compact ? 2 : 8 }}>
      {SKILL_OPTIONS.map((s) => {
        const on = selected.includes(s);
        return (
          <button
            key={s} type="button"
            onClick={() => onToggle(s)}
            className={`svc-pill ${on ? 'svc-pill-active' : 'svc-pill-soft'}`}
            style={{ cursor: 'pointer', border: 'none' }}
            data-testid={`engineer-skill-${s}`}
          >
            {s}
          </button>
        );
      })}
    </div>
  );
}
