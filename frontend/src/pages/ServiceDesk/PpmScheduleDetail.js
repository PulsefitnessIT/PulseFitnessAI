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

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

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
  const visits = data?.visits || [];

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
              <div className="rounded-lg border border-zinc-200 dark:border-zinc-700 divide-y divide-zinc-100 dark:divide-zinc-800 max-h-52 overflow-auto" data-testid="ppm-detail-machines">
                {(data?.machines || []).length === 0 ? (
                  <p className="px-3 py-2 text-xs text-zinc-400">No machines linked to this site.</p>
                ) : data.machines.map((m) => (
                  <div key={m.id} className="px-3 py-2 text-sm flex items-center justify-between gap-2">
                    <span className="min-w-0"><span className="font-medium truncate block">{m.name}</span>
                      {m.serial_number ? <span className="text-[10px] text-zinc-400 font-mono">SN {m.serial_number}</span> : null}</span>
                    {m.equipment_type ? <span className="text-[10px] text-zinc-500 bg-zinc-100 dark:bg-zinc-800 rounded px-1.5 py-0.5 shrink-0">{m.equipment_type}</span> : null}
                  </div>
                ))}
              </div>
            </div>

            {visits.length > 0 && <VisitsPanel visits={visits} />}
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

function VisitsPanel({ visits }) {
  const [active, setActive] = useState(0);
  const v = visits[active] || {};
  const dateLabel = (x) => (x.completed_at || x.scheduled_at || x.assigned_at
    ? fmtDate(x.completed_at || x.scheduled_at || x.assigned_at) : 'Visit');
  const stage = v.acknowledged_at ? 'acknowledged' : (v.received_at ? 'received' : 'allocated');
  const stageMap = {
    allocated: ['Allocated', 'bg-amber-100 text-amber-700'],
    received: ['Received', 'bg-sky-100 text-sky-700'],
    acknowledged: ['Acknowledged', 'bg-emerald-100 text-emerald-700'],
  };
  const [stLabel, stCls] = stageMap[stage];
  const calibMachines = v.calibration?.machines || [];
  return (
    <div data-testid="ppm-detail-visits">
      <p className="text-xs font-bold uppercase tracking-wide text-zinc-400 mb-1.5 flex items-center gap-1.5">
        <CheckCircle2 size={13} /> Engineer's workings
      </p>
      {visits.length > 1 && (
        <div className="flex gap-1 flex-wrap mb-2" data-testid="ppm-visit-tabs">
          {visits.map((x, i) => (
            <button key={x.case_id || i} onClick={() => setActive(i)} data-testid={`ppm-visit-tab-${i}`}
              className={`text-[11px] font-semibold px-2.5 py-1 rounded-full border ${i === active ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-white dark:bg-zinc-900 text-zinc-600 border-zinc-200 dark:border-zinc-700'}`}>
              {dateLabel(x)}{x.completed ? '' : ' ·'}
            </button>
          ))}
        </div>
      )}
      <div className="rounded-lg border border-emerald-200 dark:border-emerald-900 bg-emerald-50/50 dark:bg-emerald-950/20 p-3">
        <div className="flex items-center gap-1.5 flex-wrap mb-1.5">
          <span className={`text-[10px] font-bold uppercase tracking-wide rounded-full px-2 py-0.5 ${stCls}`} data-testid={`ppm-receipt-stage-${stage}`}>{stLabel}</span>
          {!v.completed && <span className="text-[10px] text-zinc-400">{v.status || 'in progress'}</span>}
          {v.received_at ? <span className="text-[10px] text-zinc-400">seen {fmtDate(v.received_at)}</span> : null}
          {v.acknowledged_at ? <span className="text-[10px] text-zinc-400">· ack {fmtDate(v.acknowledged_at)}</span> : null}
        </div>
        <div className="text-xs space-y-1 text-zinc-700 dark:text-zinc-300">
          {v.reference ? <p><span className="text-zinc-400">Job:</span> {v.reference}</p> : null}
          {v.engineer ? <p><span className="text-zinc-400">Engineer:</span> {v.engineer}</p> : null}
          {v.scheduled_at ? <p><span className="text-zinc-400">Visit date:</span> {fmtDate(v.scheduled_at)}</p> : null}
          {v.completed_at ? <p><span className="text-zinc-400">Completed:</span> {fmtDate(v.completed_at)}</p> : null}
          {v.summary ? <p className="pt-1 whitespace-pre-wrap">{v.summary}</p> : null}
        </div>

        {(v.machine_work || []).length > 0 && (
          <div className="mt-2.5">
            <p className="text-[10px] font-bold uppercase tracking-wide text-zinc-400 mb-1">Machines worked ({v.machine_work.length})</p>
            <div className="rounded-lg border border-zinc-200 dark:border-zinc-700 divide-y divide-zinc-100 dark:divide-zinc-800 max-h-56 overflow-auto" data-testid="ppm-visit-machine-work">
              {v.machine_work.map((mw, i) => (
                <div key={i} className="px-2.5 py-1.5" data-testid={`ppm-visit-machine-${i}`}>
                  <div className="flex items-start justify-between gap-2">
                    <span className="min-w-0">
                      <span className="text-xs font-semibold text-zinc-800 dark:text-zinc-100 block truncate">{mw.asset_name || 'Machine'}</span>
                      <span className="text-[10px] text-zinc-400">
                        {mw.asset_type ? mw.asset_type : ''}{mw.asset_type && mw.asset_serial ? ' · ' : ''}{mw.asset_serial ? `SN ${mw.asset_serial}` : ''}
                      </span>
                    </span>
                    <span className="flex items-center gap-1 shrink-0">
                      {mw.serviced ? <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Serviced</span> : null}
                      {mw.cleaned ? <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-full bg-sky-100 text-sky-700">Cleaned</span> : null}
                    </span>
                  </div>
                  {mw.notes ? <p className="text-[11px] text-zinc-500 mt-0.5 whitespace-pre-wrap">{mw.notes}</p> : null}
                </div>
              ))}
            </div>
          </div>
        )}

        {(v.calibration_captured || calibMachines.length > 0 || (v.calibration?.readings || []).length > 0) && (
          <div className="mt-2.5" data-testid="ppm-visit-calibration">
            <p className="text-[10px] font-bold uppercase tracking-wide text-zinc-400 mb-1">
              Treadmill calibration {v.calibration_result ? `· ${String(v.calibration_result).toUpperCase()}` : ''}
            </p>
            {calibMachines.length > 0 ? (
              <div className="space-y-2">
                {calibMachines.map((m, mi) => (
                  <div key={mi} className="rounded-lg border border-zinc-200 dark:border-zinc-700 p-2" data-testid={`ppm-calib-machine-${mi}`}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[11px] font-bold">{m.equipment_name || 'Treadmill'}{m.serial ? ` · SN ${m.serial}` : ''}</span>
                      <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-full ${m.overall_result === 'fail' ? 'bg-rose-100 text-rose-700' : 'bg-emerald-100 text-emerald-700'}`}>{String(m.overall_result || 'pass').toUpperCase()}</span>
                    </div>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
                      {(m.readings || []).map((r, ri) => (
                        <div key={ri} className="flex items-center justify-between text-[10px]">
                          <span className="text-zinc-500 truncate">{r.label}</span>
                          <span className={r.result === 'fail' ? 'text-rose-600 font-semibold' : 'text-zinc-700 dark:text-zinc-300'}>{r.measured || '—'}{r.result === 'fail' ? ' ✗' : ''}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (v.calibration?.readings || []).length > 0 ? (
              <div className="rounded-lg border border-zinc-200 dark:border-zinc-700 p-2 grid grid-cols-2 gap-x-3 gap-y-0.5">
                {v.calibration.readings.map((r, ri) => (
                  <div key={ri} className="flex items-center justify-between text-[10px]">
                    <span className="text-zinc-500 truncate">{r.label}</span>
                    <span className={r.result === 'fail' ? 'text-rose-600 font-semibold' : 'text-zinc-700 dark:text-zinc-300'}>{r.measured || '—'}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-zinc-500">Calibration captured.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

