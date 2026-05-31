/**
 * Iter 220e3 — Create Contract Wizard (Phase B).
 *
 * 10-step modal flow that replaces the legacy 1-screen "New Contract"
 * modal in CRM → Contracts.
 *
 *   1. Customer & site
 *   2. Assets covered
 *   3. Cover type (template select)
 *   4. Inclusions
 *   5. Exclusions
 *   6. Consumables
 *   7. Response times
 *   8. Pricing builder
 *   9. Terms & conditions
 *  10. Review + comparison matrix
 *
 * On finish we:
 *   • POST /crm/v2/contracts  (existing endpoint, now schema-extended)
 *   • POST /crm/v2/contracts/{id}/assets  for each covered asset
 *   • POST /crm/v2/contract-templates/{tpl}/apply/{id}  if a template
 *     was picked AND the user didn't tweak inclusions afterwards.
 *
 * All companies / sites / contacts / engineers / equipment come from
 * the existing CRM collections — NOTHING is duplicated.
 */
import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  X, ChevronLeft, ChevronRight, Check, Building2, MapPin,
  Wrench, Shield, ListChecks, Slash, Package, Clock,
  DollarSign, FileText, Eye,
} from 'lucide-react';
import { useContractCatalog, useContractTemplates } from './contractCatalog';
import { ContractMatrix } from './ContractMatrix';

const STEPS = [
  { id: 'customer',     label: 'Customer & Site', icon: Building2 },
  { id: 'assets',       label: 'Assets',          icon: Wrench },
  { id: 'cover',        label: 'Cover Type',      icon: Shield },
  { id: 'inclusions',   label: 'Inclusions',      icon: ListChecks },
  { id: 'exclusions',   label: 'Exclusions',      icon: Slash },
  { id: 'consumables',  label: 'Consumables',     icon: Package },
  { id: 'response',     label: 'Response Times',  icon: Clock },
  { id: 'pricing',      label: 'Pricing',         icon: DollarSign },
  { id: 'terms',        label: 'Terms',           icon: FileText },
  { id: 'review',       label: 'Review & Send',   icon: Eye },
];

function emptyForm() {
  return {
    title: '',
    company_id: '', company_name: '',
    site_id: '', site_name: '',
    contact_id: '', billing_contact_id: '',
    assigned_engineer_id: '',
    start_date: '', end_date: '', renewal_date: '',
    contract_length_months: 12,
    billing_frequency: 'annual',
    selected_asset_ids: [],
    asset_filter: { type: '', manufacturer: '' },
    template_id: '',
    tier: 'silver',
    inclusions: {},
    exclusions_structured: [],
    consumables: [],
    response_times: {},
    pricing: {
      annual_value: 0, monthly_value: 0,
      price_per_asset: 0, setup_fee: 0,
      vat_percent: 20, discount_percent: 0,
      uplift_percent: 0, cost_estimate: 0, margin_percent: 0,
    },
    terms_md: '',
  };
}

function Header({ step, c, isDark, onClose }) {
  const border = isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)';
  return (
    <div className="flex items-center justify-between px-5 py-3"
         style={{ borderBottom: `1px solid ${border}` }}>
      <div>
        <p className="text-[10px] uppercase tracking-wider font-bold"
           style={{ color: c.textDim }}>Step {step + 1} of {STEPS.length}</p>
        <h2 className="text-base font-bold" style={{ color: c.text }}>{STEPS[step].label}</h2>
      </div>
      <button onClick={onClose} aria-label="Close wizard" data-testid="wizard-close-btn"
              className="p-1.5 rounded hover:opacity-70" style={{ color: c.textDim }}>
        <X size={16} />
      </button>
    </div>
  );
}

function Stepper({ step, isDark, c }) {
  return (
    <div className="px-5 py-2 flex gap-1 overflow-x-auto"
         style={{ background: isDark ? 'var(--color-surface-dark-2)' : 'var(--color-neutral-50)' }}>
      {STEPS.map((s, i) => {
        const done = i < step;
        const active = i === step;
        const Icon = s.icon;
        return (
          <div key={s.id} className="flex items-center gap-1.5 px-2 py-1 rounded-md"
               data-testid={`wizard-step-${s.id}`}
               style={{
                 background: active ? 'var(--color-info-ios)' : done ? `${c.text}10` : 'transparent',
                 color: active ? '#fff' : done ? c.text : c.textDim,
                 fontSize: 11, fontWeight: active ? 700 : 500,
               }}>
            <Icon size={11} />
            <span className="whitespace-nowrap">{s.label}</span>
          </div>
        );
      })}
    </div>
  );
}

function StepShell({ children }) {
  return <div className="px-5 py-4 overflow-y-auto" style={{ maxHeight: '60vh' }}>{children}</div>;
}

// ── Step 1 · Customer & Site ──────────────────────────────────
function CustomerStep({ form, setForm, companies, contacts, sites, engineers, inp }) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <Field label="Contract Title *" span={2}>
        <input value={form.title} placeholder="e.g. Pulse Fitness — Annual Maintenance Cover"
               onChange={e => setForm({ ...form, title: e.target.value })} {...inp}
               data-testid="wizard-title-input" />
      </Field>
      <Field label="Customer (CRM Company)">
        <select value={form.company_id} {...inp}
                onChange={e => {
                  const co = companies.find(x => x.id === e.target.value);
                  setForm({ ...form, company_id: e.target.value,
                            company_name: co?.name || '', contact_id: '', site_id: '' });
                }}
                data-testid="wizard-company-select">
          <option value="">Select existing customer…</option>
          {companies.map(co => <option key={co.id} value={co.id}>{co.name}</option>)}
        </select>
      </Field>
      <Field label="Site">
        <select value={form.site_id} {...inp}
                onChange={e => {
                  const s = sites.find(x => x.id === e.target.value);
                  setForm({ ...form, site_id: e.target.value, site_name: s?.name || '' });
                }}
                disabled={!form.company_id}
                data-testid="wizard-site-select">
          <option value="">Any / all sites</option>
          {sites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </Field>
      <Field label="Primary Contact">
        <select value={form.contact_id} {...inp}
                onChange={e => setForm({ ...form, contact_id: e.target.value })}>
          <option value="">Select…</option>
          {contacts.filter(ct => !form.company_id || ct.company_id === form.company_id)
            .map(ct => <option key={ct.id} value={ct.id}>{ct.first_name} {ct.last_name}</option>)}
        </select>
      </Field>
      <Field label="Billing Contact">
        <select value={form.billing_contact_id} {...inp}
                onChange={e => setForm({ ...form, billing_contact_id: e.target.value })}>
          <option value="">Same as primary</option>
          {contacts.filter(ct => !form.company_id || ct.company_id === form.company_id)
            .map(ct => <option key={ct.id} value={ct.id}>{ct.first_name} {ct.last_name}</option>)}
        </select>
      </Field>
      <Field label="Assigned Engineer">
        <select value={form.assigned_engineer_id} {...inp}
                onChange={e => setForm({ ...form, assigned_engineer_id: e.target.value })}>
          <option value="">Unassigned</option>
          {engineers.map(en => <option key={en.id} value={en.id}>{en.full_name || en.name}</option>)}
        </select>
      </Field>
      <Field label="Start Date">
        <input type="date" value={form.start_date} {...inp}
               onChange={e => setForm({ ...form, start_date: e.target.value })} />
      </Field>
      <Field label="End Date">
        <input type="date" value={form.end_date} {...inp}
               onChange={e => setForm({ ...form, end_date: e.target.value })} />
      </Field>
      <Field label="Length (months)">
        <input type="number" value={form.contract_length_months} {...inp}
               onChange={e => setForm({ ...form, contract_length_months: parseInt(e.target.value) || 0 })} />
      </Field>
      <Field label="Payment Frequency">
        <select value={form.billing_frequency} {...inp}
                onChange={e => setForm({ ...form, billing_frequency: e.target.value })}>
          {['monthly', 'quarterly', 'annual', 'one_off'].map(f => <option key={f} value={f}>{f.replace('_', ' ')}</option>)}
        </select>
      </Field>
      <Field label="Renewal Date" span={2}>
        <input type="date" value={form.renewal_date} {...inp}
               onChange={e => setForm({ ...form, renewal_date: e.target.value })} />
      </Field>
    </div>
  );
}

// ── Step 2 · Assets covered ──────────────────────────────────
function AssetsStep({ form, setForm, equipment, c }) {
  const filtered = equipment.filter(eq => {
    if (form.asset_filter.type && (eq.type || '').toLowerCase() !== form.asset_filter.type.toLowerCase()) return false;
    if (form.asset_filter.manufacturer && (eq.manufacturer || '').toLowerCase() !== form.asset_filter.manufacturer.toLowerCase()) return false;
    if (form.site_id && eq.site_id && eq.site_id !== form.site_id) return false;
    return true;
  });
  const selected = new Set(form.selected_asset_ids);
  const toggle = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setForm({ ...form, selected_asset_ids: [...next] });
  };
  const selectAll = () => setForm({ ...form, selected_asset_ids: filtered.map(e => e.id) });
  const clear = () => setForm({ ...form, selected_asset_ids: [] });

  const types = [...new Set(equipment.map(e => e.type).filter(Boolean))];
  const manufacturers = [...new Set(equipment.map(e => e.manufacturer).filter(Boolean))];
  return (
    <div>
      <div className="flex gap-2 mb-3 items-center text-xs">
        <select value={form.asset_filter.type} onChange={e => setForm({ ...form, asset_filter: { ...form.asset_filter, type: e.target.value } })}
                className="px-2 py-1 rounded border" style={{ borderColor: c.border, background: 'transparent', color: c.text }}>
          <option value="">All types</option>
          {types.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={form.asset_filter.manufacturer} onChange={e => setForm({ ...form, asset_filter: { ...form.asset_filter, manufacturer: e.target.value } })}
                className="px-2 py-1 rounded border" style={{ borderColor: c.border, background: 'transparent', color: c.text }}>
          <option value="">All manufacturers</option>
          {manufacturers.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
        <button onClick={selectAll} className="ml-auto px-2 py-1 text-[11px] rounded bg-blue-500/10 text-blue-600 font-semibold" data-testid="wizard-select-all-assets">Select all visible</button>
        <button onClick={clear} className="px-2 py-1 text-[11px] rounded bg-rose-500/10 text-rose-600 font-semibold">Clear</button>
        <span className="text-[11px]" style={{ color: c.textDim }}>{form.selected_asset_ids.length} selected</span>
      </div>
      <div className="space-y-1 max-h-[40vh] overflow-y-auto pr-1">
        {filtered.length === 0 && (
          <p className="text-center py-6 text-xs" style={{ color: c.textDim }}>
            No equipment for the picked customer/site yet — assets can be added from CRM → Sites & Equipment.
          </p>
        )}
        {filtered.map(eq => {
          const isSel = selected.has(eq.id);
          return (
            <label key={eq.id} className="flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer"
                   style={{ background: isSel ? 'var(--color-info-ios)10' : 'transparent' }}
                   data-testid={`wizard-asset-${eq.id}`}>
              <input type="checkbox" checked={isSel} onChange={() => toggle(eq.id)} />
              <span className="flex-1 text-xs" style={{ color: c.text }}>
                {eq.name || eq.model_code || 'Asset'}
                {eq.serial_number && <span className="opacity-60"> · SN {eq.serial_number}</span>}
              </span>
              {eq.manufacturer && (
                <span className="text-[10px] px-1.5 py-0.5 rounded"
                      style={{ background: 'var(--color-info-ios)15', color: 'var(--color-info-ios)' }}>
                  {eq.manufacturer}
                </span>
              )}
            </label>
          );
        })}
      </div>
    </div>
  );
}

// ── Step 3 · Cover Type ──────────────────────────────────────
function CoverStep({ form, setForm, templates, catalog, c, isDark }) {
  const apply = (tpl) => {
    setForm({
      ...form,
      template_id: tpl.id,
      tier: tpl.tier_slug,
      inclusions: { ...tpl.inclusions },
      exclusions_structured: [...(tpl.exclusions || [])],
      consumables: (tpl.consumables || []).map(x => ({ ...x })),
      response_times: { ...tpl.response_times },
      pricing: { ...form.pricing, ...(tpl.pricing || {}) },
      terms_md: tpl.terms_md || form.terms_md,
    });
  };
  return (
    <div>
      <p className="text-xs mb-3" style={{ color: c.textDim }}>
        Pick a starting template — you can tweak everything in the next steps. Admins rename templates in
        <strong> CRM → Contracts → Settings → Templates</strong>.
      </p>
      <div className="grid grid-cols-2 gap-2">
        {templates.map(tpl => {
          const active = tpl.id === form.template_id;
          return (
            <button key={tpl.id} onClick={() => apply(tpl)}
                    data-testid={`wizard-template-${tpl.tier_slug}`}
                    className="text-left p-3 rounded-lg border transition-all"
                    style={{
                      borderColor: active ? 'var(--color-info-ios)' : (isDark ? 'var(--color-surface-dark-panel)' : 'var(--color-border-alt)'),
                      background: active ? 'var(--color-info-ios)10' : (isDark ? '#111' : '#fff'),
                    }}>
              <div className="flex items-center gap-2 mb-1">
                <Shield size={14} style={{ color: active ? 'var(--color-info-ios)' : c.text }} />
                <span className="font-bold text-sm" style={{ color: c.text }}>{tpl.name}</span>
                <span className="text-[10px] uppercase px-1.5 py-0.5 rounded ml-auto"
                      style={{ background: `${c.text}10`, color: c.textDim }}>
                  {tpl.tier_slug}
                </span>
              </div>
              {tpl.blurb && <p className="text-[11px]" style={{ color: c.textDim }}>{tpl.blurb}</p>}
              <p className="text-[10px] mt-1.5" style={{ color: c.textDim }}>
                {Object.values(tpl.inclusions || {}).reduce((n, arr) => n + (arr?.length || 0), 0)} inclusions
                {' · '}
                {Object.keys(tpl.response_times || {}).length} response bands
              </p>
            </button>
          );
        })}
      </div>
      <div className="mt-4 p-2 rounded-lg border text-[11px]"
           style={{ borderColor: c.border, color: c.textDim }}>
        Need a one-off shape? Pick <strong>Custom</strong> and configure each step yourself. The catalog has
        {' '}{catalog.inclusion_groups.reduce((n, g) => n + g.items.length, 0)} inclusion items.
      </div>
    </div>
  );
}

// ── Step 4 · Inclusions ──────────────────────────────────────
function InclusionsStep({ form, setForm, catalog, c, isDark }) {
  const toggle = (groupKey, itemKey) => {
    const current = new Set(form.inclusions?.[groupKey] || []);
    if (current.has(itemKey)) current.delete(itemKey); else current.add(itemKey);
    setForm({ ...form, inclusions: { ...form.inclusions, [groupKey]: [...current] } });
  };
  return (
    <div className="space-y-3">
      {catalog.inclusion_groups.map(group => (
        <details key={group.key} open data-testid={`wizard-inc-group-${group.key}`}>
          <summary className="text-xs font-bold uppercase tracking-wider mb-2 cursor-pointer"
                   style={{ color: c.text }}>
            {group.label}
          </summary>
          <div className="grid grid-cols-2 gap-1.5 pl-3">
            {group.items.map(item => {
              const checked = (form.inclusions?.[group.key] || []).includes(item.key);
              return (
                <label key={item.key} className="flex items-center gap-2 text-xs cursor-pointer px-2 py-1 rounded"
                       data-testid={`wizard-inc-${item.key}`}
                       style={{ background: checked ? 'var(--color-success-alt)15' : 'transparent', color: c.text }}>
                  <input type="checkbox" checked={checked} onChange={() => toggle(group.key, item.key)} />
                  {item.label}
                </label>
              );
            })}
          </div>
        </details>
      ))}
    </div>
  );
}

// ── Step 5 · Exclusions ──────────────────────────────────────
function ExclusionsStep({ form, setForm, catalog, c }) {
  const toggle = (key) => {
    const set = new Set(form.exclusions_structured || []);
    if (set.has(key)) set.delete(key); else set.add(key);
    setForm({ ...form, exclusions_structured: [...set] });
  };
  return (
    <div className="grid grid-cols-2 gap-1.5">
      {catalog.exclusion_items.map(item => {
        const checked = (form.exclusions_structured || []).includes(item.key);
        return (
          <label key={item.key} className="flex items-center gap-2 text-xs cursor-pointer px-2 py-1 rounded"
                 data-testid={`wizard-exc-${item.key}`}
                 style={{ background: checked ? 'var(--color-danger)15' : 'transparent', color: c.text }}>
            <input type="checkbox" checked={checked} onChange={() => toggle(item.key)} />
            {item.label}
          </label>
        );
      })}
    </div>
  );
}

// ── Step 6 · Consumables ─────────────────────────────────────
function ConsumablesStep({ form, setForm, catalog, c, inp }) {
  const items = form.consumables?.length ? form.consumables : catalog.consumable_presets.map(p => ({
    name: p.name, included: p.included_default, charge: p.default_charge,
  }));
  const update = (idx, patch) => {
    const next = items.map((it, i) => i === idx ? { ...it, ...patch } : it);
    setForm({ ...form, consumables: next });
  };
  const remove = (idx) => {
    setForm({ ...form, consumables: items.filter((_, i) => i !== idx) });
  };
  const addRow = () => setForm({ ...form, consumables: [...items, { name: '', included: false, charge: 0 }] });
  return (
    <div className="space-y-1">
      {items.map((it, i) => (
        <div key={i} className="flex items-center gap-2" data-testid={`wizard-consumable-${i}`}>
          <input value={it.name} placeholder="Item name"
                 onChange={e => update(i, { name: e.target.value })}
                 className="flex-1 px-2 py-1 rounded text-xs" {...inp} />
          <label className="flex items-center gap-1 text-xs" style={{ color: c.text }}>
            <input type="checkbox" checked={it.included} onChange={e => update(i, { included: e.target.checked })} />
            Included
          </label>
          <input type="number" value={it.charge} placeholder="0"
                 onChange={e => update(i, { charge: parseFloat(e.target.value) || 0 })}
                 className="w-20 px-2 py-1 rounded text-xs" {...inp} />
          <button onClick={() => remove(i)} className="text-[11px] text-rose-500">✕</button>
        </div>
      ))}
      <button onClick={addRow} className="mt-2 text-xs text-blue-600 font-semibold" data-testid="wizard-add-consumable">
        + Add consumable
      </button>
    </div>
  );
}

// ── Step 7 · Response Times ──────────────────────────────────
function ResponseStep({ form, setForm, catalog, c, inp }) {
  const update = (key, hours) => {
    setForm({ ...form, response_times: { ...form.response_times, [key]: { hours: parseInt(hours) || 0, unit: 'hours' } } });
  };
  return (
    <div className="grid grid-cols-2 gap-3">
      {catalog.response_time_bands.map(band => (
        <div key={band.key} data-testid={`wizard-rt-${band.key}`}>
          <label className="text-[10px] uppercase tracking-wider font-medium block mb-1" style={{ color: c.textDim }}>
            {band.label}
          </label>
          <div className="flex items-center gap-2">
            <input type="number"
                   value={form.response_times?.[band.key]?.hours ?? band.default_hours}
                   onChange={e => update(band.key, e.target.value)} {...inp}
                   className="w-full px-2 py-1.5 rounded text-xs" />
            <span className="text-[10px]" style={{ color: c.textDim }}>hours</span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Step 8 · Pricing ─────────────────────────────────────────
function PricingStep({ form, setForm, c, inp }) {
  const p = form.pricing;
  const set = (k, v) => setForm({ ...form, pricing: { ...p, [k]: parseFloat(v) || 0 } });
  const annual = p.annual_value || 0;
  const numAssets = form.selected_asset_ids?.length || 0;
  const computedTotal = annual + (p.price_per_asset || 0) * numAssets + (p.setup_fee || 0);
  const afterDiscount = computedTotal * (1 - (p.discount_percent || 0) / 100);
  const afterUplift = afterDiscount * (1 + (p.uplift_percent || 0) / 100);
  const vat = afterUplift * ((p.vat_percent || 0) / 100);
  const grossTotal = afterUplift + vat;
  const cost = p.cost_estimate || 0;
  const margin = afterUplift > 0 ? Math.round(((afterUplift - cost) / afterUplift) * 100) : 0;
  // Surface margin back into pricing so backend stores it.
  useEffect(() => {
    if (margin !== (p.margin_percent || 0)) {
      setForm(prev => ({ ...prev, pricing: { ...prev.pricing, margin_percent: margin, monthly_value: Math.round(afterUplift / 12) } }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [margin]);
  return (
    <div className="grid grid-cols-2 gap-3">
      <Field label="Annual price (£)">
        <input type="number" value={p.annual_value} onChange={e => set('annual_value', e.target.value)} {...inp} data-testid="wizard-pricing-annual" />
      </Field>
      <Field label="Price per asset (£)">
        <input type="number" value={p.price_per_asset} onChange={e => set('price_per_asset', e.target.value)} {...inp} />
      </Field>
      <Field label="Setup fee (£)">
        <input type="number" value={p.setup_fee} onChange={e => set('setup_fee', e.target.value)} {...inp} />
      </Field>
      <Field label="VAT %">
        <input type="number" value={p.vat_percent} onChange={e => set('vat_percent', e.target.value)} {...inp} />
      </Field>
      <Field label="Discount %">
        <input type="number" value={p.discount_percent} onChange={e => set('discount_percent', e.target.value)} {...inp} />
      </Field>
      <Field label="Uplift %">
        <input type="number" value={p.uplift_percent} onChange={e => set('uplift_percent', e.target.value)} {...inp} />
      </Field>
      <Field label="Cost estimate (internal £)" span={2}>
        <input type="number" value={p.cost_estimate} onChange={e => set('cost_estimate', e.target.value)} {...inp} placeholder="Used for margin only — never on the PDF" />
      </Field>
      <div className="col-span-2 grid grid-cols-3 gap-2 mt-1">
        <Summary label="Net" value={`£${Math.round(afterUplift).toLocaleString()}`} c={c} />
        <Summary label="Gross (inc VAT)" value={`£${Math.round(grossTotal).toLocaleString()}`} c={c} testId="wizard-pricing-gross" />
        <Summary label="Margin" value={`${margin}%`} c={c} accent={margin >= 35 ? 'var(--color-success-alt)' : margin >= 20 ? 'var(--color-accent-amber)' : 'var(--color-danger)'} testId="wizard-pricing-margin" />
      </div>
    </div>
  );
}

function Summary({ label, value, c, accent, testId }) {
  return (
    <div className="p-2 rounded border text-center" data-testid={testId}
         style={{ borderColor: c.border, background: 'transparent' }}>
      <p className="text-[9px] uppercase tracking-wider" style={{ color: c.textDim }}>{label}</p>
      <p className="text-base font-bold mt-0.5" style={{ color: accent || c.text }}>{value}</p>
    </div>
  );
}
Summary.displayName = 'PricingSummary';

// ── Step 9 · Terms ───────────────────────────────────────────
function TermsStep({ form, setForm, catalog, c, inp }) {
  const auto = useMemo(() => {
    const incBlocks = catalog.inclusion_groups.map(g => {
      const keys = form.inclusions?.[g.key] || [];
      if (!keys.length) return '';
      const items = g.items.filter(it => keys.includes(it.key)).map(it => `- ${it.label}`).join('\n');
      return `### ${g.label}\n${items}\n`;
    }).filter(Boolean).join('\n');
    const excBlock = (form.exclusions_structured || []).length
      ? '### Exclusions\n' + form.exclusions_structured.map(k =>
          `- ${catalog.exclusion_items.find(e => e.key === k)?.label || k}`).join('\n') + '\n'
      : '';
    return `${incBlocks}\n${excBlock}`.trim();
  }, [form.inclusions, form.exclusions_structured, catalog]);
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <p className="text-[10px] uppercase tracking-wider font-medium" style={{ color: c.textDim }}>
          Auto-generated from cover selections — edit freely
        </p>
        <button className="text-[11px] text-blue-600 font-semibold"
                onClick={() => setForm({ ...form, terms_md: auto })}
                data-testid="wizard-regenerate-terms">
          Regenerate from cover
        </button>
      </div>
      <textarea value={form.terms_md || auto}
                onChange={e => setForm({ ...form, terms_md: e.target.value })}
                rows={14} {...inp}
                className="w-full px-3 py-2 text-xs rounded font-mono"
                data-testid="wizard-terms-textarea" />
    </div>
  );
}

// ── Step 10 · Review ─────────────────────────────────────────
function ReviewStep({ form, templates, catalog, c, isDark }) {
  const tpl = templates.find(t => t.id === form.template_id);
  const draftColumn = {
    id: 'draft', name: form.title || 'New contract', tier_slug: form.tier,
    inclusions: form.inclusions, response_times: form.response_times,
    exclusions: form.exclusions_structured,
  };
  const compare = tpl
    ? [{ ...tpl, id: tpl.id, name: `${tpl.name} (template)` }, draftColumn]
    : [draftColumn];
  return (
    <div className="space-y-3">
      <div className="p-3 rounded-lg border text-xs" style={{ borderColor: c.border, background: isDark ? '#111' : '#fff' }} data-testid="wizard-review-summary">
        <p style={{ color: c.text }}><strong>{form.title || '(untitled contract)'}</strong></p>
        <p style={{ color: c.textDim }}>
          {form.company_name || 'No customer'} · {form.selected_asset_ids?.length || 0} assets ·{' '}
          {form.tier} cover ·{' '}
          £{Math.round((form.pricing?.monthly_value || (form.pricing?.annual_value || 0) / 12)).toLocaleString()}/mo
        </p>
      </div>
      <ContractMatrix catalog={catalog} columns={compare} isDark={isDark} c={c} />
    </div>
  );
}

// ── Reusable bits ───────────────────────────────────────────
function Field({ label, children, span }) {
  return (
    <div className={span === 2 ? 'col-span-2' : ''}>
      <label className="text-[10px] uppercase tracking-wider font-medium block mb-1 opacity-70">{label}</label>
      {children}
    </div>
  );
}

// ── Main wizard ─────────────────────────────────────────────
export default function ContractWizard({ open, onClose, onCreated, API, headers, c, isDark }) {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState(emptyForm);
  const [companies, setCompanies] = useState([]);
  const [contacts, setContacts] = useState([]);
  const [sites, setSites] = useState([]);
  const [engineers, setEngineers] = useState([]);
  const [equipment, setEquipment] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { catalog } = useContractCatalog(API, headers);
  const { templates } = useContractTemplates(API, headers);

  const inp = useMemo(() => ({
    className: 'w-full px-3 py-2 text-sm rounded-md',
    style: { background: isDark ? 'var(--color-ink-alt)' : '#fff',
             border: `1px solid ${c.border}`, color: c.text },
  }), [isDark, c]);

  // Load CRM data once on open.
  useEffect(() => {
    if (!open) return;
    const headersVal = headers();
    Promise.all([
      axios.get(`${API}/crm/v2/companies?limit=500`, { headers: headersVal }),
      axios.get(`${API}/crm/v2/contacts?limit=500`, { headers: headersVal }),
    ]).then(([co, ct]) => {
      setCompanies(co.data.companies || []);
      setContacts(ct.data.contacts || []);
    }).catch(() => {});
  }, [open, API, headers]);

  // When a company is picked, fetch its sites + equipment.
  useEffect(() => {
    if (!form.company_id) { setSites([]); setEquipment([]); setEngineers([]); return; }
    axios.get(`${API}/crm/v2/companies/${form.company_id}/sites-and-equipment`, { headers: headers() })
      .then(res => {
        const flatSites = (res.data.sites || []).map(s => ({ id: s.id, name: s.name }));
        const flatEq = (res.data.sites || []).flatMap(s => (s.equipment || []).map(e => ({ ...e, site_id: s.id, site_name: s.name })));
        setSites(flatSites);
        setEquipment(flatEq);
      }).catch(() => { setSites([]); setEquipment([]); });
    axios.get(`${API}/svc/engineers?limit=200`, { headers: headers() })
      .then(res => setEngineers(res.data.engineers || res.data || []))
      .catch(() => setEngineers([]));
  }, [form.company_id, API, headers]);

  if (!open) return null;

  const canNext = () => {
    if (step === 0) return !!form.title.trim();
    return true;
  };

  const next = () => setStep(s => Math.min(s + 1, STEPS.length - 1));
  const back = () => setStep(s => Math.max(s - 1, 0));

  const finalise = async ({ asDraft }) => {
    setSaving(true);
    setError(null);
    try {
      const payload = {
        title: form.title,
        type: 'service',
        tier: form.tier,
        company_id: form.company_id, company_name: form.company_name,
        contact_id: form.contact_id,
        billing_contact_id: form.billing_contact_id,
        assigned_engineer_id: form.assigned_engineer_id,
        site_id: form.site_id,
        start_date: form.start_date,
        end_date: form.end_date,
        renewal_date: form.renewal_date,
        contract_length_months: form.contract_length_months,
        annual_value: form.pricing.annual_value,
        total_value: form.pricing.annual_value,
        billing_frequency: form.billing_frequency,
        template_id: form.template_id,
        inclusions: form.inclusions,
        exclusions_structured: form.exclusions_structured,
        consumables: form.consumables,
        response_times: form.response_times,
        pricing: form.pricing,
        terms_md: form.terms_md,
      };
      const created = await axios.post(`${API}/crm/v2/contracts`, payload, { headers: headers() });
      const id = created.data.id;
      // Attach assets.
      await Promise.all((form.selected_asset_ids || []).map(asset_id => {
        const eq = equipment.find(e => e.id === asset_id) || {};
        return axios.post(`${API}/crm/v2/contracts/${id}/assets`, {
          asset_id, asset_name: eq.name, model_code: eq.model, serial_number: eq.serial_number,
          site_id: eq.site_id, coverage_type: 'full',
        }, { headers: headers() });
      }));
      if (!asDraft) {
        await axios.put(`${API}/crm/v2/contracts/${id}`, { status: 'pending_approval' }, { headers: headers() });
      }
      onCreated?.(id);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const stepProps = { form, setForm, c, isDark, inp, catalog, templates, companies, contacts, sites, engineers, equipment };

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/60 backdrop-blur-sm"
         data-testid="contract-wizard" onClick={onClose}>
      <div className="max-w-3xl w-full mx-4 rounded-2xl shadow-2xl flex flex-col"
           onClick={e => e.stopPropagation()}
           style={{ background: isDark ? 'var(--color-neutral-900)' : '#fff',
                    border: `1px solid ${c.border}`, maxHeight: '90vh' }}>
        <Header step={step} c={c} isDark={isDark} onClose={onClose} />
        <Stepper step={step} isDark={isDark} c={c} />
        <StepShell>
          {STEPS[step].id === 'customer'    && <CustomerStep {...stepProps} />}
          {STEPS[step].id === 'assets'      && <AssetsStep {...stepProps} />}
          {STEPS[step].id === 'cover'       && <CoverStep {...stepProps} />}
          {STEPS[step].id === 'inclusions'  && <InclusionsStep {...stepProps} />}
          {STEPS[step].id === 'exclusions'  && <ExclusionsStep {...stepProps} />}
          {STEPS[step].id === 'consumables' && <ConsumablesStep {...stepProps} />}
          {STEPS[step].id === 'response'    && <ResponseStep {...stepProps} />}
          {STEPS[step].id === 'pricing'     && <PricingStep {...stepProps} />}
          {STEPS[step].id === 'terms'       && <TermsStep {...stepProps} />}
          {STEPS[step].id === 'review'      && <ReviewStep {...stepProps} />}
        </StepShell>
        {error && (
          <div className="px-5 py-2 text-xs" style={{ color: 'var(--color-danger)' }} data-testid="wizard-error">
            {error}
          </div>
        )}
        <div className="px-5 py-3 flex items-center gap-2"
             style={{ borderTop: `1px solid ${c.border}` }}>
          <button onClick={back} disabled={step === 0} data-testid="wizard-back-btn"
                  className="px-3 py-1.5 text-xs font-semibold rounded-md flex items-center gap-1 disabled:opacity-40"
                  style={{ color: c.textMuted }}>
            <ChevronLeft size={12} /> Back
          </button>
          <div className="flex-1 text-center text-[11px]" style={{ color: c.textDim }}>
            {form.title ? `Drafting: ${form.title}` : 'Untitled contract'}
          </div>
          {step < STEPS.length - 1 ? (
            <button onClick={next} disabled={!canNext()} data-testid="wizard-next-btn"
                    className="px-3 py-1.5 text-xs font-semibold rounded-md bg-[var(--color-info-ios)] text-white flex items-center gap-1 disabled:opacity-40">
              Next <ChevronRight size={12} />
            </button>
          ) : (
            <div className="flex gap-2">
              <button onClick={() => finalise({ asDraft: true })} disabled={saving} data-testid="wizard-save-draft-btn"
                      className="px-3 py-1.5 text-xs font-semibold rounded-md border"
                      style={{ borderColor: c.border, color: c.textMuted }}>
                {saving ? 'Saving…' : 'Save Draft'}
              </button>
              <button onClick={() => finalise({ asDraft: false })} disabled={saving} data-testid="wizard-submit-btn"
                      className="px-3 py-1.5 text-xs font-semibold rounded-md bg-emerald-600 text-white flex items-center gap-1">
                <Check size={12} /> {saving ? 'Submitting…' : 'Submit for Approval'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
