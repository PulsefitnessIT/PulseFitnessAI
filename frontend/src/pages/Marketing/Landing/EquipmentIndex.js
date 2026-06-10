/**
 * EquipmentIndex — /equipment hub listing every equipment *type* that has
 * a servicing landing page (data-driven from the catalogue). The category
 * axis that complements /maintenance (the brand axis). Grows automatically
 * as the catalogue ingests more machines of each type.
 */
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { ArrowRight, Cog, ChevronRight, Building2 } from 'lucide-react';

import '../marketing.css';
import MarketingShell from '../MarketingShell';
import useSeo from '../../../utils/seo';

const API = process.env.REACT_APP_BACKEND_URL;
const SITE = 'https://gymaxisai.com';

export default function EquipmentIndex() {
  const [equipment, setEquipment] = useState([]);

  useEffect(() => {
    axios.get(`${API}/api/seo/landing/equipment`)
      .then((r) => setEquipment(r.data?.equipment || []))
      .catch(() => {});
  }, []);

  useSeo({
    title: 'Gym Equipment Servicing & Repair by Type | GymAxis AI',
    description:
      'Servicing and maintenance software for every type of gym equipment — treadmills, exercise bikes, rowers, cross trainers and strength machines. Asset register, fault logging, planned maintenance and parts.',
    canonical: `${SITE}/equipment`,
    image: `${SITE}/brand/og-cover.jpg`,
    structuredData: {
      '@context': 'https://schema.org',
      '@type': 'CollectionPage',
      name: 'Gym Equipment Servicing by Type',
      url: `${SITE}/equipment`,
    },
  });

  return (
    <MarketingShell>
      <section className="gx-grid-bg" data-testid="equipment-index">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 pt-14 pb-12 lg:pt-20">
          <nav className="text-xs text-slate-500 mb-5 flex items-center gap-1.5" aria-label="Breadcrumb">
            <Link to="/" className="hover:text-slate-700">GymAxis</Link>
            <ChevronRight size={11} />
            <span className="text-slate-700 font-semibold">Equipment</span>
          </nav>
          <span className="inline-flex items-center gap-2 rounded-full bg-white border border-slate-200 px-3 py-1 text-xs font-bold uppercase tracking-[0.18em] text-slate-600 dark:bg-zinc-900 dark:border-zinc-800">
            <Cog size={12} /> By equipment type
          </span>
          <h1 className="mt-5 text-4xl md:text-5xl lg:text-6xl tracking-tighter font-black leading-[1.05] max-w-4xl">
            Servicing for <span className="gx-gradient-text">every machine</span> on your floor.
          </h1>
          <p className="mt-6 text-lg md:text-xl text-slate-600 leading-relaxed max-w-3xl">
            Pick an equipment type for a servicing &amp; repair guide — common faults, planned maintenance and the brands we cover. Or browse{' '}
            <Link to="/maintenance" className="font-semibold gx-gradient-text">by manufacturer</Link>.
          </p>
        </div>
      </section>

      <section className="bg-white py-12 lg:py-20 dark:bg-zinc-900">
        <div className="max-w-6xl mx-auto px-6 lg:px-8">
          {equipment.length === 0 ? (
            <p className="text-slate-500">Loading equipment types…</p>
          ) : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
              {equipment.map((e) => (
                <Link key={e.slug} to={`/equipment/${e.slug}`} className="group rounded-2xl border border-slate-200 p-7 hover:shadow-md hover:border-slate-300 transition dark:border-zinc-800" data-testid={`equipment-card-${e.slug}`}>
                  <h2 className="text-xl font-black tracking-tight">{e.name} servicing</h2>
                  <p className="mt-2 text-sm text-slate-600">{e.product_count}+ machines · {e.brands?.length || 0} brand{(e.brands?.length || 0) === 1 ? '' : 's'}</p>
                  {e.brands?.length > 0 && (
                    <p className="mt-2 text-xs text-slate-400 flex items-center gap-1.5 line-clamp-1">
                      <Building2 size={11} /> {e.brands.slice(0, 4).join(' · ')}
                    </p>
                  )}
                  <span className="mt-4 inline-flex items-center gap-1.5 text-sm font-bold gx-gradient-text">
                    {e.name} servicing <ArrowRight size={14} />
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
