/**
 * ServiceOpsReportsPage — iter 215du (Phase 7).
 *
 * Operations console at /service-ops/reports.
 *
 * Sections:
 *  • Summary KPIs (open / closed / invoiced / revenue / AI calls)
 *  • Revenue per engineer (horizontal bar)
 *  • First-time-fix rate gauge
 *  • SLA compliance (overall + by priority)
 *  • AI observability (calls / ok rate / p50 / p95 by kind)
 *  • Audit feed (filterable timeline)
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import {
  BarChart3, RefreshCw, Sparkles, Activity, Gauge,
  ShieldCheck, Wrench, ClipboardList, Timer, MapPin,
  Download, FileText, Bookmark, X, Mail, Send, Save, Loader2,
  Inbox,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import ServiceOpsShell from './ServiceOpsShell';
import { resolveChannel } from '@/utils/channelLabel';
import { useLocalization, formatMoneySync } from '@/utils/localization';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const RANGES = [
  { id: '7', labelKey: 'service.rep_range_7', label: 'Last 7 days', days: 7 },
  { id: '30', labelKey: 'service.rep_range_30', label: 'Last 30 days', days: 30 },
  { id: '90', labelKey: 'service.rep_range_90', label: 'Last 90 days', days: 90 },
];

function gbp(n) { return formatMoneySync(n, { minimumFractionDigits: 0 }); }
function pct(n) { return `${Math.round((Number(n) || 0) * 100)}%`; }

function isoFromDaysAgo(d) {
  const t = new Date();
  t.setDate(t.getDate() - d);
  return t.toISOString();
}

function Section({ icon: Icon, title, children, testid }) {
  return (
    <section className="svc-section" data-testid={testid}>
      <div className="svc-section-head">
        <div className="svc-section-title inline-flex items-center gap-1.5"><Icon size={14} /> {title}</div>
      </div>
      <div className="svc-section-body">{children}</div>
    </section>
  );
}

function KPI({ label, value, sub, testid }) {
  return (
    <div className="svc-kpi svc-kpi--info" data-testid={testid}>
      <p className="svc-kpi-label">{label}</p>
      <p className="svc-kpi-value">{value}</p>
      {sub ? <p className="svc-kpi-hint">{sub}</p> : null}
    </div>
  );
}

export default function ServiceOpsReportsPage() {
  const { t } = useTranslation();
  useLocalization();  // warm currency cache
  const [rangeId, setRangeId] = useState('30');
  const range = RANGES.find((r) => r.id === rangeId) || RANGES[1];
  const fromIso = useMemo(() => isoFromDaysAgo(range.days), [range.days]);

  const [data, setData] = useState({});
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState('');
  const [filters, setFilters] = useState({});
  const [savedViews, setSavedViews] = useState([]);
  const [digestOpen, setDigestOpen] = useState(false);

  const loadSavedViews = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/svc/views`, { ...auth(), params: { kind: 'reports' } });
      setSavedViews(r.data?.views || []);
    } catch (e) {
      // Soft-fail — saved views shouldn't break the page.
       
      console.warn('saved views load failed', e?.response?.data?.detail || e.message);
    }
  }, []);
  useEffect(() => { loadSavedViews(); }, [loadSavedViews]);

  const applyView = (view) => {
    if (view?.range_id) setRangeId(view.range_id);
    if (view?.filters) setFilters(view.filters);
    notify.success(t('service.rep_loaded_view', 'Loaded view'), view.name);
  };

  const saveView = async () => {
    const name = window.prompt(t('service.rep_name_view', 'Name this view (e.g. "Weekly exec summary")'));
    if (!name) return;
    try {
      await axios.post(`${API}/svc/views`, {
        name: name.trim(), kind: 'reports',
        filters: { ...filters }, range_id: rangeId,
        route: '/service-ops/reports',
      }, auth());
      await loadSavedViews();
      notify.success(t('service.rep_view_saved', 'View saved'), name);
    } catch (e) {
      notify.error(t('service.rep_save_failed', 'Save failed'), e?.response?.data?.detail || e.message);
    }
  };

  const deleteView = async (view) => {
    if (!window.confirm(t('service.rep_delete_view_confirm', 'Delete saved view "{{name}}"?', { name: view.name }))) return;
    try {
      await axios.delete(`${API}/svc/views/${view.id}`, auth());
      await loadSavedViews();
      notify.success(t('service.rep_view_deleted', 'View deleted'));
    } catch (e) {
      notify.error(t('service.rep_delete_failed', 'Delete failed'), e?.response?.data?.detail || e.message);
    }
  };

  const exportFile = async (kind) => {
    const url = kind === 'pdf'
      ? `${API}/svc/reports/export.pdf?days=${range.days}`
      : `${API}/svc/reports/export.csv?type=${kind}&from=${encodeURIComponent(fromIso)}&days=${range.days}`;
    setExporting(kind);
    try {
      const r = await axios.get(url, { ...auth(), responseType: 'blob' });
      const cd = r.headers['content-disposition'] || '';
      const m = /filename="([^"]+)"/.exec(cd);
      const filename = m ? m[1] : (kind === 'pdf' ? 'svc-ops-report.pdf' : `svc-ops-${kind}.csv`);
      const blob = new Blob([r.data], { type: r.headers['content-type'] || 'application/octet-stream' });
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
      notify.success(t('service.rep_export_ready', 'Export ready'), filename);
    } catch (e) {
      notify.error(t('service.rep_export_failed', 'Export failed'), e?.response?.data?.detail || e.message);
    } finally { setExporting(''); }
  };

  const load = useCallback(async () => {
    setLoading(true);
    const params = { from: fromIso };
    try {
      const [s, r, f, sl, ai, a, dt, ch] = await Promise.all([
        axios.get(`${API}/svc/reports/summary`, { ...auth(), params }),
        axios.get(`${API}/svc/reports/revenue-by-engineer`, { ...auth(), params }),
        axios.get(`${API}/svc/reports/ftfr`, { ...auth(), params }),
        axios.get(`${API}/svc/reports/sla`, { ...auth(), params }),
        axios.get(`${API}/svc/reports/ai`, { ...auth(), params }),
        axios.get(`${API}/svc/reports/audit`, { ...auth(), params: { ...params, limit: 50 } }),
        axios.get(`${API}/svc/reports/downtime`, { ...auth(), params: { days: range.days } })
          .catch(() => ({ data: { top_assets: [], top_sites: [], total_hours: 0, case_count: 0 } })),
        axios.get(`${API}/svc/reports/channel-performance`, { ...auth(), params })
          .catch(() => ({ data: { rows: [], totals: { case_count: 0, closed_count: 0, revenue_gbp: 0 } } })),
      ]);
      setData({
        summary: s.data, revenue: r.data, ftfr: f.data, sla: sl.data,
        ai: ai.data, audit: a.data, downtime: dt.data, channels: ch.data,
      });
    } catch (e) {
      notify.error(t('service.rep_load_failed', 'Failed to load reports'), e?.response?.data?.detail || e.message);
    } finally { setLoading(false); }
  }, [fromIso, range.days]);

  useEffect(() => { load(); }, [load]);

  const kpis = data.summary?.kpis || {};
  const revenueRows = data.revenue?.rows || [];
  const maxRevenue = revenueRows.reduce((m, r) => Math.max(m, r.revenue || 0), 0) || 1;
  const ftfrRate = data.ftfr?.rate || 0;
  const slaRate = data.sla?.rate || 0;
  const aiRows = data.ai?.by_kind || [];
  const audit = data.audit?.events || [];
  const downtime = data.downtime || { top_assets: [], top_sites: [], total_hours: 0, case_count: 0 };
  const channelData = data.channels || { rows: [], totals: { case_count: 0, closed_count: 0, revenue_gbp: 0 } };
  const channelRows = channelData.rows || [];
  const maxChannelCount = channelRows.reduce((m, r) => Math.max(m, r.count || 0), 0) || 1;
  const maxChannelRevenue = channelRows.reduce((m, r) => Math.max(m, r.revenue_gbp || 0), 0) || 1;
  const topAssets = downtime.top_assets || [];
  const topSites = downtime.top_sites || [];
  const maxAssetHours = topAssets.reduce((m, r) => Math.max(m, r.downtime_hours || 0), 0) || 1;
  const maxSiteHours = topSites.reduce((m, r) => Math.max(m, r.downtime_hours || 0), 0) || 1;

  return (
    <ServiceOpsShell
      icon={BarChart3}
      title={t('service.rep_title', 'Reports & audit')}
      subtitle={t('service.rep_subtitle', 'Revenue per engineer, first-time-fix rate, SLA compliance, and AI observability — all live from the operational data.')}
      actions={(
        <>
          <select value={rangeId} onChange={(e) => setRangeId(e.target.value)} className="svc-select svc-select-sm" style={{ width: 'auto' }} data-testid="reports-range">
            {RANGES.map((r) => <option key={r.id} value={r.id}>{t(r.labelKey, r.label)}</option>)}
          </select>
          <ExportMenu exporting={exporting} onExport={exportFile} />
          <button
            type="button"
            onClick={saveView}
            className="svc-btn svc-btn-secondary svc-btn-sm"
            data-testid="reports-save-view"
            title={t('service.rep_save_view_title', 'Save the current range / filters as a reusable view')}
          >
            <Bookmark size={11} /> {t('service.rep_save_view', 'Save view')}
          </button>
          <button
            type="button"
            onClick={() => setDigestOpen(true)}
            className="svc-btn svc-btn-secondary svc-btn-sm"
            data-testid="reports-digest-open"
          >
            <Mail size={11} /> {t('service.rep_email_digest', 'Email digest')}
          </button>
          <button type="button" onClick={load} className="svc-btn svc-btn-secondary svc-btn-sm" data-testid="reports-refresh">
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} /> {t('service.rep_refresh', 'Refresh')}
          </button>
        </>
      )}
      active="reports"
      pageTestId="reports-page"
    >
      {/* Saved views chips */}
      {savedViews.length > 0 ? (
        <div className="flex items-center gap-2 flex-wrap" data-testid="reports-saved-views">
          <span className="text-[11px] uppercase tracking-wider svc-muted font-bold inline-flex items-center gap-1">
            <Bookmark size={11} /> {t('service.rep_saved_views', 'Saved views')}
          </span>
          {savedViews.map((v) => (
            <span
              key={v.id}
              className="svc-pill svc-pill--info"
              style={{ paddingRight: 4 }}
              data-testid={`reports-saved-view-${v.id}`}
            >
              <button
                type="button"
                onClick={() => applyView(v)}
                className="font-bold"
                style={{ background: 'none', border: 0, color: 'inherit', cursor: 'pointer', padding: 0 }}
                data-testid={`reports-saved-view-apply-${v.id}`}
              >
                {v.name}
              </button>
              <button
                type="button"
                onClick={() => deleteView(v)}
                aria-label={t('service.rep_delete_named', 'Delete {{name}}', { name: v.name })}
                style={{
                  background: 'none', border: 0, cursor: 'pointer', color: 'inherit',
                  padding: '0 2px', marginLeft: 2, opacity: 0.6,
                }}
                data-testid={`reports-saved-view-delete-${v.id}`}
              >
                <X size={10} />
              </button>
            </span>
          ))}
        </div>
      ) : null}
      {/* Summary KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-7 gap-3" data-testid="reports-kpis">
        <KPI label={t('service.rep_kpi_open', 'Open cases')} value={kpis.open_cases ?? '—'} testid="kpi-open-cases" />
        <KPI label={t('service.rep_kpi_closed', 'Closed in window')} value={kpis.cases_closed ?? '—'} testid="kpi-cases-closed" />
        <KPI label={t('service.rep_kpi_invoiced', 'Chargeable invoiced')} value={kpis.chargeable_invoiced ?? '—'} testid="kpi-chargeable-invoiced" />
        <KPI label={t('service.rep_kpi_revenue', 'Revenue (gross)')} value={gbp(kpis.revenue_gross)} sub={kpis.revenue_net ? t('service.rep_net', 'Net {{v}}', { v: gbp(kpis.revenue_net) }) : null} testid="kpi-revenue" />
        <KPI label={t('service.rep_kpi_ftfr', 'FTFR')} value={pct(ftfrRate)} sub={`${data.ftfr?.ftf ?? 0} / ${data.ftfr?.total_closed ?? 0}`} testid="kpi-ftfr" />
        <KPI
          label={t('service.rep_kpi_downtime', 'Downtime')}
          value={(downtime.total_hours ?? 0) >= 1000
            ? `${Math.round((downtime.total_hours ?? 0) / 24).toLocaleString()}d`
            : `${(downtime.total_hours ?? 0).toLocaleString()}h`}
          sub={t('service.rep_downtime_cases', '{{n}} cases', { n: downtime.case_count ?? 0 }) + ((downtime.total_hours ?? 0) >= 1000 ? ` · ${Math.round(downtime.total_hours).toLocaleString()}h` : '')}
          testid="kpi-downtime"
        />
        <KPI label={t('service.rep_kpi_ai', 'AI calls')} value={kpis.ai_calls ?? 0} testid="kpi-ai-calls" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Revenue per engineer */}
        <Section icon={Wrench} title={t('service.rep_revenue_per_eng', 'Revenue per engineer')} testid="reports-revenue">
          {revenueRows.length === 0 ? (
            <p className="text-xs opacity-60 italic">{t('service.rep_no_labour', 'No invoiced labour in this window.')}</p>
          ) : (
            <ul className="space-y-2" data-testid="revenue-rows">
              {revenueRows.map((r) => (
                <li key={`${r.engineer_id || 'x'}-${r.engineer_name}`} data-testid={`revenue-row-${r.engineer_id || r.engineer_name}`}>
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-bold truncate">{r.engineer_name || t('service.rep_unattributed', 'Unattributed')}</span>
                    <span className="tabular-nums">{gbp(r.revenue)} · {r.hours}h · {t('service.rep_cases', '{{n}} cases', { n: r.cases })}</span>
                  </div>
                  <div className="h-1.5 rounded-full mt-1 overflow-hidden" style={{ background: 'var(--theme-border)' }}>
                    <div
                      className="h-full"
                      style={{
                        width: `${Math.max(2, Math.round((r.revenue / maxRevenue) * 100))}%`,
                        background: '#0891b2',
                      }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Section>

        {/* SLA compliance */}
        <Section icon={ShieldCheck} title={t('service.rep_sla', 'SLA compliance')} testid="reports-sla">
          <div className="flex items-baseline gap-3">
            <span className="text-3xl font-extrabold tabular-nums" data-testid="sla-rate">{pct(slaRate)}</span>
            <span className="text-xs opacity-70">{t('service.rep_sla_split', '{{ontime}} on-time / {{breached}} breached', { ontime: data.sla?.on_time ?? 0, breached: data.sla?.breached ?? 0 })}</span>
          </div>
          <div className="h-1.5 rounded-full mt-2 overflow-hidden" style={{ background: 'var(--theme-border)' }}>
            <div className="h-full" style={{ width: `${Math.round(slaRate * 100)}%`, background: slaRate >= 0.95 ? '#10b981' : slaRate >= 0.85 ? '#f59e0b' : '#ef4444' }} />
          </div>
          <ul className="mt-3 grid grid-cols-2 gap-2" data-testid="sla-by-priority">
            {Object.entries(data.sla?.by_priority || {}).map(([p, b]) => (
              <li key={p} className="text-xs px-2 py-1.5 rounded border flex items-center justify-between" style={{ borderColor: 'var(--theme-border)' }} data-testid={`sla-priority-${p}`}>
                <span><strong>{p.toUpperCase()}</strong> · {b.total}</span>
                <span className="tabular-nums">{b.total ? Math.round((b.on_time / b.total) * 100) : 0}{t('service.rep_pct_ontime', '% on-time')}</span>
              </li>
            ))}
          </ul>
        </Section>

        {/* FTFR detail */}
        <Section icon={Gauge} title={t('service.rep_ftfr_title', 'First-time-fix rate')} testid="reports-ftfr">
          <div className="flex items-baseline gap-3">
            <span className="text-3xl font-extrabold tabular-nums" data-testid="ftfr-rate">{pct(ftfrRate)}</span>
            <span className="text-xs opacity-70">{t('service.rep_ftfr_split', '{{ftf}} / {{total}} closed', { ftf: data.ftfr?.ftf ?? 0, total: data.ftfr?.total_closed ?? 0 })}</span>
          </div>
          <div className="h-1.5 rounded-full mt-2 overflow-hidden" style={{ background: 'var(--theme-border)' }}>
            <div className="h-full" style={{ width: `${Math.round(ftfrRate * 100)}%`, background: ftfrRate >= 0.8 ? '#10b981' : ftfrRate >= 0.6 ? '#f59e0b' : '#ef4444' }} />
          </div>
          <p className="text-[11px] opacity-60 mt-2">{t('service.rep_ftfr_hint', 'A fix is "first-time" if the case never entered paused_parts. Lift this metric by improving van-stock accuracy and AI triage of likely parts.')}</p>
        </Section>

        {/* Asset downtime */}
        <Section icon={Timer} title={t('service.rep_top_assets', 'Top assets by downtime')} testid="reports-downtime-assets">
          {topAssets.length === 0 ? (
            <p className="text-xs opacity-60 italic">{t('service.rep_no_downtime', 'No downtime recorded in this window.')}</p>
          ) : (
            <ul className="space-y-2" data-testid="downtime-asset-rows">
              {topAssets.map((r, idx) => (
                <li key={`${r.asset_id || r.asset_name}-${idx}`} data-testid={`downtime-asset-row-${idx}`}>
                  <div className="flex items-center justify-between text-xs gap-2">
                    <span className="font-bold truncate">{r.asset_name || t('service.rep_unknown_asset', 'Unknown asset')}</span>
                    <span className="tabular-nums whitespace-nowrap">
                      {r.downtime_hours.toLocaleString()}h · {t('service.rep_cases', '{{n}} cases', { n: r.case_count })}
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full mt-1 overflow-hidden" style={{ background: 'var(--theme-border)' }}>
                    <div
                      className="h-full"
                      style={{
                        width: `${Math.max(2, Math.round((r.downtime_hours / maxAssetHours) * 100))}%`,
                        background: '#ef4444',
                      }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
          <p className="text-[11px] opacity-60 mt-2">{t('service.rep_total_downtime', 'Total fleet downtime:')} <strong>{(downtime.total_hours ?? 0).toLocaleString()}h</strong> {t('service.rep_across_cases', 'across {{n}} cases. Use this to prioritise PPM frequency and replacement cycles.', { n: downtime.case_count ?? 0 })}</p>
        </Section>

        {/* Site downtime */}
        <Section icon={MapPin} title={t('service.rep_top_sites', 'Top sites by downtime')} testid="reports-downtime-sites">
          {topSites.length === 0 ? (
            <p className="text-xs opacity-60 italic">{t('service.rep_no_site_downtime', 'No site downtime in this window.')}</p>
          ) : (
            <ul className="space-y-2" data-testid="downtime-site-rows">
              {topSites.map((r, idx) => (
                <li key={`${r.site_id || r.site_name}-${idx}`} data-testid={`downtime-site-row-${idx}`}>
                  <div className="flex items-center justify-between text-xs gap-2">
                    <span className="font-bold truncate">{r.site_name || t('service.rep_unknown_site', 'Unknown site')}</span>
                    <span className="tabular-nums whitespace-nowrap">
                      {r.downtime_hours.toLocaleString()}h · {t('service.rep_cases', '{{n}} cases', { n: r.case_count })}
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full mt-1 overflow-hidden" style={{ background: 'var(--theme-border)' }}>
                    <div
                      className="h-full"
                      style={{
                        width: `${Math.max(2, Math.round((r.downtime_hours / maxSiteHours) * 100))}%`,
                        background: '#f59e0b',
                      }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Section>

        {/* Iter 220cq — Channel performance (where work comes from) */}
        <Section icon={Inbox} title={t('service.rep_work_from', 'Where work comes from')} testid="reports-channels">
          {channelRows.length === 0 ? (
            <p className="text-xs opacity-60 italic">{t('service.rep_no_cases_window', 'No cases logged in this window.')}</p>
          ) : (
            <ul className="space-y-2" data-testid="channel-rows">
              {channelRows.map((r) => {
                const ch = resolveChannel({ intake_channel: r.channel });
                const label = ch?.label || r.channel;
                return (
                  <li key={r.channel} data-testid={`channel-row-${r.channel}`}>
                    <div className="flex items-center justify-between text-xs gap-2">
                      <span className="font-bold truncate">{label}</span>
                      <span className="tabular-nums whitespace-nowrap">
                        {t('service.rep_cases', '{{n}} cases', { n: r.count })} ·{' '}
                        {t('service.rep_closed_pct', '{{p}} closed', { p: pct(r.close_rate) })}
                        {r.avg_hours != null ? ` · ${t('service.rep_avg_hours', '{{h}}h avg', { h: r.avg_hours })}` : ''}
                        {r.revenue_gbp > 0 ? ` · ${gbp(r.revenue_gbp)}` : ''}
                      </span>
                    </div>
                    <div
                      className="h-1.5 rounded-full mt-1 overflow-hidden"
                      style={{ background: 'var(--theme-border)' }}
                    >
                      <div
                        className="h-full"
                        style={{
                          width: `${Math.max(2, Math.round((r.count / maxChannelCount) * 100))}%`,
                          background: r.revenue_gbp > 0
                            ? '#0891b2'
                            : '#94a3b8',
                        }}
                      />
                    </div>
                    {r.revenue_gbp > 0 && maxChannelRevenue > 0 && (
                      <div
                        className="h-1 rounded-full mt-1 overflow-hidden opacity-70"
                        style={{ background: 'var(--theme-border)' }}
                      >
                        <div
                          className="h-full"
                          style={{
                            width: `${Math.max(2, Math.round((r.revenue_gbp / maxChannelRevenue) * 100))}%`,
                            background: '#10b981',
                          }}
                        />
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          {channelData.totals?.case_count > 0 && (
            <p
              className="text-[11px] opacity-70 mt-2 inline-flex items-center gap-1.5"
              data-testid="channel-totals"
            >
              <Activity size={11} />
              {t('service.rep_channel_totals', '{{total}} total · {{closed}} closed · {{rev}} revenue', { total: channelData.totals.case_count, closed: channelData.totals.closed_count, rev: gbp(channelData.totals.revenue_gbp) })}
            </p>
          )}
        </Section>

        {/* AI observability */}
        <Section icon={Sparkles} title={t('service.rep_ai_obs', 'AI observability')} testid="reports-ai">
          {aiRows.length === 0 ? (
            <p className="text-xs opacity-60 italic">{t('service.rep_no_ai', 'No AI calls in this window.')}</p>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider opacity-70">
                  <th className="py-1">{t('service.rep_ai_kind', 'Kind')}</th>
                  <th className="py-1 text-right">{t('service.rep_ai_calls', 'Calls')}</th>
                  <th className="py-1 text-right">{t('service.rep_ai_ok', 'OK')}</th>
                  <th className="py-1 text-right">{t('service.rep_ai_p50', 'p50 ms')}</th>
                  <th className="py-1 text-right">{t('service.rep_ai_p95', 'p95 ms')}</th>
                </tr>
              </thead>
              <tbody>
                {aiRows.map((r) => (
                  <tr key={r.kind} className="border-t" style={{ borderColor: 'var(--theme-border)' }} data-testid={`ai-row-${r.kind}`}>
                    <td className="py-1 font-bold">{r.kind}</td>
                    <td className="py-1 text-right tabular-nums">{r.calls}</td>
                    <td className="py-1 text-right tabular-nums">{pct(r.ok_rate)}</td>
                    <td className="py-1 text-right tabular-nums">{r.p50_latency_ms}</td>
                    <td className="py-1 text-right tabular-nums" style={{ color: r.p95_latency_ms > 5000 ? '#ef4444' : undefined }}>{r.p95_latency_ms}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {data.ai?.totals ? (
            <p className="text-[11px] opacity-70 mt-2 inline-flex items-center gap-1.5"><Activity size={11} /> {t('service.rep_ai_totals', '{{n}} total · {{p}} success', { n: data.ai.totals.calls, p: pct(data.ai.totals.ok_rate) })}</p>
          ) : null}
        </Section>
      </div>

      {/* Audit log */}
      <Section icon={ClipboardList} title={t('service.rep_audit_feed', 'Audit feed')} testid="reports-audit">
        {audit.length === 0 ? (
          <p className="text-xs opacity-60 italic">{t('service.rep_no_events', 'No events in this window.')}</p>
        ) : (
          <ol className="space-y-1.5 text-xs max-h-96 overflow-y-auto pr-2" data-testid="audit-list">
            {audit.map((ev) => (
              <li key={ev.id} className="border-b pb-1.5" style={{ borderColor: 'var(--theme-border)' }} data-testid={`audit-row-${ev.id}`}>
                <div className="flex items-baseline gap-2 flex-wrap">
                  <span className="font-bold tabular-nums">{ev.case_reference || ev.case_id?.slice(0, 8)}</span>
                  <span className="px-1 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider" style={{ background: 'var(--theme-border)' }}>{ev.type}</span>
                  {ev.actor_name ? <span className="opacity-70">{ev.actor_name}</span> : null}
                  <span className="opacity-50 ml-auto">{new Date(ev.at).toLocaleString()}</span>
                </div>
                {ev.body ? <p className="opacity-80 mt-0.5">{ev.body}</p> : null}
                {ev.type === 'state_change' && ev.from_state ? (
                  <p className="opacity-60 mt-0.5">{ev.from_state} → {ev.to_state}{ev.reason ? ` · ${ev.reason}` : ''}</p>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </Section>
      {digestOpen ? <DigestSettingsModal onClose={() => setDigestOpen(false)} /> : null}
    </ServiceOpsShell>
  );
}

function ExportMenu({ exporting, onExport }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const items = [
    { id: 'pdf',      label: t('service.rep_exp_pdf', 'Branded PDF report'), icon: FileText },
    { id: 'summary',  label: t('service.rep_exp_summary', 'Summary KPIs (CSV)'), icon: Download },
    { id: 'revenue',  label: t('service.rep_exp_revenue', 'Revenue per engineer (CSV)'), icon: Download },
    { id: 'sla',      label: t('service.rep_exp_sla', 'SLA compliance (CSV)'), icon: Download },
    { id: 'ftfr',     label: t('service.rep_exp_ftfr', 'First-time-fix (CSV)'), icon: Download },
    { id: 'downtime', label: t('service.rep_exp_downtime', 'Downtime (CSV)'), icon: Download },
    { id: 'ai',       label: t('service.rep_exp_ai', 'AI observability (CSV)'), icon: Download },
  ];
  return (
    <div style={{ position: 'relative', display: 'inline-flex' }} data-testid="reports-export-menu">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="svc-btn svc-btn-secondary svc-btn-sm"
        disabled={!!exporting}
        data-testid="reports-export-btn"
      >
        {exporting ? <Loader2 size={11} className="animate-spin" /> : <Download size={11} />}
        {exporting ? t('service.rep_exporting', 'Exporting {{kind}}…', { kind: exporting }) : t('service.rep_export', 'Export')}
      </button>
      {open ? (
        <>
          <div
            onClick={() => setOpen(false)}
            style={{ position: 'fixed', inset: 0, zIndex: 30 }}
          />
          <ul
            className="svc-card-base"
            style={{
              position: 'absolute', top: '100%', right: 0, marginTop: 4,
              minWidth: 240, zIndex: 31, padding: 4,
            }}
            data-testid="reports-export-list"
          >
            {items.map((it) => {
              const Icon = it.icon;
              return (
                <li key={it.id}>
                  <button
                    type="button"
                    onClick={() => { setOpen(false); onExport(it.id); }}
                    className="w-full text-left px-2 py-1.5 text-xs rounded inline-flex items-center gap-2 hover:bg-slate-100"
                    style={{ color: 'inherit', background: 'transparent', border: 0, cursor: 'pointer' }}
                    data-testid={`reports-export-${it.id}`}
                  >
                    <Icon size={12} /> {it.label}
                  </button>
                </li>
              );
            })}
          </ul>
        </>
      ) : null}
    </div>
  );
}

function DigestSettingsModal({ onClose }) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [cadence, setCadence] = useState('weekly');
  const [recipients, setRecipients] = useState('');
  const [lastSentAt, setLastSentAt] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/svc/reports/digest/settings`, auth());
      setEnabled(!!r.data?.enabled);
      setCadence(r.data?.cadence || 'weekly');
      setRecipients((r.data?.recipients || []).join(', '));
      setLastSentAt(r.data?.last_sent_at || null);
    } catch (e) {
      notify.error(t('service.rep_dg_load_failed', 'Failed to load digest settings'), e?.response?.data?.detail || e.message);
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setSaving(true);
    try {
      const list = recipients.split(',').map((s) => s.trim()).filter((s) => s && s.includes('@'));
      const r = await axios.put(`${API}/svc/reports/digest/settings`, {
        enabled, cadence, recipients: list,
      }, auth());
      setEnabled(!!r.data?.enabled);
      setCadence(r.data?.cadence || cadence);
      setRecipients((r.data?.recipients || []).join(', '));
      notify.success(t('service.rep_dg_saved', 'Digest settings saved'));
    } catch (e) {
      notify.error(t('service.rep_save_failed', 'Save failed'), e?.response?.data?.detail || e.message);
    } finally { setSaving(false); }
  };

  const sendTest = async () => {
    setSending(true);
    try {
      const r = await axios.post(`${API}/svc/reports/digest/send-test`, {}, auth());
      notify.success(t('service.rep_dg_dispatched', 'Test digest dispatched'), t('service.rep_dg_sent_n', '{{n}} email(s) sent', { n: r.data?.sent ?? 0 }));
      await load();
    } catch (e) {
      notify.error(t('service.rep_send_failed', 'Send failed'), e?.response?.data?.detail || e.message);
    } finally { setSending(false); }
  };

  return (
    <div
      className="svc-drawer-overlay"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      data-testid="reports-digest-modal"
    >
      <aside
        className="svc-drawer"
        role="dialog"
        aria-label={t('service.rep_dg_aria', 'Email digest settings')}
        style={{ maxWidth: 520 }}
      >
        <header className="svc-drawer-head">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="svc-eyebrow">{t('service.rep_email_digest', 'Email digest')}</p>
              <h2 className="svc-h1" style={{ fontSize: 19, marginTop: 2 }}>{t('service.rep_dg_title', 'Service Operations summary')}</h2>
            </div>
            <button type="button" onClick={onClose} className="svc-icon-btn" aria-label={t('service.rep_close', 'Close')} data-testid="reports-digest-close">
              <X size={16} />
            </button>
          </div>
        </header>
        <div className="svc-drawer-body space-y-3">
          {loading ? (
            <div className="svc-empty"><Loader2 size={14} className="animate-spin" /> {t('service.rep_loading', 'Loading…')}</div>
          ) : (
            <>
              <p className="text-[11.5px] svc-muted">
                {t('service.rep_dg_intro', 'Send a digest to your team with open cases, breached SLAs and recently closed work. The dispatcher runs on the platform daily cron — recipients only receive a fresh digest when one is due.')}
              </p>

              <label className="svc-card-base p-3 flex items-start gap-3 cursor-pointer" data-testid="reports-digest-enable-row">
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={(e) => setEnabled(e.target.checked)}
                  data-testid="reports-digest-enabled"
                />
                <div>
                  <p className="font-bold text-sm">{t('service.rep_dg_enable', 'Enable digest emails')}</p>
                  <p className="text-[11.5px] svc-muted">{t('service.rep_dg_enable_hint', 'Switch off to pause delivery without losing the recipient list.')}</p>
                </div>
              </label>

              <label className="block">
                <span className="svc-label">{t('service.rep_dg_cadence', 'Cadence')}</span>
                <select
                  value={cadence}
                  onChange={(e) => setCadence(e.target.value)}
                  className="svc-select"
                  data-testid="reports-digest-cadence"
                >
                  <option value="daily">{t('service.rep_dg_daily', 'Daily — every morning')}</option>
                  <option value="weekly">{t('service.rep_dg_weekly', 'Weekly — every 7 days')}</option>
                </select>
              </label>

              <label className="block">
                <span className="svc-label">{t('service.rep_dg_recipients', 'Recipients (comma-separated)')}</span>
                <input
                  value={recipients}
                  onChange={(e) => setRecipients(e.target.value)}
                  placeholder="ops@yourgym.com, desk@yourgym.com"
                  className="svc-input"
                  data-testid="reports-digest-recipients"
                />
                <span className="text-[11px] svc-muted block mt-1">{t('service.rep_dg_recipients_hint', 'Up to 20 valid email addresses.')}</span>
              </label>

              {lastSentAt ? (
                <p className="text-[11px] svc-muted" data-testid="reports-digest-last-sent">
                  {t('service.rep_dg_last_sent', 'Last sent:')} <strong>{new Date(lastSentAt).toLocaleString()}</strong>
                </p>
              ) : (
                <p className="text-[11px] svc-muted">{t('service.rep_dg_none_sent', 'No digest has been sent yet.')}</p>
              )}
            </>
          )}
        </div>
        <footer className="svc-drawer-foot space-y-2">
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={sendTest}
              disabled={sending || saving}
              className="svc-btn svc-btn-secondary svc-btn-sm"
              data-testid="reports-digest-send-test"
            >
              {sending ? <Loader2 size={11} className="animate-spin" /> : <Send size={11} />}
              {sending ? t('service.rep_dg_sending', 'Sending…') : t('service.rep_dg_send_test', 'Send test now')}
            </button>
            <button
              type="button"
              onClick={save}
              disabled={saving || sending}
              className="svc-btn svc-btn-primary svc-btn-sm"
              data-testid="reports-digest-save"
            >
              <Save size={11} /> {saving ? t('service.rep_dg_saving', 'Saving…') : t('service.rep_save', 'Save')}
            </button>
          </div>
        </footer>
      </aside>
    </div>
  );
}
