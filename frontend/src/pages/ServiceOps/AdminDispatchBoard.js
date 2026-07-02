/**
 * Admin Dispatch Board — iter 216h140.
 *
 * Two-pane workspace for service managers / owners to assign unscheduled
 * jobs to engineers and pick a slot. List of engineers on the left,
 * unassigned queue on the right; clicking a job opens an assign modal.
 *
 * Lives under /service-desk/dispatch (admin-only) — keeps the existing
 * engineer-side `/svc/engineer/diary` view untouched.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  AlertTriangle, Calendar, ChevronLeft, Loader2, RefreshCw,
  Wrench, Users, X, CheckCircle2,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const PRIO_DOT = {
  P1: 'bg-red-500',
  P2: 'bg-amber-500',
  P3: 'bg-cyan-500',
  P4: 'bg-slate-400',
};

const _fmtDay = (d) =>
  d.toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short' });
const fmtTime = (iso) =>
  iso
    ? new Date(iso).toLocaleString('en-GB', {
        weekday: 'short', day: '2-digit', month: 'short',
        hour: '2-digit', minute: '2-digit',
      })
    : '—';

// ── Assign modal ─────────────────────────────────────────────
const AssignModal = ({ job, engineers, onClose, onAssign, suggestedAt }) => {
  const [engineerId, setEngineerId] = useState('');
  const [scheduledAt, setScheduledAt] = useState(suggestedAt || '');
  const [minutes, setMinutes] = useState(job?.estimated_minutes || 60);
  if (!job) return null;

  const submit = (e) => {
    e.preventDefault();
    if (!engineerId || !scheduledAt) return;
    onAssign({
      engineer_id: engineerId,
      scheduled_at: new Date(scheduledAt).toISOString(),
      estimated_minutes: Number(minutes) || 60,
    });
  };
  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center sm:justify-center bg-black/50"
      onClick={onClose}
      data-testid="assign-modal"
    >
      <div
        className="bg-white w-full sm:max-w-md sm:rounded-2xl rounded-t-2xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
              {job.reference} · {job.priority || 'P3'}
            </p>
            <h2 className="text-lg font-bold text-slate-900">{job.title}</h2>
            <p className="text-xs text-slate-500">{job.site_name || job.customer_name}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700"
            data-testid="assign-modal-close"
          >
            <X size={20} />
          </button>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1">
              Engineer
            </label>
            <select
              required
              value={engineerId}
              onChange={(e) => setEngineerId(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              data-testid="assign-engineer-select"
            >
              <option value="">— select engineer —</option>
              {engineers.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.full_name} {e.open_jobs ? `(${e.open_jobs} open)` : ''}
                </option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1">
                Start time
              </label>
              <input
                required
                type="datetime-local"
                value={scheduledAt}
                onChange={(e) => setScheduledAt(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                data-testid="assign-time-input"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1">
                Est. minutes
              </label>
              <input
                type="number"
                min={15}
                max={600}
                step={15}
                value={minutes}
                onChange={(e) => setMinutes(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                data-testid="assign-minutes-input"
              />
            </div>
          </div>
          <div className="flex gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 border border-slate-300 rounded-lg py-2 text-sm font-semibold"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex-1 bg-cyan-600 hover:bg-cyan-700 text-white rounded-lg py-2 text-sm font-semibold"
              data-testid="assign-submit"
            >
              Assign
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

// ── Engineer column (today's slots preview) ─────────────────
const EngineerColumn = ({ engineer, slots, onPick }) => {
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const todays = (slots || []).filter((s) => (s.start_at || '').startsWith(today));
  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="min-w-0">
          <p className="text-sm font-bold text-slate-900 truncate">{engineer.full_name}</p>
          <p className="text-[10px] uppercase tracking-wider text-slate-500">
            {engineer.open_jobs || 0} open · {todays.length} today
          </p>
        </div>
        <button
          type="button"
          onClick={() => onPick(engineer)}
          className="text-xs font-semibold text-cyan-700 hover:underline"
          data-testid={`pick-engineer-${engineer.id}`}
        >
          Pick
        </button>
      </div>
      <div className="space-y-1 max-h-44 overflow-y-auto">
        {todays.length === 0 ? (
          <p className="text-xs text-slate-400 italic">No jobs today</p>
        ) : (
          todays.map((s) => (
            <div
              key={s.id}
              className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1.5"
            >
              <p className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
                {new Date(s.start_at).toLocaleTimeString('en-GB', {
                  hour: '2-digit', minute: '2-digit',
                })} · {s.kind}
              </p>
              <p className="text-xs font-semibold text-slate-900 truncate">{s.title}</p>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

// ── Main page ─────────────────────────────────────────────
export default function AdminDispatchBoard() {
  const navigate = useNavigate();
  const [engineers, setEngineers] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [slotsByEng, setSlotsByEng] = useState({});
  const [loading, setLoading] = useState(true);
  const [assignFor, setAssignFor] = useState(null);
  const [pickedEngineer, setPickedEngineer] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // Engineers + unassigned queue in parallel.
      const [eRes, jRes] = await Promise.all([
        axios.get(`${API}/svc/engineers`, auth()),
        axios.get(`${API}/svc/admin/diary/unassigned`, auth()),
      ]);
      const engs = (eRes.data.engineers || []).filter((e) => e.active !== false);
      setEngineers(engs);
      setJobs(jRes.data.jobs || []);

      // Fetch each engineer's diary for today
      const today = new Date();
      const from = new Date(today); from.setHours(0, 0, 0, 0);
      const to = new Date(today); to.setHours(23, 59, 59, 999);
      const fromIso = encodeURIComponent(from.toISOString());
      const toIso = encodeURIComponent(to.toISOString());
      const slotsResults = await Promise.all(
        engs.map((e) =>
          axios
            .get(
              `${API}/svc/admin/diary?engineer_id=${e.id}&from=${fromIso}&to=${toIso}`,
              auth(),
            )
            .then((r) => [e.id, r.data.slots || []])
            .catch(() => [e.id, []]),
        ),
      );
      const map = {};
      for (const [k, v] of slotsResults) map[k] = v;
      setSlotsByEng(map);
    } catch (e) {
      notify.error('Failed to load dispatch board', e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const suggestedAt = useMemo(() => {
    // Next sensible default: next 30-min boundary today.
    const d = new Date();
    d.setMinutes(d.getMinutes() < 30 ? 30 : 60, 0, 0);
    // datetime-local format
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }, []);

  const onAssign = async (payload) => {
    if (!assignFor) return;
    try {
      await axios.post(
        `${API}/svc/admin/diary/case/${assignFor.id}/assign`,
        payload,
        auth(),
      );
      notify.success(`Assigned ${assignFor.reference} ✓`);
      setAssignFor(null);
      setPickedEngineer(null);
      load();
    } catch (e) {
      notify.error('Assign failed', e?.response?.data?.detail || e.message);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50" data-testid="admin-dispatch-board">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              onClick={() => navigate('/service-desk')}
              className="text-slate-500 hover:text-slate-900"
              data-testid="dispatch-back"
            >
              <ChevronLeft size={22} />
            </button>
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-700">
                Pulse Fitness · Service Ops
              </p>
              <h1 className="text-xl font-extrabold text-slate-900 flex items-center gap-2">
                <Calendar size={20} /> Dispatch Board
              </h1>
            </div>
          </div>
          <button
            type="button"
            onClick={load}
            className="p-2 rounded-lg hover:bg-slate-100 text-slate-500"
            data-testid="dispatch-refresh"
            aria-label="Refresh"
          >
            {loading ? <Loader2 size={18} className="animate-spin" /> : <RefreshCw size={18} />}
          </button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-4 grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left: Unassigned queue (2 cols on desktop) */}
        <section className="lg:col-span-2 space-y-3">
          <div className="bg-white border border-slate-200 rounded-2xl p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <AlertTriangle size={16} className="text-amber-500" />
                Needs dispatch ({jobs.length})
              </h2>
              <span className="text-[10px] uppercase tracking-wider text-slate-500">
                Sorted by priority · SLA
              </span>
            </div>
            {jobs.length === 0 && !loading ? (
              <div
                className="border border-dashed border-slate-300 rounded-xl p-6 text-center"
                data-testid="dispatch-empty"
              >
                <CheckCircle2 size={24} className="mx-auto text-emerald-500 mb-2" />
                <p className="text-sm font-semibold text-slate-700">
                  All caught up — every open job has an engineer.
                </p>
              </div>
            ) : (
              <ul className="divide-y divide-slate-100">
                {jobs.map((j) => (
                  <li
                    key={j.id}
                    className="py-3 flex items-center gap-3"
                    data-testid={`dispatch-job-${j.reference}`}
                  >
                    <span
                      className={`w-2 h-2 rounded-full ${PRIO_DOT[j.priority] || 'bg-slate-300'}`}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-slate-900 truncate">{j.title}</p>
                      <p className="text-xs text-slate-500 truncate">
                        {j.reference} · {j.site_name || j.customer_name || 'Unknown site'}
                        {j.sla_resolve_at ? ` · SLA ${fmtTime(j.sla_resolve_at)}` : ''}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setAssignFor(j)}
                      className="bg-cyan-600 hover:bg-cyan-700 text-white text-xs font-semibold px-3 py-1.5 rounded-lg flex items-center gap-1"
                      data-testid={`dispatch-assign-btn-${j.reference}`}
                    >
                      <Users size={12} /> Assign
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        {/* Right: engineers column */}
        <aside className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <Wrench size={16} /> Engineers ({engineers.length})
            </h2>
            {pickedEngineer ? (
              <button
                type="button"
                onClick={() => setPickedEngineer(null)}
                className="text-xs font-semibold text-slate-500 hover:underline"
              >
                Clear pick
              </button>
            ) : null}
          </div>
          {engineers.length === 0 ? (
            <div className="bg-white border border-dashed border-slate-300 rounded-2xl p-6 text-center text-sm text-slate-500">
              No active engineers yet
            </div>
          ) : (
            engineers.map((e) => (
              <EngineerColumn
                key={e.id}
                engineer={e}
                slots={slotsByEng[e.id] || []}
                onPick={(eng) => setPickedEngineer(eng)}
              />
            ))
          )}
        </aside>
      </main>

      <AssignModal
        job={assignFor}
        engineers={engineers}
        onClose={() => setAssignFor(null)}
        onAssign={onAssign}
        suggestedAt={suggestedAt}
      />
    </div>
  );
}
