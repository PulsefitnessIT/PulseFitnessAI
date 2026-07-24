import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, Truck, FileText, PackageCheck, ScanLine, AlertTriangle, Plus, ArrowRightLeft, CheckCircle2 } from 'lucide-react';
import { notify } from '@/components/notifications';
import { invApi, fmtDate, statusLabel, money } from './api';
import { Card, Spinner, StatusBadge, Btn, Field, inputCls } from './ui';

const SHIP_STATUSES = ['booked', 'collected', 'in_transit', 'customs_hold', 'customs_cleared', 'out_for_delivery', 'delivered', 'delivery_discrepancy', 'returned', 'cancelled'];
const DOC_TYPES = [['packing_list', 'inv.ship.doc_packing_list', 'Packing List'], ['delivery_note', 'inv.ship.doc_delivery_note', 'Delivery Note'], ['commercial_invoice_support', 'inv.ship.doc_commercial', 'Commercial Invoice Support'], ['export_packing_list', 'inv.ship.doc_export_packing', 'Export Packing List']];
const CUSTOMS_FIELDS = [['incoterm', 'inv.ship.incoterm', 'Incoterm'], ['hs_code', 'inv.ship.hs_code', 'HS / commodity code'], ['country_of_origin', 'inv.ship.origin', 'Country of origin'], ['export_reason', 'inv.ship.export_reason', 'Export reason'], ['declared_value', 'inv.ship.declared_value', 'Declared value'], ['currency', 'inv.ship.currency', 'Currency'], ['gross_weight', 'inv.ship.gross_weight', 'Gross weight (kg)'], ['eori', 'inv.ship.eori', 'EORI']];

// ───────────── Shipment detail (tracking, customs, docs, dealer receipt) ─────────────
function ShipmentDetail({ shipmentId, onBack }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState('');
  const [customs, setCustoms] = useState({});
  const [receipt, setReceipt] = useState({ confirmed: {}, damaged: {} });

  const load = useCallback(() => { invApi.shipment(shipmentId).then((d) => { setData(d); setCustoms(d.shipment.customs || {}); }).catch(() => notify.error(t('inv.common.load_failed', 'Load failed'))); }, [shipmentId]);
  useEffect(() => { load(); }, [load]);
  if (!data) return <Spinner />;
  const { shipment: sh, packages, units, receipt: existingReceipt, documents } = data;

  const act = async (fn, key) => { setBusy(key); try { await fn(); load(); } catch (e) { const d = e?.response?.data?.detail; notify.error(typeof d === 'object' ? d.message : (d || t('inv.common.failed', 'Failed'))); } finally { setBusy(''); } };

  const doReceive = async () => {
    const confirmed_serials = units.filter((u) => receipt.confirmed[u.id]).map((u) => u.serial_number);
    const damaged_serials = units.filter((u) => receipt.damaged[u.id]).map((u) => u.serial_number);
    if (!confirmed_serials.length && !damaged_serials.length) { notify.error(t('inv.ship.mark_one', 'Mark at least one unit')); return; }
    setBusy('receive');
    try {
      const r = await invApi.dealerReceive(shipmentId, { confirmed_serials, damaged_serials });
      notify.success(`Receipt ${statusLabel(r.receipt_status)} — ${r.confirmed} confirmed, ${r.damaged} damaged`);
      load();
    } catch (e) { const d = e?.response?.data?.detail; notify.error(typeof d === 'object' ? d.message : t('inv.common.failed', 'Failed')); } finally { setBusy(''); }
  };

  return (
    <div className="space-y-5" data-testid="inv-shipment-detail">
      <div className="flex items-center gap-3">
        <Btn variant="ghost" onClick={onBack} data-testid="inv-shipment-back"><ArrowLeft size={16} /> {t('inv.ship.title', 'Shipments')}</Btn>
        <div><h2 className="text-xl font-bold text-slate-900">{sh.reference}</h2><p className="text-sm text-slate-500">{sh.dealer_name} · {sh.dealer_country} · {sh.carrier}</p></div>
        <StatusBadge status={sh.status} className="ml-2" />
      </div>

      {/* Tracking */}
      <Card className="p-4" testId="inv-ship-tracking">
        <h3 className="mb-3 text-sm font-bold text-slate-900">{t('inv.ship.tracking', 'Tracking')}</h3>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="text-slate-500">{t('inv.ship.tracking', 'Tracking')}: <span className="font-semibold text-slate-800">{sh.tracking || '—'}</span></span>
          <span className="text-slate-500">{t('inv.ship.destination', 'Destination:')} {sh.destination || '—'}</span>
          <select className={inputCls + ' ml-auto w-auto'} value={sh.status} data-testid="inv-ship-status" onChange={(e) => act(() => invApi.shipmentStatus(shipmentId, { status: e.target.value }), 'status')}>
            {SHIP_STATUSES.map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}
          </select>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* Customs / international */}
        <Card className="p-4" testId="inv-ship-customs">
          <h3 className="mb-3 text-sm font-bold text-slate-900">{t('inv.ship.customs', 'International / customs')}</h3>
          <div className="grid grid-cols-2 gap-3">
            {CUSTOMS_FIELDS.map(([k, lk, def]) => (
              <Field key={k} label={t(lk, def)}><input className={inputCls} value={customs[k] || ''} data-testid={`inv-customs-${k}`} onChange={(e) => setCustoms((c) => ({ ...c, [k]: e.target.value }))} /></Field>
            ))}
          </div>
          <Btn className="mt-3" onClick={() => act(() => invApi.setCustoms(shipmentId, customs), 'customs')} disabled={!!busy} data-testid="inv-customs-save">{t('inv.ship.save_customs', 'Save customs data')}</Btn>
          <p className="mt-2 text-[11px] text-slate-400">{t('inv.ship.customs_note', 'Pulse never invents customs classifications — values require human review.')}</p>
        </Card>

        {/* Documents */}
        <Card className="p-4" testId="inv-ship-documents">
          <h3 className="mb-3 text-sm font-bold text-slate-900">{t('inv.ship.paperwork', 'Paperwork (versioned)')}</h3>
          <div className="flex flex-wrap gap-2">
            {DOC_TYPES.map(([dt, lk, def]) => (
              <Btn key={dt} variant="secondary" onClick={() => act(() => invApi.genDocument(shipmentId, { type: dt }), 'doc')} disabled={!!busy} data-testid={`inv-gen-doc-${dt}`}><FileText size={14} /> {t(lk, def)}</Btn>
            ))}
          </div>
          <div className="mt-3 space-y-1">
            {(documents || []).length === 0 ? <p className="text-sm text-slate-400">{t('inv.ship.no_docs', 'No documents generated.')}</p> : documents.map((d) => (
              <div key={d.id} className="flex items-center gap-2 border-b border-slate-100 py-1.5 text-sm last:border-0" data-testid={`inv-doc-${d.reference}`}>
                <FileText size={14} className="text-[#0B3D91]" />
                <span className="font-semibold">{d.template}</span>
                <span className="text-xs text-slate-400">{d.reference} · {d.template_version} · rev {d.revision}</span>
                <span className="ml-auto text-xs text-slate-400">{fmtDate(d.created_at)}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Dealer receipt */}
      <Card className="p-4" testId="inv-ship-receipt">
        <h3 className="mb-1 text-sm font-bold text-slate-900">{t('inv.ship.receipt', 'Dealer receipt confirmation')}</h3>
        <p className="mb-3 text-[11px] text-slate-400">{t('inv.ship.receipt_note', 'Scan/confirm each serial the dealer received. Damaged units are flagged as a discrepancy. (The Dealer Portal calls this same action.)')}</p>
        {existingReceipt ? (
          <div className="rounded-lg bg-slate-50 p-3 text-sm" data-testid="inv-receipt-done">
            <StatusBadge status={existingReceipt.status} />
            <p className="mt-2 text-slate-600">{t('inv.ship.confirmed', 'Confirmed:')} {(existingReceipt.confirmed || []).join(', ') || '—'}</p>
            <p className="text-rose-600">{t('inv.ship.damaged', 'Damaged:')} {(existingReceipt.damaged || []).join(', ') || '—'}</p>
          </div>
        ) : (
          <>
            <div className="space-y-2">
              {units.map((u) => (
                <div key={u.id} className="flex items-center gap-3 rounded-lg border border-slate-200 p-2" data-testid={`inv-receipt-unit-${u.id}`}>
                  <span className="text-sm font-semibold text-slate-700"><ScanLine size={13} className="mr-1 inline text-[#0B3D91]" />{u.serial_number}</span>
                  <div className="ml-auto flex gap-2">
                    <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={!!receipt.confirmed[u.id]} data-testid={`inv-receipt-confirm-${u.id}`} onChange={(e) => setReceipt((r) => ({ ...r, confirmed: { ...r.confirmed, [u.id]: e.target.checked }, damaged: { ...r.damaged, [u.id]: false } }))} /> {t('inv.ship.received_lbl', 'Received')}</label>
                    <label className="flex items-center gap-1 text-xs text-rose-600"><input type="checkbox" checked={!!receipt.damaged[u.id]} data-testid={`inv-receipt-damage-${u.id}`} onChange={(e) => setReceipt((r) => ({ ...r, damaged: { ...r.damaged, [u.id]: e.target.checked }, confirmed: { ...r.confirmed, [u.id]: false } }))} /> {t('inv.ship.damaged_lbl', 'Damaged')}</label>
                  </div>
                </div>
              ))}
            </div>
            <Btn className="mt-3" onClick={doReceive} disabled={!!busy} data-testid="inv-receipt-submit"><PackageCheck size={15} /> {busy === 'receive' ? t('inv.ship.confirming', 'Confirming…') : t('inv.ship.confirm_receipt', 'Confirm dealer receipt')}</Btn>
          </>
        )}
      </Card>
    </div>
  );
}

// ───────────── Shipments list ─────────────
export function Shipments() {
  const { t } = useTranslation();
  const [rows, setRows] = useState(null);
  const [selected, setSelected] = useState(null);
  const load = useCallback(() => invApi.shipments().then((d) => setRows(d.shipments || [])).catch(() => setRows([])), []);
  useEffect(() => { load(); }, [load]);
  if (selected) return <ShipmentDetail shipmentId={selected} onBack={() => { setSelected(null); load(); }} />;
  return (
    <div className="space-y-4" data-testid="inv-shipments">
      <h2 className="text-xl font-bold text-slate-900">{t('inv.ship.title', 'Shipments')}</h2>
      {rows === null ? <Spinner /> : rows.length === 0 ? <Card className="p-10 text-center text-slate-400" testId="inv-shipments-empty">{t('inv.ship.empty', 'No shipments yet — dispatch an order to create one.')}</Card> : (
        <Card testId="inv-shipments-table">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400"><th className="px-4 py-3">{t('inv.th.reference', 'Reference')}</th><th>{t('inv.th.dealer', 'Dealer')}</th><th>{t('inv.th.country', 'Country')}</th><th>{t('inv.th.carrier', 'Carrier')}</th><th>{t('inv.th.tracking', 'Tracking')}</th><th>{t('inv.th.status', 'Status')}</th></tr></thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id} className="cursor-pointer border-b border-slate-100 hover:bg-slate-50" data-testid={`inv-shipment-row-${s.reference}`} onClick={() => setSelected(s.id)}>
                  <td className="px-4 py-3 font-semibold text-[#0B3D91]">{s.reference}</td>
                  <td>{s.dealer_name}</td><td>{s.dealer_country}</td><td>{s.carrier}</td><td className="text-slate-500">{s.tracking || '—'}</td>
                  <td><StatusBadge status={s.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

// ───────────── Dealer inventory ─────────────
export function DealerInventory() {
  const { t } = useTranslation();
  const [rows, setRows] = useState(null);
  useEffect(() => { invApi.dealerInventory().then((d) => setRows(d.holdings || [])).catch(() => setRows([])); }, []);
  return (
    <div className="space-y-4" data-testid="inv-dealer-inventory">
      <h2 className="text-xl font-bold text-slate-900">{t('inv.dealer_inv.title', 'Dealer Inventory')}</h2>
      <p className="text-sm text-slate-500">{t('inv.dealer_inv.subtitle', "Machines confirmed as received by dealers — the dealer's on-hand stock, ready to allocate to their customers.")}</p>
      {rows === null ? <Spinner /> : rows.length === 0 ? <Card className="p-10 text-center text-slate-400" testId="inv-dealer-inv-empty">{t('inv.dealer_inv.empty', 'No dealer-held stock yet.')}</Card> : (
        <Card testId="inv-dealer-inv-table">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400"><th className="px-4 py-3">{t('inv.th.serial', 'Serial')}</th><th>{t('inv.th.model', 'Model')}</th><th>{t('inv.th.dealer', 'Dealer')}</th><th>{t('inv.th.received', 'Received')}</th><th>{t('inv.th.status', 'Status')}</th></tr></thead>
            <tbody>
              {rows.map((h) => (
                <tr key={h.unit_id} className="border-b border-slate-100" data-testid={`inv-dealer-holding-${h.serial_number}`}>
                  <td className="px-4 py-3 font-mono text-xs font-semibold">{h.serial_number}</td>
                  <td>{h.model || h.product_code}</td><td>{h.dealer_name}</td><td className="text-slate-400">{fmtDate(h.received_date)}</td>
                  <td><StatusBadge status={h.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

// ───────────── Transfer orders ─────────────
export function TransferOrders({ warehouses }) {
  const { t } = useTranslation();
  const [rows, setRows] = useState(null);
  const [form, setForm] = useState({ source_warehouse_id: '', dest_warehouse_id: '' });
  const load = useCallback(() => invApi.transfers().then((d) => setRows(d.transfers || [])).catch(() => setRows([])), []);
  useEffect(() => { load(); }, [load]);
  const create = async () => {
    if (!form.source_warehouse_id || !form.dest_warehouse_id) { notify.error(t('inv.transfers.pick_route', 'Pick source + destination')); return; }
    try { await invApi.createTransfer({ ...form, unit_ids: [] }); notify.success(t('inv.transfers.created', 'Transfer created')); load(); } catch (e) { notify.error(e?.response?.data?.detail || t('inv.common.failed', 'Failed')); }
  };
  const step = async (id, action) => { try { await invApi.transferAction(id, action); load(); } catch (e) { notify.error(t('inv.common.failed', 'Failed')); } };
  const whName = (id) => warehouses.find((w) => w.id === id)?.name || id;
  const NEXT = { awaiting_approval: 'approve', approved: 'dispatch', in_transit: 'receive' };
  return (
    <div className="space-y-4" data-testid="inv-transfers">
      <h2 className="text-xl font-bold text-slate-900">{t('inv.transfers.title', 'Transfer Orders')}</h2>
      <Card className="p-4" testId="inv-transfer-create">
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[180px]"><Field label={t('inv.transfers.source', 'Source warehouse')}><select className={inputCls} value={form.source_warehouse_id} data-testid="inv-transfer-source" onChange={(e) => setForm((f) => ({ ...f, source_warehouse_id: e.target.value }))}><option value="">—</option>{warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</select></Field></div>
          <div className="min-w-[180px]"><Field label={t('inv.transfers.dest', 'Destination warehouse')}><select className={inputCls} value={form.dest_warehouse_id} data-testid="inv-transfer-dest" onChange={(e) => setForm((f) => ({ ...f, dest_warehouse_id: e.target.value }))}><option value="">—</option>{warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</select></Field></div>
          <Btn onClick={create} data-testid="inv-transfer-submit"><Plus size={15} /> {t('inv.transfers.create', 'Create transfer')}</Btn>
        </div>
      </Card>
      {rows === null ? <Spinner /> : rows.length === 0 ? <Card className="p-8 text-center text-slate-400" testId="inv-transfers-empty">{t('inv.transfers.empty', 'No transfers yet.')}</Card> : (
        <Card testId="inv-transfers-table">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400"><th className="px-4 py-3">{t('inv.th.ref', 'Ref')}</th><th>{t('inv.th.route', 'Route')}</th><th>{t('inv.th.status', 'Status')}</th><th></th></tr></thead>
            <tbody>
              {rows.map((tr) => (
                <tr key={tr.id} className="border-b border-slate-100" data-testid={`inv-transfer-row-${tr.reference}`}>
                  <td className="px-4 py-3 font-semibold text-[#0B3D91]">{tr.reference}</td>
                  <td className="text-slate-600"><ArrowRightLeft size={12} className="mr-1 inline" />{whName(tr.source_warehouse_id)} → {whName(tr.dest_warehouse_id)}</td>
                  <td><StatusBadge status={tr.status} /></td>
                  <td className="pr-4 text-right">{NEXT[tr.status] && <Btn variant="secondary" onClick={() => step(tr.id, NEXT[tr.status])} data-testid={`inv-transfer-action-${tr.reference}`}>{statusLabel(NEXT[tr.status])}</Btn>}{tr.status === 'received' && <span className="text-emerald-600"><CheckCircle2 size={16} className="inline" /></span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
