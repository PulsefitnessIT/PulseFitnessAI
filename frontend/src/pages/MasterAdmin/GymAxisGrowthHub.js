/**
 * GymAxisGrowthHub — Master Admin → Growth → Marketing Studio
 * (Iter 220ag, replaces GrowthStudio.js).
 *
 * The previous implementation embedded the operator-facing
 * `MarketingSuite` ("Fill empty classes", "Re-engage inactive members"
 * etc.) which was the wrong context for marketing GymAxis as a B2B
 * SaaS. This Hub is a pure aggregation surface: it reads one
 * server-rolled-up payload (`GET /api/master-admin/growth/overview`)
 * and surfaces deep-links into every existing module so we **never
 * duplicate** Trials, Sales Insights, Outbound Emails, SEO Autopilot,
 * or the CRM pipeline — they already exist as first-class master-
 * admin views.
 *
 * Layout:
 *   1. Hero — explains "this is GymAxis self-promotion".
 *   2. KPI tiles row — at-a-glance numbers per funnel stage.
 *   3. Funnel cards — one per module group, each with the right
 *      "Open …" button that jumps the user to the existing module.
 *   4. B2B Journey Templates — preset library (read-only for now);
 *      the underlying journey runner already exists in Marketing.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  Rocket, Loader2, ArrowRight, Sparkles, BookOpen, Mail,
  TrendingUp, MessageSquare, Users, Workflow, RefreshCw, Building2,
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;
const auth = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

// B2B journey templates — pre-canned for the master admin. The
// Marketing module's existing JourneysTab is where they actually run;
// this list is a quick-launch surface that points there.
const JOURNEY_TEMPLATES = [
  {
    id: 'cold-to-demo',
    name: 'Cold prospect → demo',
    desc: '7 emails over 14 days. Hook → value → social proof → CTA.',
    audience: 'New CRM contacts in target ICP (gym chains, 3+ sites)',
    tone: 'B2B SaaS · GymAxis brand voice',
  },
  {
    id: 'demo-booked',
    name: 'Demo booked → close',
    desc: 'Recap email + 2 follow-ups (T+1d, T+5d) with mutual-action plan.',
    audience: 'CRM deals in "Demo Booked" stage',
    tone: 'Personal, partnership-first',
  },
  {
    id: 'trial-conversion',
    name: 'Trial day 1 / 7 / 13 → paid',
    desc: 'Activation nudge, value reminder, conversion push (PoC ROI).',
    audience: 'Orgs with `is_trial = true`',
    tone: 'Helpful, urgency only on day 13',
  },
  {
    id: 'lost-revival',
    name: 'Lost deal → 90-day re-engagement',
    desc: 'Quarterly "what\'s new" digest + relevant case study.',
    audience: 'CRM deals stage = lost in last 12 months',
    tone: 'Low-pressure, news-led',
  },
];

function KpiTile({ label, value, hint, icon: Icon, accent = 'text-zinc-900' }) {
  return (
    <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 p-4" data-testid={`growth-kpi-${label.toLowerCase().replace(/\s+/g, '-')}`}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] uppercase tracking-wider font-bold text-zinc-500">{label}</p>
        {Icon ? <Icon size={14} className="text-zinc-400" /> : null}
      </div>
      <p className={`text-3xl font-extrabold mt-2 tabular-nums ${accent}`}>{value}</p>
      {hint ? <p className="text-[11px] text-zinc-500 mt-1">{hint}</p> : null}
    </div>
  );
}

function FunnelCard({ icon: Icon, accent, title, lede, stats, ctaLabel, deepLink, onJump, testId }) {
  return (
    <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 p-5 flex flex-col gap-3" data-testid={testId}>
      <div className="flex items-center gap-3">
        <span className={`shrink-0 w-10 h-10 rounded-xl ${accent} text-white flex items-center justify-center`}>
          <Icon size={16} />
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-extrabold tracking-tight">{title}</p>
          <p className="text-[11px] text-zinc-500">{lede}</p>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 text-[12px]">
        {stats.map((s) => (
          <div key={s.label} className="rounded-lg bg-zinc-50 dark:bg-zinc-900 px-3 py-2">
            <p className="text-[10px] uppercase tracking-wider font-bold text-zinc-500">{s.label}</p>
            <p className="text-base font-extrabold tabular-nums mt-0.5">{s.value}</p>
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={() => onJump(deepLink)}
        className="mt-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold border border-fuchsia-200 dark:border-fuchsia-900 text-fuchsia-700 dark:text-fuchsia-300 hover:bg-fuchsia-50 dark:hover:bg-fuchsia-950 transition-colors"
        data-testid={`${testId}-jump`}
      >
        {ctaLabel} <ArrowRight size={12} />
      </button>
    </div>
  );
}

export default function GymAxisGrowthHub({ onJumpSection }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true); setErr(null);
    try {
      const r = await axios.get(`${API}/api/master-admin/growth/overview`, { headers: auth() });
      setData(r.data);
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Could not load growth overview');
    } finally { setBusy(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  // Best-effort: change section in the parent MasterAdminPage. Falls
  // back to a soft hash navigation if the prop isn't wired (e.g. when
  // rendered in isolation by Jest).
  const jump = (sectionId) => {
    if (typeof onJumpSection === 'function') {
      onJumpSection(sectionId);
      return;
    }
    try { window.location.hash = `#${sectionId}`; } catch { /* noop */ }
  };

  if (err) {
    return (
      <div className="rounded-2xl border border-rose-200 bg-rose-50 text-rose-700 px-4 py-3 text-sm" data-testid="growth-hub-error">
        {err}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 p-10 flex items-center justify-center gap-2 text-zinc-500" data-testid="growth-hub-loading">
        <Loader2 size={16} className="animate-spin" /> Loading GymAxis growth overview…
      </div>
    );
  }

  return (
    <div className="space-y-5" data-testid="gymaxis-growth-hub">
      {/* Hero — explains this is GymAxis self-promo. */}
      <header
        className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-gradient-to-r from-fuchsia-50 via-white to-blue-50 dark:from-zinc-900 dark:via-zinc-900 dark:to-zinc-900 px-5 py-4 flex items-center gap-4"
        data-testid="growth-hub-hero"
      >
        <span className="shrink-0 w-12 h-12 rounded-2xl bg-gradient-to-br from-fuchsia-500 to-blue-600 text-white flex items-center justify-center shadow-[0_8px_20px_-8px_rgba(217,70,239,0.6)]">
          <Rocket size={20} />
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-[11px] uppercase tracking-[0.18em] font-bold text-fuchsia-700 dark:text-fuchsia-400">
            Growth · Master Admin
          </p>
          <h2 className="text-xl sm:text-2xl font-extrabold text-zinc-900 dark:text-zinc-50 tracking-tight mt-0.5">
            GymAxis Growth Hub
          </h2>
          <p className="text-xs sm:text-sm text-zinc-600 dark:text-zinc-300 mt-1 max-w-2xl">
            How we&apos;re marketing GymAxis to fitness operators. Pulls live
            numbers from Trials, SEO Autopilot, Outbound Emails, CRM Pipeline
            and Sales Insights — no module is rebuilt here, every tile deep-links
            into the existing tool.
          </p>
        </div>
        <button
          type="button" onClick={load} disabled={busy}
          className="hidden md:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold border border-zinc-200 dark:border-zinc-700 text-zinc-700 dark:text-zinc-100 hover:border-fuchsia-400 disabled:opacity-50"
          data-testid="growth-hub-refresh"
        >
          {busy ? <Loader2 size={12} className="animate-spin"/> : <RefreshCw size={12} />}
          Refresh
        </button>
      </header>

      {/* Top KPI band */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3" data-testid="growth-hub-kpis">
        <KpiTile
          label="Active trials" value={data.trials.active}
          hint={`${data.trials.converted_30d} converted in 30d`}
          icon={Users}
        />
        <KpiTile
          label="Blog views" value={data.seo.blog_views_total.toLocaleString()}
          hint={`${data.seo.articles_published} articles published`}
          icon={BookOpen}
        />
        <KpiTile
          label="Emails sent (30d)" value={data.outbound.sent_30d.toLocaleString()}
          hint={`${data.outbound.failed_30d} failed`}
          icon={Mail}
        />
        <KpiTile
          label="Pipeline £" value={`£${Number(data.pipeline.pipeline_value_gbp || 0).toLocaleString()}`}
          hint={`${data.pipeline.deals_open} open deals`}
          icon={TrendingUp}
          accent="text-emerald-700"
        />
        <KpiTile
          label="Site chats (30d)" value={data.sales_insights.chat_sessions_30d.toLocaleString()}
          hint={`${data.sales_insights.chat_messages_30d} messages`}
          icon={MessageSquare}
        />
      </div>

      {/* Funnel cards — one per existing module group */}
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="growth-hub-funnel">
        <FunnelCard
          icon={Users}
          accent="bg-gradient-to-br from-blue-500 to-blue-700"
          title="Trial pipeline"
          lede="Active trials + 30-day conversion"
          stats={[
            { label: 'Active', value: data.trials.active },
            { label: 'Converted (30d)', value: data.trials.converted_30d },
          ]}
          ctaLabel="Open Trials"
          deepLink={data.trials.deep_link}
          onJump={jump}
          testId="growth-card-trials"
        />
        <FunnelCard
          icon={Sparkles}
          accent="bg-gradient-to-br from-amber-400 to-fuchsia-600"
          title="SEO Autopilot"
          lede="Daily articles + blog traffic"
          stats={[
            { label: 'Published', value: data.seo.articles_published },
            { label: 'Drafts', value: data.seo.articles_draft },
            { label: 'Keywords queued', value: data.seo.keywords_queued },
            { label: 'Blog views', value: data.seo.blog_views_total.toLocaleString() },
          ]}
          ctaLabel="Open SEO Autopilot"
          deepLink={data.seo.deep_link}
          onJump={jump}
          testId="growth-card-seo"
        />
        <FunnelCard
          icon={Mail}
          accent="bg-gradient-to-br from-rose-500 to-fuchsia-600"
          title="Outbound emails"
          lede="All platform-sent emails (30d)"
          stats={[
            { label: 'Sent', value: data.outbound.sent_30d.toLocaleString() },
            { label: 'Failed', value: data.outbound.failed_30d.toLocaleString() },
          ]}
          ctaLabel="Open Outbound emails"
          deepLink={data.outbound.deep_link}
          onJump={jump}
          testId="growth-card-outbound"
        />
        <FunnelCard
          icon={TrendingUp}
          accent="bg-gradient-to-br from-emerald-500 to-emerald-700"
          title="CRM Pipeline"
          lede="Open deals + win/loss (30d)"
          stats={[
            { label: 'Open', value: data.pipeline.deals_open },
            { label: 'Value', value: `£${Number(data.pipeline.pipeline_value_gbp || 0).toLocaleString()}` },
            { label: 'Won (30d)', value: data.pipeline.deals_won_30d },
            { label: 'Lost (30d)', value: data.pipeline.deals_lost_30d },
          ]}
          ctaLabel="Open CRM"
          deepLink="crm-analytics"
          onJump={jump}
          testId="growth-card-pipeline"
        />
        <FunnelCard
          icon={MessageSquare}
          accent="bg-gradient-to-br from-violet-500 to-fuchsia-600"
          title="Sales Insights"
          lede="Themes from public-site AI chat"
          stats={[
            { label: 'Sessions (30d)', value: data.sales_insights.chat_sessions_30d },
            { label: 'Messages (30d)', value: data.sales_insights.chat_messages_30d },
          ]}
          ctaLabel="Open Sales Insights"
          deepLink={data.sales_insights.deep_link}
          onJump={jump}
          testId="growth-card-sales-insights"
        />
        <FunnelCard
          icon={Building2}
          accent="bg-gradient-to-br from-zinc-700 to-zinc-900"
          title="Companies in CRM"
          lede="Total prospect + customer companies"
          stats={[
            { label: 'Companies', value: data.pipeline.companies_total },
          ]}
          ctaLabel="Open Companies"
          deepLink="crm-companies"
          onJump={jump}
          testId="growth-card-companies"
        />
      </div>

      {/* B2B Journey templates — preset launcher pointing at the
          existing Marketing → Journeys runner. We don't duplicate it
          here; we just give the master admin a quick-launch list. */}
      <section data-testid="growth-hub-journeys">
        <div className="flex items-center gap-2 mb-3">
          <Workflow size={14} className="text-fuchsia-600"/>
          <h3 className="text-sm font-extrabold">B2B journey templates</h3>
          <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-400">
            Preset launcher · runs in Marketing → Journeys
          </span>
        </div>
        <div className="grid md:grid-cols-2 gap-3">
          {JOURNEY_TEMPLATES.map((t) => (
            <div key={t.id}
              className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 p-4"
              data-testid={`growth-journey-${t.id}`}
            >
              <p className="text-sm font-extrabold">{t.name}</p>
              <p className="text-[12px] text-zinc-600 dark:text-zinc-300 mt-1">{t.desc}</p>
              <div className="mt-3 grid gap-1 text-[11px] text-zinc-500">
                <p><span className="font-bold text-zinc-700 dark:text-zinc-200">Audience:</span> {t.audience}</p>
                <p><span className="font-bold text-zinc-700 dark:text-zinc-200">Tone:</span> {t.tone}</p>
              </div>
            </div>
          ))}
        </div>
        <p className="text-[11px] text-zinc-400 mt-3">
          These templates are a preview. When journeys are ready to fire,
          we&apos;ll wire each one to <code>/api/marketing/journeys</code> with the
          GymAxis brand voice locked in.
        </p>
      </section>
    </div>
  );
}
