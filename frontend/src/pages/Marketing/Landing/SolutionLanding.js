/**
 * SolutionLanding — programmatic /solutions/:slug landing page.
 * Renders substantive, keyword-targeted content from solutionsData.js with
 * Product + FAQPage JSON-LD for rich-result eligibility.
 */
import React, { useEffect, useState } from 'react';
import { Link, useParams, Navigate } from 'react-router-dom';
import axios from 'axios';
import {
  ArrowRight, CheckCircle2, AlertTriangle, ShieldCheck, BookOpen,
  ChevronRight, Wrench,
} from 'lucide-react';

import '../marketing.css';
import MarketingShell from '../MarketingShell';
import MigrationGuarantee from '../MigrationGuarantee';
import { openTrial } from '../TrialSignupModal';
import useSeo from '../../../utils/seo';
import { getSolution } from './solutionsData';

const API = process.env.REACT_APP_BACKEND_URL;
const SITE = 'https://gymaxisai.com';

export default function SolutionLanding() {
  const { slug } = useParams();
  const sol = getSolution(slug);
  const [manufacturers, setManufacturers] = useState([]);

  useEffect(() => {
    if (!sol?.showManufacturers) return;
    axios.get(`${API}/api/seo/landing/manufacturers`)
      .then((r) => setManufacturers(r.data?.manufacturers || []))
      .catch(() => {});
  }, [sol]);

  const canonical = `${SITE}/solutions/${slug}`;
  useSeo({
    title: sol?.metaTitle,
    description: sol?.metaDescription,
    canonical,
    image: `${SITE}/brand/og-cover.jpg`,
    structuredData: sol ? {
      '@context': 'https://schema.org',
      '@graph': [
        {
          '@type': 'Product',
          name: 'GymAxis AI',
          description: sol.metaDescription,
          brand: { '@type': 'Brand', name: 'GymAxis' },
        },
        {
          '@type': 'FAQPage',
          mainEntity: sol.faqs.map((f) => ({
            '@type': 'Question', name: f.q,
            acceptedAnswer: { '@type': 'Answer', text: f.a },
          })),
        },
        {
          '@type': 'BreadcrumbList',
          itemListElement: [
            { '@type': 'ListItem', position: 1, name: 'Home', item: SITE },
            { '@type': 'ListItem', position: 2, name: 'Solutions', item: `${SITE}/solutions` },
            { '@type': 'ListItem', position: 3, name: sol.eyebrow, item: canonical },
          ],
        },
      ],
    } : undefined,
  });

  if (!sol) return <Navigate to="/solutions" replace />;

  return (
    <MarketingShell>
      <section className="gx-grid-bg" data-testid={`solution-hero-${slug}`}>
        <div className="max-w-7xl mx-auto px-6 lg:px-8 pt-14 pb-16 lg:pt-20 lg:pb-24">
          <nav className="text-xs text-slate-500 mb-5 flex items-center gap-1.5" aria-label="Breadcrumb">
            <Link to="/" className="hover:text-slate-700">GymAxis</Link>
            <ChevronRight size={11} />
            <Link to="/solutions" className="hover:text-slate-700">Solutions</Link>
            <ChevronRight size={11} />
            <span className="text-slate-700 font-semibold">{sol.eyebrow}</span>
          </nav>
          <span className="inline-flex items-center gap-2 rounded-full bg-white border border-slate-200 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-slate-600 dark:bg-zinc-900 dark:border-zinc-800">
            <Wrench size={12} /> {sol.eyebrow}
          </span>
          <h1 className="mt-5 text-4xl md:text-5xl lg:text-6xl tracking-tighter font-black leading-[1.05] max-w-4xl">
            {sol.h1}
          </h1>
          <p className="mt-6 text-lg md:text-xl text-slate-600 leading-relaxed max-w-3xl">{sol.intro}</p>
          <p className="mt-3 text-sm font-semibold text-slate-500">{sol.audience}</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <button type="button" onClick={openTrial} className="gx-cta inline-flex items-center gap-1.5 rounded-full px-6 py-3 text-sm font-bold" data-testid={`solution-trial-${slug}`}>
              Start free 3-day trial <ArrowRight size={15} />
            </button>
            <Link to="/contact" className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 px-6 py-3 text-sm font-bold text-slate-700 hover:bg-slate-50 dark:bg-zinc-900">
              Book a tailored demo
            </Link>
          </div>
        </div>
      </section>

      {/* Pain points */}
      <section className="bg-white py-16 lg:py-20 dark:bg-zinc-900">
        <div className="max-w-6xl mx-auto px-6 lg:px-8">
          <h2 className="text-3xl md:text-4xl font-black tracking-tight">The problem we solve</h2>
          <div className="mt-8 grid md:grid-cols-2 gap-5">
            {sol.pains.map((p) => (
              <div key={p.title} className="rounded-2xl border border-slate-200 p-6 dark:border-zinc-800">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-amber-100 text-amber-600 dark:bg-amber-900/30">
                  <AlertTriangle size={20} />
                </div>
                <h3 className="mt-4 text-lg font-bold tracking-tight">{p.title}</h3>
                <p className="mt-2 text-sm text-slate-600 leading-relaxed">{p.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Capabilities */}
      <section className="bg-slate-50 py-16 lg:py-20 dark:bg-zinc-900">
        <div className="max-w-6xl mx-auto px-6 lg:px-8">
          <h2 className="text-3xl md:text-4xl font-black tracking-tight">
            What you get with <span className="gx-gradient-text">GymAxis</span>
          </h2>
          <div className="mt-8 grid md:grid-cols-2 lg:grid-cols-3 gap-5">
            {sol.features.map((f) => (
              <div key={f.title} className="rounded-2xl bg-white border border-slate-200 p-6 hover:shadow-md transition dark:bg-zinc-900 dark:border-zinc-800">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center text-white" style={{ background: 'linear-gradient(135deg, var(--gx-brand-from), var(--gx-brand-to))' }}>
                  <CheckCircle2 size={20} />
                </div>
                <h3 className="mt-4 text-lg font-bold tracking-tight">{f.title}</h3>
                <p className="mt-2 text-sm text-slate-600 leading-relaxed">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Manufacturer strip */}
      {sol.showManufacturers && manufacturers.length > 0 && (
        <section className="bg-white py-14 lg:py-16 dark:bg-zinc-900">
          <div className="max-w-6xl mx-auto px-6 lg:px-8">
            <h2 className="text-2xl md:text-3xl font-black tracking-tight">Maintain every brand on your floor</h2>
            <p className="mt-3 text-slate-600 max-w-2xl">GymAxis works with equipment from every major manufacturer. See brand-specific service guides:</p>
            <div className="mt-6 flex flex-wrap gap-2.5" data-testid="solution-manufacturer-links">
              {manufacturers.map((m) => (
                <Link key={m.slug} to={`/maintenance/${m.slug}`} className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 dark:border-zinc-800">
                  {m.name} <ArrowRight size={13} />
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}

      <MigrationGuarantee />

      {/* FAQ */}
      <section className="bg-slate-50 py-16 lg:py-20 dark:bg-zinc-900">
        <div className="max-w-4xl mx-auto px-6 lg:px-8">
          <h2 className="text-3xl md:text-4xl font-black tracking-tight">Frequently asked</h2>
          <div className="mt-8 space-y-3" data-testid={`solution-faq-${slug}`}>
            {sol.faqs.map((f) => (
              <details key={f.q} className="group rounded-xl bg-white border border-slate-200 px-5 py-4 open:shadow-sm dark:bg-zinc-900 dark:border-zinc-800">
                <summary className="cursor-pointer list-none flex items-center justify-between font-semibold text-slate-800">
                  {f.q}
                  <ChevronRight size={16} className="transition group-open:rotate-90 text-slate-400" />
                </summary>
                <p className="mt-3 text-sm text-slate-600 leading-relaxed">{f.a}</p>
              </details>
            ))}
          </div>
          {sol.relatedSolutions?.length > 0 && (
            <div className="mt-10">
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-500">Related solutions</h3>
              <div className="mt-3 flex flex-wrap gap-2.5">
                {sol.relatedSolutions.map((rs) => {
                  const r = getSolution(rs);
                  return r ? (
                    <Link key={rs} to={`/solutions/${rs}`} className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 dark:border-zinc-800">
                      {r.eyebrow} <ChevronRight size={13} />
                    </Link>
                  ) : null;
                })}
              </div>
            </div>
          )}
        </div>
      </section>

      {/* CTA */}
      <section className="bg-white py-16 lg:py-24 dark:bg-zinc-900">
        <div className="max-w-5xl mx-auto px-6 lg:px-8 rounded-3xl p-10 lg:p-14 text-center" style={{ background: 'linear-gradient(135deg, var(--gx-brand-from), var(--gx-brand-to))' }}>
          <ShieldCheck size={36} className="mx-auto text-white" />
          <h2 className="mt-4 text-3xl md:text-4xl font-black tracking-tight text-white">See it in your gym in 3 days. No card.</h2>
          <p className="mt-3 text-white/85 text-lg max-w-2xl mx-auto">Start a free trial with every module unlocked — assets, maintenance, parts, CRM and finance hand-off.</p>
          <div className="mt-7 flex flex-wrap justify-center gap-3">
            <button type="button" onClick={openTrial} className="inline-flex items-center gap-1.5 rounded-full bg-white text-slate-900 px-7 py-3 text-sm font-bold hover:bg-slate-100">
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
