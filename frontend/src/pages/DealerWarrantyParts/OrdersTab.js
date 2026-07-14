import { useEffect, useState, useCallback } from 'react';
import { Plus, FileText, Trash2, Calculator, Sparkles } from 'lucide-react';
import { notify } from '@/components/notifications';
import { dpApi } from './api';
import { Spinner, Modal, Field, input, inputTight, money } from './shared';

export default function OrdersTab() {
  const [orders, setOrders] = useState([]);
  const [dealers, setDealers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState({ dealer_id: '', order_reference: '', order_value: '', spare_parts_percentage: '', currency: 'GBP', order_date: '' });
  const [lines, setLines] = useState([{ machine_model: '', quantity: 1, unit_value: '' }]);
  const [aiOpen, setAiOpen] = useState(false);
  const [aiText, setAiText] = useState('');
  const [aiLoading, setAiLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([dpApi.listOrders(), dpApi.listDealers()]).then(([o, d]) => {
      setOrders(o.orders || []); setDealers(d.dealers || []);
    }).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const dealer = dealers.find((d) => d.id === form.dealer_id);
  const linesTotal = lines.reduce((s, l) => s + (Number(l.quantity) || 0) * (Number(l.unit_value) || 0), 0);
  const orderValue = Number(form.order_value) || linesTotal;
  const pct = form.spare_parts_percentage !== '' ? Number(form.spare_parts_percentage)
    : (dealer?.default_percentage != null ? Number(dealer.default_percentage) : 2.5);
  const allowance = orderValue * pct / 100;

  const save = async () => {
    if (!form.dealer_id) { notify.error('Select a dealer'); return; }
    try {
      await dpApi.createOrder({
        ...form,
        order_value: orderValue,
        spare_parts_percentage: form.spare_parts_percentage === '' ? null : Number(form.spare_parts_percentage),
        lines: lines.filter((l) => l.machine_model).map((l) => ({ ...l, quantity: Number(l.quantity), unit_value: Number(l.unit_value) })),
      });
      notify.success('Order imported · allowance calculated');
      setModal(false);
      setForm({ dealer_id: '', order_reference: '', order_value: '', spare_parts_percentage: '', currency: 'GBP', order_date: '' });
      setLines([{ machine_model: '', quantity: 1, unit_value: '' }]);
      load();
    } catch { notify.error('Failed to import order'); }
  };

  const parseInvoice = async () => {
    if (aiText.trim().length < 20) { notify.error('Paste the invoice/order text'); return; }
    setAiLoading(true);
    try {
      const r = await dpApi.aiParseInvoice(aiText);
      if (!r.available) { notify.error(r.error || 'AI unavailable'); return; }
      if (r.order_reference) setForm((f) => ({ ...f, order_reference: r.order_reference, currency: r.currency || f.currency, order_value: r.order_value || '' }));
      if ((r.lines || []).length) setLines(r.lines.map((l) => ({ machine_model: l.machine_model || '', quantity: l.quantity || 1, unit_value: l.unit_value || '' })));
      notify.success(`AI extracted ${(r.lines || []).length} line(s) — please review before importing`);
      setAiOpen(false); setModal(true); setAiText('');
    } catch (e) { notify.error(e?.response?.data?.detail || 'AI parse failed'); }
    finally { setAiLoading(false); }
  };

  return (
    <div className="space-y-4" data-testid="dp-orders-tab">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold text-slate-500">Dealer orders &amp; invoices</h3>
        <button data-testid="dp-ai-invoice-btn" onClick={() => setAiOpen(true)} disabled={dealers.length === 0}
          className="ml-auto inline-flex items-center gap-1.5 text-sm font-semibold px-3 py-2 rounded-lg border border-[var(--gx-brand-from)]/30 text-[var(--gx-brand-from)] hover:bg-[var(--gx-brand-from)]/5 disabled:opacity-40">
          <Sparkles size={15} /> Parse invoice with AI
        </button>
        <button data-testid="dp-add-order-btn" onClick={() => setModal(true)} disabled={dealers.length === 0}
          className="inline-flex items-center gap-1.5 bg-[var(--gx-brand-from)] text-white text-sm font-semibold px-3.5 py-2 rounded-lg hover:opacity-90 disabled:opacity-40">
          <Plus size={15} /> Import order
        </button>
      </div>
      {dealers.length === 0 && <p className="text-xs text-amber-600">Add a dealer first before importing orders.</p>}

      {loading ? <Spinner /> : orders.length === 0 ? (
        <div className="text-center py-16 text-slate-400 text-sm">No orders imported yet.</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-slate-400 border-b border-slate-100 bg-slate-50/50">
              <th className="py-2.5 px-4">Reference</th><th>Dealer</th><th>Order value</th><th>%</th><th>Allowance</th><th>Machines</th>
            </tr></thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id} data-testid={`dp-order-row-${o.id}`} className="border-b border-slate-50">
                  <td className="py-2.5 px-4 font-medium text-slate-700"><FileText size={13} className="inline mr-1.5 text-slate-300" />{o.order_reference || '—'}</td>
                  <td className="text-slate-600">{o.dealer_name}</td>
                  <td className="tabular-nums">{money(o.order_value, o.currency)}</td>
                  <td className="tabular-nums text-slate-500">{o.spare_parts_percentage}%</td>
                  <td className="tabular-nums font-semibold text-[var(--gx-brand-from)]">{money(o.allowance, o.currency)}</td>
                  <td className="text-slate-400 text-xs">{(o.lines || []).length} lines</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={modal} onClose={() => setModal(false)} title="Import dealer order / invoice" testid="dp-order-modal"
        footer={<>
          <button onClick={() => setModal(false)} className="px-4 py-2 text-sm text-slate-500">Cancel</button>
          <button data-testid="dp-order-save" onClick={save} className="px-4 py-2 text-sm font-semibold bg-[var(--gx-brand-from)] text-white rounded-lg">Import order</button>
        </>}>
        <Field label="Dealer *">
          <select data-testid="dp-order-dealer" className={input} value={form.dealer_id} onChange={(e) => setForm({ ...form, dealer_id: e.target.value })}>
            <option value="">Select dealer…</option>
            {dealers.map((d) => <option key={d.id} value={d.id}>{d.name}{d.country ? ` (${d.country})` : ''}</option>)}
          </select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Order reference"><input data-testid="dp-order-ref" className={input} value={form.order_reference} onChange={(e) => setForm({ ...form, order_reference: e.target.value })} /></Field>
          <Field label="Order date"><input type="date" className={input} value={form.order_date} onChange={(e) => setForm({ ...form, order_date: e.target.value })} /></Field>
        </div>

        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-500">Equipment lines</span>
          <button onClick={() => setLines([...lines, { machine_model: '', quantity: 1, unit_value: '' }])} className="text-xs text-[var(--gx-brand-from)] font-semibold">+ Add line</button>
        </div>
        {lines.map((l, i) => (
          <div key={i} className="flex gap-2 mb-2">
            <input placeholder="Machine model" className={`${inputTight} flex-1`} value={l.machine_model} onChange={(e) => { const n = [...lines]; n[i].machine_model = e.target.value; setLines(n); }} />
            <input type="number" placeholder="Qty" className={`${inputTight} w-16`} value={l.quantity} onChange={(e) => { const n = [...lines]; n[i].quantity = e.target.value; setLines(n); }} />
            <input type="number" placeholder="Unit £" className={`${inputTight} w-24`} value={l.unit_value} onChange={(e) => { const n = [...lines]; n[i].unit_value = e.target.value; setLines(n); }} />
            {lines.length > 1 && <button onClick={() => setLines(lines.filter((_, x) => x !== i))} className="text-slate-300 hover:text-red-500"><Trash2 size={15} /></button>}
          </div>
        ))}

        <div className="grid grid-cols-2 gap-3 mt-3">
          <Field label="Order value (override)"><input type="number" className={input} value={form.order_value} onChange={(e) => setForm({ ...form, order_value: e.target.value })} placeholder={linesTotal ? String(linesTotal) : 'from lines'} /></Field>
          <Field label="Spare parts % (override)"><input type="number" step="0.1" className={input} value={form.spare_parts_percentage} onChange={(e) => setForm({ ...form, spare_parts_percentage: e.target.value })} placeholder={String(pct)} /></Field>
        </div>

        <div className="rounded-lg bg-[var(--gx-brand-from)]/5 border border-[var(--gx-brand-from)]/20 p-3 flex items-center gap-3" data-testid="dp-allowance-preview">
          <Calculator size={18} className="text-[var(--gx-brand-from)]" />
          <div className="text-sm">
            <div className="text-slate-500 text-xs">{money(orderValue)} × {pct}% =</div>
            <div className="text-lg font-bold text-[var(--gx-brand-from)]">{money(allowance)} spare parts allowance</div>
          </div>
        </div>
      </Modal>

      <Modal open={aiOpen} onClose={() => setAiOpen(false)} title="Parse invoice with AI" testid="dp-ai-invoice-modal"
        footer={<>
          <button onClick={() => setAiOpen(false)} className="px-4 py-2 text-sm text-slate-500">Cancel</button>
          <button data-testid="dp-ai-parse-btn" onClick={parseInvoice} disabled={aiLoading} className="px-4 py-2 text-sm font-semibold bg-gradient-to-r from-[var(--gx-brand-from)] to-[var(--gx-brand-to)] text-white rounded-lg disabled:opacity-50">{aiLoading ? 'Reading…' : 'Extract lines'}</button>
        </>}>
        <p className="text-xs text-slate-500 mb-2">Paste the dealer's invoice / order text. AI will extract the machine lines and order value — <strong>please review before importing</strong>.</p>
        <textarea data-testid="dp-ai-invoice-text" value={aiText} onChange={(e) => setAiText(e.target.value)} rows={9}
          className={`${input} font-mono text-xs`} placeholder={"e.g.\nPO-DE-9001\n10 x 260G Treadmill @ 8000 EUR\n5 x 500 Series Cross Trainer @ 6000 EUR\nGrand Total: 110000 EUR"} />
      </Modal>
    </div>
  );
}
