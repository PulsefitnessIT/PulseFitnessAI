import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  LayoutDashboard, Boxes, Warehouse, ClipboardList, PackageSearch, PlugZap,
  Settings as SettingsIcon, ArrowLeft, Plus, ScanLine, Truck, MapPin, ShieldCheck,
  FileText, Globe, ChevronRight, ArrowRightLeft, Headphones,
  Radar, ShieldAlert, FileBarChart, PackagePlus, Menu, X, LogOut,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { useAuth } from '@/App';
import { can, isPulseAdmin } from '@/utils/capabilities';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import AreaSwitcher from '@/components/shared/AreaSwitcher';
import { invApi, statusLabel } from './api';
import { Card, StatCard, Spinner, Btn, Field, inputCls } from './ui';
import InvOrders from './InvOrders';
import { SageOrders, OrderExceptions } from './InvSageSync';
import { WarehouseQueue } from './InvFulfilment';
import { Shipments, DealerInventory, TransferOrders } from './InvDealerDist';
import { CustomerAllocations, Installations } from './InvAllocation';
import { DealerServiceDesks } from './InvDealerService';
import { IntelDashboard, IntelAlerts, IntelReports, IntelReplenishment } from './InvIntelligence';

// Full roadmap nav — Phase-1 sections are live, later phases marked "soon".
const NAV = [
  { group: 'Overview', items: [
    { id: 'dashboard', label: 'Dashboard', Icon: LayoutDashboard, live: true },
  ] },
  { group: 'Orders', items: [
    { id: 'sage-orders', label: 'Sage Orders', Icon: FileText, live: true },
    { id: 'orders', label: 'Distribution Orders', Icon: ClipboardList, live: true },
    { id: 'exceptions', label: 'Order Exceptions', Icon: ShieldCheck, live: true },
  ] },
  { group: 'Inventory', items: [
    { id: 'availability', label: 'Stock Availability', Icon: PackageSearch, live: true },
    { id: 'warehouses', label: 'Warehouses', Icon: Warehouse, live: true },
    { id: 'fulfilment', label: 'Fulfilment', Icon: Boxes, live: true },
  ] },
  { group: 'Distribution', items: [
    { id: 'shipments', label: 'Shipments', Icon: Truck, live: true },
    { id: 'transfers', label: 'Transfer Orders', Icon: ArrowRightLeft, live: true },
    { id: 'dealer-inventory', label: 'Dealer Inventory', Icon: Warehouse, live: true },
    { id: 'allocations', label: 'Customer Allocations', Icon: MapPin, live: true },
    { id: 'installations', label: 'Installations', Icon: MapPin, live: true },
  ] },
  { group: 'Service', items: [
    { id: 'service-desks', label: 'Dealer Service Desks', Icon: Headphones, live: true },
  ] },
  { group: 'Intelligence', items: [
    { id: 'intel-dashboard', label: 'Monitoring', Icon: Radar, live: true },
    { id: 'intel-alerts', label: 'Alerts', Icon: ShieldAlert, live: true },
    { id: 'intel-reports', label: 'Reports', Icon: FileBarChart, live: true },
    { id: 'intel-replenishment', label: 'Replenishment', Icon: PackagePlus, live: true },
  ] },
  { group: 'Integration', items: [
    { id: 'sage', label: 'Sage 200 Connection', Icon: PlugZap, live: true },
    { id: 'field-ownership', label: 'Field Ownership', Icon: Globe, live: true },
  ] },
  { group: 'Configure', items: [
    { id: 'settings', label: 'Settings', Icon: SettingsIcon, live: true },
  ] },
];

// ─────────────────────────── Dashboard ───────────────────────────
function Dashboard({ go }) {
  const [d, setD] = useState(null);
  useEffect(() => { invApi.dashboard().then(setD).catch(() => notify.error('Could not load dashboard')); }, []);
  if (!d) return <Spinner />;
  const c = d.cards;
  return (
    <div className="space-y-5" data-testid="inv-dashboard">
      <h2 className="text-xl font-bold text-slate-900">Distribution Dashboard</h2>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard label="Total orders" value={c.orders_total} testId="inv-card-orders" />
        <StatCard label="Needs validation" value={c.needs_validation} tone="amber" testId="inv-card-validation" />
        <StatCard label="Awaiting stock" value={c.awaiting_stock} tone="amber" testId="inv-card-awaiting" />
        <StatCard label="Reserved" value={c.reserved} tone="green" testId="inv-card-reserved" />
        <StatCard label="In transit" value={c.in_transit} tone="navy" testId="inv-card-transit" />
        <StatCard label="Equipment units" value={c.units_total} testId="inv-card-units" />
        <StatCard label="Provisional units" value={c.units_provisional} tone="amber" testId="inv-card-provisional" />
        <StatCard label="Serialised units" value={c.units_serialised} tone="green" testId="inv-card-serialised" />
        <StatCard label="Warehouses" value={c.warehouses} tone="slate" testId="inv-card-warehouses" />
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card className="p-4" testId="inv-dash-country">
          <h3 className="mb-3 text-sm font-bold text-slate-900">Orders by country</h3>
          {d.by_country.length === 0 ? <p className="text-sm text-slate-400">No orders yet.</p> : d.by_country.map((r) => (
            <div key={r.country} className="flex items-center gap-2 py-1 text-sm"><span className="w-16 font-semibold">{r.country}</span><div className="h-2 flex-1 rounded bg-slate-100"><div className="h-2 rounded bg-[#0B3D91]" style={{ width: `${Math.min(100, r.count * 20)}%` }} /></div><span className="tabular-nums text-slate-500">{r.count}</span></div>
          ))}
        </Card>
        <Card className="p-4" testId="inv-dash-recent">
          <div className="mb-3 flex items-center justify-between"><h3 className="text-sm font-bold text-slate-900">Recent orders</h3><button className="text-xs font-semibold text-[#0B3D91]" onClick={() => go('orders')}>View all →</button></div>
          {d.recent_orders.length === 0 ? <p className="text-sm text-slate-400">No orders yet.</p> : d.recent_orders.map((o) => (
            <div key={o.id} className="flex items-center gap-2 border-b border-slate-100 py-2 text-sm last:border-0"><span className="font-semibold text-[#0B3D91]">{o.reference}</span><span className="truncate text-slate-600">{o.dealer_name}</span><span className="ml-auto text-xs text-slate-400">{statusLabel(o.status)}</span></div>
          ))}
        </Card>
      </div>
    </div>
  );
}

// ─────────────────────────── Warehouses ───────────────────────────
function Warehouses() {
  const [rows, setRows] = useState(null);
  const [form, setForm] = useState({ code: '', name: '', type: 'main', country: 'GB' });
  const [expanded, setExpanded] = useState(null);
  const [locs, setLocs] = useState({});
  const [locForm, setLocForm] = useState({ code: '', zone: '', aisle: '', rack: '', shelf: '', bin: '' });

  const load = useCallback(() => invApi.warehouses().then((d) => setRows(d.warehouses || [])).catch(() => setRows([])), []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!form.code.trim() || !form.name.trim()) return;
    try { await invApi.createWarehouse(form); notify.success('Warehouse created'); setForm({ code: '', name: '', type: 'main', country: 'GB' }); load(); }
    catch (e) { notify.error(e?.response?.data?.detail || 'Failed'); }
  };
  const toggle = async (id) => {
    if (expanded === id) { setExpanded(null); return; }
    setExpanded(id);
    const d = await invApi.locations(id); setLocs((m) => ({ ...m, [id]: d.locations || [] }));
  };
  const addLoc = async (id) => {
    if (!locForm.code.trim()) return;
    await invApi.createLocation(id, locForm); notify.success('Location added'); setLocForm({ code: '', zone: '', aisle: '', rack: '', shelf: '', bin: '' });
    const d = await invApi.locations(id); setLocs((m) => ({ ...m, [id]: d.locations || [] })); load();
  };

  return (
    <div className="space-y-5" data-testid="inv-warehouses">
      <h2 className="text-xl font-bold text-slate-900">Warehouses & Locations</h2>
      <Card className="p-4" testId="inv-wh-create">
        <h3 className="mb-3 text-sm font-bold text-slate-900">Add warehouse</h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Field label="Code" required><input className={inputCls} value={form.code} data-testid="inv-wh-code" onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))} /></Field>
          <Field label="Name" required><input className={inputCls} value={form.name} data-testid="inv-wh-name" onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} /></Field>
          <Field label="Type"><select className={inputCls} value={form.type} data-testid="inv-wh-type" onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))}>{['main', 'finished_goods', 'quarantine', 'returns', 'spare_parts', '3pl', 'dealer'].map((t) => <option key={t} value={t}>{statusLabel(t)}</option>)}</select></Field>
          <Field label="Country"><select className={inputCls} value={form.country} data-testid="inv-wh-country" onChange={(e) => setForm((f) => ({ ...f, country: e.target.value }))}>{['GB', 'FR', 'US'].map((t) => <option key={t} value={t}>{t}</option>)}</select></Field>
        </div>
        <Btn className="mt-3" onClick={create} data-testid="inv-wh-submit"><Plus size={15} /> Add warehouse</Btn>
      </Card>

      {rows === null ? <Spinner /> : rows.length === 0 ? <p className="text-sm text-slate-400">No warehouses yet.</p> : rows.map((w) => (
        <Card key={w.id} className="p-4" testId={`inv-wh-row-${w.code}`}>
          <button className="flex w-full items-center gap-3 text-left" onClick={() => toggle(w.id)}>
            <Warehouse size={18} className="text-[#0B3D91]" />
            <div><p className="font-semibold text-slate-900">{w.name}</p><p className="text-xs text-slate-400">{w.code} · {statusLabel(w.type)} · {w.country} · {w.location_count} locations</p></div>
            <ChevronRight size={16} className={`ml-auto text-slate-400 transition-transform ${expanded === w.id ? 'rotate-90' : ''}`} />
          </button>
          {expanded === w.id && (
            <div className="mt-4 border-t border-slate-100 pt-4">
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
                {['code', 'zone', 'aisle', 'rack', 'shelf', 'bin'].map((k) => (
                  <Field key={k} label={statusLabel(k)}><input className={inputCls} value={locForm[k]} data-testid={`inv-loc-${k}`} onChange={(e) => setLocForm((f) => ({ ...f, [k]: e.target.value }))} /></Field>
                ))}
              </div>
              <Btn variant="secondary" className="mt-2" onClick={() => addLoc(w.id)} data-testid={`inv-loc-add-${w.code}`}><Plus size={14} /> Add location</Btn>
              <div className="mt-3 flex flex-wrap gap-2">
                {(locs[w.id] || []).map((l) => (
                  <span key={l.id} className="inline-flex items-center gap-1 rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-mono text-slate-700" data-testid={`inv-loc-chip-${l.code}`}><MapPin size={12} /> {l.code}</span>
                ))}
              </div>
            </div>
          )}
        </Card>
      ))}
    </div>
  );
}

// ─────────────────────────── Stock availability ───────────────────────────
function StockAvailability({ warehouses }) {
  const [rows, setRows] = useState(null);
  const [rec, setRec] = useState({ warehouse_id: warehouses[0]?.id || '', product_code: '', quantity: 1 });

  const load = useCallback(() => invApi.availability().then((d) => setRows(d.holdings || [])).catch(() => setRows([])), []);
  useEffect(() => { load(); }, [load]);

  const receive = async () => {
    if (!rec.warehouse_id || !rec.product_code.trim()) { notify.error('Warehouse + product code required'); return; }
    try { await invApi.receiveStock({ ...rec, quantity: Number(rec.quantity) }); notify.success('Stock received'); setRec((r) => ({ ...r, product_code: '', quantity: 1 })); load(); }
    catch (e) { notify.error(e?.response?.data?.detail || 'Failed'); }
  };
  const whName = (id) => warehouses.find((w) => w.id === id)?.name || id;

  return (
    <div className="space-y-5" data-testid="inv-availability">
      <h2 className="text-xl font-bold text-slate-900">Stock Availability</h2>
      <Card className="p-4" testId="inv-receive">
        <h3 className="mb-3 text-sm font-bold text-slate-900">Receive stock (quick seed)</h3>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[180px]"><Field label="Warehouse"><select className={inputCls} value={rec.warehouse_id} data-testid="inv-receive-wh" onChange={(e) => setRec((r) => ({ ...r, warehouse_id: e.target.value }))}><option value="">—</option>{warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</select></Field></div>
          <div className="min-w-[140px]"><Field label="Product code"><input className={inputCls} value={rec.product_code} data-testid="inv-receive-code" onChange={(e) => setRec((r) => ({ ...r, product_code: e.target.value }))} /></Field></div>
          <div className="w-24"><Field label="Qty"><input type="number" min="1" className={inputCls} value={rec.quantity} data-testid="inv-receive-qty" onChange={(e) => setRec((r) => ({ ...r, quantity: e.target.value }))} /></Field></div>
          <Btn onClick={receive} data-testid="inv-receive-btn"><Truck size={15} /> Receive</Btn>
        </div>
      </Card>

      {rows === null ? <Spinner /> : rows.length === 0 ? <Card className="p-8 text-center text-slate-400" testId="inv-stock-empty">No stock recorded yet.</Card> : (
        <Card testId="inv-stock-table">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400"><th className="px-4 py-3">Product</th><th>Warehouse</th><th>On hand</th><th>Reserved</th><th>Available</th></tr></thead>
            <tbody>
              {rows.map((h) => (
                <tr key={h.id} className="border-b border-slate-100" data-testid={`inv-stock-row-${h.product_code}`}>
                  <td className="px-4 py-3 font-mono text-xs">{h.product_code}</td>
                  <td>{whName(h.warehouse_id)}</td>
                  <td className="tabular-nums">{h.qty_on_hand}</td>
                  <td className="tabular-nums text-amber-600">{h.qty_reserved}</td>
                  <td className="tabular-nums font-semibold text-emerald-600">{h.qty_available}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

// ─────────────────────────── Sage connection + capability discovery ───────────────────────────
function SageConnection() {
  const [conn, setConn] = useState(null);
  const [form, setForm] = useState({ edition: 'standard', version: '', company: '', api_base: '', limitations: '' });
  const [caps, setCaps] = useState(null);

  useEffect(() => {
    invApi.sageConnection().then((d) => { setConn(d.connection); if (d.connection) setForm((f) => ({ ...f, ...d.connection })); });
    invApi.sageDiscover().then(setCaps).catch(() => {});
  }, []);

  const save = async () => { try { const d = await invApi.saveSageConnection(form); setConn(d.connection); notify.success('Sage connection saved'); } catch (e) { notify.error('Failed'); } };

  return (
    <div className="space-y-5" data-testid="inv-sage">
      <h2 className="text-xl font-bold text-slate-900">Sage 200 Connection & Capability Discovery</h2>
      <div className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-800">
        Credentials not yet configured — orders are entered manually. Save your Sage deployment details here so the integration can be wired the moment API access is provided. <strong>Write-back to Sage stays disabled by design.</strong>
      </div>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card className="p-4" testId="inv-sage-form">
          <h3 className="mb-3 text-sm font-bold text-slate-900">Deployment details</h3>
          <div className="space-y-3">
            <Field label="Edition"><select className={inputCls} value={form.edition} data-testid="inv-sage-edition" onChange={(e) => setForm((f) => ({ ...f, edition: e.target.value }))}><option value="standard">Standard</option><option value="professional">Professional</option></select></Field>
            <Field label="Version"><input className={inputCls} value={form.version || ''} data-testid="inv-sage-version" onChange={(e) => setForm((f) => ({ ...f, version: e.target.value }))} /></Field>
            <Field label="Connected company"><input className={inputCls} value={form.company || ''} data-testid="inv-sage-company" onChange={(e) => setForm((f) => ({ ...f, company: e.target.value }))} /></Field>
            <Field label="API base URL"><input className={inputCls} value={form.api_base || ''} placeholder="https://api.columbus.sage.com/uk/sage200…" data-testid="inv-sage-base" onChange={(e) => setForm((f) => ({ ...f, api_base: e.target.value }))} /></Field>
            <Field label="Known limitations"><input className={inputCls} value={form.limitations || ''} data-testid="inv-sage-limits" onChange={(e) => setForm((f) => ({ ...f, limitations: e.target.value }))} /></Field>
          </div>
          <Btn className="mt-3" onClick={save} data-testid="inv-sage-save"><PlugZap size={15} /> Save connection</Btn>
          {conn && <p className="mt-2 text-xs text-slate-400">Auth status: {conn.auth_status}</p>}
        </Card>
        <Card className="p-4" testId="inv-sage-caps">
          <h3 className="mb-3 text-sm font-bold text-slate-900">Capability discovery</h3>
          {!caps ? <Spinner /> : (
            <div className="space-y-2 text-sm">
              <p className="text-xs text-slate-400">{caps.message}</p>
              {Object.entries(caps.capabilities).map(([k, v]) => (
                <div key={k} className="flex items-start gap-2 border-b border-slate-100 py-1.5 last:border-0">
                  <span className={`mt-0.5 h-2 w-2 rounded-full ${v.available === true ? 'bg-emerald-500' : v.available === false ? 'bg-rose-500' : 'bg-slate-300'}`} />
                  <div><p className="font-semibold text-slate-700">{statusLabel(k)}</p><p className="text-[11px] text-slate-400">{v.note}</p></div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

// ─────────────────────────── Field ownership matrix ───────────────────────────
function FieldOwnership() {
  const [d, setD] = useState(null);
  useEffect(() => { invApi.fieldOwnership().then(setD).catch(() => {}); }, []);
  if (!d) return <Spinner />;
  return (
    <div className="space-y-4" data-testid="inv-field-ownership">
      <h2 className="text-xl font-bold text-slate-900">System-of-Record — Field Ownership Matrix</h2>
      <p className="text-sm text-slate-500">Sage 200 stays authoritative for commercial/accounting fields; PulseFitness.ai owns the operational workflow. Sage data is never overwritten without an approved endpoint.</p>
      <Card testId="inv-fo-table">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400"><th className="px-4 py-3">Field</th><th>Record</th><th>Authoritative</th><th>Direction</th><th>Override</th><th>Reconciliation</th></tr></thead>
          <tbody>
            {d.matrix.map((r, i) => (
              <tr key={i} className="border-b border-slate-100" data-testid={`inv-fo-row-${i}`}>
                <td className="px-4 py-2.5 font-mono text-xs">{r.field}</td>
                <td className="text-slate-500">{r.record}</td>
                <td><span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${r.authoritative.includes('Sage') ? 'bg-indigo-100 text-indigo-700' : 'bg-blue-100 text-blue-700'}`}>{r.authoritative}</span></td>
                <td className="text-xs text-slate-500">{r.direction}</td>
                <td className="text-xs text-slate-500">{r.override}</td>
                <td className="text-xs text-slate-500">{r.reconciliation}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Card className="p-4" testId="inv-fo-states">
        <h3 className="mb-2 text-sm font-bold text-slate-900">Sage posting states</h3>
        <div className="flex flex-wrap gap-2">{d.sage_posting_states.map((s) => <span key={s} className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">{s}</span>)}</div>
      </Card>
    </div>
  );
}

// ─────────────────────────── Settings ───────────────────────────
function SettingsView({ warehouses }) {
  const [s, setS] = useState(null);
  useEffect(() => { invApi.settings().then(setS).catch(() => {}); }, []);
  if (!s) return <Spinner />;
  const save = async (patch) => { try { const d = await invApi.saveSettings(patch); setS(d); notify.success('Saved'); } catch (e) { notify.error('Failed'); } };
  const Toggle = ({ k, label }) => (
    <label className="flex items-center justify-between border-b border-slate-100 py-2.5" data-testid={`inv-setting-${k}`}>
      <span className="text-sm text-slate-700">{label}</span>
      <input type="checkbox" checked={!!s[k]} onChange={(e) => save({ [k]: e.target.checked })} className="h-4 w-8 accent-[#0B3D91]" />
    </label>
  );
  return (
    <div className="space-y-5" data-testid="inv-settings">
      <h2 className="text-xl font-bold text-slate-900">Settings</h2>
      <Card className="p-4">
        <Toggle k="sage_integration_enabled" label="Sage 200 integration enabled" />
        <Toggle k="automatic_order_import" label="Automatic order import from Sage" />
        <Toggle k="qc_required" label="Quality control required before dispatch" />
        <Toggle k="dealer_receipt_required" label="Dealer receipt confirmation required" />
        <Toggle k="dealer_allocation_required" label="Dealer must allocate to a customer" />
        <div className="grid grid-cols-2 gap-3 pt-3 sm:grid-cols-3">
          <Field label="Default warehouse"><select className={inputCls} value={s.default_warehouse_id || ''} data-testid="inv-setting-default-wh" onChange={(e) => save({ default_warehouse_id: e.target.value })}><option value="">—</option>{warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</select></Field>
          <Field label="Currency display"><select className={inputCls} value={s.currency_display} data-testid="inv-setting-currency" onChange={(e) => save({ currency_display: e.target.value })}>{['GBP', 'EUR', 'USD'].map((c) => <option key={c} value={c}>{c}</option>)}</select></Field>
          <Field label="Warranty activation rule"><select className={inputCls} value={s.warranty_activation_rule} data-testid="inv-setting-warranty" onChange={(e) => save({ warranty_activation_rule: e.target.value })}>{['dispatch_date', 'dealer_receipt_date', 'delivery_date', 'installation_date', 'commissioning_date', 'invoice_date'].map((c) => <option key={c} value={c}>{statusLabel(c)}</option>)}</select></Field>
        </div>
      </Card>
      <Card className="p-4" testId="inv-country-profiles">
        <h3 className="mb-2 text-sm font-bold text-slate-900">Country profiles</h3>
        <table className="w-full text-sm"><thead><tr className="text-left text-xs uppercase text-slate-400"><th className="pb-2">Country</th><th>Language</th><th>Currency</th><th>Units</th><th>Date format</th></tr></thead>
          <tbody>{(s.country_profiles || []).map((c) => <tr key={c.code} className="border-t border-slate-100"><td className="py-2 font-semibold">{c.name}</td><td>{c.language}</td><td>{c.currency}</td><td>{c.measurement}</td><td>{c.date_format}</td></tr>)}</tbody>
        </table>
      </Card>
    </div>
  );
}

// ─────────────────────────── "Coming soon" placeholder ───────────────────────────
function ComingSoon({ label }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center" data-testid="inv-coming-soon">
      <Boxes size={40} className="mb-3 text-slate-300" />
      <h2 className="text-lg font-bold text-slate-700">{label}</h2>
      <p className="mt-1 max-w-md text-sm text-slate-400">This part of the distribution lifecycle is being delivered in a later phase. The foundation, orders, stock, serial capture and Sage scaffold are live now.</p>
    </div>
  );
}

// ─────────────────────────── Shell ───────────────────────────
const FULFILMENT_STAGES = [
  { key: 'receiving', label: 'Receiving', stage: 'receiving', title: 'Receiving', Icon: Truck },
  { key: 'picking', label: 'Picking', stage: 'picking', title: 'Picking Queue', Icon: PackageSearch },
  { key: 'quality', label: 'Quality Control', stage: 'qc', title: 'Quality Control Queue', Icon: ShieldCheck },
  { key: 'packing', label: 'Packing', stage: 'packing', title: 'Packing Queue', Icon: ScanLine },
  { key: 'dispatch', label: 'Dispatch', stage: 'dispatch', title: 'Dispatch Queue', Icon: Truck },
];
const FULFILMENT_KEYS = FULFILMENT_STAGES.map((s) => s.key);

function Fulfilment({ initialStage = 'receiving' }) {
  const [active, setActive] = useState(FULFILMENT_KEYS.includes(initialStage) ? initialStage : 'receiving');
  const st = FULFILMENT_STAGES.find((s) => s.key === active) || FULFILMENT_STAGES[0];
  return (
    <div className="space-y-4" data-testid="inv-fulfilment">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Fulfilment</h2>
        <p className="text-sm text-slate-500">Work the warehouse pipeline end to end — receive, pick, QC, pack and dispatch.</p>
      </div>
      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-3" data-testid="inv-fulfilment-tabs">
        {FULFILMENT_STAGES.map((s, i) => {
          const on = s.key === active;
          return (
            <button
              key={s.key}
              onClick={() => setActive(s.key)}
              data-testid={`inv-fulfilment-tab-${s.key}`}
              className={`inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-semibold transition-colors ${on ? 'bg-[#0B3D91] text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
            >
              <span className={`flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-bold ${on ? 'bg-white/25 text-white' : 'bg-slate-300 text-slate-600'}`}>{i + 1}</span>
              <s.Icon size={14} /> {s.label}
            </button>
          );
        })}
      </div>
      <WarehouseQueue key={st.stage} stage={st.stage} title={st.title} />
    </div>
  );
}

export default function InventoryDistribution() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [sp, setSp] = useSearchParams();
  const section = sp.get('s') || 'dashboard';
  const orderId = sp.get('order') || null;
  const [warehouses, setWarehouses] = useState([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => { invApi.warehouses().then((d) => setWarehouses(d.warehouses || [])).catch(() => {}); }, [section]);

  const go = (id) => { setSp(id === 'dashboard' ? {} : { s: id }); setSidebarOpen(false); };

  const findItem = () => { const sec = FULFILMENT_KEYS.includes(section) ? 'fulfilment' : section; for (const g of NAV) { const it = g.items.find((x) => x.id === sec); if (it) return it; } return null; };
  const item = findItem();

  const render = () => {
    if (item && !item.live) return <ComingSoon label={item.label} />;
    switch (section) {
      case 'dashboard': return <Dashboard go={go} />;
      case 'sage-orders': return <SageOrders />;
      case 'orders': return <InvOrders warehouses={warehouses} initialOrderId={orderId} />;
      case 'exceptions': return <OrderExceptions />;
      case 'fulfilment': return <Fulfilment initialStage="receiving" />;
      case 'receiving': return <Fulfilment initialStage="receiving" />;
      case 'picking': return <Fulfilment initialStage="picking" />;
      case 'quality': return <Fulfilment initialStage="quality" />;
      case 'packing': return <Fulfilment initialStage="packing" />;
      case 'dispatch': return <Fulfilment initialStage="dispatch" />;
      case 'shipments': return <Shipments />;
      case 'transfers': return <TransferOrders warehouses={warehouses} />;
      case 'dealer-inventory': return <DealerInventory />;
      case 'allocations': return <CustomerAllocations />;
      case 'installations': return <Installations />;
      case 'service-desks': return <DealerServiceDesks />;
      case 'intel-dashboard': return <IntelDashboard go={go} />;
      case 'intel-alerts': return <IntelAlerts />;
      case 'intel-reports': return <IntelReports />;
      case 'intel-replenishment': return <IntelReplenishment />;
      case 'availability': return <StockAvailability warehouses={warehouses} />;
      case 'warehouses': return <Warehouses />;
      case 'sage': return <SageConnection />;
      case 'field-ownership': return <FieldOwnership />;
      case 'settings': return <SettingsView warehouses={warehouses} />;
      default: return <ComingSoon label={item?.label || 'Section'} />;
    }
  };

  return (
    <div className="min-h-screen bg-[var(--gx-bg)] flex theme-gymaxis" data-testid="inventory-distribution-page" data-theme="light">
      {/* Mobile backdrop */}
      {sidebarOpen && (
        <button
          type="button"
          aria-label="Close sidebar"
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-30 bg-black/40 md:hidden"
          data-testid="inv-sidebar-backdrop"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 w-60 bg-white border-r border-slate-200 flex flex-col transition-transform duration-200 md:translate-x-0 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}`}
      >
        {/* Logo header */}
        <div className="p-5 border-b border-slate-100 flex items-start justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-white flex items-center justify-center overflow-hidden gx-grad-ring shadow-sm">
              <img src="/brand/pulse-mark.svg" alt="Pulse Fitness" className="w-6 h-6 object-contain" draggable={false} loading="eager" decoding="async" />
            </div>
            <div>
              <div className="text-sm font-bold text-slate-900 tracking-tight">Inventory &amp; Distribution</div>
              <div className="text-[10px] text-slate-400 uppercase tracking-[0.16em] font-semibold">Dealer distribution</div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setSidebarOpen(false)}
            className="md:hidden text-slate-400 hover:text-slate-700"
            aria-label="Close sidebar"
            data-testid="inv-sidebar-close"
          >
            <X size={18} />
          </button>
        </div>

        {/* Nav groups */}
        <nav className="flex-1 p-3 overflow-y-auto" data-testid="inv-nav">
          {NAV.map((g) => (
            <div key={g.group}>
              <p className="text-[9px] uppercase tracking-[0.16em] text-slate-400 px-3 pt-4 pb-1 font-semibold first:pt-1">{g.group}</p>
              {g.items.map((it) => {
                const active = it.id === section || (it.id === 'fulfilment' && FULFILMENT_KEYS.includes(section));
                return (
                  <button
                    key={it.id}
                    onClick={() => go(it.id)}
                    data-testid={`inv-nav-${it.id}`}
                    className={`w-full text-left px-3 py-2 rounded-lg text-sm flex items-center gap-2 transition-all ${
                      active
                        ? 'bg-gradient-to-r from-[var(--gx-brand-from)]/10 to-[var(--gx-brand-to)]/10 text-[var(--gx-brand-from)] font-semibold ring-1 ring-[var(--gx-brand-from)]/15'
                        : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                    }`}
                  >
                    <it.Icon className="w-4 h-4" />
                    <span className="flex-1 truncate">{it.label}</span>
                    {!it.live && <span className="ml-auto rounded px-1 text-[9px] font-bold bg-slate-200 text-slate-500">SOON</span>}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>

        {/* User footer */}
        <div className="border-t border-slate-100 p-3 space-y-2">
          <div className="text-xs text-slate-500 px-1">
            <div className="font-medium text-slate-700 truncate">{user?.full_name || user?.email}</div>
            <div className="truncate">{user?.email}</div>
            {user?.is_master_admin && <Badge variant="outline" className="mt-1 text-[9px] border-slate-200">Master Admin</Badge>}
            {!user?.is_master_admin && isPulseAdmin(user) && <Badge variant="outline" className="mt-1 text-[9px] border-slate-200">Pulse Master Admin</Badge>}
          </div>
          {/* Module selector — hop between Service Desk / Inventory / Main app */}
          <AreaSwitcher user={user} tone="sidebar" className="mb-1" />
          {(user?.is_master_admin || isPulseAdmin(user)) && (
            <Button
              variant="ghost" size="sm"
              onClick={() => navigate('/master-admin')}
              className="w-full justify-start text-slate-600 hover:text-slate-900"
              data-testid="inv-back-to-master-admin"
            >
              <ArrowLeft className="w-4 h-4 mr-2" /> Back to Master Admin
            </Button>
          )}
          <Button
            variant="ghost" size="sm"
            onClick={() => { logout(); navigate('/login'); }}
            className="w-full justify-start text-slate-600 hover:text-slate-900"
            data-testid="inv-logout"
          >
            <LogOut className="w-4 h-4 mr-2" /> Log out
          </Button>
        </div>
      </aside>

      <main className="flex-1 md:ml-60 p-4 sm:p-6 md:p-8 max-w-[1400px] w-full" data-testid="inv-main">
        {/* Mobile top bar */}
        <div className="md:hidden flex items-center justify-between mb-4 sticky top-0 z-20 bg-[var(--gx-bg)] py-2">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            className="inline-flex items-center justify-center w-9 h-9 rounded-lg border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
            aria-label="Open navigation"
            data-testid="inv-sidebar-open"
          >
            <Menu size={18} />
          </button>
          <div className="text-sm font-bold text-slate-900 truncate">{item?.label || 'Inventory'}</div>
          <div className="w-9" aria-hidden />
        </div>
        {render()}
      </main>
    </div>
  );
}
