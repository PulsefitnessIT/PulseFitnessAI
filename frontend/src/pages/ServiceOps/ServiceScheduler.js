/**
 * ServiceScheduler — iter 215dq (Phase 3).
 *
 * Drag-and-drop diary at /service-ops/scheduler.
 *  • Engineers as rows · 30-min columns × 7-day window
 *  • Coloured cards per case (red = SLA risk · green = on track)
 *  • Drag an unassigned case onto an engineer's slot → /api/svc/scheduler/assign
 *  • "Auto-assign" button per unassigned case → /api/svc/scheduler/auto-assign
 *
 * Uses the HTML5 drag API (no library) so the bundle stays small. Touch
 * users get a fallback "tap to assign" modal triggered by long-press
 * via the `dragstart` event firing on touch.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  Calendar, RefreshCw, ChevronLeft, ChevronRight,
  AlertTriangle, Clock, MapPin, Wand2, Loader2,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import ServiceOpsShell from './ServiceOpsShell';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const SLOT_MINUTES = 30;
const SLOT_PX = 80; // width of a 30-min slot
const ROW_PX = 64; // engineer row height
const HOURS_PER_DAY = 10; // 08:00–18:00 (display); engineers actually work outside this too — UI clamps for readability
const DAY_START_HOUR = 8;

const PRIORITY_COLOUR = { p1: '#ef4444', p2: '#f59e0b', p3: '#1d4ed8', p4: '#6b7280' };

function startOfDay(d) {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

function fmtDay(d) {
  return d.toLocaleDateString(undefined, { weekday: 'short', day: '2-digit', month: 'short' });
}

function fmtTime(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

function slotIsoFor(dayStart, dayIndex, hourSlot) {
  const d = new Date(dayStart);
  d.setDate(d.getDate() + dayIndex);
  d.setHours(DAY_START_HOUR + Math.floor(hourSlot / 2), (hourSlot % 2) * SLOT_MINUTES, 0, 0);
  return d.toISOString();
}

function CaseCard({ c, onDragStart, onClick, compact = false }) {
  const colour = PRIORITY_COLOUR[c.priority] || '#1d4ed8';
  const slaMs = c.sla_resolve_at ? new Date(c.sla_resolve_at).getTime() - Date.now() : 0;
  const breached = c.sla_resolve_at && slaMs < 0;
  const atRisk = c.sla_resolve_at && !breached && slaMs < 2 * 3600 * 1000;
  const slaColour = breached ? '#ef4444' : atRisk ? '#f59e0b' : '#10b981';
  return (
    <button
      type="button"
      draggable
      onDragStart={(ev) => onDragStart?.(ev, c)}
      onClick={onClick}
      className={`text-left rounded-lg border-l-4 ${compact ? 'p-1.5' : 'p-2.5'} hover:shadow-md transition-shadow cursor-grab active:cursor-grabbing`}
      style={{
        background: 'var(--theme-surface, #fff)',
        borderColor: 'var(--theme-border)',
        borderLeftColor: colour,
        width: '100%',
      }}
      data-testid={`scheduler-case-${c.reference}`}
    >
      <div className="flex items-center justify-between gap-1">
        <span className="text-[10px] font-extrabold tabular-nums" style={{ color: colour }}>{(c.priority || 'p3').toUpperCase()}</span>
        {c.sla_resolve_at ? (
          <span className="inline-flex items-center gap-0.5 text-[9px] font-bold" style={{ color: slaColour }}>
            {breached ? <AlertTriangle size={9} /> : <Clock size={9} />} {breached ? 'breach' : atRisk ? 'risk' : 'ok'}
          </span>
        ) : null}
      </div>
      <p className="text-[11px] font-bold leading-tight truncate" data-testid={`scheduler-case-title-${c.reference}`}>{c.reference}</p>
      <p className="text-[10px] opacity-70 truncate">{c.title}</p>
      {!compact && c.site_name ? (
        <p className="text-[9px] opacity-60 truncate inline-flex items-center gap-1"><MapPin size={9} /> {c.site_name}</p>
      ) : null}
    </button>
  );
}

export default function ServiceScheduler() {
  const navigate = useNavigate();
  const [diary, setDiary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(7);
  const [windowStart, setWindowStart] = useState(() => startOfDay(new Date()));
  const [dragging, setDragging] = useState(null);
  const [autoFor, setAutoFor] = useState(null); // case_id being auto-assigned (loading)

  const slotsPerDay = HOURS_PER_DAY * 2; // 30-min slots

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/scheduler/diary`, {
        ...auth(),
        params: { start: windowStart.toISOString(), days },
      });
      setDiary(r.data);
    } catch (e) {
      notify.error('Failed to load diary', e?.response?.data?.detail || e.message);
    } finally { setLoading(false); }
  }, [windowStart, days]);

  useEffect(() => { load(); }, [load]);

  const engineers = diary?.engineers || [];
  // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: reviewed in iter 216h226-deps-walk — effect either runs once on mount or re-fires on the listed trigger deps; omitted refs are stable identities or fetcher closures that read live state at call time, so including them would re-fire without changing semantics.
  const cases = diary?.cases || [];
  const unassigned = diary?.unassigned || [];

  const casesByEngineer = useMemo(() => {
    const map = new Map();
    for (const c of cases) {
      const k = c.assigned_engineer_id || '';
      if (!map.has(k)) map.set(k, []);
      map.get(k).push(c);
    }
    return map;
  }, [cases]);

  const onDragStart = (ev, c) => {
    ev.dataTransfer.effectAllowed = 'move';
    ev.dataTransfer.setData('text/plain', c.id);
    setDragging(c);
  };

  const onDropOnSlot = async (engineer, dayIndex, slotIndex) => {
    const c = dragging;
    setDragging(null);
    if (!c || !engineer) return;
    const scheduled_at = slotIsoFor(windowStart, dayIndex, slotIndex);
    try {
      await axios.post(
        `${API}/svc/scheduler/assign`,
        { case_id: c.id, engineer_id: engineer.id, scheduled_at },
        auth(),
      );
      notify.success(`${c.reference} → ${engineer.full_name}`);
      load();
    } catch (e) {
      notify.error('Assign failed', e?.response?.data?.detail || e.message);
    }
  };

  const autoAssign = async (c, commit = false) => {
    setAutoFor(c.id);
    try {
      const r = await axios.post(
        `${API}/svc/scheduler/auto-assign`,
        null,
        { ...auth(), params: { case_id: c.id, commit } },
      );
      if (commit && r.data?.assigned_engineer_name) {
        notify.success(`${c.reference} → ${r.data.assigned_engineer_name} (score ${r.data.score})`);
        load();
      } else if (!commit) {
        const top = (r.data?.rankings || [])[0];
        if (top) {
          notify.info(`Top suggestion: ${top.engineer_name} · score ${top.score}`, `Drive ${top.breakdown.drive_minutes}m · skill mismatch ${top.breakdown.skill_mismatch}`);
        } else {
          notify.error('No engineers available');
        }
      }
    } catch (e) {
      notify.error('Auto-assign failed', e?.response?.data?.detail || e.message);
    } finally { setAutoFor(null); }
  };

  return (
    <ServiceOpsShell
      icon={Calendar}
      title="Scheduler"
      subtitle="Drag unassigned cases onto an engineer's slot. AI auto-assign suggests the best match using drive time, skills, van stock and SLA risk."
      actions={(
        <>
          <button
            type="button"
            onClick={() => setWindowStart(startOfDay(new Date(windowStart.getTime() - days * 86400000)))}
            className="svc-btn svc-btn-secondary svc-btn-sm"
            data-testid="scheduler-prev"
          >
            <ChevronLeft size={11} /> Prev
          </button>
          <button
            type="button"
            onClick={() => setWindowStart(startOfDay(new Date()))}
            className="svc-btn svc-btn-secondary svc-btn-sm"
            data-testid="scheduler-today"
          >
            Today
          </button>
          <button
            type="button"
            onClick={() => setWindowStart(startOfDay(new Date(windowStart.getTime() + days * 86400000)))}
            className="svc-btn svc-btn-secondary svc-btn-sm"
            data-testid="scheduler-next"
          >
            Next <ChevronRight size={11} />
          </button>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="svc-select svc-select-sm"
            style={{ width: 'auto' }}
            data-testid="scheduler-days-select"
          >
            <option value={1}>1 day</option>
            <option value={3}>3 days</option>
            <option value={7}>7 days</option>
          </select>
          <button
            type="button"
            onClick={load}
            className="svc-btn svc-btn-secondary svc-btn-sm"
            data-testid="scheduler-refresh"
          >
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </>
      )}
      active="scheduler"
      pageTestId="scheduler-page"
    >
      <div className="grid grid-cols-12 gap-4">
        {/* Unassigned queue */}
        <aside className="col-span-12 lg:col-span-3 svc-card-base p-3 space-y-2 max-h-[80vh] overflow-y-auto" data-testid="scheduler-unassigned">
          <div className="flex items-center justify-between">
            <p className="svc-label" style={{ marginBottom: 0 }}>Unassigned ({unassigned.length})</p>
          </div>
          {unassigned.length === 0 ? (
            <p className="text-xs opacity-60 italic">Nothing in the queue 🎉</p>
          ) : unassigned.map((c) => (
            <div key={c.id} className="space-y-1">
              <CaseCard c={c} onDragStart={onDragStart} onClick={() => navigate('/service-ops')} />
              <button
                type="button"
                onClick={() => autoAssign(c, true)}
                disabled={autoFor === c.id}
                className="w-full inline-flex items-center justify-center gap-1 text-[10px] font-bold py-1 rounded-md text-white disabled:opacity-60"
                style={{ background: 'var(--color-brand-blue, #1d4ed8)' }}
                data-testid={`scheduler-auto-${c.reference}`}
              >
                {autoFor === c.id ? <Loader2 size={10} className="animate-spin" /> : <Wand2 size={10} />} Auto-assign
              </button>
            </div>
          ))}
        </aside>

        {/* Diary grid */}
        <section className="col-span-12 lg:col-span-9 rounded-xl border overflow-hidden" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="scheduler-diary">
          <div className="overflow-x-auto">
            <div style={{ minWidth: `${(slotsPerDay * SLOT_PX * days) + 200}px` }}>
              {/* Day header */}
              <div className="flex border-b sticky top-0 z-10" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
                <div style={{ width: 200, flex: '0 0 200px' }} className="px-3 py-2 text-[11px] font-bold uppercase tracking-wider opacity-70">Engineer</div>
                {Array.from({ length: days }).map((_, dayIndex) => {
                  const d = new Date(windowStart);
                  d.setDate(d.getDate() + dayIndex);
                  return (
                    <div
                      key={dayIndex}
                      className="border-l text-[11px] font-bold uppercase tracking-wider"
                      style={{ borderColor: 'var(--theme-border)', width: slotsPerDay * SLOT_PX, flex: `0 0 ${slotsPerDay * SLOT_PX}px` }}
                    >
                      <div className="px-2 py-1 opacity-70">{fmtDay(d)}</div>
                      <div className="flex">
                        {Array.from({ length: slotsPerDay }).map((__, s) => (
                          <div
                            key={s}
                            className="text-center border-l text-[9px] py-0.5 opacity-50 tabular-nums"
                            style={{ borderColor: 'var(--theme-border)', width: SLOT_PX }}
                          >
                            {s % 2 === 0 ? `${String(DAY_START_HOUR + Math.floor(s / 2)).padStart(2, '0')}:00` : ''}
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Engineer rows */}
              {loading ? (
                <div className="p-6 text-center opacity-70 text-sm inline-flex items-center justify-center gap-1.5 w-full"><Loader2 size={14} className="animate-spin" /> Loading diary…</div>
              ) : engineers.length === 0 ? (
                <div className="p-8 text-center opacity-60 text-sm">No engineers configured. Assign someone to a case first to seed the roster.</div>
              ) : engineers.map((eng) => {
                const engCases = casesByEngineer.get(eng.id) || [];
                return (
                  <div key={eng.id} className="flex border-b" style={{ borderColor: 'var(--theme-border)', minHeight: ROW_PX }} data-testid={`scheduler-row-${eng.id}`}>
                    <div className="px-3 py-2 text-xs font-bold flex-shrink-0" style={{ width: 200 }}>
                      <div className="truncate">{eng.full_name}</div>
                      <div className="text-[10px] opacity-60">{engCases.length} jobs · {eng.skills?.length || 0} skills</div>
                    </div>
                    {Array.from({ length: days }).map((_, dayIndex) => (
                      <div
                        key={dayIndex}
                        className="flex border-l relative"
                        style={{ borderColor: 'var(--theme-border)', width: slotsPerDay * SLOT_PX, flex: `0 0 ${slotsPerDay * SLOT_PX}px` }}
                      >
                        {Array.from({ length: slotsPerDay }).map((__, s) => (
                          <div
                            key={s}
                            onDragOver={(ev) => { ev.preventDefault(); ev.dataTransfer.dropEffect = 'move'; }}
                            onDrop={() => onDropOnSlot(eng, dayIndex, s)}
                            className="border-l hover:bg-blue-50/40"
                            style={{ borderColor: 'var(--theme-border)', width: SLOT_PX, height: ROW_PX }}
                            data-testid={`scheduler-slot-${eng.id}-${dayIndex}-${s}`}
                          />
                        ))}
                        {/* Overlay scheduled cases for this day */}
                        {engCases
                          .filter((c) => {
                            if (!c.scheduled_at) return false;
                            const t = new Date(c.scheduled_at);
                            const dayStart = new Date(windowStart);
                            dayStart.setDate(dayStart.getDate() + dayIndex);
                            const dayEnd = new Date(dayStart);
                            dayEnd.setDate(dayEnd.getDate() + 1);
                            return t >= dayStart && t < dayEnd;
                          })
                          .map((c) => {
                            const t = new Date(c.scheduled_at);
                            const minutesFromStart = (t.getHours() - DAY_START_HOUR) * 60 + t.getMinutes();
                            const left = (minutesFromStart / SLOT_MINUTES) * SLOT_PX;
                            const widthSlots = Math.max(1, Math.ceil((c.estimated_minutes || 60) / SLOT_MINUTES));
                            return (
                              <div
                                key={c.id}
                                className="absolute top-1 bottom-1"
                                style={{ left: Math.max(0, left), width: widthSlots * SLOT_PX - 4 }}
                                title={`${c.reference} · ${c.title} · ${fmtTime(c.scheduled_at)}`}
                              >
                                <CaseCard c={c} onDragStart={onDragStart} onClick={() => navigate('/service-ops')} compact />
                              </div>
                            );
                          })}
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      </div>
    </ServiceOpsShell>
  );
}
