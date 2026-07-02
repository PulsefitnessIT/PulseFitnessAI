/**
 * EngineerStock — Iter 220ea·19 · Engineer App Phase 5 (Stock Control hub).
 *
 * Mobile-first van stock hub for engineers. Builds entirely on the
 * existing parts backend (svc_parts / svc_van_stock / svc_part_movements)
 * — no duplicate records. Sections:
 *   • Van    — my van stock (search · filters · sort · sell value)
 *   • Low    — lines at/below minimum + one-tap office request
 *   • History— my stock movement timeline
 *   • Requests — my replenishment requests + status
 *
 * Pricing: the mobile app shows the SELL value (compact). Cost price is
 * desktop/admin-only and is gated server-side (`show_cost`).
 *
 * Routes: /svc/engineer/stock   (also reachable from Home → Stock)
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Search, Boxes, AlertTriangle, History as HistoryIcon,
  Truck, Loader2, RefreshCw, PackagePlus, TrendingUp, Clock,
  ChevronRight, PoundSterling, CheckCircle2, XCircle, Hourglass, Package,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { useLocalization, formatMoneySync } from '@/utils/localization';

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : '/api';
const auth = () => ({
  headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
});

const TABS = [
  { k: 'van', label: 'Van', icon: Boxes },
  { k: 'low', label: 'Low', icon: AlertTriangle },
  { k: 'history', label: 'History', icon: HistoryIcon },
  { k: 'requests', label: 'Requests', icon: Truck },
];

const VAN_FILTERS = [
  { k: 'all', label: 'All' },
  { k: 'low', label: 'Low / out' },
  { k: 'most_used', label: 'Most used' },
  { k: 'recent', label: 'Recent' },
];

const REQ_STATUS = {
  pending:   { label: 'Pending',  cls: 'bg-amber-50 text-amber-700 border-amber-200', icon: Hourglass },
  approved:  { label: 'Approved', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: CheckCircle2 },
  rejected:  { label: 'Rejected', cls: 'bg-rose-50 text-rose-700 border-rose-200', icon: XCircle },
  cancelled: { label: 'Cancelled', cls: 'bg-slate-100 text-slate-500 border-slate-200', icon: XCircle },
};

const gbp = (n) => formatMoneySync(n);
const ago = (iso) => {
  if (!iso) return '—';
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (d <= 0) return 'today';
  if (d === 1) return 'yesterday';
  if (d < 30) return `${d}d ago`;
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
};

// ── Qty badge ─────────────────────────────────────────────────────
const QtyBadge = ({ qty, low, zero }) => {
  const cls = zero
    ? 'bg-rose-100 text-rose-700 border-rose-200'
    : low
      ? 'bg-amber-100 text-amber-700 border-amber-200'
      : 'bg-emerald-50 text-emerald-700 border-emerald-200';
  return (
    <span className={`inline-flex items-center justify-center min-w-[2.75rem] h-9 px-2 rounded-xl border text-base font-extrabold tabular-nums ${cls}`}>
      {qty}
    </span>
  );
};

// ── Replenish modal ───────────────────────────────────────────────
const ReplenishModal = ({ open, part, defaultQty, onClose, onDone }) => {
  const [qty, setQty] = useState(defaultQty || 1);
  const [urgency, setUrgency] = useState('normal');
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { setQty(defaultQty || 1); setUrgency('normal'); setNotes(''); }, [part, defaultQty]);
  if (!open || !part) return null;
  const submit = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/svc/engineer/stock/replenish`, {
        part_sku: part.part_sku, part_name: part.name, qty: Number(qty), urgency, notes,
      }, auth());
      notify.success(`Requested ${qty} × ${part.part_sku} from the office`);
      try { await onDone?.(); } catch { /* refresh failure shouldn't block close */ }
      onClose();
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Could not send request');
    } finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 z-[120] flex items-end sm:items-center justify-center bg-slate-900/50 p-0 sm:p-4"
         data-testid="replenish-modal" onClick={onClose}>
      <div className="w-full sm:max-w-md bg-white rounded-t-2xl sm:rounded-2xl p-5 pb-28 sm:pb-5 space-y-4"
           onClick={(e) => e.stopPropagation()}>
        <div>
          <h3 className="text-lg font-bold text-slate-900">Request replenishment</h3>
          <p className="text-sm text-slate-500">{part.name} · <span className="font-mono">{part.part_sku}</span></p>
        </div>
        <div>
          <label className="text-xs font-bold uppercase tracking-wider text-slate-500">Quantity</label>
          <div className="mt-1 flex items-center gap-3">
            <button className="w-11 h-11 rounded-xl border border-slate-200 text-xl font-bold text-slate-600"
                    onClick={() => setQty((q) => Math.max(1, (Number(q) || 1) - 1))} data-testid="replenish-qty-minus">−</button>
            <input type="number" min={1} max={999} value={qty}
                   onChange={(e) => {
                     const n = parseInt(e.target.value, 10);
                     setQty(Number.isNaN(n) ? '' : Math.min(Math.max(n, 1), 999));
                   }}
                   className="w-20 h-11 text-center text-lg font-bold border border-slate-200 rounded-xl"
                   data-testid="replenish-qty-input" />
            <button className="w-11 h-11 rounded-xl border border-slate-200 text-xl font-bold text-slate-600"
                    onClick={() => setQty((q) => Math.min(999, (Number(q) || 0) + 1))} data-testid="replenish-qty-plus">+</button>
          </div>
        </div>
        <div>
          <label className="text-xs font-bold uppercase tracking-wider text-slate-500">Urgency</label>
          <div className="mt-1 grid grid-cols-3 gap-2">
            {['normal', 'urgent', 'critical'].map((u) => (
              <button key={u} onClick={() => setUrgency(u)}
                      data-testid={`replenish-urgency-${u}`}
                      className={`h-10 rounded-xl border text-sm font-semibold capitalize transition-colors ${
                        urgency === u ? 'bg-cyan-600 text-white border-cyan-600' : 'bg-white text-slate-600 border-slate-200'}`}>
                {u}
              </button>
            ))}
          </div>
        </div>
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} maxLength={400}
                  placeholder="Notes for the office (optional)"
                  className="w-full text-sm border border-slate-200 rounded-xl px-3 py-2"
                  data-testid="replenish-notes" />
        <div className="flex gap-3 pt-1">
          <button onClick={onClose} className="flex-1 h-12 rounded-xl border border-slate-200 font-semibold text-slate-600"
                  data-testid="replenish-cancel">Cancel</button>
          <button onClick={submit} disabled={busy || !qty || Number(qty) < 1}
                  className="flex-1 h-12 rounded-xl bg-cyan-600 text-white font-bold flex items-center justify-center gap-2 disabled:opacity-60"
                  data-testid="replenish-submit">
            {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : <PackagePlus className="w-5 h-5" />}
            Send request
          </button>
        </div>
      </div>
    </div>
  );
};

export default function EngineerStock() {
  const navigate = useNavigate();
  useLocalization();  // warm currency cache
  const [tab, setTab] = useState('van');
  const [loading, setLoading] = useState(true);
  const [van, setVan] = useState({ items: [], summary: {}, show_cost: false });
  const [low, setLow] = useState({ rows: [], count: 0 });
  const [history, setHistory] = useState({ items: [] });
  const [requests, setRequests] = useState([]);
  const [search, setSearch] = useState('');
  const [vanFilter, setVanFilter] = useState('all');
  const [sort, setSort] = useState('name');
  const [modal, setModal] = useState({ open: false, part: null, qty: 1 });

  const loadVan = useCallback(async () => {
    const r = await axios.get(`${API}/svc/engineer/stock/van`, {
      ...auth(), params: { search, filter: vanFilter, sort },
    });
    setVan(r.data);
  }, [search, vanFilter, sort]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    const results = await Promise.allSettled([
      axios.get(`${API}/svc/engineer/stock/van`, { ...auth(), params: { search, filter: vanFilter, sort } }),
      axios.get(`${API}/svc/engineer/stock/low`, auth()),
      axios.get(`${API}/svc/engineer/stock/history`, { ...auth(), params: { limit: 50 } }),
      axios.get(`${API}/svc/engineer/parts-requests`, auth()),
    ]);
    const [v, l, h, rq] = results;
    if (v.status === 'fulfilled') setVan(v.value.data);
    if (l.status === 'fulfilled') setLow(l.value.data);
    if (h.status === 'fulfilled') setHistory(h.value.data);
    if (rq.status === 'fulfilled') setRequests(rq.value.data?.items || []);
    if (results.some((r) => r.status === 'rejected')) {
      notify.error('Some stock data could not be loaded');
    }
    setLoading(false);
  }, [search, vanFilter, sort]);

  useEffect(() => { loadAll(); /* initial */ }, []); // eslint-disable-line react-hooks/exhaustive-deps
  // Re-query van on filter/search/sort change (debounced for search).
  useEffect(() => {
    const t = setTimeout(() => { loadVan().catch(() => {}); }, 250);
    return () => clearTimeout(t);
  }, [search, vanFilter, sort, loadVan]);

  const summary = van.summary || {};
  const openReplenish = (part, qty) => setModal({ open: true, part, qty: qty || 1 });

  const lowBadge = low.count > 0 ? low.count : null;
  const pendingReqs = useMemo(() => requests.filter((r) => r.status === 'pending').length, [requests]);

  return (
    <div className="min-h-screen bg-slate-50" data-testid="engineer-stock-page">
      {/* Header */}
      <div className="sticky top-0 z-30 bg-white border-b border-slate-200">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center gap-3">
          <button onClick={() => navigate('/svc/engineer')} className="p-2 -ml-2 text-slate-500"
                  data-testid="stock-back-btn" aria-label="Back">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div className="flex-1">
            <h1 className="text-lg font-extrabold text-slate-900 leading-none">My Stock</h1>
            <p className="text-xs text-slate-500 mt-0.5">Van inventory &amp; replenishment</p>
          </div>
          <button onClick={() => navigate('/svc/engineer/catalogue')} className="px-2.5 h-9 rounded-lg text-xs font-bold text-cyan-700 bg-cyan-50 border border-cyan-100 flex items-center gap-1"
                  data-testid="stock-catalogue-btn">
            <Package className="w-4 h-4" /> Catalogue
          </button>
          <button onClick={loadAll} className="p-2 text-slate-500" data-testid="stock-refresh-btn" aria-label="Refresh">
            <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {/* Summary chips */}
        <div className="max-w-3xl mx-auto px-4 pb-3 grid grid-cols-3 gap-2">
          <Stat label="Lines" value={summary.lines ?? 0} testid="stock-stat-lines" />
          <Stat label="Low / out" value={(summary.low ?? 0) + (summary.zero ?? 0)} accent="amber" testid="stock-stat-low" />
          <Stat label="Van value" value={gbp(summary.value_sell)} testid="stock-stat-value" small />
        </div>

        {/* Tabs */}
        <div className="max-w-3xl mx-auto px-2 flex">
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = tab === t.k;
            const badge = t.k === 'low' ? lowBadge : (t.k === 'requests' ? (pendingReqs || null) : null);
            return (
              <button key={t.k} onClick={() => setTab(t.k)}
                      data-testid={`stock-tab-${t.k}`}
                      className={`flex-1 flex flex-col items-center gap-0.5 py-2 border-b-2 transition-colors ${
                        active ? 'border-cyan-600 text-cyan-700' : 'border-transparent text-slate-400'}`}>
                <div className="relative">
                  <Icon className="w-5 h-5" />
                  {badge ? (
                    <span className="absolute -top-1.5 -right-2 min-w-[1rem] h-4 px-1 rounded-full bg-rose-500 text-white text-[10px] font-bold flex items-center justify-center">
                      {badge}
                    </span>
                  ) : null}
                </div>
                <span className="text-[11px] font-semibold">{t.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 pt-4 pb-28 space-y-3">
        {loading && tab === 'van' && van.items.length === 0 ? (
          <div className="py-20 flex justify-center text-slate-400"><Loader2 className="w-7 h-7 animate-spin" /></div>
        ) : null}

        {/* ── VAN ── */}
        {tab === 'van' && (
          <>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input value={search} onChange={(e) => setSearch(e.target.value)}
                     placeholder="Search part, SKU, manufacturer"
                     className="w-full h-11 pl-10 pr-3 rounded-xl border border-slate-200 text-sm bg-white"
                     data-testid="stock-search" />
            </div>
            <div className="flex items-center gap-2 overflow-x-auto -mx-1 px-1 pb-1">
              {VAN_FILTERS.map((f) => (
                <button key={f.k} onClick={() => setVanFilter(f.k)}
                        data-testid={`stock-filter-${f.k}`}
                        className={`shrink-0 px-3 h-8 rounded-full text-xs font-semibold border transition-colors ${
                          vanFilter === f.k ? 'bg-slate-900 text-white border-slate-900' : 'bg-white text-slate-600 border-slate-200'}`}>
                  {f.label}
                </button>
              ))}
              <select value={sort} onChange={(e) => setSort(e.target.value)}
                      data-testid="stock-sort"
                      className="shrink-0 ml-auto h-8 rounded-full text-xs font-semibold border border-slate-200 bg-white px-2 text-slate-600">
                <option value="name">A–Z</option>
                <option value="qty">Qty ↑</option>
                <option value="most_used">Most used</option>
                <option value="recent">Recent</option>
              </select>
            </div>

            {van.items.length === 0 && !loading ? (
              <Empty icon={Boxes} title="No van stock yet"
                     body="Parts allocated to you or received from the office will appear here." />
            ) : null}

            {van.items.map((p) => (
              <div key={p.part_sku} className="bg-white rounded-2xl border border-slate-200 p-3.5 flex items-center gap-3"
                   data-testid={`van-item-${p.part_sku}`}>
                <QtyBadge qty={p.qty} low={p.low} zero={p.zero} />
                <div className="flex-1 min-w-0">
                  <p className="font-bold text-slate-900 text-sm truncate">{p.name}</p>
                  <p className="text-xs text-slate-500 truncate">
                    <span className="font-mono">{p.part_sku}</span>
                    {p.manufacturer ? ` · ${p.manufacturer}` : ''}
                    {p.category ? ` · ${p.category}` : ''}
                  </p>
                  <div className="flex items-center gap-3 mt-1 text-[11px] text-slate-400">
                    <span className="inline-flex items-center gap-0.5 font-semibold text-slate-600">
                      <PoundSterling className="w-3 h-3" />{(p.sell_price || 0).toFixed(2)}
                    </span>
                    {p.used_count > 0 && (
                      <span className="inline-flex items-center gap-0.5"><TrendingUp className="w-3 h-3" />{p.used_count} used</span>
                    )}
                    {p.last_used_at && (
                      <span className="inline-flex items-center gap-0.5"><Clock className="w-3 h-3" />{ago(p.last_used_at)}</span>
                    )}
                    {p.min_qty > 0 && <span>min {p.min_qty}</span>}
                  </div>
                </div>
                <button onClick={() => openReplenish(p, p.reorder_qty || 1)}
                        data-testid={`van-request-${p.part_sku}`}
                        className="shrink-0 px-3 h-9 rounded-xl bg-cyan-50 text-cyan-700 text-xs font-bold border border-cyan-100 flex items-center gap-1">
                  <PackagePlus className="w-4 h-4" /> Request
                </button>
              </div>
            ))}
          </>
        )}

        {/* ── LOW ── */}
        {tab === 'low' && (
          low.rows.length === 0 ? (
            <Empty icon={CheckCircle2} title="Van fully stocked"
                   body="No parts are below their minimum level. Nice." />
          ) : low.rows.map((r) => (
            <div key={r.part_sku} className="bg-white rounded-2xl border border-slate-200 p-3.5 flex items-center gap-3"
                 data-testid={`low-item-${r.part_sku}`}>
              <QtyBadge qty={r.qty} low={!r.zero} zero={r.zero} />
              <div className="flex-1 min-w-0">
                <p className="font-bold text-slate-900 text-sm truncate">{r.name}</p>
                <p className="text-xs text-slate-500 truncate"><span className="font-mono">{r.part_sku}</span>{r.manufacturer ? ` · ${r.manufacturer}` : ''}</p>
                <p className="text-[11px] text-amber-600 font-semibold mt-0.5">
                  {r.zero ? 'Out of stock' : `Below min (${r.min_qty})`} · suggest {r.suggested_qty}
                </p>
              </div>
              <button onClick={() => openReplenish(r, r.suggested_qty)}
                      data-testid={`low-request-${r.part_sku}`}
                      className="shrink-0 px-3 h-9 rounded-xl bg-cyan-600 text-white text-xs font-bold flex items-center gap-1">
                <PackagePlus className="w-4 h-4" /> Request
              </button>
            </div>
          ))
        )}

        {/* ── HISTORY ── */}
        {tab === 'history' && (
          history.items.length === 0 ? (
            <Empty icon={HistoryIcon} title="No movements yet"
                   body="Parts used on jobs, adjustments and replenishments show here." />
          ) : history.items.map((m, i) => (
            <div key={m.id || i} className="bg-white rounded-xl border border-slate-200 px-3.5 py-2.5 flex items-center gap-3"
                 data-testid="history-row">
              <MoveIcon type={m.movement_type} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-slate-800 truncate">
                  {m.part_name || m.part_sku} <span className="font-mono text-xs text-slate-400">{m.part_sku}</span>
                </p>
                <p className="text-[11px] text-slate-400 capitalize">
                  {(m.movement_type || 'move').replace('_', ' ')}
                  {m.machine_name ? ` · ${m.machine_name}` : ''}
                  {m.case_reference ? ` · ${m.case_reference}` : ''}
                </p>
              </div>
              <div className="text-right">
                <p className="text-sm font-bold tabular-nums text-slate-700">{m.qty}</p>
                <p className="text-[10px] text-slate-400">{ago(m.at)}</p>
              </div>
            </div>
          ))
        )}

        {/* ── REQUESTS ── */}
        {tab === 'requests' && (
          requests.length === 0 ? (
            <Empty icon={Truck} title="No requests"
                   body="Request replenishment from the Van or Low tabs and track it here." />
          ) : requests.map((r) => {
            const st = REQ_STATUS[r.status] || REQ_STATUS.pending;
            const Icon = st.icon;
            return (
              <div key={r.id} className="bg-white rounded-2xl border border-slate-200 p-3.5"
                   data-testid={`request-row-${r.id}`}>
                <div className="flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="font-bold text-slate-900 text-sm truncate">{r.qty} × {r.part_name || r.part_sku}</p>
                    <p className="text-xs text-slate-500 truncate">
                      <span className="font-mono">{r.part_sku}</span>
                      {r.case_reference ? ` · ${r.case_reference}` : (r.kind === 'van_replenish' ? ' · van top-up' : '')}
                      {` · ${ago(r.created_at)}`}
                    </p>
                  </div>
                  <span className={`shrink-0 inline-flex items-center gap-1 px-2.5 h-7 rounded-full border text-xs font-bold ${st.cls}`}>
                    <Icon className="w-3.5 h-3.5" />{st.label}
                  </span>
                </div>
                {(r.backordered || r.eta_date) && (
                  <p className="mt-2 text-[11px] font-semibold text-amber-600 inline-flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {r.backordered ? 'Backordered at supplier' : `ETA ${new Date(r.eta_date).toLocaleDateString('en-GB')}`}
                  </p>
                )}
              </div>
            );
          })
        )}
      </div>

      <ReplenishModal open={modal.open} part={modal.part} defaultQty={modal.qty}
                      onClose={() => setModal({ open: false, part: null, qty: 1 })}
                      onDone={loadAll} />
    </div>
  );
}

// ── Small pieces ──────────────────────────────────────────────────
const Stat = ({ label, value, accent, small, testid }) => (
  <div className={`rounded-xl border px-3 py-2 ${accent === 'amber' ? 'bg-amber-50 border-amber-100' : 'bg-slate-50 border-slate-100'}`}
       data-testid={testid}>
    <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{label}</p>
    <p className={`font-extrabold text-slate-900 ${small ? 'text-base' : 'text-xl'} leading-tight`}>{value}</p>
  </div>
);

const Empty = ({ icon: Icon, title, body }) => (
  <div className="py-16 text-center" data-testid="stock-empty">
    <div className="w-14 h-14 mx-auto rounded-2xl bg-slate-100 flex items-center justify-center text-slate-400">
      <Icon className="w-7 h-7" />
    </div>
    <p className="mt-3 font-bold text-slate-700">{title}</p>
    <p className="text-sm text-slate-400 max-w-xs mx-auto mt-1">{body}</p>
  </div>
);

const MOVE_STYLE = {
  consume:    { cls: 'bg-rose-50 text-rose-600', icon: TrendingUp },
  receive:    { cls: 'bg-emerald-50 text-emerald-600', icon: PackagePlus },
  allocate:   { cls: 'bg-cyan-50 text-cyan-600', icon: ChevronRight },
  deallocate: { cls: 'bg-slate-100 text-slate-500', icon: RefreshCw },
  adjust:     { cls: 'bg-amber-50 text-amber-600', icon: RefreshCw },
};
const MoveIcon = ({ type }) => {
  const s = MOVE_STYLE[type] || { cls: 'bg-slate-100 text-slate-500', icon: HistoryIcon };
  const Icon = s.icon;
  return (
    <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${s.cls}`}>
      <Icon className="w-4 h-4" />
    </div>
  );
};
