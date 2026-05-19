/**
 * GymAxis Memberships — Instructor Portal (/instructor).
 *
 * Any user whose JWT resolves to a user.id matched on
 * class_templates.instructor_user_id (or has is_instructor=true). Reuses
 * the standard GymAxis operator JWT — logs in via /api/auth/login.
 *
 * Tabs:
 *   • Today   — today's classes (tap → roster + check-off)
 *   • Week    — upcoming 7 days
 *   • Pay     — current-month commission (rate × completed classes)
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import Button from '@/components/shared/Button';
import {
  Calendar, Clock, Users as UsersIcon, MapPin, ChevronLeft, CheckCircle2,
  XCircle, Sparkles, LogOut, Loader2, PoundSterling, Dumbbell, ArrowLeft,
  AlertCircle, Handshake, UserCircle2, Save, Upload,
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const TABS = [
  { id: 'today', label: 'Today', icon: Calendar },
  { id: 'week',  label: 'Week',  icon: Dumbbell },
  { id: 'pay',   label: 'Pay',   icon: PoundSterling },
  { id: 'profile', label: 'Profile', icon: UserCircle2 },
];

export default function InstructorPortal() {
  const [token, setToken] = useState(() => localStorage.getItem('token'));
  const [me, setMe] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('today');
  const [viewing, setViewing] = useState(null);  // occurrence being rostered

  const headers = useMemo(() => (token ? { Authorization: `Bearer ${token}` } : {}), [token]);

  useEffect(() => {
    if (!token) { setLoading(false); return; }
    axios.get(`${API}/instructor/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => setMe(r.data))
      .catch(() => { setMe(null); })
      .finally(() => setLoading(false));
  }, [token]);

  const signOut = () => {
    localStorage.removeItem('token');
    setToken(null);
    setMe(null);
  };

  if (loading) {
    return <div className="min-h-screen bg-[var(--color-surface-darker)] text-white grid place-items-center"><Loader2 className="animate-spin text-[var(--color-brand-cyan)]" /></div>;
  }
  if (!me) return <LoginGate onAuthed={(t) => { localStorage.setItem('token', t); setToken(t); }} />;

  return (
    <div className="min-h-screen bg-[var(--color-surface-darker)] text-white pb-24" data-testid="instructor-portal">
      <TopBar me={me} onSignOut={signOut} />
      <main className="max-w-2xl mx-auto px-4 py-6">
        {viewing ? (
          <RosterView occId={viewing} headers={headers} onBack={() => setViewing(null)} />
        ) : (
          <>
            {tab === 'today' && <ClassesView scope="today" headers={headers} onPick={setViewing} />}
            {tab === 'week'  && <ClassesView scope="week"  headers={headers} onPick={setViewing} />}
            {tab === 'pay'   && <PayView headers={headers} me={me} />}
            {tab === 'profile' && <ProfileView headers={headers} />}
          </>
        )}
      </main>
      {!viewing && <BottomNav tab={tab} setTab={setTab} />}
    </div>
  );
}


/* ─────────────────── Auth gate ─────────────────── */

function LoginGate({ onAuthed }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/auth/login`, { email, password });
      if (!data.token) throw new Error('No token');
      onAuthed(data.token);
    } catch (err) {
      notifyApiError(notify, err, 'Sign in failed');
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen bg-[var(--color-surface-darker)] text-white flex flex-col" data-testid="instructor-auth-gate">
      <header className="px-6 pt-10 pb-6 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[rgb(var(--rgb-brand-cyan)/0.1)] border border-[rgb(var(--rgb-brand-cyan)/0.2)] mb-6">
          <Sparkles size={12} className="text-[var(--color-brand-cyan)]" />
          <span className="text-[10px] font-bold tracking-[0.2em] uppercase text-[var(--color-brand-cyan)]">Instructor</span>
        </div>
        <h1 className="text-4xl font-extrabold tracking-tight" style={{ letterSpacing: '-0.03em' }}>
          Your class. Your crew.
        </h1>
        <p className="text-sm text-white/60 mt-2">Check off attendance. Track your pay.</p>
      </header>
      <div className="flex-1 flex items-start justify-center px-4 pb-10">
        <form onSubmit={submit} className="w-full max-w-sm space-y-3" data-testid="instructor-login-form">
          <LabelledInput label="Email" type="email" value={email} onChange={setEmail} required testid="instructor-login-email" />
          <LabelledInput label="Password" type="password" value={password} onChange={setPassword} required testid="instructor-login-password" />
          <button type="submit" disabled={busy}
            className="w-full rounded-lg py-3 text-sm font-extrabold uppercase tracking-wider disabled:opacity-60"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }} data-testid="instructor-login-submit">
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  );
}


/* ─────────────────── Chrome ─────────────────── */

function TopBar({ me, onSignOut }) {
  return (
    <header className="sticky top-0 z-30 bg-[var(--color-surface-darker)]/90 backdrop-blur border-b border-white/10 px-5 py-3 flex items-center justify-between">
      <div>
        <div className="text-[9px] font-bold uppercase tracking-[0.25em] text-[var(--color-brand-cyan)]">Instructor</div>
        <div className="text-sm font-extrabold">{me.name}</div>
      </div>
      <Button variant="ghost" size="icon" onClick={onSignOut} icon={LogOut} title="Sign out" data-testid="instructor-signout" />
    </header>
  );
}

function BottomNav({ tab, setTab }) {
  return (
    <nav className="fixed bottom-0 inset-x-0 z-40 bg-[var(--color-ink)] border-t border-white/10 grid grid-cols-3">
      {TABS.map((t) => {
        const Icon = t.icon;
        const active = tab === t.id;
        return (
          <button key={t.id} onClick={() => setTab(t.id)} data-testid={`instructor-tab-${t.id}`}
            className={`flex flex-col items-center gap-0.5 py-3 text-[10px] font-bold uppercase tracking-wider transition ${active ? 'text-[var(--color-brand-cyan)]' : 'text-white/50 hover:text-white/80'}`}>
            <Icon size={18} />
            {t.label}
          </button>
        );
      })}
    </nav>
  );
}


/* ─────────────────── Classes list ─────────────────── */

function ClassesView({ scope, headers, onPick }) {
  const [occs, setOccs] = useState([]);
  const [pickups, setPickups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [accepting, setAccepting] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const now = new Date();
      const from = new Date(now); from.setHours(0, 0, 0, 0);
      let to;
      if (scope === 'today') {
        to = new Date(from); to.setHours(23, 59, 59, 999);
      } else {
        to = new Date(from.getTime() + 7 * 86400000);
      }
      const [cls, pks] = await Promise.all([
        axios.get(`${API}/instructor/classes`, { headers, params: { from: from.toISOString(), to: to.toISOString() } }),
        axios.get(`${API}/instructor/cover-board`, { headers }).catch(() => ({ data: { requests: [] } })),
      ]);
      setOccs(cls.data.occurrences || []);
      setPickups(pks.data.requests || []);
    } catch { notify.error('Failed to load classes'); }
    finally { setLoading(false); }
  }, [headers, scope]);
  useEffect(() => { load(); }, [load]);

  const acceptPickup = async (req) => {
    setAccepting(req.id);
    try {
      await axios.post(`${API}/instructor/cover/${req.id}/accept`, {}, { headers });
      notify.success(`You've got ${req.occurrence_name}`);
      load();
    } catch (e) { notifyApiError(notify, e, 'Failed to accept'); }
    finally { setAccepting(null); }
  };

  return (
    <div data-testid={`instructor-${scope}`}>
      <h2 className="text-xl font-extrabold tracking-tight mb-4" style={{ letterSpacing: '-0.02em' }}>
        {scope === 'today' ? 'Today' : 'This week'}
      </h2>
      {pickups.length > 0 && (
        <section className="mb-6" data-testid="instructor-pickups">
          <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.25em] font-extrabold text-amber-300 mb-2">
            <Handshake size={10} /> Cover available · {pickups.length}
          </div>
          <div className="space-y-2">
            {pickups.map((r) => (
              <div key={r.id} className="rounded-xl border border-amber-400/30 bg-amber-500/5 p-3.5 flex items-center gap-3" data-testid={`instructor-pickup-${r.id}`}>
                <div className="flex-1 min-w-0">
                  <div className="font-bold text-white text-sm truncate">{r.occurrence_name}</div>
                  <div className="text-xs text-white/60 mt-0.5">
                    {new Date(r.starts_at).toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })} · {r.requester_name} out
                  </div>
                  {r.reason && <div className="text-[11px] text-white/40 mt-0.5 italic">"{r.reason}"</div>}
                </div>
                <button onClick={() => acceptPickup(r)} disabled={accepting === r.id}
                  className="px-3 py-2 rounded-lg text-xs font-extrabold uppercase tracking-wider shrink-0 disabled:opacity-50"
                  style={{ background: 'var(--color-warning)', color: 'var(--color-surface-darker)' }}
                  data-testid={`instructor-pickup-accept-${r.id}`}>
                  {accepting === r.id ? '…' : "I'll cover"}
                </button>
              </div>
            ))}
          </div>
        </section>
      )}
      {loading ? <Loader /> : occs.length === 0 ? <Empty text={scope === 'today' ? 'No classes today. Enjoy the rest.' : 'No classes booked for you this week.'} /> : (
        <div className="space-y-2">
          {occs.map((o) => {
            const pct = o.capacity > 0 ? Math.min(100, ((o.bookings_count || 0) / o.capacity) * 100) : 0;
            const color = pct >= 95 ? 'var(--color-danger)' : pct >= 70 ? 'var(--color-warning)' : 'var(--color-success)';
            const isCompleted = o.status === 'completed';
            return (
              <button key={o.id} onClick={() => onPick(o.id)} data-testid={`instructor-occ-${o.id}`}
                className="w-full text-left rounded-xl border border-white/10 bg-white/[0.03] p-3.5 hover:border-[rgb(var(--rgb-brand-cyan)/0.4)] transition"
                style={{ borderLeft: `3px solid ${o.colour || 'var(--color-brand-cyan)'}` }}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-bold text-white text-sm flex items-center gap-2">
                      {o.name}
                      {isCompleted && <span className="text-[9px] font-extrabold uppercase tracking-wider text-emerald-300 bg-emerald-500/15 px-1.5 py-0.5 rounded">Done</span>}
                    </div>
                    <div className="text-xs text-white/60 mt-0.5 flex items-center gap-3 flex-wrap">
                      <span className="flex items-center gap-1"><Clock size={10} />{new Date(o.starts_at).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' })}</span>
                      {o.room_name && <span className="flex items-center gap-1"><MapPin size={10} />{o.room_name}</span>}
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                      <div className="w-24 h-1 rounded bg-white/10 overflow-hidden"><div className="h-full" style={{ width: `${pct}%`, background: color }} /></div>
                      <span className="text-[10px] text-white/50 flex items-center gap-1"><UsersIcon size={9} />{o.bookings_count || 0}/{o.capacity}</span>
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}


/* ─────────────────── Roster ─────────────────── */

function RosterView({ occId, headers, onBack }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [marks, setMarks] = useState({});  // { booking_id: 'attended'|'no_show' }
  const [saving, setSaving] = useState(false);
  const [requestingCover, setRequestingCover] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/instructor/occurrences/${occId}/roster`, { headers });
      setData(data);
      // pre-load existing attended/no_show marks so operator can tweak
      const next = {};
      (data.roster || []).forEach((b) => {
        if (b.status === 'attended' || b.status === 'no_show') next[b.id] = b.status;
      });
      setMarks(next);
    } catch { notify.error('Failed to load roster'); }
    finally { setLoading(false); }
  }, [headers, occId]);
  useEffect(() => { load(); }, [load]);

  const markOne = (bookingId, status) => setMarks((prev) => ({
    ...prev, [bookingId]: prev[bookingId] === status ? undefined : status,
  }));

  const requestCover = async () => {
    const reason = window.prompt("Can't make it? (optional reason — shown to colleagues)");
    if (reason === null) return;  // cancelled prompt
    setRequestingCover(true);
    try {
      const { data: res } = await axios.post(
        `${API}/instructor/occurrences/${occId}/request-cover`,
        { reason: reason.trim() }, { headers });
      notify.success(res.already_open ? 'Cover already requested' : 'Cover requested — your crew has been pinged');
      onBack();
    } catch (e) { notifyApiError(notify, e, 'Failed'); }
    finally { setRequestingCover(false); }
  };

  const submit = async () => {
    const items = Object.entries(marks).filter(([, s]) => !!s).map(([booking_id, status]) => ({ booking_id, status }));
    if (items.length === 0) { notify.error('Mark at least one member'); return; }
    setSaving(true);
    try {
      await axios.post(`${API}/instructor/occurrences/${occId}/attendance`, { items }, { headers });
      notify.success(`Saved · ${items.length} member${items.length === 1 ? '' : 's'}`);
      onBack();
    } catch (e) { notifyApiError(notify, e, 'Failed'); }
    finally { setSaving(false); }
  };

  if (loading) return <Loader />;
  if (!data) return null;
  const occ = data.occurrence;
  const markAllPresent = () => {
    const next = {};
    data.roster.forEach((b) => { if (b.status === 'booked' || b.status === 'attended') next[b.id] = 'attended'; });
    setMarks(next);
  };

  return (
    <div data-testid="instructor-roster">
      <button onClick={onBack} className="text-xs text-white/60 hover:text-white flex items-center gap-1 mb-4" data-testid="instructor-roster-back">
        <ArrowLeft size={12} /> Back to classes
      </button>
      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 mb-4" style={{ borderLeft: `3px solid ${occ.colour || 'var(--color-brand-cyan)'}` }}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="font-extrabold text-lg">{occ.name}</div>
            <div className="text-xs text-white/60 mt-0.5">
              {new Date(occ.starts_at).toLocaleString([], { weekday: 'long', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
              {occ.room_name && ` · ${occ.room_name}`}
            </div>
            <div className="mt-2 text-xs text-white/50"><span className="text-white font-bold">{data.roster.length}</span> on the roster</div>
          </div>
          <button onClick={requestCover} disabled={requestingCover}
            className="shrink-0 text-[10px] font-extrabold uppercase tracking-wider px-2.5 py-1.5 rounded-lg border border-amber-400/40 text-amber-200 hover:bg-amber-500/10 flex items-center gap-1 disabled:opacity-50"
            data-testid="instructor-request-cover">
            <AlertCircle size={10} /> {requestingCover ? '…' : 'Cover'}
          </button>
        </div>
      </div>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-[10px] uppercase tracking-[0.25em] font-extrabold text-white/50">Attendance</h3>
        <button onClick={markAllPresent} className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-brand-cyan)] hover:underline" data-testid="instructor-mark-all">All present</button>
      </div>
      {data.roster.length === 0 ? <Empty text="Empty roster — no one booked in." /> : (
        <div className="space-y-1.5">
          {data.roster.map((b) => {
            const mark = marks[b.id];
            return (
              <div key={b.id} className="rounded-lg border border-white/10 bg-white/[0.02] p-3 flex items-center justify-between gap-3" data-testid={`instructor-roster-${b.id}`}>
                <div className="min-w-0">
                  <div className="font-bold text-white text-sm truncate">{b.member.name}</div>
                  <div className="text-[11px] text-white/50 truncate">{b.member.email}</div>
                </div>
                <div className="flex gap-1.5 shrink-0">
                  <button onClick={() => markOne(b.id, 'attended')} data-testid={`instructor-mark-attended-${b.id}`}
                    className={`w-9 h-9 rounded-lg grid place-items-center transition ${mark === 'attended' ? 'bg-emerald-500 text-black' : 'bg-white/5 text-white/50 hover:bg-white/10'}`}>
                    <CheckCircle2 size={15} />
                  </button>
                  <button onClick={() => markOne(b.id, 'no_show')} data-testid={`instructor-mark-noshow-${b.id}`}
                    className={`w-9 h-9 rounded-lg grid place-items-center transition ${mark === 'no_show' ? 'bg-red-500 text-white' : 'bg-white/5 text-white/50 hover:bg-white/10'}`}>
                    <XCircle size={15} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
      <button onClick={submit} disabled={saving || Object.keys(marks).length === 0}
        className="mt-6 w-full rounded-lg py-3 text-sm font-extrabold uppercase tracking-wider disabled:opacity-50"
        style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }} data-testid="instructor-roster-save">
        {saving ? 'Saving…' : `Save · ${Object.keys(marks).filter((k) => marks[k]).length} mark${Object.keys(marks).length === 1 ? '' : 's'}`}
      </button>
    </div>
  );
}


/* ─────────────────── Pay ─────────────────── */

function PayView({ headers, me }) {
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try { const { data } = await axios.get(`${API}/instructor/commission`, { headers, params: { month } });
      setData(data); }
    catch { notify.error('Failed to load commission'); }
    finally { setLoading(false); }
  }, [headers, month]);
  useEffect(() => { load(); }, [load]);

  const shiftMonth = (delta) => {
    const [y, m] = month.split('-').map(Number);
    const d = new Date(y, m - 1 + delta, 1);
    setMonth(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
  };

  return (
    <div data-testid="instructor-pay">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-extrabold tracking-tight" style={{ letterSpacing: '-0.02em' }}>This month</h2>
        <div className="flex items-center gap-1">
          <button onClick={() => shiftMonth(-1)} className="p-1.5 rounded-lg border border-white/10 hover:bg-white/5" data-testid="instructor-pay-prev"><ChevronLeft size={14} /></button>
          <span className="text-xs font-extrabold uppercase tracking-wider text-white/70 px-3">{month}</span>
          <button onClick={() => shiftMonth(1)} className="p-1.5 rounded-lg border border-white/10 hover:bg-white/5 rotate-180" data-testid="instructor-pay-next"><ChevronLeft size={14} /></button>
        </div>
      </div>
      {loading ? <Loader /> : !data ? <Empty text="Nothing yet." /> : (
        <>
          <div className="rounded-xl border border-[rgb(var(--rgb-brand-cyan)/0.3)] bg-gradient-to-br from-[rgb(var(--rgb-brand-cyan)/0.1)] to-transparent p-5" data-testid="instructor-pay-summary">
            <div className="text-[10px] uppercase tracking-[0.25em] font-extrabold text-[var(--color-brand-cyan)]">Estimated payout</div>
            <div className="text-4xl font-extrabold tracking-tight mt-1">£{(data.pay_pence / 100).toFixed(2)}</div>
            <div className="text-xs text-white/60 mt-2">
              {data.class_count} completed × £{(data.rate_pence / 100).toFixed(2)} rate
            </div>
            <div className="grid grid-cols-3 gap-3 mt-4 pt-4 border-t border-white/10">
              <Stat label="Scheduled" value={data.scheduled_count} />
              <Stat label="Completed" value={data.class_count} />
              <Stat label="Total attended" value={data.total_attended} />
            </div>
          </div>
          <h3 className="text-[10px] uppercase tracking-[0.25em] font-extrabold text-white/50 mt-6 mb-2">Class-by-class</h3>
          {(data.occurrences || []).length === 0 ? <Empty text="No classes this month." /> : (
            <div className="space-y-1.5">
              {data.occurrences.map((o) => (
                <div key={o.id} className="rounded-lg border border-white/10 bg-white/[0.02] p-3 flex items-center justify-between gap-3" data-testid={`instructor-pay-${o.id}`}>
                  <div className="min-w-0">
                    <div className="font-bold text-white text-sm truncate">{o.name}</div>
                    <div className="text-[11px] text-white/50">{new Date(o.starts_at).toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-[10px] font-bold text-white/60">{o.attended_count || 0} there</span>
                    <span className={`text-[9px] font-extrabold uppercase tracking-wider px-1.5 py-0.5 rounded ${o.status === 'completed' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-white/5 text-white/60'}`}>
                      {o.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
      <div className="mt-6 text-[10px] text-white/30 text-center tracking-wider uppercase">Rate £{(me.rate_pence / 100).toFixed(2)} per completed class</div>
    </div>
  );
}


/* ─────────────────── Helpers ─────────────────── */

function Stat({ label, value }) {
  return (
    <div>
      <div className="text-xl font-extrabold tracking-tight">{value}</div>
      <div className="text-[9px] font-bold uppercase tracking-[0.2em] text-white/50 mt-0.5">{label}</div>
    </div>
  );
}

function LabelledInput({ label, value, onChange, type = 'text', required, testid }) {
  return (
    <label className="block">
      <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/50">{label}{required ? ' *' : ''}</span>
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)} required={required}
        autoCapitalize={type === 'email' ? 'none' : undefined}
        autoCorrect={type === 'email' ? 'off' : undefined}
        className="mt-1 w-full rounded-lg bg-black/40 border border-white/10 px-3 py-2.5 text-sm text-white placeholder-white/30 focus:outline-none focus:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
        data-testid={testid} />
    </label>
  );
}

function Loader() { return <div className="py-12 grid place-items-center text-white/40"><Loader2 className="animate-spin" /></div>; }
function Empty({ text }) { return <div className="rounded-xl border border-white/10 bg-white/[0.02] p-5 text-center text-white/50 text-sm">{text}</div>; }


/* ─────────────────── Instructor self-edit profile (iter 215w) ─────────────────── */

function ProfileView({ headers }) {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await axios.get(`${API}/instructor/profile`, { headers });
        setProfile(data.instructor);
        setDraft({ ...data.instructor, social: data.instructor.social || {} });
      } catch (e) {
        if (e.response?.status === 404) setProfile({ missing: true });
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  }, []);

  const setField = (k) => (v) => setDraft((d) => ({ ...d, [k]: v }));
  const setSocial = (k) => (v) => setDraft((d) => ({ ...d, social: { ...(d.social || {}), [k]: v } }));

  const onPhoto = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 3 * 1024 * 1024) { notify.error('Image too large — max 3MB'); return; }
    const reader = new FileReader();
    reader.onload = () => setField('photo_url')(reader.result);
    reader.readAsDataURL(f);
  };

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        headline: draft.headline || '',
        bio: draft.bio || '',
        photo_url: draft.photo_url || '',
        hero_photo_url: draft.hero_photo_url || '',
        specialties: draft.specialties || [],
        qualifications: draft.qualifications || [],
        years_experience: draft.years_experience ?? null,
        social: draft.social || {},
      };
      const { data } = await axios.patch(`${API}/instructor/profile`, payload, { headers });
      setProfile(data.instructor);
      notify.success('Profile updated');
    } catch (e) {
      notifyApiError(notify, e, 'Save failed');
    } finally { setSaving(false); }
  };

  if (loading) return <Loader />;
  if (profile?.missing) {
    return (
      <Empty text="No profile linked to your account. Ask your studio's admin to create one and send you an invite." />
    );
  }
  if (!draft) return null;

  const initials = (profile.name || '?').split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase();

  return (
    <div className="space-y-4" data-testid="instructor-profile-editor">
      <div className="rounded-2xl border border-white/10 p-4 bg-white/[0.02]">
        <div className="flex items-center gap-3 mb-4">
          {draft.photo_url ? (
            <img src={draft.photo_url} alt={profile.name}
              className="w-16 h-16 rounded-full object-cover"
              style={{ border: '2px solid var(--color-brand-cyan)' }} />
          ) : (
            <div className="w-16 h-16 rounded-full grid place-items-center text-xl font-black"
              style={{ background: 'var(--color-brand-cyan)', color: '#0A0C10' }}>{initials}</div>
          )}
          <div className="flex-1 min-w-0">
            <div className="font-bold truncate">{profile.name}</div>
            <label className="inline-flex items-center gap-1 text-xs text-[var(--color-brand-cyan)] mt-1 cursor-pointer"
              data-testid="instructor-profile-photo-upload">
              <Upload size={11} /> Upload new photo
              <input type="file" accept="image/*" className="hidden" onChange={onPhoto} />
            </label>
          </div>
        </div>

        <Field label="Headline" value={draft.headline || ''} onChange={setField('headline')} testid="instructor-profile-headline" />
        <TextareaField label="Bio" rows={6} value={draft.bio || ''} onChange={setField('bio')} testid="instructor-profile-bio" />
        <Field label="Years teaching" type="number" value={draft.years_experience ?? ''} onChange={setField('years_experience')} testid="instructor-profile-years" />

        <TagField label="Specialties" value={draft.specialties || []} onChange={setField('specialties')} placeholder="Add specialty…" testid="instructor-profile-specialty" />
        <TagField label="Qualifications" value={draft.qualifications || []} onChange={setField('qualifications')} placeholder="Add qualification…" testid="instructor-profile-qual" />

        <div className="mt-3 grid grid-cols-1 gap-2">
          <Field label="Instagram" value={draft.social?.instagram || ''} onChange={setSocial('instagram')} />
          <Field label="TikTok"    value={draft.social?.tiktok    || ''} onChange={setSocial('tiktok')} />
          <Field label="LinkedIn"  value={draft.social?.linkedin  || ''} onChange={setSocial('linkedin')} />
          <Field label="Website"   value={draft.social?.website   || ''} onChange={setSocial('website')} />
        </div>

        <button onClick={save} disabled={saving}
          className="mt-4 inline-flex items-center gap-1.5 px-4 py-2.5 rounded-lg text-sm font-extrabold"
          style={{ background: 'var(--color-brand-cyan)', color: '#0A0C10' }}
          data-testid="instructor-profile-save">
          <Save size={13} /> {saving ? 'Saving…' : 'Save profile'}
        </button>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, type = 'text', testid }) {
  return (
    <label className="block mb-3">
      <span className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-white/50">{label}</span>
      <input type={type} value={value || ''} onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-lg bg-black/40 border border-white/10 px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
        data-testid={testid} />
    </label>
  );
}
function TextareaField({ label, value, onChange, rows = 5, testid }) {
  return (
    <label className="block mb-3">
      <span className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-white/50">{label}</span>
      <textarea rows={rows} value={value || ''} onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-lg bg-black/40 border border-white/10 px-3 py-2.5 text-sm text-white focus:outline-none focus:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
        data-testid={testid} />
    </label>
  );
}
function TagField({ label, value, onChange, placeholder, testid }) {
  const [draft, setDraft] = useState('');
  const add = () => {
    const v = draft.trim();
    if (!v || value.includes(v)) { setDraft(''); return; }
    onChange([...value, v]); setDraft('');
  };
  return (
    <div className="block mb-3">
      <span className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-white/50">{label}</span>
      <div className="flex flex-wrap gap-1.5 mt-1 mb-2">
        {value.map((v, i) => (
          <span key={v} className="inline-flex items-center gap-1 bg-white/5 px-2 py-0.5 rounded-full text-xs font-bold">
            {v}
            <button onClick={() => onChange(value.filter((_, j) => j !== i))} className="opacity-60 hover:opacity-100"><XCircle size={10} /></button>
          </span>
        ))}
      </div>
      <div className="flex gap-1.5">
        <input value={draft} onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
          placeholder={placeholder}
          className="flex-1 rounded-lg bg-black/40 border border-white/10 px-3 py-2 text-sm text-white focus:outline-none focus:border-[rgb(var(--rgb-brand-cyan)/0.6)]"
          data-testid={testid} />
        <button type="button" onClick={add} className="px-3 py-1 rounded-lg bg-white/5 text-xs font-bold">Add</button>
      </div>
    </div>
  );
}
