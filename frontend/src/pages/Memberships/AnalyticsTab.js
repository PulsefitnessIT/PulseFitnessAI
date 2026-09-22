/**
 * Pulse Fitness Memberships — Analytics & Reporting engine.
 *
 * Role-based dashboards (Manager / Regional / Director) with five
 * sub-sections:
 *   • Overview   — MRR, ARPU, churn, revenue trend, forecast, mix
 *   • Retention  — cohorts, segmentation, early churn, at-risk
 *   • Classes    — occupancy rankings, instructor scorecards, heatmap
 *   • Operations — site comparison, alerts, booking conversion
 *   • AI Insights — executive brief, at-risk list, push to CRM
 *
 * Charts via Recharts. Cache-friendly (backend caches 60s per query).
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { Line, BarChart, Bar, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts';
import {
  TrendingUp, TrendingDown, Users, PoundSterling, Activity,
  AlertTriangle, Sparkles, Download, FileText, UserMinus, Target,
  Zap, Calendar as CalIcon, Gauge, ArrowRight, RefreshCw, X, Mail, Brain,
} from 'lucide-react';
import StudioBrainTab from '@/pages/Memberships/StudioBrainTab';
import AIInsightsTab from '@/pages/Memberships/AIInsightsTab';
import SubTabBar from '@/components/shared/SubTabBar';

const SECTIONS = [
  { id: 'overview',  label: 'Overview',   icon: Gauge },
  { id: 'retention', label: 'Retention',  icon: UserMinus },
  { id: 'classes',   label: 'Classes',    icon: Activity },
  { id: 'operations',label: 'Operations', icon: Target },
  { id: 'studio-brain', label: 'Studio Brain', icon: Brain },
  { id: 'ai-insights',  label: 'AI Insights',  icon: Sparkles },
];

const ROLES = [
  { id: 'manager',  label: 'Gym manager',    days: 30 },
  { id: 'regional', label: 'Regional mgr',   days: 90 },
  { id: 'director', label: 'Director',       days: 180 },
];

const CYAN = 'var(--color-brand-cyan)';
const PIE_PALETTE = ['var(--color-brand-cyan)', '#22D3EE', 'var(--color-violet-400)', '#F472B6', '#FCD34D', 'var(--color-success-light)'];

export default function AnalyticsTab({ API, headers }) {
  const { t } = useTranslation();
  const [section, setSection] = useState('overview');
  const [role, setRole] = useState('manager');
  const [drill, setDrill] = useState(null);  // {kpi, title}

  const days = ROLES.find(r => r.id === role)?.days || 30;
  const range = useMemo(() => {
    const to = new Date();
    const from = new Date(Date.now() - days * 86400_000);
    return { from: from.toISOString(), to: to.toISOString() };
  }, [days]);

  const openDrill = (kpi, title) => setDrill({ kpi, title });

  return (
    <div data-testid="mbr-analytics">
      <div className="flex items-start justify-end gap-4 mb-6">
        <div className="flex items-center gap-2">
          <DigestButton API={API} headers={headers} />
          <RoleSwitcher role={role} setRole={setRole} />
        </div>
      </div>

      <SubTabBar
        tabs={SECTIONS.map(s => ({ ...s, label: t(`memberships_console.an_sec_${s.id}`, s.label) }))}
        active={section}
        onChange={setSection}
        testId="mbr-analytics-tab"
      />

      {section === 'overview'   && <OverviewSection  API={API} headers={headers} range={range} openDrill={openDrill} />}
      {section === 'retention'  && <RetentionSection API={API} headers={headers} range={range} openDrill={openDrill} />}
      {section === 'classes'    && <ClassesSection   API={API} headers={headers} range={range} />}
      {section === 'operations' && <OperationsSection API={API} headers={headers} range={range} openDrill={openDrill} />}
      {section === 'studio-brain' && <StudioBrainTab API={API} headers={headers} />}
      {section === 'ai-insights'  && (
        <div className="space-y-6">
          <AISection API={API} headers={headers} range={range} />
          <AIInsightsTab API={API} headers={headers} />
        </div>
      )}

      {drill && <DrillDrawer API={API} headers={headers} range={range} drill={drill} onClose={() => setDrill(null)} />}
    </div>
  );
}

/* ───────────────────────── Weekly digest button ───────────────────────── */

function DigestButton({ API, headers }) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const onClick = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/memberships/analytics/send-weekly-digest`, {}, { headers });
      if (r.data.sent?.length) notify.success(r.data.sent.length === 1 ? t('memberships_console.an_digest_sent_one', 'Digest sent to 1 recipient') : t('memberships_console.an_digest_sent_many', 'Digest sent to {{n}} recipients', { n: r.data.sent.length }));
      else if (r.data.skipped === 'already_sent_this_week') notify.info(t('memberships_console.an_digest_already', 'Already sent this week — the next auto-run is Monday.'));
      else notify.info(t('memberships_console.an_digest_none', 'Digest built · no operator recipients configured yet.'));
    } catch (e) { notifyApiError(notify, e, t('memberships_console.an_digest_failed', 'Digest failed')); }
    finally { setBusy(false); }
  };
  return (
    <button onClick={onClick} disabled={busy}
      className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 text-xs font-bold disabled:opacity-40"
      data-testid="mbr-send-digest">
      <Mail size={13} /> {busy ? t('memberships_console.an_sending', 'Sending…') : t('memberships_console.an_send_digest', 'Send weekly digest')}
    </button>
  );
}

/* ───────────────────────── Drill-down drawer ───────────────────────── */

function DrillDrawer({ API, headers, range, drill, onClose }) {
  const { t } = useTranslation();
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    (async () => {
      setRows(null); setErr(false);
      try {
        const r = await axios.get(
          `${API}/memberships/analytics/members-by-kpi?kpi=${drill.kpi}&from=${range.from}&to=${range.to}&limit=200`,
          { headers });
        setRows(r.data.members || []);
      } catch { setErr(true); }
    })();
  }, [API, headers, range, drill]);

  return (
    <div className="fixed inset-0 z-[90]" data-testid="mbr-drill-drawer">
      <div className="absolute inset-0 bg-black/70" onClick={onClose} />
      <aside className="absolute top-0 right-0 bottom-0 w-full max-w-[560px] bg-[var(--color-ink)] border-l border-white/10 shadow-2xl flex flex-col">
        <div className="px-6 py-5 border-b border-white/10 flex items-center justify-between">
          <div>
            <div className="text-[10px] font-bold tracking-[0.25em] uppercase text-[var(--color-brand-cyan)]">{t('memberships_console.an_drill_kicker', 'Drill-down')}</div>
            <h2 className="text-xl font-extrabold mt-0.5">{drill.title}</h2>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg text-white/60 hover:bg-white/10 hover:text-white" data-testid="mbr-drill-close">
            <X size={16} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {!rows && !err && <div className="p-10 text-center text-white/40 text-sm flex items-center justify-center gap-2"><RefreshCw size={14} className="animate-spin" /> {t('memberships_console.an_loading', 'Loading…')}</div>}
          {err && <div className="p-10 text-center text-rose-400 text-sm">{t('memberships_console.an_drill_err', 'Failed to load · retry in a moment.')}</div>}
          {rows && rows.length === 0 && <div className="p-10 text-center text-white/50 text-sm">{t('memberships_console.an_drill_empty', 'Nothing here — zero is a good number for this KPI.')}</div>}
          {rows && rows.length > 0 && (
            <ul className="divide-y divide-white/5">
              {rows.map((m) => (
                <li key={m.id || m.email} className="px-6 py-3 flex items-center justify-between text-sm" data-testid={`mbr-drill-row-${m.id}`}>
                  <div>
                    <div className="font-semibold">{m.name}</div>
                    <div className="text-[11px] text-white/50">{m.email}{m.cancel_reason ? ` · ${m.cancel_reason}` : ''}</div>
                  </div>
                  <div className="text-right">
                    {m.lifetime_value_gbp != null && <div className="text-[11px] text-[var(--color-brand-cyan)] font-bold">£{m.lifetime_value_gbp}</div>}
                    {m.amount_gbp != null && <div className="text-[11px] text-rose-400 font-bold">{t('memberships_console.an_amount_failed', '£{{n}} failed', { n: m.amount_gbp })}</div>}
                    {m.visits_60d != null && <div className="text-[11px] text-white/50">{t('memberships_console.an_visits', '{{n}} visits', { n: m.visits_60d })}</div>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="px-6 py-3 border-t border-white/10 text-[11px] text-white/40">
          {rows?.length ? (rows.length === 1 ? t('memberships_console.an_members_one', '1 member') : t('memberships_console.an_members_many', '{{n}} members', { n: rows.length })) : ''}
        </div>
      </aside>
    </div>
  );
}

/* ───────────────────────── Role switcher ───────────────────────── */

function RoleSwitcher({ role, setRole }) {
  const { t } = useTranslation();
  return (
    <div
      className="flex items-center gap-1 p-1 rounded-lg border"
      style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}
      data-testid="mbr-role-switcher"
    >
      {ROLES.map(r => (
        <button
          key={r.id}
          onClick={() => setRole(r.id)}
          className={`px-3 py-1.5 text-xs font-bold rounded transition ${role === r.id ? 'bg-[var(--color-brand-cyan)] text-black' : 'hover:opacity-80'}`}
          style={role === r.id ? undefined : { color: 'var(--theme-text-muted)' }}
          data-testid={`mbr-role-${r.id}`}
        >{t(`memberships_console.an_role_${r.id}`, r.label)}</button>
      ))}
    </div>
  );
}

/* ───────────────────────── Overview ───────────────────────── */

function OverviewSection({ API, headers, range, openDrill }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(
        `${API}/memberships/analytics/overview?from=${range.from}&to=${range.to}&period=monthly`,
        { headers });
      setData(r.data);
    } catch { notify.error(t('memberships_console.an_ov_load_err', 'Failed to load analytics overview')); }
    finally { setLoading(false); }
  }, [API, headers, range, t]);
  useEffect(() => { load(); }, [load]);

  if (loading || !data) return <LoadingPane />;

  const k = data.kpis;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <KpiCard testId="mrr" label={t('memberships_console.an_kpi_mrr', 'MRR')}             value={`£${k.mrr_gbp.toLocaleString()}`} icon={PoundSterling} tone="cyan" />
        <KpiCard testId="arpu" label={t('memberships_console.an_kpi_arpu', 'ARPU')}            value={`£${k.arpu_gbp}`} icon={Users} tone="emerald" />
        <KpiCard testId="active-members" label={t('memberships_console.an_kpi_active', 'Active members')}  value={k.active_members} icon={Users} tone="cyan"
                 onClick={() => openDrill?.('active_members', t('memberships_console.an_kpi_active', 'Active members'))} />
        <KpiCard testId="net-growth" label={t('memberships_console.an_kpi_net_growth', 'Net growth')}      value={`${k.net_growth >= 0 ? '+' : ''}${k.net_growth}`} icon={k.net_growth >= 0 ? TrendingUp : TrendingDown} tone={k.net_growth >= 0 ? 'emerald' : 'rose'}
                 onClick={() => openDrill?.('new_members', t('memberships_console.an_drill_new_members', 'New members'))} />
        <KpiCard testId="churn-pct" label={t('memberships_console.an_kpi_churn', 'Churn %')}         value={`${k.churn_pct}%`} icon={UserMinus} tone={k.churn_pct > 5 ? 'rose' : 'neutral'}
                 onClick={() => openDrill?.('cancellations', t('memberships_console.an_drill_cancellations', 'Cancellations'))} />
        <KpiCard testId="revenue" label={t('memberships_console.an_kpi_revenue', 'Revenue')}         value={`£${k.revenue_gbp.toLocaleString()}`} icon={PoundSterling} tone="cyan" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <ChartCard title={t('memberships_console.an_ct_rev_trend', 'Revenue trend')} subtitle={t('memberships_console.an_ct_rev_trend_sub', 'Paid transactions by month · dashed line + shaded band = forecast with 1σ confidence')} className="lg:col-span-2">
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={[...data.trend, ...(data.revenue_forecast || []).map(f => ({
              bucket: f.bucket,
              forecast: f.revenue_gbp,
              forecast_lower: f.lower_gbp,
              forecast_upper: f.upper_gbp,
            }))]} margin={{ top: 10, right: 15, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="rev" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={CYAN} stopOpacity={0.6} />
                  <stop offset="95%" stopColor={CYAN} stopOpacity={0} />
                </linearGradient>
                <linearGradient id="band" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--color-warning-alt)" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="var(--color-warning-alt)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />
              <XAxis dataKey="bucket" stroke="rgba(255,255,255,0.5)" style={{ fontSize: 11 }} />
              <YAxis stroke="rgba(255,255,255,0.5)" style={{ fontSize: 11 }} />
              <Tooltip contentStyle={{ background: 'var(--color-ink)', border: '1px solid rgba(255,255,255,0.15)' }} />
              <Area dataKey="revenue" stroke={CYAN} fill="url(#rev)" name={t('memberships_console.an_ser_revenue', 'Revenue (£)')} />
              <Area dataKey="forecast_upper" stroke="none" fill="url(#band)" name={t('memberships_console.an_ser_fc_upper', 'Forecast upper (£)')} />
              <Area dataKey="forecast_lower" stroke="none" fill="var(--color-surface-darker)" fillOpacity={1} name={t('memberships_console.an_ser_fc_lower', 'Forecast lower (£)')} />
              <Line dataKey="forecast" stroke="var(--color-warning-alt)" strokeDasharray="4 4" name={t('memberships_console.an_ser_forecast', 'Forecast (£)')} />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title={t('memberships_console.an_ct_rev_product', 'Revenue by product')}>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={data.revenue_by_product} dataKey="revenue_gbp" nameKey="product" cx="50%" cy="50%" outerRadius={80} innerRadius={40} paddingAngle={2}>
                {(data.revenue_by_product || []).map((_, idx) => <Cell key={idx} fill={PIE_PALETTE[idx % PIE_PALETTE.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ background: 'var(--color-ink)', border: '1px solid rgba(255,255,255,0.15)' }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title={t('memberships_console.an_ct_growth', 'Member growth')} subtitle={t('memberships_console.an_ct_growth_sub', 'New vs cancelled, by month')}>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={data.trend}>
              <CartesianGrid stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />
              <XAxis dataKey="bucket" stroke="rgba(255,255,255,0.5)" style={{ fontSize: 11 }} />
              <YAxis stroke="rgba(255,255,255,0.5)" style={{ fontSize: 11 }} />
              <Tooltip contentStyle={{ background: 'var(--color-ink)', border: '1px solid rgba(255,255,255,0.15)' }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="new"   fill="var(--color-success-light)" name={t('memberships_console.an_ser_new', 'New members')} />
              <Bar dataKey="churn" fill="var(--color-rose)" name={t('memberships_console.an_ser_cancel', 'Cancellations')} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title={t('memberships_console.an_ct_mix', 'Membership mix')}>
          <div className="space-y-2 pt-2">
            {(data.membership_mix || []).map((m, idx) => {
              const total = (data.membership_mix || []).reduce((s, x) => s + x.count, 0) || 1;
              const pct = Math.round((m.count / total) * 100);
              return (
                <div key={idx} data-testid={`mbr-mix-${idx}`}>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="text-white/80 font-semibold">{m.plan}</span>
                    <span className="text-white/50">{m.count} · {pct}%</span>
                  </div>
                  <div className="h-2 rounded bg-white/5 overflow-hidden">
                    <div className="h-full rounded" style={{ width: `${pct}%`, background: PIE_PALETTE[idx % PIE_PALETTE.length] }} />
                  </div>
                </div>
              );
            })}
          </div>
        </ChartCard>
      </div>

      <div className="flex items-center gap-2">
        <ExportButton API={API} headers={headers} report="overview" range={range} label={t('memberships_console.an_exp_overview', 'Export overview')} />
        <ExportButton API={API} headers={headers} report="overview" range={range} pdf label={t('memberships_console.an_exp_pdf', 'Weekly PDF brief')} />
      </div>
    </div>
  );
}

/* ───────────────────────── Retention ───────────────────────── */

function RetentionSection({ API, headers, range }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const r = await axios.get(
          `${API}/memberships/analytics/retention?from=${range.from}&to=${range.to}`,
          { headers });
        setData(r.data);
      } catch { notify.error(t('memberships_console.an_ret_load_err', 'Failed to load retention')); }
      finally { setLoading(false); }
    })();
  }, [API, headers, range, t]);
  if (loading || !data) return <LoadingPane />;

  const k = data.kpis;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard testId="cancellations" label={t('memberships_console.an_drill_cancellations', 'Cancellations')}      value={k.churn_total} icon={UserMinus} tone="rose" />
        <KpiCard testId="avg-lifespan" label={t('memberships_console.an_kpi_avg_lifespan', 'Avg lifespan')}       value={`${k.avg_lifespan_days}d`} icon={CalIcon} tone="cyan" />
        <KpiCard testId="early-churn-30d" label={t('memberships_console.an_kpi_early_30', 'Early churn (30d)')}  value={k.early_churn_30d} icon={Zap} tone={k.early_churn_30d > 0 ? 'amber' : 'neutral'} />
        <KpiCard testId="early-churn-60d" label={t('memberships_console.an_kpi_early_60', 'Early churn (60d)')}  value={k.early_churn_60d} icon={Zap} tone={k.early_churn_60d > 0 ? 'amber' : 'neutral'} />
      </div>

      <ChartCard title={t('memberships_console.an_ct_segmentation', 'Engagement segmentation')} subtitle={t('memberships_console.an_ct_segmentation_sub', 'Last 60 days of visits & attendance')}>
        <div className="grid grid-cols-4 gap-3 mt-2">
          {Object.entries(data.segments).map(([key, count], _idx) => {
            const labels = {
              highly_engaged: { label: t('memberships_console.an_seg_highly', 'Highly engaged'), color: 'var(--color-success-light)' },
              regular:        { label: t('memberships_console.an_seg_regular', 'Regular'),        color: CYAN },
              at_risk:        { label: t('memberships_console.an_seg_at_risk', 'At risk'),        color: 'var(--color-warning-alt)' },
              inactive:       { label: t('memberships_console.an_seg_inactive', 'Inactive'),       color: 'var(--color-rose)' },
            };
            const l = labels[key];
            return (
              <div key={key} className="p-4 rounded-xl border border-white/10 bg-white/5" data-testid={`mbr-segment-${key}`}>
                <div className="text-[10px] font-bold tracking-wider uppercase" style={{ color: l.color }}>{l.label}</div>
                <div className="text-3xl font-extrabold mt-1">{count}</div>
                <div className="text-[11px] text-white/50 mt-1">{t('memberships_console.an_seg_members_shown', '{{n}} members shown', { n: data.segment_members[key]?.length || 0 })}</div>
              </div>
            );
          })}
        </div>
      </ChartCard>

      <ChartCard title={t('memberships_console.an_ct_cohort', 'Retention cohort matrix')} subtitle={t('memberships_console.an_ct_cohort_sub', '% of cohort still active after N months')}>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-white/50">
                <th className="text-left p-2 font-semibold">{t('memberships_console.an_th_cohort', 'Cohort')}</th>
                <th className="text-left p-2 font-semibold">{t('memberships_console.an_th_size', 'Size')}</th>
                {[0,1,2,3,4,5,6].map(m => <th key={m} className="p-2 text-center font-semibold">M{m}</th>)}
              </tr>
            </thead>
            <tbody>
              {(data.cohort_matrix || []).map((c, idx) => (
                <tr key={idx} className="border-t border-white/5" data-testid={`mbr-cohort-${idx}`}>
                  <td className="p-2 font-semibold">{c.cohort}</td>
                  <td className="p-2 text-white/60">{c.size}</td>
                  {c.retention.map((r, i) => {
                    const alpha = Math.max(0.1, r.pct / 100);
                    return (
                      <td key={i} className="p-0 text-center">
                        <div className="mx-1 my-0.5 py-2 rounded text-[11px] font-bold" style={{
                          background: `rgba(25, 205, 255, ${alpha})`, color: alpha > 0.5 ? '#000' : '#fff',
                        }}>{r.pct}%</div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ChartCard>

      <ChartCard title={t('memberships_console.an_ct_churn_plan', 'Churn by plan')}>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data.churn_by_plan} layout="vertical" margin={{ left: 30 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />
            <XAxis type="number" stroke="rgba(255,255,255,0.5)" style={{ fontSize: 11 }} />
            <YAxis type="category" dataKey="plan" stroke="rgba(255,255,255,0.5)" style={{ fontSize: 11 }} width={110} />
            <Tooltip contentStyle={{ background: 'var(--color-ink)', border: '1px solid rgba(255,255,255,0.15)' }} />
            <Bar dataKey="count" fill="var(--color-rose)" />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      <ExportButton API={API} headers={headers} report="retention" range={range} label={t('memberships_console.an_exp_retention', 'Export retention')} />

      <ReferralsBlock API={API} headers={headers} range={range} />
    </div>
  );
}

function ReferralsBlock({ API, headers, range }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(
          `${API}/memberships/analytics/referrals?from=${range.from}&to=${range.to}`,
          { headers });
        setData(r.data);
      } catch { /* silent — optional feature */ }
    })();
  }, [API, headers, range]);
  if (!data) return null;
  const k = data.kpis;
  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mt-4" data-testid="mbr-referrals-kpis">
        <KpiCard testId="referrals" label={t('memberships_console.an_kpi_referrals', 'Referrals')}      value={k.total} icon={Sparkles} tone="cyan" />
        <KpiCard testId="earned" label={t('memberships_console.an_kpi_earned', 'Earned')}         value={k.earned} icon={Sparkles} tone="emerald" />
        <KpiCard testId="pending" label={t('memberships_console.an_kpi_pending', 'Pending')}        value={k.pending} icon={Sparkles} tone="amber" />
        <KpiCard testId="conversion" label={t('memberships_console.an_kpi_conversion', 'Conversion')}     value={`${k.conversion_pct}%`} icon={ArrowRight} tone="cyan" />
        <KpiCard testId="credit-paid" label={t('memberships_console.an_kpi_credit_paid', 'Credit paid')}    value={`£${k.credit_paid_gbp}`} icon={PoundSterling} tone="emerald" />
      </div>

      <ChartCard title={t('memberships_console.an_ct_top_referrers', 'Top referrers')} subtitle={t('memberships_console.an_ct_top_referrers_sub', 'Say thanks to the members growing your studio')}>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-white/50">
              <tr>
                <th className="text-left p-2 font-semibold">{t('memberships_console.an_th_member', 'Member')}</th>
                <th className="text-left p-2 font-semibold">{t('memberships_console.an_th_code', 'Code')}</th>
                <th className="text-right p-2 font-semibold">{t('memberships_console.an_th_referred', 'Referred')}</th>
                <th className="text-right p-2 font-semibold">{t('memberships_console.an_th_converted', 'Converted')}</th>
                <th className="text-right p-2 font-semibold">{t('memberships_console.an_kpi_conversion', 'Conversion')}</th>
                <th className="text-right p-2 font-semibold">{t('memberships_console.an_th_credit_earned', 'Credit earned')}</th>
              </tr>
            </thead>
            <tbody>
              {data.top_referrers.map(r => (
                <tr key={r.member_id} className="border-t border-white/5" data-testid={`mbr-referrer-${r.member_id}`}>
                  <td className="p-2 font-semibold">{r.name}<div className="text-[10px] text-white/40">{r.email}</div></td>
                  <td className="p-2 font-mono text-[var(--color-brand-cyan)]">{r.referral_code || '—'}</td>
                  <td className="p-2 text-right text-white/70">{r.total}</td>
                  <td className="p-2 text-right text-emerald-400 font-bold">{r.earned}</td>
                  <td className="p-2 text-right text-white/70">{r.conversion_pct}%</td>
                  <td className="p-2 text-right text-[var(--color-brand-cyan)] font-bold">£{r.credit_earned_gbp}</td>
                </tr>
              ))}
              {data.top_referrers.length === 0 && (
                <tr><td colSpan={6} className="p-6 text-center text-white/50">{t('memberships_console.an_no_referrals', 'No referrals yet — prompt your superfans!')}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </ChartCard>
    </>
  );
}

/* ───────────────────────── Classes ───────────────────────── */

function ClassesSection({ API, headers, range }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const r = await axios.get(
          `${API}/memberships/analytics/classes?from=${range.from}&to=${range.to}`,
          { headers });
        setData(r.data);
      } catch { notify.error(t('memberships_console.an_cls_load_err', 'Failed to load class analytics')); }
      finally { setLoading(false); }
    })();
  }, [API, headers, range, t]);
  if (loading || !data) return <LoadingPane />;

  const k = data.kpis;
  const maxHeat = Math.max(1, ...data.heatmap.flat());
  const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <KpiCard testId="sessions" label={t('memberships_console.an_kpi_sessions', 'Sessions')}          value={k.total_sessions} icon={CalIcon} tone="cyan" />
        <KpiCard testId="occupancy" label={t('memberships_console.an_kpi_occupancy', 'Occupancy')}         value={`${k.avg_occupancy_pct}%`} icon={Gauge} tone={k.avg_occupancy_pct >= 70 ? 'emerald' : 'amber'} />
        <KpiCard testId="no-show" label={t('memberships_console.an_kpi_no_show', 'No-show')}           value={`${k.no_show_pct}%`} icon={AlertTriangle} tone={k.no_show_pct > 15 ? 'rose' : 'neutral'} />
        <KpiCard testId="waitlist-conv" label={t('memberships_console.an_kpi_waitlist_conv', 'Waitlist conv')}     value={`${k.waitlist_conversion_pct}%`} icon={ArrowRight} tone="cyan" />
        <KpiCard testId="late-cancels" label={t('memberships_console.an_kpi_late_cancels', 'Late cancels')}      value={k.late_cancels} icon={UserMinus} tone="neutral" />
      </div>

      <ChartCard title={t('memberships_console.an_ct_heatmap', 'Booking heatmap')} subtitle={t('memberships_console.an_ct_heatmap_sub', 'Day-of-week × hour-of-day')}>
        <div className="overflow-x-auto">
          <div className="grid grid-cols-[50px_repeat(24,minmax(20px,1fr))] gap-0.5 text-[9px] text-white/40">
            <div></div>
            {Array.from({ length: 24 }).map((_, h) => <div key={h} className="text-center">{h}</div>)}
            {data.heatmap.map((row, d) => (
              <React.Fragment key={d}>
                <div className="text-right pr-2 font-semibold text-white/70 self-center">{t(`memberships_console.sb_day_${d}`, DAYS[d])}</div>
                {row.map((v, h) => {
                  const alpha = v > 0 ? Math.max(0.15, v / maxHeat) : 0;
                  return (
                    <div key={h} className="h-7 rounded" style={{ background: v ? `rgba(25, 205, 255, ${alpha})` : 'rgba(255,255,255,0.04)' }} title={`${t(`memberships_console.sb_day_${d}`, DAYS[d])} ${h}:00 — ${v} bookings`} data-testid={`mbr-heat-${d}-${h}`} />
                  );
                })}
              </React.Fragment>
            ))}
          </div>
        </div>
      </ChartCard>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title={t('memberships_console.an_ct_top_classes', 'Top classes')} subtitle={t('memberships_console.an_ct_top_classes_sub', 'By occupancy')}>
          <div className="space-y-2">
            {data.classes_ranked.slice(0, 8).map((c, idx) => (
              <ClassRow key={c.template_id} c={c} idx={idx} />
            ))}
          </div>
        </ChartCard>
        <ChartCard title={t('memberships_console.an_ct_underperf', 'Underperforming classes')} subtitle={t('memberships_console.an_ct_underperf_sub', 'Occupancy < 40%')}>
          <div className="space-y-2">
            {data.underperforming.length === 0 && (
              <div className="text-xs text-white/50 py-6 text-center">{t('memberships_console.an_all_above_40', 'All classes running above 40% occupancy')} 🎉</div>
            )}
            {data.underperforming.map((c) => <ClassRow key={c.template_id} c={c} tone="rose" />)}
          </div>
        </ChartCard>
      </div>

      <ChartCard title={t('memberships_console.an_ct_instructors', 'Instructor scorecards')} subtitle={t('memberships_console.an_ct_instructors_sub', 'Sessions, retention impact, payout')}>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-white/50">
              <tr>
                <th className="text-left p-2 font-semibold">{t('memberships_console.an_th_instructor', 'Instructor')}</th>
                <th className="text-right p-2 font-semibold">{t('memberships_console.an_kpi_sessions', 'Sessions')}</th>
                <th className="text-right p-2 font-semibold">{t('memberships_console.an_th_attended', 'Attended')}</th>
                <th className="text-right p-2 font-semibold">{t('memberships_console.an_kpi_occupancy', 'Occupancy')}</th>
                <th className="text-right p-2 font-semibold">{t('memberships_console.an_kpi_no_show', 'No-show')}</th>
                <th className="text-right p-2 font-semibold">{t('memberships_console.an_th_unique_members', 'Unique members')}</th>
                <th className="text-right p-2 font-semibold">{t('memberships_console.an_th_retention_impact', 'Retention impact')}</th>
                <th className="text-right p-2 font-semibold">{t('memberships_console.an_th_payout', 'Payout')}</th>
              </tr>
            </thead>
            <tbody>
              {data.instructors.map(i => (
                <tr key={i.user_id} className="border-t border-white/5" data-testid={`mbr-instructor-${i.user_id}`}>
                  <td className="p-2 font-semibold">{i.name}</td>
                  <td className="p-2 text-right text-white/70">{i.sessions}</td>
                  <td className="p-2 text-right text-white/70">{i.attended}</td>
                  <td className="p-2 text-right font-semibold" style={{ color: i.occupancy_pct >= 70 ? 'var(--color-success-light)' : i.occupancy_pct >= 50 ? CYAN : 'var(--color-warning-alt)' }}>{i.occupancy_pct}%</td>
                  <td className="p-2 text-right text-white/70">{i.no_show_pct}%</td>
                  <td className="p-2 text-right text-white/70">{i.unique_members}</td>
                  <td className="p-2 text-right font-semibold text-[var(--color-brand-cyan)]">{i.retention_impact}</td>
                  <td className="p-2 text-right text-white/70">£{i.payout_gbp}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ChartCard>

      <div className="flex items-center gap-2">
        <ExportButton API={API} headers={headers} report="classes" range={range} label={t('memberships_console.an_exp_classes', 'Export classes')} />
        <ExportButton API={API} headers={headers} report="instructors" range={range} label={t('memberships_console.an_exp_instructors', 'Export instructors')} />
      </div>
    </div>
  );
}

function ClassRow({ c, _idx, tone }) {
  const { t } = useTranslation();
  const barColor = tone === 'rose' ? 'var(--color-rose)' : c.occupancy_pct >= 70 ? 'var(--color-success-light)' : CYAN;
  return (
    <div className="p-3 rounded-lg bg-white/5" data-testid={`mbr-class-row-${c.template_id}`}>
      <div className="flex items-center justify-between text-xs mb-1">
        <span className="font-semibold">{c.name}</span>
        <span className="text-white/50">{t('memberships_console.an_row_sessions', '{{n}} sessions', { n: c.sessions })} · {c.booked}/{c.capacity}</span>
      </div>
      <div className="h-1.5 rounded bg-white/5 overflow-hidden">
        <div className="h-full rounded" style={{ width: `${c.occupancy_pct}%`, background: barColor }} />
      </div>
      <div className="flex items-center justify-between text-[10px] text-white/40 mt-1">
        <span>{t('memberships_console.an_row_occupancy', '{{n}}% occupancy', { n: c.occupancy_pct })}</span>
        <span>{t('memberships_console.an_row_no_show', '{{n}}% no-show', { n: c.no_show_pct })}</span>
      </div>
    </div>
  );
}

/* ───────────────────────── Operations ───────────────────────── */

function OperationsSection({ API, headers, range, openDrill }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const r = await axios.get(
          `${API}/memberships/analytics/operations?from=${range.from}&to=${range.to}`,
          { headers });
        setData(r.data);
      } catch { notify.error(t('memberships_console.an_ops_load_err', 'Failed to load operations analytics')); }
      finally { setLoading(false); }
    })();
  }, [API, headers, range, t]);
  if (loading || !data) return <LoadingPane />;

  const k = data.kpis;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <KpiCard testId="bookings" label={t('memberships_console.an_kpi_bookings', 'Bookings')}            value={k.total_bookings} icon={CalIcon} tone="cyan" />
        <KpiCard testId="waitlisted" label={t('memberships_console.an_kpi_waitlisted', 'Waitlisted')}          value={k.waitlisted} icon={Activity} tone="amber" />
        <KpiCard testId="booking-conv" label={t('memberships_console.an_kpi_booking_conv', 'Booking conv')}        value={`${k.booking_conversion_pct}%`} icon={ArrowRight} tone="emerald" />
        <KpiCard testId="payment-success" label={t('memberships_console.an_kpi_payment_success', 'Payment success')}     value={`${k.payment_success_pct}%`} icon={PoundSterling} tone={k.payment_success_pct < 90 ? 'rose' : 'emerald'} />
        <KpiCard testId="refund-pct" label={t('memberships_console.an_kpi_refund', 'Refund %')}            value={`${k.refund_pct}%`} icon={TrendingDown} tone={k.refund_pct > 5 ? 'rose' : 'neutral'} />
        <KpiCard testId="failed-payments" label={t('memberships_console.an_kpi_failed_payments', 'Failed payments')}     value={k.failed_payments} icon={AlertTriangle} tone={k.failed_payments > 0 ? 'rose' : 'neutral'}
                 onClick={() => openDrill?.('failed_payments', t('memberships_console.an_kpi_failed_payments', 'Failed payments'))} />
      </div>

      {data.alerts.length > 0 && (
        <ChartCard title={t('memberships_console.an_ct_alerts', 'Live alerts')} subtitle={t('memberships_console.an_ct_alerts_sub', 'Auto-generated from your data')}>
          <div className="space-y-2">
            {data.alerts.map((a, idx) => (
              <div key={idx} className="flex items-start gap-3 p-3 rounded-lg border" style={{
                borderColor: a.severity === 'high' ? 'rgba(244,63,94,0.4)' : 'rgba(251,191,36,0.3)',
                background: a.severity === 'high' ? 'rgba(244,63,94,0.08)' : 'rgba(251,191,36,0.06)',
              }} data-testid={`mbr-alert-${a.code}`}>
                <AlertTriangle size={16} className={a.severity === 'high' ? 'text-rose-400 mt-0.5' : 'text-amber-400 mt-0.5'} />
                <div>
                  <div className="text-sm font-bold">{a.title}</div>
                  <div className="text-xs text-white/60 mt-0.5">{a.detail}</div>
                </div>
              </div>
            ))}
          </div>
        </ChartCard>
      )}

      <ChartCard title={t('memberships_console.an_ct_site_compare', 'Site comparison')}>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-white/50">
              <tr>
                <th className="text-left p-2 font-semibold">{t('memberships_console.an_th_site', 'Site')}</th>
                <th className="text-right p-2 font-semibold">{t('memberships_console.an_th_active', 'Active')}</th>
                <th className="text-right p-2 font-semibold">{t('memberships_console.an_kpi_revenue', 'Revenue')}</th>
                <th className="text-right p-2 font-semibold">{t('memberships_console.an_kpi_bookings', 'Bookings')}</th>
                <th className="text-right p-2 font-semibold">{t('memberships_console.an_th_attended', 'Attended')}</th>
                <th className="text-right p-2 font-semibold">{t('memberships_console.an_kpi_no_show', 'No-show')}</th>
                <th className="text-right p-2 font-semibold">{t('memberships_console.an_th_churn', 'Churn')}</th>
              </tr>
            </thead>
            <tbody>
              {data.site_comparison.map(s => (
                <tr key={s.site_id} className="border-t border-white/5" data-testid={`mbr-site-${s.site_id}`}>
                  <td className="p-2 font-semibold">{s.label}</td>
                  <td className="p-2 text-right text-white/70">{s.active_members}</td>
                  <td className="p-2 text-right font-bold text-[var(--color-brand-cyan)]">£{s.revenue_gbp.toLocaleString()}</td>
                  <td className="p-2 text-right text-white/70">{s.bookings}</td>
                  <td className="p-2 text-right text-emerald-400">{s.attended}</td>
                  <td className="p-2 text-right text-rose-400">{s.no_show}</td>
                  <td className="p-2 text-right text-amber-400">{s.churn}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ChartCard>

      <ExportButton API={API} headers={headers} report="operations" range={range} label={t('memberships_console.an_exp_operations', 'Export operations')} />
    </div>
  );
}

/* ───────────────────────── AI Insights ───────────────────────── */

function AISection({ API, headers, range }) {
  const { t } = useTranslation();
  const [brief, setBrief] = useState(null);
  const [briefLoading, setBriefLoading] = useState(true);
  const [risky, setRisky] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [pipeline, setPipeline] = useState('retention');
  const [pushing, setPushing] = useState(false);

  const loadBrief = useCallback(async () => {
    setBriefLoading(true);
    try {
      const r = await axios.post(
        `${API}/memberships/analytics/ai-brief`,
        { period: 'weekly' }, { headers });
      setBrief(r.data.brief);
    } catch { notify.error(t('memberships_console.an_ai_brief_err', 'Failed to generate AI brief')); }
    finally { setBriefLoading(false); }
  }, [API, headers, t]);

  const loadRisky = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/memberships/analytics/at-risk?limit=50`, { headers });
      setRisky(r.data.members || []);
    } catch { notify.error(t('memberships_console.an_ai_risk_err', 'Failed to load at-risk list')); }
  }, [API, headers, t]);

  useEffect(() => { loadBrief(); loadRisky(); }, [loadBrief, loadRisky]);

  const toggle = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const pushToCrm = async () => {
    if (selected.size === 0) { notify.error(t('memberships_console.an_select_one', 'Select at least one member')); return; }
    setPushing(true);
    try {
      const r = await axios.post(`${API}/memberships/analytics/crm-push`, {
        member_ids: [...selected], pipeline,
        note: `Auto-flagged from Memberships analytics (${pipeline})`,
      }, { headers });
      notify.success(t('memberships_console.an_crm_pushed', 'Pushed {{n}} members to CRM ({{pipeline}})', { n: r.data.pushed, pipeline }));
      setSelected(new Set());
    } catch (e) { notifyApiError(notify, e, t('memberships_console.an_crm_push_failed', 'CRM push failed')); }
    finally { setPushing(false); }
  };

  return (
    <div className="space-y-6">
      <ChartCard title={t('memberships_console.an_ct_ai_brief', 'AI executive brief')} subtitle={t('memberships_console.an_ct_ai_brief_sub', 'Generated by GPT-4o-mini from your live data')} data-testid="mbr-ai-brief">
        {briefLoading ? <LoadingPane /> : (
          <div className="space-y-4">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-[rgb(var(--rgb-brand-cyan)/0.2)]"><Sparkles size={18} className="text-[var(--color-brand-cyan)]" /></div>
              <div className="flex-1">
                <div className="text-lg font-extrabold leading-snug">{brief?.headline || t('memberships_console.an_generating', 'Generating…')}</div>
                <p className="text-sm text-white/70 mt-2 leading-relaxed">{brief?.narrative}</p>
              </div>
              <button onClick={loadBrief} className="text-xs text-white/50 hover:text-[var(--color-brand-cyan)] flex items-center gap-1" data-testid="mbr-ai-refresh">
                <RefreshCw size={12} /> {t('memberships_console.an_refresh', 'Refresh')}
              </button>
            </div>
            {brief?.actions?.length > 0 && (
              <div className="pt-3 border-t border-white/10">
                <div className="text-[10px] font-bold tracking-widest uppercase text-white/50 mb-2">{t('memberships_console.an_recommended_actions', 'Recommended actions')}</div>
                <ul className="space-y-1.5">
                  {brief.actions.map((a, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm" data-testid={`mbr-ai-action-${i}`}>
                      <ArrowRight size={14} className="text-[var(--color-brand-cyan)] mt-1 shrink-0" />
                      <span className="text-white/80">{a}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </ChartCard>

      <ChartCard title={t('memberships_console.an_ct_at_risk', 'At-risk members')} subtitle={t('memberships_console.an_ct_at_risk_sub', 'Live churn prediction — scores with AI reasoning')}>
        <div className="flex items-center justify-between mb-3 gap-3">
          <div className="text-xs text-white/50">{t('memberships_console.an_flagged_selected', '{{flagged}} flagged · {{selected}} selected', { flagged: risky.length, selected: selected.size })}</div>
          <div className="flex items-center gap-2">
            <select value={pipeline} onChange={e => setPipeline(e.target.value)} className="bg-[var(--color-ink)] border border-white/10 rounded px-2 py-1.5 text-xs" data-testid="mbr-crm-pipeline">
              <option value="retention">{t('memberships_console.an_pipe_retention', 'CRM → Retention pipeline')}</option>
              <option value="accounts">{t('memberships_console.an_pipe_accounts', 'CRM → Accounts pipeline')}</option>
              <option value="sales">{t('memberships_console.an_pipe_sales', 'CRM → Sales (upsell) pipeline')}</option>
            </select>
            <button onClick={pushToCrm} disabled={pushing || selected.size === 0}
              className="px-3 py-1.5 rounded bg-[var(--color-brand-cyan)] text-black text-xs font-bold disabled:opacity-40"
              data-testid="mbr-crm-push">
              {pushing ? t('memberships_console.an_pushing', 'Pushing…') : t('memberships_console.an_push_to_crm', 'Push to CRM ({{n}})', { n: selected.size })}
            </button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-white/50">
              <tr>
                <th className="w-8 p-2"></th>
                <th className="text-left p-2 font-semibold">{t('memberships_console.an_th_member', 'Member')}</th>
                <th className="text-right p-2 font-semibold">{t('memberships_console.an_th_risk', 'Risk')}</th>
                <th className="text-right p-2 font-semibold">{t('memberships_console.an_th_visits_30d', 'Visits 30d')}</th>
                <th className="text-right p-2 font-semibold">{t('memberships_console.an_th_failures', 'Failures')}</th>
                <th className="text-right p-2 font-semibold">{t('memberships_console.an_th_no_shows', 'No-shows')}</th>
                <th className="text-right p-2 font-semibold">{t('memberships_console.an_th_ltv', 'LTV')}</th>
                <th className="text-left p-2 font-semibold">{t('memberships_console.an_th_ai_reason', 'AI reason')}</th>
              </tr>
            </thead>
            <tbody>
              {risky.map((m) => (
                <tr key={m.id} className="border-t border-white/5" data-testid={`mbr-at-risk-${m.id}`}>
                  <td className="p-2"><input type="checkbox" checked={selected.has(m.id)} onChange={() => toggle(m.id)} data-testid={`mbr-at-risk-check-${m.id}`} /></td>
                  <td className="p-2 font-semibold">{m.name}<div className="text-[10px] text-white/40">{m.email}</div></td>
                  <td className="p-2 text-right">
                    <span className="px-2 py-0.5 rounded text-[11px] font-bold" style={{
                      background: m.risk_score >= 60 ? 'rgba(244,63,94,0.15)' : m.risk_score >= 30 ? 'rgba(251,191,36,0.15)' : 'rgba(255,255,255,0.05)',
                      color: m.risk_score >= 60 ? 'var(--color-rose)' : m.risk_score >= 30 ? 'var(--color-warning-alt)' : 'var(--color-neutral-400-alt)',
                    }}>{m.risk_score}</span>
                  </td>
                  <td className="p-2 text-right text-white/70">{m.visits_30d}</td>
                  <td className="p-2 text-right text-white/70">{m.payment_failures}</td>
                  <td className="p-2 text-right text-white/70">{m.no_show_count}</td>
                  <td className="p-2 text-right text-[var(--color-brand-cyan)] font-bold">£{m.ltv_gbp}</td>
                  <td className="p-2 text-white/70 italic">{m.reason || '—'}</td>
                </tr>
              ))}
              {risky.length === 0 && (
                <tr><td colSpan={8} className="p-6 text-center text-white/50">{t('memberships_console.an_no_at_risk', 'No at-risk members detected')}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </ChartCard>

      <ExportButton API={API} headers={headers} report="at_risk" range={range} label={t('memberships_console.an_exp_at_risk', 'Export at-risk list')} />

      <WinbackCard API={API} headers={headers} />
    </div>
  );
}

/* ───────────────────────── Win-back card ───────────────────────── */

function WinbackCard({ API, headers }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/memberships/analytics/winback-candidates`, { headers });
      setData(r.data);
    } catch (e) {
      console.error('[WinbackCard] Failed to load winback candidates:', e?.response?.status, e?.message);
    }
  }, [API, headers]);
  useEffect(() => { load(); }, [load]);
  const sendNow = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/memberships/analytics/send-winback-now`, {}, { headers });
      if (r.data.sent > 0) notify.success(r.data.sent === 1 ? t('memberships_console.an_wb_sent_one', 'Win-back emailed to 1 lapsed member') : t('memberships_console.an_wb_sent_many', 'Win-back emailed to {{n}} lapsed members', { n: r.data.sent }));
      else notify.info(t('memberships_console.an_wb_none', 'No eligible sends right now ({{n}} skipped — already sent or no email provider configured).', { n: r.data.skipped }));
      await load();
    } catch (e) { notifyApiError(notify, e, t('memberships_console.an_wb_failed', 'Win-back run failed')); }
    finally { setBusy(false); }
  };
  if (!data) return null;
  const n = data.totals?.candidates || 0;
  return (
    <ChartCard title={t('memberships_console.an_ct_winback', "We've missed you — lapsed-member win-back")} subtitle={t('memberships_console.an_ct_winback_sub', "Members who had a 5+ day streak and haven't checked in for 7+ days")} data-testid="mbr-winback-card">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="text-xs text-white/60">
          <span className="text-[var(--color-brand-cyan)] font-extrabold text-base">{n}</span> {n === 1 ? t('memberships_console.an_wb_candidate_one', 'candidate this cycle · fires nightly via `sicon_poller`') : t('memberships_console.an_wb_candidate_many', 'candidates this cycle · fires nightly via `sicon_poller`')}
        </div>
        <button onClick={sendNow} disabled={busy}
          className="px-3 py-1.5 rounded text-xs font-bold bg-[var(--color-brand-cyan)] text-black disabled:opacity-40"
          data-testid="mbr-winback-send-now">
          {busy ? t('memberships_console.an_sending', 'Sending…') : t('memberships_console.an_wb_send_now', 'Send now ({{n}})', { n })}
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-white/50">
            <tr>
              <th className="text-left p-2 font-semibold">{t('memberships_console.an_th_member', 'Member')}</th>
              <th className="text-right p-2 font-semibold">{t('memberships_console.an_th_last_attended', 'Last attended')}</th>
              <th className="text-right p-2 font-semibold">{t('memberships_console.an_th_last_winback', 'Last winback')}</th>
            </tr>
          </thead>
          <tbody>
            {data.preview.map((m) => (
              <tr key={m.id} className="border-t border-white/5" data-testid={`mbr-winback-row-${m.id}`}>
                <td className="p-2 font-semibold">{m.name}<div className="text-[10px] text-white/40">{m.email}</div></td>
                <td className="p-2 text-right text-white/70">{(m.last_attended_at || '—').slice(0, 10)}</td>
                <td className="p-2 text-right text-white/50">{m.winback_last_sent_at ? m.winback_last_sent_at.slice(0, 10) : '—'}</td>
              </tr>
            ))}
            {data.preview.length === 0 && (
              <tr><td colSpan={3} className="p-6 text-center text-white/50">{t('memberships_console.an_wb_empty', "Nobody's lapsed right now — your gym's on fire")} 🔥</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </ChartCard>
  );
}

/* ───────────────────────── Shared UI ───────────────────────── */

function KpiCard({ label, testId, value, icon: Icon, tone = 'cyan', onClick }) {
  const toneMap = {
    cyan:    { bg: 'rgba(25,205,255,0.08)',  fg: CYAN,     border: 'rgba(25,205,255,0.25)' },
    emerald: { bg: 'rgba(52,211,153,0.08)',  fg: 'var(--color-success-light)', border: 'rgba(52,211,153,0.25)' },
    amber:   { bg: 'rgba(251,191,36,0.08)',  fg: 'var(--color-warning-alt)', border: 'rgba(251,191,36,0.25)' },
    rose:    { bg: 'rgba(244,63,94,0.08)',   fg: 'var(--color-rose)', border: 'rgba(244,63,94,0.25)' },
    neutral: { bg: 'rgba(255,255,255,0.03)', fg: 'var(--color-neutral-400-alt)', border: 'rgba(255,255,255,0.08)' },
  };
  const tn = toneMap[tone] || toneMap.cyan;
  const clickable = typeof onClick === 'function';
  const Tag = clickable ? 'button' : 'div';
  const tid = testId || String(label).toLowerCase().replace(/\s/g, '-');
  return (
    <Tag
      onClick={onClick}
      className={`p-4 rounded-xl border text-left w-full ${clickable ? 'hover:border-white/30 transition cursor-pointer' : ''}`}
      style={{ background: tn.bg, borderColor: tn.border }}
      data-testid={`mbr-kpi-${tid}`}
    >
      <div className="flex items-center gap-1.5 text-[10px] font-bold tracking-wider uppercase" style={{ color: tn.fg }}>
        {Icon && <Icon size={11} />} {label}{clickable && <ArrowRight size={10} className="opacity-50 ml-auto" />}
      </div>
      <div className="text-2xl font-extrabold mt-1 tracking-tight">{value}</div>
    </Tag>
  );
}

function ChartCard({ title, subtitle, children, className = '', 'data-testid': testid }) {
  return (
    <div
      className={`p-5 rounded-2xl border ${className}`}
      style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)', color: 'var(--theme-text)' }}
      data-testid={testid}
    >
      <div className="mb-3">
        <div className="text-sm font-bold">{title}</div>
        {subtitle && <div className="text-[11px] mt-0.5" style={{ color: 'var(--theme-text-muted)' }}>{subtitle}</div>}
      </div>
      {children}
    </div>
  );
}

function LoadingPane() {
  const { t } = useTranslation();
  return (
    <div className="p-12 grid place-items-center text-white/40 text-sm">
      <div className="flex items-center gap-2"><RefreshCw size={14} className="animate-spin" /> {t('memberships_console.an_loading', 'Loading…')}</div>
    </div>
  );
}

function ExportButton({ API, headers, report, range, label, pdf = false }) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const onClick = async () => {
    setBusy(true);
    try {
      const url = pdf
        ? `${API}/memberships/analytics/export.pdf?from=${range.from}&to=${range.to}`
        : `${API}/memberships/analytics/export.csv?report=${report}&from=${range.from}&to=${range.to}`;
      const r = await axios.get(url, { headers, responseType: 'blob' });
      const blob = new Blob([r.data], { type: pdf ? 'application/pdf' : 'text/csv' });
      const href = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = href;
      a.download = pdf ? 'memberships-weekly-brief.pdf' : `memberships-${report}.csv`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(href);
    } catch { notify.error(t('memberships_console.an_export_failed', 'Export failed')); }
    finally { setBusy(false); }
  };
  const Icon = pdf ? FileText : Download;
  return (
    <button onClick={onClick} disabled={busy}
      className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 text-xs font-bold disabled:opacity-40"
      data-testid={`mbr-export-${report}${pdf ? '-pdf' : ''}`}>
      <Icon size={13} /> {busy ? t('memberships_console.an_working', 'Working…') : label}
    </button>
  );
}
