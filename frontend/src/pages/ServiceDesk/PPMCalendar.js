/**
 * Service Desk → Unified PPM calendar (all customers).
 *
 * Month grid of every customer's preventative-maintenance due dates, merged
 * with MOD contract annual visits. Filter by segment (All / Commercial /
 * MOD). Click a commercial item to pick the service, allocate one or more
 * engineers and a date — this creates the job and puts it on the schedule.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarClock, ChevronLeft, ChevronRight, Loader2, RefreshCw, Users, Check } from 'lucide-react';
import { api } from '@/lib/api';
import { notify } from '@/components/notifications';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

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

  const days = monthGrid(view);
  const todayKey = new Date().toISOString().slice(0, 10);

  return (
    <section className="rounded-xl border border-zinc-200 dark:border-zinc-800 overflow-hidden" data-testid="ppm-calendar">
      <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <CalendarClock size={16} className="text-[var(--color-brand-blue,#2563eb)]" />
          <span className="text-sm font-bold">Maintenance calendar — all customers</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="inline-flex rounded-lg border border-zinc-200 dark:border-zinc-700 overflow-hidden" data-testid="ppm-segment">
            {SEGMENTS.map((s) => (
              <button key={s.id} onClick={() => setSegment(s.id)} data-testid={`ppm-seg-${s.id}`}
                className={`px-2.5 py-1 text-xs font-semibold ${segment === s.id ? 'bg-zinc-900 text-white dark:bg-white dark:text-zinc-900' : 'text-zinc-600 hover:bg-zinc-100 dark:hover:bg-zinc-800'}`}>
                {s.label}
              </button>
            ))}
          </div>
          <Button variant="outline" size="sm" onClick={backfill} disabled={backfilling} data-testid="ppm-backfill-btn">
            {backfilling ? <Loader2 size={13} className="animate-spin mr-1.5" /> : <RefreshCw size={13} className="mr-1.5" />}
            Plan from installs
          </Button>
        </div>
      </div>

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
                <div key={key} className={`min-h-[76px] rounded-lg border p-1 ${inMonth ? 'border-zinc-200 dark:border-zinc-800' : 'border-transparent opacity-40'} ${key === todayKey ? 'ring-1 ring-[var(--color-brand-blue,#2563eb)]' : ''}`} data-testid={`ppm-day-${key}`}>
                  <div className="text-[10px] font-semibold text-zinc-400 px-0.5">{d.getDate()}</div>
                  <div className="space-y-0.5 mt-0.5">
                    {cellItems.slice(0, 3).map((it, i) => (
                      <button key={i} onClick={() => it.type === 'commercial' && setActive(it)}
                        title={`${it.customer_name} · ${it.site_name} · ${it.equipment_name || it.service_type}`}
                        className={`w-full text-left truncate text-[10px] leading-tight px-1 py-0.5 rounded border ${STATUS_STYLE[it.status] || STATUS_STYLE.planned} ${it.type === 'commercial' ? 'cursor-pointer hover:brightness-95' : 'cursor-default'}`}
                        data-testid={`ppm-item-${key}-${i}`}>
                        {it.type === 'mod' ? '🛡 ' : ''}{it.equipment_name || it.customer_name || it.title}
                      </button>
                    ))}
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
            <span className="ml-auto">Click a due item to allocate an engineer</span>
          </div>
        </div>
      )}

      {active && (
        <SchedulePpmModal item={active} engineers={engineers} onClose={() => setActive(null)} onDone={async () => { setActive(null); await load(); }} />
      )}
    </section>
  );
}

function SchedulePpmModal({ item, engineers, onClose, onDone }) {
  const [services, setServices] = useState(['Preventative Maintenance Service', 'Calibration']);
  const [service, setService] = useState(item.service_type || 'Preventative Maintenance Service');
  const [date, setDate] = useState(String(item.date).slice(0, 10));
  const [engIds, setEngIds] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => { (async () => { try { const r = await api.get('/svc/ppm/services'); if (r.data?.services) setServices(r.data.services); } catch { /* keep defaults */ } })(); }, []);
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

        <Label className="block text-xs font-semibold text-zinc-500 mb-1 flex items-center gap-1.5"><Users size={12} /> Allocate engineer(s)</Label>
        <div className="max-h-40 overflow-auto rounded-lg border border-zinc-200 dark:border-zinc-700 divide-y divide-zinc-100 dark:divide-zinc-800 mb-4" data-testid="ppm-engineer-list">
          {engineers.length === 0 ? (
            <p className="text-xs text-zinc-400 p-2">No engineers on the roster.</p>
          ) : engineers.map((e) => (
            <button key={e.id} type="button" onClick={() => toggle(e.id)} className="w-full flex items-center justify-between px-3 py-1.5 text-sm hover:bg-zinc-50 dark:hover:bg-zinc-800" data-testid={`ppm-eng-${e.id}`}>
              <span>{e.full_name}{e.open_cases != null ? <span className="text-zinc-400"> · {e.open_cases} open</span> : ''}</span>
              {engIds.includes(e.id) && <Check size={14} className="text-emerald-600" />}
            </button>
          ))}
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
