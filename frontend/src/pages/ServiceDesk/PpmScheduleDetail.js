/**
 * PPM visit detail — opens when a calendar shell is clicked.
 * Shows the site, every machine involved, and (once the job is completed) the
 * engineer's workings. Offers Allocate / Delete actions.
 */
import { useEffect, useState } from 'react';
import { Loader2, X, MapPin, Wrench, CheckCircle2, Trash2, CalendarClock, User } from 'lucide-react';
import { api } from '@/lib/api';
import { notify } from '@/components/notifications';
import { Button } from '@/components/ui/button';

const fmtDate = (d) => (d ? new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—');

export default function PpmScheduleDetail({ scheduleId, onClose, onAllocate, onDeleted }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try { const r = await api.get(`/svc/ppm/schedules/${scheduleId}`); setData(r.data); }
      catch { notify.error('Could not load the visit'); onClose?.(); }
      finally { setLoading(false); }
    })();
  }, [scheduleId]);

  const del = async () => {
    if (!window.confirm('Delete this PM visit from the calendar?')) return;
    setDeleting(true);
    try {
      const r = await api.post('/svc/ppm/schedules/delete', { schedule_ids: [scheduleId] });
      notify.success(`Removed ${r.data?.deleted || 1} visit`);
      await onDeleted?.();
    } catch { notify.error('Could not delete the visit'); }
    finally { setDeleting(false); }
  };

  const s = data?.schedule;
  const w = data?.workings;

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }} data-testid="ppm-detail">
      <div className="bg-white dark:bg-zinc-900 rounded-2xl border border-zinc-200 dark:border-zinc-800 w-full max-w-lg max-h-[92vh] flex flex-col shadow-2xl">
        <div className="px-5 py-3.5 border-b border-zinc-200 dark:border-zinc-800 flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="text-base font-bold truncate" data-testid="ppm-detail-site">{s?.site_name || 'Maintenance visit'}</h3>
            <p className="text-xs text-zinc-500 truncate">{s?.customer_name || ''}{s?.service_type ? ` · ${s.service_type}` : ''}</p>
          </div>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-700 shrink-0" data-testid="ppm-detail-close"><X size={18} /></button>
        </div>

        {loading ? (
          <div className="p-10 text-center"><Loader2 className="animate-spin mx-auto text-zinc-400" /></div>
        ) : (
          <div className="p-5 overflow-auto flex-1 space-y-4">
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="flex items-center gap-2"><CalendarClock size={14} className="text-zinc-400" /><span>{fmtDate(s?.date)}</span></div>
              <div className="flex items-center gap-2"><Wrench size={14} className="text-zinc-400" /><span>{s?.machine_count || 0} machine(s)</span></div>
              {s?.engineer ? <div className="flex items-center gap-2 col-span-2"><User size={14} className="text-zinc-400" /><span>{s.engineer}</span></div> : null}
              {s?.site_address ? <div className="flex items-start gap-2 col-span-2"><MapPin size={14} className="text-zinc-400 mt-0.5" /><span className="text-zinc-500">{s.site_address}</span></div> : null}
            </div>

            <div>
              <p className="text-xs font-bold uppercase tracking-wide text-zinc-400 mb-1.5">Machines on site</p>
              {(data?.machines || []).length === 0 ? (
                <p className="text-xs text-zinc-400">No machines linked to this site.</p>
              ) : (
                <div className="rounded-lg border border-zinc-200 dark:border-zinc-700 divide-y divide-zinc-100 dark:divide-zinc-800 max-h-52 overflow-auto" data-testid="ppm-detail-machines">
                  {data.machines.map((m) => (
                    <div key={m.id} className="px-3 py-2 text-sm flex items-center justify-between gap-2">
                      <span className="min-w-0"><span className="font-medium truncate block">{m.name}</span>
                        {m.serial_number ? <span className="text-[10px] text-zinc-400 font-mono">SN {m.serial_number}</span> : null}</span>
                      {m.equipment_type ? <span className="text-[10px] text-zinc-500 bg-zinc-100 dark:bg-zinc-800 rounded px-1.5 py-0.5 shrink-0">{m.equipment_type}</span> : null}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {w && (
              <div className="rounded-lg border border-emerald-200 dark:border-emerald-900 bg-emerald-50/50 dark:bg-emerald-950/20 p-3" data-testid="ppm-detail-workings">
                <p className="text-xs font-bold uppercase tracking-wide text-emerald-700 mb-1.5 flex items-center gap-1.5">
                  <CheckCircle2 size={13} /> Engineer's workings {w.completed ? '' : `· ${w.status || 'in progress'}`}
                </p>
                <div className="text-xs space-y-1 text-zinc-700 dark:text-zinc-300">
                  {w.reference ? <p><span className="text-zinc-400">Job:</span> {w.reference}</p> : null}
                  {w.engineer ? <p><span className="text-zinc-400">Engineer:</span> {w.engineer}</p> : null}
                  {w.completed_at ? <p><span className="text-zinc-400">Completed:</span> {fmtDate(w.completed_at)}</p> : null}
                  {w.calibration_captured ? <p><span className="text-zinc-400">Calibration:</span> {String(w.calibration_result || '').toUpperCase() || 'captured'}</p> : null}
                  {w.summary ? <p className="pt-1">{w.summary}</p> : null}
                  {(w.machine_work || []).length > 0 && (
                    <div className="pt-1.5 space-y-0.5">
                      {w.machine_work.map((mw, i) => (
                        <p key={i} className="text-[11px]"><span className="font-medium">{mw.asset_name}</span>{mw.serviced ? ' · serviced' : ''}{mw.cleaned ? ' · cleaned' : ''}{mw.notes ? ` — ${mw.notes}` : ''}</p>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {!loading && (
          <div className="px-5 py-3.5 border-t border-zinc-200 dark:border-zinc-800 flex items-center justify-between gap-2">
            <Button variant="outline" size="sm" onClick={del} disabled={deleting} data-testid="ppm-detail-delete"
              className="text-rose-600 border-rose-200 hover:bg-rose-50 dark:hover:bg-rose-950/30">
              {deleting ? <Loader2 size={13} className="animate-spin mr-1.5" /> : <Trash2 size={13} className="mr-1.5" />} Delete visit
            </Button>
            {!w?.completed && (
              <Button size="sm" onClick={() => onAllocate?.(s)} data-testid="ppm-detail-allocate"
                className="bg-[var(--color-brand-cyan)] text-[var(--color-ink)]">
                Allocate engineer &amp; date
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
