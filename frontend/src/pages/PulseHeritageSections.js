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
import { useRef } from 'react';
import { motion, useInView } from 'framer-motion';
import { useTranslation } from 'react-i18next';
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
  { name: 'THIRD SPACE' },
  { name: 'IMPERIAL COLLEGE LONDON' },
  { name: 'LEISURE UNITED', logo: '/brand/operators/leisure-united.png' },
  { name: 'BRAYWICK LEISURE', logo: '/brand/operators/braywick.png' },
  { name: 'BALANCE HEALTH' },
  { name: 'SPORT ABERDEEN', logo: '/brand/operators/sport-aberdeen.png' },
  { name: 'CHESHIRE EAST' },
];

export function TrustedBy() {
  const { t } = useTranslation();
  return (
    <section className="py-10 sm:py-12 bg-white border-b border-[var(--color-border-light)]" data-testid="pulse-trusted-by">
      <div className="max-w-7xl mx-auto px-6">
        <Reveal>
          <motion.p variants={FADE_UP} className="text-center text-[11px] uppercase tracking-[0.25em] font-bold text-[#6E7476] mb-8">
            {t('pulse.tb_caption', 'Trusted by operators worldwide — 30,000+ facilities partnered across 31 countries')}
          </motion.p>
          <motion.div variants={FADE_UP} className="flex flex-wrap items-center justify-center gap-x-12 gap-y-6">
            {PARTNERS.map((p) => {
              const testId = `trusted-partner-${p.name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
              return p.logo ? (
                <img
                  key={p.name}
                  src={p.logo}
                  alt={p.name}
                  className="h-10 w-auto max-w-[170px] object-contain select-none"
                  loading="lazy"
                  draggable={false}
                  data-testid={testId}
                />
              ) : (
                <span
                  key={p.name}
                  className="text-xs sm:text-sm font-black tracking-[0.18em] text-[#393E41] whitespace-nowrap select-none"
                  data-testid={testId}
                >
                  {p.name}
                </span>
              );
            })}
          </motion.div>
        </Reveal>
      </div>
    </section>
  );
}

// ── Heritage Timeline ──────────────────────────────────────────
const MILESTONES = (t) => [
  { year: t('pulse.ms_1980_y', '1980'), title: t('pulse.ms_1980_t', 'Foundations laid'), body: t('pulse.ms_1980_b', 'Brothers Chris and Dave Johnson — ex Rolls-Royce engineers — begin manufacturing precision-engineered strength equipment in the UK.') },
  { year: t('pulse.ms_1990s_y', '1990s'), title: t('pulse.ms_1990s_t', 'Cardio joins the line-up'), body: t('pulse.ms_1990s_b', 'Pulse releases its first in-house designed cardio range, becoming a complete fitness equipment manufacturer for strength and cardio.') },
  { year: t('pulse.ms_2000s_y', '2000s'), title: t('pulse.ms_2000s_t', 'Global expansion'), body: t('pulse.ms_2000s_b', 'Planet Pulse launches turnkey facility design, installation and partnerships across Sweden, India and Ireland.') },
  { year: t('pulse.ms_2013_y', '2013'), title: t('pulse.ms_2013_t', 'A connected future'), body: t('pulse.ms_2013_b', 'New HQ and warehouse. 18.5″ Android consoles with EGYM connectivity set the stage for the digital gym floor.') },
  { year: t('pulse.ms_2019_y', '2019'), title: t('pulse.ms_2019_t', 'The TRAKK ecosystem arrives'), body: t('pulse.ms_2019_b', 'Cardio, strength and user data linked through touchscreen consoles and app-based connectivity — a new standard for digital fitness.') },
  { year: t('pulse.ms_2023_y', '2023'), title: t('pulse.ms_2023_t', 'Smarter, faster, more connected'), body: t('pulse.ms_2023_b', 'OnDemand content and Cirrus V4 software ship; the distribution network now spans 30+ countries.') },
  { year: t('pulse.ms_today_y', 'Today'), title: t('pulse.ms_today_t', '45 years of innovation'), body: t('pulse.ms_today_b', 'The culmination of 45 years of British engineering — one connected platform where gym teams log faults, track every asset and manage service in real time. The same pioneering heritage that has equipped 30,000+ facilities across 31 countries, now working for the people who run them.') },
];

export function HeritageTimeline() {
  const { t } = useTranslation();
  return (
    <section className="py-16 sm:py-20 bg-[var(--color-neutral-25)] border-y border-[var(--color-border-light)] overflow-hidden" data-testid="pulse-heritage">
      <div className="max-w-7xl mx-auto px-6 grid lg:grid-cols-[0.9fr_1.1fr] gap-14 items-start">
        {/* Sticky intro + imagery */}
        <div className="lg:sticky lg:top-28">
          <Reveal>
            <motion.div variants={FADE_UP} className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-[var(--pulse-primary)] font-semibold mb-4">
              <span className="h-px w-6 bg-[rgb(var(--rgb-pulse-primary)/0.5)]" /> {t('pulse.her_since', 'Since 1980')}
            </motion.div>
            <motion.h2 variants={FADE_UP} className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-[var(--color-surface-dark-panel-alt)] leading-[1.1]">
              {t('pulse.her_title', '45 years of innovation in motion.')}
            </motion.h2>
            <motion.p variants={FADE_UP} className="mt-4 text-base sm:text-lg text-[var(--color-text-slate)] max-w-md">
              {t('pulse.her_desc', "The portal you're looking at is built by the same British engineering team that has designed, built and serviced gym equipment for four and a half decades.")}
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
            {MILESTONES(t).map(({ year, title, body }) => (
              <motion.div key={title} variants={FADE_UP} className="relative" data-testid={`heritage-milestone-${year.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
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

const STAT_CELLS = (t) => [
  { value: t('pulse.st_48_v', '48hr'), label: t('pulse.st_48_l', 'Service response'), sub: t('pulse.st_48_s', '94.5% hit within 48 hours') },
  { value: t('pulse.st_30k_v', '30K+'), label: t('pulse.st_30k_l', 'R&D hours each year'), sub: t('pulse.st_30k_s', '186 years of combined design experience') },
  { value: t('pulse.st_250_v', '£250M+'), label: t('pulse.st_250_l', 'Invested in leisure projects'), sub: t('pulse.st_250_s', 'Design, build & operate partnerships') },
  { value: t('pulse.st_150_v', '150+'), label: t('pulse.st_150_l', 'Employees'), sub: t('pulse.st_150_s', 'UK design, build & assembly') },
];

export function StatsBento() {
  const { t } = useTranslation();
  return (
    <section className="py-16 sm:py-20 bg-white" data-testid="pulse-stats">
      <div className="max-w-7xl mx-auto px-6">
        <Reveal className="max-w-2xl mb-10">
          <motion.div variants={FADE_UP} className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-[var(--pulse-primary)] font-semibold mb-4">
            <span className="h-px w-6 bg-[rgb(var(--rgb-pulse-primary)/0.5)]" /> {t('pulse.st_eyebrow', 'The numbers behind the portal')}
          </motion.div>
          <motion.h2 variants={FADE_UP} className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-[var(--color-surface-dark-panel-alt)] leading-[1.1]">
            {t('pulse.st_title', 'Manufacturer-grade service. Measured, not promised.')}
          </motion.h2>
        </Reveal>

        <Reveal className="grid grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-5" testId="pulse-stats-grid">
          {/* Big first-time-fix cell */}
          <motion.div
            variants={FADE_UP}
            className="col-span-2 row-span-2 rounded-3xl bg-[var(--pulse-black,#212721)] p-8 sm:p-10 flex flex-col justify-between min-h-[280px] border border-white/10"
            data-testid="stat-first-time-fix"
          >
            <div className="text-[11px] uppercase tracking-[0.2em] font-bold" style={{ color: 'rgba(255,255,255,0.55)' }}>{t('pulse.st_service', 'Service & maintenance')}</div>
            <div>
              <div className="font-black text-[var(--pulse-primary)] leading-none" style={{ fontSize: 'clamp(4rem, 9vw, 7rem)', letterSpacing: '-0.03em' }}>
                <CountUpValue value="95.5%" />
              </div>
              <div className="mt-3 text-lg font-bold" style={{ color: '#fff' }}>{t('pulse.st_fix_label', 'First-time fix rate')}</div>
              <div className="text-sm" style={{ color: 'rgba(255,255,255,0.55)' }}>{t('pulse.st_fix_sub', 'In-house UK service team · flexible service contracts · industry-leading response times')}</div>
            </div>
          </motion.div>

          {/* Image cell — 450+ products */}
          <motion.div variants={FADE_UP} className="col-span-2 row-span-2 relative rounded-3xl overflow-hidden min-h-[280px] group" data-testid="stat-products-image">
            <div className="absolute inset-0 bg-cover transition-transform duration-700 group-hover:scale-105" style={{ backgroundImage: 'url(/pulse-photos/gym-cardio-angle.webp)', backgroundPosition: 'center 68%' }} />
            <div className="absolute inset-0" style={{ background: 'linear-gradient(to top, rgba(33,39,33,0.97) 0%, rgba(33,39,33,0.82) 45%, rgba(33,39,33,0.4) 100%)' }} />
            <div className="relative h-full p-8 sm:p-10 flex flex-col justify-end">
              <div className="font-black leading-none" style={{ color: '#ffffff', fontSize: 'clamp(3rem, 6vw, 5rem)', letterSpacing: '-0.03em', textShadow: '0 2px 24px rgba(0,0,0,0.8)' }}>450+</div>
              <div className="mt-2 text-lg font-bold" style={{ color: '#ffffff', textShadow: '0 1px 16px rgba(0,0,0,0.8)' }}>{t('pulse.st_products_label', 'Fitness products designed & built')}</div>
              <div className="text-sm" style={{ color: 'rgba(255,255,255,0.85)', textShadow: '0 1px 16px rgba(0,0,0,0.8)' }}>{t('pulse.st_products_sub', '21+ fully DDA-compliant · strength, cardio & inclusive ranges')}</div>
            </div>
          </motion.div>

          {/* Small stat cells */}
          {STAT_CELLS(t).map(({ value, label, sub }) => (
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
const ECO_POINTS = (t) => [
  { icon: Recycle, value: '100%', label: t('pulse.eco1', 'Recycled steel used across manufacturing') },
  { icon: Leaf, value: '90%', label: t('pulse.eco2', 'Materials recycled in strength ranges') },
  { icon: Recycle, value: '75%', label: t('pulse.eco3', 'Materials recycled in cardio ranges') },
  { icon: Zap, value: t('pulse.eco4_v', 'Low energy'), label: t('pulse.eco4', 'Energy-saving features on cardio equipment') },
];

export function Sustainability() {
  const { t } = useTranslation();
  return (
    <section className="py-16 sm:py-20 bg-[var(--color-neutral-25)] border-y border-[var(--color-border-light)]" data-testid="pulse-sustainability">
      <div className="max-w-7xl mx-auto px-6 grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
        <div>
          <Reveal>
            <motion.div variants={FADE_UP} className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-[var(--pulse-primary)] font-semibold mb-4">
              <span className="h-px w-6 bg-[rgb(var(--rgb-pulse-primary)/0.5)]" /> {t('pulse.eco_eyebrow', 'Engineering, responsibly')}
            </motion.div>
            <motion.h2 variants={FADE_UP} className="text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight text-[var(--color-surface-dark-panel-alt)] leading-[1.1]">
              {t('pulse.eco_title', 'Built to last. Built to be rebuilt.')}
            </motion.h2>
            <motion.p variants={FADE_UP} className="mt-4 text-base sm:text-lg text-[var(--color-text-slate)] max-w-md">
              {t('pulse.eco_desc', 'Universally designed parts and an ongoing commitment to reducing our carbon footprint — the same engineering discipline behind every machine this portal tracks.')}
            </motion.p>
            <motion.div variants={FADE_UP} className="mt-9 grid sm:grid-cols-2 gap-4">
              {ECO_POINTS(t).map(({ icon: Icon, value, label }) => (
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
            {t('pulse.eco_caption', 'Designed, engineered & built in Britain')}
          </motion.div>
        </Reveal>
      </div>
    </section>
  );
}
