/**
 * Phase S2 — Time Clock & Timesheets (manager view).
 *
 * Single tab with three stacked panels:
 *
 *   1. Live punch board   — every active staff member, their state
 *      (off / on shift / on break), their last punch, today's
 *      scheduled shift, late flag.
 *   2. Weekly timesheets  — auto-built from punches + shifts. Approve
 *      / dispute per row; expand to see line items per shift with
 *      scheduled vs actual + late minutes.
 *   3. Kiosks             — manage shared front-desk kiosks (PINs).
 *
 * The clock board auto-refreshes every 30s.
 */
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  Activity, Loader2, Check, AlertTriangle, ChevronDown, ChevronRight,
  Plus, Trash2, Pencil, X, Clock, ClipboardCheck, Smartphone, RefreshCw,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STATE_TINT = {
  on_shift: '#10B981',
  on_break: '#F59E0B',
  off: '#94A3B8',
};
const STATE_LABEL = { on_shift: 'On shift', on_break: 'On break', off: 'Off' };

function fmtTime(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
  catch { return iso; }
}
function fmtGBP(n) { return `£${(Number(n) || 0).toFixed(2)}`; }
function startOfWeek() {
  const d = new Date(); d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return d.toISOString().slice(0, 10);
}

function ClockBoard({ headers }) {
  const [data, setData] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (bg = false) => {
    if (!bg) setData(null);
    else setRefreshing(true);
    try {
      const { data: d } = await axios.get(`${API}/staffing/clock/board`, { headers });
      setData(d);
    } catch { /* noop */ }
    setRefreshing(false);
  }, [headers]);

  useEffect(() => {
    load();
    const i = setInterval(() => { if (document.visibilityState === 'visible') load(true); }, 30_000);
    return () => clearInterval(i);
  }, [load]);

  if (!data) return <div className="py-6 text-xs inline-flex items-center gap-2" style={{ color: 'var(--theme-text-muted)' }}><Loader2 size={14} className="animate-spin" /> Loading board…</div>;
  const s = data.summary || {};
  return (
    <div className="rounded-xl border p-4 space-y-3" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="clock-board">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <p className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: 'var(--color-brand-cyan)' }}>Live punch board</p>
          <p className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>{data.rows?.length || 0} staff · refreshes every 30s</p>
        </div>
        <button type="button" onClick={() => load(true)} className="h-8 inline-flex items-center gap-1.5 rounded-full border px-3 text-xs font-bold"
          style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid="clock-board-refresh">
          <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
        <div className="rounded-lg border p-2" style={{ borderColor: 'var(--theme-border)' }}>
          <p className="text-[10px] uppercase tracking-wider font-bold" style={{ color: '#10B981' }}>On shift</p>
          <p className="text-xl font-bold tabular-nums" style={{ color: 'var(--theme-text)' }}>{s.on_shift || 0}</p>
        </div>
        <div className="rounded-lg border p-2" style={{ borderColor: 'var(--theme-border)' }}>
          <p className="text-[10px] uppercase tracking-wider font-bold" style={{ color: '#F59E0B' }}>On break</p>
          <p className="text-xl font-bold tabular-nums" style={{ color: 'var(--theme-text)' }}>{s.on_break || 0}</p>
        </div>
        <div className="rounded-lg border p-2" style={{ borderColor: 'var(--theme-border)' }}>
          <p className="text-[10px] uppercase tracking-wider font-bold" style={{ color: '#EF4444' }}>Late</p>
          <p className="text-xl font-bold tabular-nums" style={{ color: 'var(--theme-text)' }}>{s.late || 0}</p>
        </div>
        <div className="rounded-lg border p-2" style={{ borderColor: 'var(--theme-border)' }}>
          <p className="text-[10px] uppercase tracking-wider font-bold" style={{ color: '#94A3B8' }}>Off</p>
          <p className="text-xl font-bold tabular-nums" style={{ color: 'var(--theme-text)' }}>{s.off || 0}</p>
        </div>
      </div>
      {(data.rows || []).length === 0 ? (
        <p className="text-xs py-2" style={{ color: 'var(--theme-text-muted)' }}>No active staff yet.</p>
      ) : (
        <div className="overflow-x-auto -mx-2">
          <table className="w-full text-xs">
            <thead>
              <tr style={{ color: 'var(--theme-text-muted)' }}>
                <th className="text-left font-semibold py-1.5 px-2">Staff</th>
                <th className="text-left font-semibold py-1.5 px-2">State</th>
                <th className="text-left font-semibold py-1.5 px-2">Last punch</th>
                <th className="text-left font-semibold py-1.5 px-2">Today</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r.staff_id} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`board-row-${r.staff_id}`}>
                  <td className="py-2 px-2">
                    <div className="font-bold" style={{ color: 'var(--theme-text)' }}>{r.staff_name}</div>
                    <div className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--theme-text-muted)' }}>{r.primary_role}</div>
                  </td>
                  <td className="py-2 px-2">
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold" style={{ background: STATE_TINT[r.state] + '22', color: STATE_TINT[r.state] }}>
                      <span className="w-1.5 h-1.5 rounded-full" style={{ background: STATE_TINT[r.state] }} />
                      {STATE_LABEL[r.state]}
                    </span>
                    {r.late && (
                      <span className="ml-1.5 text-[10px] font-bold uppercase" style={{ color: '#EF4444' }}>· LATE</span>
                    )}
                  </td>
                  <td className="py-2 px-2 tabular-nums" style={{ color: 'var(--theme-text-muted)' }}>
                    {r.last_event ? `${r.last_event.kind.replace('_', ' ')} · ${fmtTime(r.last_event.occurred_at)}` : '—'}
                  </td>
                  <td className="py-2 px-2 tabular-nums" style={{ color: 'var(--theme-text-muted)' }}>
                    {r.todays_shift ? `${r.todays_shift.start_time}–${r.todays_shift.end_time}` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function TimesheetRow({ ts, onApprove, onDispute }) {
  const [open, setOpen] = useState(false);
  const tint = ts.approval_status === 'approved' ? '#10B981'
    : ts.approval_status === 'disputed' ? '#EF4444'
    : '#F59E0B';
  return (
    <div className="rounded-lg border" style={{ borderColor: 'var(--theme-border)' }} data-testid={`timesheet-${ts.id}`}>
      <button type="button" onClick={() => setOpen(!open)} className="w-full flex items-center justify-between gap-2 p-3 text-left">
        <div className="flex items-center gap-2 min-w-0">
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <div className="min-w-0">
            <p className="text-sm font-bold truncate" style={{ color: 'var(--theme-text)' }}>{ts.staff_name}</p>
            <p className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>
              {ts.actual_hours}h actual · {ts.scheduled_hours}h scheduled
              {ts.overtime_hours > 0 && <span> · {ts.overtime_hours}h OT</span>}
              {ts.late_total_minutes > 0 && <span> · {ts.late_total_minutes}m late</span>}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full" style={{ background: tint + '22', color: tint }}>
            {ts.approval_status}
          </span>
          <span className="text-sm font-bold tabular-nums" style={{ color: 'var(--theme-text)' }}>{fmtGBP(ts.payable_amount)}</span>
        </div>
      </button>
      {open && (
        <div className="border-t p-3 space-y-2" style={{ borderColor: 'var(--theme-border)' }}>
          {(ts.line_items || []).length === 0 ? (
            <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>No shifts in this week.</p>
          ) : (
            <table className="w-full text-[11px]">
              <thead>
                <tr style={{ color: 'var(--theme-text-muted)' }}>
                  <th className="text-left font-semibold py-1">Date</th>
                  <th className="text-left font-semibold py-1">Scheduled</th>
                  <th className="text-left font-semibold py-1">Actual</th>
                  <th className="text-right font-semibold py-1">Hours</th>
                  <th className="text-right font-semibold py-1">Late</th>
                </tr>
              </thead>
              <tbody>
                {ts.line_items.map((li) => (
                  <tr key={li.shift_id} className="border-t" style={{ borderColor: 'var(--theme-border)' }}>
                    <td className="py-1.5">{li.date}</td>
                    <td className="py-1.5 tabular-nums">{li.scheduled_start}–{li.scheduled_end}</td>
                    <td className="py-1.5 tabular-nums">
                      {li.missing_punch
                        ? <span className="text-rose-500 inline-flex items-center gap-1"><AlertTriangle size={10} /> missing</span>
                        : `${fmtTime(li.actual_start)}–${fmtTime(li.actual_end)}`}
                    </td>
                    <td className="py-1.5 text-right tabular-nums">{li.actual_hours}h</td>
                    <td className="py-1.5 text-right tabular-nums" style={{ color: li.late_minutes > 0 ? '#EF4444' : 'var(--theme-text-muted)' }}>
                      {li.late_minutes > 0 ? `${li.late_minutes}m` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {ts.dispute_reason && (
            <div className="rounded-md p-2 text-[11px]" style={{ background: 'rgba(239,68,68,0.08)', color: '#EF4444' }}>
              <strong>Dispute:</strong> {ts.dispute_reason}
            </div>
          )}
          {ts.approval_status !== 'approved' && (
            <div className="flex gap-2 pt-1">
              <button type="button" onClick={() => onApprove(ts)}
                className="h-8 rounded-full px-3 text-[11px] font-bold inline-flex items-center gap-1"
                style={{ background: '#10B981', color: '#001219' }} data-testid={`timesheet-approve-${ts.id}`}>
                <Check size={11} /> Approve
              </button>
              <button type="button" onClick={() => onDispute(ts)}
                className="h-8 rounded-full px-3 text-[11px] font-bold inline-flex items-center gap-1 border"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid={`timesheet-dispute-${ts.id}`}>
                <AlertTriangle size={11} /> Flag
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function TimesheetsPanel({ headers }) {
  const [weekStart, setWeekStart] = useState(startOfWeek);
  const [data, setData] = useState(null);
  const [filter, setFilter] = useState('all');

  const load = useCallback(async () => {
    setData(null);
    try {
      const params = { week_start: weekStart };
      const { data: d } = await axios.get(`${API}/staffing/timesheets`, { headers, params });
      setData(d);
    } catch { setData({ timesheets: [] }); }
  }, [headers, weekStart]);

  useEffect(() => { load(); }, [load]);

  const approve = async (ts) => {
    try { await axios.post(`${API}/staffing/timesheets/${ts.id}/approve`, {}, { headers }); load(); }
    catch (e) { window.alert(e.response?.data?.detail || 'Approve failed'); }
  };
  const dispute = async (ts) => {
    const reason = window.prompt(`Why is ${ts.staff_name}'s timesheet wrong?`);
    if (!reason) return;
    try { await axios.post(`${API}/staffing/timesheets/${ts.id}/dispute`, { reason }, { headers }); load(); }
    catch (e) { window.alert(e.response?.data?.detail || 'Dispute failed'); }
  };

  const rows = (data?.timesheets || []).filter((t) => filter === 'all' || t.approval_status === filter);

  return (
    <div className="rounded-xl border p-4 space-y-3" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="timesheets-panel">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <p className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: 'var(--color-brand-cyan)' }}>Weekly timesheets</p>
          <p className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>Week of {weekStart}</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <input type="date" value={weekStart} onChange={(e) => setWeekStart(e.target.value)}
            className="h-8 rounded-md bg-transparent border px-2 text-xs"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="timesheets-week" />
          <select value={filter} onChange={(e) => setFilter(e.target.value)}
            className="h-8 rounded-md bg-transparent border px-2 text-xs"
            style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="timesheets-filter">
            <option value="all">All</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="disputed">Disputed</option>
          </select>
        </div>
      </div>
      {!data && <div className="py-3 text-xs inline-flex items-center gap-2" style={{ color: 'var(--theme-text-muted)' }}><Loader2 size={14} className="animate-spin" /> Loading…</div>}
      {data && rows.length === 0 && (
        <p className="text-xs py-2" style={{ color: 'var(--theme-text-muted)' }}>No timesheets match this filter.</p>
      )}
      <div className="space-y-2">
        {rows.map((t) => <TimesheetRow key={t.id} ts={t} onApprove={approve} onDispute={dispute} />)}
      </div>
    </div>
  );
}

function KiosksPanel({ headers }) {
  const [list, setList] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ name: '', pin: '' });
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/staffing/kiosks`, { headers });
      setList(data.kiosks || []);
    } catch { /* noop */ }
    setLoading(false);
  }, [headers]);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    if (!form.name.trim() || !form.pin.trim()) return;
    try {
      if (editing?.id) {
        await axios.patch(`${API}/staffing/kiosks/${editing.id}`, form, { headers });
      } else {
        await axios.post(`${API}/staffing/kiosks`, form, { headers });
      }
      setEditing(null); setForm({ name: '', pin: '' });
      load();
    } catch (e) { window.alert(e.response?.data?.detail || 'Save failed'); }
  };

  const remove = async (k) => {
    if (!window.confirm(`Delete kiosk "${k.name}"?`)) return;
    try { await axios.delete(`${API}/staffing/kiosks/${k.id}`, { headers }); load(); }
    catch (e) { window.alert(e.response?.data?.detail || 'Delete failed'); }
  };

  const startNew = () => { setEditing({}); setForm({ name: '', pin: '' }); };
  const startEdit = (k) => { setEditing(k); setForm({ name: k.name, pin: '' }); };
  const kioskUrl = (k) => `${window.location.origin}/staffing/kiosk?id=${k.id}`;

  return (
    <div className="rounded-xl border p-4 space-y-3" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="kiosks-panel">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <p className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: 'var(--color-brand-cyan)' }}>Front-desk kiosks</p>
          <p className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>Shared punch devices</p>
        </div>
        <button type="button" onClick={startNew}
          className="h-8 rounded-full px-3 text-xs font-bold inline-flex items-center gap-1.5"
          style={{ background: 'var(--color-brand-cyan)', color: '#001219' }} data-testid="kiosks-new">
          <Plus size={12} /> New kiosk
        </button>
      </div>
      {loading && <div className="text-xs inline-flex items-center gap-2" style={{ color: 'var(--theme-text-muted)' }}><Loader2 size={14} className="animate-spin" /> Loading…</div>}
      {!loading && list.length === 0 && !editing && (
        <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>No kiosks yet — create one and tape the URL onto the front-desk iPad.</p>
      )}
      {editing && (
        <div className="rounded-lg border p-3 space-y-2" style={{ borderColor: 'var(--color-brand-cyan)' }} data-testid="kiosk-editor">
          <div className="grid grid-cols-2 gap-2">
            <input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="e.g. Front Desk iPad"
              className="h-9 rounded-md bg-transparent border px-2 text-xs"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="kiosk-name" />
            <input value={form.pin} onChange={(e) => setForm((f) => ({ ...f, pin: e.target.value }))}
              placeholder={editing.id ? 'New PIN (or leave blank)' : '4-6 digit PIN'}
              maxLength={6}
              className="h-9 rounded-md bg-transparent border px-2 text-xs tabular-nums"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="kiosk-pin" />
          </div>
          <div className="flex gap-2">
            <button type="button" onClick={save}
              className="h-8 rounded-full px-3 text-xs font-bold inline-flex items-center gap-1"
              style={{ background: 'var(--color-brand-cyan)', color: '#001219' }} data-testid="kiosk-save">
              <Check size={11} /> Save
            </button>
            <button type="button" onClick={() => { setEditing(null); setForm({ name: '', pin: '' }); }}
              className="h-8 rounded-full px-3 text-xs font-bold border inline-flex items-center gap-1"
              style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>
              <X size={11} /> Cancel
            </button>
          </div>
        </div>
      )}
      <ul className="space-y-2">
        {list.map((k) => (
          <li key={k.id} className="flex items-center justify-between gap-2 rounded-lg border p-2" style={{ borderColor: 'var(--theme-border)' }} data-testid={`kiosk-${k.id}`}>
            <div className="flex items-center gap-2 min-w-0">
              <Smartphone size={14} style={{ color: 'var(--color-brand-cyan)' }} />
              <div className="min-w-0">
                <p className="text-sm font-bold truncate" style={{ color: 'var(--theme-text)' }}>{k.name}</p>
                <p className="text-[10px] truncate" style={{ color: 'var(--theme-text-muted)' }}>
                  {kioskUrl(k)}
                </p>
              </div>
            </div>
            <div className="flex gap-1">
              <button type="button" onClick={() => navigator.clipboard?.writeText(kioskUrl(k))}
                className="h-7 px-2 rounded-full border text-[10px] font-bold"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid={`kiosk-copy-${k.id}`}>
                Copy URL
              </button>
              <button type="button" onClick={() => startEdit(k)} className="h-7 w-7 rounded-full border inline-flex items-center justify-center"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid={`kiosk-edit-${k.id}`}>
                <Pencil size={11} />
              </button>
              <button type="button" onClick={() => remove(k)} className="h-7 w-7 rounded-full border inline-flex items-center justify-center"
                style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid={`kiosk-delete-${k.id}`}>
                <Trash2 size={11} />
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function TimeClockTab({ headers }) {
  return (
    <div className="space-y-4" data-testid="time-clock-tab">
      <div className="flex items-center gap-2">
        <Activity size={14} style={{ color: 'var(--color-brand-cyan)' }} />
        <p className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: 'var(--color-brand-cyan)' }}>Phase S2 · Time Clock & Attendance</p>
      </div>
      <ClockBoard headers={headers} />
      <div className="flex items-center gap-1.5 text-xs pt-1" style={{ color: 'var(--theme-text-muted)' }}>
        <ClipboardCheck size={12} /> Approve hours below before exporting payroll.
      </div>
      <TimesheetsPanel headers={headers} />
      <KiosksPanel headers={headers} />
    </div>
  );
}
