/**
 * Memberships → Instructors tab.
 *
 * Operator-only Phase 3 view. Two sub-views:
 *   • Performance — per-instructor stats over a chosen window
 *   • Cover board — outstanding cover requests + assign-to action
 *
 * Mobile-first: stacked cards on small screens, table on lg+.
 */
import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { BarChart3, Trophy, AlertTriangle, Users, Calendar,
  PoundSterling, Loader2, ChevronRight, X, BadgeCheck, UserCheck, UserCircle2,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import InstructorRosterView from './InstructorRosterView';

const WINDOW_OPTIONS = [
  { value: 7,   label: '7d' },
  { value: 30,  label: '30d' },
  { value: 90,  label: '90d' },
];


export default function InstructorsTab({ API, headers }) {
  const { t } = useTranslation();
  const [view, setView] = useState('roster');
  return (
    <div data-testid="mbr-instructors">
      <div className="flex items-end justify-end gap-4 mb-4 flex-wrap">
        <div className="subtab-bar" role="tablist">
          <button type="button" onClick={() => setView('roster')}
            className={`subtab-pill ${view === 'roster' ? 'is-active' : ''}`}
            data-testid="mbr-instructors-tab-roster">
            <UserCircle2 size={12} /> {t('memberships_console.inst_roster', 'Roster')}
          </button>
          <button type="button" onClick={() => setView('performance')}
            className={`subtab-pill ${view === 'performance' ? 'is-active' : ''}`}
            data-testid="mbr-instructors-tab-performance">
            <BarChart3 size={12} /> {t('memberships_console.inst_performance', 'Performance')}
          </button>
          <button type="button" onClick={() => setView('cover')}
            className={`subtab-pill ${view === 'cover' ? 'is-active' : ''}`}
            data-testid="mbr-instructors-tab-cover">
            <AlertTriangle size={12} /> {t('memberships_console.inst_cover_board', 'Cover board')}
          </button>
        </div>
      </div>

      {view === 'roster'     && <InstructorRosterView API={API} headers={headers} />}
      {view === 'performance'&& <PerformanceView     API={API} headers={headers} />}
      {view === 'cover'      && <CoverBoardView      API={API} headers={headers} />}
    </div>
  );
}


function PerformanceView({ API, headers }) {
  const { t } = useTranslation();
  const [days, setDays] = useState(30);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    axios.get(`${API}/memberships/instructors/performance?days=${days}`, { headers })
      .then((r) => setRows(r.data?.rows || []))
      .catch((e) => notifyApiError(notify, e, t('memberships_console.inst_load_fail', 'Failed to load')))
      .finally(() => setLoading(false));
  }, [API, headers, days]);

  const totals = useMemo(() => rows.reduce((acc, r) => ({
    classes: acc.classes + r.classes_total,
    pay: acc.pay + (r.pay_due_pence || 0),
    bookings: acc.bookings + r.bookings_sum,
    attended: acc.attended + r.attended_sum,
  }), { classes: 0, pay: 0, bookings: 0, attended: 0 }), [rows]);

  return (
    <div>
      <div className="flex items-center gap-2 mb-3 overflow-x-auto -mx-1 px-1 pb-1">
        <span className="text-[10px] uppercase tracking-wider font-bold text-[color:var(--theme-text-muted)] flex-shrink-0">{t('memberships_console.inst_window', 'Window')}</span>
        {WINDOW_OPTIONS.map((o) => (
          <button key={o.value} onClick={() => setDays(o.value)}
            className={`px-2.5 py-1 rounded-md text-[11px] font-bold border transition flex-shrink-0 ${
              days === o.value
                ? 'bg-[var(--color-brand-cyan)] text-[var(--color-surface-darker)] border-[var(--color-brand-cyan)]'
                : 'bg-transparent border-[color:var(--theme-border)] text-[color:var(--theme-text-muted)]'
            }`}
            data-testid={`mbr-instructors-window-${o.value}`}>
            {o.label}
          </button>
        ))}
      </div>

      {loading ? (
        <CenteredSpinner />
      ) : rows.length === 0 ? (
        <div className="rounded-xl border border-dashed border-[color:var(--theme-border)] p-10 text-center" data-testid="mbr-instructors-empty">
          <Trophy size={32} className="mx-auto text-[color:var(--theme-text-muted)] mb-3" />
          <p className="text-sm font-bold">{t('memberships_console.inst_no_activity', 'No instructor activity in the last {{days}} days', { days })}</p>
        </div>
      ) : (
        <>
          {/* Totals strip */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
            <SummaryStat label={t('memberships_console.inst_classes', 'Classes')} value={totals.classes} icon={Calendar} />
            <SummaryStat label={t('memberships_console.inst_bookings', 'Bookings')} value={totals.bookings} icon={Users} />
            <SummaryStat label={t('memberships_console.inst_attended', 'Attended')} value={totals.attended} icon={UserCheck} />
            <SummaryStat label={t('memberships_console.inst_pay_due', 'Pay due')} value={`£${(totals.pay / 100).toFixed(2)}`} icon={PoundSterling} />
          </div>
          {/* Mobile: stacked cards. Desktop: table-like rows. */}
          <div className="space-y-2">
            {rows.map((r, i) => (
              <PerformanceRow key={r.instructor_user_id} row={r} rank={i + 1} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}


function PerformanceRow({ row, rank }) {
  const { t } = useTranslation();
  const fill = row.fill_rate_pct;
  const attRate = row.attendance_rate_pct;
  const noShow = row.no_show_rate_pct;
  return (
    <div className="rounded-xl border border-[color:var(--theme-border)] bg-white/[0.03] p-3 sm:p-4"
      data-testid={`mbr-instructor-${row.instructor_user_id}`}>
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 w-9 h-9 rounded-full overflow-hidden bg-[rgb(var(--rgb-brand-cyan)/0.15)] grid place-items-center text-[var(--color-brand-cyan)] font-extrabold text-sm">
          {row.avatar_url ? <img src={row.avatar_url} alt={row.name} className="w-full h-full object-cover" />
                          : (row.name || '?').slice(0, 1).toUpperCase()}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="font-bold truncate">{row.name}</p>
            {rank <= 3 && (
              <span className={`text-[9px] font-extrabold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                rank === 1 ? 'bg-amber-500/15 text-amber-500'
                : rank === 2 ? 'bg-zinc-500/15 text-zinc-400'
                : 'bg-orange-500/15 text-orange-500'
              }`}>
                <Trophy size={9} className="inline mr-0.5" /> #{rank}
              </span>
            )}
          </div>
          <p className="text-[11px] text-[color:var(--theme-text-muted)] truncate">{row.email}</p>
        </div>
        <div className="text-right flex-shrink-0">
          <p className="text-base font-extrabold tracking-tight">£{(row.pay_due_pence / 100).toFixed(2)}</p>
          <p className="text-[9px] uppercase tracking-wider font-bold text-[color:var(--theme-text-muted)]">{t('memberships_console.inst_pay_due', 'Pay due')}</p>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-3">
        <Metric label={t('memberships_console.inst_classes', 'Classes')} primary={row.classes_total}
          subtitle={t('memberships_console.inst_done_cancelled', '{{done}} done · {{cancelled}} cancelled', { done: row.classes_completed, cancelled: row.classes_cancelled })} />
        <Metric label={t('memberships_console.inst_fill_rate', 'Fill rate')} primary={`${fill}%`} bar={fill}
          tone={fill >= 70 ? 'emerald' : fill >= 40 ? 'amber' : 'red'} />
        <Metric label={t('memberships_console.inst_attendance', 'Attendance')} primary={`${attRate}%`} bar={attRate}
          tone={attRate >= 80 ? 'emerald' : 'amber'} />
        <Metric label={t('memberships_console.inst_no_show', 'No-show')} primary={`${noShow}%`}
          tone={noShow >= 15 ? 'red' : noShow >= 7 ? 'amber' : 'emerald'} />
      </div>
    </div>
  );
}


function Metric({ label, primary, subtitle, bar, tone = 'emerald' }) {
  const tones = {
    emerald: 'bg-emerald-500',
    amber:   'bg-amber-500',
    red:     'bg-red-500',
  };
  return (
    <div className="rounded-lg border border-[color:var(--theme-border)] p-2">
      <p className="text-[9px] uppercase tracking-wider font-bold text-[color:var(--theme-text-muted)]">{label}</p>
      <p className="text-sm font-extrabold mt-0.5">{primary}</p>
      {subtitle && <p className="text-[10px] text-[color:var(--theme-text-muted)] truncate">{subtitle}</p>}
      {bar !== undefined && (
        <div className="h-1 mt-1 rounded bg-zinc-500/15 overflow-hidden">
          <div className={`h-full ${tones[tone]}`}
            style={{ width: `${Math.min(Math.max(bar, 0), 100)}%` }} />
        </div>
      )}
    </div>
  );
}


function SummaryStat({ label, value, icon: Icon }) {
  return (
    <div className="rounded-lg border border-[color:var(--theme-border)] bg-white/[0.03] p-2.5">
      <p className="text-[9px] uppercase tracking-wider font-bold text-[color:var(--theme-text-muted)] flex items-center gap-1">
        {Icon && <Icon size={9} />} {label}
      </p>
      <p className="text-base font-extrabold mt-0.5">{value}</p>
    </div>
  );
}


/* ─────────────────── Cover board ─────────────────── */


function CoverBoardView({ API, headers }) {
  const { t } = useTranslation();
  const [requests, setRequests] = useState([]);
  const [instructors, setInstructors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [assignFor, setAssignFor] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [reqR, usersR] = await Promise.all([
        axios.get(`${API}/memberships/cover-requests`, { headers }),
        axios.get(`${API}/users?role=instructor`, { headers }).catch(() => ({ data: { users: [] } })),
      ]);
      setRequests(reqR.data?.requests || reqR.data?.cover_requests || []);
      setInstructors(usersR.data?.users || []);
    } catch (e) {
      notifyApiError(notify, e, t('memberships_console.inst_cover_load_fail', 'Failed to load cover board'));
    }
    setLoading(false);
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: the loader closure(s) re-read live state on every call; the effect re-fires on the listed trigger deps, so adding the function identity would just thrash without changing behaviour.
  useEffect(() => { load();   }, []);

  if (loading) return <CenteredSpinner />;

  if (requests.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-[color:var(--theme-border)] p-10 text-center" data-testid="mbr-cover-empty">
        <BadgeCheck size={32} className="mx-auto text-emerald-500 mb-3" />
        <p className="text-sm font-bold">{t('memberships_console.inst_no_cover', 'No outstanding cover requests')}</p>
        <p className="text-xs text-[color:var(--theme-text-muted)] mt-1">
          {t('memberships_console.inst_no_cover_hint', "Instructors can request cover from their portal — it'll show here for you to assign.")}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2" data-testid="mbr-cover-list">
      {requests.map((r) => (
        <CoverRow key={r.id} req={r} onAssign={() => setAssignFor(r)} />
      ))}
      {assignFor && (
        <AssignCoverModal API={API} headers={headers}
          req={assignFor} instructors={instructors}
          onClose={(refresh) => { setAssignFor(null); if (refresh) load(); }} />
      )}
    </div>
  );
}


function CoverRow({ req, onAssign }) {
  const { t } = useTranslation();
  const isOpen = req.status === 'open' || req.status === 'open_to_all';
  return (
    <div className="rounded-xl border border-[color:var(--theme-border)] bg-white/[0.03] p-3 sm:p-4 flex items-start gap-3"
      data-testid={`mbr-cover-${req.id}`}>
      <div className="flex-shrink-0 w-9 h-9 rounded-md bg-amber-500/15 grid place-items-center">
        <AlertTriangle size={14} className="text-amber-500" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-bold text-sm truncate">{req.class_name || t('memberships_console.inst_class', 'Class')} · {req.starts_at && new Date(req.starts_at).toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</p>
        <p className="text-[11px] text-[color:var(--theme-text-muted)] mt-0.5 truncate">
          {t('memberships_console.inst_from', 'From')} {req.from_user_name || req.from_user_email || '—'}
          {req.reason && <span className="block sm:inline sm:ml-2">· {req.reason}</span>}
        </p>
      </div>
      {isOpen ? (
        <button onClick={onAssign}
          className="flex-shrink-0 px-3 py-1.5 rounded-md text-[11px] font-extrabold flex items-center gap-1"
          style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
          data-testid={`mbr-cover-assign-${req.id}`}>
          {t('memberships_console.inst_assign', 'Assign')} <ChevronRight size={11} />
        </button>
      ) : (
        <span className="flex-shrink-0 text-[10px] uppercase tracking-wider font-bold px-2 py-1 rounded bg-emerald-500/15 text-emerald-500">
          {req.status}
        </span>
      )}
    </div>
  );
}


function AssignCoverModal({ API, headers, req, instructors, onClose }) {
  const { t } = useTranslation();
  const [picked, setPicked] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!picked) { notify.error(t('memberships_console.inst_pick', 'Pick an instructor')); return; }
    setBusy(true);
    try {
      await axios.post(`${API}/memberships/cover-requests/${req.id}/assign`,
        { instructor_user_id: picked }, { headers });
      notify.success(t('memberships_console.inst_cover_assigned', 'Cover assigned'));
      onClose(true);
    } catch (e) {
      notifyApiError(notify, e, t('memberships_console.inst_failed', 'Failed'));
    }
    setBusy(false);
  };
  const eligible = instructors.filter((u) => u.id !== req.from_user_id);

  return (
    <div className="fixed inset-0 z-[80] bg-black/70 grid place-items-end sm:place-items-center p-3" onClick={() => onClose(false)}>
      <div className="bg-[color:var(--theme-surface)] dark:bg-zinc-900 rounded-2xl border border-[color:var(--theme-border)] w-full max-w-md shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        data-testid="mbr-cover-assign-modal">
        <div className="px-5 py-4 border-b border-[color:var(--theme-border)] flex items-start justify-between">
          <div>
            <p className="text-[10px] uppercase tracking-[0.2em] font-extrabold text-amber-500">{t('memberships_console.inst_assign_cover', 'Assign cover')}</p>
            <h3 className="text-lg font-extrabold mt-0.5">{req.class_name}</h3>
            <p className="text-xs text-[color:var(--theme-text-muted)]">
              {req.starts_at && new Date(req.starts_at).toLocaleString()}
            </p>
          </div>
          <button onClick={() => onClose(false)} className="p-1.5 rounded hover:bg-zinc-500/10"><X size={14} /></button>
        </div>
        <div className="p-5 max-h-[60vh] overflow-y-auto">
          {eligible.length === 0 ? (
            <p className="text-sm text-[color:var(--theme-text-muted)]">{t('memberships_console.inst_no_eligible', 'No eligible instructors. Add one in Master Admin → Users.')}</p>
          ) : (
            <div className="space-y-2">
              {eligible.map((u) => (
                <label key={u.id}
                  className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer ${
                    picked === u.id
                      ? 'border-[var(--color-brand-cyan)] bg-[rgb(var(--rgb-brand-cyan)/0.05)]'
                      : 'border-[color:var(--theme-border)] hover:bg-zinc-500/[0.04]'
                  }`}
                  data-testid={`mbr-cover-pick-${u.id}`}>
                  <input type="radio" name="cover-pick" checked={picked === u.id}
                    onChange={() => setPicked(u.id)} className="accent-[var(--color-brand-cyan)]" />
                  <div className="min-w-0 flex-1">
                    <p className="font-bold text-sm truncate">
                      {(u.first_name || '') + ' ' + (u.last_name || '')}
                    </p>
                    <p className="text-[11px] text-[color:var(--theme-text-muted)] truncate">{u.email}</p>
                  </div>
                </label>
              ))}
            </div>
          )}
        </div>
        <div className="px-5 py-4 border-t border-[color:var(--theme-border)] flex justify-end gap-2">
          <button onClick={() => onClose(false)}
            className="px-3 py-2 text-sm font-bold text-[color:var(--theme-text-muted)] hover:text-zinc-900 dark:hover:text-white">
            {t('memberships_console.inst_cancel', 'Cancel')}
          </button>
          <button onClick={submit} disabled={busy || !picked}
            className="px-4 py-2 rounded-md text-sm font-extrabold disabled:opacity-50 flex items-center gap-1"
            style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
            data-testid="mbr-cover-assign-confirm">
            {busy ? <Loader2 size={11} className="animate-spin" /> : <BadgeCheck size={11} />} {t('memberships_console.inst_assign', 'Assign')}
          </button>
        </div>
      </div>
    </div>
  );
}


function CenteredSpinner() {
  return (
    <div className="flex items-center justify-center py-10 text-[color:var(--theme-text-muted)] text-sm gap-2">
      <Loader2 size={14} className="animate-spin" /> Loading…
    </div>
  );
}
