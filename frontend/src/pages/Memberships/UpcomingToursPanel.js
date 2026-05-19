/**
 * UpcomingToursPanel — operator-side compact list of upcoming tour bookings
 * for the current org (Memberships → Start tab and embeddable elsewhere).
 *
 * Calls:
 *   • GET /api/memberships/tour-bookings            (default = upcoming)
 *   • POST /api/memberships/tour-bookings/{id}/cancel
 *   • POST /api/memberships/tour-bookings/{id}/attended
 *   • POST /api/memberships/tour-bookings/{id}/no-show
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Calendar, Clock, MapPin, RefreshCw, Loader2, Check, X as XIcon, UserX } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

const fmtDateTime = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    weekday: 'short', day: 'numeric', month: 'short',
    hour: '2-digit', minute: '2-digit', hour12: false,
  });
};

const STATUS_STYLE = {
  booked: 'bg-blue-50 text-blue-700 border-blue-200',
  attended: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  cancelled: 'bg-zinc-100 text-zinc-500 border-zinc-200',
  no_show: 'bg-amber-50 text-amber-800 border-amber-200',
};

const UpcomingToursPanel = ({ compact = false }) => {
  const [bookings, setBookings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await axios.get(`${API}/memberships/tour-bookings`, { headers: authHeaders() });
      setBookings(r.data?.bookings || []);
    } catch (e) {
      setError(e.response?.data?.detail || "Couldn't load bookings.");
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const act = async (b, action) => {
    setBusyId(b.id);
    try {
      await axios.post(`${API}/memberships/tour-bookings/${b.id}/${action}`, {}, { headers: authHeaders() });
      load();
    } catch (e) {
      setError(e.response?.data?.detail || `Could not ${action} booking.`);
    }
    setBusyId(null);
  };

  const visible = compact ? bookings.slice(0, 5) : bookings;
  const upcomingCount = bookings.filter((b) => b.status === 'booked').length;

  return (
    <div className="rounded-xl border border-[color:var(--theme-border)] bg-[color:var(--theme-surface)] p-4" data-testid="upcoming-tours-panel">
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-[var(--color-brand-cyan)] flex items-center gap-1">
            <Calendar size={11} /> Upcoming tour bookings
          </p>
          <h3 className="text-base font-semibold mt-0.5" style={{ color: 'var(--theme-text)' }}>
            {upcomingCount} booked · {bookings.length} total
          </h3>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md border border-[color:var(--theme-border)] hover:bg-white/5"
          data-testid="upcoming-tours-refresh"
        >
          <RefreshCw size={11} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {loading ? (
        <p className="text-xs flex items-center gap-2 py-4" style={{ color: 'var(--theme-text-muted)' }}>
          <Loader2 size={12} className="animate-spin" /> Loading bookings…
        </p>
      ) : error ? (
        <p className="text-xs text-red-500" data-testid="upcoming-tours-error">{error}</p>
      ) : visible.length === 0 ? (
        <p className="text-xs italic py-3" style={{ color: 'var(--theme-text-muted)' }} data-testid="upcoming-tours-empty">
          No tour bookings yet. Once members book tours from your public sign-up page, they'll appear here.
        </p>
      ) : (
        <ul className="divide-y divide-[color:var(--theme-border)]" data-testid="upcoming-tours-list">
          {visible.map((b) => (
            <li key={b.id} className="py-2.5 flex flex-col sm:flex-row sm:items-center gap-2" data-testid={`tour-booking-${b.id}`}>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate" style={{ color: 'var(--theme-text)' }} data-testid={`tour-booking-name-${b.id}`}>
                  {b.member_name || b.member_email || 'Pending signup'}
                </p>
                <p className="text-[11px] flex items-center gap-1 flex-wrap" style={{ color: 'var(--theme-text-muted)' }}>
                  <Clock size={10} /> {fmtDateTime(b.slot_at)}
                  {b.location && (<> <span className="text-zinc-400">·</span> <MapPin size={10} /> {b.location}</>)}
                  <span className={`ml-1 inline-flex items-center px-1.5 py-0.5 rounded-full border text-[10px] uppercase tracking-wider ${STATUS_STYLE[b.status] || 'bg-zinc-50 text-zinc-500 border-zinc-200'}`}>
                    {b.status?.replace('_', ' ')}
                  </span>
                  {b.reminder_status === 'sent' && (
                    <span
                      className="ml-1 inline-flex items-center px-1.5 py-0.5 rounded-full border text-[10px] uppercase tracking-wider bg-violet-50 text-violet-700 border-violet-200"
                      title="24-hour reminder email sent"
                      data-testid={`tour-booking-reminder-${b.id}`}
                    >
                      Reminder sent
                    </span>
                  )}
                </p>
              </div>
              {b.status === 'booked' && (
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => act(b, 'attended')}
                    disabled={busyId === b.id}
                    className="text-xs px-2 py-1 rounded-md border border-emerald-200 text-emerald-700 hover:bg-emerald-50 disabled:opacity-50"
                    data-testid={`tour-booking-attended-${b.id}`}
                    title="Mark as attended"
                  >
                    <Check size={11} className="inline mr-0.5" /> Attended
                  </button>
                  <button
                    type="button"
                    onClick={() => act(b, 'no-show')}
                    disabled={busyId === b.id}
                    className="text-xs px-2 py-1 rounded-md border border-amber-200 text-amber-700 hover:bg-amber-50 disabled:opacity-50"
                    data-testid={`tour-booking-noshow-${b.id}`}
                    title="Mark as no-show"
                  >
                    <UserX size={11} className="inline mr-0.5" /> No-show
                  </button>
                  <button
                    type="button"
                    onClick={() => act(b, 'cancel')}
                    disabled={busyId === b.id}
                    className="text-xs px-2 py-1 rounded-md border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-50"
                    data-testid={`tour-booking-cancel-${b.id}`}
                    title="Cancel booking"
                  >
                    <XIcon size={11} className="inline mr-0.5" /> Cancel
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {compact && bookings.length > 5 && (
        <p className="text-[11px] mt-2 text-right" style={{ color: 'var(--theme-text-muted)' }}>
          Showing 5 of {bookings.length} — see all in Members → Tours.
        </p>
      )}
    </div>
  );
};

export default UpcomingToursPanel;
