import { useCallback, useEffect, useState } from 'react';
import { Rocket, ScanLine, CheckCircle2, XCircle, Package, Truck, ShieldCheck, AlertTriangle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { notify } from '@/components/notifications';
import { invApi, fmtDate, statusLabel } from './api';
import { Card, Spinner, StatusBadge, Btn, Field, inputCls } from './ui';

const QC_RESULTS = [
  { v: 'pass', label: 'Pass' }, { v: 'pass_note', label: 'Pass with note' },
  { v: 'rework', label: 'Rework required' }, { v: 'quarantine', label: 'Quarantine' }, { v: 'failed', label: 'Failed' },
];

function ScanInput({ placeholder, onScan, testId, disabled }) {
  const [v, setV] = useState('');
  const submit = () => { if (v.trim()) { onScan(v.trim()); setV(''); } };
  return (
    <div className="flex items-center gap-2">
      <div className="relative flex-1">
        <ScanLine size={16} className="absolute left-2.5 top-2.5 text-[#0B3D91]" />
        <input className={`${inputCls} pl-8`} placeholder={placeholder} value={v} data-testid={testId} disabled={disabled}
          onChange={(e) => setV(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && submit()} />
      </div>
      <Btn variant="secondary" onClick={submit} disabled={disabled || !v.trim()} data-testid={`${testId}-go`}>Scan</Btn>
    </div>
  );
}

// Step wrapper
function Step({ n, title, done, active, children }) {
  return (
    <Card className={`p-4 ${active ? 'ring-2 ring-[#0B3D91]/30' : ''}`} testId={`inv-ful-step-${n}`}>
      <div className="mb-3 flex items-center gap-2">
        <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${done ? 'bg-emerald-500 text-white' : active ? 'bg-[#0B3D91] text-white' : 'bg-slate-200 text-slate-500'}`}>{done ? '✓' : n}</span>
        <h3 className="text-sm font-bold text-slate-900">{title}</h3>
      </div>
      {children}
    </Card>
  );
}

export default function OrderFulfilment({ orderId }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState('');
  const [qcTpl, setQcTpl] = useState(null);
  const [dispatch, setDispatch] = useState({ carrier: '', tracking: '' });

  const load = useCallback(() => { invApi.fulfilment(orderId).then(setData).catch(() => notify.error('Could not load fulfilment')); }, [orderId]);
  useEffect(() => { load(); invApi.qcTemplates().then((d) => setQcTpl(d.templates?.[0] || null)).catch(() => {}); }, [load]);

  if (!data) return <Spinner />;
  const { order, pick_tasks: tasks, units, qc, packages, shipment } = data;

  const released = tasks.length > 0;
  const allPicked = released && tasks.every((t) => t.status === 'picked');
  const pickedUnits = units.filter((u) => ['picked', 'quality_checked', 'packed', 'dispatched'].includes(u.status));
  const openPackages = packages.filter((p) => p.status !== 'sealed' && p.status !== 'dispatched');
  const sealedPackages = packages.filter((p) => ['sealed', 'dispatched'].includes(p.status));
  const dispatched = !!shipment;

  const act = async (fn, key) => { setBusy(key); try { await fn(); load(); } catch (e) {
    const d = e?.response?.data?.detail; notify.error(typeof d === 'object' ? d.message : (d || 'Action failed'));
  } finally { setBusy(''); } };

  const doPick = async (task, serial) => {
    try { await invApi.pick(task.id, task.kind === 'serialised' ? { serial } : { qty: task.required_qty }); notify.success('Picked'); load(); }
    catch (e) { const d = e?.response?.data?.detail; notify.error(typeof d === 'object' ? d.message : (d || 'Pick rejected')); }
  };
  const doQc = async (unitId, result) => act(() => invApi.qcUnit(unitId, { template_id: qcTpl?.id, result }), 'qc');
  const addScan = async (pkgId, serial) => {
    try { const r = await invApi.addToPackage(pkgId, { serial }); notify.success(`Packed ${r.serial || ''}`); load(); }
    catch (e) { const d = e?.response?.data?.detail; notify.error(typeof d === 'object' ? d.message : (d || 'Cannot pack')); }
  };

  return (
    <div className="space-y-4" data-testid="inv-fulfilment">
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <span className="font-semibold text-slate-700">Warehouse fulfilment</span>
        <StatusBadge status={order.status} />
      </div>

      {/* Step 1 — Release */}
      <Step n={1} title="Release to warehouse" done={released} active={!released}>
        {!released ? (
          <Btn onClick={() => act(() => invApi.release(orderId), 'release')} disabled={!!busy} data-testid="inv-ful-release"><Rocket size={15} /> {busy === 'release' ? 'Releasing…' : 'Release & generate pick tasks'}</Btn>
        ) : <p className="text-sm text-slate-500">{tasks.length} pick task(s) generated.</p>}
      </Step>

      {/* Step 2 — Picking */}
      {released && (
        <Step n={2} title="Picking (scan exact serial)" done={allPicked} active={!allPicked}>
          <div className="space-y-2">
            {tasks.map((t) => (
              <div key={t.id} className="flex items-center gap-3 rounded-lg border border-slate-200 p-2" data-testid={`inv-ful-task-${t.id}`}>
                <span className="w-28 truncate text-sm font-mono text-slate-600">{t.product_code}</span>
                {t.serial_number && <span className="text-xs text-slate-400">{t.serial_number}</span>}
                {t.status === 'picked' ? (
                  <span className="ml-auto flex items-center gap-1 text-sm font-semibold text-emerald-600"><CheckCircle2 size={15} /> Picked</span>
                ) : (
                  <div className="ml-auto w-64">
                    {t.kind === 'serialised'
                      ? <ScanInput placeholder="Scan serial to pick" testId={`inv-ful-pick-${t.id}`} onScan={(s) => doPick(t, s)} disabled={!!busy} />
                      : <Btn variant="secondary" onClick={() => doPick(t)} data-testid={`inv-ful-pick-${t.id}`}>Pick ×{t.required_qty}</Btn>}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Step>
      )}

      {/* Step 3 — QC */}
      {pickedUnits.length > 0 && (
        <Step n={3} title="Quality control" done={pickedUnits.every((u) => ['quality_checked', 'packed', 'dispatched'].includes(u.status) || u.quarantined)} active>
          <p className="mb-2 text-[11px] text-slate-400">{qcTpl ? qcTpl.name : 'Standard machine QC'} — failed / quarantined units cannot be packed.</p>
          <div className="space-y-2">
            {pickedUnits.map((u) => (
              <div key={u.id} className="flex items-center gap-3 rounded-lg border border-slate-200 p-2" data-testid={`inv-ful-qc-${u.id}`}>
                <span className="text-sm font-semibold text-slate-700">{u.serial_number}</span>
                {u.qc_result ? (
                  <span className={`ml-auto flex items-center gap-1 text-sm font-semibold ${u.quarantined ? 'text-rose-600' : 'text-emerald-600'}`}>
                    {u.quarantined ? <AlertTriangle size={15} /> : <ShieldCheck size={15} />} {statusLabel(u.qc_result)}
                  </span>
                ) : (
                  <div className="ml-auto flex flex-wrap gap-1">
                    {QC_RESULTS.map((r) => (
                      <button key={r.v} className={`rounded px-2 py-1 text-xs font-semibold ${r.v === 'pass' ? 'bg-emerald-100 text-emerald-700' : r.v === 'quarantine' || r.v === 'failed' ? 'bg-rose-100 text-rose-700' : 'bg-slate-100 text-slate-600'}`} data-testid={`inv-ful-qc-${u.id}-${r.v}`} onClick={() => doQc(u.id, r.v)} disabled={!!busy}>{r.label}</button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Step>
      )}

      {/* Step 4 — Packing */}
      {pickedUnits.length > 0 && (
        <Step n={4} title="Packing" done={sealedPackages.length > 0 && openPackages.length === 0} active>
          <Btn variant="secondary" className="mb-3" onClick={() => act(() => invApi.createPackage(orderId, { type: 'pallet' }), 'pkg')} disabled={!!busy} data-testid="inv-ful-new-package"><Package size={15} /> New package</Btn>
          <div className="space-y-3">
            {packages.map((p) => (
              <div key={p.id} className="rounded-lg border border-slate-200 p-3" data-testid={`inv-ful-package-${p.package_number}`}>
                <div className="mb-2 flex items-center gap-2">
                  <span className="font-mono text-sm font-semibold">{p.package_number}</span>
                  <StatusBadge status={p.status} />
                  <span className="ml-auto text-xs text-slate-400">{(p.unit_ids || []).length} unit(s)</span>
                </div>
                {p.status !== 'sealed' && p.status !== 'dispatched' ? (
                  <div className="space-y-2">
                    <ScanInput placeholder="Scan serial into package" testId={`inv-ful-pack-${p.id}`} onScan={(s) => addScan(p.id, s)} disabled={!!busy} />
                    <Btn variant="secondary" onClick={() => act(() => invApi.sealPackage(p.id, { weight: 100 }), 'seal')} disabled={!!busy || (p.unit_ids || []).length === 0} data-testid={`inv-ful-seal-${p.id}`}>Seal package</Btn>
                  </div>
                ) : (
                  <span className="text-xs text-emerald-600">Sealed{p.weight ? ` · ${p.weight}kg` : ''}</span>
                )}
              </div>
            ))}
          </div>
        </Step>
      )}

      {/* Step 5 — Dispatch */}
      {sealedPackages.length > 0 && (
        <Step n={5} title="Dispatch" done={dispatched} active={!dispatched}>
          {dispatched ? (
            <div className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800" data-testid="inv-ful-shipment">
              <p className="font-semibold">{shipment.reference} · {shipment.carrier}</p>
              <p className="text-xs">Tracking {shipment.tracking || '—'} · {(shipment.package_ids || []).length} package(s) · In transit since {fmtDate(shipment.dispatched_at)}</p>
            </div>
          ) : (
            <div className="flex flex-wrap items-end gap-2">
              <div className="w-40"><Field label="Carrier"><input className={inputCls} value={dispatch.carrier} data-testid="inv-ful-carrier" onChange={(e) => setDispatch((d) => ({ ...d, carrier: e.target.value }))} /></Field></div>
              <div className="w-40"><Field label="Tracking"><input className={inputCls} value={dispatch.tracking} data-testid="inv-ful-tracking" onChange={(e) => setDispatch((d) => ({ ...d, tracking: e.target.value }))} /></Field></div>
              <Btn onClick={() => act(() => invApi.dispatch(orderId, dispatch), 'dispatch')} disabled={!!busy || !dispatch.carrier.trim()} data-testid="inv-ful-dispatch"><Truck size={15} /> {busy === 'dispatch' ? 'Dispatching…' : 'Dispatch shipment'}</Btn>
            </div>
          )}
        </Step>
      )}
    </div>
  );
}

// Cross-order warehouse queue (used by Receiving/Picking/QC/Packing/Dispatch nav sections)
export function WarehouseQueue({ stage, title }) {
  const [rows, setRows] = useState(null);
  const navigate = useNavigate();
  useEffect(() => { invApi.queue(stage).then((d) => setRows(d.orders || [])).catch(() => setRows([])); }, [stage]);
  return (
    <div className="space-y-4" data-testid={`inv-queue-${stage}`}>
      <h2 className="text-xl font-bold text-slate-900">{title}</h2>
      {rows === null ? <Spinner /> : rows.length === 0 ? (
        <Card className="p-10 text-center text-slate-400" testId={`inv-queue-${stage}-empty`}>Nothing in this queue right now.</Card>
      ) : (
        <Card testId={`inv-queue-${stage}-table`}>
          <table className="w-full text-sm">
            <thead><tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400"><th className="px-4 py-3">Reference</th><th>Dealer</th><th>Country</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {rows.map((o) => (
                <tr key={o.id} className="border-b border-slate-100 hover:bg-slate-50" data-testid={`inv-queue-row-${o.reference}`}>
                  <td className="px-4 py-3 font-semibold text-[#0B3D91]">{o.reference}</td>
                  <td>{o.dealer_name}</td>
                  <td>{o.dealer_country}</td>
                  <td><StatusBadge status={o.status} /></td>
                  <td className="text-right pr-4"><Btn variant="secondary" onClick={() => navigate(`/service-desk/inventory?s=orders&order=${o.id}`)} data-testid={`inv-queue-open-${o.reference}`}>Open</Btn></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
