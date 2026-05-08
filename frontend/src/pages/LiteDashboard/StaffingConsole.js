/**
 * StaffingConsole — workforce intelligence dashboard.
 *
 * Role-gated: managers/owners see every tab (Rota, Staff, Leave, Market,
 * Performance, Payroll, Live Floor, Rules, Announcements, AI). Staff
 * see a reduced set (My Shifts, My Leave, Open Shifts, Swap Requests,
 * Announcements read-only, Live Floor).
 *
 * Two mount points:
 *   - Operations → 'Staffing' tab for managers/owners (full view)
 *   - Operations → 'Gym Floor' tab for staff (same component, role-gated)
 *
 * All data fetched from /api/staffing/* — role filtering is enforced
 * server-side; the frontend just hides UI the user can't use.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Users, Calendar, UserPlus, Plane, ShoppingBag, BarChart3, PoundSterling,
  Eye, Shield, Megaphone, Sparkles, Plus, Trash2, CheckCircle2, X,
  ChevronLeft, ChevronRight, Clock, AlertTriangle, Download, RefreshCw,
} from 'lucide-react';
import { useAuth } from '@/App';
import PillTabBar from '@/components/shared/PillTabBar';
import PageHeader from '@/components/shared/PageHeader';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Canonical tab registry. Each tab knows which roles can see it.
const TABS_ALL = [
  { id: 'rota',         label: 'Rota',          icon: Calendar,    roles: ['owner','manager','master_admin'] },
  { id: 'staff',        label: 'Staff',         icon: Users,       roles: ['owner','manager','master_admin'] },
  { id: 'leave',        label: 'Time Off',      icon: Plane,       roles: ['owner','manager','master_admin','staff'] },
  { id: 'market',       label: 'Shift Market',  icon: ShoppingBag, roles: ['owner','manager','master_admin','staff'] },
  { id: 'performance',  label: 'Performance',   icon: BarChart3,   roles: ['owner','manager','master_admin'] },
  { id: 'payroll',      label: 'Payroll',       icon: PoundSterling,  roles: ['owner','manager','master_admin'] },
  { id: 'live',         label: 'Live Floor',    icon: Eye,         roles: ['owner','manager','master_admin','staff'] },
  { id: 'rules',        label: 'Rules',         icon: Shield,      roles: ['owner','manager','master_admin'] },
  { id: 'announce',     label: 'Announcements', icon: Megaphone,   roles: ['owner','manager','master_admin','staff'] },
  { id: 'ai',           label: 'AI Insights',   icon: Sparkles,    roles: ['owner','manager','master_admin'] },
];

export default function StaffingConsole() {
  const { user } = useAuth();
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const headers = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);
  const role = useMemo(() => {
    if (user?.is_master_admin || user?.is_pulse_admin) return 'master_admin';
    const r = (user?.role || '').toLowerCase();
    return ['owner','manager','staff','gym_floor'].includes(r) ? r : 'staff';
  }, [user]);
  const isManager = role === 'owner' || role === 'manager' || role === 'master_admin';

  const tabs = useMemo(() => TABS_ALL.filter((t) => t.roles.includes(role)), [role]);
  const [tab, setTab] = useState(tabs[0]?.id || 'leave');

  // Switch to a valid tab if role-based filtering drops the current one.
  useEffect(() => {
    if (!tabs.find((t) => t.id === tab)) setTab(tabs[0]?.id || 'leave');
  }, [tabs, tab]);

  return (
    <div className="space-y-5 pulse-font-body" data-testid="staffing-console">
      <PageHeader
        title={isManager ? 'Staffing' : 'My shifts'}
        subtitle={isManager
          ? 'Rota, performance, payroll, and AI workforce optimisation.'
          : 'Your shifts, time off, and open shifts you can claim.'}
        icon={Users}
        helpId={isManager ? 'staffing-overview' : 'staffing-marketplace'}
        testId="staffing-header"
        actions={!isManager ? (
          <div className="text-[10px] font-semibold uppercase tracking-[0.18em] px-3 py-1 rounded-full" style={{ background: 'rgba(25,205,255,0.1)', color: 'var(--color-brand-cyan)' }} data-testid="staffing-staff-badge">
            Staff view
          </div>
        ) : null}
      />

      <PillTabBar
        activeId={tab}
        testId="staffing-tabs"
        ariaLabel="Staffing sections"
      >
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            data-pill-id={id}
            onClick={() => setTab(id)}
            className="flex-shrink-0 inline-flex items-center gap-2 px-4 py-2.5 rounded-full text-sm font-semibold transition-colors whitespace-nowrap"
            style={tab === id
              ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
              : { color: 'var(--theme-text-muted)', background: 'transparent' }}
            data-testid={`staffing-tab-${id}`}
          >
            <Icon size={14} /> {label}
          </button>
        ))}
      </PillTabBar>

      <div>
        {tab === 'rota'        && <RotaTab        headers={headers} isManager={isManager} />}
        {tab === 'staff'       && <StaffTab       headers={headers} />}
        {tab === 'leave'       && <LeaveTab       headers={headers} isManager={isManager} />}
        {tab === 'market'      && <MarketTab      headers={headers} isManager={isManager} />}
        {tab === 'performance' && <PerformanceTab headers={headers} />}
        {tab === 'payroll'     && <PayrollTab     headers={headers} />}
        {tab === 'live'        && <LiveFloorTab   headers={headers} />}
        {tab === 'rules'       && <RulesTab       headers={headers} />}
        {tab === 'announce'    && <AnnouncementsTab headers={headers} isManager={isManager} />}
        {tab === 'ai'          && <AIInsightsTab  headers={headers} />}
      </div>
    </div>
  );
}

// ───────────────────────────── Tabs ─────────────────────────────

function Card({ children, testId }) {
  return (
    <div
      className="rounded-2xl p-4 border"
      style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
      data-testid={testId}
    >{children}</div>
  );
}

function EmptyState({ icon: Icon, title, hint, testId }) {
  return (
    <div className="rounded-2xl p-10 border text-center" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} data-testid={testId}>
      <Icon size={22} style={{ color: 'var(--theme-text-muted)' }} className="mx-auto mb-2" />
      <div className="text-sm font-semibold pulse-font-heading mb-1" style={{ color: 'var(--theme-text)' }}>{title}</div>
      {hint && <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{hint}</div>}
    </div>
  );
}

// ─── Rota (drag-and-drop week view, manager only) ───
function RotaTab({ headers, isManager }) {
  const [weekStart, setWeekStart] = useState(() => {
    const d = new Date(); d.setHours(0, 0, 0, 0);
    d.setDate(d.getDate() - d.getDay() + 1); // Monday
    return d.toISOString().slice(0, 10);
  });
  const [shifts, setShifts] = useState([]);
  const [staff, setStaff] = useState([]);
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState(null); // { staff_id, date }

  const days = useMemo(() => {
    const start = new Date(weekStart);
    return Array.from({ length: 7 }).map((_, i) => {
      const d = new Date(start); d.setDate(start.getDate() + i);
      return d.toISOString().slice(0, 10);
    });
  }, [weekStart]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [sh, st] = await Promise.all([
        axios.get(`${API}/staffing/shifts`, { headers, params: { date_from: days[0], date_to: days[6] } }),
        axios.get(`${API}/staffing/staff`, { headers }),
      ]);
      setShifts(sh.data.shifts || []);
      setStaff(st.data.staff || []);
    } catch { /* noop */ }
    setLoading(false);
  }, [headers, days]);

  useEffect(() => { load(); }, [load]);

  const weekCost = shifts.reduce((s, x) => s + (x.labour_cost || 0), 0);
  const weekHours = shifts.reduce((s, x) => s + (x.hours || 0), 0);

  const addShift = async ({ staff_id, date, start_time, end_time, role }) => {
    try {
      await axios.post(`${API}/staffing/shifts`, { staff_id, date, start_time, end_time, role: role || 'reception', status: 'scheduled' }, { headers });
      setAdding(null);
      load();
    } catch (err) { alert(err.response?.data?.detail || 'Failed'); }
  };

  const deleteShift = async (id) => {
    if (!window.confirm('Delete this shift?')) return;
    try { await axios.delete(`${API}/staffing/shifts/${id}`, { headers }); load(); }
    catch { /* noop */ }
  };

  const copyWeek = async () => {
    const target = new Date(weekStart); target.setDate(target.getDate() + 7);
    try {
      await axios.post(`${API}/staffing/shifts/bulk`, { source_start: weekStart, target_start: target.toISOString().slice(0, 10) }, { headers });
      setWeekStart(target.toISOString().slice(0, 10));
      load();
    } catch (err) { alert(err.response?.data?.detail || 'Failed'); }
  };

  const shiftsFor = (staffId, date) => shifts.filter((s) => s.staff_id === staffId && s.date === date);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="inline-flex items-center gap-1 rounded-full border" style={{ borderColor: 'var(--theme-border)' }}>
          <button type="button" onClick={() => { const d = new Date(weekStart); d.setDate(d.getDate() - 7); setWeekStart(d.toISOString().slice(0,10)); }} className="w-8 h-8 inline-flex items-center justify-center" data-testid="rota-prev-week"><ChevronLeft size={14} /></button>
          <div className="text-xs font-semibold px-2" data-testid="rota-week-label">Week of {weekStart}</div>
          <button type="button" onClick={() => { const d = new Date(weekStart); d.setDate(d.getDate() + 7); setWeekStart(d.toISOString().slice(0,10)); }} className="w-8 h-8 inline-flex items-center justify-center" data-testid="rota-next-week"><ChevronRight size={14} /></button>
        </div>
        <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}>
          <span data-testid="rota-week-hours">{weekHours.toFixed(1)}h</span>
          <span>·</span>
          <span data-testid="rota-week-cost">£{weekCost.toFixed(2)} labour</span>
        </div>
        {isManager && (
          <button type="button" onClick={copyWeek} className="text-xs font-semibold inline-flex items-center gap-1 rounded-full px-3 py-1.5" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="rota-copy-week">
            <RefreshCw size={12} /> Copy to next week
          </button>
        )}
      </div>

      <Card testId="rota-grid">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr style={{ color: 'var(--theme-text-muted)' }}>
                <th className="text-left py-2 font-semibold px-2">Staff</th>
                {days.map((d) => (
                  <th key={d} className="text-left py-2 font-semibold px-2 whitespace-nowrap">{d.slice(5)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {staff.length === 0 ? (
                <tr><td colSpan={8} className="py-8 text-center" style={{ color: 'var(--theme-text-muted)' }}>No staff yet — add staff in the Staff tab.</td></tr>
              ) : staff.map((s) => (
                <tr key={s.id} className="border-t" style={{ borderColor: 'var(--theme-border)' }}>
                  <td className="py-2 px-2" data-testid={`rota-row-${s.id}`}>
                    <div className="text-sm font-semibold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{s.full_name}</div>
                    <div className="text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--theme-text-muted)' }}>{s.primary_role}</div>
                  </td>
                  {days.map((d) => (
                    <td key={d} className="py-2 px-1 align-top">
                      <div className="space-y-1">
                        {shiftsFor(s.id, d).map((sh) => (
                          <div key={sh.id} className="rounded-lg px-2 py-1 text-[11px] flex items-center gap-1 group" style={{ background: 'rgba(25,205,255,0.12)', color: 'var(--theme-text)' }} data-testid={`rota-shift-${sh.id}`}>
                            <Clock size={10} />
                            <span className="flex-1">{sh.start_time}–{sh.end_time}</span>
                            {isManager && <button type="button" onClick={() => deleteShift(sh.id)} className="opacity-0 group-hover:opacity-100 transition-opacity"><Trash2 size={10} /></button>}
                          </div>
                        ))}
                        {isManager && (
                          <button type="button" onClick={() => setAdding({ staff_id: s.id, date: d })} className="w-full rounded-lg px-2 py-1 text-[11px] opacity-40 hover:opacity-100 border border-dashed" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid={`rota-add-${s.id}-${d}`}>+</button>
                        )}
                      </div>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {loading && <div className="text-xs mt-2" style={{ color: 'var(--theme-text-muted)' }}>Loading…</div>}
      </Card>

      {adding && (
        <AddShiftDialog
          initial={adding}
          onCancel={() => setAdding(null)}
          onSubmit={addShift}
        />
      )}
    </div>
  );
}

function AddShiftDialog({ initial, onCancel, onSubmit }) {
  const [start_time, setStart] = useState('09:00');
  const [end_time, setEnd]     = useState('17:00');
  const [role, setRole]        = useState('reception');
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[70] p-4" data-testid="add-shift-dialog" onClick={onCancel}>
      <div className="rounded-2xl border p-5 w-full max-w-sm" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} onClick={(e) => e.stopPropagation()}>
        <div className="text-sm font-semibold pulse-font-heading mb-3" style={{ color: 'var(--theme-text)' }}>Add shift · {initial.date}</div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--theme-text-muted)' }}>Start</label>
            <input type="time" value={start_time} onChange={(e) => setStart(e.target.value)} className="w-full rounded-lg px-2 py-1.5 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="add-shift-start" />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--theme-text-muted)' }}>End</label>
            <input type="time" value={end_time} onChange={(e) => setEnd(e.target.value)} className="w-full rounded-lg px-2 py-1.5 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="add-shift-end" />
          </div>
          <div className="col-span-2">
            <label className="text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--theme-text-muted)' }}>Role</label>
            <select value={role} onChange={(e) => setRole(e.target.value)} className="w-full rounded-lg px-2 py-1.5 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="add-shift-role">
              {['reception','instructor','pt','manager','cleaner','maintenance','lifeguard','duty_manager','other'].map((r) => <option key={r}>{r}</option>)}
            </select>
          </div>
        </div>
        <div className="flex items-center gap-2 justify-end mt-4">
          <button type="button" onClick={onCancel} className="text-xs px-3 py-1.5 rounded-full border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid="add-shift-cancel">Cancel</button>
          <button type="button" onClick={() => onSubmit({ ...initial, start_time, end_time, role })} className="text-xs font-semibold px-3 py-1.5 rounded-full" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="add-shift-save">Save</button>
        </div>
      </div>
    </div>
  );
}

// ─── Staff directory (manager only) ───
function StaffTab({ headers }) {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ full_name: '', email: '', primary_role: 'reception', hourly_cost: 0, contract_type: 'part_time' });
  const [showAdd, setShowAdd] = useState(false);
  const load = useCallback(async () => {
    const r = await axios.get(`${API}/staffing/staff`, { headers });
    setRows(r.data.staff || []);
  }, [headers]);
  useEffect(() => { load(); }, [load]);
  const save = async () => {
    try { await axios.post(`${API}/staffing/staff`, form, { headers }); setShowAdd(false); setForm({ full_name: '', email: '', primary_role: 'reception', hourly_cost: 0, contract_type: 'part_time' }); load(); }
    catch (err) { alert(err.response?.data?.detail || 'Failed'); }
  };
  const archive = async (id) => { if (!window.confirm('Archive staff?')) return; await axios.delete(`${API}/staffing/staff/${id}`, { headers }); load(); };

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{rows.length} active staff</div>
        <button type="button" onClick={() => setShowAdd(true)} className="text-xs font-semibold inline-flex items-center gap-1 rounded-full px-3 py-1.5" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="staff-add-btn">
          <UserPlus size={12} /> Add staff
        </button>
      </div>

      {rows.length === 0 ? <EmptyState icon={Users} title="No staff yet" hint="Click 'Add staff' to build your roster." testId="staff-empty" /> : (
        <Card testId="staff-list">
          {/* Iter 215dj — wrap in overflow-x-auto so columns don't get
              clipped on mobile (was hiding the Hourly column on phones). */}
          <div className="overflow-x-auto -mx-2 sm:mx-0">
          <table className="w-full text-sm min-w-[34rem]">
            <thead>
              <tr className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
                <th className="text-left py-2 px-2 font-semibold">Name</th>
                <th className="text-left py-2 px-2 font-semibold">Role</th>
                <th className="text-left py-2 px-2 font-semibold">Contract</th>
                <th className="text-right py-2 px-2 font-semibold">Hourly</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`staff-row-${s.id}`}>
                  <td className="py-2 px-2 font-medium" style={{ color: 'var(--theme-text)' }}>{s.full_name}</td>
                  <td className="py-2 px-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}>{s.primary_role}</td>
                  <td className="py-2 px-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}>{s.contract_type || '—'}</td>
                  <td className="py-2 px-2 text-right text-xs" style={{ color: 'var(--theme-text)' }}>£{Number(s.hourly_cost || 0).toFixed(2)}</td>
                  <td className="py-2 px-2 text-right"><button type="button" onClick={() => archive(s.id)} className="opacity-60 hover:opacity-100" data-testid={`staff-archive-${s.id}`}><Trash2 size={12} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </Card>
      )}

      {showAdd && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[70] p-4" onClick={() => setShowAdd(false)}>
          <div className="rounded-2xl border p-5 w-full max-w-md" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }} onClick={(e) => e.stopPropagation()} data-testid="staff-add-dialog">
            <div className="text-sm font-semibold mb-3 pulse-font-heading" style={{ color: 'var(--theme-text)' }}>Add staff</div>
            <div className="space-y-2">
              <input placeholder="Full name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} className="w-full rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="staff-add-name" />
              <input placeholder="Email (optional — links to existing user)" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="w-full rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="staff-add-email" />
              <div className="grid grid-cols-2 gap-2">
                <select value={form.primary_role} onChange={(e) => setForm({ ...form, primary_role: e.target.value })} className="rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="staff-add-role">
                  {['reception','instructor','pt','manager','cleaner','maintenance','lifeguard','duty_manager','other'].map((r) => <option key={r}>{r}</option>)}
                </select>
                <select value={form.contract_type} onChange={(e) => setForm({ ...form, contract_type: e.target.value })} className="rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="staff-add-contract">
                  {['full_time','part_time','casual','contractor'].map((c) => <option key={c}>{c}</option>)}
                </select>
              </div>
              <input type="number" step="0.5" placeholder="Hourly cost £" value={form.hourly_cost} onChange={(e) => setForm({ ...form, hourly_cost: parseFloat(e.target.value) || 0 })} className="w-full rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="staff-add-hourly" />
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button type="button" onClick={() => setShowAdd(false)} className="text-xs px-3 py-1.5 rounded-full border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>Cancel</button>
              <button type="button" onClick={save} className="text-xs font-semibold px-3 py-1.5 rounded-full" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="staff-add-save">Add</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Leave ───
function LeaveTab({ headers, isManager }) {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ start_date: '', end_date: '', leave_type: 'holiday', reason: '' });
  const load = useCallback(async () => { const r = await axios.get(`${API}/staffing/leave`, { headers }); setRows(r.data.leave || []); }, [headers]);
  useEffect(() => { load(); }, [load]);
  const submit = async () => { try { await axios.post(`${API}/staffing/leave`, form, { headers }); setForm({ start_date: '', end_date: '', leave_type: 'holiday', reason: '' }); load(); } catch (err) { alert(err.response?.data?.detail || 'Failed'); } };
  const decide = async (id, status) => { await axios.patch(`${API}/staffing/leave/${id}`, { status }, { headers }); load(); };

  return (
    <div className="space-y-3">
      <Card testId="leave-form">
        <div className="text-xs font-semibold uppercase tracking-[0.14em] mb-2" style={{ color: 'var(--color-brand-cyan)' }}>Request time off</div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
          <input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} className="rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="leave-start" />
          <input type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} className="rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="leave-end" />
          <select value={form.leave_type} onChange={(e) => setForm({ ...form, leave_type: e.target.value })} className="rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="leave-type">
            {['holiday','sick','unpaid','training','other'].map((t) => <option key={t}>{t}</option>)}
          </select>
          <button type="button" onClick={submit} className="text-xs font-semibold rounded-full" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="leave-submit">Submit</button>
        </div>
        <input placeholder="Reason (optional)" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} className="mt-2 w-full rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} />
      </Card>

      {rows.length === 0 ? <EmptyState icon={Plane} title="No leave requests yet" testId="leave-empty" /> : (
        <Card testId="leave-list">
          <table className="w-full text-sm">
            <thead><tr className="text-xs" style={{ color: 'var(--theme-text-muted)' }}><th className="text-left py-2 px-2">Dates</th><th className="text-left py-2 px-2">Type</th><th className="text-left py-2 px-2">Status</th>{isManager && <th className="w-32" />}</tr></thead>
            <tbody>
              {rows.map((l) => (
                <tr key={l.id} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`leave-row-${l.id}`}>
                  <td className="py-2 px-2 text-xs">{l.start_date} → {l.end_date}</td>
                  <td className="py-2 px-2 text-xs uppercase tracking-[0.14em]" style={{ color: 'var(--theme-text-muted)' }}>{l.leave_type}</td>
                  <td className="py-2 px-2 text-xs"><StatusBadge status={l.status} /></td>
                  {isManager && l.status === 'pending' && (
                    <td className="py-2 px-2 text-right space-x-1">
                      <button type="button" onClick={() => decide(l.id, 'approved')} className="text-[10px] font-semibold rounded-full px-2 py-1" style={{ background: 'var(--color-success)', color: 'var(--color-emerald-dark)' }} data-testid={`leave-approve-${l.id}`}>Approve</button>
                      <button type="button" onClick={() => decide(l.id, 'rejected')} className="text-[10px] font-semibold rounded-full px-2 py-1 border" style={{ borderColor: 'var(--theme-border)' }} data-testid={`leave-reject-${l.id}`}>Reject</button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

function StatusBadge({ status }) {
  const colour = status === 'approved' ? 'var(--color-success)' : status === 'rejected' ? 'var(--color-danger)' : status === 'pending' ? 'var(--color-warning)' : 'var(--color-text-faint-alt)';
  return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-[0.14em]" style={{ background: `${colour}22`, color: colour }}>{status}</span>;
}

// ─── Shift Marketplace ───
function MarketTab({ headers, isManager }) {
  const [open, setOpen] = useState([]);
  const [reqs, setReqs] = useState([]);
  const load = useCallback(async () => {
    const [o, r] = await Promise.all([
      axios.get(`${API}/staffing/marketplace/open`, { headers }),
      axios.get(`${API}/staffing/marketplace/requests`, { headers }),
    ]);
    setOpen(o.data.open_shifts || []);
    setReqs(r.data.requests || []);
  }, [headers]);
  useEffect(() => { load(); }, [load]);
  const claim = async (id) => { try { await axios.post(`${API}/staffing/marketplace/open/${id}/claim`, {}, { headers }); load(); } catch (err) { alert(err.response?.data?.detail || 'Failed'); } };
  const decide = async (id, status) => { await axios.patch(`${API}/staffing/marketplace/requests/${id}`, { status }, { headers }); load(); };
  return (
    <div className="space-y-3">
      <Card testId="market-open">
        <div className="text-xs font-semibold uppercase tracking-[0.14em] mb-2" style={{ color: 'var(--color-brand-cyan)' }}>Open shifts · {open.length}</div>
        {open.length === 0 ? <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>No open shifts right now.</div> : (
          <div className="space-y-2">
            {open.map((s) => (
              <div key={s.id} className="flex items-center gap-3 rounded-lg border px-3 py-2" style={{ borderColor: 'var(--theme-border)' }} data-testid={`market-open-${s.id}`}>
                <Clock size={14} style={{ color: 'var(--color-brand-cyan)' }} />
                <div className="flex-1 text-sm">{s.date} · {s.start_time}–{s.end_time}<span className="ml-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}>{s.role}</span></div>
                <button type="button" onClick={() => claim(s.id)} className="text-xs font-semibold rounded-full px-3 py-1" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid={`market-claim-${s.id}`}>Claim</button>
              </div>
            ))}
          </div>
        )}
      </Card>
      <Card testId="market-requests">
        <div className="text-xs font-semibold uppercase tracking-[0.14em] mb-2" style={{ color: 'var(--color-brand-cyan)' }}>Requests · {reqs.length}</div>
        {reqs.length === 0 ? <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Nothing pending.</div> : (
          <ul className="space-y-2">
            {reqs.map((r) => (
              <li key={r.id} className="rounded-lg border px-3 py-2 flex items-center gap-3" style={{ borderColor: 'var(--theme-border)' }} data-testid={`market-req-${r.id}`}>
                <div className="text-xs flex-1">
                  <span className="uppercase tracking-[0.14em] mr-2" style={{ color: 'var(--theme-text-muted)' }}>{r.kind}</span>
                  <span>{r.offered_shift_id.slice(0, 8)}…</span>
                </div>
                <StatusBadge status={r.status} />
                {isManager && r.status === 'pending' && (
                  <>
                    <button type="button" onClick={() => decide(r.id, 'approved')} className="text-[10px] font-semibold rounded-full px-2 py-1" style={{ background: 'var(--color-success)', color: 'var(--color-emerald-dark)' }}>Approve</button>
                    <button type="button" onClick={() => decide(r.id, 'rejected')} className="text-[10px] font-semibold rounded-full px-2 py-1 border" style={{ borderColor: 'var(--theme-border)' }}>Reject</button>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

// ─── Performance ───
function PerformanceTab({ headers }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    axios.get(`${API}/staffing/performance`, { headers }).then((r) => setData(r.data)).catch(() => setData({ staff: [] }));
  }, [headers]);
  if (!data) return <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Loading…</div>;
  if (!data.staff || data.staff.length === 0) return <EmptyState icon={BarChart3} title="No performance data yet" hint="Add staff and shifts to see breakdowns." testId="perf-empty" />;
  return (
    <Card testId="perf-list">
      {/* Iter 215dj — wrap in overflow-x-auto + min-width so labour £ /
          classes / attendees columns don't clip on mobile. */}
      <div className="overflow-x-auto -mx-2 sm:mx-0">
      <table className="w-full text-sm min-w-[36rem]">
        <thead><tr className="text-xs" style={{ color: 'var(--theme-text-muted)' }}><th className="text-left py-2 px-2 whitespace-nowrap">Staff</th><th className="text-right py-2 px-2 whitespace-nowrap">Hours</th><th className="text-right py-2 px-2 whitespace-nowrap">Labour £</th><th className="text-right py-2 px-2 whitespace-nowrap">Classes</th><th className="text-right py-2 px-2 whitespace-nowrap">Attendees</th></tr></thead>
        <tbody>
          {data.staff.map((s) => (
            <tr key={s.staff_id} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`perf-row-${s.staff_id}`}>
              <td className="py-2 px-2"><div className="font-medium" style={{ color: 'var(--theme-text)' }}>{s.full_name}</div><div className="text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--theme-text-muted)' }}>{s.primary_role}</div></td>
              <td className="py-2 px-2 text-right tabular-nums">{s.hours_scheduled}</td>
              <td className="py-2 px-2 text-right tabular-nums">£{s.labour_cost}</td>
              <td className="py-2 px-2 text-right tabular-nums">{s.classes_delivered}</td>
              <td className="py-2 px-2 text-right tabular-nums">{s.attendees}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </Card>
  );
}

// ─── Payroll (export only) ───
function PayrollTab({ headers }) {
  const [from, setFrom] = useState(() => { const d = new Date(); d.setDate(1); return d.toISOString().slice(0,10); });
  const [to, setTo] = useState(() => new Date().toISOString().slice(0,10));
  const download = async () => {
    const token = headers.Authorization?.split(' ')[1];
    const r = await fetch(`${API}/staffing/payroll/export?date_from=${from}&date_to=${to}`, { headers: { Authorization: `Bearer ${token}` } });
    const blob = await r.blob();
    const url = URL.createObjectURL(blob); const a = document.createElement('a');
    a.href = url; a.download = `payroll-${from}-to-${to}.csv`; a.click(); URL.revokeObjectURL(url);
  };
  return (
    <Card testId="payroll-card">
      <div className="text-xs font-semibold uppercase tracking-[0.14em] mb-3" style={{ color: 'var(--color-brand-cyan)' }}>Export payroll CSV</div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="payroll-from" />
        <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="payroll-to" />
        <button type="button" onClick={download} className="text-xs font-semibold rounded-full inline-flex items-center gap-1 justify-center" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="payroll-download"><Download size={12} /> Download CSV</button>
      </div>
      <p className="text-[11px] mt-3" style={{ color: 'var(--theme-text-muted)' }}>Non-cancelled shifts only. Hours multiply by each staff&apos;s hourly cost.</p>
    </Card>
  );
}

// ─── Live Floor ───
function LiveFloorTab({ headers }) {
  const [data, setData] = useState(null);
  const load = useCallback(async () => { try { const r = await axios.get(`${API}/staffing/live-floor`, { headers }); setData(r.data); } catch { /* noop */ } }, [headers]);
  useEffect(() => { load(); const iv = setInterval(load, 60000); return () => clearInterval(iv); }, [load]);
  if (!data) return <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Loading…</div>;
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 text-xs" style={{ color: 'var(--theme-text-muted)' }}>
        <span className="inline-flex items-center gap-1"><div className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: 'var(--color-success)' }} />Live · {new Date(data.as_of).toLocaleTimeString()}</span>
        <span>{data.coverage.on_now} on now</span>
        <span>{data.coverage.open_shifts_today} open today</span>
      </div>
      <Card testId="live-now">
        <div className="text-xs font-semibold uppercase tracking-[0.14em] mb-2" style={{ color: 'var(--color-success)' }}>On the floor now</div>
        {data.on_now.length === 0 ? <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Nobody scheduled right now.</div> : (
          <ul className="space-y-1">
            {data.on_now.map((s) => (
              <li key={s.id} className="flex items-center gap-2 text-sm" data-testid={`live-now-${s.id}`}>
                <div className="w-7 h-7 rounded-full flex items-center justify-center" style={{ background: 'var(--color-success)22', color: 'var(--color-success)' }}>{(s.staff_name || '?').charAt(0).toUpperCase()}</div>
                <div className="flex-1">{s.staff_name}</div>
                <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{s.role} · until {s.end_time}</div>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card testId="live-upcoming">
        <div className="text-xs font-semibold uppercase tracking-[0.14em] mb-2" style={{ color: 'var(--color-brand-cyan)' }}>Up next today</div>
        {data.upcoming.length === 0 ? <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Nothing else scheduled today.</div> : (
          <ul className="space-y-1">
            {data.upcoming.map((s) => (
              <li key={s.id} className="flex items-center gap-2 text-sm" data-testid={`live-up-${s.id}`}>
                <Clock size={13} />
                <div className="flex-1">{s.staff_name}</div>
                <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{s.start_time}–{s.end_time} · {s.role}</div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

// ─── Rules (compliance) ───
function RulesTab({ headers }) {
  const [rules, setRules] = useState(null);
  useEffect(() => { axios.get(`${API}/staffing/rules`, { headers }).then((r) => setRules(r.data)); }, [headers]);
  const save = async () => { await axios.put(`${API}/staffing/rules`, rules, { headers }); alert('Rules saved'); };
  if (!rules) return <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Loading…</div>;
  const F = ({ k, label, step = '0.5' }) => (
    <div>
      <label className="text-[11px] uppercase tracking-[0.14em]" style={{ color: 'var(--theme-text-muted)' }}>{label}</label>
      <input type="number" step={step} value={rules[k] ?? 0} onChange={(e) => setRules({ ...rules, [k]: parseFloat(e.target.value) || 0 })} className="w-full rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid={`rules-${k}`} />
    </div>
  );
  return (
    <Card testId="rules-card">
      <div className="text-xs font-semibold uppercase tracking-[0.14em] mb-3" style={{ color: 'var(--color-brand-cyan)' }}>Compliance rules</div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <F k="max_hours_per_week" label="Max hours per week" />
        <F k="min_rest_hours_between_shifts" label="Min rest between shifts (h)" />
        <F k="min_break_minutes_per_shift" label="Min break per shift (min)" step="1" />
        <F k="max_days_consecutive" label="Max consecutive days" step="1" />
      </div>
      <button type="button" onClick={save} className="mt-4 text-xs font-semibold rounded-full px-4 py-2" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="rules-save">Save rules</button>
    </Card>
  );
}

// ─── Announcements ───
function AnnouncementsTab({ headers, isManager }) {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ title: '', body: '' });
  const load = useCallback(async () => { const r = await axios.get(`${API}/staffing/announcements`, { headers }); setRows(r.data.announcements || []); }, [headers]);
  useEffect(() => { load(); }, [load]);
  const submit = async () => { await axios.post(`${API}/staffing/announcements`, { ...form, audience: 'all' }, { headers }); setForm({ title: '', body: '' }); load(); };
  const remove = async (id) => { if (!window.confirm('Delete?')) return; await axios.delete(`${API}/staffing/announcements/${id}`, { headers }); load(); };
  return (
    <div className="space-y-3">
      {isManager && (
        <Card testId="announce-form">
          <div className="text-xs font-semibold uppercase tracking-[0.14em] mb-2" style={{ color: 'var(--color-brand-cyan)' }}>Post an announcement</div>
          <input placeholder="Title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="w-full rounded-lg px-3 py-2 text-sm border mb-2" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="announce-title" />
          <textarea placeholder="Message to staff…" value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} rows={3} className="w-full rounded-lg px-3 py-2 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="announce-body" />
          <button type="button" onClick={submit} disabled={!form.title || !form.body} className="mt-2 text-xs font-semibold rounded-full px-4 py-2 disabled:opacity-40" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }} data-testid="announce-post">Post</button>
        </Card>
      )}
      {rows.length === 0 ? <EmptyState icon={Megaphone} title="No announcements yet" testId="announce-empty" /> : (
        <div className="space-y-2">
          {rows.map((a) => (
            <Card key={a.id} testId={`announce-${a.id}`}>
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0" style={{ background: 'var(--color-brand-cyan)22', color: 'var(--color-brand-cyan)' }}><Megaphone size={14} /></div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{a.title}</div>
                  <div className="text-sm mt-1" style={{ color: 'var(--theme-text-muted)' }}>{a.body}</div>
                  <div className="text-[10px] uppercase tracking-[0.14em] mt-2" style={{ color: 'var(--theme-text-muted)' }}>{a.author_name} · {a.created_at?.slice(0, 10)}</div>
                </div>
                {isManager && <button type="button" onClick={() => remove(a.id)} className="opacity-60 hover:opacity-100" data-testid={`announce-del-${a.id}`}><Trash2 size={12} /></button>}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── AI Insights ───
function AIInsightsTab({ headers }) {
  const [data, setData] = useState(null);
  useEffect(() => { axios.get(`${API}/staffing/ai/insights`, { headers }).then((r) => setData(r.data)).catch(() => setData({ flags: [], narrative: 'No data yet.' })); }, [headers]);
  if (!data) return <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Analysing last 30 days…</div>;
  const DAYS = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  return (
    <div className="space-y-3">
      <Card testId="ai-narrative">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}><Sparkles size={14} /></div>
          <div className="flex-1 text-sm" style={{ color: 'var(--theme-text)' }}>{data.narrative}</div>
        </div>
      </Card>
      <Card testId="ai-flags">
        <div className="text-xs font-semibold uppercase tracking-[0.14em] mb-2" style={{ color: 'var(--color-brand-cyan)' }}>Flagged slots · {data.flags.length}</div>
        {data.flags.length === 0 ? <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>No anomalies in the last 30 days. Nice.</div> : (
          <ul className="space-y-1">
            {data.flags.map((f, i) => (
              <li key={i} className="flex items-center gap-2 text-sm" data-testid={`ai-flag-${i}`}>
                <AlertTriangle size={13} style={{ color: f.kind === 'understaffed' ? 'var(--color-danger)' : 'var(--color-warning)' }} />
                <span className="flex-1">{DAYS[f.weekday]} at {String(f.hour).padStart(2, '0')}:00 · {f.kind}</span>
                <span className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>demand {f.demand} / supply {f.supply}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
