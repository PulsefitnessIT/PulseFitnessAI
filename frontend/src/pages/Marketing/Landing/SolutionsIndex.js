/**
 * SolutionsIndex — /solutions hub linking to every programmatic solution
 * landing page. Provides internal-linking structure for SEO.
 */
import { Link } from 'react-router-dom';
import { ArrowRight, Layers, ChevronRight } from 'lucide-react';

import '../marketing.css';
import MarketingShell from '../MarketingShell';
import useSeo from '../../../utils/seo';
import { SOLUTIONS } from './solutionsData';

const SITE = 'https://pulsefitness.ai';

export default function SolutionsIndex() {
  useSeo({
    title: 'Solutions for Gyms & Leisure Operators | Pulse Fitness AI',
    description:
      'Software solutions for gym and leisure operators: equipment maintenance, planned maintenance (PPM), asset management, CRM and service management — all in one platform.',
    canonical: `${SITE}/solutions`,
    image: `${SITE}/brand/og-cover.jpg`,
    structuredData: {
      '@context': 'https://schema.org',
      '@type': 'CollectionPage',
      name: 'Pulse Fitness Solutions',
      url: `${SITE}/solutions`,
    },
  });

  return (
    <MarketingShell>
      <section className="gx-grid-bg" data-testid="solutions-index">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 pt-14 pb-12 lg:pt-20">
          <nav className="text-xs text-slate-500 mb-5 flex items-center gap-1.5" aria-label="Breadcrumb">
            <Link to="/" className="hover:text-slate-700">Pulse Fitness</Link>
            <ChevronRight size={11} />
            <span className="text-slate-700 font-semibold">Solutions</span>
          </nav>
          <span className="inline-flex items-center gap-2 rounded-full bg-white border border-slate-200 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-slate-600 dark:bg-zinc-900 dark:border-zinc-800">
            <Layers size={12} /> Solutions
          </span>
          <h1 className="mt-5 text-4xl md:text-5xl lg:text-6xl tracking-tighter font-black leading-[1.05] max-w-4xl">
            One platform, <span className="gx-gradient-text">every operations job</span>.
          </h1>
          <p className="mt-6 text-lg md:text-xl text-slate-600 leading-relaxed max-w-3xl">
            From equipment maintenance to CRM, Pulse Fitness replaces the patchwork of tools gyms and leisure operators juggle. Pick the job you need solved.
          </p>
        </div>
      </section>

      <section className="bg-white py-12 lg:py-20 dark:bg-zinc-900">
        <div className="max-w-6xl mx-auto px-6 lg:px-8 grid md:grid-cols-2 gap-5">
          {SOLUTIONS.map((s) => (
            <Link key={s.slug} to={`/solutions/${s.slug}`} className="group rounded-2xl border border-slate-200 p-7 hover:shadow-md hover:border-slate-300 transition dark:border-zinc-800" data-testid={`solution-card-${s.slug}`}>
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">{s.eyebrow}</span>
              <h2 className="mt-2 text-xl font-black tracking-tight group-hover:text-slate-900 dark:group-hover:text-zinc-100">{s.h1}</h2>
              <p className="mt-3 text-sm text-slate-600 leading-relaxed line-clamp-3">{s.intro}</p>
              <span className="mt-4 inline-flex items-center gap-1.5 text-sm font-bold gx-gradient-text">
                Explore <ArrowRight size={14} />
              </span>
            </Link>
          ))}
        </div>
      </section>
    </MarketingShell>
  );
}
