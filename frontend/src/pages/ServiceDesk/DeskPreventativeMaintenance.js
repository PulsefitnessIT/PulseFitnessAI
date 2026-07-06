/**
 * Service Desk → Preventative Maintenance
 *
 * Operators schedule recurring PM visits per piece of customer equipment
 * (weekly / fortnightly / monthly / quarterly / 6-monthly / annual). Schedules
 * flow through to the
 * Operations portal's Preventative Maintenance page automatically. When a
 * PM falls due, the operator confirms it to spawn the engineer job.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarClock, Plus, Trash2, CheckCircle2, Loader2, Wrench, AlertTriangle } from 'lucide-react';
import { api } from '@/lib/api';
import { notify } from '@/components/notifications';

const FREQ_LABEL = { weekly: 'Weekly', fortnightly: 'Fortnightly', monthly: 'Monthly', quarterly: 'Quarterly', biannual: '6-monthly', annual: 'Annual' };

function fmtDate(d) {
  if (!d) return '—';
  try { return new Date(`${String(d).slice(0, 10)}T00:00:00`).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }); }
  catch { return d; }
}

export default function DeskPreventativeMaintenance() {
  const [schedules, setSchedules] = useState([]);
  const [due, setDue] = useState([]);
  const [equipment, setEquipment] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, d] = await Promise.all([
        api.get('/svc/pm/schedules'),
        api.get('/svc/pm/due', { params: { lead_days: 14 } }),
      ]);
      setSchedules(s.data?.schedules || []);
      setDue(d.data?.due || []);
    } catch (e) { notify.error('Could not load PM schedules'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const openAdd = async () => {
    setShowAdd(true);
    if (equipment.length === 0) {
      try {
        const r = await api.get('/svc/engineer/equipment', { params: { limit: 500 } });
        setEquipment(r.data?.equipment || r.data?.items || (Array.isArray(r.data) ? r.data : []));
      } catch { /* non-blocking */ }
    }
  };

  const confirmVisit = async (id) => {
    setBusyId(id);
    try {
      const r = await api.post(`/svc/pm/schedules/${id}/confirm`, {});
      notify.success(`Job ${r.data?.reference || ''} created · next PM ${fmtDate(r.data?.next_pm)}`);
      await load();
    } catch (e) { notify.error('Could not create the PM job'); }
    finally { setBusyId(null); }
  };

  const removeSchedule = async (id) => {
    setBusyId(id);
    try { await api.delete(`/svc/pm/schedules/${id}`); notify.success('PM schedule removed'); await load(); }
    catch { notify.error('Could not remove schedule'); }
    finally { setBusyId(null); }
  };

  return (
    <div className="space-y-6" data-testid="desk-pm-page">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-black text-zinc-900 dark:text-zinc-100 flex items-center gap-2">
            <CalendarClock size={20} /> Preventative Maintenance
          </h1>
          <p className="text-sm text-zinc-500 mt-0.5">Recurring PM visits per machine. Schedules also appear in the Operations Preventative Maintenance page.</p>
        </div>
        <button onClick={openAdd} className="inline-flex items-center gap-1.5 text-sm font-semibold px-3 py-2 rounded-lg bg-zinc-900 text-white dark:bg-white dark:text-zinc-900 hover:opacity-90" data-testid="pm-add-btn">
          <Plus size={15} /> Schedule PM
        </button>
      </div>

      {/* Due now */}
      <section className="rounded-xl border border-amber-300 bg-amber-50 dark:bg-amber-900/15 dark:border-amber-800/60 p-4" data-testid="pm-due-section">
        <p className="text-sm font-bold text-amber-900 dark:text-amber-200 flex items-center gap-2">
          <AlertTriangle size={15} /> Due / upcoming (next 14 days) · {due.length}
        </p>
        {due.length === 0 ? (
          <p className="text-xs text-amber-800/80 dark:text-amber-300/80 mt-1">Nothing due. You're all caught up.</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {due.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-3 bg-white dark:bg-zinc-900/40 rounded-lg px-3 py-2" data-testid={`pm-due-row-${s.id}`}>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 truncate">{s.equipment_name || 'Equipment'} <span className="text-zinc-400 font-normal">· {s.customer_name || '—'}</span></p>
                  <p className="text-xs text-zinc-500">Due {fmtDate(s.next_pm)} · {FREQ_LABEL[s.frequency] || s.frequency}</p>
                </div>
                <button onClick={() => confirmVisit(s.id)} disabled={busyId === s.id} className="shrink-0 inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50" data-testid={`pm-confirm-${s.id}`}>
                  {busyId === s.id ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />} Confirm &amp; create job
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* All schedules */}
      <section className="rounded-xl border border-zinc-200 dark:border-zinc-800 overflow-hidden">
        <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-800">
          <p className="text-sm font-bold text-zinc-900 dark:text-zinc-100">All PM schedules · {schedules.length}</p>
        </div>
        {loading ? (
          <div className="p-8 text-center text-zinc-400"><Loader2 className="animate-spin mx-auto" /></div>
        ) : schedules.length === 0 ? (
          <div className="p-8 text-center text-sm text-zinc-500" data-testid="pm-empty">
            <Wrench size={24} className="mx-auto opacity-40 mb-2" />
            No PM schedules yet. Use “Schedule PM” to set up recurring maintenance.
          </div>
        ) : (
          <table className="w-full text-sm" data-testid="pm-schedules-table">
            <thead className="bg-zinc-50 dark:bg-zinc-900/40 text-xs text-zinc-500">
              <tr>
                <th className="text-left font-semibold px-4 py-2">Equipment</th>
                <th className="text-left font-semibold px-4 py-2">Customer</th>
                <th className="text-left font-semibold px-4 py-2">Frequency</th>
                <th className="text-left font-semibold px-4 py-2">Last PM</th>
                <th className="text-left font-semibold px-4 py-2">Next PM</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {schedules.map((s) => (
                <tr key={s.id} className="border-t border-zinc-100 dark:border-zinc-800/60" data-testid={`pm-row-${s.id}`}>
                  <td className="px-4 py-2.5 font-medium text-zinc-900 dark:text-zinc-100">{s.equipment_name || '—'}</td>
                  <td className="px-4 py-2.5 text-zinc-600 dark:text-zinc-300">
                    {s.customer_name || '—'}
                    {s.customer_acknowledged && (
                      <span className="ml-2 inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-700 bg-emerald-100 dark:bg-emerald-900/40 dark:text-emerald-300 px-1.5 py-0.5 rounded-full" title={`Acknowledged${s.customer_acknowledged_by ? ` by ${s.customer_acknowledged_by}` : ''}`} data-testid={`pm-ack-${s.id}`}>
                        <CheckCircle2 size={10} /> Customer acknowledged
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">{FREQ_LABEL[s.frequency] || s.frequency}</td>
                  <td className="px-4 py-2.5 text-zinc-600 dark:text-zinc-300">{fmtDate(s.last_pm)}</td>
                  <td className="px-4 py-2.5">
                    <span className={`inline-flex items-center gap-1 ${s.is_due ? 'text-amber-700 font-semibold' : 'text-zinc-700 dark:text-zinc-300'}`}>
                      {fmtDate(s.next_pm)}{s.is_due ? ' · due' : ''}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <button onClick={() => removeSchedule(s.id)} disabled={busyId === s.id} className="text-zinc-400 hover:text-rose-600 disabled:opacity-40" data-testid={`pm-delete-${s.id}`} aria-label="Delete schedule">
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {showAdd && (
        <AddPmModal
          equipment={equipment}
          existing={schedules}
          onClose={() => setShowAdd(false)}
          onCreated={async () => { setShowAdd(false); await load(); }}
        />
      )}
    </div>
  );
}

function AddPmModal({ equipment, existing, onClose, onCreated }) {
  const usedEq = useMemo(() => new Set((existing || []).map((s) => s.equipment_id)), [existing]);
  const options = useMemo(() => (equipment || []).filter((e) => !usedEq.has(e.id)), [equipment, usedEq]);
  const [equipmentId, setEquipmentId] = useState('');
  const [frequency, setFrequency] = useState('annual');
  const [nextPm, setNextPm] = useState('');
  const [lastPm, setLastPm] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!equipmentId || !nextPm) { notify.error('Pick equipment and a next-PM date'); return; }
    setBusy(true);
    try {
      await api.post('/svc/pm/schedules', { equipment_id: equipmentId, frequency, next_pm: nextPm, last_pm: lastPm || undefined });
      notify.success('PM schedule created');
      onCreated();
    } catch (e) { notify.error(e?.response?.data?.detail || 'Could not create schedule'); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose} data-testid="pm-add-modal">
      <div className="bg-white dark:bg-zinc-900 rounded-2xl shadow-xl w-full max-w-md p-5" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-black text-zinc-900 dark:text-zinc-100 mb-3">Schedule preventative maintenance</h2>
        <label className="block text-xs font-semibold text-zinc-500 mb-1">Equipment</label>
        <select value={equipmentId} onChange={(e) => setEquipmentId(e.target.value)} className="w-full mb-3 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-transparent px-3 py-2 text-sm" data-testid="pm-equipment-select">
          <option value="">Select equipment…</option>
          {options.map((e) => (
            <option key={e.id} value={e.id}>{e.name}{e.customer_name ? ` · ${e.customer_name}` : ''}</option>
          ))}
        </select>
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div>
            <label className="block text-xs font-semibold text-zinc-500 mb-1">Frequency</label>
            <select value={frequency} onChange={(e) => setFrequency(e.target.value)} className="w-full rounded-lg border border-zinc-300 dark:border-zinc-700 bg-transparent px-3 py-2 text-sm" data-testid="pm-frequency-select">
              <option value="weekly">Weekly</option>
              <option value="fortnightly">Fortnightly</option>
              <option value="monthly">Monthly</option>
              <option value="quarterly">Quarterly</option>
              <option value="biannual">6-monthly</option>
              <option value="annual">Annual</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-zinc-500 mb-1">Next PM date</label>
            <input type="date" value={nextPm} onChange={(e) => setNextPm(e.target.value)} className="w-full rounded-lg border border-zinc-300 dark:border-zinc-700 bg-transparent px-3 py-2 text-sm" data-testid="pm-next-date" />
          </div>
        </div>
        <label className="block text-xs font-semibold text-zinc-500 mb-1">Previous PM (optional)</label>
        <input type="date" value={lastPm} onChange={(e) => setLastPm(e.target.value)} className="w-full mb-4 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-transparent px-3 py-2 text-sm" data-testid="pm-last-date" />
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="text-sm px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700" data-testid="pm-cancel-btn">Cancel</button>
          <button onClick={submit} disabled={busy} className="inline-flex items-center gap-1.5 text-sm font-semibold px-3 py-2 rounded-lg bg-zinc-900 text-white dark:bg-white dark:text-zinc-900 disabled:opacity-50" data-testid="pm-save-btn">
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} Create schedule
          </button>
        </div>
      </div>
    </div>
  );
}
