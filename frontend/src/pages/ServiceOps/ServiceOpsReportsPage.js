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
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  BarChart3, RefreshCw, Sparkles, Activity, Gauge,
  ShieldCheck, Wrench, ClipboardList, Timer, MapPin,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import ServiceOpsShell from './ServiceOpsShell';

const API = process.env.REACT_APP_BACKEND_URL ? `${process.env.REACT_APP_BACKEND_URL}/api` : '/api';
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` } });

const RANGES = [
  { id: '7', label: 'Last 7 days', days: 7 },
  { id: '30', label: 'Last 30 days', days: 30 },
  { id: '90', label: 'Last 90 days', days: 90 },
];

function gbp(n) { return `£${(Number(n) || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`; }
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
  const [rangeId, setRangeId] = useState('30');
  const range = RANGES.find((r) => r.id === rangeId) || RANGES[1];
  const fromIso = useMemo(() => isoFromDaysAgo(range.days), [range.days]);

  const [data, setData] = useState({});
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const params = { from: fromIso };
    try {
      const [s, r, f, sl, ai, a, dt] = await Promise.all([
        axios.get(`${API}/svc/reports/summary`, { ...auth(), params }),
        axios.get(`${API}/svc/reports/revenue-by-engineer`, { ...auth(), params }),
        axios.get(`${API}/svc/reports/ftfr`, { ...auth(), params }),
        axios.get(`${API}/svc/reports/sla`, { ...auth(), params }),
        axios.get(`${API}/svc/reports/ai`, { ...auth(), params }),
        axios.get(`${API}/svc/reports/audit`, { ...auth(), params: { ...params, limit: 50 } }),
        axios.get(`${API}/svc/reports/downtime`, { ...auth(), params: { days: range.days } })
          .catch(() => ({ data: { top_assets: [], top_sites: [], total_hours: 0, case_count: 0 } })),
      ]);
      setData({
        summary: s.data, revenue: r.data, ftfr: f.data, sla: sl.data,
        ai: ai.data, audit: a.data, downtime: dt.data,
      });
    } catch (e) {
      notify.error('Failed to load reports', e?.response?.data?.detail || e.message);
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
  const topAssets = downtime.top_assets || [];
  const topSites = downtime.top_sites || [];
  const maxAssetHours = topAssets.reduce((m, r) => Math.max(m, r.downtime_hours || 0), 0) || 1;
  const maxSiteHours = topSites.reduce((m, r) => Math.max(m, r.downtime_hours || 0), 0) || 1;

  return (
    <ServiceOpsShell
      icon={BarChart3}
      title="Reports & audit"
      subtitle="Revenue per engineer, first-time-fix rate, SLA compliance, and AI observability — all live from the operational data."
      actions={(
        <>
          <select value={rangeId} onChange={(e) => setRangeId(e.target.value)} className="svc-select svc-select-sm" style={{ width: 'auto' }} data-testid="reports-range">
            {RANGES.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
          </select>
          <button type="button" onClick={load} className="svc-btn svc-btn-secondary svc-btn-sm" data-testid="reports-refresh">
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </>
      )}
      active="reports"
      pageTestId="reports-page"
    >
      {/* Summary KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-7 gap-3" data-testid="reports-kpis">
        <KPI label="Open cases" value={kpis.open_cases ?? '—'} testid="kpi-open-cases" />
        <KPI label="Closed in window" value={kpis.cases_closed ?? '—'} testid="kpi-cases-closed" />
        <KPI label="Chargeable invoiced" value={kpis.chargeable_invoiced ?? '—'} testid="kpi-chargeable-invoiced" />
        <KPI label="Revenue (gross)" value={gbp(kpis.revenue_gross)} sub={kpis.revenue_net ? `Net ${gbp(kpis.revenue_net)}` : null} testid="kpi-revenue" />
        <KPI label="FTFR" value={pct(ftfrRate)} sub={`${data.ftfr?.ftf ?? 0} / ${data.ftfr?.total_closed ?? 0}`} testid="kpi-ftfr" />
        <KPI
          label="Downtime"
          value={`${(downtime.total_hours ?? 0).toLocaleString()}h`}
          sub={`${downtime.case_count ?? 0} cases`}
          testid="kpi-downtime"
        />
        <KPI label="AI calls" value={kpis.ai_calls ?? 0} testid="kpi-ai-calls" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Revenue per engineer */}
        <Section icon={Wrench} title="Revenue per engineer" testid="reports-revenue">
          {revenueRows.length === 0 ? (
            <p className="text-xs opacity-60 italic">No invoiced labour in this window.</p>
          ) : (
            <ul className="space-y-2" data-testid="revenue-rows">
              {revenueRows.map((r) => (
                <li key={`${r.engineer_id || 'x'}-${r.engineer_name}`} data-testid={`revenue-row-${r.engineer_id || r.engineer_name}`}>
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-bold truncate">{r.engineer_name || 'Unattributed'}</span>
                    <span className="tabular-nums">{gbp(r.revenue)} · {r.hours}h · {r.cases} case{r.cases === 1 ? '' : 's'}</span>
                  </div>
                  <div className="h-1.5 rounded-full mt-1 overflow-hidden" style={{ background: 'var(--theme-border)' }}>
                    <div
                      className="h-full"
                      style={{
                        width: `${Math.max(2, Math.round((r.revenue / maxRevenue) * 100))}%`,
                        background: 'var(--color-brand-blue, #1d4ed8)',
                      }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Section>

        {/* SLA compliance */}
        <Section icon={ShieldCheck} title="SLA compliance" testid="reports-sla">
          <div className="flex items-baseline gap-3">
            <span className="text-3xl font-extrabold tabular-nums" data-testid="sla-rate">{pct(slaRate)}</span>
            <span className="text-xs opacity-70">{data.sla?.on_time ?? 0} on-time / {data.sla?.breached ?? 0} breached</span>
          </div>
          <div className="h-1.5 rounded-full mt-2 overflow-hidden" style={{ background: 'var(--theme-border)' }}>
            <div className="h-full" style={{ width: `${Math.round(slaRate * 100)}%`, background: slaRate >= 0.95 ? '#10b981' : slaRate >= 0.85 ? '#f59e0b' : '#ef4444' }} />
          </div>
          <ul className="mt-3 grid grid-cols-2 gap-2" data-testid="sla-by-priority">
            {Object.entries(data.sla?.by_priority || {}).map(([p, b]) => (
              <li key={p} className="text-xs px-2 py-1.5 rounded border flex items-center justify-between" style={{ borderColor: 'var(--theme-border)' }} data-testid={`sla-priority-${p}`}>
                <span><strong>{p.toUpperCase()}</strong> · {b.total}</span>
                <span className="tabular-nums">{b.total ? Math.round((b.on_time / b.total) * 100) : 0}% on-time</span>
              </li>
            ))}
          </ul>
        </Section>

        {/* FTFR detail */}
        <Section icon={Gauge} title="First-time-fix rate" testid="reports-ftfr">
          <div className="flex items-baseline gap-3">
            <span className="text-3xl font-extrabold tabular-nums" data-testid="ftfr-rate">{pct(ftfrRate)}</span>
            <span className="text-xs opacity-70">{data.ftfr?.ftf ?? 0} / {data.ftfr?.total_closed ?? 0} closed</span>
          </div>
          <div className="h-1.5 rounded-full mt-2 overflow-hidden" style={{ background: 'var(--theme-border)' }}>
            <div className="h-full" style={{ width: `${Math.round(ftfrRate * 100)}%`, background: ftfrRate >= 0.8 ? '#10b981' : ftfrRate >= 0.6 ? '#f59e0b' : '#ef4444' }} />
          </div>
          <p className="text-[11px] opacity-60 mt-2">A fix is &ldquo;first-time&rdquo; if the case never entered <code>paused_parts</code>. Lift this metric by improving van-stock accuracy and AI triage of likely parts.</p>
        </Section>

        {/* Asset downtime */}
        <Section icon={Timer} title="Top assets by downtime" testid="reports-downtime-assets">
          {topAssets.length === 0 ? (
            <p className="text-xs opacity-60 italic">No downtime recorded in this window.</p>
          ) : (
            <ul className="space-y-2" data-testid="downtime-asset-rows">
              {topAssets.map((r, idx) => (
                <li key={`${r.asset_id || r.asset_name}-${idx}`} data-testid={`downtime-asset-row-${idx}`}>
                  <div className="flex items-center justify-between text-xs gap-2">
                    <span className="font-bold truncate">{r.asset_name || 'Unknown asset'}</span>
                    <span className="tabular-nums whitespace-nowrap">
                      {r.downtime_hours.toLocaleString()}h · {r.case_count} case{r.case_count === 1 ? '' : 's'}
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
          <p className="text-[11px] opacity-60 mt-2">Total fleet downtime: <strong>{(downtime.total_hours ?? 0).toLocaleString()}h</strong> across {downtime.case_count ?? 0} cases. Use this to prioritise PPM frequency and replacement cycles.</p>
        </Section>

        {/* Site downtime */}
        <Section icon={MapPin} title="Top sites by downtime" testid="reports-downtime-sites">
          {topSites.length === 0 ? (
            <p className="text-xs opacity-60 italic">No site downtime in this window.</p>
          ) : (
            <ul className="space-y-2" data-testid="downtime-site-rows">
              {topSites.map((r, idx) => (
                <li key={`${r.site_id || r.site_name}-${idx}`} data-testid={`downtime-site-row-${idx}`}>
                  <div className="flex items-center justify-between text-xs gap-2">
                    <span className="font-bold truncate">{r.site_name || 'Unknown site'}</span>
                    <span className="tabular-nums whitespace-nowrap">
                      {r.downtime_hours.toLocaleString()}h · {r.case_count} case{r.case_count === 1 ? '' : 's'}
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

        {/* AI observability */}
        <Section icon={Sparkles} title="AI observability" testid="reports-ai">
          {aiRows.length === 0 ? (
            <p className="text-xs opacity-60 italic">No AI calls in this window.</p>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider opacity-70">
                  <th className="py-1">Kind</th>
                  <th className="py-1 text-right">Calls</th>
                  <th className="py-1 text-right">OK</th>
                  <th className="py-1 text-right">p50 ms</th>
                  <th className="py-1 text-right">p95 ms</th>
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
            <p className="text-[11px] opacity-70 mt-2 inline-flex items-center gap-1.5"><Activity size={11} /> {data.ai.totals.calls} total · {pct(data.ai.totals.ok_rate)} success</p>
          ) : null}
        </Section>
      </div>

      {/* Audit log */}
      <Section icon={ClipboardList} title="Audit feed" testid="reports-audit">
        {audit.length === 0 ? (
          <p className="text-xs opacity-60 italic">No events in this window.</p>
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
    </ServiceOpsShell>
  );
}
