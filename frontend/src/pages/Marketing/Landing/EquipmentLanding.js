/**
 * EquipmentLanding — programmatic /equipment/:slug landing page.
 *
 * The *category* axis that complements the manufacturer (*brand*) axis at
 * /maintenance/:slug. Targets high-intent search terms like "treadmill
 * servicing & repair" / "exercise bike maintenance". Data-driven: renders
 * the real, serviceable machines of this type across every brand from the
 * catalogue + curated common-faults / PM-task editorial so the page is
 * substantive (no thin content). Article-grade + Service/FAQPage JSON-LD.
 */
import { useEffect, useState } from 'react';
import { Link, useParams, Navigate } from 'react-router-dom';
import axios from 'axios';
import {
  ArrowRight, CheckCircle2, ShieldCheck, ChevronRight, Wrench, Loader2,
  AlertTriangle, CalendarClock,
} from 'lucide-react';

import '../marketing.css';
import MarketingShell from '../MarketingShell';
import MigrationGuarantee from '../MigrationGuarantee';
import { openTrial } from '../TrialSignupModal';
import useSeo from '../../../utils/seo';

const API = process.env.REACT_APP_BACKEND_URL;
const SITE = 'https://gymaxisai.com';
const brandSlug = (b) => (b || '').toLowerCase().replace(/&/g, ' and ').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

export default function EquipmentLanding() {
  const { slug } = useParams();
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading');

  useEffect(() => {
    setStatus('loading');
    axios.get(`${API}/api/seo/landing/equipment/${encodeURIComponent(slug)}`)
      .then((r) => { setData(r.data); setStatus('ok'); })
      .catch(() => setStatus('notfound'));
  }, [slug]);

  const name = data?.name || '';
  const plural = data?.plural || `${name.toLowerCase()}s`;
  const canonical = `${SITE}/equipment/${slug}`;
  const faqs = data ? [
    { q: `How often should commercial ${plural} be serviced?`, a: `Most operators run a planned preventive maintenance (PPM) visit on ${plural} every 1–3 months depending on footfall, plus daily staff checks. GymAxis schedules each PPM per asset and auto-queues the next visit when the last is closed.` },
    { q: `What are the most common ${name.toLowerCase()} faults?`, a: `${(data.faults || []).slice(0, 3).join(', ')} and similar wear items. GymAxis logs each fault with AI-triaged severity and the likely parts, so engineers arrive prepared.` },
    { q: `Can GymAxis track every ${name.toLowerCase()} as an asset?`, a: `Yes — each ${name.toLowerCase()} carries a full lifecycle record: purchase, warranty, every fault, every PPM visit and every part fitted, with photo and signature proof of work.` },
    { q: `Does it separate warranty from chargeable repairs?`, a: 'Yes. Each asset knows its cover, so warranty and chargeable work are split automatically at the point of repair — no missed warranty claims.' },
  ] : [];

  useSeo({
    title: data ? `${name} Servicing & Repair Software | GymAxis AI` : 'Equipment servicing | GymAxis',
    description: data
      ? `Service and maintain commercial ${plural} with GymAxis: asset register, AI fault logging, planned maintenance, parts and compliance evidence across every brand on your floor.`
      : undefined,
    canonical,
    image: `${SITE}/brand/og-cover.jpg`,
    structuredData: data ? {
      '@context': 'https://schema.org',
      '@graph': [
        {
          '@type': 'Service',
          name: `${name} Servicing & Maintenance Software`,
          serviceType: data.term,
          provider: { '@type': 'Organization', name: 'GymAxis AI', url: SITE },
          areaServed: 'GB',
          description: `Preventive maintenance, fault repair, asset management and parts control software for commercial ${plural}.`,
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
            { '@type': 'ListItem', position: 2, name: 'Equipment', item: `${SITE}/equipment` },
            { '@type': 'ListItem', position: 3, name, item: canonical },
          ],
        },
      ],
    } : undefined,
  });

  if (status === 'notfound') return <Navigate to="/equipment" replace />;
  if (status === 'loading') {
    return (
      <MarketingShell>
        <div className="min-h-[50vh] flex items-center justify-center" data-testid="equipment-loading">
          <Loader2 className="animate-spin text-slate-400" size={28} />
        </div>
      </MarketingShell>
    );
  }

  return (
    <MarketingShell>
      <section className="gx-grid-bg" data-testid={`equipment-hero-${slug}`}>
        <div className="max-w-7xl mx-auto px-6 lg:px-8 pt-14 pb-16 lg:pt-20 lg:pb-24">
          <nav className="text-xs text-slate-500 mb-5 flex items-center gap-1.5" aria-label="Breadcrumb">
            <Link to="/" className="hover:text-slate-700">GymAxis</Link>
            <ChevronRight size={11} />
            <Link to="/equipment" className="hover:text-slate-700">Equipment</Link>
            <ChevronRight size={11} />
            <span className="text-slate-700 font-semibold">{name}</span>
          </nav>
          <span className="inline-flex items-center gap-2 rounded-full bg-white border border-slate-200 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-slate-600 dark:bg-zinc-900 dark:border-zinc-800">
            <Wrench size={12} /> {name} servicing
          </span>
          <h1 className="mt-5 text-4xl md:text-5xl lg:text-6xl tracking-tighter font-black leading-[1.05] max-w-4xl">
            {name} servicing &amp; repair, <span className="gx-gradient-text">planned and proven</span>.
          </h1>
          <p className="mt-6 text-lg md:text-xl text-slate-600 leading-relaxed max-w-3xl">
            {data.intro} Asset register, AI-triaged fault logging, planned preventive maintenance, parts control and proof-of-work — for every {name.toLowerCase()} on your floor, whatever the brand.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <button type="button" onClick={openTrial} className="gx-cta inline-flex items-center gap-1.5 rounded-full px-6 py-3 text-sm font-bold" data-testid={`equipment-trial-${slug}`}>
              Start free 3-day trial <ArrowRight size={15} />
            </button>
            <Link to="/contact" className="inline-flex items-center gap-1.5 rounded-full border border-slate-300 px-6 py-3 text-sm font-bold text-slate-700 hover:bg-slate-50 dark:bg-zinc-900">
              Book a tailored demo
            </Link>
          </div>
        </div>
      </section>

      {/* Common faults + PM tasks */}
      <section className="bg-white py-16 lg:py-20 dark:bg-zinc-900">
        <div className="max-w-6xl mx-auto px-6 lg:px-8 grid lg:grid-cols-2 gap-6">
          <div className="rounded-2xl border border-slate-200 p-7 dark:border-zinc-800" data-testid="equipment-faults">
            <div className="flex items-center gap-2 text-amber-600">
              <AlertTriangle size={18} />
              <h2 className="text-xl font-black tracking-tight text-slate-900 dark:text-zinc-100">Common {name.toLowerCase()} faults</h2>
            </div>
            <ul className="mt-5 space-y-3">
              {data.faults.map((f) => (
                <li key={f} className="flex items-start gap-3 text-sm text-slate-700 dark:text-zinc-300">
                  <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0" />
                  {f}
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-2xl border border-slate-200 p-7 dark:border-zinc-800" data-testid="equipment-tasks">
            <div className="flex items-center gap-2 text-emerald-600">
              <CalendarClock size={18} />
              <h2 className="text-xl font-black tracking-tight text-slate-900 dark:text-zinc-100">Planned maintenance tasks</h2>
            </div>
            <ul className="mt-5 space-y-3">
              {data.tasks.map((t) => (
                <li key={t} className="flex items-start gap-3 text-sm text-slate-700 dark:text-zinc-300">
                  <CheckCircle2 size={16} className="mt-0.5 text-emerald-500 shrink-0" />
                  {t}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* Real machines from the catalogue */}
      {data?.products?.length > 0 && (
        <section className="bg-slate-50 py-16 lg:py-20 dark:bg-zinc-900">
          <div className="max-w-6xl mx-auto px-6 lg:px-8">
            <h2 className="text-3xl md:text-4xl font-black tracking-tight">{plural.charAt(0).toUpperCase() + plural.slice(1)} we maintain</h2>
            <p className="mt-3 text-slate-600 max-w-2xl">A sample of the {plural} tracked in the GymAxis catalogue across {data.brands.length} brand{data.brands.length === 1 ? '' : 's'}. Add yours to the asset register in minutes.</p>
            <div className="mt-8 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4" data-testid="equipment-products">
              {data.products.map((p) => (
                <div key={`${p.manufacturer || ''}-${p.title}`} className="rounded-2xl bg-white border border-slate-200 overflow-hidden dark:bg-zinc-900 dark:border-zinc-800">
                  <div className="aspect-[4/3] bg-white dark:bg-white flex items-center justify-center overflow-hidden">
                    <img src={p.image_url} alt={`${p.manufacturer || ''} ${p.title}`.trim()} loading="lazy" className="w-full h-full object-contain p-3" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                  </div>
                  <div className="px-3 py-3 border-t border-slate-100 dark:border-zinc-800">
                    {p.manufacturer && <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">{p.manufacturer}</p>}
                    <p className="text-sm font-semibold text-slate-800 line-clamp-2 dark:text-zinc-100">{p.title}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Brands serviced cross-links */}
      {data?.brands?.length > 0 && (
        <section className="bg-white py-14 dark:bg-zinc-900">
          <div className="max-w-6xl mx-auto px-6 lg:px-8">
            <h2 className="text-2xl md:text-3xl font-black tracking-tight">{name} brands we service</h2>
            <div className="mt-5 flex flex-wrap gap-2.5" data-testid="equipment-brands">
              {data.brands.map((b) => (
                <Link key={b} to={`/maintenance/${brandSlug(b)}`} className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:border-slate-300 hover:bg-slate-50 dark:hover:bg-zinc-800 dark:border-zinc-800" data-testid={`equipment-brand-${brandSlug(b)}`}>
                  {b} <ChevronRight size={13} className="text-slate-400" />
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
          <div className="mt-8 space-y-3" data-testid={`equipment-faq-${slug}`}>
            {faqs.map((f) => (
              <details key={f.q} className="group rounded-xl bg-white border border-slate-200 px-5 py-4 open:shadow-sm dark:bg-zinc-900 dark:border-zinc-800">
                <summary className="cursor-pointer list-none flex items-center justify-between font-semibold text-slate-800 dark:text-zinc-100">
                  {f.q}
                  <ChevronRight size={16} className="transition group-open:rotate-90 text-slate-400 shrink-0 ml-3" />
                </summary>
                <p className="mt-3 text-sm text-slate-600 leading-relaxed dark:text-zinc-300">{f.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="bg-white py-16 lg:py-24 dark:bg-zinc-900">
        <div className="max-w-5xl mx-auto px-6 lg:px-8 rounded-3xl p-10 lg:p-14 text-center" style={{ background: 'linear-gradient(135deg, var(--gx-brand-from), var(--gx-brand-to))' }}>
          <ShieldCheck size={36} className="mx-auto text-white" />
          <h2 className="mt-4 text-3xl md:text-4xl font-black tracking-tight text-white">Keep your {plural} on the floor. Start in 3 days, no card.</h2>
          <p className="mt-3 text-white/85 text-lg max-w-2xl mx-auto">Import your {plural} and start logging faults, scheduling PPM and tracking parts on a free trial.</p>
          <div className="mt-7 flex flex-wrap justify-center gap-3">
            <button type="button" onClick={openTrial} className="inline-flex items-center gap-1.5 rounded-full bg-white dark:bg-white text-slate-900 dark:text-slate-900 px-7 py-3 text-sm font-bold hover:bg-slate-100">
              Start free trial <ArrowRight size={15} />
            </button>
            <Link to="/equipment" className="inline-flex items-center gap-1.5 rounded-full border border-white/40 px-7 py-3 text-sm font-bold text-white hover:bg-white/10">
              Browse all equipment
            </Link>
          </div>
        </div>
      </section>
    </MarketingShell>
  );
}
