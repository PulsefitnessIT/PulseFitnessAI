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
import { HardHat, Plus, Loader2, Trash2, Save, BadgeCheck, X, ExternalLink } from 'lucide-react';
import { toast } from 'sonner';
import ServiceOpsShell from './ServiceOpsShell';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } });

const SKILL_OPTIONS = [
  'cardio', 'strength', 'electrical', 'mechanical', 'hydraulic',
  'plate-loaded', 'cable', 'install', 'commissioning',
];

const QUAL_SUGGESTIONS = [
  'IOSH Working Safely', 'PAT Tester', 'CSCS Card', 'NEBOSH',
  '18th Edition', 'First Aid at Work', 'Working at Height', 'Confined Spaces',
];

export default function EngineersAdminPage() {
  const [engineers, setEngineers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [addBusy, setAddBusy] = useState(false);
  const [addForm, setAddForm] = useState({
    email: '', full_name: '', mobile: '', vehicle_reg: '', sage_user_id: '', skills: [],
    // Iter 216h87 — trust fields settable at creation
    photo_url: '', qualifications: [], years_experience: '', verified: false,
  });
  const [editingId, setEditingId] = useState(null);
  const [editDraft, setEditDraft] = useState({});
  // Iter 276b — cross-org machine-access requests from engineers.
  const [requests, setRequests] = useState([]);
  const [reqBusy, setReqBusy] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [engRes, reqRes] = await Promise.all([
        axios.get(`${API}/svc/engineers`, auth()),
        axios.get(`${API}/svc/access-requests?status=pending`, auth()).catch(() => ({ data: {} })),
      ]);
      setEngineers(engRes.data.engineers || []);
      setRequests(reqRes.data.requests || []);
    } catch {
      toast.error('Could not load engineers');
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const decideRequest = async (id, action) => {
    setReqBusy(id);
    try {
      await axios.post(`${API}/svc/access-requests/${id}/${action}`, {}, auth());
      toast.success(action === 'approve' ? 'Access granted' : 'Request declined');
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not update request');
    } finally {
      setReqBusy('');
    }
  };

  const create = async () => {
    if (!addForm.email || !addForm.full_name) {
      toast.error('Email and name are required');
      return;
    }
    setAddBusy(true);
    try {
      const payload = { ...addForm };
      if (payload.years_experience === '' || payload.years_experience == null) {
        delete payload.years_experience;
      } else {
        payload.years_experience = Math.max(0, parseInt(payload.years_experience, 10) || 0);
      }
      await axios.post(`${API}/svc/engineers`, payload, auth());
      toast.success('Engineer added');
      setShowAdd(false);
      setAddForm({
        email: '', full_name: '', mobile: '', vehicle_reg: '', sage_user_id: '', skills: [],
        photo_url: '', qualifications: [], years_experience: '', verified: false,
      });
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not add engineer');
    }
    setAddBusy(false);
  };

  const save = async (id) => {
    try {
      const payload = { ...editDraft };
      // Coerce years_experience to int / null
      if (payload.years_experience === '' || payload.years_experience == null) {
        payload.years_experience = null;
      } else {
        payload.years_experience = Math.max(0, parseInt(payload.years_experience, 10) || 0);
      }
      await axios.patch(`${API}/svc/engineers/${id}`, payload, auth());
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
      // Iter 216h87 — trust card fields
      photo_url: eng.photo_url || '',
      qualifications: eng.qualifications || [],
      years_experience: eng.years_experience || '',
      verified: !!eng.verified,
    });
  };

  const toggleQual = (qual, target = 'edit') => {
    if (target === 'add') {
      const cur = new Set(addForm.qualifications || []);
      if (cur.has(qual)) cur.delete(qual); else cur.add(qual);
      setAddForm({ ...addForm, qualifications: [...cur] });
    } else {
      const cur = new Set(editDraft.qualifications || []);
      if (cur.has(qual)) cur.delete(qual); else cur.add(qual);
      setEditDraft({ ...editDraft, qualifications: [...cur] });
    }
  };

  const addCustomQual = (raw, target = 'edit') => {
    const q = (raw || '').trim();
    if (!q) return;
    if (target === 'add') {
      const cur = new Set(addForm.qualifications || []);
      cur.add(q);
      setAddForm({ ...addForm, qualifications: [...cur] });
    } else {
      const cur = new Set(editDraft.qualifications || []);
      cur.add(q);
      setEditDraft({ ...editDraft, qualifications: [...cur] });
    }
  };

  // Iter 216h87 follow-up — Preview public tracking page for any engineer.
  const previewTracking = async (engineerId, engineerName) => {
    try {
      const r = await axios.get(`${API}/svc/engineers/${engineerId}/preview-tracking-link`, auth());
      const url = r.data?.url;
      if (!url) throw new Error('No URL returned');
      window.open(url, '_blank', 'noopener');
    } catch (e) {
      const msg = e?.response?.data?.detail || e.message;
      toast.error(`Cannot preview ${engineerName}`, { description: msg });
    }
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
      className="svc-btn svc-btn-primary"
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
      {requests.length > 0 && (
        <section
          className="svc-card mb-3"
          style={{ padding: 16, border: '1px solid var(--theme-border)' }}
          data-testid="access-requests-panel"
        >
          <p className="text-[11px] font-bold uppercase tracking-wide" style={{ color: 'var(--theme-text-muted)', marginBottom: 10 }}>
            Machine access requests ({requests.length})
          </p>
          <div className="space-y-2">
            {requests.map((r) => (
              <div
                key={r.id}
                className="flex items-center justify-between gap-3 rounded-xl"
                style={{ padding: 10, border: '1px solid var(--theme-border)' }}
                data-testid={`access-request-${r.id}`}
              >
                <div className="min-w-0">
                  <p className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>
                    {r.engineer_name}
                    {r.engineer_company ? <span style={{ color: 'var(--theme-text-muted)', fontWeight: 400 }}> · {r.engineer_company}</span> : null}
                  </p>
                  <p className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>
                    wants access to <b>{r.equipment_name || 'a machine'}</b>
                    {r.message ? ` — "${r.message}"` : ''}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={() => decideRequest(r.id, 'approve')}
                    disabled={reqBusy === r.id}
                    className="px-3 py-1.5 rounded-lg text-xs font-bold text-white disabled:opacity-50"
                    style={{ background: '#059669' }}
                    data-testid={`access-request-approve-${r.id}`}
                  >
                    {reqBusy === r.id ? '…' : 'Approve'}
                  </button>
                  <button
                    type="button"
                    onClick={() => decideRequest(r.id, 'decline')}
                    disabled={reqBusy === r.id}
                    className="px-3 py-1.5 rounded-lg text-xs font-bold disabled:opacity-50"
                    style={{ border: '1px solid var(--theme-border)', color: 'var(--theme-text-muted)' }}
                    data-testid={`access-request-decline-${r.id}`}
                  >
                    Decline
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
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

          {/* Iter 216h87 — Trust card fields on the Add form */}
          <div
            className="mt-3 pt-3"
            style={{ borderTop: '1px dashed var(--theme-border)' }}
            data-testid="engineers-add-trust-panel"
          >
            <div className="text-xs svc-muted mb-2" style={{ fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              Trust profile · shown to customers on the live-tracking page
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <Field label="Photo URL (optional)">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    {addForm.photo_url ? (
                      <img
                        src={addForm.photo_url}
                        alt=""
                        style={{ width: 32, height: 32, borderRadius: '50%', objectFit: 'cover', border: '1px solid var(--theme-border)' }}
                        onError={(ev) => { ev.target.style.display = 'none'; }}
                      />
                    ) : null}
                    <input
                      className="svc-input"
                      placeholder="https://… (square image works best)"
                      value={addForm.photo_url}
                      onChange={(e) => setAddForm({ ...addForm, photo_url: e.target.value })}
                      data-testid="engineers-add-photo"
                      style={{ flex: 1 }}
                    />
                  </div>
                </Field>
                <Field label="Years of experience">
                  <input
                    type="number"
                    min={0}
                    max={60}
                    className="svc-input"
                    placeholder="e.g. 8"
                    value={addForm.years_experience}
                    onChange={(e) => setAddForm({ ...addForm, years_experience: e.target.value })}
                    data-testid="engineers-add-years"
                    style={{ width: 120 }}
                  />
                </Field>
                <label
                  style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 10, cursor: 'pointer', fontSize: 13 }}
                  data-testid="engineers-add-verified-toggle"
                >
                  <input
                    type="checkbox"
                    checked={!!addForm.verified}
                    onChange={(e) => setAddForm({ ...addForm, verified: e.target.checked })}
                    data-testid="engineers-add-verified-checkbox"
                  />
                  <BadgeCheck size={14} color={addForm.verified ? '#10b981' : '#94a3b8'} />
                  <span style={{ fontWeight: 600 }}>Verified engineer</span>
                </label>
              </div>
              <div>
                <div className="svc-field-label">Qualifications</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 6 }}>
                  {(addForm.qualifications || []).map((q) => (
                    <span
                      key={q}
                      className="svc-pill svc-pill-success"
                      style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
                      data-testid={`engineers-add-qual-chip-${q.replace(/\W+/g, '_')}`}
                    >
                      ✓ {q}
                      <button
                        type="button"
                        onClick={() => toggleQual(q, 'add')}
                        style={{ background: 'transparent', border: 'none', padding: 0, cursor: 'pointer', display: 'flex' }}
                        aria-label={`Remove ${q}`}
                      >
                        <X size={11} />
                      </button>
                    </span>
                  ))}
                  {(addForm.qualifications || []).length === 0 ? (
                    <span className="svc-muted text-xs">Pick from below or type your own</span>
                  ) : null}
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 6 }}>
                  {QUAL_SUGGESTIONS
                    .filter((q) => !(addForm.qualifications || []).includes(q))
                    .map((q) => (
                      <button
                        key={q}
                        type="button"
                        className="svc-pill svc-pill-soft"
                        onClick={() => toggleQual(q, 'add')}
                        style={{ cursor: 'pointer', border: 'none' }}
                        data-testid={`engineers-add-qual-suggest-${q.replace(/\W+/g, '_')}`}
                      >
                        + {q}
                      </button>
                    ))}
                </div>
                <input
                  className="svc-input"
                  placeholder="Add custom qualification & press Enter"
                  data-testid="engineers-add-qual-custom"
                  onKeyDown={(ev) => {
                    if (ev.key === 'Enter') {
                      ev.preventDefault();
                      addCustomQual(ev.target.value, 'add');
                      ev.target.value = '';
                    }
                  }}
                />
              </div>
            </div>
          </div>

          <div className="flex gap-2 mt-3">
            <button type="button" className="svc-btn svc-btn-primary" onClick={create} disabled={addBusy} data-testid="engineers-add-submit">
              {addBusy ? <Loader2 size={14} className="animate-spin" /> : null} Add engineer
            </button>
            <button type="button" className="svc-btn-secondary" onClick={() => setShowAdd(false)}>Cancel</button>
          </div>
        </section>
      ) : null}

      <section className="svc-card" style={{ padding: 0, border: '1px solid var(--theme-border)', overflowX: 'auto' }}>
        <table className="svc-table" data-testid="engineers-table" style={{ minWidth: '52rem' }}>
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
                <React.Fragment key={e.id}>
                <tr data-testid={`engineer-row-${e.id}`}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      {e.photo_url ? (
                        <img
                          src={e.photo_url}
                          alt={e.full_name}
                          style={{ width: 28, height: 28, borderRadius: '50%', objectFit: 'cover' }}
                          data-testid={`engineer-photo-${e.id}`}
                        />
                      ) : null}
                      <div>
                        <div style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4 }}>
                          {e.full_name}
                          {e.verified ? (
                            <BadgeCheck size={13} color="#10b981" data-testid={`engineer-verified-${e.id}`} title="Verified — shown on customer tracking page" />
                          ) : null}
                        </div>
                        <div className="text-xs svc-muted">{e.email}</div>
                        {(e.qualifications || []).length > 0 ? (
                          <div className="text-xs svc-muted" style={{ marginTop: 2 }}>
                            {e.qualifications.slice(0, 3).join(' · ')}
                            {e.qualifications.length > 3 ? ` +${e.qualifications.length - 3}` : ''}
                          </div>
                        ) : null}
                      </div>
                    </div>
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
                        <button type="button" className="svc-btn-secondary svc-btn-sm" onClick={() => previewTracking(e.id, e.full_name)} data-testid={`engineer-preview-${e.id}`} title="Preview customer-facing tracking page">
                          <ExternalLink size={11} /> Preview
                        </button>
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
                {editing ? (
                  <tr data-testid={`engineer-trust-row-${e.id}`} style={{ background: 'var(--theme-surface-soft, #f8fafc)' }}>
                    <td colSpan={8} style={{ padding: 12 }}>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, alignItems: 'start' }}>
                        <div>
                          <div className="svc-field-label">Photo URL</div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            {editDraft.photo_url ? (
                              <img
                                src={editDraft.photo_url}
                                alt=""
                                style={{ width: 36, height: 36, borderRadius: '50%', objectFit: 'cover', border: '1px solid var(--theme-border)' }}
                                onError={(ev) => { ev.target.style.display = 'none'; }}
                              />
                            ) : null}
                            <input
                              className="svc-input svc-input-sm"
                              placeholder="https://… (square image works best)"
                              value={editDraft.photo_url || ''}
                              onChange={(ev) => setEditDraft({ ...editDraft, photo_url: ev.target.value })}
                              data-testid={`engineer-photo-input-${e.id}`}
                              style={{ flex: 1 }}
                            />
                          </div>
                          <div className="svc-field-label" style={{ marginTop: 10 }}>Years of experience</div>
                          <input
                            type="number"
                            min={0}
                            max={60}
                            className="svc-input svc-input-sm"
                            placeholder="e.g. 8"
                            value={editDraft.years_experience}
                            onChange={(ev) => setEditDraft({ ...editDraft, years_experience: ev.target.value })}
                            data-testid={`engineer-years-input-${e.id}`}
                            style={{ width: 100 }}
                          />
                          <label
                            style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 12, cursor: 'pointer', fontSize: 13 }}
                            data-testid={`engineer-verified-toggle-${e.id}`}
                          >
                            <input
                              type="checkbox"
                              checked={!!editDraft.verified}
                              onChange={(ev) => setEditDraft({ ...editDraft, verified: ev.target.checked })}
                              data-testid={`engineer-verified-checkbox-${e.id}`}
                            />
                            <BadgeCheck size={14} color={editDraft.verified ? '#10b981' : '#94a3b8'} />
                            <span style={{ fontWeight: 600 }}>Verified engineer</span>
                            <span className="svc-muted text-xs" style={{ marginLeft: 4 }}>
                              shown to customers on the live-tracking page
                            </span>
                          </label>
                        </div>
                        <div>
                          <div className="svc-field-label">Qualifications</div>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 6 }}>
                            {(editDraft.qualifications || []).map((q) => (
                              <span
                                key={q}
                                className="svc-pill svc-pill-success"
                                style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
                                data-testid={`engineer-qual-chip-${e.id}-${q.replace(/\W+/g, '_')}`}
                              >
                                ✓ {q}
                                <button
                                  type="button"
                                  onClick={() => toggleQual(q)}
                                  style={{ background: 'transparent', border: 'none', padding: 0, cursor: 'pointer', display: 'flex' }}
                                  aria-label={`Remove ${q}`}
                                >
                                  <X size={11} />
                                </button>
                              </span>
                            ))}
                            {(editDraft.qualifications || []).length === 0 ? (
                              <span className="svc-muted text-xs">None — pick from below or type your own</span>
                            ) : null}
                          </div>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 6 }}>
                            {QUAL_SUGGESTIONS
                              .filter((q) => !(editDraft.qualifications || []).includes(q))
                              .map((q) => (
                                <button
                                  key={q}
                                  type="button"
                                  className="svc-pill svc-pill-soft"
                                  onClick={() => toggleQual(q)}
                                  style={{ cursor: 'pointer', border: 'none' }}
                                  data-testid={`engineer-qual-suggest-${e.id}-${q.replace(/\W+/g, '_')}`}
                                >
                                  + {q}
                                </button>
                              ))}
                          </div>
                          <input
                            className="svc-input svc-input-sm"
                            placeholder="Add custom qualification & press Enter"
                            data-testid={`engineer-qual-custom-${e.id}`}
                            onKeyDown={(ev) => {
                              if (ev.key === 'Enter') {
                                ev.preventDefault();
                                addCustomQual(ev.target.value);
                                ev.target.value = '';
                              }
                            }}
                          />
                        </div>
                      </div>
                    </td>
                  </tr>
                ) : null}
                </React.Fragment>
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
