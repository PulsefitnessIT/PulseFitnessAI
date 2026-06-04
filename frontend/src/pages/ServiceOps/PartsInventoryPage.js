/**
 * PartsInventoryPage — iter 215dr (Phase 4).
 *
 * Operator-facing parts inventory console at /service-ops/parts.
 *
 * Three tabs:
 *   • Catalogue — SKU master + Sicon import paste-in
 *   • Stock & reorder — warehouse stock, low-stock pills, reorder rules
 *   • Purchase orders — drafts, submitted, received; create from
 *     low-stock; mark received
 *
 * Design pulls the same operator language as ServiceDeskPage so it
 * feels like one console.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  Package, Boxes, FileText, AlertTriangle, Plus, Send, CheckCircle,
  Trash2, Edit3, Inbox, X, Truck,
} from 'lucide-react';
import SupplierMultiPicker from '@/components/shared/SupplierMultiPicker';
import { notify } from '@/components/notifications';
import ServiceOpsShell from './ServiceOpsShell';
import { useLocalization, formatMoneySync, getCachedLocalization } from '@/utils/localization';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const TABS = [
  { id: 'catalogue', label: 'Catalogue', icon: Package },
  { id: 'stock', label: 'Stock & reorder', icon: Boxes },
  { id: 'pos', label: 'Purchase orders', icon: FileText },
];

const PO_STATUS_COLOUR = {
  draft: '#6b7280', submitted: '#1d4ed8', received: '#10b981', cancelled: '#ef4444',
};

function gbp(n) { return formatMoneySync(n); }

export default function PartsInventoryPage() {
  useLocalization();  // warm currency cache
  const [tab, setTab] = useState('catalogue');
  return (
    <ServiceOpsShell
      icon={Package}
      title="Parts inventory"
      subtitle="Catalogue, warehouse + van stock, low-stock alerts, and supplier purchase orders. Pulse Fitness orgs sync from Sage / Sicon."
      active="parts"
      pageTestId="parts-inventory-page"
    >
      <nav className="svc-tabs">
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`svc-tab ${active ? 'svc-tab--active' : ''}`}
              data-testid={`parts-tab-${t.id}`}
            >
              <Icon size={13} /> {t.label}
            </button>
          );
        })}
      </nav>

      {tab === 'catalogue' ? <CatalogueTab /> : null}
      {tab === 'stock' ? <StockTab /> : null}
      {tab === 'pos' ? <POTab /> : null}
    </ServiceOpsShell>
  );
}

// ── Catalogue ────────────────────────────────────────────────────
function CatalogueTab() {
  const [parts, setParts] = useState([]);
  const [search, setSearch] = useState('');
  const [draft, setDraft] = useState({ sku: '', name: '', manufacturer: '', supplier: '', cost: 0 });
  const [busy, setBusy] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importPayload, setImportPayload] = useState('');

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/svc/parts`, { ...auth(), params: { search, limit: 100 } });
      setParts(r.data.parts || []);
    } catch (e) { notify.error('Could not load catalogue', e?.response?.data?.detail || e.message); }
  }, [search]);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!draft.sku.trim() || !draft.name.trim()) { notify.error('SKU and name required'); return; }
    setBusy(true);
    try {
      await axios.post(`${API}/svc/parts`, draft, auth());
      setDraft({ sku: '', name: '', manufacturer: '', supplier: '', cost: 0 });
      notify.success('Part added');
      load();
    } catch (e) { notify.error('Could not add', e?.response?.data?.detail || e.message); }
    finally { setBusy(false); }
  };

  const sicon = async () => {
    let parts;
    try { parts = JSON.parse(importPayload); } catch { notify.error('JSON parse error'); return; }
    if (!Array.isArray(parts)) { notify.error('Expected an array'); return; }
    setBusy(true);
    try {
      const r = await axios.post(`${API}/svc/parts/imports/sicon`, { parts }, auth());
      notify.success('Sicon import complete', `Inserted ${r.data.inserted}, updated ${r.data.updated}`);
      setImporting(false);
      setImportPayload('');
      load();
    } catch (e) { notify.error('Import failed', e?.response?.data?.detail || e.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-4" data-testid="parts-catalogue-tab">
      <div className="flex items-center gap-2 flex-wrap">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search SKU / name / manufacturer…"
          className="flex-1 min-w-[14rem] px-3 py-1.5 rounded-md border bg-transparent text-sm"
          style={{ borderColor: 'var(--theme-border)' }}
          data-testid="catalogue-search"
        />
        <button
          type="button"
          onClick={() => setImporting(true)}
          className="px-3 py-1.5 rounded-md border text-xs font-bold inline-flex items-center gap-1"
          style={{ borderColor: 'var(--theme-border)' }}
          data-testid="catalogue-sicon-import"
        >
          <Inbox size={12} /> Import from Sicon
        </button>
      </div>

      <div className="grid grid-cols-12 gap-2 items-end rounded-md border p-3" style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }} data-testid="catalogue-add-row">
        <Field className="col-span-2" label="SKU"><input value={draft.sku} onChange={(e) => setDraft({ ...draft, sku: e.target.value.toUpperCase() })} className="ip" data-testid="catalogue-add-sku" /></Field>
        <Field className="col-span-4" label="Name"><input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} className="ip" data-testid="catalogue-add-name" /></Field>
        <Field className="col-span-2" label="Manufacturer"><input value={draft.manufacturer} onChange={(e) => setDraft({ ...draft, manufacturer: e.target.value })} className="ip" data-testid="catalogue-add-mfr" /></Field>
        <Field className="col-span-2" label="Supplier">
          <SupplierMultiPicker
            single
            value={draft.supplier}
            onChange={(v) => setDraft({ ...draft, supplier: v })}
            placeholder="Pick a supplier or add a new one…"
            testid="catalogue-add-supplier"
          />
        </Field>
        <Field className="col-span-1" label={`Cost ${getCachedLocalization().currency_symbol}`}><input type="number" value={draft.cost} onChange={(e) => setDraft({ ...draft, cost: Number(e.target.value) })} className="ip tabular-nums" data-testid="catalogue-add-cost" /></Field>
        <button
          type="button"
          onClick={create}
          disabled={busy}
          className="col-span-1 px-2 py-1.5 rounded-md text-xs font-bold text-white inline-flex items-center justify-center gap-1 disabled:opacity-60"
          style={{ background: 'var(--color-brand-blue, #1d4ed8)' }}
          data-testid="catalogue-add-submit"
        >
          <Plus size={11} /> Add
        </button>
      </div>

      <div className="rounded-md border overflow-hidden" style={{ borderColor: 'var(--theme-border)' }}>
        <table className="w-full text-sm">
          <thead style={{ background: 'var(--theme-surface)' }}>
            <tr className="text-left text-[11px] uppercase tracking-wider opacity-70">
              <th className="px-3 py-2">SKU</th>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">Manufacturer</th>
              <th className="px-3 py-2">Supplier</th>
              <th className="px-3 py-2 text-right">Cost</th>
              <th className="px-3 py-2">Sage / Sicon</th>
            </tr>
          </thead>
          <tbody>
            {parts.length === 0 ? (
              <tr><td colSpan="6" className="px-3 py-10 text-center opacity-70 text-xs">
                Empty catalogue. Add a part above, or click <strong>Import from Sicon</strong>.
              </td></tr>
            ) : parts.map((p) => (
              <tr key={p.id} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`catalogue-row-${p.sku}`}>
                <td className="px-3 py-2 font-bold tabular-nums">{p.sku}</td>
                <td className="px-3 py-2">{p.name}</td>
                <td className="px-3 py-2 text-xs opacity-80">{p.manufacturer || '—'}</td>
                <td className="px-3 py-2 text-xs opacity-80">{p.supplier || '—'}</td>
                <td className="px-3 py-2 text-right tabular-nums">{gbp(p.cost)}</td>
                <td className="px-3 py-2 text-[10px] opacity-70">{p.sage_stock_code || p.sicon_part_id ? `${p.sage_stock_code || ''} ${p.sicon_part_id ? `· ${p.sicon_part_id}` : ''}` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {importing ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.6)' }} data-testid="sicon-import-modal">
          <div className="w-full max-w-2xl rounded-xl border shadow-xl" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
            <div className="px-4 py-3 border-b flex items-center justify-between" style={{ borderColor: 'var(--theme-border)' }}>
              <p className="font-bold inline-flex items-center gap-1.5"><Inbox size={14} /> Sicon parts import</p>
              <button type="button" aria-label="Close" onClick={() => setImporting(false)}><X size={14} /></button>
            </div>
            <div className="p-4 space-y-2">
              <p className="text-xs opacity-70">Paste a JSON array exported from Sicon. Each row needs at least <code>{'{ sku, name }'}</code>; <code>sicon_part_id</code> + <code>sage_stock_code</code> are kept for the cutover worker.</p>
              <textarea
                value={importPayload}
                onChange={(e) => setImportPayload(e.target.value)}
                rows={10}
                className="w-full px-2 py-1.5 rounded-md border bg-transparent text-xs font-mono"
                style={{ borderColor: 'var(--theme-border)' }}
                placeholder='[{"sku":"TM-BLT","name":"Treadmill belt","sicon_part_id":"SP-117"}]'
                data-testid="sicon-import-payload"
              />
              <div className="flex justify-end gap-2">
                <button type="button" onClick={() => setImporting(false)} className="px-3 py-1.5 rounded-md border text-xs font-bold" style={{ borderColor: 'var(--theme-border)' }}>Cancel</button>
                <button type="button" onClick={sicon} disabled={busy} className="px-3 py-1.5 rounded-md text-xs font-bold text-white" style={{ background: 'var(--color-brand-blue, #1d4ed8)' }} data-testid="sicon-import-submit">Run import</button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <style>{`.ip{width:100%;padding:6px 8px;border:1px solid var(--theme-border);border-radius:6px;font-size:13px;background:transparent}`}</style>
    </div>
  );
}

// ── Stock & reorder ──────────────────────────────────────────────
function StockTab() {
  const [stock, setStock] = useState([]);
  const [low, setLow] = useState([]);
  const [rules, setRules] = useState([]);
  const [draftRule, setDraftRule] = useState({ part_sku: '', location: 'warehouse', min_qty: 1, max_qty: 5, supplier: '' });
  const [_adjusting, _setAdjusting] = useState(null); // {part_sku}

  const load = useCallback(async () => {
    try {
      const [a, b, c] = await Promise.all([
        axios.get(`${API}/svc/inventory/stock?location=warehouse`, auth()),
        axios.get(`${API}/svc/inventory/low-stock`, auth()),
        axios.get(`${API}/svc/inventory/reorder-rules`, auth()),
      ]);
      setStock(a.data.stock || []);
      setLow(b.data.rows || []);
      setRules(c.data.rules || []);
    } catch (e) { notify.error('Could not load stock', e?.response?.data?.detail || e.message); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const submitRule = async () => {
    if (!draftRule.part_sku.trim()) { notify.error('SKU required'); return; }
    try {
      await axios.post(`${API}/svc/inventory/reorder-rules`, draftRule, auth());
      notify.success('Reorder rule saved');
      setDraftRule({ part_sku: '', location: 'warehouse', min_qty: 1, max_qty: 5, supplier: '' });
      load();
    } catch (e) { notify.error('Could not save rule', e?.response?.data?.detail || e.message); }
  };

  const removeRule = async (id) => {
    try { await axios.delete(`${API}/svc/inventory/reorder-rules/${id}`, auth()); load(); }
    catch (e) { notify.error('Delete failed', e?.response?.data?.detail || e.message); }
  };

  const adjust = async (sku, delta) => {
    try {
      await axios.post(`${API}/svc/inventory/stock/adjust`,
        { part_sku: sku, qty: delta, location: 'warehouse', reason: 'manual count' },
        auth());
      load();
    } catch (e) { notify.error('Adjust failed', e?.response?.data?.detail || e.message); }
  };

  return (
    <div className="space-y-5" data-testid="parts-stock-tab">
      {low.length > 0 ? (
        <div className="rounded-xl border p-3 space-y-2" style={{ borderColor: '#fecaca', background: '#fef2f2' }} data-testid="low-stock-banner">
          <p className="text-xs font-extrabold inline-flex items-center gap-1.5" style={{ color: '#b91c1c' }}>
            <AlertTriangle size={13} /> {low.length} part{low.length === 1 ? '' : 's'} below the reorder threshold
          </p>
          <ul className="space-y-1 text-xs">
            {low.map((r) => (
              <li key={`${r.part_sku}-${r.location}-${r.engineer_id}`} className="flex items-center justify-between gap-2" data-testid={`low-stock-row-${r.part_sku}`}>
                <span><strong>{r.part_sku}</strong> {r.part?.name ? `— ${r.part.name}` : ''} <span className="opacity-60">· {r.location}{r.engineer_id ? ` (eng ${r.engineer_id.slice(0, 6)})` : ''}</span></span>
                <span className="tabular-nums opacity-80">on hand <strong>{r.on_hand}</strong> / min {r.min_qty} → reorder <strong>{r.shortfall}</strong></span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <section className="rounded-md border" style={{ borderColor: 'var(--theme-border)' }}>
        <div className="px-3 py-2 border-b font-bold inline-flex items-center gap-1.5" style={{ borderColor: 'var(--theme-border)' }}><Boxes size={13} /> Warehouse stock</div>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] uppercase tracking-wider opacity-70"><th className="px-3 py-2">SKU</th><th className="px-3 py-2">Name</th><th className="px-3 py-2 text-right">On hand</th><th className="px-3 py-2 text-right">Adjust</th></tr></thead>
          <tbody>
            {stock.length === 0 ? (
              <tr><td colSpan="4" className="px-3 py-6 text-center opacity-60 text-xs">No warehouse stock yet. Receive a PO or adjust manually.</td></tr>
            ) : stock.map((s) => (
              <tr key={s.id} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`stock-row-${s.part_sku}`}>
                <td className="px-3 py-2 font-bold tabular-nums">{s.part_sku}</td>
                <td className="px-3 py-2">{s.part?.name || '—'}</td>
                <td className="px-3 py-2 text-right tabular-nums">{s.qty}</td>
                <td className="px-3 py-2 text-right">
                  <button type="button" onClick={() => adjust(s.part_sku, +1)} className="px-1.5 py-0.5 text-[11px] rounded border mr-1" style={{ borderColor: 'var(--theme-border)' }} data-testid={`stock-plus-${s.part_sku}`}>+1</button>
                  <button type="button" onClick={() => adjust(s.part_sku, -1)} className="px-1.5 py-0.5 text-[11px] rounded border" style={{ borderColor: 'var(--theme-border)' }} data-testid={`stock-minus-${s.part_sku}`}>-1</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="rounded-md border" style={{ borderColor: 'var(--theme-border)' }}>
        <div className="px-3 py-2 border-b font-bold inline-flex items-center gap-1.5" style={{ borderColor: 'var(--theme-border)' }}><Edit3 size={13} /> Reorder rules</div>
        <div className="grid grid-cols-12 gap-2 p-3 items-end" data-testid="rule-add-row">
          <Field className="col-span-3" label="SKU"><input value={draftRule.part_sku} onChange={(e) => setDraftRule({ ...draftRule, part_sku: e.target.value.toUpperCase() })} className="ip" data-testid="rule-add-sku" /></Field>
          <Field className="col-span-2" label="Location">
            <select value={draftRule.location} onChange={(e) => setDraftRule({ ...draftRule, location: e.target.value })} className="ip" data-testid="rule-add-location">
              <option value="warehouse">warehouse</option>
              <option value="van">van</option>
            </select>
          </Field>
          <Field className="col-span-1" label="Min"><input type="number" min={0} value={draftRule.min_qty} onChange={(e) => setDraftRule({ ...draftRule, min_qty: Number(e.target.value) })} className="ip tabular-nums" data-testid="rule-add-min" /></Field>
          <Field className="col-span-1" label="Max"><input type="number" min={0} value={draftRule.max_qty} onChange={(e) => setDraftRule({ ...draftRule, max_qty: Number(e.target.value) })} className="ip tabular-nums" data-testid="rule-add-max" /></Field>
          <Field className="col-span-3" label="Supplier"><input value={draftRule.supplier} onChange={(e) => setDraftRule({ ...draftRule, supplier: e.target.value })} className="ip" data-testid="rule-add-supplier" /></Field>
          <button type="button" onClick={submitRule} className="col-span-2 px-2 py-1.5 rounded-md text-xs font-bold text-white inline-flex items-center justify-center gap-1" style={{ background: 'var(--color-brand-blue, #1d4ed8)' }} data-testid="rule-add-submit"><Plus size={11} /> Save rule</button>
        </div>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] uppercase tracking-wider opacity-70"><th className="px-3 py-2">SKU</th><th className="px-3 py-2">Loc</th><th className="px-3 py-2 text-right">Min</th><th className="px-3 py-2 text-right">Max</th><th className="px-3 py-2">Supplier</th><th className="px-3 py-2"></th></tr></thead>
          <tbody>
            {rules.length === 0 ? (
              <tr><td colSpan="6" className="px-3 py-6 text-center opacity-60 text-xs">No reorder rules yet — add one above.</td></tr>
            ) : rules.map((r) => (
              <tr key={r.id} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`rule-row-${r.part_sku}-${r.location}`}>
                <td className="px-3 py-2 font-bold tabular-nums">{r.part_sku}</td>
                <td className="px-3 py-2 text-xs opacity-80">{r.location}{r.engineer_id ? ` · ${r.engineer_id.slice(0, 6)}` : ''}</td>
                <td className="px-3 py-2 text-right tabular-nums">{r.min_qty}</td>
                <td className="px-3 py-2 text-right tabular-nums">{r.max_qty}</td>
                <td className="px-3 py-2 text-xs opacity-80">{r.supplier || '—'}</td>
                <td className="px-3 py-2 text-right">
                  <button type="button" onClick={() => removeRule(r.id)} className="opacity-60 hover:opacity-100" aria-label="Remove rule" data-testid={`rule-remove-${r.id}`}><Trash2 size={12} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <style>{`.ip{width:100%;padding:6px 8px;border:1px solid var(--theme-border);border-radius:6px;font-size:13px;background:transparent}`}</style>
    </div>
  );
}

// ── Purchase orders ──────────────────────────────────────────────
function POTab() {
  const [pos, setPOs] = useState([]);
  const [statusFilter, setStatusFilter] = useState('');
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState({ supplier: '', supplier_email: '', notes: '', lines: [{ part_sku: '', qty: 1, unit_cost: 0 }] });
  const [supplierForLowStock, setSupplierForLowStock] = useState('ALL');

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/svc/inventory/purchase-orders`, { ...auth(), params: { status: statusFilter || undefined } });
      setPOs(r.data.purchase_orders || []);
    } catch (e) { notify.error('Could not load POs', e?.response?.data?.detail || e.message); }
  }, [statusFilter]);
  useEffect(() => { load(); }, [load]);

  const fromLowStock = async () => {
    try {
      const r = await axios.post(
        `${API}/svc/inventory/purchase-orders/from-low-stock`,
        { supplier: supplierForLowStock || 'ALL' },
        auth(),
      );
      notify.success(`Created ${r.data.reference}`, `${(r.data.lines || []).length} line(s) · ${gbp(r.data.total)}`);
      load();
    } catch (e) {
      notify.error('Could not generate PO', e?.response?.data?.detail || e.message);
    }
  };

  const create = async () => {
    if (!draft.supplier.trim()) { notify.error('Supplier required'); return; }
    const lines = draft.lines.filter((l) => l.part_sku.trim() && Number(l.qty) > 0);
    if (lines.length === 0) { notify.error('Add at least one line'); return; }
    try {
      await axios.post(`${API}/svc/inventory/purchase-orders`, { ...draft, lines }, auth());
      notify.success('PO created');
      setCreating(false);
      setDraft({ supplier: '', supplier_email: '', notes: '', lines: [{ part_sku: '', qty: 1, unit_cost: 0 }] });
      load();
    } catch (e) {
      notify.error('Create failed', e?.response?.data?.detail || e.message);
    }
  };

  const submit = async (id) => {
    try { await axios.post(`${API}/svc/inventory/purchase-orders/${id}/submit`, {}, auth()); notify.success('Submitted'); load(); }
    catch (e) { notify.error('Submit failed', e?.response?.data?.detail || e.message); }
  };
  const receive = async (id) => {
    try { await axios.post(`${API}/svc/inventory/purchase-orders/${id}/receive`, { full: true }, auth()); notify.success('Received'); load(); }
    catch (e) { notify.error('Receive failed', e?.response?.data?.detail || e.message); }
  };
  const cancel = async (id) => {
    if (!window.confirm('Cancel this purchase order?')) return;
    try { await axios.post(`${API}/svc/inventory/purchase-orders/${id}/cancel`, {}, auth()); notify.success('Cancelled'); load(); }
    catch (e) { notify.error('Cancel failed', e?.response?.data?.detail || e.message); }
  };

  return (
    <div className="space-y-4" data-testid="parts-po-tab">
      <div className="flex flex-wrap items-center gap-2">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="px-2 py-1.5 rounded-md border text-sm bg-transparent" style={{ borderColor: 'var(--theme-border)' }} data-testid="po-status-filter">
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="submitted">Submitted</option>
          <option value="received">Received</option>
          <option value="cancelled">Cancelled</option>
        </select>
        <button type="button" onClick={() => setCreating(true)} className="px-3 py-1.5 rounded-md text-xs font-bold text-white inline-flex items-center gap-1" style={{ background: 'var(--color-brand-blue, #1d4ed8)' }} data-testid="po-create-open"><Plus size={12} /> Create PO</button>
        <div className="ml-auto flex items-center gap-1.5">
          <input value={supplierForLowStock} onChange={(e) => setSupplierForLowStock(e.target.value)} placeholder="Supplier or ALL" className="px-2 py-1.5 rounded-md border text-xs bg-transparent" style={{ borderColor: 'var(--theme-border)' }} data-testid="po-low-stock-supplier" />
          <button type="button" onClick={fromLowStock} className="px-3 py-1.5 rounded-md border text-xs font-bold inline-flex items-center gap-1" style={{ borderColor: 'var(--theme-border)' }} data-testid="po-from-low-stock"><AlertTriangle size={12} /> Generate from low-stock</button>
        </div>
      </div>

      <div className="rounded-md border overflow-hidden" style={{ borderColor: 'var(--theme-border)' }}>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] uppercase tracking-wider opacity-70"><th className="px-3 py-2">Ref</th><th className="px-3 py-2">Supplier</th><th className="px-3 py-2">Status</th><th className="px-3 py-2 text-right">Lines</th><th className="px-3 py-2 text-right">Total</th><th className="px-3 py-2"></th></tr></thead>
          <tbody>
            {pos.length === 0 ? (
              <tr><td colSpan="6" className="px-3 py-10 text-center opacity-60 text-xs">No purchase orders yet.</td></tr>
            ) : pos.map((p) => {
              const colour = PO_STATUS_COLOUR[p.status] || '#6b7280';
              return (
                <tr key={p.id} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`po-row-${p.reference}`}>
                  <td className="px-3 py-2 font-bold tabular-nums">{p.reference}</td>
                  <td className="px-3 py-2 truncate max-w-[14rem]">{p.supplier}</td>
                  <td className="px-3 py-2"><span className="px-1.5 py-0.5 rounded text-[10px] font-extrabold uppercase tracking-wider" style={{ background: `${colour}22`, color: colour }}>{p.status}</span></td>
                  <td className="px-3 py-2 text-right tabular-nums">{(p.lines || []).length}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{gbp(p.total)}</td>
                  <td className="px-3 py-2 text-right space-x-1">
                    {p.status === 'draft' ? <button type="button" onClick={() => submit(p.id)} className="px-2 py-0.5 rounded text-[11px] font-bold border inline-flex items-center gap-1" style={{ borderColor: 'var(--theme-border)' }} data-testid={`po-submit-${p.reference}`}><Send size={10} /> Submit</button> : null}
                    {(p.status === 'submitted' || p.status === 'draft') ? <button type="button" onClick={() => receive(p.id)} className="px-2 py-0.5 rounded text-[11px] font-bold text-white inline-flex items-center gap-1" style={{ background: '#10b981' }} data-testid={`po-receive-${p.reference}`}><Truck size={10} /> Receive</button> : null}
                    {p.status !== 'received' && p.status !== 'cancelled' ? <button type="button" onClick={() => cancel(p.id)} className="px-2 py-0.5 rounded text-[11px] font-bold border inline-flex items-center gap-1" style={{ borderColor: 'var(--theme-border)', color: '#b91c1c' }} data-testid={`po-cancel-${p.reference}`}><X size={10} /> Cancel</button> : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {creating ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.6)' }} data-testid="po-create-modal">
          <div className="w-full max-w-2xl rounded-xl border shadow-xl" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
            <div className="px-4 py-3 border-b flex items-center justify-between" style={{ borderColor: 'var(--theme-border)' }}>
              <p className="font-bold inline-flex items-center gap-1.5"><FileText size={14} /> New purchase order</p>
              <button type="button" aria-label="Close" onClick={() => setCreating(false)}><X size={14} /></button>
            </div>
            <div className="p-4 space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Supplier" required><input value={draft.supplier} onChange={(e) => setDraft({ ...draft, supplier: e.target.value })} className="ip" data-testid="po-supplier" /></Field>
                <Field label="Supplier email"><input value={draft.supplier_email} onChange={(e) => setDraft({ ...draft, supplier_email: e.target.value })} className="ip" data-testid="po-supplier-email" /></Field>
              </div>
              <div className="space-y-1.5" data-testid="po-lines">
                <p className="text-[10px] font-bold uppercase tracking-wider opacity-60">Lines</p>
                {draft.lines.map((line, i) => (
                  <div key={i} className="grid grid-cols-12 gap-2 items-center">
                    <input value={line.part_sku} onChange={(e) => { const ls = [...draft.lines]; ls[i].part_sku = e.target.value.toUpperCase(); setDraft({ ...draft, lines: ls }); }} placeholder="SKU" className="col-span-3 ip" data-testid={`po-line-sku-${i}`} />
                    <input type="number" value={line.qty} onChange={(e) => { const ls = [...draft.lines]; ls[i].qty = Number(e.target.value); setDraft({ ...draft, lines: ls }); }} placeholder="Qty" className="col-span-2 ip tabular-nums" data-testid={`po-line-qty-${i}`} />
                    <input type="number" value={line.unit_cost} onChange={(e) => { const ls = [...draft.lines]; ls[i].unit_cost = Number(e.target.value); setDraft({ ...draft, lines: ls }); }} placeholder={`Unit ${getCachedLocalization().currency_symbol}`} className="col-span-2 ip tabular-nums" data-testid={`po-line-cost-${i}`} />
                    <input value={line.description || ''} onChange={(e) => { const ls = [...draft.lines]; ls[i].description = e.target.value; setDraft({ ...draft, lines: ls }); }} placeholder="Description (optional)" className="col-span-4 ip" data-testid={`po-line-desc-${i}`} />
                    <button type="button" aria-label="Remove line" onClick={() => { const ls = [...draft.lines]; ls.splice(i, 1); setDraft({ ...draft, lines: ls.length ? ls : [{ part_sku: '', qty: 1, unit_cost: 0 }] }); }} className="col-span-1 opacity-60 hover:opacity-100 inline-flex justify-center" data-testid={`po-line-remove-${i}`}><Trash2 size={11} /></button>
                  </div>
                ))}
                <button type="button" onClick={() => setDraft({ ...draft, lines: [...draft.lines, { part_sku: '', qty: 1, unit_cost: 0 }] })} className="text-xs font-bold opacity-70 hover:opacity-100 inline-flex items-center gap-1" data-testid="po-line-add"><Plus size={11} /> Add line</button>
              </div>
              <Field label="Notes"><textarea value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} rows={2} className="ip" data-testid="po-notes" /></Field>
            </div>
            <div className="px-4 py-3 border-t flex justify-end gap-2" style={{ borderColor: 'var(--theme-border)' }}>
              <button type="button" onClick={() => setCreating(false)} className="px-3 py-1.5 rounded-md border text-xs font-bold" style={{ borderColor: 'var(--theme-border)' }}>Cancel</button>
              <button type="button" onClick={create} className="px-3 py-1.5 rounded-md text-xs font-bold text-white inline-flex items-center gap-1" style={{ background: 'var(--color-brand-blue, #1d4ed8)' }} data-testid="po-create-submit"><CheckCircle size={11} /> Create draft PO</button>
            </div>
          </div>
        </div>
      ) : null}
      <style>{`.ip{width:100%;padding:6px 8px;border:1px solid var(--theme-border);border-radius:6px;font-size:13px;background:transparent}`}</style>
    </div>
  );
}

function Field({ label, required, className = '', children }) {
  return (
    <label className={`block ${className}`}>
      <span className="text-[10px] font-bold uppercase tracking-wider opacity-60">{label}{required ? <span style={{ color: '#ef4444' }}> *</span> : null}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}
