/**
 * Richer marketing sections for /pulse-pricing: an ROI/savings calculator,
 * service-provider tiers (Service Desk / Engineer App), and an FAQ accordion.
 * On-brand (Pulse cyan). Illustrative figures only.
 */
import { useState } from 'react';
import { motion } from 'framer-motion';
import { ChevronDown, Headset, Wrench, ArrowRight, TrendingDown } from 'lucide-react';

const money = (n) => '£' + Math.round(n).toLocaleString();

function RoiSlider({ label, value, set, min, max, step, prefix }) {
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
        data-testid={`roi-${label.toLowerCase().replace(/[^a-z]+/g, '-')}`}
      />
    </div>
  );
}

const FAQS = [
  { q: 'Can I buy just one module?', a: 'Yes. Every module — Operations, CRM, Marketing and Memberships — is a standalone subscription. Start with one and add more whenever you need them.' },
  { q: 'What’s the difference between Lite, Managed and the modules?', a: 'Lite is the free equipment portal included with every Pulse Fitness service agreement. Managed adds AI diagnostics and reporting handled by your account manager. The modules are the full self-serve software platform for running your gym.' },
  { q: 'Do you charge in my currency?', a: 'Yes — pricing is shown and billed in GBP, EUR or USD. We auto-detect your region and you can switch currency at any time.' },
  { q: 'Is there a free trial?', a: 'Every module comes with a 14-day free trial. No card is required to start, and you can cancel anytime.' },
  { q: 'Can I switch between monthly and annual billing?', a: 'Absolutely. Annual billing saves you roughly 17% versus monthly, and you can change your billing cycle whenever suits you.' },
  { q: 'What happens to my data if I cancel?', a: 'Your data stays yours. Export it any time, and nothing is deleted the moment you cancel — you keep read access during your notice period.' },
];

export default function PulsePricingExtras({ onStart }) {
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
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--pulse-primary)] font-semibold mb-3">Your return</div>
            <h2 className="text-2xl sm:text-4xl font-bold tracking-[-0.02em] text-[var(--color-surface-dark-panel-alt)]">See what Pulse pays back.</h2>
            <p className="mt-3 text-sm sm:text-base text-[var(--color-text-slate)]">AI triage resolves a large share of faults before an engineer is dispatched. Estimate your saving.</p>
          </div>
          <div className="grid gap-6 lg:grid-cols-2 items-stretch">
            <div className="rounded-2xl border border-[var(--color-border-subtle,#e5e7eb)] bg-white p-7 space-y-6">
              <RoiSlider label="Machines in estate" value={machines} set={setMachines} min={10} max={500} step={5} />
              <RoiSlider label="Avg engineer callout" value={callout} set={setCallout} min={40} max={400} step={10} prefix="£" />
              <RoiSlider label="Callouts per month" value={perMonth} set={setPerMonth} min={1} max={60} step={1} />
            </div>
            <div className="rounded-2xl bg-[var(--color-surface-dark-panel-alt,#0f172a)] text-white p-7 flex flex-col justify-center">
              <div className="inline-flex items-center gap-2 text-[var(--pulse-primary)] text-sm font-semibold">
                <TrendingDown size={16} /> Estimated saving
              </div>
              <div className="mt-3 text-5xl font-extrabold tracking-tight" data-testid="roi-annual-saving">{money(annualSaved)}<span className="text-lg font-semibold text-white/60">/yr</span></div>
              <div className="mt-1 text-sm text-white/70">≈ {money(monthlySaved)} every month in avoided callouts</div>
              <p className="mt-4 text-xs text-white/50">Illustrative — assumes AI triage resolves ~40% of callouts remotely plus proactive monitoring across your estate. Your results will vary.</p>
              <button type="button" onClick={onStart} className="mt-6 h-11 rounded-full bg-[var(--pulse-primary)] text-[#0A0C10] font-semibold text-sm inline-flex items-center justify-center gap-2 hover:brightness-95 transition" data-testid="roi-cta">
                Start your free trial <ArrowRight size={15} />
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* ── Service provider tiers ── */}
      <section className="py-12" data-testid="pulse-service-provider">
        <div className="max-w-5xl mx-auto px-6">
          <div className="text-center max-w-2xl mx-auto mb-8">
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--pulse-primary)] font-semibold mb-3">For service providers</div>
            <h2 className="text-2xl sm:text-3xl font-bold tracking-[-0.02em] text-[var(--color-surface-dark-panel-alt)]">Run service & field teams on Pulse.</h2>
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            {[
              { icon: Headset, name: 'Service Desk', blurb: 'Multi-client fault triage, SLAs, CSAT surveys and a branded customer portal — everything your desk needs in one queue.', features: ['Unlimited cases & SLA tracking', 'AI triage & knowledge base', 'Customer portal + CSAT'] },
              { icon: Wrench, name: 'Engineer App', blurb: 'A mobile-first app for field engineers: job packs, on-site sign-off, parts and photo evidence — online or off.', features: ['Offline job packs & sign-off', 'Parts, BOM & photo evidence', 'Live scheduling & routing'] },
            ].map((t) => (
              <motion.div key={t.name} initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.5 }}
                className="rounded-2xl border border-[var(--color-border-subtle,#e5e7eb)] bg-white p-7" data-testid={`sp-card-${t.name.toLowerCase().replace(/\s+/g, '-')}`}>
                <div className="w-11 h-11 rounded-xl bg-[color-mix(in_srgb,var(--pulse-primary)_18%,white)] flex items-center justify-center">
                  <t.icon size={20} className="text-[var(--pulse-primary)]" />
                </div>
                <div className="mt-4 font-bold text-lg text-[var(--color-surface-dark-panel-alt)]">{t.name}</div>
                <p className="text-sm text-[var(--color-text-slate)] mt-2 leading-relaxed">{t.blurb}</p>
                <ul className="mt-4 space-y-2">
                  {t.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-sm text-[var(--color-surface-dark-panel-alt)]">
                      <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-[var(--pulse-primary)] flex-shrink-0" />{f}
                    </li>
                  ))}
                </ul>
                <button type="button" onClick={onStart} className="mt-6 w-full h-10 rounded-full border border-[var(--color-border-subtle,#d4d4d8)] text-[var(--color-surface-dark-panel-alt)] font-medium text-sm inline-flex items-center justify-center gap-2 hover:border-[var(--pulse-primary)] transition" data-testid={`sp-cta-${t.name.toLowerCase().replace(/\s+/g, '-')}`}>
                  Talk to us <ArrowRight size={14} />
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
            <div className="text-xs uppercase tracking-[0.18em] text-[var(--pulse-primary)] font-semibold mb-3">FAQ</div>
            <h2 className="text-2xl sm:text-3xl font-bold tracking-[-0.02em] text-[var(--color-surface-dark-panel-alt)]">Questions, answered.</h2>
          </div>
          <div className="space-y-3">
            {FAQS.map((f, i) => {
              const isOpen = open === i;
              return (
                <div key={i} className="rounded-xl border border-[var(--color-border-subtle,#e5e7eb)] bg-white overflow-hidden" data-testid={`faq-item-${i}`}>
                  <button type="button" onClick={() => setOpen(isOpen ? -1 : i)}
                    className="w-full flex items-center justify-between gap-4 px-5 py-4 text-left" data-testid={`faq-toggle-${i}`}>
                    <span className="font-semibold text-[var(--color-surface-dark-panel-alt)] text-sm sm:text-base">{f.q}</span>
                    <ChevronDown size={18} className={`text-[var(--pulse-primary)] flex-shrink-0 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                  </button>
                  {isOpen ? <div className="px-5 pb-4 text-sm text-[var(--color-text-slate)] leading-relaxed">{f.a}</div> : null}
                </div>
              );
            })}
          </div>
        </div>
      </section>
    </>
  );
}
