/**
 * /admin/design-system — living component gallery for master admins.
 *
 * Purpose: act as the single source of visual truth for the Pulse Fitness design
 * system. Any time a design question surfaces ("which variant is this
 * button?", "what's the sub-tab active colour?", "is this the right spacing?")
 * this page answers it in one glance. Also a guard-rail against drift: when
 * future agents or yourself modify the shadcn Button primitive or the
 * .btn-* / .subtab-* classes in index.css, this page reflects the change
 * instantly so regressions are obvious.
 */
import { useMemo, useState } from 'react';
import { Plus, Save, Download, Trash2, Eye, AlertCircle, CheckCircle2, Copy, Settings, Search, Filter, Calendar, Sparkles, Building2 } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { colors as TOKEN_COLORS, spacing as TOKEN_SPACING, radii as TOKEN_RADII, typography as TOKEN_TYPE, motion as TOKEN_MOTION, cardClass } from '../../theme/tokens';
import { BRANDS } from '../../theme/useBrand';
import PulseDesignTab from './PulseDesignTab';

const Section = ({ title, subtitle, children }) => (
  <section className="mb-10" data-testid={`ds-section-${title.toLowerCase().replace(/\s+/g, '-')}`}>
    <h2 className="text-2xl pulse-font-heading font-semibold tracking-tight mb-1" style={{ color: 'var(--theme-text)' }}>{title}</h2>
    {subtitle && <p className="pulse-font-body text-sm mb-4" style={{ color: 'var(--theme-text-muted)' }}>{subtitle}</p>}
    <div className="rounded-2xl border p-6" style={{ background: 'var(--theme-surface)', borderColor: 'var(--theme-border)' }}>
      {children}
    </div>
  </section>
);

const Label2 = ({ children }) => (
  <div className="text-[10px] font-bold uppercase tracking-[0.2em] mb-2" style={{ color: 'var(--theme-text-muted)' }}>{children}</div>
);

const Row = ({ children }) => (
  <div className="flex flex-wrap items-center gap-3 mb-4">{children}</div>
);

const PALETTE = [
  { name: 'Brand cyan', value: 'var(--color-brand-cyan)', note: 'Primary action fill' },
  { name: 'Brand cyan hover', value: '#4DDBFF', note: 'Hover state' },
  { name: 'Dark text', value: 'var(--color-ink)', note: 'Text on cyan' },
  { name: 'Destructive', value: 'var(--color-danger)', note: 'Delete / danger' },
  { name: 'Success', value: 'var(--color-success)', note: 'Positive state' },
  { name: 'Warning', value: 'var(--color-warning)', note: 'Attention needed' },
];

export default function DesignSystemPage() {
  // Iter 215bh — top-level brand switcher (Pulse Fitness vs Pulse Fitness).
  const [brand, setBrand] = useState('gymaxis');
  const [subTab, setSubTab] = useState('overview');
  const SUBTABS = useMemo(() => [
    { id: 'overview', label: 'Overview' },
    { id: 'tokens', label: 'Tokens' },
    { id: 'buttons', label: 'Buttons' },
    { id: 'cards', label: 'Cards & Motion' },
    { id: 'tabs', label: 'Tabs & Pills' },
    { id: 'inputs', label: 'Inputs' },
    { id: 'brand', label: 'Brand strategy' },
  ], []);

  return (
    <div className="max-w-6xl mx-auto p-6 pulse-font-body" data-testid="design-system-page">
      <header className="mb-6">
        <h1 className="text-3xl sm:text-4xl pulse-font-heading font-semibold tracking-tight mb-1" style={{ color: 'var(--theme-text)' }}>
          Design System
        </h1>
        <p className="text-sm" style={{ color: 'var(--theme-text-muted)' }}>
          Every reusable visual pattern, side-by-side, per brand. If a button / pill / input on any page
          doesn&rsquo;t match a sample here, the page is drifting — please file a polish ticket.
        </p>
      </header>

      {/* Brand switcher */}
      <div className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-white p-1 mb-6" data-testid="ds-brand-switcher">
        {[
          { id: 'gymaxis',  label: 'Pulse Fitness' },
          { id: 'pulse',    label: 'Pulse Fitness' },
        ].map((b) => (
          <button
            key={b.id}
            type="button"
            onClick={() => setBrand(b.id)}
            className={`px-4 py-1.5 rounded-lg text-sm font-bold transition-all ${
              brand === b.id
                ? 'bg-slate-900 text-white shadow-sm'
                : 'text-slate-500 hover:text-slate-900'
            }`}
            data-testid={`ds-brand-tab-${b.id}`}
          >
            {b.label}
          </button>
        ))}
      </div>

      {brand === 'pulse' && <PulseDesignTab />}
      {brand === 'gymaxis' && (
        <>
      {/* Sub-tab pill row — dogfoods the pattern it documents */}
      <div className="subtab-bar mb-8 flex-wrap" role="tablist">
        {SUBTABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setSubTab(t.id)}
            className={`subtab-pill ${subTab === t.id ? 'is-active' : ''}`}
            data-testid={`ds-tab-${t.id}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {subTab === 'tokens' && (
        <>
          <Section title="Design tokens" subtitle={'Single source of truth at /app/frontend/src/theme/tokens.js. Every colour, spacing and radius below is exported from there — never inline a hex literal again.'}>
            <Label2>Brand colours</Label2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
              {Object.entries({ brandCyan: TOKEN_COLORS.brandCyan, brandBlue: TOKEN_COLORS.brandBlue, brandBlueHover: TOKEN_COLORS.brandBlueHover, ink: TOKEN_COLORS.ink }).map(([k, v]) => (
                <div key={k} className="rounded-xl overflow-hidden border" style={{ borderColor: 'var(--theme-border)' }}>
                  <div style={{ background: v, height: 56 }} />
                  <div className="p-3">
                    <div className="text-xs font-mono">{k}</div>
                    <div className="text-[10px] font-mono" style={{ color: 'var(--theme-text-muted)' }}>{v}</div>
                  </div>
                </div>
              ))}
            </div>

            <Label2>Semantic colours</Label2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
              {Object.entries({ success: TOKEN_COLORS.success, warning: TOKEN_COLORS.warning, danger: TOKEN_COLORS.danger, info: TOKEN_COLORS.info }).map(([k, v]) => (
                <div key={k} className="rounded-xl overflow-hidden border" style={{ borderColor: 'var(--theme-border)' }}>
                  <div style={{ background: v, height: 56 }} />
                  <div className="p-3">
                    <div className="text-xs font-mono">{k}</div>
                    <div className="text-[10px] font-mono" style={{ color: 'var(--theme-text-muted)' }}>{v}</div>
                  </div>
                </div>
              ))}
            </div>

            <Label2>Spacing scale (default card padding = lg / 20px)</Label2>
            <div className="space-y-2 mb-6">
              {Object.entries(TOKEN_SPACING).map(([k, v]) => (
                <div key={k} className="flex items-center gap-3">
                  <span className="text-xs font-mono w-8" style={{ color: 'var(--theme-text-muted)' }}>{k}</span>
                  <span className="bg-[var(--color-brand-cyan)]" style={{ width: v, height: 12, borderRadius: 4 }} />
                  <span className="text-xs font-mono" style={{ color: 'var(--theme-text-muted)' }}>{v}</span>
                </div>
              ))}
            </div>

            <Label2>Radii</Label2>
            <div className="flex items-end gap-3 mb-6">
              {Object.entries(TOKEN_RADII).map(([k, v]) => (
                <div key={k} className="text-center">
                  <div className="bg-[var(--color-brand-cyan)]" style={{ width: 56, height: 56, borderRadius: v }} />
                  <div className="text-[10px] font-mono mt-1.5" style={{ color: 'var(--theme-text-muted)' }}>{k}</div>
                  <div className="text-[9px] font-mono" style={{ color: 'var(--theme-text-muted)' }}>{v}</div>
                </div>
              ))}
            </div>

            <Label2>Type hierarchy</Label2>
            <div className="space-y-3">
              <div><div className="text-[10px] font-mono mb-1" style={{ color: 'var(--theme-text-muted)' }}>typography.h1</div><div className={TOKEN_TYPE.h1}>This is a page title.</div></div>
              <div><div className="text-[10px] font-mono mb-1" style={{ color: 'var(--theme-text-muted)' }}>typography.h2</div><div className={TOKEN_TYPE.h2}>This is a section header.</div></div>
              <div><div className="text-[10px] font-mono mb-1" style={{ color: 'var(--theme-text-muted)' }}>typography.h3</div><div className={TOKEN_TYPE.h3}>This is a card title.</div></div>
              <div><div className="text-[10px] font-mono mb-1" style={{ color: 'var(--theme-text-muted)' }}>typography.body</div><div className={TOKEN_TYPE.body}>Body copy explains the thing in 1–2 sentences without showing off.</div></div>
              <div><div className="text-[10px] font-mono mb-1" style={{ color: 'var(--theme-text-muted)' }}>typography.meta</div><div className={TOKEN_TYPE.meta} style={{ color: 'var(--theme-text-muted)' }}>Updated 2 minutes ago · craig@pulsefitness.com</div></div>
            </div>
          </Section>
        </>
      )}

      {subTab === 'cards' && (
        <>
          <Section title="The ONE card pattern" subtitle="rounded-xl + soft border + subtle hover shadow. Drop p-5 inside for default padding. Ten years of experience: never have multiple competing card styles.">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className={`${cardClass()} p-5`}>
                <h3 className={TOKEN_TYPE.h3}>Default tone</h3>
                <p className={`${TOKEN_TYPE.body} mt-2`} style={{ color: 'var(--theme-text-muted)' }}>The everywhere card. Use this 95% of the time.</p>
                <Button size="sm" className="mt-3">Action</Button>
              </div>
              <div className={`${cardClass({ tone: 'subtle' })} p-5`}>
                <h3 className={TOKEN_TYPE.h3}>Subtle tone</h3>
                <p className={`${TOKEN_TYPE.body} mt-2`} style={{ color: 'var(--theme-text-muted)' }}>For secondary or stacked context (e.g. activity feed).</p>
                <Button size="sm" variant="outline" className="mt-3">Action</Button>
              </div>
              <div className={`${cardClass({ tone: 'accent' })} p-5`}>
                <h3 className={TOKEN_TYPE.h3}>Accent tone</h3>
                <p className={`${TOKEN_TYPE.body} mt-2`} style={{ color: 'var(--theme-text-muted)' }}>Highlight cards (upgrade prompts, what's-new).</p>
                <Button size="sm" className="mt-3">Action</Button>
              </div>
            </div>
          </Section>
          <Section title="Motion language" subtitle="Three classes only. Pages should never feel snappy or sluggish — pick one, apply consistently.">
            <div className="space-y-2 text-xs font-mono">
              <div><span className="inline-block w-32" style={{ color: 'var(--theme-text-muted)' }}>motion.fast</span> {TOKEN_MOTION.fast}</div>
              <div><span className="inline-block w-32" style={{ color: 'var(--theme-text-muted)' }}>motion.base</span> {TOKEN_MOTION.base}</div>
              <div><span className="inline-block w-32" style={{ color: 'var(--theme-text-muted)' }}>motion.slow</span> {TOKEN_MOTION.slow}</div>
            </div>
          </Section>
        </>
      )}

      {subTab === 'brand' && (
        <Section title="Brand strategy — Two products, one engine" subtitle="Strategy B (locked Apr 30, 2026): Pulse Fitness is the marketing parent; Pulse Fitness is the operator-facing brand inside the product.">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className={`${cardClass()} p-5`}>
              <div className="flex items-center gap-2 mb-2">
                <Sparkles size={16} style={{ color: BRANDS.GYMAXIS.accent }} />
                <h3 className={TOKEN_TYPE.h3}>Pulse Fitness — Marketing & HQ</h3>
              </div>
              <p className={`${TOKEN_TYPE.body} mb-3`} style={{ color: 'var(--theme-text-muted)' }}>
                Public homepage, login, pricing, features. Master Admin (HQ console) and the MOD service portal also use this brand.
              </p>
              <ul className="text-xs space-y-1 font-mono" style={{ color: 'var(--theme-text-muted)' }}>
                <li>accent: <span style={{ color: BRANDS.GYMAXIS.accent }}>{BRANDS.GYMAXIS.accent}</span></li>
                <li>name: {BRANDS.GYMAXIS.name}</li>
              </ul>
            </div>
            <div className={`${cardClass({ tone: 'accent' })} p-5`}>
              <div className="flex items-center gap-2 mb-2">
                <Building2 size={16} style={{ color: BRANDS.PULSE.accent }} />
                <h3 className={TOKEN_TYPE.h3}>Pulse Fitness — In-app operator</h3>
              </div>
              <p className={`${TOKEN_TYPE.body} mb-3`} style={{ color: 'var(--theme-text-muted)' }}>
                Every authenticated operator surface — Operations, Memberships, Marketing Suite, CRM, Service Desk, Gym Floor.
              </p>
              <ul className="text-xs space-y-1 font-mono" style={{ color: 'var(--theme-text-muted)' }}>
                <li>accent: <span style={{ color: BRANDS.PULSE.accent }}>{BRANDS.PULSE.accent}</span></li>
                <li>name: {BRANDS.PULSE.name}</li>
              </ul>
            </div>
          </div>
          <div className="mt-5 p-4 rounded-lg" style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.25)' }}>
            <div className="flex items-start gap-2">
              <AlertCircle size={16} className="mt-0.5" style={{ color: TOKEN_COLORS.warning }} />
              <div className="text-sm">
                <div className="font-semibold mb-1">Don't mix.</div>
                <div style={{ color: 'var(--theme-text-muted)' }}>
                  Using Pulse Fitness branding inside an authenticated operator portal (or vice-versa) tells customers the platform is unfinished. Resolve via <code className="font-mono text-xs">useBrand(user, surface)</code> in <code className="font-mono text-xs">/theme/useBrand.js</code>.
                </div>
              </div>
            </div>
          </div>
        </Section>
      )}

      {subTab === 'overview' && (
        <>
          <Section title="Colour palette" subtitle="Pulse Fitness brand + semantic tokens used across every module.">
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              {PALETTE.map((c) => (
                <div key={c.value} className="rounded-xl overflow-hidden border" style={{ borderColor: 'var(--theme-border)' }}>
                  <div style={{ background: c.value, height: 72 }} />
                  <div className="p-3">
                    <div className="text-sm font-semibold" style={{ color: 'var(--theme-text)' }}>{c.name}</div>
                    <div className="text-xs font-mono" style={{ color: 'var(--theme-text-muted)' }}>{c.value}</div>
                    <div className="text-xs mt-1" style={{ color: 'var(--theme-text-muted)' }}>{c.note}</div>
                  </div>
                </div>
              ))}
            </div>
          </Section>

          <Section title="Typography" subtitle="Two typefaces carry the whole app.">
            <div className="space-y-4">
              <div>
                <Label2>pulse-font-heading · Nunito</Label2>
                <div className="pulse-font-heading text-4xl font-semibold tracking-tight" style={{ color: 'var(--theme-text)' }}>Pulse Fitness Pro</div>
                <div className="pulse-font-heading text-2xl font-semibold tracking-tight" style={{ color: 'var(--theme-text)' }}>Section heading</div>
              </div>
              <div>
                <Label2>pulse-font-body · Montserrat</Label2>
                <div className="text-base" style={{ color: 'var(--theme-text)' }}>Body copy runs in Montserrat. 16px default, 13px on buttons, 11px for eyebrows.</div>
              </div>
            </div>
          </Section>
        </>
      )}

      {subTab === 'buttons' && (
        <>
          <Section title="Shadcn Button primitive" subtitle="Every <Button> across the app inherits from here. Prefer variant + size over per-call className overrides.">
            <Label2>Variants (size = default)</Label2>
            <Row>
              <Button data-testid="ds-btn-default"><Plus /> Default</Button>
              <Button variant="outline" data-testid="ds-btn-outline"><Save /> Outline</Button>
              <Button variant="secondary" data-testid="ds-btn-secondary"><Download /> Secondary</Button>
              <Button variant="ghost" data-testid="ds-btn-ghost"><Eye /> Ghost</Button>
              <Button variant="destructive" data-testid="ds-btn-destructive"><Trash2 /> Destructive</Button>
              <Button variant="link" data-testid="ds-btn-link">Link</Button>
            </Row>

            <Label2>Sizes (variant = default)</Label2>
            <Row>
              <Button size="sm" data-testid="ds-btn-sm"><Plus /> Small</Button>
              <Button data-testid="ds-btn-md"><Plus /> Default</Button>
              <Button size="lg" data-testid="ds-btn-lg"><Plus /> Large</Button>
              <Button size="icon" aria-label="Icon only" data-testid="ds-btn-icon"><Settings /></Button>
            </Row>

            <Label2>States</Label2>
            <Row>
              <Button data-testid="ds-btn-hover">Hover me</Button>
              <Button disabled data-testid="ds-btn-disabled">Disabled</Button>
            </Row>
          </Section>

          <Section title="Utility button classes" subtitle="For raw <button> tags outside the shadcn primitive. Drop in as className.">
            <Label2>.btn-primary / .btn-secondary / .btn-ghost</Label2>
            <Row>
              <button type="button" className="btn-primary" data-testid="ds-util-primary"><Plus size={14} /> Primary</button>
              <button type="button" className="btn-secondary" data-testid="ds-util-secondary"><Save size={14} /> Secondary</button>
              <button type="button" className="btn-ghost" data-testid="ds-util-ghost"><Eye size={14} /> Ghost</button>
              <button type="button" className="btn-icon" aria-label="Bell" data-testid="ds-util-icon"><Settings size={14} /></button>
            </Row>

            <Label2>Sized variants</Label2>
            <Row>
              <button type="button" className="btn-primary btn-sm" data-testid="ds-util-primary-sm">Small</button>
              <button type="button" className="btn-primary" data-testid="ds-util-primary-md">Default</button>
              <button type="button" className="btn-primary" disabled data-testid="ds-util-primary-disabled">Disabled</button>
            </Row>
          </Section>
        </>
      )}

      {subTab === 'tabs' && (
        <Section title="Sub-tab pills" subtitle="Use .subtab-bar + .subtab-pill for in-page view toggles (Reactive ↔ PPM, Kanban ↔ List, etc.)">
          <Label2>Example — Reactive / Planned Maintenance</Label2>
          <div className="subtab-bar mb-6">
            <button type="button" className="subtab-pill is-active"><AlertCircle size={12} /> Reactive Faults</button>
            <button type="button" className="subtab-pill"><Calendar size={12} /> Planned Maintenance</button>
          </div>

          <Label2>Example — Performance / Cover board</Label2>
          <div className="subtab-bar mb-6">
            <button type="button" className="subtab-pill is-active"><CheckCircle2 size={12} /> Performance</button>
            <button type="button" className="subtab-pill"><AlertCircle size={12} /> Cover board</button>
          </div>

          <Label2>Example — 4-way</Label2>
          <div className="subtab-bar">
            <button type="button" className="subtab-pill is-active">Overview</button>
            <button type="button" className="subtab-pill">Organisations</button>
            <button type="button" className="subtab-pill">AI Usage</button>
            <button type="button" className="subtab-pill">Activity Log</button>
          </div>
        </Section>
      )}

      {subTab === 'inputs' && (
        <Section title="Form inputs" subtitle="All inputs use the same height (h-9), radius (rounded-md), and border colour tokens.">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-2xl">
            <div>
              <Label className="text-xs">Text input</Label>
              <Input placeholder="Search members…" data-testid="ds-input-text" />
            </div>
            <div>
              <Label className="text-xs">Disabled</Label>
              <Input placeholder="Not editable" disabled data-testid="ds-input-disabled" />
            </div>
            <div className="md:col-span-2">
              <Label className="text-xs">Search field (in-place)</Label>
              <div className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--theme-text-muted)' }} />
                <input
                  placeholder="Search contacts / companies / deals…"
                  className="w-full h-9 pl-9 pr-3 text-sm rounded-md"
                  style={{ background: 'var(--theme-bg)', border: '1px solid var(--theme-border)', color: 'var(--theme-text)' }}
                  data-testid="ds-input-search"
                />
              </div>
            </div>
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <button type="button" className="btn-secondary" data-testid="ds-input-filter"><Filter size={14} /> Filter</button>
            <button type="button" className="btn-secondary" data-testid="ds-input-copy"><Copy size={14} /> Copy link</button>
          </div>
        </Section>
      )}
        </>
      )}
    </div>
  );
}
