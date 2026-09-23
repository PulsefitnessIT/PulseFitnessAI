/**
 * PayrollTimesheetsTab — payroll downloads each staff member's monthly
 * timesheet in the company Excel template (all formulas + yellow hand-in
 * cell), pre-filled from recorded hours. Filenames carry the staff name.
 * Payroll can also set the per-year hand-in schedule (auto-generated, editable).
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Loader2, Download, Save, CalendarDays, ClipboardList, RefreshCw, Package } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const surf = { background: 'var(--theme-surface)', border: '1px solid var(--theme-border)' };
const inp = { background: 'var(--theme-bg)', border: '1px solid var(--theme-border)', color: 'var(--theme-text)' };

export default function PayrollTimesheetsTab({ headers }) {
  const [year, setYear] = useState(new Date().getFullYear());
  const [sched, setSched] = useState(null);
  const [staff, setStaff] = useState([]);
  const [month, setMonth] = useState(1);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [packBusy, setPackBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [sc, st] = await Promise.all([
        axios.get(`${API}/staffing/timesheet-schedule`, { headers, params: { year } }),
        axios.get(`${API}/staffing/staff`, { headers }),
      ]);
      setSched(sc.data);
      const list = Array.isArray(st.data) ? st.data : (st.data.staff || []);
      setStaff(list.filter(s => s.active !== false));
    } catch { /* silent */ }
    finally { setLoading(false); }
  }, [headers, year]);
  useEffect(() => { load(); }, [load]);

  const patchMonth = (idx, key, val) => {
    setSched(s => ({ ...s, months: s.months.map((m, i) => i === idx ? { ...m, [key]: val } : m) }));
  };
  const saveSched = async () => {
    setSaving(true);
    try {
      const r = await axios.put(`${API}/staffing/timesheet-schedule`,
        { year, months: sched.months }, { headers });
      setSched({ ...sched, months: r.data.months, auto: false });
    } catch (e) { alert(e?.response?.data?.detail || 'Could not save the schedule.'); }
    finally { setSaving(false); }
  };
  const regenAuto = async () => {
    if (sched && !sched.auto && !window.confirm('Reload this year and discard unsaved edits?')) return;
    try {
      const r = await axios.get(`${API}/staffing/timesheet-schedule`, { headers, params: { year } });
      setSched(r.data);
    } catch { /* silent */ }
  };

  const dl = async (url, params, fallback) => {
    const r = await axios.get(`${API}${url}`, { headers, params, responseType: 'blob' });
    const cd = r.headers['content-disposition'] || '';
    const m = cd.match(/filename="?([^"]+)"?/);
    const a = document.createElement('a');
    a.href = URL.createObjectURL(r.data);
    a.download = (m ? m[1] : fallback);
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  };
  const downloadStaff = async (s) => {
    setBusyId(s.id);
    try { await dl('/staffing/timesheets/month-export', { staff_id: s.id, year, month }, `Timesheet ${s.full_name}.xlsx`); }
    catch (e) { alert(e?.response?.data?.detail || 'Download failed.'); }
    finally { setBusyId(null); }
  };
  const downloadPack = async () => {
    setPackBusy(true);
    try { await dl('/staffing/timesheets/month-pack', { year, month }, `Timesheets ${year}.zip`); }
    catch (e) { alert(e?.response?.data?.detail || 'Pack download failed.'); }
    finally { setPackBusy(false); }
  };

  if (loading) return <div className="flex items-center gap-2 p-6 text-sm" style={{ color: 'var(--theme-text-muted)' }}><Loader2 size={14} className="animate-spin" /> Loading timesheets…</div>;
  if (!sched) return <div className="p-6 text-sm" style={{ color: 'var(--theme-text-muted)' }}>Could not load the timesheet schedule.</div>;

  const months = sched.months || [];
  const cur = months.find(m => m.month === month) || months[0];
  const years = [year - 1, year, year + 1, year + 2];

  return (
    <div className="space-y-5" data-testid="payroll-timesheets-tab">
      {/* Download bar */}
      <div className="rounded-xl p-4" style={surf}>
        <div className="flex items-center gap-2 mb-3">
          <ClipboardList size={16} style={{ color: 'var(--theme-accent)' }} />
          <h3 className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>Monthly timesheets (Excel)</h3>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Year
            <select data-testid="ts-year" value={year} onChange={e => setYear(Number(e.target.value))}
              className="block mt-1 px-2 py-2 text-sm rounded-md" style={inp}>
              {years.map(y => <option key={y} value={y}>{y}</option>)}
            </select></label>
          <label className="text-xs" style={{ color: 'var(--theme-text-muted)' }}>Month
            <select data-testid="ts-month" value={month} onChange={e => setMonth(Number(e.target.value))}
              className="block mt-1 px-2 py-2 text-sm rounded-md" style={inp}>
              {months.map(m => <option key={m.month} value={m.month}>{`${m.label} · hand-in ${m.hand_in || '—'}`}</option>)}
            </select></label>
          <button data-testid="ts-download-pack" onClick={downloadPack} disabled={packBusy}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold disabled:opacity-50"
            style={{ background: 'var(--theme-accent)', color: '#fff' }}>
            {packBusy ? <Loader2 size={14} className="animate-spin" /> : <Package size={14} />} Download all (one file each)
          </button>
        </div>
        {cur && (
          <p className="text-[11px] mt-2" style={{ color: 'var(--theme-text-muted)' }}>
            {cur.label}: {cur.weeks} weeks from {cur.period_start} · yellow hand-in date {cur.hand_in}
          </p>
        )}
      </div>

      {/* Per-staff list */}
      <div className="rounded-xl overflow-hidden" style={surf} data-testid="ts-staff-list">
        {staff.length === 0 && <p className="text-sm text-center py-8" style={{ color: 'var(--theme-text-muted)' }}>No active staff.</p>}
        {staff.map(s => (
          <div key={s.id} className="flex items-center gap-3 px-4 py-2.5 border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`ts-staff-${s.id}`}>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>{s.full_name}</p>
              <p className="text-[11px]" style={{ color: 'var(--theme-text-muted)' }}>{s.department || s.primary_role || '—'} · {(s.hours_per_week || s.weekly_hours || 0)}h/wk</p>
            </div>
            <button data-testid={`ts-download-${s.id}`} onClick={() => downloadStaff(s)} disabled={busyId === s.id}
              className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-md disabled:opacity-50"
              style={{ background: 'transparent', color: 'var(--theme-text)', border: '1px solid var(--theme-border)' }}>
              {busyId === s.id ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />} {cur?.label} Excel
            </button>
          </div>
        ))}
      </div>

      {/* Hand-in schedule editor */}
      <div className="rounded-xl p-4" style={surf} data-testid="ts-schedule-editor">
        <div className="flex items-center gap-2 mb-1">
          <CalendarDays size={16} style={{ color: 'var(--theme-accent)' }} />
          <h3 className="text-sm font-bold" style={{ color: 'var(--theme-text)' }}>Timesheet hand-in schedule · {year}</h3>
          {sched.auto && <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded" style={{ background: 'var(--theme-accent)22', color: 'var(--theme-accent)' }}>Auto-generated</span>}
        </div>
        <p className="text-[11px] mb-3" style={{ color: 'var(--theme-text-muted)' }}>Set when each month's timesheets are due. The hand-in date is highlighted yellow on the sheet. Edit any month, then Save.</p>
        <div className="overflow-x-auto">
          <table className="w-full text-xs" style={{ color: 'var(--theme-text)' }}>
            <thead><tr style={{ color: 'var(--theme-text-muted)' }}>
              <th className="text-left py-1 pr-3">Month</th><th className="text-left py-1 pr-3">Period start (Mon)</th>
              <th className="text-left py-1 pr-3">Weeks</th><th className="text-left py-1 pr-3">Hand-in (yellow)</th>
            </tr></thead>
            <tbody>
              {months.map((m, i) => (
                <tr key={m.month} data-testid={`ts-sched-row-${m.month}`} className="border-t" style={{ borderColor: 'var(--theme-border)' }}>
                  <td className="py-1.5 pr-3 font-semibold">{m.label}</td>
                  <td className="py-1.5 pr-3">
                    <input data-testid={`ts-sched-start-${m.month}`} type="date" value={m.period_start || ''} onChange={e => patchMonth(i, 'period_start', e.target.value)}
                      className="px-2 py-1 rounded-md" style={inp} /></td>
                  <td className="py-1.5 pr-3">
                    <select data-testid={`ts-sched-weeks-${m.month}`} value={m.weeks} onChange={e => patchMonth(i, 'weeks', Number(e.target.value))}
                      className="px-2 py-1 rounded-md" style={inp}><option value={4}>4</option><option value={5}>5</option></select></td>
                  <td className="py-1.5 pr-3">
                    <input data-testid={`ts-sched-handin-${m.month}`} type="date" value={m.hand_in || ''} onChange={e => patchMonth(i, 'hand_in', e.target.value)}
                      className="px-2 py-1 rounded-md" style={inp} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex items-center gap-2 mt-3">
          <button data-testid="ts-sched-save" onClick={saveSched} disabled={saving}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold disabled:opacity-50" style={{ background: 'var(--theme-accent)', color: '#fff' }}>
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Save schedule
          </button>
          <button data-testid="ts-sched-regen" onClick={regenAuto}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold" style={{ background: 'transparent', color: 'var(--theme-text)', border: '1px solid var(--theme-border)' }}>
            <RefreshCw size={13} /> Reload {year}
          </button>
        </div>
      </div>
    </div>
  );
}
