/**
 * PayrollWorkspaceTab — configurable pay periods + exception-based Payroll
 * Workspace on the Attendance Spine. Submit → approve → lock (immutable
 * snapshot) → export with field mapping. Payroll resolves exceptions, not
 * spreadsheets.
 */
import { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import {
  Plus, Lock, Download, CheckCircle2, RotateCcw, AlertTriangle, X, Save,
  Loader2, FileSpreadsheet, ShieldCheck, ChevronRight, BarChart3, Table2,
} from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const token = () => localStorage.getItem('token');

const STATUS_STYLE = {
  draft: ['#94a3b8', 'Draft'], returned: ['#b45309', 'Returned'],
  submitted: ['#2563eb', 'Submitted'], approved: ['#16a34a', 'Approved'],
  locked: ['#7c3aed', 'Locked'],
};
const EX_LABEL = {
  missing_entry: 'Missing entry', unapproved_overtime: 'Unapproved OT',
  unpaid_leave: 'Unpaid leave', no_payroll_id: 'No payroll ID',
  above_contract: 'Above contract', below_contract: 'Below contract',
  missing_approval: 'Awaiting approval',
};

function Pill({ status }) {
  const [c, l] = STATUS_STYLE[status] || ['#94a3b8', status];
  return <span className="px-2 py-0.5 rounded-full text-[11px] font-bold" style={{ background: `${c}1a`, color: c }}>{l}</span>;
}

export default function PayrollWorkspaceTab({ headers }) {
  const [periods, setPeriods] = useState([]);
  const [sel, setSel] = useState(null);
  const [ws, setWs] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [adj, setAdj] = useState(null);
  const [ret, setRet] = useState(null);
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState('workspace');

  const loadPeriods = useCallback(async () => {
    const r = await axios.get(`${API}/payroll/periods`, { headers });
    setPeriods(r.data.periods || []);
    if (!sel && r.data.periods?.length) setSel(r.data.periods[0].id);
  }, [headers, sel]);
  useEffect(() => { loadPeriods(); }, [loadPeriods]);

  const loadWs = useCallback(async () => {
    if (!sel) { setWs(null); return; }
    setLoading(true);
    try { const r = await axios.get(`${API}/payroll/periods/${sel}/workspace`, { headers }); setWs(r.data); }
    catch { setWs(null); }
    setLoading(false);
  }, [sel, headers]);
  useEffect(() => { loadWs(); }, [loadWs]);

  const act = async (fn) => { setBusy(true); try { await fn(); await loadWs(); await loadPeriods(); } catch (e) { alert(e?.response?.data?.detail || 'Action failed'); } setBusy(false); };
  const approve = (staff_id) => act(() => axios.post(`${API}/payroll/periods/${sel}/approve`, { staff_id }, { headers }));
  const submitBehalf = (staff_id) => act(() => axios.post(`${API}/payroll/periods/${sel}/submit`, { staff_id, declaration: true }, { headers }));
  const lock = () => { if (window.confirm('Lock this period? A permanent payroll snapshot is created and it can no longer be edited without an adjustment.')) act(() => axios.post(`${API}/payroll/periods/${sel}/lock`, {}, { headers })); };
  const approveReady = () => act(async () => {
    const r = await axios.post(`${API}/payroll/periods/${sel}/approve-ready`, {}, { headers });
    alert(`Approved ${r.data.approved} clean employee${r.data.approved === 1 ? '' : 's'}. ${r.data.skipped_count} left as exception${r.data.skipped_count === 1 ? '' : 's'} to review.`);
  });

  const exportCsv = async () => {
    const res = await fetch(`${API}/payroll/periods/${sel}/export`, { headers: { Authorization: `Bearer ${token()}` } });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = `payroll-${sel}.csv`; a.click(); URL.revokeObjectURL(url);
  };

  const period = ws?.period;
  const locked = period?.status === 'locked';
  const s = ws?.summary || {};

  return (
    <div className="space-y-4" data-testid="payroll-workspace">
      <div className="flex items-center gap-1.5">
        {[['workspace', 'Workspace', Table2], ['reports', 'Reports', BarChart3]].map(([id, label, Icon]) => (
          <button key={id} onClick={() => setView(id)} data-testid={`payroll-view-${id}`}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border ${view === id ? 'border-cyan-500 text-cyan-700 bg-cyan-50' : 'border-slate-200 text-slate-500'}`}>
            <Icon size={13} /> {label}
          </button>
        ))}
      </div>

      {view === 'reports' && <PayrollReports headers={headers} />}

      {view === 'workspace' && (<>
      <div className="flex items-center gap-2 flex-wrap">
        <select value={sel || ''} onChange={(e) => setSel(e.target.value)} data-testid="payroll-period-select"
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm min-w-[240px]">
          <option value="">Select a pay period…</option>
          {periods.map((p) => <option key={p.id} value={p.id}>{p.name} {p.status === 'locked' ? '🔒' : ''}</option>)}
        </select>
        <button onClick={() => setShowNew(true)} data-testid="payroll-new-period"
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-cyan-600 text-white text-xs font-semibold"><Plus size={13} /> New period</button>
      </div>

      {!sel && <div className="text-sm text-slate-400">Create a pay period to open the workspace.</div>}
      {loading && <Loader2 className="animate-spin text-cyan-500" />}

      {ws && !loading && (
        <>
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="flex items-start justify-between flex-wrap gap-2">
              <div>
                <div className="flex items-center gap-2"><h3 className="font-bold text-slate-900">{period.name}</h3><Pill status={period.status} /></div>
                <div className="text-xs text-slate-500 mt-0.5">{period.start_date} → {period.end_date} · pay date {period.payroll_date || '—'}</div>
              </div>
              <div className="flex gap-2">
                <button onClick={exportCsv} data-testid="payroll-export"
                  className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-300 text-slate-700 text-xs font-semibold"><Download size={13} /> Export CSV</button>
                {!locked && s.awaiting_approval > 0 && <button onClick={approveReady} disabled={busy} data-testid="payroll-approve-ready"
                  className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-emerald-600 text-white text-xs font-semibold"><CheckCircle2 size={13} /> Approve all ready</button>}
                {!locked && <button onClick={lock} disabled={busy} data-testid="payroll-lock"
                  className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-violet-600 text-white text-xs font-semibold"><Lock size={13} /> Lock period</button>}
                {locked && <span className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-violet-700"><ShieldCheck size={14} /> Snapshot locked</span>}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-2" data-testid="payroll-summary">
            {[['Ready for payroll', s.ready, '#16a34a'], ['Awaiting approval', s.awaiting_approval, '#2563eb'], ['Missing timesheet', s.missing_timesheet, '#b45309'], ['Exceptions', s.exceptions, '#f59e0b']].map(([l, v, c]) => (
              <div key={l} className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="text-2xl font-bold" style={{ color: c }}>{v ?? 0}</div>
                <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{l}</div>
              </div>
            ))}
          </div>

          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
                <tr>
                  <th className="text-left px-3 py-2">Employee</th>
                  <th className="text-left px-3 py-2">Status</th>
                  <th className="text-right px-3 py-2">Regular</th>
                  <th className="text-right px-3 py-2">OT</th>
                  <th className="text-right px-3 py-2">Hol</th>
                  <th className="text-right px-3 py-2">Sick</th>
                  <th className="text-left px-3 py-2">Exceptions</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {ws.rows.map((r) => (
                  <tr key={r.staff_id} className={`border-t border-slate-100 ${r.exceptions.length ? 'bg-amber-50/30' : ''}`} data-testid={`payroll-row-${r.staff_id}`}>
                    <td className="px-3 py-2 font-semibold text-slate-800">{r.full_name}
                      {r.payroll_number ? <span className="ml-2 text-[11px] text-slate-400">#{r.payroll_number}</span> : <span className="ml-2 text-[11px] text-rose-400">no ID</span>}</td>
                    <td className="px-3 py-2"><Pill status={r.status} /></td>
                    <td className="px-3 py-2 text-right">{r.totals.regular}h</td>
                    <td className="px-3 py-2 text-right">{r.totals.overtime_approved || r.totals.overtime_raw || 0}h</td>
                    <td className="px-3 py-2 text-right">{r.totals.holiday}h</td>
                    <td className="px-3 py-2 text-right">{r.totals.sick}h</td>
                    <td className="px-3 py-2">
                      <div className="flex gap-1 flex-wrap">
                        {r.exceptions.map((e) => <span key={e} className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 font-semibold">{EX_LABEL[e] || e}</span>)}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right whitespace-nowrap">
                      {!locked && r.status === 'draft' && <button onClick={() => submitBehalf(r.staff_id)} data-testid={`payroll-submit-${r.staff_id}`} className="text-xs font-semibold text-slate-600 hover:underline mr-2">Submit</button>}
                      {!locked && (r.status === 'submitted' || r.status === 'returned') && <>
                        <button onClick={() => approve(r.staff_id)} data-testid={`payroll-approve-${r.staff_id}`} className="text-xs font-semibold text-emerald-600 hover:underline mr-2">Approve</button>
                        <button onClick={() => setRet({ staff_id: r.staff_id, name: r.full_name, reason: '' })} className="text-xs font-semibold text-amber-600 hover:underline">Return</button>
                      </>}
                      {locked && <button onClick={() => setAdj({ staff_id: r.staff_id, name: r.full_name, category: 'overtime', new_value: '', reason: '' })} data-testid={`payroll-adjust-${r.staff_id}`} className="text-xs font-semibold text-violet-600 hover:underline">Adjust</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      </>)}

      {showNew && <NewPeriodModal headers={headers} onClose={() => setShowNew(false)} onCreated={(id) => { setShowNew(false); setSel(id); loadPeriods(); }} />}
      {ret && <ReturnModal onClose={() => setRet(null)} onSubmit={async (reason) => { await act(() => axios.post(`${API}/payroll/periods/${sel}/return`, { staff_id: ret.staff_id, reason }, { headers })); setRet(null); }} name={ret.name} />}
      {adj && <AdjustModal periodId={sel} headers={headers} adj={adj} onClose={() => setAdj(null)} onSaved={() => { setAdj(null); }} />}
    </div>
  );
}

function NewPeriodModal({ headers, onClose, onCreated }) {
  const [mode, setMode] = useState('generate');
  const [freq, setFreq] = useState('month');
  const [anchor, setAnchor] = useState(() => new Date().toISOString().slice(0, 10));
  const [custom, setCustom] = useState({ name: '', start_date: '', end_date: '' });
  const [busy, setBusy] = useState(false);
  const create = async () => {
    setBusy(true);
    try {
      let res;
      if (mode === 'generate') res = await axios.post(`${API}/payroll/periods/generate`, { frequency: freq, anchor }, { headers });
      else res = await axios.post(`${API}/payroll/periods`, { ...custom, frequency: 'custom' }, { headers });
      onCreated(res.data.id);
    } catch (e) { alert(e?.response?.data?.detail || 'Failed'); setBusy(false); }
  };
  return createPortal(
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/40 p-4" data-testid="payroll-new-modal">
      <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-2xl">
        <div className="flex items-center justify-between mb-3"><h3 className="font-bold text-slate-900">New pay period</h3><button onClick={onClose}><X size={18} className="text-slate-400" /></button></div>
        <div className="flex gap-1.5 mb-3">
          {[['generate', 'Quick generate'], ['custom', 'Custom dates']].map(([k, l]) => (
            <button key={k} onClick={() => setMode(k)} className={`px-3 py-1.5 rounded-lg text-xs font-semibold border ${mode === k ? 'border-cyan-500 text-cyan-700 bg-cyan-50' : 'border-slate-200 text-slate-500'}`}>{l}</button>
          ))}
        </div>
        {mode === 'generate' ? (
          <div className="space-y-2">
            <label className="block text-xs font-semibold text-slate-600">Frequency
              <select value={freq} onChange={(e) => setFreq(e.target.value)} data-testid="payroll-gen-freq" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
                <option value="month">Calendar month</option><option value="4_week">4-week</option><option value="5_week">5-week</option>
              </select></label>
            <label className="block text-xs font-semibold text-slate-600">{freq === 'month' ? 'Any date in the month' : 'Start date'}
              <input type="date" value={anchor} onChange={(e) => setAnchor(e.target.value)} data-testid="payroll-gen-anchor" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" /></label>
          </div>
        ) : (
          <div className="space-y-2">
            <input placeholder="Period name" value={custom.name} onChange={(e) => setCustom({ ...custom, name: e.target.value })} className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <div className="grid grid-cols-2 gap-2">
              <input type="date" value={custom.start_date} onChange={(e) => setCustom({ ...custom, start_date: e.target.value })} className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
              <input type="date" value={custom.end_date} onChange={(e) => setCustom({ ...custom, end_date: e.target.value })} className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            </div>
          </div>
        )}
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose} className="px-3 py-2 rounded-lg text-sm font-semibold text-slate-500">Cancel</button>
          <button onClick={create} disabled={busy} data-testid="payroll-create-period" className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-cyan-600 text-white text-sm font-semibold">{busy ? <Loader2 size={14} className="animate-spin" /> : <FileSpreadsheet size={14} />} Create</button>
        </div>
      </div>
    </div>, document.body);
}

function ReturnModal({ onClose, onSubmit, name }) {
  const [reason, setReason] = useState('');
  return createPortal(
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/40 p-4" data-testid="payroll-return-modal">
      <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-2xl">
        <h3 className="font-bold text-slate-900 mb-2">Return to {name} for correction</h3>
        <textarea value={reason} onChange={(e) => setReason(e.target.value)} data-testid="payroll-return-reason" placeholder="What needs fixing?" rows={3} className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
        <div className="flex justify-end gap-2 mt-3">
          <button onClick={onClose} className="px-3 py-2 rounded-lg text-sm font-semibold text-slate-500">Cancel</button>
          <button onClick={() => reason.trim() && onSubmit(reason.trim())} data-testid="payroll-return-save" className="px-4 py-2 rounded-lg bg-amber-500 text-white text-sm font-semibold">Return</button>
        </div>
      </div>
    </div>, document.body);
}

function AdjustModal({ periodId, headers, adj, onClose, onSaved }) {
  const [f, setF] = useState(adj);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    if (!f.reason.trim() || f.new_value === '') return;
    setBusy(true);
    try { await axios.post(`${API}/payroll/periods/${periodId}/adjustment`, { staff_id: f.staff_id, category: f.category, old_value: null, new_value: Number(f.new_value), reason: f.reason }, { headers }); onSaved(); }
    catch (e) { alert(e?.response?.data?.detail || 'Failed'); setBusy(false); }
  };
  return createPortal(
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/40 p-4" data-testid="payroll-adjust-modal">
      <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-2xl">
        <h3 className="font-bold text-slate-900 mb-1">Payroll adjustment — {f.name}</h3>
        <p className="text-[11px] text-slate-500 mb-3">The locked snapshot stays intact; this is recorded as an authorised adjustment.</p>
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs font-semibold text-slate-600">Category
            <input value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" /></label>
          <label className="text-xs font-semibold text-slate-600">New value
            <input type="number" value={f.new_value} onChange={(e) => setF({ ...f, new_value: e.target.value })} data-testid="payroll-adjust-value" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" /></label>
        </div>
        <label className="block text-xs font-semibold text-slate-600 mt-2">Reason
          <input value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} data-testid="payroll-adjust-reason" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" /></label>
        <div className="flex justify-end gap-2 mt-3">
          <button onClick={onClose} className="px-3 py-2 rounded-lg text-sm font-semibold text-slate-500">Cancel</button>
          <button onClick={save} disabled={busy} data-testid="payroll-adjust-save" className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-violet-600 text-white text-sm font-semibold"><Save size={14} /> Record</button>
        </div>
      </div>
    </div>, document.body);
}

/* ─────────────── Payroll Reports (§43) ─────────────── */
function monthBounds() {
  const n = new Date();
  const first = new Date(n.getFullYear(), n.getMonth(), 1);
  const last = new Date(n.getFullYear(), n.getMonth() + 1, 0);
  const iso = (d) => d.toISOString().slice(0, 10);
  return [iso(first), iso(last)];
}

function PayrollReports({ headers }) {
  const [mb] = useState(monthBounds);
  const [from, setFrom] = useState(mb[0]);
  const [to, setTo] = useState(mb[1]);
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { const r = await axios.get(`${API}/payroll/reports?date_from=${from}&date_to=${to}`, { headers }); setD(r.data); }
    catch { setD(null); }
    setLoading(false);
  }, [from, to, headers]);
  useEffect(() => { load(); }, [load]);

  const t = d?.totals || {};
  const sub = d?.submissions || {};
  const tiles = [
    ['Hours worked', `${t.worked ?? 0}h`, '#0f172a'],
    ['Overtime', `${t.overtime ?? 0}h`, '#0891b2'],
    ['Holiday', `${t.holiday ?? 0}h`, '#2563eb'],
    ['Sick', `${t.sick ?? 0}h`, '#dc2626'],
    ['Attendance rate', `${t.attendance_rate ?? 0}%`, '#16a34a'],
    ['Adjustments', d?.adjustments ?? 0, '#7c3aed'],
  ];

  return (
    <div className="space-y-4" data-testid="payroll-reports">
      <div className="flex items-end gap-3 flex-wrap">
        <label className="text-xs font-semibold text-slate-600">From
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} data-testid="payroll-report-from" className="mt-1 block rounded-lg border border-slate-300 px-3 py-2 text-sm" /></label>
        <label className="text-xs font-semibold text-slate-600">To
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} data-testid="payroll-report-to" className="mt-1 block rounded-lg border border-slate-300 px-3 py-2 text-sm" /></label>
        {loading && <Loader2 className="animate-spin text-cyan-500 mb-2" />}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-6 gap-2" data-testid="payroll-report-tiles">
        {tiles.map(([l, v, c]) => (
          <div key={l} className="rounded-xl border border-slate-200 bg-white p-3">
            <div className="text-xl font-bold" style={{ color: c }}>{v}</div>
            <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{l}</div>
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h3 className="font-bold text-slate-900 mb-3">Hours by department</h3>
        <div style={{ width: '100%', height: 240 }}>
          <ResponsiveContainer>
            <BarChart data={d?.by_department || []} margin={{ top: 4, right: 8, left: -12, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
              <XAxis dataKey="department" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="worked" name="Worked" fill="#0891b2" radius={[4, 4, 0, 0]} />
              <Bar dataKey="overtime" name="Overtime" fill="#f59e0b" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid md:grid-cols-3 gap-2" data-testid="payroll-report-submissions">
        {[['On-time submissions', sub.on_time, '#16a34a'], ['Late submissions', sub.late, '#b45309'], ['Missing submissions', sub.missing, '#dc2626']].map(([l, v, c]) => (
          <div key={l} className="rounded-xl border border-slate-200 bg-white p-3">
            <div className="text-lg font-bold" style={{ color: c }}>{v ?? 0}</div>
            <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{l}</div>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-3 py-2">Employee</th>
              <th className="text-left px-3 py-2">Dept</th>
              <th className="text-right px-3 py-2">Worked</th>
              <th className="text-right px-3 py-2">OT</th>
              <th className="text-right px-3 py-2">Holiday</th>
              <th className="text-right px-3 py-2">Sick</th>
              <th className="text-right px-3 py-2">Missing</th>
              <th className="text-right px-3 py-2">Attendance</th>
            </tr>
          </thead>
          <tbody>
            {(d?.by_employee || []).map((r) => (
              <tr key={r.staff_id} className="border-t border-slate-100" data-testid={`payroll-report-emp-${r.staff_id}`}>
                <td className="px-3 py-2 font-semibold text-slate-800">{r.full_name}</td>
                <td className="px-3 py-2 text-slate-500">{r.department}</td>
                <td className="px-3 py-2 text-right">{r.worked}h</td>
                <td className="px-3 py-2 text-right">{r.overtime}h</td>
                <td className="px-3 py-2 text-right">{r.holiday}h</td>
                <td className="px-3 py-2 text-right">{r.sick}h</td>
                <td className="px-3 py-2 text-right">{r.missing}</td>
                <td className="px-3 py-2 text-right font-semibold" style={{ color: r.attendance_rate >= 90 ? '#16a34a' : r.attendance_rate >= 70 ? '#b45309' : '#dc2626' }}>{r.attendance_rate}%</td>
              </tr>
            ))}
            {d && !d.by_employee?.length && <tr><td colSpan={8} className="px-3 py-6 text-center text-slate-400">No data in this range.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

