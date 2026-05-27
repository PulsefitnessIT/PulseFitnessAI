/**
 * GymAxisGrowthHub — Master Admin → Growth → Marketing Studio
 * (Iter 220ag/220ah, replaces GrowthStudio.js).
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
 *   4. B2B Journey Templates — Launch (one-click) materialises the
 *      template into ``marketing_journeys`` and surfaces the
 *      resulting status; the runner stays in Marketing → Journeys.
 */
import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  Rocket, Loader2, ArrowRight, Sparkles, BookOpen, Mail,
  TrendingUp, MessageSquare, Users, Workflow, RefreshCw, Building2,
  Check, RotateCcw, Send,
} from 'lucide-react';
import { notify } from '@/components/notifications';

const API = process.env.REACT_APP_BACKEND_URL;
const auth = () => ({ Authorization: `Bearer ${localStorage.getItem('token')}` });

// B2B journey templates — server-driven so we can show "existing
// journey" state (already launched + status + run-count) right on the
// card. The launch button materialises the template into
// ``marketing_journeys`` for the master-admin org via
// ``POST /master-admin/growth/journey-templates/{id}/launch``.
const TEMPLATE_AUDIENCE_HINTS = {
  'cold-to-demo': 'New CRM contacts in target ICP (gym chains, 3+ sites)',
  'demo-booked': 'CRM deals in "Demo Booked" stage',
  'trial-conversion': 'Orgs with `is_trial = true`',
  'lost-revival': 'CRM deals stage = lost in last 12 months',
};
const TEMPLATE_TONE_HINTS = {
  'cold-to-demo': 'B2B SaaS · GymAxis brand voice',
  'demo-booked': 'Personal, partnership-first',
  'trial-conversion': 'Helpful, urgency only on day 13',
  'lost-revival': 'Low-pressure, news-led',
};

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

// JourneyTemplateCard — Iter 220ah. Materialise a B2B journey via
// POST /master-admin/growth/journey-templates/{id}/launch and surface
// the resulting status. Re-create archives the existing copy and
// spawns a fresh one.
const JOURNEY_RUNNER_URL = '/marketing?tab=journeys';

function JourneyTemplateCard({ t, onLaunched }) {
  const [busy, setBusy] = useState(false);
  const existing = t.existing_journey;

  const openInRunner = () => {
    try { window.open(JOURNEY_RUNNER_URL, '_blank', 'noopener,noreferrer'); }
    catch { window.location.href = JOURNEY_RUNNER_URL; }
  };

  const launch = async (mode) => {
    setBusy(true);
    try {
      const url = mode === 'recreate'
        ? `${API}/api/master-admin/growth/journey-templates/${t.id}/recreate`
        : `${API}/api/master-admin/growth/journey-templates/${t.id}/launch`;
      const r = await axios.post(url, {}, { headers: auth() });
      const created = r.data?.created;
      if (created) {
        notify.success(`Journey created: ${t.name}`);
      } else {
        notify.info('Journey already exists — opening in Journeys.');
      }
      onLaunched?.(r.data?.journey);
    } catch (e) {
      notify.error(e?.response?.data?.detail || 'Launch failed');
    } finally { setBusy(false); }
  };

  return (
    <div
      className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 p-4 flex flex-col gap-3"
      data-testid={`growth-journey-${t.id}`}
    >
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-extrabold">{t.name}</p>
          <p className="text-[12px] text-zinc-600 dark:text-zinc-300 mt-1">{t.description}</p>
        </div>
        {existing ? (
          <span
            className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-green-100 text-green-800 inline-flex items-center gap-1 shrink-0"
            data-testid={`growth-journey-${t.id}-existing-pill`}
            title={`Created ${existing.created_at || ''}`}
          >
            <Check size={9}/> Launched
          </span>
        ) : null}
      </div>
      <div className="grid gap-1 text-[11px] text-zinc-500">
        <p><span className="font-bold text-zinc-700 dark:text-zinc-200">Audience:</span> {TEMPLATE_AUDIENCE_HINTS[t.id] || '—'}</p>
        <p><span className="font-bold text-zinc-700 dark:text-zinc-200">Tone:</span> {TEMPLATE_TONE_HINTS[t.id] || '—'}</p>
        <p><span className="font-bold text-zinc-700 dark:text-zinc-200">Steps:</span> {t.node_count} email{t.node_count === 1 ? '' : 's'}</p>
        {existing?.metrics ? (
          <p><span className="font-bold text-zinc-700 dark:text-zinc-200">Entered:</span> {existing.metrics.entered || 0} contact{existing.metrics.entered === 1 ? '' : 's'}</p>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-2 mt-1">
        {existing ? (
          <>
            <button
              type="button" onClick={openInRunner}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold bg-fuchsia-600 text-white hover:bg-fuchsia-700"
              data-testid={`growth-journey-${t.id}-open`}
            >
              <Send size={11}/> Open in Journeys <ArrowRight size={11}/>
            </button>
            <button
              type="button" onClick={() => launch('recreate')} disabled={busy}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold border border-zinc-200 dark:border-zinc-700 text-zinc-700 dark:text-zinc-100 hover:border-fuchsia-400 disabled:opacity-50"
              data-testid={`growth-journey-${t.id}-recreate`}
            >
              {busy ? <Loader2 size={11} className="animate-spin"/> : <RotateCcw size={11}/>}
              Re-create
            </button>
          </>
        ) : (
          <button
            type="button" onClick={() => launch('launch')} disabled={busy}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold bg-gradient-to-r from-fuchsia-600 to-blue-600 text-white hover:opacity-90 disabled:opacity-50"
            data-testid={`growth-journey-${t.id}-launch`}
          >
            {busy ? <Loader2 size={11} className="animate-spin"/> : <Rocket size={11}/>}
            Launch journey
          </button>
        )}
      </div>
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
  // Iter 220ah — server-driven B2B journey template list. We keep it
  // in its own state slot so launching a template doesn't reload the
  // whole overview payload.
  const [templates, setTemplates] = useState(null);
  const [templatesErr, setTemplatesErr] = useState(null);

  const load = useCallback(async () => {
    setBusy(true); setErr(null);
    try {
      const r = await axios.get(`${API}/api/master-admin/growth/overview`, { headers: auth() });
      setData(r.data);
    } catch (e) {
      setErr(e?.response?.data?.detail || 'Could not load growth overview');
    } finally { setBusy(false); }
  }, []);

  const loadTemplates = useCallback(async () => {
    setTemplatesErr(null);
    try {
      const r = await axios.get(
        `${API}/api/master-admin/growth/journey-templates`,
        { headers: auth() },
      );
      setTemplates(r.data?.templates || []);
    } catch (e) {
      setTemplatesErr(e?.response?.data?.detail || 'Could not load journey templates');
    }
  }, []);

  useEffect(() => { load(); loadTemplates(); }, [load, loadTemplates]);

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

      {/* B2B Journey templates — server-driven launcher. The "Launch"
          button materialises the template into ``marketing_journeys``
          for the master-admin org via the growth-hub launch endpoint.
          Re-create archives the previous copy and spawns a fresh one.
          The journey runs in Marketing → Journeys — we don't duplicate
          the canvas here. */}
      <section data-testid="growth-hub-journeys">
        <div className="flex items-center gap-2 mb-3">
          <Workflow size={14} className="text-fuchsia-600"/>
          <h3 className="text-sm font-extrabold">B2B journey templates</h3>
          <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-400">
            One-click launch · runs in Marketing → Journeys
          </span>
          <button
            type="button" onClick={loadTemplates}
            className="ml-auto text-[11px] inline-flex items-center gap-1 text-zinc-500 hover:text-zinc-900"
            data-testid="growth-hub-journeys-refresh"
            title="Refresh launch status"
          >
            <RefreshCw size={11}/> Refresh
          </button>
        </div>
        {templatesErr ? (
          <div className="rounded-md border border-rose-200 bg-rose-50 text-rose-700 px-3 py-2 text-sm" data-testid="growth-hub-journeys-error">
            {templatesErr}
          </div>
        ) : !templates ? (
          <div className="text-zinc-500 text-sm inline-flex items-center gap-2" data-testid="growth-hub-journeys-loading">
            <Loader2 size={14} className="animate-spin"/> Loading templates…
          </div>
        ) : (
          <div className="grid md:grid-cols-2 gap-3">
            {templates.map((t) => (
              <JourneyTemplateCard
                key={t.id} t={t} onLaunched={loadTemplates}
              />
            ))}
          </div>
        )}
        <p className="text-[11px] text-zinc-400 mt-3">
          Each &quot;Launch&quot; creates a multi-step email journey in
          <code className="mx-1">marketing_journeys</code>
          scoped to the master-admin org. Edit the steps in
          Marketing &rarr; Journeys, then test-send or enrol contacts there.
        </p>
      </section>
    </div>
  );
}
