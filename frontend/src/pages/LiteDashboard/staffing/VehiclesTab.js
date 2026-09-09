/**
 * VehiclesTab — HR/manager fleet register + weekly check register.
 * Assign vehicles to staff drivers + a check type; review submitted weekly
 * checks; export for Health & Safety. Reuses staff_members (drivers) and
 * engineer vehicle_reg (import) — no data is duplicated.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Truck, Plus, ShieldAlert, FileDown, Link2, Loader2, X, Check, Trash2 } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const token = () => (typeof window !== 'undefined' ? localStorage.getItem('token') : '');
const CHECK_LABEL = { van_maintenance: 'Van Maintenance', vehicle_check: 'Vehicle Check' };
const STATUS_TONE = {
  due: '#F59E0B', in_progress: '#0EA5E9', submitted: '#10B981', reviewed: '#10B981',
};
const fmtD = (s) => (s ? new Date(s + (s?.length === 10 ? 'T00:00:00' : '')).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : '—');

export default function VehiclesTab({ headers }) {
  const [view, setView] = useState('register'); // 'register' | 'checks'
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
          {[['register', 'Fleet register'], ['checks', 'Weekly checks'], ['defects', 'Defects']].map(([id, lab]) => (
            <button key={id} onClick={() => setView(id)} data-testid={`vehicles-view-${id}`}
              className="px-4 py-1.5 text-xs font-semibold"
              style={view === id ? { background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' } : { color: 'var(--theme-text-muted)' }}>{lab}</button>
          ))}
        </div>
        {view === 'register' && (
          <div className="flex gap-2">
            <button onClick={() => setImportOpen(true)} data-testid="vehicles-import-btn" className="inline-flex items-center gap-1 text-xs font-semibold rounded-full px-3 py-1.5 border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}><Link2 size={13} /> Import from engineers</button>
            <button onClick={() => setEdit({})} data-testid="vehicles-add-btn" className="inline-flex items-center gap-1 text-xs font-semibold rounded-full px-3 py-1.5" style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-ink)' }}><Plus size={13} /> Add vehicle</button>
          </div>
        )}
      </div>

      {view === 'register' ? (
        <FleetRegister data={data} onEdit={setEdit} onChanged={load} headers={headers} />
      ) : view === 'checks' ? (
        <WeeklyChecks headers={headers} week={data.week_commencing} onOpen={setDetail} />
      ) : (
        <DefectTracker headers={headers} />
      )}

      {edit && <VehicleModal vehicle={edit} drivers={drivers} headers={headers} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />}
      {importOpen && <ImportModal headers={headers} onClose={() => setImportOpen(false)} onDone={() => { setImportOpen(false); load(); }} />}
      {detail && <CheckDetailModal checkId={detail} headers={headers} onClose={() => setDetail(null)} onReviewed={() => setDetail(null)} />}
    </div>
  );
}

function FleetRegister({ data, onEdit, onChanged, headers }) {
  const del = async (id) => { if (!window.confirm('Remove this vehicle from the register?')) return; await axios.delete(`${API}/vehicles/${id}`, { headers }); onChanged(); };
  if (!data.vehicles.length) return <div className="rounded-xl border p-10 text-center text-sm" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>No vehicles yet. Add one or import from engineer profiles.</div>;
  return (
    <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--theme-border)' }} data-testid="vehicles-register">
      <table className="w-full text-sm">
        <thead><tr className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
          <th className="text-left py-2 px-3">Reg</th><th className="text-left py-2 px-3">Make/Model</th>
          <th className="text-left py-2 px-3">Check type</th><th className="text-left py-2 px-3">Drivers</th>
          <th className="text-left py-2 px-3">This week</th><th className="w-20" /></tr></thead>
        <tbody>
          {data.vehicles.map((v) => (
            <tr key={v.id} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`vehicle-reg-${v.id}`}>
              <td className="py-2 px-3 font-bold uppercase" style={{ color: 'var(--theme-text)' }}>{v.reg_no}{v.is_ev && <span className="ml-1 text-[9px] px-1 rounded bg-emerald-100 text-emerald-700">EV</span>}</td>
              <td className="py-2 px-3" style={{ color: 'var(--theme-text-muted)' }}>{v.make_model || '—'}</td>
              <td className="py-2 px-3 text-xs uppercase tracking-wide" style={{ color: 'var(--theme-text-muted)' }}>{CHECK_LABEL[v.check_type]}</td>
              <td className="py-2 px-3 text-xs" style={{ color: 'var(--theme-text-muted)' }}>{(v.driver_names || []).join(', ') || <span className="text-amber-600">Unassigned</span>}</td>
              <td className="py-2 px-3">
                <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full" style={{ background: `${STATUS_TONE[v.this_week?.status] || '#94a3b8'}22`, color: STATUS_TONE[v.this_week?.status] || '#94a3b8' }} data-testid={`vehicle-week-${v.id}`}>
                  {v.this_week?.has_defects && <ShieldAlert size={11} />}
                  {{ due: 'Due', in_progress: 'In progress', submitted: 'Submitted', reviewed: 'Reviewed' }[v.this_week?.status] || 'Due'}
                </span>
              </td>
              <td className="py-2 px-3 text-right whitespace-nowrap">
                <button onClick={() => onEdit(v)} data-testid={`vehicle-edit-${v.id}`} className="text-[11px] font-semibold underline mr-2" style={{ color: 'var(--color-brand-cyan)' }}>Edit</button>
                <button onClick={() => del(v.id)} data-testid={`vehicle-del-${v.id}`} className="text-slate-400 hover:text-rose-500"><Trash2 size={13} /></button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WeeklyChecks({ headers, week, onOpen }) {
  const [wk, setWk] = useState(week);
  const [rows, setRows] = useState(null);
  const load = useCallback(() => { axios.get(`${API}/vehicle-checks/register?week=${wk}`, { headers }).then((r) => setRows(r.data.checks || [])).catch(() => setRows([])); }, [wk, headers]);
  useEffect(() => { load(); }, [load]);
  const exportCsv = async () => {
    const r = await axios.get(`${API}/vehicle-checks/export.csv?week=${wk}`, { headers, responseType: 'blob' });
    const url = URL.createObjectURL(r.data); const a = document.createElement('a'); a.href = url; a.download = `vehicle-checks-${wk}.csv`; a.click();
  };
  return (
    <div className="space-y-3" data-testid="vehicles-checks">
      <div className="flex items-center gap-2 flex-wrap">
        <input type="date" value={wk} onChange={(e) => setWk(e.target.value)} data-testid="vehicles-week" className="rounded-lg px-3 py-1.5 text-sm border" style={{ background: 'var(--theme-bg)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }} />
        <span className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Week commencing (any date in the week)</span>
        <button onClick={exportCsv} data-testid="vehicles-export" className="ml-auto inline-flex items-center gap-1 text-xs font-semibold rounded-full px-3 py-1.5 border" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}><FileDown size={13} /> Export CSV</button>
      </div>
      {!rows ? <Loader2 className="animate-spin" style={{ color: 'var(--color-brand-cyan)' }} /> : rows.length === 0 ? (
        <div className="rounded-xl border p-10 text-center text-sm" style={{ borderColor: 'var(--theme-border)', color: 'var(--theme-text-muted)' }}>No checks submitted for this week yet.</div>
      ) : (
        <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--theme-border)' }}>
          <table className="w-full text-sm">
            <thead><tr className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>
              <th className="text-left py-2 px-3">Reg</th><th className="text-left py-2 px-3">Driver</th>
              <th className="text-left py-2 px-3">Status</th><th className="text-left py-2 px-3">Defects</th><th className="w-16" /></tr></thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`check-row-${c.id}`}>
                  <td className="py-2 px-3 font-bold uppercase" style={{ color: 'var(--theme-text)' }}>{c.details?.reg_no}</td>
                  <td className="py-2 px-3" style={{ color: 'var(--theme-text-muted)' }}>{c.driver_name}</td>
                  <td className="py-2 px-3"><span className="text-[11px] font-semibold px-2 py-0.5 rounded-full" style={{ background: `${STATUS_TONE[c.status] || '#94a3b8'}22`, color: STATUS_TONE[c.status] || '#94a3b8' }}>{c.status}</span></td>
                  <td className="py-2 px-3">{c.has_defects ? <span className="inline-flex items-center gap-1 text-rose-600 text-xs font-semibold"><ShieldAlert size={13} /> {c.defect?.safe_to_drive === false ? 'Not safe' : 'Yes'}</span> : <span className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>None</span>}</td>
                  <td className="py-2 px-3 text-right"><button onClick={() => onOpen(c.id)} data-testid={`check-open-${c.id}`} className="text-[11px] font-semibold underline" style={{ color: 'var(--color-brand-cyan)' }}>Open</button></td>
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
                  <div className="flex items-center gap-2">
                    <span className="font-bold uppercase" style={{ color: 'var(--theme-text)' }}>{d.reg_no}</span>
                    {d.safe_to_drive === false && <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-rose-600"><ShieldAlert size={12} /> Not safe</span>}
                    <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full" style={{ background: `${DEFECT_TONE[d.status]}22`, color: DEFECT_TONE[d.status] }}>{DEFECT_LABEL[d.status]}</span>
                  </div>
                  <p className="text-sm mt-1" style={{ color: 'var(--theme-text)' }}>{d.details || 'No description provided.'}</p>
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

function Modal({ children, onClose, testId, wide }) {
  return (
    <div className="fixed inset-0 z-[300] flex items-center justify-center bg-black/50 p-4" onClick={onClose} data-testid={testId}>
      <div className={`w-full ${wide ? 'max-w-2xl' : 'max-w-lg'} max-h-[85vh] overflow-y-auto rounded-2xl bg-white p-5 shadow-2xl`} onClick={(e) => e.stopPropagation()}>{children}</div>
    </div>
  );
}

function VehicleModal({ vehicle, drivers, headers, onClose, onSaved }) {
  const isNew = !vehicle.id;
  const [f, setF] = useState({
    reg_no: vehicle.reg_no || '', make_model: vehicle.make_model || '',
    check_type: vehicle.check_type || 'vehicle_check', is_ev: !!vehicle.is_ev,
    provider: vehicle.provider || '', driver_staff_ids: vehicle.driver_staff_ids || [],
    primary_driver_staff_id: vehicle.primary_driver_staff_id || null,
    odometer: vehicle.odometer || '', service_record: vehicle.service_record || {},
    notes: vehicle.notes || '',
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const sr = f.service_record || {};
  const setSr = (k, v) => setF((p) => ({ ...p, service_record: { ...p.service_record, [k]: v } }));
  const toggleDriver = (id) => setF((p) => {
    const has = p.driver_staff_ids.includes(id);
    const ids = has ? p.driver_staff_ids.filter((x) => x !== id) : [...p.driver_staff_ids, id];
    return { ...p, driver_staff_ids: ids, primary_driver_staff_id: ids.includes(p.primary_driver_staff_id) ? p.primary_driver_staff_id : ids[0] || null };
  });
  const save = async () => {
    if (!f.reg_no.trim()) { setErr('Registration is required.'); return; }
    setBusy(true); setErr('');
    try {
      if (isNew) await axios.post(`${API}/vehicles`, f, { headers });
      else await axios.patch(`${API}/vehicles/${vehicle.id}`, f, { headers });
      onSaved();
    } catch (e) { setErr(e?.response?.data?.detail || 'Save failed.'); setBusy(false); }
  };
  return (
    <Modal onClose={onClose} testId="vehicle-modal" wide>
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-bold text-slate-900 flex items-center gap-2"><Truck size={18} /> {isNew ? 'Add vehicle' : 'Edit vehicle'}</h3>
        <button onClick={onClose} className="text-slate-400"><X size={18} /></button>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
        <label className="block"><span className="text-xs text-slate-500">Registration *</span>
          <input value={f.reg_no} onChange={(e) => setF((p) => ({ ...p, reg_no: e.target.value }))} data-testid="vm-reg" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 uppercase" /></label>
        <label className="block"><span className="text-xs text-slate-500">Make / model</span>
          <input value={f.make_model} onChange={(e) => setF((p) => ({ ...p, make_model: e.target.value }))} data-testid="vm-model" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" /></label>
        <label className="block"><span className="text-xs text-slate-500">Check type</span>
          <select value={f.check_type} onChange={(e) => setF((p) => ({ ...p, check_type: e.target.value }))} data-testid="vm-check-type" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2">
            <option value="vehicle_check">Vehicle Check (company car/van)</option>
            <option value="van_maintenance">Van Maintenance (Vanarama)</option>
          </select></label>
        <div className="flex items-end gap-4">
          <label className="inline-flex items-center gap-2 text-sm"><input type="checkbox" checked={f.is_ev} onChange={(e) => setF((p) => ({ ...p, is_ev: e.target.checked }))} data-testid="vm-ev" className="h-4 w-4" /> Electric vehicle</label>
        </div>
        <label className="block"><span className="text-xs text-slate-500">Provider / garage</span>
          <input value={f.provider} onChange={(e) => setF((p) => ({ ...p, provider: e.target.value }))} placeholder={f.check_type === 'van_maintenance' ? 'Vanarama' : ''} data-testid="vm-provider" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" /></label>
        <label className="block"><span className="text-xs text-slate-500">Odometer</span>
          <input value={f.odometer} onChange={(e) => setF((p) => ({ ...p, odometer: e.target.value }))} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" /></label>
      </div>

      <div className="mt-4">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Assign drivers</span>
        <div className="mt-2 max-h-40 overflow-y-auto rounded-lg border border-slate-200 divide-y divide-slate-100" data-testid="vm-drivers">
          {drivers.map((s) => {
            const on = f.driver_staff_ids.includes(s.id);
            return (
              <div key={s.id} className="flex items-center justify-between px-3 py-2">
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <input type="checkbox" checked={on} onChange={() => toggleDriver(s.id)} data-testid={`vm-driver-${s.id}`} className="h-4 w-4" />
                  <span className="text-slate-700">{s.full_name}</span>
                  {s.department && <span className="text-[11px] text-slate-400">· {s.department}</span>}
                </label>
                {on && (
                  <button onClick={() => setF((p) => ({ ...p, primary_driver_staff_id: s.id }))} className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${f.primary_driver_staff_id === s.id ? 'bg-cyan-100 text-cyan-700' : 'text-slate-400 border border-slate-200'}`}>
                    {f.primary_driver_staff_id === s.id ? 'Primary ✓' : 'Set primary'}
                  </button>
                )}
              </div>
            );
          })}
        </div>
        <p className="text-[11px] text-slate-400 mt-1">The primary driver's registration is written back to their engineer profile automatically.</p>
      </div>

      <details className="mt-4">
        <summary className="text-xs font-semibold text-slate-500 cursor-pointer">Service / MOT / legal record (optional)</summary>
        <div className="grid grid-cols-2 gap-3 mt-2 text-sm">
          {[['next_service', 'Next service'], ['mot_due', 'MOT due'], ['tax_status', 'Tax status'], ['insurance_expiry', 'Insurance expiry'], ['mileage_due', 'Mileage due'], ['service_ref', 'Service ref.']].map(([k, lab]) => (
            <label key={k} className="block"><span className="text-xs text-slate-500">{lab}</span>
              <input value={sr[k] || ''} onChange={(e) => setSr(k, e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" /></label>
          ))}
        </div>
      </details>

      {err && <div className="mt-3 text-xs text-rose-600" data-testid="vm-error">{err}</div>}
      <div className="mt-4 flex justify-end gap-2">
        <button onClick={onClose} className="px-3 py-2 rounded-lg text-sm font-semibold text-slate-600 border border-slate-200">Cancel</button>
        <button onClick={save} disabled={busy} data-testid="vm-save" className="px-4 py-2 rounded-lg text-sm font-bold text-slate-900" style={{ background: 'var(--color-brand-cyan)' }}>{busy ? 'Saving…' : 'Save vehicle'}</button>
      </div>
    </Modal>
  );
}

function ImportModal({ headers, onClose, onDone }) {
  const [cands, setCands] = useState(null);
  const [sel, setSel] = useState({});
  const [busy, setBusy] = useState(false);
  useEffect(() => { axios.get(`${API}/vehicles/import-candidates`, { headers }).then((r) => setCands(r.data.candidates || [])).catch(() => setCands([])); }, [headers]);
  const doImport = async () => {
    setBusy(true);
    const items = (cands || []).filter((c) => sel[c.reg_no]).map((c) => ({ reg_no: c.reg_no, staff_id: c.staff_id, check_type: 'van_maintenance' }));
    await axios.post(`${API}/vehicles/import`, { items }, { headers });
    onDone();
  };
  return (
    <Modal onClose={onClose} testId="vehicle-import-modal">
      <div className="flex items-center justify-between mb-3"><h3 className="font-bold text-slate-900 flex items-center gap-2"><Link2 size={18} /> Import from engineer profiles</h3><button onClick={onClose} className="text-slate-400"><X size={18} /></button></div>
      {!cands ? <Loader2 className="animate-spin text-cyan-500" /> : cands.length === 0 ? (
        <div className="text-sm text-slate-500 py-6 text-center">No engineer registrations to import — everything's already in the register.</div>
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
          <div className="text-xs text-slate-500">{d.driver_name} · week {fmtD(d.week_commencing)} · {CHECK_LABEL[d.check_type]}</div></div>
        <button onClick={onClose} className="text-slate-400"><X size={18} /></button>
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
