/**
 * Public "brag" widget — shareable stats for a single gym.
 *
 * Served at /m/:slug/brag, no auth required. Designed to be
 * Instagram-pretty: big number, top class, brand colour, simple CTA.
 * The gym can screenshot it or paste the link into their bio.
 */
import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Sparkles, Users, Calendar, TrendingUp, ArrowRight } from 'lucide-react';

export default function BrandedBragPage() {
  const { slug } = useParams();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(false);
  const API = process.env.REACT_APP_BACKEND_URL;

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/api/m/${slug}/brag`);
        setData(r.data);
      } catch { setErr(true); }
    })();
  }, [slug, API]);

  if (err) return (
    <div className="min-h-screen bg-[var(--color-surface-darker)] text-white grid place-items-center p-8" data-testid="brag-404">
      <div className="text-center">
        <div className="text-6xl font-black opacity-20">404</div>
        <div className="mt-2 text-white/60 text-sm">Studio not found</div>
      </div>
    </div>
  );
  if (!data) return <div className="min-h-screen bg-[var(--color-surface-darker)]" data-testid="brag-loading" />;

  const color = data.organization.primary_brand_colour || 'var(--color-brand-cyan)';
  const s = data.stats;

  return (
    <div className="min-h-screen bg-[var(--color-surface-darker)] text-white flex items-center justify-center p-6" data-testid="brag-page">
      <div className="w-full max-w-[480px] rounded-[24px] overflow-hidden border border-white/10 shadow-2xl" style={{ background: 'linear-gradient(180deg, var(--color-ink) 0%, var(--color-surface-darker) 100%)' }}>
        {/* Header */}
        <div className="px-6 py-7 border-b border-white/5" style={{ background: `linear-gradient(135deg, ${color}22 0%, transparent 60%)` }}>
          <div className="flex items-center gap-3">
            {data.organization.logo_url ? (
              <img src={data.organization.logo_url} alt="" className="w-12 h-12 rounded-xl" loading="eager" decoding="async" />
            ) : (
              <div className="w-12 h-12 rounded-xl grid place-items-center" style={{ background: `${color}1F`, color }}>
                <Sparkles size={22} />
              </div>
            )}
            <div>
              <div className="text-[10px] font-bold tracking-[0.25em] uppercase" style={{ color }}>Studio live stats</div>
              <h1 className="text-xl font-extrabold leading-tight">{data.organization.name}</h1>
            </div>
          </div>
        </div>

        {/* Hero number */}
        <div className="px-6 py-8 text-center">
          <div className="text-[72px] font-black tracking-tight leading-none" style={{ color }}>
            {s.active_members}
          </div>
          <div className="text-sm font-bold tracking-wider uppercase text-white/50 mt-2">Active members</div>
        </div>

        {/* Stat grid */}
        <div className="px-6 pb-6 grid grid-cols-2 gap-3">
          <Stat icon={Calendar} label="Classes this month" value={s.classes_this_month} color={color} />
          <Stat icon={Users} label="Check-ins this month" value={s.attendance_this_month} color={color} />
        </div>

        {/* Top class */}
        {s.top_class && (
          <div className="mx-6 mb-6 p-4 rounded-xl border" style={{ borderColor: `${color}55`, background: `${color}0E` }} data-testid="brag-top-class">
            <div className="flex items-center gap-1.5 text-[10px] font-bold tracking-wider uppercase" style={{ color }}>
              <TrendingUp size={11} /> Top class · last 30 days
            </div>
            <div className="mt-2 text-2xl font-extrabold">{s.top_class.name}</div>
            <div className="text-xs text-white/60 mt-1">{s.top_class.attended} members attended</div>
          </div>
        )}

        {/* CTA */}
        <div className="px-6 pb-6">
          <a href={`/m/${data.organization.slug}`} className="flex items-center justify-center gap-2 w-full py-3 rounded-xl font-bold text-sm text-black transition-transform hover:scale-[1.02]" style={{ background: color }} data-testid="brag-cta">
            Book a class <ArrowRight size={16} />
          </a>
          <a href={`${API}/api/m/${data.organization.slug}/poster.png`} target="_blank" rel="noreferrer" download={`${data.organization.slug}-poster.png`}
             className="mt-3 flex items-center justify-center gap-2 w-full py-2.5 rounded-xl font-bold text-xs border border-white/15 text-white/70 hover:bg-white dark:bg-zinc-900/5 transition"
             data-testid="brag-poster-download">
            Download QR poster
          </a>
          <div className="mt-4 text-center">
            <div className="text-[10px] text-white/30 tracking-[0.2em] uppercase">Powered by GymAxis</div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Stat({ icon: Icon, label, value, color }) {
  return (
    <div className="p-4 rounded-xl border border-white/10 bg-white dark:bg-zinc-900/[0.03]">
      <div className="flex items-center gap-1.5 text-[10px] font-bold tracking-wider uppercase text-white/50">
        <Icon size={11} style={{ color }} /> {label}
      </div>
      <div className="text-2xl font-extrabold mt-1">{value}</div>
    </div>
  );
}
