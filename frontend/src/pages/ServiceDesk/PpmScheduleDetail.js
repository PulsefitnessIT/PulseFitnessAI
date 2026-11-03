/**
 * PPM visit detail — opens when a calendar shell is clicked.
 * Shows the site, every machine involved, and (once the job is completed) the
 * engineer's workings. Offers Allocate / Delete actions.
 */
import { useEffect, useState } from 'react';
import { Loader2, X, MapPin, Wrench, CheckCircle2, Trash2, CalendarClock, User, Printer } from 'lucide-react';
import { api } from '@/lib/api';
import { notify } from '@/components/notifications';
import { Button } from '@/components/ui/button';

const fmtDate = (d) => (d ? new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—');

// Classify a calibration reading as 'speed' or 'incline' (explicit type → label → unit).
const axisOf = (r) => {
  const t = String(r?.type || '').toLowerCase();
  if (t === 'speed' || t === 'incline') return t;
  const l = String(r?.label || '').toLowerCase();
  const u = String(r?.unit || '').toLowerCase();
  if (l.includes('incline') || u === '%') return 'incline';
  return 'speed';
};
// Human-friendly set-point label (strip "Speed — "/"Incline — " prefix; fall back to target+unit).
const humanizeReading = (r) => {
  let lbl = String(r?.label || '').replace(/^(speed|incline)\s*[—–-]\s*/i, '').trim();
  if (!lbl) lbl = r?.target ? `${r.target}${r.unit ? ` ${r.unit}` : ''}` : '';
  return lbl || '—';
};

const MW_COLS = '<colgroup><col style="width:30%"/><col style="width:15%"/><col style="width:17%"/><col style="width:10%"/><col style="width:10%"/><col style="width:18%"/></colgroup>';

function buildReportHtml(data) {
  const s = data?.schedule || {};
  const machines = data?.machines || [];
  const visits = data?.visits || [];
  const esc = (x) => String(x ?? '').replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  const yn = (b) => (b ? '✓' : '—');
  const calibHtml = (readings) => {
    const sp = readings.filter((r) => axisOf(r) === 'speed');
    const inc = readings.filter((r) => axisOf(r) === 'incline');
    const sect = (title, rows) => (rows.length ? `<div class="cal"><div class="calh">${title}</div><table class="rt fx"><colgroup><col style="width:45%"/><col style="width:35%"/><col style="width:20%"/></colgroup><tr><th>Set point</th><th>Measured</th><th>Result</th></tr>${rows.map((r) => `<tr><td>${esc(humanizeReading(r))}</td><td>${esc(r.measured || '—')}</td><td class="${r.result === 'fail' ? 'fail' : 'pass'}">${esc((r.result || 'pass').toUpperCase())}</td></tr>`).join('')}</table></div>` : '');
    return sect('Speed (mph)', sp) + sect('Incline (%)', inc);
  };
  const workedKeys = new Set(visits.flatMap((v) => (v.machine_work || []).flatMap((m) => [m.asset_serial, m.asset_name].filter(Boolean).map((x) => String(x).toLowerCase()))));
  const unworked = machines.filter((m) => ![m.serial_number, m.name].filter(Boolean).some((x) => workedKeys.has(String(x).toLowerCase())));
  const visitsHtml = visits.map((v, vi) => {
    const cm = (v.calibration?.machines || []).filter((m) => (m.readings || []).length);
    const flat = v.calibration?.readings || [];
    const extra = vi === 0 ? unworked.map((m) => `<tr><td>${esc(m.name)}</td><td>${esc(m.equipment_type || '')}</td><td>${esc(m.serial_number || '')}</td><td>—</td><td>—</td><td>Not serviced</td></tr>`).join('') : '';
    const mw = (v.machine_work || []).map((m) => `<tr><td>${esc(m.asset_name)}</td><td>${esc(m.asset_type || '')}</td><td>${esc(m.asset_serial || '')}</td><td>${yn(m.serviced)}</td><td>${yn(m.cleaned)}</td><td>${esc(m.notes || '')}</td></tr>`).join('') + extra;
    const calib = cm.length
      ? cm.map((m) => `<div class="cm"><div class="cmh">${esc(m.equipment_name || 'Treadmill')}${m.serial ? ` · SN ${esc(m.serial)}` : ''} — <b>${esc((m.overall_result || 'pass').toUpperCase())}</b></div>${calibHtml(m.readings || [])}</div>`).join('')
      : (flat.length ? calibHtml(flat) : '');
    return `<div class="visit">
      <h3>Visit — ${esc(fmtDate(v.scheduled_at || v.completed_at))} ${v.reference ? `(Job ${esc(v.reference)})` : ''}</h3>
      <p class="meta">Engineer: ${esc(v.engineer || '—')} · Status: ${esc(v.status || '—')}${v.completed_at ? ` · Completed ${esc(fmtDate(v.completed_at))}` : ''}</p>
      ${v.summary ? `<p class="summary">${esc(v.summary)}</p>` : ''}
      ${mw ? `<h4>Machines worked</h4><table class="rt fx">${MW_COLS}<tr><th>Machine</th><th>Type</th><th>Serial</th><th>Serviced</th><th>Cleaned</th><th>Notes</th></tr>${mw}</table>` : ''}
      ${calib ? `<h4>Treadmill calibration${v.calibration_result ? ` · ${esc(String(v.calibration_result).toUpperCase())}` : ''}</h4>${calib}` : ''}
    </div>`;
  }).join('');
  return `<!doctype html><html><head><meta charset="utf-8"><title>Service report — ${esc(s.site_name || '')}</title>
  <style>
    body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#111;margin:32px;font-size:12px}
    h1{font-size:20px;margin:0 0 2px} h2{font-size:13px;margin:16px 0 6px;color:#555;text-transform:uppercase;letter-spacing:.04em}
    h3{font-size:14px;margin:14px 0 2px} h4{font-size:12px;margin:10px 0 4px;color:#444}
    .sub{color:#666;margin:0 0 12px} .meta{color:#666;margin:2px 0 6px} .summary{margin:4px 0;white-space:pre-wrap}
    table.rt{border-collapse:collapse;width:100%;margin:4px 0 8px} .rt th,.rt td{border:1px solid #ddd;padding:4px 7px;text-align:left;font-size:11px}
    .rt th{background:#f5f5f5;font-weight:700} .fail{color:#b00020;font-weight:700} .pass{color:#0a7d33}
    .visit{border-top:2px solid #eee;padding-top:8px;margin-top:10px} .cal{margin:4px 0} .calh{font-weight:700;font-size:11px;color:#333;margin:4px 0 2px}
    .cm{border:1px solid #eee;border-radius:6px;padding:6px 8px;margin:6px 0} .cmh{font-weight:700;font-size:11px;margin-bottom:3px}
    .foot{margin-top:24px;color:#5B6570;font-size:9px;border-top:1px solid #C9D4E5;padding-top:8px}
    table.lh{width:100%;border-collapse:collapse;border-bottom:2px solid #0B3D91;margin-bottom:10px} .lh td{vertical-align:top;padding:0 0 8px}
    .co{text-align:right;font-size:10px;color:#5B6570;line-height:1.45}
    h1.ttl{font-size:28px;margin:10px 0 10px}
    .boxes{display:grid;grid-template-columns:1fr 1fr;gap:12px;align-items:stretch}
    .bx{border:1px solid #000;padding:6px 8px;min-height:64px;line-height:1.5;box-sizing:border-box}
    table.fx{table-layout:fixed} .fx td,.fx th{overflow-wrap:anywhere}
    .ilogos{display:flex;align-items:center;gap:12px} .imod{height:50px;border-left:1px solid #C9D4E5;padding-left:12px}
    table.ref{width:100%;border-collapse:collapse;margin:10px 0 4px;border:1px solid #000;table-layout:fixed} .ref th,.ref td{padding:4px 7px;text-align:left;font-size:11px;border-bottom:1px solid #000} .ref th{font-weight:700} .ref th:not(:first-child){border-left:1px solid #000}
    .ihdr{display:flex;justify-content:space-between;align-items:center;margin:0 0 10px}
    .ilogo{height:40px} .iaddr{height:50px}
    .gen{margin-top:18px;color:#5B6570;font-size:9px}
    table.pg{width:100%;border-collapse:collapse} table.pg>thead>tr>td,table.pg>tbody>tr>td,table.pg>tfoot>tr>td{padding:0;border:0}
    .ifoot img{display:block;width:100%;max-width:760px;margin-top:16px}
    .fspace{display:none}
    @media print{@page{size:A4;margin:8mm 0 0 0} body{margin:0 12mm}
      .fspace{display:block;height:38mm}
      .ifoot{position:fixed;left:0;right:0;bottom:0} .ifoot img{width:100%;max-width:none;margin:0}}
  </style></head><body>
  <table class="pg"><tbody><tr><td>
  <div class="ihdr"><div class="ilogos"><img class="ilogo" src="${window.location.origin}/brand/pulse-header-logo.png" alt="Pulse Fitness"/>${s.is_mod ? `<img class="imod" src="${window.location.origin}/brand/mod-badge.png" alt="Ministry of Defence"/>` : ''}</div><img class="iaddr" src="${window.location.origin}/brand/pulse-header-address.png" alt="Pulse Fitness, Part of The Pulse Group, Radnor Park, Greenfield Road, Congleton, Cheshire CW12 4TW. +44 (0)1260 294600, info@pulsefitness.com, www.pulsefitness.com"/></div>
  <h1 class="ttl">Service Report</h1>
  <div class="boxes">
    <div class="bx"><b>Customer / Site Address</b><br/>${[s.customer_name, s.site_name, s.site_address].filter(Boolean).map(esc).join('<br/>') || '—'}</div>
    <div class="bx"><b>Engineer</b><br/>${esc(visits[0]?.engineer || s.engineer || '—')}<br/>${esc(s.service_type || '')}</div>
  </div>
  <table class="ref"><tr><th>Scheduled</th><td>${esc(fmtDate(s.date))}</td><th>Service</th><td>${esc(s.service_type || '—')}</td><th>Machines</th><td>${machines.length}</td></tr>
    <tr><th>Visits</th><td>${visits.length}</td><th>Latest job</th><td>${esc(visits[0]?.reference || '—')}</td><th>Issued</th><td>${esc(new Date().toLocaleDateString('en-GB'))}</td></tr></table>
  <h2>Engineer's workings${visits.length > 1 ? ` (${visits.length} visits)` : ''}</h2>
  ${visitsHtml || `<p>No completed visits yet.</p>${machines.length ? `<h4>Machines</h4><table class="rt fx">${MW_COLS}<tr><th>Machine</th><th>Type</th><th>Serial</th><th>Serviced</th><th>Cleaned</th><th>Notes</th></tr>${machines.map((m) => `<tr><td>${esc(m.name)}</td><td>${esc(m.equipment_type || '')}</td><td>${esc(m.serial_number || '')}</td><td>—</td><td>—</td><td>Not serviced</td></tr>`).join('')}</table>` : ''}`}
  <p class="gen">Generated by PulseFitness.ai · ${esc(new Date().toLocaleString('en-GB'))}</p>
  </td></tr></tbody><tfoot><tr><td><div class="fspace"></div></td></tr></tfoot></table>
  <div class="ifoot"><img src="${window.location.origin}/brand/pulse-invoice-footer.png" alt="A pulseglobal Company. Registered Office: Pulse Fitness Limited, Radnor Park, Greenfield Road, Congleton, Cheshire, CW12 4TW. Company Registration No 4354059. VAT Registration No 785413509."/></div>
  </body></html>`;
}

function printReport(data) {
  const win = window.open('', '_blank', 'width=900,height=1000');
  if (!win) { notify.error('Please allow pop-ups to print the report'); return; }
  win.document.open();
  win.document.write(buildReportHtml(data));
  win.document.close();
  win.focus();
  setTimeout(() => { try { win.print(); } catch { /* user can print manually */ } }, 350);
}


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
            <div className="flex items-center gap-2">
              {visits.length > 0 && (
                <Button variant="outline" size="sm" onClick={() => printReport(data)} data-testid="ppm-detail-print">
                  <Printer size={13} className="mr-1.5" /> Print report
                </Button>
              )}
              {!w?.completed && (
                <Button size="sm" onClick={() => onAllocate?.(s)} data-testid="ppm-detail-allocate"
                  className="bg-[var(--color-brand-cyan)] text-[var(--color-ink)]">
                  Allocate engineer &amp; date
                </Button>
              )}
            </div>
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
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-[11px] font-bold">{m.equipment_name || 'Treadmill'}{m.serial ? ` · SN ${m.serial}` : ''}</span>
                      <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-full ${m.overall_result === 'fail' ? 'bg-rose-100 text-rose-700' : 'bg-emerald-100 text-emerald-700'}`}>{String(m.overall_result || 'pass').toUpperCase()}</span>
                    </div>
                    <CalibrationReadings readings={m.readings || []} testid={`ppm-calib-machine-${mi}`} />
                  </div>
                ))}
              </div>
            ) : (v.calibration?.readings || []).length > 0 ? (
              <div className="rounded-lg border border-zinc-200 dark:border-zinc-700 p-2">
                <CalibrationReadings readings={v.calibration.readings} testid="ppm-calib-flat" />
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


function CalibrationReadings({ readings, testid }) {
  const rows = readings || [];
  const speed = rows.filter((r) => axisOf(r) === 'speed');
  const incline = rows.filter((r) => axisOf(r) === 'incline');
  const Section = ({ title, items, tid }) => (items.length ? (
    <div className="mb-1.5" data-testid={tid}>
      <p className="text-[9px] font-extrabold uppercase tracking-wide text-zinc-400 mb-0.5">{title}</p>
      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
        {items.map((r, i) => (
          <div key={i} className="flex items-center justify-between text-[10px]">
            <span className="text-zinc-500 truncate">{humanizeReading(r)}</span>
            <span className={r.result === 'fail' ? 'text-rose-600 font-semibold' : 'text-zinc-700 dark:text-zinc-300'}>{r.measured || '—'}{r.result === 'fail' ? ' ✗' : ''}</span>
          </div>
        ))}
      </div>
    </div>
  ) : null);
  return (
    <div>
      <Section title="Speed (mph)" items={speed} tid={`${testid}-speed`} />
      <Section title="Incline (%)" items={incline} tid={`${testid}-incline`} />
    </div>
  );
}
