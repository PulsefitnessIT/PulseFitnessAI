import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Truck, PackageCheck, X, Boxes, Loader2 } from 'lucide-react';
import { notify } from '@/components/notifications';
import { useAuth } from '@/App';

/* Fulfilment panel for a CPQ v2 quote — raise a PO from the deal's
   equipment/spare lines, then receive goods (GRN) to auto-create the
   equipment register records. Renders inside QuoteDetail. */
export const QuoteFulfilmentPanel = ({ quoteId, API, headers, fmt, c, isDark }) => {
  const { user } = useAuth();
  const canManage = !!(user && (user.is_master_admin || user.is_pulse_admin
    || ['owner', 'admin', 'manager'].includes((user.role || '').toLowerCase())));
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState('');
  const [poForm, setPoForm] = useState(null);   // {supplier_name, supplier_email, line_ids:Set}
  const [grnFor, setGrnFor] = useState(null);    // po
  const [grnRows, setGrnRows] = useState({});    // line_id -> {qty, serials}

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/crm/v2/quotes/${quoteId}/fulfilment`, { headers: headers() });
      setData(r.data);
    } catch (e) { console.error(e); }
  }, [API, headers, quoteId]);
  useEffect(() => { load(); }, [load]);

  if (!data) return null;
  const panel = isDark ? 'var(--color-neutral-950)' : 'var(--color-neutral-50)';
  const bd = isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)';
  const PO_STATUS = {
    draft: { t: 'Draft', col: c.textMuted }, ordered: { t: 'Ordered', col: 'var(--color-info-ios)' },
    part_received: { t: 'Part received', col: 'var(--color-accent-amber)' },
    received: { t: 'Received', col: 'var(--color-success-alt)' }, cancelled: { t: 'Cancelled', col: 'var(--color-danger-alt)' },
  };

  const openPo = () => setPoForm({ supplier_name: '', supplier_email: '', line_ids: new Set(data.procurable_lines.map(l => l.line_id)) });
  const submitPo = async () => {
    setBusy('po');
    try {
      const r = await axios.post(`${API}/crm/v2/quotes/${quoteId}/purchase-orders`,
        { supplier_name: poForm.supplier_name, supplier_email: poForm.supplier_email, line_ids: [...poForm.line_ids] },
        { headers: headers() });
      setData(r.data); setPoForm(null); notify.success('Purchase order raised');
    } catch (e) { notify.error(e.response?.data?.detail || 'Could not raise PO'); }
    setBusy('');
  };

  const openGrn = (po) => {
    setGrnFor(po);
    const rows = {};
    po.items.forEach(it => { rows[it.line_id] = { qty: String(Math.max(0, (it.quantity || 0) - (it.received_qty || 0))), serials: '' }; });
    setGrnRows(rows);
  };
  const submitGrn = async () => {
    setBusy('grn');
    try {
      const items = grnFor.items.map(it => {
        const row = grnRows[it.line_id] || {};
        const qty = parseFloat(row.qty) || 0;
        if (qty <= 0) return null;
        const serials = (row.serials || '').split(/[\n,]+/).map(s => s.trim()).filter(Boolean);
        return { line_id: it.line_id, received_qty: qty, serials };
      }).filter(Boolean);
      const r = await axios.post(`${API}/crm/v2/quotes/${quoteId}/purchase-orders/${grnFor.id}/receive`, { items }, { headers: headers() });
      setData(r.data); setGrnFor(null);
      notify.success(`${r.data.created_equipment.length} equipment record(s) created`);
    } catch (e) { notify.error(e.response?.data?.detail || 'Could not receive goods'); }
    setBusy('');
  };

  if (data.summary.procurable_line_count === 0) return null;

  return (
    <div className="mt-6" data-testid="quote-fulfilment-panel">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold flex items-center gap-1.5" style={{ color: c.text }}>
          <Truck size={15} /> Fulfilment — purchase orders &amp; goods received
        </h3>
        {canManage && (
          <button onClick={openPo} className="text-xs px-2 py-1 rounded border" style={{ borderColor: bd, color: 'var(--color-info-ios)' }} data-testid="fulfilment-raise-po">Raise purchase order</button>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4">
        {[
          { l: 'Equipment units', v: data.summary.equipment_units_expected, testid: 'fulfilment-units-expected' },
          { l: 'Purchase orders', v: data.summary.po_count, testid: 'fulfilment-po-count' },
          { l: 'Registered', v: data.summary.equipment_created, testid: 'fulfilment-equipment-created' },
        ].map(k => (
          <div key={k.l} className="p-3 rounded-lg border" style={{ background: panel, borderColor: bd }}>
            <p className="text-[10px] uppercase tracking-wider" style={{ color: c.textDim }}>{k.l}</p>
            <p className="text-base font-medium" style={{ color: c.text }} data-testid={k.testid}>{k.v}</p>
          </div>
        ))}
      </div>

      {data.purchase_orders.length === 0 && (
        <p className="text-sm mb-3" style={{ color: c.textMuted }} data-testid="fulfilment-empty">No purchase orders yet. Raise one from this deal's equipment &amp; spare lines.</p>
      )}

      <div className="space-y-2">
        {data.purchase_orders.map(po => {
          const stat = PO_STATUS[po.status] || PO_STATUS.draft;
          const outstanding = po.items.reduce((s, i) => s + Math.max(0, (i.quantity || 0) - (i.received_qty || 0)), 0);
          return (
            <div key={po.id} className="p-3 rounded-lg border" style={{ background: panel, borderColor: bd }} data-testid={`fulfilment-po-${po.id}`}>
              <div className="flex items-center gap-3 flex-wrap">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium" style={{ color: c.text }}>{po.po_number} · {po.supplier_name}</p>
                  <p className="text-[11px]" style={{ color: c.textDim }}>{po.items.length} line(s) · {fmt(po.subtotal)} ex VAT</p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{ background: `${stat.col}22`, color: stat.col }} data-testid={`fulfilment-po-status-${po.id}`}>{stat.t}</span>
                {canManage && outstanding > 0 && (
                  <button onClick={() => openGrn(po)} className="text-xs px-2.5 py-1 rounded-md border inline-flex items-center gap-1" style={{ borderColor: bd, color: 'var(--color-success-alt)' }} data-testid={`fulfilment-receive-${po.id}`}><PackageCheck size={12} /> Receive goods</button>
                )}
              </div>
              <div className="mt-2 space-y-0.5">
                {po.items.map(it => (
                  <p key={it.line_id} className="text-[11px]" style={{ color: c.textDim }}>
                    {it.is_equipment ? '🏋' : '🔧'} {it.name} — {it.received_qty || 0}/{it.quantity} received
                  </p>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {data.equipment.length > 0 && (
        <div className="mt-3">
          <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: c.textDim }}>Equipment registered from this deal</p>
          <div className="flex flex-wrap gap-1.5" data-testid="fulfilment-equipment-list">
            {data.equipment.map(e => (
              <span key={e.id} className="text-[11px] px-2 py-1 rounded-full border inline-flex items-center gap-1" style={{ borderColor: bd, color: c.text }} data-testid={`fulfilment-equipment-${e.id}`}>
                <Boxes size={11} /> {e.name}{e.serial_number ? ` · ${e.serial_number}` : ''}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Raise PO dialog */}
      {poForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setPoForm(null)}>
          <div className="w-full max-w-md rounded-xl p-5" style={{ background: isDark ? 'var(--color-ink)' : '#fff' }} onClick={e => e.stopPropagation()} data-testid="fulfilment-po-dialog">
            <div className="flex items-center justify-between mb-3"><h4 className="font-semibold" style={{ color: c.text }}>Raise purchase order</h4><button onClick={() => setPoForm(null)}><X size={16} style={{ color: c.textMuted }} /></button></div>
            <label className="text-xs" style={{ color: c.textDim }}>Supplier name</label>
            <input value={poForm.supplier_name} onChange={e => setPoForm(f => ({ ...f, supplier_name: e.target.value }))} className="w-full mt-1 mb-2 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${bd}`, color: c.text }} data-testid="fulfilment-po-supplier" />
            <label className="text-xs" style={{ color: c.textDim }}>Supplier email (optional)</label>
            <input value={poForm.supplier_email} onChange={e => setPoForm(f => ({ ...f, supplier_email: e.target.value }))} className="w-full mt-1 mb-3 px-3 py-2 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${bd}`, color: c.text }} data-testid="fulfilment-po-email" />
            <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: c.textDim }}>Lines to procure (at cost)</p>
            <div className="max-h-40 overflow-y-auto mb-3">
              {data.procurable_lines.map(l => (
                <label key={l.line_id} className="flex items-center gap-2 text-sm py-1" style={{ color: c.text }}>
                  <input type="checkbox" checked={poForm.line_ids.has(l.line_id)} onChange={() => setPoForm(f => { const s = new Set(f.line_ids); s.has(l.line_id) ? s.delete(l.line_id) : s.add(l.line_id); return { ...f, line_ids: s }; })} />
                  <span className="flex-1 truncate">{l.description} × {l.quantity}</span>
                  <span className="text-[11px]" style={{ color: c.textDim }}>{fmt(l.cost_price)}</span>
                </label>
              ))}
            </div>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setPoForm(null)} className="px-3 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={submitPo} disabled={busy === 'po' || !poForm.supplier_name.trim() || poForm.line_ids.size === 0} className="px-3 py-2 text-sm rounded-md bg-[var(--color-info-ios)] text-white disabled:opacity-50" data-testid="fulfilment-po-submit">{busy === 'po' ? 'Raising…' : 'Raise PO'}</button>
            </div>
          </div>
        </div>
      )}

      {/* GRN dialog */}
      {grnFor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setGrnFor(null)}>
          <div className="w-full max-w-lg rounded-xl p-5" style={{ background: isDark ? 'var(--color-ink)' : '#fff' }} onClick={e => e.stopPropagation()} data-testid="fulfilment-grn-dialog">
            <div className="flex items-center justify-between mb-3"><h4 className="font-semibold" style={{ color: c.text }}>Receive goods · {grnFor.po_number}</h4><button onClick={() => setGrnFor(null)}><X size={16} style={{ color: c.textMuted }} /></button></div>
            <p className="text-[11px] mb-3" style={{ color: c.textDim }}>Equipment lines create asset records — one per serial number entered.</p>
            <div className="space-y-3 max-h-72 overflow-y-auto">
              {grnFor.items.map(it => {
                const outstanding = Math.max(0, (it.quantity || 0) - (it.received_qty || 0));
                if (outstanding <= 0) return null;
                return (
                  <div key={it.line_id} className="p-2 rounded-md border" style={{ borderColor: bd }} data-testid={`fulfilment-grn-line-${it.line_id}`}>
                    <p className="text-sm" style={{ color: c.text }}>{it.name} <span className="text-[11px]" style={{ color: c.textDim }}>({outstanding} outstanding)</span></p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-[11px]" style={{ color: c.textDim }}>Qty</span>
                      <input type="number" min="0" max={outstanding} value={grnRows[it.line_id]?.qty || ''} onChange={e => setGrnRows(r => ({ ...r, [it.line_id]: { ...r[it.line_id], qty: e.target.value } }))} className="w-16 px-2 py-1 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${bd}`, color: c.text }} data-testid={`fulfilment-grn-qty-${it.line_id}`} />
                      {it.is_equipment && (
                        <input value={grnRows[it.line_id]?.serials || ''} onChange={e => setGrnRows(r => ({ ...r, [it.line_id]: { ...r[it.line_id], serials: e.target.value } }))} placeholder="serials, comma-separated" className="flex-1 px-2 py-1 text-sm rounded-md" style={{ background: isDark ? 'var(--color-ink-alt)' : '#fff', border: `1px solid ${bd}`, color: c.text }} data-testid={`fulfilment-grn-serials-${it.line_id}`} />
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="flex gap-2 justify-end mt-4">
              <button onClick={() => setGrnFor(null)} className="px-3 py-2 text-sm" style={{ color: c.textMuted }}>Cancel</button>
              <button onClick={submitGrn} disabled={busy === 'grn' || !Object.values(grnRows).some(r => (parseFloat(r?.qty) || 0) > 0)} className="px-3 py-2 text-sm rounded-md bg-[var(--color-success-alt)] text-white disabled:opacity-50" data-testid="fulfilment-grn-submit">{busy === 'grn' ? <Loader2 size={13} className="animate-spin" /> : 'Receive & register'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default QuoteFulfilmentPanel;
