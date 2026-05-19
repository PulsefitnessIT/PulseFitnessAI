/**
 * /compare — index page listing the live comparison pages.
 */
import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Sparkles } from 'lucide-react';

import '../marketing.css';
import MarketingShell from '../MarketingShell';

const ENTRIES = [
  { slug: 'mindbody',  name: 'Mindbody',  blurb: 'Bookings-first SaaS for studios — versus a fully-integrated operations + service desk.' },
  { slug: 'glofox',    name: 'Glofox',    blurb: 'Boutique gym management — versus an asset-aware platform with engineer mobile + Sicon link.' },
  { slug: 'clubready', name: 'ClubReady', blurb: 'Sales-CRM-led club software — versus contracts + service hardened for multi-site operators.' },
];

export default function CompareIndex() {
  React.useEffect(() => {
    const prev = document.title;
    document.title = 'GymAxis alternatives — compare side-by-side';
    return () => { document.title = prev; };
  }, []);
  return (
    <MarketingShell>
      <section className="gx-grid-bg">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 pt-14 pb-16 lg:pt-20 lg:pb-24">
          <span className="inline-flex items-center gap-2 rounded-full bg-white border border-slate-200 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-slate-600 dark:bg-zinc-900 dark:border-zinc-800">
            <Sparkles size={12} /> Side-by-side comparisons
          </span>
          <h1 className="mt-5 text-4xl md:text-5xl lg:text-6xl tracking-tighter font-black leading-[1.05] max-w-4xl">
            How GymAxis stacks up against the<br /><span className="gx-gradient-text">tools you already know.</span>
          </h1>
          <p className="mt-6 text-lg md:text-xl text-slate-600 max-w-3xl">
            Honest, feature-by-feature comparisons. We highlight where we win, where we don't, and which gym profile each tool is best suited to.
          </p>
        </div>
      </section>
      <section className="bg-white pb-24 dark:bg-zinc-900">
        <div className="max-w-6xl mx-auto px-6 lg:px-8 grid md:grid-cols-3 gap-5">
          {ENTRIES.map((e) => (
            <Link
              key={e.slug}
              to={`/compare/${e.slug}`}
              data-testid={`compare-card-${e.slug}`}
              className="rounded-2xl bg-white border border-slate-200 p-6 hover:shadow-md hover:-translate-y-0.5 transition group dark:bg-zinc-900 dark:border-zinc-800"
            >
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">vs {e.name}</p>
              <h2 className="mt-2 text-2xl font-black tracking-tight">GymAxis vs {e.name}</h2>
              <p className="mt-3 text-sm text-slate-600 leading-relaxed">{e.blurb}</p>
              <span className="mt-5 inline-flex items-center gap-1.5 text-sm font-bold text-slate-800 group-hover:text-slate-600">
                Read comparison <ArrowRight size={14} />
              </span>
            </Link>
          ))}
        </div>
      </section>
    </MarketingShell>
  );
}
