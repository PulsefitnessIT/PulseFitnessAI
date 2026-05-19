/**
 * Engineer Diary v1 — iter 216h140.
 *
 * Week-grid calendar view of the current engineer's assigned work,
 * unified across:
 *   • Service jobs   (svc_cases · blue)
 *   • PPM visits     (ppm_tasks · purple)
 *   • Personal blocks (svc_diary_blocks · slate)
 *
 * View modes: Week (7-day grid) · Day (vertical agenda).
 * Slots are read from `GET /api/svc/engineer/diary?from=&to=`.
 * Reschedule is a tap-and-pick-new-time flow (drag-and-drop deferred
 * to V2 to keep the mobile experience reliable).
 *
 * Layout: light-mode GymAxis brand, mobile-first with desktop
 * comfortable widening — Phase 4 desktop 3-column polish will come
 * later in the iteration.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  Calendar, ChevronLeft, ChevronRight, Plus, RefreshCw,
  Wrench, ShieldCheck, Coffee, Loader2, X, Clock,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const HOURS = Array.from({ length: 13 }, (_, i) => i + 7); // 07:00 → 19:00

// ── date helpers ────────────────────────────────────────────────
const startOfWeek = (d) => {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  const day = (x.getDay() + 6) % 7; // Mon=0
  x.setDate(x.getDate() - day);
  return x;
};
const addDays = (d, n) => {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
};
const sameDay = (a, b) =>
  a.getFullYear() === b.getFullYear() &&
  a.getMonth() === b.getMonth() &&
  a.getDate() === b.getDate();
const fmtDay = (d) =>
  d.toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short' });
const fmtTime = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
};
const fmtRange = (s, e) => `${fmtTime(s)} – ${fmtTime(e)}`;

const KIND_STYLE = {
  job: { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-900',
         dot: 'bg-blue-600', icon: Wrench },
  ppm: { bg: 'bg-purple-50', border: 'border-purple-200', text: 'text-purple-900',
         dot: 'bg-purple-600', icon: ShieldCheck },
  block: { bg: 'bg-slate-100', border: 'border-slate-300', text: 'text-slate-700',
           dot: 'bg-slate-500', icon: Coffee },
  holiday: { bg: 'bg-amber-50', border: 'border-amber-200', text: 'text-amber-900',
             dot: 'bg-amber-500', icon: Coffee },
  training: { bg: 'bg-emerald-50', border: 'border-emerald-200', text: 'text-emerald-900',
              dot: 'bg-emerald-600', icon: ShieldCheck },
  lunch: { bg: 'bg-orange-50', border: 'border-orange-200', text: 'text-orange-900',
           dot: 'bg-orange-500', icon: Coffee },
};

const slotStyle = (s) => KIND_STYLE[s.kind] || KIND_STYLE.block;

// ── compact slot card (used in day list + week grid) ────────────
const SlotChip = ({ slot, onClick, mode = 'list' }) => {
  const st = slotStyle(slot);
  const Icon = st.icon;
  if (mode === 'grid') {
    return (
      <button
        type="button"
        onClick={onClick}
        data-testid={`slot-grid-${slot.id}`}
        className={`w-full text-left rounded-md border ${st.border} ${st.bg} px-2 py-1.5 hover:shadow-sm transition-all`}
      >
        <p className={`text-[10px] font-bold uppercase tracking-wide ${st.text} flex items-center gap-1`}>
          <Icon size={10} /> {fmtTime(slot.start_at)}
        </p>
        <p className={`text-xs font-semibold ${st.text} truncate`}>{slot.title}</p>
        {slot.subtitle ? (
          <p className="text-[10px] text-slate-500 truncate">{slot.subtitle}</p>
        ) : null}
      </button>
    );
  }
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={`slot-list-${slot.id}`}
      className={`w-full flex items-stretch gap-3 rounded-xl border ${st.border} ${st.bg} hover:shadow-md transition-all p-3 text-left`}
    >
      <div className={`w-1.5 rounded-full ${st.dot}`} />
      <div className="flex-1 min-w-0">
        <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500 flex items-center gap-2">
          <Icon size={12} /> {slot.kind} · {slot.reference || '—'}
        </p>
        <p className="text-sm font-semibold text-slate-900 truncate">{slot.title}</p>
        {slot.subtitle ? (
          <p className="text-xs text-slate-500 truncate">{slot.subtitle}</p>
        ) : null}
      </div>
      <div className="text-right flex-shrink-0">
        <p className="text-sm font-bold text-slate-900 tabular-nums">
          {fmtTime(slot.start_at)}
        </p>
        {slot.end_at ? (
          <p className="text-[10px] text-slate-500 tabular-nums">{fmtTime(slot.end_at)}</p>
        ) : null}
      </div>
    </button>
  );
};

// ── slot detail drawer ──────────────────────────────────────────
const SlotDrawer = ({ slot, onClose, onReschedule, onDeleteBlock }) => {
  const [editing, setEditing] = useState(false);
  const [newTime, setNewTime] = useState('');
  if (!slot) return null;
  const st = slotStyle(slot);
  const Icon = st.icon;
  const canReschedule = slot.source === 'case';
  const canDelete = slot.source === 'block';

  const onSubmit = (e) => {
    e.preventDefault();
    if (!newTime) return;
    // newTime is local datetime — convert to ISO UTC for the API
    const iso = new Date(newTime).toISOString();
    onReschedule(slot, iso);
  };

  return (
    <div
      className="fixed inset-0 z-40 flex items-end sm:items-center sm:justify-center bg-black/50"
      onClick={onClose}
      data-testid="slot-drawer-backdrop"
    >
      <div
        className="bg-white w-full sm:max-w-md sm:rounded-2xl rounded-t-2xl p-5 max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
        data-testid="slot-drawer"
      >
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className={`w-9 h-9 rounded-xl ${st.bg} border ${st.border} flex items-center justify-center`}>
              <Icon size={18} className={st.text} />
            </span>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                {slot.kind} · {slot.reference || '—'}
              </p>
              <h2 className="text-lg font-bold text-slate-900">{slot.title}</h2>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700"
            data-testid="slot-drawer-close"
          >
            <X size={20} />
          </button>
        </div>
        {slot.subtitle ? (
          <p className="text-sm text-slate-600 mb-2">{slot.subtitle}</p>
        ) : null}
        <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 text-sm font-semibold text-slate-900 mb-4 flex items-center gap-2">
          <Clock size={14} className="text-slate-500" />
          {fmtRange(slot.start_at, slot.end_at)}
        </div>

        {slot.deeplink ? (
          <a
            href={slot.deeplink}
            className="block w-full text-center bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2.5 rounded-lg mb-3"
            data-testid="slot-drawer-open"
          >
            Open job detail
          </a>
        ) : null}

        {canReschedule && !editing ? (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="block w-full text-center bg-white hover:bg-slate-50 border border-slate-300 text-slate-900 font-semibold py-2.5 rounded-lg mb-2"
            data-testid="slot-drawer-reschedule"
          >
            Reschedule
          </button>
        ) : null}
        {canReschedule && editing ? (
          <form onSubmit={onSubmit} className="space-y-2 mb-2">
            <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide">
              New start time
            </label>
            <input
              type="datetime-local"
              value={newTime}
              onChange={(e) => setNewTime(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              required
              data-testid="slot-drawer-reschedule-input"
            />
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setEditing(false)}
                className="flex-1 border border-slate-300 rounded-lg py-2 text-sm font-semibold"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="flex-1 bg-blue-600 hover:bg-blue-700 text-white rounded-lg py-2 text-sm font-semibold"
                data-testid="slot-drawer-reschedule-submit"
              >
                Save
              </button>
            </div>
          </form>
        ) : null}
        {canDelete ? (
          <button
            type="button"
            onClick={() => onDeleteBlock(slot)}
            className="block w-full text-center bg-red-50 hover:bg-red-100 text-red-700 font-semibold py-2.5 rounded-lg"
            data-testid="slot-drawer-delete-block"
          >
            Delete block
          </button>
        ) : null}
      </div>
    </div>
  );
};

// ── new-block modal ─────────────────────────────────────────────
const NewBlockModal = ({ open, onClose, onCreate }) => {
  const [form, setForm] = useState({
    title: '', start_at: '', end_at: '', kind: 'block', note: '',
  });
  const update = (k, v) => setForm((s) => ({ ...s, [k]: v }));
  if (!open) return null;
  const submit = (e) => {
    e.preventDefault();
    if (!form.title || !form.start_at || !form.end_at) return;
    onCreate({
      title: form.title,
      kind: form.kind,
      note: form.note || null,
      start_at: new Date(form.start_at).toISOString(),
      end_at: new Date(form.end_at).toISOString(),
    });
  };
  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center sm:justify-center bg-black/50"
      onClick={onClose}
      data-testid="new-block-modal"
    >
      <div
        className="bg-white w-full sm:max-w-md sm:rounded-2xl rounded-t-2xl p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-lg font-bold text-slate-900 mb-3">Add block</h3>
        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1">
              Title
            </label>
            <input
              required
              value={form.title}
              onChange={(e) => update('title', e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              placeholder="Annual leave / Training / Lunch"
              data-testid="new-block-title"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1">
              Kind
            </label>
            <select
              value={form.kind}
              onChange={(e) => update('kind', e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              data-testid="new-block-kind"
            >
              <option value="block">Block</option>
              <option value="holiday">Holiday</option>
              <option value="training">Training</option>
              <option value="lunch">Lunch</option>
            </select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1">
                Start
              </label>
              <input
                required
                type="datetime-local"
                value={form.start_at}
                onChange={(e) => update('start_at', e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                data-testid="new-block-start"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1">
                End
              </label>
              <input
                required
                type="datetime-local"
                value={form.end_at}
                onChange={(e) => update('end_at', e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
                data-testid="new-block-end"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-1">
              Note (optional)
            </label>
            <textarea
              rows={2}
              value={form.note}
              onChange={(e) => update('note', e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
              data-testid="new-block-note"
            />
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
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white rounded-lg py-2 text-sm font-semibold"
              data-testid="new-block-submit"
            >
              Create
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

// ── main component ─────────────────────────────────────────────
export default function EngineerDiary() {
  const navigate = useNavigate();
  const [anchor, setAnchor] = useState(() => startOfWeek(new Date()));
  const [view, setView] = useState('week'); // 'week' | 'day'
  const [dayAnchor, setDayAnchor] = useState(() => new Date());
  const [slots, setSlots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [showNew, setShowNew] = useState(false);

  const weekStart = useMemo(() => startOfWeek(anchor), [anchor]);
  const weekEnd = useMemo(() => addDays(weekStart, 7), [weekStart]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const from = view === 'week'
        ? weekStart.toISOString()
        : new Date(dayAnchor.setHours(0, 0, 0, 0)).toISOString();
      const to = view === 'week'
        ? weekEnd.toISOString()
        : new Date(new Date(dayAnchor).setHours(23, 59, 59, 999)).toISOString();
      const r = await axios.get(
        `${API}/svc/engineer/diary?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
        auth(),
      );
      setSlots(r.data.slots || []);
    } catch (e) {
      notify.error('Failed to load diary', e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [view, weekStart, weekEnd, dayAnchor]);

  useEffect(() => { load(); }, [load]);

  const slotsByDay = useMemo(() => {
    const map = {};
    for (let i = 0; i < 7; i++) {
      map[i] = [];
    }
    for (const s of slots) {
      const d = new Date(s.start_at);
      const offset = Math.floor((d - weekStart) / 86400000);
      if (offset >= 0 && offset < 7) map[offset].push(s);
    }
    return map;
  }, [slots, weekStart]);

  const todaySlots = useMemo(
    () => slots.filter((s) => sameDay(new Date(s.start_at), dayAnchor)),
    [slots, dayAnchor],
  );

  const onReschedule = async (slot, isoTime) => {
    try {
      await axios.post(
        `${API}/svc/engineer/diary/case/${slot.source_id}/reschedule`,
        { scheduled_at: isoTime },
        auth(),
      );
      notify.success('Rescheduled');
      setSelected(null);
      load();
    } catch (e) {
      notify.error('Reschedule failed', e?.response?.data?.detail || e.message);
    }
  };

  const onDeleteBlock = async (slot) => {
    if (!window.confirm('Delete this block?')) return;
    try {
      await axios.delete(
        `${API}/svc/engineer/diary/blocks/${slot.source_id}`,
        auth(),
      );
      notify.success('Block deleted');
      setSelected(null);
      load();
    } catch (e) {
      notify.error('Delete failed', e?.response?.data?.detail || e.message);
    }
  };

  const onCreateBlock = async (payload) => {
    try {
      await axios.post(`${API}/svc/engineer/diary/blocks`, payload, auth());
      notify.success('Block added');
      setShowNew(false);
      load();
    } catch (e) {
      notify.error('Create failed', e?.response?.data?.detail || e.message);
    }
  };

  const openSlot = (slot) => {
    if (slot.source === 'case' && slot.deeplink) {
      // For job slots, allow viewing details but also let user reschedule.
      // We open the drawer first (which has both "Open" and "Reschedule").
    }
    setSelected(slot);
  };

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-diary">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              onClick={() => navigate('/svc/engineer')}
              className="text-slate-500 hover:text-slate-900"
              data-testid="diary-back"
            >
              <ChevronLeft size={22} />
            </button>
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-blue-700">
                GymAxis · Engineer
              </p>
              <h1 className="text-xl font-extrabold text-slate-900 flex items-center gap-2">
                <Calendar size={20} /> My Diary
              </h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={load}
              className="p-2 rounded-lg hover:bg-slate-100 text-slate-500"
              data-testid="diary-refresh"
              aria-label="Refresh"
            >
              {loading ? <Loader2 size={18} className="animate-spin" /> : <RefreshCw size={18} />}
            </button>
            <button
              type="button"
              onClick={() => setShowNew(true)}
              className="hidden sm:flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-3 py-2 rounded-lg text-sm font-semibold"
              data-testid="diary-add-block"
            >
              <Plus size={16} /> Block
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-4 space-y-4">
        {/* View toggle + week navigation */}
        <div className="flex items-center justify-between gap-3 bg-white border border-slate-200 rounded-2xl px-3 py-2">
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() =>
                view === 'week'
                  ? setAnchor(addDays(weekStart, -7))
                  : setDayAnchor(addDays(dayAnchor, -1))
              }
              className="p-2 rounded-lg hover:bg-slate-100 text-slate-500"
              data-testid="diary-prev"
            >
              <ChevronLeft size={18} />
            </button>
            <button
              type="button"
              onClick={() => {
                setAnchor(startOfWeek(new Date()));
                setDayAnchor(new Date());
              }}
              className="px-3 py-1.5 rounded-lg hover:bg-slate-100 text-xs font-semibold text-slate-700"
              data-testid="diary-today"
            >
              Today
            </button>
            <button
              type="button"
              onClick={() =>
                view === 'week'
                  ? setAnchor(addDays(weekStart, 7))
                  : setDayAnchor(addDays(dayAnchor, 1))
              }
              className="p-2 rounded-lg hover:bg-slate-100 text-slate-500"
              data-testid="diary-next"
            >
              <ChevronRight size={18} />
            </button>
            <p className="ml-2 text-sm font-semibold text-slate-700 tabular-nums">
              {view === 'week'
                ? `${fmtDay(weekStart)} → ${fmtDay(addDays(weekStart, 6))}`
                : fmtDay(dayAnchor)}
            </p>
          </div>
          <div className="inline-flex bg-slate-100 rounded-lg p-1 text-xs font-semibold">
            <button
              type="button"
              onClick={() => setView('week')}
              className={`px-3 py-1 rounded-md ${
                view === 'week' ? 'bg-white shadow text-slate-900' : 'text-slate-500'
              }`}
              data-testid="diary-view-week"
            >
              Week
            </button>
            <button
              type="button"
              onClick={() => setView('day')}
              className={`px-3 py-1 rounded-md ${
                view === 'day' ? 'bg-white shadow text-slate-900' : 'text-slate-500'
              }`}
              data-testid="diary-view-day"
            >
              Day
            </button>
          </div>
        </div>

        {/* Empty state */}
        {!loading && slots.length === 0 ? (
          <div
            className="bg-white border border-dashed border-slate-300 rounded-2xl p-8 text-center"
            data-testid="diary-empty"
          >
            <Calendar size={28} className="mx-auto text-slate-300 mb-2" />
            <p className="text-sm font-semibold text-slate-700">No jobs in this range</p>
            <p className="text-xs text-slate-500 mt-1">
              When a dispatcher assigns work it will show up here automatically.
            </p>
          </div>
        ) : null}

        {/* Week grid */}
        {view === 'week' && slots.length > 0 ? (
          <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
            <div className="grid grid-cols-7 divide-x divide-slate-200">
              {Array.from({ length: 7 }, (_, i) => {
                const d = addDays(weekStart, i);
                const isToday = sameDay(d, new Date());
                return (
                  <div key={i} className="min-h-[260px] flex flex-col">
                    <div
                      className={`px-2 py-2 text-center border-b border-slate-200 ${
                        isToday ? 'bg-blue-50' : 'bg-slate-50'
                      }`}
                    >
                      <p className="text-[10px] uppercase font-bold tracking-wider text-slate-500">
                        {DAYS[i]}
                      </p>
                      <p
                        className={`text-base font-bold tabular-nums ${
                          isToday ? 'text-blue-700' : 'text-slate-900'
                        }`}
                      >
                        {d.getDate()}
                      </p>
                    </div>
                    <div className="flex-1 p-1.5 space-y-1.5">
                      {(slotsByDay[i] || []).map((s) => (
                        <SlotChip key={s.id} slot={s} mode="grid" onClick={() => openSlot(s)} />
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}

        {/* Day list */}
        {view === 'day' && slots.length > 0 ? (
          <div className="space-y-2" data-testid="diary-day-list">
            {todaySlots.length === 0 ? (
              <div className="bg-white border border-slate-200 rounded-2xl p-6 text-center text-sm text-slate-500">
                No items today
              </div>
            ) : (
              todaySlots.map((s) => (
                <SlotChip key={s.id} slot={s} mode="list" onClick={() => openSlot(s)} />
              ))
            )}
          </div>
        ) : null}

        {/* Mobile FAB for new block */}
        <button
          type="button"
          onClick={() => setShowNew(true)}
          className="sm:hidden fixed bottom-6 right-6 z-30 bg-blue-600 hover:bg-blue-700 text-white w-14 h-14 rounded-full shadow-lg flex items-center justify-center"
          data-testid="diary-add-block-fab"
          aria-label="Add block"
        >
          <Plus size={22} />
        </button>
      </main>

      <SlotDrawer
        slot={selected}
        onClose={() => setSelected(null)}
        onReschedule={onReschedule}
        onDeleteBlock={onDeleteBlock}
      />
      <NewBlockModal
        open={showNew}
        onClose={() => setShowNew(false)}
        onCreate={onCreateBlock}
      />
    </div>
  );
}
