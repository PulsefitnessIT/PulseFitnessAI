import { useEffect, useState, useCallback } from 'react';
import { Plus, RotateCcw } from 'lucide-react';
import { notify } from '@/components/notifications';
import { dpApi } from './api';
import { Spinner, Modal, Field, input } from './shared';
import { FAILURE_REASONS } from './UsageTab';

const RMA_STATUSES = [
  'not_required', 'return_requested', 'awaiting_return', 'in_transit',
  'received_by_pulse', 'under_inspection', 'quality_review', 'closed',
];
const TONE = {
  return_requested: 'bg-amber-50 text-amber-700 border-amber-200',
  awaiting_return: 'bg-amber-50 text-amber-700 border-amber-200',
  in_transit: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  received_by_pulse: 'bg-blue-50 text-blue-700 border-blue-200',
  under_inspection: 'bg-violet-50 text-violet-700 border-violet-200',
  quality_review: 'bg-violet-50 text-violet-700 border-violet-200',
  closed: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  not_required: 'bg-slate-100 text-slate-500 border-slate-200',
};

export default function RmaTab() {
  const [rows, setRows] = useState([]);
  const [dealers, setDealers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState({ dealer_id: '', part_sku: '', part_name: '', quantity: 1, machine_model: '', reason: '', failure_reason: 'manufacturing_defect_suspected', failed_part_returned: true });

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([dpApi.listRma(), dpApi.listDealers()]).then(([r, d]) => {
      setRows(r.rma || []); setDealers(d.dealers || []);
    }).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    if (!form.dealer_id || !form.part_sku.trim()) { notify.error('Dealer and part required'); return; }
    try {
      await dpApi.createRma({ ...form, quantity: Number(form.quantity) });
      notify.success('RMA created');
      setModal(false);
      setForm({ dealer_id: '', part_sku: '', part_name: '', quantity: 1, machine_model: '', reason: '', failure_reason: 'manufacturing_defect_suspected', failed_part_returned: true });
      load();
    } catch { notify.error('Failed to create RMA'); }
  };

  const setStatus = async (r, status) => {
    try { await dpApi.updateRma(r.id, { status }); notify.success('RMA updated'); load(); }
    catch { notify.error('Update failed'); }
  };

  return (
    <div className="space-y-4" data-testid="dp-rma-tab">
      <div className="flex items-center">
        <h3 className="text-sm font-semibold text-slate-500 flex items-center gap-2"><RotateCcw size={15} /> Returns &amp; RMA (failed parts)</h3>
        <button data-testid="dp-add-rma-btn" onClick={() => setModal(true)} disabled={dealers.length === 0}
          className="ml-auto inline-flex items-center gap-1.5 bg-[var(--gx-brand-from)] text-white text-sm font-semibold px-3.5 py-2 rounded-lg hover:opacity-90 disabled:opacity-40">
          <Plus size={15} /> New RMA
        </button>
      </div>

      {loading ? <Spinner /> : rows.length === 0 ? (
        <div className="text-center py-16 text-slate-400 text-sm">No returns raised yet.</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100 bg-slate-50/50">
              <th className="py-2.5 px-4">RMA</th><th>Dealer</th><th>Part</th><th>Failure</th><th>Status</th>
            </tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} data-testid={`dp-rma-row-${r.id}`} className="border-b border-slate-50">
                  <td className="py-2.5 px-4 font-mono text-xs text-slate-500">{r.rma_reference}</td>
                  <td className="text-slate-600">{r.dealer_name}</td>
                  <td><span className="font-mono text-xs text-slate-500">{r.part_sku}</span> {r.part_name}</td>
                  <td className="text-xs capitalize text-slate-600">{(r.failure_reason || '').replace(/_/g, ' ')}</td>
                  <td>
                    <select data-testid={`dp-rma-status-${r.id}`} value={r.status} onChange={(e) => setStatus(r, e.target.value)}
                      className={`text-[11px] font-semibold px-2 py-1 rounded-full border capitalize ${TONE[r.status] || TONE.not_required}`}>
                      {RMA_STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={modal} onClose={() => setModal(false)} title="New return / RMA" testid="dp-rma-modal"
        footer={<>
          <button onClick={() => setModal(false)} className="px-4 py-2 text-sm text-slate-500">Cancel</button>
          <button data-testid="dp-rma-save" onClick={save} className="px-4 py-2 text-sm font-semibold bg-[var(--gx-brand-from)] text-white rounded-lg">Create RMA</button>
        </>}>
        <Field label="Dealer *">
          <select data-testid="dp-rma-dealer" className={input} value={form.dealer_id} onChange={(e) => setForm({ ...form, dealer_id: e.target.value })}>
            <option value="">Select dealer…</option>
            {dealers.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Part SKU *"><input data-testid="dp-rma-sku" className={`${input} font-mono`} value={form.part_sku} onChange={(e) => setForm({ ...form, part_sku: e.target.value.toUpperCase() })} /></Field>
          <Field label="Part name"><input className={input} value={form.part_name} onChange={(e) => setForm({ ...form, part_name: e.target.value })} /></Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Quantity"><input type="number" className={input} value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></Field>
          <Field label="Machine model"><input className={input} value={form.machine_model} onChange={(e) => setForm({ ...form, machine_model: e.target.value })} /></Field>
        </div>
        <Field label="Failure reason">
          <select className={input} value={form.failure_reason} onChange={(e) => setForm({ ...form, failure_reason: e.target.value })}>
            {FAILURE_REASONS.map((r) => <option key={r} value={r}>{r.replace(/_/g, ' ')}</option>)}
          </select>
        </Field>
        <Field label="Reason / notes"><input className={input} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} /></Field>
      </Modal>
    </div>
  );
}
