/**
 * PartsAllocator — iter 215dq.
 *
 * Search the parts catalogue, pick a part, choose source (warehouse
 * already-triaged or van stock), set qty. Returns a list of allocation
 * objects via onChange so the parent can render and persist.
 *
 * Used at intake (case isn't created yet — purely local state) and in
 * the case drawer (case exists — POSTs to /api/svc/parts/allocate).
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { Package, Search, Plus, X, Truck, Warehouse } from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

export default function PartsAllocator({ value = [], onChange, caseId, engineerId }) {
  const [search, setSearch] = useState('');
  const [results, setResults] = useState([]);
  const [picked, setPicked] = useState(null);
  const [qty, setQty] = useState(1);
  const [source, setSource] = useState('warehouse');
  const [creatingSku, setCreatingSku] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const t = setTimeout(async () => {
      try {
        const r = await axios.get(`${API}/svc/parts`, { ...auth(), params: { search, limit: 8 } });
        setResults(r.data.parts || []);
      } catch (_) { /* ignore */ }
    }, 200);
    return () => clearTimeout(t);
  }, [search]);

  const allocations = value || [];

  const addLocal = (alloc) => onChange?.([...allocations, alloc]);
  const removeAt = (i) => {
    const next = [...allocations];
    next.splice(i, 1);
    onChange?.(next);
  };

  const submit = async () => {
    if (!picked) { notify.error('Pick a part first'); return; }
    if (qty <= 0) { notify.error('Qty must be > 0'); return; }
    if (source === 'van' && !engineerId) { notify.error('Assign engineer before allocating from van'); return; }
    setBusy(true);
    try {
      if (caseId) {
        const r = await axios.post(
          `${API}/svc/parts/allocate`,
          { case_id: caseId, part_sku: picked.sku, qty, source, engineer_id: engineerId || '' },
          auth(),
        );
        addLocal(r.data);
      } else {
        addLocal({
          id: `tmp-${Date.now()}`,
          part_sku: picked.sku,
          part_name: picked.name,
          qty,
          source,
          engineer_id: engineerId || '',
        });
      }
      setPicked(null);
      setSearch('');
      setQty(1);
      setSource('warehouse');
    } catch (e) {
      notify.error('Allocation failed', e?.response?.data?.detail || e.message);
    } finally { setBusy(false); }
  };

  const createPart = async () => {
    const sku = creatingSku.trim().toUpperCase();
    if (!sku) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/svc/parts`, { sku, name: search || sku }, auth());
      setPicked(r.data);
      setResults([r.data]);
      setCreatingSku('');
      notify.success(`Added ${sku} to catalogue`);
    } catch (e) {
      notify.error('Could not add part', e?.response?.data?.detail || e.message);
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-2" data-testid="parts-allocator">
      {/* Existing allocations */}
      {allocations.length > 0 ? (
        <ul className="space-y-1">
          {allocations.map((a, i) => (
            <li
              key={a.id || `${a.part_sku}-${i}`}
              className="flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-md border text-xs"
              style={{ borderColor: 'var(--theme-border)', background: 'var(--theme-surface)' }}
              data-testid={`parts-row-${a.part_sku}`}
            >
              <span className="inline-flex items-center gap-1.5 min-w-0">
                {a.source === 'van' ? <Truck size={11} /> : <Warehouse size={11} />}
                <strong className="truncate">{a.part_sku}</strong>
                <span className="opacity-70 truncate">— {a.part_name}</span>
              </span>
              <span className="inline-flex items-center gap-2 flex-shrink-0">
                <span className="opacity-70 tabular-nums">qty {a.qty}</span>
                <button
                  type="button"
                  onClick={async () => {
                    if (caseId && a.id && !String(a.id).startsWith('tmp-')) {
                      try {
                        await axios.delete(`${API}/svc/parts/allocate/${a.id}`, auth());
                      } catch (_) { /* ignore */ }
                    }
                    removeAt(i);
                  }}
                  aria-label="Remove allocation"
                  className="p-0.5 hover:opacity-70"
                  data-testid={`parts-remove-${a.part_sku}`}
                >
                  <X size={11} />
                </button>
              </span>
            </li>
          ))}
        </ul>
      ) : null}

      {/* Picker */}
      <div className="rounded-md border p-2 space-y-2" style={{ borderColor: 'var(--theme-border)' }}>
        <div className="relative">
          <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 opacity-50" />
          <input
            type="text"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPicked(null); }}
            placeholder="Search SKU or name…"
            className="w-full pl-7 pr-3 py-1.5 rounded-md border bg-transparent text-sm"
            style={{ borderColor: 'var(--theme-border)' }}
            data-testid="parts-search"
          />
        </div>
        {results.length > 0 && !picked ? (
          <ul className="max-h-32 overflow-y-auto space-y-0.5" data-testid="parts-results">
            {results.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  onClick={() => setPicked(p)}
                  className="w-full text-left px-2 py-1 rounded text-xs hover:bg-black/5"
                  data-testid={`parts-option-${p.sku}`}
                >
                  <strong>{p.sku}</strong>
                  <span className="opacity-70"> — {p.name}</span>
                  {p.manufacturer ? <span className="opacity-50"> · {p.manufacturer}</span> : null}
                </button>
              </li>
            ))}
          </ul>
        ) : null}

        {/* Empty catalogue / Sage-Sicon hint */}
        {results.length === 0 && search.trim() ? (
          <div className="text-[11px] opacity-70 space-y-1.5" data-testid="parts-empty-hint">
            <p>No part matches "{search}". For Pulse Fitness orgs, parts will sync from Sage / Sicon — until then add ad-hoc:</p>
            <div className="flex gap-1.5">
              <input
                type="text"
                value={creatingSku}
                onChange={(e) => setCreatingSku(e.target.value)}
                placeholder="SKU"
                className="px-2 py-1 rounded border text-xs"
                style={{ borderColor: 'var(--theme-border)' }}
                data-testid="parts-new-sku"
              />
              <button
                type="button"
                onClick={createPart}
                disabled={!creatingSku.trim() || busy}
                className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-bold border disabled:opacity-50"
                style={{ borderColor: 'var(--theme-border)' }}
                data-testid="parts-create"
              >
                <Plus size={10} /> Add to catalogue
              </button>
            </div>
          </div>
        ) : null}

        {picked ? (
          <div className="grid grid-cols-12 gap-2 items-center pt-1">
            <span className="col-span-5 text-xs font-bold truncate" data-testid="parts-picked">
              <Package size={11} className="inline mr-1" />
              {picked.sku} <span className="opacity-70 font-normal">— {picked.name}</span>
            </span>
            <input
              type="number"
              min={1}
              value={qty}
              onChange={(e) => setQty(Math.max(1, Number(e.target.value)))}
              className="col-span-2 px-2 py-1 rounded border text-xs tabular-nums"
              style={{ borderColor: 'var(--theme-border)' }}
              data-testid="parts-qty"
            />
            <select
              value={source}
              onChange={(e) => setSource(e.target.value)}
              className="col-span-3 px-2 py-1 rounded border text-xs bg-transparent"
              style={{ borderColor: 'var(--theme-border)' }}
              data-testid="parts-source"
            >
              <option value="warehouse">Warehouse</option>
              <option value="van">Van stock</option>
            </select>
            <button
              type="button"
              onClick={submit}
              disabled={busy}
              className="col-span-2 px-2 py-1 rounded text-xs font-bold text-white disabled:opacity-50"
              style={{ background: '#0891b2' }}
              data-testid="parts-allocate"
            >
              {busy ? '…' : 'Allocate'}
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
