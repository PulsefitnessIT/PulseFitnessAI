/**
 * GymAxis Memberships — Analytics & Reporting engine.
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
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';
import { Line, BarChart, Bar, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts';
import {
  TrendingUp, TrendingDown, Users, PoundSterling, Activity,
  AlertTriangle, Sparkles, Download, FileText, UserMinus, Target,
  Zap, Calendar as CalIcon, Gauge, ArrowRight, RefreshCw, X, Mail,
} from 'lucide-react';

const SECTIONS = [
  { id: 'overview',  label: 'Overview',   icon: Gauge },
  { id: 'retention', label: 'Retention',  icon: UserMinus },
  { id: 'classes',   label: 'Classes',    icon: Activity },
  { id: 'operations',label: 'Operations', icon: Target },
  { id: 'ai',        label: 'AI insights',icon: Sparkles },
];

const ROLES = [
  { id: 'manager',  label: 'Gym manager',    days: 30 },
  { id: 'regional', label: 'Regional mgr',   days: 90 },
  { id: 'director', label: 'Director',       days: 180 },
];

const CYAN = 'var(--color-brand-cyan)';
const PIE_PALETTE = ['var(--color-brand-cyan)', '#22D3EE', 'var(--color-violet-400)', '#F472B6', '#FCD34D', 'var(--color-success-light)'];

export default function AnalyticsTab({ API, headers }) {
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

      <div className="flex items-center gap-1 mb-6 border-b border-white/10 overflow-x-auto">
        {SECTIONS.map(s => {
          const Icon = s.icon;
          const active = section === s.id;
          return (
            <button
              key={s.id}
              onClick={() => setSection(s.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-semibold transition whitespace-nowrap ${active ? 'text-[var(--color-brand-cyan)] border-b-2 border-[var(--color-brand-cyan)]' : 'text-white/60 hover:text-white'}`}
              data-testid={`mbr-analytics-tab-${s.id}`}
            >
              <Icon size={14} /> {s.label}
            </button>
          );
        })}
      </div>

      {section === 'overview'   && <OverviewSection  API={API} headers={headers} range={range} openDrill={openDrill} />}
      {section === 'retention'  && <RetentionSection API={API} headers={headers} range={range} openDrill={openDrill} />}
      {section === 'classes'    && <ClassesSection   API={API} headers={headers} range={range} />}
      {section === 'operations' && <OperationsSection API={API} headers={headers} range={range} openDrill={openDrill} />}
      {section === 'ai'         && <AISection        API={API} headers={headers} range={range} />}

      {drill && <DrillDrawer API={API} headers={headers} range={range} drill={drill} onClose={() => setDrill(null)} />}
    </div>
  );
}

/* ───────────────────────── Weekly digest button ───────────────────────── */

function DigestButton({ API, headers }) {
  const [busy, setBusy] = useState(false);
  const onClick = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/memberships/analytics/send-weekly-digest`, {}, { headers });
      if (r.data.sent?.length) notify.success(`Digest sent to ${r.data.sent.length} recipient${r.data.sent.length > 1 ? 's' : ''}`);
      else if (r.data.skipped === 'already_sent_this_week') notify.info('Already sent this week — the next auto-run is Monday.');
      else notify.info('Digest built · no operator recipients configured yet.');
    } catch (e) { notifyApiError(notify, e, 'Digest failed'); }
    finally { setBusy(false); }
  };
  return (
    <button onClick={onClick} disabled={busy}
      className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 text-xs font-bold disabled:opacity-40"
      data-testid="mbr-send-digest">
      <Mail size={13} /> {busy ? 'Sending…' : 'Send weekly digest'}
    </button>
  );
}

/* ───────────────────────── Drill-down drawer ───────────────────────── */

function DrillDrawer({ API, headers, range, drill, onClose }) {
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
            <div className="text-[10px] font-bold tracking-[0.25em] uppercase text-[var(--color-brand-cyan)]">Drill-down</div>
            <h2 className="text-xl font-extrabold mt-0.5">{drill.title}</h2>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg text-white/60 hover:bg-white/10 hover:text-white" data-testid="mbr-drill-close">
            <X size={16} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {!rows && !err && <div className="p-10 text-center text-white/40 text-sm flex items-center justify-center gap-2"><RefreshCw size={14} className="animate-spin" /> Loading…</div>}
          {err && <div className="p-10 text-center text-rose-400 text-sm">Failed to load · retry in a moment.</div>}
          {rows && rows.length === 0 && <div className="p-10 text-center text-white/50 text-sm">Nothing here — zero is a good number for this KPI.</div>}
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
                    {m.amount_gbp != null && <div className="text-[11px] text-rose-400 font-bold">£{m.amount_gbp} failed</div>}
                    {m.visits_60d != null && <div className="text-[11px] text-white/50">{m.visits_60d} visits</div>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="px-6 py-3 border-t border-white/10 text-[11px] text-white/40">
          {rows?.length ? `${rows.length} member${rows.length === 1 ? '' : 's'}` : ''}
        </div>
      </aside>
    </div>
  );
}

/* ───────────────────────── Role switcher ───────────────────────── */

function RoleSwitcher({ role, setRole }) {
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
        >{r.label}</button>
      ))}
    </div>
  );
}

/* ───────────────────────── Overview ───────────────────────── */

function OverviewSection({ API, headers, range, openDrill }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(
        `${API}/memberships/analytics/overview?from=${range.from}&to=${range.to}&period=monthly`,
        { headers });
      setData(r.data);
    } catch { notify.error('Failed to load analytics overview'); }
    finally { setLoading(false); }
  }, [API, headers, range]);
  useEffect(() => { load(); }, [load]);

  if (loading || !data) return <LoadingPane />;

  const k = data.kpis;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <KpiCard label="MRR"             value={`£${k.mrr_gbp.toLocaleString()}`} icon={PoundSterling} tone="cyan" />
        <KpiCard label="ARPU"            value={`£${k.arpu_gbp}`} icon={Users} tone="emerald" />
        <KpiCard label="Active members"  value={k.active_members} icon={Users} tone="cyan"
                 onClick={() => openDrill?.('active_members', 'Active members')} />
        <KpiCard label="Net growth"      value={`${k.net_growth >= 0 ? '+' : ''}${k.net_growth}`} icon={k.net_growth >= 0 ? TrendingUp : TrendingDown} tone={k.net_growth >= 0 ? 'emerald' : 'rose'}
                 onClick={() => openDrill?.('new_members', 'New members')} />
        <KpiCard label="Churn %"         value={`${k.churn_pct}%`} icon={UserMinus} tone={k.churn_pct > 5 ? 'rose' : 'neutral'}
                 onClick={() => openDrill?.('cancellations', 'Cancellations')} />
        <KpiCard label="Revenue"         value={`£${k.revenue_gbp.toLocaleString()}`} icon={PoundSterling} tone="cyan" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <ChartCard title="Revenue trend" subtitle="Paid transactions by month · dashed line + shaded band = forecast with 1σ confidence" className="lg:col-span-2">
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
              <Area dataKey="revenue" stroke={CYAN} fill="url(#rev)" name="Revenue (£)" />
              <Area dataKey="forecast_upper" stroke="none" fill="url(#band)" name="Forecast upper (£)" />
              <Area dataKey="forecast_lower" stroke="none" fill="var(--color-surface-darker)" fillOpacity={1} name="Forecast lower (£)" />
              <Line dataKey="forecast" stroke="var(--color-warning-alt)" strokeDasharray="4 4" name="Forecast (£)" />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Revenue by product">
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
        <ChartCard title="Member growth" subtitle="New vs cancelled, by month">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={data.trend}>
              <CartesianGrid stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />
              <XAxis dataKey="bucket" stroke="rgba(255,255,255,0.5)" style={{ fontSize: 11 }} />
              <YAxis stroke="rgba(255,255,255,0.5)" style={{ fontSize: 11 }} />
              <Tooltip contentStyle={{ background: 'var(--color-ink)', border: '1px solid rgba(255,255,255,0.15)' }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="new"   fill="var(--color-success-light)" name="New members" />
              <Bar dataKey="churn" fill="var(--color-rose)" name="Cancellations" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Membership mix">
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
        <ExportButton API={API} headers={headers} report="overview" range={range} label="Export overview" />
        <ExportButton API={API} headers={headers} report="overview" range={range} pdf label="Weekly PDF brief" />
      </div>
    </div>
  );
}

/* ───────────────────────── Retention ───────────────────────── */

function RetentionSection({ API, headers, range }) {
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
      } catch { notify.error('Failed to load retention'); }
      finally { setLoading(false); }
    })();
  }, [API, headers, range]);
  if (loading || !data) return <LoadingPane />;

  const k = data.kpis;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard label="Cancellations"      value={k.churn_total} icon={UserMinus} tone="rose" />
        <KpiCard label="Avg lifespan"       value={`${k.avg_lifespan_days}d`} icon={CalIcon} tone="cyan" />
        <KpiCard label="Early churn (30d)"  value={k.early_churn_30d} icon={Zap} tone={k.early_churn_30d > 0 ? 'amber' : 'neutral'} />
        <KpiCard label="Early churn (60d)"  value={k.early_churn_60d} icon={Zap} tone={k.early_churn_60d > 0 ? 'amber' : 'neutral'} />
      </div>

      <ChartCard title="Engagement segmentation" subtitle="Last 60 days of visits & attendance">
        <div className="grid grid-cols-4 gap-3 mt-2">
          {Object.entries(data.segments).map(([key, count], _idx) => {
            const labels = {
              highly_engaged: { label: 'Highly engaged', color: 'var(--color-success-light)' },
              regular:        { label: 'Regular',        color: CYAN },
              at_risk:        { label: 'At risk',        color: 'var(--color-warning-alt)' },
              inactive:       { label: 'Inactive',       color: 'var(--color-rose)' },
            };
            const l = labels[key];
            return (
              <div key={key} className="p-4 rounded-xl border border-white/10 bg-white/5" data-testid={`mbr-segment-${key}`}>
                <div className="text-[10px] font-bold tracking-wider uppercase" style={{ color: l.color }}>{l.label}</div>
                <div className="text-3xl font-extrabold mt-1">{count}</div>
                <div className="text-[11px] text-white/50 mt-1">{data.segment_members[key]?.length || 0} members shown</div>
              </div>
            );
          })}
        </div>
      </ChartCard>

      <ChartCard title="Retention cohort matrix" subtitle="% of cohort still active after N months">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-white/50">
                <th className="text-left p-2 font-semibold">Cohort</th>
                <th className="text-left p-2 font-semibold">Size</th>
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="Churn by plan">
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

        <ChartCard title="At-risk member preview">
          <div className="space-y-1.5 pt-2 max-h-[220px] overflow-y-auto">
            {(data.segment_members.at_risk || []).slice(0, 10).map((m, idx) => (
              <div key={m.id} className="flex items-center justify-between px-3 py-2 rounded-lg bg-white/5 text-xs" data-testid={`mbr-at-risk-preview-${idx}`}>
                <span className="font-semibold">{m.name}</span>
                <span className="text-white/50">{m.visits_60d} visits · £{m.lifetime_value_gbp}</span>
              </div>
            ))}
            {(!data.segment_members.at_risk || data.segment_members.at_risk.length === 0) && (
              <div className="text-xs text-white/50 py-6 text-center">No at-risk members in window</div>
            )}
          </div>
        </ChartCard>
      </div>

      <ExportButton API={API} headers={headers} report="retention" range={range} label="Export retention" />

      <ReferralsBlock API={API} headers={headers} range={range} />
    </div>
  );
}

function ReferralsBlock({ API, headers, range }) {
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
        <KpiCard label="Referrals"      value={k.total} icon={Sparkles} tone="cyan" />
        <KpiCard label="Earned"         value={k.earned} icon={Sparkles} tone="emerald" />
        <KpiCard label="Pending"        value={k.pending} icon={Sparkles} tone="amber" />
        <KpiCard label="Conversion"     value={`${k.conversion_pct}%`} icon={ArrowRight} tone="cyan" />
        <KpiCard label="Credit paid"    value={`£${k.credit_paid_gbp}`} icon={PoundSterling} tone="emerald" />
      </div>

      <ChartCard title="Top referrers" subtitle="Say thanks to the members growing your studio">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-white/50">
              <tr>
                <th className="text-left p-2 font-semibold">Member</th>
                <th className="text-left p-2 font-semibold">Code</th>
                <th className="text-right p-2 font-semibold">Referred</th>
                <th className="text-right p-2 font-semibold">Converted</th>
                <th className="text-right p-2 font-semibold">Conversion</th>
                <th className="text-right p-2 font-semibold">Credit earned</th>
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
                <tr><td colSpan={6} className="p-6 text-center text-white/50">No referrals yet — prompt your superfans!</td></tr>
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
      } catch { notify.error('Failed to load class analytics'); }
      finally { setLoading(false); }
    })();
  }, [API, headers, range]);
  if (loading || !data) return <LoadingPane />;

  const k = data.kpis;
  const maxHeat = Math.max(1, ...data.heatmap.flat());
  const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <KpiCard label="Sessions"          value={k.total_sessions} icon={CalIcon} tone="cyan" />
        <KpiCard label="Occupancy"         value={`${k.avg_occupancy_pct}%`} icon={Gauge} tone={k.avg_occupancy_pct >= 70 ? 'emerald' : 'amber'} />
        <KpiCard label="No-show"           value={`${k.no_show_pct}%`} icon={AlertTriangle} tone={k.no_show_pct > 15 ? 'rose' : 'neutral'} />
        <KpiCard label="Waitlist conv"     value={`${k.waitlist_conversion_pct}%`} icon={ArrowRight} tone="cyan" />
        <KpiCard label="Late cancels"      value={k.late_cancels} icon={UserMinus} tone="neutral" />
      </div>

      <ChartCard title="Booking heatmap" subtitle="Day-of-week × hour-of-day">
        <div className="overflow-x-auto">
          <div className="grid grid-cols-[50px_repeat(24,minmax(20px,1fr))] gap-0.5 text-[9px] text-white/40">
            <div></div>
            {Array.from({ length: 24 }).map((_, h) => <div key={h} className="text-center">{h}</div>)}
            {data.heatmap.map((row, d) => (
              <React.Fragment key={d}>
                <div className="text-right pr-2 font-semibold text-white/70 self-center">{DAYS[d]}</div>
                {row.map((v, h) => {
                  const alpha = v > 0 ? Math.max(0.15, v / maxHeat) : 0;
                  return (
                    <div key={h} className="h-7 rounded" style={{ background: v ? `rgba(25, 205, 255, ${alpha})` : 'rgba(255,255,255,0.04)' }} title={`${DAYS[d]} ${h}:00 — ${v} bookings`} data-testid={`mbr-heat-${d}-${h}`} />
                  );
                })}
              </React.Fragment>
            ))}
          </div>
        </div>
      </ChartCard>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="Top classes" subtitle="By occupancy">
          <div className="space-y-2">
            {data.classes_ranked.slice(0, 8).map((c, idx) => (
              <ClassRow key={c.template_id} c={c} idx={idx} />
            ))}
          </div>
        </ChartCard>
        <ChartCard title="Underperforming classes" subtitle="Occupancy < 40%">
          <div className="space-y-2">
            {data.underperforming.length === 0 && (
              <div className="text-xs text-white/50 py-6 text-center">All classes running above 40% occupancy 🎉</div>
            )}
            {data.underperforming.map((c) => <ClassRow key={c.template_id} c={c} tone="rose" />)}
          </div>
        </ChartCard>
      </div>

      <ChartCard title="Instructor scorecards" subtitle="Sessions, retention impact, payout">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-white/50">
              <tr>
                <th className="text-left p-2 font-semibold">Instructor</th>
                <th className="text-right p-2 font-semibold">Sessions</th>
                <th className="text-right p-2 font-semibold">Attended</th>
                <th className="text-right p-2 font-semibold">Occupancy</th>
                <th className="text-right p-2 font-semibold">No-show</th>
                <th className="text-right p-2 font-semibold">Unique members</th>
                <th className="text-right p-2 font-semibold">Retention impact</th>
                <th className="text-right p-2 font-semibold">Payout</th>
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
        <ExportButton API={API} headers={headers} report="classes" range={range} label="Export classes" />
        <ExportButton API={API} headers={headers} report="instructors" range={range} label="Export instructors" />
      </div>
    </div>
  );
}

function ClassRow({ c, _idx, tone }) {
  const barColor = tone === 'rose' ? 'var(--color-rose)' : c.occupancy_pct >= 70 ? 'var(--color-success-light)' : CYAN;
  return (
    <div className="p-3 rounded-lg bg-white/5" data-testid={`mbr-class-row-${c.template_id}`}>
      <div className="flex items-center justify-between text-xs mb-1">
        <span className="font-semibold">{c.name}</span>
        <span className="text-white/50">{c.sessions} sessions · {c.booked}/{c.capacity}</span>
      </div>
      <div className="h-1.5 rounded bg-white/5 overflow-hidden">
        <div className="h-full rounded" style={{ width: `${c.occupancy_pct}%`, background: barColor }} />
      </div>
      <div className="flex items-center justify-between text-[10px] text-white/40 mt-1">
        <span>{c.occupancy_pct}% occupancy</span>
        <span>{c.no_show_pct}% no-show</span>
      </div>
    </div>
  );
}

/* ───────────────────────── Operations ───────────────────────── */

function OperationsSection({ API, headers, range, openDrill }) {
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
      } catch { notify.error('Failed to load operations analytics'); }
      finally { setLoading(false); }
    })();
  }, [API, headers, range]);
  if (loading || !data) return <LoadingPane />;

  const k = data.kpis;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <KpiCard label="Bookings"            value={k.total_bookings} icon={CalIcon} tone="cyan" />
        <KpiCard label="Waitlisted"          value={k.waitlisted} icon={Activity} tone="amber" />
        <KpiCard label="Booking conv"        value={`${k.booking_conversion_pct}%`} icon={ArrowRight} tone="emerald" />
        <KpiCard label="Payment success"     value={`${k.payment_success_pct}%`} icon={PoundSterling} tone={k.payment_success_pct < 90 ? 'rose' : 'emerald'} />
        <KpiCard label="Refund %"            value={`${k.refund_pct}%`} icon={TrendingDown} tone={k.refund_pct > 5 ? 'rose' : 'neutral'} />
        <KpiCard label="Failed payments"     value={k.failed_payments} icon={AlertTriangle} tone={k.failed_payments > 0 ? 'rose' : 'neutral'}
                 onClick={() => openDrill?.('failed_payments', 'Failed payments')} />
      </div>

      {data.alerts.length > 0 && (
        <ChartCard title="Live alerts" subtitle="Auto-generated from your data">
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

      <ChartCard title="Site comparison">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-white/50">
              <tr>
                <th className="text-left p-2 font-semibold">Site</th>
                <th className="text-right p-2 font-semibold">Active</th>
                <th className="text-right p-2 font-semibold">Revenue</th>
                <th className="text-right p-2 font-semibold">Bookings</th>
                <th className="text-right p-2 font-semibold">Attended</th>
                <th className="text-right p-2 font-semibold">No-show</th>
                <th className="text-right p-2 font-semibold">Churn</th>
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

      <ExportButton API={API} headers={headers} report="operations" range={range} label="Export operations" />
    </div>
  );
}

/* ───────────────────────── AI Insights ───────────────────────── */

function AISection({ API, headers, range }) {
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
    } catch { notify.error('Failed to generate AI brief'); }
    finally { setBriefLoading(false); }
  }, [API, headers]);

  const loadRisky = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/memberships/analytics/at-risk?limit=50`, { headers });
      setRisky(r.data.members || []);
    } catch { notify.error('Failed to load at-risk list'); }
  }, [API, headers]);

  useEffect(() => { loadBrief(); loadRisky(); }, [loadBrief, loadRisky]);

  const toggle = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const pushToCrm = async () => {
    if (selected.size === 0) { notify.error('Select at least one member'); return; }
    setPushing(true);
    try {
      const r = await axios.post(`${API}/memberships/analytics/crm-push`, {
        member_ids: [...selected], pipeline,
        note: `Auto-flagged from Memberships analytics (${pipeline})`,
      }, { headers });
      notify.success(`Pushed ${r.data.pushed} members to CRM (${pipeline})`);
      setSelected(new Set());
    } catch (e) { notifyApiError(notify, e, 'CRM push failed'); }
    finally { setPushing(false); }
  };

  return (
    <div className="space-y-6">
      <ChartCard title="AI executive brief" subtitle="Generated by GPT-4o-mini from your live data" data-testid="mbr-ai-brief">
        {briefLoading ? <LoadingPane /> : (
          <div className="space-y-4">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-[rgb(var(--rgb-brand-cyan)/0.2)]"><Sparkles size={18} className="text-[var(--color-brand-cyan)]" /></div>
              <div className="flex-1">
                <div className="text-lg font-extrabold leading-snug">{brief?.headline || 'Generating…'}</div>
                <p className="text-sm text-white/70 mt-2 leading-relaxed">{brief?.narrative}</p>
              </div>
              <button onClick={loadBrief} className="text-xs text-white/50 hover:text-[var(--color-brand-cyan)] flex items-center gap-1" data-testid="mbr-ai-refresh">
                <RefreshCw size={12} /> Refresh
              </button>
            </div>
            {brief?.actions?.length > 0 && (
              <div className="pt-3 border-t border-white/10">
                <div className="text-[10px] font-bold tracking-widest uppercase text-white/50 mb-2">Recommended actions</div>
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

      <ChartCard title="At-risk members" subtitle="Live churn prediction — scores with AI reasoning">
        <div className="flex items-center justify-between mb-3 gap-3">
          <div className="text-xs text-white/50">{risky.length} flagged · {selected.size} selected</div>
          <div className="flex items-center gap-2">
            <select value={pipeline} onChange={e => setPipeline(e.target.value)} className="bg-[var(--color-ink)] border border-white/10 rounded px-2 py-1.5 text-xs" data-testid="mbr-crm-pipeline">
              <option value="retention">CRM → Retention pipeline</option>
              <option value="accounts">CRM → Accounts pipeline</option>
              <option value="sales">CRM → Sales (upsell) pipeline</option>
            </select>
            <button onClick={pushToCrm} disabled={pushing || selected.size === 0}
              className="px-3 py-1.5 rounded bg-[var(--color-brand-cyan)] text-black text-xs font-bold disabled:opacity-40"
              data-testid="mbr-crm-push">
              {pushing ? 'Pushing…' : `Push to CRM (${selected.size})`}
            </button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-white/50">
              <tr>
                <th className="w-8 p-2"></th>
                <th className="text-left p-2 font-semibold">Member</th>
                <th className="text-right p-2 font-semibold">Risk</th>
                <th className="text-right p-2 font-semibold">Visits 30d</th>
                <th className="text-right p-2 font-semibold">Failures</th>
                <th className="text-right p-2 font-semibold">No-shows</th>
                <th className="text-right p-2 font-semibold">LTV</th>
                <th className="text-left p-2 font-semibold">AI reason</th>
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
                <tr><td colSpan={8} className="p-6 text-center text-white/50">No at-risk members detected</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </ChartCard>

      <ExportButton API={API} headers={headers} report="at_risk" range={range} label="Export at-risk list" />

      <WinbackCard API={API} headers={headers} />
    </div>
  );
}

/* ───────────────────────── Win-back card ───────────────────────── */

function WinbackCard({ API, headers }) {
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
      if (r.data.sent > 0) notify.success(`Win-back emailed to ${r.data.sent} lapsed member${r.data.sent === 1 ? '' : 's'}`);
      else notify.info(`No eligible sends right now (${r.data.skipped} skipped — already sent or no email provider configured).`);
      await load();
    } catch (e) { notifyApiError(notify, e, 'Win-back run failed'); }
    finally { setBusy(false); }
  };
  if (!data) return null;
  const n = data.totals?.candidates || 0;
  return (
    <ChartCard title="We've missed you — lapsed-member win-back" subtitle="Members who had a 5+ day streak and haven't checked in for 7+ days" data-testid="mbr-winback-card">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="text-xs text-white/60">
          <span className="text-[var(--color-brand-cyan)] font-extrabold text-base">{n}</span> candidate{n === 1 ? '' : 's'} this cycle · fires nightly via `sicon_poller`
        </div>
        <button onClick={sendNow} disabled={busy}
          className="px-3 py-1.5 rounded text-xs font-bold bg-[var(--color-brand-cyan)] text-black disabled:opacity-40"
          data-testid="mbr-winback-send-now">
          {busy ? 'Sending…' : `Send now (${n})`}
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-white/50">
            <tr>
              <th className="text-left p-2 font-semibold">Member</th>
              <th className="text-right p-2 font-semibold">Last attended</th>
              <th className="text-right p-2 font-semibold">Last winback</th>
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
              <tr><td colSpan={3} className="p-6 text-center text-white/50">Nobody's lapsed right now — your gym's on fire 🔥</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </ChartCard>
  );
}

/* ───────────────────────── Shared UI ───────────────────────── */

function KpiCard({ label, value, icon: Icon, tone = 'cyan', onClick }) {
  const toneMap = {
    cyan:    { bg: 'rgba(25,205,255,0.08)',  fg: CYAN,     border: 'rgba(25,205,255,0.25)' },
    emerald: { bg: 'rgba(52,211,153,0.08)',  fg: 'var(--color-success-light)', border: 'rgba(52,211,153,0.25)' },
    amber:   { bg: 'rgba(251,191,36,0.08)',  fg: 'var(--color-warning-alt)', border: 'rgba(251,191,36,0.25)' },
    rose:    { bg: 'rgba(244,63,94,0.08)',   fg: 'var(--color-rose)', border: 'rgba(244,63,94,0.25)' },
    neutral: { bg: 'rgba(255,255,255,0.03)', fg: 'var(--color-neutral-400-alt)', border: 'rgba(255,255,255,0.08)' },
  };
  const t = toneMap[tone] || toneMap.cyan;
  const clickable = typeof onClick === 'function';
  const Tag = clickable ? 'button' : 'div';
  return (
    <Tag
      onClick={onClick}
      className={`p-4 rounded-xl border text-left w-full ${clickable ? 'hover:border-white/30 transition cursor-pointer' : ''}`}
      style={{ background: t.bg, borderColor: t.border }}
      data-testid={`mbr-kpi-${label.toLowerCase().replace(/\s/g,'-')}`}
    >
      <div className="flex items-center gap-1.5 text-[10px] font-bold tracking-wider uppercase" style={{ color: t.fg }}>
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
  return (
    <div className="p-12 grid place-items-center text-white/40 text-sm">
      <div className="flex items-center gap-2"><RefreshCw size={14} className="animate-spin" /> Loading…</div>
    </div>
  );
}

function ExportButton({ API, headers, report, range, label, pdf = false }) {
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
    } catch { notify.error('Export failed'); }
    finally { setBusy(false); }
  };
  const Icon = pdf ? FileText : Download;
  return (
    <button onClick={onClick} disabled={busy}
      className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 text-xs font-bold disabled:opacity-40"
      data-testid={`mbr-export-${report}${pdf ? '-pdf' : ''}`}>
      <Icon size={13} /> {busy ? 'Working…' : label}
    </button>
  );
}
