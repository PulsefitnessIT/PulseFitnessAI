/**
 * Shared module deep-dive template — iter 215ao–215aq.
 *
 * Renders every section in the spec:
 *   1. Hero (outcome-focused headline)
 *   2. Problem → Solution
 *   3. Feature breakdown
 *   4. Visual UI sections (alternating)
 *   5. AI capabilities
 *   6. Integration with other modules
 *   7. Results / benefits
 *   8. CTA
 *
 * A page just supplies a `module` config object — see ./modules/*.js
 */
import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Sparkles, CheckCircle2 } from 'lucide-react';

import './marketing.css';
import MarketingShell from './MarketingShell';
import { openTrial } from './TrialSignupModal';
import { openPreview } from './ProductPreviewModal';
import SiteCalculatorUpsell from './SiteCalculatorUpsell';

export default function ModulePage({ module: m }) {
  return (
    <MarketingShell>
      <Hero m={m} />
      <ProblemSolution m={m} />
      <Features m={m} />
      <VisualSections m={m} />
      <AISection m={m} />
      <Integrations m={m} />
      <Results m={m} />
      <SiteCalculatorUpsell accent={m.color} />
      <Cta m={m} />
    </MarketingShell>
  );
}

function Hero({ m }) {
  const Icon = m.icon;
  return (
    <section className="gx-grid-bg" data-testid={`mod-${m.id}-hero`}>
      <div className="max-w-7xl mx-auto px-6 lg:px-8 pt-14 pb-20 lg:pt-20 lg:pb-28 grid lg:grid-cols-12 gap-12 items-center">
        <div className="lg:col-span-7">
          <span className="inline-flex items-center gap-2 rounded-full bg-white border border-slate-200 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em]" style={{ color: m.color }}>
            <Icon size={12} />{m.name} module
          </span>
          <h1 className="mt-5 text-5xl md:text-6xl tracking-tighter font-black leading-[1.04]">
            {m.heroLine1}<br /><span style={{ color: m.color }}>{m.heroLine2}</span>
          </h1>
          <p className="mt-6 text-lg md:text-xl text-slate-600 leading-relaxed max-w-xl">{m.heroSubtitle}</p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <button type="button" onClick={openTrial} className="gx-cta inline-flex items-center gap-1.5 rounded-full px-6 py-3 text-sm font-bold">
              Start Free Trial <ArrowRight size={15} />
            </button>
            <Link to="/contact" className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 px-6 py-3 text-sm font-bold text-slate-700 hover:bg-slate-50 transition-colors">
              Talk to sales <ArrowRight size={15} />
            </Link>
            <button type="button" onClick={openPreview} className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 px-6 py-3 text-sm font-bold text-slate-700 hover:bg-slate-50 transition-colors">
              See it in action <ArrowRight size={15} />
            </button>
          </div>
        </div>
        <div className="lg:col-span-5">
          <HeroVisual m={m} />
        </div>
      </div>
    </section>
  );
}

function HeroVisual({ m }) {
  const Icon = m.icon;
  return (
    <div className="relative aspect-square max-w-md mx-auto">
      <div className="absolute inset-[10%] rounded-full opacity-20 blur-3xl" style={{ background: m.color }} />
      <div className="relative w-full h-full rounded-[36px] gx-glass p-8 flex flex-col">
        <div className="w-14 h-14 rounded-2xl flex items-center justify-center text-white" style={{ background: m.color }}>
          <Icon size={26} />
        </div>
        <p className="mt-5 text-xs uppercase tracking-[0.2em] font-bold text-slate-400">Live preview</p>
        <p className="mt-1 text-2xl font-bold tracking-tight">{m.heroVisualHeadline}</p>
        <div className="mt-auto space-y-2">
          {(m.heroVisualLines || []).map((line, i) => (
            <div key={i} className="flex items-center justify-between rounded-xl bg-white/80 border border-slate-100 px-3 py-2 text-sm">
              <span className="font-semibold text-slate-700">{line.label}</span>
              <span className="font-bold" style={{ color: m.color }}>{line.value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ProblemSolution({ m }) {
  return (
    <section className="py-24 md:py-32 bg-white" data-testid={`mod-${m.id}-problem`}>
      <div className="max-w-7xl mx-auto px-6 lg:px-8 grid lg:grid-cols-2 gap-14">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">The problem</p>
          <h2 className="mt-3 text-3xl md:text-4xl font-bold tracking-tight">{m.problemHeadline}</h2>
          <p className="mt-4 text-base md:text-lg text-slate-600 leading-relaxed">{m.problemBody}</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.2em] font-bold" style={{ color: m.color }}>How GymAxis solves it</p>
          <h2 className="mt-3 text-3xl md:text-4xl font-bold tracking-tight">{m.solutionHeadline}</h2>
          <p className="mt-4 text-base md:text-lg text-slate-600 leading-relaxed">{m.solutionBody}</p>
        </div>
      </div>
    </section>
  );
}

function Features({ m }) {
  return (
    <section className="py-24 md:py-32 bg-slate-50/60" data-testid={`mod-${m.id}-features`}>
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="max-w-2xl">
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">Capabilities</p>
          <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">{m.featuresHeadline}</h2>
        </div>
        <div className="mt-12 grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {m.features.map((f, i) => {
            const FIcon = f.icon;
            return (
              <div key={i} className="gx-card rounded-3xl border border-slate-100 bg-white p-7" data-testid={`mod-${m.id}-feature-${i}`}>
                <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: `${m.color}14`, color: m.color }}>
                  <FIcon size={18} />
                </div>
                <h3 className="mt-5 text-lg font-bold tracking-tight">{f.title}</h3>
                <p className="mt-1 text-sm text-slate-600 leading-relaxed">{f.body}</p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function VisualSections({ m }) {
  return (
    <section className="py-24 md:py-32 bg-white" data-testid={`mod-${m.id}-visuals`}>
      <div className="max-w-7xl mx-auto px-6 lg:px-8 space-y-24">
        {m.visualSections.map((v, i) => (
          <div key={i} className={`grid lg:grid-cols-2 gap-12 items-center ${i % 2 === 1 ? 'lg:[direction:rtl]' : ''}`}>
            <div className="lg:[direction:ltr]">
              <p className="text-xs uppercase tracking-[0.2em] font-bold" style={{ color: m.color }}>{v.eyebrow}</p>
              <h3 className="mt-3 text-3xl md:text-4xl font-bold tracking-tight">{v.title}</h3>
              <p className="mt-4 text-base md:text-lg text-slate-600 leading-relaxed">{v.body}</p>
              <ul className="mt-5 space-y-2">
                {(v.bullets || []).map((b, j) => (
                  <li key={j} className="flex items-start gap-2 text-sm text-slate-700">
                    <CheckCircle2 size={15} className="mt-0.5 shrink-0" style={{ color: m.color }} />
                    <span>{b}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="lg:[direction:ltr] aspect-[4/3] rounded-3xl border border-slate-200 gx-glass p-6 flex flex-col">
              <p className="text-[10px] uppercase tracking-[0.22em] font-bold text-slate-400">{v.visualEyebrow || v.eyebrow}</p>
              <p className="mt-1 text-lg font-bold tracking-tight">{v.visualHeadline || v.title}</p>
              <div className="mt-4 flex-1 grid gap-2 content-start">
                {(v.visualRows || []).map((row, k) => (
                  <div key={k} className="rounded-xl bg-slate-50/80 border border-slate-100 px-3 py-2.5 text-sm flex items-center justify-between">
                    <span className="font-semibold text-slate-700">{row.l}</span>
                    <span className="font-bold" style={{ color: row.tone === 'mute' ? '#94A3B8' : m.color }}>{row.r}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function AISection({ m }) {
  return (
    <section className="py-24 md:py-28 bg-slate-50/60" data-testid={`mod-${m.id}-ai`}>
      <div className="max-w-7xl mx-auto px-6 lg:px-8 grid lg:grid-cols-2 gap-12 items-center">
        <div>
          <p className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.2em] font-bold" style={{ color: m.color }}>
            <Sparkles size={13} />AI inside
          </p>
          <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">{m.aiHeadline}</h2>
          <p className="mt-4 text-base md:text-lg text-slate-600 leading-relaxed">{m.aiBody}</p>
        </div>
        <div className="grid gap-3">
          {m.aiCapabilities.map((cap, i) => (
            <div key={i} className="rounded-2xl border border-slate-200 bg-white p-5 flex gap-4">
              <span className="shrink-0 w-9 h-9 rounded-xl flex items-center justify-center text-white" style={{ background: `linear-gradient(135deg, ${m.color}, var(--gx-brand-to))` }}>
                <Sparkles size={15} />
              </span>
              <div>
                <p className="font-bold tracking-tight">{cap.title}</p>
                <p className="mt-0.5 text-sm text-slate-600 leading-relaxed">{cap.body}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Integrations({ m }) {
  return (
    <section className="py-24 md:py-28 bg-white" data-testid={`mod-${m.id}-integrations`}>
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="max-w-2xl">
          <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">Connected platform</p>
          <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">{m.integrationsHeadline}</h2>
        </div>
        <div className="mt-10 grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {m.integrations.map((it, i) => {
            const IIcon = it.icon;
            return (
              <Link key={i} to={it.to} className="gx-card flex items-start gap-3 rounded-2xl border border-slate-100 bg-slate-50/40 p-5">
                <span className="shrink-0 w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: `${it.color}14`, color: it.color }}>
                  <IIcon size={17} />
                </span>
                <div>
                  <p className="font-bold tracking-tight">{it.name}</p>
                  <p className="mt-0.5 text-sm text-slate-600 leading-snug">{it.body}</p>
                </div>
              </Link>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function Results({ m }) {
  return (
    <section className="py-24 md:py-28 bg-slate-50/60" data-testid={`mod-${m.id}-results`}>
      <div className="max-w-7xl mx-auto px-6 lg:px-8 text-center">
        <p className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">Operator outcomes</p>
        <h2 className="mt-3 text-4xl md:text-5xl font-bold tracking-tight">{m.resultsHeadline}</h2>
        <div className="mt-12 grid grid-cols-2 lg:grid-cols-4 gap-6">
          {m.results.map((r, i) => (
            <div key={i} className="rounded-3xl border border-slate-100 bg-white p-6">
              <div className="text-4xl font-black tracking-tighter" style={{ color: m.color }}>{r.value}</div>
              <p className="mt-2 text-sm text-slate-600 leading-snug">{r.label}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Cta({ m }) {
  return (
    <section className="py-24 md:py-28" data-testid={`mod-${m.id}-cta`}>
      <div className="max-w-5xl mx-auto px-6 lg:px-8">
        <div
          className="relative overflow-hidden rounded-[36px] p-10 md:p-14 text-center text-white"
          style={{ background: `linear-gradient(135deg, ${m.color} 0%, var(--gx-brand-to) 100%)` }}
        >
          <div className="absolute inset-0 opacity-25 mix-blend-overlay" style={{ background: 'radial-gradient(circle at 30% 20%, rgba(255,255,255,.7), transparent 50%), radial-gradient(circle at 80% 80%, rgba(255,255,255,.5), transparent 50%)' }} />
          <div className="relative">
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-black tracking-tighter leading-[1.06]">{m.ctaHeadline}</h2>
            <p className="mt-4 text-base md:text-lg text-white/90 max-w-xl mx-auto">{m.ctaSubtitle}</p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              <button type="button" onClick={openTrial} className="inline-flex items-center gap-1.5 rounded-full bg-white text-slate-900 px-7 py-3.5 text-sm font-bold shadow-xl hover:shadow-2xl transition-shadow">Start Free Trial <ArrowRight size={15} /></button>
              <Link to="/contact" className="inline-flex items-center gap-1.5 rounded-full border-2 border-white/40 text-white px-7 py-3.5 text-sm font-bold hover:bg-white/10 transition-colors">Talk to sales <ArrowRight size={15} /></Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
