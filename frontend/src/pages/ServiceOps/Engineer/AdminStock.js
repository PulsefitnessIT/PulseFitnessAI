/**
 * AdminStock — Iter 220ea·22 · Stock Phase 4 (Office/Admin stock overview).
 *
 * Responsive office surface (mobile + desktop) for owners / admins /
 * managers. Built on the existing stock backend (/svc/admin/stock/*) —
 * no duplicate data. Tabs:
 *   • Overview   — warehouse + every engineer's van (value / low / zero)
 *   • Transfer   — move stock warehouse↔van / van↔van (immediate + audit)
 *   • Stock-take — count a location → variance vs expected → post
 *   • Cross-org  — (master / pulse admins) value + low/zero per org
 *
 * Reached from the Engineer App (Account Settings → Stock → Stock
 * management) and the desktop Service Desk.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Boxes, Truck, ClipboardCheck, Globe2, Loader2, RefreshCw,
  Warehouse, AlertTriangle, Search, ArrowRight, Users,
  Building2, ChevronRight, PackageCheck, Trash2, FileText, Download, ShoppingCart,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { useLocalization, formatMoneySync } from '@/utils/localization';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const gbp = (n) => formatMoneySync(n);
const num = (n) => (Number(n) || 0).toLocaleString('en-GB');
const newIdem = () => (crypto?.randomUUID?.() || `idem-${Date.now()}-${Math.random().toString(36).slice(2)}`);

const Stat = ({ label, value, icon: Icon, tid }) => (
  <div className="rounded-2xl border border-slate-100 bg-white p-3.5 shadow-sm" data-testid={tid}>
    <div className="flex items-center gap-1.5 text-slate-500">
      {Icon && <Icon className="w-3.5 h-3.5" />}
      <span className="text-[10px] font-bold uppercase tracking-wider">{label}</span>
    </div>
    <p className="mt-1 text-xl font-extrabold text-slate-900 tabular-nums">{value}</p>
  </div>
);

export default function AdminStock() {
  const navigate = useNavigate();
  useLocalization();  // warm currency cache + re-render subtree on load
  const [tab, setTab] = useState('overview');
  const [overview, setOverview] = useState(null);
  const [locations, setLocations] = useState({ engineers: [] });
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadCore = useCallback(async () => {
    setLoading(true);
    try {
      const [ov, loc] = await Promise.all([
        axios.get(`${API}/svc/admin/stock/overview`, auth()),
        axios.get(`${API}/svc/admin/stock/locations`, auth()),
      ]);
      setOverview(ov.data);
      setLocations(loc.data);
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not load stock overview');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadCore(); }, [loadCore]);

  const canCross = overview?.can_cross_org;
  const tabs = [
    { k: 'overview', label: 'Overview', icon: Boxes },
    { k: 'transfer', label: 'Transfer', icon: Truck },
    { k: 'stocktake', label: 'Stock-take', icon: ClipboardCheck },
    { k: 'reports', label: 'Reports', icon: FileText },
    ...(canCross ? [{ k: 'crossorg', label: 'Cross-org', icon: Globe2 }] : []),
  ];

  const openDetail = (loc) => { setDetail(loc); setTab('detail'); };

  return (
    <div className="min-h-screen bg-slate-50 pb-28" data-testid="admin-stock-page">
      <header className="sticky top-0 z-20 bg-white border-b border-slate-200">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center gap-3">
          <button onClick={() => navigate(-1)} data-testid="admin-stock-back"
                  className="w-9 h-9 rounded-xl bg-slate-100 flex items-center justify-center text-slate-600">
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div className="flex-1">
            <h1 className="text-lg font-extrabold text-slate-900 leading-none">Stock management</h1>
            <p className="text-xs text-slate-500 mt-0.5">Office &amp; admin overview</p>
          </div>
          <button onClick={loadCore} data-testid="admin-stock-refresh"
                  className="w-9 h-9 rounded-xl bg-slate-100 flex items-center justify-center text-slate-600">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
        <div className="max-w-5xl mx-auto px-4 flex gap-1 overflow-x-auto">
          {tabs.map((t) => (
            <button key={t.k} onClick={() => setTab(t.k)} data-testid={`admin-stock-tab-${t.k}`}
                    className={`shrink-0 flex items-center gap-1.5 px-3.5 py-2.5 text-sm font-bold border-b-2 transition-colors ${
                      (tab === t.k || (tab === 'detail' && t.k === 'overview')) ? 'border-cyan-600 text-cyan-700' : 'border-transparent text-slate-500'}`}>
              <t.icon className="w-4 h-4" /> {t.label}
            </button>
          ))}
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-4">
        {loading && !overview ? (
          <div className="py-24 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-slate-300" /></div>
        ) : (
          <>
            {tab === 'overview' && <OverviewTab overview={overview} onDrill={openDetail} />}
            {tab === 'detail' && <DetailTab detail={detail} showCost={overview?.show_cost} onBack={() => setTab('overview')} />}
            {tab === 'transfer' && <TransferTab locations={locations} onDone={loadCore} />}
            {tab === 'stocktake' && <StockTakeTab locations={locations} showCost={overview?.show_cost} onDone={loadCore} />}
            {tab === 'reports' && <ReportsTab locations={locations} showCost={overview?.show_cost} />}
            {tab === 'crossorg' && canCross && <CrossOrgTab />}
          </>
        )}
      </main>
    </div>
  );
}

/* ───────────────────────────── Overview ─────────────────────────── */

const OverviewTab = ({ overview, onDrill }) => {
  if (!overview) return null;
  const { warehouse, engineers = [], totals = {}, show_cost } = overview;
  return (
    <div className="space-y-5" data-testid="admin-stock-overview">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
        <Stat label="Stock value" value={gbp(totals.value_sell)} tid="overview-stat-value" />
        <Stat label="Catalogue" value={num(totals.catalogue_parts)} tid="overview-stat-catalogue" />
        <Stat label="Low lines" value={num(totals.low)} icon={AlertTriangle} tid="overview-stat-low" />
        <Stat label="Out of stock" value={num(totals.zero)} icon={AlertTriangle} tid="overview-stat-zero" />
      </div>

      <button onClick={() => onDrill({ location: 'warehouse', name: 'Warehouse' })}
              data-testid="overview-warehouse-card"
              className="w-full text-left rounded-2xl border border-slate-200 bg-white p-4 flex items-center gap-3 hover:border-cyan-300 transition-colors">
        <div className="w-11 h-11 rounded-xl bg-teal-50 text-teal-600 flex items-center justify-center"><Warehouse className="w-5 h-5" /></div>
        <div className="flex-1 min-w-0">
          <p className="font-bold text-slate-900">Warehouse</p>
          <p className="text-xs text-slate-500">{num(warehouse.lines)} lines · {num(warehouse.units)} units{warehouse.low ? ` · ${warehouse.low} low` : ''}{warehouse.zero ? ` · ${warehouse.zero} out` : ''}</p>
        </div>
        <div className="text-right">
          <p className="font-extrabold text-slate-900 tabular-nums">{gbp(warehouse.value_sell)}</p>
          {show_cost && <p className="text-[11px] text-slate-400">cost {gbp(warehouse.value_cost)}</p>}
        </div>
        <ChevronRight className="w-4 h-4 text-slate-300" />
      </button>

      <div>
        <div className="flex items-center gap-2 mb-2 text-slate-500">
          <Users className="w-4 h-4" />
          <h2 className="text-[11px] font-bold uppercase tracking-wider">Engineer vans ({engineers.length})</h2>
        </div>
        {engineers.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-200 p-8 text-center text-sm text-slate-400" data-testid="overview-no-engineers">
            No van stock allocated yet.
          </div>
        ) : (
          <div className="space-y-2">
            {engineers.map((e) => (
              <button key={e.engineer_id} onClick={() => onDrill({ location: 'van', engineer_id: e.engineer_id, name: e.name })}
                      data-testid={`overview-engineer-${e.engineer_id}`}
                      className="w-full text-left rounded-2xl border border-slate-200 bg-white p-3.5 flex items-center gap-3 hover:border-cyan-300 transition-colors">
                <div className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center"><Truck className="w-5 h-5" /></div>
                <div className="flex-1 min-w-0">
                  <p className="font-bold text-slate-900 truncate">{e.name}</p>
                  <p className="text-xs text-slate-500">{num(e.lines)} lines · {num(e.units)} units
                    {e.low ? <span className="text-amber-600 font-semibold"> · {e.low} low</span> : null}
                    {e.zero ? <span className="text-rose-600 font-semibold"> · {e.zero} out</span> : null}
                  </p>
                </div>
                <div className="text-right">
                  <p className="font-extrabold text-slate-900 tabular-nums">{gbp(e.value_sell)}</p>
                  {show_cost && <p className="text-[11px] text-slate-400">cost {gbp(e.value_cost)}</p>}
                </div>
                <ChevronRight className="w-4 h-4 text-slate-300" />
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

/* ─────────────────────────── Detail (by-location) ───────────────── */

const DetailTab = ({ detail, showCost, onBack }) => {
  const [items, setItems] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!detail) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({ location: detail.location, engineer_id: detail.engineer_id || '', search });
      const r = await axios.get(`${API}/svc/admin/stock/by-location?${params}`, auth());
      setItems(r.data.items || []);
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not load stock');
    } finally { setLoading(false); }
  }, [detail, search]);

  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);

  return (
    <div className="space-y-3" data-testid="admin-stock-detail">
      <button onClick={onBack} className="text-sm font-bold text-cyan-700 flex items-center gap-1" data-testid="detail-back">
        <ArrowLeft className="w-4 h-4" /> Overview
      </button>
      <div className="flex items-center gap-2">
        <div className="w-9 h-9 rounded-xl bg-slate-900 text-white flex items-center justify-center">
          {detail?.location === 'warehouse' ? <Warehouse className="w-4 h-4" /> : <Truck className="w-4 h-4" />}
        </div>
        <h2 className="font-extrabold text-slate-900">{detail?.name || (detail?.location === 'warehouse' ? 'Warehouse' : 'Van')}</h2>
      </div>
      <div className="relative">
        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search parts…"
               data-testid="detail-search"
               className="w-full h-11 pl-9 pr-3 rounded-xl border border-slate-200 text-sm bg-white" />
      </div>
      {loading ? (
        <div className="py-16 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-slate-300" /></div>
      ) : items.length === 0 ? (
        <p className="py-12 text-center text-sm text-slate-400" data-testid="detail-empty">No parts at this location.</p>
      ) : (
        <div className="rounded-2xl border border-slate-200 bg-white divide-y divide-slate-100 overflow-hidden">
          {items.slice(0, 150).map((it) => (
            <div key={it.part_sku} className="p-3 flex items-center gap-3" data-testid={`detail-row-${it.part_sku}`}>
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-slate-900 text-sm truncate">{it.name}</p>
                <p className="text-[11px] text-slate-400 font-mono">{it.part_sku}{it.manufacturer ? ` · ${it.manufacturer}` : ''}</p>
              </div>
              <div className="text-right">
                <p className={`font-bold tabular-nums ${it.zero ? 'text-rose-600' : it.low ? 'text-amber-600' : 'text-slate-900'}`}>{num(it.qty)}</p>
                <p className="text-[10px] text-slate-400">{it.min_qty ? `min ${it.min_qty}` : ''}</p>
              </div>
              <div className="text-right w-20">
                <p className="text-sm font-bold text-slate-700 tabular-nums">{gbp(it.value_sell)}</p>
                {showCost && it.value_cost != null && <p className="text-[10px] text-slate-400">cost {gbp(it.value_cost)}</p>}
              </div>
            </div>
          ))}
          {items.length > 150 && (
            <p className="px-3 py-2.5 text-center text-xs text-slate-400" data-testid="detail-more-hint">
              Showing first 150 of {num(items.length)} — search to narrow.
            </p>
          )}
        </div>
      )}
    </div>
  );
};

/* ───────────────────── Location picker (shared) ─────────────────── */

const LocationPicker = ({ label, value, onChange, engineers, tid }) => (
  <div>
    <label className="text-[11px] font-bold uppercase tracking-wider text-slate-500">{label}</label>
    <select value={value} onChange={(e) => onChange(e.target.value)} data-testid={tid}
            className="w-full mt-1 h-11 px-3 rounded-xl border border-slate-200 text-sm bg-white">
      <option value="warehouse">Warehouse</option>
      {engineers.map((e) => (
        <option key={e.engineer_id} value={`van:${e.engineer_id}`}>{e.name}</option>
      ))}
    </select>
  </div>
);

const parseLoc = (v) => (v.startsWith('van:')
  ? { type: 'van', engineer_id: v.slice(4) }
  : { type: 'warehouse', engineer_id: '' });

/* ───────────────────────────── Transfer ─────────────────────────── */

const TransferTab = ({ locations, onDone }) => {
  const engineers = locations.engineers || [];
  const [sku, setSku] = useState('');
  const [results, setResults] = useState([]);
  const [picked, setPicked] = useState(null);
  const [qty, setQty] = useState(1);
  const [cart, setCart] = useState([]);          // [{sku, name, qty}]
  const [from, setFrom] = useState('warehouse');
  const [to, setTo] = useState(engineers[0] ? `van:${engineers[0].engineer_id}` : 'warehouse');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [avail, setAvail] = useState({});        // {sku: qty at `from`}

  const searchParts = useCallback(async (q) => {
    if (!q || q.length < 2) { setResults([]); return; }
    try {
      const r = await axios.get(`${API}/svc/parts/catalogue?search=${encodeURIComponent(q)}&page_size=8`, auth());
      setResults(r.data.items || []);
    } catch { setResults([]); }
  }, []);

  useEffect(() => { const t = setTimeout(() => searchParts(sku), 250); return () => clearTimeout(t); }, [sku, searchParts]);

  // Iter 220ea·22b — show how many of each line are in stock at the
  // source so the user never over-transfers. Re-fetches when the source
  // location, cart or the picked part changes.
  useEffect(() => {
    const p = parseLoc(from);
    const skus = [...new Set([...cart.map((x) => x.sku), ...(picked ? [picked.sku] : [])])];
    if (skus.length === 0) { setAvail({}); return undefined; }
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.post(`${API}/svc/admin/stock/availability`, {
          location: p.type, engineer_id: p.engineer_id, part_skus: skus,
        }, auth());
        if (!cancelled) setAvail(r.data.availability || {});
      } catch { /* non-blocking */ }
    })();
    return () => { cancelled = true; };
  }, [from, cart, picked]);

  const addToCart = () => {
    if (!picked) { notify.error('Pick a part first'); return; }
    const q = Math.max(1, Number(qty) || 1);
    setCart((c) => {
      const i = c.findIndex((x) => x.sku === picked.sku);
      if (i >= 0) { const n = [...c]; n[i] = { ...n[i], qty: n[i].qty + q }; return n; }
      return [...c, { sku: picked.sku, name: picked.name, qty: q }];
    });
    setPicked(null); setSku(''); setQty(1); setResults([]);
  };

  const removeLine = (s) => setCart((c) => c.filter((x) => x.sku !== s));
  const totalUnits = cart.reduce((s, x) => s + x.qty, 0);
  const locName = (v) => (v === 'warehouse' ? 'Warehouse' : (engineers.find((e) => `van:${e.engineer_id}` === v)?.name || 'Van'));
  const fromName = locName(from);
  // A line is short when we know the source qty and it's below the line qty.
  const lineShort = (x) => avail[x.sku] !== undefined && x.qty > avail[x.sku];
  const hasShortfall = cart.some(lineShort);

  const submit = async () => {
    if (cart.length === 0) { notify.error('Add at least one part'); return; }
    if (from === to) { notify.error('Source and destination are the same'); return; }
    setBusy(true);
    try {
      const r = await axios.post(`${API}/svc/admin/stock/transfer-batch`, {
        from: parseLoc(from), to: parseLoc(to), reason,
        items: cart.map((x) => ({ part_sku: x.sku, qty: x.qty })),
      }, { headers: { ...auth().headers, 'Idempotency-Key': newIdem() } });
      if (r.data.already_done) notify.success('Already transferred');
      else notify.success(`Moved ${r.data.transferred} part${r.data.transferred === 1 ? '' : 's'} (${totalUnits} units)`);
      setCart([]); setReason('');
      onDone?.();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (detail && typeof detail === 'object' && Array.isArray(detail.failures)) {
        notify.error(`${detail.message}: ${detail.failures.map((f) => `${f.part_sku} (${f.reason})`).join(', ')}`);
      } else {
        notify.error(detail || 'Transfer failed');
      }
    } finally { setBusy(false); }
  };

  return (
    <div className="max-w-lg space-y-4" data-testid="admin-stock-transfer">
      <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-4">
        <div className="grid grid-cols-[1fr_auto_1fr] items-end gap-2">
          <LocationPicker label="From" value={from} onChange={setFrom} engineers={engineers} tid="transfer-from" />
          <ArrowRight className="w-5 h-5 text-slate-400 mb-3" />
          <LocationPicker label="To" value={to} onChange={setTo} engineers={engineers} tid="transfer-to" />
        </div>

        {/* Add a part line */}
        <div className="border-t border-slate-100 pt-3 space-y-2.5">
          <label className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Add parts</label>
          {picked ? (
            <div className="rounded-xl border border-cyan-200 bg-cyan-50 p-2.5 space-y-1.5" data-testid="transfer-picked">
              <div className="flex items-center gap-2">
                <PackageCheck className="w-4 h-4 text-cyan-600 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-bold text-slate-900 truncate">{picked.name}</p>
                  <p className="text-[11px] font-mono text-slate-500">{picked.sku}</p>
                </div>
                <input type="number" min="1" value={qty} onChange={(e) => setQty(e.target.value)}
                       data-testid="transfer-qty"
                       className="w-16 h-9 px-2 rounded-lg border border-slate-200 text-sm text-right tabular-nums" />
                <button onClick={addToCart} data-testid="transfer-add-line"
                        className="px-3 h-9 rounded-lg bg-cyan-600 text-white text-sm font-bold">Add</button>
                <button onClick={() => { setPicked(null); setSku(''); }} className="text-xs font-bold text-slate-400">✕</button>
              </div>
              <p className={`text-[11px] font-semibold ${avail[picked.sku] === undefined ? 'text-slate-400' : (Number(qty) > avail[picked.sku] ? 'text-rose-600' : 'text-emerald-600')}`}
                 data-testid="transfer-picked-avail">
                {avail[picked.sku] === undefined ? `Checking stock in ${fromName}…` : `${avail[picked.sku]} in stock at ${fromName}`}
              </p>
            </div>
          ) : (
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input value={sku} onChange={(e) => setSku(e.target.value)} placeholder="Search SKU or name…"
                     data-testid="transfer-part-search"
                     className="w-full h-11 pl-9 pr-3 rounded-xl border border-slate-200 text-sm bg-white" />
              {results.length > 0 && (
                <div className="absolute z-10 mt-1 w-full rounded-xl border border-slate-200 bg-white shadow-lg max-h-60 overflow-auto">
                  {results.map((p) => (
                    <button key={p.id || p.sku} onClick={() => { setPicked(p); setResults([]); }}
                            data-testid={`transfer-result-${p.sku}`}
                            className="w-full text-left px-3 py-2 hover:bg-slate-50 border-b border-slate-50 last:border-0">
                      <p className="text-sm font-semibold text-slate-900 truncate">{p.name}</p>
                      <p className="text-[11px] font-mono text-slate-400">{p.sku}</p>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Cart */}
        {cart.length > 0 && (
          <div className="rounded-xl border border-slate-200 divide-y divide-slate-100 overflow-hidden" data-testid="transfer-cart">
            {cart.map((x) => {
              const short = lineShort(x);
              return (
                <div key={x.sku} className={`flex items-center gap-2 px-3 py-2 ${short ? 'bg-rose-50' : ''}`} data-testid={`transfer-cart-${x.sku}`}>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-slate-900 truncate">{x.name}</p>
                    <p className="text-[11px] font-mono text-slate-400">{x.sku}</p>
                    {avail[x.sku] !== undefined && (
                      <p className={`text-[11px] font-semibold ${short ? 'text-rose-600' : 'text-slate-400'}`} data-testid={`transfer-cart-avail-${x.sku}`}>
                        {short ? `Only ${avail[x.sku]} in ${fromName}` : `${avail[x.sku]} in ${fromName}`}
                      </p>
                    )}
                  </div>
                  <span className={`text-sm font-bold tabular-nums ${short ? 'text-rose-600' : 'text-slate-700'}`}>× {x.qty}</span>
                  <button onClick={() => removeLine(x.sku)} data-testid={`transfer-remove-${x.sku}`}
                          className="w-7 h-7 rounded-lg bg-slate-100 text-slate-500 flex items-center justify-center">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            })}
          </div>
        )}

        <div>
          <label className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Reason (optional)</label>
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. restock van"
                 data-testid="transfer-reason"
                 className="w-full mt-1 h-11 px-3 rounded-xl border border-slate-200 text-sm bg-white" />
        </div>

        <p className="text-xs text-slate-500">
          Move <span className="font-bold text-slate-700">{cart.length}</span> part{cart.length === 1 ? '' : 's'} ({totalUnits} units) from <span className="font-bold text-slate-700">{locName(from)}</span> → <span className="font-bold text-slate-700">{locName(to)}</span>
        </p>
        {hasShortfall && (
          <p className="text-xs font-semibold text-rose-600" data-testid="transfer-shortfall-warning">
            Some lines exceed what&apos;s in stock at {fromName}. Reduce the quantity or remove them.
          </p>
        )}
        <button onClick={submit} disabled={busy || cart.length === 0 || hasShortfall} data-testid="transfer-submit"
                className="w-full h-12 rounded-xl bg-cyan-600 text-white font-bold flex items-center justify-center gap-2 disabled:opacity-50">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Truck className="w-4 h-4" />} Transfer {cart.length || ''} {cart.length === 1 ? 'part' : 'parts'}
        </button>
      </div>
    </div>
  );
};

/* ───────────────────────────── Stock-take ───────────────────────── */

const StockTakeTab = ({ locations, onDone }) => {
  const engineers = locations.engineers || [];
  const [loc, setLoc] = useState('warehouse');
  const [items, setItems] = useState([]);
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = parseLoc(loc);
      const params = new URLSearchParams({ location: p.type, engineer_id: p.engineer_id || '' });
      const r = await axios.get(`${API}/svc/admin/stock/by-location?${params}`, auth());
      setItems(r.data.items || []);
      setCounts({});
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not load location');
    } finally { setLoading(false); }
  }, [loc]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    if (!q) return items;
    return items.filter((i) => `${i.part_sku} ${i.name}`.toLowerCase().includes(q));
  }, [items, search]);

  const dirty = useMemo(() => Object.entries(counts).filter(([sku, v]) => {
    const it = items.find((x) => x.part_sku === sku);
    return it && v !== '' && Number(v) !== it.qty;
  }), [counts, items]);

  const post = async () => {
    if (dirty.length === 0) { notify.error('No variances to post'); return; }
    setBusy(true);
    try {
      const p = parseLoc(loc);
      const payload = {
        location: p.type, engineer_id: p.engineer_id || '',
        counts: dirty.map(([sku, v]) => ({ part_sku: sku, counted_qty: Number(v) })),
        reason: 'Stock-take',
      };
      const r = await axios.post(`${API}/svc/admin/stock/stock-take`, payload,
        { headers: { ...auth().headers, 'Idempotency-Key': newIdem() } });
      notify.success(`Posted ${r.data.adjusted} adjustment${r.data.adjusted === 1 ? '' : 's'} (variance ${r.data.variance_units >= 0 ? '+' : ''}${r.data.variance_units})`);
      onDone?.();
      await load();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Stock-take failed');
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-3" data-testid="admin-stock-stocktake">
      <LocationPicker label="Location to count" value={loc} onChange={setLoc} engineers={engineers} tid="stocktake-location" />
      <div className="relative">
        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search parts…"
               data-testid="stocktake-search"
               className="w-full h-11 pl-9 pr-3 rounded-xl border border-slate-200 text-sm bg-white" />
      </div>

      {loading ? (
        <div className="py-16 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-slate-300" /></div>
      ) : filtered.length === 0 ? (
        <p className="py-12 text-center text-sm text-slate-400" data-testid="stocktake-empty">No parts at this location.</p>
      ) : (
        <div className="rounded-2xl border border-slate-200 bg-white divide-y divide-slate-100 overflow-hidden">
          <div className="grid grid-cols-[1fr_64px_72px_64px] gap-2 px-3 py-2 bg-slate-50 text-[10px] font-bold uppercase tracking-wider text-slate-400">
            <span>Part</span><span className="text-right">System</span><span className="text-right">Counted</span><span className="text-right">Var</span>
          </div>
          {filtered.slice(0, 150).map((it) => {
            const v = counts[it.part_sku] ?? '';
            const variance = v === '' ? null : Number(v) - it.qty;
            return (
              <div key={it.part_sku} className="grid grid-cols-[1fr_64px_72px_64px] gap-2 items-center px-3 py-2" data-testid={`stocktake-row-${it.part_sku}`}>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-slate-900 truncate">{it.name}</p>
                  <p className="text-[10px] font-mono text-slate-400">{it.part_sku}</p>
                </div>
                <p className="text-right tabular-nums text-slate-600 text-sm">{num(it.qty)}</p>
                <input type="number" value={v} placeholder={String(it.qty)}
                       onChange={(e) => setCounts((c) => ({ ...c, [it.part_sku]: e.target.value }))}
                       data-testid={`stocktake-count-${it.part_sku}`}
                       className="h-9 w-full px-2 rounded-lg border border-slate-200 text-sm text-right tabular-nums" />
                <p className={`text-right tabular-nums text-sm font-bold ${variance == null ? 'text-slate-300' : variance === 0 ? 'text-slate-400' : variance > 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                  {variance == null ? '—' : `${variance > 0 ? '+' : ''}${variance}`}
                </p>
              </div>
            );
          })}
          {filtered.length > 150 && (
            <p className="px-3 py-2.5 text-center text-xs text-slate-400" data-testid="stocktake-more-hint">
              Showing first 150 of {num(filtered.length)} — search to count a specific part.
            </p>
          )}
        </div>
      )}

      <div className="sticky bottom-4 z-[210]">
        <button onClick={post} disabled={busy || dirty.length === 0} data-testid="stocktake-post"
                className="w-full h-12 rounded-xl bg-cyan-600 text-white font-bold flex items-center justify-center gap-2 shadow-lg disabled:opacity-50">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <ClipboardCheck className="w-4 h-4" />}
          Post {dirty.length} adjustment{dirty.length === 1 ? '' : 's'}
        </button>
      </div>
    </div>
  );
};

/* ───────────────────────────── Reports ──────────────────────────── */

const downloadFile = async (path, filename) => {
  try {
    const r = await axios.get(`${API}${path}`, { ...auth(), responseType: 'blob' });
    const url = URL.createObjectURL(r.data);
    const a = document.createElement('a');
    a.href = url; a.download = filename; document.body.appendChild(a); a.click();
    a.remove(); URL.revokeObjectURL(url);
  } catch { notify.error('Download failed'); }
};

const ReportsTab = ({ locations, showCost }) => {
  const engineers = locations.engineers || [];
  const [loc, setLoc] = useState('warehouse');
  const [period, setPeriod] = useState('month');
  const [report, setReport] = useState(null);
  const [reorder, setReorder] = useState(null);
  const [loading, setLoading] = useState(true);

  const p = parseLoc(loc);
  const qs = `location=${p.type}&engineer_id=${encodeURIComponent(p.engineer_id || '')}`;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [rep, reo] = await Promise.all([
        axios.get(`${API}/svc/admin/stock/report?${qs}&period=${period}`, auth()),
        axios.get(`${API}/svc/admin/stock/reorder-report?${qs}`, auth()),
      ]);
      setReport(rep.data); setReorder(reo.data);
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not load report');
    } finally { setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loc, period]);

  useEffect(() => { load(); }, [load]);

  const snap = report?.snapshot || {};
  const stamp = new Date().toISOString().slice(0, 10);

  return (
    <div className="space-y-4" data-testid="admin-stock-reports">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[180px]">
          <LocationPicker label="Location" value={loc} onChange={setLoc} engineers={engineers} tid="reports-location" />
        </div>
        <div>
          <label className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Period</label>
          <div className="mt-1 flex rounded-xl border border-slate-200 overflow-hidden">
            {[['week', 'Week'], ['month', 'Month']].map(([k, lbl]) => (
              <button key={k} onClick={() => setPeriod(k)} data-testid={`reports-period-${k}`}
                      className={`px-4 h-11 text-sm font-bold ${period === k ? 'bg-slate-900 text-white' : 'bg-white text-slate-500'}`}>
                {lbl}
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading ? (
        <div className="py-16 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-slate-300" /></div>
      ) : (
        <>
          {/* Snapshot */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
            <Stat label="Stock value" value={gbp(snap.value_sell)} tid="reports-stat-value" />
            <Stat label="Units" value={num(snap.units)} tid="reports-stat-units" />
            <Stat label="Below min" value={num(snap.below_min)} icon={AlertTriangle} tid="reports-stat-belowmin" />
            <Stat label="Out of stock" value={num(snap.out)} icon={AlertTriangle} tid="reports-stat-out" />
          </div>

          {/* Exports */}
          <div className="flex flex-wrap gap-2">
            <button onClick={() => downloadFile(`/svc/admin/stock/report.csv?${qs}`, `stock-${p.type}-${stamp}.csv`)}
                    data-testid="reports-export-stock-csv"
                    className="inline-flex items-center gap-1.5 px-3.5 h-10 rounded-xl bg-slate-900 text-white text-sm font-bold">
              <Download className="w-4 h-4" /> Stock CSV
            </button>
            <button onClick={() => downloadFile(`/svc/admin/stock/reorder-report.csv?${qs}`, `reorder-${p.type}-${stamp}.csv`)}
                    data-testid="reports-export-reorder-csv"
                    className="inline-flex items-center gap-1.5 px-3.5 h-10 rounded-xl bg-amber-600 text-white text-sm font-bold">
              <ShoppingCart className="w-4 h-4" /> Reorder CSV
            </button>
            <button onClick={() => downloadFile(`/svc/admin/stock/report.pdf?${qs}&period=${period}`, `stock-report-${p.type}-${stamp}.pdf`)}
                    data-testid="reports-export-pdf"
                    className="inline-flex items-center gap-1.5 px-3.5 h-10 rounded-xl bg-cyan-600 text-white text-sm font-bold">
              <FileText className="w-4 h-4" /> PDF report
            </button>
          </div>

          {/* Period activity */}
          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <h3 className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2">Activity this {report?.period}</h3>
            {(report?.movements || []).length === 0 ? (
              <p className="text-sm text-slate-400" data-testid="reports-no-activity">No stock movements in this period.</p>
            ) : (
              <div className="divide-y divide-slate-100">
                {report.movements.map((m) => (
                  <div key={m.type} className="flex items-center justify-between py-1.5 text-sm" data-testid={`reports-movement-${m.type}`}>
                    <span className="font-semibold text-slate-700 capitalize">{m.type.replace(/_/g, ' ')}</span>
                    <span className="text-slate-500">{num(m.count)} moves · {num(m.units)} units</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Reorder list */}
          <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 bg-amber-50 border-b border-amber-100">
              <h3 className="font-bold text-amber-900 flex items-center gap-1.5"><ShoppingCart className="w-4 h-4" /> Reorder needed</h3>
              <span className="text-xs font-bold text-amber-700">{reorder?.totals?.parts || 0} parts · {num(reorder?.totals?.suggested_units || 0)} units{showCost && reorder?.totals?.est_order_cost != null ? ` · ${gbp(reorder.totals.est_order_cost)}` : ''}</span>
            </div>
            {(reorder?.items || []).length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-slate-400" data-testid="reports-reorder-empty">Everything is at or above its minimum level. Set Min/Max levels on parts to drive this list.</p>
            ) : (
              <div className="divide-y divide-slate-100">
                <div className="grid grid-cols-[1fr_48px_48px_60px] gap-2 px-4 py-2 bg-slate-50 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  <span>Part</span><span className="text-right">Have</span><span className="text-right">Min</span><span className="text-right">Order</span>
                </div>
                {reorder.items.slice(0, 100).map((it) => (
                  <div key={it.part_sku} className="grid grid-cols-[1fr_48px_48px_60px] gap-2 items-center px-4 py-2" data-testid={`reports-reorder-${it.part_sku}`}>
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-slate-900 truncate">{it.name}</p>
                      <p className="text-[10px] font-mono text-slate-400">{it.part_sku}</p>
                    </div>
                    <span className={`text-right text-sm font-bold tabular-nums ${it.zero ? 'text-rose-600' : 'text-amber-600'}`}>{num(it.qty)}</span>
                    <span className="text-right text-sm tabular-nums text-slate-500">{num(it.min_qty)}</span>
                    <span className="text-right text-sm font-extrabold tabular-nums text-cyan-700">{num(it.suggested_order)}</span>
                  </div>
                ))}
                {reorder.items.length > 100 && (
                  <p className="px-4 py-2 text-center text-xs text-slate-400">Showing first 100 — download the Reorder CSV for the full list.</p>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};

/* ───────────────────────────── Cross-org ────────────────────────── */

const CrossOrgTab = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/svc/admin/stock/cross-org`, auth());
        setData(r.data);
      } catch (e) {
        notify.error(e?.response?.data?.detail || 'Could not load cross-org stock');
      } finally { setLoading(false); }
    })();
  }, []);

  if (loading) return <div className="py-16 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-slate-300" /></div>;
  if (!data) return null;
  const { organizations = [], totals = {} } = data;

  return (
    <div className="space-y-4" data-testid="admin-stock-crossorg">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
        <Stat label="Organisations" value={num(totals.orgs)} icon={Building2} tid="crossorg-stat-orgs" />
        <Stat label="Total value" value={gbp(totals.value_sell)} tid="crossorg-stat-value" />
        <Stat label="Low lines" value={num(totals.low)} icon={AlertTriangle} tid="crossorg-stat-low" />
        <Stat label="Out of stock" value={num(totals.zero)} icon={AlertTriangle} tid="crossorg-stat-zero" />
      </div>
      <div className="rounded-2xl border border-slate-200 bg-white divide-y divide-slate-100 overflow-hidden">
        {organizations.map((o) => (
          <div key={o.organization_id} className="p-3.5 flex items-center gap-3" data-testid={`crossorg-row-${o.organization_id}`}>
            <div className="w-10 h-10 rounded-xl bg-slate-900 text-white flex items-center justify-center"><Building2 className="w-5 h-5" /></div>
            <div className="flex-1 min-w-0">
              <p className="font-bold text-slate-900 truncate">{o.name}</p>
              <p className="text-xs text-slate-500">{num(o.lines)} lines · {num(o.units)} units · {num(o.van_engineers)} vans
                {o.low ? <span className="text-amber-600 font-semibold"> · {o.low} low</span> : null}
                {o.zero ? <span className="text-rose-600 font-semibold"> · {o.zero} out</span> : null}
              </p>
            </div>
            <p className="font-extrabold text-slate-900 tabular-nums">{gbp(o.value_sell)}</p>
          </div>
        ))}
      </div>
    </div>
  );
};
