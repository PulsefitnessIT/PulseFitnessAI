/**
 * StaffPortal — self-serve portal for ACTIVATED employees.
 * Route: /staff-portal (scoped staff JWT in sessionStorage 'staff_jwt').
 * Tabs: My Rota · Timesheets · Holidays · Documents · System Access.
 * Reuses the existing staffing collections via /api/new-starter/portal/*.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  Loader2, LogOut, Calendar, Clock, Plane, FileText, ShieldCheck, Download,
  CheckCircle2, AlertCircle, Plus, Trash2, Users,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const CORE = '#19CDFF';

function mondayOf(d = new Date()) {
  const x = new Date(d); x.setHours(0, 0, 0, 0);
  x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
  return x.toISOString().slice(0, 10);
}
const fmtDate = (s) => (s ? new Date(s + (s.length === 10 ? 'T00:00:00' : '')).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }) : '—');

async function downloadPdf(url, headers, name) {
  const r = await axios.get(url, { headers, responseType: 'blob' });
  const blobUrl = URL.createObjectURL(new Blob([r.data], { type: 'application/pdf' }));
  const a = document.createElement('a'); a.href = blobUrl; a.target = '_blank'; if (name) a.download = name; a.click();
}

const TABS = [
  ['rota', 'My Rota', Calendar],
  ['timesheets', 'Timesheets', Clock],
  ['holidays', 'Holidays', Plane],
  ['documents', 'Documents', FileText],
  ['access', 'System Access', ShieldCheck],
];

export default function StaffPortal() {
  const [jwt] = useState(() => sessionStorage.getItem('staff_jwt') || '');
  const [me, setMe] = useState(null);
  const [tab, setTab] = useState('rota');
  const H = jwt ? { Authorization: `Bearer ${jwt}` } : {};

  useEffect(() => {
    if (!jwt) { window.location.href = '/staff-login'; return; }
    axios.get(`${API}/new-starter/me`, { headers: H })
      .then((r) => setMe(r.data))
      .catch(() => { sessionStorage.removeItem('staff_jwt'); window.location.href = '/staff-login'; });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jwt]);

  const logout = () => { sessionStorage.removeItem('staff_jwt'); window.location.href = '/staff-login'; };

  if (!jwt) return null;
  if (!me) return <Shell><div className="flex justify-center mt-24"><Loader2 className="animate-spin text-cyan-500" size={32} /></div></Shell>;

  return (
    <Shell>
      <div className="max-w-5xl mx-auto py-8 px-4" data-testid="staff-portal">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Staff Portal</h1>
            <p className="text-slate-500 text-sm">Hello {me.person?.full_name} — {me.employment?.job_title || me.employment?.position || 'welcome aboard'}.</p>
          </div>
          <div className="flex items-center gap-2">
            {me.activated && <span className="px-3 py-1 rounded-full bg-emerald-100 text-emerald-700 text-sm font-semibold">Active employee ✓</span>}
            <button onClick={logout} data-testid="staff-portal-logout"
              className="inline-flex items-center gap-1.5 text-sm font-semibold px-3 py-1.5 rounded-lg border border-slate-300 text-slate-600 hover:border-slate-400">
              <LogOut size={14} /> Log out</button>
          </div>
        </div>

        <div className="mt-6 flex gap-1.5 flex-wrap border-b border-slate-200 pb-px">
          {TABS.map(([id, label, Icon]) => (
            <button key={id} onClick={() => setTab(id)} data-testid={`staff-tab-${id}`}
              className={`inline-flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-t-lg -mb-px border-b-2 transition-colors ${tab === id ? 'border-cyan-400 text-slate-900' : 'border-transparent text-slate-500 hover:text-slate-700'}`}>
              <Icon size={15} /> {label}
            </button>
          ))}
        </div>

        <div className="mt-6">
          {tab === 'rota' && <RotaTab H={H} />}
          {tab === 'timesheets' && <TimesheetsTab H={H} />}
          {tab === 'holidays' && <HolidaysTab H={H} />}
          {tab === 'documents' && <DocumentsTab H={H} />}
          {tab === 'access' && <AccessTab H={H} />}
        </div>
      </div>
    </Shell>
  );
}

function Card({ children, testId }) {
  return <div className="rounded-2xl bg-white border border-slate-200 shadow-sm p-5" data-testid={testId}>{children}</div>;
}
function Empty({ icon: Icon, title, hint }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center">
      <Icon size={22} className="mx-auto mb-2 text-slate-400" />
      <div className="text-sm font-semibold text-slate-700">{title}</div>
      {hint && <div className="text-xs text-slate-400 mt-1">{hint}</div>}
    </div>
  );
}

/* ─────────────── Rota ─────────────── */
function RotaTab({ H }) {
  const [shifts, setShifts] = useState(null);
  useEffect(() => { axios.get(`${API}/new-starter/portal/rota?days=28`, { headers: H }).then((r) => setShifts(r.data.shifts)).catch(() => setShifts([])); }, [H]);
  if (!shifts) return <Loader2 className="animate-spin text-cyan-500" />;
  if (shifts.length === 0) return <Empty icon={Calendar} title="No upcoming shifts" hint="Your manager hasn't scheduled you in the next 4 weeks." />;
  return (
    <Card testId="staff-rota">
      <h2 className="font-bold text-slate-900 mb-3">Your upcoming shifts</h2>
      <div className="space-y-2">
        {shifts.map((s) => (
          <div key={s.id} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 px-4 py-3" data-testid={`staff-shift-${s.id}`}>
            <div>
              <div className="text-sm font-semibold text-slate-800">{fmtDate(s.date)}</div>
              <div className="text-xs text-slate-500 capitalize">{(s.role || 'shift').replace(/_/g, ' ')}{s.site_id ? '' : ''}</div>
            </div>
            <div className="text-sm font-semibold text-slate-700">{s.start_time}–{s.end_time}</div>
          </div>
        ))}
      </div>
    </Card>
  );
}

/* ─────────────── Timesheets ─────────────── */
function TimesheetsTab({ H }) {
  const [week, setWeek] = useState(mondayOf());
  const [ts, setTs] = useState(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState(false);

  const load = useCallback(() => {
    setTs(null); setOk(false);
    axios.get(`${API}/new-starter/portal/timesheet?week_start=${week}`, { headers: H })
      .then((r) => setTs(r.data)).catch(() => setTs({ line_items: [] }));
  }, [week, H]);
  useEffect(() => { load(); }, [load]);

  const shift = (delta) => { const d = new Date(week + 'T00:00:00'); d.setDate(d.getDate() + delta * 7); setWeek(d.toISOString().slice(0, 10)); };
  const submitEdit = async () => {
    setBusy(true);
    try { await axios.post(`${API}/new-starter/portal/timesheet/edit`, { week_start: week, note }, { headers: H }); setOk(true); setNote(''); load(); }
    finally { setBusy(false); }
  };

  return (
    <Card testId="staff-timesheets">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-bold text-slate-900">Timesheet</h2>
        <div className="flex items-center gap-2">
          <button onClick={() => shift(-1)} className="px-2 py-1 rounded border border-slate-300 text-sm" data-testid="ts-prev">‹</button>
          <span className="text-sm font-semibold text-slate-700" data-testid="ts-week">Week of {fmtDate(week)}</span>
          <button onClick={() => shift(1)} className="px-2 py-1 rounded border border-slate-300 text-sm" data-testid="ts-next">›</button>
        </div>
      </div>
      {!ts ? <Loader2 className="animate-spin text-cyan-500" /> : (
        <>
          <div className="grid grid-cols-3 gap-2 mb-3">
            <Stat label="Scheduled" value={`${ts.scheduled_hours ?? 0}h`} />
            <Stat label="Actual" value={`${ts.actual_hours ?? 0}h`} />
            <Stat label="Status" value={(ts.approval_status || 'pending')} />
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs text-slate-400">
                <th className="py-1.5">Date</th><th>Scheduled</th><th>Actual</th><th>Late</th></tr></thead>
              <tbody data-testid="ts-lines">
                {(ts.line_items || []).length === 0 && <tr><td colSpan={4} className="py-4 text-slate-400 text-center">No shifts this week.</td></tr>}
                {(ts.line_items || []).map((li) => (
                  <tr key={li.shift_id} className="border-t border-slate-100">
                    <td className="py-2 text-slate-700">{fmtDate(li.date)}</td>
                    <td className="text-slate-500">{li.scheduled_start}–{li.scheduled_end} ({li.scheduled_hours}h)</td>
                    <td className={li.missing_punch ? 'text-amber-600' : 'text-slate-700'}>{li.missing_punch ? 'Missing punch' : `${li.actual_hours}h`}</td>
                    <td className="text-slate-500">{li.late_minutes ? `${li.late_minutes}m` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 border-t border-slate-200 pt-3">
            <div className="text-xs font-semibold text-slate-500 mb-1">Something wrong? Request a correction</div>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} data-testid="ts-edit-note" rows={2}
              placeholder="Describe what needs correcting (e.g. 'I clocked out at 18:00 not 17:30 on Tuesday')."
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            {ok && <div className="text-xs text-emerald-600 mt-1" data-testid="ts-edit-ok">Sent to your manager for review ✓</div>}
            <button onClick={submitEdit} disabled={busy || !note.trim()} data-testid="ts-edit-submit"
              className="mt-2 rounded-lg px-4 py-2 text-sm font-semibold text-slate-900 disabled:opacity-40" style={{ background: CORE }}>
              {busy ? 'Sending…' : 'Send correction request'}</button>
          </div>
        </>
      )}
    </Card>
  );
}
function Stat({ label, value }) {
  return <div className="rounded-lg bg-slate-50 border border-slate-200 px-3 py-2"><div className="text-[11px] text-slate-400 uppercase tracking-wide">{label}</div><div className="text-sm font-bold text-slate-800 capitalize">{value}</div></div>;
}

/* ─────────────── Holidays ─────────────── */
function HolidaysTab({ H }) {
  const [data, setData] = useState(null);
  const [form, setForm] = useState({ start_date: '', end_date: '', note: '' });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const load = useCallback(() => { axios.get(`${API}/new-starter/portal/holidays`, { headers: H }).then((r) => setData(r.data)).catch(() => setData({ mine: [], team: [], allowance: {} })); }, [H]);
  useEffect(() => { load(); }, [load]);

  const submit = async () => {
    setBusy(true); setErr('');
    try { await axios.post(`${API}/new-starter/portal/holidays`, form, { headers: H }); setForm({ start_date: '', end_date: '', note: '' }); load(); }
    catch (e) { setErr(e?.response?.data?.detail || 'Could not submit request.'); }
    finally { setBusy(false); }
  };
  const cancel = async (id) => { await axios.delete(`${API}/new-starter/portal/holidays/${id}`, { headers: H }); load(); };

  if (!data) return <Loader2 className="animate-spin text-cyan-500" />;
  const a = data.allowance || {};
  const tone = { approved: 'bg-emerald-50 text-emerald-700', pending: 'bg-amber-50 text-amber-700', rejected: 'bg-red-50 text-red-600', cancelled: 'bg-slate-100 text-slate-500' };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="lg:col-span-2 space-y-4">
        <Card testId="staff-holiday-request">
          <h2 className="font-bold text-slate-900 mb-3">Request holiday</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="block"><span className="text-xs text-slate-500">From</span>
              <input type="date" value={form.start_date} onChange={(e) => setForm((p) => ({ ...p, start_date: e.target.value }))} data-testid="holiday-start" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" /></label>
            <label className="block"><span className="text-xs text-slate-500">To</span>
              <input type="date" value={form.end_date} onChange={(e) => setForm((p) => ({ ...p, end_date: e.target.value }))} data-testid="holiday-end" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" /></label>
          </div>
          <input value={form.note} onChange={(e) => setForm((p) => ({ ...p, note: e.target.value }))} data-testid="holiday-note" placeholder="Note (optional)" className="mt-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          {err && <div className="text-red-500 text-sm mt-2" data-testid="holiday-error">{err}</div>}
          <button onClick={submit} disabled={busy || !form.start_date || !form.end_date} data-testid="holiday-submit"
            className="mt-3 inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold text-slate-900 disabled:opacity-40" style={{ background: CORE }}>
            <Plus size={15} /> {busy ? 'Submitting…' : 'Submit request'}</button>
        </Card>

        <Card testId="staff-holiday-mine">
          <h2 className="font-bold text-slate-900 mb-3">Your requests</h2>
          {(data.mine || []).length === 0 ? <div className="text-sm text-slate-400">No holiday requests yet.</div> : (
            <div className="space-y-2">
              {data.mine.map((r) => (
                <div key={r.id} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 px-4 py-2.5" data-testid={`holiday-row-${r.id}`}>
                  <div className="text-sm text-slate-700">{fmtDate(r.start_date)} → {fmtDate(r.end_date)}<span className="ml-2 text-xs capitalize text-slate-400">{r.leave_type}</span></div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full capitalize ${tone[r.status] || tone.pending}`}>{r.status}</span>
                    {r.status === 'pending' && <button onClick={() => cancel(r.id)} data-testid={`holiday-cancel-${r.id}`} className="text-slate-400 hover:text-red-500"><Trash2 size={14} /></button>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="space-y-4">
        <Card testId="staff-holiday-allowance">
          <div className="text-xs text-slate-400 uppercase tracking-wide mb-1">Holiday allowance</div>
          <div className="text-3xl font-bold text-slate-900">{a.remaining ?? '—'}<span className="text-base font-medium text-slate-400"> / {a.total ?? '—'} days</span></div>
          <div className="text-xs text-slate-500 mt-1">{a.used ?? 0} days taken/approved this year</div>
        </Card>
        <Card testId="staff-holiday-team">
          <div className="flex items-center gap-2 mb-2"><Users size={15} className="text-cyan-600" /><h2 className="font-bold text-slate-900 text-sm">{data.department ? `${data.department} team` : 'Team'} — booked holidays</h2></div>
          {(data.team || []).length === 0 ? <div className="text-xs text-slate-400">{data.department ? 'No approved holidays in your department.' : 'Department not set — ask HR.'}</div> : (
            <div className="space-y-1.5">
              {data.team.map((t, i) => (
                <div key={i} className="text-sm text-slate-600 flex items-center justify-between gap-2" data-testid={`team-holiday-${i}`}>
                  <span className="font-medium text-slate-700">{t.full_name}</span>
                  <span className="text-xs text-slate-400">{fmtDate(t.start_date)}–{fmtDate(t.end_date)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

/* ─────────────── Documents ─────────────── */
function DocumentsTab({ H }) {
  const [data, setData] = useState(null);
  useEffect(() => { axios.get(`${API}/new-starter/portal/documents`, { headers: H }).then((r) => setData(r.data)).catch(() => setData({ documents: [] })); }, [H]);
  if (!data) return <Loader2 className="animate-spin text-cyan-500" />;
  const rows = [];
  if (data.offer_available) rows.push({ id: 'offer', label: 'Offer letter (PDF)', url: `${API}/new-starter/offer.pdf`, name: 'offer-letter.pdf' });
  if (data.contract_available) rows.push({ id: 'contract', label: 'Employment contract (PDF)', url: `${API}/new-starter/contract.pdf`, name: 'employment-contract.pdf' });
  (data.documents || []).forEach((d) => rows.push({ id: d.id, label: `${d.original_filename} (${(d.document_type || 'document').replace(/_/g, ' ')})`, url: `${API}/staff-onboarding/files/${d.id}/download`, name: d.original_filename }));
  if (rows.length === 0) return <Empty icon={FileText} title="No documents yet" hint="Your signed contract and uploaded documents will appear here." />;
  return (
    <Card testId="staff-documents">
      <h2 className="font-bold text-slate-900 mb-3">Your documents</h2>
      <div className="space-y-2">
        {rows.map((r) => (
          <div key={r.id} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 px-4 py-3" data-testid={`staff-doc-${r.id}`}>
            <div className="flex items-center gap-2 text-sm text-slate-700"><FileText size={15} className="text-cyan-600" /> {r.label}</div>
            <button onClick={() => downloadPdf(r.url, H, r.name)} data-testid={`staff-doc-dl-${r.id}`} className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border border-slate-300 text-slate-600 hover:border-cyan-400"><Download size={13} /> Download</button>
          </div>
        ))}
      </div>
    </Card>
  );
}

/* ─────────────── System Access ─────────────── */
function AccessTab({ H }) {
  const [data, setData] = useState(null);
  useEffect(() => { axios.get(`${API}/new-starter/portal/access`, { headers: H }).then((r) => setData(r.data)).catch(() => setData({ modules: [] })); }, [H]);
  if (!data) return <Loader2 className="animate-spin text-cyan-500" />;
  const STATUS = { not_started: ['Awaiting line manager', 'bg-slate-100 text-slate-500'], awaiting_manager: ['Awaiting line-manager approval', 'bg-amber-50 text-amber-700'], granted: ['Access granted', 'bg-emerald-50 text-emerald-700'] };
  const [label, cls] = STATUS[data.status] || STATUS.not_started;
  return (
    <Card testId="staff-access">
      <h2 className="font-bold text-slate-900 mb-1">System & module access</h2>
      <p className="text-sm text-slate-500 mb-3">Your line manager decides which parts of PulseFitness.ai you can use.</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
        <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-3"><div className="text-[11px] text-slate-400 uppercase tracking-wide">Line manager</div><div className="text-sm font-semibold text-slate-800" data-testid="access-line-manager">{data.line_manager || 'Not assigned yet'}</div></div>
        <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-3"><div className="text-[11px] text-slate-400 uppercase tracking-wide">Provisioning status</div><span className={`inline-block mt-0.5 text-xs font-semibold px-2 py-0.5 rounded-full ${cls}`} data-testid="access-status">{label}</span></div>
      </div>
      <div className="text-xs font-semibold text-slate-500 mb-2">Modules</div>
      {(data.modules || []).length === 0 ? <div className="text-sm text-slate-400">No modules are available on your organisation's plan.</div> : (
        <div className="space-y-2" data-testid="access-modules">
          {data.modules.map((m) => (
            <div key={m.key} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 px-4 py-2.5" data-testid={`access-module-${m.key}`}>
              <span className="text-sm text-slate-700">{m.label}</span>
              {m.granted
                ? <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-600"><CheckCircle2 size={14} /> Granted</span>
                : <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-400"><AlertCircle size={14} /> Not granted</span>}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function Shell({ children }) {
  return (
    <div className="min-h-screen bg-slate-50">
      <div className="bg-white border-b border-slate-200">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center gap-2">
          <img src="/brand/pulse-logo-dark.svg" alt="Pulse Fitness" className="h-6" onError={(e) => { e.target.style.display = 'none'; }} />
          <span className="font-bold text-slate-800">Pulse Fitness</span>
        </div>
      </div>
      {children}
    </div>
  );
}
