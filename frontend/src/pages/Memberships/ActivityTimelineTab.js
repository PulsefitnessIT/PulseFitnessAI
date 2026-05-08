/**
 * Sprint C — Member Activity Timeline tab.
 *
 * Pulls GET /memberships/members/{id}/activity and renders a
 * reverse-chronological feed combining bookings, payments, invoices,
 * portal-invite events, membership changes, and the original join.
 *
 * Designed to be cheap to scan: icon + title + 1-line subtitle + relative
 * timestamp. Empty / loading / error states use the same surface the
 * other drawer tabs use so the drawer feels unified.
 */
import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  Loader2, CalendarDays, CreditCard, FileText, Mail, Tag as TagIcon,
  UserPlus, AlertTriangle, CheckCircle2, XCircle, Pause, Activity,
} from 'lucide-react';

const KIND_META = {
  booking:        { icon: CalendarDays,  colour: 'text-sky-500',     ring: 'bg-sky-500/10' },
  payment:        { icon: CreditCard,    colour: 'text-emerald-500', ring: 'bg-emerald-500/10' },
  invoice:        { icon: FileText,      colour: 'text-amber-500',   ring: 'bg-amber-500/10' },
  portal_invited: { icon: Mail,          colour: 'text-indigo-500',  ring: 'bg-indigo-500/10' },
  reminder_sent:  { icon: Mail,          colour: 'text-indigo-400',  ring: 'bg-indigo-400/10' },
  tag_added:      { icon: TagIcon,       colour: 'text-fuchsia-500', ring: 'bg-fuchsia-500/10' },
  membership:     { icon: Activity,      colour: 'text-cyan-500',    ring: 'bg-cyan-500/10' },
  joined:         { icon: UserPlus,      colour: 'text-emerald-600', ring: 'bg-emerald-600/10' },
};

function relativeTime(iso) {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const diff = Math.floor((Date.now() - then) / 1000);
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return new Date(iso).toLocaleDateString();
}

function formatGBP(pence) {
  if (pence == null) return '';
  return `£${(Number(pence) / 100).toFixed(2)}`;
}

function StatusBadge({ kind, status }) {
  if (!status) return null;
  const palette = {
    attended:   'bg-emerald-500/15 text-emerald-600',
    paid:       'bg-emerald-500/15 text-emerald-600',
    succeeded:  'bg-emerald-500/15 text-emerald-600',
    booked:     'bg-sky-500/15 text-sky-600',
    issued:     'bg-amber-500/15 text-amber-600',
    overdue:    'bg-rose-500/15 text-rose-600',
    no_show:    'bg-rose-500/15 text-rose-600',
    cancelled:  'bg-[color:var(--theme-text-muted)]/15 text-[color:var(--theme-text-muted)]',
    refunded:   'bg-amber-500/15 text-amber-600',
  };
  const cls = palette[status] || 'bg-white/10 text-[color:var(--theme-text-muted)]';
  return (
    <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${cls}`}>
      {status.replace('_', ' ')}
    </span>
  );
}

export default function ActivityTimelineTab({ memberId, API, headers }) {
  const [events, setEvents] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(
        `${API}/memberships/members/${memberId}/activity`, { headers }
      );
      setEvents(data.events || []);
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to load activity');
    }
  }, [API, headers, memberId]);

  useEffect(() => { load(); }, [load]);

  if (error) {
    return (
      <div className="rounded-lg border border-rose-500/30 bg-rose-500/5 p-4 text-sm text-rose-500 inline-flex items-center gap-2" data-testid="activity-tab-error">
        <AlertTriangle size={14} /> {error}
      </div>
    );
  }

  if (!events) {
    return (
      <div className="flex items-center gap-2 text-[color:var(--theme-text-muted)] text-sm" data-testid="activity-tab-loading">
        <Loader2 size={14} className="animate-spin" /> Loading timeline…
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <div className="rounded-lg border border-[color:var(--theme-border)] p-6 text-center text-sm text-[color:var(--theme-text-muted)]" data-testid="activity-tab-empty">
        No activity logged yet.
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid="activity-tab">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-bold text-[color:var(--theme-text)] inline-flex items-center gap-2">
          <Activity size={14} /> Member activity
        </h4>
        <span className="text-[10px] text-[color:var(--theme-text-muted)] font-bold uppercase tracking-wider">
          {events.length} event{events.length === 1 ? '' : 's'}
        </span>
      </div>

      <ol className="relative space-y-0" data-testid="activity-tab-list">
        {events.map((ev, idx) => {
          const meta = KIND_META[ev.kind] || { icon: Activity, colour: 'text-[color:var(--color-brand-cyan)]', ring: 'bg-white/5' };
          const Icon = meta.icon;
          const last = idx === events.length - 1;
          return (
            <li key={ev.id || `${ev.kind}-${idx}`} className="relative pl-8 pb-4" data-testid={`activity-item-${ev.kind}`}>
              {/* spine */}
              {!last && (
                <span
                  aria-hidden
                  className="absolute left-[11px] top-6 bottom-0 w-px bg-[color:var(--theme-border)]"
                />
              )}
              {/* dot */}
              <span className={`absolute left-0 top-1 h-6 w-6 rounded-full ${meta.ring} flex items-center justify-center`}>
                <Icon size={11} className={meta.colour} />
              </span>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-bold text-[color:var(--theme-text)] truncate inline-flex items-center gap-2 flex-wrap">
                    {ev.title}
                    <StatusBadge kind={ev.kind} status={ev.status} />
                  </p>
                  {ev.subtitle && (
                    <p className="text-[11px] text-[color:var(--theme-text-muted)] truncate">{ev.subtitle}</p>
                  )}
                  {ev.amount_pence != null && (
                    <p className="text-[11px] font-bold tabular-nums text-[color:var(--theme-text)] mt-0.5">
                      {formatGBP(ev.amount_pence)}
                    </p>
                  )}
                </div>
                <span className="shrink-0 text-[10px] text-[color:var(--theme-text-muted)] tabular-nums">
                  {relativeTime(ev.at)}
                </span>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
