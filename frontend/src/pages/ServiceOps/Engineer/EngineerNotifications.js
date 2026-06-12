/**
 * EngineerNotifications — iter 216h142 (Phase 4 / Slice 2).
 *
 * In-app notification centre for field engineers.
 *  • Lists notifications (latest first) with read/unread filter.
 *  • Mark single + mark-all-as-read.
 *  • Delete individual notifications.
 *  • Subscribe to Web Push (button asks for OS permission, registers
 *    service worker, posts subscription to backend).
 *
 * Backend:
 *   GET    /api/svc/engineer/notifications[?unread=true]
 *   GET    /api/svc/engineer/notifications/unread-count
 *   POST   /api/svc/engineer/notifications/{id}/read
 *   POST   /api/svc/engineer/notifications/read-all
 *   DELETE /api/svc/engineer/notifications/{id}
 *   GET    /api/svc/engineer/push/vapid-key
 *   POST   /api/svc/engineer/push/subscribe
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  Bell, BellOff, ChevronLeft, CheckCheck, Wrench, Calendar, Trash2,
  Loader2, RefreshCw, AlertTriangle, ShieldCheck, Inbox,
  Settings, MoonStar, Clock,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const KIND_META = {
  job_assigned:     { icon: Wrench,         color: 'bg-blue-100 text-blue-700' },
  job_rescheduled:  { icon: Calendar,       color: 'bg-amber-100 text-amber-700' },
  job_unassigned:   { icon: AlertTriangle,  color: 'bg-slate-200 text-slate-700' },
  job_due_soon:     { icon: Calendar,       color: 'bg-purple-100 text-purple-700' },
  ppm_due:          { icon: ShieldCheck,    color: 'bg-emerald-100 text-emerald-700' },
  test:             { icon: Bell,           color: 'bg-pink-100 text-pink-700' },
  default:          { icon: Bell,           color: 'bg-slate-100 text-slate-700' },
};

const fmtRelative = (iso) => {
  if (!iso) return '';
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  const hours = Math.floor(mins / 60);
  const days = Math.floor(hours / 24);
  if (mins < 1) return 'now';
  if (mins < 60) return `${mins}m`;
  if (hours < 24) return `${hours}h`;
  if (days < 7) return `${days}d`;
  return new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
};

// urlBase64 → Uint8Array helper for the Push subscription API.
const urlBase64ToUint8Array = (base64String) => {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  const output = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) output[i] = rawData.charCodeAt(i);
  return output;
};

// ── Push subscribe button ────────────────────────────────────
const PushSubscribeButton = () => {
  const [permission, setPermission] = useState(
    typeof Notification !== 'undefined' ? Notification.permission : 'default',
  );
  const [busy, setBusy] = useState(false);
  const supported =
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window;

  const subscribe = useCallback(async () => {
    if (!supported) return;
    setBusy(true);
    try {
      const perm = await Notification.requestPermission();
      setPermission(perm);
      if (perm !== 'granted') {
        notify.error('Notifications blocked', 'Enable them in your browser settings to receive job alerts.');
        return;
      }
      const reg = await navigator.serviceWorker.register('/sw.js');
      await navigator.serviceWorker.ready;
      const keyRes = await axios.get(`${API}/svc/engineer/push/vapid-key`, auth());
      const applicationServerKey = urlBase64ToUint8Array(keyRes.data.public_key);
      let sub = await reg.pushManager.getSubscription();
      if (!sub) {
        sub = await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey,
        });
      }
      await axios.post(
        `${API}/svc/engineer/push/subscribe`,
        { subscription: sub.toJSON(), user_agent: navigator.userAgent },
        auth(),
      );
      notify.success('Push notifications enabled');
    } catch (e) {
      notify.error('Subscribe failed', e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }, [supported]);

  const sendTest = useCallback(async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/svc/engineer/push/test`, {}, auth());
      notify.success('Test notification sent', 'It will also appear in this list.');
    } catch (e) {
      notify.error('Test failed', e?.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  }, []);

  if (!supported) {
    return (
      <div
        className="flex items-center gap-2 text-xs text-slate-500"
        data-testid="push-unsupported"
      >
        <BellOff size={14} /> Push not supported on this browser.
      </div>
    );
  }

  if (permission === 'granted') {
    return (
      <button
        type="button"
        onClick={sendTest}
        disabled={busy}
        className="flex items-center gap-2 px-3 py-2 rounded-lg border border-emerald-200 bg-emerald-50 text-emerald-700 text-xs font-semibold hover:bg-emerald-100"
        data-testid="push-test"
      >
        {busy ? <Loader2 size={12} className="animate-spin" /> : <Bell size={12} />}
        Send test push
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={subscribe}
      disabled={busy}
      className="flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold"
      data-testid="push-subscribe"
    >
      {busy ? <Loader2 size={12} className="animate-spin" /> : <Bell size={12} />}
      Enable push notifications
    </button>
  );
};

// ── Single row ──────────────────────────────────────────────
const Row = ({ n, onOpen, onRead, onDelete }) => {
  const meta = KIND_META[n.kind] || KIND_META.default;
  const Icon = meta.icon;
  const unread = !n.read_at;
  return (
    <li
      className={`relative px-3 py-3 flex items-start gap-3 ${
        unread ? 'bg-blue-50/50' : 'bg-white'
      }`}
      data-testid={`notif-row-${n.id}`}
    >
      <span className={`w-9 h-9 rounded-xl ${meta.color} flex items-center justify-center flex-shrink-0`}>
        <Icon size={16} />
      </span>
      <button
        type="button"
        onClick={() => onOpen(n)}
        className="flex-1 text-left min-w-0"
        data-testid={`notif-open-${n.id}`}
      >
        <div className="flex items-center gap-2 mb-0.5">
          {unread ? <span className="w-1.5 h-1.5 rounded-full bg-blue-600 flex-shrink-0" /> : null}
          <p className={`text-sm truncate ${unread ? 'font-bold text-slate-900' : 'font-semibold text-slate-700'}`}>
            {n.title}
          </p>
          <span className="text-[10px] text-slate-400 tabular-nums flex-shrink-0 ml-auto">
            {fmtRelative(n.created_at)}
          </span>
        </div>
        {n.body ? (
          <p className="text-xs text-slate-500 truncate">{n.body}</p>
        ) : null}
      </button>
      <div className="flex items-center gap-1 flex-shrink-0">
        {unread ? (
          <button
            type="button"
            onClick={() => onRead(n)}
            className="text-slate-400 hover:text-emerald-600 p-1"
            title="Mark as read"
            data-testid={`notif-mark-read-${n.id}`}
          >
            <CheckCheck size={14} />
          </button>
        ) : null}
        <button
          type="button"
          onClick={() => onDelete(n)}
          className="text-slate-400 hover:text-red-600 p-1"
          title="Delete"
          data-testid={`notif-delete-${n.id}`}
        >
          <Trash2 size={14} />
        </button>
      </div>
    </li>
  );
};

// ── Notification prefs panel · Iter 216h156 ─────────────────
//
// Per-engineer push prefs: quiet hours, per-kind opt-out, snooze.
// Surfaced inline above the list so engineers find it next to the
// alerts that are bothering them.

const KIND_LABELS = {
  job_assigned:     'New job assigned',
  job_rescheduled:  'Job rescheduled',
  job_request:      'Inbox: new request',
  job_self_claimed: 'Self-claim confirmations',
  appointment:      'Appointment reminders',
  attachment:       'New attachment',
  note:             'Case notes',
  parts_approved:   'Parts approved',
  parts_rejected:   'Parts rejected',
  ppm_due:          'PPM due',
  sla_warning:      'SLA at-risk',
  test:             'Test notification',
};

const NotificationPrefsPanel = ({ open, onClose }) => {
  const [data, setData] = useState(null);
  const [savingKind, setSavingKind] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/svc/engineer/notification-prefs`, auth());
      setData(r.data);
    } catch (e) {
      notify.error('Failed to load prefs', e?.response?.data?.detail || e.message);
    }
  }, []);

  useEffect(() => { if (open) load(); }, [open, load]);

  if (!open) return null;
  if (!data) {
    return (
      <div className="bg-white border border-slate-200 rounded-2xl p-4 text-center text-xs text-slate-500"
           data-testid="notif-prefs-panel">
        <Loader2 size={16} className="animate-spin mx-auto" />
      </div>
    );
  }

  const { prefs, kinds, currently_in_dnd, currently_in_quiet_hours } = data;

  const saveQuiet = async (next) => {
    setSaving(true);
    try {
      const r = await axios.put(
        `${API}/svc/engineer/notification-prefs`,
        next, auth(),
      );
      setData((d) => ({ ...d, prefs: r.data.prefs }));
    } catch (e) {
      notify.error('Save failed', e?.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  const toggleKind = async (kind) => {
    const current = prefs.kind_prefs?.[kind];
    const nextVal = current === false ? true : false; // missing == enabled
    setSavingKind(kind);
    try {
      const r = await axios.put(
        `${API}/svc/engineer/notification-prefs`,
        { kind_prefs: { ...(prefs.kind_prefs || {}), [kind]: nextVal } },
        auth(),
      );
      setData((d) => ({ ...d, prefs: r.data.prefs }));
    } catch (e) {
      notify.error('Save failed', e?.response?.data?.detail || e.message);
    } finally {
      setSavingKind(null);
    }
  };

  const snooze = async (minutes) => {
    try {
      await axios.post(`${API}/svc/engineer/notification-prefs/snooze`,
                       { minutes }, auth());
      await load();
    } catch (e) {
      notify.error('Snooze failed', e?.response?.data?.detail || e.message);
    }
  };

  const clearSnooze = async () => {
    try {
      await axios.delete(`${API}/svc/engineer/notification-prefs/snooze`, auth());
      await load();
    } catch (e) {
      notify.error('Clear failed', e?.response?.data?.detail || e.message);
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-4 space-y-4"
         data-testid="notif-prefs-panel">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <Settings size={14} /> Notification preferences
          </p>
          <p className="text-xs text-slate-500">
            In-app alerts always land. These switches gate the disruptive
            phone-buzz push only.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-slate-400 hover:text-slate-700 text-xs"
          data-testid="notif-prefs-close"
        >
          Done
        </button>
      </div>

      {/* Snooze row */}
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 space-y-2">
        <p className="text-xs font-bold text-slate-700 flex items-center gap-1.5">
          <MoonStar size={12} /> Do Not Disturb
        </p>
        {currently_in_dnd ? (
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs text-amber-700">
              Snoozed until {new Date(prefs.dnd_until).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
            </p>
            <button
              type="button"
              onClick={clearSnooze}
              className="text-xs font-semibold text-blue-600 hover:underline"
              data-testid="notif-prefs-clear-snooze"
            >
              Clear
            </button>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {[
              { label: '30 min', m: 30 },
              { label: '1 hr',   m: 60 },
              { label: '4 hr',   m: 240 },
              { label: 'Till end of day', m: 480 },
            ].map((opt) => (
              <button
                key={opt.m}
                type="button"
                onClick={() => snooze(opt.m)}
                className="text-xs font-semibold px-2.5 py-1 rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-100"
                data-testid={`notif-prefs-snooze-${opt.m}`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Quiet hours */}
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 space-y-2">
        <p className="text-xs font-bold text-slate-700 flex items-center gap-1.5">
          <Clock size={12} /> Quiet hours
          {currently_in_quiet_hours ? (
            <span className="ml-1 text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">
              Active now
            </span>
          ) : null}
        </p>
        <div className="flex items-center gap-2 flex-wrap">
          <label className="text-xs text-slate-500">Start</label>
          <input
            type="time"
            value={prefs.quiet_hours_start || ''}
            onChange={(e) => saveQuiet({ quiet_hours_start: e.target.value })}
            disabled={saving}
            className="text-xs px-2 py-1 border border-slate-300 rounded font-mono"
            data-testid="notif-prefs-quiet-start"
          />
          <label className="text-xs text-slate-500">End</label>
          <input
            type="time"
            value={prefs.quiet_hours_end || ''}
            onChange={(e) => saveQuiet({ quiet_hours_end: e.target.value })}
            disabled={saving}
            className="text-xs px-2 py-1 border border-slate-300 rounded font-mono"
            data-testid="notif-prefs-quiet-end"
          />
          {(prefs.quiet_hours_start || prefs.quiet_hours_end) ? (
            <button
              type="button"
              onClick={() => saveQuiet({ quiet_hours_start: '', quiet_hours_end: '' })}
              className="text-xs text-slate-500 hover:underline"
              data-testid="notif-prefs-quiet-clear"
            >
              Clear
            </button>
          ) : null}
        </div>
        <p className="text-[10px] text-slate-400">
          Crosses midnight automatically — e.g. 22:00 → 07:00 silences overnight.
        </p>
      </div>

      {/* Per-kind toggles */}
      <div className="space-y-1">
        <p className="text-xs font-bold text-slate-700">Per-alert push toggles</p>
        <ul className="divide-y divide-slate-100 border border-slate-200 rounded-xl overflow-hidden">
          {kinds.map((k) => {
            const enabled = prefs.kind_prefs?.[k] !== false;
            const busy = savingKind === k;
            return (
              <li key={k} className="flex items-center justify-between px-3 py-2">
                <span className="text-xs text-slate-700">{KIND_LABELS[k] || k}</span>
                <button
                  type="button"
                  onClick={() => toggleKind(k)}
                  disabled={busy}
                  className={`relative inline-flex h-5 w-9 rounded-full transition ${
                    enabled ? 'bg-emerald-500' : 'bg-slate-300'
                  }`}
                  data-testid={`notif-prefs-toggle-${k}`}
                >
                  <span className={`absolute top-0.5 ${enabled ? 'left-[18px]' : 'left-0.5'} h-4 w-4 rounded-full bg-white transition shadow`} />
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
};

// ── Main page ──────────────────────────────────────────────
export default function EngineerNotifications() {
  const orgBrand = useEngineerOrgBrand();
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all'); // 'all' | 'unread'
  const [prefsOpen, setPrefsOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(
        `${API}/svc/engineer/notifications${filter === 'unread' ? '?unread=true' : ''}`,
        auth(),
      );
      setItems(r.data?.notifications || []);
    } catch (e) {
      notify.error('Failed to load', e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const unreadCount = useMemo(
    () => items.filter((n) => !n.read_at).length, [items],
  );

  const onOpen = useCallback(async (n) => {
    if (!n.read_at) {
      try { await axios.post(`${API}/svc/engineer/notifications/${n.id}/read`, {}, auth()); }
      catch (e) { /* swallow */ }
    }
    if (n.link) navigate(n.link);
  }, [navigate]);

  const onRead = useCallback(async (n) => {
    try {
      await axios.post(`${API}/svc/engineer/notifications/${n.id}/read`, {}, auth());
      setItems((xs) => xs.map((x) => (x.id === n.id ? { ...x, read_at: new Date().toISOString() } : x)));
    } catch (e) {
      notify.error('Mark read failed', e?.response?.data?.detail || e.message);
    }
  }, []);

  const onDelete = useCallback(async (n) => {
    try {
      await axios.delete(`${API}/svc/engineer/notifications/${n.id}`, auth());
      setItems((xs) => xs.filter((x) => x.id !== n.id));
    } catch (e) {
      notify.error('Delete failed', e?.response?.data?.detail || e.message);
    }
  }, []);

  const onReadAll = useCallback(async () => {
    try {
      await axios.post(`${API}/svc/engineer/notifications/read-all`, {}, auth());
      setItems((xs) => xs.map((x) => ({ ...x, read_at: x.read_at || new Date().toISOString() })));
      notify.success('All caught up');
    } catch (e) {
      notify.error('Mark all read failed', e?.response?.data?.detail || e.message);
    }
  }, []);

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-notifications">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              onClick={() => navigate('/svc/engineer')}
              className="text-slate-500 hover:text-slate-900"
              data-testid="notif-back"
              aria-label="Back"
            >
              <ChevronLeft size={22} />
            </button>
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-blue-700">
                {orgBrand.label}
              </p>
              <h1 className="text-xl font-extrabold text-slate-900 flex items-center gap-2">
                <Bell size={20} /> Notifications
                {unreadCount ? (
                  <span className="bg-red-500 text-white text-[10px] font-bold rounded-full px-1.5 min-w-[20px] text-center">
                    {unreadCount}
                  </span>
                ) : null}
              </h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPrefsOpen((v) => !v)}
              className={`p-2 rounded-lg ${prefsOpen ? 'bg-blue-50 text-blue-700' : 'hover:bg-slate-100 text-slate-500'}`}
              data-testid="notif-prefs-toggle"
              aria-label="Preferences"
              title="Notification preferences"
            >
              <Settings size={18} />
            </button>
            <button
              type="button"
              onClick={load}
              className="p-2 rounded-lg hover:bg-slate-100 text-slate-500"
              data-testid="notif-refresh"
              aria-label="Refresh"
            >
              {loading ? <Loader2 size={18} className="animate-spin" /> : <RefreshCw size={18} />}
            </button>
            {unreadCount > 0 ? (
              <button
                type="button"
                onClick={onReadAll}
                className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold px-3 py-2 rounded-lg"
                data-testid="notif-mark-all-read"
              >
                <CheckCheck size={14} /> Mark all read
              </button>
            ) : null}
          </div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-4 space-y-3">
        {/* Iter 216h156 — collapsible prefs panel (quiet hours / kinds / snooze). */}
        <NotificationPrefsPanel open={prefsOpen} onClose={() => setPrefsOpen(false)} />

        {/* Push subscribe panel */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-bold text-slate-900">Browser notifications</p>
            <p className="text-xs text-slate-500">
              Get instant alerts when a job is assigned or rescheduled — even when this tab is closed.
            </p>
          </div>
          <PushSubscribeButton />
        </div>

        {/* Filter chips */}
        <div className="bg-white border border-slate-200 rounded-2xl px-3 py-2 flex items-center gap-2">
          {[
            { k: 'all',    label: 'All' },
            { k: 'unread', label: `Unread${unreadCount ? ` · ${unreadCount}` : ''}` },
          ].map((opt) => (
            <button
              key={opt.k}
              type="button"
              onClick={() => setFilter(opt.k)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${
                filter === opt.k
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
              data-testid={`notif-filter-${opt.k}`}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* List */}
        {!loading && items.length === 0 ? (
          <div
            className="bg-white border border-dashed border-slate-300 rounded-2xl p-10 text-center"
            data-testid="notif-empty"
          >
            <Inbox size={28} className="mx-auto text-slate-300 mb-2" />
            <p className="text-sm font-semibold text-slate-700">You're all caught up</p>
            <p className="text-xs text-slate-500 mt-1">
              When a dispatcher assigns or reschedules a job we'll let you know here.
            </p>
          </div>
        ) : (
          <ul className="bg-white border border-slate-200 rounded-2xl divide-y divide-slate-100 overflow-hidden">
            {items.map((n) => (
              <Row
                key={n.id}
                n={n}
                onOpen={onOpen}
                onRead={onRead}
                onDelete={onDelete}
              />
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}

