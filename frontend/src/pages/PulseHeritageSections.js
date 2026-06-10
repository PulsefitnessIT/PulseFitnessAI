/**
 * Pulse Heritage marketing sections (iter 228 — landing redesign).
 *
 * Four sections stripped from the official "Pulse Fitness Master
 * Presentation v4" and rebuilt for the /pulse landing page:
 *   <TrustedBy />        — typographic partner strip
 *   <HeritageTimeline /> — "45 Years of Innovation in Motion"
 *   <StatsBento />       — company + service stats control-room grid
 *   <Sustainability />   — recycled-materials engineering proof points
 *
 * Pure presentational components — no auth / data dependencies.
 */
import React, { useRef } from 'react';
import { motion, useInView } from 'framer-motion';
import { Recycle, Leaf, Zap } from 'lucide-react';

const FADE_UP = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.7, ease: [0.16, 1, 0.3, 1] } },
};
const stagger = { show: { transition: { staggerChildren: 0.08 } } };

function Reveal({ children, className = '', testId }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, amount: 0.2 });
  return (
    <motion.div ref={ref} initial="hidden" animate={inView ? 'show' : 'hidden'} variants={stagger} className={className} data-testid={testId}>
      {children}
    </motion.div>
  );
}

// ── Trusted By ─────────────────────────────────────────────────
const PARTNERS = [
  'THIRD SPACE',
  'IMPERIAL COLLEGE LONDON',
  'LEISURE UNITED',
  'BRAYWICK LEISURE',
  'BALANCE HEALTH',
  'SPORT ABERDEEN',
  'CHESHIRE EAST',
];

export function TrustedBy() {
  return (
    <section className="py-10 sm:py-12 bg-white border-b border-[var(--color-border-light)]" data-testid="pulse-trusted-by">
      <div className="max-w-7xl mx-auto px-6">
        <Reveal>
          <motion.p variants={FADE_UP} className="text-center text-[11px] uppercase tracking-[0.25em] font-bold text-[var(--color-text-slate)] mb-7">
            Trusted by operators worldwide — 30,000+ facilities partnered across 31 countries
          </motion.p>
          <motion.div variants={FADE_UP} className="flex flex-wrap items-center justify-center gap-x-10 gap-y-4">
            {PARTNERS.map((name) => (
              <span
                key={name}
                className="text-xs sm:text-sm font-black tracking-[0.18em] text-[var(--pulse-grey-light,#A2ACAB)] whitespace-nowrap select-none"
                data-testid={`trusted-partner-${name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
              >
                {name}
              </span>
            ))}
          </motion.div>
        </Reveal>
      </div>
    </section>
  );
}

// ── Heritage Timeline ──────────────────────────────────────────
const MILESTONES = [
  { year: '1980', title: 'Foundations laid', body: 'Brothers Chris and Dave Johnson — ex Rolls-Royce engineers — begin manufacturing precision-engineered strength equipment in the UK.' },
  { year: '1990s', title: 'Cardio joins the line-up', body: 'Pulse releases its first in-house designed cardio range, becoming a complete fitness equipment manufacturer for strength and cardio.' },
  { year: '2000s', title: 'Global expansion', body: 'Planet Pulse launches turnkey facility design, installation and partnerships across Sweden, India and Ireland.' },
  { year: '2013', title: 'A connected future', body: 'New HQ and warehouse. 18.5″ Android consoles with EGYM connectivity set the stage for the digital gym floor.' },
  { year: '2019', title: 'The TRAKK ecosystem arrives', body: 'Cardio, strength and user data linked through touchscreen consoles and app-based connectivity — a new standard for digital fitness.' },
  { year: '2023', title: 'Smarter, faster, more connected', body: 'OnDemand content and Cirrus V4 software ship; the distribution network now spans 30+ countries.' },
  { year: 'Today', title: '45 years of innovation', body: 'Next-generation connected equipment, the TRAKK Web & Mobile apps — and this self-service portal for the teams who run it all.' },
];

export function HeritageTimeline() {
  return (
    <section className="py-16 sm:py-20 bg-[var(--color-neutral-25)] border-y border-[var(--color-border-light)] overflow-hidden" data-testid="pulse-heritage">
      <div className="max-w-7xl mx-auto px-6 grid lg:grid-cols-[0.9fr_1.1fr] gap-14 items-start">
        {/* Sticky intro + imagery */}
        <div className="lg:sticky lg:top-28">
          <Reveal>
            <motion.div variants={FADE_UP} className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-[var(--pulse-primary)] font-semibold mb-4">
              <span className="h-px w-6 bg-[rgb(var(--rgb-pulse-primary)/0.5)]" /> Since 1980
            </motion.div>
            <motion.h2 variants={FADE_UP} className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-[var(--color-surface-dark-panel-alt)] leading-[1.1]">
              45 years of innovation in motion.
            </motion.h2>
            <motion.p variants={FADE_UP} className="mt-4 text-base sm:text-lg text-[var(--color-text-slate)] max-w-md">
              The portal you&apos;re looking at is built by the same British engineering team
              that has designed, built and serviced gym equipment for four and a half decades.
            </motion.p>
            <motion.div variants={FADE_UP} className="mt-10 relative hidden sm:block" aria-hidden="true">
              <div className="rounded-3xl overflow-hidden border border-[var(--color-border-light)] shadow-xl w-[78%]">
                <img src="/pulse-photos/gym-orange-lights.webp" alt="Modern Pulse Fitness gym installation" className="w-full h-auto object-cover max-h-[340px]" loading="lazy" />
              </div>
              <div className="absolute -bottom-10 right-0 w-[42%] rounded-3xl overflow-hidden border border-[var(--color-border-light)] shadow-2xl bg-white">
                <img src="/pulse-photos/product-crosstrainer.webp" alt="Pulse Fitness cross trainer" className="w-full h-auto object-cover" loading="lazy" />
              </div>
            </motion.div>
          </Reveal>
        </div>

        {/* Timeline rail */}
        <Reveal className="relative pl-8 sm:pl-10" testId="pulse-heritage-timeline">
          <div className="absolute left-[7px] sm:left-[9px] top-2 bottom-2 w-px bg-gradient-to-b from-[var(--pulse-primary)] via-[rgb(var(--rgb-pulse-primary)/0.35)] to-transparent" />
          <div className="space-y-8">
            {MILESTONES.map(({ year, title, body }) => (
              <motion.div key={year} variants={FADE_UP} className="relative" data-testid={`heritage-milestone-${year.toLowerCase()}`}>
                <span className="absolute -left-8 sm:-left-10 top-1.5 w-[15px] h-[15px] sm:w-[19px] sm:h-[19px] rounded-full border-[3px] border-[var(--pulse-primary)] bg-white" />
                <div className="text-[11px] font-black tracking-[0.2em] text-[var(--pulse-primary)] uppercase">{year}</div>
                <h3 className="mt-1 text-lg sm:text-xl font-extrabold text-[var(--color-surface-dark-panel-alt)] tracking-tight">{title}</h3>
                <p className="mt-1.5 text-sm text-[var(--color-text-slate)] leading-relaxed max-w-lg">{body}</p>
              </motion.div>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

// ── Stats Bento ────────────────────────────────────────────────
function CountUpValue({ value }) {
  // Static render — the design calls for bold cyan numerals; counting
  // animation is handled by the entrance fade for simplicity/perf.
  return <span>{value}</span>;
}

const STAT_CELLS = [
  { value: '95.5%', label: 'First-time fix rate', sub: 'In-house UK service team', big: true },
  { value: '48hr', label: 'Service response', sub: '94.5% hit within 48 hours' },
  { value: '30K+', label: 'R&D hours each year', sub: '186 years of combined design experience' },
  { value: '£250M+', label: 'Invested in leisure projects', sub: 'Design, build & operate partnerships' },
  { value: '150+', label: 'Employees', sub: 'UK design, build & assembly' },
];

export function StatsBento() {
  return (
    <section className="py-16 sm:py-20 bg-white" data-testid="pulse-stats">
      <div className="max-w-7xl mx-auto px-6">
        <Reveal className="max-w-2xl mb-10">
          <motion.div variants={FADE_UP} className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-[var(--pulse-primary)] font-semibold mb-4">
            <span className="h-px w-6 bg-[rgb(var(--rgb-pulse-primary)/0.5)]" /> The numbers behind the portal
          </motion.div>
          <motion.h2 variants={FADE_UP} className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-[var(--color-surface-dark-panel-alt)] leading-[1.1]">
            Manufacturer-grade service. Measured, not promised.
          </motion.h2>
        </Reveal>

        <Reveal className="grid grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-5" testId="pulse-stats-grid">
          {/* Big first-time-fix cell */}
          <motion.div
            variants={FADE_UP}
            className="col-span-2 row-span-2 rounded-3xl bg-[var(--pulse-black,#212721)] p-8 sm:p-10 flex flex-col justify-between min-h-[280px] border border-white/10"
            data-testid="stat-first-time-fix"
          >
            <div className="text-[11px] uppercase tracking-[0.2em] font-bold" style={{ color: 'rgba(255,255,255,0.55)' }}>Service &amp; maintenance</div>
            <div>
              <div className="font-black text-[var(--pulse-primary)] leading-none" style={{ fontSize: 'clamp(4rem, 9vw, 7rem)', letterSpacing: '-0.03em' }}>
                <CountUpValue value="95.5%" />
              </div>
              <div className="mt-3 text-lg font-bold" style={{ color: '#fff' }}>First-time fix rate</div>
              <div className="text-sm" style={{ color: 'rgba(255,255,255,0.55)' }}>In-house UK service team · flexible service contracts · industry-leading response times</div>
            </div>
          </motion.div>

          {/* Image cell — 450+ products */}
          <motion.div variants={FADE_UP} className="col-span-2 row-span-2 relative rounded-3xl overflow-hidden min-h-[280px] group" data-testid="stat-products-image">
            <div className="absolute inset-0 bg-cover transition-transform duration-700 group-hover:scale-105" style={{ backgroundImage: 'url(/pulse-photos/gym-cardio-angle.webp)', backgroundPosition: 'center 68%' }} />
            <div className="absolute inset-0" style={{ background: 'linear-gradient(to top, rgba(33,39,33,0.97) 0%, rgba(33,39,33,0.82) 45%, rgba(33,39,33,0.4) 100%)' }} />
            <div className="relative h-full p-8 sm:p-10 flex flex-col justify-end">
              <div className="font-black leading-none" style={{ color: '#ffffff', fontSize: 'clamp(3rem, 6vw, 5rem)', letterSpacing: '-0.03em', textShadow: '0 2px 24px rgba(0,0,0,0.8)' }}>450+</div>
              <div className="mt-2 text-lg font-bold" style={{ color: '#ffffff', textShadow: '0 1px 16px rgba(0,0,0,0.8)' }}>Fitness products designed &amp; built</div>
              <div className="text-sm" style={{ color: 'rgba(255,255,255,0.85)', textShadow: '0 1px 16px rgba(0,0,0,0.8)' }}>21+ fully DDA-compliant · strength, cardio &amp; inclusive ranges</div>
            </div>
          </motion.div>

          {/* Small stat cells */}
          {STAT_CELLS.slice(1).map(({ value, label, sub }) => (
            <motion.div
              key={label}
              variants={FADE_UP}
              className="rounded-3xl bg-[var(--color-neutral-25)] border border-[var(--color-border-light)] p-6 sm:p-7 hover:border-[rgb(var(--rgb-pulse-primary)/0.4)] transition-colors"
              data-testid={`stat-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}
            >
              <div className="text-3xl sm:text-4xl font-black text-[var(--color-surface-dark-panel-alt)] tracking-tight" style={{ letterSpacing: '-0.02em' }}>{value}</div>
              <div className="mt-2 text-sm font-bold text-[var(--color-surface-dark-panel-alt)]">{label}</div>
              <div className="mt-0.5 text-xs text-[var(--color-text-slate)] leading-relaxed">{sub}</div>
            </motion.div>
          ))}
        </Reveal>
      </div>
    </section>
  );
}

// ── Sustainability ─────────────────────────────────────────────
const ECO_POINTS = [
  { icon: Recycle, value: '100%', label: 'Recycled steel used across manufacturing' },
  { icon: Leaf, value: '90%', label: 'Materials recycled in strength ranges' },
  { icon: Recycle, value: '75%', label: 'Materials recycled in cardio ranges' },
  { icon: Zap, value: 'Low energy', label: 'Energy-saving features on cardio equipment' },
];

export function Sustainability() {
  return (
    <section className="py-16 sm:py-20 bg-[var(--color-neutral-25)] border-y border-[var(--color-border-light)]" data-testid="pulse-sustainability">
      <div className="max-w-7xl mx-auto px-6 grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
        <div>
          <Reveal>
            <motion.div variants={FADE_UP} className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-[var(--pulse-primary)] font-semibold mb-4">
              <span className="h-px w-6 bg-[rgb(var(--rgb-pulse-primary)/0.5)]" /> Engineering, responsibly
            </motion.div>
            <motion.h2 variants={FADE_UP} className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-[var(--color-surface-dark-panel-alt)] leading-[1.1]">
              Built to last. Built to be rebuilt.
            </motion.h2>
            <motion.p variants={FADE_UP} className="mt-4 text-base sm:text-lg text-[var(--color-text-slate)] max-w-md">
              Universally designed parts and an ongoing commitment to reducing our carbon
              footprint — the same engineering discipline behind every machine this portal tracks.
            </motion.p>
            <motion.div variants={FADE_UP} className="mt-9 grid sm:grid-cols-2 gap-4">
              {ECO_POINTS.map(({ icon: Icon, value, label }) => (
                <div key={label} className="flex gap-4 items-start bg-white rounded-2xl border border-[var(--color-border-light)] p-5" data-testid={`eco-${label.toLowerCase().split(' ')[0]}-${value.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
                  <div className="w-10 h-10 rounded-xl bg-[rgb(var(--rgb-pulse-primary)/0.12)] flex items-center justify-center flex-shrink-0">
                    <Icon size={18} className="text-[var(--pulse-primary)]" />
                  </div>
                  <div>
                    <div className="text-xl font-black text-[var(--color-surface-dark-panel-alt)] tracking-tight">{value}</div>
                    <div className="text-xs text-[var(--color-text-slate)] leading-relaxed mt-0.5">{label}</div>
                  </div>
                </div>
              ))}
            </motion.div>
          </Reveal>
        </div>

        {/* Imagery composition — the machines themselves, built to last */}
        <Reveal className="relative" testId="pulse-sustainability-imagery">
          <motion.div variants={FADE_UP} className="grid grid-cols-2 gap-4">
            {[
              ['/pulse-photos/product-crosstrainer.webp', 'Pulse cross trainer'],
              ['/pulse-photos/product-stepmill.webp', 'Pulse premium stepmill'],
              ['/pulse-photos/product-cable-machine.webp', 'Pulse multi-functional trainer'],
              ['/pulse-photos/product-bike.webp', 'Pulse group cycle'],
            ].map(([src, alt]) => (
              <div key={src} className="rounded-3xl overflow-hidden border border-[var(--color-border-light)] bg-white shadow-sm">
                <img src={src} alt={alt} className="w-full h-auto object-cover" loading="lazy" />
              </div>
            ))}
          </motion.div>
          <motion.div variants={FADE_UP} className="mt-4 text-center text-[11px] uppercase tracking-[0.2em] font-bold text-[var(--color-text-slate)]">
            Designed, engineered &amp; built in Britain
          </motion.div>
        </Reveal>
      </div>
    </section>
  );
}
