/**
 * StaffPortal — self-serve portal for ACTIVATED employees.
 * Route: /staff-portal (scoped staff JWT in sessionStorage 'staff_jwt').
 * Tabs: My Rota · Timesheets · Holidays · Documents · System Access.
 * Reuses the existing staffing collections via /api/new-starter/portal/*.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import {
  Loader2, LogOut, Calendar, Clock, Plane, FileText, ShieldCheck, Download,
  CheckCircle2, AlertCircle, Plus, Trash2, Users,
  Home, Play, Square, Coffee, Sun, Thermometer, ChevronLeft, ChevronRight,
  ClipboardCheck, PenLine, Truck, Camera, ShieldAlert, Check, X, MoreHorizontal,
  IdCard,
} from 'lucide-react';
import StaffNotificationBell from '@/components/staffing/StaffNotificationBell';
import Navbar from '../components/shared/Navbar';
import PillTabBar from '../components/shared/PillTabBar';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const CORE = '#19CDFF';

// Resolve a stored photo_url (relative "/api/..." proxy path or data: URI).
const photoSrc = (u) => (u ? (u.startsWith('/api') ? `${process.env.REACT_APP_BACKEND_URL}${u}` : u) : '');

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
  ['home', 'Home', Home],
  ['mytime', 'My Time', Clock],
  ['rota', 'My Rota', Calendar],
  ['timesheets', 'Timesheets', Clock],
  ['holidays', 'Holidays', Plane],
  ['vehicle', 'Vehicle', Truck],
  ['documents', 'Documents', FileText],
  ['access', 'System Access', ShieldCheck],
  ['details', 'My Details', IdCard],
];
const PRIMARY_TABS = ['home', 'mytime', 'vehicle', 'holidays'];

export default function StaffPortal() {
  const [jwt] = useState(() => sessionStorage.getItem('staff_jwt') || localStorage.getItem('token') || '');
  const [me, setMe] = useState(null);
  const [tab, setTab] = useState('home');
  const [moreOpen, setMoreOpen] = useState(false);
  const H = jwt ? { Authorization: `Bearer ${jwt}` } : {};
  const usingPlatformToken = !sessionStorage.getItem('staff_jwt') && !!localStorage.getItem('token');

  useEffect(() => {
    if (!jwt) { window.location.href = '/staff-login'; return; }
    axios.get(`${API}/new-starter/me`, { headers: H })
      .then((r) => setMe(r.data))
      .catch(async () => {
        // Activated staff opened from the launcher (platform token) may have a
        // staff_members record but no onboarding case (/new-starter/me 404s).
        // Fall back to a minimal profile so My Day / My Time still render.
        if (usingPlatformToken) {
          try {
            const r = await axios.get(`${API}/staffing/me/portal-access`, { headers: H });
            if (r.data?.has_staff_portal) {
              setMe({ activated: true, person: { full_name: r.data.full_name },
                portal_name: 'Pulse Fitness Staff Portal' });
              return;
            }
          } catch { /* fall through */ }
          window.location.href = '/launch'; return;
        }
        sessionStorage.removeItem('staff_jwt'); window.location.href = '/staff-login';
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jwt]);

  // Single-login staff arrive on a platform token — a full sign-out must clear
  // the platform session (else the app still thinks they're logged in and the
  // next sign-in is blocked). We clear the platform keys and return them to the
  // main pulsefitness.ai login (where their single login lives), NOT the
  // dedicated /staff-login. Dedicated /staff-login users just drop staff_jwt.
  const logout = () => {
    if (usingPlatformToken) {
      try { axios.post(`${API}/auth/logout`, {}).catch(() => {}); } catch { /* ignore */ }
      ['token', 'user_cache', 'crm_token', 'member_token', 'sites_cache',
       'active_site_cache', 'active_site_all', 'impersonation_active'].forEach((k) => {
        try { localStorage.removeItem(k); } catch { /* quota */ }
      });
      try { sessionStorage.removeItem('crm_active_session'); } catch { /* ignore */ }
      try { window.dispatchEvent(new CustomEvent('gymaxis:auth-changed')); } catch { /* ignore */ }
      window.location.href = '/login?signedout=1';
      return;
    }
    sessionStorage.removeItem('staff_jwt'); window.location.href = '/staff-login';
  };
  if (!jwt) return null;

  const dateStr = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

  if (!me) {
    return (
      <div className="min-h-screen overflow-x-hidden pulse-font" style={{ background: 'var(--theme-bg)' }} data-portal="staff">
        {usingPlatformToken ? <Navbar /> : <FallbackBar onLogout={logout} />}
        <div className="pt-24 flex justify-center"><Loader2 className="animate-spin text-cyan-500" size={32} /></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen overflow-x-hidden pulse-font" style={{ background: 'var(--theme-bg)' }} data-portal="staff" data-testid="staff-portal-root">
      {usingPlatformToken ? <Navbar /> : <FallbackBar onLogout={logout} />}

      <div className="pt-24 pb-28 sm:pb-12 module-fade-in">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8" data-testid="staff-portal">
          {/* Header — same layout as the other modules */}
          <div className="mb-6">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <h1 className="text-2xl sm:text-4xl tracking-tight font-semibold mb-1 pulse-font-heading leading-tight break-words" style={{ color: 'var(--theme-text)' }}>
                  Staff Portal
                </h1>
                <p className="pulse-font-body" style={{ color: 'var(--theme-text-muted)' }}>Welcome back, {me.person?.full_name}</p>
              </div>
              <div className="flex items-center gap-3 shrink-0 mt-1.5">
                {me.activated && <span className="px-3 py-1 rounded-full bg-emerald-100 text-emerald-700 text-xs font-semibold whitespace-nowrap">Active employee ✓</span>}
                <StaffNotificationBell
                  endpoint={`${API}/new-starter/portal/notifications`}
                  readEndpoint={`${API}/new-starter/portal/notifications/read`}
                  headers={H} onNavigate={setTab} />
                <div className="hidden sm:block text-sm pulse-font-body" style={{ color: 'var(--theme-text-muted)' }} data-testid="staff-today-date">{dateStr}</div>
              </div>
            </div>
          </div>

          {/* Desktop pill tabs — identical styling to the module consoles */}
          <PillTabBar className="mb-6 w-full hidden md:block" activeId={tab} testId="staff-dashboard-tabs" ariaLabel="Staff portal sections">
            {TABS.map(([id, label, Icon]) => {
              const isActive = tab === id;
              return (
                <button key={id} data-pill-id={id} onClick={() => setTab(id)} data-testid={`staff-tab-${id}`}
                  className="flex-shrink-0 inline-flex items-center gap-2 px-4 py-2.5 rounded-full text-sm font-semibold transition-colors whitespace-nowrap"
                  style={isActive
                    ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
                    : { color: 'var(--theme-text-muted)', background: 'transparent' }}>
                  <Icon size={14} /> {label}
                </button>
              );
            })}
          </PillTabBar>

          <div className="mt-2">
            {tab === 'home' && <MyDayTab H={H} onGoTo={setTab} />}
            {tab === 'mytime' && <MyTimeTab H={H} />}
            {tab === 'rota' && <RotaTab H={H} />}
            {tab === 'timesheets' && <TimesheetsTab H={H} />}
            {tab === 'holidays' && <HolidaysTab H={H} />}
            {tab === 'vehicle' && <VehicleTab H={H} jwt={jwt} />}
            {tab === 'documents' && <DocumentsTab H={H} />}
            {tab === 'access' && <AccessTab H={H} />}
            {tab === 'details' && <MyDetailsTab me={me} H={H} />}
          </div>
        </div>
      </div>

      <BottomNav tab={tab} setTab={setTab} onMore={() => setMoreOpen(true)} />
      {moreOpen && <MoreSheet tab={tab} jwt={jwt} setTab={(t) => { setTab(t); setMoreOpen(false); }} onClose={() => setMoreOpen(false)} />}
    </div>
  );
}

/* Fallback top bar for dedicated /staff-login sessions (no platform session, so
   the shared Navbar's Switch-area / avatar aren't available). Mirrors the
   platform's black header. */
function FallbackBar({ onLogout }) {
  return (
    <div style={{ backgroundColor: '#000000' }} className="border-b border-white/10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-20 flex items-center justify-between">
        <img
          src="https://customer-assets.emergentagent.com/job_maintenance-hub-357/artifacts/iscy9t7o_Pulse%20Fitness%20Primary%20Logo%20Badge%20RGB.jpg"
          alt="Pulse Fitness" className="h-10 rounded-md object-cover"
          style={{ objectPosition: 'center', aspectRatio: '3.8/1', clipPath: 'inset(12% 3% 12% 3% round 6px)' }}
          data-testid="staff-portal-logo" />
        <button onClick={onLogout} data-testid="staff-portal-logout"
          className="inline-flex items-center gap-1.5 text-sm font-semibold px-3 py-1.5 rounded-lg border border-white/20 text-white/90 hover:bg-white/10">
          <LogOut size={14} /> Log out</button>
      </div>
    </div>
  );
}

function BottomNav({ tab, setTab, onMore }) {
  const primary = TABS.filter(([id]) => PRIMARY_TABS.includes(id));
  const moreActive = !PRIMARY_TABS.includes(tab);
  return (
    <nav className="sm:hidden fixed bottom-0 inset-x-0 z-40 bg-white/95 backdrop-blur border-t border-slate-200 pb-[env(safe-area-inset-bottom)]"
      data-testid="staff-bottom-nav">
      <div className="grid grid-cols-5">
        {primary.map(([id, label, Icon]) => {
          const active = tab === id;
          return (
            <button key={id} onClick={() => setTab(id)} data-testid={`bottom-nav-${id}`}
              className={`flex flex-col items-center justify-center gap-0.5 py-2 text-[10px] font-semibold transition-colors ${active ? 'text-cyan-600' : 'text-slate-400'}`}>
              <Icon size={20} className="shrink-0" />
              <span className="truncate max-w-full">{label}</span>
            </button>
          );
        })}
        <button onClick={onMore} data-testid="bottom-nav-more"
          className={`flex flex-col items-center justify-center gap-0.5 py-2 text-[10px] font-semibold transition-colors ${moreActive ? 'text-cyan-600' : 'text-slate-400'}`}>
          <MoreHorizontal size={20} className="shrink-0" />
          <span>More</span>
        </button>
      </div>
    </nav>
  );
}

function MoreSheet({ tab, setTab, onClose, jwt }) {
  const rest = TABS.filter(([id]) => !PRIMARY_TABS.includes(id));
  const downloadHandbook = async () => {
    try {
      const r = await axios.get(`${API}/new-starter/portal/handbook.pdf`, { headers: { Authorization: `Bearer ${jwt}` }, responseType: 'blob' });
      const url = URL.createObjectURL(r.data); const a = document.createElement('a'); a.href = url; a.download = 'pulse-staff-portal-handbook.pdf'; a.click(); URL.revokeObjectURL(url);
    } catch { /* ignore */ }
  };
  return (
    <div className="sm:hidden fixed inset-0 z-50 flex items-end bg-black/40" onClick={onClose} data-testid="staff-more-sheet">
      <div className="w-full rounded-t-2xl bg-white p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-slate-200" />
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-bold text-slate-900">More</span>
          <button onClick={onClose} className="text-slate-400" data-testid="more-sheet-close"><X size={18} /></button>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {rest.map(([id, label, Icon]) => {
            const active = tab === id;
            return (
              <button key={id} onClick={() => setTab(id)} data-testid={`more-nav-${id}`}
                className={`flex items-center gap-2 rounded-xl border px-3 py-3 text-sm font-semibold transition-colors ${active ? 'border-cyan-300 bg-cyan-50 text-cyan-700' : 'border-slate-200 text-slate-600'}`}>
                <Icon size={18} className="shrink-0" /> {label}
              </button>
            );
          })}
        </div>
        <button onClick={downloadHandbook} data-testid="more-handbook"
          className="mt-3 w-full flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-3 py-3 text-sm font-semibold text-slate-600">
          <FileText size={16} /> Staff Portal Handbook (PDF)
        </button>
      </div>
    </div>
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

/* ─────────────── Home / My Day ─────────────── */
function StatusPill({ label, color }) {
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold"
      style={{ background: `${color || '#94a3b8'}1a`, color: color || '#94a3b8' }}>
      <span className="w-2 h-2 rounded-full" style={{ background: color || '#94a3b8' }} /> {label}
    </span>
  );
}

function BigAction({ icon: Icon, label, onClick, tone = 'primary', testId, disabled }) {
  const tones = {
    primary: { background: CORE, color: '#062a33' },
    dark: { background: '#0f172a', color: '#fff' },
    amber: { background: '#f59e0b', color: '#3a2600' },
    ghost: { background: '#fff', color: '#0f172a', border: '1px solid #e2e8f0' },
  };
  return (
    <button onClick={onClick} disabled={disabled} data-testid={testId}
      className="flex-1 min-w-[46%] sm:min-w-[30%] inline-flex flex-col items-center justify-center gap-1.5 rounded-2xl px-4 py-5 text-sm font-bold shadow-sm active:scale-[0.98] transition-transform disabled:opacity-50"
      style={tones[tone]}>
      <Icon size={22} /> {label}
    </button>
  );
}

function MyDayTab({ H, onGoTo }) {
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(false);
  const [entry, setEntry] = useState(null);    // daily-timesheet inline form
  const [absence, setAbsence] = useState(null); // report-absence inline form
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    try { const r = await axios.get(`${API}/new-starter/portal/my-day`, { headers: H }); setD(r.data); }
    catch (e) { setD({ error: e?.response?.data?.detail || 'Could not load your day.' }); }
  }, [H]);
  useEffect(() => { load(); }, [load]);

  const [rtw, setRtw] = useState([]);
  const loadRtw = useCallback(async () => {
    try { const r = await axios.get(`${API}/new-starter/portal/rtw-pending`, { headers: H }); setRtw(r.data?.pending || []); }
    catch { setRtw([]); }
  }, [H]);
  useEffect(() => { loadRtw(); }, [loadRtw]);

  const punch = async (kind) => {
    setBusy(true); setErr('');
    try { await axios.post(`${API}/new-starter/portal/day/punch`, { kind }, { headers: H }); await load(); }
    catch (e) { setErr(e?.response?.data?.detail || 'Could not record that.'); }
    setBusy(false);
  };
  const saveEntry = async () => {
    setBusy(true); setErr('');
    try {
      await axios.post(`${API}/new-starter/portal/day/timesheet`,
        { start: entry.start, finish: entry.finish, break_minutes: Number(entry.break_minutes || 0) }, { headers: H });
      setEntry(null); await load();
    } catch (e) { setErr(e?.response?.data?.detail || 'Could not save.'); }
    setBusy(false);
  };
  const saveAbsence = async () => {
    if (!absence.first_day) { setErr('Pick the first day.'); return; }
    setBusy(true); setErr('');
    try {
      await axios.post(`${API}/new-starter/portal/report-absence`,
        { absence_type: absence.absence_type, first_day: absence.first_day, expected_return: absence.expected_return || null, note: absence.note || null }, { headers: H });
      setAbsence(null); await load();
    } catch (e) { setErr(e?.response?.data?.detail || 'Could not report.'); }
    setBusy(false);
  };

  if (!d) return <Loader2 className="animate-spin text-cyan-500" />;
  if (d.error) return <Empty icon={AlertCircle} title="Nothing to show yet" hint={d.error} />;

  const rec = d.record || {};
  const method = d.time_entry_method;
  const isClock = method === 'live_clock' || method === 'clock';
  const state = d.clock_state;
  const hour = new Date().getHours();
  const greet = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
  const m = d.month || {};

  return (
    <div className="space-y-4" data-testid="staff-my-day">
      <div>
        <h2 className="text-2xl font-bold text-slate-900">{greet}, {d.first_name}</h2>
        <p className="text-slate-500 text-sm">{fmtDate(d.date)}</p>
      </div>

      {rtw.map((r) => (
        <RtwAckCard key={r.leave_id} rtw={r} H={H} onDone={loadRtw} />
      ))}

      <Card testId="my-day-today">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-3">
            <StatusPill label={d.status_label || rec.actual_status} color={d.status_color} />
            {isClock && state !== 'off' && <span className="text-xs font-semibold text-emerald-600">● {state === 'on_break' ? 'On break' : 'Clocked in'}</span>}
          </div>
          <div className="text-sm text-slate-500">
            {rec.start_time ? `${rec.start_time}–${rec.finish_time || '…'}` : (d.expected_hours_today ? `Expected ${d.expected_hours_today}h` : '')}
          </div>
        </div>

        {err && <div className="mt-3 text-sm text-rose-600" data-testid="my-day-error">{err}</div>}

        {/* Primary actions */}
        <div className="mt-4 flex flex-wrap gap-3">
          {isClock ? (
            <>
              {state === 'off' && <BigAction icon={Play} label="Start my day" tone="primary" testId="my-day-start" onClick={() => punch('clock_in')} disabled={busy} />}
              {state === 'on_shift' && <>
                <BigAction icon={Coffee} label="Start break" tone="ghost" testId="my-day-break-start" onClick={() => punch('break_start')} disabled={busy} />
                <BigAction icon={Square} label="Finish day" tone="dark" testId="my-day-finish" onClick={() => punch('clock_out')} disabled={busy} />
              </>}
              {state === 'on_break' && <BigAction icon={Play} label="End break" tone="primary" testId="my-day-break-end" onClick={() => punch('break_end')} disabled={busy} />}
            </>
          ) : (
            <BigAction icon={Clock} label="Enter today's hours" tone="primary" testId="my-day-enter-hours"
              onClick={() => setEntry({ start: rec.start_time || '09:00', finish: rec.finish_time || '17:00', break_minutes: rec.break_minutes || 30 })} disabled={busy} />
          )}
          <BigAction icon={Plane} label="Request holiday" tone="ghost" testId="my-day-request-holiday" onClick={() => onGoTo('holidays')} />
          <BigAction icon={Thermometer} label="Report absence" tone="amber" testId="my-day-report-absence"
            onClick={() => setAbsence({ absence_type: 'sick', first_day: d.date, expected_return: '', note: '' })} />
        </div>

        {/* Inline daily-timesheet form */}
        {entry && (
          <div className="mt-4 rounded-xl border border-slate-200 p-4" data-testid="my-day-entry-form">
            <div className="grid grid-cols-3 gap-2">
              <label className="text-xs font-semibold text-slate-600">Start
                <input type="time" value={entry.start} onChange={(e) => setEntry({ ...entry, start: e.target.value })} data-testid="my-day-entry-start" className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm" /></label>
              <label className="text-xs font-semibold text-slate-600">Finish
                <input type="time" value={entry.finish} onChange={(e) => setEntry({ ...entry, finish: e.target.value })} data-testid="my-day-entry-finish" className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm" /></label>
              <label className="text-xs font-semibold text-slate-600">Break (min)
                <input type="number" value={entry.break_minutes} onChange={(e) => setEntry({ ...entry, break_minutes: e.target.value })} data-testid="my-day-entry-break" className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm" /></label>
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <button onClick={() => setEntry(null)} className="px-3 py-2 rounded-lg text-sm font-semibold text-slate-500">Cancel</button>
              <button onClick={saveEntry} disabled={busy} data-testid="my-day-entry-save" className="px-4 py-2 rounded-lg text-sm font-bold text-white" style={{ background: CORE }}>Save hours</button>
            </div>
          </div>
        )}

        {/* Inline report-absence form */}
        {absence && (
          <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50/50 p-4" data-testid="my-day-absence-form">
            <div className="grid sm:grid-cols-2 gap-2">
              <label className="text-xs font-semibold text-slate-600">Type
                <select value={absence.absence_type} onChange={(e) => setAbsence({ ...absence, absence_type: e.target.value })} data-testid="my-day-absence-type" className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm">
                  <option value="sick">Sick</option><option value="family_leave">Family / emergency</option><option value="other">Other authorised</option>
                </select></label>
              <label className="text-xs font-semibold text-slate-600">First day
                <input type="date" value={absence.first_day} onChange={(e) => setAbsence({ ...absence, first_day: e.target.value })} data-testid="my-day-absence-first" className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm" /></label>
              <label className="text-xs font-semibold text-slate-600">Expected return (optional)
                <input type="date" value={absence.expected_return} onChange={(e) => setAbsence({ ...absence, expected_return: e.target.value })} data-testid="my-day-absence-return" className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm" /></label>
              <label className="text-xs font-semibold text-slate-600">Note (optional)
                <input value={absence.note} onChange={(e) => setAbsence({ ...absence, note: e.target.value })} data-testid="my-day-absence-note" className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm" /></label>
            </div>
            <p className="mt-2 text-[11px] text-amber-700">Leave the return date blank if it's unknown — we'll keep marking you absent until you're back.</p>
            <div className="mt-3 flex justify-end gap-2">
              <button onClick={() => setAbsence(null)} className="px-3 py-2 rounded-lg text-sm font-semibold text-slate-500">Cancel</button>
              <button onClick={saveAbsence} disabled={busy} data-testid="my-day-absence-save" className="px-4 py-2 rounded-lg text-sm font-bold text-white bg-amber-500">Report absence</button>
            </div>
          </div>
        )}
      </Card>

      {/* This month */}
      <Card testId="my-day-month">
        <h3 className="font-bold text-slate-900 mb-3 flex items-center gap-2"><Sun size={16} /> This month</h3>
        <div className="grid grid-cols-4 gap-2 text-center">
          {[['Recorded', `${m.recorded ?? 0}h`], ['Expected', `${m.expected ?? 0}h`], ['Overtime', `${m.overtime ?? 0}h`], ['Missing', m.missing ?? 0]].map(([l, v]) => (
            <div key={l} className="rounded-xl bg-slate-50 py-3">
              <div className="text-lg font-bold text-slate-900">{v}</div>
              <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">{l}</div>
            </div>
          ))}
        </div>
      </Card>

      {/* Upcoming */}
      {(d.upcoming_leave || []).length > 0 && (
        <Card testId="my-day-upcoming">
          <h3 className="font-bold text-slate-900 mb-2">Upcoming</h3>
          <div className="space-y-1.5">
            {d.upcoming_leave.map((l) => (
              <div key={l.id} className="flex items-center justify-between text-sm">
                <span className="capitalize text-slate-700">{(l.leave_type || 'leave')}</span>
                <span className="text-slate-500">{fmtDate(l.start_date)}{l.end_date && l.end_date !== l.start_date ? ` – ${fmtDate(l.end_date)}` : ''}</span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

/* ─────────────── Return-to-work acknowledgement ─────────────── */
const FIT_LABELS = { yes: 'Fit to return', phased: 'Phased return', no: 'Not yet fit' };

function RtwAckCard({ rtw, H, onDone }) {
  const [agreed, setAgreed] = useState(false);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const submit = async () => {
    if (!agreed) { setErr('Please tick the box to confirm the agreed actions.'); return; }
    setBusy(true); setErr('');
    try {
      await axios.post(`${API}/new-starter/portal/rtw/${rtw.leave_id}/acknowledge`,
        { agreed: true, comment: comment || null }, { headers: H });
      await onDone();
    } catch (e) { setErr(e?.response?.data?.detail || 'Could not submit your sign-off.'); setBusy(false); }
  };

  return (
    <div className="rounded-2xl border border-emerald-200 bg-emerald-50/60 p-5 shadow-sm" data-testid={`rtw-ack-card-${rtw.leave_id}`}>
      <div className="flex items-start gap-3">
        <div className="mt-0.5 rounded-lg bg-emerald-100 p-2 text-emerald-700"><ClipboardCheck size={18} /></div>
        <div className="flex-1 min-w-0">
          <h3 className="font-bold text-slate-900">Return-to-work sign-off</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            {rtw.interviewer ? `${rtw.interviewer} ` : 'Your manager '}completed a return-to-work check for your absence
            {rtw.start_date ? ` from ${fmtDate(rtw.start_date)}` : ''}{rtw.return_date ? `, returning ${fmtDate(rtw.return_date)}` : ''}.
            Please confirm the agreed actions below.
          </p>

          <div className="mt-3 space-y-2 text-sm">
            {rtw.reason && (
              <div><span className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Reason</span>
                <div className="text-slate-700">{rtw.reason}</div></div>
            )}
            {rtw.fit_to_return && (
              <div><span className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Fitness to return</span>
                <div className="text-slate-700">{FIT_LABELS[rtw.fit_to_return] || rtw.fit_to_return}{rtw.fit_details ? ` — ${rtw.fit_details}` : ''}</div></div>
            )}
            <div><span className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Agreed actions</span>
              <div className="text-slate-700" data-testid={`rtw-ack-actions-${rtw.leave_id}`}>{rtw.agreed_actions || 'No specific actions were recorded.'}</div></div>
          </div>

          <label className="mt-4 flex items-start gap-2 text-sm text-slate-700 cursor-pointer">
            <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)}
              data-testid={`rtw-ack-agree-${rtw.leave_id}`} className="mt-0.5 h-4 w-4 rounded border-slate-300 text-emerald-600" />
            <span>I confirm I have discussed and agree to the actions recorded above.</span>
          </label>

          <label className="mt-3 block text-xs font-semibold text-slate-600">Comment (optional)
            <textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={2}
              data-testid={`rtw-ack-comment-${rtw.leave_id}`}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" placeholder="Anything you'd like to add" /></label>

          {err && <div className="mt-2 text-xs text-rose-600" data-testid={`rtw-ack-error-${rtw.leave_id}`}>{err}</div>}
          <p className="mt-2 text-[11px] text-slate-500">Signing records your name, {'\u0026'} the date {'\u0026'} time as your electronic acknowledgement.</p>

          <div className="mt-3 flex justify-end">
            <button onClick={submit} disabled={busy} data-testid={`rtw-ack-submit-${rtw.leave_id}`}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm font-bold disabled:opacity-60">
              {busy ? <Loader2 size={14} className="animate-spin" /> : <PenLine size={14} />} Sign {'\u0026'} confirm
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────── My Time (spine) ─────────────── */
function PeriodSubmitCard({ H }) {
  const [rows, setRows] = useState(null);
  const [busy, setBusy] = useState('');
  const load = useCallback(async () => {
    try { const r = await axios.get(`${API}/new-starter/portal/periods`, { headers: H }); setRows(r.data.periods || []); }
    catch { setRows([]); }
  }, [H]);
  useEffect(() => { load(); }, [load]);

  const submit = async (pid) => {
    setBusy(pid);
    try { await axios.post(`${API}/new-starter/portal/period/${pid}/submit`, { declaration: true }, { headers: H }); await load(); }
    catch (e) { alert(e?.response?.data?.detail || 'Could not submit'); }
    setBusy('');
  };

  const open = (rows || []).filter((r) => ['draft', 'returned'].includes(r.status));
  if (!open.length) return null;
  return (
    <div className="rounded-2xl border border-cyan-200 bg-cyan-50/60 p-4" data-testid="period-submit-card">
      {open.map((r) => (
        <div key={r.period.id} className="flex items-center justify-between flex-wrap gap-2 py-1">
          <div>
            <div className="font-bold text-slate-900">Your {r.period.name} timesheet is ready</div>
            <div className="text-xs text-slate-600">
              {r.totals.regular}h recorded · {r.totals.overtime_raw || 0}h overtime · {r.totals.missing} missing
              {r.status === 'returned' && r.returned_reason && <span className="text-amber-700"> · returned: {r.returned_reason}</span>}
            </div>
          </div>
          <button onClick={() => submit(r.period.id)} disabled={busy === r.period.id} data-testid={`period-submit-${r.period.id}`}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-bold text-white" style={{ background: CORE }}>
            {busy === r.period.id ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />} Submit to manager
          </button>
        </div>
      ))}
      <p className="mt-1 text-[11px] text-slate-500">By submitting you confirm this reflects your working time and absence for the period.</p>
    </div>
  );
}

function MyTimeTab({ H }) {
  const [scope, setScope] = useState('week');
  const [anchor, setAnchor] = useState(() => new Date().toISOString().slice(0, 10));
  const [d, setD] = useState(null);

  const load = useCallback(async () => {
    setD(null);
    try { const r = await axios.get(`${API}/new-starter/portal/my-time?scope=${scope}&anchor=${anchor}`, { headers: H }); setD(r.data); }
    catch { setD({ records: [], totals: {} }); }
  }, [H, scope, anchor]);
  useEffect(() => { load(); }, [load]);

  const shift = (dir) => {
    const x = new Date(anchor + 'T00:00:00');
    x.setDate(x.getDate() + dir * (scope === 'month' ? 30 : 7));
    setAnchor(x.toISOString().slice(0, 10));
  };

  const t = d?.totals || {};
  return (
    <div className="space-y-4" data-testid="staff-my-time">
      <PeriodSubmitCard H={H} />
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex gap-1.5">
          {['week', 'month'].map((s) => (
            <button key={s} onClick={() => setScope(s)} data-testid={`my-time-scope-${s}`}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold border capitalize ${scope === s ? 'border-cyan-500 text-cyan-700 bg-cyan-50' : 'border-slate-200 text-slate-500'}`}>{s}</button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => shift(-1)} data-testid="my-time-prev" className="p-1.5 rounded-lg border border-slate-200 text-slate-500"><ChevronLeft size={16} /></button>
          <span className="text-xs font-semibold text-slate-600">{d ? `${fmtDate(d.start)} – ${fmtDate(d.end)}` : '…'}</span>
          <button onClick={() => shift(1)} data-testid="my-time-next" className="p-1.5 rounded-lg border border-slate-200 text-slate-500"><ChevronRight size={16} /></button>
        </div>
      </div>

      {!d ? <Loader2 className="animate-spin text-cyan-500" /> : (
        <Card testId="my-time-table">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-slate-400 text-xs uppercase tracking-wide">
                <tr><th className="text-left py-1.5">Date</th><th className="text-left">Status</th><th className="text-left">Start</th><th className="text-left">Finish</th><th className="text-left">Break</th><th className="text-right">Hours</th></tr>
              </thead>
              <tbody>
                {d.records.map((r) => {
                  const meta = (d.statuses || {})[r.actual_status] || {};
                  return (
                    <tr key={r.date} className="border-t border-slate-100" data-testid={`my-time-row-${r.date}`}>
                      <td className="py-2 font-semibold text-slate-700">{fmtDate(r.date)}</td>
                      <td><StatusPill label={meta.label || r.actual_status} color={meta.color} /></td>
                      <td className="text-slate-600">{r.start_time || '—'}</td>
                      <td className="text-slate-600">{r.finish_time || '—'}</td>
                      <td className="text-slate-600">{r.break_minutes ? `${r.break_minutes}m` : '—'}</td>
                      <td className="text-right font-semibold text-slate-800">{r.regular_hours ? `${r.regular_hours}h` : '—'}</td>
                    </tr>
                  );
                })}
                {!d.records.length && <tr><td colSpan={6} className="py-6 text-center text-slate-400">No days in this range yet.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="mt-4 grid grid-cols-3 sm:grid-cols-6 gap-2 text-center">
            {[['Worked', `${t.worked ?? 0}h`], ['Expected', `${t.expected ?? 0}h`], ['Overtime', `${t.overtime ?? 0}h`], ['Holiday', `${t.holiday ?? 0}h`], ['Sick', `${t.sick ?? 0}h`], ['Missing', t.missing ?? 0]].map(([l, v]) => (
              <div key={l} className="rounded-lg bg-slate-50 py-2">
                <div className="text-sm font-bold text-slate-900">{v}</div>
                <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">{l}</div>
              </div>
            ))}
          </div>
        </Card>
      )}
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
const DOW = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

function selfHoursOf(r) {
  let base = 0;
  if (r.start && r.finish) {
    const [sh, sm] = r.start.split(':').map(Number);
    const [fh, fm] = r.finish.split(':').map(Number);
    let mins = (fh * 60 + fm) - (sh * 60 + sm);
    if (mins < 0) mins += 24 * 60;
    base = mins / 60;
  }
  base -= (Number(r.break_minutes) || 0) / 60;
  base += Number(r.pt_classes) || 0;
  return Math.max(0, Math.round(base * 100) / 100);
}

function TimesheetsTab({ H }) {
  const [week, setWeek] = useState(mondayOf());
  const [ts, setTs] = useState(null);
  const [rows, setRows] = useState([]);
  const [sig, setSig] = useState('');
  const [busy, setBusy] = useState(false);
  const [savedOk, setSavedOk] = useState(false);
  const [err, setErr] = useState('');

  const weekDates = useMemo(() => {
    const base = new Date(week + 'T00:00:00');
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(base); d.setDate(d.getDate() + i);
      return d.toISOString().slice(0, 10);
    });
  }, [week]);

  const load = useCallback(() => {
    setTs(null); setSavedOk(false); setErr('');
    axios.get(`${API}/new-starter/portal/timesheet?week_start=${week}`, { headers: H })
      .then((r) => setTs(r.data)).catch(() => setTs({ line_items: [] }));
  }, [week, H]);
  useEffect(() => { load(); }, [load]);

  // Seed the editable grid from persisted self_entries whenever the week loads.
  useEffect(() => {
    if (!ts) return;
    const se = ts.self_entries || {};
    setRows(weekDates.map((d) => ({
      date: d,
      start: se[d]?.start || '',
      finish: se[d]?.finish || '',
      break_minutes: se[d]?.break_minutes ?? '',
      pt_classes: se[d]?.pt_classes ?? '',
    })));
  }, [ts, weekDates]);

  const shiftByDate = useMemo(() => {
    const m = {};
    (ts?.line_items || []).filter((li) => li.source !== 'self').forEach((li) => { m[li.date] = li; });
    return m;
  }, [ts]);

  const locked = !!ts?.locked;
  const status = ts?.approval_status || 'pending';
  const weekTotal = rows.reduce((a, r) => a + selfHoursOf(r), 0)
    + Object.values(shiftByDate).reduce((a, li) => a + (li.actual_hours || 0), 0);

  const shift = (delta) => { const d = new Date(week + 'T00:00:00'); d.setDate(d.getDate() + delta * 7); setWeek(d.toISOString().slice(0, 10)); };
  const setRow = (i, patch) => setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));

  const saveDraft = async () => {
    setBusy(true); setErr(''); setSavedOk(false);
    try {
      const days = rows.filter((r) => r.start || r.finish || r.break_minutes || r.pt_classes)
        .map((r) => ({ date: r.date, start: r.start || null, finish: r.finish || null,
          break_minutes: Number(r.break_minutes) || 0, pt_classes: Number(r.pt_classes) || 0 }));
      const { data } = await axios.post(`${API}/new-starter/portal/timesheet/self-save`, { week_start: week, days }, { headers: H });
      setTs(data); setSavedOk(true);
    } catch (e) { setErr(e?.response?.data?.detail || 'Could not save.'); }
    finally { setBusy(false); }
  };

  const submit = async () => {
    if (!sig.trim()) { setErr('Type your name to sign the timesheet.'); return; }
    setBusy(true); setErr('');
    try {
      await saveDraftSilently();
      await axios.post(`${API}/new-starter/portal/timesheet/submit`, { week_start: week, signature: sig.trim() }, { headers: H });
      setSig(''); load();
    } catch (e) { setErr(e?.response?.data?.detail || 'Could not submit.'); }
    finally { setBusy(false); }
  };
  const saveDraftSilently = async () => {
    const days = rows.filter((r) => r.start || r.finish || r.break_minutes || r.pt_classes)
      .map((r) => ({ date: r.date, start: r.start || null, finish: r.finish || null,
        break_minutes: Number(r.break_minutes) || 0, pt_classes: Number(r.pt_classes) || 0 }));
    await axios.post(`${API}/new-starter/portal/timesheet/self-save`, { week_start: week, days }, { headers: H });
  };

  const BANNER = {
    submitted: ['bg-amber-50 border-amber-200 text-amber-800', 'Submitted — awaiting your manager\u2019s approval. Locked for edits.'],
    approved: ['bg-emerald-50 border-emerald-200 text-emerald-800', `Approved by ${ts?.approved_by || 'your manager'} \u2713`],
    returned: ['bg-red-50 border-red-200 text-red-800', `Returned by your manager: ${ts?.return_reason || 'please review and re-submit.'}`],
  };
  const banner = BANNER[status];

  return (
    <Card testId="staff-timesheets">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="font-bold text-slate-900">My timesheet</h2>
          <p className="text-xs text-slate-500">Fill in the hours you worked each day, then sign and submit for approval.</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => shift(-1)} className="px-2 py-1 rounded border border-slate-300 text-sm" data-testid="ts-prev">‹</button>
          <span className="text-sm font-semibold text-slate-700" data-testid="ts-week">Week of {fmtDate(week)}</span>
          <button onClick={() => shift(1)} className="px-2 py-1 rounded border border-slate-300 text-sm" data-testid="ts-next">›</button>
        </div>
      </div>
      {!ts ? <Loader2 className="animate-spin text-cyan-500" /> : (
        <>
          {banner && <div className={`mb-3 rounded-lg border px-3 py-2 text-sm ${banner[0]}`} data-testid="ts-banner">{banner[1]}</div>}

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
            <Stat label="Worked" value={`${Math.round(weekTotal * 100) / 100}h`} />
            <Stat label="Standard" value={`${ts.standard_hours ?? 0}h`} />
            <Stat label="Overtime" value={`${ts.overtime_hours ?? 0}h`} />
            <Stat label="Status" value={status} />
          </div>

          <div className="overflow-x-auto -mx-1">
            <table className="w-full text-sm min-w-[560px]" data-testid="ts-grid">
              <thead><tr className="text-left text-[11px] text-slate-400 uppercase">
                <th className="py-1.5 pl-1">Day</th><th>Start</th><th>Finish</th><th>Break (min)</th><th>PT classes</th><th className="text-right pr-1">Total</th>
              </tr></thead>
              <tbody>
                {rows.map((r, i) => {
                  const sh = shiftByDate[r.date];
                  const dt = selfHoursOf(r);
                  return (
                    <tr key={r.date} className="border-t border-slate-100 align-middle" data-testid={`ts-row-${i}`}>
                      <td className="py-2 pl-1">
                        <div className="font-semibold text-slate-700">{DOW[i]}</div>
                        <div className="text-[11px] text-slate-400">{fmtDate(r.date)}</div>
                        {sh && <div className="text-[11px] text-cyan-600 mt-0.5">Rota: {sh.scheduled_start}–{sh.scheduled_end}{sh.actual_hours ? ` · ${sh.actual_hours}h clocked` : ''}</div>}
                      </td>
                      <td><input type="time" value={r.start} disabled={locked} onChange={(e) => setRow(i, { start: e.target.value })} data-testid={`ts-start-${i}`} className="w-[104px] rounded border border-slate-300 px-2 py-1 disabled:bg-slate-50 disabled:text-slate-400" /></td>
                      <td><input type="time" value={r.finish} disabled={locked} onChange={(e) => setRow(i, { finish: e.target.value })} data-testid={`ts-finish-${i}`} className="w-[104px] rounded border border-slate-300 px-2 py-1 disabled:bg-slate-50 disabled:text-slate-400" /></td>
                      <td><input type="number" min="0" step="5" value={r.break_minutes} disabled={locked} onChange={(e) => setRow(i, { break_minutes: e.target.value })} data-testid={`ts-break-${i}`} className="w-[70px] rounded border border-slate-300 px-2 py-1 disabled:bg-slate-50 disabled:text-slate-400" /></td>
                      <td><input type="number" min="0" step="0.5" value={r.pt_classes} disabled={locked} onChange={(e) => setRow(i, { pt_classes: e.target.value })} data-testid={`ts-pt-${i}`} className="w-[70px] rounded border border-slate-300 px-2 py-1 disabled:bg-slate-50 disabled:text-slate-400" /></td>
                      <td className="text-right pr-1 font-semibold text-slate-800" data-testid={`ts-total-${i}`}>{dt ? `${dt}h` : '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot><tr className="border-t-2 border-slate-200"><td className="py-2 pl-1 font-bold text-slate-900" colSpan={5}>Week total</td><td className="text-right pr-1 font-bold text-slate-900" data-testid="ts-week-total">{Math.round(weekTotal * 100) / 100}h</td></tr></tfoot>
            </table>
          </div>

          {err && <div className="mt-2 text-xs text-red-600" data-testid="ts-error">{err}</div>}

          {!locked && (
            <div className="mt-4 border-t border-slate-200 pt-3">
              <div className="flex flex-wrap items-end gap-3">
                <label className="flex-1 min-w-[180px]">
                  <span className="text-xs font-semibold text-slate-500">Sign (type your full name)</span>
                  <input value={sig} onChange={(e) => setSig(e.target.value)} data-testid="ts-signature" placeholder="e.g. Becky Hassell"
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
                </label>
                <button onClick={saveDraft} disabled={busy} data-testid="ts-save-draft"
                  className="rounded-lg px-4 py-2 text-sm font-semibold border border-slate-300 text-slate-700 disabled:opacity-40">
                  {busy ? 'Saving…' : 'Save draft'}</button>
                <button onClick={submit} disabled={busy} data-testid="ts-submit"
                  className="rounded-lg px-4 py-2 text-sm font-semibold text-slate-900 disabled:opacity-40" style={{ background: CORE }}>
                  Submit for approval</button>
              </div>
              {savedOk && <div className="text-xs text-emerald-600 mt-2" data-testid="ts-saved-ok">Draft saved ✓</div>}
            </div>
          )}
          {locked && ts.employee_signature && (
            <div className="mt-3 text-xs text-slate-500" data-testid="ts-signed-by">Signed by {ts.employee_signature}{ts.submitted_at ? ` · ${fmtDate(ts.submitted_at.slice(0, 10))}` : ''}</div>
          )}
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
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const load = useCallback(() => { axios.get(`${API}/new-starter/portal/holidays`, { headers: H }).then((r) => setData(r.data)).catch(() => setData({ mine: [], team: [], allowance: {} })); }, [H]);
  useEffect(() => { load(); }, [load]);

  // Live working-days preview (excludes weekends + bank holidays) once both dates are set.
  useEffect(() => {
    if (!form.start_date || !form.end_date || form.end_date < form.start_date) { setPreview(null); return; }
    let alive = true;
    axios.get(`${API}/new-starter/portal/holidays/preview`, { headers: H, params: { start: form.start_date, end: form.end_date } })
      .then((r) => { if (alive) setPreview(r.data); }).catch(() => { if (alive) setPreview(null); });
    return () => { alive = false; };
  }, [form.start_date, form.end_date, H]);

  const submit = async () => {
    setBusy(true); setErr('');
    try { await axios.post(`${API}/new-starter/portal/holidays`, form, { headers: H }); setForm({ start_date: '', end_date: '', note: '' }); setPreview(null); load(); }
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
          {preview && (
            <div className="mt-3 flex items-center gap-2 rounded-lg bg-cyan-50 border border-cyan-200 px-3 py-2 text-sm text-cyan-800" data-testid="holiday-working-days">
              <Calendar size={15} />
              <span><strong>{preview.working_days}</strong> working day{preview.working_days === 1 ? '' : 's'} will be deducted{preview.bank_holidays > 0 ? ` — ${preview.bank_holidays} bank holiday${preview.bank_holidays === 1 ? '' : 's'} excluded` : ''}.
                {typeof a.remaining === 'number' && preview.working_days > a.remaining && <span className="ml-1 font-semibold text-amber-700">More than your {a.remaining} remaining — your manager will review.</span>}
              </span>
            </div>
          )}
          <input value={form.note} onChange={(e) => setForm((p) => ({ ...p, note: e.target.value }))} data-testid="holiday-note" placeholder="Note (optional)" className="mt-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          {err && <div className="text-red-500 text-sm mt-2" data-testid="holiday-error">{err}</div>}
          <button onClick={submit} disabled={busy || !form.start_date || !form.end_date} data-testid="holiday-submit"
            className="mt-3 inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold text-slate-900 disabled:opacity-40" style={{ background: CORE }}>
            <Plus size={15} /> {busy ? 'Submitting…' : 'Submit request'}</button>
          <p className="mt-2 text-[11px] text-slate-500">Your request is routed to your line manager for approval. We count working days only.</p>
        </Card>

        <Card testId="staff-holiday-mine">
          <h2 className="font-bold text-slate-900 mb-3">Your requests</h2>
          {(data.mine || []).length === 0 ? <div className="text-sm text-slate-400">No holiday requests yet.</div> : (
            <div className="space-y-2">
              {data.mine.map((r) => (
                <div key={r.id} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 px-4 py-2.5" data-testid={`holiday-row-${r.id}`}>
                  <div className="text-sm text-slate-700">{fmtDate(r.start_date)} → {fmtDate(r.end_date)}
                    <span className="ml-2 text-xs capitalize text-slate-400">{r.leave_type}</span>
                    {typeof r.working_days === 'number' && <span className="ml-2 text-xs font-semibold text-cyan-700" data-testid={`holiday-days-${r.id}`}>{r.working_days} day{r.working_days === 1 ? '' : 's'}</span>}
                  </div>
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


/* ─────────────── My Details (populated from the new-starter sign-up) ─────────────── */
function mask4(v) {
  const s = String(v || '').replace(/\s+/g, '');
  if (!s) return '';
  if (s.length <= 4) return '••••';
  return '•••• ' + s.slice(-4);
}
function DetailRow({ label, value, testId }) {
  return (
    <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-3" data-testid={testId}>
      <div className="text-[11px] text-slate-400 uppercase tracking-wide">{label}</div>
      <div className="text-sm font-semibold text-slate-800 break-words">{value ? value : <span className="text-slate-400 font-normal">Not provided</span>}</div>
    </div>
  );
}
function DetailSection({ title, children }) {
  return (
    <div className="mb-5">
      <div className="text-xs font-bold uppercase tracking-wider text-cyan-600 mb-2">{title}</div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">{children}</div>
    </div>
  );
}
function MyDetailsTab({ me, H }) {
  // The Staff Portal already loads /new-starter/me for onboarding-origin staff.
  // We reuse that here; if the parent only has a minimal profile (platform-token
  // staff with no onboarding case), we try a direct fetch, else show a gentle note.
  const [full, setFull] = useState(me && me.forms ? me : null);
  const [reqs, setReqs] = useState([]);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const [photo, setPhoto] = useState('');
  const [photoBusy, setPhotoBusy] = useState(false);
  const fileRef = useRef(null);

  const loadReqs = useCallback(() => {
    axios.get(`${API}/new-starter/portal/detail-change-requests`, { headers: H })
      .then((r) => setReqs(r.data?.requests || [])).catch(() => setReqs([]));
  }, [H]);

  useEffect(() => {
    if (me && me.forms) setFull(me);
    else axios.get(`${API}/new-starter/me`, { headers: H }).then((r) => setFull(r.data)).catch(() => setFull(me || {}));
    loadReqs();
  }, [me, H, loadReqs]);

  if (!full) return <Loader2 className="animate-spin text-cyan-500" />;

  const person = full.person || {};
  const emp = full.employment || {};
  const nd = (full.forms && full.forms.new_starter && full.forms.new_starter.data) || {};
  const photoUrl = photo || person.photo_url || '';
  const onPhoto = async (e) => {
    const f = e.target.files?.[0]; if (!f) return;
    setPhotoBusy(true); setMsg('');
    try {
      const fd = new FormData(); fd.append('file', f);
      const r = await axios.post(`${API}/new-starter/portal/photo`, fd, { headers: { ...H } });
      setPhoto(r.data.photo_url); setMsg('Profile photo updated.');
    } catch (err) {
      setMsg(err?.response?.data?.detail || 'Could not upload photo.');
    } finally { setPhotoBusy(false); if (fileRef.current) fileRef.current.value = ''; }
  };
  const hasData = !!(nd.dob || nd.home_address || nd.ni_number || nd.emergency_contact_name
    || emp.job_title || emp.position || emp.department || emp.proposed_start_date);
  const pending = reqs.find((r) => r.status === 'pending');

  const startEdit = () => {
    setForm({
      home_address: nd.home_address || emp.home_address || '', dob: nd.dob || '',
      ni_number: nd.ni_number || '', emergency_contact_name: nd.emergency_contact_name || '',
      emergency_contact_phone: nd.emergency_contact_phone || '',
      bank_name: nd.bank_name || '', sort_code: nd.sort_code || '', bank_account: nd.bank_account || '',
    });
    setNote(''); setMsg(''); setEditing(true);
  };
  const setF = (k) => (e) => setForm((p) => ({ ...p, [k]: e.target.value }));
  const submit = async () => {
    setBusy(true); setMsg('');
    try {
      const r = await axios.post(`${API}/new-starter/portal/detail-change-request`,
        { changes: form, note }, { headers: H });
      setEditing(false); setMsg(`Request sent to HR (${(r.data?.fields || []).length} field(s)).`); loadReqs();
    } catch (e) {
      setMsg(e?.response?.data?.detail || 'Could not submit — please try again.');
    } finally { setBusy(false); }
  };

  const EDIT_FIELDS = [
    ['home_address', 'Home address'], ['dob', 'Date of birth'], ['ni_number', 'National Insurance no.'],
    ['emergency_contact_name', 'Emergency contact name'], ['emergency_contact_phone', 'Emergency contact phone'],
    ['bank_name', 'Bank name'], ['sort_code', 'Sort code'], ['bank_account', 'Bank account'],
  ];

  return (
    <Card testId="staff-details">
      <div className="flex items-start justify-between gap-3 mb-1 flex-wrap">
        <h2 className="font-bold text-slate-900">My details</h2>
        <div className="flex items-center gap-2">
          {full.activated && <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700">From your sign-up ✓</span>}
          {!editing && (
            <button onClick={startEdit} disabled={!!pending} data-testid="detail-request-change-btn"
              className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border border-slate-300 text-slate-600 hover:border-cyan-400 disabled:opacity-40"
              title={pending ? 'You already have a change request awaiting HR review' : undefined}>
              <PenLine size={13} /> Request changes
            </button>
          )}
        </div>
      </div>
      <p className="text-sm text-slate-500 mb-4">The information you provided during your Pulse Fitness sign-up. Use “Request changes” to ask HR to update your personal, emergency-contact or payroll details.</p>

      <div className="flex items-center gap-4 mb-5 pb-5 border-b border-slate-100" data-testid="detail-photo-block">
        <div className="h-20 w-20 rounded-full overflow-hidden bg-slate-100 border border-slate-200 flex items-center justify-center shrink-0">
          {photoUrl
            ? <img src={photoSrc(photoUrl)} alt="Your headshot" className="h-full w-full object-cover" data-testid="detail-photo-img" />
            : <span className="text-xl font-bold text-slate-400" data-testid="detail-photo-initials">{(person.full_name || '?').split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase()}</span>}
        </div>
        <div>
          <div className="text-sm font-semibold text-slate-800">Profile photo</div>
          <div className="text-xs text-slate-500 mb-1">A clear headshot your manager sees next to your name.</div>
          <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={onPhoto} data-testid="detail-photo-input" />
          <button type="button" onClick={() => fileRef.current && fileRef.current.click()} disabled={photoBusy} data-testid="detail-photo-btn"
            className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border border-slate-300 text-slate-600 hover:border-cyan-400 disabled:opacity-50">
            {photoBusy ? <Loader2 size={13} className="animate-spin" /> : <Camera size={13} />} {photoUrl ? 'Change photo' : 'Add photo'}
          </button>
        </div>
      </div>

      {msg && <div className="rounded-lg border border-cyan-200 bg-cyan-50 px-4 py-3 text-sm text-cyan-800 mb-4" data-testid="detail-request-msg">{msg}</div>}
      {pending && !editing && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 mb-4" data-testid="detail-pending-banner">
          A change request is awaiting HR review: {Object.values(pending.changes || {}).map((c) => c.label).join(', ')}.
        </div>
      )}
      {!hasData && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 mb-4" data-testid="staff-details-empty">
          Your personal details will appear here once your new-starter sign-up has been completed.
        </div>
      )}

      {editing ? (
        <div className="mb-2" data-testid="detail-edit-form">
          <div className="text-xs font-bold uppercase tracking-wider text-cyan-600 mb-2">Request changes</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {EDIT_FIELDS.map(([k, label]) => (
              <label key={k} className="block">
                <span className="text-[11px] text-slate-400 uppercase tracking-wide">{label}</span>
                <input value={form[k] || ''} onChange={setF(k)} data-testid={`detail-input-${k}`}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-800 focus:border-cyan-400 outline-none" />
              </label>
            ))}
          </div>
          <label className="block mt-3">
            <span className="text-[11px] text-slate-400 uppercase tracking-wide">Note to HR (optional)</span>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} data-testid="detail-input-note"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-800 focus:border-cyan-400 outline-none" />
          </label>
          <div className="flex gap-2 mt-3">
            <button onClick={submit} disabled={busy} data-testid="detail-submit-request"
              className="inline-flex items-center gap-1.5 text-sm font-bold px-4 py-2 rounded-lg disabled:opacity-50"
              style={{ background: CORE, color: '#00121a' }}>
              {busy ? <Loader2 className="animate-spin" size={15} /> : <Check size={15} />} Send to HR
            </button>
            <button onClick={() => setEditing(false)} data-testid="detail-cancel-request"
              className="inline-flex items-center gap-1.5 text-sm font-semibold px-4 py-2 rounded-lg border border-slate-300 text-slate-600">
              <X size={15} /> Cancel
            </button>
          </div>
          <p className="text-xs text-slate-400 mt-2">Your current values are pre-filled — edit only what needs changing. HR will review before anything updates.</p>
        </div>
      ) : (
        <>
          <DetailSection title="Personal">
            <DetailRow label="Full name" value={person.full_name} testId="detail-full-name" />
            <DetailRow label="Preferred name" value={emp.preferred_name} testId="detail-preferred-name" />
            <DetailRow label="Email" value={person.email} testId="detail-email" />
            <DetailRow label="Date of birth" value={nd.dob} testId="detail-dob" />
            <DetailRow label="Home address" value={nd.home_address || emp.home_address} testId="detail-address" />
            <DetailRow label="National Insurance no." value={mask4(nd.ni_number)} testId="detail-ni" />
          </DetailSection>

          <DetailSection title="Emergency contact">
            <DetailRow label="Name" value={nd.emergency_contact_name} testId="detail-ec-name" />
            <DetailRow label="Phone" value={nd.emergency_contact_phone} testId="detail-ec-phone" />
          </DetailSection>

          <DetailSection title="Payroll">
            <DetailRow label="Bank name" value={nd.bank_name} testId="detail-bank-name" />
            <DetailRow label="Sort code" value={nd.sort_code} testId="detail-sort-code" />
            <DetailRow label="Bank account" value={mask4(nd.bank_account)} testId="detail-bank" />
          </DetailSection>

          <DetailSection title="Employment">
            <DetailRow label="Job title" value={emp.job_title || emp.position} testId="detail-job-title" />
            <DetailRow label="Department" value={emp.department} testId="detail-department" />
            <DetailRow label="Site / place of work" value={emp.site || emp.place_of_work} testId="detail-site" />
            <DetailRow label="Start date" value={emp.proposed_start_date} testId="detail-start-date" />
            <DetailRow label="Employment type" value={emp.employment_type} testId="detail-emp-type" />
            <DetailRow label="Line manager" value={emp.line_manager} testId="detail-line-manager" />
          </DetailSection>

          {reqs.length > 0 && (
            <div className="mt-2">
              <div className="text-xs font-bold uppercase tracking-wider text-cyan-600 mb-2">Recent change requests</div>
              <div className="space-y-2" data-testid="detail-request-history">
                {reqs.slice(0, 5).map((r) => {
                  const tone = r.status === 'approved' ? 'bg-emerald-50 text-emerald-700'
                    : r.status === 'rejected' ? 'bg-rose-50 text-rose-700' : 'bg-amber-50 text-amber-700';
                  return (
                    <div key={r.id} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 px-4 py-2.5 text-sm">
                      <span className="text-slate-600 truncate">{Object.values(r.changes || {}).map((c) => c.label).join(', ')}</span>
                      <span className={`shrink-0 text-xs font-semibold px-2 py-0.5 rounded-full ${tone}`}>{(r.status || '').charAt(0).toUpperCase() + (r.status || '').slice(1)}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}
    </Card>
  );
}


/* ─────────────── Vehicle checks ─────────────── */
const CHECK_TYPE_LABEL = { car: 'Car', electric_car: 'Electric Car', van: 'Van', electric_van: 'Electric Van', lorry: 'Lorry / HGV', van_maintenance: 'Van', vehicle_check: 'Car' };
const vType = (v) => CHECK_TYPE_LABEL[v?.vehicle_type || v?.check_type] || 'Vehicle';
const VSTATUS = {
  due: ['Due this week', 'bg-amber-50 text-amber-700 border-amber-200'],
  in_progress: ['In progress', 'bg-sky-50 text-sky-700 border-sky-200'],
  submitted: ['Submitted', 'bg-emerald-50 text-emerald-700 border-emerald-200'],
  reviewed: ['Reviewed ✓', 'bg-emerald-50 text-emerald-700 border-emerald-200'],
};

function VehicleTab({ H, jwt }) {
  const [data, setData] = useState(null);
  const [openId, setOpenId] = useState(null);
  const load = useCallback(() => {
    axios.get(`${API}/new-starter/portal/vehicles`, { headers: H })
      .then((r) => setData(r.data)).catch(() => setData({ vehicles: [] }));
  }, [H]);
  useEffect(() => { load(); }, [load]);

  if (!data) return <Loader2 className="animate-spin text-cyan-500" />;
  if (openId) return <VehicleCheckForm H={H} jwt={jwt} vehicleId={openId} onBack={() => { setOpenId(null); load(); }} />;

  if (!data.vehicles?.length) return <Empty icon={Truck} title="No vehicle assigned" hint="Your manager assigns vehicles and the weekly check you need to complete." />;

  return (
    <div className="space-y-3" data-testid="staff-vehicle-tab">
      <p className="text-sm text-slate-500">Complete your weekly vehicle check. Week commencing <strong>{fmtDate(data.week_commencing)}</strong>.</p>
      {data.vehicles.map((v) => {
        const [label, cls] = VSTATUS[v.this_week?.status] || VSTATUS.due;
        return (
          <button key={v.id} onClick={() => setOpenId(v.id)} data-testid={`vehicle-card-${v.id}`}
            className="w-full text-left rounded-2xl bg-white border border-slate-200 shadow-sm p-5 hover:border-cyan-300 transition-colors">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3 min-w-0">
                <span className="rounded-xl bg-slate-900 text-white p-2.5"><Truck size={18} /></span>
                <div className="min-w-0">
                  <div className="font-bold text-slate-900 uppercase tracking-wide">{v.reg_no}</div>
                  <div className="text-xs text-slate-500 truncate">{v.make_model || vType(v)} · {vType(v)}</div>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {v.this_week?.has_defects && <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-rose-600"><ShieldAlert size={13} /> Defect</span>}
                <span className={`text-[11px] font-semibold px-2 py-1 rounded-full border ${cls}`} data-testid={`vehicle-status-${v.id}`}>{label}</span>
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}

function TriState({ value, onChange, testId }) {
  const opts = [['ok', 'OK', 'emerald'], ['defect', 'Defect', 'rose'], ['na', 'N/A', 'slate']];
  const on = { emerald: 'bg-emerald-500 text-white border-emerald-500', rose: 'bg-rose-500 text-white border-rose-500', slate: 'bg-slate-400 text-white border-slate-400' };
  return (
    <div className="inline-flex rounded-lg overflow-hidden border border-slate-200 shrink-0" data-testid={testId}>
      {opts.map(([val, lab, tone]) => (
        <button key={val} type="button" onClick={() => onChange(val)} data-testid={`${testId}-${val}`}
          className={`px-3 py-1.5 text-xs font-semibold border-l first:border-l-0 border-slate-200 ${value === val ? on[tone] : 'bg-white text-slate-500'}`}>
          {lab}
        </button>
      ))}
    </div>
  );
}

function VehicleCheckForm({ H, jwt, vehicleId, onBack }) {
  const [d, setD] = useState(null);
  const [items, setItems] = useState({});
  const [details, setDetails] = useState({});
  const [defect, setDefect] = useState({});
  const [photos, setPhotos] = useState({ vehicle: {}, defect: [] });
  const [declaration, setDeclaration] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [saved, setSaved] = useState('');
  const locked = d?.check?.status === 'submitted' || d?.check?.status === 'reviewed';

  useEffect(() => {
    axios.get(`${API}/new-starter/portal/vehicle-check?vehicle_id=${vehicleId}`, { headers: H }).then((r) => {
      setD(r.data);
      const c = r.data.check || {};
      setItems(c.items || {});
      setDetails({ ...c.details, driver_name: (c.details?.driver_name) || r.data.check?.driver_name });
      setDefect(c.defect || {});
      setPhotos(c.photos || { vehicle: {}, defect: [] });
      setDeclaration(!!c.declaration?.confirmed);
    }).catch((e) => setErr(e?.response?.data?.detail || 'Could not load the check.'));
  }, [vehicleId, H]);

  const setItem = (id, val) => setItems((p) => ({ ...p, [id]: val }));
  const hasDefects = Object.values(items).some((v) => v === 'defect') || defect.safe_to_drive === false;
  const allIds = (d?.template?.sections || []).flatMap((s) => s.items.map((i) => i.id));
  const answered = allIds.filter((i) => items[i]).length;

  const persist = async (submit) => {
    setBusy(true); setErr(''); setSaved('');
    const body = { vehicle_id: vehicleId, details, items, defect, photos };
    try {
      const url = submit ? 'submit' : 'save';
      const r = await axios.post(`${API}/new-starter/portal/vehicle-check/${url}`, body, { headers: H });
      if (submit) { onBack(); } else { setSaved('Saved'); setTimeout(() => setSaved(''), 1500); setD((p) => ({ ...p, check: { ...p.check, status: r.data.status } })); }
    } catch (e) { setErr(e?.response?.data?.detail || 'Something went wrong.'); }
    finally { setBusy(false); }
  };

  const submit = () => {
    if (!declaration) { setErr('Please confirm the declaration before submitting.'); return; }
    if (answered < allIds.length) { setErr(`Please answer all ${allIds.length} checks (${answered} done).`); return; }
    persist(true);
  };

  const uploadPhoto = async (file, slot) => {
    const fd = new FormData(); fd.append('file', file);
    try {
      const r = await axios.post(`${API}/new-starter/portal/vehicle-check/photo`, fd, { headers: { ...H, 'Content-Type': 'multipart/form-data' } });
      if (slot === 'defect') setPhotos((p) => ({ ...p, defect: [...(p.defect || []), r.data.file_id] }));
      else setPhotos((p) => ({ ...p, vehicle: { ...(p.vehicle || {}), [slot]: r.data.file_id } }));
    } catch { setErr('Photo upload failed.'); }
  };

  if (!d) return <Loader2 className="animate-spin text-cyan-500" />;
  const tmpl = d.template;
  const sr = d.vehicle?.service_record || {};

  return (
    <div className="space-y-4" data-testid="vehicle-check-form">
      <div className="flex items-center justify-between gap-2">
        <button onClick={onBack} data-testid="vehicle-check-back" className="inline-flex items-center gap-1 text-sm font-semibold text-slate-500 hover:text-slate-800"><ChevronLeft size={16} /> Vehicles</button>
        {locked && <span className="text-[11px] font-semibold px-2 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">Submitted — read only</span>}
      </div>

      <Card testId="vehicle-check-details">
        <div className="flex items-center gap-3">
          <span className="rounded-xl bg-slate-900 text-white p-2.5"><Truck size={18} /></span>
          <div>
            <div className="font-bold text-slate-900 uppercase tracking-wide">{d.vehicle.reg_no}</div>
            <div className="text-xs text-slate-500">{tmpl.title} · Week commencing {fmtDate(d.week_commencing)}</div>
          </div>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-4 text-sm">
          <label className="block"><span className="text-xs text-slate-500">Driver</span>
            <input value={details.driver_name || ''} disabled={locked} onChange={(e) => setDetails((p) => ({ ...p, driver_name: e.target.value }))} data-testid="vehicle-driver-name" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" /></label>
          <label className="block"><span className="text-xs text-slate-500">Make / model</span>
            <input value={d.vehicle.make_model || ''} disabled className="mt-1 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-slate-500" /></label>
          <label className="block"><span className="text-xs text-slate-500">Odometer</span>
            <input value={details.odometer || ''} disabled={locked} onChange={(e) => setDetails((p) => ({ ...p, odometer: e.target.value }))} data-testid="vehicle-odometer" placeholder="Mileage" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" /></label>
        </div>
        {(sr.mot_due || sr.next_service || sr.insurance_expiry || sr.tax_status) && (
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500">
            {sr.next_service && <span>Next service: <strong>{sr.next_service}</strong></span>}
            {sr.mot_due && <span>MOT due: <strong>{sr.mot_due}</strong></span>}
            {sr.tax_status && <span>Tax: <strong>{sr.tax_status}</strong></span>}
            {sr.insurance_expiry && <span>Insurance: <strong>{sr.insurance_expiry}</strong></span>}
          </div>
        )}
      </Card>

      {tmpl.sections.map((s) => (
        <Card key={s.key} testId={`vehicle-section-${s.key}`}>
          <h3 className="font-bold text-slate-900 mb-3">{s.title}</h3>
          <div className="space-y-2.5">
            {s.items.map((it) => (
              <div key={it.id} className="flex items-start justify-between gap-3">
                <span className="text-sm text-slate-700 flex-1">{it.label}</span>
                <TriState value={items[it.id]} onChange={locked ? () => {} : (v) => setItem(it.id, v)} testId={`vehicle-item-${it.id}`} />
              </div>
            ))}
          </div>
        </Card>
      ))}

      {hasDefects && (
        <Card testId="vehicle-defect-block">
          <h3 className="font-bold text-rose-600 mb-3 flex items-center gap-2"><ShieldAlert size={18} /> Defects / corrective action</h3>
          <textarea value={defect.details || ''} disabled={locked} onChange={(e) => setDefect((p) => ({ ...p, details: e.target.value }))} rows={3} data-testid="vehicle-defect-details" placeholder="Describe the defect, location and any reference…" className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          <div className="grid grid-cols-2 gap-3 mt-3 text-sm">
            <YesNo label="Safe to drive?" value={defect.safe_to_drive} disabled={locked} onChange={(v) => setDefect((p) => ({ ...p, safe_to_drive: v }))} testId="vehicle-safe" />
            <YesNo label="Manager told?" value={defect.manager_told} disabled={locked} onChange={(v) => setDefect((p) => ({ ...p, manager_told: v }))} testId="vehicle-mgr-told" />
            <YesNo label={`${d.vehicle.provider || 'Provider'} contacted?`} value={defect.provider_contacted} disabled={locked} onChange={(v) => setDefect((p) => ({ ...p, provider_contacted: v }))} testId="vehicle-provider" />
            <YesNo label="Repair booked?" value={defect.repair_booked} disabled={locked} onChange={(v) => setDefect((p) => ({ ...p, repair_booked: v }))} testId="vehicle-repair-booked" />
          </div>
          {!locked && (
            <label className="mt-3 inline-flex items-center gap-2 text-xs font-semibold text-slate-600 cursor-pointer">
              <Camera size={14} /> Add defect photo
              <input type="file" accept="image/*" capture="environment" className="hidden" data-testid="vehicle-defect-photo" onChange={(e) => e.target.files[0] && uploadPhoto(e.target.files[0], 'defect')} />
            </label>
          )}
          {(photos.defect || []).length > 0 && (
            <div className="flex gap-2 mt-2 flex-wrap">
              {photos.defect.map((fid) => (
                <img key={fid} src={`${API}/vehicle-checks/photo/${fid}?auth=${jwt}`} alt="defect" className="h-16 w-16 object-cover rounded-lg border border-slate-200" />
              ))}
            </div>
          )}
        </Card>
      )}

      {!locked && (
        <Card testId="vehicle-declaration">
          <label className="flex items-start gap-2 text-sm text-slate-700 cursor-pointer">
            <input type="checkbox" checked={declaration} onChange={(e) => setDeclaration(e.target.checked)} data-testid="vehicle-declaration-check" className="mt-0.5 h-4 w-4 rounded border-slate-300 text-cyan-600" />
            <span>{tmpl.declaration}</span>
          </label>
          {err && <div className="mt-2 text-xs text-rose-600" data-testid="vehicle-error">{err}</div>}
          <div className="mt-4 flex items-center justify-between gap-2">
            <span className="text-xs text-slate-400">{answered}/{allIds.length} checks answered {saved && <span className="text-emerald-600 font-semibold ml-2">{saved}</span>}</span>
            <div className="flex gap-2">
              <button onClick={() => persist(false)} disabled={busy} data-testid="vehicle-save-draft" className="px-4 py-2 rounded-lg border border-slate-300 text-sm font-semibold text-slate-600">Save draft</button>
              <button onClick={submit} disabled={busy} data-testid="vehicle-submit" className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-bold text-slate-900" style={{ background: CORE }}>{busy ? <Loader2 size={14} className="animate-spin" /> : <PenLine size={14} />} Submit check</button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

function YesNo({ label, value, onChange, disabled, testId }) {
  return (
    <div data-testid={testId}>
      <span className="text-xs text-slate-500 block mb-1">{label}</span>
      <div className="inline-flex rounded-lg overflow-hidden border border-slate-200">
        <button type="button" disabled={disabled} onClick={() => onChange(true)} data-testid={`${testId}-yes`} className={`px-4 py-1.5 text-xs font-semibold ${value === true ? 'bg-emerald-500 text-white' : 'bg-white text-slate-500'}`}>Yes</button>
        <button type="button" disabled={disabled} onClick={() => onChange(false)} data-testid={`${testId}-no`} className={`px-4 py-1.5 text-xs font-semibold border-l border-slate-200 ${value === false ? 'bg-rose-500 text-white' : 'bg-white text-slate-500'}`}>No</button>
      </div>
    </div>
  );
}
