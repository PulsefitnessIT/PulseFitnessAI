import { useEffect, useState, useCallback } from 'react';
import { Plus, Trash2, Star, Search } from 'lucide-react';
import { notify } from '@/components/notifications';
import { dpApi } from './api';
import { Spinner, Modal, Field, input, money } from './shared';

const PRIORITY_TONE = {
  critical: 'bg-red-50 text-red-700 border-red-200',
  high: 'bg-amber-50 text-amber-700 border-amber-200',
  medium: 'bg-blue-50 text-blue-700 border-blue-200',
  low: 'bg-slate-100 text-slate-600 border-slate-200',
  optional: 'bg-slate-100 text-slate-500 border-slate-200',
};

export default function MostUsedTab() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState({ machine_model: '', part_number: '', part_description: '', priority: 'high', recommended_dealer_stock_quantity: '', avg_usage_per_year: '', failure_frequency: '', cost: '', lead_time_days: '' });

  const load = useCallback(() => {
    setLoading(true);
    dpApi.listMostUsed(q ? { machine_model: q } : {}).then((d) => setRows(d.most_used || [])).finally(() => setLoading(false));
  }, [q]);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    if (!form.machine_model.trim() || !form.part_number.trim()) { notify.error('Model and part number required'); return; }
    try {
      await dpApi.upsertMostUsed({
        ...form,
        recommended_dealer_stock_quantity: form.recommended_dealer_stock_quantity === '' ? null : Number(form.recommended_dealer_stock_quantity),
        avg_usage_per_year: Number(form.avg_usage_per_year) || 0,
        failure_frequency: Number(form.failure_frequency) || 0,
        cost: Number(form.cost) || 0,
        lead_time_days: Number(form.lead_time_days) || 0,
      });
      notify.success('Most-used part saved');
      setModal(false);
      setForm({ machine_model: '', part_number: '', part_description: '', priority: 'high', recommended_dealer_stock_quantity: '', avg_usage_per_year: '', failure_frequency: '', cost: '', lead_time_days: '' });
      load();
    } catch { notify.error('Failed to save'); }
  };

  const remove = async (id) => { await dpApi.deleteMostUsed(id); notify.success('Removed'); load(); };

  return (
    <div className="space-y-4" data-testid="dp-most-used-tab">
      <div className="flex items-center gap-2">
        <div className="relative flex-1 max-w-xs">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter by model…" className={`${input} pl-9`} />
        </div>
        <button data-testid="dp-add-mu-btn" onClick={() => setModal(true)} className="ml-auto inline-flex items-center gap-1.5 bg-[var(--gx-brand-from)] text-white text-sm font-semibold px-3.5 py-2 rounded-lg hover:opacity-90">
          <Plus size={15} /> Add part
        </button>
      </div>

      {loading ? <Spinner /> : rows.length === 0 ? (
        <div className="text-center py-16 text-slate-400 text-sm">No most-used parts defined yet.</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100 bg-slate-50/50">
              <th className="py-2.5 px-4">Model</th><th>Part</th><th>Priority</th><th>Rec. stock</th><th>Cost</th><th></th>
            </tr></thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.id} data-testid={`dp-mu-row-${m.id}`} className="border-b border-slate-50">
                  <td className="py-2.5 px-4 text-slate-600">{m.machine_model}</td>
                  <td><span className="font-mono text-xs text-slate-500">{m.part_number}</span> {m.part_description}</td>
                  <td><span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border capitalize ${PRIORITY_TONE[m.priority] || PRIORITY_TONE.medium}`}>{m.priority}</span></td>
                  <td className="tabular-nums">{m.recommended_dealer_stock_quantity ?? '—'}</td>
                  <td className="tabular-nums">{money(m.cost)}</td>
                  <td className="text-right pr-3"><button onClick={() => remove(m.id)} className="text-slate-300 hover:text-red-500"><Trash2 size={14} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={modal} onClose={() => setModal(false)} title="Add most-used part" testid="dp-mu-modal"
        footer={<>
          <button onClick={() => setModal(false)} className="px-4 py-2 text-sm text-slate-500">Cancel</button>
          <button data-testid="dp-mu-save" onClick={save} className="px-4 py-2 text-sm font-semibold bg-[var(--gx-brand-from)] text-white rounded-lg">Save</button>
        </>}>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Machine model *"><input data-testid="dp-mu-model" className={input} value={form.machine_model} onChange={(e) => setForm({ ...form, machine_model: e.target.value })} /></Field>
          <Field label="Part number *"><input data-testid="dp-mu-part" className={`${input} font-mono`} value={form.part_number} onChange={(e) => setForm({ ...form, part_number: e.target.value.toUpperCase() })} /></Field>
        </div>
        <Field label="Description"><input className={input} value={form.part_description} onChange={(e) => setForm({ ...form, part_description: e.target.value })} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Priority">
            <select className={input} value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
              {['critical', 'high', 'medium', 'low', 'optional'].map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </Field>
          <Field label="Recommended dealer stock"><input type="number" className={input} value={form.recommended_dealer_stock_quantity} onChange={(e) => setForm({ ...form, recommended_dealer_stock_quantity: e.target.value })} /></Field>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Avg usage / yr"><input type="number" className={input} value={form.avg_usage_per_year} onChange={(e) => setForm({ ...form, avg_usage_per_year: e.target.value })} /></Field>
          <Field label="Unit cost £"><input type="number" className={input} value={form.cost} onChange={(e) => setForm({ ...form, cost: e.target.value })} /></Field>
          <Field label="Lead time (days)"><input type="number" className={input} value={form.lead_time_days} onChange={(e) => setForm({ ...form, lead_time_days: e.target.value })} /></Field>
        </div>
      </Modal>
    </div>
  );
}
