import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Bell, ShieldAlert, Loader2, CheckCheck, ShieldCheck } from 'lucide-react';

/**
 * Master Admin header alert bell. Shows a live unread count of critical/abuse
 * security alerts (short-polled by the parent) and, on click, a dropdown of
 * the most recent unread alerts with "Mark all read" + jump-to-Security-Centre.
 */
function fmtWhen(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString('en-GB', {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
    });
  } catch { return ''; }
}

export default function AlertBell({ API, headers, count = 0, onViewCentre, onChanged }) {
  const [open, setOpen] = useState(false);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [marking, setMarking] = useState(false);
  const ref = useRef(null);

  const fetchList = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/master-admin/security-centre/alerts`, {
        headers, params: { limit: 15 },
      });
      setAlerts(r.data?.alerts || []);
    } catch { /* transient */ } finally { setLoading(false); }
  };

  useEffect(() => {
    if (open) fetchList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey); };
  }, [open]);

  const markAllRead = async () => {
    setMarking(true);
    try {
      await axios.post(`${API}/master-admin/security-centre/alerts/ack`, {}, { headers });
      setAlerts([]);
      onChanged?.();
    } catch { /* best-effort */ } finally { setMarking(false); }
  };

  const badge = count > 99 ? '99+' : String(count);

  return (
    <div className="relative flex-shrink-0" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="relative p-2 rounded-lg text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100 transition-colors"
        aria-label={`Security alerts${count ? ` (${count} unread)` : ''}`}
        data-testid="alert-bell-btn"
      >
        <Bell size={18} className={count > 0 ? 'text-red-600' : ''} />
        {count > 0 && (
          <span
            className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 flex items-center justify-center rounded-full bg-red-600 text-white text-[10px] font-bold leading-none animate-in zoom-in-50"
            data-testid="alert-bell-badge"
          >
            {badge}
          </span>
        )}
      </button>

      {open && (
        <div
          className="absolute right-0 mt-2 w-[360px] max-w-[calc(100vw-2rem)] rounded-xl border border-zinc-200 bg-white shadow-2xl z-[9999] overflow-hidden"
          data-testid="alert-bell-dropdown"
        >
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-zinc-100">
            <div className="flex items-center gap-2">
              <ShieldAlert size={15} className="text-red-500" />
              <span className="text-sm font-semibold text-zinc-900">Security alerts</span>
              {count > 0 && (
                <span className="rounded-full bg-red-100 text-red-700 px-1.5 py-0.5 text-[10px] font-bold">{badge}</span>
              )}
            </div>
            {alerts.length > 0 && (
              <button
                onClick={markAllRead}
                disabled={marking}
                className="inline-flex items-center gap-1 text-xs font-medium text-zinc-500 hover:text-zinc-900 disabled:opacity-50"
                data-testid="alert-bell-mark-read"
              >
                {marking ? <Loader2 size={12} className="animate-spin" /> : <CheckCheck size={13} />}
                Mark all read
              </button>
            )}
          </div>

          <div className="max-h-[340px] overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center gap-2 py-10 text-zinc-400 text-sm">
                <Loader2 size={16} className="animate-spin" /> Loading…
              </div>
            ) : alerts.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-10 text-zinc-400" data-testid="alert-bell-empty">
                <ShieldCheck size={26} className="text-emerald-400" />
                <p className="text-sm">No unread security alerts.</p>
              </div>
            ) : (
              <ul className="divide-y divide-zinc-100" data-testid="alert-bell-list">
                {alerts.map((a) => {
                  const critical = a.severity === 'critical';
                  return (
                    <li key={a.id} data-testid={`alert-bell-item-${a.id}`}>
                      <button
                        onClick={() => { setOpen(false); onViewCentre?.(); }}
                        className="w-full text-left px-4 py-3 hover:bg-zinc-50 transition-colors"
                      >
                        <div className="flex items-center gap-2">
                          <span className={`h-2 w-2 rounded-full flex-shrink-0 ${critical ? 'bg-red-500' : 'bg-amber-500'}`} />
                          <span className="text-sm font-medium text-zinc-900 truncate">{a.title}</span>
                          <span className="ml-auto text-[11px] text-zinc-400 whitespace-nowrap">{fmtWhen(a.created_at)}</span>
                        </div>
                        <p className="mt-0.5 pl-4 text-xs text-zinc-500 truncate">
                          {a.actor}{a.detail ? ` — ${a.detail}` : ''}
                        </p>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <div className="border-t border-zinc-100 px-4 py-2">
            <button
              onClick={() => { setOpen(false); onViewCentre?.(); }}
              className="w-full text-center text-xs font-semibold text-[var(--color-brand-blue,#2563eb)] hover:underline"
              data-testid="alert-bell-view-centre"
            >
              Open Security Alert Centre →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
