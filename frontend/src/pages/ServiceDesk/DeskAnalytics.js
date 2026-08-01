/**
 * Owner Analytics — Iter 254.
 *
 * Sales-hook dashboard for the Service Desk: SLA compliance %, engineer
 * utilisation and revenue per job over a user-selectable date range
 * (presets + custom from/to). Backed by GET /api/svc/analytics/owner.
 */
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import {
  ComposedChart, Bar, Line, XAxis, YAxis, Tooltip, Legend,
  ResponsiveContainer, CartesianGrid,
} from 'recharts';
import { Card } from '@/components/ui/card';
import { Loader2, Timer, Gauge, PoundSterling, HardHat } from 'lucide-react';
import { authConfig } from './authConfig';

const PRESETS = [
  { id: '7', days: 7 },
  { id: '30', days: 30 },
  { id: '90', days: 90 },
];

const fmtPct = (v) => (v == null ? '—' : `${Math.round(v * 100)}%`);
const fmtGBP = (v) => `£${Number(v || 0).toLocaleString('en-GB', { maximumFractionDigits: 0 })}`;
const isoDaysAgo = (d) => new Date(Date.now() - d * 86400000).toISOString().slice(0, 10);

function KPI({ label, value, sub, testid }) {
  return (
    <Card className="p-4" data-testid={testid}>
      <div className="text-2xl font-bold text-zinc-900 dark:text-zinc-100 tabular-nums">{value}</div>
      <div className="text-xs text-zinc-500 mt-0.5">{label}</div>
      {sub && <div className="text-[11px] text-zinc-400 mt-0.5">{sub}</div>}
    </Card>
  );
}

function MiniBar({ pct, tone = 'bg-emerald-500' }) {
  return (
    <div className="h-2 rounded-full bg-zinc-100 dark:bg-zinc-800 overflow-hidden">
      <div className={`h-full rounded-full ${tone}`} style={{ width: `${Math.min(100, Math.round((pct || 0) * 100))}%` }} />
    </div>
  );
}

export default function DeskAnalytics({ API }) {
  const { t } = useTranslation();
  const [preset, setPreset] = useState('30');
  const [fromDate, setFromDate] = useState(isoDaysAgo(30));
  const [toDate, setToDate] = useState(isoDaysAgo(0));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async (fIso, tIso) => {
    setLoading(true);
    setError('');
    try {
      const r = await axios.get(`${API}/svc/analytics/owner`, {
        ...authConfig(),
        params: { from: `${fIso}T00:00:00+00:00`, to: `${tIso}T23:59:59+00:00` },
      });
      setData(r.data);
    } catch (e) {
      setError(e.response?.data?.detail || t('service.anl_load_err', 'Could not load analytics'));
    } finally {
      setLoading(false);
    }
  }, [API, t]);

  useEffect(() => { load(fromDate, toDate); /* initial */ // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pickPreset = (p) => {
    setPreset(p.id);
    const f = isoDaysAgo(p.days);
    const tt = isoDaysAgo(0);
    setFromDate(f); setToDate(tt);
    load(f, tt);
  };

  const applyCustom = () => { setPreset('custom'); load(fromDate, toDate); };

  const h = data?.headline || {};
  const rev = data?.revenue || {};
  const sla = data?.sla_by_priority || {};
  const trend = (data?.trend || []).map((w) => ({
    ...w,
    label: w.week.slice(5),
    sla_display: w.sla_pct == null ? null : Math.round(w.sla_pct * 100),
  }));

  return (
    <div className="space-y-6" data-testid="desk-analytics">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{t('service.anl_title', 'Analytics')}</h1>
          <p className="text-sm text-zinc-500 mt-1">{t('service.anl_subtitle', 'SLA compliance, engineer utilisation and revenue per job.')}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2" data-testid="analytics-range-controls">
          {PRESETS.map((p) => (
            <button
              key={p.id} onClick={() => pickPreset(p)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors ${
                preset === p.id ? 'bg-orange-500 text-white border-orange-500' : 'bg-white text-zinc-600 border-zinc-200 hover:bg-zinc-50'
              }`}
              data-testid={`analytics-range-${p.id}`}
            >
              {t('service.anl_range_days', '{{n}} days', { n: p.days })}
            </button>
          ))}
          <input type="date" value={fromDate} max={toDate} onChange={(e) => setFromDate(e.target.value)}
            className="px-2 py-1.5 rounded-lg border border-zinc-200 text-xs" data-testid="analytics-from-date" />
          <span className="text-xs text-zinc-400">→</span>
          <input type="date" value={toDate} min={fromDate} onChange={(e) => setToDate(e.target.value)}
            className="px-2 py-1.5 rounded-lg border border-zinc-200 text-xs" data-testid="analytics-to-date" />
          <button onClick={applyCustom}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-orange-500 hover:bg-orange-600 text-white"
            data-testid="analytics-apply-range">
            {t('service.anl_apply', 'Apply')}
          </button>
        </div>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-16 text-zinc-500 text-sm" data-testid="analytics-loading">
          <Loader2 size={16} className="mr-2 animate-spin" /> {t('service.anl_crunching', 'Crunching numbers…')}
        </div>
      )}
      {!loading && error && <div className="text-sm text-red-600" data-testid="analytics-error">{error}</div>}

      {!loading && data && (
        <>
          {/* KPI row */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3" data-testid="analytics-kpis">
            <KPI label={t('service.anl_kpi_sla_resolve', 'Resolve SLA met')} value={fmtPct(h.sla_resolve_rate)} testid="kpi-sla-resolve" />
            <KPI label={t('service.anl_kpi_sla_response', 'Response SLA met')} value={fmtPct(h.sla_response_rate)} testid="kpi-sla-response" />
            <KPI label={t('service.anl_kpi_avg_response', 'Avg response')} value={`${h.avg_response_h ?? 0}h`} testid="kpi-avg-response" />
            <KPI label={t('service.anl_kpi_avg_resolve', 'Avg resolve')} value={`${h.avg_resolve_h ?? 0}h`} testid="kpi-avg-resolve" />
            <KPI label={t('service.anl_kpi_cases_closed', 'Cases closed')} value={h.cases_closed ?? 0} sub={t('service.anl_cases_sub', '{{raised}} raised · {{open}} open', { raised: h.cases_created ?? 0, open: h.open_cases ?? 0 })} testid="kpi-cases-closed" />
            <KPI label={t('service.anl_kpi_rev_per_job', 'Revenue / job')} value={fmtGBP(rev.avg_per_job)} sub={t('service.anl_jobs_billed', '{{n}} jobs billed', { n: rev.jobs_billed || 0 })} testid="kpi-revenue-per-job" />
          </div>

          {/* Weekly trend */}
          <Card className="p-5" data-testid="analytics-trend">
            <div className="flex items-center gap-2 mb-4">
              <Gauge className="w-4 h-4 text-zinc-500" />
              <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{t('service.anl_weekly', 'Weekly cases & SLA on-time %')}</div>
            </div>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={trend} margin={{ top: 5, right: 10, bottom: 0, left: -20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                  <YAxis yAxisId="n" tick={{ fontSize: 11 }} allowDecimals={false} />
                  <YAxis yAxisId="pct" orientation="right" domain={[0, 100]} tick={{ fontSize: 11 }} unit="%" />
                  <Tooltip />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar yAxisId="n" dataKey="created" name={t('service.anl_raised', 'Raised')} fill="#94a3b8" radius={[3, 3, 0, 0]} />
                  <Bar yAxisId="n" dataKey="closed" name={t('service.anl_closed', 'Closed')} fill="#f97316" radius={[3, 3, 0, 0]} />
                  <Line yAxisId="pct" dataKey="sla_display" name={t('service.anl_sla_ontime', 'SLA on-time %')} stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} connectNulls />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* SLA by priority */}
            <Card className="p-5" data-testid="analytics-sla-priority">
              <div className="flex items-center gap-2 mb-4">
                <Timer className="w-4 h-4 text-zinc-500" />
                <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{t('service.anl_sla_by_priority', 'SLA compliance by priority')}</div>
              </div>
              <div className="space-y-3">
                {['p1', 'p2', 'p3', 'p4'].map((p) => {
                  const b = sla[p] || {};
                  const respPct = b.response_total ? b.response_on_time / b.response_total : null;
                  const resPct = b.resolve_total ? b.resolve_on_time / b.resolve_total : null;
                  return (
                    <div key={p} data-testid={`sla-priority-${p}`}>
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className="font-semibold uppercase text-zinc-700">{p}</span>
                        <span className="text-zinc-500">
                          {t('service.anl_response', 'response')} {fmtPct(respPct)} ({b.response_on_time || 0}/{b.response_total || 0}) ·
                          {' '}{t('service.anl_resolve', 'resolve')} {fmtPct(resPct)} ({b.resolve_on_time || 0}/{b.resolve_total || 0})
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <MiniBar pct={respPct} tone="bg-sky-500" />
                        <MiniBar pct={resPct} tone="bg-emerald-500" />
                      </div>
                    </div>
                  );
                })}
                <div className="flex gap-4 text-[11px] text-zinc-400 pt-1">
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-sky-500 inline-block" /> {t('service.anl_response_cap', 'Response')}</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" /> {t('service.anl_resolve_cap', 'Resolve')}</span>
                </div>
              </div>
            </Card>

            {/* Revenue */}
            <Card className="p-5" data-testid="analytics-revenue">
              <div className="flex items-center gap-2 mb-4">
                <PoundSterling className="w-4 h-4 text-zinc-500" />
                <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{t('service.anl_revenue', 'Revenue')}</div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-2xl font-bold tabular-nums" data-testid="revenue-total">{fmtGBP(rev.total)}</div>
                  <div className="text-xs text-zinc-500">{t('service.anl_total_billed', 'Total billed')}</div>
                </div>
                <div>
                  <div className="text-2xl font-bold tabular-nums">{fmtGBP(rev.avg_per_job)}</div>
                  <div className="text-xs text-zinc-500">{t('service.anl_avg_per_job', 'Average per job')}</div>
                </div>
                <div>
                  <div className="text-lg font-semibold tabular-nums text-emerald-600">{fmtGBP(rev.paid)}</div>
                  <div className="text-xs text-zinc-500">{t('service.anl_paid', 'Paid')}</div>
                </div>
                <div>
                  <div className="text-lg font-semibold tabular-nums text-amber-600">{fmtGBP(rev.outstanding)}</div>
                  <div className="text-xs text-zinc-500">{t('service.anl_outstanding', 'Outstanding')}</div>
                </div>
              </div>
              <div className="text-[11px] text-zinc-400 mt-3">
                {t('service.anl_rev_footer', '{{inv}} invoices raised · {{jobs}} jobs billed in range', { inv: rev.invoices_raised || 0, jobs: rev.jobs_billed || 0 })}
              </div>
            </Card>
          </div>

          {/* Engineer utilisation */}
          <Card className="p-5" data-testid="analytics-engineers">
            <div className="flex items-center gap-2 mb-4">
              <HardHat className="w-4 h-4 text-zinc-500" />
              <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{t('service.anl_engineer_util', 'Engineer utilisation')}</div>
              <span className="text-[11px] text-zinc-400 ml-auto">{t('service.anl_capacity', 'capacity = 8h × weekdays in range')}</span>
            </div>
            {(data.engineers || []).length === 0 ? (
              <div className="text-sm text-zinc-500" data-testid="engineers-empty">{t('service.anl_no_engineers', 'No active engineers yet.')}</div>
            ) : (
              <div className="space-y-3">
                {data.engineers.map((e) => (
                  <div key={e.engineer_id} className="grid grid-cols-12 gap-3 items-center" data-testid={`engineer-row-${e.engineer_id}`}>
                    <div className="col-span-4 sm:col-span-3 text-sm font-medium text-zinc-800 truncate">{e.name}</div>
                    <div className="col-span-4 sm:col-span-5">
                      <MiniBar pct={e.utilisation_pct} tone="bg-orange-500" />
                    </div>
                    <div className="col-span-4 text-right text-xs text-zinc-500 tabular-nums">
                      {t('service.anl_eng_stats', '{{pct}}% · {{hours}}h logged · {{done}} done · {{open}} open', { pct: Math.round((e.utilisation_pct || 0) * 100), hours: e.hours_logged, done: e.jobs_completed, open: e.open_workload })}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
