import { useEffect, useState, useCallback, useMemo } from 'react';
import axios from 'axios';
import {
  Phone, Mail, Calendar, CheckCircle, FileText, Activity,
  DollarSign, AlertOctagon, Award, ChevronDown, ChevronRight,
  Loader2,
} from 'lucide-react';

/**
 * <TimelinePanel/> — unified chronological feed for a single CRM
 * entity (Iter 220bu/220bv).
 *
 * Consumes `GET /api/crm/v2/timeline` and renders a Day-grouped feed
 * with per-source icons, deep links, status pills, and a "Load more"
 * button when more events are paginated behind the current view.
 *
 * Props:
 *   scope: { type: 'company'|'opportunity'|'tender', id: string }
 *   API:     REACT_APP_BACKEND_URL (no trailing /api — same convention
 *            as SEO/Social Autopilot panels)
 *   headers: () => ({ Authorization: 'Bearer ...' })
 *   isDark:  boolean (theme variable selector)
 *   c:       theme palette object from the CRM context
 *   onDeepLink?: (event) => void  — optional custom drill-in handler
 *                                   (defaults to console.log)
 */

const ICON_BY_HINT = {
  call: Phone,
  email: Mail,
  meeting: Calendar,
  task: CheckCircle,
  note: FileText,
  system: Activity,
  visit: Activity,
  quote: DollarSign,
  case: AlertOctagon,
  tender: Award,
};

const COLOR_BY_TYPE = (type) => {
  if (type.startsWith('quote:')) return 'var(--color-success-alt)';
  if (type.startsWith('case:')) return 'var(--color-warning)';
  if (type.startsWith('tender:')) return 'var(--color-accent-magenta)';
  if (type.startsWith('activity:call')) return 'var(--color-info-ios)';
  if (type.startsWith('activity:email')) return 'var(--color-cyan-500)';
  if (type.startsWith('activity:meeting')) return 'var(--color-accent-violet)';
  return 'var(--color-text-faint-alt)';
};

const STATUS_TONE = {
  draft: 'var(--color-text-faint-alt)',
  sent: 'var(--color-info-ios)',
  accepted: 'var(--color-success-alt-2)',
  lost: 'var(--color-danger)',
  submitted: 'var(--color-info-ios)',
  open: 'var(--color-warning)',
  resolved: 'var(--color-success-alt)',
  closed: 'var(--color-text-faint-alt)',
};

function _dayKey(iso) {
  if (!iso) return 'unknown';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return 'unknown';
  return d.toISOString().slice(0, 10); // YYYY-MM-DD
}

function _dayLabel(iso) {
  const today = new Date();
  const yest = new Date(today.getTime() - 86400_000);
  const tKey = today.toISOString().slice(0, 10);
  const yKey = yest.toISOString().slice(0, 10);
  if (iso === 'unknown') return 'Older';
  if (iso === tKey) return 'Today';
  if (iso === yKey) return 'Yesterday';
  // dd MMM yyyy
  const d = new Date(iso);
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function _timeLabel(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}

function _typeLabel(type) {
  // "activity:call" -> "Call"
  // "quote:sent" -> "Quote · sent"
  // "tender:status_changed" -> "Tender · status changed"
  const [src, sub] = type.split(':');
  const pretty = (sub || '').replace(/_/g, ' ');
  if (src === 'activity') return pretty.charAt(0).toUpperCase() + pretty.slice(1);
  const srcCap = src.charAt(0).toUpperCase() + src.slice(1);
  return sub ? `${srcCap} · ${pretty}` : srcCap;
}

export default function TimelinePanel({
  scope, API, headers, isDark, c, onDeepLink,
}) {
  const [events, setEvents] = useState([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);
  const PAGE = 30;

  const load = useCallback(async (reset = true) => {
    if (!scope?.type || !scope?.id) return;
    if (reset) {
      setLoading(true);
      setSkip(0);
    } else {
      setLoadingMore(true);
    }
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set(`${scope.type}_id`, scope.id);
      params.set('limit', PAGE);
      params.set('skip', reset ? 0 : skip);
      const res = await axios.get(
        `${API}/api/crm/v2/timeline?${params.toString()}`,
        { headers: headers() },
      );
      const newRows = res.data?.events || [];
      setTotal(res.data?.total || 0);
      setEvents(reset ? newRows : [...events, ...newRows]);
      setSkip((reset ? 0 : skip) + newRows.length);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not load timeline');
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope?.type, scope?.id, API]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(true);   }, [scope?.type, scope?.id]);

  const grouped = useMemo(() => {
    const g = new Map();
    for (const ev of events) {
      const key = _dayKey(ev.occurred_at);
      if (!g.has(key)) g.set(key, []);
      g.get(key).push(ev);
    }
    // Mongo-side sort is desc; Python merge re-sorted; map insertion preserves
    // newest-first day order naturally.
    return Array.from(g.entries());
  }, [events]);

  const handleClick = (ev) => {
    if (onDeepLink) onDeepLink(ev);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-10" data-testid="timeline-loading">
        <Loader2 size={20} className="animate-spin" style={{ color: c?.textDim || 'var(--color-text-faint-alt)' }} />
      </div>
    );
  }

  if (error) {
    return (
      <div
        className="rounded-lg border p-4 text-sm"
        style={{ borderColor: 'var(--color-danger)', color: 'var(--color-danger)' }}
        data-testid="timeline-error"
      >
        {error}
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <p
        className="text-center py-10 text-sm"
        style={{ color: c?.textDim || 'var(--color-text-faint-alt)' }}
        data-testid="timeline-empty"
      >
        No activity yet on this {scope?.type || 'record'}.
      </p>
    );
  }

  return (
    <div className="space-y-5" data-testid="timeline-panel">
      {grouped.map(([dayKey, dayEvents]) => (
        <div key={dayKey} data-testid={`timeline-day-${dayKey}`}>
          <div className="flex items-center gap-2 mb-2 pb-1 border-b" style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}>
            <p
              className="text-[10px] uppercase tracking-wider font-semibold"
              style={{ color: c?.textDim || 'var(--color-text-faint-alt)' }}
            >
              {_dayLabel(dayKey)}
            </p>
            <span className="text-[10px]" style={{ color: c?.textFaint || 'var(--color-text-faint-alt)' }}>
              {dayEvents.length} event{dayEvents.length === 1 ? '' : 's'}
            </span>
          </div>
          <div className="space-y-0">
            {dayEvents.map((ev, i) => {
              const Icon = ICON_BY_HINT[ev.icon_hint] || Activity;
              const accent = COLOR_BY_TYPE(ev.type);
              const statusTone = ev.status_hint ? (STATUS_TONE[ev.status_hint] || 'var(--color-text-faint-alt)') : null;
              const isLastInDay = i === dayEvents.length - 1;
              return (
                <button
                  type="button"
                  key={ev.id}
                  onClick={() => handleClick(ev)}
                  className="flex gap-3 relative w-full text-left hover:bg-white/5 rounded-md transition-all px-1 py-1.5 group"
                  data-testid={`timeline-event-${ev.source_collection}`}
                >
                  {!isLastInDay && (
                    <div
                      className="absolute left-[1.05rem] top-9 w-px h-full"
                      style={{ background: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)' }}
                    />
                  )}
                  <div
                    className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 z-10 border"
                    style={{
                      background: isDark ? 'var(--color-surface-dark-2)' : '#fff',
                      borderColor: accent,
                      color: accent,
                    }}
                  >
                    <Icon size={12} />
                  </div>
                  <div className="flex-1 min-w-0 pb-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span
                        className="text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded"
                        style={{ background: `${accent}15`, color: accent }}
                      >
                        {_typeLabel(ev.type)}
                      </span>
                      {statusTone && (
                        <span
                          className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded"
                          style={{ background: `${statusTone}15`, color: statusTone }}
                        >
                          {ev.status_hint}
                        </span>
                      )}
                      <span className="text-[10px]" style={{ color: c?.textDim || 'var(--color-text-faint-alt)' }}>
                        {_timeLabel(ev.occurred_at)}
                      </span>
                    </div>
                    {ev.subject && (
                      <p className="text-sm font-medium mt-1" style={{ color: c?.text || 'inherit' }}>
                        {ev.subject}
                      </p>
                    )}
                    {ev.body && (
                      <p className="text-xs mt-0.5 line-clamp-2" style={{ color: c?.textDim || 'var(--color-text-faint-alt)' }}>
                        {ev.body}
                      </p>
                    )}
                    {ev.actor && (
                      <p className="text-[10px] mt-1" style={{ color: c?.textFaint || 'var(--color-text-faint-alt)' }}>
                        by {ev.actor}
                      </p>
                    )}
                  </div>
                  <ChevronRight
                    size={14}
                    className="opacity-0 group-hover:opacity-100 transition-opacity self-center shrink-0"
                    style={{ color: c?.textDim || 'var(--color-text-faint-alt)' }}
                  />
                </button>
              );
            })}
          </div>
        </div>
      ))}

      {events.length < total && (
        <div className="flex justify-center pt-2">
          <button
            type="button"
            onClick={() => load(false)}
            disabled={loadingMore}
            className="px-4 py-1.5 text-xs font-medium rounded-md border transition-all hover:bg-white/5 disabled:opacity-50 flex items-center gap-1.5"
            style={{ borderColor: isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)', color: c?.textMuted || 'inherit' }}
            data-testid="timeline-load-more"
          >
            {loadingMore ? (
              <>
                <Loader2 size={12} className="animate-spin" /> Loading…
              </>
            ) : (
              <>
                <ChevronDown size={12} /> Load more ({total - events.length} remaining)
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
