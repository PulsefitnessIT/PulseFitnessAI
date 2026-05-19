/**
 * TourSlotPicker — date-grouped, capacity-aware slot grid for the public
 * membership signup. Loads availability from
 * `GET /api/public/signup/{slug}/tour-slots` and posts the selection to
 * `POST /api/public/signup/{slug}/draft/{draftId}/book-tour`.
 *
 * Props:
 *   • API      — backend base URL (already includes `/api`)
 *   • slug     — gym slug from the URL
 *   • draftId  — current signup draft (must exist; the parent saves the
 *                draft before showing the slot picker)
 *   • email / fullName — denormalised onto the booking row so operators
 *                see who's coming without joining `signup_drafts`
 *   • value     — `{ slot_at, booking_id }` (controlled)
 *   • onChange  — fires after a successful book / cancel call
 *   • accent    — primary brand colour for selected state
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { MapPin, Loader2, Check, X as XIcon, AlertTriangle, Clock } from 'lucide-react';

const fmtDate = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
};

const fmtTime = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false });
};

const TourSlotPicker = ({ API, slug, draftId, email, fullName, value, onChange, accent = '#2563EB' }) => {
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [slotsByDate, setSlotsByDate] = useState({});
  const [meta, setMeta] = useState({ location: 'Reception', duration_minutes: 30, lead_time_hours: 4 });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await axios.get(`${API}/public/signup/${slug}/tour-slots`);
      setSlotsByDate(r.data?.slots_by_date || {});
      setMeta({
        location: r.data?.location || 'Reception',
        duration_minutes: r.data?.duration_minutes || 30,
        lead_time_hours: r.data?.lead_time_hours || 4,
      });
    } catch (e) {
      setError(e.response?.data?.detail || "Couldn't load availability.");
    }
    setLoading(false);
  }, [API, slug]);

  useEffect(() => { load(); }, [load]);

  const orderedDates = useMemo(
    () => Object.keys(slotsByDate || {}).sort(),
    [slotsByDate],
  );
  const [activeDate, setActiveDate] = useState(null);
  useEffect(() => {
    if (orderedDates.length && !activeDate) setActiveDate(orderedDates[0]);
  }, [orderedDates, activeDate]);

  const bookSlot = async (slotAt) => {
    if (!draftId) {
      setError('Please complete the Your details step first so we can save the booking against your sign-up.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await axios.post(
        `${API}/public/signup/${slug}/draft/${draftId}/book-tour`,
        { slot_at: slotAt, email, full_name: fullName },
      );
      onChange && onChange({ slot_at: slotAt, booking_id: r.data?.booking_id });
      // After a successful booking, re-fetch — the now-taken slot drops from the grid.
      load();
    } catch (e) {
      setError(e.response?.data?.detail || 'Could not book that slot. Try another.');
    }
    setBusy(false);
  };

  const cancelBooking = async () => {
    if (!draftId) return;
    setBusy(true);
    setError(null);
    try {
      await axios.post(`${API}/public/signup/${slug}/draft/${draftId}/cancel-tour`);
      onChange && onChange(null);
      load();
    } catch (e) {
      setError(e.response?.data?.detail || 'Could not cancel.');
    }
    setBusy(false);
  };

  if (loading) {
    return (
      <div className="p-6 text-center text-zinc-400" data-testid="tour-slot-picker-loading">
        <Loader2 size={20} className="inline animate-spin" /> Loading availability…
      </div>
    );
  }

  if (error && !orderedDates.length) {
    return (
      <div className="p-4 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700" data-testid="tour-slot-picker-error">
        <AlertTriangle size={14} className="inline mr-1" /> {error}
      </div>
    );
  }

  if (!orderedDates.length) {
    return (
      <div className="p-4 rounded-lg bg-zinc-100 border border-zinc-200 text-sm text-zinc-600" data-testid="tour-slot-picker-empty">
        No tour slots available in the next 2 weeks. The gym team will reach out after sign-up to find a time.
      </div>
    );
  }

  // Already-booked summary
  if (value?.slot_at) {
    return (
      <div className="space-y-2" data-testid="tour-slot-picker-booked">
        <div
          className="p-4 rounded-lg border flex items-center gap-3"
          style={{ background: `${accent}11`, borderColor: `${accent}66` }}
        >
          <div className="w-8 h-8 rounded-full grid place-items-center text-white shrink-0" style={{ background: accent }}>
            <Check size={16} />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-zinc-900">
              Tour booked for {fmtDate(value.slot_at)} at {fmtTime(value.slot_at)}
            </p>
            <p className="text-xs text-zinc-500 mt-0.5 flex items-center gap-1">
              <MapPin size={11} /> {meta.location} · {meta.duration_minutes}-minute slot
            </p>
          </div>
          <button
            type="button"
            onClick={cancelBooking}
            disabled={busy}
            className="text-xs text-zinc-500 hover:text-red-600 flex items-center gap-1 disabled:opacity-50"
            data-testid="tour-slot-picker-cancel"
          >
            <XIcon size={12} /> Cancel
          </button>
        </div>
      </div>
    );
  }

  const currentSlots = activeDate ? (slotsByDate[activeDate] || []) : [];

  return (
    <div className="space-y-3" data-testid="tour-slot-picker">
      <p className="text-xs text-zinc-500 flex items-center gap-1">
        <MapPin size={11} /> {meta.location}
        <span className="mx-1 text-zinc-300">·</span>
        <Clock size={11} /> {meta.duration_minutes}-minute slots
      </p>
      {/* Horizontal day strip */}
      <div className="flex gap-2 overflow-x-auto pb-2 -mx-1 px-1" data-testid="tour-slot-day-strip">
        {orderedDates.map((date) => {
          const active = date === activeDate;
          const d = new Date(date);
          const count = (slotsByDate[date] || []).length;
          return (
            <button
              type="button"
              key={date}
              onClick={() => setActiveDate(date)}
              className={`shrink-0 px-3 py-2 rounded-lg border text-left transition-colors ${
                active ? 'border-transparent text-white' : 'border-zinc-200 bg-white text-zinc-700 hover:border-zinc-300'
              }`}
              style={active ? { background: accent } : undefined}
              data-testid={`tour-slot-day-${date}`}
            >
              <p className="text-[10px] uppercase tracking-wider leading-tight">
                {d.toLocaleDateString(undefined, { weekday: 'short' })}
              </p>
              <p className="text-sm font-semibold leading-tight">
                {d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}
              </p>
              <p className={`text-[10px] mt-0.5 ${active ? 'text-white/80' : 'text-zinc-400'}`}>
                {count} slot{count === 1 ? '' : 's'}
              </p>
            </button>
          );
        })}
      </div>
      {/* Slot grid for active date */}
      <div className="grid grid-cols-3 sm:grid-cols-4 gap-2" data-testid="tour-slot-grid">
        {currentSlots.map((s) => (
          <button
            type="button"
            key={s.slot_at}
            onClick={() => bookSlot(s.slot_at)}
            disabled={busy}
            className="px-2 py-2 rounded-md border border-zinc-200 bg-white text-sm font-medium text-zinc-700 hover:border-zinc-900 hover:bg-zinc-50 disabled:opacity-50"
            data-testid={`tour-slot-${s.slot_at}`}
          >
            {fmtTime(s.slot_at)}
          </button>
        ))}
      </div>
      {error && (
        <p className="text-xs text-red-600 flex items-center gap-1" data-testid="tour-slot-picker-inline-error">
          <AlertTriangle size={11} /> {error}
        </p>
      )}
    </div>
  );
};

export default TourSlotPicker;
