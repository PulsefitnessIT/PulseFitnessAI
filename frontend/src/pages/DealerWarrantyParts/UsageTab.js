import { useEffect, useState, useCallback } from 'react';
import { Plus, Wrench, RotateCcw } from 'lucide-react';
import { notify } from '@/components/notifications';
import { dpApi } from './api';
import { Spinner, Modal, Field, input, money } from './shared';

export const FAILURE_REASONS = [
  'mechanical_failure', 'electrical_failure', 'wear_and_tear', 'accidental_damage',
  'misuse', 'corrosion_environmental', 'transit_damage', 'installation_issue',
  'manufacturing_defect_suspected', 'unknown', 'other',
];

export default function UsageTab() {
  const [rows, setRows] = useState([]);
  const [dealers, setDealers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState({ dealer_id: '', part_sku: '', part_name: '', quantity: 1, machine_model: '', serial_number: '', failure_reason: 'wear_and_tear', warranty: true, chargeable: false, failed_part_returned: false, notes: '' });

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([dpApi.listUsage(), dpApi.listDealers()]).then(([u, d]) => {
      setRows(u.usage || []); setDealers(d.dealers || []);
    }).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    if (!form.dealer_id || !form.part_sku.trim() || !form.quantity) { notify.error('Dealer, part and quantity required'); return; }
    try {
      await dpApi.logUsage({ ...form, quantity: Number(form.quantity) });
      notify.success('Part usage logged · stock reduced');
      setModal(false);
      setForm({ dealer_id: '', part_sku: '', part_name: '', quantity: 1, machine_model: '', serial_number: '', failure_reason: 'wear_and_tear', warranty: true, chargeable: false, failed_part_returned: false, notes: '' });
      load();
    } catch (e) { notify.error(e?.response?.data?.detail || 'Failed to log usage'); }
  };

  const raiseRma = async (u) => {
    try {
      const rma = await dpApi.createRma({
        dealer_id: u.dealer_id, part_sku: u.part_sku, part_name: u.part_name, quantity: u.quantity,
        machine_model: u.machine_model, serial_number: u.serial_number, reason: u.reason || 'Failed part return',
        failure_reason: u.failure_reason, usage_log_id: u.id, case_id: u.case_id, failed_part_returned: true,
      });
      notify.success(`RMA raised: ${rma.rma_reference}`);
    } catch { notify.error('Failed to raise RMA'); }
  };

  return (
    <div className="space-y-4" data-testid="dp-usage-tab">
      <div className="flex items-center">
        <h3 className="text-sm font-semibold text-slate-500 flex items-center gap-2"><Wrench size={15} /> Engineer &amp; dealer parts usage</h3>
        <button data-testid="dp-log-usage-btn" onClick={() => setModal(true)} disabled={dealers.length === 0}
          className="ml-auto inline-flex items-center gap-1.5 bg-[var(--gx-brand-from)] text-white text-sm font-semibold px-3.5 py-2 rounded-lg hover:opacity-90 disabled:opacity-40">
          <Plus size={15} /> Log part used
        </button>
      </div>

      {loading ? <Spinner /> : rows.length === 0 ? (
        <div className="text-center py-16 text-slate-400 text-sm">No parts logged as used yet.</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100 bg-slate-50/50">
              <th className="py-2.5 px-4">When</th><th>Dealer</th><th>Part</th><th>Qty</th><th>Machine / Serial</th><th>Failure</th><th>Cover</th><th></th>
            </tr></thead>
            <tbody>
              {rows.map((u) => (
                <tr key={u.id} data-testid={`dp-usage-row-${u.id}`} className="border-b border-slate-50">
                  <td className="py-2.5 px-4 text-xs text-slate-400 whitespace-nowrap">{new Date(u.at).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })}</td>
                  <td className="text-slate-600">{u.dealer_name}</td>
                  <td><span className="font-mono text-xs text-slate-500">{u.part_sku}</span> {u.part_name}</td>
                  <td className="tabular-nums">{u.quantity}</td>
                  <td className="text-xs text-slate-500">{u.machine_model}{u.serial_number ? ` · ${u.serial_number}` : ''}</td>
                  <td className="text-xs capitalize text-slate-600">{(u.failure_reason || '').replace(/_/g, ' ')}</td>
                  <td>{u.warranty ? <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2 py-0.5">Warranty</span> : <span className="text-[11px] font-semibold text-slate-600 bg-slate-100 border border-slate-200 rounded-full px-2 py-0.5">Chargeable</span>}</td>
                  <td className="text-right pr-3"><button data-testid={`dp-usage-rma-${u.id}`} onClick={() => raiseRma(u)} title="Raise RMA" className="text-slate-400 hover:text-[var(--gx-brand-from)] inline-flex items-center gap-1 text-xs"><RotateCcw size={13} /> RMA</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={modal} onClose={() => setModal(false)} title="Log part used (Engineer App)" testid="dp-usage-modal"
        footer={<>
          <button onClick={() => setModal(false)} className="px-4 py-2 text-sm text-slate-500">Cancel</button>
          <button data-testid="dp-usage-save" onClick={save} className="px-4 py-2 text-sm font-semibold bg-[var(--gx-brand-from)] text-white rounded-lg">Submit usage</button>
        </>}>
        <Field label="Dealer *">
          <select data-testid="dp-usage-dealer" className={input} value={form.dealer_id} onChange={(e) => setForm({ ...form, dealer_id: e.target.value })}>
            <option value="">Select dealer…</option>
            {dealers.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Part SKU *"><input data-testid="dp-usage-sku" className={`${input} font-mono`} value={form.part_sku} onChange={(e) => setForm({ ...form, part_sku: e.target.value.toUpperCase() })} /></Field>
          <Field label="Part name"><input className={input} value={form.part_name} onChange={(e) => setForm({ ...form, part_name: e.target.value })} /></Field>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Quantity *"><input type="number" data-testid="dp-usage-qty" className={input} value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></Field>
          <Field label="Machine model"><input className={input} value={form.machine_model} onChange={(e) => setForm({ ...form, machine_model: e.target.value })} /></Field>
          <Field label="Serial number"><input className={input} value={form.serial_number} onChange={(e) => setForm({ ...form, serial_number: e.target.value })} /></Field>
        </div>
        <Field label="Failure reason">
          <select className={input} value={form.failure_reason} onChange={(e) => setForm({ ...form, failure_reason: e.target.value })}>
            {FAILURE_REASONS.map((r) => <option key={r} value={r}>{r.replace(/_/g, ' ')}</option>)}
          </select>
        </Field>
        <div className="flex items-center gap-5 mb-3">
          <label className="text-sm text-slate-700 flex items-center gap-2 cursor-pointer"><input type="checkbox" checked={form.warranty} onChange={(e) => setForm({ ...form, warranty: e.target.checked, chargeable: e.target.checked ? false : form.chargeable })} /> Warranty</label>
          <label className="text-sm text-slate-700 flex items-center gap-2 cursor-pointer"><input type="checkbox" checked={form.chargeable} onChange={(e) => setForm({ ...form, chargeable: e.target.checked })} /> Chargeable</label>
          <label className="text-sm text-slate-700 flex items-center gap-2 cursor-pointer"><input type="checkbox" checked={form.failed_part_returned} onChange={(e) => setForm({ ...form, failed_part_returned: e.target.checked })} /> Failed part returned</label>
        </div>
        <Field label="Notes"><input className={input} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field>
      </Modal>
    </div>
  );
}
