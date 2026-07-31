/**
 * Richer marketing sections for /pulse-pricing: an ROI/savings calculator,
 * service-provider tiers (Service Desk / Engineer App), and an FAQ accordion.
 * On-brand (Pulse cyan). Illustrative figures only. Fully i18n (EN/FR/DE).
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { ChevronDown, Headset, Wrench, ArrowRight, TrendingDown } from 'lucide-react';

const money = (n) => '£' + Math.round(n).toLocaleString();

function RoiSlider({ label, testid, value, set, min, max, step, prefix }) {
  return (
    <div>
      <div className="flex items-center justify-between text-sm text-[var(--color-text-slate)]">
        <span>{label}</span>
        <span className="font-bold text-[var(--color-surface-dark-panel-alt)]">{prefix || ''}{value}</span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => set(Number(e.target.value))}
        className="w-full mt-2 accent-[var(--pulse-primary)]"
        data-testid={testid}
      />
    </div>
  );
}

const SP_TIERS = [
  { key: 'service-desk', icon: Headset, nameKey: 'pulse_pricing.sp_desk_name', blurbKey: 'pulse_pricing.sp_desk_blurb', featureKeys: ['pulse_pricing.sp_desk_f1', 'pulse_pricing.sp_desk_f2', 'pulse_pricing.sp_desk_f3'] },
  { key: 'engineer-app', icon: Wrench, nameKey: 'pulse_pricing.sp_eng_name', blurbKey: 'pulse_pricing.sp_eng_blurb', featureKeys: ['pulse_pricing.sp_eng_f1', 'pulse_pricing.sp_eng_f2', 'pulse_pricing.sp_eng_f3'] },
];

const FAQ_KEYS = [1, 2, 3, 4, 5, 6];

export default function PulsePricingExtras({ onStart }) {
  const { t } = useTranslation();
  const [machines, setMachines] = useState(80);
  const [callout, setCallout] = useState(120);
  const [perMonth, setPerMonth] = useState(12);
  const [open, setOpen] = useState(0);

  // AI triage resolves ~40% of reactive callouts remotely, and proactive
  // monitoring across the estate prevents ~£3/machine/month of downtime.
  const monthlySaved = perMonth * callout * 0.4 + machines * 3;
  const annualSaved = monthlySaved * 12;

  return (
    <>
      {/* ── ROI / savings calculator ── */}
      <section className="py-16" data-testid="pulse-roi-calculator">
        <div className="max-w-5xl mx-auto px-6">
          <div className="text-center max-w-2xl mx-auto mb-10">
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--pulse-primary)] font-semibold mb-3">{t('pulse_pricing.roi_eyebrow', 'Your return')}</div>
            <h2 className="text-2xl sm:text-4xl font-bold tracking-[-0.02em] text-[var(--color-surface-dark-panel-alt)]">{t('pulse_pricing.roi_heading', 'See what Pulse pays back.')}</h2>
            <p className="mt-3 text-sm sm:text-base text-[var(--color-text-slate)]">{t('pulse_pricing.roi_subtitle', 'AI triage resolves a large share of faults before an engineer is dispatched. Estimate your saving.')}</p>
          </div>
          <div className="grid gap-6 lg:grid-cols-2 items-stretch">
            <div className="rounded-2xl border border-[var(--color-border-subtle,#e5e7eb)] bg-white p-7 space-y-6">
              <RoiSlider label={t('pulse_pricing.roi_machines', 'Machines in estate')} testid="roi-machines-in-estate" value={machines} set={setMachines} min={10} max={500} step={5} />
              <RoiSlider label={t('pulse_pricing.roi_callout', 'Avg engineer callout')} testid="roi-avg-engineer-callout" value={callout} set={setCallout} min={40} max={400} step={10} prefix="£" />
              <RoiSlider label={t('pulse_pricing.roi_per_month', 'Callouts per month')} testid="roi-callouts-per-month" value={perMonth} set={setPerMonth} min={1} max={60} step={1} />
            </div>
            <div className="rounded-2xl bg-[var(--color-surface-dark-panel-alt,#0f172a)] text-white p-7 flex flex-col justify-center">
              <div className="inline-flex items-center gap-2 text-[var(--pulse-primary)] text-sm font-semibold">
                <TrendingDown size={16} /> {t('pulse_pricing.roi_saving_label', 'Estimated saving')}
              </div>
              <div className="mt-3 text-5xl font-extrabold tracking-tight text-[var(--pulse-primary)]" data-testid="roi-annual-saving">{money(annualSaved)}<span className="text-lg font-semibold text-white/60">{t('pulse_pricing.per_year', '/yr')}</span></div>
              <div className="mt-1 text-sm text-white/70">{t('pulse_pricing.roi_per_month_note', '≈ {{amount}} every month in avoided callouts', { amount: money(monthlySaved) })}</div>
              <p className="mt-4 text-xs text-white/50">{t('pulse_pricing.roi_disclaimer', 'Illustrative — assumes AI triage resolves ~40% of callouts remotely plus proactive monitoring across your estate. Your results will vary.')}</p>
              <button type="button" onClick={onStart} className="mt-6 h-11 rounded-full bg-[var(--pulse-primary)] text-[#0A0C10] font-semibold text-sm inline-flex items-center justify-center gap-2 hover:brightness-95 transition" data-testid="roi-cta">
                {t('pulse_pricing.roi_cta', 'Start your free trial')} <ArrowRight size={15} />
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* ── Service provider tiers ── */}
      <section className="py-12" data-testid="pulse-service-provider">
        <div className="max-w-5xl mx-auto px-6">
          <div className="text-center max-w-2xl mx-auto mb-8">
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--pulse-primary)] font-semibold mb-3">{t('pulse_pricing.sp_eyebrow', 'For service providers')}</div>
            <h2 className="text-2xl sm:text-3xl font-bold tracking-[-0.02em] text-[var(--color-surface-dark-panel-alt)]">{t('pulse_pricing.sp_heading', 'Run service & field teams on Pulse.')}</h2>
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            {SP_TIERS.map((tier) => (
              <motion.div key={tier.key} initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.5 }}
                className="rounded-2xl border border-[var(--color-border-subtle,#e5e7eb)] bg-white p-7" data-testid={`sp-card-${tier.key}`}>
                <div className="w-11 h-11 rounded-xl bg-[color-mix(in_srgb,var(--pulse-primary)_18%,white)] flex items-center justify-center">
                  <tier.icon size={20} className="text-[var(--pulse-primary)]" />
                </div>
                <div className="mt-4 font-bold text-lg text-[var(--color-surface-dark-panel-alt)]">{t(tier.nameKey)}</div>
                <p className="text-sm text-[var(--color-text-slate)] mt-2 leading-relaxed">{t(tier.blurbKey)}</p>
                <ul className="mt-4 space-y-2">
                  {tier.featureKeys.map((fk) => (
                    <li key={fk} className="flex items-start gap-2 text-sm text-[var(--color-surface-dark-panel-alt)]">
                      <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-[var(--pulse-primary)] flex-shrink-0" />{t(fk)}
                    </li>
                  ))}
                </ul>
                <button type="button" onClick={onStart} className="mt-6 w-full h-10 rounded-full border border-[var(--color-border-subtle,#d4d4d8)] text-[var(--color-surface-dark-panel-alt)] font-medium text-sm inline-flex items-center justify-center gap-2 hover:border-[var(--pulse-primary)] transition" data-testid={`sp-cta-${tier.key}`}>
                  {t('pulse_pricing.sp_cta', 'Talk to us')} <ArrowRight size={14} />
                </button>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── FAQ ── */}
      <section className="py-16" data-testid="pulse-faq">
        <div className="max-w-3xl mx-auto px-6">
          <div className="text-center mb-8">
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--pulse-primary)] font-semibold mb-3">{t('pulse_pricing.faq_eyebrow', 'FAQ')}</div>
            <h2 className="text-2xl sm:text-3xl font-bold tracking-[-0.02em] text-[var(--color-surface-dark-panel-alt)]">{t('pulse_pricing.faq_heading', 'Questions, answered.')}</h2>
          </div>
          <div className="space-y-3">
            {FAQ_KEYS.map((n, i) => {
              const isOpen = open === i;
              return (
                <div key={n} className="rounded-xl border border-[var(--color-border-subtle,#e5e7eb)] bg-white overflow-hidden" data-testid={`faq-item-${i}`}>
                  <button type="button" onClick={() => setOpen(isOpen ? -1 : i)}
                    className="w-full flex items-center justify-between gap-4 px-5 py-4 text-left" data-testid={`faq-toggle-${i}`}>
                    <span className="font-semibold text-[var(--color-surface-dark-panel-alt)] text-sm sm:text-base">{t(`pulse_pricing.faq_q${n}`)}</span>
                    <ChevronDown size={18} className={`text-[var(--pulse-primary)] flex-shrink-0 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                  </button>
                  {isOpen ? <div className="px-5 pb-4 text-sm text-[var(--color-text-slate)] leading-relaxed">{t(`pulse_pricing.faq_a${n}`)}</div> : null}
                </div>
              );
            })}
          </div>
        </div>
      </section>
    </>
  );
}
