import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Radar, ShieldAlert, Activity, CheckCircle2, XCircle,
  FileBarChart, PackagePlus, RefreshCw, Info, Eye, UserCheck,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { invApi, statusLabel, fmtDate } from './api';
import { Card, StatCard, Spinner, Btn } from './ui';

const SEV_STYLE = {
  critical: { dot: 'bg-rose-500', chip: 'bg-rose-100 text-rose-700', tone: 'red' },
  warning: { dot: 'bg-amber-500', chip: 'bg-amber-100 text-amber-800', tone: 'amber' },
  monitor: { dot: 'bg-blue-500', chip: 'bg-blue-100 text-blue-700', tone: 'navy' },
  information: { dot: 'bg-slate-400', chip: 'bg-slate-100 text-slate-600', tone: 'slate' },
};

const SEVERITIES = ['critical', 'warning', 'monitor', 'information'];
const STATUSES = ['new', 'assigned', 'under_review', 'resolved', 'dismissed'];

// ─────────────────────────── Monitoring Dashboard ───────────────────────────
export function IntelDashboard({ go }) {
  const { t } = useTranslation();
  const [ov, setOv] = useState(null);
  const [scanning, setScanning] = useState(false);
  const load = useCallback(() => invApi.intelOverview().then(setOv).catch(() => notify.error(t('inv.intel.load_error', 'Could not load overview'))), [t]);
  useEffect(() => { load(); }, [load]);

  const runScan = async () => {
    setScanning(true);
    try { const r = await invApi.intelScan(); notify.success(t('inv.intel.scan_complete', 'Scan complete — {{alerts}} alert(s) from {{agents}} agents', { alerts: r.alerts_raised, agents: r.agents_run })); load(); }
    catch (e) { notify.error(t('inv.intel.scan_failed', 'Scan failed')); } finally { setScanning(false); }
  };

  if (!ov) return <Spinner />;
  const c = ov.alert_counts || {};
  const AGENTS = [
    ['inv.intel.agent_serial', 'Serial & Asset Integrity'], ['inv.intel.agent_order', 'Order Exception'],
    ['inv.intel.agent_risk', 'Inventory Risk'], ['inv.intel.agent_alloc', 'Dealer Allocation'],
    ['inv.intel.agent_sage', 'Sage Integration Health'], ['inv.intel.agent_doc', 'Document Compliance'],
    ['inv.intel.agent_replen', 'Replenishment'],
  ];
  return (
    <div className="space-y-5" data-testid="inv-intel-dashboard">
      <div className="flex flex-wrap items-center gap-3">
        <div><h2 className="text-xl font-bold text-slate-900">{t('inv.intel.dash_title', 'Intelligence & Monitoring')}</h2>
          <p className="text-sm text-slate-500">{t('inv.intel.dash_subtitle', 'Agents analyse the shared distribution data and raise alerts — every action requires human review. No commercial, financial or stock change is ever made automatically.')}</p></div>
        <Btn className="ml-auto" onClick={runScan} disabled={scanning} data-testid="inv-intel-scan-btn"><Radar size={15} className={scanning ? 'animate-spin' : ''} /> {scanning ? t('inv.intel.scanning', 'Scanning…') : t('inv.intel.run_scan', 'Run scan')}</Btn>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label={t('inv.intel.critical', 'Critical')} value={c.critical || 0} tone="red" testId="inv-intel-count-critical" />
        <StatCard label={t('inv.intel.warning', 'Warning')} value={c.warning || 0} tone="amber" testId="inv-intel-count-warning" />
        <StatCard label={t('inv.intel.monitor', 'Monitor')} value={c.monitor || 0} tone="navy" testId="inv-intel-count-monitor" />
        <StatCard label={t('inv.intel.open_alerts', 'Open alerts')} value={ov.open_alerts || 0} tone={ov.open_alerts ? 'amber' : 'green'} testId="inv-intel-count-open" />
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card className="p-4" testId="inv-intel-status">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-bold text-slate-900"><Activity size={15} className="text-[#0B3D91]" /> {t('inv.intel.status_title', 'Monitoring status')}</h3>
          <div className="space-y-2 text-sm">
            <div className="flex items-center justify-between border-b border-slate-100 py-1.5"><span className="text-slate-600">{t('inv.intel.last_scan', 'Last scan')}</span><span className="font-semibold text-slate-800">{ov.last_scan ? fmtDate(ov.last_scan) : t('inv.intel.never', 'Never run')}</span></div>
            <div className="flex items-center justify-between border-b border-slate-100 py-1.5"><span className="text-slate-600">{t('inv.intel.open_alerts', 'Open alerts')}</span><span className="font-semibold text-slate-800">{ov.open_alerts || 0}</span></div>
            <div className="flex items-center justify-between py-1.5"><span className="text-slate-600">{t('inv.intel.agents_count', 'Monitoring agents')}</span><span className="font-semibold text-slate-800">7</span></div>
          </div>
          <Btn variant="secondary" className="mt-3 w-full" onClick={() => go('intel-alerts')} data-testid="inv-intel-view-alerts"><ShieldAlert size={14} /> {t('inv.intel.view_alerts', 'View alerts')}</Btn>
        </Card>
        <Card className="p-4" testId="inv-intel-agents">
          <h3 className="mb-3 text-sm font-bold text-slate-900">{t('inv.intel.active_agents', 'Active monitoring agents')}</h3>
          <div className="space-y-1.5 text-sm">
            {AGENTS.map(([k, def]) => (
              <div key={k} className="flex items-center gap-2 border-b border-slate-100 py-1 last:border-0"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /><span className="text-slate-700">{t(k, def)}</span><span className="ml-auto text-[11px] text-slate-400">{t('inv.intel.readonly', 'read-only')}</span></div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

// ─────────────────────────── Alerts ───────────────────────────
export function IntelAlerts() {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [severity, setSeverity] = useState('all');
  const [status, setStatus] = useState('all');
  const load = useCallback(() => invApi.intelAlerts({ severity, status }).then(setData).catch(() => setData({ alerts: [], counts: {} })), [severity, status]);
  useEffect(() => { load(); }, [load]);

  const setAlert = async (id, s) => { try { await invApi.intelSetAlertStatus(id, s); notify.success(t('inv.intel.alert_set', 'Alert {{status}}', { status: statusLabel(s) })); load(); } catch (e) { notify.error(t('inv.common.failed', 'Failed')); } };

  return (
    <div className="space-y-4" data-testid="inv-intel-alerts">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-bold text-slate-900">{t('inv.intel.alerts_title', 'Monitoring Alerts')}</h2>
        <div className="ml-auto flex flex-wrap gap-2">
          <select className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm" value={severity} data-testid="inv-intel-filter-severity" onChange={(e) => setSeverity(e.target.value)}>
            <option value="all">{t('inv.intel.all_severities', 'All severities')}</option>{SEVERITIES.map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}
          </select>
          <select className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm" value={status} data-testid="inv-intel-filter-status" onChange={(e) => setStatus(e.target.value)}>
            <option value="all">{t('inv.intel.all_statuses', 'All statuses')}</option>{STATUSES.map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}
          </select>
        </div>
      </div>
      <div className="flex items-start gap-2 rounded-lg bg-blue-50 px-4 py-2.5 text-xs text-blue-800"><Info size={14} className="mt-0.5 shrink-0" /><span>{t('inv.intel.alerts_note', 'Agents flag issues for a human to review and action. Marking an alert resolved/dismissed does not change any order, stock or financial record.')}</span></div>

      {data === null ? <Spinner /> : data.alerts.length === 0 ? (
        <Card className="p-10 text-center" testId="inv-intel-alerts-empty"><CheckCircle2 size={34} className="mx-auto mb-2 text-emerald-400" /><p className="text-slate-500">{t('inv.intel.no_alerts', 'No alerts match this filter. Run a scan from the dashboard to refresh.')}</p></Card>
      ) : (
        <div className="space-y-3">
          {data.alerts.map((a) => {
            const sev = SEV_STYLE[a.severity] || SEV_STYLE.information;
            const done = ['resolved', 'dismissed'].includes(a.status);
            return (
              <Card key={a.id} className="p-4" testId={`inv-intel-alert-${a.id}`}>
                <div className="flex items-start gap-3">
                  <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${sev.dot}`} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${sev.chip}`}>{a.severity}</span>
                      <span className="text-[11px] font-semibold text-slate-400">{a.agent}</span>
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-600">{statusLabel(a.status)}</span>
                    </div>
                    <p className="mt-1 font-semibold text-slate-900">{a.title}</p>
                    <p className="mt-0.5 text-sm text-slate-600"><span className="font-semibold text-slate-500">{t('inv.intel.suggested', 'Suggested action:')} </span>{a.suggested_action}</p>
                    {a.evidence && Object.keys(a.evidence).length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1.5">{Object.entries(a.evidence).map(([k, v]) => <span key={k} className="rounded bg-slate-50 px-2 py-0.5 text-[11px] font-mono text-slate-500">{k}: {String(v)}</span>)}</div>
                    )}
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap justify-end gap-2 border-t border-slate-100 pt-3">
                  {!done && a.status === 'new' && <Btn variant="secondary" onClick={() => setAlert(a.id, 'assigned')} data-testid={`inv-intel-alert-assign-${a.id}`}><UserCheck size={13} /> {t('inv.intel.assign', 'Assign')}</Btn>}
                  {!done && a.status !== 'under_review' && <Btn variant="secondary" onClick={() => setAlert(a.id, 'under_review')} data-testid={`inv-intel-alert-review-${a.id}`}><Eye size={13} /> {t('inv.intel.under_review', 'Under review')}</Btn>}
                  {!done && <Btn onClick={() => setAlert(a.id, 'resolved')} data-testid={`inv-intel-alert-resolve-${a.id}`}><CheckCircle2 size={13} /> {t('inv.intel.resolve', 'Resolve')}</Btn>}
                  {!done && <Btn variant="ghost" onClick={() => setAlert(a.id, 'dismissed')} data-testid={`inv-intel-alert-dismiss-${a.id}`}><XCircle size={13} /> {t('inv.intel.dismiss', 'Dismiss')}</Btn>}
                  {done && <span className="text-xs font-semibold text-slate-400">{statusLabel(a.status)}</span>}
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────── Reports ───────────────────────────
const REPORTS = [
  { id: 'serial_register', labelKey: 'inv.intel.report_serial', label: 'Serial Register' },
  { id: 'stock_ledger', labelKey: 'inv.intel.report_ledger', label: 'Stock Ledger' },
  { id: 'order_progress', labelKey: 'inv.intel.report_progress', label: 'Order Progress' },
  { id: 'dealer_stock_ageing', labelKey: 'inv.intel.report_ageing', label: 'Dealer Stock Ageing' },
];

export function IntelReports() {
  const { t } = useTranslation();
  const [active, setActive] = useState('serial_register');
  const [data, setData] = useState(null);
  const load = useCallback(() => { setData(null); invApi.intelReport(active).then(setData).catch(() => setData({ columns: [], rows: [] })); }, [active]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4" data-testid="inv-intel-reports">
      <h2 className="text-xl font-bold text-slate-900">{t('inv.intel.reports_title', 'Distribution Reports')}</h2>
      <div className="flex flex-wrap gap-2">
        {REPORTS.map((r) => (
          <button key={r.id} onClick={() => setActive(r.id)} data-testid={`inv-intel-report-tab-${r.id}`}
            className={`inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-semibold transition-colors ${active === r.id ? 'inv-active text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>
            <FileBarChart size={14} /> {t(r.labelKey, r.label)}
          </button>
        ))}
      </div>
      {data === null ? <Spinner /> : (
        <Card testId="inv-intel-report-table">
          {data.rows.length === 0 ? <p className="px-4 py-10 text-center text-sm text-slate-400">{t('inv.intel.no_report', 'No data for this report yet.')}</p> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">{data.columns.map((c) => <th key={c} className="px-4 py-3 whitespace-nowrap">{statusLabel(c)}</th>)}</tr></thead>
                <tbody>
                  {data.rows.map((row, i) => (
                    <tr key={i} className="border-b border-slate-100" data-testid={`inv-intel-report-row-${i}`}>
                      {data.columns.map((c) => <td key={c} className="px-4 py-2.5 text-slate-700 whitespace-nowrap">{row[c] === null || row[c] === undefined || row[c] === '' ? '—' : String(row[c])}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

// ─────────────────────────── Replenishment ───────────────────────────
export function IntelReplenishment() {
  const { t } = useTranslation();
  const [reorderPoint, setReorderPoint] = useState(2);
  const [data, setData] = useState(null);
  const load = useCallback(() => { setData(null); invApi.intelReplenishment(reorderPoint).then(setData).catch(() => setData({ recommendations: [] })); }, [reorderPoint]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-4" data-testid="inv-intel-replenishment">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-bold text-slate-900">{t('inv.intel.replen_title', 'Replenishment')}</h2>
        <div className="ml-auto flex items-center gap-2 text-sm">
          <span className="text-slate-500">{t('inv.intel.reorder_point', 'Reorder point')}</span>
          <input type="number" min="0" className="w-20 rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm" value={reorderPoint} data-testid="inv-intel-reorder-point" onChange={(e) => setReorderPoint(Number(e.target.value))} />
          <Btn variant="secondary" onClick={load} data-testid="inv-intel-replenish-refresh"><RefreshCw size={14} /> {t('inv.common.refresh', 'Refresh')}</Btn>
        </div>
      </div>
      {data === null ? <Spinner /> : (
        <>
          <div className="flex items-start gap-2 rounded-lg bg-amber-50 px-4 py-2.5 text-xs text-amber-800"><Info size={14} className="mt-0.5 shrink-0" /><span>{data.note || t('inv.intel.replen_note', 'Recommendations require human approval — no Sage purchase order is created automatically.')}</span></div>
          {data.recommendations.length === 0 ? (
            <Card className="p-10 text-center" testId="inv-intel-replenish-empty"><PackagePlus size={34} className="mx-auto mb-2 text-emerald-400" /><p className="text-slate-500">{t('inv.intel.replen_empty', 'No products at or below the reorder point.')}</p></Card>
          ) : (
            <Card testId="inv-intel-replenish-table">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400"><th className="px-4 py-3">{t('inv.th.product', 'Product')}</th><th>{t('inv.th.available', 'Available')}</th><th>{t('inv.intel.reorder_point', 'Reorder point')}</th><th>{t('inv.intel.recommended_qty', 'Recommended qty')}</th></tr></thead>
                <tbody>
                  {data.recommendations.map((r, i) => (
                    <tr key={i} className="border-b border-slate-100" data-testid={`inv-intel-replenish-row-${r.product_code}`}>
                      <td className="px-4 py-2.5 font-mono text-xs">{r.product_code}</td>
                      <td className="tabular-nums text-rose-600">{r.available}</td>
                      <td className="tabular-nums text-slate-500">{r.reorder_point}</td>
                      <td className="tabular-nums font-semibold text-[#0B3D91]">{r.recommended_qty}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
