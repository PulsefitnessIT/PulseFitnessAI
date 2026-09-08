/**
 * AttendanceTab — the manager face of the Attendance Spine.
 *
 * Three views over the single-source-of-truth daily records:
 *   • Board     — exception-based "Today's Attendance" (replaces the
 *                 Attendance Request spreadsheet). Managers manage
 *                 exceptions, not type "IN" for everyone.
 *   • Patterns  — reusable working patterns (not everyone is Mon–Fri).
 *   • Profiles  — per-staff work & payroll profile (extends staff_members).
 *
 * All data comes from /api/attendance/* — one approved leave or clock punch
 * already resolved into these records server-side (ENTER ONCE → USE EVERYWHERE).
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import {
  CalendarDays, RefreshCw, AlertTriangle, Users, Layers, IdCard,
  Plus, Trash2, Save, X, Check, Wand2, Loader2, Upload, FileSpreadsheet,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const REGION_LABEL = {
  'england-and-wales': 'England & Wales',
  scotland: 'Scotland',
  'northern-ireland': 'Northern Ireland',
};
const TIME_ENTRY = [
  ['live_clock', 'Live Clock'],
  ['daily_timesheet', 'Daily Timesheet'],
  ['auto_assisted', 'Auto-Assisted'],
  ['manager_entered', 'Manager-Entered'],
];
const OT_RULES = [
  ['auto', 'Automatically calculated'],
  ['manager_approval', 'Manager approval required'],
  ['pre_approved', 'Only pre-approved'],
  ['not_eligible', 'Not eligible'],
  ['toil', 'TOIL instead'],
];

function Badge({ status, statuses }) {
  const meta = (statuses && statuses[status]) || { label: status, color: '#94a3b8' };
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold"
      style={{ background: `${meta.color}1a`, color: meta.color }}>
      <span className="w-2 h-2 rounded-full" style={{ background: meta.color }} />
      {meta.label}
    </span>
  );
}

export default function AttendanceTab({ headers, isManager }) {
  const [view, setView] = useState('board');
  if (!isManager) {
    return <div className="text-sm text-slate-500" data-testid="attendance-mgr-only">Managers and owners only.</div>;
  }
  return (
    <div className="space-y-4" data-testid="attendance-tab">
      <div className="flex items-center gap-1.5 flex-wrap">
        {[['board', 'Attendance Board', CalendarDays], ['patterns', 'Working Patterns', Layers], ['profiles', 'Work Profiles', IdCard], ['import', 'Import', Upload]].map(([id, label, Icon]) => (
          <button key={id} onClick={() => setView(id)} data-testid={`attendance-view-${id}`}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors ${view === id ? 'border-cyan-500 text-cyan-700 bg-cyan-50' : 'border-slate-200 text-slate-500 hover:text-slate-700'}`}>
            <Icon size={13} /> {label}
          </button>
        ))}
      </div>
      {view === 'board' && <BoardView headers={headers} />}
      {view === 'patterns' && <PatternsView headers={headers} />}
      {view === 'profiles' && <ProfilesView headers={headers} />}
      {view === 'import' && <MigrationView headers={headers} />}
    </div>
  );
}

/* ─────────────────────────── Board ─────────────────────────── */
function BoardView({ headers }) {
  const [day, setDay] = useState(() => new Date().toISOString().slice(0, 10));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [correct, setCorrect] = useState(null);
  const [rtw, setRtw] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/attendance/board?date=${day}`, { headers });
      setData(r.data);
    } catch (e) { setData({ error: e?.response?.data?.detail || 'Failed to load' }); }
    setLoading(false);
  }, [day, headers]);

  useEffect(() => { load(); }, [load]);

  const s = data?.summary || {};
  const statuses = data?.statuses || {};
  const tiles = [
    ['Expected working', s.expected_working, '#0f172a'],
    ['Confirmed', s.confirmed, '#16a34a'],
    ['Holiday', s.holiday, '#2563eb'],
    ['Sick', s.sick, '#dc2626'],
    ['Off', s.off, '#94a3b8'],
    ['Needs attention', s.exceptions, '#f59e0b'],
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-end gap-3 flex-wrap">
        <label className="text-xs font-semibold text-slate-600">Date
          <input type="date" value={day} onChange={(e) => setDay(e.target.value)} data-testid="attendance-board-date"
            className="mt-1 block rounded-lg border border-slate-300 px-3 py-2 text-sm" /></label>
        <button onClick={load} data-testid="attendance-board-refresh"
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-900 text-white text-xs font-semibold">
          {loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} Refresh
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-6 gap-2" data-testid="attendance-board-summary">
        {tiles.map(([label, val, color]) => (
          <div key={label} className="rounded-xl border border-slate-200 p-3 bg-white">
            <div className="text-2xl font-bold" style={{ color }}>{val ?? 0}</div>
            <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">{label}</div>
          </div>
        ))}
      </div>

      {s.exceptions > 0 && (
        <div className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-sm text-amber-800" data-testid="attendance-board-exception-banner">
          <AlertTriangle size={15} /> {s.exceptions} attendance record{s.exceptions === 1 ? '' : 's'} need your attention — everyone else is resolved automatically.
        </div>
      )}

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-3 py-2">Employee</th>
              <th className="text-left px-3 py-2">Status</th>
              <th className="text-left px-3 py-2">Start</th>
              <th className="text-left px-3 py-2">Finish</th>
              <th className="text-left px-3 py-2">Hours</th>
              <th className="text-left px-3 py-2">Source</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {(data?.rows || []).map((r) => (
              <tr key={r.staff_id} data-testid={`attendance-row-${r.staff_id}`}
                className={`border-t border-slate-100 ${r.is_exception ? 'bg-amber-50/40' : ''}`}>
                <td className="px-3 py-2 font-semibold text-slate-800">{r.full_name}
                  {r.department && <span className="ml-2 text-[11px] text-slate-400">{r.department}</span>}</td>
                <td className="px-3 py-2"><Badge status={r.status} statuses={statuses} /></td>
                <td className="px-3 py-2 text-slate-600">{r.start_time || '—'}</td>
                <td className="px-3 py-2 text-slate-600">{r.finish_time || '—'}</td>
                <td className="px-3 py-2 text-slate-600">{r.regular_hours ? `${r.regular_hours}h` : (r.expected_hours ? `${r.expected_hours}h exp` : '—')}</td>
                <td className="px-3 py-2 text-[11px] text-slate-400">{r.manual_override ? 'manager' : (r.source || '').replace(/_/g, ' ')}</td>
                <td className="px-3 py-2 text-right whitespace-nowrap">
                  {r.status === 'sick' && r.leave_event_id && (
                    <button onClick={() => setRtw(r)} data-testid={`attendance-rtw-${r.staff_id}`}
                      className="text-xs font-semibold text-emerald-600 hover:underline mr-3">Return to work</button>
                  )}
                  <button onClick={() => setCorrect(r)} data-testid={`attendance-correct-${r.staff_id}`}
                    className="text-xs font-semibold text-cyan-700 hover:underline">Correct</button>
                </td>
              </tr>
            ))}
            {data && !data.rows?.length && (
              <tr><td colSpan={7} className="px-3 py-6 text-center text-slate-400">No active staff for this org.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {correct && (
        <CorrectModal row={correct} statuses={statuses} headers={headers}
          onClose={() => setCorrect(null)} onSaved={() => { setCorrect(null); load(); }} />
      )}
      {rtw && (
        <ReturnToWorkModal row={rtw} headers={headers}
          onClose={() => setRtw(null)} onSaved={() => { setRtw(null); load(); }} />
      )}
    </div>
  );
}

function CorrectModal({ row, statuses, headers, onClose, onSaved }) {
  const [status, setStatus] = useState(row.status);
  const [start, setStart] = useState(row.start_time || '');
  const [finish, setFinish] = useState(row.finish_time || '');
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const save = async () => {
    if (!reason.trim()) { setErr('A reason is required.'); return; }
    setSaving(true); setErr('');
    try {
      await axios.patch(`${API}/attendance/daily/${row.record_id}`,
        { actual_status: status, start_time: start || null, finish_time: finish || null, reason },
        { headers });
      onSaved();
    } catch (e) { setErr(e?.response?.data?.detail || 'Save failed'); setSaving(false); }
  };

  return createPortal(
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/40 p-4" data-testid="attendance-correct-modal">
      <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-2xl">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-bold text-slate-900">Correct — {row.full_name}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={18} /></button>
        </div>
        <label className="block text-xs font-semibold text-slate-600 mb-2">Status
          <select value={status} onChange={(e) => setStatus(e.target.value)} data-testid="attendance-correct-status"
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
            {Object.entries(statuses).map(([k, m]) => <option key={k} value={k}>{m.label}</option>)}
          </select></label>
        <div className="grid grid-cols-2 gap-2 mb-2">
          <label className="block text-xs font-semibold text-slate-600">Start
            <input type="time" value={start} onChange={(e) => setStart(e.target.value)} data-testid="attendance-correct-start"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" /></label>
          <label className="block text-xs font-semibold text-slate-600">Finish
            <input type="time" value={finish} onChange={(e) => setFinish(e.target.value)} data-testid="attendance-correct-finish"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" /></label>
        </div>
        <label className="block text-xs font-semibold text-slate-600 mb-3">Reason (required)
          <input value={reason} onChange={(e) => setReason(e.target.value)} data-testid="attendance-correct-reason"
            placeholder="Why is this being changed?" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" /></label>
        {err && <div className="text-xs text-rose-600 mb-2" data-testid="attendance-correct-error">{err}</div>}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-2 rounded-lg text-sm font-semibold text-slate-600">Cancel</button>
          <button onClick={save} disabled={saving} data-testid="attendance-correct-save"
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-cyan-600 text-white text-sm font-semibold disabled:opacity-60">
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Save correction
          </button>
        </div>
      </div>
    </div>, document.body);
}

function ReturnToWorkModal({ row, headers, onClose, onSaved }) {
  const [rd, setRd] = useState(() => new Date().toISOString().slice(0, 10));
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');
  const save = async () => {
    setSaving(true); setErr('');
    try {
      await axios.post(`${API}/attendance/absence/${row.leave_event_id}/close`, { return_date: rd }, { headers });
      onSaved();
    } catch (e) { setErr(e?.response?.data?.detail || 'Could not close absence'); setSaving(false); }
  };
  return createPortal(
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/40 p-4" data-testid="attendance-rtw-modal">
      <div className="w-full max-w-sm rounded-2xl bg-white p-5 shadow-2xl">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-base font-bold text-slate-900">Return to work — {row.full_name}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={18} /></button>
        </div>
        <p className="text-xs text-slate-500 mb-3">Set the first day back. Days from then on stop being marked sick.</p>
        <label className="block text-xs font-semibold text-slate-600 mb-3">First day back
          <input type="date" value={rd} onChange={(e) => setRd(e.target.value)} data-testid="attendance-rtw-date"
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" /></label>
        {err && <div className="text-xs text-rose-600 mb-2" data-testid="attendance-rtw-error">{err}</div>}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-2 rounded-lg text-sm font-semibold text-slate-600">Cancel</button>
          <button onClick={save} disabled={saving} data-testid="attendance-rtw-save"
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm font-semibold disabled:opacity-60">
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Close absence
          </button>
        </div>
      </div>
    </div>, document.body);
}
function blankDays() {
  return Array.from({ length: 7 }, (_, dow) => ({
    dow, working: dow < 5, start: dow < 5 ? '09:00' : null, finish: dow < 5 ? '17:00' : null,
    break_minutes: dow < 5 ? 30 : 0, expected_hours: dow < 5 ? 7.5 : 0,
  }));
}

function PatternsView({ headers }) {
  const [patterns, setPatterns] = useState([]);
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const r = await axios.get(`${API}/attendance/patterns`, { headers });
    setPatterns(r.data.patterns || []);
  }, [headers]);
  useEffect(() => { load(); }, [load]);

  const seed = async () => {
    setBusy(true);
    await axios.post(`${API}/attendance/patterns/seed-defaults`, {}, { headers });
    await load(); setBusy(false);
  };
  const save = async () => {
    const body = { name: editing.name, type: editing.type, days: editing.days };
    if (editing.id) await axios.put(`${API}/attendance/patterns/${editing.id}`, body, { headers });
    else await axios.post(`${API}/attendance/patterns`, body, { headers });
    setEditing(null); await load();
  };
  const del = async (id) => { await axios.delete(`${API}/attendance/patterns/${id}`, { headers }); await load(); };

  return (
    <div className="space-y-4" data-testid="attendance-patterns">
      <div className="flex gap-2">
        <button onClick={() => setEditing({ name: '', type: 'standard', days: blankDays() })} data-testid="attendance-pattern-new"
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-cyan-600 text-white text-xs font-semibold"><Plus size={13} /> New pattern</button>
        <button onClick={seed} disabled={busy} data-testid="attendance-pattern-seed"
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-300 text-slate-700 text-xs font-semibold">
          {busy ? <Loader2 size={13} className="animate-spin" /> : <Wand2 size={13} />} Seed default patterns</button>
      </div>

      <div className="grid md:grid-cols-2 gap-3">
        {patterns.map((p) => (
          <div key={p.id} className="rounded-xl border border-slate-200 bg-white p-4" data-testid={`attendance-pattern-${p.id}`}>
            <div className="flex items-start justify-between">
              <div>
                <div className="font-semibold text-slate-800">{p.name}</div>
                <div className="text-[11px] uppercase tracking-wide text-slate-400">{p.type}</div>
              </div>
              <div className="flex gap-2">
                <button onClick={() => setEditing({ ...p, days: p.days?.length ? p.days : blankDays() })} className="text-xs font-semibold text-cyan-700">Edit</button>
                <button onClick={() => del(p.id)} data-testid={`attendance-pattern-del-${p.id}`} className="text-rose-500"><Trash2 size={14} /></button>
              </div>
            </div>
            <div className="mt-2 flex gap-1 flex-wrap">
              {(p.days || []).filter((d) => d.working).map((d) => (
                <span key={d.dow} className="text-[11px] px-2 py-0.5 rounded bg-slate-100 text-slate-600">{DOW[d.dow]} {d.start}–{d.finish}</span>
              ))}
            </div>
          </div>
        ))}
        {!patterns.length && <div className="text-sm text-slate-400">No patterns yet — seed the defaults or create one.</div>}
      </div>

      {editing && createPortal(
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/40 p-4" data-testid="attendance-pattern-modal">
          <div className="w-full max-w-lg rounded-2xl bg-white p-5 shadow-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-base font-bold text-slate-900">{editing.id ? 'Edit' : 'New'} working pattern</h3>
              <button onClick={() => setEditing(null)} className="text-slate-400"><X size={18} /></button>
            </div>
            <div className="grid grid-cols-2 gap-2 mb-3">
              <label className="block text-xs font-semibold text-slate-600">Name
                <input value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} data-testid="attendance-pattern-name"
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" /></label>
              <label className="block text-xs font-semibold text-slate-600">Type
                <select value={editing.type} onChange={(e) => setEditing({ ...editing, type: e.target.value })}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
                  {['standard', 'shift', 'part_time', 'engineer', 'flexible', 'custom'].map((t) => <option key={t} value={t}>{t}</option>)}
                </select></label>
            </div>
            <div className="space-y-1.5">
              {editing.days.map((d, i) => (
                <div key={d.dow} className="flex items-center gap-2 text-xs">
                  <label className="w-24 flex items-center gap-1.5 font-semibold text-slate-600">
                    <input type="checkbox" checked={d.working} data-testid={`attendance-pattern-day-${d.dow}`}
                      onChange={(e) => { const days = [...editing.days]; days[i] = { ...d, working: e.target.checked }; setEditing({ ...editing, days }); }} />
                    {DOW[d.dow]}</label>
                  <input type="time" value={d.start || ''} disabled={!d.working}
                    onChange={(e) => { const days = [...editing.days]; days[i] = { ...d, start: e.target.value }; setEditing({ ...editing, days }); }}
                    className="rounded border border-slate-300 px-2 py-1 disabled:bg-slate-50" />
                  <input type="time" value={d.finish || ''} disabled={!d.working}
                    onChange={(e) => { const days = [...editing.days]; days[i] = { ...d, finish: e.target.value }; setEditing({ ...editing, days }); }}
                    className="rounded border border-slate-300 px-2 py-1 disabled:bg-slate-50" />
                  <input type="number" value={d.break_minutes || 0} disabled={!d.working} title="Break minutes"
                    onChange={(e) => { const days = [...editing.days]; days[i] = { ...d, break_minutes: Number(e.target.value) }; setEditing({ ...editing, days }); }}
                    className="w-16 rounded border border-slate-300 px-2 py-1 disabled:bg-slate-50" />
                  <input type="number" step="0.25" value={d.expected_hours || 0} disabled={!d.working} title="Expected hours"
                    onChange={(e) => { const days = [...editing.days]; days[i] = { ...d, expected_hours: Number(e.target.value) }; setEditing({ ...editing, days }); }}
                    className="w-16 rounded border border-slate-300 px-2 py-1 disabled:bg-slate-50" />
                </div>
              ))}
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setEditing(null)} className="px-3 py-2 rounded-lg text-sm font-semibold text-slate-600">Cancel</button>
              <button onClick={save} data-testid="attendance-pattern-save" className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-cyan-600 text-white text-sm font-semibold"><Save size={14} /> Save</button>
            </div>
          </div>
        </div>, document.body)}
    </div>
  );
}

/* ─────────────────────────── Profiles ─────────────────────────── */
function ProfilesView({ headers }) {
  const [data, setData] = useState({ profiles: [], patterns: [], regions: [] });
  const [editing, setEditing] = useState(null);

  const load = useCallback(async () => {
    const r = await axios.get(`${API}/attendance/work-profiles`, { headers });
    setData(r.data);
  }, [headers]);
  useEffect(() => { load(); }, [load]);

  const patName = useCallback((id) => data.patterns.find((p) => p.id === id)?.name, [data.patterns]);

  const save = async () => {
    const b = editing;
    await axios.put(`${API}/attendance/work-profile/${b.staff_id}`, {
      payroll_number: b.payroll_number || null,
      job_title: b.job_title || null,
      working_pattern_id: b.working_pattern_id || null,
      standard_daily_hours: b.standard_daily_hours != null ? Number(b.standard_daily_hours) : null,
      bank_holiday_region: b.bank_holiday_region || null,
      time_entry_method: b.time_entry_method || null,
      overtime_eligibility: !!b.overtime_eligibility,
      overtime_rule: b.overtime_rule || null,
      employment_status: b.employment_status || null,
      start_date: b.start_date || null,
    }, { headers });
    setEditing(null); await load();
  };

  return (
    <div className="space-y-3" data-testid="attendance-profiles">
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-3 py-2">Employee</th>
              <th className="text-left px-3 py-2">Payroll #</th>
              <th className="text-left px-3 py-2">Pattern</th>
              <th className="text-left px-3 py-2">Daily hrs</th>
              <th className="text-left px-3 py-2">BH region</th>
              <th className="text-left px-3 py-2">Time entry</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {data.profiles.map((p) => (
              <tr key={p.staff_id} className="border-t border-slate-100" data-testid={`attendance-profile-${p.staff_id}`}>
                <td className="px-3 py-2 font-semibold text-slate-800">{p.full_name}
                  {p.job_title && <span className="ml-2 text-[11px] text-slate-400">{p.job_title}</span>}</td>
                <td className="px-3 py-2 text-slate-600">{p.payroll_number || '—'}</td>
                <td className="px-3 py-2 text-slate-600">{patName(p.working_pattern_id) || 'Default'}</td>
                <td className="px-3 py-2 text-slate-600">{p.standard_daily_hours ?? '—'}</td>
                <td className="px-3 py-2 text-slate-600">{REGION_LABEL[p.bank_holiday_region] || p.bank_holiday_region}</td>
                <td className="px-3 py-2 text-slate-600">{(TIME_ENTRY.find((t) => t[0] === p.time_entry_method) || [])[1] || p.time_entry_method}</td>
                <td className="px-3 py-2 text-right">
                  <button onClick={() => setEditing({ ...p })} data-testid={`attendance-profile-edit-${p.staff_id}`}
                    className="text-xs font-semibold text-cyan-700 hover:underline">Edit</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && createPortal(
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/40 p-4" data-testid="attendance-profile-modal">
          <div className="w-full max-w-lg rounded-2xl bg-white p-5 shadow-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-base font-bold text-slate-900">Work profile — {editing.full_name}</h3>
              <button onClick={() => setEditing(null)} className="text-slate-400"><X size={18} /></button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Payroll number"><input value={editing.payroll_number || ''} data-testid="attendance-profile-payroll"
                onChange={(e) => setEditing({ ...editing, payroll_number: e.target.value })} className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" /></Field>
              <Field label="Job title"><input value={editing.job_title || ''}
                onChange={(e) => setEditing({ ...editing, job_title: e.target.value })} className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" /></Field>
              <Field label="Working pattern"><select value={editing.working_pattern_id || ''} data-testid="attendance-profile-pattern"
                onChange={(e) => setEditing({ ...editing, working_pattern_id: e.target.value })} className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
                <option value="">Default (from hours)</option>
                {data.patterns.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select></Field>
              <Field label="Standard daily hours"><input type="number" step="0.25" value={editing.standard_daily_hours ?? ''}
                onChange={(e) => setEditing({ ...editing, standard_daily_hours: e.target.value })} className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" /></Field>
              <Field label="Bank holiday region"><select value={editing.bank_holiday_region || ''} data-testid="attendance-profile-region"
                onChange={(e) => setEditing({ ...editing, bank_holiday_region: e.target.value })} className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
                {(data.regions || []).map((r) => <option key={r} value={r}>{REGION_LABEL[r] || r}</option>)}
              </select></Field>
              <Field label="Time entry method"><select value={editing.time_entry_method || ''} data-testid="attendance-profile-time-entry"
                onChange={(e) => setEditing({ ...editing, time_entry_method: e.target.value })} className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
                {TIME_ENTRY.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select></Field>
              <Field label="Overtime rule"><select value={editing.overtime_rule || ''}
                onChange={(e) => setEditing({ ...editing, overtime_rule: e.target.value })} className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
                {OT_RULES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select></Field>
              <Field label="Employment status"><select value={editing.employment_status || 'active'}
                onChange={(e) => setEditing({ ...editing, employment_status: e.target.value })} className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
                {['active', 'probation', 'leaver', 'on_leave'].map((s) => <option key={s} value={s}>{s}</option>)}
              </select></Field>
              <label className="col-span-2 flex items-center gap-2 text-xs font-semibold text-slate-600">
                <input type="checkbox" checked={!!editing.overtime_eligibility} data-testid="attendance-profile-ot-eligible"
                  onChange={(e) => setEditing({ ...editing, overtime_eligibility: e.target.checked })} /> Eligible for overtime</label>
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setEditing(null)} className="px-3 py-2 rounded-lg text-sm font-semibold text-slate-600">Cancel</button>
              <button onClick={save} data-testid="attendance-profile-save" className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-cyan-600 text-white text-sm font-semibold"><Save size={14} /> Save profile</button>
            </div>
          </div>
        </div>, document.body)}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block text-xs font-semibold text-slate-600">
      <span className="block mb-1">{label}</span>{children}
    </label>
  );
}

/* ─────────────── Migration / Import (§74–§76) ─────────────── */
function MigrationView({ headers }) {
  return (
    <div className="space-y-4" data-testid="attendance-import">
      <p className="text-sm text-slate-500">Import your legacy spreadsheets into the single source of truth. Preview first — nothing is written until you commit, and existing employees are matched, never duplicated.</p>
      <div className="grid md:grid-cols-2 gap-4">
        <ImportCard headers={headers} kind="attendance"
          title="Attendance Request" hint="The year grid of IN / HOL / BH / SICK / COMP / OFF." />
        <ImportCard headers={headers} kind="timesheet"
          title="Timesheets" hint="One employee's month sheets (start/finish/break/PT/classes)." />
      </div>
    </div>
  );
}

function ImportCard({ headers, kind, title, hint }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState('');
  const [err, setErr] = useState('');
  const base = kind === 'attendance' ? 'attendance' : 'timesheets';

  const call = async (action) => {
    if (!file) { setErr('Choose a file first.'); return; }
    setBusy(action); setErr('');
    const fd = new FormData(); fd.append('file', file);
    try {
      const r = await axios.post(`${API}/migration/${base}/${action}`, fd,
        { headers: { ...headers, 'Content-Type': 'multipart/form-data' } });
      if (action === 'preview') { setPreview(r.data); setResult(null); }
      else { setResult(r.data); }
    } catch (e) { setErr(e?.response?.data?.detail || 'Failed'); }
    setBusy('');
  };

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4" data-testid={`import-card-${kind}`}>
      <div className="flex items-center gap-2 mb-1"><FileSpreadsheet size={16} className="text-cyan-600" /><h3 className="font-bold text-slate-900">{title}</h3></div>
      <p className="text-xs text-slate-500 mb-3">{hint}</p>
      <input type="file" accept=".xlsx" onChange={(e) => { setFile(e.target.files[0]); setPreview(null); setResult(null); }} data-testid={`import-file-${kind}`}
        className="block w-full text-xs text-slate-600 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-slate-100 file:text-slate-700 file:font-semibold" />
      <div className="mt-3 flex gap-2">
        <button onClick={() => call('preview')} disabled={busy} data-testid={`import-preview-${kind}`}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-300 text-slate-700 text-xs font-semibold">
          {busy === 'preview' ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />} Preview</button>
        {preview && <button onClick={() => call('commit')} disabled={busy} data-testid={`import-commit-${kind}`}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-cyan-600 text-white text-xs font-semibold">
          {busy === 'commit' ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} Commit import</button>}
      </div>
      {err && <div className="mt-2 text-xs text-rose-600" data-testid={`import-error-${kind}`}>{err}</div>}

      {preview && (
        <div className="mt-3 rounded-lg bg-slate-50 p-3 text-xs" data-testid={`import-preview-result-${kind}`}>
          {kind === 'attendance' ? (
            <>
              <div className="font-semibold text-slate-700">{preview.rows_parsed} rows · {preview.date_range?.from} → {preview.date_range?.to}</div>
              <div className="mt-1 text-emerald-700">Matched employees: {preview.employees_matched.length}</div>
              {preview.employees_unmatched.length > 0 && <div className="text-amber-700">Unmatched (will be skipped): {preview.employees_unmatched.join(', ')}</div>}
              <div className="mt-1 flex gap-2 flex-wrap">{Object.entries(preview.by_status).map(([k, v]) => <span key={k} className="px-1.5 py-0.5 rounded bg-white border border-slate-200">{k}: {v}</span>)}</div>
            </>
          ) : (
            <>
              <div className="font-semibold text-slate-700">{preview.employee_name || 'No name found'} {preview.employee_matched ? <span className="text-emerald-600">✓ matched</span> : <span className="text-amber-600">not matched</span>}</div>
              <div className="mt-1">{preview.days_parsed} days · {preview.totals?.hours}h · PT {preview.totals?.pt} · Classes {preview.totals?.classes}</div>
              {preview.conflicts?.length > 0 && (
                <div className="mt-2 text-rose-600 font-semibold" data-testid="import-conflicts">⚠ {preview.conflicts.length} conflict(s) — review required:</div>
              )}
              {(preview.conflicts || []).slice(0, 5).map((c) => (
                <div key={c.date} className="text-rose-600">{c.date}: attendance {c.attendance} vs timesheet {c.timesheet_hours}h</div>
              ))}
            </>
          )}
        </div>
      )}

      {result && (
        <div className="mt-2 rounded-lg bg-emerald-50 border border-emerald-200 p-3 text-xs text-emerald-800" data-testid={`import-commit-result-${kind}`}>
          {kind === 'attendance'
            ? <>Imported {result.written} records. Skipped {result.skipped}{result.unmatched?.length ? ` · unmatched: ${result.unmatched.join(', ')}` : ''}.</>
            : <>Imported {result.written} days for {result.employee}{result.skipped_conflicts ? ` · ${result.skipped_conflicts} conflict day(s) skipped` : ''}.</>}
        </div>
      )}
    </div>
  );
}

