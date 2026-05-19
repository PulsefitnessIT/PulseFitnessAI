/**
 * Pulse Fitness — Design System reference tab.
 *
 * Mirrors the GymAxis design system gallery but in the Pulse brand:
 * cyan accent, dark-on-light type, rounded shadcn cards. Lives inside
 * /admin/design-system as a brand toggle alongside the GymAxis content.
 */
import { Sparkles, ArrowRight, CheckCircle2 } from 'lucide-react';

const PALETTE = [
  { name: 'Brand cyan',          value: '#19CDFF', token: '--color-brand-cyan',           note: 'Primary CTA + accent' },
  { name: 'Brand cyan deep',     value: '#0BB0DD', token: '--color-brand-cyan-deep',      note: 'Cyan gradient end' },
  { name: 'Ink (heading)',       value: '#0B1220', token: '--color-surface-dark-panel-alt', note: 'Headings on light' },
  { name: 'Slate (body)',        value: '#475569', token: '--color-text-slate',           note: 'Body copy' },
  { name: 'Surface white',       value: '#FFFFFF', token: '--color-white',                note: 'Cards' },
  { name: 'Subtle slate',        value: '#F1F5F9', token: '--color-slate-50',             note: 'Section bands' },
  { name: 'Ink dark',            value: '#0F172A', token: '--color-neutral-900',          note: 'Dark CTAs / final hero' },
  { name: 'Success',             value: '#10B981', token: '--color-success',              note: 'Positive state' },
];

const TYPE_SAMPLES = [
  { name: 'H1 / Display',  className: 'text-4xl sm:text-5xl font-extrabold tracking-tight', sample: 'Manage your gym.' },
  { name: 'H2 / Section',  className: 'text-2xl sm:text-3xl font-bold tracking-tight',      sample: 'Two tiers, one portal.' },
  { name: 'Eyebrow',       className: 'text-xs uppercase tracking-[0.18em] font-bold',      sample: 'Pulse Fitness Self-Service Portal' },
  { name: 'Body',          className: 'text-base leading-relaxed',                          sample: 'Log faults in seconds. Track every piece of kit. Get AI-assisted diagnostics before the engineer arrives.' },
  { name: 'Caption',       className: 'text-xs',                                            sample: 'Powered by GymAxis AI · last updated today' },
];

function Swatch({ p }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden" data-testid={`pulse-ds-swatch-${p.token}`}>
      <div className="h-20" style={{ background: p.value }} />
      <div className="p-3">
        <p className="text-sm font-semibold text-slate-900">{p.name}</p>
        <p className="text-[11px] font-mono text-slate-500 mt-0.5">{p.token}</p>
        <p className="text-[11px] font-mono text-slate-400">{p.value}</p>
        <p className="text-[11px] text-slate-500 mt-1">{p.note}</p>
      </div>
    </div>
  );
}

export default function PulseDesignTab() {
  return (
    <div data-testid="pulse-design-tab" data-brand="pulse" className="space-y-10">
      <header>
        <p className="text-xs uppercase tracking-[0.18em] font-bold text-[#19CDFF] mb-2">Pulse Fitness</p>
        <h2 className="text-3xl font-bold tracking-tight text-slate-900">Pulse Fitness Brand System</h2>
        <p className="mt-2 text-sm text-slate-500 max-w-2xl">
          Reference for the Pulse-branded surfaces (`/pulse`, `/pulse-pricing`, Lite portal).
          Don&rsquo;t reuse these tokens on GymAxis-branded surfaces — Pulse keeps its own
          cyan-on-white identity and Proxima Nova typography.
        </p>
      </header>

      {/* Palette */}
      <section data-testid="pulse-ds-palette">
        <h3 className="text-base font-semibold text-slate-900 mb-3">Palette</h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {PALETTE.map((p) => <Swatch key={p.token} p={p} />)}
        </div>
      </section>

      {/* Typography */}
      <section data-testid="pulse-ds-typography">
        <h3 className="text-base font-semibold text-slate-900 mb-3">Typography</h3>
        <div className="rounded-2xl border border-slate-200 bg-white p-6 space-y-5">
          <p className="text-[11px] font-mono text-slate-400">Family · Proxima Nova → fallback to system sans-serif</p>
          {TYPE_SAMPLES.map((t) => (
            <div key={t.name}>
              <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400 mb-1">{t.name}</p>
              <p className={`${t.className} text-slate-900`}>{t.sample}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Buttons */}
      <section data-testid="pulse-ds-buttons">
        <h3 className="text-base font-semibold text-slate-900 mb-3">Buttons</h3>
        <div className="rounded-2xl border border-slate-200 bg-white p-6 flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-xl px-5 py-2.5 text-sm font-bold text-[#0F172A]"
            style={{ background: 'linear-gradient(135deg, #19CDFF 0%, #0BB0DD 100%)', boxShadow: '0 0 24px rgba(25,205,255,0.35)' }}
            data-testid="pulse-ds-btn-primary"
          >
            <Sparkles size={14} /> Primary cyan
          </button>
          <button type="button" className="inline-flex items-center gap-1.5 rounded-xl px-5 py-2.5 text-sm font-bold bg-slate-900 text-white hover:bg-slate-800" data-testid="pulse-ds-btn-dark">
            Dark / nav <ArrowRight size={14} />
          </button>
          <button type="button" className="inline-flex items-center gap-1.5 rounded-xl px-5 py-2.5 text-sm font-bold bg-white text-slate-900 border-2 border-slate-200 hover:border-[#19CDFF]" data-testid="pulse-ds-btn-secondary">
            Secondary outline
          </button>
          <button type="button" className="inline-flex items-center gap-1.5 rounded-xl px-5 py-2.5 text-sm font-bold text-slate-500 hover:text-slate-900" data-testid="pulse-ds-btn-ghost">
            Ghost link
          </button>
        </div>
      </section>

      {/* Card sample */}
      <section data-testid="pulse-ds-cards">
        <h3 className="text-base font-semibold text-slate-900 mb-3">Plan card pattern</h3>
        <div className="rounded-2xl border border-slate-200 bg-white p-6">
          <div
            className="rounded-2xl bg-gradient-to-b from-[rgba(25,205,255,0.08)] via-white to-white border-2 border-[rgba(25,205,255,0.4)] p-6 max-w-md"
            style={{ boxShadow: '0 20px 60px rgba(25,205,255,0.15)' }}
          >
            <div className="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.18em] text-[#19CDFF] mb-3">
              <Sparkles size={11} /> AI-Powered
            </div>
            <h4 className="text-2xl font-extrabold tracking-tight text-slate-900">Pro</h4>
            <p className="mt-1 text-sm text-slate-500">The full Pulse Fitness operating suite — AI triage, automated check sheets, KPI tracking.</p>
            <div className="mt-5 flex items-baseline gap-2">
              <span className="text-3xl font-extrabold tracking-tight text-slate-900">Talk to us</span>
              <span className="text-sm text-slate-500">· tailored to your estate</span>
            </div>
            <ul className="mt-5 space-y-1.5 text-sm text-slate-700">
              <li className="flex items-start gap-2"><CheckCircle2 size={14} className="text-emerald-500 mt-0.5 shrink-0" /> AI fault diagnosis</li>
              <li className="flex items-start gap-2"><CheckCircle2 size={14} className="text-[#19CDFF] mt-0.5 shrink-0" /> Operational reports + KPI engine</li>
              <li className="flex items-start gap-2"><CheckCircle2 size={14} className="text-[#19CDFF] mt-0.5 shrink-0" /> Risk assessments with auto-scoring</li>
            </ul>
          </div>
        </div>
      </section>

      {/* Usage rules */}
      <section data-testid="pulse-ds-rules">
        <h3 className="text-base font-semibold text-slate-900 mb-3">Usage rules</h3>
        <div className="rounded-2xl border border-amber-200 bg-amber-50/60 p-5 text-sm text-amber-900 leading-relaxed">
          <p className="font-bold mb-2">Pulse stays Pulse.</p>
          <ul className="space-y-1 list-disc pl-5">
            <li>Never apply <code className="font-mono text-xs">.theme-gymaxis</code> to Pulse-branded routes (the global brand-attr sync does this for you).</li>
            <li>The Pulse landing page injects scoped CSS via <code className="font-mono text-xs">PULSE_LANDING_CSS</code>; reuse it for any new Pulse marketing page.</li>
            <li>No GymAxis purple gradients on Pulse surfaces. The Pulse identity is white + cyan + ink.</li>
            <li>Logo: rounded badge, never on dark cyan backgrounds at &gt;60% opacity.</li>
          </ul>
        </div>
      </section>
    </div>
  );
}
