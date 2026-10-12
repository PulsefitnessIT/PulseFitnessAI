/**
 * VehiclesTab — HR/manager fleet register + weekly check register.
 * Assign vehicles to staff drivers + a check type; review submitted weekly
 * checks; export for Health & Safety. Reuses staff_members (drivers) and
 * engineer vehicle_reg (import) — no data is duplicated.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import { Truck, Plus, ShieldAlert, FileDown, FileText, FileArchive, Link2, Loader2, X, Check, Trash2 } from 'lucide-react';
import CrashPacksManager from './CrashPacksManager';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const token = () => (typeof window !== 'undefined' ? localStorage.getItem('token') : '');
const VEHICLE_TYPE_LABEL = { car: 'Car', electric_car: 'Electric Car', van: 'Van', electric_van: 'Electric Van', lorry: 'Lorry / HGV', van_maintenance: 'Van', vehicle_check: 'Car' };
const vtLabel = (v) => VEHICLE_TYPE_LABEL[v?.vehicle_type || v?.check_type] || 'Vehicle';

async function downloadCheckPdf(checkId, headers) {
  const r = await axios.get(`${API}/vehicle-checks/${checkId}/pdf`, { headers, responseType: 'blob' });
  const cd = r.headers['content-disposition'] || '';
  const m = cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  const name = m ? decodeURIComponent(m[1]) : `vehicle-check-${checkId}.pdf`;
  const url = URL.createObjectURL(r.data);
  const a = document.createElement('a'); a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}

const STATUS_TONE = {
  due: '#F59E0B', in_progress: '#0EA5E9', submitted: '#10B981', reviewed: '#10B981',
};
const fmtD = (s) => (s ? new Date(s + (s?.length === 10 ? 'T00:00:00' : '')).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : '—');

export default function VehiclesTab({ headers }) {
  const [view, setView] = useState('dashboard'); // 'dashboard' | 'register' | 'checks' | 'defects'
  const [data, setData] = useState(null);
  const [drivers, setDrivers] = useState([]);
  const [edit, setEdit] = useState(null); // vehicle being edited or {} for new
  const [importOpen, setImportOpen] = useState(false);
  const [detail, setDetail] = useState(null); // check detail id

  const load = useCallback(() => {
    axios.get(`${API}/vehicles`, { headers }).then((r) => setData(r.data)).catch(() => setData({ vehicles: [] }));
    axios.get(`${API}/vehicles/driver-options`, { headers }).then((r) => setDrivers(r.data.drivers || [])).catch(() => {});
  }, [headers]);
  useEffect(() => { load(); }, [load]);

  if (!data) return <div className="p-6"><Loader2 className="animate-spin" style={{ color: 'var(--color-brand-cyan)' }} /></div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="inline-flex rounded-lg overflow-hidden border" style={{ borderColor: 'var(--theme-border)' }}>
          {[['dashboard', 'Overview'], ['register', 'Fleet register'], ['checks', 'Weekly checks'], ['defects', 'Defects'], ['crash', 'Crash Packs']].map(([id, lab]) => (
            <button key={id} onClick={() => setView(id)} data-testid={`vehicles-view-${id}`}
              className="px-4 py-1.5 text-xs font-semibold"
              style={view === id ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' } : { color: 'var(--theme-text-muted)' }}>{lab}</button>
          ))}
        </div>
        {view === 'register' && (
          <div className="flex gap-2">
            <button onClick={() => setImportOpen(true)} data-testid="vehicles-import-btn" className="inline-flex items-center gap-1 text-xs font-semibold rounded-full px-3 py-1.5 border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}><Link2 size={13} /> Import Vehicle Details</button>
            <button onClick={async () => { const r = await axios.get(`${API}/vehicles/export.csv`, { headers, responseType: 'blob' }); const url = URL.createObjectURL(r.data); const a = document.createElement('a'); a.href = url; a.download = 'Fleet Register.csv'; a.click(); URL.revokeObjectURL(url); }} data-testid="vehicles-export-csv" className="inline-flex items-center gap-1 text-xs font-semibold rounded-full px-3 py-1.5 border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}><FileDown size={13} /> Export CSV</button>
            <button onClick={async () => { const r = await axios.get(`${API}/vehicles/export.pdf`, { headers, responseType: 'blob' }); const url = URL.createObjectURL(r.data); const a = document.createElement('a'); a.href = url; a.download = 'Fleet Register.pdf'; a.click(); URL.revokeObjectURL(url); }} data-testid="vehicles-export-pdf" className="inline-flex items-center gap-1 text-xs font-semibold rounded-full px-3 py-1.5 border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}><FileText size={13} /> Print / PDF</button>
            <button onClick={() => setEdit({})} data-testid="vehicles-add-btn" className="inline-flex items-center gap-1 text-xs font-semibold rounded-full px-3 py-1.5" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}><Plus size={13} /> Add vehicle</button>
          </div>
        )}
      </div>

      {view === 'register' ? (
        <FleetRegister data={data} onEdit={setEdit} onChanged={load} headers={headers} />
      ) : view === 'checks' ? (
        <WeeklyChecks headers={headers} week={data.week_commencing} onOpen={setDetail} />
      ) : view === 'defects' ? (
        <DefectTracker headers={headers} />
      ) : view === 'crash' ? (
        <CrashPacksManager headers={headers} />
      ) : (
        <FleetDashboard headers={headers} onGoto={setView} />
      )}

      {edit && <VehicleModal vehicle={edit} drivers={drivers} headers={headers} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />}
      {importOpen && <ImportModal headers={headers} onClose={() => setImportOpen(false)} onDone={() => { setImportOpen(false); load(); }} />}
      {detail && <CheckDetailModal checkId={detail} headers={headers} onClose={() => setDetail(null)} onReviewed={() => setDetail(null)} />}
    </div>
  );
}

function StatCard({ label, value, sub, tone, testId, onClick }) {
  return (
    <button onClick={onClick} disabled={!onClick} data-testid={testId}
      className="text-left rounded-xl border p-4 disabled:cursor-default hover:shadow-sm transition-shadow"
      style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
      <div className="text-[11px] font-semibold uppercase tracking-wide" style={{ color: 'var(--theme-text-muted)' }}>{label}</div>
      <div className="text-2xl font-bold mt-1" style={{ color: tone || 'var(--theme-text)' }}>{value}</div>
      {sub && <div className="text-[11px] mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>{sub}</div>}
    </button>
  );
}

function FleetDashboard({ headers, onGoto }) {
  const [d, setD] = useState(null);
  useEffect(() => { axios.get(`${API}/vehicle-checks/dashboard`, { headers }).then((r) => setD(r.data)).catch(() => setD({ total_vehicles: 0 })); }, [headers]);
  if (!d) return <Loader2 className="animate-spin" style={{ color: 'var(--color-brand-cyan)' }} />;
  if (!d.total_vehicles) return <div className="rounded-xl border p-10 text-center text-sm" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>No vehicles yet — add one in the Fleet register to start tracking compliance.</div>;

  const pctTone = d.checks_pct >= 90 ? '#16a34a' : d.checks_pct >= 60 ? '#d97706' : '#dc2626';
  const expTone = (days) => (days < 0 ? '#dc2626' : days <= 14 ? '#d97706' : 'var(--theme-text)');
  return (
    <div className="space-y-4" data-testid="vehicles-dashboard">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard testId="dash-checks-pct" label="Checks done this week" value={`${d.checks_pct}%`} tone={pctTone} sub={`${d.checks_done}/${d.total_vehicles} vehicles · ${d.checks_reviewed} reviewed`} onClick={() => onGoto('checks')} />
        <StatCard testId="dash-open-defects" label="Open defects" value={d.open_defects} tone={d.open_defects ? '#dc2626' : '#16a34a'} sub={`${d.booked_defects} booked in`} onClick={() => onGoto('defects')} />
        <StatCard testId="dash-not-safe" label="Flagged not safe" value={d.not_safe} tone={d.not_safe ? '#dc2626' : '#16a34a'} sub="unresolved" onClick={() => onGoto('defects')} />
        <StatCard testId="dash-expiries" label="Legal dates ≤60 days" value={d.expiries.length} tone={d.expiries.some((e) => e.days < 0) ? '#dc2626' : d.expiries.length ? '#d97706' : '#16a34a'} sub="MOT / tax / insurance / service / lease" />
      </div>

      <div className="rounded-xl border p-4" style={{ borderColor: 'var(--theme-border)' }} data-testid="dash-outstanding">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>Outstanding checks — week {fmtD(d.week_commencing)}</h3>
          <span className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>{d.outstanding.length} to complete</span>
        </div>
        {d.outstanding.length === 0 ? (
          <div className="text-sm inline-flex items-center gap-1" style={{ color: '#16a34a' }}><Check size={15} /> All vehicles checked this week.</div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {d.outstanding.map((o) => (
              <span key={o.id} className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }} data-testid={`dash-outstanding-${o.id}`}>
                <span className="font-bold uppercase" style={{ color: 'var(--theme-text)' }}>{o.reg_no}</span>
                {o.driver_names.length ? `· ${o.driver_names.join(', ')}` : '· unassigned'}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-xl border p-4" style={{ borderColor: 'var(--theme-border)' }} data-testid="dash-legal">
        <h3 className="text-sm font-bold mb-2" style={{ color: 'var(--theme-text)' }}>Upcoming MOT / tax / insurance / service / lease renewals</h3>
        {d.expiries.length === 0 ? (
          <div className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>Nothing due in the next 60 days.</div>
        ) : (
          <div className="space-y-1.5">
            {d.expiries.map((e, i) => (
              <div key={i} className="flex items-center justify-between gap-3 text-sm" data-testid={`dash-expiry-${i}`}>
                <span><span className="font-bold uppercase" style={{ color: 'var(--theme-text)' }}>{e.reg_no}</span> <span style={{ color: 'var(--theme-text-muted)' }}>· {e.kind}</span></span>
                <span className="font-semibold" style={{ color: expTone(e.days) }}>{e.days < 0 ? `Overdue ${-e.days}d` : e.days === 0 ? 'Due today' : `in ${e.days}d`} <span className="text-xs font-normal" style={{ color: 'var(--theme-text-muted)' }}>({e.date})</span></span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

const DEPARTMENTS = ['Management', 'Head Office', 'Installations', 'Service Engineers', 'Design & Build', 'Install'];

function Section({ title, children }) {
  return (
    <div className="rounded-xl border p-4" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-bg)' }}>
      <div className="text-[11px] font-bold uppercase tracking-wide mb-3" style={{ color: 'var(--color-brand-cyan)' }}>{title}</div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">{children}</div>
    </div>
  );
}
function TInput({ label, value, onChange, type = 'text', placeholder, upper, testid, span }) {
  return (
    <label className={`block ${span ? 'sm:col-span-2' : ''}`}>
      <span className="text-[11px] font-semibold" style={{ color: 'var(--theme-text-muted)' }}>{label}</span>
      <input type={type} value={value || ''} onChange={onChange} placeholder={placeholder}
        className={`mt-1 w-full rounded-lg border px-3 py-2 text-sm ${upper ? 'uppercase' : ''}`}
        style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
        data-testid={testid} />
    </label>
  );
}

function FleetRegister({ data, onEdit, onChanged, headers }) {
  const del = async (id, e) => { e.stopPropagation(); if (!window.confirm('Remove this vehicle from the register?')) return; await axios.delete(`${API}/vehicles/${id}`, { headers }); onChanged(); };
  if (!data.vehicles.length) return <div className="rounded-xl border p-10 text-center text-sm" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>No vehicles yet. Add one or import from engineer profiles.</div>;
  const groups = {};
  data.vehicles.forEach((v) => { const d = v.fleet_department || 'Unassigned department'; (groups[d] = groups[d] || []).push(v); });
  const order = Object.keys(groups).sort((a, b) => {
    const ia = DEPARTMENTS.indexOf(a), ib = DEPARTMENTS.indexOf(b);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib) || a.localeCompare(b);
  });
  return (
    <div className="space-y-5" data-testid="vehicles-register">
      {order.map((dep) => (
        <div key={dep} data-testid={`fleet-dept-${dep}`}>
          <div className="flex items-center gap-2 mb-2">
            <h3 className="text-xs font-bold uppercase tracking-wide" style={{ color: 'var(--color-brand-cyan)' }}>{dep}</h3>
            <span className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>{groups[dep].length} vehicle{groups[dep].length === 1 ? '' : 's'}</span>
          </div>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {groups[dep].map((v) => (
              <button key={v.id} onClick={() => onEdit(v)} data-testid={`vehicle-reg-${v.id}`}
                className="text-left rounded-xl border p-3 hover:shadow-md transition-shadow"
                style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="font-bold uppercase flex items-center gap-1.5" style={{ color: 'var(--theme-text)' }}>
                      {v.reg_no}
                      {v.is_ev && <span className="text-[9px] px-1 rounded bg-emerald-100 text-emerald-700">EV</span>}
                      {v.is_hybrid && <span className="text-[9px] px-1 rounded bg-amber-100 text-amber-700">HYB</span>}
                    </div>
                    <div className="text-xs truncate" style={{ color: 'var(--theme-text-muted)' }}>{v.make_model || vtLabel(v)}</div>
                  </div>
                  <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full shrink-0" style={{ background: `${STATUS_TONE[v.this_week?.status] || '#94a3b8'}22`, color: STATUS_TONE[v.this_week?.status] || '#94a3b8' }} data-testid={`vehicle-week-${v.id}`}>
                    {v.this_week?.has_defects && <ShieldAlert size={10} />}
                    {{ due: 'Due', in_progress: 'In progress', submitted: 'Submitted', reviewed: 'Reviewed' }[v.this_week?.status] || 'Due'}
                  </span>
                </div>
                <div className="mt-2 flex items-center justify-between gap-2">
                  <span className="text-xs truncate" style={{ color: 'var(--theme-text-muted)' }}>
                    {(v.driver_names || []).join(', ') || v.driver_label || <span className="text-amber-600">Unassigned</span>}
                  </span>
                  <span className="flex items-center gap-2 shrink-0">
                    {v.lease_end_date && <span className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>Lease {fmtD(v.lease_end_date)}</span>}
                    <span onClick={(e) => del(v.id, e)} data-testid={`vehicle-del-${v.id}`} className="text-slate-400 hover:text-rose-500 cursor-pointer"><Trash2 size={13} /></span>
                  </span>
                </div>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function WeeklyChecks({ headers, week, onOpen }) {
  const [wk, setWk] = useState(week);
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [rows, setRows] = useState(null);
  const ranged = !!(from || to);
  const load = useCallback(() => {
    const qs = ranged
      ? `?date_from=${from || ''}&date_to=${to || ''}`
      : `?week=${wk}`;
    axios.get(`${API}/vehicle-checks/register${qs}`, { headers })
      .then((r) => setRows(r.data.checks || [])).catch(() => setRows([]));
  }, [wk, from, to, ranged, headers]);
  useEffect(() => { load(); }, [load]);
  const exportCsv = async () => {
    const qs = ranged ? `?date_from=${from || ''}&date_to=${to || ''}` : `?week=${wk}`;
    const r = await axios.get(`${API}/vehicle-checks/export.csv${qs}`, { headers, responseType: 'blob' });
    const url = URL.createObjectURL(r.data); const a = document.createElement('a');
    a.href = url; a.download = `vehicle-checks-${ranged ? `${from || 'start'}_to_${to || 'now'}` : wk}.csv`; a.click();
  };
  const [zipBusy, setZipBusy] = useState(false);
  const exportZip = async () => {
    setZipBusy(true);
    try {
      const qs = ranged ? `?date_from=${from || ''}&date_to=${to || ''}` : `?week=${wk}`;
      const r = await axios.get(`${API}/vehicle-checks/export-zip${qs}`, { headers, responseType: 'blob' });
      const cd = r.headers['content-disposition'] || '';
      const m = cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
      const name = m ? decodeURIComponent(m[1]) : `Vehicle Checks - ${ranged ? `${from || 'start'} to ${to || 'now'}` : wk}.zip`;
      const url = URL.createObjectURL(r.data); const a = document.createElement('a');
      a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url);
    } catch (e) {
      alert(e?.response?.status === 404 ? 'No completed checks in this range.' : 'Could not build the ZIP.');
    } finally { setZipBusy(false); }
  };
  return (
    <div className="space-y-3" data-testid="vehicles-checks">
      <div className="flex items-end gap-2 flex-wrap">
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold" style={{ color: 'var(--theme-text-muted)' }}>Week commencing</span>
          <input type="date" value={wk} disabled={ranged} onChange={(e) => setWk(e.target.value)} data-testid="vehicles-week"
            className="rounded-lg px-3 py-1.5 text-sm border disabled:opacity-40"
            style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} />
        </label>
        <span className="pb-2 text-[11px] font-semibold" style={{ color: 'var(--theme-text-muted)' }}>or date range</span>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold" style={{ color: 'var(--theme-text-muted)' }}>From</span>
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} data-testid="vehicles-date-from"
            className="rounded-lg px-3 py-1.5 text-sm border"
            style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold" style={{ color: 'var(--theme-text-muted)' }}>To</span>
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} data-testid="vehicles-date-to"
            className="rounded-lg px-3 py-1.5 text-sm border"
            style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} />
        </label>
        {ranged && (
          <button onClick={() => { setFrom(''); setTo(''); }} data-testid="vehicles-range-clear"
            className="pb-2 text-[11px] font-semibold underline" style={{ color: 'var(--color-brand-cyan)' }}>Clear range</button>
        )}
        <button onClick={exportCsv} data-testid="vehicles-export" className="ml-auto inline-flex items-center gap-1 text-xs font-semibold rounded-full px-3 py-1.5 border self-end" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}><FileDown size={13} /> Export CSV</button>
        <button onClick={exportZip} disabled={zipBusy} data-testid="vehicles-export-zip" className="inline-flex items-center gap-1 text-xs font-semibold rounded-full px-3 py-1.5 self-end text-white disabled:opacity-60" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>{zipBusy ? <Loader2 size={13} className="animate-spin" /> : <FileArchive size={13} />} Download all PDFs (ZIP)</button>
      </div>
      {!rows ? <Loader2 className="animate-spin" style={{ color: 'var(--color-brand-cyan)' }} /> : rows.length === 0 ? (
        <div className="rounded-xl border p-10 text-center text-sm" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>{ranged ? 'No checks completed in this date range.' : 'No checks submitted for this week yet.'}</div>
      ) : (
        <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--theme-border)' }}>
          <table className="w-full text-sm">
            <thead><tr className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
              <th className="text-left py-2 px-3">Reg</th><th className="text-left py-2 px-3">Driver</th>
              <th className="text-left py-2 px-3">Completed</th>
              <th className="text-left py-2 px-3">Status</th><th className="text-left py-2 px-3">Defects</th><th className="w-16" /></tr></thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`check-row-${c.id}`}>
                  <td className="py-2 px-3 font-bold uppercase" style={{ color: 'var(--theme-text)' }}>{c.details?.reg_no}</td>
                  <td className="py-2 px-3" style={{ color: 'var(--theme-text-muted)' }}>{c.driver_name}</td>
                  <td className="py-2 px-3" style={{ color: 'var(--theme-text-muted)' }}>{c.submitted_at ? fmtD(c.submitted_at.slice(0, 10)) : '—'}</td>
                  <td className="py-2 px-3"><span className="text-[11px] font-semibold px-2 py-0.5 rounded-full" style={{ background: `${STATUS_TONE[c.status] || '#94a3b8'}22`, color: STATUS_TONE[c.status] || '#94a3b8' }}>{c.status}</span></td>
                  <td className="py-2 px-3">{c.has_defects ? <span className="inline-flex items-center gap-1 text-rose-600 text-xs font-semibold"><ShieldAlert size={13} /> {c.defect?.safe_to_drive === false ? 'Not safe' : 'Yes'}</span> : <span className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>None</span>}</td>
                  <td className="py-2 px-3 text-right whitespace-nowrap">
                    <button onClick={() => downloadCheckPdf(c.id, headers)} data-testid={`check-pdf-${c.id}`} title="Download PDF" className="inline-flex items-center gap-1 text-[11px] font-semibold mr-3" style={{ color: 'var(--theme-text-muted)' }}><FileDown size={13} /> PDF</button>
                    <button onClick={() => onOpen(c.id)} data-testid={`check-open-${c.id}`} className="text-[11px] font-semibold underline" style={{ color: 'var(--color-brand-cyan)' }}>Open</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const DEFECT_TONE = { open: '#dc2626', booked_in: '#d97706', resolved: '#16a34a' };
const DEFECT_LABEL = { open: 'Open', booked_in: 'Booked in', resolved: 'Resolved' };

function DefectTracker({ headers }) {
  const [status, setStatus] = useState('open');
  const [data, setData] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [booking, setBooking] = useState(null); // defect being booked-in
  const load = useCallback(() => {
    const qs = status === 'all' ? '' : `?status=${status}`;
    axios.get(`${API}/vehicle-defects${qs}`, { headers }).then((r) => setData(r.data)).catch(() => setData({ defects: [], counts: {} }));
  }, [status, headers]);
  useEffect(() => { load(); }, [load]);

  const setState = async (id, newStatus, extra = {}) => {
    setBusyId(id);
    try { await axios.patch(`${API}/vehicle-defects/${id}`, { status: newStatus, ...extra }, { headers }); setBooking(null); load(); }
    finally { setBusyId(null); }
  };

  const counts = data?.counts || {};
  return (
    <div className="space-y-3" data-testid="vehicles-defects">
      <div className="flex items-center gap-2 flex-wrap">
        {[['open', `Open (${counts.open ?? 0})`], ['booked_in', `Booked in (${counts.booked_in ?? 0})`], ['resolved', `Resolved (${counts.resolved ?? 0})`], ['all', 'All']].map(([id, lab]) => (
          <button key={id} onClick={() => setStatus(id)} data-testid={`defect-filter-${id}`}
            className="px-3 py-1.5 text-xs font-semibold rounded-full border"
            style={status === id ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)', borderColor: 'transparent' } : { borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>{lab}</button>
        ))}
      </div>
      {!data ? <Loader2 className="animate-spin" style={{ color: 'var(--color-brand-cyan)' }} /> : data.defects.length === 0 ? (
        <div className="rounded-xl border p-10 text-center text-sm" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>No {status === 'all' ? '' : DEFECT_LABEL[status]?.toLowerCase()} defects. 🎉</div>
      ) : (
        <div className="space-y-2">
          {data.defects.map((d) => (
            <div key={d.id} className="rounded-xl border p-4" style={{ borderColor: 'var(--theme-border)' }} data-testid={`defect-${d.id}`}>
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-bold uppercase" style={{ color: 'var(--theme-text)' }}>{d.reg_no}</span>
                    {(d.priority === 'critical' || d.escalated) && <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-full text-white" style={{ background: '#dc2626' }} data-testid={`defect-critical-${d.id}`}><ShieldAlert size={12} /> CRITICAL</span>}
                    {d.safe_to_drive === false && <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-rose-600"><ShieldAlert size={12} /> Not safe</span>}
                    <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full" style={{ background: `${DEFECT_TONE[d.status]}22`, color: DEFECT_TONE[d.status] }}>{DEFECT_LABEL[d.status]}</span>
                  </div>
                  <p className="text-sm mt-1 whitespace-pre-line" style={{ color: 'var(--theme-text)' }}>{d.details || 'No description provided.'}</p>
                  {(d.photo_ids || []).length > 0 && (
                    <div className="flex gap-2 mt-2 flex-wrap" data-testid={`defect-photos-${d.id}`}>
                      {d.photo_ids.map((fid) => (
                        <a key={fid} href={`${API}/vehicle-checks/photo/${fid}?auth=${token()}`} target="_blank" rel="noreferrer">
                          <img src={`${API}/vehicle-checks/photo/${fid}?auth=${token()}`} alt="defect" className="h-16 w-16 object-cover rounded-lg border" style={{ borderColor: 'var(--theme-border)' }} />
                        </a>
                      ))}
                    </div>
                  )}
                  <div className="text-[11px] mt-1" style={{ color: 'var(--theme-text-muted)' }}>
                    Reported by {d.reported_by || '—'}
                    {d.booking_ref && ` · Ref ${d.booking_ref}`}{d.booking_date && ` · Booked ${fmtD(d.booking_date)}`}
                    {d.resolved_note && ` · ${d.resolved_note}`}
                  </div>
                </div>
                <div className="flex gap-1.5 shrink-0">
                  {d.status === 'open' && (
                    <button onClick={() => setBooking(d)} disabled={busyId === d.id} data-testid={`defect-book-${d.id}`}
                      className="text-[11px] font-semibold rounded-full px-3 py-1.5 text-white" style={{ background: '#d97706' }}>Mark booked-in</button>
                  )}
                  {d.status !== 'resolved' && (
                    <button onClick={() => setState(d.id, 'resolved')} disabled={busyId === d.id} data-testid={`defect-resolve-${d.id}`}
                      className="inline-flex items-center gap-1 text-[11px] font-semibold rounded-full px-3 py-1.5 text-white bg-emerald-600">{busyId === d.id ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />} Resolve</button>
                  )}
                  {d.status === 'resolved' && (
                    <button onClick={() => setState(d.id, 'open')} disabled={busyId === d.id} data-testid={`defect-reopen-${d.id}`}
                      className="text-[11px] font-semibold rounded-full px-3 py-1.5 border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>Reopen</button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {booking && (
        <Modal onClose={() => setBooking(null)} testId="defect-booking-modal">
          <div className="flex items-center justify-between mb-3"><h3 className="font-bold text-slate-900">Book in repair — {booking.reg_no}</h3><button onClick={() => setBooking(null)} className="text-slate-400"><X size={18} /></button></div>
          <BookingForm onSubmit={(ref, dt) => setState(booking.id, 'booked_in', { booking_ref: ref, booking_date: dt })} />
        </Modal>
      )}
    </div>
  );
}

function BookingForm({ onSubmit }) {
  const [ref, setRef] = useState('');
  const [dt, setDt] = useState('');
  return (
    <div className="space-y-3 text-sm">
      <label className="block"><span className="text-xs text-slate-500">Provider / garage reference</span>
        <input value={ref} onChange={(e) => setRef(e.target.value)} data-testid="defect-booking-ref" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" placeholder="e.g. Vanarama ref" /></label>
      <label className="block"><span className="text-xs text-slate-500">Booking date</span>
        <input type="date" value={dt} onChange={(e) => setDt(e.target.value)} data-testid="defect-booking-date" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" /></label>
      <div className="flex justify-end"><button onClick={() => onSubmit(ref, dt)} data-testid="defect-booking-save" className="px-4 py-2 rounded-lg text-sm font-bold text-slate-900" style={{ background: 'var(--color-brand-cyan)' }}>Save booking</button></div>
    </div>
  );
}

function Modal({ children, onClose, testId, wide, themed }) {
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, []);
  return createPortal(
    <div className="fixed inset-0 z-[1000] flex items-start sm:items-center justify-center bg-black/60 p-4 overflow-y-auto" onClick={onClose} data-testid={testId}>
      <div className={`w-full ${wide ? 'max-w-3xl' : 'max-w-lg'} my-4 sm:my-8 max-h-[92vh] overflow-y-auto rounded-2xl p-5 shadow-2xl ${themed ? '' : 'bg-white'}`}
        style={themed ? { background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' } : undefined}
        onClick={(e) => e.stopPropagation()}>{children}</div>
    </div>,
    document.body,
  );
}

function DriverPicker({ value, drivers, onChange }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const ref = useRef(null);
  const selected = drivers.find((d) => d.id === value);
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);
  const ql = q.trim().toLowerCase();
  const filtered = ql
    ? drivers.filter((d) => (d.full_name || '').toLowerCase().includes(ql) || (d.department || '').toLowerCase().includes(ql) || (d.job_title || '').toLowerCase().includes(ql))
    : drivers;
  const pick = (id) => { onChange(id); setOpen(false); setQ(''); };
  return (
    <div className="relative mt-1" ref={ref}>
      <button type="button" onClick={() => setOpen((o) => !o)} data-testid="vm-driver-select"
        className="w-full flex items-center justify-between rounded-lg border px-3 py-2 text-sm text-left"
        style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', color: selected ? 'var(--theme-text)' : 'var(--theme-text-muted)' }}>
        <span className="truncate">{selected ? `${selected.full_name}${selected.department ? ` · ${selected.department}` : ''}` : '— Unassigned —'}</span>
        <span className="flex items-center gap-2 shrink-0">
          {selected && <X size={13} onClick={(e) => { e.stopPropagation(); pick(''); }} className="hover:text-rose-500" />}
          <span className="text-[10px]" style={{ color: 'var(--theme-text-muted)' }}>▾</span>
        </span>
      </button>
      {open && (
        <div className="absolute z-20 mt-1 w-full rounded-lg border shadow-xl"
          style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
          <div className="p-2 border-b" style={{ borderColor: 'var(--theme-border)' }}>
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search staff by name…" data-testid="vm-driver-search"
              className="w-full rounded-md border px-2.5 py-1.5 text-sm"
              style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} />
          </div>
          <div className="max-h-44 overflow-y-auto">
            <button type="button" onClick={() => pick('')} className="w-full text-left px-3 py-2 text-sm hover:opacity-70" style={{ color: 'var(--theme-text-muted)' }}>— Unassigned —</button>
            {filtered.length === 0 && <div className="px-3 py-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}>No staff match &ldquo;{q}&rdquo;.</div>}
            {filtered.map((d) => (
              <button key={d.id} type="button" onClick={() => pick(d.id)} data-testid={`vm-driver-option-${d.id}`}
                className="w-full text-left px-3 py-2 text-sm hover:opacity-70 flex items-center justify-between"
                style={{ color: 'var(--theme-text)', background: d.id === value ? 'var(--theme-bg)' : 'transparent' }}>
                <span className="truncate">{d.full_name}</span>
                {d.department && <span className="text-[11px] shrink-0 ml-2" style={{ color: 'var(--theme-text-muted)' }}>{d.department}</span>}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function VehicleModal({ vehicle, drivers, headers, onClose, onSaved }) {
  const isNew = !vehicle.id;
  const [f, setF] = useState({
    reg_no: vehicle.reg_no || '', make_model: vehicle.make_model || '',
    vehicle_type: vehicle.vehicle_type || vehicle.check_type || 'car',
    provider: vehicle.provider || '', driver_staff_ids: vehicle.driver_staff_ids || [],
    primary_driver_staff_id: vehicle.primary_driver_staff_id || null,
    driver_label: vehicle.driver_label || '',
    fleet_department: vehicle.fleet_department || '',
    lease_company: vehicle.lease_company || '',
    lease_end_date: vehicle.lease_end_date || '',
    fuel_card_number: vehicle.fuel_card_number || '',
    dart: vehicle.dart || '', congestion: vehicle.congestion || '', m6_toll: vehicle.m6_toll || '',
    odometer: vehicle.odometer || '', service_record: vehicle.service_record || {},
    notes: vehicle.notes || '',
    is_ev: vehicle.is_ev ?? ((vehicle.vehicle_type || vehicle.check_type || '').startsWith('electric')),
    is_hybrid: vehicle.is_hybrid ?? false,
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [fines, setFines] = useState(vehicle.fines || []);
  const [nf, setNf] = useState({ kind: '', date: '', value: '', paid: false, file_id: null });
  const [fineBusy, setFineBusy] = useState(false);
  const uploadFine = async (file) => {
    if (!file) return;
    setFineBusy(true);
    try {
      const fd = new FormData(); fd.append('file', file);
      const r = await axios.post(`${API}/vehicles/fine-upload`, fd, { headers: { ...headers, 'Content-Type': 'multipart/form-data' } });
      setNf((p) => ({ ...p, file_id: r.data.file_id }));
    } catch { setErr('Fine document upload failed.'); } finally { setFineBusy(false); }
  };
  const addFine = async () => {
    if (!nf.kind.trim()) { setErr('Enter the fine type first.'); return; }
    setFineBusy(true); setErr('');
    try {
      const r = await axios.post(`${API}/vehicles/${vehicle.id}/fines`, nf, { headers });
      setFines((p) => [...p, r.data]); setNf({ kind: '', date: '', value: '', paid: false, file_id: null });
    } catch (e) { setErr(e?.response?.data?.detail || 'Could not add fine.'); } finally { setFineBusy(false); }
  };
  const toggleFine = async (fid, paid) => {
    await axios.patch(`${API}/vehicles/${vehicle.id}/fines/${fid}`, { paid }, { headers });
    setFines((p) => p.map((f) => (f.id === fid ? { ...f, paid } : f)));
  };
  const delFine = async (fid) => {
    if (!window.confirm('Remove this fine?')) return;
    await axios.delete(`${API}/vehicles/${vehicle.id}/fines/${fid}`, { headers });
    setFines((p) => p.filter((f) => f.id !== fid));
  };
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
  const sr = f.service_record || {};
  const setSr = (k, v) => setF((p) => ({ ...p, service_record: { ...p.service_record, [k]: v } }));
  const save = async () => {
    if (!f.reg_no.trim()) { setErr('Registration is required.'); return; }
    setBusy(true); setErr('');
    try {
      if (isNew) await axios.post(`${API}/vehicles`, f, { headers });
      else await axios.patch(`${API}/vehicles/${vehicle.id}`, f, { headers });
      onSaved();
    } catch (e) { setErr(e?.response?.data?.detail || 'Save failed.'); setBusy(false); }
  };
  const cellStyle = { background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' };
  return (
    <Modal onClose={onClose} testId="vehicle-modal" wide themed>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2 min-w-0">
          <span className="rounded-xl p-2" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}><Truck size={18} /></span>
          <div className="min-w-0">
            <h3 className="font-bold uppercase truncate" style={{ color: 'var(--theme-text)' }}>{f.reg_no || (isNew ? 'Add vehicle' : 'Vehicle')}</h3>
            <div className="text-xs truncate" style={{ color: 'var(--theme-text-muted)' }}>{f.make_model || vtLabel(f)}{f.fleet_department ? ` · ${f.fleet_department}` : ''}</div>
          </div>
        </div>
        <button onClick={onClose} style={{ color: 'var(--theme-text-muted)' }}><X size={18} /></button>
      </div>

      <div className="space-y-3">
        <Section title="Vehicle details">
          <TInput label="Registration *" value={f.reg_no} onChange={(e) => set('reg_no', e.target.value)} upper testid="vm-reg" />
          <TInput label="Make / model" value={f.make_model} onChange={(e) => set('make_model', e.target.value)} testid="vm-model" />
          <label className="block">
            <span className="text-[11px] font-semibold" style={{ color: 'var(--theme-text-muted)' }}>Vehicle type</span>
            <select value={f.vehicle_type} onChange={(e) => set('vehicle_type', e.target.value)} data-testid="vm-vehicle-type"
              className="mt-1 w-full rounded-lg border px-3 py-2 text-sm" style={cellStyle}>
              <option value="car">Car</option><option value="electric_car">Electric Car</option>
              <option value="van">Van</option><option value="electric_van">Electric Van</option><option value="lorry">Lorry / HGV</option>
            </select>
          </label>
          <label className="block">
            <span className="text-[11px] font-semibold" style={{ color: 'var(--theme-text-muted)' }}>Department</span>
            <input list="fleet-departments" value={f.fleet_department} onChange={(e) => set('fleet_department', e.target.value)} placeholder="e.g. Service Engineers" data-testid="vm-department"
              className="mt-1 w-full rounded-lg border px-3 py-2 text-sm" style={cellStyle} />
            <datalist id="fleet-departments">{DEPARTMENTS.map((d) => <option key={d} value={d} />)}</datalist>
          </label>
          <TInput label="Odometer" value={f.odometer} onChange={(e) => set('odometer', e.target.value)} />
          <div className="sm:col-span-2 flex flex-wrap items-center gap-5" data-testid="vm-powertrain">
            <span className="text-[11px] font-semibold uppercase tracking-wide" style={{ color: 'var(--theme-text-muted)' }}>Powertrain</span>
            <label className="flex items-center gap-2 cursor-pointer" style={{ color: 'var(--theme-text)' }}>
              <input type="checkbox" checked={!!f.is_ev} onChange={(e) => set('is_ev', e.target.checked)} data-testid="vm-is-ev" className="h-4 w-4" /> Electric (EV)
            </label>
            <label className="flex items-center gap-2 cursor-pointer" style={{ color: 'var(--theme-text)' }}>
              <input type="checkbox" checked={!!f.is_hybrid} onChange={(e) => set('is_hybrid', e.target.checked)} data-testid="vm-is-hybrid" className="h-4 w-4" /> Hybrid
            </label>
            <span className="text-[11px] basis-full" style={{ color: 'var(--theme-text-muted)' }}>Tick EV to add the electric-vehicle section to the weekly checklist.</span>
          </div>
        </Section>

        <Section title="Assigned driver">
          <div className="sm:col-span-2">
            <span className="text-[11px] font-semibold" style={{ color: 'var(--theme-text-muted)' }}>Driver</span>
            <DriverPicker
              value={f.primary_driver_staff_id}
              drivers={drivers}
              onChange={(id) => setF((p) => ({ ...p, primary_driver_staff_id: id || null, driver_staff_ids: id ? [id] : [] }))}
            />
            {!f.primary_driver_staff_id && f.driver_label && (
              <p className="mt-1.5 text-[11px]" style={{ color: 'var(--theme-text-muted)' }} data-testid="vm-driver-hint">
                Imported driver: <span className="font-semibold" style={{ color: 'var(--theme-text)' }}>{f.driver_label}</span> — search above to link them to a staff member.
              </p>
            )}
          </div>
          <TInput label="Driver label (pool / leased / unlinked)" value={f.driver_label} onChange={(e) => set('driver_label', e.target.value)} placeholder="e.g. Pool Car, Leased, Install" span testid="vm-driver-label" />
        </Section>

        <Section title="Lease & finance">
          <TInput label="Lease / finance company" value={f.lease_company} onChange={(e) => set('lease_company', e.target.value)} placeholder="e.g. LEX Auto Lease" testid="vm-lease-company" />
          <TInput label="Lease end date" type="date" value={f.lease_end_date} onChange={(e) => set('lease_end_date', e.target.value)} testid="vm-lease-end" />
          <TInput label="Supplier / garage (repairs)" value={f.provider} onChange={(e) => set('provider', e.target.value)} placeholder="e.g. Vanarama" testid="vm-provider" span />
        </Section>

        <Section title="Fuel card & tolls">
          <TInput label="Fuel card number" value={f.fuel_card_number} onChange={(e) => set('fuel_card_number', e.target.value)} testid="vm-fuel-card" />
          <TInput label="DART Charge" value={f.dart} onChange={(e) => set('dart', e.target.value)} testid="vm-dart" />
          <TInput label="Congestion charge" value={f.congestion} onChange={(e) => set('congestion', e.target.value)} testid="vm-congestion" />
          <TInput label="M6 Toll" value={f.m6_toll} onChange={(e) => set('m6_toll', e.target.value)} testid="vm-m6" />
        </Section>

        <Section title="Legal & service">
          <TInput label="MOT due" type="date" value={sr.mot_due} onChange={(e) => setSr('mot_due', e.target.value)} testid="vm-mot" />
          <TInput label="Next service" type="date" value={sr.next_service} onChange={(e) => setSr('next_service', e.target.value)} testid="vm-next-service" />
          <TInput label="Insurance expiry" type="date" value={sr.insurance_expiry} onChange={(e) => setSr('insurance_expiry', e.target.value)} testid="vm-insurance" />
          <TInput label="Tax status" value={sr.tax_status} onChange={(e) => setSr('tax_status', e.target.value)} placeholder="e.g. Taxed / SORN" />
          <TInput label="Mileage due" value={sr.mileage_due} onChange={(e) => setSr('mileage_due', e.target.value)} />
          <TInput label="Service ref." value={sr.service_ref} onChange={(e) => setSr('service_ref', e.target.value)} />
        </Section>

        <Section title="Notes">
          <label className="block sm:col-span-2">
            <textarea value={f.notes} onChange={(e) => set('notes', e.target.value)} rows={2} data-testid="vm-notes" placeholder="Anything else worth recording…"
              className="w-full rounded-lg border px-3 py-2 text-sm" style={cellStyle} />
          </label>
        </Section>

        <Section title="Fines">
          {isNew ? (
            <div className="sm:col-span-2 text-xs" style={{ color: 'var(--theme-text-muted)' }}>Save the vehicle first, then reopen it to log fines.</div>
          ) : (
            <>
              <div className="sm:col-span-2 space-y-2" data-testid="vm-fines-list">
                {fines.length === 0 && <div className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>No fines logged.</div>}
                {fines.map((fi) => (
                  <div key={fi.id} className="flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-xs" style={{ borderColor: 'var(--theme-border)' }} data-testid={`vm-fine-${fi.id}`}>
                    <span style={{ color: 'var(--theme-text)' }}><span className="font-semibold">{fi.kind || 'Fine'}</span>{fi.date ? ` · ${fmtD(fi.date)}` : ''}{fi.value ? ` · £${fi.value}` : ''}</span>
                    <span className="flex items-center gap-2 shrink-0">
                      {fi.file_id && <a href={`${API}/vehicle-checks/photo/${fi.file_id}?auth=${token()}`} target="_blank" rel="noreferrer" className="underline" style={{ color: 'var(--color-brand-cyan)' }}>View</a>}
                      <button type="button" onClick={() => toggleFine(fi.id, !fi.paid)} data-testid={`vm-fine-toggle-${fi.id}`} className={`px-2 py-0.5 rounded-full font-semibold ${fi.paid ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>{fi.paid ? 'Paid' : 'Unpaid'}</button>
                      <button type="button" onClick={() => delFine(fi.id)} data-testid={`vm-fine-delete-${fi.id}`} className="text-slate-400 hover:text-rose-500"><Trash2 size={13} /></button>
                    </span>
                  </div>
                ))}
              </div>
              <TInput label="Fine type" value={nf.kind} onChange={(e) => setNf((p) => ({ ...p, kind: e.target.value }))} placeholder="e.g. Speeding, Parking, Bus lane" testid="vm-fine-kind" />
              <TInput label="Date" type="date" value={nf.date} onChange={(e) => setNf((p) => ({ ...p, date: e.target.value }))} testid="vm-fine-date" />
              <TInput label="Value (£)" value={nf.value} onChange={(e) => setNf((p) => ({ ...p, value: e.target.value }))} placeholder="e.g. 60" testid="vm-fine-value" />
              <div className="flex items-end gap-3">
                <label className="flex items-center gap-2 text-sm cursor-pointer" style={{ color: 'var(--theme-text)' }}>
                  <input type="checkbox" checked={nf.paid} onChange={(e) => setNf((p) => ({ ...p, paid: e.target.checked }))} data-testid="vm-fine-paid" className="h-4 w-4" /> Paid
                </label>
                <label className="inline-flex items-center gap-1 text-xs font-semibold rounded-lg px-3 py-2 border cursor-pointer" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} data-testid="vm-fine-upload-label">
                  {fineBusy ? <Loader2 size={13} className="animate-spin" /> : <FileDown size={13} className="rotate-180" />} {nf.file_id ? 'Scan attached' : 'Scan fine'}
                  <input type="file" accept="image/*,application/pdf" className="hidden" data-testid="vm-fine-file" onChange={(e) => uploadFine(e.target.files[0])} />
                </label>
              </div>
              <div className="sm:col-span-2 flex justify-end">
                <button type="button" onClick={addFine} disabled={fineBusy} data-testid="vm-fine-add" className="inline-flex items-center gap-1 text-xs font-bold rounded-full px-3 py-1.5" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}><Plus size={13} /> Add fine</button>
              </div>
            </>
          )}
        </Section>
      </div>

      {err && <div className="mt-3 text-xs text-rose-600" data-testid="vm-error">{err}</div>}
      <div className="mt-4 flex justify-end gap-2">
        <button onClick={onClose} className="px-3 py-2 rounded-lg text-sm font-semibold border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>Cancel</button>
        <button onClick={save} disabled={busy} data-testid="vm-save" className="px-4 py-2 rounded-lg text-sm font-bold" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}>{busy ? 'Saving…' : 'Save vehicle'}</button>
      </div>
    </Modal>
  );
}

function ImportModal({ headers, onClose, onDone }) {
  const [cands, setCands] = useState(null);
  const [sel, setSel] = useState({});
  const [busy, setBusy] = useState(false);
  const [csvResult, setCsvResult] = useState(null);
  const [csvErr, setCsvErr] = useState('');
  useEffect(() => { axios.get(`${API}/vehicles/import-candidates`, { headers }).then((r) => setCands(r.data.candidates || [])).catch(() => setCands([])); }, [headers]);
  const doImport = async () => {
    setBusy(true);
    const items = (cands || []).filter((c) => sel[c.reg_no]).map((c) => ({ reg_no: c.reg_no, staff_id: c.staff_id, vehicle_type: 'van' }));
    await axios.post(`${API}/vehicles/import`, { items }, { headers });
    onDone();
  };
  const downloadTemplate = async () => {
    const r = await axios.get(`${API}/vehicles/import-template.csv`, { headers, responseType: 'blob' });
    const url = URL.createObjectURL(r.data); const a = document.createElement('a'); a.href = url; a.download = 'vehicle-import-template.csv'; a.click(); URL.revokeObjectURL(url);
  };
  const uploadCsv = async (file) => {
    if (!file) return;
    setBusy(true); setCsvErr(''); setCsvResult(null);
    const fd = new FormData(); fd.append('file', file);
    try {
      const r = await axios.post(`${API}/vehicles/import-csv`, fd, { headers: { ...headers, 'Content-Type': 'multipart/form-data' } });
      setCsvResult(r.data);
    } catch (e) { setCsvErr(e?.response?.data?.detail || 'CSV import failed.'); }
    finally { setBusy(false); }
  };
  return (
    <Modal onClose={onClose} testId="vehicle-import-modal" wide>
      <div className="flex items-center justify-between mb-3"><h3 className="font-bold text-slate-900 flex items-center gap-2"><Link2 size={18} /> Import vehicles</h3><button onClick={onClose} className="text-slate-400"><X size={18} /></button></div>

      <div className="rounded-xl border border-slate-200 p-4 mb-4" data-testid="import-csv-block">
        <div className="font-semibold text-slate-800 text-sm mb-1">Bulk import from spreadsheet (CSV)</div>
        <p className="text-xs text-slate-500 mb-3">Download the template, fill in every column (reg, make/model, vehicle type, supplier, odometer, the driver's name and/or email, MOT/tax/insurance/service dates), then upload. Assign the vehicle to a person by putting their <strong>name</strong> in the <code>driver_names</code> column (or their email in <code>driver_emails</code>) — both are matched to your staff.</p>
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={downloadTemplate} data-testid="import-template-btn" className="inline-flex items-center gap-1 text-xs font-semibold rounded-full px-3 py-1.5 border border-slate-300 text-slate-700"><FileDown size={13} /> Download CSV template</button>
          <label className="inline-flex items-center gap-1 text-xs font-semibold rounded-full px-3 py-1.5 text-slate-900 cursor-pointer" style={{ background: 'var(--color-brand-cyan)' }} data-testid="import-csv-label">
            <Plus size={13} /> Upload CSV
            <input type="file" accept=".csv,text/csv" className="hidden" data-testid="import-csv-input" onChange={(e) => uploadCsv(e.target.files[0])} />
          </label>
        </div>
        {csvErr && <div className="mt-2 text-xs text-rose-600" data-testid="import-csv-error">{csvErr}</div>}
        {csvResult && (
          <div className="mt-3 text-xs" data-testid="import-csv-result">
            <div className="font-semibold text-emerald-700">Imported {csvResult.created} vehicle(s){csvResult.skipped ? `, skipped ${csvResult.skipped} duplicate(s)` : ''}.</div>
            {(csvResult.errors || []).length > 0 && <ul className="mt-1 list-disc pl-4 text-amber-700">{csvResult.errors.map((er, i) => <li key={i}>{er}</li>)}</ul>}
            <button onClick={onDone} className="mt-2 underline font-semibold" style={{ color: 'var(--color-brand-cyan)' }}>Done — refresh register</button>
          </div>
        )}
      </div>

      <div className="font-semibold text-slate-800 text-sm mb-2">Or link from engineer profiles</div>
      {!cands ? <Loader2 className="animate-spin text-cyan-500" /> : cands.length === 0 ? (
        <div className="text-sm text-slate-500 py-4 text-center">No engineer registrations to import — everything's already in the register.</div>
      ) : (
        <div className="space-y-2">
          {cands.map((c) => (
            <label key={c.reg_no} className="flex items-center gap-3 rounded-lg border border-slate-200 px-3 py-2 cursor-pointer" data-testid={`import-cand-${c.reg_no}`}>
              <input type="checkbox" checked={!!sel[c.reg_no]} onChange={(e) => setSel((p) => ({ ...p, [c.reg_no]: e.target.checked }))} className="h-4 w-4" />
              <span className="font-bold uppercase text-slate-800">{c.reg_no}</span>
              <span className="text-xs text-slate-400">{c.engineer_name}</span>
            </label>
          ))}
        </div>
      )}
      {cands && cands.length > 0 && (
        <div className="mt-4 flex justify-end"><button onClick={doImport} disabled={busy} data-testid="import-confirm" className="px-4 py-2 rounded-lg text-sm font-bold text-slate-900" style={{ background: 'var(--color-brand-cyan)' }}>Import selected</button></div>
      )}
    </Modal>
  );
}

function CheckDetailModal({ checkId, headers, onClose, onReviewed }) {
  const [d, setD] = useState(null);
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { axios.get(`${API}/vehicle-checks/${checkId}`, { headers }).then((r) => setD(r.data)).catch(() => {}); }, [checkId, headers]);
  const review = async () => { setBusy(true); await axios.post(`${API}/vehicle-checks/${checkId}/review`, { notes }, { headers }); onReviewed(); };
  if (!d) return <Modal onClose={onClose} testId="check-detail-modal"><Loader2 className="animate-spin text-cyan-500" /></Modal>;
  const df = d.defect || {};
  return (
    <Modal onClose={onClose} testId="check-detail-modal" wide>
      <div className="flex items-center justify-between mb-3">
        <div><h3 className="font-bold text-slate-900 uppercase">{d.details?.reg_no}</h3>
          <div className="text-xs text-slate-500">{d.driver_name} · week {fmtD(d.week_commencing)} · {vtLabel(d)}</div></div>
        <div className="flex items-center gap-2">
          <button onClick={() => downloadCheckPdf(checkId, headers)} data-testid="check-detail-pdf" className="inline-flex items-center gap-1 text-xs font-semibold rounded-full px-3 py-1.5 border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}><FileDown size={13} /> PDF</button>
          <button onClick={onClose} className="text-slate-400"><X size={18} /></button>
        </div>
      </div>
      {d.has_defects && (
        <div className="rounded-lg bg-rose-50 border border-rose-200 p-3 mb-3" data-testid="check-detail-defect">
          <div className="font-semibold text-rose-700 flex items-center gap-1"><ShieldAlert size={15} /> Defect reported {df.safe_to_drive === false && '· NOT SAFE TO DRIVE'}</div>
          {df.details && <p className="text-sm text-slate-700 mt-1">{df.details}</p>}
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-[11px] text-slate-500">
            <span>Manager told: {yn(df.manager_told)}</span><span>Provider contacted: {yn(df.provider_contacted)}</span><span>Repair booked: {yn(df.repair_booked)}</span>
          </div>
          {(d.photos?.defect || []).length > 0 && (
            <div className="flex gap-2 mt-2 flex-wrap">{d.photos.defect.map((fid) => (<img key={fid} src={`${API}/vehicle-checks/photo/${fid}?auth=${token()}`} alt="defect" className="h-16 w-16 object-cover rounded-lg border" />))}</div>
          )}
        </div>
      )}
      <div className="space-y-3 max-h-64 overflow-y-auto">
        {(d.template?.sections || []).map((s) => (
          <div key={s.key}>
            <div className="text-xs font-bold uppercase tracking-wide text-slate-400 mb-1">{s.title}</div>
            <div className="space-y-1">
              {s.items.map((it) => {
                const v = d.items?.[it.id];
                const c = v === 'defect' ? 'text-rose-600' : v === 'na' ? 'text-slate-400' : 'text-emerald-600';
                return <div key={it.id} className="flex items-center justify-between gap-3 text-xs"><span className="text-slate-600 flex-1">{it.label}</span><span className={`font-semibold uppercase ${c}`}>{v || '—'}</span></div>;
              })}
            </div>
          </div>
        ))}
      </div>
      {d.status === 'submitted' ? (
        <div className="mt-4 border-t border-slate-100 pt-3">
          <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Review note (optional)" data-testid="check-review-notes" className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          <div className="mt-2 flex justify-end"><button onClick={review} disabled={busy} data-testid="check-review-btn" className="inline-flex items-center gap-1 px-4 py-2 rounded-lg text-sm font-bold text-white bg-emerald-600">{busy ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Mark reviewed</button></div>
        </div>
      ) : d.manager_review ? (
        <div className="mt-4 text-xs text-emerald-700 border-t border-slate-100 pt-3">Reviewed by {d.manager_review.reviewer}{d.manager_review.notes ? ` — “${d.manager_review.notes}”` : ''}</div>
      ) : null}
    </Modal>
  );
}

const yn = (v) => (v === true ? 'Yes' : v === false ? 'No' : '—');
