/**
 * Service Desk → Unified PPM calendar (all customers).
 *
 * Month grid of every customer's preventative-maintenance due dates, merged
 * with MOD contract annual visits. Filter by segment (All / Commercial /
 * MOD). Click a commercial item to pick the service, allocate one or more
 * engineers and a date — this creates the job and puts it on the schedule.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarClock, ChevronLeft, ChevronRight, Loader2, RefreshCw, Users, Check, Plus, Search, Trash2, ListChecks, X, CalendarRange } from 'lucide-react';
import { api } from '@/lib/api';
import { notify } from '@/components/notifications';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import BulkPpmWizard from './BulkPpmWizard';
import PpmScheduleDetail from './PpmScheduleDetail';

const SEGMENTS = [{ id: 'all', label: 'All' }, { id: 'commercial', label: 'Commercial' }, { id: 'mod', label: 'MOD' }];
const STATUS_STYLE = {
  overdue: 'bg-rose-100 text-rose-800 border-rose-300',
  due_soon: 'bg-amber-100 text-amber-800 border-amber-300',
  planned: 'bg-sky-100 text-sky-800 border-sky-300',
  scheduled: 'bg-emerald-100 text-emerald-800 border-emerald-300',
  unplanned: 'bg-zinc-100 text-zinc-600 border-zinc-300',
};
const monthLabel = (d) => d.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });
function monthGrid(view) {
  const first = new Date(view.getFullYear(), view.getMonth(), 1);
  const start = new Date(first);
  start.setDate(first.getDate() - ((first.getDay() + 6) % 7)); // Monday-first
  const days = [];
  for (let i = 0; i < 42; i += 1) { const d = new Date(start); d.setDate(start.getDate() + i); days.push(d); }
  return days;
}

export default function PPMCalendar() {
  const [view, setView] = useState(() => new Date());
  const [segment, setSegment] = useState('all');
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [backfilling, setBackfilling] = useState(false);
  const [engineers, setEngineers] = useState([]);
  const [active, setActive] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [showWizard, setShowWizard] = useState(false);
  const [detailId, setDetailId] = useState(null);
  const [manageMode, setManageMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState([]);
  const [showDeleteAll, setShowDeleteAll] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [searching, setSearching] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const from = new Date(view.getFullYear(), view.getMonth(), 1).toISOString().slice(0, 10);
    const to = new Date(view.getFullYear(), view.getMonth() + 1, 0).toISOString().slice(0, 10);
    try {
      const r = await api.get('/svc/ppm/calendar', { params: { from, to, segment } });
      setItems(r.data?.items || []);
    } catch { notify.error('Could not load the maintenance calendar'); }
    finally { setLoading(false); }
  }, [view, segment]);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    (async () => {
      try { const r = await api.get('/svc/desk/engineers'); setEngineers(r.data?.engineers || []); }
      catch { /* non-blocking */ }
    })();
  }, []);

  const byDay = useMemo(() => {
    const map = {};
    items.forEach((it) => { const k = String(it.date).slice(0, 10); (map[k] = map[k] || []).push(it); });
    return map;
  }, [items]);

  const backfill = async () => {
    setBackfilling(true);
    try {
      const r = await api.post('/svc/ppm/backfill', {});
      notify.success(`Planned ${r.data?.schedules_created || 0} maintenance schedule(s) from install dates`);
      await load();
    } catch { notify.error('Back-fill failed'); }
    finally { setBackfilling(false); }
  };

  // ── Search booked visits (all months) ──
  useEffect(() => {
    const term = query.trim();
    if (term.length < 2) { setResults(null); return undefined; }
    setSearching(true);
    const t = setTimeout(async () => {
      try { const r = await api.get('/svc/ppm/search', { params: { q: term } }); setResults(r.data?.results || []); }
      catch { setResults([]); }
      finally { setSearching(false); }
    }, 350);
    return () => clearTimeout(t);
  }, [query]);

  const jumpTo = (r) => {
    const d = new Date(r.date);
    setView(new Date(d.getFullYear(), d.getMonth(), 1));
    setQuery(''); setResults(null);
    setDetailId(r.schedule_id);
  };

  // ── Bulk delete (manage mode) ──
  const toggleSelect = (id) => setSelectedIds((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const deleteSelected = async () => {
    if (!selectedIds.length) return;
    if (!window.confirm(`Delete ${selectedIds.length} PM visit(s) from the calendar?`)) return;
    try {
      const r = await api.post('/svc/ppm/schedules/delete', { schedule_ids: selectedIds });
      notify.success(`Removed ${r.data?.deleted || 0} visit(s)`);
      setSelectedIds([]); setManageMode(false); await load();
    } catch { notify.error('Bulk delete failed'); }
  };
  const exitManage = () => { setManageMode(false); setSelectedIds([]); };

  // ── Drag to reschedule ──
  const [dragId, setDragId] = useState(null);
  const [dragOverKey, setDragOverKey] = useState(null);
  const reschedule = async (scheduleId, dateKey) => {
    const item = items.find((it) => it.schedule_id === scheduleId);
    if (!item || item.date === dateKey) return;
    // optimistic
    setItems((prev) => prev.map((it) => (it.schedule_id === scheduleId ? { ...it, date: dateKey } : it)));
    try {
      await api.post(`/svc/ppm/schedules/${scheduleId}/reschedule`, { date: dateKey });
      notify.success(`Moved to ${new Date(dateKey).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`);
    } catch {
      notify.error('Could not reschedule'); await load();
    }
  };

  const days = monthGrid(view);
  const todayKey = new Date().toISOString().slice(0, 10);

  return (
    <section className="rounded-xl border border-zinc-200 dark:border-zinc-800 overflow-hidden" data-testid="ppm-calendar">
      <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <CalendarClock size={16} className="text-[var(--color-brand-blue,#2563eb)]" />
          <span className="text-sm font-bold">Maintenance calendar — all customers</span>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative" data-testid="ppm-search-wrap">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search site or customer…"
              className="h-8 w-52 pl-8 pr-7 rounded-full border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-xs" data-testid="ppm-search-input" />
            {query && <button onClick={() => { setQuery(''); setResults(null); }} className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-700" data-testid="ppm-search-clear"><X size={13} /></button>}
            {results !== null && (
              <div className="absolute z-30 mt-1 w-80 right-0 max-h-72 overflow-auto rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 shadow-xl" data-testid="ppm-search-results">
                {searching ? <div className="p-3 text-xs text-zinc-400 flex items-center gap-2"><Loader2 size={12} className="animate-spin" /> Searching…</div>
                  : results.length === 0 ? <div className="p-3 text-xs text-zinc-400">No booked visits match “{query}”.</div>
                    : results.map((r) => (
                      <button key={r.schedule_id} onClick={() => jumpTo(r)} className="w-full text-left px-3 py-2 hover:bg-zinc-50 dark:hover:bg-zinc-800 border-b border-zinc-100 dark:border-zinc-800 last:border-0" data-testid={`ppm-search-result-${r.schedule_id}`}>
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-semibold truncate">{r.site_name || r.customer_name}</span>
                          <span className="text-[10px] text-zinc-500 shrink-0">{new Date(r.date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}</span>
                        </div>
                        <div className="text-[10px] text-zinc-400 truncate">{r.customer_name}{r.machine_count ? ` · ${r.machine_count} machines` : ''}{r.engineer ? ` · ${r.engineer}` : ''}</div>
                      </button>
                    ))}
              </div>
            )}
          </div>
          <div className="inline-flex rounded-full border border-zinc-200 dark:border-zinc-700 overflow-hidden bg-white dark:bg-zinc-900" data-testid="ppm-segment">
            {SEGMENTS.map((s) => (
              <button key={s.id} onClick={() => setSegment(s.id)} data-testid={`ppm-seg-${s.id}`}
                className="px-3 py-1 text-xs font-semibold transition-colors"
                style={segment === s.id
                  ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }
                  : { background: 'transparent', color: 'var(--theme-text-muted)' }}>
                {s.label}
              </button>
            ))}
          </div>
          <Button size="sm" onClick={() => setShowCreate(true)} data-testid="ppm-create-btn" className="bg-[var(--color-brand-cyan)] text-[var(--color-ink)] hover:opacity-90">
            <Plus size={13} className="mr-1.5" /> Create PM
          </Button>
          <Button size="sm" variant="outline" onClick={() => setShowWizard(true)} data-testid="ppm-bulk-btn">
            <CalendarRange size={13} className="mr-1.5" /> Bulk schedule
          </Button>
          <Button variant="outline" size="sm" onClick={backfill} disabled={backfilling} data-testid="ppm-backfill-btn">
            {backfilling ? <Loader2 size={13} className="animate-spin mr-1.5" /> : <RefreshCw size={13} className="mr-1.5" />}
            Plan from installs
          </Button>
          <Button variant={manageMode ? 'default' : 'outline'} size="sm" onClick={() => (manageMode ? exitManage() : setManageMode(true))} data-testid="ppm-manage-btn"
            className={manageMode ? 'bg-rose-600 text-white hover:bg-rose-700' : ''}>
            <ListChecks size={13} className="mr-1.5" /> {manageMode ? 'Done' : 'Manage'}
          </Button>
        </div>
      </div>

      {manageMode && (
        <div className="px-4 py-2 bg-rose-50 dark:bg-rose-950/20 border-b border-rose-200 dark:border-rose-900 flex items-center justify-between gap-2 flex-wrap" data-testid="ppm-manage-bar">
          <span className="text-xs font-semibold text-rose-700 dark:text-rose-300">{selectedIds.length} selected · tick visits to remove</span>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => setShowDeleteAll(true)} data-testid="ppm-deleteall-btn">
              Delete ALL for a customer…
            </Button>
            <Button size="sm" onClick={deleteSelected} disabled={!selectedIds.length} data-testid="ppm-delete-selected-btn"
              className="bg-rose-600 text-white hover:bg-rose-700">
              <Trash2 size={13} className="mr-1.5" /> Delete selected
            </Button>
          </div>
        </div>
      )}

      <div className="px-4 py-2 flex items-center justify-between">
        <button onClick={() => setView(new Date(view.getFullYear(), view.getMonth() - 1, 1))} className="p-1.5 rounded hover:bg-zinc-100 dark:hover:bg-zinc-800" data-testid="ppm-prev-month" aria-label="Previous month"><ChevronLeft size={16} /></button>
        <span className="text-sm font-bold" data-testid="ppm-month-label">{monthLabel(view)}</span>
        <button onClick={() => setView(new Date(view.getFullYear(), view.getMonth() + 1, 1))} className="p-1.5 rounded hover:bg-zinc-100 dark:hover:bg-zinc-800" data-testid="ppm-next-month" aria-label="Next month"><ChevronRight size={16} /></button>
      </div>

      {loading ? (
        <div className="p-8 text-center text-zinc-400"><Loader2 className="animate-spin mx-auto" /></div>
      ) : (
        <div className="px-3 pb-3">
          <div className="grid grid-cols-7 gap-1 text-[10px] uppercase tracking-wider text-zinc-400 font-semibold px-1 mb-1">
            {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => <div key={d} className="text-center">{d}</div>)}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {days.map((d) => {
              const key = d.toISOString().slice(0, 10);
              const inMonth = d.getMonth() === view.getMonth();
              const cellItems = byDay[key] || [];
              return (
                <div key={key}
                  onDragOver={(e) => { if (dragId && !manageMode) { e.preventDefault(); setDragOverKey(key); } }}
                  onDragLeave={() => setDragOverKey((k) => (k === key ? null : k))}
                  onDrop={(e) => { e.preventDefault(); if (dragId) { reschedule(dragId, key); } setDragId(null); setDragOverKey(null); }}
                  className={`min-h-[76px] rounded-lg border p-1 ${inMonth ? 'border-zinc-200 dark:border-zinc-800' : 'border-transparent opacity-40'} ${key === todayKey ? 'ring-1 ring-[var(--color-brand-blue,#2563eb)]' : ''} ${dragOverKey === key ? 'ring-2 ring-[var(--color-brand-cyan)] bg-cyan-50/40 dark:bg-cyan-950/20' : ''}`}
                  data-testid={`ppm-day-${key}`}>
                  <div className="text-[10px] font-semibold text-zinc-400 px-0.5">{d.getDate()}</div>
                  <div className="space-y-0.5 mt-0.5">
                    {cellItems.slice(0, 3).map((it, i) => {
                      const isCommercial = it.type === 'commercial';
                      const selected = selectedIds.includes(it.schedule_id);
                      const label = it.site_name || it.customer_name || it.title;
                      const draggable = isCommercial && !manageMode;
                      const onClick = () => {
                        if (!isCommercial) return;
                        if (manageMode) { toggleSelect(it.schedule_id); return; }
                        setDetailId(it.schedule_id);
                      };
                      return (
                        <button key={i} onClick={onClick}
                          draggable={draggable}
                          onDragStart={(e) => { if (draggable) { setDragId(it.schedule_id); e.dataTransfer.effectAllowed = 'move'; } }}
                          onDragEnd={() => { setDragId(null); setDragOverKey(null); }}
                          title={`${it.customer_name} · ${it.site_name}${it.machine_count ? ` · ${it.machine_count} machines` : ''}${it.engineer ? ` · ${it.engineer}` : ''}${draggable ? ' · drag to reschedule' : ''}`}
                          className={`w-full flex items-center gap-1 text-[10px] leading-tight px-1 py-0.5 rounded border ${STATUS_STYLE[it.status] || STATUS_STYLE.planned} ${isCommercial ? 'cursor-pointer hover:brightness-95' : 'cursor-default'} ${draggable ? 'active:cursor-grabbing' : ''} ${manageMode && selected ? 'ring-2 ring-rose-500' : ''} ${dragId === it.schedule_id ? 'opacity-40' : ''}`}
                          data-testid={`ppm-item-${key}-${i}`}>
                          {manageMode && isCommercial && (
                            <span className={`w-2.5 h-2.5 rounded-[3px] border shrink-0 ${selected ? 'bg-rose-500 border-rose-500' : 'border-zinc-400 bg-white/60'}`} />
                          )}
                          {it.type === 'mod' ? '🛡 ' : ''}
                          <span className="truncate flex-1 text-left font-medium">{label}</span>
                          {it.machine_count ? <span className="shrink-0 text-[8px] font-bold bg-black/10 dark:bg-white/15 rounded px-1">{it.machine_count}</span> : null}
                        </button>
                      );
                    })}
                    {cellItems.length > 3 && <div className="text-[9px] text-zinc-400 px-1">+{cellItems.length - 3} more</div>}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="flex items-center gap-3 mt-2 px-1 text-[10px] text-zinc-500 flex-wrap">
            <span className="inline-flex items-center gap-1"><i className="w-2.5 h-2.5 rounded-sm bg-rose-300 inline-block" /> Overdue</span>
            <span className="inline-flex items-center gap-1"><i className="w-2.5 h-2.5 rounded-sm bg-amber-300 inline-block" /> Due soon</span>
            <span className="inline-flex items-center gap-1"><i className="w-2.5 h-2.5 rounded-sm bg-sky-300 inline-block" /> Planned</span>
            <span className="inline-flex items-center gap-1"><i className="w-2.5 h-2.5 rounded-sm bg-emerald-300 inline-block" /> Scheduled</span>
            <span className="ml-auto">{manageMode ? 'Tick visits then Delete selected' : 'Click a visit for details · drag it to another day to reschedule'}</span>
          </div>
        </div>
      )}

      {active && (
        <SchedulePpmModal item={active} engineers={engineers} onClose={() => setActive(null)} onDone={async () => { setActive(null); await load(); }} />
      )}
      {showCreate && (
        <CreatePpmModal onClose={() => setShowCreate(false)} onDone={async () => { setShowCreate(false); await load(); }} />
      )}
      {showWizard && (
        <BulkPpmWizard onClose={() => setShowWizard(false)} onDone={async () => { setShowWizard(false); await load(); }} />
      )}
      {detailId && (
        <PpmScheduleDetail scheduleId={detailId}
          onClose={() => setDetailId(null)}
          onAllocate={(s) => { setDetailId(null); setActive({ schedule_id: s.id, date: s.date, service_type: s.service_type, customer_name: s.customer_name, site_name: s.site_name, site_id: s.site_id, equipment_name: `${s.machine_count} machines` }); }}
          onDeleted={async () => { setDetailId(null); await load(); }} />
      )}
      {showDeleteAll && (
        <DeleteAllModal onClose={() => setShowDeleteAll(false)} onDone={async () => { setShowDeleteAll(false); exitManage(); await load(); }} />
      )}
    </section>
  );
}

function SchedulePpmModal({ item, engineers, onClose, onDone }) {
  const [services, setServices] = useState(['Preventative Maintenance Service', 'Calibration']);
  const [service, setService] = useState(item.service_type || 'Preventative Maintenance Service');
  const [date, setDate] = useState(String(item.date).slice(0, 10));
  const [engIds, setEngIds] = useState([]);
  const [load, setLoad] = useState({});
  const [slots, setSlots] = useState({});
  const [suggested, setSuggested] = useState(null);
  const [suggestReason, setSuggestReason] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { (async () => { try { const r = await api.get('/svc/ppm/services'); if (r.data?.services) setServices(r.data.services); } catch { /* keep defaults */ } })(); }, []);
  useEffect(() => {
    if (!date) { setLoad({}); setSlots({}); setSuggested(null); return; }
    (async () => {
      try {
        const r = await api.get('/svc/ppm/engineer-load', { params: { date, site_id: item.site_id || undefined } });
        setLoad(r.data?.load || {});
        setSlots(r.data?.slots || {});
        setSuggested(r.data?.suggested_engineer_id || null);
        setSuggestReason(r.data?.suggested_reason || null);
      } catch { setLoad({}); setSlots({}); setSuggested(null); setSuggestReason(null); }
    })();
  }, [date, item.site_id]);
  const toggle = (id) => setEngIds((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));

  const submit = async () => {
    if (!date) { notify.error('Pick a service date'); return; }
    setBusy(true);
    try {
      const r = await api.post('/svc/ppm/schedule', {
        schedule_id: item.schedule_id, service_type: service, scheduled_at: date, engineer_ids: engIds,
      });
      notify.success(`Scheduled · job ${r.data?.reference || ''}${engIds.length ? ` · ${engIds.length} engineer(s)` : ''}`);
      onDone();
    } catch (e) { notify.error(e?.response?.data?.detail || 'Could not schedule'); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose} data-testid="ppm-schedule-modal">
      <div className="bg-white dark:bg-zinc-900 rounded-2xl shadow-xl w-full max-w-md p-5" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-black text-zinc-900 dark:text-zinc-100 mb-1">Schedule maintenance</h2>
        <p className="text-xs text-zinc-500 mb-3">{item.customer_name || '—'} · {item.site_name || '—'}{item.equipment_name ? ` · ${item.equipment_name}` : ''}</p>

        <Label className="block text-xs font-semibold text-zinc-500 mb-1">Service</Label>
        <Select value={service} onValueChange={setService}>
          <SelectTrigger className="w-full mb-3" data-testid="ppm-service-select"><SelectValue /></SelectTrigger>
          <SelectContent>{services.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
        </Select>

        <Label className="block text-xs font-semibold text-zinc-500 mb-1">Service date</Label>
        <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="mb-3" data-testid="ppm-date" />

        <Label className="block text-xs font-semibold text-zinc-500 mb-1 flex items-center gap-1.5"><Users size={12} /> Allocate engineer(s)<span className="ml-auto font-normal text-zinc-400">jobs on this date</span></Label>
        <div className="max-h-40 overflow-auto rounded-lg border border-zinc-200 dark:border-zinc-700 divide-y divide-zinc-100 dark:divide-zinc-800 mb-4" data-testid="ppm-engineer-list">
          {engineers.length === 0 ? (
            <p className="text-xs text-zinc-400 p-2">No engineers on the roster.</p>
          ) : engineers.map((e) => {
            const n = load[e.id] || 0;
            const daySlots = slots[e.id] || [];
            const isSuggested = suggested === e.id;
            return (
              <button key={e.id} type="button" onClick={() => toggle(e.id)} className={`w-full flex flex-col gap-0.5 px-3 py-1.5 text-sm text-left hover:bg-zinc-50 dark:hover:bg-zinc-800 ${isSuggested ? 'bg-emerald-50/60 dark:bg-emerald-950/20' : ''}`} data-testid={`ppm-eng-${e.id}`}>
                <span className="flex items-center justify-between gap-2 w-full">
                  <span className="flex items-center gap-2 min-w-0">
                    {engIds.includes(e.id) && <Check size={14} className="text-emerald-600 shrink-0" />}
                    <span className={engIds.includes(e.id) ? 'font-semibold' : ''}>{e.full_name}</span>
                    {isSuggested && <span className="text-[9px] font-bold uppercase tracking-wide bg-emerald-600 text-white px-1.5 py-0.5 rounded-full shrink-0" data-testid={`ppm-suggested-${e.id}`} title={suggestReason || 'Suggested'}>Suggested</span>}
                  </span>
                  <span
                    className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full shrink-0 ${n === 0 ? 'bg-emerald-100 text-emerald-700' : n <= 2 ? 'bg-amber-100 text-amber-700' : 'bg-rose-100 text-rose-700'}`}
                    title={`${n} job(s) already scheduled on this date`}
                    data-testid={`ppm-eng-load-${e.id}`}
                  >
                    {n === 0 ? 'free' : `${n} job${n === 1 ? '' : 's'}`}
                  </span>
                </span>
                {daySlots.length > 0 && (
                  <span className="flex flex-wrap gap-1 pl-6" data-testid={`ppm-eng-slots-${e.id}`}>
                    {daySlots.map((s, i) => (
                      <span key={i} className="text-[9px] font-mono bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 px-1.5 py-0.5 rounded" title={`${s.title}${s.site_name ? ` · ${s.site_name}` : ''}`}>
                        {s.time}{s.minutes ? `·${s.minutes}m` : ''}{s.site_name ? ` · ${s.site_name}` : ''}
                      </span>
                    ))}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} data-testid="ppm-cancel">Cancel</Button>
          <Button onClick={submit} disabled={busy} data-testid="ppm-schedule-save">
            {busy ? <Loader2 size={14} className="animate-spin mr-1.5" /> : <Check size={14} className="mr-1.5" />} Schedule &amp; assign
          </Button>
        </div>
      </div>
    </div>
  );
}


const FREQS = [
  { v: 'monthly', label: 'Monthly' },
  { v: 'quarterly', label: 'Quarterly' },
  { v: 'six_monthly', label: '6-monthly' },
  { v: 'annual', label: 'Annual' },
];

function CreatePpmModal({ onClose, onDone }) {
  const mode = 'single';
  const [customers, setCustomers] = useState([]);
  const [serviceTypes, setServiceTypes] = useState([]);
  const [customerOrgId, setCustomerOrgId] = useState('');
  const [sites, setSites] = useState([]);
  const [siteId, setSiteId] = useState('');
  const [serviceType, setServiceType] = useState('Preventative Maintenance Service');
  const [frequency, setFrequency] = useState('annual');
  const [firstVisit, setFirstVisit] = useState(() => new Date().toISOString().slice(0, 10));
  const [newType, setNewType] = useState('');
  const [saving, setSaving] = useState(false);

  const loadTypes = useCallback(async () => {
    try { const r = await api.get('/svc/ppm/service-types'); setServiceTypes(r.data?.service_types || []); }
    catch { /* non-blocking */ }
  }, []);
  useEffect(() => {
    (async () => {
      try { const r = await api.get('/svc/desk/customers'); setCustomers(r.data?.customers || []); }
      catch { /* non-blocking */ }
    })();
    loadTypes();
  }, [loadTypes]);

  useEffect(() => {
    setSites([]); setSiteId('');
    if (!customerOrgId) return;
    (async () => {
      try {
        const r = await api.get('/svc/desk/customer-sites', { params: { organization_id: customerOrgId } });
        setSites(r.data?.sites || []);
      } catch { setSites([]); }
    })();
  }, [customerOrgId]);

  const addType = async () => {
    const name = newType.trim();
    if (!name) return;
    try {
      await api.post('/svc/ppm/service-types', { name });
      setNewType(''); await loadTypes(); setServiceType(name);
      notify.success(`Added service type “${name}”`);
    } catch { notify.error('Could not add service type'); }
  };

  const submit = async () => {
    if (!customerOrgId) { notify.error('Pick a customer'); return; }
    if (!siteId) { notify.error('Pick a site'); return; }
    setSaving(true);
    try {
      const r = await api.post('/svc/ppm/schedules', {
        customer_org_id: customerOrgId, site_id: siteId,
        service_type: serviceType, frequency, first_visit: firstVisit,
      });
      notify.success('Preventative maintenance scheduled', `Next visit ${r.data?.next_pm || firstVisit}`);
      await onDone?.();
    } catch (e) { notify.error('Could not create PM', e?.response?.data?.detail || e.message); }
    finally { setSaving(false); }
  };

  const activeType = serviceTypes.find((s) => s.name === serviceType);

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }} data-testid="ppm-create-modal">
      <div className="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 w-full max-w-lg max-h-[92vh] overflow-auto shadow-2xl">
        <div className="px-5 py-3.5 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between">
          <h3 className="text-base font-bold">Create preventative maintenance</h3>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-700" data-testid="ppm-create-close">✕</button>
        </div>
        <div className="p-5 space-y-4">
          <p className="text-[11px] text-zinc-500">Schedule a single site. For many sites at once, use <span className="font-semibold">Bulk schedule</span>.</p>

          <div>
            <Label className="text-xs">Customer</Label>
            <select value={customerOrgId} onChange={(e) => setCustomerOrgId(e.target.value)}
              className="w-full mt-1 h-10 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 text-sm" data-testid="ppm-create-customer">
              <option value="">— Select customer —</option>
              {customers.map((c) => (
                <option key={c.organization_id} value={c.organization_id}>{c.name}{c.is_operator ? ' (my org)' : ''}{c.site_count != null ? ` · ${c.site_count} sites` : ''}</option>
              ))}
            </select>
          </div>

          {mode === 'single' ? (
            <div>
              <Label className="text-xs">Site</Label>
              <select value={siteId} onChange={(e) => setSiteId(e.target.value)} disabled={!customerOrgId}
                className="w-full mt-1 h-10 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 text-sm" data-testid="ppm-create-site">
                <option value="">{sites.length ? '— Select site —' : 'No sites'}</option>
                {sites.map((s) => <option key={s.id} value={s.id}>{s.name}{s.equipment_count != null ? ` · ${s.equipment_count} machines` : ''}</option>)}
              </select>
            </div>
          ) : null}

          <div>
            <Label className="text-xs">Service type</Label>
            <select value={serviceType} onChange={(e) => setServiceType(e.target.value)}
              className="w-full mt-1 h-10 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 text-sm" data-testid="ppm-create-service">
              {serviceTypes.map((s) => <option key={s.id} value={s.name}>{`${s.name}${s.calibrate_treadmills ? ' (PM + treadmill calibration)' : (s.requires_calibration ? ' (calibration)' : '')}`}</option>)}
            </select>
            {activeType?.checklist_items?.length ? (
              <p className="text-[11px] text-zinc-500 mt-1">Records on the case: {activeType.checklist_items.join(', ')}</p>
            ) : null}
            <div className="flex items-center gap-2 mt-2">
              <Input value={newType} onChange={(e) => setNewType(e.target.value)} placeholder="Add a new service type…" className="h-8 text-xs" data-testid="ppm-create-newtype" />
              <Button size="sm" variant="outline" onClick={addType} data-testid="ppm-create-addtype">Add</Button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Frequency</Label>
              <select value={frequency} onChange={(e) => setFrequency(e.target.value)}
                className="w-full mt-1 h-10 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 text-sm" data-testid="ppm-create-frequency">
                {FREQS.map((f) => <option key={f.v} value={f.v}>{f.label}</option>)}
              </select>
            </div>
            <div>
              <Label className="text-xs">First visit</Label>
              <Input type="date" value={firstVisit} onChange={(e) => setFirstVisit(e.target.value)} className="mt-1" data-testid="ppm-create-date" />
            </div>
          </div>
        </div>
        <div className="px-5 py-3.5 border-t border-zinc-200 dark:border-zinc-800 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose} data-testid="ppm-create-cancel">Cancel</Button>
          <Button size="sm" onClick={submit} disabled={saving} data-testid="ppm-create-submit"
            className="bg-[var(--color-brand-cyan)] text-[var(--color-ink)] hover:opacity-90">
            {saving ? <Loader2 size={13} className="animate-spin mr-1.5" /> : <Plus size={13} className="mr-1.5" />}
            Create PM
          </Button>
        </div>
      </div>
    </div>
  );
}


function DeleteAllModal({ onClose, onDone }) {
  const [customers, setCustomers] = useState([]);
  const [customerOrgId, setCustomerOrgId] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try { const r = await api.get('/svc/desk/customers'); setCustomers(r.data?.customers || []); }
      catch { /* non-blocking */ }
    })();
  }, []);

  const run = async () => {
    if (!customerOrgId) { notify.error('Pick a customer'); return; }
    const name = customers.find((c) => c.organization_id === customerOrgId)?.name || 'this customer';
    if (!window.confirm(`Delete ALL preventative maintenance visits for ${name}? This cannot be undone.`)) return;
    setBusy(true);
    try {
      const r = await api.post('/svc/ppm/schedules/delete-all', { customer_org_id: customerOrgId });
      notify.success(`Deleted ${r.data?.deleted || 0} PM visit(s)`);
      await onDone?.();
    } catch (e) { notify.error('Could not delete', e?.response?.data?.detail || e.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-[60] bg-black/50 flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }} data-testid="ppm-deleteall-modal">
      <div className="bg-white dark:bg-zinc-900 rounded-2xl border border-zinc-200 dark:border-zinc-800 w-full max-w-md p-5 shadow-2xl">
        <h3 className="text-base font-bold text-rose-700 flex items-center gap-2"><Trash2 size={16} /> Delete all PM visits</h3>
        <p className="text-xs text-zinc-500 mt-1 mb-3">Clears every scheduled preventative maintenance visit for the chosen customer — useful to undo a mistaken bulk import.</p>
        <Label className="text-xs">Customer</Label>
        <select value={customerOrgId} onChange={(e) => setCustomerOrgId(e.target.value)}
          className="w-full mt-1 h-10 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 text-sm" data-testid="ppm-deleteall-customer">
          <option value="">— Select customer —</option>
          {customers.map((c) => <option key={c.organization_id} value={c.organization_id}>{c.name}</option>)}
        </select>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="ghost" size="sm" onClick={onClose} data-testid="ppm-deleteall-cancel">Cancel</Button>
          <Button size="sm" onClick={run} disabled={busy || !customerOrgId} data-testid="ppm-deleteall-confirm"
            className="bg-rose-600 text-white hover:bg-rose-700">
            {busy ? <Loader2 size={14} className="animate-spin mr-1.5" /> : <Trash2 size={14} className="mr-1.5" />} Delete all
          </Button>
        </div>
      </div>
    </div>
  );
}
