/**
 * Phase S2 — Staff "My Clock" tab.
 *
 * Self-service punch widget for the staff role inside StaffingConsole.
 * Shows current state, today's scheduled shift, big primary action
 * button (Clock In / Clock Out / Break / End Break), recent history,
 * and a small dispute link on this week's timesheet.
 *
 * Captures GPS at punch time via navigator.geolocation; fails open if
 * the user denies — the backend will accept the punch but skip the
 * geofence check. Hard rejects only happen if the operator is more
 * than 5km from the configured site centre.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  Play, Square, Coffee, Loader2, AlertTriangle, Clock, MapPin, History as HistIcon,
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STATE_LABEL = {
  off: 'Off the clock',
  on_shift: 'On shift',
  on_break: 'On break',
};
const STATE_TINT = {
  off: '#94A3B8',
  on_shift: '#10B981',
  on_break: '#F59E0B',
};

function formatTime(iso) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
  catch { return iso; }
}

function getGeo() {
  // Promise wrapper around navigator.geolocation. Resolves to null on denial / unsupported.
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({
        gps_lat: pos.coords.latitude,
        gps_lng: pos.coords.longitude,
        accuracy_m: pos.coords.accuracy,
      }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: 5000, maximumAge: 30000 },
    );
  });
}

export default function MyClockTab({ headers }) {
  const [status, setStatus] = useState(null);
  const [history, setHistory] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, h] = await Promise.all([
        axios.get(`${API}/staffing/clock/status`, { headers }),
        axios.get(`${API}/staffing/clock/history`, { headers, params: { days: 7 } }),
      ]);
      setStatus(s.data);
      setHistory(h.data.events || []);
    } catch { /* noop */ }
  }, [headers]);

  useEffect(() => { load(); }, [load]);

  if (!status) {
    return <div className="py-8 text-xs inline-flex items-center gap-2" style={{ color: 'var(--theme-text-muted)' }}>
      <Loader2 size={14} className="animate-spin" /> Loading clock…
    </div>;
  }
  if (!status.linked) {
    return (
      <div className="rounded-xl border p-6 text-center" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="my-clock-unlinked">
        <Clock size={20} className="mx-auto mb-2" style={{ color: 'var(--theme-text-muted)' }} />
        <p className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>Account not linked to a staff record</p>
        <p className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>
          Ask a manager to add you to the staff list — your account email needs to match.
        </p>
      </div>
    );
  }

  const state = status.state || 'off';
  const tint = STATE_TINT[state];

  const punch = async (kind) => {
    setBusy(true);
    try {
      const geo = await getGeo();
      const body = {
        kind,
        shift_id: status.todays_shift?.id || null,
        site_id: status.todays_shift?.site_id || null,
        ...(geo || {}),
      };
      const { data } = await axios.post(`${API}/staffing/clock/punch`, body, { headers });
      if (data.geo_warning) {
        window.alert(`Punch recorded · note: ${data.geo_warning}`);
      }
      load();
    } catch (e) {
      window.alert(e.response?.data?.detail || 'Punch failed');
    }
    setBusy(false);
  };

  const primary = (() => {
    if (state === 'off') return { label: 'Clock In', kind: 'clock_in', icon: Play, bg: '#10B981' };
    if (state === 'on_shift') return { label: 'Clock Out', kind: 'clock_out', icon: Square, bg: '#EF4444' };
    if (state === 'on_break') return { label: 'End Break', kind: 'break_end', icon: Play, bg: '#10B981' };
    return null;
  })();
  const secondary = state === 'on_shift'
    ? { label: 'Start Break', kind: 'break_start', icon: Coffee, bg: '#F59E0B' }
    : null;

  return (
    <div className="space-y-4 max-w-2xl" data-testid="my-clock-tab">
      <div className="rounded-xl border p-5 space-y-4" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <p className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: tint }}>Current state</p>
            <p className="text-2xl font-bold pulse-font-heading" style={{ color: 'var(--theme-text)' }}>{STATE_LABEL[state]}</p>
            {status.last_event?.occurred_at && (
              <p className="text-xs mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>
                Since {formatTime(status.last_event.occurred_at)}
                {status.last_event.source === 'kiosk' && ' · via kiosk'}
                {status.last_event.geo_warning && (
                  <span className="ml-1 inline-flex items-center gap-1 text-amber-500">
                    · <AlertTriangle size={10} /> {status.last_event.geo_warning}
                  </span>
                )}
              </p>
            )}
          </div>
          <span className="w-3 h-3 rounded-full shrink-0" style={{ background: tint }} />
        </div>
        {status.todays_shift ? (
          <div className="rounded-lg border p-3" style={{ borderColor: 'var(--theme-border)' }}>
            <p className="text-[10px] uppercase tracking-[0.14em] font-bold" style={{ color: 'var(--color-brand-cyan)' }}>Today's shift</p>
            <p className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>
              {status.todays_shift.start_time}–{status.todays_shift.end_time} · {status.todays_shift.role}
            </p>
            {status.todays_shift.notes && (
              <p className="text-[11px] mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>{status.todays_shift.notes}</p>
            )}
          </div>
        ) : (
          <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>No scheduled shift today.</p>
        )}
        <div className="flex gap-2 flex-wrap">
          {primary && (
            <button
              type="button"
              onClick={() => punch(primary.kind)}
              disabled={busy}
              className="h-12 px-6 rounded-full text-sm font-bold inline-flex items-center gap-2 disabled:opacity-50 transition-transform active:scale-95"
              style={{ background: primary.bg, color: '#001219' }}
              data-testid={`my-clock-${primary.kind}`}
            >
              {busy ? <Loader2 size={16} className="animate-spin" /> : <primary.icon size={16} />}
              {primary.label}
            </button>
          )}
          {secondary && (
            <button
              type="button"
              onClick={() => punch(secondary.kind)}
              disabled={busy}
              className="h-12 px-5 rounded-full text-sm font-bold inline-flex items-center gap-2 disabled:opacity-50 border"
              style={{ borderColor: secondary.bg, color: secondary.bg, background: 'transparent' }}
              data-testid={`my-clock-${secondary.kind}`}
            >
              <secondary.icon size={14} /> {secondary.label}
            </button>
          )}
        </div>
        <p className="text-[10px] inline-flex items-center gap-1" style={{ color: 'var(--theme-text-muted)' }}>
          <MapPin size={10} /> Location is captured at punch time and used for geofence audit only.
        </p>
      </div>

      <div className="rounded-xl border p-4" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
        <p className="text-[10px] uppercase tracking-[0.14em] font-bold mb-2 inline-flex items-center gap-1" style={{ color: 'var(--color-brand-cyan)' }}>
          <HistIcon size={11} /> Recent (last 7 days)
        </p>
        {history.length === 0 ? (
          <p className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>No punches yet.</p>
        ) : (
          <ul className="space-y-1" data-testid="my-clock-history">
            {history.slice(0, 20).map((e) => (
              <li key={e.id} className="flex items-center justify-between gap-2 text-xs" data-testid={`history-${e.id}`}>
                <span className="inline-flex items-center gap-2 min-w-0">
                  <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded shrink-0"
                    style={{
                      background: e.kind === 'clock_in' ? 'rgba(16,185,129,0.15)'
                        : e.kind === 'clock_out' ? 'rgba(239,68,68,0.15)'
                        : 'rgba(245,158,11,0.15)',
                      color: e.kind === 'clock_in' ? '#10B981'
                        : e.kind === 'clock_out' ? '#EF4444'
                        : '#F59E0B',
                    }}>
                    {e.kind.replace('_', ' ')}
                  </span>
                  <span className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>
                    {e.source === 'kiosk' ? 'Kiosk' : e.source === 'manual' ? 'Manual' : 'Mobile'}
                  </span>
                </span>
                <span className="tabular-nums text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>
                  {new Date(e.occurred_at).toLocaleString([], { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
