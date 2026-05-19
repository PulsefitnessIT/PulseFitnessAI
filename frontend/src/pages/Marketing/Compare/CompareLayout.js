/**
 * CompareLayout — shared visual scaffold for /compare/* SEO pages.
 *
 * Each comparison page passes:
 *   - competitor: { name, slug, tagline, founded?, hq?, focus? }
 *   - hero: { headline, subheadline }
 *   - matrix: [{ feature, gymaxis, competitor, notes? }]
 *   - winsForGymAxis: [{ title, body }]
 *   - whenCompetitorWins: [{ title, body }]
 *   - faqs: [{ q, a }]
 *
 * Renders schema.org `Product` + `FAQPage` JSON-LD for rich-result eligibility.
 */
import React from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight, CheckCircle2, MinusCircle, ShieldCheck,
  Sparkles, BookOpen, ChevronRight,
} from 'lucide-react';

import '../marketing.css';
import MarketingShell from '../MarketingShell';
import { openTrial } from '../TrialSignupModal';
import MigrationGuarantee from '../MigrationGuarantee';

export default function CompareLayout({
  competitor, hero, matrix, winsForGymAxis, whenCompetitorWins, faqs,
}) {
  // Set page title + meta description for SEO. We do this imperatively
  // because the marketing site is a single SPA without react-helmet.
  React.useEffect(() => {
    const prevTitle = document.title;
    const prevDesc = document.querySelector('meta[name="description"]')?.getAttribute('content');
    document.title = `GymAxis vs ${competitor.name} — feature-by-feature comparison`;
    let meta = document.querySelector('meta[name="description"]');
    if (!meta) {
      meta = document.createElement('meta');
      meta.setAttribute('name', 'description');
      document.head.appendChild(meta);
    }
    meta.setAttribute(
      'content',
      `${competitor.name} alternative — see how GymAxis AI stacks up on operations, service desk, contracts, memberships and reporting.`,
    );
    return () => {
      document.title = prevTitle;
      if (meta && prevDesc) meta.setAttribute('content', prevDesc);
    };
  }, [competitor.name]);

  const productJsonLd = {
    '@context': 'https://schema.org',
    '@type': 'Product',
    name: 'GymAxis AI',
    description: hero.subheadline,
    brand: { '@type': 'Brand', name: 'GymAxis' },
    review: {
      '@type': 'Review',
      reviewRating: { '@type': 'Rating', ratingValue: '4.9', bestRating: '5' },
      author: { '@type': 'Organization', name: 'GymAxis Customer' },
    },
  };
  const faqJsonLd = {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: (faqs || []).map((f) => ({
      '@type': 'Question',
      name: f.q,
      acceptedAnswer: { '@type': 'Answer', text: f.a },
    })),
  };

  return (
    <MarketingShell>
      {/* JSON-LD for rich results */}
      <script
        type="application/ld+json"
         
        dangerouslySetInnerHTML={{ __html: JSON.stringify(productJsonLd) }}
      />
      <script
        type="application/ld+json"
         
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqJsonLd) }}
      />

      {/* Hero */}
      <section className="gx-grid-bg" data-testid={`compare-hero-${competitor.slug}`}>
        <div className="max-w-7xl mx-auto px-6 lg:px-8 pt-14 pb-16 lg:pt-20 lg:pb-24">
          <nav className="text-xs text-slate-500 mb-5 flex items-center gap-1.5" aria-label="Breadcrumb">
            <Link to="/" className="hover:text-slate-700">GymAxis</Link>
            <ChevronRight size={11} />
            <Link to="/compare" className="hover:text-slate-700">Compare</Link>
            <ChevronRight size={11} />
            <span className="text-slate-700 font-semibold">vs {competitor.name}</span>
          </nav>
          <span className="inline-flex items-center gap-2 rounded-full bg-white border border-slate-200 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-slate-600 dark:bg-zinc-900 dark:border-zinc-800">
            <Sparkles size={12} /> Alternative comparison
          </span>
          <h1 className="mt-5 text-4xl md:text-5xl lg:text-6xl tracking-tighter font-black leading-[1.05] max-w-4xl">
            {hero.headline}
          </h1>
          <p className="mt-6 text-lg md:text-xl text-slate-600 leading-relaxed max-w-3xl">
            {hero.subheadline}
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={openTrial}
              className="gx-cta inline-flex items-center gap-1.5 rounded-full px-6 py-3 text-sm font-bold"
              data-testid={`compare-trial-${competitor.slug}`}
            >
              Start free 3-day trial <ArrowRight size={15} />
            </button>
            <Link
              to="/contact"
              className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 px-6 py-3 text-sm font-bold text-slate-700 hover:bg-slate-50 dark:bg-zinc-900"
              data-testid={`compare-demo-${competitor.slug}`}
            >
              Book a tailored demo
            </Link>
          </div>
        </div>
      </section>

      {/* Feature matrix */}
      <section className="bg-white py-16 lg:py-20 dark:bg-zinc-900">
        <div className="max-w-6xl mx-auto px-6 lg:px-8">
          <h2 className="text-3xl md:text-4xl font-black tracking-tight">
            Feature-by-feature: <span className="gx-gradient-text">GymAxis vs {competitor.name}</span>
          </h2>
          <p className="mt-3 text-slate-600 max-w-2xl">
            What you actually get day-to-day on the operator console, the engineer mobile, and the back-office finance hand-off.
          </p>
          <div className="mt-8 overflow-x-auto rounded-2xl border border-slate-200 dark:border-zinc-800" data-testid={`compare-matrix-${competitor.slug}`}>
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 dark:bg-zinc-900">
                <tr>
                  <th className="px-5 py-4 font-bold tracking-tight text-slate-700">Capability</th>
                  <th className="px-5 py-4 font-bold tracking-tight text-slate-700">GymAxis AI</th>
                  <th className="px-5 py-4 font-bold tracking-tight text-slate-700">{competitor.name}</th>
                </tr>
              </thead>
              <tbody>
                {matrix.map((row, i) => (
                  <tr key={row.feature} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'}>
                    <td className="px-5 py-4 font-semibold text-slate-800">{row.feature}</td>
                    <Cell value={row.gymaxis} good />
                    <Cell value={row.competitor} good={false} />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Why GymAxis */}
      <section className="bg-slate-50 py-16 lg:py-20 dark:bg-zinc-900">
        <div className="max-w-6xl mx-auto px-6 lg:px-8">
          <h2 className="text-3xl md:text-4xl font-black tracking-tight">Where GymAxis pulls ahead</h2>
          <div className="mt-8 grid md:grid-cols-2 gap-5">
            {winsForGymAxis.map((w) => (
              <div key={w.title} className="rounded-2xl bg-white border border-slate-200 p-6 hover:shadow-md transition dark:bg-zinc-900 dark:border-zinc-800">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center text-white" style={{ background: 'linear-gradient(135deg, var(--gx-brand-from), var(--gx-brand-to))' }}>
                  <CheckCircle2 size={20} />
                </div>
                <h3 className="mt-4 text-lg font-bold tracking-tight">{w.title}</h3>
                <p className="mt-2 text-sm text-slate-600 leading-relaxed">{w.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Honest counterweight */}
      {whenCompetitorWins?.length ? (
        <section className="bg-white py-16 lg:py-20 dark:bg-zinc-900">
          <div className="max-w-6xl mx-auto px-6 lg:px-8">
            <h2 className="text-3xl md:text-4xl font-black tracking-tight">
              When {competitor.name} might be the better pick
            </h2>
            <p className="mt-3 text-slate-600 max-w-2xl">
              Honest assessment — we'd rather you find the right tool than churn out of GymAxis in three months.
            </p>
            <div className="mt-8 grid md:grid-cols-2 gap-5">
              {whenCompetitorWins.map((w) => (
                <div key={w.title} className="rounded-2xl border border-slate-200 p-6 dark:border-zinc-800">
                  <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-slate-100 text-slate-600 dark:bg-zinc-800">
                    <MinusCircle size={20} />
                  </div>
                  <h3 className="mt-4 text-lg font-bold tracking-tight">{w.title}</h3>
                  <p className="mt-2 text-sm text-slate-600 leading-relaxed">{w.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>
      ) : null}

      {/* Migration guarantee — high-conversion anchor for /compare visitors */}
      <MigrationGuarantee />

      {/* FAQ */}
      <section className="bg-slate-50 py-16 lg:py-20 dark:bg-zinc-900">
        <div className="max-w-4xl mx-auto px-6 lg:px-8">
          <h2 className="text-3xl md:text-4xl font-black tracking-tight">Frequently asked</h2>
          <div className="mt-8 space-y-3" data-testid={`compare-faq-${competitor.slug}`}>
            {faqs.map((f) => (
              <details key={f.q} className="group rounded-xl bg-white border border-slate-200 px-5 py-4 open:shadow-sm dark:bg-zinc-900 dark:border-zinc-800">
                <summary className="cursor-pointer list-none flex items-center justify-between font-semibold text-slate-800">
                  {f.q}
                  <ChevronRight size={16} className="transition group-open:rotate-90 text-slate-400" />
                </summary>
                <p className="mt-3 text-sm text-slate-600 leading-relaxed">{f.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="bg-white py-16 lg:py-24 dark:bg-zinc-900">
        <div className="max-w-5xl mx-auto px-6 lg:px-8 rounded-3xl p-10 lg:p-14 text-center" style={{ background: 'linear-gradient(135deg, var(--gx-brand-from), var(--gx-brand-to))' }}>
          <ShieldCheck size={36} className="mx-auto text-white" />
          <h2 className="mt-4 text-3xl md:text-4xl font-black tracking-tight text-white">
            See it in your gym in 3 days. No card.
          </h2>
          <p className="mt-3 text-white/85 text-lg max-w-2xl mx-auto">
            Start a free trial with all modules unlocked. If GymAxis isn't a clear win over {competitor.name}, we'll help you migrate back — no hard sell.
          </p>
          <div className="mt-7 flex flex-wrap justify-center gap-3">
            <button type="button" onClick={openTrial} className="inline-flex items-center gap-1.5 rounded-full bg-white text-slate-900 px-7 py-3 text-sm font-bold hover:bg-slate-100 dark:bg-zinc-900 dark:bg-zinc-800 dark:text-zinc-100">
              Start free trial <ArrowRight size={15} />
            </button>
            <Link to="/blog" className="inline-flex items-center gap-1.5 rounded-full border border-white/40 px-7 py-3 text-sm font-bold text-white hover:bg-white/10">
              <BookOpen size={14} /> Read the blog
            </Link>
          </div>
        </div>
      </section>
    </MarketingShell>
  );
}

function Cell({ value, good }) {
  if (value === true || value === false) {
    return (
      <td className="px-5 py-4">
        {value ? (
          <span className={`inline-flex items-center gap-1.5 ${good ? 'text-emerald-600' : 'text-slate-500'} font-semibold text-sm`}>
            <CheckCircle2 size={15} /> Yes
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 text-slate-400 text-sm">
            <MinusCircle size={15} /> No
          </span>
        )}
      </td>
    );
  }
  return <td className="px-5 py-4 text-slate-700 text-sm leading-relaxed">{value}</td>;
}
