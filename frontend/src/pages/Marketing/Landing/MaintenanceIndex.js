/**
 * MaintenanceIndex — /maintenance hub listing every manufacturer that has
 * a maintenance landing page (data-driven from the catalogue). Grows
 * automatically as more manufacturers are ingested.
 */
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { ArrowRight, Wrench, ChevronRight } from 'lucide-react';

import '../marketing.css';
import MarketingShell from '../MarketingShell';
import useSeo from '../../../utils/seo';

const API = process.env.REACT_APP_BACKEND_URL;
const SITE = 'https://www.gymaxisai.com';

export default function MaintenanceIndex() {
  const [manufacturers, setManufacturers] = useState([]);

  useEffect(() => {
    axios.get(`${API}/api/seo/landing/manufacturers`)
      .then((r) => setManufacturers(r.data?.manufacturers || []))
      .catch(() => {});
  }, []);

  useSeo({
    title: 'Gym Equipment Maintenance by Manufacturer | GymAxis AI',
    description:
      'Maintenance and service software for every major gym equipment manufacturer — asset register, fault logging, planned maintenance, parts and compliance. Find your brand.',
    canonical: `${SITE}/maintenance`,
    image: `${SITE}/brand/og-cover.jpg`,
    structuredData: {
      '@context': 'https://schema.org',
      '@type': 'CollectionPage',
      name: 'Gym Equipment Maintenance by Manufacturer',
      url: `${SITE}/maintenance`,
    },
  });

  return (
    <MarketingShell>
      <section className="gx-grid-bg" data-testid="maintenance-index">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 pt-14 pb-12 lg:pt-20">
          <nav className="text-xs text-slate-500 mb-5 flex items-center gap-1.5" aria-label="Breadcrumb">
            <Link to="/" className="hover:text-slate-700">GymAxis</Link>
            <ChevronRight size={11} />
            <span className="text-slate-700 font-semibold">Maintenance</span>
          </nav>
          <span className="inline-flex items-center gap-2 rounded-full bg-white border border-slate-200 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-slate-600 dark:bg-zinc-900 dark:border-zinc-800">
            <Wrench size={12} /> By manufacturer
          </span>
          <h1 className="mt-5 text-4xl md:text-5xl lg:text-6xl tracking-tighter font-black leading-[1.05] max-w-4xl">
            Maintenance software for <span className="gx-gradient-text">every brand</span> on your floor.
          </h1>
          <p className="mt-6 text-lg md:text-xl text-slate-600 leading-relaxed max-w-3xl">
            Whatever you run — cardio, strength, indoor cycling or functional — GymAxis keeps it serviced, compliant and on the floor. Pick a manufacturer for a brand-specific guide.
          </p>
        </div>
      </section>

      <section className="bg-white py-12 lg:py-20 dark:bg-zinc-900">
        <div className="max-w-6xl mx-auto px-6 lg:px-8">
          {manufacturers.length === 0 ? (
            <p className="text-slate-500">Loading manufacturers…</p>
          ) : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
              {manufacturers.map((m) => (
                <Link key={m.slug} to={`/maintenance/${m.slug}`} className="group rounded-2xl border border-slate-200 p-7 hover:shadow-md hover:border-slate-300 transition dark:border-zinc-800" data-testid={`maintenance-card-${m.slug}`}>
                  <h2 className="text-xl font-black tracking-tight">{m.name}</h2>
                  <p className="mt-2 text-sm text-slate-600">{m.product_count}+ products in catalogue</p>
                  <span className="mt-4 inline-flex items-center gap-1.5 text-sm font-bold gx-gradient-text">
                    {m.name} maintenance <ArrowRight size={14} />
                  </span>
                </Link>
              ))}
            </div>
          )}
        </div>
      </section>
    </MarketingShell>
  );
}
