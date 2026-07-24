import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { RefreshCw, Play, AlertTriangle, Link2, CheckCircle2, Activity } from 'lucide-react';
import { notify } from '@/components/notifications';
import { invApi, fmtDate, statusLabel } from './api';
import { Card, StatCard, Spinner, StatusBadge, Btn, Field, inputCls } from './ui';

const HEALTH_TONE = { healthy: 'green', delayed: 'amber', warning: 'amber', failed: 'red', authentication_required: 'red', reconciliation_required: 'amber' };

function HealthPill({ health }) {
  const tone = HEALTH_TONE[health] || 'slate';
  const styles = { green: 'bg-emerald-100 text-emerald-800', amber: 'bg-amber-100 text-amber-800', red: 'bg-rose-100 text-rose-800', slate: 'bg-slate-100 text-slate-700' };
  return <span className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-bold ${styles[tone]}`} data-testid="inv-sync-health"><Activity size={12} /> {statusLabel(health)}</span>;
}

// ─────────────────────────── Sage Orders (sync console) ───────────────────────────
export function SageOrders() {
  const { t } = useTranslation();
  const [status, setStatus] = useState(null);
  const [orders, setOrders] = useState(null);
  const [runs, setRuns] = useState([]);
  const [busy, setBusy] = useState('');

  const load = useCallback(() => {
    invApi.syncStatus().then(setStatus).catch(() => {});
    invApi.sageOrders().then((d) => setOrders(d.orders || [])).catch(() => setOrders([]));
    invApi.syncRuns().then((d) => setRuns(d.runs || [])).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  const run = async (simulate) => {
    setBusy(simulate ? 'sim' : 'live');
    try {
      const res = await invApi.runSync({ simulate });
      if (res.run) {
        const r = res.run;
        notify.success(`Sync complete — imported ${r.imported}, updated ${r.updated}, skipped ${r.skipped}, needs mapping ${r.needs_mapping}`);
      } else {
        notify.info(res.message || 'Sage not connected');
      }
      load();
    } catch (e) { notify.error(t('inv.sync.failed', 'Sync failed')); } finally { setBusy(''); }
  };

  return (
    <div className="space-y-5" data-testid="inv-sage-orders">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-bold text-slate-900">{t('inv.sync.title', 'Sage Orders')}</h2>
        {status && <HealthPill health={status.health} />}
        <div className="ml-auto flex gap-2">
          <Btn variant="secondary" onClick={() => run(false)} disabled={!!busy} data-testid="inv-sync-run"><RefreshCw size={15} /> {busy === 'live' ? t('inv.sync.syncing', 'Syncing…') : t('inv.sync.run', 'Run sync')}</Btn>
          <Btn onClick={() => run(true)} disabled={!!busy} data-testid="inv-sync-simulate"><Play size={15} /> {busy === 'sim' ? t('inv.sync.simulating', 'Simulating…') : t('inv.sync.simulate', 'Simulate Sage feed')}</Btn>
        </div>
      </div>

      {!status ? <Spinner /> : (
        <>
          {!status.connected && (
            <div className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-800">
              {t('inv.sync.not_connected', 'Sage 200 is not connected yet — orders are imported manually or via Simulate Sage feed, which exercises the exact same idempotent pipeline. The moment Sage credentials are configured, live sync uses the same engine.')}
            </div>
          )}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard label={t('inv.sync.sage_orders', 'Sage orders')} value={status.total_orders} testId="inv-sync-total" />
            <StatCard label={t('inv.sync.needs_mapping', 'Needs mapping')} value={status.needs_mapping} tone="amber" testId="inv-sync-needs-mapping" />
            <StatCard label={t('inv.sync.open_errors', 'Open errors')} value={status.open_errors} tone={status.open_errors ? 'red' : 'green'} testId="inv-sync-errors" />
            <StatCard label={t('inv.sync.last_run', 'Last run')} value={status.last_run ? statusLabel(status.last_run.trigger) : '—'} tone="slate" />
          </div>

          {status.last_run && (
            <Card className="p-4" testId="inv-last-run">
              <h3 className="mb-2 text-sm font-bold text-slate-900">{t('inv.sync.last_run_title', 'Last sync run')}</h3>
              <div className="flex flex-wrap gap-4 text-sm">
                {['imported', 'updated', 'skipped', 'duplicates_prevented', 'needs_mapping', 'failures'].map((k) => (
                  <div key={k}><span className="text-slate-400">{statusLabel(k)}: </span><span className="font-bold tabular-nums">{status.last_run[k] ?? 0}</span></div>
                ))}
                <div className="ml-auto text-slate-400">{fmtDate(status.last_run.finished_at)}</div>
              </div>
            </Card>
          )}
        </>
      )}

      <Card testId="inv-sage-orders-table">
        <div className="border-b border-slate-200 px-4 py-3"><h3 className="text-sm font-bold text-slate-900">{t('inv.sync.imported_orders', 'Imported Sage orders')}</h3></div>
        {orders === null ? <Spinner /> : orders.length === 0 ? <p className="px-4 py-8 text-center text-sm text-slate-400">{t('inv.sync.no_orders', 'No Sage orders yet. Click “Simulate Sage feed” to import a sample feed.')}</p> : (
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs uppercase text-slate-400"><th className="px-4 py-2">{t('inv.th.sage_no', 'Sage no.')}</th><th>{t('inv.th.account', 'Account')}</th><th>{t('inv.th.dealer', 'Dealer')}</th><th>{t('inv.th.country', 'Country')}</th><th>{t('inv.th.currency', 'Currency')}</th><th>{t('inv.th.sync_state', 'Sync state')}</th><th>{t('inv.th.synced', 'Synced')}</th></tr></thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id} className="border-t border-slate-100" data-testid={`inv-sage-order-${o.sage_order_number}`}>
                  <td className="px-4 py-2.5 font-semibold text-[#0B3D91]">{o.sage_order_number}</td>
                  <td className="font-mono text-xs">{o.sage_customer_account}</td>
                  <td>{o.dealer_name}</td>
                  <td>{o.dealer_country}</td>
                  <td>{o.currency}</td>
                  <td><StatusBadge status={o.sync_state} /></td>
                  <td className="text-slate-400">{fmtDate(o.last_synced_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {runs.length > 0 && (
        <Card className="p-4" testId="inv-sync-runs">
          <h3 className="mb-2 text-sm font-bold text-slate-900">{t('inv.sync.recent_runs', 'Recent runs')}</h3>
          {runs.slice(0, 8).map((r) => (
            <div key={r.id} className="flex flex-wrap items-center gap-3 border-b border-slate-100 py-1.5 text-xs last:border-0">
              <span className="font-semibold">{statusLabel(r.trigger)}</span>
              <span className="text-slate-500">imported {r.imported} · updated {r.updated} · skipped {r.skipped} · needs-map {r.needs_mapping} · fail {r.failures}</span>
              <span className="ml-auto text-slate-400">{fmtDate(r.started_at)}</span>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}

// ─────────────────────────── Order Exceptions (mapping) ───────────────────────────
function DealerMapRow({ ex, onDone }) {
  const { t } = useTranslation();
  const [q, setQ] = useState(ex.dealer_name || '');
  const [results, setResults] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (q.length < 2) { setResults([]); return; } const tmr = setTimeout(() => invApi.dealers(q).then((d) => setResults(d.dealers || [])).catch(() => {}), 250); return () => clearTimeout(tmr); }, [q]);

  const pick = async (companyId) => {
    setBusy(true);
    try { await invApi.mapDealer({ sage_account: ex.sage_account, crm_company_id: companyId }); notify.success(t('inv.ex.dealer_mapped', 'Dealer mapped')); onDone(); }
    catch (e) { notify.error(t('inv.common.failed', 'Failed')); } finally { setBusy(false); }
  };

  return (
    <div className="relative border-b border-slate-100 py-2.5 last:border-0" data-testid={`inv-ex-dealer-${ex.sage_account}`}>
      <div className="flex items-center gap-3">
        <span className="font-mono text-xs text-slate-500">{ex.sage_account}</span>
        <span className="text-sm font-semibold text-slate-800">{ex.dealer_name}</span>
        <div className="relative ml-auto w-64">
          <input className={inputCls} placeholder={t('inv.ex.link_crm', 'Link to CRM company…')} value={q} data-testid={`inv-ex-dealer-input-${ex.sage_account}`} onChange={(e) => setQ(e.target.value)} disabled={busy} />
          {results.length > 0 && (
            <div className="absolute right-0 z-10 mt-1 w-full rounded-lg border border-slate-200 bg-white shadow-lg">
              {results.map((c) => <button key={c.id} className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50" data-testid={`inv-ex-dealer-opt-${c.id}`} onClick={() => pick(c.id)}>{c.name}</button>)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ProductMapRow({ ex, onDone }) {
  const { t } = useTranslation();
  const [code, setCode] = useState(ex.sage_stock_code || '');
  const map = async () => { try { await invApi.mapProduct({ sage_stock_code: ex.sage_stock_code, product_code: code }); notify.success(t('inv.ex.product_mapped', 'Product mapped')); onDone(); } catch (e) { notify.error(t('inv.common.failed', 'Failed')); } };
  return (
    <div className="flex items-center gap-3 border-b border-slate-100 py-2.5 last:border-0" data-testid={`inv-ex-product-${ex.sage_stock_code}`}>
      <span className="font-mono text-xs text-slate-500">{ex.sage_stock_code}</span>
      <span className="text-sm text-slate-700">{ex.description}</span>
      <div className="ml-auto flex items-center gap-2">
        <input className={inputCls + ' w-40'} value={code} data-testid={`inv-ex-product-input-${ex.sage_stock_code}`} onChange={(e) => setCode(e.target.value)} />
        <Btn variant="secondary" onClick={map} data-testid={`inv-ex-product-map-${ex.sage_stock_code}`}><Link2 size={14} /> {t('inv.ex.map', 'Map')}</Btn>
      </div>
    </div>
  );
}

export function OrderExceptions() {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState('');

  const load = useCallback(() => { invApi.sageExceptions().then(setData).catch(() => setData({ unmapped_dealers: [], unmapped_products: [], errors: [] })); }, []);
  useEffect(() => { load(); }, [load]);

  const retryAll = async () => {
    setBusy('retry');
    try {
      const d = await invApi.sageOrders('needs_mapping');
      for (const o of (d.orders || [])) { await invApi.retrySageOrder(o.id).catch(() => {}); }
      notify.success(t('inv.ex.retried', 'Retried mapped orders'));
      load();
    } catch (e) { notify.error(t('inv.common.failed', 'Failed')); } finally { setBusy(''); }
  };

  if (!data) return <Spinner />;
  const clean = data.unmapped_dealers.length === 0 && data.unmapped_products.length === 0 && data.errors.length === 0;

  return (
    <div className="space-y-5" data-testid="inv-exceptions">
      <div className="flex items-center gap-3">
        <h2 className="text-xl font-bold text-slate-900">{t('inv.ex.title', 'Order Exceptions')}</h2>
        <Btn variant="secondary" className="ml-auto" onClick={retryAll} disabled={!!busy} data-testid="inv-ex-retry-all"><RefreshCw size={15} /> {busy === 'retry' ? t('inv.ex.retrying', 'Retrying…') : t('inv.ex.retry', 'Retry mapped orders')}</Btn>
      </div>

      {clean ? (
        <Card className="p-10 text-center" testId="inv-ex-clean">
          <CheckCircle2 size={36} className="mx-auto mb-2 text-emerald-500" />
          <p className="text-slate-600">{t('inv.ex.clean', 'No exceptions — all imported Sage orders are mapped and clean.')}</p>
        </Card>
      ) : (
        <>
          {data.unmapped_dealers.length > 0 && (
            <Card className="p-4" testId="inv-ex-dealers">
              <h3 className="mb-2 flex items-center gap-2 text-sm font-bold text-slate-900"><AlertTriangle size={15} className="text-amber-500" /> {t('inv.ex.unmapped_dealers', 'Unmapped dealers')} ({data.unmapped_dealers.length})</h3>
              <p className="mb-2 text-xs text-slate-400">{t('inv.ex.unmapped_dealers_note', 'Link each Sage account to an existing CRM company — no duplicate dealer records are created.')}</p>
              {data.unmapped_dealers.map((ex) => <DealerMapRow key={ex.sage_account} ex={ex} onDone={load} />)}
            </Card>
          )}
          {data.unmapped_products.length > 0 && (
            <Card className="p-4" testId="inv-ex-products">
              <h3 className="mb-2 flex items-center gap-2 text-sm font-bold text-slate-900"><AlertTriangle size={15} className="text-amber-500" /> {t('inv.ex.unmapped_products', 'Unmapped products')} ({data.unmapped_products.length})</h3>
              {data.unmapped_products.map((ex) => <ProductMapRow key={ex.sage_stock_code} ex={ex} onDone={load} />)}
            </Card>
          )}
          {data.errors.length > 0 && (
            <Card className="p-4" testId="inv-ex-errors">
              <h3 className="mb-2 text-sm font-bold text-slate-900">{t('inv.ex.sync_errors', 'Sync errors')} ({data.errors.length})</h3>
              {data.errors.map((e) => (
                <div key={e.id} className="border-b border-slate-100 py-1.5 text-sm last:border-0"><span className="font-mono text-xs text-slate-500">{e.sage_order_id}</span> <span className="text-slate-600">{e.message}</span></div>
              ))}
            </Card>
          )}
        </>
      )}
    </div>
  );
}
