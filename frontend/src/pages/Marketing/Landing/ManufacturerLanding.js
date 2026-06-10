/**
 * ManufacturerLanding — programmatic /maintenance/:slug landing page.
 * Renders a manufacturer's real product range from the catalogue plus
 * GymAxis service value props. Targets "[brand] equipment maintenance
 * software". Article-grade content (real product grid) avoids thin pages.
 */
import React, { useEffect, useState } from 'react';
import { Link, useParams, Navigate } from 'react-router-dom';
import axios from 'axios';
import {
  ArrowRight, CheckCircle2, ShieldCheck, ChevronRight, Wrench, Loader2,
} from 'lucide-react';

import '../marketing.css';
import MarketingShell from '../MarketingShell';
import MigrationGuarantee from '../MigrationGuarantee';
import { openTrial } from '../TrialSignupModal';
import useSeo from '../../../utils/seo';

const API = process.env.REACT_APP_BACKEND_URL;
const SITE = 'https://gymaxisai.com';

const VALUE_PROPS = [
  { title: 'Asset register for every machine', body: 'Tag and track every unit with its full service history, warranty position and lifecycle status.' },
  { title: 'Fault logging with AI triage', body: 'Members and staff report faults in seconds; AI classifies severity and pre-allocates likely parts.' },
  { title: 'Planned preventive maintenance', body: 'Schedule recurring service visits per asset; the next PPM auto-queues when the last is closed.' },
  { title: 'Parts & van stock', body: 'Catalogue, van and warehouse stock with warranty-vs-chargeable cover decided automatically.' },
  { title: 'Engineer mobile, offline-first', body: 'Field engineers work jobs with proof of work even in a plant room with no signal.' },
  { title: 'Compliance-ready evidence', body: 'Every repair is signed, photographed and reported — ready for inspectors and insurers.' },
];

export default function ManufacturerLanding() {
  const { slug } = useParams();
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading');

  useEffect(() => {
    setStatus('loading');
    axios.get(`${API}/api/seo/landing/manufacturer/${encodeURIComponent(slug)}`)
      .then((r) => { setData(r.data); setStatus('ok'); })
      .catch(() => setStatus('notfound'));
  }, [slug]);

  const name = data?.name || '';
  const canonical = `${SITE}/maintenance/${slug}`;
  const faqs = data ? [
    { q: `Does GymAxis work with ${name} equipment?`, a: `Yes. GymAxis maintains equipment from every major manufacturer, including ${name}. Add your ${name} machines to the asset register — manually or by bulk import — and the built-in manufacturer catalogue enriches them with the right model and image.` },
    { q: `Can I track service history for each ${name} machine?`, a: `Every ${name} asset carries a complete lifecycle history: purchase, warranty, every fault, every planned visit and every part fitted — all on one record.` },
    { q: `How does it handle ${name} warranty vs chargeable repairs?`, a: `Each asset knows its cover, so warranty and chargeable work are separated automatically at the point of repair — no missed warranty claims.` },
    { q: 'Can field engineers service it on site?', a: 'Yes — engineers work jobs on an offline-first mobile app, recording parts, photos, signatures and GPS proof of work that sync when back online.' },
  ] : [];

  useSeo({
    title: data ? `${name} Equipment Maintenance & Service Software | GymAxis AI` : 'Equipment maintenance | GymAxis',
    description: data
      ? `Maintain your ${name} equipment with GymAxis: asset register, fault logging, planned maintenance, parts and compliance evidence — across one site or your whole estate.`
      : undefined,
    canonical,
    image: `${SITE}/brand/og-cover.jpg`,
    structuredData: data ? {
      '@context': 'https://schema.org',
      '@graph': [
        {
          '@type': 'Service',
          name: `${name} Equipment Maintenance Software`,
          provider: { '@type': 'Organization', name: 'GymAxis AI', url: SITE },
          areaServed: 'GB',
          description: `Maintenance, asset management and service management software for ${name} gym equipment.`,
        },
        {
          '@type': 'FAQPage',
          mainEntity: faqs.map((f) => ({
            '@type': 'Question', name: f.q,
            acceptedAnswer: { '@type': 'Answer', text: f.a },
          })),
        },
        {
          '@type': 'BreadcrumbList',
          itemListElement: [
            { '@type': 'ListItem', position: 1, name: 'Home', item: SITE },
            { '@type': 'ListItem', position: 2, name: 'Maintenance', item: `${SITE}/maintenance` },
            { '@type': 'ListItem', position: 3, name, item: canonical },
          ],
        },
      ],
    } : undefined,
  });

  if (status === 'notfound') return <Navigate to="/maintenance" replace />;
  if (status === 'loading') {
    return (
      <MarketingShell>
        <div className="min-h-[50vh] flex items-center justify-center" data-testid="manufacturer-loading">
          <Loader2 className="animate-spin text-slate-400" size={28} />
        </div>
      </MarketingShell>
    );
  }

  return (
    <MarketingShell>
      <section className="gx-grid-bg" data-testid={`manufacturer-hero-${slug}`}>
        <div className="max-w-7xl mx-auto px-6 lg:px-8 pt-14 pb-16 lg:pt-20 lg:pb-24">
          <nav className="text-xs text-slate-500 mb-5 flex items-center gap-1.5" aria-label="Breadcrumb">
            <Link to="/" className="hover:text-slate-700">GymAxis</Link>
            <ChevronRight size={11} />
            <Link to="/maintenance" className="hover:text-slate-700">Maintenance</Link>
            <ChevronRight size={11} />
            <span className="text-slate-700 font-semibold">{name}</span>
          </nav>
          <span className="inline-flex items-center gap-2 rounded-full bg-white border border-slate-200 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-slate-600 dark:bg-zinc-900 dark:border-zinc-800">
            <Wrench size={12} /> {name} maintenance
          </span>
          <h1 className="mt-5 text-4xl md:text-5xl lg:text-6xl tracking-tighter font-black leading-[1.05] max-w-4xl">
            {name} equipment maintenance &amp; service software.
          </h1>
          <p className="mt-6 text-lg md:text-xl text-slate-600 leading-relaxed max-w-3xl">
            Keep your {name} machines on the floor and compliant. GymAxis gives you an asset register, AI-triaged fault logging, planned maintenance, parts control and proof-of-work — purpose-built for the gyms and leisure operators who run {name} kit.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <button type="button" onClick={openTrial} className="gx-cta inline-flex items-center gap-1.5 rounded-full px-6 py-3 text-sm font-bold" data-testid={`manufacturer-trial-${slug}`}>
              Start free 3-day trial <ArrowRight size={15} />
            </button>
            <Link to="/contact" className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 px-6 py-3 text-sm font-bold text-slate-700 hover:bg-slate-50 dark:bg-zinc-900">
              Book a tailored demo
            </Link>
          </div>
        </div>
      </section>

      {/* Value props */}
      <section className="bg-white py-16 lg:py-20 dark:bg-zinc-900">
        <div className="max-w-6xl mx-auto px-6 lg:px-8">
          <h2 className="text-3xl md:text-4xl font-black tracking-tight">
            Everything you need to maintain <span className="gx-gradient-text">{name}</span> equipment
          </h2>
          <div className="mt-8 grid md:grid-cols-2 lg:grid-cols-3 gap-5">
            {VALUE_PROPS.map((f) => (
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

      {/* Real product range from the catalogue */}
      {data?.products?.length > 0 && (
        <section className="bg-slate-50 py-16 lg:py-20 dark:bg-zinc-900">
          <div className="max-w-6xl mx-auto px-6 lg:px-8">
            <h2 className="text-3xl md:text-4xl font-black tracking-tight">{name} equipment we maintain</h2>
            <p className="mt-3 text-slate-600 max-w-2xl">A sample of the {name} range tracked in the GymAxis manufacturer catalogue. Add yours to the asset register in minutes.</p>
            <div className="mt-8 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4" data-testid="manufacturer-products">
              {data.products.map((p) => (
                <div key={p.url || p.title} className="rounded-2xl bg-white border border-slate-200 overflow-hidden dark:bg-zinc-900 dark:border-zinc-800">
                  <div className="aspect-[4/3] bg-white flex items-center justify-center overflow-hidden">
                    <img src={p.image_url} alt={`${name} ${p.title}`} loading="lazy" className="w-full h-full object-contain p-3" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                  </div>
                  <div className="px-3 py-3 border-t border-slate-100 dark:border-zinc-800">
                    <p className="text-sm font-semibold text-slate-800 line-clamp-2 dark:text-zinc-100">{p.title}</p>
                  </div>
                </div>
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
          <div className="mt-8 space-y-3" data-testid={`manufacturer-faq-${slug}`}>
            {faqs.map((f) => (
              <details key={f.q} className="group rounded-xl bg-white border border-slate-200 px-5 py-4 open:shadow-sm dark:bg-zinc-900 dark:border-zinc-800">
                <summary className="cursor-pointer list-none flex items-center justify-between font-semibold text-slate-800">
                  {f.q}
                  <ChevronRight size={16} className="transition group-open:rotate-90 text-slate-400 shrink-0 ml-3" />
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
          <h2 className="mt-4 text-3xl md:text-4xl font-black tracking-tight text-white">Maintain your {name} estate in 3 days. No card.</h2>
          <p className="mt-3 text-white/85 text-lg max-w-2xl mx-auto">Import your {name} assets and start logging faults, scheduling PPM and tracking parts on a free trial.</p>
          <div className="mt-7 flex flex-wrap justify-center gap-3">
            <button type="button" onClick={openTrial} className="inline-flex items-center gap-1.5 rounded-full bg-white text-slate-900 px-7 py-3 text-sm font-bold hover:bg-slate-100">
              Start free trial <ArrowRight size={15} />
            </button>
            <Link to="/solutions/gym-maintenance-software" className="inline-flex items-center gap-1.5 rounded-full border border-white/40 px-7 py-3 text-sm font-bold text-white hover:bg-white/10">
              Explore maintenance software
            </Link>
          </div>
        </div>
      </section>
    </MarketingShell>
  );
}
