/**
 * StaffNotificationBell — shared in-app bell for the Staff Portal (employee)
 * and the Staffing console (manager). Shows event pings + live nudges from a
 * feed endpoint, with an unread badge and a click-to-navigate dropdown.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Bell, AlertTriangle, CheckCircle2, X } from 'lucide-react';

const TONE = {
  missing_time: ['bg-amber-50', 'text-amber-700', AlertTriangle],
  rtw_unsigned: ['bg-amber-50', 'text-amber-700', AlertTriangle],
  pending_approvals: ['bg-amber-50', 'text-amber-700', AlertTriangle],
  vehicle_check_due: ['bg-amber-50', 'text-amber-700', AlertTriangle],
  vehicle_check_overdue: ['bg-rose-50', 'text-rose-700', AlertTriangle],
  vehicle_defect: ['bg-rose-50', 'text-rose-700', AlertTriangle],
  dbs_expiry: ['bg-amber-50', 'text-amber-700', AlertTriangle],
  dbs_expired: ['bg-rose-50', 'text-rose-700', AlertTriangle],
  holiday_request: ['bg-cyan-50', 'text-cyan-700', Bell],
  leave_decision: ['bg-emerald-50', 'text-emerald-700', CheckCircle2],
};

export default function StaffNotificationBell({ endpoint, readEndpoint, headers, onNavigate }) {
  const [data, setData] = useState({ notifications: [], nudges: [], unread: 0 });
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  const load = useCallback(async () => {
    try { const r = await axios.get(endpoint, { headers }); setData(r.data || { notifications: [], nudges: [], unread: 0 }); }
    catch { /* silent — bell is non-critical */ }
  }, [endpoint, headers]);

  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t); }, [load]);

  useEffect(() => {
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const toggle = async () => {
    const next = !open; setOpen(next);
    if (next && data.unread > 0) {
      try { await axios.post(readEndpoint, {}, { headers }); } catch { /* ignore */ }
      load();
    }
  };

  const go = (link) => {
    setOpen(false);
    if (link && onNavigate && !link.startsWith('/')) onNavigate(link);
  };

  const items = [
    ...(data.nudges || []).map((n) => ({ ...n, _nudge: true, id: `nudge-${n.type}` })),
    ...(data.notifications || []),
  ];

  return (
    <div className="relative" ref={ref}>
      <button onClick={toggle} data-testid="staff-notif-bell"
        className="relative inline-flex items-center justify-center h-9 w-9 rounded-lg border transition-colors hover:opacity-80"
        style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)', background: 'transparent' }}>
        <Bell size={16} />
        {data.unread > 0 && (
          <span data-testid="staff-notif-badge"
            className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 rounded-full bg-rose-500 text-white text-[10px] font-bold flex items-center justify-center">
            {data.unread > 9 ? '9+' : data.unread}
          </span>
        )}
      </button>

      {open && (
        <div data-testid="staff-notif-panel"
          className="fixed left-4 right-4 top-24 sm:absolute sm:left-auto sm:right-0 sm:top-auto sm:mt-2 sm:w-80 max-h-[70vh] overflow-y-auto rounded-2xl bg-white border border-slate-200 shadow-2xl z-[200]">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
            <span className="text-sm font-bold text-slate-900">Notifications</span>
            <button onClick={() => setOpen(false)} className="text-slate-400 hover:text-slate-600"><X size={16} /></button>
          </div>
          {items.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-slate-400" data-testid="staff-notif-empty">You're all caught up.</div>
          ) : (
            <div className="divide-y divide-slate-100">
              {items.map((n) => {
                const [bg, fg, Icon] = TONE[n.type] || ['bg-slate-50', 'text-slate-600', Bell];
                return (
                  <button key={n.id} onClick={() => go(n.link)} data-testid={`staff-notif-item-${n.type}`}
                    className={`w-full text-left px-4 py-3 flex items-start gap-3 hover:bg-slate-50 ${!n._nudge && !n.read ? 'bg-cyan-50/40' : ''}`}>
                    <span className={`mt-0.5 rounded-lg p-1.5 ${bg} ${fg}`}><Icon size={15} /></span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-semibold text-slate-800">{n.title}</span>
                      <span className="block text-xs text-slate-500 mt-0.5">{n.body}</span>
                      {n._nudge && <span className="inline-block mt-1 text-[10px] font-semibold uppercase tracking-wide text-amber-600">Reminder</span>}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
