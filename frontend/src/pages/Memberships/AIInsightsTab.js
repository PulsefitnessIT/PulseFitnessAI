/**
 * Memberships → AI Insights (Phase 5).
 *
 * Four sub-views, mobile-first stacked cards on small screens:
 *   1. Demand forecast — predicted fill % per future class
 *   2. Underperformers — chronic dead slots
 *   3. Pricing recs (Claude) — raise/hold/lower per plan
 *   4. New-class suggestions (Claude) — proposed types + slots
 *
 * The two LLM endpoints are pull-on-demand (button click) to avoid
 * burning the LLM key on idle tab loads. The two deterministic ones
 * load on tab entry.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import {
  Brain, TrendingUp, TrendingDown, AlertTriangle, Sparkles,
  PoundSterling, Users, Calendar, Loader2, RefreshCw, Lightbulb,
  ArrowUpRight, ArrowDownRight, Minus, Trophy, Clock,
} from 'lucide-react';
import { notify } from '@/components/notifications';
import { notifyApiError } from '@/lib/formatApiError';


const SUB_TABS = [
  { id: 'demand',   label: 'Demand',         icon: TrendingUp,   description: 'Predicted fill % for upcoming classes' },
  { id: 'underper', label: 'Underperformers', icon: AlertTriangle, description: 'Chronic dead slots to cancel or replace' },
  { id: 'pricing',  label: 'Pricing',        icon: PoundSterling, description: 'AI-driven price-move recommendations' },
  { id: 'classes',  label: 'New classes',    icon: Lightbulb,    description: 'Class types that could fill capacity' },
];


export default function AIInsightsTab({ API, headers }) {
  const [view, setView] = useState('demand');

  return (
    <div data-testid="mbr-ai-insights">
      {/* Sub-tab pills — horizontal scroll on mobile */}
      <div className="flex gap-2 overflow-x-auto -mx-1 px-1 pb-2 mb-4">
        {SUB_TABS.map((t) => {
          const Icon = t.icon;
          const active = view === t.id;
          return (
            <button key={t.id} onClick={() => setView(t.id)}
              className={`flex-shrink-0 px-3 py-2 rounded-md text-xs font-extrabold flex items-center gap-1.5 border transition ${
                active
                  ? 'bg-fuchsia-500 text-white border-fuchsia-500'
                  : 'bg-transparent border-[color:var(--theme-border)] text-[color:var(--theme-text-muted)]'
              }`}
              data-testid={`mbr-ai-tab-${t.id}`}>
              <Icon size={11} /> {t.label}
            </button>
          );
        })}
      </div>

      {view === 'demand'   && <DemandView   API={API} headers={headers} />}
      {view === 'underper' && <UnderView    API={API} headers={headers} />}
      {view === 'pricing'  && <PricingView  API={API} headers={headers} />}
      {view === 'classes'  && <ClassesView  API={API} headers={headers} />}
    </div>
  );
}


/* ────────────── 1. Demand forecast ────────────── */


function DemandView({ API, headers }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    axios.get(`${API}/memberships/ai/demand-forecast?weeks_back=8&weeks_ahead=2`, { headers })
      .then((r) => setData(r.data))
      .catch((e) => notifyApiError(notify, e, 'Failed to load forecast'))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  if (loading) return <Spinner />;
  if (!data || data.count === 0) {
    return <Empty icon={TrendingUp} title="Not enough history yet" hint="Run classes for at least 2 weeks and we can predict next week's fills." />;
  }

  const high = (data.rows || []).filter((r) => r.action === 'demand_high');
  const low  = (data.rows || []).filter((r) => r.action === 'demand_low');

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        <Stat label="High demand" value={high.length} tone="emerald" icon={TrendingUp} />
        <Stat label="Low demand"  value={low.length}  tone="amber"   icon={TrendingDown} />
        <Stat label="Confident"   value={data.summary?.high_confidence_count || 0} tone="violet" icon={Brain} />
      </div>

      {high.length > 0 && (
        <Section title="Likely to overfill" tone="emerald" testid="mbr-ai-demand-high">
          {high.slice(0, 10).map((r) => <ForecastRow key={r.occurrence_id} r={r} />)}
        </Section>
      )}
      {low.length > 0 && (
        <Section title="Likely to underfill" tone="amber" testid="mbr-ai-demand-low">
          {low.slice(0, 10).map((r) => <ForecastRow key={r.occurrence_id} r={r} />)}
        </Section>
      )}

      <details className="rounded-xl border border-[color:var(--theme-border)] bg-white dark:bg-zinc-900/[0.03] p-3">
        <summary className="cursor-pointer text-xs font-bold text-[color:var(--theme-text-muted)]">
          See all {data.count} predictions
        </summary>
        <div className="mt-2 space-y-1.5">
          {(data.rows || []).map((r) => <ForecastRow key={r.occurrence_id} r={r} />)}
        </div>
      </details>
    </div>
  );
}


function ForecastRow({ r }) {
  const tone = r.predicted_fill_pct >= 90 ? 'emerald'
              : r.predicted_fill_pct >= 60 ? 'sky'
              : r.predicted_fill_pct >= 30 ? 'amber'
              : 'red';
  const tones = {
    emerald: 'bg-emerald-500/15 text-emerald-500',
    sky:     'bg-sky-500/15 text-sky-500',
    amber:   'bg-amber-500/15 text-amber-500',
    red:     'bg-red-500/15 text-red-400',
    violet:  'bg-violet-500/15 text-violet-400',
  };
  const start = r.starts_at ? new Date(r.starts_at) : null;
  return (
    <div className="rounded-lg border border-[color:var(--theme-border)] bg-white dark:bg-zinc-900/[0.03] p-3 flex items-start gap-3"
      data-testid={`mbr-ai-forecast-${r.occurrence_id}`}>
      <div className={`flex-shrink-0 w-12 text-center px-2 py-1 rounded-md ${tones[tone]} font-extrabold`}>
        <p className="text-base">{Math.round(r.predicted_fill_pct)}%</p>
        <p className="text-[8px] uppercase tracking-wider">pred.</p>
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-bold text-sm truncate">{r.name}</p>
        <p className="text-[11px] text-[color:var(--theme-text-muted)] truncate">
          {start && start.toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
          {r.instructor_name && ` · ${r.instructor_name}`}
        </p>
        <p className="text-[10px] text-[color:var(--theme-text-muted)] mt-0.5">
          Currently {r.current_bookings}/{r.capacity} ({r.current_fill_pct}%) · {r.confidence} confidence · {r.samples} samples
        </p>
      </div>
    </div>
  );
}


/* ────────────── 2. Underperformers ────────────── */


function UnderView({ API, headers }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [params, setParams] = useState({ weeks: 4, fill: 50 });

  const load = (p = params) => {
    setLoading(true);
    axios.get(`${API}/memberships/ai/underperformers?weeks=${p.weeks}&fill_threshold_pct=${p.fill}&min_occurrences=3`, { headers })
      .then((r) => setData(r.data))
      .catch((e) => notifyApiError(notify, e, 'Failed'))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  return (
    <div>
      <div className="flex items-center gap-2 mb-3 overflow-x-auto -mx-1 px-1 pb-1">
        {[2, 4, 8].map((w) => (
          <button key={w} onClick={() => { const p = { ...params, weeks: w }; setParams(p); load(p); }}
            className={`flex-shrink-0 px-2.5 py-1 rounded-md text-[11px] font-bold border transition ${
              params.weeks === w
                ? 'bg-amber-500 text-white border-amber-500'
                : 'bg-transparent border-[color:var(--theme-border)] text-[color:var(--theme-text-muted)]'
            }`}
            data-testid={`mbr-ai-under-weeks-${w}`}>
            Last {w}w
          </button>
        ))}
        <span className="text-[10px] uppercase tracking-wider font-bold text-[color:var(--theme-text-muted)] ml-2">Threshold</span>
        {[40, 50, 60].map((f) => (
          <button key={f} onClick={() => { const p = { ...params, fill: f }; setParams(p); load(p); }}
            className={`flex-shrink-0 px-2.5 py-1 rounded-md text-[11px] font-bold border transition ${
              params.fill === f
                ? 'bg-amber-500 text-white border-amber-500'
                : 'bg-transparent border-[color:var(--theme-border)] text-[color:var(--theme-text-muted)]'
            }`}
            data-testid={`mbr-ai-under-fill-${f}`}>
            &lt;{f}%
          </button>
        ))}
      </div>
      {loading ? <Spinner /> : !data || data.count === 0 ? (
        <Empty icon={Trophy} title={`No underperformers in the last ${params.weeks} weeks`} hint={`Every class is averaging above ${params.fill}% fill — well done.`} />
      ) : (
        <div className="space-y-2">
          {data.rows.map((r) => (
            <div key={r.template_id}
              className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-3 sm:p-4"
              data-testid={`mbr-ai-under-${r.template_id}`}>
              <div className="flex items-start gap-3">
                <div className="flex-shrink-0 w-10 h-10 rounded-md bg-amber-500/20 grid place-items-center text-amber-500">
                  <AlertTriangle size={14} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-bold truncate">{r.name}</p>
                  <p className="text-[11px] text-[color:var(--theme-text-muted)] mt-0.5">
                    {r.weekday !== undefined && new Date(2026, 0, r.weekday + 5).toLocaleDateString([], { weekday: 'long' })}
                    {r.start_time && ` · ${r.start_time}`}
                    {r.duration_min && ` · ${r.duration_min} min`}
                    {r.instructors?.length > 0 && ` · ${r.instructors.join(', ')}`}
                  </p>
                </div>
                <div className="text-right flex-shrink-0">
                  <p className="text-xl font-extrabold text-amber-500">{r.avg_fill_pct}%</p>
                  <p className="text-[9px] uppercase tracking-wider font-bold text-[color:var(--theme-text-muted)]">avg fill</p>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2 mt-3">
                <Mini label="Sessions" value={r.occurrences} />
                <Mini label="Lost capacity" value={r.lost_capacity} />
                <Mini label="No-shows" value={r.no_show_count} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


/* ────────────── 3. Pricing recs (Claude) ────────────── */


function PricingView({ API, headers }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const generate = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/memberships/ai/pricing-recommendations`, { headers, timeout: 120000 });
      setData(r.data);
    } catch (e) {
      notifyApiError(notify, e, 'Failed to generate pricing recs');
    }
    setLoading(false);
  };

  if (!data) {
    return (
      <div className="rounded-2xl border border-fuchsia-500/30 bg-fuchsia-500/5 p-6 sm:p-8 text-center" data-testid="mbr-ai-pricing-empty">
        <PoundSterling size={32} className="mx-auto text-fuchsia-500 mb-3" />
        <p className="text-base font-extrabold mb-1">AI pricing recommendations</p>
        <p className="text-sm text-[color:var(--theme-text-muted)] max-w-md mx-auto mb-4">
          Claude analyses your last 90 days of demand, revenue, trial conversions, and waitlist depth to suggest price moves per plan.
        </p>
        <button onClick={generate} disabled={loading}
          className="px-4 py-2.5 rounded-md text-sm font-extrabold flex items-center gap-1.5 mx-auto disabled:opacity-50"
          style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
          data-testid="mbr-ai-pricing-run">
          {loading ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
          Generate recommendations
        </button>
      </div>
    );
  }

  const recs = data.recommendations || [];
  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-fuchsia-500/30 bg-fuchsia-500/5 p-3 flex items-start gap-3">
        <Brain size={16} className="text-fuchsia-500 flex-shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold">{data.summary || 'Strategy summary'}</p>
          <p className="text-[11px] text-[color:var(--theme-text-muted)] mt-0.5">
            Org fill: {data.org_signals?.fill_pct}% · waitlist: {data.org_signals?.waitlist_ratio_pct}% · generated {new Date(data.generated_at).toLocaleString()}
          </p>
        </div>
        <button onClick={generate} disabled={loading}
          className="flex-shrink-0 p-2 rounded hover:bg-fuchsia-500/10"
          title="Regenerate"
          data-testid="mbr-ai-pricing-refresh">
          {loading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
        </button>
      </div>
      {recs.map((r) => <PricingRow key={r.plan_id} rec={r} />)}
    </div>
  );
}


function PricingRow({ rec }) {
  const dir = rec.direction || 'hold';
  const Icon = dir === 'raise' ? ArrowUpRight : dir === 'lower' ? ArrowDownRight : Minus;
  const tone = dir === 'raise' ? 'text-emerald-500'
              : dir === 'lower' ? 'text-amber-500'
              : 'text-zinc-500';
  const bg = dir === 'raise' ? 'bg-emerald-500/10 border-emerald-500/30'
            : dir === 'lower' ? 'bg-amber-500/10 border-amber-500/30'
            : 'bg-zinc-500/5 border-[color:var(--theme-border)]';
  const delta = (rec.suggested_pence || 0) - (rec.current_pence || 0);
  const deltaPct = rec.current_pence > 0
    ? Math.round((delta / rec.current_pence) * 100)
    : 0;
  return (
    <div className={`rounded-xl border p-3 sm:p-4 ${bg}`}
      data-testid={`mbr-ai-pricing-${rec.plan_id}`}>
      <div className="flex items-start gap-3 flex-wrap">
        <div className="flex-1 min-w-0">
          <p className="font-bold truncate">{rec.plan_name}</p>
          <p className="text-[11px] text-[color:var(--theme-text-muted)] mt-0.5 capitalize">
            <span className={`inline-flex items-center gap-1 font-extrabold ${tone} mr-2`}>
              <Icon size={10} /> {dir}
            </span>
            <span className="ml-1">{rec.confidence} confidence</span>
          </p>
        </div>
        <div className="text-right flex-shrink-0">
          <p className="text-[10px] uppercase tracking-wider font-bold text-[color:var(--theme-text-muted)]">From / to</p>
          <p className="text-sm">
            <span className="line-through opacity-60">£{(rec.current_pence / 100).toFixed(2)}</span>
            <span className={`ml-1.5 text-base font-extrabold ${tone}`}>£{(rec.suggested_pence / 100).toFixed(2)}</span>
          </p>
          {delta !== 0 && (
            <p className={`text-[10px] font-bold ${tone}`}>
              {delta > 0 ? '+' : ''}{deltaPct}% (£{(delta / 100).toFixed(2)})
            </p>
          )}
        </div>
      </div>
      {rec.rationale && (
        <p className="text-[12px] text-[color:var(--theme-text-muted)] mt-2 leading-relaxed">
          {rec.rationale}
        </p>
      )}
    </div>
  );
}


/* ────────────── 4. New-class suggestions (Claude) ────────────── */


function ClassesView({ API, headers }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const generate = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/memberships/ai/class-suggestions`, { headers, timeout: 120000 });
      setData(r.data);
    } catch (e) {
      notifyApiError(notify, e, 'Failed to generate suggestions');
    }
    setLoading(false);
  };

  if (!data) {
    return (
      <div className="rounded-2xl border border-fuchsia-500/30 bg-fuchsia-500/5 p-6 sm:p-8 text-center" data-testid="mbr-ai-classes-empty">
        <Lightbulb size={32} className="mx-auto text-fuchsia-500 mb-3" />
        <p className="text-base font-extrabold mb-1">AI new-class suggestions</p>
        <p className="text-sm text-[color:var(--theme-text-muted)] max-w-md mx-auto mb-4">
          Claude looks at your top-performing classes, waitlist depth, and unmet demand signals to propose 3-5 new class types.
        </p>
        <button onClick={generate} disabled={loading}
          className="px-4 py-2.5 rounded-md text-sm font-extrabold flex items-center gap-1.5 mx-auto disabled:opacity-50"
          style={{ background: 'var(--color-brand-cyan)', color: 'var(--color-surface-darker)' }}
          data-testid="mbr-ai-classes-run">
          {loading ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
          Suggest classes
        </button>
      </div>
    );
  }

  const sugs = data.suggestions || [];
  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-fuchsia-500/30 bg-fuchsia-500/5 p-3 flex items-start gap-3">
        <Brain size={16} className="text-fuchsia-500 flex-shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold">{data.summary}</p>
          <p className="text-[11px] text-[color:var(--theme-text-muted)] mt-0.5">
            Generated {new Date(data.generated_at).toLocaleString()}
          </p>
        </div>
        <button onClick={generate} disabled={loading}
          className="flex-shrink-0 p-2 rounded hover:bg-fuchsia-500/10"
          title="Regenerate"
          data-testid="mbr-ai-classes-refresh">
          {loading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
        </button>
      </div>
      {sugs.map((s, i) => (
        <div key={i}
          className="rounded-xl border border-[color:var(--theme-border)] bg-white dark:bg-zinc-900/[0.03] p-3 sm:p-4"
          data-testid={`mbr-ai-class-sug-${i}`}>
          <div className="flex items-start gap-3 flex-wrap">
            <div className="flex-shrink-0 w-10 h-10 rounded-md bg-fuchsia-500/15 grid place-items-center text-fuchsia-500">
              <Lightbulb size={14} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-extrabold text-base truncate">{s.name}</p>
              <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-[color:var(--theme-text-muted)] mt-0.5">
                {s.best_weekday && <span><Calendar size={9} className="inline mr-0.5" />{s.best_weekday}</span>}
                {s.best_time && <span><Clock size={9} className="inline mr-0.5" />{s.best_time}</span>}
                {s.duration_min && <span>{s.duration_min} min</span>}
                {s.confidence && <span className="uppercase font-bold">{s.confidence} conf.</span>}
              </div>
            </div>
          </div>
          {s.rationale && (
            <p className="text-[12px] text-[color:var(--theme-text-muted)] mt-2 leading-relaxed">
              {s.rationale}
            </p>
          )}
          {s.expected_audience && (
            <p className="text-[11px] mt-2 inline-flex items-center gap-1 px-2 py-1 rounded bg-[rgb(var(--rgb-brand-cyan)/0.15)] text-[var(--color-brand-cyan)]">
              <Users size={9} /> {s.expected_audience}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}


/* ────────────── Shared bits ────────────── */


function Stat({ label, value, tone = 'emerald', icon: Icon }) {
  const tones = {
    emerald: 'text-emerald-500',
    amber:   'text-amber-500',
    red:     'text-red-400',
    violet:  'text-violet-400',
  };
  return (
    <div className="rounded-lg border border-[color:var(--theme-border)] bg-white dark:bg-zinc-900/[0.03] p-3">
      <p className="text-[9px] uppercase tracking-wider font-bold text-[color:var(--theme-text-muted)] flex items-center gap-1">
        {Icon && <Icon size={9} />} {label}
      </p>
      <p className={`text-xl font-extrabold mt-0.5 ${tones[tone]}`}>{value}</p>
    </div>
  );
}


function Mini({ label, value }) {
  return (
    <div className="rounded bg-white dark:bg-zinc-900/[0.04] p-1.5 text-center border border-[color:var(--theme-border)]">
      <p className="text-[9px] uppercase tracking-wider font-bold text-[color:var(--theme-text-muted)]">{label}</p>
      <p className="text-sm font-extrabold mt-0.5">{value}</p>
    </div>
  );
}


function Section({ title, tone = 'emerald', testid, children }) {
  const dot = {
    emerald: 'bg-emerald-500',
    amber:   'bg-amber-500',
    sky:     'bg-sky-500',
  }[tone] || 'bg-zinc-500';
  return (
    <div className="space-y-1.5" data-testid={testid}>
      <div className="flex items-center gap-2">
        <span className={`inline-block w-2 h-2 rounded-full ${dot}`}></span>
        <h3 className="text-[10px] uppercase tracking-[0.18em] font-extrabold text-[color:var(--theme-text-muted)]">{title}</h3>
      </div>
      {children}
    </div>
  );
}


function Spinner() {
  return (
    <div className="flex items-center justify-center py-10 text-[color:var(--theme-text-muted)] text-sm gap-2">
      <Loader2 size={14} className="animate-spin" /> Loading…
    </div>
  );
}


function Empty({ icon: Icon, title, hint }) {
  return (
    <div className="rounded-xl border border-dashed border-[color:var(--theme-border)] p-10 text-center">
      <Icon size={32} className="mx-auto text-[color:var(--theme-text-muted)] mb-3" />
      <p className="text-sm font-bold">{title}</p>
      {hint && <p className="text-xs text-[color:var(--theme-text-muted)] mt-1 max-w-sm mx-auto">{hint}</p>}
    </div>
  );
}
