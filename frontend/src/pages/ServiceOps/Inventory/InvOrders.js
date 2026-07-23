import { useCallback, useEffect, useRef, useState } from 'react';
import { Plus, Search, ArrowLeft, ScanLine, CheckCircle2, PackageCheck, ShieldCheck, Trash2, FileUp, Sparkles, Loader2, RefreshCw, Play } from 'lucide-react';
import { notify } from '@/components/notifications';
import { invApi, money, fmtDate, statusLabel } from './api';
import { Card, StatCard, Spinner, StatusBadge, Btn, Field, inputCls } from './ui';
import OrderFulfilment from './InvFulfilment';

const SOURCE_BADGE = {
  sage: { label: 'Sage 200', cls: 'bg-blue-100 text-blue-700' },
  invoice: { label: 'AI Invoice', cls: 'bg-violet-100 text-violet-700' },
  crm: { label: 'CRM', cls: 'bg-emerald-100 text-emerald-700' },
  manual: { label: 'Manual', cls: 'bg-slate-100 text-slate-600' },
};
function SourceBadge({ source }) {
  const s = SOURCE_BADGE[source] || SOURCE_BADGE.manual;
  return <span className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-bold ${s.cls}`} data-testid={`inv-order-source-${source || 'manual'}`}>{s.label}</span>;
}

const CURRENCIES = ['GBP', 'EUR', 'USD'];
const COUNTRIES = [{ c: 'GB', n: 'United Kingdom' }, { c: 'FR', n: 'France' }, { c: 'US', n: 'United States' }];
const LANGS = [{ c: 'en', n: 'English' }, { c: 'fr', n: 'Français' }];

const PRODUCT_TYPE_LABELS = {
  serialised_machine: 'Serialised machine', non_serialised_equipment: 'Non-serialised equipment',
  spare_part: 'Spare part', accessory: 'Accessory', installation_item: 'Installation item',
  service_item: 'Service item', delivery_charge: 'Delivery charge', warranty_parts_allowance: 'Warranty parts allowance',
  promotional_item: 'Promotional item', packaging: 'Packaging', other: 'Other',
};

// ─────────────────────────── Create order wizard ───────────────────────────
function CreateOrderModal({ warehouses, onClose, onCreated, autoInvoice }) {
  const [header, setHeader] = useState({
    dealer_id: '', dealer_name: '', dealer_country: 'GB', currency: 'GBP', language: 'en',
    customer_po: '', delivery_address: '', requested_delivery_date: '', sales_rep: '', notes: '',
    warehouse_id: warehouses[0]?.id || '',
  });
  const [dealerQuery, setDealerQuery] = useState('');
  const [dealerResults, setDealerResults] = useState([]);
  const [lines, setLines] = useState([{ product_code: '', description: '', product_type: 'serialised_machine', quantity: 1, unit_price: 0 }]);
  const [saving, setSaving] = useState(false);
  const [source, setSource] = useState('manual');
  const [parsing, setParsing] = useState(false);
  const fileRef = useRef(null);

  const onInvoiceFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setParsing(true);
    try {
      const res = await invApi.parseInvoiceOrder(f);
      setHeader((h) => ({
        ...h,
        dealer_name: res.header?.dealer_name || h.dealer_name,
        customer_po: res.header?.customer_po || h.customer_po,
        delivery_address: res.header?.delivery_address || h.delivery_address,
      }));
      if ((res.lines || []).length) setLines(res.lines);
      setSource('invoice');
      notify.success(`Read ${res.line_count || 0} line(s)${res.supplier_name ? ` from ${res.supplier_name}` : ''}. Review & create.`);
    } catch (err) {
      notify.error(err?.response?.data?.detail || 'Could not read that invoice');
    } finally { setParsing(false); if (fileRef.current) fileRef.current.value = ''; }
  };

  useEffect(() => { if (autoInvoice) { const t = setTimeout(() => fileRef.current?.click(), 250); return () => clearTimeout(t); } }, [autoInvoice]);

  useEffect(() => {
    if (dealerQuery.length < 2) { setDealerResults([]); return; }
    const t = setTimeout(() => { invApi.dealers(dealerQuery).then((d) => setDealerResults(d.dealers || [])).catch(() => {}); }, 250);
    return () => clearTimeout(t);
  }, [dealerQuery]);

  const setLine = (i, patch) => setLines((ls) => ls.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));
  const addLine = () => setLines((ls) => [...ls, { product_code: '', description: '', product_type: 'serialised_machine', quantity: 1, unit_price: 0 }]);
  const removeLine = (i) => setLines((ls) => ls.filter((_, idx) => idx !== i));

  const total = lines.reduce((s, l) => s + Number(l.quantity || 0) * Number(l.unit_price || 0), 0);
  const valid = header.dealer_name.trim() && lines.length > 0 && lines.every((l) => l.product_code.trim() && l.description.trim());

  const submit = async () => {
    setSaving(true);
    try {
      const res = await invApi.createOrder({ ...header, source, lines: lines.map((l) => ({ ...l, quantity: Number(l.quantity), unit_price: Number(l.unit_price) })) });
      notify.success(`Order ${res.order.reference} created — ${res.provisional_units} provisional unit(s)`);
      onCreated(res.order.id);
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not create order');
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-[200] flex items-start justify-center overflow-y-auto bg-black/50 p-4" data-testid="inv-create-order-modal">
      <div className="my-6 w-full max-w-3xl rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <h2 className="text-lg font-bold text-slate-900">{source === 'invoice' ? 'New order — from invoice' : 'New order'}</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600" data-testid="inv-create-close">✕</button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto px-6 py-5 space-y-5">
          <div className="rounded-xl border border-violet-200 bg-violet-50/60 p-3">
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-violet-100"><Sparkles size={18} className="text-violet-600" /></div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-bold text-slate-900">Add from an invoice or PO</p>
                <p className="text-[11px] text-slate-500">No Sage needed — upload a supplier invoice / purchase order (PDF or image) and AI fills the order for you to review.</p>
              </div>
              <input ref={fileRef} type="file" accept=".pdf,image/*" className="hidden" data-testid="inv-order-invoice-file" onChange={onInvoiceFile} />
              <Btn variant="secondary" onClick={() => fileRef.current?.click()} disabled={parsing} data-testid="inv-order-invoice-btn">
                {parsing ? <Loader2 size={15} className="animate-spin" /> : <FileUp size={15} />} {parsing ? 'Reading…' : 'Upload invoice'}
              </Btn>
            </div>
            {source === 'invoice' && <p className="mt-2 flex items-center gap-1 text-[11px] font-semibold text-violet-700"><CheckCircle2 size={12} /> Read from invoice — review the fields below, then create.</p>}
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="relative">
              <Field label="Dealer" required hint="Search your CRM companies, or type a name">
                <input
                  className={inputCls}
                  value={header.dealer_name}
                  placeholder="Search dealer…"
                  data-testid="inv-order-dealer"
                  onChange={(e) => { setHeader((h) => ({ ...h, dealer_name: e.target.value, dealer_id: '' })); setDealerQuery(e.target.value); }}
                />
              </Field>
              {dealerResults.length > 0 && (
                <div className="absolute z-10 mt-1 w-full rounded-lg border border-slate-200 bg-white shadow-lg">
                  {dealerResults.map((d) => (
                    <button
                      key={d.id}
                      className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
                      data-testid={`inv-dealer-opt-${d.id}`}
                      onClick={() => { setHeader((h) => ({ ...h, dealer_name: d.name, dealer_id: d.id, dealer_country: (d.country || '').startsWith('France') ? 'FR' : h.dealer_country })); setDealerResults([]); }}
                    >
                      {d.name} <span className="text-slate-400">· {d.country || '—'}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <Field label="Customer PO"><input className={inputCls} value={header.customer_po} data-testid="inv-order-po" onChange={(e) => setHeader((h) => ({ ...h, customer_po: e.target.value }))} /></Field>
            <Field label="Destination country">
              <select className={inputCls} value={header.dealer_country} data-testid="inv-order-country" onChange={(e) => setHeader((h) => ({ ...h, dealer_country: e.target.value }))}>
                {COUNTRIES.map((c) => <option key={c.c} value={c.c}>{c.n}</option>)}
              </select>
            </Field>
            <Field label="Currency" hint="Original transaction currency — never recalculated">
              <select className={inputCls} value={header.currency} data-testid="inv-order-currency" onChange={(e) => setHeader((h) => ({ ...h, currency: e.target.value }))}>
                {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
            <Field label="Portal language">
              <select className={inputCls} value={header.language} data-testid="inv-order-language" onChange={(e) => setHeader((h) => ({ ...h, language: e.target.value }))}>
                {LANGS.map((c) => <option key={c.c} value={c.c}>{c.n}</option>)}
              </select>
            </Field>
            <Field label="Fulfilling warehouse">
              <select className={inputCls} value={header.warehouse_id} data-testid="inv-order-warehouse" onChange={(e) => setHeader((h) => ({ ...h, warehouse_id: e.target.value }))}>
                <option value="">—</option>
                {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
              </select>
            </Field>
            <Field label="Requested delivery date"><input type="date" className={inputCls} value={header.requested_delivery_date} data-testid="inv-order-delivery-date" onChange={(e) => setHeader((h) => ({ ...h, requested_delivery_date: e.target.value }))} /></Field>
            <Field label="Sales rep"><input className={inputCls} value={header.sales_rep} data-testid="inv-order-rep" onChange={(e) => setHeader((h) => ({ ...h, sales_rep: e.target.value }))} /></Field>
          </div>
          <Field label="Delivery address"><input className={inputCls} value={header.delivery_address} data-testid="inv-order-address" onChange={(e) => setHeader((h) => ({ ...h, delivery_address: e.target.value }))} /></Field>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate-900">Order lines</h3>
              <Btn variant="secondary" onClick={addLine} data-testid="inv-add-line"><Plus size={14} /> Add line</Btn>
            </div>
            <div className="space-y-2">
              {lines.map((l, i) => (
                <div key={i} className="grid grid-cols-12 items-end gap-2 rounded-lg border border-slate-200 p-2" data-testid={`inv-line-${i}`}>
                  <div className="col-span-2"><Field label="Code"><input className={inputCls} value={l.product_code} data-testid={`inv-line-code-${i}`} onChange={(e) => setLine(i, { product_code: e.target.value })} /></Field></div>
                  <div className="col-span-3"><Field label="Description"><input className={inputCls} value={l.description} data-testid={`inv-line-desc-${i}`} onChange={(e) => setLine(i, { description: e.target.value })} /></Field></div>
                  <div className="col-span-3"><Field label="Type"><select className={inputCls} value={l.product_type} data-testid={`inv-line-type-${i}`} onChange={(e) => setLine(i, { product_type: e.target.value })}>{Object.entries(PRODUCT_TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field></div>
                  <div className="col-span-1"><Field label="Qty"><input type="number" min="1" className={inputCls} value={l.quantity} data-testid={`inv-line-qty-${i}`} onChange={(e) => setLine(i, { quantity: e.target.value })} /></Field></div>
                  <div className="col-span-2"><Field label="Unit price"><input type="number" className={inputCls} value={l.unit_price} data-testid={`inv-line-price-${i}`} onChange={(e) => setLine(i, { unit_price: e.target.value })} /></Field></div>
                  <div className="col-span-1 pb-2">{lines.length > 1 && <button onClick={() => removeLine(i)} className="text-rose-500 hover:text-rose-700" data-testid={`inv-line-remove-${i}`}><Trash2 size={16} /></button>}</div>
                </div>
              ))}
            </div>
            <p className="mt-2 text-right text-sm font-semibold text-slate-700">Order value: {money(total, header.currency)}</p>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-slate-200 px-6 py-4">
          <Btn variant="secondary" onClick={onClose}>Cancel</Btn>
          <Btn onClick={submit} disabled={!valid || saving} data-testid="inv-create-submit">{saving ? 'Creating…' : 'Create order'}</Btn>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────── Serial capture row ───────────────────────────
function UnitRow({ unit, onAssigned }) {
  const [serial, setSerial] = useState('');
  const [busy, setBusy] = useState(false);

  const assign = async (override = false) => {
    if (!serial.trim()) return;
    setBusy(true);
    try {
      await invApi.assignSerial(unit.id, { serial_number: serial.trim(), override_duplicate: override });
      notify.success('Serial assigned');
      onAssigned();
    } catch (e) {
      if (e?.response?.status === 409) {
        if (window.confirm('This serial already exists in the platform. Assign anyway (authorised override)?')) {
          assign(true); return;
        }
      } else {
        notify.error(e?.response?.data?.detail || 'Could not assign serial');
      }
    } finally { setBusy(false); }
  };

  return (
    <div className="flex items-center gap-3 border-b border-slate-100 py-2 last:border-0" data-testid={`inv-unit-${unit.id}`}>
      <span className="w-40 truncate text-sm text-slate-600">{unit.model || unit.product_code}</span>
      <StatusBadge status={unit.status} />
      {unit.serial_number ? (
        <span className="ml-auto flex items-center gap-1 text-sm font-semibold text-slate-800" data-testid={`inv-unit-serial-${unit.id}`}><ScanLine size={14} className="text-[#0B3D91]" /> {unit.serial_number}</span>
      ) : (
        <div className="ml-auto flex items-center gap-2">
          <input className="rounded-lg border border-slate-300 px-2 py-1 text-sm" placeholder="Scan / type serial" value={serial} data-testid={`inv-unit-input-${unit.id}`} onChange={(e) => setSerial(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && assign()} />
          <Btn variant="secondary" onClick={() => assign()} disabled={busy || !serial.trim()} data-testid={`inv-unit-assign-${unit.id}`}>Bind</Btn>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────── Order detail ───────────────────────────
function OrderDetail({ orderId, onBack }) {
  const [data, setData] = useState(null);
  const [tab, setTab] = useState('overview');
  const [busy, setBusy] = useState('');

  const load = useCallback(() => { invApi.order(orderId).then(setData).catch(() => notify.error('Could not load order')); }, [orderId]);
  useEffect(() => { load(); }, [load]);

  if (!data) return <Spinner />;
  const { order, lines, units, reservations } = data;
  const cur = order.currency;

  const run = async (fn, key) => { setBusy(key); try { await fn(); load(); } catch (e) { notify.error(e?.response?.data?.detail || 'Action failed'); } finally { setBusy(''); } };

  const validation = order.validation;

  return (
    <div className="space-y-5" data-testid="inv-order-detail">
      <div className="flex items-center gap-3">
        <Btn variant="ghost" onClick={onBack} data-testid="inv-order-back"><ArrowLeft size={16} /> Orders</Btn>
        <div>
          <h2 className="text-xl font-bold text-slate-900">{order.reference}</h2>
          <p className="text-sm text-slate-500">{order.dealer_name} · {order.dealer_country} · {cur}</p>
        </div>
        <StatusBadge status={order.status} className="ml-2" />
        <span className="ml-auto rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-600">{order.sage_posting_status}</span>
      </div>

      <div className="flex gap-1 border-b border-slate-200">
        {[['overview', 'Overview'], ['fulfilment', 'Warehouse Fulfilment']].map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)} data-testid={`inv-order-tab-${id}`}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-semibold transition-colors ${tab === id ? 'border-[#0B3D91] text-[#0B3D91]' : 'border-transparent text-slate-500 hover:text-slate-700'}`}>{label}</button>
        ))}
      </div>

      {tab === 'fulfilment' ? <OrderFulfilment orderId={orderId} /> : (
      <>
      <div className="flex flex-wrap gap-2">
        <Btn variant="secondary" onClick={() => run(() => invApi.validate(orderId), 'validate')} disabled={!!busy} data-testid="inv-order-validate"><ShieldCheck size={15} /> {busy === 'validate' ? 'Validating…' : 'Validate'}</Btn>
        <Btn variant="secondary" onClick={() => run(() => invApi.reserve(orderId), 'reserve')} disabled={!!busy} data-testid="inv-order-reserve"><PackageCheck size={15} /> {busy === 'reserve' ? 'Reserving…' : 'Reserve stock'}</Btn>
      </div>

      {validation && (
        <Card className="p-4" testId="inv-order-validation">
          <div className="mb-2 flex items-center gap-2"><span className="text-sm font-bold text-slate-900">Validation</span><StatusBadge status={validation.outcome} /></div>
          <ul className="space-y-1 text-sm">
            {validation.checks.map((c) => (
              <li key={c.check} className="flex items-center gap-2">
                {c.ok ? <CheckCircle2 size={14} className="text-emerald-500" /> : <span className="text-amber-500">⚠</span>}
                <span className="text-slate-600">{c.message}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card className="p-4" testId="inv-order-lines">
          <h3 className="mb-3 text-sm font-bold text-slate-900">Order lines</h3>
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs uppercase text-slate-400"><th className="pb-2">Code</th><th>Description</th><th>Qty</th><th>Unit</th><th>Status</th></tr></thead>
            <tbody>
              {lines.map((l) => (
                <tr key={l.id} className="border-t border-slate-100" data-testid={`inv-line-row-${l.line_number}`}>
                  <td className="py-2 font-mono text-xs">{l.product_code}</td>
                  <td>{l.description}<div className="text-[11px] text-slate-400">{PRODUCT_TYPE_LABELS[l.product_type]}</div></td>
                  <td className="tabular-nums">{l.qty_allocated || 0}/{l.quantity}</td>
                  <td className="tabular-nums">{money(l.unit_price, cur)}</td>
                  <td><StatusBadge status={l.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <Card className="p-4" testId="inv-order-units">
          <h3 className="mb-1 text-sm font-bold text-slate-900">Equipment units — serial capture</h3>
          <p className="mb-3 text-[11px] text-slate-400">Provisional slots become the active asset record. Serial uniqueness is enforced across the platform.</p>
          {units.length === 0 ? <p className="text-sm text-slate-400">No serialised units on this order.</p> : units.map((u) => <UnitRow key={u.id} unit={u} onAssigned={load} />)}
        </Card>
      </div>

      {reservations.length > 0 && (
        <Card className="p-4" testId="inv-order-reservations">
          <h3 className="mb-2 text-sm font-bold text-slate-900">Reservations</h3>
          {reservations.map((r) => (
            <div key={r.id} className="flex items-center gap-3 border-b border-slate-100 py-1.5 text-sm last:border-0">
              <span className="font-mono text-xs">{r.product_code}</span>
              <span className="tabular-nums">×{r.quantity}</span>
              <StatusBadge status={r.status} className="ml-auto" />
            </div>
          ))}
        </Card>
      )}
      </>
      )}
    </div>
  );
}

// ─────────────────────────── Orders list ───────────────────────────
export default function InvOrders({ warehouses, initialOrderId }) {
  const [orders, setOrders] = useState(null);
  const [q, setQ] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [creating, setCreating] = useState(false);
  const [createMode, setCreateMode] = useState('manual');
  const [selected, setSelected] = useState(initialOrderId || null);

  const load = useCallback(() => {
    invApi.orders({ q: q || undefined, status: statusFilter }).then((d) => setOrders(d.orders || [])).catch(() => setOrders([]));
  }, [q, statusFilter]);
  useEffect(() => { const t = setTimeout(load, 200); return () => clearTimeout(t); }, [load]);

  const openCreate = (mode) => { setCreateMode(mode); setCreating(true); };

  if (selected) return <OrderDetail orderId={selected} onBack={() => { setSelected(null); load(); }} />;

  const shown = (orders || []).filter((o) => sourceFilter === 'all' || (o.source || 'manual') === sourceFilter);

  return (
    <div className="space-y-4" data-testid="inv-orders">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Orders</h2>
          <p className="text-sm text-slate-500">All distribution orders — manual, AI-invoice, CRM and Sage 200 (badged by source).</p>
        </div>
        <div className="ml-auto flex flex-wrap gap-2">
          <Btn variant="ai" onClick={() => openCreate("invoice")} data-testid="inv-import-invoice-btn"><Sparkles size={15} /> Import from invoice</Btn>
          <Btn onClick={() => openCreate('manual')} data-testid="inv-new-order-btn"><Plus size={16} /> New order</Btn>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[220px]">
          <Search size={16} className="absolute left-3 top-2.5 text-slate-400" />
          <input className={`${inputCls} pl-9`} placeholder="Search reference, dealer, PO…" value={q} data-testid="inv-orders-search" onChange={(e) => setQ(e.target.value)} />
        </div>
        <select className={inputCls + ' w-auto'} value={sourceFilter} data-testid="inv-orders-source-filter" onChange={(e) => setSourceFilter(e.target.value)}>
          <option value="all">All sources</option>
          <option value="manual">Manual</option>
          <option value="invoice">AI Invoice</option>
          <option value="sage">Sage 200</option>
          <option value="crm">CRM</option>
        </select>
        <select className={inputCls + ' w-auto'} value={statusFilter} data-testid="inv-orders-status-filter" onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="all">All statuses</option>
          <option value="needs_validation">Needs validation</option>
          <option value="awaiting_stock">Awaiting stock</option>
          <option value="partially_available">Partially available</option>
          <option value="reserved">Reserved</option>
          <option value="in_transit">In transit</option>
        </select>
      </div>

      {orders === null ? <Spinner /> : shown.length === 0 ? (
        <Card className="p-10 text-center" testId="inv-orders-empty">
          <p className="text-slate-500">No orders yet.</p>
          <div className="mt-3 flex justify-center gap-2">
            <Btn variant="ai" onClick={() => openCreate("invoice")}><Sparkles size={16} /> Import from invoice</Btn>
            <Btn onClick={() => openCreate('manual')}><Plus size={16} /> Create your first order</Btn>
          </div>
        </Card>
      ) : (
        <Card testId="inv-orders-table">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400"><th className="px-4 py-3">Reference</th><th>Source</th><th>Dealer</th><th>Country</th><th>PO</th><th>Value</th><th>Status</th><th>Created</th></tr></thead>
            <tbody>
              {shown.map((o) => (
                <tr key={o.id} className="cursor-pointer border-b border-slate-100 hover:bg-slate-50" data-testid={`inv-order-row-${o.reference}`} onClick={() => setSelected(o.id)}>
                  <td className="px-4 py-3 font-semibold text-[#0B3D91]">{o.reference}</td>
                  <td><SourceBadge source={o.source} /></td>
                  <td>{o.dealer_name}</td>
                  <td>{o.dealer_country}</td>
                  <td className="text-slate-500">{o.customer_po || '—'}</td>
                  <td className="tabular-nums">{o.currency}</td>
                  <td><StatusBadge status={o.status} /></td>
                  <td className="text-slate-400">{fmtDate(o.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {creating && <CreateOrderModal warehouses={warehouses} autoInvoice={createMode === 'invoice'} onClose={() => setCreating(false)} onCreated={(id) => { setCreating(false); setSelected(id); }} />}
    </div>
  );
}
